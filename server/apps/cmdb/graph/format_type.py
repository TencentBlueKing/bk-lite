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
    return f"ANY(x IN {value} WHERE x IN n.{field})"


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
    "int=": format_int_eq,
    "int>": format_int_gt,
    "int<": format_int_lt,
    "int<>": format_int_neq,
    "int[]": format_int_in,
    "id=": format_id_eq,  # 修改为使用ID()函数
    "id[]": format_id_in,  # 修改为使用ID()函数
    "list[]": format_list_in,
}
