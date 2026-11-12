"""启动后的一次性实例形态修复。

组织字段、列表标量和有变化的唯一规则按这个顺序做完。完成后不再扫描。
不注册周期任务；未完成时由任务自己预约下一页，下次启动再投递一次。
"""

from __future__ import annotations

import json
from collections import defaultdict

from apps.cmdb.constants.constants import INSTANCE, MODEL, ORGANIZATION
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.models.repair_state import DISPLAY_BACKFILL_STAGE, CmdbRepairState
from apps.cmdb.services.instance_shape_queries import organization_repair_statement, scalar_repair_statement
from apps.cmdb.services.unique_rule import (
    _collect_existing_instance_conflicts,
    _context_from_model_info,
    build_unique_rules_from_attr_rows,
    dump_unique_rules,
    parse_unique_rules,
)
from apps.core.logger import cmdb_logger as logger
from apps.core.logger import safe_log_value

STAGE_ORGANIZATION = "organization"
STAGE_SCALAR = "scalar_to_list"
STAGE_DISPLAY_BACKFILL = DISPLAY_BACKFILL_STAGE
UNIQUE_RULE_PREFIX = "unique_rule:"
OUTCOME_CONFLICT = "conflict_held"

PAGE_SIZE = 500
RUN_BUDGET = 2000
_LIST_ATTR_TYPES = {"organization", "user", "enum"}


def instance_shape_repair_pending() -> bool:
    for stage in (STAGE_ORGANIZATION, STAGE_SCALAR):
        row = CmdbRepairState.objects.filter(stage=stage).only("completed").first()
        if row is None or not row.completed:
            return True
    return CmdbRepairState.objects.filter(stage__startswith=UNIQUE_RULE_PREFIX, completed=False).exists()


def defer_unique_rule(model_id: str, field_groups: tuple[tuple[str, ...], ...]) -> None:
    fingerprint = json.dumps([list(group) for group in field_groups], ensure_ascii=False)
    stage = f"{UNIQUE_RULE_PREFIX}{model_id}"
    current = CmdbRepairState.objects.filter(stage=stage).first()
    if current and current.completed and current.outcome == OUTCOME_CONFLICT and current.fingerprint == fingerprint:
        return
    CmdbRepairState.objects.update_or_create(
        stage=stage,
        defaults={"completed": False, "outcome": "", "fingerprint": fingerprint, "cursor": "0"},
    )
    logger.debug("event=unique_rule_startup_deferred model_id=%s", safe_log_value(model_id))


def reset_scalar_repair() -> None:
    CmdbRepairState.objects.update_or_create(
        stage=STAGE_SCALAR,
        defaults={"completed": False, "cursor": "", "outcome": ""},
    )


