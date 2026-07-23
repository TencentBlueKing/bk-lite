from typing import Any, Iterable, Mapping


def count_distinct_repair_targets(items: Iterable[Mapping[str, Any]]) -> int:
    """按完整作用域统计修复目标，避免不同空间的同名对象被合并。"""
    identities = {
        (
            str(item.get("namespace") or "").strip(),
            str(item.get("target_type") or "").strip(),
            str(item.get("target_name") or "").strip(),
        )
        for item in items
        if str(item.get("target_name") or "").strip()
    }
    return len(identities)
