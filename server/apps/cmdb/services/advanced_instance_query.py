"""按高级筛选查询当前模型实例，供列表和导出共用。"""

from apps.cmdb.constants.constants import INSTANCE
from apps.cmdb.graph.advanced_filter import build_permission_clause, compile_advanced_filter, resolve_advanced_filter
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.graph.format_type import ParameterCollector
from apps.cmdb.model_ops.extensions import is_file_attr_type
from apps.cmdb.services.model import ModelManage
from apps.cmdb.services.model_visibility import BusinessModelVisibility


def _other_end(src, dst, current):
    if src == current and dst == current:
        return current
    if src == current:
        return dst
    if dst == current:
        return src
    return None


def _absorb_associations(model_id, conditions):
    loaded = {}
    seen = set()

    def absorb(mid):
        if not mid or mid in seen:
            return
        seen.add(mid)
        for edge in ModelManage.model_association_search(mid, business_only=True) or []:
            asst_id = edge.get("model_asst_id")
            if asst_id and asst_id not in loaded:
                loaded[asst_id] = {"src_model_id": edge.get("src_model_id"), "dst_model_id": edge.get("dst_model_id")}

    absorb(model_id)
    for raw in conditions or []:
        if not isinstance(raw, dict):
            continue
        current = model_id
        for asst_id in raw.get("path") or []:
            edge = loaded.get(asst_id)
            if not edge:
                break
            nxt = _other_end(edge.get("src_model_id"), edge.get("dst_model_id"), current)
            if nxt is None:
                break
            absorb(nxt)
            current = nxt
    return loaded, seen


def _attrs(model_id):
    rows = ModelManage.search_model_attr_v2(model_id) or []
    result = {}
    for attr in rows:
        attr_id = attr.get("attr_id")
        if not attr_id or attr.get("is_display_field") or is_file_attr_type(attr.get("attr_type")):
            continue
        result[attr_id] = attr.get("attr_type")
    return result


def run_advanced_instance_query(
    *,
    model_id,
    params,
    advanced_filter,
    permission_map,
    creator,
    permission_lookup,
    page,
    order,
    order_type,
    case_sensitive=True,
    fields=None,
    include_count=True,
    label=INSTANCE,
):
    from apps.cmdb.services.instance import InstanceManage

    conditions = advanced_filter.get("conditions") if isinstance(advanced_filter, dict) else []
    associations, models = _absorb_associations(model_id, conditions)
    visible = set()
    attrs = {}
    for mid in models:
        info = ModelManage.search_model_info(mid) or {}
        if BusinessModelVisibility.is_visible(info):
            visible.add(mid)
        attrs[mid] = _attrs(mid)
    logic, resolved = resolve_advanced_filter(model_id, advanced_filter, associations, visible, attrs)
    collector = ParameterCollector()

    def permission_for(mid, alias):
        source = permission_map if mid == model_id else (permission_lookup(mid) if permission_lookup else {})
        built = InstanceManage._build_format_permission_dict(source or {}, creator or "")
        return build_permission_clause(built, collector, alias)

    match = compile_advanced_filter(
        model_id,
        logic,
        resolved,
        label=label,
        collector=collector,
        permission_for=permission_for,
        base_params=params,
        case_sensitive=case_sensitive,
    )
    with GraphClient() as client:
        return client.query_compiled_entities(
            match,
            collector.get_params(),
            page=page,
            order=order,
            order_type=order_type,
            fields=fields,
            include_count=include_count,
        )
