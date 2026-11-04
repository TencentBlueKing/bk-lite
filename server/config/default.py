from celery.schedules import crontab  # noqa: F401 - 供 split-settings 共享配置命名空间使用
from split_settings.tools import include, optional  # noqa: F401 - 保留共享配置命名空间

from apps.core.celery_runtime.environment import load_runtime_environment

load_runtime_environment()

include(
    "components/base.py",
    "components/locale.py",
    "components/app.py",
    "components/cache.py",
    "components/celery.py",
    "components/database.py",
    "components/drf.py",
    "components/log.py",
    "components/minio.py",
    "components/nats.py",
    "components/extra.py",
    "components/mlflow.py",
)
