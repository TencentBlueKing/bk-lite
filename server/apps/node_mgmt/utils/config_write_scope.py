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


def _signing_key():
    return os.getenv("NODE_CONFIG_WRITE_SIGNING_KEY") or settings.SECRET_KEY


def build_config_write_scope(source_app, operation, payload):
    if source_app not in MANAGED_CONFIG_OWNER_MODELS or operation not in ALLOWED_OPERATIONS:
        raise BaseAppException("不支持的配置调用范围")
    if not isinstance(payload, dict):
        raise BaseAppException("配置调用参数必须是对象")
    return signing.dumps(
        {"source_app": source_app, "operation": operation, "payload": payload},
        key=_signing_key(),
        salt=CONFIG_WRITE_SCOPE_SALT,
        compress=True,
    )


def verify_config_write_scope(token, expected_operation):
    try:
        scope = signing.loads(
            token,
            key=_signing_key(),
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
    for source_app, (app_label, model_name) in MANAGED_CONFIG_OWNER_MODELS.items():
        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:
            continue
        owned_ids = model.objects.filter(id__in=normalized_ids, is_child=is_child).values_list("id", flat=True)
        for config_id in owned_ids:
            owners.setdefault(str(config_id), set()).add(source_app)
    return owners


def assert_managed_config_owner(ids, source_app, *, is_child):
    if source_app not in MANAGED_CONFIG_OWNER_MODELS:
        raise BaseAppException("配置归属校验失败")
    owners = _owners_by_config_id(ids, is_child=is_child)
    if not owners or any(owner_set != {source_app} for owner_set in owners.values()):
        raise BaseAppException("配置归属校验失败")


def assert_config_ids_unmanaged(ids, *, is_child):
    owners = _owners_by_config_id(ids, is_child=is_child)
    if any(owner_set for owner_set in owners.values()):
        raise BaseAppException("托管配置必须使用带调用范围的接口")
