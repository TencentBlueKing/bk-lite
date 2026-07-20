from celery import current_app
from django.conf import settings
from django.db import transaction

from apps.cmdb.constants.constants import INSTANCE, INSTANCE_ASSOCIATION
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.services.auto_relation_rule import (
    AUTO_RELATION_MATCHING_RULE_CONTAINS,
    AUTO_RELATION_MATCHING_RULE_EXACT,
    AUTO_RELATION_MATCHING_RULE_IEXACT,
    AUTO_RELATION_RULE_FIELD,
    AutoRelationMatchPair,
    AutoRelationRule,
    parse_auto_relation_rule_set,
)
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import cmdb_logger as logger

AUTO_RELATION_EDGE_SOURCE = "auto_rule"
AUTO_RELATION_EDGE_SOURCE_FIELD = "association_source"
AUTO_RELATION_EDGE_RULE_ID_FIELD = "auto_rule_model_asst_id"
INSTANCE_RECONCILE_TASK = "apps.cmdb.tasks.celery_tasks.reconcile_instance_auto_association_task"
INSTANCE_BATCH_RECONCILE_TASK = "apps.cmdb.tasks.celery_tasks.reconcile_instances_auto_association_task"
RULE_FULL_SYNC_TASK = "apps.cmdb.tasks.celery_tasks.full_sync_auto_association_rule_task"
_PENDING_RULE_FULL_SYNC_IDS: set[str] = set()


def schedule_instance_auto_relation_reconcile(instance_ids: list[int] | tuple[int, ...] | set[int] | None) -> None:
    normalized_ids = []
    for instance_id in list(instance_ids or []):
        try:
            normalized_id = int(instance_id)
        except (TypeError, ValueError):
            continue
        if normalized_id <= 0 or normalized_id in normalized_ids:
            continue
        normalized_ids.append(normalized_id)

    if not normalized_ids:
        return

    def _dispatch() -> None:
        from apps.cmdb.tasks.celery_tasks import reconcile_instances_auto_association_task

        # 同批实例合并为一个任务，避免逐实例重复触发相同规则全量同步。
        if settings.DEBUG:
            reconcile_instances_auto_association_task(normalized_ids)
        else:
            current_app.send_task(INSTANCE_BATCH_RECONCILE_TASK, args=[normalized_ids])

    transaction.on_commit(_dispatch)


def schedule_rule_auto_relation_full_sync(model_asst_ids: list[str] | tuple[str, ...] | set[str] | None) -> None:
    normalized_ids = []
    for model_asst_id in list(model_asst_ids or []):
        normalized_id = str(model_asst_id or "").strip()
        if not normalized_id or normalized_id in normalized_ids or normalized_id in _PENDING_RULE_FULL_SYNC_IDS:
            continue
        normalized_ids.append(normalized_id)
        _PENDING_RULE_FULL_SYNC_IDS.add(normalized_id)

    if not normalized_ids:
        return

    def _dispatch() -> None:
        from apps.cmdb.tasks.celery_tasks import full_sync_auto_association_rule_task

        try:
            for model_asst_id in normalized_ids:
                if settings.DEBUG:
                    full_sync_auto_association_rule_task(model_asst_id)
                else:
                    current_app.send_task(RULE_FULL_SYNC_TASK, args=[model_asst_id])
        finally:
            for model_asst_id in normalized_ids:
                _PENDING_RULE_FULL_SYNC_IDS.discard(model_asst_id)

    transaction.on_commit(_dispatch)


def schedule_incoming_rule_full_sync_by_model_ids(model_ids: list[str] | tuple[str, ...] | set[str] | None) -> None:
    normalized_model_ids = []
    for model_id in list(model_ids or []):
        normalized_id = str(model_id or "").strip()
        if not normalized_id or normalized_id in normalized_model_ids:
            continue
        normalized_model_ids.append(normalized_id)

    if not normalized_model_ids:
        return

    rule_ids: list[str] = []
    for model_id in normalized_model_ids:
        for model_asst_id in AutoRelationRuleReconcileService._list_enabled_rule_ids_by_dst_model(model_id):
            if model_asst_id not in rule_ids:
                rule_ids.append(model_asst_id)

    schedule_rule_auto_relation_full_sync(rule_ids)


