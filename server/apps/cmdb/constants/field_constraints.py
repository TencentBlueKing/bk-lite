# -- coding: utf-8 --
"""
CMDB 字段约束常量定义

本模块定义字段校验相关的常量和枚举类型,用于支持字段级别的数据校验功能。

主要内容:
1. 字符串校验类型枚举及预定义正则表达式
2. 前端组件类型定义
3. 时间显示格式定义
4. 默认约束配置

使用示例:
    from apps.cmdb.constants.field_constraints import (
        StringValidationType,
        DEFAULT_STRING_CONSTRAINT
    )
    
    constraint = {
        "validation_type": StringValidationType.IPV4
    }
"""
import re


class StringValidationType:
    """
    字符串校验类型枚举
    
    定义字符串字段支持的所有校验类型及其对应的正则表达式
    """
    UNRESTRICTED = "unrestricted"
    IPV4 = "ipv4"
    IPV6 = "ipv6"
    EMAIL = "email"
    MOBILE_PHONE = "mobile_phone"
    URL = "url"
    JSON = "json"
    CUSTOM = "custom"

    CHOICES = (
        (UNRESTRICTED, "无限制"),
        (IPV4, "IPv4"),
        (IPV6, "IPv6"),
        (EMAIL, "Email"),
        (MOBILE_PHONE, "手机号"),
        (URL, "URL"),
        (JSON, "JSON"),
        (CUSTOM, "自定义正则"),
    )

    # 预定义正则表达式
    # IPv4: 支持0.0.0.0 到 255.255.255.255
    # IPv6: 支持标准IPv6格式及IPv4映射格式
    # Email: 支持标准邮箱格式
    # 手机号: 支持中国大陆11位手机号(1开头,第二位3-9)
    # URL: 支持http/https/ftp协议
    REGEX_MAP = {
        IPV4: r'^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$',
        IPV6: r'^(([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}|(([0-9a-fA-F]{1,4}:){1,6}|:):((:[0-9a-fA-F]{1,4}){1,6}|:)|::([fF]{4}(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))$',
        EMAIL: r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',
        MOBILE_PHONE: r'^1[3-9]\d{9}$',
        URL: r'^(https?|ftp)://[^\s/$.?#].[^\s]*$',
    }

    @classmethod
    def get_choices_dict(cls):
        """获取选项字典"""
        return dict(cls.CHOICES)

    @classmethod
    def validate_type(cls, validation_type: str) -> bool:
        """验证校验类型是否合法"""
        return validation_type in [choice[0] for choice in cls.CHOICES]


class WidgetType:
    """
    前端组件类型枚举

    定义字符串字段在前端的展示方式:
    - SINGLE_LINE: 单行文本框(<input type="text"/>)
    - MULTI_LINE: 多行文本框(<textarea/>)

    注意: 此配置仅影响前端UI展示,不影响后端存储和校验逻辑
    """
    SINGLE_LINE = "single_line"
    MULTI_LINE = "multi_line"

    CHOICES = (
        (SINGLE_LINE, "单行"),
        (MULTI_LINE, "多行"),
    )

    @classmethod
    def validate_type(cls, widget_type: str) -> bool:
        """验证组件类型是否合法"""
        return widget_type in [choice[0] for choice in cls.CHOICES]


class TimeDisplayFormat:
    """
    时间显示格式枚举
    
    定义时间字段在前端的展示格式:
    - DATETIME: 完整日期时间(如: 2026-02-02 14:30:00)
    - DATE: 仅日期(如: 2026-02-02 00:00:00)
    
    注意: 后端统一使用时间戳存储,此配置仅影响前端展示和录入组件
    """
    DATETIME = "datetime"
    DATE = "date"

    CHOICES = (
        (DATETIME, "日期时间"),
        (DATE, "仅日期"),
    )

    @classmethod
    def validate_format(cls, display_format: str) -> bool:
        """验证显示格式是否合法"""
        return display_format in [choice[0] for choice in cls.CHOICES]


# ========== 默认约束配置 ==========

# 字符串类型默认约束: 无限制 + 单行输入
DEFAULT_STRING_CONSTRAINT = {
    "validation_type": StringValidationType.UNRESTRICTED,
    "widget_type": WidgetType.SINGLE_LINE,
    "custom_regex": ""
}

# 数字类型默认约束: 无最小最大值限制 + 允许负数
DEFAULT_NUMBER_CONSTRAINT = {
    "min_value": None,
    "max_value": None
}

# 时间类型默认约束: 完整日期时间 + 东八区
DEFAULT_TIME_CONSTRAINT = {
    "display_format": TimeDisplayFormat.DATETIME,
    # "timezone": "Asia/Shanghai"
}

# 用户提示默认值: 空字符串
USER_PROMPT = "user_prompt"
DEFAULT_USER_PROMPT = {
    USER_PROMPT: ""
}

# ========== 校验配置限制 ==========

# 自定义正则表达式最大长度(防止ReDoS攻击)
MAX_CUSTOM_REGEX_LENGTH = 200
