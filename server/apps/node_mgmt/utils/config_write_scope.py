import json
import os

from django.apps import apps
from django.conf import settings
from django.core import signing

from apps.core.exceptions.base_app_exception import BaseAppException

CONFIG_WRITE_SCOPE_SALT = "bk-lite.node-config-write-scope.v1"
CONFIG_WRITE_SCOPE_MAX_AGE_SECONDS = 60
CONFIG_WRITE_SCOPE_MAX_AGE_LIMIT_SECONDS = 300
MANAGED_CONFIG_OWNER_MODELS = {
    "log": ("log", "CollectConfig"),
    "monitor": ("monitor", "CollectConfig"),
}
ALLOWED_OPERATIONS = {"update", "delete", "update_child", "delete_child"}


def _env_enabled(name):
    return os.getenv(name, "false").strip().lower() in {"1", "true", "yes", "on"}


def config_write_scope_signing_enabled():
    return _env_enabled("NODE_CONFIG_WRITE_SCOPE_SIGNING_ENABLED")


def config_write_scope_enforcement_enabled():
    return _env_enabled("NODE_CONFIG_WRITE_SCOPE_ENFORCEMENT_ENABLED")


def _max_age_seconds():
    raw_value = os.getenv(
        "NODE_CONFIG_WRITE_SCOPE_MAX_AGE_SECONDS",
        str(CONFIG_WRITE_SCOPE_MAX_AGE_SECONDS),
    )
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = CONFIG_WRITE_SCOPE_MAX_AGE_SECONDS
    return min(max(value, 1), CONFIG_WRITE_SCOPE_MAX_AGE_LIMIT_SECONDS)


def _signing_keys():
    dedicated_key = os.getenv("NODE_CONFIG_WRITE_SIGNING_KEY")
    if not dedicated_key:
        return settings.SECRET_KEY, list(getattr(settings, "SECRET_KEY_FALLBACKS", ()))

    try:
        fallback_keys = json.loads(os.getenv("NODE_CONFIG_WRITE_SIGNING_KEY_FALLBACKS", "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        fallback_keys = []
    if not isinstance(fallback_keys, list):
        fallback_keys = []
    return dedicated_key, [key for key in fallback_keys if isinstance(key, str) and key]


def build_config_write_scope(source_app, operation, payload):
    if source_app not in MANAGED_CONFIG_OWNER_MODELS or operation not in ALLOWED_OPERATIONS:
        raise BaseAppException("不支持的配置调用范围")
    if not isinstance(payload, dict):
        raise BaseAppException("配置调用参数必须是对象")
    signing_key, _ = _signing_keys()
    return signing.dumps(
        {"source_app": source_app, "operation": operation, "payload": payload},
        key=signing_key,
        salt=CONFIG_WRITE_SCOPE_SALT,
        compress=True,
    )


def verify_config_write_scope(token, expected_operation):
    signing_key, fallback_keys = _signing_keys()
    try:
        scope = signing.loads(
            token,
            key=signing_key,
            fallback_keys=fallback_keys,
            salt=CONFIG_WRITE_SCOPE_SALT,
            max_age=_max_age_seconds(),
        )
    except (signing.BadSignature, signing.SignatureExpired, TypeError, ValueError) as exc:
        raise BaseAppException("配置调用范围无效或已过期") from exc

    if (
        not isinstance(scope, dict)
        or scope.get("source_app") not in MANAGED_CONFIG_OWNER_MODELS
        or scope.get("operation") != expected_operation
        or not isinstance(scope.get("payload"), dict)
    ):
        raise BaseAppException("配置调用范围无效或已过期")
    return scope["source_app"], scope["payload"]


def _owners_by_config_id(ids, *, is_child):
    normalized_ids = {str(config_id) for config_id in ids if config_id is not None}
    owners = {config_id: set() for config_id in normalized_ids}
    installed_owner_apps = set()
    for source_app, (app_label, model_name) in MANAGED_CONFIG_OWNER_MODELS.items():
        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:
            continue
        installed_owner_apps.add(source_app)
        owned_ids = model.objects.filter(id__in=normalized_ids, is_child=is_child).values_list("id", flat=True)
        for config_id in owned_ids:
            owners.setdefault(str(config_id), set()).add(source_app)
    return owners, installed_owner_apps


def assert_managed_config_owner(ids, source_app, *, is_child):
    if source_app not in MANAGED_CONFIG_OWNER_MODELS:
        raise BaseAppException("配置归属校验失败")
    owners, installed_owner_apps = _owners_by_config_id(ids, is_child=is_child)
    if source_app not in installed_owner_apps:
        if any(owner_set for owner_set in owners.values()):
            raise BaseAppException("配置归属校验失败")
        return
    if not owners or any(owner_set != {source_app} for owner_set in owners.values()):
        raise BaseAppException("配置归属校验失败")


def assert_config_ids_unmanaged(ids, *, is_child):
    if config_ids_managed(ids, is_child=is_child):
        raise BaseAppException("托管配置必须使用带调用范围的接口")


def config_ids_managed(ids, *, is_child):
    owners, _ = _owners_by_config_id(ids, is_child=is_child)
    return any(owner_set for owner_set in owners.values())
