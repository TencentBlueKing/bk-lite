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
from django.db.models import F
from django.utils import timezone as django_timezone
from django.utils.dateparse import parse_datetime

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import celery_logger as logger
from apps.log.constants.alert_policy import AlertConstants
from apps.log.constants.database import DatabaseConstants
from apps.log.constants.web import WebConstants
from apps.log.models.policy import Alert, AlertSnapshot, Event, EventRawData
from apps.log.services.aggregate_group_identity import SOURCE_ID_MAX_LENGTH, build_aggregate_group_identity
from apps.log.services.alert_access import snapshot_policy_organization_ids
from apps.log.services.alert_lifecycle_notify import LogAlertLifecycleNotifier
from apps.log.services.alert_query_clue import freeze_log_alert_query_clue
from apps.log.services.log_event_contract import to_logical_event
from apps.log.services.policy_condition import (
    collect_stats_expressions,
    compare_targets,
    condition_alias,
    normalize_condition,
    parse_metric,
    stats_alias,
    uses_previous_count_delta,
)
from apps.log.services.search import SearchService
from apps.log.tasks.utils.policy import period_to_seconds
from apps.log.utils.query_log import VictoriaMetricsAPI
from apps.monitor.utils.system_mgmt_api import SystemMgmtUtils


class LogPolicyScan:
    _ALERT_NAME_TOKEN_RE = re.compile(r"\$\{([^}]+)\}")
    _NO_DATA_SOURCE_SUFFIX = ":no_data"

    def __init__(self, policy, scan_time=None, window_start=None, window_end=None, execution_key=None, cursor_time=None):
        self.policy = policy
        self.vlogs_api = VictoriaMetricsAPI()
        self.scan_time = scan_time or policy.last_run_time
        self.window_start = window_start
        self.window_end = window_end
        self.execution_key = execution_key
        self.cursor_time = cursor_time
        self.organizations = snapshot_policy_organization_ids(policy)
        self.baseline_status = "not_required"
        self.baselines = {}
        self.window_observed = False
        self.aggregation_query = ""
        self.observed_final_query = ""

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
        existing_by_id = {event.id: event for event in Event.objects.filter(id__in=event_ids, action="").select_related("alert")}
        source_id_candidates = [self._normalize_source_id_candidates(source_id) for source_id in source_ids]
        missing_source_ids = {
            candidate for event_id, candidates in zip(event_ids, source_id_candidates) if event_id not in existing_by_id for candidate in candidates
        }
        if not missing_source_ids:
            return existing_by_id, {}

        legacy_events = Event.objects.filter(
            policy_id=self.policy.id,
            source_id__in=missing_source_ids,
            action="",
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

    def _normalize_source_id_candidates(self, source_ids):
        if isinstance(source_ids, str):
            source_ids = [source_ids]
        return tuple(dict.fromkeys(source_id for source_id in source_ids if isinstance(source_id, str) and source_id))

    def _get_event_source_id_candidates(self, event):
        aliases = event.get("source_id_aliases", [])
        if isinstance(aliases, str):
            aliases = [aliases]
        return self._normalize_source_id_candidates([event["source_id"], *aliases])

    def _load_persisted_alias_claims(self, active_alerts, current_source_ids):
        alerts_by_id = {alert.id: alert for alert in active_alerts}
        if not alerts_by_id:
            return {}, {}

        claims_by_alias = {}
        current_alerts = {}
        claim_rows = (
            Event.objects.filter(alert_id__in=alerts_by_id, action="")
            .exclude(source_id=F("alert__source_id"))
            .values_list("alert_id", "source_id")
            .distinct()
        )
        for alert_id, source_id in claim_rows:
            alias = alerts_by_id[alert_id].source_id
            claims_by_alias.setdefault(alias, set()).add(source_id)
            if source_id in current_source_ids:
                current_alerts[source_id] = alerts_by_id[alert_id]
        return claims_by_alias, current_alerts

    def _get_keyword_sample_limit(self, alert_condition):
        """样本条数：缺省 5，读取时钳到 1..SAMPLE_LIMIT_MAX。"""
        limit = alert_condition.get("limit", 5) if isinstance(alert_condition, dict) else 5
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 5
        return min(max(limit, 1), AlertConstants.SAMPLE_LIMIT_MAX)

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

    def _build_jump_query(self, base_query, group_values, window_start, window_end):
        """冻结检索语句：展开日志分组后再用 AND 精确过滤分组值。"""
        expanded = self._build_query_with_log_groups(base_query)
        return self._build_jump_query_from_expanded(expanded, group_values, window_start, window_end)

    def _build_jump_query_from_expanded(self, expanded_query, group_values, window_start, window_end):
        filters = []
        for field, value in (group_values or {}).items():
            filters.append(self._build_exact_field_filter(field, value))
        query = (expanded_query or "").strip() or "*"
        if filters:
            group_filter = " AND ".join(filters)
            if query == "*":
                query = group_filter
            else:
                query = f"{query} AND {group_filter}"
        return {"query": query, "window_start": window_start, "window_end": window_end}

    def _fetch_aggregate_samples(self, jobs, expanded_query, start_timestamp, end_timestamp, sample_limit):
        """聚合触发行取样。失败只让该行 samples 为空，不丢掉事件。"""
        if not jobs:
            return {}
        try:
            max_workers = int(os.getenv("LOG_GROUPED_ALERT_MAX_WORKERS", "10"))
        except (TypeError, ValueError):
            max_workers = 10
        results = {}

        def fetch(index, group_values):
            # 延迟导入：通知正文回归夹具会替换 django.db，模块顶层不能依赖该符号。
            from django.db import close_old_connections

            close_old_connections()
            sample_query = self._build_group_sample_query(expanded_query, group_values)
            try:
                logs = self.vlogs_api.query(
                    query=sample_query,
                    start=start_timestamp,
                    end=end_timestamp,
                    limit=sample_limit,
                )
            except Exception as exc:
                logger.warning(
                    "event=log_policy_aggregate_sample_failed policy_id=%s failed_stage=%s error_type=%s",
                    getattr(self.policy, "id", ""),
                    "sample",
                    type(exc).__name__,
                )
                logs = []
            finally:
                close_old_connections()
            return index, self._to_logical_logs((logs or [])[:sample_limit])

        with ThreadPoolExecutor(max_workers=min(max_workers, len(jobs))) as executor:
            futures = [executor.submit(fetch, index, group_values) for index, group_values in jobs]
            for future in as_completed(futures):
                try:
                    index, logs = future.result()
                    results[index] = logs
                except Exception as exc:
                    logger.warning(
                        "event=log_policy_aggregate_sample_failed policy_id=%s failed_stage=%s error_type=%s",
                        getattr(self.policy, "id", ""),
                        "sample",
                        type(exc).__name__,
                    )
        for index, _group_values in jobs:
            results.setdefault(index, [])
        return results

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

    def _to_logical_logs(self, logs):
        if not isinstance(logs, list):
            return []
        return [to_logical_event(item) for item in logs]

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

    def evaluate_keyword(self, window_start, window_end):
        """只读关键字判定。每项含 group_values、total_count、triggered。"""
        self.window_observed = False
        self.observed_final_query = ""
        alert_condition = self.policy.alert_condition or {}
        query = alert_condition.get("query", "")
        if not query:
            logger.warning(f"policy {self.policy.id} has empty query for keyword alert")
            return []

        final_query = self._build_query_with_log_groups(query)
        self.observed_final_query = final_query
        sample_limit = self._get_keyword_sample_limit(alert_condition)
        group_by = self._normalize_group_by(alert_condition.get("group_by", []))
        if group_by:
            group_query = self._build_keyword_group_query(final_query, group_by)
            grouped_results = self.vlogs_api.query(query=group_query, start=window_start, end=window_end, limit=1000)
            self.window_observed = True
            items = []
            for result in grouped_results or []:
                group_values = self._extract_group_values(result, group_by)
                if not group_values:
                    logger.warning(
                        "event=log_policy_keyword_group_skipped policy_id=%s reason=%s",
                        self.policy.id,
                        "incomplete_group",
                    )
                    continue
                total_count = self._parse_count_value(result.get("total_count"), default=0)
                items.append(
                    {
                        "group_values": group_values,
                        "total_count": total_count,
                        "triggered": total_count > 0,
                        "final_query": final_query,
                        "sample_limit": sample_limit,
                        "group_by": group_by,
                        "base_query": query,
                    }
                )
            return items

        logs = self.vlogs_api.query(query=final_query, start=window_start, end=window_end, limit=sample_limit)
        self.window_observed = True
        if not logs:
            return []
        total_count = self._get_keyword_match_count(final_query, window_start, window_end)
        if total_count <= 0:
            total_count = len(logs)
        return [
            {
                "group_values": {},
                "total_count": total_count,
                "triggered": total_count > 0,
                "final_query": final_query,
                "sample_limit": sample_limit,
                "group_by": [],
                "base_query": query,
                "sample_logs": logs,
            }
        ]

    def keyword_alert_detection(self):
        """关键字告警检测"""
        try:
            start_timestamp, end_timestamp = self._get_scan_window()
            items = self._detection_rows(start_timestamp, end_timestamp)
            events = []
            if items:
                group_by = items[0].get("group_by") or []
                if group_by:
                    pending = [(idx, item["group_values"], item["total_count"]) for idx, item in enumerate(items) if item["triggered"]]
                    if pending:
                        events.extend(
                            self._collect_grouped_keyword_events(
                                pending,
                                items[0]["final_query"],
                                items[0]["sample_limit"],
                                start_timestamp,
                                end_timestamp,
                                group_by,
                            )
                        )
                elif items[0]["triggered"]:
                    item = items[0]
                    logs = item.get("sample_logs") or []
                    sample_limit = item["sample_limit"]
                    total_count = item["total_count"]
                    events.append(
                        {
                            "source_id": f"policy_{self.policy.id}",
                            "level": self.policy.alert_level,
                            "content": f"{self._render_alert_name()}: 检测到 {total_count} 条匹配日志",
                            "value": total_count,
                            "raw_data": self._to_logical_logs(logs[:sample_limit]),
                            "jump_query": self._build_jump_query(item.get("base_query") or "", {}, start_timestamp, end_timestamp),
                        }
                    )
            events.extend(self._no_data_events(start_timestamp, end_timestamp, items))
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
            "raw_data": self._to_logical_logs((logs or [])[:sample_limit]),
            "jump_query": self._build_jump_query_from_expanded(final_query, group_values, start_timestamp, end_timestamp),
        }
        return idx, event

    def _collect_grouped_keyword_events(self, pending, final_query, sample_limit, start_timestamp, end_timestamp, group_by):
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

    def evaluate_aggregate(self, window_start, window_end):
        """只读聚合判定。每项含 group_values、result、aggregate_data、triggered、reason。"""
        self.baseline_status = "not_required"
        self.baselines = {}
        self.window_observed = False
        self.aggregation_query = ""
        self.observed_final_query = ""
        alert_condition = self.policy.alert_condition or {}
        base_query = alert_condition.get("query", "*")
        group_by = self._normalize_group_by(alert_condition.get("group_by", []))
        rule = alert_condition.get("rule", {}) or {}
        if not rule.get("conditions"):
            logger.warning(
                "event=log_policy_aggregate_scan policy_id=%s failed_stage=%s error_type=%s",
                getattr(self.policy, "id", ""),
                "conditions",
                "missing_conditions",
            )
            return []

        base_query_with_groups = self._build_query_with_log_groups(base_query)
        aggregation_query = self._build_aggregation_query(base_query_with_groups, group_by, rule)
        logger.info("event=log_policy_aggregate_scan policy_id=%s", self.policy.id)
        aggregation_results = self.vlogs_api.query(
            query=aggregation_query,
            start=window_start,
            end=window_end,
            limit=1000,
        )
        self.window_observed = True
        self.aggregation_query = aggregation_query
        self.observed_final_query = base_query_with_groups
        window_seconds = window_end - window_start
        self._load_baselines(aggregation_query, rule, window_start, window_end)

        if not aggregation_results:
            logger.info("event=log_policy_aggregate_scan policy_id=%s group_count=%s", self.policy.id, 0)
            return []

        rows = []
        for result in aggregation_results:
            if not isinstance(result, dict):
                continue
            group_values = self._extract_group_values(result, group_by) if group_by else {}
            aggregate_data = self._extract_aggregate_data(
                result,
                rule,
                window_seconds=window_seconds,
                group_by=group_by,
                baselines=self.baselines,
            )
            triggered = self._check_rule_conditions(aggregate_data, rule)
            reason = ""
            if not triggered:
                reason = self._first_condition_reason(aggregate_data)
            rows.append(
                {
                    "group_values": group_values,
                    "result": result,
                    "aggregate_data": aggregate_data,
                    "triggered": triggered,
                    "reason": reason,
                }
            )
        return rows

    def _trigger_count(self):
        """连续满足次数。缺省和非法值按 1，不额外查窗。"""
        rule = (getattr(self.policy, "alert_condition", None) or {}).get("rule")
        raw = rule.get("trigger_count", 1) if isinstance(rule, dict) else 1
        if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
            return 1
        return min(raw, AlertConstants.TRIGGER_COUNT_MAX)

    def _row_group_key(self, row, group_by):
        source = row.get("group_values") if isinstance(row, dict) else {}
        return self._group_key_tuple(source or {}, group_by)

    def _triggered_group_keys(self, rows, group_by):
        keys = set()
        for row in rows or []:
            if isinstance(row, dict) and row.get("triggered"):
                keys.add(self._row_group_key(row, group_by))
        return keys

    def _mark_window_failed(self, rows):
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            row["triggered"] = False
            row["reason"] = "window_failed"
            row["streak"] = 0
        return rows

    def _apply_streak(self, rows, previous_windows, trigger_count):
        group_by = self._normalize_group_by((getattr(self.policy, "alert_condition", None) or {}).get("group_by"))
        previous_keys = [self._triggered_group_keys(window_rows, group_by) for window_rows in previous_windows]
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            streak = 0
            if row.get("triggered"):
                streak = 1
                key = self._row_group_key(row, group_by)
                for keys in previous_keys:
                    if key not in keys:
                        break
                    streak += 1
            row["streak"] = streak
            if streak < trigger_count:
                row["triggered"] = False
        return rows

    def _rows_with_streak(self, window_start, window_end, evaluate):
        """先查前 N-1 个平移窗，最后查本窗，避免本窗对照状态被覆盖。"""
        trigger_count = self._trigger_count()
        if trigger_count <= 1:
            return evaluate(window_start, window_end)
        duration = window_end - window_start
        previous_windows = []
        for index in range(1, trigger_count):
            try:
                previous_windows.append(evaluate(window_start - index * duration, window_end - index * duration))
            except Exception as exc:
                logger.warning(
                    "event=log_policy_streak_failed policy_id=%s failed_stage=%s window_index=%s error_type=%s",
                    getattr(self.policy, "id", ""),
                    "streak",
                    index,
                    type(exc).__name__,
                )
                return self._mark_window_failed(evaluate(window_start, window_end))
        return self._apply_streak(evaluate(window_start, window_end), previous_windows, trigger_count)

    def _detection_rows(self, window_start, window_end):
        if getattr(self.policy, "alert_type", None) == AlertConstants.TYPE_KEYWORD:
            return self._rows_with_streak(window_start, window_end, self.evaluate_keyword)
        return self._rows_with_streak(window_start, window_end, self.evaluate_aggregate)

    def aggregate_alert_detection(self):
        """聚合告警检测"""
        events = []
        try:
            start_timestamp, end_timestamp = self._get_scan_window()
            rows = self._detection_rows(start_timestamp, end_timestamp)
            alert_condition = self.policy.alert_condition or {}
            group_by = self._normalize_group_by(alert_condition.get("group_by", []))
            rule = alert_condition.get("rule", {}) or {}
            pending_samples = []
            base_query = alert_condition.get("query", "*")
            expanded_query = self._build_query_with_log_groups(base_query)
            sample_limit = self._get_keyword_sample_limit(alert_condition)
            for row in rows:
                if not row["triggered"]:
                    continue
                result = row["result"]
                aggregate_data = row["aggregate_data"]
                group_values = row.get("group_values") or {}
                rendered_alert_name = self._render_alert_name(result, group_by, aggregate_data=aggregate_data)
                identity = build_aggregate_group_identity(self.policy.id, result, group_by)
                jump_query = self._build_jump_query_from_expanded(expanded_query, group_values, start_timestamp, end_timestamp)
                event = {
                    "source_id": identity.source_id,
                    "level": self.policy.alert_level,
                    "content": rendered_alert_name,
                    "value": aggregate_data.get("count", 0),
                    "jump_query": jump_query,
                    "raw_data": {
                        "aggregate_result": aggregate_data,
                        "rule": rule,
                        "query_result": result,
                        "samples": [],
                        "jump_query": jump_query,
                    },
                }
                if identity.legacy_source_ids:
                    event["source_id_aliases"] = list(identity.legacy_source_ids)
                pending_samples.append((len(events), group_values))
                events.append(event)
            samples_by_index = self._fetch_aggregate_samples(
                pending_samples,
                expanded_query,
                start_timestamp,
                end_timestamp,
                sample_limit,
            )
            for index, samples in samples_by_index.items():
                events[index]["raw_data"]["samples"] = samples
            events.extend(self._no_data_events(start_timestamp, end_timestamp, rows))
            return events
        except Exception as e:
            logger.error(f"aggregate alert detection failed for policy {self.policy.id}: {e}")
            raise

    def evaluate_no_data(self, window_start, window_end, current_rows):
        """缺失分组。无分组看本窗 0 行；有分组用上一等长窗集合减去本窗集合。"""
        if not self._no_data_enabled() or not self.window_observed:
            return []
        alert_condition = self.policy.alert_condition or {}
        group_by = self._normalize_group_by(alert_condition.get("group_by", []))
        if not group_by and not self._ungrouped_window_empty(current_rows):
            return []
        prev_start, prev_end = self._baseline_bounds("previous_window", window_start, window_end)
        previous_rows = self._load_no_data_previous_rows(window_start, window_end, group_by)
        if previous_rows is None:
            return []
        if not group_by:
            return [self._no_data_row({}, prev_start, prev_end, self._row_count(previous_rows.get(())))]
        current_keys = self._current_group_keys(current_rows, group_by)
        missing = []
        for key, row in previous_rows.items():
            if not key or any(part == "" for part in key) or key in current_keys:
                continue
            group_values = {field: value for field, value in zip(group_by, key)}
            missing.append(self._no_data_row(group_values, prev_start, prev_end, self._row_count(row)))
        return missing

    def _no_data_enabled(self):
        no_data = (getattr(self.policy, "alert_condition", None) or {}).get("no_data")
        return isinstance(no_data, dict) and no_data.get("enabled") is True

    def _no_data_level(self):
        no_data = (getattr(self.policy, "alert_condition", None) or {}).get("no_data") or {}
        level = no_data.get("level") if isinstance(no_data, dict) else None
        allowed = {
            AlertConstants.LEVEL_INFO,
            AlertConstants.LEVEL_WARNING,
            AlertConstants.LEVEL_ERROR,
            AlertConstants.LEVEL_CRITICAL,
        }
        if level in allowed:
            return level
        return self.policy.alert_level

    def _ungrouped_window_empty(self, current_rows):
        """无分组是否视为本窗无日志。

        关键字看 total_count。聚合的 VictoriaLogs `stats` 在 0 条时仍返回一行
        count=0，不是空列表；已触发的行留给正常条件，不再判无数据。
        """
        rows = [row for row in (current_rows or []) if isinstance(row, dict)]
        if not rows:
            return True
        if getattr(self.policy, "alert_type", None) == AlertConstants.TYPE_KEYWORD:
            return all((row.get("total_count") or 0) <= 0 for row in rows)
        if any(row.get("triggered") for row in rows):
            return False
        return all(self._aggregate_row_count(row) == 0 for row in rows)

    def _aggregate_row_count(self, row):
        aggregate = row.get("aggregate_data")
        if isinstance(aggregate, dict) and aggregate.get("count") is not None:
            return self._parse_count_value(aggregate.get("count"), default=0)
        result = row.get("result") if isinstance(row.get("result"), dict) else row
        return self._message_count_from_result(result)

    def _current_group_keys(self, current_rows, group_by):
        keys = set()
        for row in current_rows or []:
            if not isinstance(row, dict):
                continue
            group_values = row.get("group_values")
            if not group_values and isinstance(row.get("result"), dict):
                group_values = self._extract_group_values(row["result"], group_by)
            if not group_values:
                continue
            key = self._group_key_tuple(group_values, group_by)
            if not key or any(part == "" for part in key):
                continue
            keys.add(key)
        return keys

    def _load_no_data_previous_rows(self, window_start, window_end, group_by):
        """上一等长窗的分组行。查询失败返回 None，本轮不判无数据。"""
        if getattr(self.policy, "alert_type", None) != AlertConstants.TYPE_KEYWORD:
            cached = (self.baselines or {}).get("previous_window")
            if isinstance(cached, dict) and cached.get("status") == "unavailable":
                return None
            if isinstance(cached, dict) and cached.get("status") == "ok" and isinstance(cached.get("rows"), dict):
                return cached["rows"]
            query = self.aggregation_query
        elif group_by:
            query = self._build_keyword_group_query(self.observed_final_query, group_by)
        else:
            query = f"{self.observed_final_query} | stats count() as total_count"
        if not query:
            logger.warning(
                "event=log_policy_baseline_failed policy_id=%s failed_stage=%s compare_to=%s error_type=%s",
                getattr(self.policy, "id", ""),
                "baseline",
                "previous_window",
                "ValueError",
            )
            return None
        return self._query_baseline(query, "previous_window", window_start, window_end)

    def _row_count(self, row):
        if not isinstance(row, dict):
            return 0
        raw = row.get("count__msg", row.get("total_count", row.get("count", 0)))
        return self._parse_count_value(raw, default=0)

    def _no_data_row(self, group_values, prev_start, prev_end, previous_count):
        baseline = {
            "to": "previous_window",
            "window": {"start": prev_start, "end": prev_end},
            "status": "ok",
            "values": {"count__msg": previous_count},
        }
        return {
            "group_values": group_values,
            "no_data": True,
            "baseline_window": {"start": prev_start, "end": prev_end},
            "aggregate_result": {"count": 0, "no_data": True, "baseline": baseline},
        }

    def _with_no_data_source_id(self, source_id):
        """分组身份后追加 :no_data。列长 100，超长时先缩短身份再追加。"""
        suffix = self._NO_DATA_SOURCE_SUFFIX
        text = source_id if isinstance(source_id, str) and source_id else f"policy_{self.policy.id}"
        room = SOURCE_ID_MAX_LENGTH - len(suffix)
        if len(text) > room:
            text = text[:room]
        return f"{text}{suffix}"

    def _no_data_events(self, window_start, window_end, current_rows):
        rows = self.evaluate_no_data(window_start, window_end, current_rows)
        if not rows:
            return []
        alert_condition = self.policy.alert_condition or {}
        group_by = self._normalize_group_by(alert_condition.get("group_by", []))
        expanded = self.observed_final_query or self._build_query_with_log_groups(alert_condition.get("query") or "*")
        level = self._no_data_level()
        events = []
        for row in rows:
            group_values = row.get("group_values") or {}
            aggregate_result = row["aggregate_result"]
            rendered = self._render_alert_name(group_values, group_by, aggregate_data=aggregate_result)
            identity = build_aggregate_group_identity(self.policy.id, group_values, group_by)
            jump_query = self._build_jump_query_from_expanded(expanded, group_values, window_start, window_end)
            events.append(
                {
                    "source_id": self._with_no_data_source_id(identity.source_id),
                    "level": level,
                    "content": f"无数据：{rendered}",
                    "value": 0,
                    "jump_query": jump_query,
                    "raw_data": {
                        "aggregate_result": aggregate_result,
                        "samples": [],
                        "jump_query": jump_query,
                    },
                }
            )
        return events

    def _build_query_with_log_groups(self, base_query):
        """构建包含日志分组规则的查询语句，并按检索同一套契约映射 message → _msg。"""
        log_groups = getattr(self.policy, "log_groups", [])
        try:
            query_with_groups, group_info = SearchService._build_storage_query(base_query, log_groups)
            if group_info:
                logger.info(f"Policy {self.policy.id} applied log groups: {[g['name'] for g in group_info]}")
            return self._add_collect_type_filter(query_with_groups)
        except Exception as e:
            logger.warning(f"Failed to apply log groups for policy {self.policy.id}: {e}")
            mapped_query, _ = SearchService._build_storage_query(base_query, None)
            return self._add_collect_type_filter(mapped_query)

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
        """构建 LogSQL 聚合查询。片段由 policy_condition.stats_expression 生成。"""
        conditions = rule.get("conditions", [])

        if not conditions:
            raise BaseAppException("rule conditions cannot be empty")

        stats_functions = collect_stats_expressions(conditions, self._map_storage_filter)
        if not stats_functions:
            stats_functions.append("count() as total_count")

        stats_clause = ", ".join(stats_functions)
        if group_by:
            by_fields = ", ".join(group_by)
            return f"{base_query} | stats by ({by_fields}) {stats_clause}"
        return f"{base_query} | stats {stats_clause}"

    def _map_storage_filter(self, raw_filter):
        """占比分子走检索的 message → _msg 映射。不记录筛选原文。"""
        mapped, _group_info = SearchService._build_storage_query(raw_filter, None)
        return mapped

    def _group_key_tuple(self, source, group_by):
        """分组键：按 group_by 顺序的字符串元组；无分组时为 ()。"""
        if not group_by:
            return ()
        if not isinstance(source, dict):
            return tuple("" for _ in group_by)
        values = []
        for field in group_by:
            raw = source.get(field)
            values.append("" if raw in (None, "") else str(raw))
        return tuple(values)

    def _message_count_from_result(self, result):
        raw_value = result.get("count__msg", result.get("total_count", 0)) if isinstance(result, dict) else 0
        try:
            return int(float(str(raw_value))) if raw_value not in (None, "") else 0
        except (TypeError, ValueError):
            logger.warning(
                "event=log_policy_count_parse_failed policy_id=%s failed_stage=%s error_type=%s",
                getattr(self.policy, "id", ""),
                "count_parse",
                "ValueError",
            )
            return 0

    def _rule_uses_func(self, rule, func_name):
        conditions = rule.get("conditions", []) if isinstance(rule, dict) else []
        return any(isinstance(condition, dict) and condition.get("func") == func_name for condition in conditions)

    def _baseline_bounds(self, compare_to, window_start, window_end):
        duration = window_end - window_start
        if compare_to == "previous_window":
            return window_start - duration, window_start
        offset = AlertConstants.COMPARE_OFFSET_SECONDS.get(compare_to)
        if offset is None:
            return None, None
        return window_start - offset, window_end - offset

    def _load_baselines(self, aggregation_query, rule, window_start, window_end):
        """每个不同的对照时段查一次。任一失败则 baseline_status 为 unavailable。"""
        targets = compare_targets((rule or {}).get("conditions"))
        self.baselines = {}
        if not targets:
            self.baseline_status = "not_required"
            return
        failed = False
        for compare_to in targets:
            start, end = self._baseline_bounds(compare_to, window_start, window_end)
            rows = self._query_baseline(aggregation_query, compare_to, window_start, window_end)
            if rows is None:
                failed = True
            self.baselines[compare_to] = {
                "status": "unavailable" if rows is None else "ok",
                "window": {"start": start, "end": end} if start is not None else {},
                "rows": rows,
            }
        self.baseline_status = "unavailable" if failed else "ok"

    def _query_baseline(self, aggregation_query, compare_to, window_start, window_end):
        """同一条聚合查询平移到对照窗。异常返回 None，不记录查询正文。"""
        start, end = self._baseline_bounds(compare_to, window_start, window_end)
        if start is None or end is None:
            logger.warning(
                "event=log_policy_baseline_failed policy_id=%s failed_stage=%s compare_to=%s error_type=%s",
                getattr(self.policy, "id", ""),
                "baseline",
                compare_to,
                "ValueError",
            )
            return None
        try:
            rows = self.vlogs_api.query(query=aggregation_query, start=start, end=end, limit=1000)
        except Exception as exc:
            logger.warning(
                "event=log_policy_baseline_failed policy_id=%s failed_stage=%s compare_to=%s error_type=%s",
                getattr(self.policy, "id", ""),
                "baseline",
                compare_to,
                type(exc).__name__,
            )
            return None

        group_by = self._normalize_group_by((getattr(self.policy, "alert_condition", None) or {}).get("group_by"))
        grouped = {}
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            grouped[self._group_key_tuple(row, group_by)] = row
        return grouped

    def _query_previous_window_counts(self, base_query_with_groups, group_by, window_start, window_end):
        """查询上一等长窗各分组 count。保留给第一批回归；新扫描走 _query_baseline。"""
        window_seconds = window_end - window_start
        prev_start = window_start - window_seconds
        prev_end = window_start
        normalized_group_by = self._normalize_group_by(group_by)
        if normalized_group_by:
            by_fields = ", ".join(normalized_group_by)
            query = f"{base_query_with_groups} | stats by ({by_fields}) count() as count__msg"
        else:
            query = f"{base_query_with_groups} | stats count() as count__msg"
        try:
            rows = self.vlogs_api.query(query=query, start=prev_start, end=prev_end, limit=1000)
        except Exception as exc:
            logger.warning(
                "event=log_policy_previous_window_failed policy_id=%s failed_stage=%s error_type=%s",
                getattr(self.policy, "id", ""),
                "previous_window",
                type(exc).__name__,
            )
            return None

        counts = {}
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            key = self._group_key_tuple(row, normalized_group_by)
            counts[key] = self._parse_count_value(row.get("count__msg", row.get("total_count")), default=0)
        return counts

    def _extract_aggregate_data(self, result, rule, *, window_seconds=None, previous_counts=None, group_by=None, baselines=None):
        """从查询结果提取聚合数据，并写出 conditions / baseline。

        previous_counts 仍接受：第一批直接调用把它当作 previous_window 的 count 对照。
        """
        conditions = rule.get("conditions", []) if isinstance(rule, dict) else []
        usable = [condition for condition in conditions if isinstance(condition, dict) and condition.get("func")]
        if not usable:
            return {}

        normalized = [normalize_condition(condition) for condition in usable]
        group_fields = self._normalize_group_by(group_by)
        group_key = self._group_key_tuple(result, group_fields)
        baseline_view = self._baseline_view(usable, previous_counts, baselines)
        aggregate_data = {}
        resolved = []
        for index, (raw, condition) in enumerate(zip(usable, normalized)):
            self._write_current_metric(aggregate_data, result, raw, condition, index)
            resolved_item = self._resolve_condition(
                raw,
                condition,
                result,
                baseline_view,
                group_key,
                window_seconds,
                index,
            )
            resolved.append(resolved_item)
            self._write_ratio_keys(aggregate_data, condition, resolved_item, index)
        self._write_derived_legacy_keys(
            aggregate_data,
            result,
            usable,
            baseline_view,
            group_key,
            window_seconds,
        )
        aggregate_data["conditions"] = resolved
        baseline_payload = self._baseline_payload(baseline_view, group_key, normalized)
        if baseline_payload is not None:
            aggregate_data["baseline"] = baseline_payload
        return aggregate_data

    def _baseline_view(self, conditions, previous_counts, baselines):
        if baselines is not None:
            return baselines
        targets = compare_targets(conditions)
        if not targets:
            return {}
        view = {}
        for target in targets:
            if target == "previous_window" and previous_counts is not None:
                rows = {key: {"count__msg": count} for key, count in previous_counts.items()}
                view[target] = {"status": "ok", "window": {}, "rows": rows}
            else:
                view[target] = {"status": "unavailable", "window": {}, "rows": None}
        return view

    def _write_current_metric(self, aggregate_data, result, raw, condition, index):
        func = raw.get("func")
        if func in AlertConstants.COUNT_DERIVED_FUNCS or func in ("bytes_rate", "ratio"):
            return
        alias = stats_alias(condition, index)
        if func == "count":
            raw_value = result.get(alias, result.get("total_count", 0)) if isinstance(result, dict) else 0
            numeric_value = parse_metric(raw_value, as_int=True)
            if numeric_value is None:
                numeric_value = 0
            aggregate_data[condition_alias(condition, index)] = numeric_value
            if "count" not in aggregate_data:
                aggregate_data["count"] = numeric_value
            return
        if func in ("sum", "avg", "max", "min"):
            raw_value = result.get(alias, 0) if isinstance(result, dict) else 0
            numeric_value = parse_metric(raw_value, as_int=False)
            aggregate_data[condition_alias(condition, index)] = 0.0 if numeric_value is None else numeric_value
            return
        if func == "count_uniq":
            raw_value = result.get(alias, 0) if isinstance(result, dict) else 0
            numeric_value = parse_metric(raw_value, as_int=True)
            aggregate_data[condition_alias(condition, index)] = 0 if numeric_value is None else numeric_value
            return
        if func == "quantile":
            raw_value = result.get(alias) if isinstance(result, dict) else None
            aggregate_data[condition_alias(condition, index)] = parse_metric(raw_value, as_int=False)

    def _write_derived_legacy_keys(self, aggregate_data, result, conditions, baselines, group_key, window_seconds):
        needs_rate = any(isinstance(condition, dict) and condition.get("func") == "count_rate" for condition in conditions)
        needs_delta = any(uses_previous_count_delta(condition) for condition in conditions)
        needs_bytes = any(isinstance(condition, dict) and condition.get("func") == "bytes_rate" for condition in conditions)
        needs_ratio = any(isinstance(condition, dict) and condition.get("func") == "ratio" for condition in conditions)
        if needs_rate or needs_delta or needs_ratio:
            message_count = self._message_count_from_result(result)
            aggregate_data["count__msg"] = message_count
            if "count" not in aggregate_data:
                aggregate_data["count"] = message_count
            if (needs_rate or needs_delta) and window_seconds is not None:
                aggregate_data["window_seconds"] = window_seconds
            if needs_rate:
                aggregate_data["count_rate"] = message_count / window_seconds if window_seconds else None
            if needs_delta:
                previous_count, _reason = self._baseline_metric(
                    "count",
                    "count__msg",
                    baselines,
                    "previous_window",
                    group_key,
                )
                if _reason == "missing_baseline":
                    aggregate_data["previous_count"] = None
                    aggregate_data["count_delta"] = None
                else:
                    aggregate_data["previous_count"] = previous_count
                    aggregate_data["count_delta"] = message_count - previous_count
        if needs_bytes:
            raw_bytes = result.get("bytes__msg", 0) if isinstance(result, dict) else 0
            parsed_bytes = parse_metric(raw_bytes, as_int=False)
            aggregate_data["bytes__msg"] = 0.0 if parsed_bytes is None else parsed_bytes
            if window_seconds is not None and "window_seconds" not in aggregate_data:
                aggregate_data["window_seconds"] = window_seconds
            aggregate_data["bytes_rate"] = aggregate_data["bytes__msg"] / window_seconds if window_seconds else None

    def _baseline_metric(self, func, alias, baselines, compare_to, group_key):
        info = (baselines or {}).get(compare_to) or {}
        if info.get("status") != "ok" or not isinstance(info.get("rows"), dict):
            return None, "missing_baseline"
        row = info["rows"].get(group_key)
        if row is None:
            if func in AlertConstants.MISSING_GROUP_ZERO_FUNCS:
                return 0 if func != "sum" else 0.0, ""
            return None, "baseline_missing"
        raw_value = row.get(alias, row.get("total_count")) if func == "count" else row.get(alias)
        if func == "count" and raw_value is None:
            raw_value = row.get("count__msg", row.get("total_count"))
        as_int = func in ("count", "count_uniq")
        parsed = parse_metric(raw_value, as_int=as_int)
        if parsed is None:
            if func in AlertConstants.MISSING_GROUP_ZERO_FUNCS:
                return 0 if func != "sum" else 0.0, ""
            if func == "quantile":
                return None, "not_numeric"
            return None, "baseline_missing"
        return parsed, ""

    def _resolve_condition(self, raw, condition, result, baselines, group_key, window_seconds, index):
        func = condition.get("func")
        field = condition.get("field") or "_msg"
        compare = dict(condition.get("compare") or {"kind": "absolute"})
        kind = compare.get("kind") or "absolute"
        params = condition.get("params") or {}
        current, current_reason = self._current_metric(func, condition, result, window_seconds, index)
        baseline_number = None
        reason = current_reason
        if kind != "absolute" and not reason:
            baseline_number, reason = self._baseline_metric(
                func,
                stats_alias(condition, index),
                baselines,
                compare.get("to"),
                group_key,
            )
        value = None
        if reason:
            value = None
        elif kind == "absolute":
            value = current
        elif kind == "percent" and baseline_number == 0:
            value = None
            reason = "baseline_zero"
        elif kind == "delta":
            value = current - baseline_number
        elif kind == "percent":
            value = (current - baseline_number) / float(baseline_number) * 100
        else:
            value = current
        op = raw.get("op")
        threshold = raw.get("value")
        matched = False
        if value is not None and op and threshold is not None:
            matched = bool(self._compare_values(value, op, threshold))
        resolved = {
            "func": func,
            "field": field,
            "compare": compare,
            "current": current,
            "value": value,
            "op": op,
            "threshold": threshold,
            "matched": matched,
            "reason": reason or "",
        }
        if kind != "absolute":
            resolved["baseline"] = baseline_number
        if params:
            resolved["params"] = params
        if func == "ratio":
            hit, total = self._ratio_counts(result, index)
            resolved["hit"] = hit
            resolved["total"] = total
        return resolved

    def _ratio_counts(self, result, index):
        if not isinstance(result, dict):
            return 0, 0
        hit = parse_metric(result.get(f"ratio_{index}_hit"), as_int=True)
        return (0 if hit is None else hit), self._message_count_from_result(result)

    def _write_ratio_keys(self, aggregate_data, condition, resolved_item, index):
        if condition.get("func") != "ratio":
            return
        alias = condition_alias(condition, index)
        aggregate_data[alias] = resolved_item.get("value")
        aggregate_data[f"{alias}_hit"] = resolved_item.get("hit")
        aggregate_data[f"{alias}_total"] = resolved_item.get("total")

    def _current_metric(self, func, condition, result, window_seconds, index):
        if func == "count_rate":
            message_count = self._message_count_from_result(result)
            if not window_seconds:
                return None, ""
            return message_count / window_seconds, ""
        if func == "bytes_rate":
            raw_bytes = result.get("bytes__msg", 0) if isinstance(result, dict) else 0
            parsed = parse_metric(raw_bytes, as_int=False)
            amount = 0.0 if parsed is None else parsed
            if not window_seconds:
                return None, ""
            return amount / window_seconds, ""
        if func == "ratio":
            hit, total = self._ratio_counts(result, index)
            if total == 0:
                return None, "denominator_zero"
            return hit / float(total) * 100, ""
        alias = stats_alias(condition, index)
        if func == "count":
            raw_value = result.get(alias, result.get("total_count", 0)) if isinstance(result, dict) else 0
            parsed = parse_metric(raw_value, as_int=True)
            return (0 if parsed is None else parsed), ""
        if func in ("sum", "avg", "max", "min"):
            raw_value = result.get(alias, 0) if isinstance(result, dict) else 0
            parsed = parse_metric(raw_value, as_int=False)
            return (0.0 if parsed is None else parsed), ""
        if func == "count_uniq":
            raw_value = result.get(alias, 0) if isinstance(result, dict) else 0
            parsed = parse_metric(raw_value, as_int=True)
            return (0 if parsed is None else parsed), ""
        if func == "quantile":
            raw_value = result.get(alias) if isinstance(result, dict) else None
            parsed = parse_metric(raw_value, as_int=False)
            if parsed is None:
                return None, "not_numeric"
            return parsed, ""
        raw_value = result.get(alias, 0) if isinstance(result, dict) else 0
        parsed = parse_metric(raw_value, as_int=False)
        return parsed, ""

    def _baseline_payload(self, baselines, group_key, conditions):
        targets = compare_targets(conditions)
        if not targets:
            return None
        values = {}
        any_bad = False
        for target in targets:
            info = (baselines or {}).get(target) or {}
            if info.get("status") != "ok" or not isinstance(info.get("rows"), dict):
                any_bad = True
                continue
            row = info["rows"].get(group_key)
            if isinstance(row, dict):
                for key, raw in row.items():
                    if key in values:
                        continue
                    parsed = parse_metric(raw, as_int=str(key).startswith("count"))
                    if parsed is not None:
                        values[key] = parsed
            else:
                for condition in conditions:
                    compare = condition.get("compare") or {}
                    if compare.get("to") != target or compare.get("kind") in (None, "absolute"):
                        continue
                    if condition.get("func") in AlertConstants.MISSING_GROUP_ZERO_FUNCS:
                        alias = stats_alias(condition, 0)
                        values.setdefault(alias, 0 if condition.get("func") != "sum" else 0.0)
        if len(targets) == 1:
            info = (baselines or {}).get(targets[0]) or {}
            return {
                "to": targets[0],
                "window": info.get("window") or {},
                "status": info.get("status") or "unavailable",
                "values": values,
            }
        return {
            "status": "unavailable" if any_bad else "ok",
            "values": values,
        }

    def _first_condition_reason(self, aggregate_data):
        for item in (aggregate_data or {}).get("conditions") or []:
            if not isinstance(item, dict) or item.get("matched"):
                continue
            if item.get("reason"):
                return item["reason"]
        if aggregate_data.get("count_delta") is None and any(
            uses_previous_count_delta(item) for item in (aggregate_data or {}).get("conditions") or []
        ):
            return "missing_baseline"
        return ""

    def _render_alert_name(self, result=None, group_by=None, aggregate_data=None):
        """渲染告警名称模板

        将告警名称中的${field}占位符替换为实际的分组字段值
        例如：${host}出现报错 -> server01出现报错

        Args:
            result: 查询结果，包含分组字段的值
            group_by: 分组字段列表（聚合告警中必定存在）
            aggregate_data: 聚合结果，支持 ${count} / ${count_rate} / ${count_delta} / ${previous_count}

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
        if isinstance(aggregate_data, dict):
            baseline = aggregate_data.get("baseline") if isinstance(aggregate_data.get("baseline"), dict) else {}
            baseline_values = baseline.get("values") if isinstance(baseline.get("values"), dict) else {}
            for key, value in baseline_values.items():
                context[f"baseline_{key}"] = self._format_template_value(value)
            for key, value in aggregate_data.items():
                if key in ("conditions", "baseline"):
                    continue
                context[key] = self._format_template_value(value)

        try:

            def replace_token(match):
                token = match.group(1)
                value = context.get(token, "")
                return "" if value is None else str(value)

            rendered_name = self._ALERT_NAME_TOKEN_RE.sub(replace_token, alert_name)
            return rendered_name.strip()
        except Exception as exc:
            logger.warning(
                "event=log_policy_alert_name_failed policy_id=%s failed_stage=%s error_type=%s",
                getattr(self.policy, "id", ""),
                "alert_name",
                type(exc).__name__,
            )
            return alert_name

    @staticmethod
    def _format_template_value(value):
        if isinstance(value, float) and not isinstance(value, bool):
            return f"{value:.2f}"
        return value

    def _check_rule_conditions(self, aggregate_data, rule):
        """按 conditions[i].matched 组合。没有解析结果时沿用第一批的键比较。"""
        conditions = rule.get("conditions", []) if isinstance(rule, dict) else []
        mode = rule.get("mode", "and") if isinstance(rule, dict) else "and"
        if not conditions:
            return False
        resolved = aggregate_data.get("conditions") if isinstance(aggregate_data, dict) else None
        if isinstance(resolved, list) and resolved:
            return self._combine_resolved_conditions(resolved, mode)
        return self._check_rule_conditions_legacy(aggregate_data, rule, mode)

    def _combine_resolved_conditions(self, resolved, mode):
        results = []
        for item in resolved:
            if not isinstance(item, dict):
                continue
            if not item.get("func") or not item.get("op") or item.get("threshold") is None:
                continue
            matched = bool(item.get("matched"))
            reason = item.get("reason") or ""
            if not matched and reason:
                logger.debug(
                    "event=log_policy_condition_skipped policy_id=%s reason=%s",
                    getattr(self.policy, "id", ""),
                    reason,
                )
            results.append(matched)
        return self._combine_condition_results(results, mode)

    def _check_rule_conditions_legacy(self, aggregate_data, rule, mode):
        condition_results = []
        for condition in rule.get("conditions", []):
            func = condition.get("func")
            field = condition.get("field", "_msg")
            op = condition.get("op")
            expected_value = condition.get("value")
            if not all([func, op, expected_value is not None]):
                continue
            normalized = normalize_condition(condition)
            key = f"{func}_{field}"
            if uses_previous_count_delta(condition):
                actual_value = aggregate_data.get("count_delta")
            elif func == "count" or normalized.get("func") == "count":
                actual_value = aggregate_data.get("count", aggregate_data.get(key, 0))
            elif func in AlertConstants.COUNT_DERIVED_FUNCS:
                actual_value = aggregate_data.get(func)
            else:
                actual_value = aggregate_data.get(condition_alias(normalized), aggregate_data.get(key, 0))
            if actual_value is None:
                logger.debug(
                    "event=log_policy_condition_skipped policy_id=%s reason=%s",
                    getattr(self.policy, "id", ""),
                    "missing_baseline",
                )
                condition_results.append(False)
                continue
            condition_results.append(self._compare_values(actual_value, op, expected_value))
        return self._combine_condition_results(condition_results, mode)

    def _combine_condition_results(self, results, mode):
        if not results:
            return False
        if mode == "and":
            return all(results)
        if mode == "or":
            return any(results)
        logger.warning(
            "event=log_policy_rule_mode_unsupported policy_id=%s failed_stage=%s error_type=%s",
            getattr(self.policy, "id", ""),
            "rule_mode",
            "unsupported_mode",
        )
        return False

    def _compare_values(self, actual_value, op, expected_value):  # noqa: C901
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
        """创建事件；带兼容别名的聚合事件按策略串行认领别名。"""
        if not events:
            return []

        if not any(event.get("source_id_aliases") for event in events):
            return self._create_events(events)

        with transaction.atomic():
            # 旧身份没有唯一约束。按策略串行化新版本 worker 的“查询并认领”，
            # 使相同旧身份在并发扫描中最多归属一个 g2 主身份。
            type(self.policy).objects.select_for_update().only("id").get(id=self.policy.id)
            event_objs, new_alerts, event_id_to_raw_data = self._create_events(events, defer_snapshots=True)

        # 快照包含对象存储 IO，不占用策略锁；告警和事件已经原子提交。
        self._create_snapshots_for_alerts(event_objs, new_alerts, events, event_id_to_raw_data)
        return event_objs

    def _create_events(self, events, defer_snapshots=False):  # noqa: C901
        """创建事件 - 优化版本，使用批量操作"""
        if not events:
            return []

        try:
            # 1. 批量查询所有可能存在的活跃告警
            source_ids = [event["source_id"] for event in events]
            source_id_candidates = [self._get_event_source_id_candidates(event) for event in events]
            lookup_source_ids = {source_id for candidates in source_id_candidates for source_id in candidates}
            active_alerts = list(
                Alert.objects.filter(
                    policy_id=self.policy.id,
                    source_id__in=lookup_source_ids,
                    status=AlertConstants.STATUS_NEW,
                )
            )
            if any(len(candidates) > 1 for candidates in source_id_candidates):
                # Alert 可能仍保存旧别名，而策略编辑会改变旧别名的拼接顺序。
                # g2 Event 才是稳定主索引；不受扫描 cursor 的时间窗限制地反查其活动 Alert。
                identity_alert_ids = (
                    Event.objects.filter(
                        policy_id=self.policy.id,
                        source_id__in=source_ids,
                        action="",
                        alert__status=AlertConstants.STATUS_NEW,
                    )
                    .values_list("alert_id", flat=True)
                    .distinct()
                )
                active_alert_ids = {alert.id for alert in active_alerts}
                for identity_alert in Alert.objects.filter(id__in=identity_alert_ids):
                    if identity_alert.id not in active_alert_ids:
                        active_alerts.append(identity_alert)
                        active_alert_ids.add(identity_alert.id)

            # 手动构建映射表，因为source_id不是唯一字段
            # 对于同一个source_id可能有多个告警，我们取最新的一个
            existing_alerts = {}
            for alert in active_alerts:
                source_id = alert.source_id
                if source_id not in existing_alerts or alert.created_at > existing_alerts[source_id].created_at:
                    existing_alerts[source_id] = alert
            claimed_source_ids_by_alias, claimed_alerts_by_source = self._load_persisted_alias_claims(active_alerts, set(source_ids))
            existing_alerts.update(claimed_alerts_by_source)

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
            existing_events, legacy_events = self._find_existing_events(event_ids, source_id_candidates)

            for event, candidates in zip(events, source_id_candidates):
                event_id = self._build_event_id(event["source_id"])
                source_id = event["source_id"]
                existing_event = existing_events.get(event_id)
                if existing_event is None:
                    for candidate in candidates:
                        candidate_event = legacy_events.get(candidate)
                        if candidate_event is None:
                            continue
                        claimed_source_ids = claimed_source_ids_by_alias.get(candidate, set())
                        if candidate != source_id and claimed_source_ids and source_id not in claimed_source_ids:
                            continue
                        if candidate != source_id:
                            claimed_source_ids_by_alias.setdefault(candidate, set()).add(source_id)
                            # 保留旧 Event 供旧版本按 legacy source_id 重试；本次继续创建
                            # 确定性 g2 Event，作为不会破坏回滚的持久化认领记录。
                            continue
                        existing_event = candidate_event
                        break

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

                alert_obj = existing_alerts.get(source_id)
                if alert_obj is None:
                    for alias in candidates[1:]:
                        candidate_alert = existing_alerts.get(alias)
                        if candidate_alert is None:
                            continue
                        claimed_source_ids = claimed_source_ids_by_alias.get(alias, set())
                        if claimed_source_ids and source_id not in claimed_source_ids:
                            continue
                        claimed_source_ids_by_alias.setdefault(alias, set()).add(source_id)
                        alert_obj = candidate_alert
                        existing_alerts[source_id] = alert_obj
                        break

                if alert_obj is not None:
                    # 存在活跃告警，准备更新
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
                    alert_source_id = source_id
                    for alias in candidates[1:]:
                        claimed_source_ids = claimed_source_ids_by_alias.get(alias, set())
                        if claimed_source_ids and source_id not in claimed_source_ids:
                            continue
                        alert_source_id = alias
                        claimed_source_ids_by_alias.setdefault(alias, set()).add(source_id)
                        break
                    alert_obj = Alert(
                        id=uuid.uuid4().hex,
                        policy=self.policy,
                        source_id=alert_source_id,
                        collect_type=self.policy.collect_type,
                        level=event["level"],
                        value=event.get("value"),
                        content=event["content"],
                        status=AlertConstants.STATUS_NEW,
                        start_event_time=self.scan_time,
                        end_event_time=self.scan_time,
                        operator="",
                        organizations=list(self.organizations),
                        handlers=list(self.policy.handlers or []),
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
                        for event in Event.objects.select_for_update().filter(id__in=[event.id for event in events_to_update]).order_by("id")
                    }
                    locked_alerts = {
                        alert.id: alert
                        for alert in Alert.objects.select_for_update().filter(id__in=[alert.id for alert in alerts_to_update]).order_by("id")
                    }
                    stale_alert_ids = {
                        alert.id
                        for alert in locked_alerts.values()
                        if alert.status != AlertConstants.STATUS_NEW
                        or (self.execution_key is not None and alert.end_event_time and self.scan_time and alert.end_event_time > self.scan_time)
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
                        event_id: raw_data for event_id, raw_data in event_id_to_raw_data.items() if event_id in writable_event_ids
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
            if defer_snapshots:
                logger.info(f"Prepared {len(event_objs)} idempotent events for policy {self.policy.id}")
                return event_objs, alerts_to_create, event_id_to_raw_data

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

            jump_by_source = {
                event.get("source_id"): event.get("jump_query") for event in raw_events or [] if event.get("source_id") and event.get("jump_query")
            }
            event_jump_map = {event_obj.id: jump_by_source.get(event_obj.source_id) for event_obj in event_objs}

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
                    source_id=first_event.alert.source_id,
                    event_objs=related_events,
                    event_raw_data_map=event_raw_data_map,
                    snapshot_time=self.scan_time,
                    event_jump_map=event_jump_map,
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
        event_jump_map=None,
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
                    window_start, window_end = self._get_scan_window()
                    query_clue = freeze_log_alert_query_clue(self.policy, window_start, window_end)

                    # 批量构建快照数据
                    new_snapshots = []
                    snapshots_changed = False
                    jump_map = event_jump_map or {}
                    for event_obj in event_objs:
                        raw_data = event_raw_data_map.get(event_obj.id, {})
                        jump_query = jump_map.get(event_obj.id)
                        event_snapshot = existing_snapshots.get(event_obj.id)
                        if event_snapshot:
                            # 主数据事务与快照事务刻意分离；旧 worker 可能晚于新 worker
                            # 取得快照锁，只允许相同或更新的事件时间覆盖同一 event_id。
                            persisted_time = parse_datetime(event_snapshot.get("event_time") or event_snapshot.get("snapshot_time") or "")
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
                            updated_snapshot = {
                                "event_time": event_obj.event_time.isoformat() if event_obj.event_time else None,
                                "snapshot_time": snapshot_time.isoformat(),
                                "raw_data": raw_data,
                                "query_clue": query_clue,
                            }
                            if jump_query:
                                updated_snapshot["jump_query"] = jump_query
                            event_snapshot.update(updated_snapshot)
                            snapshots_changed = True
                            continue

                        event_snapshot = {
                            "type": "event",
                            "event_id": event_obj.id,
                            "event_time": event_obj.event_time.isoformat() if event_obj.event_time else None,
                            "snapshot_time": snapshot_time.isoformat(),
                            "raw_data": raw_data,
                            "query_clue": query_clue,
                        }
                        if jump_query:
                            event_snapshot["jump_query"] = jump_query
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
        raw_data = self._load_notice_raw_data(event_obj)
        if isinstance(raw_data, dict) and isinstance(raw_data.get("aggregate_result"), dict):
            from apps.log.services.alert_notice_format import _jump_query_for_event, format_aggregate_notice

            jump_query = _jump_query_for_event(event_obj, raw_data)
            return format_aggregate_notice(
                event_obj,
                self.policy,
                raw_data,
                jump_query,
                base_url=WebConstants.URL,
                sample_limit=AlertConstants.SAMPLE_LIMIT_MAX,
                text_limit=AlertConstants.NOTICE_SAMPLE_TEXT_MAX,
            )

        title = "【日志告警通知】"
        url = f"{WebConstants.URL}/log/event/alert"
        # 没有聚合结果时保持原四行，避免旧渠道正文变化。
        content_parts = [
            f"时间：{event_obj.event_time}",
            f"告警内容：{event_obj.content}",
            f"策略名称：{self.policy.name}",
            f'查看告警详情：<a href="{url}">点击查看详情</a>',
        ]

        content = "\n".join(content_parts)

        return title, content

    def _load_notice_raw_data(self, event_obj):
        """读取事件原始数据。没有管理器时直接返回，避免旧通知路径触库。"""
        raw = getattr(event_obj, "raw_data", None)
        if raw is not None:
            return raw
        manager = getattr(EventRawData, "objects", None)
        event_id = getattr(event_obj, "id", None)
        if manager is None or not event_id:
            return None
        try:
            row = manager.filter(event_id=event_id).order_by("-id").first()
        except Exception:
            return None
        if row is None:
            return None
        return getattr(row, "data", None)

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
