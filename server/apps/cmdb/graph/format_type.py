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


def format_str_contains(param):
    field = param["field"]
    value = param["value"]
    return f"n.{field} =~ '.*{value}.*'"


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


def user_in(param):
    field = param["field"]
    value = param["value"]
    return f"n.{field} IN {value}"


def user_eq(param):
    field = param["field"]
    value = param["value"]
    return f"n.{field} = {value}"


# 映射参数类型和对应的转换函数
FORMAT_TYPE = {
    "bool": format_bool,
    "time": format_time,
    "str=": format_str_eq,
    "str<>": format_str_neq,
    "str*": format_str_contains,
    "str[]": format_str_in,
    "int=": format_int_eq,
    "int>": format_int_gt,
    "int<": format_int_lt,
    "int<>": format_int_neq,
    "int[]": format_int_in,
    "list[]": format_list_in,
    "id=": id_eq,
    "id[]": id_in,
    "user[]": user_in,
    "user=": user_eq,
}
