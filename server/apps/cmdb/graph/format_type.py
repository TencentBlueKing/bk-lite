def format_bool(param):
    field = param["field"]
    value = param["value"]
    return f"n.{field} = {value}"


def format_time(param):
    field = param["field"]
    start = param["start"]
    end = param["end"]
    return f"n.{field} >= '{start}' AND n.{field} <= '{end}'"


def format_str_eq(param):
    field = param["field"]
    value = param["value"]
    return f"n.{field} = '{value}'"


def format_str_neq(param):
    field = param["field"]
    value = param["value"]
    return f"n.{field} <> '{value}'"


# neo4j
def format_str_contains(param):
    field = param["field"]
    value = param["value"]
    return f"n.{field} =~ '.*{value}.*'"


def format_str_like(param):
    """str*: {"field": "name", "type": "str*", "value": "host"} -> "n.name contains 'host'" """
    field = param["field"]
    value = param["value"]
    return f"n.{field} contains '{value}'"


def format_str_in(param):
    field = param["field"]
    value = param["value"]
    return f"n.{field} IN {value}"


def format_user_in(param):
    field = param["field"]
    value = param["value"]
    return f"n.{field} IN {value}"


def format_int_eq(param):
    field = param["field"]
    value = param["value"]
    return f"n.{field} = {value}"


def format_int_gt(param):
    field = param["field"]
    value = param["value"]
    return f"n.{field} > {value}"


def format_int_lt(param):
    field = param["field"]
    value = param["value"]
    return f"n.{field} < {value}"


def format_int_neq(param):
    field = param["field"]
    value = param["value"]
    return f"n.{field} <> {value}"


def format_int_in(param):
    field = param["field"]
    value = param["value"]
    return f"n.{field} IN {value}"


def format_list_in(param):
    field = param["field"]
    value = param["value"]
    return f"(n.{field} IN {value} OR ANY(x IN {value} WHERE x IN n.{field}))"


def id_in(param):
    value = param["value"]
    return f"id(n) IN {value}"


def id_eq(param):
    value = param["value"]
    return f"id(n) = {value}"


def format_id_eq(param):
    """id=: {"field": "id", "type": "id=", "value": 115} -> "ID(n) = 115" """
    value = param["value"]
    return f"ID(n) = {value}"


def format_id_in(param):
    """id[]: {"field": "id", "type": "id[]", "value": [115,116]} -> "ID(n) IN [115,116]" """
    value = param["value"]
    return f"ID(n) IN {value}"


# 映射参数类型和对应的转换函数
FORMAT_TYPE = {
    "bool": format_bool,
    "time": format_time,
    "str=": format_str_eq,
    "str<>": format_str_neq,
    "str*": format_str_like,  # 修改为使用contains
    "str[]": format_str_in,
    "user[]": format_user_in,
    "int=": format_int_eq,
    "int>": format_int_gt,
    "int<": format_int_lt,
    "int<>": format_int_neq,
    "int[]": format_int_in,
    "id=": format_id_eq,  # 修改为使用ID()函数
    "id[]": format_id_in,  # 修改为使用ID()函数
    "list[]": format_list_in,
}


# ===== 参数化查询支持 =====


class ParameterCollector:
    """参数收集器 - 用于收集查询参数"""

    def __init__(self):
        self.params = {}
        self._counter = 0

    def add_param(self, value, prefix="p"):
        """添加参数并返回参数名"""
        self._counter += 1
        param_name = f"{prefix}{self._counter}"
        self.params[param_name] = value
        return f"${param_name}"

    def get_params(self):
        """获取所有参数"""
        return self.params

    def reset(self):
        """重置收集器"""
        self.params = {}
        self._counter = 0


def format_bool_params(param, collector):
    """参数化版本：bool类型"""
    from apps.cmdb.graph.validators import CQLValidator

    field = CQLValidator.validate_field(param["field"])
    value = param["value"]
    param_name = collector.add_param(value, prefix="bool")
    return f"n.{field} = {param_name}"


def format_time_params(param, collector):
    """参数化版本：time类型"""
    from apps.cmdb.graph.validators import CQLValidator

    field = CQLValidator.validate_field(param["field"])
    start = param["start"]
    end = param["end"]
    start_param = collector.add_param(start, prefix="time_start")
    end_param = collector.add_param(end, prefix="time_end")
    return f"n.{field} >= {start_param} AND n.{field} <= {end_param}"


def format_str_eq_params(param, collector):
    """参数化版本：str="""
    from apps.cmdb.graph.validators import CQLValidator

    field = CQLValidator.validate_field(param["field"])
    value = param["value"]
    param_name = collector.add_param(value, prefix="str")
    return f"n.{field} = {param_name}"


def format_str_neq_params(param, collector):
    """参数化版本：str<>"""
    from apps.cmdb.graph.validators import CQLValidator

    field = CQLValidator.validate_field(param["field"])
    value = param["value"]
    param_name = collector.add_param(value, prefix="str")
    return f"n.{field} <> {param_name}"


