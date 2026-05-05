"""
Configuración del Engine Async para SQLAlchemy/SQLModel.
"""
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.core.config import settings


async_engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,  
    future=True,
    pool_pre_ping=True,  
    pool_size=10,
    max_overflow=20,
)


async_session_factory = sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def init_db() -> None:
    """
    Inicializa las tablas de la base de datos.
    Solo usar en desarrollo, en producción usar Alembic.
    """
    async with async_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency para obtener una sesión de base de datos.
    
    Uso:
        @router.get("/items")
        async def get_items(session: AsyncSession = Depends(get_session)):
            ...
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
