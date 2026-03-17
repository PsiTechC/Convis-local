"""
Celery Configuration for Background Tasks
Handles delayed workflow execution and scheduled tasks
"""
from celery import Celery
from app.config.settings import settings
import logging

logger = logging.getLogger(__name__)

# Initialize Celery
celery_app = Celery(
    "convis_workflows",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.services.integrations.celery_tasks"]
)

# Celery Configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,  # 10 minutes max per task
    task_soft_time_limit=540,  # 9 minutes soft limit
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    result_expires=86400,  # 24 hours
    broker_connection_retry_on_startup=True,
)

# Task routes (optional - for organizing tasks)
celery_app.conf.task_routes = {
    "app.services.integrations.celery_tasks.execute_delayed_workflow": {"queue": "workflows"},
    "app.services.integrations.celery_tasks.execute_delayed_action": {"queue": "actions"},
}

logger.info("Celery configured successfully")