def format_str_like_params(param, collector):
    """
    参数化版本：str* (使用CONTAINS)

    支持 case_sensitive 参数控制是否区分大小写：
    - case_sensitive=True (默认): n.field CONTAINS $param
    - case_sensitive=False: toLower(n.field) CONTAINS toLower($param)
    """
    from apps.cmdb.graph.validators import CQLValidator

    field = CQLValidator.validate_field(param["field"])
    value = param["value"]
    case_sensitive = param.get("case_sensitive", True)

    param_name = collector.add_param(value, prefix="str")

    if case_sensitive:
        return f"n.{field} CONTAINS {param_name}"
    else:
        return f"toLower(n.{field}) CONTAINS toLower({param_name})"


def format_str_in_params(param, collector):
    """参数化版本：str[]"""
    from apps.cmdb.graph.validators import CQLValidator

    field = CQLValidator.validate_field(param["field"])
    value = param["value"]
    param_name = collector.add_param(value, prefix="str_list")
    return f"n.{field} IN {param_name}"


def format_user_in_params(param, collector):
    """参数化版本：user[]"""
    from apps.cmdb.graph.validators import CQLValidator

    field = CQLValidator.validate_field(param["field"])
    value = param["value"]
    param_name = collector.add_param(value, prefix="user_list")
    return f"n.{field} IN {param_name}"


def format_int_eq_params(param, collector):
    """参数化版本：int="""
    from apps.cmdb.graph.validators import CQLValidator

    field = CQLValidator.validate_field(param["field"])
    value = param["value"]
    param_name = collector.add_param(value, prefix="int")
    return f"n.{field} = {param_name}"


def format_int_gt_params(param, collector):
    """参数化版本：int>"""
    from apps.cmdb.graph.validators import CQLValidator

    field = CQLValidator.validate_field(param["field"])
    value = param["value"]
    param_name = collector.add_param(value, prefix="int")
    return f"n.{field} > {param_name}"


def format_int_lt_params(param, collector):
    """参数化版本：int<"""
    from apps.cmdb.graph.validators import CQLValidator

    field = CQLValidator.validate_field(param["field"])
    value = param["value"]
    param_name = collector.add_param(value, prefix="int")
    return f"n.{field} < {param_name}"


def format_int_neq_params(param, collector):
    """参数化版本：int<>"""
    from apps.cmdb.graph.validators import CQLValidator

    field = CQLValidator.validate_field(param["field"])
    value = param["value"]
    param_name = collector.add_param(value, prefix="int")
    return f"n.{field} <> {param_name}"


def format_int_in_params(param, collector):
    """参数化版本：int[]"""
    from apps.cmdb.graph.validators import CQLValidator

    field = CQLValidator.validate_field(param["field"])
    value = param["value"]
    param_name = collector.add_param(value, prefix="int_list")
    return f"n.{field} IN {param_name}"


def format_id_eq_params(param, collector):
    """参数化版本：id="""
    from apps.cmdb.graph.validators import CQLValidator

    value = CQLValidator.validate_id(param["value"])
    param_name = collector.add_param(value, prefix="id")
    return f"ID(n) = {param_name}"


def format_id_in_params(param, collector):
    """参数化版本：id[]"""
    from apps.cmdb.graph.validators import CQLValidator

    value = CQLValidator.validate_ids(param["value"])
    param_name = collector.add_param(value, prefix="ids")
    return f"ID(n) IN {param_name}"


def format_list_in_params(param, collector):
    """
    参数化版本：list[]

    支持字段为标量或列表两种情况：
    - 标量字段: n.field IN $list (如 n.operator=3 在 [3,5] 中)
    - 列表字段: ANY(x IN $list WHERE x IN n.field) (如 n.tags=[1,2] 与 [2,3] 有交集)
    """
    from apps.cmdb.graph.validators import CQLValidator

    field = CQLValidator.validate_field(param["field"])
    value = param["value"]
    param_name = collector.add_param(value, prefix="list")
    return f"(n.{field} IN {param_name} OR ANY(x IN {param_name} WHERE x IN n.{field}))"


# 参数化格式映射表
FORMAT_TYPE_PARAMS = {
    "bool": format_bool_params,
    "time": format_time_params,
    "str=": format_str_eq_params,
    "str<>": format_str_neq_params,
    "str*": format_str_like_params,
    "str[]": format_str_in_params,
    "user[]": format_user_in_params,
    "int=": format_int_eq_params,
    "int>": format_int_gt_params,
    "int<": format_int_lt_params,
    "int<>": format_int_neq_params,
    "int[]": format_int_in_params,
    "id=": format_id_eq_params,
    "id[]": format_id_in_params,
    "list[]": format_list_in_params,
}
