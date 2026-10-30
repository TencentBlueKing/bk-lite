"""把高级筛选编译成一条参数化查询。"""

from apps.cmdb.graph.format_type import FORMAT_TYPE_PARAMS, apply_node_alias
from apps.cmdb.graph.validators import CQLValidator

MAX_CONDITIONS = 10
ADVANCED_FILTER_TIMEOUT_MS = 15000
ADVANCED_FILTER_TIMEOUT_SECONDS = 15

OPERATORS_BY_TYPE = {
    "str": {"str=", "str<>", "str*", "str!*", "empty", "not_empty"},
    "int": {"int=", "int<>", "int>", "int<", "empty", "not_empty"},
    "float": {"int=", "int<>", "int>", "int<", "empty", "not_empty"},
    "enum": {"list_any[]", "list_none[]", "empty", "not_empty"},
    "time": {"time", "time<", "time>", "empty", "not_empty"},
    "user": {"list[]", "user[]", "empty", "not_empty"},
    "organization": {"list[]", "empty", "not_empty"},
    "bool": {"bool", "empty", "not_empty"},
    "tag": {"list_any[]", "list_none[]", "empty", "not_empty"},
}
VALUELESS = {"empty", "not_empty"}


class AdvancedFilterError(Exception):
    def __init__(self, message, index=None):
        super().__init__(message)
        self.index = index


class AdvancedFilterTimeout(Exception):
    pass


def format_node_conditions(params, alias, logic, collector, case_sensitive=True):
    parts = []
    for param in params or []:
        method = FORMAT_TYPE_PARAMS.get(param.get("type"))
        if not method:
            continue
        text = method({**param, "case_sensitive": case_sensitive}, collector)
        if text:
            parts.append(apply_node_alias(text, alias))
    if not parts:
        return ""
    return "(" + f" {logic} ".join(parts) + ")"


def build_permission_clause(permission_dict, collector, alias, organization_field="organization"):
    """与实例列表相同的组织权限拼接，作用在指定节点别名上。"""
    if not permission_dict:
        return ""
    permission_filters = []
    for organization_id, query_list in permission_dict.items():
        organization_query = [{"field": organization_field, "type": "list[]", "value": [organization_id]}]
        org_base = format_node_conditions(organization_query, alias, "AND", collector)
        org_perm = format_node_conditions(query_list or [], alias, "OR", collector)
        org_filters = [item for item in (org_base, org_perm) if item]
        if not org_filters:
            continue
        if len(org_filters) == 1:
            permission_filters.append(org_filters[0])
        else:
            permission_filters.append("(" + " AND ".join(org_filters) + ")")
    if not permission_filters:
        return ""
    if len(permission_filters) == 1:
        return permission_filters[0]
    return "(" + " OR ".join(permission_filters) + ")"


def _fail(index, message):
    raise AdvancedFilterError(message, index)


def _other_end(src, dst, current):
    if src == current and dst == current:
        return current
    if src == current:
        return dst
    if dst == current:
        return src
    return None


def _query_param(condition):
    op = condition["type"]
    param = {"field": condition["field"], "type": op}
    if op in VALUELESS:
        return param
    if op == "time":
        param["start"] = condition.get("start")
        param["end"] = condition.get("end")
        return param
    param["value"] = condition.get("value")
    return param


def _missing_value(condition):
    op = condition.get("type")
    if op in VALUELESS:
        return False
    if op == "time":
        return condition.get("start") in (None, "") or condition.get("end") in (None, "")
    value = condition.get("value")
    return value is None or value == "" or value == []


