"""按主键顺序分批归约告警字段，避免把整组成员一次装进多个列表。"""

import json
from typing import Any, Dict, Iterable, List, Optional

from apps.alerts.constants.constants import EventAction
from apps.alerts.enrichment.merge import merge_namespace_payload
from apps.alerts.service.monitor_object_snapshot import resolve_monitor_objects
from apps.alerts.service.monitor_sources import normalize_push_source_ids
from apps.alerts.utils.enrichment import resolve_data_path

MAX_ALERT_OWNERS = 50

EMPTY_ENRICHMENT_META = {"schema_version": 1, "event_count": 0, "status_counts": {}}


class _UniqueValue:
    def __init__(self):
        self._value = None
        self._seen = False
        self._conflict = False

    def add(self, value: Any) -> None:
        if self._conflict:
            return
        if not self._seen:
            self._value = value
            self._seen = True
            return
        if self._value != value:
            self._conflict = True
            self._value = None

    @property
    def value(self) -> Any:
        return None if self._conflict or not self._seen else self._value


class EventFieldReducer:
    def __init__(self, group_by_field: str = ""):
        self.group_by_field = group_by_field or ""
        self.event_count = 0
        self._source_name = _UniqueValue()
        self._resource_id = _UniqueValue()
        self._resource_name = _UniqueValue()
        self._resource_type = _UniqueValue()
        self._item = _UniqueValue()
        self._push_source_ids = set()
        self._labels_json: Optional[str] = None
        self._labels: Dict[str, Any] = {}
        self._labels_conflict = False
        self._enrichment: Dict[str, Any] = {}
        self._status_counts: Dict[str, int] = {}
        self._dimension_names = [item.strip() for item in self.group_by_field.split(",") if item.strip()]
        self._dimensions = {name: _UniqueValue() for name in self._dimension_names}
        self._monitor_objects: List[dict] = []
        self._monitors_by_id: Dict[str, dict] = {}
        self._owners: List[str] = []
        self._owner_seen = set()

    def consume(self, events: Iterable) -> None:
        event_list = list(events)
        if not event_list:
            return
        created = []
        for event in event_list:
            self.event_count += 1
            source = getattr(event, "source", None)
            self._source_name.add(getattr(source, "name", None) if source is not None else None)
            push_source_id = getattr(event, "push_source_id", None)
            if isinstance(push_source_id, str) and push_source_id.strip():
                self._push_source_ids.add(push_source_id)
            self._resource_id.add(getattr(event, "resource_id", None))
            self._resource_name.add(getattr(event, "resource_name", None))
            self._resource_type.add(getattr(event, "resource_type", None))
            self._item.add(getattr(event, "item", None))
            self._absorb_labels(event)
            self._absorb_enrichment(event)
            status = (getattr(event, "enrichment_meta", None) or {}).get("status", "skipped")
            self._status_counts[status] = self._status_counts.get(status, 0) + 1
            self._absorb_dimensions(event)
            if getattr(event, "action", None) == EventAction.CREATED:
                created.append(event)
                self._absorb_owner(event)
        self._absorb_monitors(created)

    def standard_fields(self) -> Dict[str, Any]:
        if self.event_count == 0:
            return {
                "source_name": None,
                "push_source_ids": [],
                "resource_id": None,
                "resource_name": None,
                "resource_type": None,
                "item": None,
                "labels": {},
                "enrichment": {},
                "enrichment_meta": dict(EMPTY_ENRICHMENT_META),
            }
        return {
            "source_name": self._source_name.value,
            "push_source_ids": normalize_push_source_ids(self._push_source_ids),
            "resource_id": self._resource_id.value,
            "resource_name": self._resource_name.value,
            "resource_type": self._resource_type.value,
            "item": self._item.value,
            "labels": {} if self._labels_conflict else (self._labels or {}),
            "enrichment": self._enrichment,
            "enrichment_meta": {
                "schema_version": 1,
                "event_count": self.event_count,
                "status_counts": dict(self._status_counts),
            },
        }

    def dimensions(self) -> Dict[str, str]:
        result = {}
        for name, tracker in self._dimensions.items():
            value = tracker.value
            if value:
                result[name] = value
        return result

    @property
    def monitor_objects(self) -> List[dict]:
        return self._monitor_objects

    @property
    def owners(self) -> List[str]:
        return self._owners

    def _absorb_labels(self, event) -> None:
        if self._labels_conflict:
            return
        serialized = json.dumps(getattr(event, "labels", None) or {}, sort_keys=True, ensure_ascii=False)
        if self._labels_json is None:
            self._labels_json = serialized
            self._labels = getattr(event, "labels", None) or {}
            return
        if serialized != self._labels_json:
            self._labels_conflict = True
            self._labels = {}

    def _absorb_enrichment(self, event) -> None:
        data = getattr(event, "enrichment", None) or {}
        for namespace, payload in data.items():
            if not payload:
                continue
            existing = self._enrichment.get(namespace)
            if existing is None:
                self._enrichment[namespace], _ = merge_namespace_payload({}, payload)
            elif existing != payload:
                self._enrichment[namespace], _ = merge_namespace_payload(existing, payload)

    def _absorb_dimensions(self, event) -> None:
        for name in self._dimension_names:
            if name.startswith("enrichment."):
                raw_value = resolve_data_path(
                    {"enrichment": getattr(event, "enrichment", None) or {}},
                    name,
                )
            else:
                raw_value = getattr(event, name, None)
            if raw_value is None:
                continue
            normalized = str(raw_value).strip()
            if normalized:
                self._dimensions[name].add(normalized)

    def _absorb_owner(self, event) -> None:
        if len(self._owners) >= MAX_ALERT_OWNERS:
            return
        for name in getattr(event, "assignee", None) or []:
            if not isinstance(name, str):
                continue
            username = name.strip()
            if not username or username in self._owner_seen:
                continue
            self._owner_seen.add(username)
            self._owners.append(username)
            if len(self._owners) >= MAX_ALERT_OWNERS:
                return

    def _absorb_monitors(self, created_events: List) -> None:
        for snapshot in resolve_monitor_objects(created_events):
            existing = self._monitors_by_id.get(snapshot["monitor_id"])
            if existing is None:
                self._monitors_by_id[snapshot["monitor_id"]] = snapshot
                self._monitor_objects.append(snapshot)
                continue
            for field in ("cmdb_id", "node_id", "resource_type", "resource_name"):
                if existing[field] is None and snapshot[field] is not None:
                    existing[field] = snapshot[field]
