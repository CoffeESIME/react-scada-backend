"""
Script para limpiar completamente la base de datos SCADA.
Elimina todos los datos de tags, métricas, alarmas y pantallas.

Uso:
    python scripts/reset_db.py

ADVERTENCIA: Esto eliminará TODOS los datos. Usar con precaución.
"""
import asyncio
import sys
import os

# Agregar el directorio padre al path para importar módulos de la app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.db.session import async_session_factory

async def reset_database():
    """Limpia todas las tablas de la base de datos."""
    
    print("=" * 60)
    print("🚨 ADVERTENCIA: Este script eliminará TODOS los datos.")
    print("=" * 60)
    
    confirmation = input("Escribe 'SI' para confirmar: ")
    if confirmation.strip().upper() != "SI":
        print("❌ Operación cancelada.")
        return
    
    print("\n🔄 Iniciando limpieza de la base de datos...")
    
    async with async_session_factory() as session:
        try:
            # Orden importante: eliminar primero las tablas con FK
            # Usamos IF EXISTS para evitar errores si la tabla no existe
            
            # 1. Eliminar métricas (historial)
            try:
                result = await session.execute(text("DELETE FROM metrics"))
                print(f"   ✅ Métricas eliminadas: {result.rowcount} registros")
            except Exception as e:
                print(f"   ⚠️ Tabla metrics no existe o error: {e}")
            
            # 2. Eliminar alarmas activas (puede no existir)
            try:
                result = await session.execute(text("DELETE FROM active_alarms"))
                print(f"   ✅ Alarmas activas eliminadas: {result.rowcount} registros")
            except Exception:
                print(f"   ⚠️ Tabla active_alarms no existe (OK)")
            
            # 3. Eliminar definiciones de alarmas
            try:
                result = await session.execute(text("DELETE FROM alarm_definitions"))
                print(f"   ✅ Definiciones de alarmas eliminadas: {result.rowcount} registros")
            except Exception:
                print(f"   ⚠️ Tabla alarm_definitions no existe (OK)")
            
            # 4. Eliminar tags
            try:
                result = await session.execute(text("DELETE FROM tags"))
                print(f"   ✅ Tags eliminados: {result.rowcount} registros")
            except Exception as e:
                print(f"   ❌ Error eliminando tags: {e}")
            
            # 5. Eliminar pantallas SCADA
            try:
                result = await session.execute(text("DELETE FROM screens"))
                print(f"   ✅ Pantallas eliminadas: {result.rowcount} registros")
            except Exception:
                print(f"   ⚠️ Tabla screens no existe (OK)")
            
            # 6. Resetear secuencias de IDs (ignorar errores)
            for seq in ["tags_id_seq", "screens_id_seq", "alarm_definitions_id_seq", "active_alarms_id_seq"]:
                try:
                    await session.execute(text(f"ALTER SEQUENCE IF EXISTS {seq} RESTART WITH 1"))
                except Exception:
                    pass
            print("   ✅ Secuencias de ID reiniciadas (si existían)")
            
            await session.commit()
            
            print("\n" + "=" * 60)
            print("✅ Base de datos limpiada exitosamente!")
            print("=" * 60)
            print("\n⚠️  IMPORTANTE: Reinicia el backend para limpiar cachés en memoria:")
            print("    docker-compose restart backend")
            print("")
            
        except Exception as e:
            await session.rollback()
            print(f"\n❌ Error durante la limpieza: {e}")
            raise

if __name__ == "__main__":
    asyncio.run(reset_database())
