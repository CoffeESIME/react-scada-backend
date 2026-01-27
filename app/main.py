"""
Punto de entrada principal de la aplicación FastAPI SCADA.
"""
import sys
import asyncio

# --- PARCHE OBLIGATORIO PARA WINDOWS (Asyncpg & Psycopg) ---
# Windows usa por defecto "ProactorEventLoop", que es incompatible con
# los drivers de base de datos asíncronos. Esto fuerza el uso de "Selector".
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
# -----------------------------------------------------------

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn 

from app.core.config import settings
from app.db.session import init_db
from app.api import endpoints, auth 

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager para startup y shutdown."""
    print(f"🚀 Starting {settings.app_name}...")
    
    # 1. Inicializar DB
    if settings.debug:
        await init_db()
        print("✅ Database initialized")
    
    # 2. Iniciar Motores
    from app.services.engine import data_acquisition_loop
    from app.services.mqtt_listener import start_mqtt_listener
    
    data_task = asyncio.create_task(data_acquisition_loop())
    listener_task = asyncio.create_task(start_mqtt_listener())
    
    print("✅ Background Services Started")
    
    yield
    
    # --- SHUTDOWN ---
    print("🛑 Shutting down...")
    data_task.cancel()
    listener_task.cancel()
    
    try:
        await asyncio.wait([data_task, listener_task], timeout=5.0)
    except Exception as e:
        print(f"⚠️ Error stopping services: {e}")
            
    print("✅ All services stopped.")


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(endpoints.router, prefix="/api")
app.include_router(auth.router)

@app.get("/")
async def root():
    return {"status": "running", "driver": "psycopg", "os": sys.platform}

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    # IMPORTANTE: reload=False evita el error WinError 10038
    uvicorn.run("app.main:app", host="127.0.0.1", port=8888, reload=False)