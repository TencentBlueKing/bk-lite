"""仅用于独立Celery运行层的临时PostgreSQL验收，不用于业务服务部署。"""

import os

from apps.core.tests.celery_test_settings import DEFAULT_AUTO_FIELD, INSTALLED_APPS, MIDDLEWARE, SECRET_KEY, TIME_ZONE, USE_TZ  # noqa: F401

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "celery_runtime_validation",
        "USER": os.getenv("CELERY_TEST_DB_USER", "postgres"),
        "PASSWORD": os.getenv("CELERY_TEST_DB_PASSWORD", ""),
        "HOST": os.getenv("CELERY_TEST_DB_HOST", "127.0.0.1"),
        "PORT": os.getenv("CELERY_TEST_DB_PORT", "5432"),
        "TEST": {"NAME": "test_celery_runtime_validation"},
    }
}
