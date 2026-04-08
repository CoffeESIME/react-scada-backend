"""
Cliente MQTT persistente para el backend SCADA.

Implementa el patrón Singleton con una conexión TCP de larga vida usando aiomqtt.
La conexión se inicia durante el startup de FastAPI y se mantiene viva en un
background task con reconexión automática exponencial.

Topología de Mosquitto soportada:
  - Puerto 1883  → Loopback sin TLS (VPS_LOCAL / DEVELOPMENT)
  - Puerto 8884  → mTLS estricto con CA propia  (EDGE_PLANTA)
"""
import asyncio
import json
import logging
import ssl
from datetime import datetime, timezone
from typing import Any, Optional

import aiomqtt

from app.core.config import DeploymentEnv, Settings, get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_tls_context(cfg: Settings) -> Optional[ssl.SSLContext]:
    """
    Construye y devuelve un SSLContext apropiado según el entorno.

    Casos:
      - DEVELOPMENT / VPS_LOCAL → None  (sin cifrado)
      - EDGE_PLANTA              → mTLS estricto con verificación de servidor y cliente
      - TLS simple (CA custom)   → Verifica sólo el servidor (sin cert cliente)
    """
    if not cfg.mqtt_use_tls:
        return None

    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED

    # Cargar CA personalizada (obligatorio en mTLS)
    if cfg.mqtt_ca_cert:
        ctx.load_verify_locations(cafile=str(cfg.mqtt_ca_cert))
        logger.debug("TLS: CA cargada desde %s", cfg.mqtt_ca_cert)

    # Cargar certificado + clave del cliente (mTLS bidireccional)
    if cfg.mqtt_client_cert and cfg.mqtt_client_key:
        ctx.load_cert_chain(
            certfile=str(cfg.mqtt_client_cert),
            keyfile=str(cfg.mqtt_client_key),
        )
        logger.debug(
            "mTLS: Certificado de cliente cargado: %s", cfg.mqtt_client_cert
        )

    return ctx


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

