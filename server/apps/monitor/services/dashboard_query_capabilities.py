import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from apps.monitor.models import MonitorObject

from .metric_query_contract import AuthorizedMetricQueryError, build_instance_matchers, escape_metric_label_value

CAPABILITY_MANIFEST = Path(__file__).resolve().parent.parent / "support-files" / "dashboard_query_capabilities.json"
MAX_CAPABILITY_TEMPLATE_LENGTH = 20_000
MAX_KAFKA_DIMENSIONS = 10
MAX_KAFKA_DIMENSION_VALUE_LENGTH = 256


def dashboard_query_capability_id(template: str) -> str:
    value = 2166136261
    for byte in template.encode("utf-8"):
        value ^= byte
        value = (value * 16777619) & 0xFFFFFFFF
    return f"dashboard:v1:{value:08x}"


def _query_window(start: int, end: int) -> str:
    seconds = max(1, round((end - start) / 1000))
    for divisor, suffix in ((86400, "d"), (3600, "h"), (60, "m")):
        if seconds % divisor == 0:
            return f"{seconds // divisor}{suffix}"
    return f"{seconds}s"


@dataclass(frozen=True)
class DashboardQueryCapability:
    id: str
    object_names: frozenset[str]
    template: str


@lru_cache(maxsize=1)
def load_dashboard_query_capabilities() -> dict[str, DashboardQueryCapability]:
    payload = json.loads(CAPABILITY_MANIFEST.read_text(encoding="utf-8"))
    if payload.get("version") != 1 or not isinstance(payload.get("capabilities"), list):
        raise RuntimeError("invalid dashboard query capability manifest")

    capabilities = {}
    for item in payload["capabilities"]:
        capability_id = str(item.get("id") or "")
        template = str(item.get("template") or "")
        object_names = item.get("object_names")
        selectors = re.findall(r"\{([^{}]*)\}", template)
        if (
            not capability_id
            or not template
            or len(template) > MAX_CAPABILITY_TEMPLATE_LENGTH
            or "__$labels__" not in template
            or not selectors
            or any("__$labels__" not in selector for selector in selectors)
            or not isinstance(object_names, list)
            or not object_names
            or dashboard_query_capability_id(template) != capability_id
            or capability_id in capabilities
        ):
            raise RuntimeError(f"invalid dashboard query capability: {capability_id or '-'}")
        normalized_object_names = frozenset(str(name).strip() for name in object_names if str(name).strip())
        if not normalized_object_names:
            raise RuntimeError(f"invalid dashboard query capability: {capability_id}")
        capabilities[capability_id] = DashboardQueryCapability(
            id=capability_id,
            object_names=normalized_object_names,
            template=template,
        )
    return capabilities


def _normalize_kafka_dimensions(value) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value or len(value) > MAX_KAFKA_DIMENSIONS:
        raise AuthorizedMetricQueryError(
            "Kafka 查询维度数量无效",
            code="capability_params_invalid",
        )
    normalized = []
    for item in value:
        if not isinstance(item, dict):
            raise AuthorizedMetricQueryError("Kafka 查询维度无效", code="capability_params_invalid")
        dimension = {
            "consumer_group": str(item.get("consumer_group") or "").strip(),
            "topic": str(item.get("topic") or "").strip(),
            "partition": str(item.get("partition") or "").strip(),
        }
        if not dimension["topic"] or not dimension["partition"]:
            raise AuthorizedMetricQueryError("Kafka 查询维度无效", code="capability_params_invalid")
        if any(len(value) > MAX_KAFKA_DIMENSION_VALUE_LENGTH for value in dimension.values()):
            raise AuthorizedMetricQueryError("Kafka 查询维度过长", code="capability_params_invalid")
        normalized.append(dimension)
    return normalized


def _build_kafka_dimension_query(capability_id: str, params, instance_matchers: list[str]) -> str:
    definitions = {
        "dashboard:dynamic:kafka:current-offset": ("kafka_consumergroup_current_offset_gauge", True),
        "dashboard:dynamic:kafka:oldest-offset": ("kafka_topic_partition_oldest_offset_gauge", False),
        "dashboard:dynamic:kafka:lag-history": ("kafka_consumergroup_lag_gauge", True),
    }
    definition = definitions.get(capability_id)
    if not definition:
        raise AuthorizedMetricQueryError("查询能力不存在", code="capability_not_found")
    if not isinstance(params, dict):
        raise AuthorizedMetricQueryError("Kafka 查询参数无效", code="capability_params_invalid")
    metric_name, with_consumer_group = definition
    dimensions = _normalize_kafka_dimensions(params.get("dimensions"))
    selectors = []
    for item in dimensions:
        labels = [
            *instance_matchers,
            f'topic="{escape_metric_label_value(item["topic"])}"',
            f'partition="{escape_metric_label_value(item["partition"])}"',
        ]
        if with_consumer_group:
            if not item["consumer_group"]:
                raise AuthorizedMetricQueryError("Kafka 查询维度无效", code="capability_params_invalid")
            labels.append(f'consumergroup="{escape_metric_label_value(item["consumer_group"])}"')
        selectors.append(f'{metric_name}{{{",".join(labels)}}}')
    return f'max by (consumergroup, topic, partition) ({" or ".join(selectors)})'


def build_dashboard_query(
    *,
    capability_id: str,
    monitor_object: MonitorObject,
    instance_ids: tuple[str, ...],
    start: int,
    end: int,
    params=None,
) -> str:
    instance_keys = [str(key).strip() for key in monitor_object.instance_id_keys or [] if str(key).strip()]
    if not instance_keys:
        raise AuthorizedMetricQueryError(
            "监控对象缺少实例标识契约",
            code="metric_instance_keys_missing",
        )
    matchers = build_instance_matchers(instance_ids, instance_keys)

    if capability_id.startswith("dashboard:dynamic:kafka:"):
        if monitor_object.name != "Kafka":
            raise AuthorizedMetricQueryError("查询能力与监控对象不匹配", code="capability_object_mismatch")
        return _build_kafka_dimension_query(capability_id, params, matchers)

    capability = load_dashboard_query_capabilities().get(capability_id)
    if not capability:
        raise AuthorizedMetricQueryError("查询能力不存在", code="capability_not_found")
    if monitor_object.name not in capability.object_names:
        raise AuthorizedMetricQueryError("查询能力与监控对象不匹配", code="capability_object_mismatch")

    query = capability.template.replace("__$labels__", ", ".join(matchers))
    query = query.replace("__$window__", _query_window(start, end))
    if "__$" in query:
        raise AuthorizedMetricQueryError("查询能力参数不完整", code="capability_template_invalid")
    return query
