"""
Bridge MQTT para tags de campo.

Estrategia:
  - write_tag: Publica el valor en el topic configurado usando el singleton
               mqtt_client (conexión TCP persistente, sin overhead de reconexión).
  - read_tag:  Se suscribe temporalmente al topic y espera el primer mensaje
               con timeout. Útil para lecturas on-demand (no para polling continuo,
               que ya lo hace el engine de adquisición con suscripciones permanentes).
"""
import asyncio
import json
import logging
from typing import Any, Dict, Optional

from app.services.bridges.base import IndustrialDriver
from app.core.mqtt_client import mqtt_client

logger = logging.getLogger(__name__)


class MqttBridge(IndustrialDriver):
    """
    Driver MQTT para escritura y lectura one-shot de tags de campo.

    connection_config esperado:
    {
        "topic":    "planta/motor01/setpoint",   # topic donde publicar / suscribirse
        "json_key": "value",                     # (opcional) clave dentro del JSON
        "qos":      1,                           # (opcional, default 1)
        "retain":   false                        # (opcional, default false)
    }
    """

    def __init__(self, connection_config: Dict[str, Any]) -> None:
        super().__init__(connection_config)
        self._topic: str = connection_config.get("topic", "")
        self._json_key: Optional[str] = connection_config.get("json_key")
        self._qos: int = int(connection_config.get("qos", 1))
        self._retain: bool = bool(connection_config.get("retain", False))

    # ------------------------------------------------------------------
    # Lifecycle — MQTT usa la conexión singleton, no abre/cierra TCP aquí
    # ------------------------------------------------------------------

    async def connect(self) -> bool:
        """
        El bridge MQTT no gestiona su propia conexión TCP.
        Reutiliza el singleton mqtt_client que ya está conectado al broker.
        """
        if not self._topic:
            logger.error("[MQTT Bridge] 'topic' no configurado en connection_config")
            return False

        if not mqtt_client.is_connected:
            logger.warning(
                "[MQTT Bridge] mqtt_client no está conectado al broker — "
                "el mensaje se encolará y se enviará al reconectar."
            )
        self.connected = True
        return True

    async def disconnect(self) -> None:
        """No-op: la conexión es compartida con el resto del backend."""
        self.connected = False

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def write_tag(self, tag_config: Dict[str, Any], value: Any) -> bool:
        """
        Publica 'value' en el topic del dispositivo de campo.

        El payload puede enviarse de dos formas:
          - Si se definió 'json_key': {"<json_key>": value, "ts": "..."}
          - Si no:                    el valor como string simple

        Args:
            tag_config: connection_config del tag (contiene topic, qos, etc.)
            value:      Valor ya escalado inversamente (raw) que debe llegar al device.

        Returns:
            True si el mensaje se encoló correctamente en el broker.
        """
        topic = tag_config.get("topic") or self._topic
        if not topic:
            logger.error("[MQTT Bridge] write_tag: topic vacío")
            return False

        json_key = tag_config.get("json_key") or self._json_key
        qos = int(tag_config.get("qos", self._qos))
        retain = bool(tag_config.get("retain", self._retain))

        if json_key:
            payload = json.dumps({json_key: value})
        else:
            # Payload raw — el dispositivo lo recibe como string simple
            payload = json.dumps(value) if not isinstance(value, str) else value

        logger.info(
            "[MQTT Bridge] write_tag → topic='%s' payload='%s' qos=%s retain=%s",
            topic, payload, qos, retain,
        )

        success = await mqtt_client.publish(topic, payload, qos=qos, retain=retain)

        if not success:
            logger.error("[MQTT Bridge] Fallo al encolar mensaje en broker [topic=%s]", topic)

        return success

    # ------------------------------------------------------------------
    # Read (one-shot con timeout)
    # ------------------------------------------------------------------

    async def read_tag(self, tag_config: Dict[str, Any]) -> Any:
        """
        Lectura one-shot: se suscribe al topic y espera el primer mensaje
        con un timeout de 3 segundos.

        NOTA: Para adquisición continua el engine.py usa suscripciones
        permanentes. Este método existe para diagnóstico puntual o tests.

        Returns:
            El valor parseado o None si timeout/error.
        """
        topic = tag_config.get("topic") or self._topic
        json_key = tag_config.get("json_key") or self._json_key

        if not topic:
            logger.error("[MQTT Bridge] read_tag: topic vacío")
            return None

        try:
            import aiomqtt
            from app.core.config import get_settings

            cfg = get_settings()

            # Abre una conexión efímera sólo para esta lectura
            async with aiomqtt.Client(
                hostname=cfg.mqtt_broker_host,
                port=cfg.mqtt_broker_port,
                username=cfg.mqtt_username,
                password=cfg.mqtt_password,
                keepalive=10,
            ) as client:
                await client.subscribe(topic)
                async with asyncio.timeout(3.0):
                    async for message in client.messages:
                        raw = message.payload
                        if isinstance(raw, bytes):
                            raw = raw.decode("utf-8", errors="replace")

                        # Intenta parsear como JSON
                        try:
                            parsed = json.loads(raw)
                            if json_key and isinstance(parsed, dict):
                                return parsed.get(json_key)
                            return parsed
                        except (json.JSONDecodeError, TypeError):
                            # Payload plano (string/número)
                            try:
                                return float(raw)
                            except ValueError:
                                return raw

        except TimeoutError:
            logger.warning("[MQTT Bridge] read_tag timeout esperando mensaje en '%s'", topic)
            return None
        except Exception as e:
            logger.error("[MQTT Bridge] read_tag error: %s", e)
            return None