def resolve_advanced_filter(model_id, payload, associations, visible, attrs_by_model):
    """校验并解析高级筛选。associations 以 model_asst_id 为键，值含 src_model_id、dst_model_id。"""
    if not isinstance(payload, dict):
        _fail(None, "高级筛选格式不正确")
    logic = payload.get("logic")
    if logic not in {"AND", "OR"}:
        _fail(None, "条件组合只支持 AND 或 OR")
    conditions = payload.get("conditions")
    if not isinstance(conditions, list) or not conditions:
        _fail(None, "请至少添加一个筛选条件")
    if len(conditions) > MAX_CONDITIONS:
        _fail(None, f"筛选条件不能超过 {MAX_CONDITIONS} 个")

    resolved = []
    for offset, raw in enumerate(conditions, start=1):
        if not isinstance(raw, dict):
            _fail(offset, "条件格式不正确")
        path = raw.get("path") or []
        if not isinstance(path, list) or len(path) > 2 or any(not isinstance(item, str) or not item for item in path):
            _fail(offset, "关联路径最多两层")
        if len(path) == 2 and path[0] == path[1]:
            _fail(offset, "不能沿同一关系返回")
        current = model_id
        models = []
        for asst_id in path:
            edge = associations.get(asst_id)
            if not edge:
                _fail(offset, "关联关系不存在")
            nxt = _other_end(edge.get("src_model_id"), edge.get("dst_model_id"), current)
            if nxt is None:
                _fail(offset, "关联关系与上一步不相接")
            if nxt not in visible:
                _fail(offset, "关联模型不可见")
            models.append(nxt)
            current = nxt
        end_model = model_id if not models else models[-1]
        attr_type = (attrs_by_model.get(end_model) or {}).get(raw.get("field"))
        if not attr_type:
            _fail(offset, "字段不可筛选")
        op = raw.get("type")
        allowed = OPERATORS_BY_TYPE.get(attr_type)
        if not allowed or op not in allowed:
            _fail(offset, "运算符与字段类型不匹配")
        if _missing_value(raw):
            _fail(offset, "请填写筛选值")
        resolved.append(
            {
                "index": offset,
                "path": list(path),
                "models": models,
                "end_model_id": end_model,
                "query": _query_param(raw),
            }
        )
    return logic, resolved


def _permission(permission_for, model_id, alias):
    if permission_for is None:
        return ""
    return permission_for(model_id, alias) or ""


def compile_advanced_filter(
    model_id,
    logic,
    conditions,
    *,
    label,
    collector,
    permission_for,
    base_params,
    case_sensitive=True,
):
    """返回 MATCH...WHERE 片段。片段结束时 n 代表去重后的当前模型实例。"""
    validated_label = CQLValidator.validate_label(label)
    lines = [f"MATCH (n:{validated_label})"]
    where = []
    current_perm = _permission(permission_for, model_id, "n")
    if current_perm:
        where.append(current_perm)
    base = format_node_conditions(base_params, "n", "AND", collector, case_sensitive)
    if base:
        where.append(base)
    self_conditions = [item for item in conditions if not item["path"]]
    if logic == "AND" and self_conditions:
        where.append(format_node_conditions([item["query"] for item in self_conditions], "n", "AND", collector, case_sensitive))
    if where:
        lines.append("WHERE " + " AND ".join(where))

    if logic == "AND":
        groups = {}
        for item in conditions:
            if not item["path"]:
                continue
            groups.setdefault(item["path"][0], []).append(item)
        for index, (asst_id, group) in enumerate(groups.items()):
            lines.append(_and_group(index, asst_id, group, collector, permission_for, case_sensitive, validated_label))
        return "\n".join(lines)

    self_expr = "false"
    if self_conditions:
        self_expr = format_node_conditions([item["query"] for item in self_conditions], "n", "OR", collector, case_sensitive)
    lines.append(f"WITH n, {self_expr} AS c0")
    carried = ["n", "c0"]
    full_paths = {}
    for item in conditions:
        if item["path"]:
            full_paths.setdefault(tuple(item["path"]), []).append(item)
    for index, (path, group) in enumerate(full_paths.items(), start=1):
        lines.append(_or_group(index, path, group, collector, permission_for, case_sensitive, validated_label))
        flag = f"c{index}"
        lines.append(f"WITH {', '.join(carried)}, count(x{index}) > 0 AS {flag}")
        carried.append(flag)
    flags = [name for name in carried if name != "n"]
    lines.append("WHERE " + " OR ".join(flags))
    return "\n".join(lines)


