def _is_skill_tool_id(value):
    """非零整数才是工具 ID。0 / bool 视为缺失；负 ID 是身份类内置工具。"""
    return isinstance(value, int) and not isinstance(value, bool) and value != 0


def _tool_names(tool):
    """请求体里 name 常是展示名，rawName 才是 langchain 类别名。"""
    names = []
    for key in ("name", "rawName"):
        value = tool.get(key)
        if value and value not in names:
            names.append(value)
    return names


def resolve_request_tools(request_tools, skill_tools):
    """解析本次技能执行最终使用的工具列表。

    安全要求（BL-NEW-001 越权 / 代码执行）：
        请求体中的 ``tools`` 只能用于「为 Skill 已授权的工具携带运行时参数」，
        绝不能用于「越权添加」Skill 未授权的工具。历史实现中只要请求带了
        ``tools`` 就原样返回，低权限用户可借此把任意全局工具 ID（如通用
        Python / Shell 执行工具）注入到自己有权运行的 Skill，再配合沙箱逃逸
        以服务进程权限执行任意命令。

    因此这里以**服务端 Skill 配置**（``skill_tools``）作为唯一权威授权来源，
    请求工具按白名单过滤：

    - 带非零整数 ``id`` 的工具（含身份类内置工具的负 ID）：``id`` 必须命中
      Skill 已授权的工具 ID。（只认 ID，避免用合法 ``name`` + 伪造 ``id``
      欺骗下游按 ID 加载。）
    - 不带有效 ``id`` 的工具（如按 name 匹配的内置工具）：``name`` / ``rawName``
      必须命中 Skill 已授权的工具名。

    未授权的请求工具一律丢弃。请求未携带 ``tools`` 时回退到 Skill 自身配置。
    """
    skill_tools = skill_tools or []
    if not request_tools:
        return skill_tools

    authorized_ids = set()
    authorized_names = set()
    for tool in skill_tools:
        if not isinstance(tool, dict):
            continue
        tool_id = tool.get("id")
        if _is_skill_tool_id(tool_id):
            authorized_ids.add(tool_id)
        for name in _tool_names(tool):
            authorized_names.add(name)

    resolved = []
    for tool in request_tools:
        if not isinstance(tool, dict):
            continue
        tool_id = tool.get("id")
        if _is_skill_tool_id(tool_id):
            # 有效 ID：必须按 ID 命中授权集合（name 不参与判定，防伪造）。
            if tool_id in authorized_ids:
                resolved.append(tool)
        elif any(name in authorized_names for name in _tool_names(tool)):
            # 无有效 ID：按 name / rawName 命中授权集合（内置工具等）。
            resolved.append(tool)
    return resolved
