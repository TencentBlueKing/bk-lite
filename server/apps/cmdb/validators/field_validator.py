# -- coding: utf-8 --
"""
CMDB 字段校验器

提供字段级别的数据校验功能,在实例创建/更新/导入时自动应用约束规则。

主要功能:
1. 字符串格式校验: IPv4/IPv6/Email/手机号/URL/JSON/自定义正则
2. 数字范围校验: 最小值/最大值/负数限制
3. 字段级统一校验入口

设计原则:
- 空值不校验(由 is_required 控制)
- 校验失败抛出 BaseAppException,包含清晰的错误信息
- 支持默认配置,兼容旧数据
- 防御性编程,避免ReDoS攻击

使用示例:
    from apps.cmdb.validators.field_validator import FieldValidator

    # 方式1: 直接校验字符串
    FieldValidator.validate_string(
        "192.168.1.1",
        {"validation_type": "ipv4", "widget_type": "single_line"}
    )

    # 方式2: 直接校验数字
    FieldValidator.validate_number(
        512,
        {"min_value": 1, "max_value": 1024},
        "int"
    )

    # 方式3: 根据属性定义自动校验(推荐)
    attr = {
        "attr_id": "server_ip",
        "attr_type": "str",
        "option": {"validation_type": "ipv4"}
    }
    FieldValidator.validate_field_by_attr("192.168.1.1", attr)
"""

import re
import json
from typing import Any, Dict

from apps.cmdb.constants.field_constraints import (
    IDENTIFIER_PATTERN,
    IDENTIFIER_ERROR_MESSAGE,
    StringValidationType,
    DEFAULT_STRING_CONSTRAINT,
    DEFAULT_NUMBER_CONSTRAINT,
    MAX_CUSTOM_REGEX_LENGTH,
)
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import cmdb_logger as logger


class ValidationTimeoutError(Exception):
    pass


def timeout_handler(signum, frame):
    raise ValidationTimeoutError("字段校验超时")


class IdentifierValidator:
    """校验模型ID、属性ID等标识符的格式"""

    @classmethod
    def is_valid(cls, identifier: str) -> bool:
        if not identifier or not isinstance(identifier, str):
            return False
        return bool(IDENTIFIER_PATTERN.match(identifier))

    @classmethod
    def get_error_message(cls, field_name: str = "ID") -> str:
        return f"{field_name}{IDENTIFIER_ERROR_MESSAGE}"


