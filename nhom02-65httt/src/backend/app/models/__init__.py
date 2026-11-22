"""ORM models package. Import all models here so Alembic autogenerate detects them."""

from app.models.user import User

__all__ = ["User"]
