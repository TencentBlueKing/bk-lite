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
    def validate_table_option(option: Any) -> None:
        """
        校验 table 字段的 option 配置

        option 应该是列定义数组：
        [
            {
                "column_id": "name",
                "column_name": "名称",
                "column_type": "str",  # str 或 number
                "order": 1
            },
            ...
        ]

        Args:
            option: table 字段的 option 配置

        Raises:
            BaseAppException: 校验失败时抛出
        """
        if not isinstance(option, list):
            raise BaseAppException("table 字段 option 必须是数组")

        if len(option) == 0:
            raise BaseAppException("table 字段至少需要定义一列")

        column_ids = set()
        for idx, col in enumerate(option):
            if not isinstance(col, dict):
                raise BaseAppException(f"第{idx + 1}列配置必须是对象")

            # 校验必填字段
            column_id = col.get("column_id")
            column_name = col.get("column_name")
            column_type = col.get("column_type")
            order = col.get("order")

            if not column_id:
                raise BaseAppException(f"第{idx + 1}列缺少 column_id")
            if not column_name:
                raise BaseAppException(f"第{idx + 1}列缺少 column_name")
            if not column_type:
                raise BaseAppException(f"第{idx + 1}列缺少 column_type")
            if order is None:
                raise BaseAppException(f"第{idx + 1}列缺少 order")

            # 校验 column_id 格式（使用与 attr_id 相同的规则）
            if not IdentifierValidator.is_valid(column_id):
                raise BaseAppException(
                    f"第{idx + 1}列 column_id '{column_id}' "
                    + IdentifierValidator.get_error_message("列ID")
                )

            # 校验 column_id 唯一性
            if column_id in column_ids:
                raise BaseAppException(f"列ID '{column_id}' 重复")
            column_ids.add(column_id)

            # 校验 column_type 只能是 str 或 number
            if column_type not in {"str", "number"}:
                raise BaseAppException(
                    f"第{idx + 1}列的 column_type 只能是 'str' 或 'number'，当前值: '{column_type}'"
                )

            # 校验 order 为正整数
            try:
                order_int = int(order)
                if order_int < 1:
                    raise BaseAppException(f"第{idx + 1}列的 order 必须 >= 1")
            except (ValueError, TypeError):
                raise BaseAppException(f"第{idx + 1}列的 order 必须是整数")

    @staticmethod
    def validate_table_value(value: Any, option: list, attr_id: str = "table") -> None:
        """
        校验 table 字段的值

        value 应该是 JSON 字符串或已解析的数组：
        [
            {"name": "disk-a", "size": 100},
            {"name": "disk-b", "size": 200}
        ]

        Args:
            value: table 字段值（JSON string 或 list）
            option: 列定义（已校验过的）
            attr_id: 字段 ID（用于错误提示）

        Raises:
            BaseAppException: 校验失败时抛出
        """
        # 空值不校验
        if value is None or value == "" or value == []:
            return

        # 统一为 rows 结构
        if isinstance(value, str):
            try:
                rows = json.loads(value)
            except json.JSONDecodeError as e:
                raise BaseAppException(f"table 字段值不是合法的 JSON 格式: {str(e)}")
        elif isinstance(value, list):
            rows = value
        else:
            raise BaseAppException(
                f"table 字段值必须是 JSON 字符串或数组，当前类型: {type(value)}"
            )

        if not isinstance(rows, list):
            raise BaseAppException("table 字段值解析后必须是数组")

        # 构建列ID到类型的映射
        column_map = {col["column_id"]: col["column_type"] for col in option}

        # 校验每一行
        for row_idx, row in enumerate(rows):
            if not isinstance(row, dict):
                raise BaseAppException(
                    f"第{row_idx + 1}行数据必须是对象，当前类型: {type(row)}"
                )

            # 校验行的键必须是定义的 column_id 子集
            for key in row.keys():
                if key not in column_map:
                    raise BaseAppException(
                        f"第{row_idx + 1}行包含未定义的列 '{key}'，允许的列: {list(column_map.keys())}"
                    )

            # 校验 number 列的值必须可转为数值
            for col_id, col_type in column_map.items():
                if col_id not in row:
                    continue

                cell_value = row[col_id]

                # 空值允许
                if cell_value is None or cell_value == "":
                    continue

                if col_type == "number":
                    try:
                        float(cell_value)
                    except (ValueError, TypeError):
                        raise BaseAppException(
                            f"第{row_idx + 1}行，列 '{col_id}' 的值 '{cell_value}' 不是有效的数字"
                        )

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
                    "attr_type": "str",  # str/int/float/time/table/...
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

            # 表格类型校验
            elif attr_type == "table":
                if option:
                    # 先校验 option 配置
                    FieldValidator.validate_table_option(option)
                    # 再校验值
                    FieldValidator.validate_table_value(
                        value, option, attr.get("attr_id", "table")
                    )

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
