import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if BASE_DIR.name == "config":
    BASE_DIR = BASE_DIR.parent
SECRET_KEY = os.getenv("SECRET_KEY", "")
APP_CODE = os.getenv("APP_CODE", "bk-lite")
DASHBOARD_SHARE_SIGNING_KEY = os.getenv("DASHBOARD_SHARE_SIGNING_KEY", "")
DASHBOARD_SHARE_SESSION_AGE = int(os.getenv("DASHBOARD_SHARE_SESSION_AGE", "1800"))

SESSION_COOKIE_AGE = 60 * 60 * 24 * 7 * 2
SESSION_COOKIE_NAME = f"{APP_CODE}_sessionid"
LOGIN_CACHE_EXPIRED = 60 * 60
# CSRF配置
CSRF_COOKIE_NAME = f"{APP_CODE}_csrftoken"

ALLOWED_HOSTS = ["*"]

ASGI_APPLICATION = "asgi.application"

DEBUG = os.getenv("DEBUG", "0").lower() in ["1", "true"]
STATIC_URL = "static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles/")
