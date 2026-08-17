from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from django.db.models import Q
from django.utils import timezone

from apps.cmdb.constants.subscription import INSTANCE_QUERY_PAGE_SIZE, FilterType, TriggerType
from apps.cmdb.models.change_record import CREATE_INST, DELETE_INST, UPDATE_INST, ChangeRecord
from apps.cmdb.models.subscription_rule import SubscriptionRule
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.model import ModelManage
from apps.cmdb.utils.subscription_utils import truncate_value
from apps.core.logger import cmdb_logger as logger


def _optional_uuid(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        parsed = UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None
    if parsed.version != 4:
        return None
    return str(parsed)


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass
class TriggerEvent:
    """
    触发事件数据类。

    记录单个触发事件的完整信息，用于在检测和发送阶段之间传递数据。

    Attributes:
        rule_id: 触发的订阅规则 ID
        rule_name: 规则名称
        model_id: 目标模型 ID
        model_name: 模型显示名称
        trigger_type: 触发类型（见 TriggerType 枚举）
        inst_id: 实例 ID
        inst_name: 实例显示名称
        change_summary: 变更摘要描述
        triggered_at: 触发时间（ISO 格式字符串）
    """

    rule_id: int
    rule_name: str
    model_id: str
    model_name: str
    trigger_type: str
    inst_id: int
    inst_name: str
    change_summary: str
    triggered_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SubscriptionTriggerService:
    """
    订阅触发检测服务。

    职责：
    - 根据订阅规则检测数据变更并生成触发事件
    - 支持多种触发类型：属性变化、关联变化、临近到期
    - 维护规则的快照数据和检查时间

    检测机制：
    - 属性变化：基于 ChangeRecord 增量窗口检测，对比 last_check_time 到 checkpoint 的变更
    - 关联变化：对比快照中的关联实例列表，检测新增/删除/属性变化
    - 临近到期：基于配置的时间字段和提前天数，使用去重键避免重复通知

    合并策略：
    - ATTRIBUTE_MERGE_MODE = "single"：同一实例的多次属性变更合并为单个事件
    """

    # 属性变更合并模式："single" 表示同一实例的多次变更合并为一个事件
    ATTRIBUTE_MERGE_MODE = "single"

    def __init__(self, rule: SubscriptionRule):
        self.rule = rule
        self.events: list[TriggerEvent] = []
        self.model_info = ModelManage.search_model_info(rule.model_id) or {}
        self.model_name = self.model_info.get("model_name") or rule.model_id
        self.attribute_merge_mode = self.ATTRIBUTE_MERGE_MODE

    @staticmethod
    def _normalize_relation_change_models(
        relation_config: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        relation_config = relation_config or {}
        related_models = relation_config.get("related_models")
        normalized: list[dict[str, Any]] = []
        if isinstance(related_models, list):
            for item in related_models:
                if not isinstance(item, dict):
                    continue
                related_model = item.get("related_model")
                if not related_model:
                    continue
                fields = item.get("fields", [])
                normalized.append(
                    {
                        "related_model": related_model,
                        "fields": fields if isinstance(fields, list) else [],
                    }
                )
        if normalized:
            deduplicated: list[dict[str, Any]] = []
            seen: set[str] = set()
            for item in normalized:
                model_id = item["related_model"]
                if model_id in seen:
                    continue
                seen.add(model_id)
                deduplicated.append(item)
            return deduplicated

        related_model = relation_config.get("related_model")
        if related_model:
            fields = relation_config.get("fields", [])
            return [
                {
                    "related_model": related_model,
                    "fields": fields if isinstance(fields, list) else [],
                }
            ]
        return []

    def process(self) -> list[TriggerEvent]:
        # 固定检查上界，确保查询窗口稳定在 (last_check_time, checkpoint]。
        checkpoint = timezone.now()
        logger.info(
            "[Subscription] 触发检测开始 "
            f"rule_id={self.rule.id}, model_id={self.rule.model_id}, "
            f"trigger_types={self.rule.trigger_types}, checkpoint={checkpoint.isoformat()}"
        )
        instances = self._get_current_instances()
        logger.info(f"[Subscription] 当前实例集加载完成 rule_id={self.rule.id}, instances_count={len(instances)}")
        if not instances:
            self._update_snapshot(
                {
                    "instances": [],
                    "instance_uuids": [],
                    "relations": {},
                    "relations_by_uuid": {},
                    "expiration_notified": {},
                },
                checkpoint,
            )
            logger.info(f"[Subscription] 当前实例为空，已更新快照 rule_id={self.rule.id}")
            return []

        instance_ids = [int(i.get("_id")) for i in instances if i.get("_id") is not None]
        relation_maps_by_model: dict[str, dict[int, list[int]]] = {}
        relation_failed_instance_ids_by_model: dict[str, set[int]] = {}
        if TriggerType.RELATION_CHANGE.value in self.rule.trigger_types:
            relation_models = self._normalize_relation_change_models(self.rule.trigger_config.get("relation_change", {}))
            for relation_model in relation_models:
                related_model = relation_model.get("related_model")
                if not related_model:
                    continue
                (
                    relation_maps_by_model[related_model],
                    relation_failed_instance_ids_by_model[related_model],
                ) = self._get_relation_instances(instance_ids, related_model)

        current_snapshot = self._build_current_snapshot(
            instances,
            relation_maps_by_model,
            relation_failed_instance_ids_by_model,
        )

        if TriggerType.ATTRIBUTE_CHANGE.value in self.rule.trigger_types:
            self.events.extend(self._check_attribute_change(instances, checkpoint))
        if TriggerType.RELATION_CHANGE.value in self.rule.trigger_types:
            self.events.extend(
                self._check_relation_change(
                    current_snapshot,
                    instances,
                    checkpoint,
                    relation_failed_instance_ids_by_model,
                )
            )
        if TriggerType.EXPIRATION.value in self.rule.trigger_types:
            self.events.extend(self._check_expiration(instances, current_snapshot))
        if TriggerType.CONFIG_FILE.value in self.rule.trigger_types:
            self.events.extend(self._check_config_file(instances, current_snapshot, checkpoint))

        self._update_snapshot(current_snapshot, checkpoint)
        logger.info(f"[Subscription] 触发检测结束 rule_id={self.rule.id}, events_count={len(self.events)}")
        return self.events

    def _get_current_instances(self) -> list[dict[str, Any]]:
        """分页获取当前符合筛选条件的实例列表。"""
        page_size = INSTANCE_QUERY_PAGE_SIZE
        page = 1
        all_instances: list[dict[str, Any]] = []

        while True:
            if self.rule.filter_type == FilterType.CONDITION.value:
                query_list = self.rule.instance_filter.get("query_list", [])
            else:
                instance_uuids = self.rule.instance_filter.get("instance_uuids") or []
                instance_ids = self.rule.instance_filter.get("instance_ids") or []
                if instance_uuids:
                    normalized_uuids = []
                    for value in instance_uuids:
                        uid = _optional_uuid(value)
                        if uid:
                            normalized_uuids.append(uid)
                    if not normalized_uuids:
                        logger.info(f"[Subscription] 实例 UUID 筛选为空，跳过 rule_id={self.rule.id}")
                        return []
                    query_list = [{"field": "inst_uuid", "type": "str[]", "value": normalized_uuids}]
                elif instance_ids:
                    # 过渡期只读兼容：清洗前旧规则仍可能仅有 instance_ids
                    query_list = [{"field": "id", "type": "id[]", "value": instance_ids}]
                else:
                    logger.info(f"[Subscription] 实例筛选为空，跳过 rule_id={self.rule.id}")
                    return []

            data, count = InstanceManage.instance_list(
                model_id=self.rule.model_id,
                params=list(query_list),
                page=page,
                page_size=page_size,
                order="",
                permission_map={},
                creator="",
            )
            all_instances.extend(data)
            logger.info(f"[Subscription] 分页查询实例 rule_id={self.rule.id}, page={page}, page_size={page_size}, fetched={len(data)}, total={count}")
            if len(all_instances) >= count:
                break
            page += 1

        return all_instances

    def _get_relation_instances(self, instance_ids: list[int], related_model: str) -> tuple[dict[int, list[int]], set[int]]:
        logger.info(f"[Subscription] 开始查询关联实例 rule_id={self.rule.id}, related_model={related_model}, instance_count={len(instance_ids)}")
        try:
            relation_map = InstanceManage.instance_association_map(
                self.rule.model_id,
                instance_ids,
                related_model=related_model,
            )
            logger.info(f"[Subscription] 关联实例批量查询完成 rule_id={self.rule.id}, related_model={related_model}, relation_map_size={len(relation_map)}")
            return relation_map, set()
        except Exception as exc:
            logger.error(
                "[Subscription] batch query relation failed, fallback to per-instance query "
                f"rule_id={self.rule.id}, related_model={related_model}, error={exc}",
                exc_info=True,
            )

        relation_map: dict[int, list[int]] = {}
        failed_instance_ids: set[int] = set()
        for inst_id in instance_ids:
            try:
                rels = InstanceManage.instance_association(self.rule.model_id, inst_id)
            except Exception as exc:
                logger.error(
                    f"[Subscription] query relation failed inst_id={inst_id}, error={exc}",
                    exc_info=True,
                )
                failed_instance_ids.add(inst_id)
                continue
            related_ids: list[int] = []
            related_uuids: list[str] = []
            for rel in rels:
                if rel.get("src_model_id") == related_model:
                    related_uuid = _optional_uuid(rel.get("src_inst_uuid"))
                    related_graph_id = _optional_int(rel.get("src_inst_id"))
                elif rel.get("dst_model_id") == related_model:
                    related_uuid = _optional_uuid(rel.get("dst_inst_uuid"))
                    related_graph_id = _optional_int(rel.get("dst_inst_id"))
                else:
                    continue
                if related_uuid:
                    related_uuids.append(related_uuid)
                elif related_graph_id is not None:
                    related_ids.append(related_graph_id)
            # query_entity_by_uuids 拒绝重复 UUID，先去重。
            related_uuids = list(dict.fromkeys(related_uuids))
            if related_uuids:
                try:
                    for entity in InstanceManage.query_entity_by_uuids(related_uuids) or []:
                        related_graph_id = _optional_int(entity.get("_id"))
                        if related_graph_id is not None:
                            related_ids.append(related_graph_id)
                except Exception as resolve_exc:
                    logger.error(
                        f"[Subscription] query related uuid failed inst_id={inst_id}, error={resolve_exc}",
                        exc_info=True,
                    )
                    failed_instance_ids.add(inst_id)
                    continue
            relation_map[inst_id] = sorted(list(set(related_ids)))
        logger.info(
            "[Subscription] 关联实例查询完成 "
            f"rule_id={self.rule.id}, relation_map_size={len(relation_map)}, "
            f"failed_instance_count={len(failed_instance_ids)}"
        )
        return relation_map, failed_instance_ids

    def _build_current_snapshot(
        self,
        instances: list[dict[str, Any]],
        relations_by_model: dict[str, dict[int, list[int]]],
        failed_relation_instance_ids_by_model: dict[str, set[int]] | None = None,
    ) -> dict[str, Any]:
        relation_models = self._normalize_relation_change_models(self.rule.trigger_config.get("relation_change", {}))
        failed_relation_instance_ids_by_model = failed_relation_instance_ids_by_model or {}
        previous = self.rule.snapshot_data or {}
        previous_relations = previous.get("relations") or {}
        previous_relations_by_uuid = previous.get("relations_by_uuid") or {}

        id_to_uuid: dict[int, str] = {}
        related_ids: list[int] = []
        for inst in instances:
            graph_id = _optional_int(inst.get("_id"))
            inst_uuid = _optional_uuid(inst.get("inst_uuid"))
            if graph_id is not None and inst_uuid:
                id_to_uuid[graph_id] = inst_uuid
        for relation_map in relations_by_model.values():
            for inst_id, related in relation_map.items():
                related_ids.extend(related)
        missing_ids = sorted({item for item in related_ids if item not in id_to_uuid})
        if missing_ids:
            try:
                for entity in InstanceManage.query_entity_by_ids(missing_ids) or []:
                    graph_id = _optional_int(entity.get("_id"))
                    inst_uuid = _optional_uuid(entity.get("inst_uuid"))
                    if graph_id is not None and inst_uuid:
                        id_to_uuid[graph_id] = inst_uuid
            except Exception as exc:
                logger.error(
                    f"[Subscription] 关联实例 UUID 映射失败 rule_id={self.rule.id}, error={exc}",
                    exc_info=True,
                )

        snapshot_relations: dict[str, dict[str, list[int]]] = {}
        snapshot_relations_by_uuid: dict[str, dict[str, list[str]]] = {}
        instance_ids: list[int] = []
        instance_uuids: list[str] = []
        for inst in instances:
            graph_id = _optional_int(inst.get("_id"))
            inst_uuid = _optional_uuid(inst.get("inst_uuid"))
            if graph_id is not None:
                instance_ids.append(graph_id)
            if inst_uuid:
                instance_uuids.append(inst_uuid)
            inst_relations: dict[str, list[int]] = {}
            inst_relations_uuid: dict[str, list[str]] = {}
            for relation_model in relation_models:
                related_model = relation_model.get("related_model")
                if not related_model:
                    continue
                failed_instance_ids = failed_relation_instance_ids_by_model.get(related_model, set())
                if graph_id is not None and graph_id in failed_instance_ids:
                    previous_related_ids = (previous_relations.get(str(graph_id), {}) or {}).get(related_model)
                    if previous_related_ids is not None:
                        inst_relations[related_model] = list(previous_related_ids)
                    if inst_uuid:
                        previous_related_uuids = (previous_relations_by_uuid.get(inst_uuid, {}) or {}).get(related_model)
                        if previous_related_uuids is not None:
                            inst_relations_uuid[related_model] = list(previous_related_uuids)
                    continue
                related_graph_ids = relations_by_model.get(related_model, {}).get(graph_id, []) if graph_id is not None else []
                inst_relations[related_model] = related_graph_ids
                if inst_uuid:
                    related_uuids = [id_to_uuid[item] for item in related_graph_ids if item in id_to_uuid]
                    inst_relations_uuid[related_model] = related_uuids
            if graph_id is not None:
                snapshot_relations[str(graph_id)] = inst_relations
            if inst_uuid:
                snapshot_relations_by_uuid[inst_uuid] = inst_relations_uuid
        return {
            "instances": instance_ids,
            "instance_uuids": instance_uuids,
            "relations": snapshot_relations,
            "relations_by_uuid": snapshot_relations_by_uuid,
        }

    def _current_instance_tokens(self, instances: list[dict[str, Any]]) -> tuple[set[str], dict[str, int]]:
        tokens: set[str] = set()
        id_by_token: dict[str, int] = {}
        for inst in instances:
            graph_id = _optional_int(inst.get("_id"))
            inst_uuid = _optional_uuid(inst.get("inst_uuid"))
            token = inst_uuid or (f"id:{graph_id}" if graph_id is not None else None)
            if not token:
                continue
            tokens.add(token)
            if graph_id is not None:
                id_by_token[token] = graph_id
        return tokens, id_by_token

    def _snapshot_instance_tokens(
        self,
        snapshot: dict[str, Any] | None,
        uuid_by_id: dict[int, str],
    ) -> tuple[set[str], dict[str, int]]:
        snapshot = snapshot or {}
        tokens: set[str] = set()
        id_by_token: dict[str, int] = {}
        uuids = snapshot.get("instance_uuids") or []
        digits = snapshot.get("instances") or []
        if uuids:
            paired: dict[str, int] = {}
            if len(uuids) == len(digits):
                for digit, uuid_value in zip(digits, uuids):
                    uid = _optional_uuid(uuid_value)
                    gid = _optional_int(digit)
                    if uid and gid is not None:
                        paired[uid] = gid
            for uuid_value in uuids:
                uid = _optional_uuid(uuid_value)
                if not uid:
                    continue
                tokens.add(uid)
                if uid in paired:
                    id_by_token[uid] = paired[uid]
            return tokens, id_by_token
        for digit in digits:
            gid = _optional_int(digit)
            if gid is None:
                continue
            token = uuid_by_id.get(gid) or f"id:{gid}"
            tokens.add(token)
            id_by_token[token] = gid
        return tokens, id_by_token

    def _merge_attribute_summary(
        self,
        merged_event_map: dict[int, dict[str, Any]],
        inst_id: int,
        inst_name: str,
        summary_part: str,
    ) -> None:
        merged = merged_event_map.setdefault(
            inst_id,
            {
                "inst_name": inst_name,
                "parts": [],
            },
        )
        if not merged.get("inst_name") or merged["inst_name"] == str(inst_id):
            merged["inst_name"] = inst_name
        if summary_part and summary_part not in merged["parts"]:
            merged["parts"].append(summary_part)

    def _emit_attribute_event(
        self,
        events: list[TriggerEvent],
        inst_id: int,
        inst_name: str,
        summary_part: str,
        now_str: str,
    ) -> None:
        events.append(
            TriggerEvent(
                rule_id=self.rule.id,
                rule_name=self.rule.name,
                model_id=self.rule.model_id,
                model_name=self.model_name,
                trigger_type=TriggerType.ATTRIBUTE_CHANGE.value,
                inst_id=inst_id,
                inst_name=inst_name,
                change_summary=summary_part,
                triggered_at=now_str,
            )
        )

    @staticmethod
    def _resolve_attribute_inst_name(
        instance_map: dict[int, dict[str, Any]],
        inst_id: int,
        before_data: dict | None = None,
        after_data: dict | None = None,
    ) -> str:
        inst = instance_map.get(inst_id, {})
        inst_name = inst.get("inst_name") or inst.get("ip_addr") or str(inst_id)
        if inst_name and inst_name != str(inst_id):
            return inst_name
        before_data = before_data or {}
        after_data = after_data or {}
        return after_data.get("inst_name") or after_data.get("ip_addr") or before_data.get("inst_name") or before_data.get("ip_addr") or str(inst_id)

    def _build_related_change_map(
        self,
        related_model: str,
        related_instance_ids: list[int] | None,
        watch_fields: set[str],
        checkpoint: datetime,
        related_instance_uuids: list[str] | None = None,
    ) -> tuple[dict[Any, list[str]], int]:
        related_instance_ids = related_instance_ids or []
        related_instance_uuids = related_instance_uuids or []
        if not related_instance_ids and not related_instance_uuids:
            return {}, 0

        last_check = self.rule.last_check_time or self.rule.created_at
        query = ChangeRecord.objects.filter(
            model_id=related_model,
            type__in=[UPDATE_INST, CREATE_INST, DELETE_INST],
            created_at__gt=last_check,
            created_at__lte=checkpoint,
        )
        if related_instance_uuids:
            query = query.filter(Q(inst_id__in=related_instance_ids) | Q(inst_uuid__in=related_instance_uuids))
        else:
            query = query.filter(inst_id__in=related_instance_ids)
        related_change_records = list(query.order_by("created_at"))
        related_change_map: dict[Any, list[str]] = {}
        for record in related_change_records:
            before_data = record.before_data or {}
            after_data = record.after_data or {}
            changed_fields = self._get_changed_fields(before_data, after_data)
            matched_fields = sorted(list(changed_fields & watch_fields)) if watch_fields else sorted(list(changed_fields))
            if not matched_fields:
                continue

            change_details: list[str] = []
            for field in matched_fields:
                old_val = truncate_value(before_data.get(field))
                new_val = truncate_value(after_data.get(field))
                change_details.append(f"{field}: {old_val} → {new_val}")
            if not change_details:
                continue
            summary = "字段变化: " + "; ".join(change_details)
            related_change_map.setdefault(record.inst_id, []).append(summary)
            record_uuid = _optional_uuid(record.inst_uuid)
            if record_uuid:
                related_change_map.setdefault(record_uuid, []).append(summary)
        return related_change_map, len(related_change_records)

    def _build_related_inst_name_map(
        self,
        related_model: str,
        previous_relations: dict[str, dict[str, list[int]]],
        current_relations: dict[str, dict[str, list[int]]],
    ) -> dict[int, str]:
        related_instance_ids = sorted(
            {
                int(rel_id)
                for relations in (previous_relations.values(), current_relations.values())
                for relation_item in relations
                for rel_id in (relation_item.get(related_model, []) or [])
                if rel_id is not None
            }
        )
        if not related_instance_ids:
            return {}

        related_inst_name_map: dict[int, str] = {}
        try:
            related_instances, _ = InstanceManage.instance_list(
                model_id=related_model,
                params=[
                    {
                        "field": "id",
                        "type": "id[]",
                        "value": related_instance_ids,
                    }
                ],
                page=1,
                page_size=max(1, len(related_instance_ids)),
                order="",
                permission_map={},
                creator="",
            )
            for related_inst in related_instances:
                related_inst_id = related_inst.get("_id")
                if related_inst_id is None:
                    continue
                try:
                    related_inst_id = int(related_inst_id)
                except (TypeError, ValueError):
                    continue
                related_inst_name_map[related_inst_id] = related_inst.get("inst_name") or related_inst.get("ip_addr") or str(related_inst_id)
        except Exception as exc:
            logger.error(
                f"[Subscription] 关联实例名称查询失败 rule_id={self.rule.id}, related_model={related_model}, error={exc}",
                exc_info=True,
            )
        return related_inst_name_map

    def _build_related_inst_name_map_by_uuid(
        self,
        related_model: str,
        previous_relations: dict[str, dict[str, list[str]]],
        current_relations: dict[str, dict[str, list[str]]],
    ) -> dict[str, str]:
        related_uuids = sorted(
            {
                uid
                for relations in (previous_relations.values(), current_relations.values())
                for relation_item in relations
                for rel_id in (relation_item.get(related_model, []) or [])
                if (uid := _optional_uuid(rel_id))
            }
        )
        if not related_uuids:
            return {}

        related_inst_name_map: dict[str, str] = {}
        try:
            related_instances, _ = InstanceManage.instance_list(
                model_id=related_model,
                params=[{"field": "inst_uuid", "type": "str[]", "value": related_uuids}],
                page=1,
                page_size=max(1, len(related_uuids)),
                order="",
                permission_map={},
                creator="",
            )
            for related_inst in related_instances:
                related_uuid = _optional_uuid(related_inst.get("inst_uuid"))
                if not related_uuid:
                    continue
                related_inst_name_map[related_uuid] = related_inst.get("inst_name") or related_inst.get("ip_addr") or related_uuid
        except Exception as exc:
            logger.error(
                f"[Subscription] 关联实例名称查询失败 rule_id={self.rule.id}, related_model={related_model}, error={exc}",
                exc_info=True,
            )
        return related_inst_name_map

    def _emit_filter_membership_changes(
        self,
        *,
        events: list[TriggerEvent],
        merged_event_map: dict[int, dict[str, Any]],
        instance_map: dict[int, dict[str, Any]],
        previous_tokens: set[str],
        previous_id_by_token: dict[str, int],
        current_tokens: set[str],
        current_id_by_token: dict[str, int],
        merge_mode: str,
        now_str: str,
    ) -> None:
        """过滤条件模式下，对比实例集合增减并补齐进入/离开范围类触发。"""
        added_tokens = sorted(current_tokens - previous_tokens)
        removed_tokens = sorted(previous_tokens - current_tokens)

        for token in added_tokens:
            inst_id = current_id_by_token.get(token)
            if inst_id is None:
                continue
            summary = "实例进入订阅范围（可能为新建或属性变化命中过滤条件）"
            inst_name = self._resolve_attribute_inst_name(instance_map, inst_id)
            if merge_mode == "single":
                self._merge_attribute_summary(merged_event_map, inst_id, inst_name, summary)
            else:
                self._emit_attribute_event(events, inst_id, inst_name, summary, now_str)

        for token in removed_tokens:
            inst_id = previous_id_by_token.get(token)
            if inst_id is None and token.startswith("id:"):
                inst_id = _optional_int(token[3:])
            if inst_id is None:
                continue
            summary = "实例离开订阅范围（可能为删除或属性变化不再命中过滤条件）"
            inst_name = self._resolve_attribute_inst_name(instance_map, inst_id)
            if merge_mode == "single":
                self._merge_attribute_summary(merged_event_map, inst_id, inst_name, summary)
            else:
                self._emit_attribute_event(events, inst_id, inst_name, summary, now_str)

        if added_tokens or removed_tokens:
            logger.info(
                "[Subscription] 过滤条件实例集合变化检测完成 " f"rule_id={self.rule.id}, added_count={len(added_tokens)}, " f"removed_count={len(removed_tokens)}"
            )

    def _check_attribute_change(self, instances: list[dict[str, Any]], checkpoint: datetime) -> list[TriggerEvent]:
        # 属性变化通过 ChangeRecord 增量窗口比对，避免全量字段对比开销。
        events: list[TriggerEvent] = []
        config = self.rule.trigger_config.get("attribute_change", {})
        watch_fields = set(config.get("fields", []))
        merge_mode = self.attribute_merge_mode
        if not watch_fields:
            logger.info(f"[Subscription] 未配置属性监听字段，跳过 rule_id={self.rule.id}")
            return events

        instance_map = {int(inst.get("_id")): inst for inst in instances if inst.get("_id") is not None}
        uuid_by_id = {}
        for inst in instances:
            graph_id = _optional_int(inst.get("_id"))
            inst_uuid = _optional_uuid(inst.get("inst_uuid"))
            if graph_id is not None and inst_uuid:
                uuid_by_id[graph_id] = inst_uuid
        snapshot = self.rule.snapshot_data or {}
        previous_tokens, previous_id_by_token = self._snapshot_instance_tokens(snapshot, uuid_by_id)
        current_tokens, current_id_by_token = self._current_instance_tokens(instances)
        previous_instance_ids = {gid for gid in (_optional_int(inst_id) for inst_id in snapshot.get("instances") or []) if gid is not None}
        candidate_instance_ids = sorted(set(instance_map.keys()) | previous_instance_ids)
        candidate_uuids = []
        for value in snapshot.get("instance_uuids") or []:
            uid = _optional_uuid(value)
            if uid:
                candidate_uuids.append(uid)
        candidate_uuids.extend(uuid_by_id.values())
        now_str = timezone.now().isoformat()

        merged_event_map: dict[int, dict[str, Any]] = {}

        # 过滤条件模式下，显式对比实例集合增减，补齐新增/删除类触发。
        if self.rule.filter_type == FilterType.CONDITION.value:
            self._emit_filter_membership_changes(
                events=events,
                merged_event_map=merged_event_map,
                instance_map=instance_map,
                previous_tokens=previous_tokens,
                previous_id_by_token=previous_id_by_token,
                current_tokens=current_tokens,
                current_id_by_token=current_id_by_token,
                merge_mode=merge_mode,
                now_str=now_str,
            )

        if not candidate_instance_ids and not candidate_uuids:
            return events

        last_check = self.rule.last_check_time or self.rule.created_at
        query = ChangeRecord.objects.filter(
            model_id=self.rule.model_id,
            type__in=[UPDATE_INST, CREATE_INST, DELETE_INST],
            created_at__gt=last_check,
            created_at__lte=checkpoint,
        )
        if candidate_uuids:
            query = query.filter(Q(inst_id__in=candidate_instance_ids) | Q(inst_uuid__in=candidate_uuids))
        else:
            query = query.filter(inst_id__in=candidate_instance_ids)
        records = list(query.order_by("created_at"))
        if not records:
            logger.info(
                "[Subscription] 属性变更窗口无变更记录 "
                f"rule_id={self.rule.id}, candidate_instances={len(candidate_instance_ids)}, "
                f"last_check={last_check.isoformat()}, checkpoint={checkpoint.isoformat()}"
            )
            return events
        logger.info(
            "[Subscription] 属性变更窗口查询完成 "
            f"rule_id={self.rule.id}, watch_fields={sorted(list(watch_fields))}, "
            f"candidate_instances={len(candidate_instance_ids)}, "
            f"records_count={len(records)}, merge_mode={merge_mode}, last_check={last_check.isoformat()}, "
            f"checkpoint={checkpoint.isoformat()}"
        )

        for record in records:
            before_data = record.before_data or {}
            after_data = record.after_data or {}
            changed_fields = self._get_changed_fields(before_data, after_data)
            matched = sorted(list(changed_fields & watch_fields))
            if not matched:
                continue
            inst_name = self._resolve_attribute_inst_name(instance_map, record.inst_id, before_data, after_data)
            change_details = []
            for field in matched:
                old_val = truncate_value(before_data.get(field))
                new_val = truncate_value(after_data.get(field))
                change_details.append(f"{field}: {old_val} → {new_val}")
            if not change_details:
                continue

            field_change_summary = "字段变化: " + "; ".join(change_details)
            if merge_mode == "single":
                self._merge_attribute_summary(merged_event_map, record.inst_id, inst_name, field_change_summary)
            else:
                self._emit_attribute_event(
                    events,
                    record.inst_id,
                    inst_name,
                    field_change_summary,
                    now_str,
                )

        if merge_mode == "single":
            for inst_id, merged in merged_event_map.items():
                parts = merged.get("parts", [])
                change_summary = " | ".join(parts)
                if "实例进入订阅范围" in change_summary and "字段变化:" in change_summary:
                    change_summary = "创建并修改: " + change_summary

                events.append(
                    TriggerEvent(
                        rule_id=self.rule.id,
                        rule_name=self.rule.name,
                        model_id=self.rule.model_id,
                        model_name=self.model_name,
                        trigger_type=TriggerType.ATTRIBUTE_CHANGE.value,
                        inst_id=inst_id,
                        inst_name=merged.get("inst_name", str(inst_id)),
                        change_summary=change_summary,
                        triggered_at=now_str,
                    )
                )
        logger.info(f"[Subscription] 属性变更检测完成 rule_id={self.rule.id}, merge_mode={merge_mode}, events_count={len(events)}")
        return events

    def _check_relation_change(
        self,
        current_snapshot: dict[str, Any],
        instances: list[dict[str, Any]],
        checkpoint: datetime,
        failed_relation_instance_ids_by_model: dict[str, set[int]] | None = None,
    ) -> list[TriggerEvent]:
        # 关联变化关注两类事件：关联实例新增/删除，及已关联实例的属性变化。
        relation_config = self.rule.trigger_config.get("relation_change", {}) or {}
        relation_models = self._normalize_relation_change_models(relation_config)
        if not relation_models:
            logger.info(f"[Subscription] 未配置关联模型，跳过 rule_id={self.rule.id}")
            return []

        failed_relation_instance_ids_by_model = failed_relation_instance_ids_by_model or {}
        previous_relations_by_uuid = (self.rule.snapshot_data or {}).get("relations_by_uuid")
        if previous_relations_by_uuid:
            return self._check_relation_change_by_uuid(
                current_snapshot,
                instances,
                checkpoint,
                failed_relation_instance_ids_by_model,
                relation_models,
            )

        previous_relations = (self.rule.snapshot_data or {}).get("relations", {})
        current_relations = current_snapshot.get("relations", {})
        all_instance_ids = sorted(set(previous_relations.keys()) | set(current_relations.keys()))
        inst_name_map = {
            str(int(inst.get("_id"))): (inst.get("inst_name") or inst.get("ip_addr") or str(inst.get("_id")))
            for inst in instances
            if inst.get("_id") is not None
        }
        now_str = timezone.now().isoformat()
        events: list[TriggerEvent] = []
        total_related_record_count = 0

        for relation_model in relation_models:
            related_model = relation_model.get("related_model")
            if not related_model:
                continue
            failed_instance_ids = failed_relation_instance_ids_by_model.get(related_model, set())
            watch_fields = set(relation_model.get("fields", []) or [])
            related_instance_ids = sorted(
                {
                    int(rel_id)
                    for relations in (previous_relations.values(), current_relations.values())
                    for relation_item in relations
                    for rel_id in (relation_item.get(related_model, []) or [])
                    if rel_id is not None
                }
            )
            related_change_map, related_record_count = self._build_related_change_map(
                related_model=related_model,
                related_instance_ids=related_instance_ids,
                watch_fields=watch_fields,
                checkpoint=checkpoint,
            )
            total_related_record_count += related_record_count
            related_inst_name_map = self._build_related_inst_name_map(
                related_model=related_model,
                previous_relations=previous_relations,
                current_relations=current_relations,
            )

            for inst_id_str in all_instance_ids:
                if int(inst_id_str) in failed_instance_ids:
                    continue
                prev_related = set((previous_relations.get(inst_id_str, {}) or {}).get(related_model, []))
                curr_related = set((current_relations.get(inst_id_str, {}) or {}).get(related_model, []))
                added = sorted(list(curr_related - prev_related))
                removed = sorted(list(prev_related - curr_related))
                stable_related = sorted(list(prev_related & curr_related))

                summary_parts = []
                if added:
                    summary_parts.append(f"新增关联: {added}")
                if removed:
                    summary_parts.append(f"删除关联: {removed}")

                changed_related_parts = []
                for related_inst_id in stable_related:
                    change_summaries = related_change_map.get(related_inst_id, [])
                    if not change_summaries:
                        continue
                    merged_summary = " | ".join(change_summaries)
                    related_inst_name = related_inst_name_map.get(related_inst_id, str(related_inst_id))
                    changed_related_parts.append(f"关联实例[{related_inst_name}]属性变化: {merged_summary}")
                if changed_related_parts:
                    summary_parts.extend(changed_related_parts)

                if not summary_parts:
                    continue

                events.append(
                    TriggerEvent(
                        rule_id=self.rule.id,
                        rule_name=self.rule.name,
                        model_id=self.rule.model_id,
                        model_name=self.model_name,
                        trigger_type=TriggerType.RELATION_CHANGE.value,
                        inst_id=int(inst_id_str),
                        inst_name=inst_name_map.get(inst_id_str, inst_id_str),
                        change_summary=f"关联模型[{related_model}]变化: {'; '.join(summary_parts)}",
                        triggered_at=now_str,
                    )
                )
        logger.info(
            "[Subscription] 关联变化检测完成 "
            f"rule_id={self.rule.id}, relation_models_count={len(relation_models)}, "
            f"instances_compared={len(all_instance_ids)}, related_record_count={total_related_record_count}, "
            f"events_count={len(events)}"
        )
        return events

    def _check_relation_change_by_uuid(
        self,
        current_snapshot: dict[str, Any],
        instances: list[dict[str, Any]],
        checkpoint: datetime,
        failed_relation_instance_ids_by_model: dict[str, set[int]],
        relation_models: list[dict[str, Any]],
    ) -> list[TriggerEvent]:
        previous_relations = (self.rule.snapshot_data or {}).get("relations_by_uuid") or {}
        current_relations = current_snapshot.get("relations_by_uuid") or {}
        uuid_to_id: dict[str, int] = {}
        inst_name_map: dict[str, str] = {}
        snapshot = self.rule.snapshot_data or {}
        snapshot_uuids = snapshot.get("instance_uuids") or []
        snapshot_ids = snapshot.get("instances") or []
        if len(snapshot_uuids) == len(snapshot_ids):
            for digit, uuid_value in zip(snapshot_ids, snapshot_uuids):
                uid = _optional_uuid(uuid_value)
                gid = _optional_int(digit)
                if uid and gid is not None:
                    uuid_to_id[uid] = gid
        for inst in instances:
            graph_id = _optional_int(inst.get("_id"))
            inst_uuid = _optional_uuid(inst.get("inst_uuid"))
            if inst_uuid and graph_id is not None:
                uuid_to_id[inst_uuid] = graph_id
            if inst_uuid:
                inst_name_map[inst_uuid] = inst.get("inst_name") or inst.get("ip_addr") or inst_uuid
        all_instance_uuids = sorted(set(previous_relations.keys()) | set(current_relations.keys()))
        now_str = timezone.now().isoformat()
        events: list[TriggerEvent] = []
        total_related_record_count = 0

        for relation_model in relation_models:
            related_model = relation_model.get("related_model")
            if not related_model:
                continue
            failed_instance_ids = failed_relation_instance_ids_by_model.get(related_model, set())
            failed_uuids = {uid for uid, gid in uuid_to_id.items() if gid in failed_instance_ids}
            watch_fields = set(relation_model.get("fields", []) or [])
            related_uuids = sorted(
                {
                    uid
                    for relations in (previous_relations.values(), current_relations.values())
                    for relation_item in relations
                    for rel_id in (relation_item.get(related_model, []) or [])
                    if (uid := _optional_uuid(rel_id))
                }
            )
            related_change_map, related_record_count = self._build_related_change_map(
                related_model=related_model,
                related_instance_ids=[],
                related_instance_uuids=related_uuids,
                watch_fields=watch_fields,
                checkpoint=checkpoint,
            )
            total_related_record_count += related_record_count
            related_inst_name_map = self._build_related_inst_name_map_by_uuid(related_model, previous_relations, current_relations)

            for inst_uuid in all_instance_uuids:
                if inst_uuid in failed_uuids:
                    continue
                prev_related = {_optional_uuid(item) for item in ((previous_relations.get(inst_uuid, {}) or {}).get(related_model, []) or [])}
                curr_related = {_optional_uuid(item) for item in ((current_relations.get(inst_uuid, {}) or {}).get(related_model, []) or [])}
                prev_related.discard(None)
                curr_related.discard(None)
                added = sorted(curr_related - prev_related)
                removed = sorted(prev_related - curr_related)
                stable_related = sorted(prev_related & curr_related)

                summary_parts = []
                if added:
                    summary_parts.append(f"新增关联: {added}")
                if removed:
                    summary_parts.append(f"删除关联: {removed}")

                changed_related_parts = []
                for related_inst_uuid in stable_related:
                    change_summaries = related_change_map.get(related_inst_uuid, [])
                    if not change_summaries:
                        continue
                    merged_summary = " | ".join(change_summaries)
                    related_inst_name = related_inst_name_map.get(related_inst_uuid, related_inst_uuid)
                    changed_related_parts.append(f"关联实例[{related_inst_name}]属性变化: {merged_summary}")
                if changed_related_parts:
                    summary_parts.extend(changed_related_parts)
                if not summary_parts:
                    continue
                events.append(
                    TriggerEvent(
                        rule_id=self.rule.id,
                        rule_name=self.rule.name,
                        model_id=self.rule.model_id,
                        model_name=self.model_name,
                        trigger_type=TriggerType.RELATION_CHANGE.value,
                        inst_id=uuid_to_id.get(inst_uuid, 0),
                        inst_name=inst_name_map.get(inst_uuid, inst_uuid),
                        change_summary=f"关联模型[{related_model}]变化: {'; '.join(summary_parts)}",
                        triggered_at=now_str,
                    )
                )
        logger.info(
            "[Subscription] 关联变化检测完成 "
            f"rule_id={self.rule.id}, relation_models_count={len(relation_models)}, "
            f"instances_compared={len(all_instance_uuids)}, related_record_count={total_related_record_count}, "
            f"events_count={len(events)}"
        )
        return events

    def _check_expiration(self, instances: list[dict[str, Any]], current_snapshot: dict[str, Any]) -> list[TriggerEvent]:
        # 到期提醒使用去重键避免同一实例在窗口内反复通知。
        config = self.rule.trigger_config.get("expiration", {})
        time_field = config.get("time_field")
        days_before = config.get("days_before")
        if not time_field or not isinstance(days_before, int) or days_before <= 0:
            logger.info(f"[Subscription] 到期配置无效，跳过 rule_id={self.rule.id}")
            return []

        previous_notified = set(((self.rule.snapshot_data or {}).get("expiration_notified", {}) or {}).keys())
        current_notified: dict[str, str] = {}
        today = timezone.localdate()
        target_date = today + timedelta(days=days_before)
        now_str = timezone.now().isoformat()
        events: list[TriggerEvent] = []
        for inst in instances:
            raw_val = inst.get(time_field)
            if not raw_val:
                continue
            expire_date = self._parse_to_date(raw_val)
            if not expire_date:
                continue
            if today <= expire_date <= target_date:
                days_remaining = (expire_date - today).days
                inst_id = _optional_int(inst.get("_id"))
                inst_uuid = _optional_uuid(inst.get("inst_uuid"))
                if inst_id is None:
                    continue
                id_key = f"{inst_id}:{time_field}:{expire_date.isoformat()}"
                uuid_key = f"{inst_uuid}:{time_field}:{expire_date.isoformat()}" if inst_uuid else None
                current_notified[uuid_key or id_key] = now_str
                if id_key in previous_notified or (uuid_key and uuid_key in previous_notified):
                    continue
                inst_name = inst.get("inst_name") or inst.get("ip_addr") or str(inst_id)
                events.append(
                    TriggerEvent(
                        rule_id=self.rule.id,
                        rule_name=self.rule.name,
                        model_id=self.rule.model_id,
                        model_name=self.model_name,
                        trigger_type=TriggerType.EXPIRATION.value,
                        inst_id=inst_id,
                        inst_name=inst_name,
                        change_summary=f"字段 {time_field} 将在 {days_remaining} 天后到期（{expire_date}）",
                        triggered_at=now_str,
                    )
                )
        current_snapshot["expiration_notified"] = current_notified
        logger.info(
            "[Subscription] 到期检测完成 "
            f"rule_id={self.rule.id}, time_field={time_field}, days_before={days_before}, "
            f"instances_checked={len(instances)}, dedup_keys={len(current_notified)}, "
            f"events_count={len(events)}"
        )
        return events

    def _update_snapshot(self, current_snapshot: dict[str, Any], checkpoint: datetime) -> None:
        updates: dict[str, Any] = {
            "snapshot_data": current_snapshot,
            "last_check_time": checkpoint,
            "updated_by": "system",
        }
        if self.events:
            updates["last_triggered_at"] = checkpoint
        SubscriptionRule.objects.filter(id=self.rule.id).update(**updates)
        for key, value in updates.items():
            setattr(self.rule, key, value)
        logger.info(f"[Subscription] 快照更新完成 rule_id={self.rule.id}, last_check_time={checkpoint.isoformat()}, triggered={bool(self.events)}")

    @staticmethod
    def _get_changed_fields(before_data: dict, after_data: dict) -> set[str]:
        fields = set(before_data.keys()) | set(after_data.keys())
        return {f for f in fields if before_data.get(f) != after_data.get(f)}

    @staticmethod
    def _parse_to_date(raw_val: Any):
        if isinstance(raw_val, datetime):
            return raw_val.date()
        if isinstance(raw_val, str):
            try:
                return datetime.fromisoformat(raw_val.replace("Z", "+00:00")).date()
            except Exception:
                return None
        return None

    def _check_config_file(
        self,
        instances: list[dict[str, Any]],
        current_snapshot: dict[str, Any],
        checkpoint: datetime,
    ) -> list[TriggerEvent]:
        from apps.cmdb.models.config_file_version import ConfigFileVersion, ConfigFileVersionStatus

        events: list[TriggerEvent] = []

        if self.rule.model_id != "host":
            logger.info(f"[Subscription] 配置文件触发仅对主机模型生效，跳过 " f"rule_id={self.rule.id}, model_id={self.rule.model_id}")
            return events

        instance_ids = [str(inst.get("_id")) for inst in instances if inst.get("_id") is not None]
        instance_uuids = [uid for inst in instances if (uid := _optional_uuid(inst.get("inst_uuid")))]
        if not instance_ids and not instance_uuids:
            return events

        instance_map = {str(inst.get("_id")): inst for inst in instances if inst.get("_id") is not None}
        instance_map_by_uuid = {uid: inst for inst in instances if (uid := _optional_uuid(inst.get("inst_uuid")))}

        last_check = self.rule.last_check_time or self.rule.created_at
        query = ConfigFileVersion.objects.filter(
            model_id="host",
            status=ConfigFileVersionStatus.SUCCESS,
            created_at__gt=last_check,
            created_at__lte=checkpoint,
        )
        if instance_uuids:
            query = query.filter(Q(instance_uuid__in=instance_uuids) | Q(instance_id__in=instance_ids))
        else:
            query = query.filter(instance_id__in=instance_ids)
        versions = query.order_by("created_at")

        if not versions.exists():
            logger.info(
                f"[Subscription] 配置文件检测窗口无新增记录 "
                f"rule_id={self.rule.id}, last_check={last_check.isoformat()}, "
                f"checkpoint={checkpoint.isoformat()}"
            )
            return events

        previous_notified = set(((self.rule.snapshot_data or {}).get("config_file_notified", {}) or {}).keys())
        current_notified: dict[str, str] = {}
        now_str = timezone.now().isoformat()
        notified_instance_ids: set[str] = set()

        for version in versions:
            version_uuid = _optional_uuid(version.instance_uuid)
            id_key = str(version.instance_id)
            dedup_key = version_uuid or id_key

            if (
                dedup_key in previous_notified
                or id_key in previous_notified
                or (version_uuid and version_uuid in previous_notified)
                or dedup_key in current_notified
            ):
                continue

            if version.instance_id in notified_instance_ids or (version_uuid and version_uuid in notified_instance_ids):
                continue

            notified_instance_ids.add(version.instance_id)
            if version_uuid:
                notified_instance_ids.add(version_uuid)
            current_notified[dedup_key] = now_str

            inst = instance_map_by_uuid.get(version_uuid or "", {}) or instance_map.get(version.instance_id, {})
            inst_name = inst.get("inst_name") or inst.get("ip_addr") or version.instance_id
            inst_id = _optional_int(inst.get("_id")) or _optional_int(version.instance_id) or 0

            events.append(
                TriggerEvent(
                    rule_id=self.rule.id,
                    rule_name=self.rule.name,
                    model_id=self.rule.model_id,
                    model_name=self.model_name,
                    trigger_type=TriggerType.CONFIG_FILE.value,
                    inst_id=inst_id,
                    inst_name=inst_name,
                    change_summary="检测到配置采集任务采集到配置文件",
                    triggered_at=now_str,
                )
            )

        current_snapshot["config_file_notified"] = current_notified

        logger.info(f"[Subscription] 配置文件检测完成 " f"rule_id={self.rule.id}, events_count={len(events)}")
        return events
