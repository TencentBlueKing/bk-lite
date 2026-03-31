import json
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import cmdb_logger as logger

UniqueDisplayType = Literal["none", "single", "joint"]

UNIQUE_RULE_MAX_COUNT = 3
UNIQUE_RULE_UNSUPPORTED_ATTR_TYPES = {"enum", "tag", "bool"}
UNIQUE_RULE_UNSUPPORTED_FIELD_IDS = {"inst_name", "organization"}


@dataclass(slots=True, frozen=True)
class ModelUniqueRule:
    """
    模型级唯一规则持久化结构。
    存储位置：model.unique_rules（JSON string）
    约束：
    1. rule_id 使用 uuid.uuid4().hex 生成
    2. order 为 1-based 连续整数，由服务端重排
    3. field_ids 长度 >= 1
    4. field_ids 内元素不可重复
    """

    rule_id: str
    order: int
    field_ids: list[str]


@dataclass(slots=True, frozen=True)
class UniqueRulePayload:
    """
    前端提交的规则载荷。
    创建和编辑都只允许传 field_ids。
    rule_id 和 order 由服务端生成或维护。
    """

    field_ids: list[str]


@dataclass(slots=True, frozen=True)
class UniqueRuleFieldMeta:
    """
    可参与唯一规则的字段元数据。
    disabled_reason 仅用于前端候选展示。
    """

    attr_id: str
    attr_name: str
    attr_type: str
    is_required: bool
    selectable: bool
    disabled_reason: str = ""


@dataclass(slots=True, frozen=True)
class UniqueRuleConflict:
    """
    唯一规则冲突结果。
    用于规则保存校验、实例写入校验、导入校验。
    """

    rule_id: str
    rule_order: int
    field_ids: list[str]
    field_names: list[str]
    field_values: dict[str, Any]
    exist_instance_ids: list[int]
    exist_instance_names: list[str]
    message: str


@dataclass(slots=True)
class UniqueRuleCheckContext:
    """
    唯一规则检查上下文。
    - attrs_by_id: 当前模型字段定义映射
    - unique_rules: 额外唯一规则
    - builtin_unique_fields: 必含 inst_name
    - legacy_unique_fields: 历史 is_only 字段集合
    """

    model_id: str
    attrs_by_id: dict[str, dict[str, Any]]
    unique_rules: list[ModelUniqueRule] = field(default_factory=list)
    builtin_unique_fields: set[str] = field(default_factory=set)
    legacy_unique_fields: set[str] = field(default_factory=set)


@dataclass(slots=True, frozen=True)
class AttrUniqueDisplay:
    """
    字段唯一性只读展示结构。
    返回给属性列表接口。
    """

    attr_id: str
    is_only: bool
    unique_display_type: UniqueDisplayType


