from html import escape


def build_user_rule_block(write_rule: str) -> str:
    """将用户配置的 write_rule 转为不可闭合外层标签的数据块。"""
    rule_text = str(write_rule or "").strip()
    if not rule_text:
        return "未配置额外写入规则"

    escaped_rule = escape(rule_text, quote=True)
    return f"<user_rule>\n{escaped_rule}\n</user_rule>"
