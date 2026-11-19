import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if BASE_DIR.name == "config":
    BASE_DIR = BASE_DIR.parent
SECRET_KEY = os.getenv("SECRET_KEY", "")
SECRET_KEY_FALLBACKS = json.loads(os.getenv("SECRET_KEY_FALLBACKS", "[]"))
K8S_INSTALL_TOKEN_DB_ENABLED = os.getenv("K8S_INSTALL_TOKEN_DB_ENABLED", "0").lower() in ["1", "true"]
K8S_INSTALL_TOKEN_ISSUANCE_PAUSED = os.getenv("K8S_INSTALL_TOKEN_ISSUANCE_PAUSED", "0").lower() in ["1", "true"]
APP_CODE = os.getenv("APP_CODE", "bk-lite")
DASHBOARD_SHARE_SIGNING_KEY = os.getenv("DASHBOARD_SHARE_SIGNING_KEY", "")
DASHBOARD_SHARE_SESSION_AGE = int(os.getenv("DASHBOARD_SHARE_SESSION_AGE", "28800"))

SESSION_COOKIE_AGE = 60 * 60 * 24 * 7 * 2
SESSION_COOKIE_NAME = f"{APP_CODE}_sessionid"
LOGIN_CACHE_EXPIRED = 60 * 60
# CSRF配置
CSRF_COOKIE_NAME = f"{APP_CODE}_csrftoken"

ALLOWED_HOSTS = ["*"]

ASGI_APPLICATION = "asgi.application"

DEBUG = os.getenv("DEBUG", "0").lower() in ["1", "true"]
WEB_BASE_URL = os.getenv("WEB_BASE_URL", "").rstrip("/")
# 告警作业完成后 job_mgmt 回调 alerts 的本服务入口。Celery 走 HTTP，不能写
# 127.0.0.1/localhost（SSRFValidator.validate_callback 会拦 loopback）。
# K8s Service 名与 Docker Compose 服务名都是 server:8000；未设置或留空时用该默认值。
SELF_BASE_URL = (os.getenv("SELF_BASE_URL") or "http://server:8000").strip().rstrip("/")
# 逗号分隔、host 精确匹配。默认空 = 禁用 legacy 外部回调。现网示例：bklite.ai,bklite.cn
LEGACY_THIRD_LOGIN_ALLOWED_CALLBACK_HOSTS = os.getenv("LEGACY_THIRD_LOGIN_ALLOWED_CALLBACK_HOSTS", "")
STATIC_URL = "static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles/")
