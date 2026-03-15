from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    'jobspy_async_api',
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=['app.workers.tasks'],
)

celery_app.conf.update(
    task_soft_time_limit=settings.celery_task_soft_time_limit,
    task_time_limit=settings.celery_task_time_limit,
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    timezone='UTC',
    enable_utc=True,
    beat_schedule={
        'retry-due-webhooks-every-30-seconds': {
            'task': 'webhooks.retry_due',
            'schedule': 30.0,
            'args': (100,),
        },
        'cleanup-retention-daily': {
            'task': 'maintenance.cleanup_retention',
            'schedule': 86400.0,
            'args': (14,),
        },
    },
)
