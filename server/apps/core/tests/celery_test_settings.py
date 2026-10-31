"""只供公共 Celery/Beat 基础设施测试，不能用于部署。"""

SECRET_KEY = "celery-runtime-test-only"
INSTALLED_APPS = ("django.contrib.auth", "django.contrib.contenttypes", "django_celery_beat")
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
USE_TZ = True
TIME_ZONE = "UTC"
MIDDLEWARE = ()
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
