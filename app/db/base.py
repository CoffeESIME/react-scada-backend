"""
Base para Alembic migrations.
Importa todos los modelos aquí para que Alembic los detecte.
"""
from sqlmodel import SQLModel

# Importar todos los modelos para que Alembic los registre
from app.db.models import User, Tag, Metric, Alarm, Screen, Node, Edge

# Re-exportar metadata para Alembic
target_metadata = SQLModel.metadata
