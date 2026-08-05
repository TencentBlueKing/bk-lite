import hashlib
import json
from dataclasses import dataclass

SOURCE_ID_MAX_LENGTH = 100
_MIN_DIGEST_LENGTH = 32


@dataclass(frozen=True)
class AggregateGroupIdentity:
    """聚合分组的持久化身份及升级期兼容别名。"""

    source_id: str
    legacy_source_ids: tuple[str, ...] = ()


def build_aggregate_group_identity(policy_id, result, group_by):
    """构建定长、无歧义的聚合分组身份。

    无分组策略保持历史身份不变；有分组策略使用带版本前缀的规范化 JSON
    摘要，并在旧身份满足数据库长度契约时提供版本切换兼容别名。
    """
    fields = tuple(group_by or ())
    if not fields:
        return AggregateGroupIdentity(source_id=f"policy_{policy_id}_")

    canonical_groups = [
        {
            "field": str(field),
            "present": field in result,
            "value": result.get(field),
        }
        for field in sorted(fields, key=str)
    ]
    canonical = json.dumps(
        {"groups": canonical_groups, "version": 2},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    prefix = f"policy_{policy_id}_g2_"
    digest_length = SOURCE_ID_MAX_LENGTH - len(prefix)
    if digest_length < _MIN_DIGEST_LENGTH:
        raise ValueError("policy id is too long to build aggregate group source id")
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:digest_length]
    source_id = f"{prefix}{digest}"

    legacy_source_id = f"policy_{policy_id}_{_build_legacy_group_key(result, fields)}"
    aliases = (legacy_source_id,) if len(legacy_source_id) <= SOURCE_ID_MAX_LENGTH else ()
    return AggregateGroupIdentity(source_id=source_id, legacy_source_ids=aliases)


def _build_legacy_group_key(result, group_by):
    group_values = []
    for field in group_by:
        field_value = result.get(field, "unknown")
        if isinstance(field_value, list):
            formatted_value = ",".join(str(item) for item in field_value)
        elif isinstance(field_value, dict):
            formatted_value = str(field_value)
        elif field_value is None:
            formatted_value = "null"
        else:
            formatted_value = str(field_value)
        group_values.append(f"{field}={formatted_value}")
    return ", ".join(group_values)
