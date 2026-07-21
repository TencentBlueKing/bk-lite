from apps.log.models.log_group import LogGroup
from apps.core.logger import log_logger as logger


class LogGroupQueryBuilder:
    """日志分组查询构建器 - 专门处理日志分组与查询的组合逻辑"""

    DENY_ALL_QUERY = '(__bk_lite_log_scope__:"deny-1") AND (__bk_lite_log_scope__:"deny-2")'
    VALID_RULE_MODES = frozenset({"AND", "OR"})

    @classmethod
    def validate_rule_mode(cls, rule_json):
        mode = rule_json.get("mode", "AND")
        if not isinstance(mode, str) or mode.upper() not in cls.VALID_RULE_MODES:
            raise ValueError(f"Unsupported mode: {mode}")
        return mode.upper()

    @staticmethod
    def json_to_logsql_expression(rule_json):
        """将规则JSON转换为VictoriaLogs LogsQL表达式"""

        def escape_regex_value(value):
            """转义正则表达式中的特殊字符"""
            # 转义正则表达式特殊字符
            special_chars = r"\.^$*+?{}[]|()"
            escaped = str(value)
            for char in special_chars:
                escaped = escaped.replace(char, "\\" + char)
            return escaped

        def build_contains_query(field, value):
            """构建包含查询，使用正则表达式"""
            escaped_value = escape_regex_value(value)
            return f'{field}:re(".*{escaped_value}.*")'

        def build_not_contains_query(field, value):
            """构建不包含查询，使用正则表达式"""
            escaped_value = escape_regex_value(value)
            return f'!{field}:re(".*{escaped_value}.*")'

        op_map = {
            "==": lambda f, v: f'{f}:"{v}"',
            "!=": lambda f, v: f'!{f}:"{v}"',
            "contains": build_contains_query,
            "!contains": build_not_contains_query,
            "startswith": lambda f, v: f"{f}:{v}*",
            "endswith": lambda f, v: f"{f}:*{v}",
        }

        # 如果不存在规则，返回空字符串
        if not rule_json:
            return ""

        mode = LogGroupQueryBuilder.validate_rule_mode(rule_json)
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
            if valid_groups and all(item.get("status") == "empty_rule" for item in group_info):
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

    @staticmethod
    def _build_group_conditions(groups):
        """构建日志分组的查询条件"""
        conditions = []
        invalid_group_status = {}

        for group in groups:
            try:
                if not group.rule:
                    invalid_group_status[group.id] = "empty_rule"
                    continue

                condition = LogGroupQueryBuilder.json_to_logsql_expression(group.rule)
                if condition and condition.strip():
                    conditions.append(condition)
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
