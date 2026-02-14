"""
Helper to dispatch Celery tasks with an explicit Redis connection.

This avoids issues where uvicorn's subprocess may not correctly
inherit the Celery broker config on Windows.
"""

from app.workers.celery_app import celery_app


def send_execute_payment(payment_id: str) -> None:
    """Send execute_payment task to the Celery broker."""
    celery_app.send_task(
        "app.workers.tasks.execute_payment",
        args=[payment_id],
    )
