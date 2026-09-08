import re

from apps.core.exceptions.base_app_exception import ValidationAppException

TOLERATIONS_UNSET = object()

MAX_K8S_DAEMONSET_TOLERATIONS = 16
ALLOWED_TOLERATION_EFFECTS = frozenset({"NoSchedule", "NoExecute"})
ALLOWED_TOLERATION_FIELDS = frozenset({"key", "effect", "value"})
PLACEHOLDER_TOKEN = "__"

_NAME_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9._-]{0,61}[A-Za-z0-9])?$")
_DNS_LABEL_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")

DEFAULT_DS_TOLERATIONS = (
    {"key": "node-role.kubernetes.io/control-plane", "effect": "NoSchedule"},
    {"key": "node-role.kubernetes.io/master", "effect": "NoSchedule"},
)


def _fail(message: str) -> None:
    raise ValidationAppException(message)


def _validate_key(key) -> str:
    if not isinstance(key, str) or not key:
        _fail("Invalid tolerations: key is required and must be a non-empty string")
    if PLACEHOLDER_TOKEN in key:
        _fail("Invalid tolerations: __ is reserved for template placeholders")
    if key.count("/") > 1:
        _fail("Invalid tolerations: key has more than one /")
    if "/" in key:
        prefix, name = key.split("/")
        if len(prefix) > 253 or not all(_DNS_LABEL_RE.fullmatch(part) for part in prefix.split(".")):
            _fail(f"Invalid tolerations: key prefix {prefix!r} is not a DNS subdomain")
    else:
        name = key
    if not _NAME_RE.fullmatch(name):
        _fail(f"Invalid tolerations: key name {name!r} violates Kubernetes qualified-name rules")
    return key


def _validate_value(value) -> str:
    if not isinstance(value, str):
        _fail("Invalid tolerations: value must be a string")
    if value and not _NAME_RE.fullmatch(value):
        _fail(f"Invalid tolerations: value {value!r} violates Kubernetes label-value rules")
    if PLACEHOLDER_TOKEN in value:
        _fail("Invalid tolerations: __ is reserved for template placeholders")
    return value


def normalize_k8s_daemonset_tolerations(value):
    """规范化 DaemonSet 污点容忍三态：None 表示缺省，[] 表示零容忍，列表表示显式清单。"""
    if value is None:
        return None
    if not isinstance(value, list):
        _fail("Invalid tolerations: must be a JSON array")
    if len(value) > MAX_K8S_DAEMONSET_TOLERATIONS:
        _fail(f"Invalid tolerations: at most {MAX_K8S_DAEMONSET_TOLERATIONS} items")

    items = []
    for entry in value:
        if not isinstance(entry, dict):
            _fail("Invalid tolerations: items must be objects")
        unknown = sorted(set(entry) - ALLOWED_TOLERATION_FIELDS)
        if unknown:
            _fail(f"Invalid tolerations: unknown fields {unknown} (wildcard tolerations are not allowed)")
        key = _validate_key(entry.get("key"))
        effect = entry.get("effect")
        if effect not in ALLOWED_TOLERATION_EFFECTS:
            _fail("Invalid tolerations: effect must be NoSchedule or NoExecute")
        item = {"key": key, "effect": effect}
        if "value" in entry and entry.get("value") is not None:
            item["value"] = _validate_value(entry.get("value"))
        items.append(item)
    return items


def extract_request_tolerations(data):
    """从请求体取出三态：缺字段为 UNSET，null 为 None，[] / 列表经校验后返回。"""
    if data is None or "tolerations" not in data:
        return TOLERATIONS_UNSET
    return normalize_k8s_daemonset_tolerations(data.get("tolerations"))


def apply_tolerations_to_payload(params: dict, tolerations) -> dict:
    """None / UNSET 省略字段（webhookd 默认两条）；[] 显式写入空清单。"""
    if tolerations is TOLERATIONS_UNSET or tolerations is None:
        return params
    params["tolerations"] = tolerations
    return params


def token_tolerations_kwargs(tolerations) -> dict:
    if tolerations is TOLERATIONS_UNSET:
        return {}
    normalized = normalize_k8s_daemonset_tolerations(tolerations)
    if normalized is None:
        return {}
    return {"tolerations": normalized}


def include_stored_tolerations(payload: dict, stored) -> dict:
    """持久化值写入返回/token：None 表示未配置，不写入；[] 必须写入。"""
    if stored is not None:
        payload["tolerations"] = stored
    return payload
