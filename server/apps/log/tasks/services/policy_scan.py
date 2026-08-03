import hashlib
import json
import os
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

# 单条告警快照列表最大保留条数（保留最新的 N 条）
# 超出后丢弃最旧记录，防止 S3 对象无限膨胀。可通过环境变量调整。
try:
    _MAX_ALERT_SNAPSHOTS = int(os.getenv("LOG_MAX_ALERT_SNAPSHOTS", "500"))
    if _MAX_ALERT_SNAPSHOTS <= 0:
        raise ValueError("必须为正整数")
except ValueError:
    _MAX_ALERT_SNAPSHOTS = 500

from django.db import IntegrityError, transaction
from django.utils import timezone as django_timezone
from django.utils.dateparse import parse_datetime

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import celery_logger as logger
from apps.log.constants.alert_policy import AlertConstants
from apps.log.constants.database import DatabaseConstants
from apps.log.constants.web import WebConstants
from apps.log.models.policy import Alert, AlertSnapshot, Event, EventRawData
from apps.log.services.alert_lifecycle_notify import LogAlertLifecycleNotifier
from apps.log.tasks.utils.policy import period_to_seconds
from apps.log.utils.log_group import LogGroupQueryBuilder
from apps.log.utils.query_log import VictoriaMetricsAPI
from apps.monitor.utils.system_mgmt_api import SystemMgmtUtils


