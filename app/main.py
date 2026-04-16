"""
Punto de entrada principal de la aplicación FastAPI SCADA (Dockerized).
"""
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
# Uvicorn se invoca desde el Dockerfile, pero lo importamos por si ejecutas manual
import uvicorn 

from app.core.config import settings
from app.db.session import init_db
from app.api import endpoints, auth, tags, screens, history

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager para startup y shutdown."""
    print(f"🚀 Starting {settings.app_name} in Docker...")
    
    # 1. Inicializar DB
    await init_db()
    print("✅ Database initialized")
    
    # 2. Iniciar Motores
    from app.services.engine import data_acquisition_loop
    from app.services.mqtt_listener import start_mqtt_listener
    from app.services.history import history_service
    from app.core.mqtt_client import mqtt_client  # <--- IMPORTANTE
    
    # Iniciar la conexión persistente TCP de subida (Publishing)
    await mqtt_client.startup()
    print("✅ MQTT Publisher Client Started")

    data_task = asyncio.create_task(data_acquisition_loop())
    listener_task = asyncio.create_task(start_mqtt_listener())
    await history_service.start()
    
    print("✅ Background Services Started (Poller, Listener & History)")
    
    yield
    
    # --- SHUTDOWN ---
    print("🛑 Shutting down...")
    
    data_task.cancel()
    listener_task.cancel()
    await history_service.stop()
    await mqtt_client.shutdown()  # <--- Detener limpiamente
    
    try:
        await asyncio.gather(data_task, listener_task, return_exceptions=True)
    except Exception as e:
        print(f"⚠️ Error stopping services: {e}")
            
    print("✅ All services stopped.")


app = FastAPI(
    title=settings.app_name,
    description="Sistema SCADA IIoT (Docker Environment)",
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

# Routers
app.include_router(endpoints.router, prefix="/api")
app.include_router(auth.router)
app.include_router(tags.router, prefix="/api")
app.include_router(screens.router, prefix="/api")
app.include_router(history.router, prefix="/api")

@app.get("/")
async def root():
    return {
        "status": "running", 
        "environment": "Docker/Linux", 
        "db_driver": "psycopg"
    }

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app", 
        host="0.0.0.0", 
        port=8888, 
        reload=True
    )