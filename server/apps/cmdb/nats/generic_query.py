"""CMDB 通用查询 NATS handler。过滤、统计、排序和分页在 CMDB 内完成。"""

import nats_client
from apps.cmdb.nats.nats import _build_nats_model_permission_map, _build_nats_permission_map, _resolve_nats_cmdb_language
from apps.cmdb.services.asset_overview_query import list_model_association_options
from apps.cmdb.services.classification import ClassificationManage
from apps.cmdb.services.generic_query import (
    GenericQueryError,
    ensure_payload_limit,
    one_hop_query_plan,
    query_instance_value,
    query_instances,
    query_model_counts,
    query_models,
    query_one_hop_relations,
)
from apps.cmdb.services.generic_query_graph import GenericQueryGraphError, count_by_attr, query_one_hop
from apps.cmdb.services.model import ModelManage
from apps.cmdb.validators.field_validator import encode_collected_tag
from apps.core.logger import cmdb_logger as logger


def _ok(data) -> dict:
    ensure_payload_limit(data)
    return {"result": True, "data": data, "message": ""}


def _fail(message: str, status: str = "failed") -> dict:
    return {"result": False, "data": {"status": status}, "message": message}


def _guard(stage: str):
    def decorate(func):
        def wrapped(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except GenericQueryError as exc:
                return _fail(exc.message, exc.status)
            except GenericQueryGraphError as exc:
                return _fail(exc.message, "failed")
            except Exception as exc:
                logger.exception(
                    "event=cmdb_generic_query_failed failed_stage=%s error_type=%s",
                    stage,
                    type(exc).__name__,
                )
                return _fail("查询失败", "failed")

        wrapped.__name__ = func.__name__
        return wrapped

    return decorate


def _require_model_classification(models, model_id, classification_id) -> None:
    """分类只核对所选模型是否属于该类，不代替模型可见性。"""
    if classification_id in (None, ""):
        return
    row = next((item for item in models if str(item.get("model_id")) == str(model_id)), None)
    if row is None:
        return
    if str(row.get("classification_id") or "") != str(classification_id):
        raise GenericQueryError("模型不属于所选分类")


def _require_condition_group(filters):
    if filters in (None, "", []):
        return None
    if isinstance(filters, (list, dict)):
        return filters
    raise GenericQueryError("条件过滤格式错误")


def _tag_filter_options(attr: dict) -> list[dict]:
    config = ModelManage.normalize_tag_field_option(attr.get("option"))
    options = []
    for item in config.get("options") or []:
        key = str(item.get("key") or "").strip()
        if not key:
            continue
        raw_value = str(item.get("value") or "").strip()
        encoded = encode_collected_tag(key, raw_value)
        if not encoded:
            continue
        label = f"{key}:{raw_value}" if raw_value else f"{key}:"
        options.append({"value": encoded, "label": label})
    return options


def _attr_option(attr: dict) -> dict:
    raw_type = str(attr.get("attr_type") or "string").lower()
    if raw_type == "tag":
        value_type = "tag"
    elif raw_type == "enum":
        value_type = "enum"
    elif raw_type in {"int", "integer", "float", "number", "long", "double"}:
        value_type = "number"
    else:
        value_type = "string"
    options = _tag_filter_options(attr) if value_type == "tag" else []
    if value_type == "enum":
        for option in ModelManage.resolve_runtime_enum_options(attr) or []:
            if not isinstance(option, dict):
                continue
            option_id = option.get("id")
            if option_id in (None, ""):
                continue
            options.append({"value": option_id, "label": option.get("name") or option.get("label") or option_id})
    return {
        "attr_id": attr.get("attr_id"),
        "attr_name": attr.get("attr_name") or attr.get("attr_id"),
        "attr_type": attr.get("attr_type") or "string",
        "value_type": value_type,
        "options": options,
    }


def _text_list(value) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    raise GenericQueryError("列表参数格式错误")


def _visible_models(user_info):
    language = _resolve_nats_cmdb_language(user_info)
    model_permissions = _build_nats_model_permission_map(user_info)
    instance_permissions = _build_nats_permission_map(user_info)
    if model_permissions is None or instance_permissions is None:
        raise GenericQueryError("无权限", status="forbidden")
    models = ModelManage.search_model(language=language, permissions_map=model_permissions) or []
    classifications = ClassificationManage.search_model_classification(language=language) or []
    names = {str(item.get("classification_id")): item.get("classification_name") or "" for item in classifications if item.get("classification_id")}
    visible = []
    for model in models:
        row = dict(model)
        row["classification_name"] = names.get(str(row.get("classification_id") or ""), "")
        visible.append(row)
    return visible, instance_permissions, names


def _load_model_attrs(model_id: str, user_info) -> list:
    language = _resolve_nats_cmdb_language(user_info)
    try:
        return list(ModelManage.search_model_attr(model_id, language=language) or [])
    except Exception as exc:
        raise GenericQueryError("指定模型不存在或无权访问", status="forbidden") from exc


def _enum_group_labels(attrs: list, group_by) -> dict[str, str] | None:
    """枚举分布用选项名称做分类。没有这份对照时，图里的分组键是选项 id。"""
    key = str(group_by or "").strip()
    if not key:
        return None
    attr = next((item for item in attrs or [] if str(item.get("attr_id") or "") == key), None)
    if not isinstance(attr, dict) or str(attr.get("attr_type") or "").lower() != "enum":
        return None
    labels = {}
    for option in ModelManage.resolve_runtime_enum_options(attr) or []:
        if not isinstance(option, dict):
            continue
        option_id = option.get("id")
        if option_id in (None, ""):
            continue
        labels[str(option_id)] = str(option.get("name") or option.get("label") or option_id)
    return labels


def _attr_types_from(attrs: list) -> dict[str, str]:
    types = {"inst_name": "string", "inst_uuid": "string"}
    for attr in attrs or []:
        if not isinstance(attr, dict):
            continue
        attr_id = str(attr.get("attr_id") or "").strip()
        if attr_id:
            types[attr_id] = str(attr.get("attr_type") or "string")
    return types


def _reject_retired_model_args(kwargs) -> None:
    if kwargs.get("analysis_mode") not in (None, ""):
        raise GenericQueryError("当前查询不支持该参数")


def _reject_split_mode(analysis_mode, message: str) -> None:
    if str(analysis_mode or "").strip():
        raise GenericQueryError(message)


_INSTANCE_SPLIT = "当前查询不支持该参数"
_ONE_HOP_SPLIT = "当前查询不支持该参数"


def _model_query_scope(user_info, classification_id, model_id, model_ids):
    models, instance_permissions, names = _visible_models(user_info)
    if classification_id and str(classification_id) not in names:
        raise GenericQueryError("指定分类不存在或无权访问", status="forbidden")
    selected = _text_list(model_ids)
    if model_id not in (None, ""):
        selected.append(str(model_id))
    counts = count_by_attr("model_id", [], instance_permissions)
    return models, counts, str(classification_id or ""), selected


@nats_client.register
@_guard("query_cmdb_models")
def query_cmdb_models(
    classification_id=None,
    model_id=None,
    model_ids=None,
    page=None,
    page_size=None,
    user_info=None,
    **kwargs,
):
    """CMDB 模型列表。kwargs 接收运营分析透传的未知参数，不因此报错。"""
    _reject_retired_model_args(kwargs)
    del kwargs
    models, counts, classification, selected = _model_query_scope(user_info, classification_id, model_id, model_ids)
    data = query_models(
        models=models,
        instance_counts=counts,
        classification_id=classification,
        model_ids=selected,
        page=page,
        page_size=page_size,
    )
    return _ok(data)


@nats_client.register
@_guard("query_cmdb_model_counts")
def query_cmdb_model_counts(
    classification_id=None,
    model_id=None,
    model_ids=None,
    user_info=None,
    **kwargs,
):
    """CMDB 模型数量。固定返回一行，不接受分页。"""
    _reject_retired_model_args(kwargs)
    if kwargs.get("page") not in (None, "") or kwargs.get("page_size") not in (None, ""):
        raise GenericQueryError("计数不支持分页")
    del kwargs
    models, counts, classification, selected = _model_query_scope(user_info, classification_id, model_id, model_ids)
    return _ok(
        query_model_counts(
            models=models,
            instance_counts=counts,
            classification_id=classification,
            model_ids=selected,
        )
    )


def _fill_unset_model_attrs(items, attrs: list) -> None:
    """明细行补上模型里有、这条实例没写过的属性。已有值保持不变，空值用 null。"""
    if not isinstance(items, list):
        return
    keys: list[str] = []
    seen: set[str] = set()
    for attr in attrs or []:
        if not isinstance(attr, dict) or attr.get("is_display_field"):
            continue
        attr_id = str(attr.get("attr_id") or "").strip()
        if not attr_id or attr_id.startswith("_") or attr_id in seen:
            continue
        if str(attr.get("attr_type") or "").lower() == "pwd":
            continue
        seen.add(attr_id)
        keys.append(attr_id)
    for item in items:
        if not isinstance(item, dict):
            continue
        for key in keys:
            item.setdefault(key, None)


def _instance_scope(user_info, model_id, classification_id, filters):
    parsed_filters = _require_condition_group(filters)
    models, instance_permissions, _names = _visible_models(user_info)
    visible_ids = {str(item.get("model_id")) for item in models}
    if str(model_id or "") not in visible_ids:
        raise GenericQueryError("指定模型不存在或无权访问", status="forbidden")
    _require_model_classification(models, model_id, classification_id)
    attrs = _load_model_attrs(str(model_id), user_info)
    return parsed_filters, instance_permissions, attrs


@nats_client.register
@_guard("query_cmdb_instances")
def query_cmdb_instances(
    model_id=None,
    classification_id=None,
    analysis_mode=None,
    filters=None,
    group_by=None,
    aggregate_field=None,
    aggregate_op=None,
    order_by=None,
    order_dir=None,
    page=None,
    page_size=None,
    user_info=None,
    **kwargs,
):
    del kwargs
    parsed_filters, instance_permissions, attrs = _instance_scope(user_info, model_id, classification_id, filters)
    _reject_split_mode(analysis_mode, _INSTANCE_SPLIT)
    data = query_instances(
        model_id=str(model_id),
        analysis_mode="detail",
        attr_types=_attr_types_from(attrs),
        permission_map=instance_permissions,
        filters=parsed_filters,
        group_by=group_by,
        aggregate_field=aggregate_field,
        aggregate_op=aggregate_op,
        order_by=order_by,
        order_dir=order_dir,
        page=page,
        page_size=page_size,
    )
    rows = data if isinstance(data, list) else data.get("items")
    _fill_unset_model_attrs(rows, attrs)
    return _ok(data)


@nats_client.register
@_guard("query_cmdb_instance_value")
def query_cmdb_instance_value(
    model_id=None,
    classification_id=None,
    analysis_mode=None,
    filters=None,
    group_by=None,
    aggregate_field=None,
    aggregate_op=None,
    order_by=None,
    order_dir=None,
    page=None,
    page_size=None,
    user_info=None,
    **kwargs,
):
    del kwargs
    parsed_filters, instance_permissions, attrs = _instance_scope(user_info, model_id, classification_id, filters)
    _reject_split_mode(analysis_mode, _INSTANCE_SPLIT)
    data = query_instance_value(
        model_id=str(model_id),
        attr_types=_attr_types_from(attrs),
        permission_map=instance_permissions,
        filters=parsed_filters,
        aggregate_field=aggregate_field,
        aggregate_op=aggregate_op,
        group_by=group_by,
        order_by=order_by,
        order_dir=order_dir,
        page=page,
        page_size=page_size,
    )
    return _ok([data])


@nats_client.register
@_guard("query_cmdb_instance_distribution")
def query_cmdb_instance_distribution(
    model_id=None,
    classification_id=None,
    analysis_mode=None,
    filters=None,
    group_by=None,
    aggregate_field=None,
    aggregate_op=None,
    order_by=None,
    order_dir=None,
    page=None,
    page_size=None,
    user_info=None,
    **kwargs,
):
    del kwargs
    parsed_filters, instance_permissions, attrs = _instance_scope(user_info, model_id, classification_id, filters)
    _reject_split_mode(analysis_mode, _INSTANCE_SPLIT)
    if aggregate_field not in (None, "") or aggregate_op not in (None, ""):
        raise GenericQueryError("分布查询不支持聚合")
    if not str(group_by or "").strip():
        raise GenericQueryError("请选择分布属性")
    data = query_instances(
        model_id=str(model_id),
        analysis_mode="distribution",
        attr_types=_attr_types_from(attrs),
        permission_map=instance_permissions,
        filters=parsed_filters,
        group_by=group_by,
        order_by=order_by,
        order_dir=order_dir,
        page=page,
        page_size=page_size,
        group_labels=_enum_group_labels(attrs, group_by),
    )
    return _ok(data)


def _one_hop_direction(start_model_id: str, association: dict) -> tuple[str, str]:
    """起点在关系左侧则向外，在右侧则向内。两端相同无法由起点决定。"""
    src = str(association.get("src_model_id") or "")
    dst = str(association.get("dst_model_id") or "")
    if src == start_model_id and dst == start_model_id:
        raise GenericQueryError("关系两端相同，无法由起点确定走向")
    if src == start_model_id:
        return "out", dst
    if dst == start_model_id:
        return "in", src
    raise GenericQueryError("关系方向与起点模型不一致")


def _selected_one_hop_associations(start_model_id, model_asst_id, associations, visible_ids) -> list[dict]:
    """每条关系单独校验。走向和终点模型可以不同，两端相同的关系仍然拒绝。"""
    selected = []
    for asst_id in _text_list(model_asst_id):
        if asst_id not in selected:
            selected.append(asst_id)
    if not selected:
        raise GenericQueryError("起点模型和关系不能为空")
    by_id = {str(item.get("model_asst_id") or ""): item for item in associations}
    chosen = []
    for asst_id in selected:
        association = by_id.get(asst_id)
        if association is None:
            raise GenericQueryError("关系不存在或无权访问", status="forbidden")
        _direction, end_model_id = _one_hop_direction(str(start_model_id), association)
        if str(end_model_id) not in visible_ids:
            raise GenericQueryError("终点模型不存在或无权访问", status="forbidden")
        chosen.append(association)
    return chosen


def _execute_one_hop(
    *,
    start_model_id,
    classification_id,
    model_asst_id,
    analysis_mode,
    page,
    page_size,
    user_info,
):
    if not start_model_id or model_asst_id in (None, "", []):
        raise GenericQueryError("起点模型和关系不能为空")
    models, instance_permissions, _names = _visible_models(user_info)
    visible_ids = {str(item.get("model_id")) for item in models}
    if str(start_model_id) not in visible_ids:
        raise GenericQueryError("指定模型不存在或无权访问", status="forbidden")
    _require_model_classification(models, start_model_id, classification_id)
    language = _resolve_nats_cmdb_language(user_info)
    associations = list_model_association_options(language, start_model_id)
    chosen = _selected_one_hop_associations(start_model_id, model_asst_id, associations, visible_ids)
    relation_ids = [str(item.get("model_asst_id") or "") for item in chosen]
    association_names = {relation_id: str(item.get("asst_name") or item.get("label") or "") for relation_id, item in zip(relation_ids, chosen)}
    plan = one_hop_query_plan(analysis_mode, page, page_size)
    graph_result = query_one_hop(
        start_model_id=str(start_model_id),
        model_asst_ids=relation_ids,
        permission_map=instance_permissions,
        part=plan["part"],
        skip=int(plan.get("skip") or 0),
        limit=plan.get("limit"),
    )
    data = query_one_hop_relations(
        analysis_mode=analysis_mode,
        graph_result=graph_result,
        page=page,
        page_size=page_size,
        association_names=association_names,
    )
    return _ok(data)


@nats_client.register
@_guard("query_cmdb_one_hop")
def query_cmdb_one_hop(
    start_model_id=None,
    classification_id=None,
    model_asst_id=None,
    analysis_mode=None,
    page=None,
    page_size=None,
    user_info=None,
    **kwargs,
):
    """kwargs 吃掉已取消的起点条件和终点条件，避免旧组件请求失败。"""
    del kwargs
    _reject_split_mode(analysis_mode, _ONE_HOP_SPLIT)
    return _execute_one_hop(
        start_model_id=start_model_id,
        classification_id=classification_id,
        model_asst_id=model_asst_id,
        analysis_mode="detail",
        page=page,
        page_size=page_size,
        user_info=user_info,
    )


@nats_client.register
@_guard("query_cmdb_one_hop_counts")
def query_cmdb_one_hop_counts(
    start_model_id=None,
    classification_id=None,
    model_asst_id=None,
    analysis_mode=None,
    page=None,
    page_size=None,
    user_info=None,
    **kwargs,
):
    """kwargs 吃掉已取消的起点条件和终点条件，避免旧组件请求失败。"""
    del kwargs
    _reject_split_mode(analysis_mode, _ONE_HOP_SPLIT)
    if page not in (None, "") or page_size not in (None, ""):
        raise GenericQueryError("数量不支持分页")
    payload = _execute_one_hop(
        start_model_id=start_model_id,
        classification_id=classification_id,
        model_asst_id=model_asst_id,
        analysis_mode="count",
        page=None,
        page_size=None,
        user_info=user_info,
    )
    return _ok([payload["data"]])


@nats_client.register
@_guard("query_cmdb_one_hop_distribution")
def query_cmdb_one_hop_distribution(
    start_model_id=None,
    classification_id=None,
    model_asst_id=None,
    analysis_mode=None,
    page=None,
    page_size=None,
    user_info=None,
    **kwargs,
):
    """kwargs 吃掉已取消的起点条件和终点条件，避免旧组件请求失败。"""
    del kwargs
    _reject_split_mode(analysis_mode, _ONE_HOP_SPLIT)
    if page not in (None, ""):
        raise GenericQueryError("排行不支持页码")
    return _execute_one_hop(
        start_model_id=start_model_id,
        classification_id=classification_id,
        model_asst_id=model_asst_id,
        analysis_mode="distribution",
        page=None,
        page_size=page_size,
        user_info=user_info,
    )


@nats_client.register
@_guard("list_cmdb_model_options")
def list_cmdb_model_options(classification_id=None, user_info=None, **kwargs):
    del kwargs
    models, _permissions, _names = _visible_models(user_info)
    if classification_id:
        models = [item for item in models if str(item.get("classification_id")) == str(classification_id)]
    data = [
        {
            "model_id": item.get("model_id"),
            "model_name": item.get("model_name") or item.get("model_id"),
            "classification_id": item.get("classification_id") or "",
        }
        for item in models
        if item.get("model_id")
    ]
    ensure_payload_limit(data)
    return {"result": True, "data": data, "message": ""}


def _attr_list_model_id(model_id, start_model_id, model_asst_id, user_info):
    """直接模型优先。没传模型时，用起点和关联找到另一端。"""
    if model_id not in (None, ""):
        return str(model_id)
    start = str(start_model_id or "").strip()
    association = str(model_asst_id or "").strip()
    if not start and not association:
        return ""
    if not start or not association:
        raise GenericQueryError("模型不能为空")
    language = _resolve_nats_cmdb_language(user_info)
    row = next(
        (item for item in list_model_association_options(language, start) if str(item.get("model_asst_id") or "") == association),
        None,
    )
    if not row:
        return None
    src = str(row.get("src_model_id") or "")
    dst = str(row.get("dst_model_id") or "")
    return dst if src == start else src


@nats_client.register
@_guard("list_cmdb_attr_options")
def list_cmdb_attr_options(model_id=None, start_model_id=None, model_asst_id=None, user_info=None, **kwargs):
    del kwargs
    resolved = _attr_list_model_id(model_id, start_model_id, model_asst_id, user_info)
    if resolved is None:
        return {"result": True, "data": [], "message": ""}
    if not resolved:
        raise GenericQueryError("模型不能为空")
    model_id = resolved
    models, _permissions, _names = _visible_models(user_info)
    if str(model_id) not in {str(item.get("model_id")) for item in models}:
        raise GenericQueryError("指定模型不存在或无权访问", status="forbidden")
    language = _resolve_nats_cmdb_language(user_info)
    attrs = ModelManage.search_model_attr(str(model_id), language=language) or []
    data = [_attr_option(attr) for attr in attrs if attr.get("attr_id")]
    ensure_payload_limit(data)
    return {"result": True, "data": data, "message": ""}
