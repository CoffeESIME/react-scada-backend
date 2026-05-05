"""
Base para Alembic migrations.
Importa todos los modelos aquí para que Alembic los detecte.
"""
from sqlmodel import SQLModel


from app.db.models import User, Tag, Metric, Alarm, Screen, Node, Edge


target_metadata = SQLModel.metadata
