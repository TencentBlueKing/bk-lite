from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any

from django.utils import timezone

from apps.cmdb.constants.subscription import (
    FilterType,
    INSTANCE_QUERY_PAGE_SIZE,
    TriggerType,
)
from apps.cmdb.models.change_record import (
    CREATE_INST,
    DELETE_INST,
    ChangeRecord,
    UPDATE_INST,
)
from apps.cmdb.models.subscription_rule import SubscriptionRule
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.model import ModelManage
from apps.cmdb.utils.subscription_utils import truncate_value
from apps.core.logger import cmdb_logger as logger


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

    def process(self) -> list[TriggerEvent]:
        # 固定检查上界，确保查询窗口稳定在 (last_check_time, checkpoint]。
        checkpoint = timezone.now()
        logger.info(
            "[Subscription] 触发检测开始 "
            f"rule_id={self.rule.id}, model_id={self.rule.model_id}, "
            f"trigger_types={self.rule.trigger_types}, checkpoint={checkpoint.isoformat()}"
        )
        instances = self._get_current_instances()
        logger.info(
            "[Subscription] 当前实例集加载完成 "
            f"rule_id={self.rule.id}, instances_count={len(instances)}"
        )
        if not instances:
            self._update_snapshot(
                {"instances": [], "relations": {}, "expiration_notified": {}},
                checkpoint,
            )
            logger.info(
                f"[Subscription] 当前实例为空，已更新快照 rule_id={self.rule.id}"
            )
            return []

        instance_ids = [
            int(i.get("_id")) for i in instances if i.get("_id") is not None
        ]
        relation_map: dict[int, list[int]] = {}
        if TriggerType.RELATION_CHANGE.value in self.rule.trigger_types:
            related_model = (
                self.rule.trigger_config.get("relation_change", {}) or {}
            ).get("related_model")
            if related_model:
                relation_map = self._get_relation_instances(instance_ids, related_model)

        current_snapshot = self._build_current_snapshot(instances, relation_map)

        if TriggerType.ATTRIBUTE_CHANGE.value in self.rule.trigger_types:
            self.events.extend(self._check_attribute_change(instances, checkpoint))
        if TriggerType.RELATION_CHANGE.value in self.rule.trigger_types:
            self.events.extend(
                self._check_relation_change(current_snapshot, instances, checkpoint)
            )
        if TriggerType.EXPIRATION.value in self.rule.trigger_types:
            self.events.extend(self._check_expiration(instances, current_snapshot))

        self._update_snapshot(current_snapshot, checkpoint)
        logger.info(
            "[Subscription] 触发检测结束 "
            f"rule_id={self.rule.id}, events_count={len(self.events)}"
        )
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
                instance_ids = self.rule.instance_filter.get("instance_ids", [])
                if not instance_ids:
                    logger.info(
                        f"[Subscription] 实例筛选为空，跳过 rule_id={self.rule.id}"
                    )
                    return []
                query_list = [{"field": "id", "type": "id[]", "value": instance_ids}]

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
            logger.info(
                "[Subscription] 分页查询实例 "
                f"rule_id={self.rule.id}, page={page}, page_size={page_size}, "
                f"fetched={len(data)}, total={count}"
            )
            if len(all_instances) >= count:
                break
            page += 1

        return all_instances

    def _get_relation_instances(
        self, instance_ids: list[int], related_model: str
    ) -> dict[int, list[int]]:
        logger.info(
            "[Subscription] 开始查询关联实例 "
            f"rule_id={self.rule.id}, related_model={related_model}, "
            f"instance_count={len(instance_ids)}"
        )
        relation_map: dict[int, list[int]] = {}
        for inst_id in instance_ids:
            try:
                rels = InstanceManage.instance_association(self.rule.model_id, inst_id)
            except Exception as exc:
                logger.error(
                    f"[Subscription] query relation failed inst_id={inst_id}, error={exc}",
                    exc_info=True,
                )
                continue
            related_ids: list[int] = []
            for rel in rels:
                if rel.get("src_model_id") == related_model:
                    related_ids.append(int(rel.get("src_inst_id")))
                elif rel.get("dst_model_id") == related_model:
                    related_ids.append(int(rel.get("dst_inst_id")))
            relation_map[inst_id] = sorted(list(set(related_ids)))
        logger.info(
            "[Subscription] 关联实例查询完成 "
            f"rule_id={self.rule.id}, relation_map_size={len(relation_map)}"
        )
        return relation_map

    def _build_current_snapshot(
        self, instances: list[dict[str, Any]], relations: dict[int, list[int]]
    ) -> dict[str, Any]:
        related_model = (self.rule.trigger_config.get("relation_change", {}) or {}).get(
            "related_model", ""
        )
        snapshot_relations: dict[str, dict[str, list[int]]] = {}
        for inst in instances:
            inst_id = int(inst.get("_id"))
            snapshot_relations[str(inst_id)] = (
                {related_model: relations.get(inst_id, [])} if related_model else {}
            )
        return {
            "instances": [
                int(i.get("_id")) for i in instances if i.get("_id") is not None
            ],
            "relations": snapshot_relations,
        }

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
        return (
            after_data.get("inst_name")
            or after_data.get("ip_addr")
            or before_data.get("inst_name")
            or before_data.get("ip_addr")
            or str(inst_id)
        )

    def _build_related_change_map(
        self,
        related_model: str,
        watch_fields: set[str],
        checkpoint: datetime,
    ) -> tuple[dict[int, list[str]], int]:
        last_check = self.rule.last_check_time or self.rule.created_at
        related_change_records = list(
            ChangeRecord.objects.filter(
                model_id=related_model,
                type__in=[UPDATE_INST, CREATE_INST, DELETE_INST],
                created_at__gt=last_check,
                created_at__lte=checkpoint,
            ).order_by("created_at")
        )
        related_change_map: dict[int, list[str]] = {}
        for record in related_change_records:
            before_data = record.before_data or {}
            after_data = record.after_data or {}
            changed_fields = self._get_changed_fields(before_data, after_data)
            matched_fields = (
                sorted(list(changed_fields & watch_fields))
                if watch_fields
                else sorted(list(changed_fields))
            )
            if not matched_fields:
                continue

            change_details: list[str] = []
            for field in matched_fields:
                old_val = truncate_value(before_data.get(field))
                new_val = truncate_value(after_data.get(field))
                change_details.append(f"{field}: {old_val} → {new_val}")
            if not change_details:
                continue
            related_change_map.setdefault(record.inst_id, []).append(
                "字段变化: " + "; ".join(change_details)
            )
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
                related_inst_name_map[related_inst_id] = (
                    related_inst.get("inst_name")
                    or related_inst.get("ip_addr")
                    or str(related_inst_id)
                )
        except Exception as exc:
            logger.error(
                f"[Subscription] 关联实例名称查询失败 rule_id={self.rule.id}, related_model={related_model}, error={exc}",
                exc_info=True,
            )
        return related_inst_name_map

    def _check_attribute_change(
        self, instances: list[dict[str, Any]], checkpoint: datetime
    ) -> list[TriggerEvent]:
        # 属性变化通过 ChangeRecord 增量窗口比对，避免全量字段对比开销。
        events: list[TriggerEvent] = []
        config = self.rule.trigger_config.get("attribute_change", {})
        watch_fields = set(config.get("fields", []))
        merge_mode = self.attribute_merge_mode
        if not watch_fields:
            logger.info(
                f"[Subscription] 未配置属性监听字段，跳过 rule_id={self.rule.id}"
            )
            return events

        instance_map = {
            int(inst.get("_id")): inst
            for inst in instances
            if inst.get("_id") is not None
        }
        previous_instance_ids = {
            int(inst_id)
            for inst_id in (self.rule.snapshot_data or {}).get("instances", [])
        }
        candidate_instance_ids = sorted(
            set(instance_map.keys()) | previous_instance_ids
        )
        now_str = timezone.now().isoformat()

        merged_event_map: dict[int, dict[str, Any]] = {}

        # 过滤条件模式下，显式对比实例集合增减，补齐新增/删除类触发。
        if self.rule.filter_type == FilterType.CONDITION.value:
            current_instance_ids = set(instance_map.keys())
            added_ids = sorted(current_instance_ids - previous_instance_ids)
            removed_ids = sorted(previous_instance_ids - current_instance_ids)

            for inst_id in added_ids:
                summary = "实例进入订阅范围（可能为新建或属性变化命中过滤条件）"
                inst_name = self._resolve_attribute_inst_name(instance_map, inst_id)
                if merge_mode == "single":
                    self._merge_attribute_summary(
                        merged_event_map, inst_id, inst_name, summary
                    )
                else:
                    self._emit_attribute_event(
                        events, inst_id, inst_name, summary, now_str
                    )

            for inst_id in removed_ids:
                summary = "实例离开订阅范围（可能为删除或属性变化不再命中过滤条件）"
                inst_name = self._resolve_attribute_inst_name(instance_map, inst_id)
                if merge_mode == "single":
                    self._merge_attribute_summary(
                        merged_event_map, inst_id, inst_name, summary
                    )
                else:
                    self._emit_attribute_event(
                        events, inst_id, inst_name, summary, now_str
                    )

            if added_ids or removed_ids:
                logger.info(
                    "[Subscription] 过滤条件实例集合变化检测完成 "
                    f"rule_id={self.rule.id}, added_count={len(added_ids)}, "
                    f"removed_count={len(removed_ids)}"
                )

        if not candidate_instance_ids:
            return events

        last_check = self.rule.last_check_time or self.rule.created_at
        query = ChangeRecord.objects.filter(
            model_id=self.rule.model_id,
            type__in=[UPDATE_INST, CREATE_INST, DELETE_INST],
            inst_id__in=candidate_instance_ids,
            created_at__gt=last_check,
            created_at__lte=checkpoint,
        ).order_by("created_at")
        records = list(query)
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
            inst_name = self._resolve_attribute_inst_name(
                instance_map, record.inst_id, before_data, after_data
            )
            change_details = []
            for field in matched:
                old_val = truncate_value(before_data.get(field))
                new_val = truncate_value(after_data.get(field))
                change_details.append(f"{field}: {old_val} → {new_val}")
            if not change_details:
                continue

            field_change_summary = "字段变化: " + "; ".join(change_details)
            if merge_mode == "single":
                self._merge_attribute_summary(
                    merged_event_map, record.inst_id, inst_name, field_change_summary
                )
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
        logger.info(
            "[Subscription] 属性变更检测完成 "
            f"rule_id={self.rule.id}, merge_mode={merge_mode}, events_count={len(events)}"
        )
        return events

    def _check_relation_change(
        self,
        current_snapshot: dict[str, Any],
        instances: list[dict[str, Any]],
        checkpoint: datetime,
    ) -> list[TriggerEvent]:
        # 关联变化关注两类事件：关联实例新增/删除，及已关联实例的属性变化。
        relation_config = self.rule.trigger_config.get("relation_change", {}) or {}
        related_model = relation_config.get("related_model", "")
        watch_fields = set(relation_config.get("fields", []) or [])
        if not related_model:
            logger.info(f"[Subscription] 未配置关联模型，跳过 rule_id={self.rule.id}")
            return []

        previous_relations = (self.rule.snapshot_data or {}).get("relations", {})
        current_relations = current_snapshot.get("relations", {})
        all_instance_ids = set(previous_relations.keys()) | set(
            current_relations.keys()
        )
        inst_name_map = {
            str(int(inst.get("_id"))): (
                inst.get("inst_name") or inst.get("ip_addr") or str(inst.get("_id"))
            )
            for inst in instances
            if inst.get("_id") is not None
        }
        now_str = timezone.now().isoformat()
        events: list[TriggerEvent] = []
        related_change_map, related_record_count = self._build_related_change_map(
            related_model=related_model,
            watch_fields=watch_fields,
            checkpoint=checkpoint,
        )
        related_inst_name_map = self._build_related_inst_name_map(
            related_model=related_model,
            previous_relations=previous_relations,
            current_relations=current_relations,
        )

        for inst_id_str in all_instance_ids:
            prev_related = set(
                (previous_relations.get(inst_id_str, {}) or {}).get(related_model, [])
            )
            curr_related = set(
                (current_relations.get(inst_id_str, {}) or {}).get(related_model, [])
            )
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
                related_inst_name = related_inst_name_map.get(
                    related_inst_id, str(related_inst_id)
                )
                changed_related_parts.append(
                    f"关联实例[{related_inst_name}]属性变化: {merged_summary}"
                )
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
            f"rule_id={self.rule.id}, related_model={related_model}, "
            f"instances_compared={len(all_instance_ids)}, related_record_count={related_record_count}, "
            f"watch_fields={sorted(list(watch_fields)) if watch_fields else []}, events_count={len(events)}"
        )
        return events

    def _check_expiration(
        self, instances: list[dict[str, Any]], current_snapshot: dict[str, Any]
    ) -> list[TriggerEvent]:
        # 到期提醒使用去重键避免同一实例在窗口内反复通知。
        config = self.rule.trigger_config.get("expiration", {})
        time_field = config.get("time_field")
        days_before = config.get("days_before")
        if not time_field or not isinstance(days_before, int) or days_before <= 0:
            logger.info(f"[Subscription] 到期配置无效，跳过 rule_id={self.rule.id}")
            return []

        previous_notified = set(
            (
                (self.rule.snapshot_data or {}).get("expiration_notified", {}) or {}
            ).keys()
        )
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
                inst_id = int(inst.get("_id"))
                dedup_key = f"{inst_id}:{time_field}:{expire_date.isoformat()}"
                current_notified[dedup_key] = now_str
                if dedup_key in previous_notified:
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

    def _update_snapshot(
        self, current_snapshot: dict[str, Any], checkpoint: datetime
    ) -> None:
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
        logger.info(
            "[Subscription] 快照更新完成 "
            f"rule_id={self.rule.id}, last_check_time={checkpoint.isoformat()}, "
            f"triggered={bool(self.events)}"
        )

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
