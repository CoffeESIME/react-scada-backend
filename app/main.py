"""
Punto de entrada principal de la aplicación FastAPI SCADA.
"""
import asyncio  # <--- Necesario para create_task y gather
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db.session import init_db
from app.api import endpoints 
# from app.api import auth, screens 

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager para startup y shutdown."""
    # --- STARTUP ---
    print(f"🚀 Starting {settings.app_name}...")
    
    # 1. Inicializar DB
    if settings.debug:
        await init_db()
        print("✅ Database initialized")
    
    # 2. Iniciar Motores
    # Importamos aquí dentro para evitar referencias circulares
    from app.services.engine import data_acquisition_loop
    from app.services.mqtt_listener import start_mqtt_listener
    
    # Guardamos las tareas en variables
    # (Usamos asyncio.create_task que requiere el import de arriba)
    data_task = asyncio.create_task(data_acquisition_loop())
    listener_task = asyncio.create_task(start_mqtt_listener())
    
    print("✅ Background Services Started (Poller & Listener)")
    
    yield # La app corre aquí
    
    # --- SHUTDOWN ---
    print("🛑 Shutting down...")
    
    # Cancelación controlada
    tasks = [data_task, listener_task]
    for task in tasks:
        task.cancel()
    
    print("⏳ Waiting for services to stop...")
    try:
        # Esperamos a que terminen limpiamente
        await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        print(f"⚠️ Error during graceful shutdown: {e}")
            
    print("✅ All services stopped.")


# Crear aplicación FastAPI
app = FastAPI(
    title=settings.app_name,
    description="Sistema SCADA IIoT",
    version="0.1.0",
    lifespan=lifespan,
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrar routers
app.include_router(endpoints.router, prefix="/api")

@app.get("/")
async def root():
    return {"status": "running", "system": "SCADA Backend v1", "driver": "psycopg"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

# --- BLOQUE DE EJECUCIÓN ---
if __name__ == "__main__":
    # Ahora puedes usar reload=True si quieres, ya no explotará en Windows
    # porque psycopg soporta el bucle que usa Uvicorn por defecto.
    uvicorn.run("app.main:app", host="127.0.0.1", port=8888, reload=True)