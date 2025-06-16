import os

from config.components.locale import TIME_ZONE

IS_USE_CELERY = os.getenv("IS_USE_CELERY", "False").lower() == "true"
# celery
CELERY_IMPORTS = ()
CELERY_TIMEZONE = TIME_ZONE  # celery 时区问题
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "amqp://admin:password@rabbitmq.lite/")

if IS_USE_CELERY:
    INSTALLED_APPS = locals().get("INSTALLED_APPS", [])
    INSTALLED_APPS += (
        "django_celery_beat",
        "django_celery_results",
    )
    CELERY_ENABLE_UTC = False
    CELERY_WORKER_CONCURRENCY = 2  # 并发数
    CELERY_MAX_TASKS_PER_CHILD = 5  # worker最多执行5个任务便自我销毁释放内存
    CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers.DatabaseScheduler"
    CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
    CELERY_ACCEPT_CONTENT = ["application/json"]
    CELERY_TASK_SERIALIZER = "json"
    CELERY_RESULT_SERIALIZER = "json"
    CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND")
    DJANGO_CELERY_BEAT_TZ_AWARE = False