def _and_group(index, asst_id, group, collector, permission_for, case_sensitive, label):
    alias = f"h{index}"
    relation = f"r{index}a"
    asst_param = collector.add_param(asst_id, prefix="asst")
    model_param = collector.add_param(group[0]["models"][0], prefix="model")
    checks = [f"{relation}.model_asst_id = {asst_param}", f"{alias}.model_id = {model_param}"]
    one_hop = [item for item in group if len(item["path"]) == 1]
    if one_hop:
        checks.append(format_node_conditions([item["query"] for item in one_hop], alias, "AND", collector, case_sensitive))
        perm = _permission(permission_for, one_hop[0]["end_model_id"], alias)
        if perm:
            checks.append(perm)
    lines = [f"MATCH (n)-[{relation}]-({alias}:{label}) WHERE " + " AND ".join(item for item in checks if item)]
    two_hops = {}
    for item in group:
        if len(item["path"]) == 2:
            two_hops.setdefault(item["path"][1], []).append(item)
    for hop_index, (second, hop_group) in enumerate(two_hops.items()):
        end_alias = f"e{index}_{hop_index}"
        second_relation = f"r{index}_{hop_index}"
        second_param = collector.add_param(second, prefix="asst")
        end_model = collector.add_param(hop_group[0]["end_model_id"], prefix="model")
        hop_checks = [
            f"{second_relation}.model_asst_id = {second_param}",
            f"{end_alias}.model_id = {end_model}",
            format_node_conditions([item["query"] for item in hop_group], end_alias, "AND", collector, case_sensitive),
        ]
        perm = _permission(permission_for, hop_group[0]["end_model_id"], end_alias)
        if perm:
            hop_checks.append(perm)
        lines.append(f"MATCH ({alias})-[{second_relation}]-({end_alias}:{label}) WHERE " + " AND ".join(item for item in hop_checks if item))
    lines.append("WITH DISTINCT n")
    return "\n".join(lines)


def _or_group(index, path, group, collector, permission_for, case_sensitive, label):
    end_alias = f"x{index}"
    if len(path) == 1:
        relation = f"q{index}"
        asst_param = collector.add_param(path[0], prefix="asst")
        model_param = collector.add_param(group[0]["end_model_id"], prefix="model")
        checks = [
            f"{relation}.model_asst_id = {asst_param}",
            f"{end_alias}.model_id = {model_param}",
            format_node_conditions([item["query"] for item in group], end_alias, "OR", collector, case_sensitive),
        ]
        perm = _permission(permission_for, group[0]["end_model_id"], end_alias)
        if perm:
            checks.append(perm)
        return f"OPTIONAL MATCH (n)-[{relation}]-({end_alias}:{label}) WHERE " + " AND ".join(checks)
    first, second = path
    first_relation = f"q{index}a"
    second_relation = f"q{index}b"
    first_param = collector.add_param(first, prefix="asst")
    second_param = collector.add_param(second, prefix="asst")
    model_param = collector.add_param(group[0]["end_model_id"], prefix="model")
    checks = [
        f"{first_relation}.model_asst_id = {first_param}",
        f"{second_relation}.model_asst_id = {second_param}",
        f"{end_alias}.model_id = {model_param}",
        format_node_conditions([item["query"] for item in group], end_alias, "OR", collector, case_sensitive),
    ]
    perm = _permission(permission_for, group[0]["end_model_id"], end_alias)
    if perm:
        checks.append(perm)
    return f"OPTIONAL MATCH (n)-[{first_relation}]-(:{label})-[{second_relation}]-({end_alias}:{label}) WHERE " + " AND ".join(checks)


def data_and_count_statements(match, projection, order, order_type, page):
    order_clause = f" ORDER BY n.{order} {order_type}" if order else f" ORDER BY ID(n) {order_type}"
    data = f"{match} RETURN {projection}{order_clause}"
    if page:
        data += f" SKIP {int(page['skip'])} LIMIT {int(page['limit'])}"
    count = f"{match} RETURN count(n) AS count"
    return data, count
