def format_to_vm_filter(conditions):
    """
    将纬度条件格式化为 VictoriaMetrics 的标准语法。

    Args:
        conditions (list): 包含过滤条件的字典列表，每个字典格式为：
            {"name": <纬度名称>, "value": <值>, "method": <运算符>}

    Returns:
        str: 格式化后的 VictoriaMetrics 过滤条件语法。
    """
    vm_filters = []
    for condition in conditions:
        name = condition.get("name")
        value = condition.get("value")
        method = condition.get("method")
        vm_filters.append(f'{name}{method}"{value}"')

    # 使用逗号连接多个条件
    return ",".join(vm_filters)