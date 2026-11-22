"""Base Celery tasks. Crawler and marketplace sync tasks will be added here."""

from __future__ import annotations

from app.worker.celery_app import celery_app


@celery_app.task(name="app.worker.tasks.ping")
def ping() -> str:
    """Health ping task to verify worker connectivity."""
    return "pong"
