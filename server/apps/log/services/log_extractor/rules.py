from django.db import IntegrityError, transaction
from django.db.models import F
from rest_framework.exceptions import ValidationError

from apps.log.constants.victoriametrics import VictoriaLogsConstants
from apps.log.models import CollectInstance, LogExtractor
from apps.log.services.log_extractor.publication import mark_dirty
from apps.log.services.log_extractor.semantics import execute_rules, normalize_rule
from apps.log.services.search import SearchService

MAX_RULES_PER_INSTANCE = 20


def _actor_fields(user) -> dict:
    return {
        "created_by": getattr(user, "username", ""),
        "updated_by": getattr(user, "username", ""),
        "domain": getattr(user, "domain", "domain.com"),
        "updated_by_domain": getattr(user, "domain", "domain.com"),
    }


def _restore_runtime_event_shape(event: dict) -> dict:
    """把 VictoriaLogs 查询响应中的点号字段恢复成运行时嵌套 JSON。"""
    restored = {key: value for key, value in event.items() if "." not in key}
    for key, value in event.items():
        if "." not in key:
            continue
        segments = key.split(".")
        if not all(segments):
            restored[key] = value
            continue
        current = restored
        conflict = False
        for segment in segments[:-1]:
            existing = current.get(segment)
            if existing is None:
                existing = {}
                current[segment] = existing
            if not isinstance(existing, dict):
                conflict = True
                break
            current = existing
        if conflict or segments[-1] in current:
            restored[key] = value
        else:
            current[segments[-1]] = value
    return restored


def _restore_sample_payload(payload: object) -> object:
    if isinstance(payload, list):
        return [_restore_runtime_event_shape(item) if isinstance(item, dict) else item for item in payload]
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return {**payload, "data": _restore_sample_payload(payload["data"])}
    return payload


def create_rule(instance: CollectInstance, validated_data: dict, user) -> tuple[LogExtractor, int]:
    try:
        with transaction.atomic():
            locked_instance = CollectInstance.objects.select_for_update().get(pk=instance.pk)
            count = LogExtractor.objects.filter(collect_instance=locked_instance).count()
            if count >= MAX_RULES_PER_INSTANCE:
                raise ValidationError({"collect_instance": f"单个采集实例最多 {MAX_RULES_PER_INSTANCE} 条规则"})
            rule = LogExtractor.objects.create(
                **validated_data,
                collect_instance=locked_instance,
                sort_order=count,
                **_actor_fields(user),
            )
            generation = mark_dirty()
            return rule, generation
    except IntegrityError as exc:
        raise ValidationError({"name": "实例内名称或顺序重复"}) from exc


def update_rule(rule: LogExtractor, validated_data: dict, user) -> tuple[LogExtractor, int]:
    try:
        with transaction.atomic():
            locked = LogExtractor.objects.select_for_update().get(pk=rule.pk)
            validated_data.pop("collect_instance", None)
            for field, value in validated_data.items():
                setattr(locked, field, value)
            locked.updated_by = getattr(user, "username", "")
            locked.updated_by_domain = getattr(user, "domain", "domain.com")
            locked.save()
            generation = mark_dirty()
            return locked, generation
    except IntegrityError as exc:
        raise ValidationError({"name": "实例内名称重复"}) from exc


def delete_rule(rule: LogExtractor) -> int:
    with transaction.atomic():
        locked = LogExtractor.objects.select_for_update().get(pk=rule.pk)
        instance_id = locked.collect_instance_id
        order = locked.sort_order
        locked.delete()
        LogExtractor.objects.filter(collect_instance_id=instance_id, sort_order__gt=order).update(sort_order=F("sort_order") - 1)
        return mark_dirty()


def reorder_rules(instance: CollectInstance, ordered_ids: list[int]) -> int:
    if not isinstance(ordered_ids, list) or len(ordered_ids) != len(set(ordered_ids)):
        raise ValidationError({"ids": "必须提交无重复的完整规则 ID 列表"})
    with transaction.atomic():
        CollectInstance.objects.select_for_update().get(pk=instance.pk)
        rules = list(LogExtractor.objects.select_for_update().filter(collect_instance=instance).order_by("sort_order", "id"))
        rule_map = {rule.id: rule for rule in rules}
        if set(ordered_ids) != set(rule_map):
            raise ValidationError({"ids": "必须提交当前实例全部且仅全部规则 ID"})
        LogExtractor.objects.filter(collect_instance=instance).update(sort_order=F("sort_order") + 1000)
        for order, rule_id in enumerate(ordered_ids):
            rule_map[rule_id].sort_order = order
        LogExtractor.objects.bulk_update(rule_map.values(), ("sort_order",))
        return mark_dirty()


def preview_rule(instance: CollectInstance, event: dict, draft: dict, before_rule_id: int | None = None) -> dict:
    if not isinstance(event, dict):
        raise ValidationError({"event": "必须是日志事件对象"})
    normalized = normalize_rule(draft)
    saved = LogExtractor.objects.filter(collect_instance=instance).order_by("sort_order", "id")
    if before_rule_id is not None:
        target = saved.filter(pk=before_rule_id).first()
        if not target:
            raise ValidationError({"rule_id": "规则不属于当前实例"})
        saved = saved.filter(sort_order__lt=target.sort_order)
    rules = [
        normalize_rule(
            {
                "extractor_type": item.extractor_type,
                "source_field": item.source_field,
                "target_field": item.target_field,
                "condition": item.condition,
                "config": item.config,
                "delete_source": item.delete_source,
            }
        )
        for item in saved
    ]
    rules.append(normalized)
    safe_event = dict(event)
    safe_event["instance_id"] = instance.pk
    result = execute_rules(safe_event, rules)
    return {
        "event": result.event,
        "results": [{"status": item.status, "error": item.error} for item in result.results],
    }


def load_samples(instance: CollectInstance, limit) -> object:
    normalized_limit = VictoriaLogsConstants.normalize_query_limit(limit, default=10)
    escaped_id = str(instance.pk).replace("\\", "\\\\").replace('"', '\\"')
    payload = SearchService.search_logs(
        f'instance_id:"{escaped_id}"', "", "", normalized_limit, log_groups=[], resolved_groups=[]
    )
    return _restore_sample_payload(payload)