class MQTTClient:
    """
    Cliente MQTT singleton con conexión persistente.

    Ciclo de vida:
      1. `startup()` se llama una sola vez en el lifespan de FastAPI.
         Lanza `_connection_loop()` como background task.
      2. `_connection_loop()` mantiene la conexión viva indefinidamente y
         redistribuye los mensajes entrantes a los handlers registrados.
      3. `shutdown()` cancela el loop y espera el cierre limpio.
      4. `publish()` / `publish_alarm()` / `send_command()` son seguros para
         llamar desde cualquier endpoint una vez que el cliente esté conectado.
    """

    _instance: Optional["MQTTClient"] = None

    # -------------------------------------------------------------------------
    # Singleton pattern
    # -------------------------------------------------------------------------

    def __new__(cls) -> "MQTTClient":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:  # type: ignore[has-type]
            return
        self._initialized = True

        self._cfg: Settings = get_settings()
        self._tls_context: Optional[ssl.SSLContext] = _build_tls_context(self._cfg)

        # Estado interno
        self._client: Optional[aiomqtt.Client] = None
        self._connected: bool = False
        self._task: Optional[asyncio.Task] = None  # background task
        self._publish_queue: asyncio.Queue = asyncio.Queue(maxsize=1_000)

        logger.info(
            "MQTTClient inicializado | env=%s host=%s:%s tls=%s",
            self._cfg.deployment_env.value,
            self._cfg.mqtt_broker_host,
            self._cfg.mqtt_broker_port,
            self._cfg.mqtt_use_tls,
        )

    # -------------------------------------------------------------------------
    # Lifecycle (llamar desde FastAPI lifespan)
    # -------------------------------------------------------------------------

    async def startup(self) -> None:
        """Inicia el loop de conexión persistente en segundo plano."""
        if self._task and not self._task.done():
            logger.warning("MQTTClient.startup() llamado pero la tarea ya está activa.")
            return
        self._task = asyncio.create_task(
            self._connection_loop(), name="mqtt-connection-loop"
        )
        logger.info("Background task 'mqtt-connection-loop' iniciado.")

    async def shutdown(self) -> None:
        """Cancela el loop de conexión y espera su cierre limpio."""
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(self._task), timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        self._connected = False
        logger.info("MQTTClient detenido limpiamente.")

    # -------------------------------------------------------------------------
    # Background connection loop
    # -------------------------------------------------------------------------

    async def _connection_loop(self) -> None:
        """
        Mantiene la conexión TCP activa indefinidamente.

        En caso de desconexión, reintenta con backoff hasta `mqtt_reconnect_delay`.
        El loop también drena la `_publish_queue` mientras está conectado.
        """
        delay = self._cfg.mqtt_reconnect_delay

        while True:
            try:
                logger.info(
                    "Conectando a MQTT %s:%s...",
                    self._cfg.mqtt_broker_host,
                    self._cfg.mqtt_broker_port,
                )
                async with aiomqtt.Client(
                    hostname=self._cfg.mqtt_broker_host,
                    port=self._cfg.mqtt_broker_port,
                    identifier=self._cfg.mqtt_client_id,
                    username=self._cfg.mqtt_username,
                    password=self._cfg.mqtt_password,
                    keepalive=self._cfg.mqtt_keepalive,
                    tls_context=self._tls_context,  # None → sin TLS
                ) as client:
                    self._client = client
                    self._connected = True
                    logger.info(
                        "✓ Conectado a MQTT broker [%s]",
                        self._cfg.deployment_env.value,
                    )

                    # Drena la cola de publicaciones pendientes mientras hay conexión
                    await self._drain_publish_queue()

            except asyncio.CancelledError:
                logger.info("Connection loop cancelado — saliendo.")
                break
            except aiomqtt.MqttError as exc:
                self._connected = False
                self._client = None
                logger.error(
                    "Error MQTT: %s — reintentando en %.1fs", exc, delay
                )
                await asyncio.sleep(delay)
            except Exception as exc:  # noqa: BLE001
                self._connected = False
                self._client = None
                logger.exception("Error inesperado en connection loop: %s", exc)
                await asyncio.sleep(delay)
            finally:
                self._connected = False
                self._client = None

    async def _drain_publish_queue(self) -> None:
        """
        Consume mensajes de la cola de publicación mientras el cliente está vivo.

        Se suspende esperando el próximo mensaje, lo publica, y repite.
        Si el cliente se desconecta, el MqttError interrumpe este bucle
        y el `_connection_loop` externo inicia la reconexión.
        """
        while self._connected and self._client is not None:
            try:
                # Espera un mensaje con timeout para poder detectar desconexiones
                topic, payload, qos, retain = await asyncio.wait_for(
                    self._publish_queue.get(), timeout=1.0
                )
                await self._client.publish(topic, payload, qos=qos, retain=retain)
                self._publish_queue.task_done()
                logger.debug("Published → %s (qos=%s)", topic, qos)
            except asyncio.TimeoutError:
                # Sin mensajes pendientes — loop normal
                continue
            except aiomqtt.MqttError:
                # Re-lanzar para que _connection_loop maneje la reconexión
                raise
            except asyncio.CancelledError:
                break

    # -------------------------------------------------------------------------
    # API pública de publicación
    # -------------------------------------------------------------------------

    async def publish(
        self,
        topic: str,
        payload: str | bytes,
        qos: int = 1,
        retain: bool = False,
    ) -> bool:
        """
        Encola un mensaje para ser publicado en la conexión persistente.

        No abre ni cierra ninguna conexión TCP — reutiliza la existente.

        Args:
            topic:   Topic MQTT destino (ej: "scada/alarms/motor_01").
            payload: Contenido del mensaje (str o bytes).
            qos:     Quality of Service (0, 1 o 2).
            retain:  Si True, el broker retiene el mensaje para nuevos suscriptores.

        Returns:
            True si se encoló correctamente; False si la cola está llena o hay error.
        """
        if not self._connected:
            logger.warning("publish() llamado pero MQTT no está conectado. [topic=%s]", topic)
            # Intentamos encolar de todas formas — se enviará al reconectar
        try:
            self._publish_queue.put_nowait((topic, payload, qos, retain))
            return True
        except asyncio.QueueFull:
            logger.error(
                "Cola de publicación MQTT llena (max=%s). Mensaje descartado. [topic=%s]",
                self._publish_queue.maxsize,
                topic,
            )
            return False

    async def publish_alarm(
        self,
        alarm_id: str,
        severity: str,
        message: str,
        status: str = "ACTIVE",
    ) -> bool:
        """
        Publica una alarma estructurada en 'scada/alarms/<severity>'.

        Args:
            alarm_id: Identificador único de la alarma.
            severity: Nivel de severidad (info | warning | critical).
            message:  Descripción legible de la alarma.
            status:   Estado (ACTIVE | RESOLVED | ACKNOWLEDGED).
        """
        payload = json.dumps({
            "alarm_id":  alarm_id,
            "severity":  severity,
            "message":   message,
            "status":    status,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        })
        topic = f"scada/alarms/{severity}"
        return await self.publish(topic, payload)

    async def send_command(
        self,
        device_id: str,
        command: str,
        value: Any,
    ) -> bool:
        """
        Envía un comando a un dispositivo (ESP32 / Gateway).

        Args:
            device_id: ID del dispositivo destino.
            command:   Tipo de comando (ej: "set_state", "set_value").
            value:     Valor del comando.
        """
        payload = json.dumps({"command": command, "value": value})
        topic = f"scada/commands/{device_id}"
        return await self.publish(topic, payload)

    # -------------------------------------------------------------------------
    # Diagnóstico
    # -------------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """Indica si la conexión al broker está activa en este momento."""
        return self._connected

    def __repr__(self) -> str:
        return (
            f"<MQTTClient env={self._cfg.deployment_env.value} "
            f"host={self._cfg.mqtt_broker_host}:{self._cfg.mqtt_broker_port} "
            f"connected={self._connected} tls={self._cfg.mqtt_use_tls}>"
        )


# ---------------------------------------------------------------------------
# Singleton global — importar desde aquí en el resto del proyecto
# ---------------------------------------------------------------------------
mqtt_client = MQTTClient()
