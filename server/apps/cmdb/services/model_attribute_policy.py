"""CMDB 模型字段定义策略。

该模块承载枚举字段规则与默认值归一逻辑；``ModelManage`` 保留同名兼容入口，
避免改变现有 HTTP、OpenAPI、NATS、内部服务和测试 patch 接缝。
"""

from typing import Any

from apps.cmdb.constants.constants import ENUM_SELECT_MODE_DEFAULT
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import cmdb_logger as logger


class ModelAttributePolicy:
    """模型字段定义的无状态策略集合。"""

    @staticmethod
    def _normalize_default_value(raw_value: Any) -> list[str]:
        if raw_value in (None, ""):
            return []

        source = raw_value if isinstance(raw_value, list) else [raw_value]
        seen: set[str] = set()
        normalized: list[str] = []
        for item in source:
            value = str(item or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        return normalized

    @staticmethod
    def sanitize_attr_default_value(attr: dict, log_context: str = "") -> dict:
        item = dict(attr)
        normalized = ModelAttributePolicy._normalize_default_value(item.get("default_value"))
        if item.get("attr_type") != "enum":
            item["default_value"] = normalized
            return item

        runtime_options = ModelAttributePolicy.resolve_runtime_enum_options(item)
        valid_ids = {str(option.get("id")).strip() for option in runtime_options if isinstance(option, dict) and str(option.get("id", "")).strip()}
        sanitized = [value for value in normalized if value in valid_ids]
        select_mode = item.get("enum_select_mode", ENUM_SELECT_MODE_DEFAULT)
        if select_mode != "multiple":
            sanitized = sanitized[:1]

        removed_values = [value for value in normalized if value not in sanitized]
        if removed_values:
            logger.info(
                "[ModelDefaultValue] pruned stale defaults context=%s attr_id=%s removed=%s rule_type=%s",
                log_context or "runtime",
                item.get("attr_id"),
                removed_values,
                item.get("enum_rule_type", "custom"),
            )

        item["default_value"] = sanitized
        return item

    @staticmethod
    def normalize_enum_public_binding(attr_info: dict, current_attr: dict | None = None) -> dict:
        """规范化 enum 公共选项库绑定信息并回填 option 快照。"""
        if attr_info.get("attr_type") != "enum":
            return attr_info

        option_value = attr_info.get("option")
        if isinstance(option_value, dict) and option_value.get("enum_rule_type"):
            attr_info["enum_rule_type"] = option_value.get("enum_rule_type", "custom")
            attr_info["public_library_id"] = option_value.get("public_library_id")
            if "enum_select_mode" in option_value:
                attr_info["enum_select_mode"] = option_value.get("enum_select_mode")
            attr_info["option"] = option_value.get("option", [])

        enum_rule_type = attr_info.get("enum_rule_type", "custom")
        attr_info["enum_rule_type"] = enum_rule_type

        if enum_rule_type == "public_library":
            public_library_id = attr_info.get("public_library_id")
            if not public_library_id:
                raise BaseAppException("绑定公共选项库时 public_library_id 必填")

            from apps.cmdb.services.public_enum_library import get_library_or_raise

            library = get_library_or_raise(public_library_id)
            attr_info["option"] = library.options
            attr_info["public_library_id"] = public_library_id

            logger.info(
                "[EnumPublicBinding] normalized attr_id=%s, enum_rule_type=%s, public_library_id=%s",
                attr_info.get("attr_id"),
                enum_rule_type,
                public_library_id,
            )
        else:
            attr_info["enum_rule_type"] = "custom"
            attr_info["public_library_id"] = None

        return attr_info

    @staticmethod
    def validate_enum_rule_immutable(current_attr: dict, incoming_attr: dict) -> None:
        """禁止已创建的枚举字段切换选项规则来源。"""
        if current_attr.get("attr_type") != "enum":
            return
        if incoming_attr.get("attr_type") != "enum":
            return

        current_rule = current_attr.get("enum_rule_type", "custom")
        incoming_rule = incoming_attr.get("enum_rule_type", "custom")

        if current_rule != incoming_rule:
            raise BaseAppException(f"枚举字段创建后规则类型不可切换（当前: {current_rule}）")

    @staticmethod
    def ensure_enum_select_mode(attr_info: dict) -> dict:
        """为枚举字段补齐默认选择模式。"""
        if attr_info.get("attr_type") != "enum":
            return attr_info

        if "enum_select_mode" not in attr_info:
            attr_info["enum_select_mode"] = ENUM_SELECT_MODE_DEFAULT

        return attr_info

    @staticmethod
    def validate_enum_select_mode_immutable(current_attr: dict, incoming_attr: dict) -> None:
        """禁止已创建的枚举字段切换单选/多选模式。"""
        if current_attr.get("attr_type") != "enum":
            return
        if incoming_attr.get("attr_type") != "enum":
            return

        current_mode = current_attr.get("enum_select_mode", ENUM_SELECT_MODE_DEFAULT)
        incoming_mode = incoming_attr.get("enum_select_mode", current_mode)

        if current_mode != incoming_mode:
            raise BaseAppException(f"枚举字段创建后选择模式不可切换（当前: {current_mode}）")

    @staticmethod
    def resolve_runtime_enum_options(attr: dict) -> list[dict]:
        """解析枚举运行时选项，公共库不可用时回退字段快照。"""
        if attr.get("attr_type") != "enum":
            return []

        enum_rule_type = attr.get("enum_rule_type", "custom")
        option = attr.get("option", [])

        if enum_rule_type != "public_library":
            return option if isinstance(option, list) else []

        public_library_id = str(attr.get("public_library_id") or "").strip()
        if not public_library_id:
            return option if isinstance(option, list) else []

        try:
            from apps.cmdb.services.public_enum_library import get_library_or_raise

            library = get_library_or_raise(public_library_id)
            runtime_options = library.options
            return runtime_options if isinstance(runtime_options, list) else []
        except Exception as e:
            logger.warning(
                "[EnumPublicBinding] resolve_runtime_enum_options fallback to snapshot, public_library_id=%s, error=%s",
                public_library_id,
                e,
            )
            return option if isinstance(option, list) else []