class LogPolicyScan:
    _ALERT_NAME_TOKEN_RE = re.compile(r"\$\{([^}]+)\}")

    def __init__(self, policy, scan_time=None, window_start=None, window_end=None, execution_key=None, cursor_time=None):
        self.policy = policy
        self.vlogs_api = VictoriaMetricsAPI()
        self.scan_time = scan_time or policy.last_run_time
        self.window_start = window_start
        self.window_end = window_end
        self.execution_key = execution_key
        self.cursor_time = cursor_time

    def _get_scan_window(self):
        window_start = getattr(self, "window_start", None)
        window_end = getattr(self, "window_end", None)
        if window_start is not None and window_end is not None:
            return window_start, window_end

        end_timestamp = int(self.scan_time.timestamp())
        period_seconds = period_to_seconds(self.policy.period)
        start_timestamp = end_timestamp - period_seconds
        return start_timestamp, end_timestamp

    def _build_event_id(self, source_id):
        execution_key = getattr(self, "execution_key", None)
        if execution_key is None:
            start_timestamp, end_timestamp = self._get_scan_window()
            execution_key = f"{start_timestamp}:{end_timestamp}"
        identity = f"{self.policy.id}:{execution_key}:{source_id}"
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]

    def _find_existing_events(self, event_ids, source_ids):
        existing_by_id = {event.id: event for event in Event.objects.filter(id__in=event_ids).select_related("alert")}
        missing_source_ids = {source_id for event_id, source_id in zip(event_ids, source_ids) if event_id not in existing_by_id}
        if not missing_source_ids:
            return existing_by_id, {}

        legacy_events = Event.objects.filter(
            policy_id=self.policy.id,
            source_id__in=missing_source_ids,
        ).select_related("alert")
        cursor_time = getattr(self, "cursor_time", None)
        if cursor_time is None:
            # 旧版本首次扫描失败时不会推进 last_run_time，重试时 safe_time 可能已变化；
            # 此时此前写入的随机 UUID Event 仍属于这次未完成的首次执行。
            legacy_events = legacy_events.filter(event_time__lte=self.scan_time)
        else:
            legacy_events = legacy_events.filter(
                event_time__gt=cursor_time,
                event_time__lte=self.scan_time,
            )

        legacy_by_source = {}
        for event in legacy_events.order_by("event_time"):
            legacy_by_source[event.source_id] = event
        return existing_by_id, legacy_by_source

    def _get_keyword_sample_limit(self, alert_condition):
        """获取关键字告警样本条数限制"""
        limit = alert_condition.get("limit", 5)
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 5
        return max(limit, 1)

    def _normalize_group_by(self, group_by):
        if not group_by:
            return []
        if isinstance(group_by, str):
            return [group_by]
        return [field for field in group_by if field]

    def _parse_count_value(self, raw_value, default=0):
        try:
            return int(float(str(raw_value))) if raw_value not in [None, ""] else default
        except (TypeError, ValueError):
            logger.warning(f"Failed to parse count value for policy {self.policy.id}: {raw_value}")
            return default

    def _build_keyword_group_query(self, final_query, group_by):
        by_fields = ", ".join(group_by)
        return f"{final_query} | stats by ({by_fields}) count() as total_count"

    def _escape_log_query_value(self, value):
        return str(value).replace("\\", "\\\\").replace('"', '\\"')

    def _build_exact_field_filter(self, field, value):
        if field == "_stream" and isinstance(value, str) and value.startswith("{") and value.endswith("}"):
            return f"{field}:{value}"
        escaped_value = self._escape_log_query_value(value)
        return f'{field}:="{escaped_value}"'

    def _build_group_sample_query(self, final_query, group_values):
        filters = []
        for field, value in group_values.items():
            filters.append(self._build_exact_field_filter(field, value))
        if not filters:
            return final_query
        group_filter = " AND ".join(filters)

        query = (final_query or "").strip()
        if not query or query == "*":
            return group_filter
        return f"{query} | filter {group_filter}"

    def _extract_group_values(self, result, group_by):
        group_values = {}
        for field in group_by:
            value = result.get(field)
            if value in [None, ""]:
                return {}
            group_values[field] = value
        return group_values

    def _build_group_source_id(self, group_values):
        canonical = json.dumps(group_values, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
        return f"policy_{self.policy.id}_{digest}"

    def _get_keyword_match_count(self, query, start_timestamp, end_timestamp):
        """获取关键字告警真实命中数量"""
        count_query = f"{query} | stats count() as total_count"
        count_result = self.vlogs_api.query(
            query=count_query,
            start=start_timestamp,
            end=end_timestamp,
            limit=1,
        )
        if not count_result:
            return 0

        raw_total = count_result[0].get("total_count", 0)
        try:
            return int(float(str(raw_total))) if raw_total not in [None, ""] else 0
        except (TypeError, ValueError):
            logger.warning(f"Failed to parse keyword match count for policy {self.policy.id}: {raw_total}")
            return 0

    def keyword_alert_detection(self):
        """关键字告警检测"""
        events = []

        try:
            start_timestamp, end_timestamp = self._get_scan_window()

            # 构建查询条件
            alert_condition = self.policy.alert_condition
            query = alert_condition.get("query", "")

            if not query:
                logger.warning(f"policy {self.policy.id} has empty query for keyword alert")
                return events

            # 应用日志分组规则
            final_query = self._build_query_with_log_groups(query)

            sample_limit = self._get_keyword_sample_limit(alert_condition)
            group_by = self._normalize_group_by(alert_condition.get("group_by", []))
            if group_by:
                return self._keyword_grouped_alert_detection(final_query, group_by, sample_limit, start_timestamp, end_timestamp)

            # 查询日志
            logs = self.vlogs_api.query(
                query=final_query,
                start=start_timestamp,
                end=end_timestamp,
                limit=sample_limit,
            )

            if logs:
                total_count = self._get_keyword_match_count(final_query, start_timestamp, end_timestamp)
                if total_count <= 0:
                    total_count = len(logs)

                # 关键字告警按策略聚合，所有匹配日志合并到一个告警中
                source_id = f"policy_{self.policy.id}"
                content = f"{self._render_alert_name()}: 检测到 {total_count} 条匹配日志"
                events.append(
                    {
                        "source_id": source_id,
                        "level": self.policy.alert_level,
                        "content": content,
                        "value": total_count,
                        "raw_data": logs[:sample_limit],  # 只保留少量样本日志作为原始数据
                    }
                )

            return events

        except Exception as e:
            logger.error(f"keyword alert detection failed for policy {self.policy.id}: {e}")
            raise

    def _fetch_group_sample(self, idx, group_values, total_count, final_query, start_timestamp, end_timestamp, sample_limit, group_by):
        """为单个分组并发获取样本日志，返回 (idx, event_dict) 保序。"""
        sample_query = self._build_group_sample_query(final_query, group_values)
        try:
            logs = self.vlogs_api.query(query=sample_query, start=start_timestamp, end=end_timestamp, limit=sample_limit)
        except Exception as e:
            logger.warning(f"Failed to query keyword grouped samples for policy {self.policy.id}: {e}")
            logs = []
        event = {
            "source_id": self._build_group_source_id(group_values),
            "level": self.policy.alert_level,
            "content": self._render_alert_name(group_values, group_by),
            "value": total_count,
            "raw_data": (logs or [])[:sample_limit],
        }
        return idx, event

    def _keyword_grouped_alert_detection(self, final_query, group_by, sample_limit, start_timestamp, end_timestamp):
        group_query = self._build_keyword_group_query(final_query, group_by)
        grouped_results = self.vlogs_api.query(query=group_query, start=start_timestamp, end=end_timestamp, limit=1000)

        # 预处理：筛出有效分组，记录原始序号以便并发后保序
        pending = []
        for idx, result in enumerate(grouped_results or []):
            group_values = self._extract_group_values(result, group_by)
            if not group_values:
                logger.warning(f"Skip keyword grouped result without complete group values for policy {self.policy.id}: {result}")
                continue
            total_count = self._parse_count_value(result.get("total_count"), default=0)
            if total_count <= 0:
                continue
            pending.append((idx, group_values, total_count))

        if not pending:
            return []

        try:
            max_workers = int(os.getenv("LOG_GROUPED_ALERT_MAX_WORKERS", "10"))
        except (TypeError, ValueError):
            max_workers = 10
        results_map = {}

        with ThreadPoolExecutor(max_workers=min(max_workers, len(pending))) as executor:
            futures = {
                executor.submit(
                    self._fetch_group_sample,
                    idx,
                    group_values,
                    total_count,
                    final_query,
                    start_timestamp,
                    end_timestamp,
                    sample_limit,
                    group_by,
                ): idx
                for idx, group_values, total_count in pending
            }
            for future in as_completed(futures):
                try:
                    idx, event = future.result()
                    results_map[idx] = event
                except Exception as e:
                    logger.warning(f"Unexpected error in grouped sample fetch for policy {self.policy.id}: {e}")

        # 按原始分组顺序返回
        return [results_map[idx] for idx, _, _ in pending if idx in results_map]

    def aggregate_alert_detection(self):
        """聚合告警检测"""
        events = []

        try:
            start_timestamp, end_timestamp = self._get_scan_window()

            alert_condition = self.policy.alert_condition
            base_query = alert_condition.get("query", "*")
            group_by = alert_condition.get("group_by", [])
            rule = alert_condition.get("rule", {})

            # 验证必要参数
            if not rule.get("conditions"):
                logger.warning(f"policy {self.policy.id} has no rule conditions for aggregate alert")
                return events

            # 应用日志分组规则
            base_query_with_groups = self._build_query_with_log_groups(base_query)

            # 构建LogSQL聚合查询语句
            aggregation_query = self._build_aggregation_query(base_query_with_groups, group_by, rule)
            logger.info(f"Executing aggregation query for policy {self.policy.id}: {aggregation_query}")

            # 执行聚合查询
            aggregation_results = self.vlogs_api.query(
                query=aggregation_query,
                start=start_timestamp,
                end=end_timestamp,
                limit=1000,  # 聚合结果通常数量较少
            )

            if not aggregation_results:
                logger.info(f"No aggregation results for policy {self.policy.id}")
                return events

            # 处理聚合查询结果
            for result in aggregation_results:
                # 从聚合结果中提取计算值
                aggregate_data = self._extract_aggregate_data(result, rule)

                # 检查是否满足告警条件
                if self._check_rule_conditions(aggregate_data, rule):
                    # 渲染告警名称模板
                    rendered_alert_name = self._render_alert_name(result, group_by)
                    # 构建分组标识和source_id
                    group_key = self._build_group_key(result, group_by)
                    source_id = f"policy_{self.policy.id}_{group_key}"

                    events.append(
                        {
                            "source_id": source_id,
                            "level": self.policy.alert_level,
                            "content": rendered_alert_name,
                            "value": aggregate_data.get("count", 0),
                            "raw_data": {
                                "aggregate_result": aggregate_data,
                                "rule": rule,
                                "query_result": result,
                            },
                        }
                    )

            return events

        except Exception as e:
            logger.error(f"aggregate alert detection failed for policy {self.policy.id}: {e}")
            raise

    def _build_query_with_log_groups(self, base_query):
        """构建包含日志分组规则的查询语句

        Args:
            base_query: 策略的基础查询条件

        Returns:
            str: 组合了日志分组规则的最终查询语句
        """
        try:
            # 获取策略配置的日志分组
            log_groups = getattr(self.policy, "log_groups", [])

            if not log_groups:
                # 没有配置日志分组，使用原有逻辑（添加采集类型过滤）
                return self._add_collect_type_filter(base_query)

            # 使用日志分组查询构建器
            query_with_groups, group_info = LogGroupQueryBuilder.build_query_with_groups(base_query, log_groups)

            # 记录应用的日志分组信息
            if group_info:
                logger.info(f"Policy {self.policy.id} applied log groups: {[g['name'] for g in group_info]}")

            # 添加采集类型过滤
            final_query = self._add_collect_type_filter(query_with_groups)

            return final_query

        except Exception as e:
            logger.warning(f"Failed to apply log groups for policy {self.policy.id}: {e}")
            # 发生错误时回退到原有逻辑
            return self._add_collect_type_filter(base_query)

    def _add_collect_type_filter(self, query):
        """添加采集类型过滤条件"""
        if not self.policy.collect_type:
            return query or "*"

        collect_type_filter = f'collect_type:"{self.policy.collect_type.name}"'

        if not query or query.strip() == "*":
            # 如果是通配符查询，直接使用采集类型过滤
            return collect_type_filter
        else:
            # 组合原查询条件和采集类型过滤
            return f"({query}) AND {collect_type_filter}"

    def _build_aggregation_query(self, base_query, group_by, rule):
        """构建LogSQL聚合查询语句"""
        conditions = rule.get("conditions", [])

        if not conditions:
            raise BaseAppException("rule conditions cannot be empty")

        # 收集需要计算的聚合函数
        stats_functions = []

        for condition in conditions:
            func = condition.get("func")
            field = condition.get("field", "_msg")

            if not func:
                logger.warning(f"condition missing func: {condition}")
                continue

            if func == "count":
                # count函数不需要字段参数，使用别名
                alias = f"count_{field.replace('.', '_')}"  # 处理字段名中的特殊字符
                stats_functions.append(f"count() as {alias}")
            elif func == "sum":
                alias = f"sum_{field.replace('.', '_')}"
                stats_functions.append(f"sum({field}) as {alias}")
            elif func == "avg":
                alias = f"avg_{field.replace('.', '_')}"
                stats_functions.append(f"avg({field}) as {alias}")
            elif func == "max":
                alias = f"max_{field.replace('.', '_')}"
                stats_functions.append(f"max({field}) as {alias}")
            elif func == "min":
                alias = f"min_{field.replace('.', '_')}"
                stats_functions.append(f"min({field}) as {alias}")
            else:
                logger.warning(f"unsupported aggregation function: {func}")

        # 如果没有有效的聚合函数，默认使用count
        if not stats_functions:
            stats_functions.append("count() as total_count")

        # 去重聚合函数
        stats_functions = list(dict.fromkeys(stats_functions))

        # 构建stats子句
        stats_clause = ", ".join(stats_functions)

        # 构建完整查询 - 使用正确的语法顺序
        if group_by:
            # 有分组的情况：query | stats by (field1, field2) func1() as alias1, func2() as alias2
            by_fields = ", ".join(group_by)
            query = f"{base_query} | stats by ({by_fields}) {stats_clause}"
        else:
            # 无分组的情况：query | stats func1() as alias1, func2() as alias2
            query = f"{base_query} | stats {stats_clause}"

        logger.debug(f"Built aggregation query: {query}")
        return query

    def _extract_aggregate_data(self, result, rule):
        """从查询结果中提取聚合数据"""
        aggregate_data = {}
        conditions = rule.get("conditions", [])

        for condition in conditions:
            func = condition.get("func")
            field = condition.get("field", "_msg")

            if not func:
                continue

            # 根据别名格式提取数据
            if func == "count":
                alias = f"count_{field.replace('.', '_')}"
                raw_value = result.get(alias, result.get("total_count", 0))
                # count函数结果转换为整数
                try:
                    numeric_value = int(float(str(raw_value))) if raw_value not in [None, ""] else 0
                except (ValueError, TypeError):
                    logger.warning(f"Failed to convert count value '{raw_value}' to integer, using 0")
                    numeric_value = 0

                aggregate_data[f"{func}_{field}"] = numeric_value
                # 兼容原有逻辑，设置通用的count值
                if "count" not in aggregate_data:
                    aggregate_data["count"] = numeric_value
            elif func in ["sum", "avg", "max", "min"]:
                alias = f"{func}_{field.replace('.', '_')}"
                raw_value = result.get(alias, 0)
                # 数值聚合函数结果转换为浮点数
                try:
                    numeric_value = float(str(raw_value)) if raw_value not in [None, ""] else 0.0
                except (ValueError, TypeError):
                    logger.warning(f"Failed to convert {func} value '{raw_value}' to float, using 0.0")
                    numeric_value = 0.0

                aggregate_data[f"{func}_{field}"] = numeric_value
            else:
                # 其他函数保持原值
                alias = f"{func}_{field.replace('.', '_')}"
                aggregate_data[f"{func}_{field}"] = result.get(alias, 0)

        return aggregate_data

    def _render_alert_name(self, result=None, group_by=None):
        """渲染告警名称模板

        将告警名称中的${field}占位符替换为实际的分组字段值
        例如：${host}出现报错 -> server01出现报错

        Args:
            result: 查询结果，包含分组字段的值
            group_by: 分组字段列表（聚合告警中必定存在）

        Returns:
            str: 渲染后的告警名称
        """
        if not self.policy.alert_name:
            return "聚合告警" if self.policy.alert_type == "aggregate" else "关键字告警"

        alert_name = self.policy.alert_name
        context = {"level": self.policy.alert_level}
        if isinstance(result, dict):
            context.update(result)
            for field, value in result.items():
                if not str(field).startswith("log."):
                    context[f"log.{field}"] = value

        try:

            def replace_token(match):
                token = match.group(1)
                value = context.get(token, "")
                return "" if value is None else str(value)

            rendered_name = self._ALERT_NAME_TOKEN_RE.sub(replace_token, alert_name)
            return rendered_name.strip()
        except Exception as e:
            logger.warning(f"Failed to render alert name template '{alert_name}': {e}")
            return alert_name

    def _build_group_key(self, result, group_by):
        """根据分组字段构建分组标识"""
        if not group_by:
            return ""

        group_values = []
        for field in group_by:
            field_value = result.get(field, "unknown")

            # 处理各种数据类型，确保转换为字符串
            if isinstance(field_value, list):
                # 如果是列表，转换为逗号分隔的字符串
                formatted_value = ",".join(str(item) for item in field_value)
            elif isinstance(field_value, dict):
                # 如果是字典，转换为键值对字符串
                formatted_value = str(field_value)
            elif field_value is None:
                formatted_value = "null"
            else:
                # 其他类型直接转换为字符串
                formatted_value = str(field_value)

            group_values.append(f"{field}={formatted_value}")

        return ", ".join(group_values)

    def _check_rule_conditions(self, aggregate_data, rule):
        """检查规则条件"""
        conditions = rule.get("conditions", [])
        mode = rule.get("mode", "and")

        if not conditions:
            return False

        condition_results = []
        for condition in conditions:
            func = condition.get("func")
            field = condition.get("field", "_msg")
            op = condition.get("op")
            expected_value = condition.get("value")

            if not all([func, op, expected_value is not None]):
                logger.warning(f"incomplete condition: {condition}")
                continue

            # 获取聚合值
            key = f"{func}_{field}"
            if func == "count":
                actual_value = aggregate_data.get("count", aggregate_data.get(key, 0))
            else:
                actual_value = aggregate_data.get(key, 0)

            # 执行条件比较
            comparison_result = self._compare_values(actual_value, op, expected_value)
            condition_results.append(comparison_result)

            logger.debug(f"condition check: {key}={actual_value} {op} {expected_value} -> {comparison_result}")

        if not condition_results:
            return False

        # 根据mode组合结果
        if mode == "and":
            return all(condition_results)
        elif mode == "or":
            return any(condition_results)
        else:
            logger.warning(f"unsupported rule mode: {mode}")
            return False

    def _compare_values(self, actual_value, op, expected_value):
        """比较值"""
        try:
            # 数值比较优化：尝试转换为数值类型进行比较
            if op in [">", "<", "=", "!=", ">=", "<="]:
                try:
                    # 尝试将两个值都转换为数值类型
                    if isinstance(actual_value, str) and actual_value.replace(".", "").replace("-", "").isdigit():
                        actual_numeric = float(actual_value)
                    elif isinstance(actual_value, (int, float)):
                        actual_numeric = float(actual_value)
                    else:
                        actual_numeric = None

                    if isinstance(expected_value, str) and expected_value.replace(".", "").replace("-", "").isdigit():
                        expected_numeric = float(expected_value)
                    elif isinstance(expected_value, (int, float)):
                        expected_numeric = float(expected_value)
                    else:
                        expected_numeric = None

                    # 如果两个值都能转换为数值，则进行数值比较
                    if actual_numeric is not None and expected_numeric is not None:
                        if op == ">":
                            return actual_numeric > expected_numeric
                        elif op == "<":
                            return actual_numeric < expected_numeric
                        elif op == "=":
                            return abs(actual_numeric - expected_numeric) < 1e-10  # 浮点数相等比较
                        elif op == "!=":
                            return abs(actual_numeric - expected_numeric) >= 1e-10
                        elif op == ">=":
                            return actual_numeric >= expected_numeric
                        elif op == "<=":
                            return actual_numeric <= expected_numeric

                except (ValueError, TypeError) as e:
                    logger.debug(f"Failed to convert values to numeric for comparison: {actual_value} {op} {expected_value}, error: {e}")
                    # 如果数值转换失败，继续使用原始值比较
                    pass

            # 原有逻辑：直接比较（用于字符串和其他类型）
            if isinstance(expected_value, (int, float)) and isinstance(actual_value, (int, float)):
                if op == ">":
                    return actual_value > expected_value
                elif op == "<":
                    return actual_value < expected_value
                elif op == "=":
                    return actual_value == expected_value
                elif op == "!=":
                    return actual_value != expected_value
                elif op == ">=":
                    return actual_value >= expected_value
                elif op == "<=":
                    return actual_value <= expected_value

            # 字符串和列表操作
            if op == "in":
                if isinstance(expected_value, list):
                    return actual_value in expected_value
                else:
                    return str(expected_value) in str(actual_value)
            elif op == "nin":
                if isinstance(expected_value, list):
                    return actual_value not in expected_value
                else:
                    return str(expected_value) not in str(actual_value)
            else:
                logger.warning(f"Unsupported operator: {op}")
                return False

        except Exception as e:
            logger.error(f"Error comparing values: {actual_value} {op} {expected_value}, error: {e}")
            return False

    def create_events(self, events):
        """创建事件 - 优化版本，使用批量操作"""
        if not events:
            return []

        try:
            # 1. 批量查询所有可能存在的活跃告警
            source_ids = [event["source_id"] for event in events]
            existing_alerts_qs = Alert.objects.filter(
                policy_id=self.policy.id,
                source_id__in=source_ids,
                status=AlertConstants.STATUS_NEW,
            )

            # 手动构建映射表，因为source_id不是唯一字段
            # 对于同一个source_id可能有多个告警，我们取最新的一个
            existing_alerts = {}
            for alert in existing_alerts_qs:
                source_id = alert.source_id
                if source_id not in existing_alerts or alert.created_at > existing_alerts[source_id].created_at:
                    existing_alerts[source_id] = alert

            logger.debug(f"Found {len(existing_alerts)} existing alerts for policy {self.policy.id}")

            # 2. 分类处理：需要更新的告警和需要创建的告警
            alerts_to_update = []
            alerts_to_create = []
            create_events = []
            existing_event_objs = []
            events_to_update = []
            # 建立 event_id 到原始数据的映射，用于后续快照创建
            event_id_to_raw_data = {}
            event_ids = [self._build_event_id(source_id) for source_id in source_ids]
            existing_events, legacy_events = self._find_existing_events(event_ids, source_ids)

            for event in events:
                event_id = self._build_event_id(event["source_id"])
                source_id = event["source_id"]
                existing_event = existing_events.get(event_id) or legacy_events.get(source_id)

                if existing_event:
                    # 同一执行的旧 worker 可能在较新结果提交后才返回；旧结果只能复用，
                    # 不得回退 Event/Alert/RawData/快照的时间与内容。
                    if existing_event.event_time and self.scan_time and existing_event.event_time > self.scan_time:
                        continue
                    alert_obj = existing_event.alert
                    level_changed = existing_event.level != event["level"]
                    if level_changed:
                        alert_obj.notice = False
                        existing_event.notified = False
                        existing_event.notice_result = []
                        existing_event.notice_retry_count = 0
                    alert_obj.value = event.get("value", alert_obj.value)
                    alert_obj.content = event["content"]
                    alert_obj.level = event["level"]
                    alert_obj.end_event_time = self.scan_time
                    alerts_to_update.append(alert_obj)

                    existing_event.event_time = self.scan_time
                    existing_event.value = event.get("value")
                    existing_event.level = event["level"]
                    existing_event.content = event["content"]
                    events_to_update.append(existing_event)
                    existing_event_objs.append(existing_event)
                    if event.get("raw_data"):
                        event_id_to_raw_data[existing_event.id] = event["raw_data"]
                    continue

                if source_id in existing_alerts:
                    # 存在活跃告警，准备更新
                    alert_obj = existing_alerts[source_id]
                    if alert_obj.level != event["level"]:
                        # 级别变化属于显著变化，重置已通知标记以重新通知
                        alert_obj.notice = False
                    alert_obj.value = event.get("value", alert_obj.value)
                    alert_obj.content = event["content"]
                    alert_obj.level = event["level"]
                    alert_obj.end_event_time = self.scan_time
                    alerts_to_update.append(alert_obj)
                else:
                    # 不存在活跃告警，准备创建
                    alert_obj = Alert(
                        id=uuid.uuid4().hex,
                        policy=self.policy,
                        source_id=source_id,
                        collect_type=self.policy.collect_type,
                        level=event["level"],
                        value=event.get("value"),
                        content=event["content"],
                        status=AlertConstants.STATUS_NEW,
                        start_event_time=self.scan_time,
                        end_event_time=self.scan_time,
                        operator="",
                    )
                    alerts_to_create.append(alert_obj)
                    # 更新映射表，供后续事件关联使用
                    existing_alerts[source_id] = alert_obj

                # 保存原始数据到映射表（用于快照创建）
                if event.get("raw_data"):
                    event_id_to_raw_data[event_id] = event["raw_data"]

                # 准备事件记录（使用映射表中的alert_obj）
                create_events.append(
                    Event(
                        id=event_id,
                        policy=self.policy,
                        source_id=source_id,
                        alert=existing_alerts[source_id],
                        event_time=self.scan_time,
                        value=event.get("value"),
                        level=event["level"],
                        content=event["content"],
                        notice_result=[],
                    )
                )

            # 3. 批量执行数据库操作（外层事务保证 Alert/Event/EventRawData 原子性）
            # 任一步失败（包括 EventRawData.save() 触发的 S3 上传异常）均回滚全部 DB 写入，
            # 避免"告警有、数据无"的孤儿记录。
            # 注意：S3JSONField.pre_save() 在 DB 写入前上传至 MinIO；若 MinIO 失败则抛异常
            # → 事务回滚，DB 保持一致。快照写入在事务外独立执行（各自已有 atomic 保护）。
            try:
                with transaction.atomic():
                    # 分类阶段的查询可能早于并发 worker 提交。写入前按 Event → Alert 的
                    # 固定顺序加行锁并重新判定时间，避免旧 worker 的陈旧对象反向覆盖。
                    locked_events = {
                        event.id: event
                        for event in Event.objects.select_for_update()
                        .filter(id__in=[event.id for event in events_to_update])
                        .order_by("id")
                    }
                    locked_alerts = {
                        alert.id: alert
                        for alert in Alert.objects.select_for_update()
                        .filter(id__in=[alert.id for alert in alerts_to_update])
                        .order_by("id")
                    }
                    stale_alert_ids = {
                        alert.id
                        for alert in locked_alerts.values()
                        if alert.status != AlertConstants.STATUS_NEW
                        or (
                            self.execution_key is not None
                            and alert.end_event_time
                            and self.scan_time
                            and alert.end_event_time > self.scan_time
                        )
                    }

                    refreshed_events = []
                    refreshed_existing_event_objs = []
                    for desired_event in events_to_update:
                        current_event = locked_events[desired_event.id]
                        if current_event.alert_id in stale_alert_ids or (
                            current_event.event_time and self.scan_time and current_event.event_time > self.scan_time
                        ):
                            stale_alert_ids.add(current_event.alert_id)
                            continue

                        if current_event.level != desired_event.level:
                            current_event.notified = False
                            current_event.notice_result = []
                            current_event.notice_retry_count = 0
                        current_event.event_time = desired_event.event_time
                        current_event.value = desired_event.value
                        current_event.level = desired_event.level
                        current_event.content = desired_event.content
                        refreshed_events.append(current_event)
                        refreshed_existing_event_objs.append(current_event)

                    events_to_update = refreshed_events
                    existing_event_objs = refreshed_existing_event_objs

                    refreshed_alerts = {}
                    for desired_alert in alerts_to_update:
                        current_alert = locked_alerts[desired_alert.id]
                        if current_alert.id in stale_alert_ids:
                            continue
                        if current_alert.level != desired_alert.level:
                            current_alert.notice = False
                        current_alert.value = desired_alert.value
                        current_alert.content = desired_alert.content
                        current_alert.level = desired_alert.level
                        current_alert.end_event_time = desired_alert.end_event_time
                        refreshed_alerts[current_alert.id] = current_alert
                    alerts_to_update = list(refreshed_alerts.values())

                    if stale_alert_ids:
                        create_events = [event for event in create_events if event.alert_id not in stale_alert_ids]

                    writable_event_ids = {event.id for event in create_events}
                    writable_event_ids.update(event.id for event in existing_event_objs)
                    event_id_to_raw_data = {
                        event_id: raw_data
                        for event_id, raw_data in event_id_to_raw_data.items()
                        if event_id in writable_event_ids
                    }

                    # 批量创建新告警
                    if alerts_to_create:
                        Alert.objects.bulk_create(alerts_to_create, batch_size=DatabaseConstants.DEFAULT_BATCH_SIZE)
                        logger.debug(f"Created {len(alerts_to_create)} new alerts for policy {self.policy.id}")

                    # 批量更新现有告警
                    if alerts_to_update:
                        Alert.objects.bulk_update(
                            alerts_to_update,
                            ["value", "content", "level", "end_event_time", "notice"],
                            batch_size=DatabaseConstants.DEFAULT_BATCH_SIZE,
                        )
                        logger.debug(f"Updated {len(alerts_to_update)} existing alerts for policy {self.policy.id}")

                    if events_to_update:
                        Event.objects.bulk_update(
                            events_to_update,
                            [
                                "event_time",
                                "value",
                                "level",
                                "content",
                                "notified",
                                "notice_result",
                                "notice_retry_count",
                            ],
                            batch_size=DatabaseConstants.DEFAULT_BATCH_SIZE,
                        )

                    # 批量创建事件记录
                    event_objs = Event.objects.bulk_create(create_events, batch_size=DatabaseConstants.DEFAULT_BATCH_SIZE)

                    # 批量创建事件原始数据记录（关联到已创建的事件对象）
                    if event_id_to_raw_data:
                        create_raw_data = []
                        for event_obj in event_objs:
                            if event_obj.id in event_id_to_raw_data:
                                create_raw_data.append(
                                    EventRawData(
                                        event=event_obj,  # 使用 event 字段，而不是 event_id
                                        data=event_id_to_raw_data[event_obj.id],
                                    )
                                )

                        # 逐个保存原始数据记录以确保 S3JSONField 能正确上传数据
                        for raw_data_obj in create_raw_data:
                            raw_data_obj.save()
                        logger.debug(f"Created {len(create_raw_data)} raw data records for policy {self.policy.id}")

                    for event_obj in existing_event_objs:
                        raw_data = event_id_to_raw_data.get(event_obj.id)
                        if raw_data:
                            raw_data_obj = EventRawData.objects.filter(event=event_obj).order_by("id").first()
                            if raw_data_obj:
                                raw_data_obj.data = raw_data
                            else:
                                raw_data_obj = EventRawData(event=event_obj, data=raw_data)
                            raw_data_obj.save()
            except IntegrityError:
                # 相同执行并发越过“先查后写”时，事件主键是最终数据库幂等门禁。
                # 只有全部目标事件均已由竞争方提交，才把冲突视为成功；其他约束错误保留原始异常。
                recovered_events = {event.id: event for event in Event.objects.filter(id__in=event_ids).select_related("alert")}
                if set(recovered_events) != set(event_ids):
                    raise
                if any(event.event_time != self.scan_time for event in recovered_events.values()):
                    raise RuntimeError(f"policy {self.policy.id} concurrent scan window conflict")
                event_objs = [recovered_events[event_id] for event_id in event_ids]
                existing_event_objs = []
                alerts_to_create = []

            # 为告警创建或更新快照（传递原始数据映射）
            # 快照写入在事务外执行：每条快照各自有 atomic 保护，且 S3JSONField 写 MinIO
            # 不应阻塞主事务；快照失败不影响告警/事件已提交的数据。
            event_objs = existing_event_objs + event_objs
            self._create_snapshots_for_alerts(event_objs, alerts_to_create, events, event_id_to_raw_data)

            logger.info(f"Prepared {len(event_objs)} idempotent events for policy {self.policy.id}")
            return event_objs

        except Exception as e:
            logger.error(f"create events failed for policy {self.policy.id}: {e}")
            raise

    def _create_snapshots_for_alerts(self, event_objs, new_alerts, raw_events, event_id_to_raw_data=None):
        """为告警创建或更新快照数据

        Args:
            event_objs: 创建的事件对象列表
            new_alerts: 新创建的告警对象列表
            raw_events: 原始事件数据列表（包含raw_data）
            event_id_to_raw_data: event_id 到原始数据的映射（优先使用此映射）
        """
        if not event_objs:
            return

        try:
            # 优先使用传入的映射，如果没有则从 raw_events 构建
            if event_id_to_raw_data:
                # 使用传入的映射
                event_raw_data_map = event_id_to_raw_data
            else:
                # 从 raw_events 构建映射（兼容旧逻辑）
                source_raw_data_map = {event["source_id"]: event.get("raw_data", {}) for event in raw_events if event.get("raw_data")}

                # 建立事件ID到原始数据的映射
                event_raw_data_map = {event_obj.id: source_raw_data_map.get(event_obj.source_id, {}) for event_obj in event_objs}

            # 建立告警ID到事件对象的映射（使用 defaultdict 优化）
            from collections import defaultdict

            alert_events_map = defaultdict(list)
            for event_obj in event_objs:
                alert_events_map[event_obj.alert_id].append(event_obj)

            # 为每个告警更新快照
            for alert_id, related_events in alert_events_map.items():
                # 获取第一个事件对象用于获取告警信息
                first_event = related_events[0]

                # 更新告警快照
                self._update_alert_snapshot(
                    alert_id=alert_id,
                    policy_id=self.policy.id,
                    source_id=first_event.source_id,
                    event_objs=related_events,
                    event_raw_data_map=event_raw_data_map,
                    snapshot_time=self.scan_time,
                )

            logger.debug(f"Updated snapshots for {len(alert_events_map)} alerts")

        except Exception as e:
            logger.error(f"Failed to create snapshots for alerts: {e}")
            raise

    def _update_alert_snapshot(
        self,
        alert_id,
        policy_id,
        source_id,
        event_objs,
        event_raw_data_map,
        snapshot_time,
    ):
        """更新告警的快照数据

        Args:
            alert_id: 告警ID
            policy_id: 策略ID
            source_id: 资源ID
            event_objs: 事件对象列表
            event_raw_data_map: 事件ID到原始数据的映射
            snapshot_time: 快照时间
        """
        try:
            with transaction.atomic():
                snapshot_obj, created = AlertSnapshot.objects.get_or_create(
                    alert_id=alert_id,
                    defaults={
                        "policy_id": policy_id,
                        "source_id": source_id,
                        "snapshots": [],
                    },
                )
                if not created:
                    # Re-fetch with row lock to prevent lost-update on concurrent appends
                    snapshot_obj = AlertSnapshot.objects.select_for_update().get(pk=snapshot_obj.pk)

                # 如果有事件数据，添加到snapshots列表末尾
                if event_objs:
                    existing_snapshots = {
                        item.get("event_id"): item for item in snapshot_obj.snapshots if item.get("type") == "event" and item.get("event_id")
                    }

                    # 批量构建快照数据
                    new_snapshots = []
                    snapshots_changed = False
                    for event_obj in event_objs:
                        raw_data = event_raw_data_map.get(event_obj.id, {})
                        event_snapshot = existing_snapshots.get(event_obj.id)
                        if event_snapshot:
                            # 主数据事务与快照事务刻意分离；旧 worker 可能晚于新 worker
                            # 取得快照锁，只允许相同或更新的事件时间覆盖同一 event_id。
                            persisted_time = parse_datetime(
                                event_snapshot.get("event_time") or event_snapshot.get("snapshot_time") or ""
                            )
                            candidate_time = event_obj.event_time or snapshot_time
                            if persisted_time and django_timezone.is_naive(persisted_time):
                                persisted_time = django_timezone.make_aware(
                                    persisted_time,
                                    django_timezone.get_default_timezone(),
                                )
                            if candidate_time and django_timezone.is_naive(candidate_time):
                                candidate_time = django_timezone.make_aware(
                                    candidate_time,
                                    django_timezone.get_default_timezone(),
                                )
                            if persisted_time and candidate_time and persisted_time > candidate_time:
                                continue
                            event_snapshot.update(
                                {
                                    "event_time": event_obj.event_time.isoformat() if event_obj.event_time else None,
                                    "snapshot_time": snapshot_time.isoformat(),
                                    "raw_data": raw_data,
                                }
                            )
                            snapshots_changed = True
                            continue

                        event_snapshot = {
                            "type": "event",
                            "event_id": event_obj.id,
                            "event_time": event_obj.event_time.isoformat() if event_obj.event_time else None,
                            "snapshot_time": snapshot_time.isoformat(),
                            "raw_data": raw_data,
                        }
                        new_snapshots.append(event_snapshot)

                    # 同一执行的重试覆盖快照；新执行追加，并裁剪至上限。
                    if new_snapshots or snapshots_changed:
                        snapshot_obj.snapshots.extend(new_snapshots)
                        if len(snapshot_obj.snapshots) > _MAX_ALERT_SNAPSHOTS:
                            snapshot_obj.snapshots = snapshot_obj.snapshots[-_MAX_ALERT_SNAPSHOTS:]
                        snapshot_obj.save(update_fields=["snapshots", "updated_at"])

        except Exception as e:
            logger.error(f"Failed to update alert snapshot for alert {alert_id}: {e}")
            raise

    def _format_notice_content(self, event_obj):
        """格式化通知内容
        Args:
            event_obj: 事件对象
        Returns:
            tuple: (title, content) 格式化后的标题和内容
        """
        # 格式化标题
        title = "【日志告警通知】"
        url = f"{WebConstants.URL}/log/event/alert"
        # 格式化内容
        content_parts = [
            f"时间：{event_obj.event_time}",
            f"告警内容：{event_obj.content}",
            f"策略名称：{self.policy.name}",
            f'查看告警详情：<a href="{url}">点击查看详情</a>',
        ]

        content = "\n".join(content_parts)

        return title, content

    def send_notice(self, event_obj, max_attempts=None):
        """发送通知

        内联重试（范围A）：单次发送遇瞬时通道故障时按 max_attempts 重试 + 线性退避，
        兜住亚秒级通道抖动；仍失败则返回 (False, 最后一次结果)，由持久化补偿任务（范围B）后续重投。
        补偿任务本身即外层重试循环，调用时传 max_attempts=1 做单次发送，避免在 worker 内叠加 sleep 阻塞。
        """
        lifecycle_notifier = LogAlertLifecycleNotifier(self.policy)
        # 告警中心接收结构化生命周期 Event；其他渠道继续使用原有文本通知。
        if lifecycle_notifier.is_alert_center_channel():
            success, result = lifecycle_notifier.notify_created(
                event_obj,
                max_attempts=max_attempts,
            )
            if success:
                self._reconcile_closed_after_created(
                    event_obj,
                    lifecycle_notifier,
                    max_attempts=max_attempts,
                )
            return success, result

        if not self.policy.notice_users:
            return False, []

        # 使用新的格式化方法
        title, content = self._format_notice_content(event_obj)

        if max_attempts is None:
            max_attempts = AlertConstants.NOTICE_SEND_MAX_ATTEMPTS
        max_attempts = max(max_attempts, 1)
        last_result = None
        for attempt in range(1, max_attempts + 1):
            try:
                result = SystemMgmtUtils.send_msg_with_channel(self.policy.notice_type_id, title, content, self.policy.notice_users)
                # 检查发送结果
                if result.get("result") is False:
                    last_result = result
                    msg = (
                        f"send notice failed for policy {self.policy.id} (attempt {attempt}/{max_attempts}): {result.get('message', 'Unknown error')}"
                    )
                    logger.error(msg)
                else:
                    logger.info(f"send notice success for policy {self.policy.id} (attempt {attempt}/{max_attempts})")
                    return True, result
            except Exception as e:
                msg = f"send notice exception for policy {self.policy.id} (attempt {attempt}/{max_attempts}): {e}"
                logger.error(msg, exc_info=True)
                last_result = {"result": False, "message": msg}

            # 非末次尝试 → 线性退避后重试
            if attempt < max_attempts:
                time.sleep(AlertConstants.NOTICE_SEND_RETRY_BACKOFF_SECONDS * attempt)

        return False, last_result if last_result is not None else {"result": False, "message": "Unknown error"}

    @staticmethod
    def _reconcile_closed_after_created(event_obj, lifecycle_notifier, max_attempts=None):
        """created 成功后重放并发发生的关闭，保证远端最终事件顺序。"""
        closed_alert = (
            Alert.objects.select_related("policy", "collect_type")
            .prefetch_related("policy__policyorganization_set")
            .filter(
                id=event_obj.alert_id,
                status=AlertConstants.STATUS_CLOSED,
                end_event_time__isnull=False,
            )
            .first()
        )
        if not closed_alert:
            return

        closed_success, _ = lifecycle_notifier.notify_closed(
            closed_alert,
            max_attempts=max_attempts,
        )
        Alert.objects.filter(
            id=closed_alert.id,
            status=AlertConstants.STATUS_CLOSED,
            end_event_time=closed_alert.end_event_time,
        ).update(notice=closed_success)

    def notice(self, event_objs, max_attempts=None):
        """通知"""
        if not event_objs or not self.policy.notice:
            return

        try:
            for event in event_objs:
                with transaction.atomic():
                    # 同步首发与补偿/并发扫描都以 Event 行锁领取通知；锁必须覆盖外部发送和
                    # 回执落库，避免两个持有旧对象的 worker 同时看到 notified=False 后双投。
                    current = Event.objects.select_for_update().get(pk=event.pk)
                    current_alert = Alert.objects.select_for_update().get(pk=current.alert_id)
                    if current.level == "info" or current.notified:
                        continue
                    if current_alert.notice:
                        current.notice_result = [{"result": True, "message": "skipped: alert already notified"}]
                        current.notified = True
                        current.save(update_fields=["notice_result", "notified", "updated_at"])
                        continue

                    is_notice, notice_result = self.send_notice(current, max_attempts=max_attempts)
                    current.notice_result = notice_result
                    current.notified = is_notice
                    current.notice_retry_count = (current.notice_retry_count or 0) + 1
                    current.save(
                        update_fields=[
                            "notice_result",
                            "notified",
                            "notice_retry_count",
                            "updated_at",
                        ]
                    )
                    if is_notice:
                        # 仅活跃告警接收 created 回执，避免覆盖并发关闭留下的补偿状态。
                        Alert.objects.filter(
                            id=current.alert_id,
                            status=AlertConstants.STATUS_NEW,
                        ).update(notice=True)

            logger.info(f"Completed notification for {len(event_objs)} events")

        except Exception as e:
            logger.error(f"notice failed for policy {self.policy.id}: {e}")

    def run(self):
        """运行策略扫描"""
        try:
            events = []

            # 根据告警类型进行不同的检测
            if self.policy.alert_type == AlertConstants.TYPE_KEYWORD:
                events = self.keyword_alert_detection()
            elif self.policy.alert_type == AlertConstants.TYPE_AGGREGATE:
                events = self.aggregate_alert_detection()
            else:
                logger.warning(f"Unknown alert type: {self.policy.alert_type} for policy {self.policy.id}")
                return

            if not events:
                logger.info(f"No alert events detected for policy {self.policy.id}")
                return

            logger.info(f"Detected {len(events)} alert events for policy {self.policy.id}")

            # 创建事件记录
            event_objs = self.create_events(events)

            # 事件通知
            if self.policy.notice and event_objs:
                self.notice(event_objs)

        except Exception as e:
            logger.error(f"Policy scan failed for policy {self.policy.id}: {e}")
            raise
