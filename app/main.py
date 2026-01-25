"""
Punto de entrada principal de la aplicación FastAPI SCADA.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db.session import init_db
from app.api import endpoints, auth, screens


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager para startup y shutdown."""
    # Startup
    print(f"🚀 Starting {settings.app_name}...")
    
    # Inicializar base de datos (solo desarrollo)
    if settings.debug:
        await init_db()
        print("✅ Database initialized")
    
    # TODO: Iniciar servicios de background
    # from app.services.history import history_service
    # await history_service.start()
    
    yield
    
    # Shutdown
    print("🛑 Shutting down...")
    # TODO: Detener servicios
    # await history_service.stop()


# Crear aplicación FastAPI
app = FastAPI(
    title=settings.app_name,
    description="Sistema SCADA para monitoreo y control industrial",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrar routers
app.include_router(endpoints.router)
app.include_router(auth.router)
app.include_router(screens.router)


@app.get("/")
async def root():
    """Endpoint raíz."""
    return {
        "name": settings.app_name,
        "version": "0.1.0",
        "status": "running"
    }


@app.get("/health")
async def health():
    """Health check para orquestadores."""
    return {"status": "healthy"}