def _deduplicate_field_ids(field_ids: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for field_id in field_ids:
        normalized = str(field_id or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _normalize_rule_field_ids(field_ids: list[str]) -> list[str]:
    return _deduplicate_field_ids(list(field_ids or []))


def _normalize_compare_value(value: Any) -> str:
    if isinstance(value, (dict, list, tuple, set)):
        try:
            normalized = list(value) if isinstance(value, set) else value
            return json.dumps(normalized, ensure_ascii=False, sort_keys=True)
        except TypeError:
            return str(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _format_value_for_message(value: Any) -> str:
    if isinstance(value, (dict, list, tuple, set)):
        normalized = list(value) if isinstance(value, set) else value
        return json.dumps(normalized, ensure_ascii=False, sort_keys=True)
    return str(value)


def _is_empty_unique_rule_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def _build_rule_signature(item: dict[str, Any], field_ids: list[str]) -> tuple[str, ...] | None:
    values = [item.get(field_id) for field_id in field_ids]
    if any(_is_empty_unique_rule_value(value) for value in values):
        return None
    return tuple(_normalize_compare_value(item.get(field_id)) for field_id in field_ids)


def _get_attr_name(attrs_by_id: dict[str, dict[str, Any]], field_id: str) -> str:
    return str(attrs_by_id.get(field_id, {}).get("attr_name") or field_id)


def _collect_occupied_field_ids(rules: list[ModelUniqueRule], editing_rule_id: str | None = None) -> set[str]:
    occupied_field_ids: set[str] = set()
    for rule in rules:
        if rule.rule_id == editing_rule_id:
            continue
        occupied_field_ids.update(rule.field_ids)
    return occupied_field_ids


def _build_conflict(
    rule: ModelUniqueRule,
    attrs_by_id: dict[str, dict[str, Any]],
    item: dict[str, Any],
    matched_items: list[dict[str, Any]],
    conflict_prefix: str = "与现有实例冲突",
) -> UniqueRuleConflict:
    field_names = [_get_attr_name(attrs_by_id, field_id) for field_id in rule.field_ids]
    field_values = {field_id: item.get(field_id) for field_id in rule.field_ids}
    value_summary = "，".join(
        f"{field_name}={_format_value_for_message(item.get(field_id))}" for field_id, field_name in zip(rule.field_ids, field_names)
    )
    message = f"规则 {rule.order}【{' + '.join(field_names)}】{conflict_prefix}：{value_summary}"
    exist_instance_ids = [int(match.get("_id")) for match in matched_items if match.get("_id") is not None]
    exist_instance_names = [
        str(match.get("inst_name") or match.get("_id")) for match in matched_items if match.get("_id") is not None or match.get("inst_name")
    ]
    return UniqueRuleConflict(
        rule_id=rule.rule_id,
        rule_order=rule.order,
        field_ids=list(rule.field_ids),
        field_names=field_names,
        field_values=field_values,
        exist_instance_ids=exist_instance_ids,
        exist_instance_names=exist_instance_names,
        message=message,
    )


def collect_unique_rule_conflicts(
    rules: list[ModelUniqueRule],
    items: list[dict[str, Any]],
    exist_items: list[dict[str, Any]],
    attrs_by_id: dict[str, dict[str, Any]],
    exclude_instance_ids: set[int] | None = None,
) -> list[UniqueRuleConflict]:
    conflicts: list[UniqueRuleConflict] = []
    excluded_ids = exclude_instance_ids or set()
    filtered_exist_items = [item for item in exist_items if int(item.get("_id", -1)) not in excluded_ids]

    for rule in rules:
        exist_map: dict[tuple[str, ...], list[dict[str, Any]]] = {}
        for exist_item in filtered_exist_items:
            signature = _build_rule_signature(exist_item, rule.field_ids)
            if signature is None:
                continue
            exist_map.setdefault(signature, []).append(exist_item)

        batch_map: dict[tuple[str, ...], list[dict[str, Any]]] = {}
        for item in items:
            signature = _build_rule_signature(item, rule.field_ids)
            if signature is None:
                continue
            matched_exist_items = exist_map.get(signature, [])
            if matched_exist_items:
                conflicts.append(_build_conflict(rule, attrs_by_id, item, matched_exist_items))
                continue

            matched_batch_items = batch_map.get(signature, [])
            if matched_batch_items:
                conflicts.append(
                    _build_conflict(
                        rule,
                        attrs_by_id,
                        item,
                        matched_batch_items,
                        conflict_prefix="与本批次数据冲突",
                    )
                )
                continue

            batch_map.setdefault(signature, []).append(item)

    return conflicts


def raise_unique_rule_conflict_if_needed(
    unique_rules: str | list[dict[str, Any]] | list[ModelUniqueRule] | None,
    items: list[dict[str, Any]],
    exist_items: list[dict[str, Any]],
    attrs_by_id: dict[str, dict[str, Any]],
    exclude_instance_ids: set[int] | None = None,
) -> None:
    conflicts = collect_unique_rule_conflicts(
        rules=parse_unique_rules(unique_rules),
        items=items,
        exist_items=exist_items,
        attrs_by_id=attrs_by_id,
        exclude_instance_ids=exclude_instance_ids,
    )
    if conflicts:
        raise BaseAppException(conflicts[0].message)


def parse_unique_rules(raw: str | list[dict[str, Any]] | None) -> list[ModelUniqueRule]:
    """
    解析 model.unique_rules，返回规范化规则列表。

    Args:
        raw: 模型实体上的 unique_rules 原始值，支持 JSON 字符串、对象列表或 None。

    Returns:
        规则对象列表，已完成字段去重与顺序规范化。

    Failure Conditions:
        原始数据格式非法时不会抛异常，而是记录日志并回退为空列表，保证旧数据兼容读取。
    """

    if raw in (None, "", []):
        return []

    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, json.JSONDecodeError):
        logger.warning("[UniqueRule] parse_unique_rules failed, raw=%s", raw)
        return []

    if not isinstance(data, list):
        return []

    rules: list[ModelUniqueRule] = []
    for index, item in enumerate(data, start=1):
        if isinstance(item, ModelUniqueRule):
            field_ids = _normalize_rule_field_ids(item.field_ids)
            if not field_ids:
                continue
            rules.append(
                ModelUniqueRule(
                    rule_id=str(item.rule_id or uuid.uuid4().hex),
                    order=int(item.order or index),
                    field_ids=field_ids,
                )
            )
            continue

        if not isinstance(item, dict):
            continue

        field_ids = _normalize_rule_field_ids(item.get("field_ids") or [])
        if not field_ids:
            continue
        try:
            order = int(item.get("order") or index)
        except (TypeError, ValueError):
            order = index
        rules.append(
            ModelUniqueRule(
                rule_id=str(item.get("rule_id") or uuid.uuid4().hex),
                order=order,
                field_ids=field_ids,
            )
        )

    rules.sort(key=lambda rule: (rule.order, rule.rule_id))
    return reorder_unique_rules(rules)


def dump_unique_rules(rules: list[ModelUniqueRule]) -> str:
    """
    将规则列表序列化为 JSON string，ensure_ascii=False。

    Args:
        rules: 规则对象列表。

    Returns:
        适合持久化到 model.unique_rules 的 JSON 字符串。

    Failure Conditions:
        无显式失败条件；若传入非 dataclass 内容，json 序列化会抛出异常。
    """

    return json.dumps([asdict(rule) for rule in reorder_unique_rules(rules)], ensure_ascii=False)


def reorder_unique_rules(rules: list[ModelUniqueRule]) -> list[ModelUniqueRule]:
    """
    按当前顺序重排 order，确保为 1-based 连续整数。

    Args:
        rules: 原始规则列表。

    Returns:
        重排后的新规则列表。

    Failure Conditions:
        无显式失败条件；空列表直接返回空列表。
    """

    return [ModelUniqueRule(rule_id=rule.rule_id, order=index, field_ids=list(rule.field_ids)) for index, rule in enumerate(rules, start=1)]


def build_unique_rule_context(model_id: str) -> UniqueRuleCheckContext:
    """
    加载模型字段、inst_name、历史 is_only、extra unique_rules，构建统一检查上下文。

    Args:
        model_id: 模型 ID。

    Returns:
        当前模型的唯一规则检查上下文。

    Failure Conditions:
        模型不存在时抛出 BaseAppException。
    """

    from apps.cmdb.services.model import ModelManage

    model_info = ModelManage.search_model_info(model_id)
    if not model_info:
        raise BaseAppException("模型不存在")

    attrs = ModelManage.parse_attrs(model_info.get("attrs", "[]"))
    attrs_by_id = {attr.get("attr_id"): attr for attr in attrs if isinstance(attr, dict) and attr.get("attr_id") and not attr.get("is_display_field")}
    legacy_unique_fields = {attr_id for attr_id, attr in attrs_by_id.items() if attr.get("is_only") and attr_id != "inst_name"}

    return UniqueRuleCheckContext(
        model_id=model_id,
        attrs_by_id=attrs_by_id,
        unique_rules=parse_unique_rules(model_info.get("unique_rules", "[]")),
        builtin_unique_fields={"inst_name"},
        legacy_unique_fields=legacy_unique_fields,
    )


def list_unique_rules(model_id: str) -> list[dict[str, Any]]:
    """
    返回规则列表，包含 field_names。

    Args:
        model_id: 模型 ID。

    Returns:
        前端可直接展示的规则列表。

    Failure Conditions:
        模型不存在时抛出 BaseAppException。
    """

    ctx = build_unique_rule_context(model_id)
    return [
        {
            "rule_id": rule.rule_id,
            "order": rule.order,
            "field_ids": list(rule.field_ids),
            "field_names": [_get_attr_name(ctx.attrs_by_id, field_id) for field_id in rule.field_ids],
        }
        for rule in ctx.unique_rules
    ]


def list_unique_rule_candidate_fields(model_id: str, editing_rule_id: str | None = None) -> list[UniqueRuleFieldMeta]:
    """
    返回前端候选字段列表，已包含 selectable 与 disabled_reason。

    Args:
        model_id: 模型 ID。
        editing_rule_id: 编辑场景下的规则 ID，用于放开本规则已占用字段。

    Returns:
        候选字段元数据列表。

    Failure Conditions:
        模型不存在时抛出 BaseAppException。
    """

    ctx = build_unique_rule_context(model_id)
    occupied_field_ids = _collect_occupied_field_ids(ctx.unique_rules, editing_rule_id)

    candidates: list[UniqueRuleFieldMeta] = []
    for attr_id, attr in ctx.attrs_by_id.items():
        attr_type = str(attr.get("attr_type") or "")
        selectable, disabled_reason = _evaluate_field_selectability(attr_id, attr, attr_type, occupied_field_ids)

        candidates.append(
            UniqueRuleFieldMeta(
                attr_id=attr_id,
                attr_name=str(attr.get("attr_name") or attr_id),
                attr_type=attr_type,
                is_required=bool(attr.get("is_required")),
                selectable=selectable,
                disabled_reason=disabled_reason,
            )
        )

    return candidates


def _evaluate_field_selectability(
    attr_id: str,
    attr: dict[str, Any],
    attr_type: str,
    occupied_field_ids: set[str],
) -> tuple[bool, str]:
    if attr_id == "inst_name":
        return False, "inst_name 为内置唯一字段，不支持加入额外唯一规则"
    if attr_id == "organization":
        return False, "组织字段不支持加入额外唯一规则"
    if attr.get("is_display_field"):
        return False, "冗余展示字段不可加入唯一规则"
    if not attr.get("is_required"):
        return False, "仅必填字段可加入唯一规则"
    if attr_type in UNIQUE_RULE_UNSUPPORTED_ATTR_TYPES:
        return False, "枚举、标签、布尔字段不可加入唯一规则"
    if attr_id in occupied_field_ids:
        return False, "该字段已被其他唯一规则使用"
    return True, ""


def validate_unique_rule_payload(
    ctx: UniqueRuleCheckContext,
    payload: UniqueRulePayload,
    editing_rule_id: str | None = None,
) -> None:
    """
    校验条数、字段重复、字段存在、字段必填、字段类型是否合法。

    Args:
        ctx: 唯一规则上下文。
        payload: 当前提交的字段列表。
        editing_rule_id: 编辑场景的 rule_id；用于跳过当前规则自身占用字段检查。

    Returns:
        无返回，校验通过即结束。

    Failure Conditions:
        规则数量超限、字段重复、字段不存在、字段非法或字段被其他规则占用时抛出 BaseAppException。
    """

    field_ids = _normalize_rule_field_ids(payload.field_ids)
    if not field_ids:
        raise BaseAppException("field_ids 不能为空")
    if len(field_ids) != len(list(payload.field_ids or [])):
        raise BaseAppException("field_ids 内存在重复字段")

    if editing_rule_id is None and len(ctx.unique_rules) >= UNIQUE_RULE_MAX_COUNT:
        raise BaseAppException(f"每个模型最多只能配置 {UNIQUE_RULE_MAX_COUNT} 条额外唯一规则")

    occupied_field_ids = _collect_occupied_field_ids(ctx.unique_rules, editing_rule_id)

    for field_id in field_ids:
        attr = ctx.attrs_by_id.get(field_id)
        if not attr:
            raise BaseAppException(f"字段 {field_id} 不存在于当前模型")
        if field_id == "inst_name":
            raise BaseAppException("额外唯一规则不允许包含 inst_name")
        if field_id == "organization":
            raise BaseAppException("额外唯一规则不允许包含 organization")
        if not attr.get("is_required"):
            raise BaseAppException(f"字段 {_get_attr_name(ctx.attrs_by_id, field_id)} 不是必填字段")
        if str(attr.get("attr_type") or "") in UNIQUE_RULE_UNSUPPORTED_ATTR_TYPES:
            raise BaseAppException(f"字段 {_get_attr_name(ctx.attrs_by_id, field_id)} 的类型不支持加入唯一规则")
        if field_id in occupied_field_ids:
            raise BaseAppException(f"字段 {_get_attr_name(ctx.attrs_by_id, field_id)} 已被其他唯一规则使用")


def validate_unique_rules_against_existing_instances(
    model_id: str,
    rules: list[ModelUniqueRule],
    exist_items: list[dict[str, Any]],
) -> list[UniqueRuleConflict]:
    """
    校验规则与历史实例是否冲突。

    Args:
        model_id: 模型 ID。
        rules: 待保存规则列表。
        exist_items: 当前模型历史实例。

    Returns:
        冲突列表；为空表示通过。

    Failure Conditions:
        无显式失败条件；模型不存在时由 build_unique_rule_context 抛出 BaseAppException。
    """

    ctx = build_unique_rule_context(model_id)
    return _collect_existing_instance_conflicts(rules, exist_items, ctx.attrs_by_id)


def _collect_existing_instance_conflicts(
    rules: list[ModelUniqueRule],
    exist_items: list[dict[str, Any]],
    attrs_by_id: dict[str, dict[str, Any]],
) -> list[UniqueRuleConflict]:
    conflicts: list[UniqueRuleConflict] = []

    for rule in rules:
        signature_map: dict[tuple[str, ...], list[dict[str, Any]]] = {}
        for exist_item in exist_items:
            signature = _build_rule_signature(exist_item, rule.field_ids)
            if signature is None:
                continue
            matched_items = signature_map.get(signature, [])
            if matched_items:
                conflicts.append(_build_conflict(rule, attrs_by_id, exist_item, matched_items, conflict_prefix="与现有实例冲突"))
                continue
            signature_map.setdefault(signature, []).append(exist_item)

    return conflicts


def _save_unique_rules(model_id: str, rules: list[ModelUniqueRule]) -> None:
    from apps.cmdb.constants.constants import MODEL
    from apps.cmdb.graph.drivers.graph_client import GraphClient
    from apps.cmdb.services.model import ModelManage

    model_info = ModelManage.search_model_info(model_id)
    if not model_info:
        raise BaseAppException("模型不存在")

    with GraphClient() as ag:
        ag.set_entity_properties(
            MODEL,
            [model_info["_id"]],
            {"unique_rules": dump_unique_rules(rules)},
            {},
            [],
            False,
        )


def _query_model_instances(model_id: str) -> list[dict[str, Any]]:
    from apps.cmdb.constants.constants import INSTANCE
    from apps.cmdb.graph.drivers.graph_client import GraphClient

    with GraphClient() as ag:
        exist_items, _ = ag.query_entity(INSTANCE, [{"field": "model_id", "type": "str=", "value": model_id}])
    return exist_items


def _log_invalid_unique_rule_payload(model_id: str, operator: str, field_ids: list[str], reason: str) -> None:
    logger.warning(
        "[UniqueRule] invalid payload model_id=%s operator=%s field_ids=%s reason=%s",
        model_id,
        operator,
        field_ids,
        reason,
    )


def _raise_conflict_if_rules_invalid(model_id: str, operator: str, action: str, rules: list[ModelUniqueRule]) -> None:
    conflicts = validate_unique_rules_against_existing_instances(model_id, rules, _query_model_instances(model_id))
    if not conflicts:
        return

    conflict = conflicts[0]
    logger.warning(
        "[UniqueRule] %s blocked by conflict model_id=%s operator=%s rule_id=%s order=%s field_ids=%s conflict_instance_ids=%s",
        action,
        model_id,
        operator,
        conflict.rule_id,
        conflict.rule_order,
        conflict.field_ids,
        conflict.exist_instance_ids,
    )
    raise BaseAppException(conflict.message)


def _apply_unique_rule_mutation(
    model_id: str,
    operator: str,
    action: str,
    field_ids: list[str],
    mutate,
    validate=None,
) -> list[dict[str, Any]]:
    logger.info("[UniqueRule] %s start model_id=%s operator=%s field_ids=%s", action, model_id, operator, field_ids)
    ctx = build_unique_rule_context(model_id)

    if validate:
        try:
            validate(ctx)
        except BaseAppException as err:
            _log_invalid_unique_rule_payload(model_id, operator, field_ids, err.message)
            raise

    next_rules = mutate(ctx)
    _raise_conflict_if_rules_invalid(model_id, operator, action, next_rules)
    _save_unique_rules(model_id, next_rules)
    return list_unique_rules(model_id)


def create_unique_rule(model_id: str, payload: UniqueRulePayload, operator: str) -> list[dict[str, Any]]:
    """
    创建规则；成功后返回最新规则列表。

    Args:
        model_id: 模型 ID。
        payload: 前端提交字段列表。
        operator: 操作人。

    Returns:
        最新规则列表。

    Failure Conditions:
        参数非法、规则数量超限、字段不合法或历史实例冲突时抛出 BaseAppException。
    """

    return _apply_unique_rule_mutation(
        model_id=model_id,
        operator=operator,
        action="create",
        field_ids=list(payload.field_ids),
        mutate=lambda ctx: reorder_unique_rules(
            [
                *ctx.unique_rules,
                ModelUniqueRule(rule_id=uuid.uuid4().hex, order=len(ctx.unique_rules) + 1, field_ids=list(payload.field_ids)),
            ]
        ),
        validate=lambda ctx: validate_unique_rule_payload(ctx, payload),
    )


def update_unique_rule(model_id: str, rule_id: str, payload: UniqueRulePayload, operator: str) -> list[dict[str, Any]]:
    """
    更新规则；成功后返回最新规则列表。

    Args:
        model_id: 模型 ID。
        rule_id: 待更新规则 ID。
        payload: 前端提交字段列表。
        operator: 操作人。

    Returns:
        最新规则列表。

    Failure Conditions:
        规则不存在、参数非法或历史实例冲突时抛出 BaseAppException。
    """

    def _validate(ctx: UniqueRuleCheckContext) -> None:
        if not next((rule for rule in ctx.unique_rules if rule.rule_id == rule_id), None):
            raise BaseAppException("唯一规则不存在")
        validate_unique_rule_payload(ctx, payload, editing_rule_id=rule_id)

    return _apply_unique_rule_mutation(
        model_id=model_id,
        operator=operator,
        action="update",
        field_ids=list(payload.field_ids),
        mutate=lambda ctx: reorder_unique_rules(
            [
                ModelUniqueRule(rule_id=rule.rule_id, order=rule.order, field_ids=list(payload.field_ids)) if rule.rule_id == rule_id else rule
                for rule in ctx.unique_rules
            ]
        ),
        validate=_validate,
    )


def delete_unique_rule(model_id: str, rule_id: str, operator: str) -> list[dict[str, Any]]:
    """
    删除规则；成功后返回最新规则列表。

    Args:
        model_id: 模型 ID。
        rule_id: 待删除规则 ID。
        operator: 操作人。

    Returns:
        最新规则列表。

    Failure Conditions:
        规则不存在时抛出 BaseAppException。
    """

    def _build_next_rules(ctx: UniqueRuleCheckContext) -> list[ModelUniqueRule]:
        next_rules = [rule for rule in ctx.unique_rules if rule.rule_id != rule_id]
        if len(next_rules) == len(ctx.unique_rules):
            raise BaseAppException("唯一规则不存在")
        return reorder_unique_rules(next_rules)

    return _apply_unique_rule_mutation(
        model_id=model_id,
        operator=operator,
        action="delete",
        field_ids=[],
        mutate=_build_next_rules,
    )


def guard_attr_change_against_unique_rules(
    model_id: str,
    target_attr_id: str,
    next_attr: dict[str, Any] | None,
    operation: Literal["delete", "update_required", "update_type"],
    operator: str = "system",
) -> None:
    """
    字段删除/改必填/改类型前，阻止破坏已配置规则。

    Args:
        model_id: 模型 ID。
        target_attr_id: 待变更字段 ID。
        next_attr: 变更后的字段定义；删除场景可为 None。
        operation: 变更类型。
        operator: 操作人，仅用于日志。

    Returns:
        无返回；校验通过即放行。

    Failure Conditions:
        字段已被规则引用且本次变更会破坏规则合法性时抛出 BaseAppException。
    """

    ctx = build_unique_rule_context(model_id)
    matched_rules = [rule for rule in ctx.unique_rules if target_attr_id in rule.field_ids]
    if not matched_rules:
        return

    should_block = False
    if operation == "delete":
        should_block = True
        message = "字段已被唯一规则使用，请先删除相关唯一规则"
    elif operation == "update_required":
        should_block = bool(next_attr and not next_attr.get("is_required"))
        message = "字段已被唯一规则使用，不能取消必填"
    else:
        should_block = bool(next_attr and str(next_attr.get("attr_type") or "") in UNIQUE_RULE_UNSUPPORTED_ATTR_TYPES)
        message = "字段已被唯一规则使用，不能修改为 enum、tag、bool 类型"

    if not should_block:
        return

    logger.warning(
        "[UniqueRule] attr change blocked model_id=%s operator=%s attr_id=%s operation=%s rule_ids=%s",
        model_id,
        operator,
        target_attr_id,
        operation,
        [rule.rule_id for rule in matched_rules],
    )
    raise BaseAppException(message)


def enrich_attrs_with_unique_display(
    attrs: list[dict[str, Any]],
    unique_rules: list[ModelUniqueRule],
    model_id: str = "",
) -> list[dict[str, Any]]:
    """
    为属性列表增加 unique_display_type。

    Args:
        attrs: 原始属性列表。
        unique_rules: 当前模型的额外唯一规则列表。
        model_id: 模型 ID，仅用于日志。

    Returns:
        已补充 unique_display_type 的属性列表。

    Failure Conditions:
        无显式失败条件；仅做只读展示增强，不修改 is_only 原始语义。
    """

    joint_field_ids = {field_id for rule in unique_rules if len(rule.field_ids) > 1 for field_id in rule.field_ids}
    single_field_ids = {field_id for rule in unique_rules if len(rule.field_ids) == 1 for field_id in rule.field_ids}
    result: list[dict[str, Any]] = []

    # is_only 与 unique_display_type 并存：前者保留后端兼容语义，后者仅用于前端只读展示。
    for attr in attrs:
        attr_id = attr.get("attr_id")
        unique_display_type: UniqueDisplayType = "none"
        if attr_id in joint_field_ids:
            unique_display_type = "joint"
        elif attr.get("is_only") or attr_id in single_field_ids:
            unique_display_type = "single"
        result.append({**attr, "unique_display_type": unique_display_type})

    if model_id:
        logger.debug(
            "[UniqueRule] enrich unique display model_id=%s attr_count=%s single_count=%s joint_count=%s",
            model_id,
            len(result),
            len([item for item in result if item.get("unique_display_type") == "single"]),
            len([item for item in result if item.get("unique_display_type") == "joint"]),
        )
    return result


def copy_unique_rules_to_model(src_model_id: str, dst_model_id: str, operator: str) -> list[ModelUniqueRule]:
    """
    复制模型属性时复制 unique_rules，并对目标模型重新做合法性校验。

    Args:
        src_model_id: 源模型 ID。
        dst_model_id: 目标模型 ID。
        operator: 操作人。

    Returns:
        已复制并落库的规则列表。

    Failure Conditions:
        目标模型字段集不满足规则合法性时抛出 BaseAppException。
    """

    src_ctx = build_unique_rule_context(src_model_id)
    if not src_ctx.unique_rules:
        _save_unique_rules(dst_model_id, [])
        return []

    dst_ctx = build_unique_rule_context(dst_model_id)
    copied_rules: list[ModelUniqueRule] = []
    temp_ctx = UniqueRuleCheckContext(
        model_id=dst_model_id,
        attrs_by_id=dst_ctx.attrs_by_id,
        unique_rules=[],
        builtin_unique_fields=dst_ctx.builtin_unique_fields,
        legacy_unique_fields=dst_ctx.legacy_unique_fields,
    )
    for rule in src_ctx.unique_rules:
        payload = UniqueRulePayload(field_ids=list(rule.field_ids))
        validate_unique_rule_payload(temp_ctx, payload)
        next_rule = ModelUniqueRule(rule_id=uuid.uuid4().hex, order=len(copied_rules) + 1, field_ids=list(rule.field_ids))
        copied_rules.append(next_rule)
        temp_ctx.unique_rules = list(copied_rules)

    _save_unique_rules(dst_model_id, copied_rules)
    logger.info(
        "[UniqueRule] copy success src_model_id=%s dst_model_id=%s operator=%s copied_rule_count=%s",
        src_model_id,
        dst_model_id,
        operator,
        len(copied_rules),
    )
    return copied_rules


def apply_unique_rules_to_attr_export_rows(
    attr_rows: list[dict[str, Any]],
    rules: list[ModelUniqueRule],
) -> list[dict[str, Any]]:
    """
    为 attr-{model_id} 导出行补充 unique_rule_order 列。

    Args:
        attr_rows: 属性导出行。
        rules: 当前模型唯一规则。

    Returns:
        已补充 unique_rule_order 的属性行列表。

    Failure Conditions:
        无显式失败条件；未参与规则的字段写空值。
    """

    attr_rule_map = {field_id: rule.order for rule in rules for field_id in rule.field_ids}
    return [
        {
            **row,
            "unique_rule_order": attr_rule_map.get(row.get("attr_id"), ""),
        }
        for row in attr_rows
    ]


def build_unique_rules_from_attr_rows(model_id: str, rows: list[dict[str, Any]]) -> list[ModelUniqueRule]:
    """
    从 attr-{model_id} sheet 的 unique_rule_order 列重建规则列表。

    Args:
        model_id: 模型 ID。
        rows: 属性 sheet 行列表。

    Returns:
        重建后的规则对象列表。

    Failure Conditions:
        unique_rule_order 非法、分组超限或字段不满足规则约束时抛出 BaseAppException。
    """

    grouped_field_ids: dict[int, list[str]] = {}
    for row in rows:
        raw_order = row.get("unique_rule_order", "")
        if raw_order in (None, ""):
            continue
        try:
            order = int(raw_order)
        except (TypeError, ValueError):
            raise BaseAppException(f"模型 {model_id} 的 unique_rule_order 必须是正整数")
        if order <= 0:
            raise BaseAppException(f"模型 {model_id} 的 unique_rule_order 必须是正整数")
        field_id = str(row.get("attr_id") or "").strip()
        if not field_id:
            continue
        grouped_field_ids.setdefault(order, []).append(field_id)

    if len(grouped_field_ids) > UNIQUE_RULE_MAX_COUNT:
        raise BaseAppException(f"每个模型最多只能配置 {UNIQUE_RULE_MAX_COUNT} 条额外唯一规则")

    ctx = build_unique_rule_context(model_id)
    generated_rules: list[ModelUniqueRule] = []
    temp_ctx = UniqueRuleCheckContext(
        model_id=model_id,
        attrs_by_id=ctx.attrs_by_id,
        unique_rules=[],
        builtin_unique_fields=ctx.builtin_unique_fields,
        legacy_unique_fields=ctx.legacy_unique_fields,
    )
    for order in sorted(grouped_field_ids):
        field_ids = _deduplicate_field_ids(grouped_field_ids[order])
        payload = UniqueRulePayload(field_ids=field_ids)
        validate_unique_rule_payload(temp_ctx, payload)
        generated_rules.append(ModelUniqueRule(rule_id=uuid.uuid4().hex, order=len(generated_rules) + 1, field_ids=field_ids))
        temp_ctx.unique_rules = list(generated_rules)

    return reorder_unique_rules(generated_rules)
