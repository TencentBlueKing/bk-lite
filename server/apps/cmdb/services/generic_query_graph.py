"""把通用查询的计数、数值聚合和一跳关系统计下推到图数据库。"""

from __future__ import annotations

from apps.cmdb.constants.constants import INSTANCE, INSTANCE_ASSOCIATION
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.graph.falkordb_format import FormatDBResult
from apps.cmdb.graph.format_type import ParameterCollector
from apps.cmdb.graph.validators import CQLValidator
from apps.cmdb.services.generic_query_limits import DETAIL_PAGE_SIZE_MAX, ONE_HOP_LIST_MAX, QUERY_TIMEOUT_MS, STAT_GROUP_MAX
from apps.cmdb.services.instance import InstanceManage

_AGGREGATIONS = {
    "sum": "sum",
    "avg": "avg",
    "min": "min",
    "max": "max",
}


class GenericQueryGraphError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def count_by_attr(
    group_by_attr: str,
    params: list,
    permission_map: dict,
    condition_params: list | None = None,
    condition_logic: str = "AND",
) -> dict:
    """图内 GROUP BY 计数，返回 {分组值: 数量}。"""
    CQLValidator.validate_field(group_by_attr)
    return InstanceManage.group_inst_count(
        group_by_attr=group_by_attr,
        permissions_map=permission_map,
        params=list(params or []),
        condition_params=list(condition_params or []),
        condition_logic=condition_logic,
    )


def aggregate_numeric(
    field: str,
    aggregation: str,
    params: list,
    permission_map: dict,
    condition_params: list | None = None,
    condition_logic: str = "AND",
) -> dict:
    """图内对数值属性做 sum/avg/min/max，同时返回参与计数。"""
    agg = _AGGREGATIONS.get(str(aggregation or "").strip().lower())
    if agg is None:
        raise GenericQueryGraphError("聚合方式不受支持")
    validated = CQLValidator.validate_field(field)
    with GraphClient() as client:
        where, query_params = _where_clause(
            client,
            params,
            permission_map,
            alias="n",
            condition_params=condition_params,
            condition_logic=condition_logic,
        )
        query = f"MATCH (n:{INSTANCE}) {where} " f"RETURN {agg}(n.{validated}) AS value, count(n) AS scanned"
        rows = _run(client, query, query_params)
    if not rows:
        return {"value": None, "scanned": 0}
    row = rows[0]
    return {"value": row.get("value"), "scanned": int(row.get("scanned") or 0)}


_DETAIL_ORDER = "ORDER BY start_name ASC, end_name ASC, start_uuid ASC, end_uuid ASC, model_asst_id ASC"
_RANK_ORDER = "ORDER BY relation_count DESC, start_uuid ASC"


def query_one_hop(
    *,
    start_model_id: str,
    model_asst_ids: list[str],
    permission_map: dict,
    part: str = "detail",
    skip: int = 0,
    limit: int | None = None,
) -> dict:
    """一跳关联在图里完成。无方向匹配同时覆盖向外和向内，起点和终点的权限写进同一条 MATCH。"""
    relation_ids = list(dict.fromkeys(str(item).strip() for item in model_asst_ids or [] if str(item).strip()))
    if part not in {"count", "distribution", "detail"}:
        raise GenericQueryGraphError("分析方式不受支持")
    if not start_model_id or not relation_ids:
        raise GenericQueryGraphError("起点模型和关系不能为空")
    pattern = f"(s)-[e:{INSTANCE_ASSOCIATION}]-(t)"
    where = ["s.model_id = $start_model_id"]
    params = {"start_model_id": str(start_model_id)}
    with GraphClient() as client:
        collector = ParameterCollector()
        relation_param = collector.add_param(relation_ids, prefix="asst_ids")
        start_permission, collector = _permission_clause(client, permission_map, alias="s", collector=collector)
        end_permission, collector = _permission_clause(client, permission_map, alias="t", collector=collector)
        params.update(collector.get_params())
        where_sql = " AND ".join([*where, f"e.model_asst_id IN {relation_param}", start_permission, end_permission])
        if part == "count":
            return {"pair_count": _pair_count(client, pattern, where_sql, params)}
        if part == "distribution":
            return _rank_starts(client, pattern, where_sql, params, limit)
        return _page_pairs(client, pattern, where_sql, params, skip, limit)


