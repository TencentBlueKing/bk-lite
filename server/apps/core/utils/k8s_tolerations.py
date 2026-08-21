import re

from apps.core.exceptions.base_app_exception import ValidationAppException

MAX_K8S_DS_TOLERATIONS = 16
ALLOWED_K8S_DS_TOLERATION_EFFECTS = frozenset({"NoSchedule", "NoExecute"})
ALLOWED_K8S_DS_TOLERATION_FIELDS = frozenset({"key", "effect", "value"})
DEFAULT_K8S_DS_TOLERATIONS = [
    {"key": "node-role.kubernetes.io/control-plane", "effect": "NoSchedule"},
    {"key": "node-role.kubernetes.io/master", "effect": "NoSchedule"},
]

_NAME_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9._-]{0,61}[A-Za-z0-9])?$")
_DNS_LABEL_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")


def _validate_key(key) -> str:
    if not isinstance(key, str) or not key:
        raise ValidationAppException("污点容忍 key 必填且必须为非空字符串")
    if "__" in key:
        raise ValidationAppException("污点容忍 key 不能包含 __")
    if key.count("/") > 1:
        raise ValidationAppException("污点容忍 key 最多包含一个 /")
    if "/" in key:
        prefix, name = key.split("/")
        if len(prefix) > 253 or not all(_DNS_LABEL_RE.fullmatch(part) for part in prefix.split(".")):
            raise ValidationAppException("污点容忍 key 前缀不是合法 DNS 子域")
    else:
        name = key
    if not _NAME_RE.fullmatch(name):
        raise ValidationAppException("污点容忍 key 不符合 Kubernetes qualified name")
    return key


def _validate_value(value) -> str:
    if not isinstance(value, str):
        raise ValidationAppException("污点容忍 value 必须为字符串")
    if "__" in value:
        raise ValidationAppException("污点容忍 value 不能包含 __")
    if value and not _NAME_RE.fullmatch(value):
        raise ValidationAppException("污点容忍 value 不符合 Kubernetes label value")
    return value


def _normalize_item(entry) -> dict:
    if not isinstance(entry, dict):
        raise ValidationAppException("污点容忍清单项必须为对象")
    unknown = sorted(set(entry) - ALLOWED_K8S_DS_TOLERATION_FIELDS)
    if unknown:
        raise ValidationAppException("污点容忍清单不允许未知字段")

    item = {
        "key": _validate_key(entry.get("key")),
        "effect": entry.get("effect"),
    }
    if item["effect"] not in ALLOWED_K8S_DS_TOLERATION_EFFECTS:
        raise ValidationAppException("污点容忍 effect 必须为 NoSchedule 或 NoExecute")

    if "value" in entry and entry.get("value") is not None:
        item["value"] = _validate_value(entry.get("value"))
    return item


def normalize_k8s_tolerations(value=None):
    """规范化 DaemonSet 污点容忍清单。

    None 表示未配置，调用方不得传给 webhookd（缺省注入默认两条）。
    空列表表示显式零容忍，必须原样下发。
    """
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValidationAppException("污点容忍清单必须为数组")
    if len(value) > MAX_K8S_DS_TOLERATIONS:
        raise ValidationAppException(f"污点容忍清单最多 {MAX_K8S_DS_TOLERATIONS} 项")
    return [_normalize_item(entry) for entry in value]


def apply_k8s_tolerations_param(params: dict, value=None) -> dict:
    """把三态清单写入 webhookd 请求：None 省略字段，[] 显式下发。"""
    normalized = normalize_k8s_tolerations(value)
    if normalized is not None:
        params["tolerations"] = normalized
    return params
