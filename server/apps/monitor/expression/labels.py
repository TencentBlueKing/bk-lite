import re

VALID_LABEL_METHODS = {"=", "!=", "=~", "!~"}
LABEL_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def escape_label_value(value) -> str:
    if isinstance(value, (list, tuple, set, dict)):
        raise ValueError("label value 必须是标量")
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def format_to_vm_filter(conditions: list[dict]) -> str:
    vm_filters: list[str] = []
    for condition in conditions:
        name = condition.get("name")
        value = condition.get("value")
        method = condition.get("method")

        if not name or not LABEL_NAME_RE.match(str(name)):
            raise ValueError(f"非法的 label name：{name!r}，只允许 [a-zA-Z_][a-zA-Z0-9_]*")

        if method not in VALID_LABEL_METHODS:
            raise ValueError(f"非法的运算符：{method!r}，只允许 {sorted(VALID_LABEL_METHODS)}")

        escaped_value = escape_label_value(value if value is not None else "")
        vm_filters.append(f'{name}{method}"{escaped_value}"')

    return ",".join(vm_filters)