class FieldValidator:
    """
    字段校验器

    提供字段级别的数据校验功能,支持字符串格式、数字范围等多种校验规则。
    """

    @staticmethod
    def validate_string(value: Any, constraint: Dict) -> None:
        """
        字符串格式校验

        支持的校验类型:
        - unrestricted: 无限制(默认)
        - ipv4: IPv4地址格式
        - ipv6: IPv6地址格式
        - email: 邮箱地址格式
        - mobile_phone: 中国手机号格式
        - url: URL地址格式
        - json: 合法JSON格式
        - custom: 自定义正则表达式

        Args:
            value: 待校验的值
            constraint: 约束配置字典
                {
                    "validation_type": "ipv4",  # 校验类型
                    "widget_type": "single_line",  # 组件类型(不影响校验)
                    "custom_regex": ""  # 自定义正则(validation_type=custom时使用)
                }

        Raises:
            BaseAppException: 校验失败时抛出,包含具体错误信息

        Examples:
            >>> FieldValidator.validate_string("192.168.1.1", {"validation_type": "ipv4"})
            >>> FieldValidator.validate_string("test@example.com", {"validation_type": "email"})
        """
        # 空值不校验(由 is_required 控制)
        if value is None or value == "":
            return

        # 确保值为字符串类型
        if not isinstance(value, str):
            value = str(value)

        # 合并默认约束
        constraint = {**DEFAULT_STRING_CONSTRAINT, **(constraint or {})}
        validation_type = constraint.get(
            "validation_type", StringValidationType.UNRESTRICTED
        )

        # 无限制类型直接通过
        if validation_type == StringValidationType.UNRESTRICTED:
            return

        # JSON 格式特殊处理
        if validation_type == StringValidationType.JSON:
            try:
                json.loads(value)
                return
            except json.JSONDecodeError as e:
                raise BaseAppException(f"JSON格式校验失败: {str(e)}")
            except Exception as e:
                raise BaseAppException(f"JSON格式校验异常: {str(e)}")

        # 自定义正则表达式校验
        if validation_type == StringValidationType.CUSTOM:
            custom_regex = constraint.get("custom_regex", "").strip()

            # 检查正则是否为空
            if not custom_regex:
                raise BaseAppException("自定义正则表达式不能为空")

            # 检查正则长度(防止ReDoS攻击)
            if len(custom_regex) > MAX_CUSTOM_REGEX_LENGTH:
                raise BaseAppException(
                    f"自定义正则表达式长度不能超过 {MAX_CUSTOM_REGEX_LENGTH} 字符"
                )

            # 编译并校验正则
            try:
                pattern = re.compile(custom_regex)
                if not pattern.match(value):
                    raise BaseAppException(f"值 '{value}' 不符合自定义正则表达式规则")
                return

            except re.error as e:
                raise BaseAppException(f"正则表达式格式错误: {str(e)}")
            except Exception as e:
                logger.error(f"自定义正则校验异常: {e}", exc_info=True)
                raise BaseAppException(f"正则表达式校验异常: {str(e)}")

        # 预定义类型校验
        regex = StringValidationType.REGEX_MAP.get(validation_type)
        if not regex:
            raise BaseAppException(f"未知的校验类型: {validation_type}")

        try:
            pattern = re.compile(regex)
            if not pattern.match(value):
                # 获取类型的中文名称
                type_name = dict(StringValidationType.CHOICES).get(
                    validation_type, validation_type
                )
                raise BaseAppException(f"值 '{value}' 不符合 {type_name} 格式要求")
        except re.error as e:
            logger.error(f"预定义正则编译失败 [{validation_type}]: {e}", exc_info=True)
            raise BaseAppException(f"内部错误: 校验规则配置异常")

    @staticmethod
    def validate_number(value: Any, constraint: Dict, attr_type: str = "int") -> None:
        """
        数字范围校验

        支持的约束:
        - min_value: 最小值(None表示无限制)
        - max_value: 最大值(None表示无限制)

        Args:
            value: 待校验的值
            constraint: 约束配置字典
                {
                    "min_value": 1,  # 最小值,None表示无限制
                    "max_value": 1024,  # 最大值,None表示无限制
                }
            attr_type: 字段类型,可选值: "int" 或 "float"

        Raises:
            BaseAppException: 校验失败时抛出,包含具体错误信息

        Examples:
            >>> FieldValidator.validate_number(512, {"min_value": 1, "max_value": 1024}, "int")
            >>> FieldValidator.validate_number(3.14, {"min_value": 0}, "float")
        """
        # 空值不校验
        if value is None or value == "":
            return

        # 类型转换与验证
        try:
            if attr_type == "int":
                value = int(value)
            elif attr_type == "float":
                value = float(value)
            else:
                raise BaseAppException(f"不支持的数字类型: {attr_type}")
        except (ValueError, TypeError) as e:
            type_name = "整数" if attr_type == "int" else "浮点数"
            raise BaseAppException(f"值 '{value}' 不是有效的{type_name}")

        # 合并默认约束
        constraint = {**DEFAULT_NUMBER_CONSTRAINT, **(constraint or {})}
        min_value = constraint.get("min_value")
        max_value = constraint.get("max_value")
        allow_negative = constraint.get("allow_negative", True)

        # 负数检查
        if not allow_negative and value < 0:
            raise BaseAppException(f"不允许输入负数,当前值: {value}")

        # 最小值检查
        if min_value is not None:
            try:
                min_value = float(min_value) if attr_type == "float" else int(min_value)
                if value < min_value:
                    raise BaseAppException(f"值 {value} 小于最小值 {min_value}")
            except (ValueError, TypeError):
                logger.warning(f"最小值配置无效: {min_value}, 跳过校验")

        # 最大值检查
        if max_value is not None:
            try:
                max_value = float(max_value) if attr_type == "float" else int(max_value)
                if value > max_value:
                    raise BaseAppException(f"值 {value} 大于最大值 {max_value}")
            except (ValueError, TypeError):
                logger.warning(f"最大值配置无效: {max_value}, 跳过校验")

    @staticmethod
    def validate_field_by_attr(value: Any, attr: Dict) -> None:
        """
        根据属性定义自动选择合适的校验方法

        这是推荐的统一校验入口,会根据字段类型自动选择对应的校验逻辑。

        Args:
            value: 字段值
            attr: 属性定义字典
                {
                    "attr_id": "server_ip",
                    "attr_type": "str",  # str/int/float/time/...
                    "option": {...}  # 对应类型的约束配置

                }

        Raises:
            BaseAppException: 校验失败时抛出

        Examples:
            >>> attr = {
            ...     "attr_id": "server_ip",
            ...     "attr_type": "str",
            ...     "option": {"validation_type": "ipv4"}
            ...
            ... }
            >>> FieldValidator.validate_field_by_attr("192.168.1.1", attr)
        """
        if not attr:
            return

        attr_type = attr.get("attr_type")
        option = attr.get("option", {})

        try:
            # 字符串类型校验
            if attr_type == "str":
                if option:
                    FieldValidator.validate_string(value, option)

            # 整数类型校验
            elif attr_type == "int":
                if option:
                    FieldValidator.validate_number(value, option, "int")

            # 浮点数类型校验
            elif attr_type == "float":
                if option:
                    FieldValidator.validate_number(value, option, "float")

            # 其他类型暂不处理(password/user/organization/bool/enum/time等)
            # 这些类型由现有逻辑处理或不需要额外校验
        except Exception as e:
            # 捕获意外异常,记录日志并抛出通用错误
            attr_id = attr.get("attr_id", "unknown")
            logger.error(f"字段 {attr_id} 校验异常: {e}", exc_info=True)
            raise BaseAppException(f"字段校验失败: {getattr(e, 'message', str(e))}")

    @staticmethod
    def validate_instance_data(instance_data: Dict, attrs: list) -> list:
        """
        批量校验实例数据中的所有字段

        Args:
            instance_data: 实例数据字典（属性键值对）
            attrs: 属性定义列表

        Returns:
            list: 校验错误列表,格式:
                [
                    {
                        "field": "server_ip",
                        "value": "999.999.999.999",
                        "error": "值 '999.999.999.999' 不符合 IPv4 格式要求"
                    },
                    ...
                ]
        """
        validation_errors = []

        for attr in attrs:
            attr_id = attr.get("attr_id")

            # 只校验实例数据中存在的字段
            if attr_id not in instance_data:
                continue

            value = instance_data[attr_id]

            try:
                FieldValidator.validate_field_by_attr(value, attr)
            except BaseAppException as e:
                validation_errors.append(
                    {
                        "field": attr_id,
                        "field_name": attr.get("attr_name", attr_id),
                        "value": value,
                        "error": getattr(e, "message", str(e)),
                    }
                )
            except Exception as e:
                logger.error(f"字段 {attr_id} 校验异常: {e}", exc_info=True)
                validation_errors.append(
                    {
                        "field": attr_id,
                        "field_name": attr.get("attr_name", attr_id),
                        "value": value,
                        "error": f"校验异常: {getattr(e, 'message', str(e))}",
                    }
                )

        return validation_errors
