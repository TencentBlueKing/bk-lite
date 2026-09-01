import logging
import math
import os
import re

import pandas as pd

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import monitor_logger as logger
from apps.monitor.models.monitor_metrics import Metric
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.utils.dimension import parse_instance_id
from apps.monitor.utils.display_fields_metrics import display_field_key, extract_metric_bindings
from apps.monitor.utils.instance_id_keys import resolve_metric_instance_id_keys
from apps.monitor.utils.unit_converter import UnitConverter
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI


def _positive_int_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


class MetricsQueryBudgetExceeded(BaseAppException):
    ERROR_CODE = "4220460"
    MESSAGE = "指标范围查询超过服务端预算，请缩短时间范围、减少实例或增大查询步长"
    STATUS_CODE = 422
    LOG_LEVEL = logging.WARNING


class Metrics:
    _STEP_PATTERN = re.compile(r"^(?P<value>\d+)(?P<unit>[smhdw])$")
    _LIMITING_QUERY_PATTERN = re.compile(r"^\s*(topk|bottomk|limitk)\s*\(", re.IGNORECASE)
    _EXPLICIT_SERIES_LIMIT_PATTERN = re.compile(
        r"^\s*(?:topk|bottomk|limitk)\s*\(\s*(?P<limit>\d+)\s*,",
        re.IGNORECASE,
    )
    MAX_GAP_DETECTION_POINTS = 50000
    CARD_QUERY_MAX_SERIES = 200
    CARD_QUERY_MAX_POINTS = 100000
    # 查询本身已带 topk/bottomk/limitk 时的兜底硬上限；超过则截断而非拒绝。
    CARD_QUERY_HARD_MAX_SERIES = 2000
    RANGE_QUERY_MAX_DURATION_SECONDS = _positive_int_env(
        "MONITOR_RANGE_QUERY_MAX_DURATION_SECONDS",
        366 * 24 * 60 * 60,
    )
    RANGE_QUERY_MAX_POINTS_PER_SERIES = _positive_int_env(
        "MONITOR_RANGE_QUERY_MAX_POINTS_PER_SERIES",
        10000,
    )
    RANGE_QUERY_MAX_SERIES = _positive_int_env(
        "MONITOR_RANGE_QUERY_MAX_SERIES",
        2000,
    )
    RANGE_QUERY_MAX_TOTAL_POINTS = _positive_int_env(
        "MONITOR_RANGE_QUERY_MAX_TOTAL_POINTS",
        500000,
    )

    @staticmethod
    def _range_budget_limits(card_budget=False) -> dict:
        if card_budget:
            return {
                "duration_seconds": Metrics.RANGE_QUERY_MAX_DURATION_SECONDS,
                "points_per_series": max(1, Metrics.CARD_QUERY_MAX_POINTS // Metrics.CARD_QUERY_MAX_SERIES),
                "series": Metrics.CARD_QUERY_MAX_SERIES,
                "total_points": Metrics.CARD_QUERY_MAX_POINTS,
            }
        return {
            "duration_seconds": Metrics.RANGE_QUERY_MAX_DURATION_SECONDS,
            "points_per_series": Metrics.RANGE_QUERY_MAX_POINTS_PER_SERIES,
            "series": Metrics.RANGE_QUERY_MAX_SERIES,
            "total_points": Metrics.RANGE_QUERY_MAX_TOTAL_POINTS,
        }

    @staticmethod
    def _raise_range_budget(reason: str, limits: dict, actual: dict):
        raise MetricsQueryBudgetExceeded(
            data={
                "code": "MONITOR_RANGE_QUERY_BUDGET_EXCEEDED",
                "reason": reason,
                "limits": limits,
                "actual": actual,
                "suggestions": [
                    "缩短查询时间范围",
                    "减少实例或序列数量",
                    "增大查询步长",
                ],
            }
        )

    @staticmethod
    def _prepare_range_budget(start_ms, end_ms, step, card_budget=False) -> dict:
        start_ms = int(start_ms)
        end_ms = int(end_ms)
        step_seconds = Metrics.parse_step_to_seconds(step)
        duration_seconds = max(0.0, (end_ms - start_ms) / 1000.0)
        points_per_series = int(duration_seconds // step_seconds) + 1
        limits = Metrics._range_budget_limits(card_budget=card_budget)
        actual = {
            "duration_seconds": duration_seconds,
            "step_seconds": step_seconds,
            "points_per_series": points_per_series,
        }

        if duration_seconds > limits["duration_seconds"]:
            Metrics._raise_range_budget("duration", limits, actual)
        if points_per_series > limits["points_per_series"]:
            Metrics._raise_range_budget("points_per_series", limits, actual)

        return {
            "start_ms": start_ms,
            "end_ms": end_ms,
            "duration_seconds": duration_seconds,
            "step_seconds": step_seconds,
            "points_per_series": points_per_series,
            "limits": limits,
        }

    @staticmethod
    def _apply_range_series_limit(query: str, max_series: int) -> str:
        explicit_limit = Metrics._EXPLICIT_SERIES_LIMIT_PATTERN.match(query or "")
        if explicit_limit and int(explicit_limit.group("limit")) <= max_series:
            return query
        return f"limitk({max_series + 1}, {query})"

    @staticmethod
    def _enforce_range_response_budget(response: dict, budget: dict) -> dict:
        if response.get("status") != "success":
            return {"series": 0, "filled_series": 0, "total_points": 0}

        result = (response.get("data") or {}).get("result") or []
        series_count = len(result)
        filled_series_count = sum(bool(item.get("values")) for item in result)
        total_points = filled_series_count * budget["points_per_series"]
        actual = {
            "duration_seconds": budget["duration_seconds"],
            "step_seconds": budget["step_seconds"],
            "points_per_series": budget["points_per_series"],
            "series": series_count,
            "filled_series": filled_series_count,
            "total_points": total_points,
        }

        if series_count > budget["limits"]["series"]:
            Metrics._raise_range_budget("series", budget["limits"], actual)
        if total_points > budget["limits"]["total_points"]:
            Metrics._raise_range_budget("total_points", budget["limits"], actual)
        return actual

    @staticmethod
    def get_effective_metric_instance_id_keys(metric: Metric) -> list[str]:
        monitor_object = getattr(metric, "monitor_object", None) or MonitorObject.objects.filter(id=metric.monitor_object_id).first()
        metric_keys = getattr(metric, "instance_id_keys", [])
        monitor_object_keys = getattr(monitor_object, "instance_id_keys", [])
        effective_keys = resolve_metric_instance_id_keys(metric_keys, monitor_object_keys, strict=True)

        if not metric_keys and effective_keys:
            logger.warning(
                "Metric instance_id_keys empty, fallback to monitor object keys. metric_id=%s monitor_object_id=%s keys=%s",
                getattr(metric, "id", None),
                getattr(metric, "monitor_object_id", None),
                effective_keys,
            )
        return effective_keys

    @staticmethod
    def get_metrics(query, time=None):
        """查询指标信息。

        :param query: PromQL
        :param time: 求值时刻（Unix 秒）；None 表示由 VictoriaMetrics 使用当前时间
        """
        return VictoriaMetricsAPI().query(query, time=time)

    @staticmethod
    def query_already_limited(query: str) -> bool:
        """True when the query already applies topk/bottomk/limitk."""
        return bool(Metrics._LIMITING_QUERY_PATTERN.match(query or ""))

    @staticmethod
    def apply_card_series_limit(query: str, limit: int | None = None) -> tuple[str, bool]:
        """Wrap an unlimited card query with limitk(N+1) for truncation detection.

        Returns (rewritten_query, applied). Queries that already start with
        topk/bottomk/limitk are left unchanged (hard cap applied in finalize).
        """
        series_limit = Metrics.CARD_QUERY_MAX_SERIES if limit is None else limit
        if Metrics.query_already_limited(query):
            return query, False
        return f"limitk({series_limit + 1}, {query})", True

    @staticmethod
    def clamp_card_step(start_ms, end_ms, step) -> tuple[str, bool]:
        """Enlarge step so worst-case series * points stays under CARD_QUERY_MAX_POINTS.

        Assumes at most CARD_QUERY_MAX_SERIES series. Returns (step_string, clamped).
        """
        step_seconds = Metrics.parse_step_to_seconds(step)
        duration_seconds = max(0.0, (int(end_ms) - int(start_ms)) / 1000.0)
        max_points_per_series = max(1, Metrics.CARD_QUERY_MAX_POINTS // Metrics.CARD_QUERY_MAX_SERIES)
        if max_points_per_series <= 1:
            min_step = max(1, int(duration_seconds) or 1)
        else:
            min_step = max(1, math.ceil(duration_seconds / (max_points_per_series - 1)))

        if step_seconds >= min_step:
            if isinstance(step, str) and step.strip():
                return step, False
            return f"{step_seconds}s", False
        return f"{min_step}s", True

    @staticmethod
    def finalize_card_series_budget(response, *, applied_limit: bool) -> bool:
        """Trim over-budget series and annotate series_budget. Returns truncated flag."""
        data = response.setdefault("data", {})
        result = data.get("result") or []
        truncated = False
        limit = Metrics.CARD_QUERY_MAX_SERIES

        if applied_limit:
            if len(result) > limit:
                truncated = True
                data["result"] = result[:limit]
        elif len(result) > Metrics.CARD_QUERY_HARD_MAX_SERIES:
            # 查询已自带 limit 算子时的兜底：截断而非抛错，避免浏览器卡死。
            truncated = True
            limit = Metrics.CARD_QUERY_HARD_MAX_SERIES
            data["result"] = result[:limit]

        data["series_budget"] = {
            "truncated": truncated,
            "limit": limit,
            "applied": applied_limit,
        }
        return truncated

    @staticmethod
    def get_metrics_range(
        query,
        start,
        end,
        step,
        detect_gaps=False,
        collection_interval_seconds=None,
        max_gap_detection_points=None,
        card_budget=False,
        fill_missing=True,
    ):
        """查询指标（范围）

        When card_budget=True, rewrite the query with limitk before hitting VM and
        clamp step so the card path cannot overload VictoriaMetrics or the browser.
        """
        start_ms = int(start)
        end_ms = int(end)
        effective_query = query
        applied_limit = False
        effective_step = step
        step_clamped = False

        if card_budget:
            effective_query, applied_limit = Metrics.apply_card_series_limit(query)
            effective_step, step_clamped = Metrics.clamp_card_step(start_ms, end_ms, step)

        budget = Metrics._prepare_range_budget(
            start_ms,
            end_ms,
            effective_step,
            card_budget=card_budget,
        )
        if not card_budget:
            effective_query = Metrics._apply_range_series_limit(
                query,
                budget["limits"]["series"],
            )

        step_seconds = budget["step_seconds"]
        start_sec = start_ms / 1000  # Convert milliseconds to seconds
        end_sec = end_ms / 1000  # Convert milliseconds to seconds
        vm_api = VictoriaMetricsAPI()
        resp = vm_api.query_range(effective_query, start_sec, end_sec, effective_step)

        truncated = False
        if card_budget:
            truncated = Metrics.finalize_card_series_budget(resp, applied_limit=applied_limit)
            if step_clamped:
                data = resp.setdefault("data", {})
                data["step"] = str(effective_step)
                data["step_clamped"] = True

        response_budget = Metrics._enforce_range_response_budget(resp, budget)

        if detect_gaps:
            data = resp.setdefault("data", {})
            try:
                collection_interval = int(collection_interval_seconds)
            except (TypeError, ValueError):
                collection_interval = 0

            detection_limit = max_gap_detection_points or Metrics.MAX_GAP_DETECTION_POINTS
            detection_points = int((end_sec - start_sec) / collection_interval) + 1 if collection_interval > 0 else 0

            if truncated:
                data["gaps"] = []
                data["gap_detection"] = {
                    "status": "limited",
                    "limited": True,
                    "reason": "series_truncated",
                }
            elif collection_interval > 0 and (
                detection_points > detection_limit or detection_points * response_budget["filled_series"] > budget["limits"]["total_points"]
            ):
                data["gaps"] = []
                data["gap_detection"] = {
                    "status": "limited",
                    "limited": True,
                    "reason": "max_points_exceeded",
                }
            elif collection_interval > 0:
                detection_resp = (
                    resp
                    if step_seconds == collection_interval
                    else vm_api.query_range(effective_query, start_sec, end_sec, f"{collection_interval}s")
                )
                gaps = Metrics.detect_gap_intervals(
                    detection_resp.get("data", {}).get("result", []),
                    collection_interval,
                    range_start=start_sec,
                    range_end=end_sec,
                )
                data["gaps"] = gaps
                data["gap_detection"] = {"status": "ok", "limited": False}
            else:
                data["gaps"] = []
                data["gap_detection"] = {"status": "skipped", "limited": False}
        if fill_missing:
            Metrics.fill_missing_points(start_sec, end_sec, step_seconds, resp.get("data", {}).get("result", []))
        return resp

    @staticmethod
    def enforce_card_query_budget(response, start_ms=None, end_ms=None, step=None):
        """Deprecated post-fetch guard; card path now uses pre-query limitk + step clamp.

        Kept for callers that still invoke it; prefers truncation annotation over raise
        when series_budget is already present.
        """
        del start_ms, end_ms, step  # retained for call-site compatibility
        data = response.get("data", {})
        if "series_budget" in data:
            return
        Metrics.finalize_card_series_budget(response, applied_limit=False)

    @staticmethod
    def parse_step_to_seconds(step) -> int:
        """将 step 解析为秒数，支持整数秒或 Prometheus duration（如 5m、1h）。"""
        if step is None:
            raise ValueError("step is required")

        if isinstance(step, int):
            if step <= 0:
                raise ValueError("step must be greater than 0")
            return step

        if isinstance(step, float):
            if step <= 0:
                raise ValueError("step must be greater than 0")
            return int(step)

        step_str = str(step).strip().lower()
        if not step_str:
            raise ValueError("step is required")

        if step_str.isdigit():
            step_seconds = int(step_str)
            if step_seconds <= 0:
                raise ValueError("step must be greater than 0")
            return step_seconds

        matched = Metrics._STEP_PATTERN.match(step_str)
        if not matched:
            raise ValueError("step format is invalid")

        value = int(matched.group("value"))
        if value <= 0:
            raise ValueError("step must be greater than 0")

        multiplier_map = {
            "s": 1,
            "m": 60,
            "h": 3600,
            "d": 86400,
            "w": 604800,
        }
        return value * multiplier_map[matched.group("unit")]

    @staticmethod
    def detect_gap_intervals(
        data_list,
        collection_interval_seconds,
        range_end=None,
        range_start=None,
    ):
        try:
            collection_interval = int(collection_interval_seconds)
        except (TypeError, ValueError):
            return []
        if collection_interval <= 0:
            return []

        tolerance_seconds = max(collection_interval * 2, 60)
        try:
            normalized_range_end = float(range_end) if range_end is not None else None
        except (TypeError, ValueError):
            normalized_range_end = None
        try:
            normalized_range_start = float(range_start) if range_start is not None else None
        except (TypeError, ValueError):
            normalized_range_start = None
        gaps = []

        for item in data_list:
            real_points = sorted(float(timestamp) for timestamp, value in item.get("values", []) if value is not None)
            if real_points and normalized_range_start is not None:
                first_timestamp = real_points[0]
                missing_duration = first_timestamp - normalized_range_start
                if missing_duration >= tolerance_seconds:
                    gaps.append(
                        {
                            "start": normalized_range_start,
                            "end": first_timestamp - collection_interval,
                            "duration": missing_duration,
                            "series": [
                                {
                                    "metric": item.get("metric", {}),
                                    "missing_points": int(missing_duration / collection_interval),
                                }
                            ],
                        }
                    )

            for prev_timestamp, next_timestamp in zip(real_points, real_points[1:]):
                missing_duration = next_timestamp - prev_timestamp - collection_interval
                if missing_duration < tolerance_seconds:
                    continue
                gaps.append(
                    {
                        "start": prev_timestamp + collection_interval,
                        "end": next_timestamp - collection_interval,
                        "duration": missing_duration,
                        "series": [
                            {
                                "metric": item.get("metric", {}),
                                "missing_points": int(missing_duration / collection_interval),
                            }
                        ],
                    }
                )

            if real_points and normalized_range_end is not None:
                last_timestamp = real_points[-1]
                missing_duration = normalized_range_end - last_timestamp
                if missing_duration >= tolerance_seconds:
                    gaps.append(
                        {
                            "start": last_timestamp + collection_interval,
                            "end": normalized_range_end,
                            "duration": missing_duration,
                            "series": [
                                {
                                    "metric": item.get("metric", {}),
                                    "missing_points": int(missing_duration / collection_interval),
                                }
                            ],
                        }
                    )

        return Metrics.merge_gap_intervals(gaps, collection_interval)

    @staticmethod
    def merge_gap_intervals(gaps, collection_interval_seconds):
        gaps_by_series = {}
        for gap in gaps:
            series_key = tuple(
                sorted(tuple(sorted((str(key), str(value)) for key, value in item.get("metric", {}).items())) for item in gap.get("series", []))
            )
            gaps_by_series.setdefault(series_key, []).append(gap)

        merged = []
        for series_gaps in gaps_by_series.values():
            current_series_gaps = []
            for gap in sorted(series_gaps, key=lambda item: (item["start"], item["end"])):
                if not current_series_gaps or gap["start"] > current_series_gaps[-1]["end"] + collection_interval_seconds:
                    current_series_gaps.append({**gap, "series": list(gap.get("series", []))})
                    continue

                current = current_series_gaps[-1]
                current["end"] = max(current["end"], gap["end"])
                current["duration"] = current["end"] - current["start"] + collection_interval_seconds
                for series_item in current["series"]:
                    if "missing_points" in series_item:
                        series_item["missing_points"] = int(current["duration"] / collection_interval_seconds)

            merged.extend(current_series_gaps)

        return sorted(merged, key=lambda item: (item["start"], item["end"]))

    @staticmethod
    def fill_missing_points(start, end, step, data_list):
        """
        Fill missing time points in the `values` field for multiple instances using pandas frequency inference.
        :param start: Start timestamp in seconds (float)
        :param end: End timestamp in seconds (float)
        :param step: Time interval (seconds) (int)
        :param data_list: Data list, format [{"metric": dict, "values": [[timestamp, value], ...]}, ...]
        :return: Updated data list with missing points filled in `values`
        """
        Metrics.enforce_fill_budget(start, end, step, data_list)

        for item in data_list:
            values = item["values"]

            if not values:
                continue

            # Convert original values to DataFrame
            original_df = pd.DataFrame(values, columns=["timestamp", "value"])
            original_df["timestamp"] = pd.to_datetime(original_df["timestamp"].astype(float), unit="s")
            original_df.set_index("timestamp", inplace=True)

            # Create complete time range DataFrame (start and end are now in seconds)
            full_time_index = pd.date_range(
                start=pd.to_datetime(start, unit="s"),
                end=pd.to_datetime(end, unit="s"),
                freq=f"{int(step)}s",
            )
            full_df = pd.DataFrame(index=full_time_index, columns=["value"])
            full_df["value"] = None

            # Concatenate and sort all timestamps
            all_df = pd.concat([original_df, full_df])
            all_df = all_df[~all_df.index.duplicated(keep="first")]  # Keep original values for duplicates
            all_df.sort_index(inplace=True)

            # Convert back to the original `values` format
            result_values = []
            for ts, row in all_df.iterrows():
                timestamp_float = ts.timestamp()
                value = row["value"]
                # Convert NaN to None, keep original values
                if pd.isna(value):
                    value = None
                result_values.append([timestamp_float, value])

            item["values"] = result_values

    @staticmethod
    def enforce_fill_budget(start, end, step, data_list) -> dict:
        budget = Metrics._prepare_range_budget(
            int(float(start) * 1000),
            int(float(end) * 1000),
            step,
        )
        return Metrics._enforce_range_response_budget(
            {"status": "success", "data": {"result": data_list}},
            budget,
        )

    @staticmethod
    def query_metric_by_instance(
        metric_query: str,
        instance_id: str,
        instance_id_keys: list,
        dimensions: list,
        *,
        series_limit: int | None = None,
        series_mode: str | None = None,
    ):
        """
        根据实例ID查询指标，按维度分组

        :param metric_query: 指标查询语句模板，包含 __$labels__ 占位符
        :param instance_id: 实例ID，字符串元组格式，如 "('aa', 'bb')"
        :param instance_id_keys: 实例ID对应的维度键列表，如 ["name", "id"]
        :param dimensions: 用于分组的维度列表
        :param series_limit: 可选，限制返回序列数（列表维度预览用）
        :param series_mode: top / bottom / limited，配合 series_limit
        :return: 查询结果
        """
        # 解析 instance_id 字符串元组
        instance_id_values = parse_instance_id(instance_id)
        if not instance_id_keys:
            raise BaseAppException("指标未配置有效的 instance_id_keys，无法按实例查询")

        # 构建标签过滤条件: name="aa", id="bb"
        label_conditions = []
        for key, value in zip(instance_id_keys, instance_id_values):
            label_conditions.append(f'{key}="{value}"')
        labels_str = ", ".join(label_conditions)

        # 替换查询语句中的占位符
        query = metric_query.replace("__$labels__", labels_str)

        # 兼容两种 dimensions 格式: [{"name": "xxx"}] 或 ["xxx"]
        if dimensions:
            dimension_names = [d["name"] if isinstance(d, dict) else d for d in dimensions]
        else:
            dimension_names = []
        group_by = ", ".join(dimension_names) if dimension_names else ""

        # 使用 any() 聚合函数进行即时查询
        if group_by:
            final_query = f"any({query}) by ({group_by})"
        else:
            final_query = f"any({query})"

        # 列表维度预览：高维指标截断，避免浮层刷屏；完整明细走搜索页。
        if series_limit is not None:
            try:
                limit = int(series_limit)
            except (TypeError, ValueError):
                limit = 0
            if limit > 0:
                mode = (series_mode or "top").lower()
                if mode == "bottom":
                    final_query = f"bottomk({limit}, {final_query})"
                elif mode == "limited":
                    final_query = f"limitk({limit}, {final_query})"
                else:
                    final_query = f"topk({limit}, {final_query})"

        return VictoriaMetricsAPI().query(final_query)

    @staticmethod
    def convert_instance_list_metrics(monitor_object_id: int, instances: list) -> list:
        """
        对实例列表中的补充指标进行单位转换

        :param monitor_object_id: 监控对象ID
        :param instances: 实例列表，每个实例包含指标名称作为key，值为字符串
        :return: 转换后的实例列表，指标值变为 {"value": "xxx", "unit": "xxx"} 格式
        """
        if not instances:
            return instances

        monitor_obj = MonitorObject.objects.filter(id=monitor_object_id).first()
        if not monitor_obj:
            return instances

        # 取数 key 必须与 MonitorObjectService._fill_display_metrics 一致:
        # display_fields 绑定用 (plugin, metric) 复合 key,supplementary 兜底用裸指标名。
        targets = Metrics._resolve_convert_targets(monitor_object_id, monitor_obj)
        if not targets:
            return instances

        for out_key, source_unit, data_type in targets:
            if not source_unit:
                continue

            if data_type == "Enum":
                for instance in instances:
                    raw_value = instance.get(out_key)
                    if raw_value is not None and not isinstance(raw_value, dict):
                        instance[out_key] = {"value": str(raw_value), "unit": ""}
                continue

            values = []
            valid_indices = []
            for idx, instance in enumerate(instances):
                raw_value = instance.get(out_key)
                if raw_value is not None and not isinstance(raw_value, dict):
                    try:
                        values.append(float(raw_value))
                        valid_indices.append(idx)
                    except (ValueError, TypeError):
                        pass

            if not values:
                continue

            converted_values, target_unit = UnitConverter.auto_convert(values, source_unit)
            display_unit = UnitConverter.get_display_unit(target_unit)

            for i, idx in enumerate(valid_indices):
                instances[idx][out_key] = {
                    "value": str(converted_values[i]),
                    "unit": display_unit,
                }

        return instances

    @staticmethod
    def _resolve_convert_targets(monitor_object_id, monitor_obj):
        """返回 [(out_key, source_unit, data_type), ...],与回填 key 规则保持一致。"""
        bindings = extract_metric_bindings(monitor_obj.display_fields)
        if bindings:
            metrics = (
                Metric.objects.filter(monitor_object_id=monitor_object_id, name__in=[b["metric"] for b in bindings])
                .select_related("monitor_plugin")
                .values("name", "unit", "data_type", "monitor_plugin__name")
            )
            by_plugin = {((m["monitor_plugin__name"] or ""), m["name"]): m for m in metrics}
            by_name = {}
            for m in metrics:
                by_name.setdefault(m["name"], m)
            targets = []
            for binding in bindings:
                plugin_name, metric_name = binding["plugin"], binding["metric"]
                meta = by_plugin.get((plugin_name, metric_name)) if plugin_name else by_name.get(metric_name)
                if not meta:
                    continue
                targets.append((display_field_key(plugin_name, metric_name), meta["unit"], meta["data_type"]))
            return targets

        supplementary = monitor_obj.supplementary_indicators
        if not supplementary:
            return []
        metrics = Metric.objects.filter(monitor_object_id=monitor_object_id, name__in=supplementary).values("name", "unit", "data_type")
        unit_map = {m["name"]: m["unit"] for m in metrics}
        dtype_map = {m["name"]: m["data_type"] for m in metrics}
        return [(name, unit_map.get(name), dtype_map.get(name)) for name in supplementary]
