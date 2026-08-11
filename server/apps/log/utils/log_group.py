import json
import re

from django.conf import settings

from apps.core.logger import log_logger as logger
from apps.log.models.log_group import LogGroup


class LogGroupQueryBuilder:
    """日志分组查询构建器 - 专门处理日志分组与查询的组合逻辑"""

    DENY_ALL_QUERY = '(__bk_lite_log_scope__:"deny-1") AND (__bk_lite_log_scope__:"deny-2")'
    VALID_RULE_MODES = frozenset({"AND", "OR"})
    MODE_VALID = "valid"
    MODE_LEGACY_OR = "legacy_or"
    MODE_LEGACY_EMPTY_RULE = "legacy_empty_rule"
    MODE_INVALID = "invalid"
    SUPPORTED_OPERATIONS = frozenset({"==", "!=", "contains", "!contains", "startswith", "endswith"})
    ACCEPTED_FIELD_PATTERN = re.compile(r"^[A-Za-z_@][A-Za-z0-9_.@/-]*$")
    RAW_FIELD_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
    UNSAFE_QUOTED_VALUE_PATTERN = re.compile(r'["\\\x00-\x1f\x7f]')
    UNSAFE_LEGACY_WILDCARD_PATTERN = re.compile(
        r"[*|()]|^\s*[!-]|(?:^|\s)(?:AND|OR|NOT)(?:\s|$)",
        re.IGNORECASE,
    )

    @classmethod
    def classify_rule_mode(cls, rule_json):
        """按历史运行语义分类规则模式，不回显不可信的原始值。"""
        if not isinstance(rule_json, dict):
            return cls.MODE_INVALID, None

        mode = rule_json.get("mode", "AND")
        if not isinstance(mode, str):
            return cls.MODE_INVALID, None

        normalized_mode = mode.upper()
        if normalized_mode in cls.VALID_RULE_MODES:
            return cls.MODE_VALID, normalized_mode

        # 旧实现把所有未知字符串解释为 OR；该分类只供显式迁移兼容使用。
        return cls.MODE_LEGACY_OR, None

    @classmethod
    def validate_rule_mode(cls, rule_json):
        classification, normalized_mode = cls.classify_rule_mode(rule_json)
        if classification != cls.MODE_VALID:
            raise ValueError("Rule mode must be AND or OR")
        return normalized_mode

    @classmethod
    def validate_rule(cls, rule_json, *, allow_legacy_or=False, require_legacy_safe=False):
        mode, used_legacy_or = cls._resolve_rule_mode(rule_json, allow_legacy_or=allow_legacy_or)
        conditions = rule_json.get("conditions", [])
        if not isinstance(conditions, list):
            raise ValueError("Rule conditions must be a list")

        for condition in conditions:
            if not isinstance(condition, dict):
                raise ValueError("Each rule condition must be an object")
            if set(("field", "op", "value")) - condition.keys():
                raise ValueError("Each rule condition must include field, op and value")
            if not isinstance(condition["field"], str) or not condition["field"].strip():
                raise ValueError("Rule condition field must be a non-empty string")
            if not isinstance(condition["op"], str) or condition["op"] not in cls.SUPPORTED_OPERATIONS:
                raise ValueError("Rule condition op is unsupported")
            if condition["value"] is None or isinstance(condition["value"], (dict, list)):
                raise ValueError("Rule condition value must be a scalar")
            if not cls.ACCEPTED_FIELD_PATTERN.fullmatch(condition["field"]):
                raise ValueError("Rule condition field contains unsupported LogsQL syntax")

            value_text = str(condition["value"])
            if cls.UNSAFE_QUOTED_VALUE_PATTERN.search(value_text):
                raise ValueError("Rule condition value contains unsupported LogsQL syntax")
            if (
                require_legacy_safe
                and condition["op"] in {"startswith", "endswith"}
                and cls.UNSAFE_LEGACY_WILDCARD_PATTERN.search(value_text)
            ):
                raise ValueError("Rule wildcard condition value is unsafe for legacy LogsQL syntax")

        return mode, used_legacy_or

    @classmethod
    def classify_rule(cls, rule_json):
        classification, normalized_mode = cls.classify_rule_mode(rule_json)
        try:
            cls.validate_rule(rule_json, allow_legacy_or=classification == cls.MODE_LEGACY_OR)
        except (TypeError, ValueError):
            return cls.MODE_INVALID, None
        return classification, normalized_mode

    @classmethod
    def _resolve_rule_mode(cls, rule_json, *, allow_legacy_or=False):
        classification, normalized_mode = cls.classify_rule_mode(rule_json)
        if classification == cls.MODE_VALID:
            return normalized_mode, False
        if classification == cls.MODE_LEGACY_OR and allow_legacy_or:
            return "OR", True
        raise ValueError("Rule mode must be AND or OR")

    @staticmethod
    def _configured_legacy_or_group_ids():
        configured_ids = getattr(settings, "LOG_GROUP_LEGACY_OR_GROUP_IDS", frozenset())
        if isinstance(configured_ids, str):
            configured_ids = configured_ids.split(",")
        try:
            return frozenset(str(group_id).strip() for group_id in configured_ids if str(group_id).strip())
        except TypeError:
            return frozenset()

    @staticmethod
    def _legacy_migration_mode_enabled():
        return getattr(settings, "LOG_GROUP_RULE_MODE_ENFORCEMENT", "strict") == "legacy"

    @staticmethod
    def _is_legacy_falsey_non_object(rule_json):
        if rule_json is None:
            return True
        if isinstance(rule_json, (str, list)):
            return not rule_json
        if type(rule_json) in (bool, int, float):
            return not rule_json
        return False

    @classmethod
    def _encode_logsql_field(cls, field):
        """把字段名编码为 LogsQL 字段标识符，防止字段名改变查询结构。"""
        if cls.RAW_FIELD_PATTERN.fullmatch(field):
            return field
        return cls._encode_logsql_string(field)

    @staticmethod
    def _encode_logsql_string(value):
        """按 LogsQL 双引号字符串规则编码不可信字面量。"""
        return json.dumps(str(value), ensure_ascii=False)

    @staticmethod
    def _escape_regex_value(value):
        """把不可信值转换为只匹配其字面量的正则片段。"""
        return re.escape(str(value))

    @classmethod
    def _strict_operation_map(cls):
        def regex_filter(field, pattern, *, negate=False):
            prefix = "!" if negate else ""
            return f"{prefix}{cls._encode_logsql_field(field)}:re({cls._encode_logsql_string(pattern)})"

        return {
            "==": lambda field, value: (
                f"{cls._encode_logsql_field(field)}:{cls._encode_logsql_string(value)}"
            ),
            "!=": lambda field, value: (
                f"!{cls._encode_logsql_field(field)}:{cls._encode_logsql_string(value)}"
            ),
            "contains": lambda field, value: regex_filter(
                field, f".*{cls._escape_regex_value(value)}.*"
            ),
            "!contains": lambda field, value: regex_filter(
                field, f".*{cls._escape_regex_value(value)}.*", negate=True
            ),
            "startswith": lambda field, value: (
                f"{cls._encode_logsql_field(field)}:{cls._encode_logsql_string(value)}*"
            ),
            "endswith": lambda field, value: regex_filter(
                field, f".*{cls._escape_regex_value(value)}$"
            ),
        }

    @staticmethod
    def _legacy_operation_map():
        def escape_regex_value(value):
            special_chars = r"\.^$*+?{}[]|()"
            escaped = str(value)
            for char in special_chars:
                escaped = escaped.replace(char, "\\" + char)
            return escaped

        return {
            "==": lambda field, value: f'{field}:"{value}"',
            "!=": lambda field, value: f'!{field}:"{value}"',
            "contains": lambda field, value: f'{field}:re(".*{escape_regex_value(value)}.*")',
            "!contains": lambda field, value: f'!{field}:re(".*{escape_regex_value(value)}.*")',
            "startswith": lambda field, value: f"{field}:{value}*",
            "endswith": lambda field, value: f"{field}:*{value}",
        }

    @classmethod
    def json_to_logsql_expression(cls, rule_json, *, allow_legacy_or=False, preserve_legacy_structure=False):
        """将规则JSON转换为VictoriaLogs LogsQL表达式"""

        # 如果不存在规则，返回空字符串
        if rule_json == {}:
            return ""

        if preserve_legacy_structure:
            mode, _ = cls._resolve_rule_mode(rule_json, allow_legacy_or=allow_legacy_or)
            op_map = cls._legacy_operation_map()
        else:
            mode, _ = cls.validate_rule(rule_json, allow_legacy_or=allow_legacy_or)
            op_map = cls._strict_operation_map()
        connector = " AND " if mode == "AND" else " OR "

        expressions = []
        for rule in rule_json.get("conditions", []):
            field = rule["field"]
            op = rule["op"]
            value = rule["value"]
            expr_func = op_map.get(op)
            if expr_func:
                expressions.append(expr_func(field, value))
            else:
                raise ValueError(f"Unsupported operation: {op}")

        if not expressions:
            return ""

        if len(expressions) == 1:
            return expressions[0]
        else:
            return f"({connector.join(expressions)})"

    @staticmethod
    def build_query_with_groups(user_query, log_group_ids, resolved_groups=None):
        """构建包含日志分组规则的查询语句

        Args:
            user_query (str): 用户输入的查询语句
            log_group_ids (list): 日志分组ID列表
            resolved_groups (list, optional): 已解析的 LogGroup 对象列表，传入时跳过数据库查询

        Returns:
            tuple: (final_query, group_info)
                   final_query: 最终查询语句
                   group_info: 使用的分组信息（用于调试和日志）
        """
        if not log_group_ids:
            return user_query, []

        normalized_ids = [str(group_id).strip() for group_id in log_group_ids if str(group_id).strip()]
        has_default = "default" in normalized_ids

        if resolved_groups is not None:
            valid_groups = resolved_groups
        else:
            valid_groups = LogGroupQueryBuilder._get_valid_groups(normalized_ids)

        if not valid_groups:
            return LogGroupQueryBuilder.DENY_ALL_QUERY, []

        # 构建分组条件
        group_conditions, invalid_group_status = LogGroupQueryBuilder._build_group_conditions(valid_groups)

        group_info = []
        for group in valid_groups:
            group_info.append(
                {
                    "id": group.id,
                    "name": group.name,
                    "status": invalid_group_status.get(group.id, "applied"),
                }
            )

        if has_default:
            if not any(item.get("id") == "default" for item in group_info):
                group_info.insert(0, {"id": "default", "name": "Default", "status": "empty_rule"})
            return user_query.strip() if user_query else "*", group_info

        if not group_conditions:
            empty_rule_statuses = {"empty_rule"}
            if LogGroupQueryBuilder._legacy_migration_mode_enabled():
                empty_rule_statuses.add(LogGroupQueryBuilder.MODE_LEGACY_EMPTY_RULE)
            if valid_groups and all(item.get("status") in empty_rule_statuses for item in group_info):
                return user_query.strip() if user_query else "*", group_info
            return LogGroupQueryBuilder.DENY_ALL_QUERY, group_info

        # 组合最终查询
        final_query = LogGroupQueryBuilder._combine_query_and_groups(user_query, group_conditions)

        return final_query, group_info

    @staticmethod
    def _get_valid_groups(log_group_ids):
        """获取有效的日志分组对象"""
        try:
            return list(LogGroup.objects.filter(id__in=log_group_ids))
        except Exception:
            return []

    @classmethod
    def _build_group_conditions(cls, groups):
        """构建日志分组的查询条件"""
        conditions = []
        invalid_group_status = {}
        legacy_or_group_ids = cls._configured_legacy_or_group_ids()
        legacy_migration_mode = cls._legacy_migration_mode_enabled()

        for group in groups:
            try:
                if group.rule == {}:
                    invalid_group_status[group.id] = "empty_rule"
                    continue
                if legacy_migration_mode and cls._is_legacy_falsey_non_object(group.rule):
                    invalid_group_status[group.id] = cls.MODE_LEGACY_EMPTY_RULE
                    continue

                allow_legacy_or = legacy_migration_mode or str(group.id) in legacy_or_group_ids
                classification, _ = cls.classify_rule_mode(group.rule)
                condition = cls.json_to_logsql_expression(
                    group.rule,
                    allow_legacy_or=allow_legacy_or,
                    preserve_legacy_structure=legacy_migration_mode,
                )
                if condition and condition.strip():
                    conditions.append(condition)
                    if classification == cls.MODE_LEGACY_OR:
                        invalid_group_status[group.id] = cls.MODE_LEGACY_OR
                else:
                    invalid_group_status[group.id] = "empty_rule"
            except Exception:
                invalid_group_status[group.id] = "invalid_rule"
                continue

        return conditions, invalid_group_status

    @staticmethod
    def _combine_query_and_groups(user_query, group_conditions):
        """组合用户查询和分组条件"""

        # 清理用户查询
        user_query = user_query.strip() if user_query else ""

        # 如果没有有效的分组条件，直接返回用户查询
        if not group_conditions:
            return LogGroupQueryBuilder.DENY_ALL_QUERY

        # 构建分组过滤器
        group_filter = f"({' OR '.join(group_conditions)})" if len(group_conditions) > 1 else group_conditions[0]

        logger.debug(
            "查询合并处理",
            extra={
                "user_query": user_query[:100] + "..." if len(user_query) > 100 else user_query,
                "group_filter": group_filter[:100] + "..." if len(group_filter) > 100 else group_filter,
                "has_aggregation": bool(user_query and "|" in user_query),
            },
        )

        # 聚合查询处理：将分组条件合并到过滤部分
        if user_query and "|" in user_query:
            query_parts = user_query.split("|", 1)
            filter_part = query_parts[0].strip()
            aggregation_part = query_parts[1].strip()

            # 构建合并的过滤条件
            if filter_part and group_filter:
                combined_filter = f"({filter_part}) AND ({group_filter})"
            elif group_filter:
                combined_filter = group_filter
            else:
                combined_filter = filter_part or "*"

            final_query = f"{combined_filter} | {aggregation_part}"
            logger.debug("聚合查询合并完成", extra={"final_query": final_query[:200] + "..." if len(final_query) > 200 else final_query})
            return final_query

        # 普通查询处理
        if user_query and group_filter:
            final_query = f"({user_query}) AND ({group_filter})"
        elif group_filter:
            final_query = group_filter
        else:
            final_query = user_query if user_query else "*"

        logger.debug("查询合并完成", extra={"final_query": final_query[:200] + "..." if len(final_query) > 200 else final_query})
        return final_query

    @staticmethod
    def validate_log_groups(log_group_ids):
        """验证日志分组是否存在且有效

        Args:
            log_group_ids (list): 日志分组ID列表

        Returns:
            tuple: (is_valid, error_message, valid_groups)
        """
        if not log_group_ids:
            return True, "", []

        if not isinstance(log_group_ids, list):
            return False, "log_groups 必须是一个数组", []

        normalized_ids = [str(group_id).strip() for group_id in log_group_ids if str(group_id).strip() and str(group_id).strip() != "default"]

        if not normalized_ids:
            return True, "", []

        try:
            existing_groups = list(LogGroup.objects.filter(id__in=normalized_ids))
            existing_ids = {g.id for g in existing_groups}

            # 检查是否有不存在的分组ID
            missing_ids = set(normalized_ids) - existing_ids
            if missing_ids:
                return False, f"以下日志分组不存在: {', '.join(missing_ids)}", existing_groups

            return True, "", existing_groups

        except Exception as e:
            return False, f"查询日志分组时发生错误: {str(e)}", []
