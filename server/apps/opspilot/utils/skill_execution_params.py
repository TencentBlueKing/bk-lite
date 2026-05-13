def resolve_request_tools(request_tools, skill_tools):
    if request_tools:
        return request_tools
    if skill_tools:
        return skill_tools
    return []