class InstanceShapeRepair:
    def __init__(self, graph_client=None, driver_name: str | None = None):
        self._graph_client = graph_client or GraphClient
        if driver_name is None:
            from apps.cmdb.services.instance_shape_queries import graph_driver_name

            driver_name = graph_driver_name()
        self._driver_name = driver_name

    def run(self, budget: int = RUN_BUDGET) -> str:
        remaining = budget
        if not _stage_completed(STAGE_ORGANIZATION):
            if remaining <= 0:
                return "continue"
            remaining -= self._repair_organization(remaining)
            if not _stage_completed(STAGE_ORGANIZATION) or remaining <= 0:
                return "continue"
        if not _stage_completed(STAGE_SCALAR):
            if remaining <= 0:
                return "continue"
            remaining -= self._repair_scalar(remaining)
            if not _stage_completed(STAGE_SCALAR) or remaining <= 0:
                return "continue"
        if self._apply_one_unique_rule():
            if CmdbRepairState.objects.filter(stage__startswith=UNIQUE_RULE_PREFIX, completed=False).exists():
                return "continue"
        return "done"

    def _repair_organization(self, budget: int) -> int:
        state = _stage_row(STAGE_ORGANIZATION)
        after_id = _cursor_id(state.cursor)
        processed = 0
        default_group = None
        with self._graph_client() as graph:
            while processed < budget:
                page_limit = min(PAGE_SIZE, budget - processed)
                statement, params = organization_repair_statement(
                    driver=self._driver_name,
                    after_id=after_id,
                    limit=page_limit,
                )
                rows = graph.query_scalar_rows(statement, params)
                if not rows:
                    _complete(state)
                    logger.info("event=organization_repair_completed")
                    return processed
                dirty_ids = [int(row["id"]) for row in rows if _needs_default_organization(row.get(ORGANIZATION))]
                if dirty_ids:
                    if default_group is None:
                        from apps.cmdb.utils.base import get_default_group_id

                        default_group = get_default_group_id()
                    graph.batch_update_node_properties(INSTANCE, dirty_ids, {ORGANIZATION: default_group})
                after_id = int(rows[-1]["id"])
                processed += len(rows)
                state.cursor = str(after_id)
                state.save(update_fields=["cursor", "updated_at"])
                if len(rows) < page_limit:
                    _complete(state)
                    logger.info("event=organization_repair_completed")
                    return processed
        return processed

    def _repair_scalar(self, budget: int) -> int:
        state = _stage_row(STAGE_SCALAR)
        model_id, after_id = _split_model_cursor(state.cursor)
        processed = 0
        with self._graph_client() as graph:
            models, _ = graph.query_entity(MODEL, [], fields=["model_id", "attrs"], include_count=False)
            ordered = sorted((item for item in models if item.get("model_id")), key=lambda item: item["model_id"])
            if model_id and all(item["model_id"] != model_id for item in ordered):
                after_id = None
                ordered = [item for item in ordered if item["model_id"] > model_id]
                model_id = ""
            started = model_id == ""
            for model in ordered:
                current_model_id = model["model_id"]
                if not started:
                    if current_model_id != model_id:
                        continue
                    started = True
                else:
                    after_id = None
                fields = _list_fields(model.get("attrs"))
                if not fields:
                    continue
                while processed < budget:
                    page_limit = min(PAGE_SIZE, budget - processed)
                    statement, params = scalar_repair_statement(
                        driver=self._driver_name,
                        model_id=current_model_id,
                        fields=fields,
                        after_id=after_id,
                        limit=page_limit,
                    )
                    rows = graph.query_scalar_rows(statement, params)
                    if not rows:
                        after_id = None
                        break
                    updates_by_field = defaultdict(list)
                    for row in rows:
                        node_id = int(row["id"])
                        for field in fields:
                            value = row.get(field)
                            if value is None or value == "" or isinstance(value, list):
                                continue
                            updates_by_field[field].append({"id": node_id, "value": [value]})
                    for field, updates in updates_by_field.items():
                        graph.batch_update_node_property_values(INSTANCE, field, updates)
                    after_id = int(rows[-1]["id"])
                    processed += len(rows)
                    state.cursor = f"{current_model_id}|{after_id}"
                    state.save(update_fields=["cursor", "updated_at"])
                    if len(rows) < page_limit:
                        after_id = None
                        break
                    if processed >= budget:
                        return processed
            if started or not ordered:
                _complete(state)
                logger.info("event=scalar_repair_completed")
        return processed

    def _apply_one_unique_rule(self) -> bool:
        state = CmdbRepairState.objects.filter(stage__startswith=UNIQUE_RULE_PREFIX, completed=False).order_by("stage").first()
        if state is None:
            return False
        model_id = state.stage[len(UNIQUE_RULE_PREFIX) :]
        try:
            groups = json.loads(state.fingerprint or "[]")
        except json.JSONDecodeError:
            logger.warning("event=unique_rule_fingerprint_invalid model_id=%s", safe_log_value(model_id))
            _finish(state, outcome="invalid")
            return True
        if not isinstance(groups, list):
            logger.warning("event=unique_rule_fingerprint_invalid model_id=%s", safe_log_value(model_id))
            _finish(state, outcome="invalid")
            return True
        model_info = self._load_model(model_id)
        if not model_info:
            logger.warning("event=unique_rule_model_missing model_id=%s", safe_log_value(model_id))
            _finish(state, outcome="missing")
            return True
        rows = [{"attr_id": field_id, "unique_rule_order": order} for order, group in enumerate(groups, start=1) for field_id in group]
        rules = build_unique_rules_from_attr_rows(
            model_id,
            rows,
            model_info=model_info,
            preserve_existing_ids=True,
        )
        stored = tuple(tuple(rule.field_ids) for rule in parse_unique_rules(model_info.get("unique_rules")))
        desired = tuple(tuple(rule.field_ids) for rule in rules)
        if stored == desired:
            _finish(state, outcome="")
            return True
        fields = sorted({field_id for group in desired for field_id in group}) or ["inst_name"]
        instances = list(self._iter_instances(model_id, fields))
        attrs_by_id = _context_from_model_info(model_info).attrs_by_id
        conflicts = _collect_existing_instance_conflicts(rules, instances, attrs_by_id)
        if conflicts:
            logger.warning(
                "event=unique_rule_conflict_held model_id=%s conflict_count=%s",
                safe_log_value(model_id),
                len(conflicts),
            )
            state.completed = True
            state.outcome = OUTCOME_CONFLICT
            state.save(update_fields=["completed", "outcome", "updated_at"])
            return True
        with self._graph_client() as graph:
            graph.set_entity_properties(
                MODEL,
                [model_info["_id"]],
                {"unique_rules": dump_unique_rules(rules)},
                {},
                [],
                False,
            )
        from apps.cmdb.display_field import ExcludeFieldsCache

        ExcludeFieldsCache.invalidate_model_attrs(model_id)
        logger.info("event=unique_rule_applied model_id=%s rule_count=%s", safe_log_value(model_id), len(rules))
        _finish(state, outcome="")
        return True

    def _load_model(self, model_id: str):
        with self._graph_client() as graph:
            rows, _ = graph.query_entity(
                MODEL,
                [{"field": "model_id", "type": "str=", "value": model_id}],
                include_count=False,
            )
        return rows[0] if rows else None

    def _iter_instances(self, model_id: str, fields: list[str]):
        cursor = None
        while True:
            params = [{"field": "model_id", "type": "str=", "value": model_id}]
            if cursor is not None:
                params.append({"field": "id", "type": "id>", "value": cursor})
            with self._graph_client() as graph:
                page, _ = graph.query_entity(
                    INSTANCE,
                    params,
                    page={"skip": 0, "limit": PAGE_SIZE},
                    fields=fields,
                    include_count=False,
                )
            if not page:
                break
            yield from page
            if len(page) < PAGE_SIZE:
                break
            next_cursor = page[-1]["_id"]
            if cursor is not None and next_cursor <= cursor:
                break
            cursor = next_cursor


