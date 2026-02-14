"""Celery application instance — uses Redis as broker + result backend."""

import os

from celery import Celery

from app.core.config import settings

_broker = settings.REDIS_URL or "redis://127.0.0.1:6379/0"

celery_app = Celery("agentic_payments")

celery_app.conf.update(
    broker_url=_broker,
    result_backend=_broker,
    broker_connection_retry_on_startup=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

# Auto-discover tasks in app.workers.tasks
celery_app.autodiscover_tasks(["app.workers"])
