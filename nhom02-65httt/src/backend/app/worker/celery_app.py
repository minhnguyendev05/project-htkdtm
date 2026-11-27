"""Celery application configuration using Redis broker and Asia/Ho_Chi_Minh timezone."""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "erp_smart_pricing",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["market_data.tasks"],
)

celery_app.conf.update(
    timezone="Asia/Ho_Chi_Minh",
    enable_utc=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    beat_schedule={
        "market-data-daily-active-product-crawl": {
            "task": "market_data.tasks.crawl_active_products_task",
            "schedule": crontab(hour=2, minute=0),
            "kwargs": {
                "limit": 100,
                "min_products": 60,
                "min_delay": 2.0,
                "max_delay": 4.0,
            },
        },
    },
)

celery_app.autodiscover_tasks(["app.worker"])