def _stage_completed(stage: str) -> bool:
    row = CmdbRepairState.objects.filter(stage=stage).only("completed").first()
    return bool(row and row.completed)


def _stage_row(stage: str) -> CmdbRepairState:
    row, _ = CmdbRepairState.objects.get_or_create(stage=stage, defaults={"completed": False, "cursor": ""})
    return row


def _complete(state: CmdbRepairState) -> None:
    state.completed = True
    state.cursor = ""
    state.save(update_fields=["completed", "cursor", "updated_at"])


def _finish(state: CmdbRepairState, *, outcome: str) -> None:
    state.completed = True
    state.outcome = outcome
    state.save(update_fields=["completed", "outcome", "updated_at"])


def _cursor_id(cursor: str) -> int | None:
    text = str(cursor or "").strip()
    if not text:
        return None
    return int(text)


def _split_model_cursor(cursor: str) -> tuple[str, int | None]:
    text = str(cursor or "").strip()
    if not text or "|" not in text:
        return "", None
    model_id, raw_id = text.split("|", 1)
    if not raw_id:
        return model_id, None
    return model_id, int(raw_id)


def _needs_default_organization(value) -> bool:
    if isinstance(value, bool):
        return False
    if value is None or value == "" or value == []:
        return True
    return isinstance(value, int)


def _list_fields(attrs_value) -> list[str]:
    if isinstance(attrs_value, list):
        attrs = attrs_value
    else:
        try:
            attrs = json.loads(attrs_value or "[]")
        except (TypeError, json.JSONDecodeError):
            return []
    fields = []
    for attr in attrs:
        if not isinstance(attr, dict):
            continue
        attr_id = str(attr.get("attr_id") or "").strip()
        attr_type = str(attr.get("attr_type") or "")
        if not attr_id:
            continue
        if attr_type in _LIST_ATTR_TYPES or "list" in attr_type or "array" in attr_type:
            fields.append(attr_id)
    return fields
