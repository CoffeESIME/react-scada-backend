from pyModbusTCP.client import ModbusClient
import time

# --- CONFIRMA QUE ESTA IP ES LA QUE TIENE EL PLC AHORA ---
# (Si cambiaste a .155 en el hardware, úsala. Si sigue en .20, pon .20)
PLC_IP = "192.168.0.155" 
PORT = 502

print(f"🕵️ Conectando a {PLC_IP}...")
c = ModbusClient(host=PLC_IP, port=PORT, unit_id=1, auto_open=True)

# Intento de conexión explícito
if not c.open():
    print("❌ ERROR DE CONEXIÓN TCP: El puerto 502 está cerrado o inalcanzable.")
    print("   -> Causa probable: Firewall de Windows o el PLC tiene otra IP.")
else:
    print("✅ Conexión TCP establecida. Intentando leer Modbus...")

try:
    while True:
        # Lee el registro 0
        regs = c.read_holding_registers(0, 1)
        
        if regs:
            valor_raw = regs[0]
            voltaje = (valor_raw * 10.0) / 27648.0
            print(f"📊 PLC: {valor_raw}  |  ⚡ {voltaje:.2f} V")
        else:
            # --- AQUÍ ESTÁ EL DIAGNÓSTICO ---
            print("❌ Lectura fallida (None).")
            print(f"   🔴 Razón: {c.last_error_as_txt}")   # <-- BUENO (Propiedad)
            print(f"   🔴 Código Excepción: {c.last_except()}")
            
            # Si dice "Timeout", es red/firewall.
            # Si dice "Illegal Data Address", es el puntero del DB.
            
        time.sleep(1.0)

except KeyboardInterrupt:
    print("\nDeteniendo...")
    c.close()