class AutoRelationRuleReconcileService:
    @staticmethod
    def _normalize_instance_ids(instance_ids) -> list[int]:
        normalized_ids = []
        for instance_id in list(instance_ids or []):
            try:
                normalized_id = int(instance_id)
            except (TypeError, ValueError):
                continue
            if normalized_id <= 0 or normalized_id in normalized_ids:
                continue
            normalized_ids.append(normalized_id)
        return normalized_ids

    @staticmethod
    def _matches_pair(source_value, target_value, pair: AutoRelationMatchPair) -> bool:
        if pair.matching_rule == AUTO_RELATION_MATCHING_RULE_EXACT:
            return source_value == target_value
        if source_value is None or target_value is None:
            return False
        if pair.matching_rule == AUTO_RELATION_MATCHING_RULE_IEXACT:
            return str(source_value).strip().lower() == str(target_value).strip().lower()
        if pair.matching_rule == AUTO_RELATION_MATCHING_RULE_CONTAINS:
            return str(source_value).strip() in str(target_value).strip()
        logger.warning(
            "[AutoRelationRule] unsupported matching_rule skipped, matching_rule=%s, src_field_id=%s, dst_field_id=%s",
            pair.matching_rule,
            pair.src_field_id,
            pair.dst_field_id,
        )
        return False

    @staticmethod
    def _get_mapping(association: dict) -> str:
        return str(association.get("mapping") or "n:n")

    @staticmethod
    def _is_empty_value(value) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return value.strip() == ""
        if isinstance(value, (list, dict, tuple, set)):
            return len(value) == 0
        return False

    @staticmethod
    def _query_instances_by_model(model_id: str) -> list[dict]:
        with GraphClient() as ag:
            instances, _ = ag.query_entity(
                INSTANCE,
                [{"field": "model_id", "type": "str=", "value": model_id}],
            )
        return instances

    @staticmethod
    def _query_existing_edges_for_source(model_asst_id: str, src_inst_id: int) -> list[dict]:
        with GraphClient() as ag:
            return ag.query_edge(
                INSTANCE_ASSOCIATION,
                [
                    {"field": "model_asst_id", "type": "str=", "value": model_asst_id},
                    {"field": "src_inst_id", "type": "int=", "value": src_inst_id},
                ],
            )

    @classmethod
    def _list_enabled_rules_by_src_model(cls, model_id: str) -> list[tuple[dict, list[AutoRelationRule]]]:
        from apps.cmdb.services.model import ModelManage

        associations = ModelManage.model_association_search(model_id)
        result = []
        for association in associations:
            if association.get("src_model_id") != model_id:
                continue
            rule_set = parse_auto_relation_rule_set(association.get(AUTO_RELATION_RULE_FIELD))
            if not rule_set:
                continue
            enabled_rules = [rule for rule in rule_set.rules if rule.enabled]
            if not enabled_rules:
                continue
            result.append((association, enabled_rules))
        return result

    @classmethod
    def _list_enabled_rule_ids_by_dst_model(cls, model_id: str) -> list[str]:
        from apps.cmdb.services.model import ModelManage

        associations = ModelManage.model_association_search(model_id)
        result = []
        for association in associations:
            if association.get("dst_model_id") != model_id:
                continue
            rule_set = parse_auto_relation_rule_set(association.get(AUTO_RELATION_RULE_FIELD))
            if not rule_set or not any(rule.enabled for rule in rule_set.rules):
                continue
            model_asst_id = str(association.get("model_asst_id") or "").strip()
            if model_asst_id and model_asst_id not in result:
                result.append(model_asst_id)
        return result

    @classmethod
    def _calculate_desired_target_ids(
        cls,
        source_instance: dict,
        association: dict,
        rules: list[AutoRelationRule],
        target_instances: list[dict] | None = None,
    ) -> set[int]:
        candidate_targets = target_instances if target_instances is not None else cls._query_instances_by_model(association["dst_model_id"])
        desired_ids: set[int] = set()
        for rule in rules:
            source_fields_ready = True
            for pair in rule.match_pairs:
                if cls._is_empty_value(source_instance.get(pair.src_field_id)):
                    source_fields_ready = False
                    break
            if not source_fields_ready:
                continue

            for target_instance in candidate_targets:
                matched = True
                for pair in rule.match_pairs:
                    if not cls._matches_pair(
                        source_instance.get(pair.src_field_id),
                        target_instance.get(pair.dst_field_id),
                        pair,
                    ):
                        matched = False
                        break
                if matched:
                    desired_ids.add(target_instance["_id"])
        return desired_ids

    @classmethod
    def cleanup_auto_edges_by_rule(cls, model_asst_id: str) -> int:
        with GraphClient() as ag:
            edges = ag.query_edge(
                INSTANCE_ASSOCIATION,
                [
                    {
                        "field": AUTO_RELATION_EDGE_SOURCE_FIELD,
                        "type": "str=",
                        "value": AUTO_RELATION_EDGE_SOURCE,
                    },
                    {
                        "field": AUTO_RELATION_EDGE_RULE_ID_FIELD,
                        "type": "str=",
                        "value": model_asst_id,
                    },
                ],
            )
            for edge in edges:
                ag.delete_edge(edge["_id"])
        return len(edges)

    @classmethod
    def _log_ambiguity(cls, association: dict, source_instance: dict, desired_target_ids: set[int], reason: str) -> None:
        logger.warning(
            "[AutoRelationRule] ambiguous match skipped, model_asst_id=%s, src_inst_id=%s, mapping=%s, desired_target_ids=%s, reason=%s",
            association.get("model_asst_id"),
            source_instance.get("_id"),
            cls._get_mapping(association),
            sorted(desired_target_ids),
            reason,
        )

    @classmethod
    def _filter_desired_targets_for_mapping(
        cls,
        association: dict,
        source_instance: dict,
        desired_target_ids: set[int],
        target_claims: dict[int, int] | None = None,
    ) -> tuple[set[int], int]:
        mapping = cls._get_mapping(association)
        if not desired_target_ids:
            return desired_target_ids, 0

        conflict_count = 0
        if mapping in {"n:1", "1:1"} and len(desired_target_ids) > 1:
            cls._log_ambiguity(association, source_instance, desired_target_ids, "multiple targets matched under constrained mapping")
            return set(), 1

        if mapping in {"1:n", "1:1"} and target_claims is not None:
            filtered_target_ids: set[int] = set()
            for dst_inst_id in desired_target_ids:
                claimed_by = target_claims.get(dst_inst_id)
                if claimed_by is not None and claimed_by != source_instance["_id"]:
                    conflict_count += 1
                    logger.warning(
                        "[AutoRelationRule] destination collision skipped, model_asst_id=%s, dst_inst_id=%s, src_inst_id=%s, claimed_by=%s",
                        association.get("model_asst_id"),
                        dst_inst_id,
                        source_instance.get("_id"),
                        claimed_by,
                    )
                    continue
                filtered_target_ids.add(dst_inst_id)
                target_claims[dst_inst_id] = source_instance["_id"]
            return filtered_target_ids, conflict_count

        return desired_target_ids, conflict_count

    @classmethod
    def reconcile_source_instance(
        cls,
        source_instance: dict,
        association: dict,
        rules: list[AutoRelationRule],
        target_instances: list[dict] | None = None,
        target_claims: dict[int, int] | None = None,
    ) -> dict:
        model_asst_id = association["model_asst_id"]
        existing_edges = cls._query_existing_edges_for_source(model_asst_id, source_instance["_id"])
        auto_edges = [
            edge
            for edge in existing_edges
            if edge.get(AUTO_RELATION_EDGE_SOURCE_FIELD) == AUTO_RELATION_EDGE_SOURCE
            and edge.get(AUTO_RELATION_EDGE_RULE_ID_FIELD) == model_asst_id
        ]
        all_existing_target_ids = {int(edge["dst_inst_id"]) for edge in existing_edges if edge.get("dst_inst_id") is not None}
        desired_target_ids = cls._calculate_desired_target_ids(source_instance, association, rules, target_instances=target_instances)
        desired_target_ids, mapping_conflicts = cls._filter_desired_targets_for_mapping(
            association,
            source_instance,
            desired_target_ids,
            target_claims=target_claims,
        )

        summary = {
            "model_asst_id": model_asst_id,
            "src_inst_id": source_instance["_id"],
            "desired": len(desired_target_ids),
            "created": 0,
            "deleted": 0,
            "skipped": 0,
            "conflicts": mapping_conflicts,
        }

        for edge in auto_edges:
            dst_inst_id = int(edge["dst_inst_id"])
            if dst_inst_id in desired_target_ids:
                continue
            with GraphClient() as ag:
                ag.delete_edge(edge["_id"])
            summary["deleted"] += 1

        for dst_inst_id in desired_target_ids:
            if dst_inst_id in all_existing_target_ids:
                summary["skipped"] += 1
                continue

            edge_data = {
                "model_asst_id": model_asst_id,
                "src_model_id": association["src_model_id"],
                "src_inst_id": source_instance["_id"],
                "dst_model_id": association["dst_model_id"],
                "dst_inst_id": dst_inst_id,
                "asst_id": association.get("asst_id"),
                AUTO_RELATION_EDGE_SOURCE_FIELD: AUTO_RELATION_EDGE_SOURCE,
                AUTO_RELATION_EDGE_RULE_ID_FIELD: model_asst_id,
            }

            try:
                from apps.cmdb.services.instance import InstanceManage

                InstanceManage.check_asso_mapping(edge_data)
                with GraphClient() as ag:
                    ag.create_edge(
                        INSTANCE_ASSOCIATION,
                        edge_data["src_inst_id"],
                        INSTANCE,
                        edge_data["dst_inst_id"],
                        INSTANCE,
                        edge_data,
                        "model_asst_id",
                    )
                summary["created"] += 1
                all_existing_target_ids.add(dst_inst_id)
            except BaseAppException as exc:
                summary["conflicts"] += 1
                logger.warning(
                    "[AutoRelationRule] skip creating auto association, model_asst_id=%s, src_inst_id=%s, dst_inst_id=%s, reason=%s",
                    model_asst_id,
                    source_instance["_id"],
                    dst_inst_id,
                    getattr(exc, "message", str(exc)),
                )

        return summary

    @classmethod
    def reconcile_for_instances(cls, instance_ids: list[int]) -> dict:
        normalized_ids = cls._normalize_instance_ids(instance_ids)
        summary = {
            "requested": len(normalized_ids),
            "instances": 0,
            "missing": [],
            "source_rules": 0,
            "full_sync_rules": 0,
            "created": 0,
            "deleted": 0,
            "skipped": 0,
            "conflicts": 0,
            "failed": [],
            "success": True,
        }
        if not normalized_ids:
            return summary

        with GraphClient() as ag:
            instances, _ = ag.query_entity(
                INSTANCE,
                [{"field": "id", "type": "id[]", "value": normalized_ids}],
            )

        instances_by_id = {int(instance["_id"]): instance for instance in instances}
        summary["instances"] = len(instances_by_id)
        summary["missing"] = [
            instance_id for instance_id in normalized_ids if instance_id not in instances_by_id
        ]
        # 目标侧规则跨实例去重，每条规则本轮只全量同步一次。
        incoming_rule_ids = []

        for instance_id in normalized_ids:
            instance = instances_by_id.get(instance_id)
            if not instance:
                continue
            try:
                for association, rules in cls._list_enabled_rules_by_src_model(
                    instance["model_id"]
                ):
                    item_summary = cls.reconcile_source_instance(instance, association, rules)
                    summary["source_rules"] += 1
                    summary["created"] += item_summary["created"]
                    summary["deleted"] += item_summary["deleted"]
                    summary["skipped"] += item_summary["skipped"]
                    summary["conflicts"] += item_summary["conflicts"]

                for model_asst_id in cls._list_enabled_rule_ids_by_dst_model(
                    instance["model_id"]
                ):
                    if model_asst_id not in incoming_rule_ids:
                        incoming_rule_ids.append(model_asst_id)
            except Exception as exc:
                logger.exception(
                    "[AutoRelationRule] batch instance reconcile failed, instance_id=%s",
                    instance_id,
                )
                summary["failed"].append(
                    {"instance_id": instance_id, "error": str(getattr(exc, "message", exc))}
                )

        if incoming_rule_ids:
            schedule_rule_auto_relation_full_sync(incoming_rule_ids)
        summary["full_sync_rules"] = len(incoming_rule_ids)
        summary["success"] = not summary["failed"]
        return summary

    @classmethod
    def reconcile_for_instance(cls, instance_id: int) -> dict:
        with GraphClient() as ag:
            instance = ag.query_entity_by_id(instance_id)

        if not instance:
            logger.warning("[AutoRelationRule] instance not found, skip reconcile. instance_id=%s", instance_id)
            return {
                "instance_id": instance_id,
                "source_rules": 0,
                "full_sync_rules": 0,
                "created": 0,
                "deleted": 0,
                "skipped": 0,
                "conflicts": 0,
                "success": False,
            }

        summary = {
            "instance_id": instance_id,
            "source_rules": 0,
            "full_sync_rules": 0,
            "created": 0,
            "deleted": 0,
            "skipped": 0,
            "conflicts": 0,
            "success": True,
        }

        for association, rules in cls._list_enabled_rules_by_src_model(instance["model_id"]):
            item_summary = cls.reconcile_source_instance(instance, association, rules)
            summary["source_rules"] += 1
            summary["created"] += item_summary["created"]
            summary["deleted"] += item_summary["deleted"]
            summary["skipped"] += item_summary["skipped"]
            summary["conflicts"] += item_summary["conflicts"]

        incoming_rule_ids = cls._list_enabled_rule_ids_by_dst_model(instance["model_id"])
        if incoming_rule_ids:
            # 当前实例处于目标侧时，无法只靠单实例局部推导所有受影响源实例，因此退化为规则级全量收敛。
            schedule_rule_auto_relation_full_sync(incoming_rule_ids)
            summary["full_sync_rules"] = len(incoming_rule_ids)

        return summary

    @classmethod
    def full_sync_rule(cls, model_asst_id: str) -> dict:
        from apps.cmdb.services.model import ModelManage

        association = ModelManage.model_association_info_search(model_asst_id)
        rule_set = parse_auto_relation_rule_set(association.get(AUTO_RELATION_RULE_FIELD)) if association else None
        enabled_rules = [rule for rule in (rule_set.rules if rule_set else []) if rule.enabled]
        summary = {
            "model_asst_id": model_asst_id,
            "mode": "cleanup",
            "source_instances": 0,
            "created": 0,
            "deleted": 0,
            "skipped": 0,
            "conflicts": 0,
            "success": True,
        }

        if not association or not enabled_rules:
            summary["deleted"] = cls.cleanup_auto_edges_by_rule(model_asst_id)
            return summary

        target_instances = cls._query_instances_by_model(association["dst_model_id"])
        source_instances = cls._query_instances_by_model(association["src_model_id"])
        target_claims: dict[int, int] | None = {} if cls._get_mapping(association) in {"1:n", "1:1"} else None
        summary["mode"] = "full_sync"
        summary["source_instances"] = len(source_instances)

        for source_instance in source_instances:
            item_summary = cls.reconcile_source_instance(
                source_instance,
                association,
                enabled_rules,
                target_instances=target_instances,
                target_claims=target_claims,
            )
            summary["created"] += item_summary["created"]
            summary["deleted"] += item_summary["deleted"]
            summary["skipped"] += item_summary["skipped"]
            summary["conflicts"] += item_summary["conflicts"]

        return summary
