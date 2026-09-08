import re
from typing import Any, Dict, Iterable, List, Tuple

from apps.alerts.enrichment.merge import normalize_namespace_payload

ENRICHMENT_PATH_PATTERN = re.compile(r"^enrichment\.[A-Za-z][A-Za-z0-9_]{0,63}(?:\.[A-Za-z][A-Za-z0-9_]{0,63})+$")


def is_enrichment_path(value: str) -> bool:
    return bool(ENRICHMENT_PATH_PATTERN.fullmatch(str(value or "")))


def enrichment_orm_lookup(path: str) -> str:
    if not is_enrichment_path(path):
        raise ValueError("非法 enrichment 路径")
    return "__".join(path.split("."))


def enrichment_orm_lookups(path: str) -> Tuple[str, str]:
    """返回当前对象结构和历史数组结构的 ORM 路径。"""
    current = enrichment_orm_lookup(path)
    segments = path.split(".")
    legacy = "__".join([segments[0], segments[1], "0", *segments[2:]])
    return current, legacy


def resolve_data_path(data: Dict[str, Any], path: str) -> Any:
    current: Any = data
    for segment in path.split("."):
        if isinstance(current, list):
            current = normalize_namespace_payload(current)
        if not isinstance(current, dict):
            return None
        current = current.get(segment)
    return current


def flatten_enrichment(enrichment: Dict[str, Any], *, max_items: int = 20, max_value_length: int = 200) -> List[Tuple[str, str]]:
    """将 enrichment 展开为有界、稳定的展示项，不输出无界对象。"""
    items: List[Tuple[str, str]] = []

    def walk(value: Any, segments: Iterable[str]) -> None:
        if len(items) >= max_items:
            return
        if isinstance(value, dict):
            for key in sorted(value):
                if key == "_meta":
                    continue
                walk(value[key], [*segments, str(key)])
            return
        if isinstance(value, list):
            rendered = ", ".join(str(item) for item in value)
        else:
            rendered = str(value)
        items.append((".".join(segments), rendered[:max_value_length]))

    walk(enrichment or {}, [])
    return items
