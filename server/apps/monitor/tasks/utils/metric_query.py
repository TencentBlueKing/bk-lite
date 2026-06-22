import re

# 允许的 label 运算符白名单（PromQL/MetricsQL 标准）
_VALID_METHODS = {"=", "!=", "=~", "!~"}

# label name 合法正则（Prometheus 规范）
_LABEL_NAME_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')


def _escape_label_value(value) -> str:
    """转义 PromQL/MetricsQL label value 中的反斜杠和双引号。"""
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def format_to_vm_filter(conditions):
    """
    将纬度条件格式化为 VictoriaMetrics 的标准语法。

    对 name/method/value 三个字段执行输入校验与转义，防止 PromQL/MetricsQL 注入：
    - name：只允许 [a-zA-Z_][a-zA-Z0-9_]* 格式的合法 label 名
    - method：只允许 =/!=/=~/!~ 四种标准运算符
    - value：对 \\ 和 " 转义后再拼入查询

    Args:
        conditions (list): 包含过滤条件的字典列表，每个字典格式为：
            {"name": <纬度名称>, "value": <值>, "method": <运算符>}

    Returns:
        str: 格式化后的 VictoriaMetrics 过滤条件语法。

    Raises:
        ValueError: name 或 method 不合法时抛出，拒绝生成查询。
    """
    vm_filters = []
    for condition in conditions:
        name = condition.get("name")
        value = condition.get("value")
        method = condition.get("method")

        if not name or not _LABEL_NAME_RE.match(str(name)):
            raise ValueError(f"非法的 label name：{name!r}，只允许 [a-zA-Z_][a-zA-Z0-9_]*")

        if method not in _VALID_METHODS:
            raise ValueError(f"非法的运算符：{method!r}，只允许 {sorted(_VALID_METHODS)}")

        escaped_value = _escape_label_value(value if value is not None else "")
        vm_filters.append(f'{name}{method}"{escaped_value}"')

    # 使用逗号连接多个条件
    return ",".join(vm_filters)
