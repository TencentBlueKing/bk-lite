# -- coding: utf-8 --
"""
CMDB 字段校验器模块

提供字段级别的数据校验功能,支持:
- 字符串格式校验(IPv4/IPv6/Email/手机号/URL/JSON/自定义正则)
- 数字范围校验(最小值/最大值/负数限制)
- 时间格式校验

使用示例:
    from apps.cmdb.validators import FieldValidator
    
    # 校验IPv4地址
    FieldValidator.validate_string(
        "192.168.1.1",
        {"validation_type": "ipv4"}
    )
    
    # 校验数字范围
    FieldValidator.validate_number(
        512,
        {"min_value": 1, "max_value": 1024},
        "int"
    )
"""
from apps.cmdb.validators.field_validator import FieldValidator

__all__ = ['FieldValidator']
