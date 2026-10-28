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


def _audit_log_export_max_rows(default=10000):
    """审计日志 Excel 单次导出行数上限。非法或非正数回退默认值。"""
    raw = os.getenv("AUDIT_LOG_EXPORT_MAX_ROWS")
    if raw is None or str(raw).strip() == "":
        return default
    try:
        value = int(str(raw).strip())
    except ValueError:
        return default
    return value if value > 0 else default


# 与 apps.system_mgmt.utils.audit_log_export.EXPORT_MAX_ROWS 默认值保持一致。
AUDIT_LOG_EXPORT_MAX_ROWS = _audit_log_export_max_rows()

SESSION_COOKIE_AGE = 60 * 60 * 24 * 7 * 2
SESSION_COOKIE_NAME = f"{APP_CODE}_sessionid"
LOGIN_CACHE_EXPIRED = 60 * 60
# CSRF配置
CSRF_COOKIE_NAME = f"{APP_CODE}_csrftoken"

ALLOWED_HOSTS = ["*"]

ASGI_APPLICATION = "asgi.application"

DEBUG = os.getenv("DEBUG", "0").lower() in ["1", "true"]
WEB_BASE_URL = os.getenv("WEB_BASE_URL", "").rstrip("/")
# 逗号分隔、host 精确匹配。默认空 = 禁用 legacy 外部回调。现网示例：bklite.ai,bklite.cn
LEGACY_THIRD_LOGIN_ALLOWED_CALLBACK_HOSTS = os.getenv("LEGACY_THIRD_LOGIN_ALLOWED_CALLBACK_HOSTS", "")
STATIC_URL = "static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles/")
