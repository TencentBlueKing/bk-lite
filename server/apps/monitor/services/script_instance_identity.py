"""脚本实例的身份。

脚本实例仍是独立行，主键和序列标签按绑定对象的身份键补齐。
单键对象的主键与现有主机脚本实例相同；多键对象从第二键起固定为 script。
"""

import re

from django.db.models import Exists, OuterRef

from apps.monitor.constants.monitor_object import MonitorObjConstants
from apps.monitor.services.custom_script_plugin import RESERVED_SCRIPT_TAG_KEYS, SCRIPT_COLLECT_TYPE
from apps.monitor.utils.dimension import normalize_instance_identity

SCRIPT_EXTRA_IDENTITY_VALUE = "script"
_IDENTITY_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_RESERVED_IDENTITY_KEYS = frozenset(RESERVED_SCRIPT_TAG_KEYS)


def object_identity_keys(raw_keys) -> list[str]:
    keys = [str(key) for key in (raw_keys or []) if key not in (None, "")]
    return keys or ["instance_id"]


def script_extra_identity_tags(raw_keys) -> list[tuple[str, str]]:
    """第二键及之后。第一键始终是 instance_id，由现有模板写出。"""
    keys = object_identity_keys(raw_keys)
    if keys[0] != "instance_id":
        raise ValueError("脚本实例要求对象的第一身份键是 instance_id")
    tags = []
    for key in keys[1:]:
        if key in _RESERVED_IDENTITY_KEYS or not _IDENTITY_KEY.match(key):
            raise ValueError(f"脚本实例不能使用身份键 {key}")
        tags.append((key, SCRIPT_EXTRA_IDENTITY_VALUE))
    return tags


def script_storage_identity(instance_id, raw_keys) -> dict:
    """把接入页传来的实例 ID 收成脚本实例的存储键。"""
    incoming = normalize_instance_identity(instance_id)
    primary = incoming["logical_instance_value"]
    tags = script_extra_identity_tags(raw_keys)
    values = [primary, *[value for _, value in tags]]
    identity = normalize_instance_identity(tuple(values) if len(values) > 1 else values[0])
    storage_key = identity["storage_instance_key"]
    if len(storage_key) > MonitorObjConstants.INSTANCE_ID_MAX_LENGTH:
        raise ValueError(f"脚本实例标识超过 {MonitorObjConstants.INSTANCE_ID_MAX_LENGTH} 字符，请缩短实例名称")
    return {
        "primary": primary,
        "tags": tags,
        "logical_instance_value": identity["logical_instance_value"],
        "storage_instance_key": storage_key,
    }


def prepare_script_identity_instances(instances, raw_keys) -> list:
    prepared = []
    for instance in instances:
        identity = script_storage_identity(instance.get("instance_id"), raw_keys)
        prepared.append(
            {
                **instance,
                **dict(identity["tags"]),
                "raw_instance_id": instance.get("instance_id"),
                "logical_instance_value": identity["logical_instance_value"],
                "storage_instance_key": identity["storage_instance_key"],
                "instance_id": identity["storage_instance_key"],
                "script_identity_tags": identity["tags"],
            }
        )
    return prepared


def include_script_instances_requested(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def apply_script_instance_visibility(queryset, include: bool):
    """默认列表不含脚本实例。要求包含时给每行标 is_script。"""
    marker = script_instance_exists()
    if include:
        return queryset.annotate(is_script=marker)
    return queryset.exclude(marker)


def policy_selects_script_instances(policy) -> bool:
    """策略指标属于脚本插件时，组织圈选只覆盖脚本实例。无法解析指标时按原生策略处理。"""
    from apps.monitor.models.monitor_metrics import Metric
    from apps.monitor.tasks.utils.policy_multi import query_metric_items

    metric_ids = [item.get("metric_id") for item in query_metric_items(getattr(policy, "query_condition", None) or {}) if item.get("metric_id")]
    if not metric_ids:
        return False
    collect_types = Metric.objects.filter(id__in=metric_ids).values_list("monitor_plugin__collect_type", flat=True)
    return any(str(item or "").casefold() == SCRIPT_COLLECT_TYPE for item in collect_types)


def scope_memberships_for_policy(policy, memberships):
    """组织圈选：脚本指标的策略只留脚本实例，其余策略去掉脚本实例。

    memberships 是 MonitorInstanceOrganization 的查询集，条件直接并进这一条查询。
    """
    marker = script_instance_exists("monitor_instance_id")
    if policy_selects_script_instances(policy):
        return memberships.filter(marker)
    return memberships.exclude(marker)


def script_instance_exists(instance_ref="id"):
    """实例名下有脚本采集配置，即为脚本实例。"""
    from apps.monitor.models.collect_config import CollectConfig

    return Exists(
        CollectConfig.objects.filter(
            monitor_instance_id=OuterRef(instance_ref),
            collect_type__iexact=SCRIPT_COLLECT_TYPE,
        )
    )


def inject_script_identity_tags(rendered: str, tags: list[tuple[str, str]]) -> str:
    """在已渲染的单键子配置上补身份标签和覆盖逻辑。没有额外键时原样返回。"""
    if not tags:
        return rendered
    text = rendered
    tag_lines = "\n".join(f'        {key} = "{value}"' for key, value in tags)
    text = _replace_once(text, "\n\n[[processors.starlark]]", f"\n{tag_lines}\n\n[[processors.starlark]]")
    # 局部变量加前缀，避免身份键叫 name、k、metric 这类名字时盖掉脚本里已有的变量。
    init_lines = "\n".join(f'    extra_{key} = ""' for key, _value in tags)
    text = _replace_once(text, '    script = ""\n', f'    script = ""\n{init_lines}\n')
    read_lines = "\n".join(f'        elif k == "{key}":\n            extra_{key} = metric.tags[k]' for key, _value in tags)
    text = _replace_once(text, '        elif k.startswith("bklite_script_"):\n', f"{read_lines}\n        elif k.startswith(\"bklite_script_\"):\n")
    check_lines = "\n".join(f'    if extra_{key} != "" and extra_{key} != reserved_{key}:\n        conflicts.append("{key}")' for key, _value in tags)
    text = _replace_once(
        text,
        '    if script != "" and script != reserved_script:\n        conflicts.append("script")\n',
        '    if script != "" and script != reserved_script:\n        conflicts.append("script")\n' + check_lines + "\n",
    )
    assign_lines = "\n".join(f'    metric.tags["{key}"] = reserved_{key}' for key, _value in tags)
    text = _replace_once(text, '    metric.tags["script"] = reserved_script\n', f'    metric.tags["script"] = reserved_script\n{assign_lines}\n')
    constant_lines = "\n".join(f'        reserved_{key} = "{value}"' for key, value in tags)
    text = _replace_once(text, '        reserved_script = "default"\n', f'        reserved_script = "default"\n{constant_lines}\n')
    tagpass_lines = "\n".join(f'        {key} = ["{value}"]' for key, value in tags)
    text = _replace_once(text, _tagpass_instance_line(text), _tagpass_instance_line(text) + tagpass_lines + "\n")
    return text


def _tagpass_instance_line(rendered: str) -> str:
    marker = "[processors.starlark.tagpass]\n"
    start = rendered.index(marker) + len(marker)
    line_end = rendered.index("\n", start)
    return rendered[start : line_end + 1]


def _replace_once(text: str, old: str, new: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError("脚本子配置结构无法补齐身份标签")
    return text.replace(old, new, 1)