def _pair_count(client, pattern: str, where_sql: str, params: dict) -> int:
    query = (
        f"MATCH {pattern} WHERE {where_sql} "
        "WITH DISTINCT s.inst_uuid AS start_uuid, t.inst_uuid AS end_uuid, e.model_asst_id AS model_asst_id "
        "RETURN count(*) AS pair_count"
    )
    rows = _run(client, query, params)
    return int((rows[0].get("pair_count") if rows else 0) or 0)


def _rank_starts(client, pattern: str, where_sql: str, params: dict, limit: int | None) -> dict:
    count_query = f"MATCH {pattern} WHERE {where_sql} " "WITH DISTINCT s.inst_uuid AS start_uuid " "RETURN count(start_uuid) AS group_count"
    count_rows = _run(client, count_query, params)
    group_count = int((count_rows[0].get("group_count") if count_rows else 0) or 0)
    bounded = _return_limit(limit)
    if group_count == 0 or (bounded is None and group_count > STAT_GROUP_MAX):
        return {"group_count": group_count, "groups": []}
    query = (
        f"MATCH {pattern} WHERE {where_sql} "
        "WITH DISTINCT s.inst_uuid AS start_uuid, s.inst_name AS start_name, "
        "t.inst_uuid AS end_uuid, e.model_asst_id AS model_asst_id "
        "WITH start_uuid, start_name, count(*) AS relation_count "
        "RETURN start_uuid, start_name, relation_count " + _RANK_ORDER
    )
    if bounded is not None:
        query += f" LIMIT {bounded}"
    return {"group_count": group_count, "groups": _run(client, query, params)}


def _page_pairs(client, pattern: str, where_sql: str, params: dict, skip: int, limit: int | None) -> dict:
    # 总数和当前页仍各查一次。超过不分页上限就不再把对应关系拉回来。
    pair_count = _pair_count(client, pattern, where_sql, params)
    offset = _non_negative(skip)
    if limit is None:
        if pair_count > ONE_HOP_LIST_MAX:
            raise GenericQueryGraphError(f"对应关系超过 {ONE_HOP_LIST_MAX} 条，请缩小范围或填写分页")
        if pair_count == 0:
            return {"pair_count": 0, "pairs": [], "paged": False}
        bounded = pair_count
        paged = False
    else:
        bounded = _return_limit(limit)
        paged = True
        if pair_count == 0:
            return {"pair_count": 0, "pairs": [], "paged": True}
    query = (
        f"MATCH {pattern} WHERE {where_sql} "
        "WITH DISTINCT s.inst_uuid AS start_uuid, s.inst_name AS start_name, "
        "s.model_id AS start_model_id, t.inst_uuid AS end_uuid, "
        "t.inst_name AS end_name, t.model_id AS end_model_id, e.model_asst_id AS model_asst_id "
        "RETURN start_uuid, start_name, start_model_id, end_uuid, end_name, end_model_id, model_asst_id "
        + _DETAIL_ORDER
        + f" SKIP {offset} LIMIT {bounded}"
    )
    return {"pair_count": pair_count, "pairs": _run(client, query, params), "paged": paged}


def _return_limit(limit: int | None) -> int | None:
    if limit is None:
        return None
    number = _non_negative(limit)
    if number < 1 or number > DETAIL_PAGE_SIZE_MAX:
        raise GenericQueryGraphError(f"每页最多 {DETAIL_PAGE_SIZE_MAX} 条")
    return number


def _non_negative(value) -> int:
    if isinstance(value, bool):
        raise GenericQueryGraphError("分页参数不受支持")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise GenericQueryGraphError("分页参数不受支持") from exc
    if number < 0:
        raise GenericQueryGraphError("分页参数不受支持")
    return number


