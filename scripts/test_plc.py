from pyModbusTCP.client import ModbusClient
import time
import os

# CONFIGURACIÓN
PLC_IP = "192.168.0.155"
PORT = 502

c = ModbusClient(host=PLC_IP, port=PORT, unit_id=1, auto_open=True)

print("--- MONITOREO EN VIVO (Ctrl+C para salir) ---")

try:
    while True:
        # Lee el registro 0 (donde pusiste la analógica o el contador)
        regs = c.read_holding_registers(0, 1)
        
        if regs:
            # regs[0] es el valor crudo (0-27648 si es analógica)
            valor_raw = regs[0]
            
            # Simulamos una conversión a voltaje (0-27648 -> 0-10V)
            voltaje = (valor_raw * 10.0) / 27648.0
            
            # Limpiar pantalla y mostrar (opcional, o solo print)
            print(f"📊 Valor PLC: {valor_raw}  |  ⚡ Voltaje aprox: {voltaje:.2f} V")
        else:
            print("❌ Error de lectura")
            
        time.sleep(0.5) # Actualiza cada medio segundo

except KeyboardInterrupt:
    print("\nDeteniendo...")
    c.close()