# -- coding: utf-8 --
# @File: template.py
# @Time: 2025/12/10 17:41
# @Author: windyzhao
from typing import Dict, Any, Tuple

# 默认的告警标题和内容模板
DEFAULT_TITLE = "【${resource_type}】${resource_name}发生${item} 异常"
DEFAULT_CONTENT = "【${resource_type}】${resource_name}发生${item} 异常"


def format_template_string(template: str, data: Dict[str, Any]) -> str:
    """格式化模板字符串中的变量

    Args:
        template: 包含${变量名}格式的模板字符串
        data: 包含变量名和对应值的字典

    Returns:
        格式化后的字符串
    """
    if not template:
        return ""

    result = template
    # 替换所有${var}格式的变量
    for key, value in data.items():
        placeholder = "${" + key + "}"
        if not value:
            value = ""
        result = result.replace(placeholder, str(value))

    return result


def format_alert_message(rule: dict, event_data: Dict[str, Any]) -> Tuple[str, str]:
    """格式化告警标题和内容

    Args:
        rule: 告警规则配置
        event_data: 触发事件的数据

    Returns:
        包含格式化后标题和内容的字典
    """
    title = rule.get("title", None)
    content = rule.get("content", None)

    # 如果规则中没有设置标题或内容，使用默认格式
    if not title:
        title = DEFAULT_TITLE
    if not content:
        content = DEFAULT_CONTENT

    # 格式化标题和内容
    formatted_title = format_template_string(title, event_data)
    formatted_content = format_template_string(content, event_data)

    return formatted_title, formatted_content