def _permission_clause(client, permission_map: dict, alias: str, collector: ParameterCollector | None = None):
    """把实例权限写成图条件。权限范围为空时失败关闭，不退回全量终点。"""
    if not permission_map:
        raise GenericQueryGraphError("缺少权限范围，已拒绝查询")
    collector = collector or ParameterCollector()
    permission = InstanceManage._build_format_permission_dict(permission_map or {}, "")
    permission_parts = []
    for organization_id, query_list in permission.items():
        org_params = [{"field": "organization", "type": "list[]", "value": [organization_id]}]
        org_str, _ignored = client.format_search_params(
            org_params,
            param_type="AND",
            param_collector=collector,
            alias=alias,
        )
        extra_str, _ignored = client.format_search_params(
            query_list or [],
            param_type="OR",
            param_collector=collector,
            alias=alias,
        )
        if org_str and extra_str:
            permission_parts.append(f"({org_str} AND {extra_str})")
        elif org_str:
            permission_parts.append(org_str)
    if not permission_parts:
        raise GenericQueryGraphError("缺少权限范围，已拒绝查询")
    joined = permission_parts[0] if len(permission_parts) == 1 else "(" + " OR ".join(permission_parts) + ")"
    return joined, collector


def _where_clause(
    client,
    params: list,
    permission_map: dict,
    alias: str,
    condition_params: list | None = None,
    condition_logic: str = "AND",
) -> tuple[str, dict]:
    collector = ParameterCollector()
    base, _query_params = client.format_search_params(
        list(params or []),
        param_type="AND",
        param_collector=collector,
        alias=alias,
    )
    group_sql, _ignored = client.format_search_params(
        list(condition_params or []),
        param_type="OR" if str(condition_logic or "AND").upper() == "OR" else "AND",
        param_collector=collector,
        alias=alias,
    )
    if not permission_map:
        raise GenericQueryGraphError("缺少权限范围，已拒绝查询")
    permission = InstanceManage._build_format_permission_dict(permission_map or {}, "")
    permission_parts = []
    for organization_id, query_list in permission.items():
        org_params = [{"field": "organization", "type": "list[]", "value": [organization_id]}]
        org_str, _ignored = client.format_search_params(
            org_params,
            param_type="AND",
            param_collector=collector,
            alias=alias,
        )
        extra_str, _ignored = client.format_search_params(
            query_list or [],
            param_type="OR",
            param_collector=collector,
            alias=alias,
        )
        if org_str and extra_str:
            permission_parts.append(f"({org_str} AND {extra_str})")
        elif org_str:
            permission_parts.append(org_str)
    if not permission_parts:
        raise GenericQueryGraphError("缺少权限范围，已拒绝查询")
    parts = []
    if base:
        parts.append(base)
    if group_sql:
        parts.append(group_sql)
    joined = permission_parts[0] if len(permission_parts) == 1 else "(" + " OR ".join(permission_parts) + ")"
    parts.append(joined)
    return "WHERE " + " AND ".join(parts), collector.get_params()


def _run(client, query: str, params: dict) -> list[dict]:
    if hasattr(client, "_execute_query"):
        result = client._execute_query(query, params=params, timeout=QUERY_TIMEOUT_MS)
        return _rows_from_falkor(result)
    session = getattr(client, "session", None)
    if session is None:
        raise GenericQueryGraphError("图数据库连接不可用")
    transaction = session.begin_transaction(timeout=QUERY_TIMEOUT_MS / 1000)
    try:
        cursor = transaction.run(query, params or {})
        rows = [record.data() for record in cursor]
        transaction.commit()
        return rows
    except Exception:
        transaction.rollback()
        raise


def _rows_from_falkor(result) -> list[dict]:
    formatted = FormatDBResult(result)
    rows = []
    for record in formatted.records or []:
        if formatted.headers and len(formatted.headers) == len(record):
            rows.append(dict(zip(formatted.headers, record)))
        elif isinstance(record, dict):
            rows.append(record)
    return rows
