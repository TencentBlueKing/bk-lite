import re

import pandas as pd

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import monitor_logger as logger
from apps.monitor.models.monitor_metrics import Metric
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.utils.dimension import parse_instance_id
from apps.monitor.utils.display_fields_metrics import (
    display_field_key,
    extract_metric_bindings,
)
from apps.monitor.utils.instance_id_keys import resolve_metric_instance_id_keys
from apps.monitor.utils.unit_converter import UnitConverter
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI


class Metrics:
    _STEP_PATTERN = re.compile(r"^(?P<value>\d+)(?P<unit>[smhdw])$")
    MAX_GAP_DETECTION_POINTS = 50000

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
    def get_metrics(query):
        """查询指标信息"""
        return VictoriaMetricsAPI().query(query)

    @staticmethod
    def get_metrics_range(
        query,
        start,
        end,
        step,
        detect_gaps=False,
        collection_interval_seconds=None,
        max_gap_detection_points=None,
    ):
        """查询指标（范围）"""
        step_seconds = Metrics.parse_step_to_seconds(step)
        start = int(start) / 1000  # Convert milliseconds to seconds
        end = int(end) / 1000  # Convert milliseconds to seconds
        vm_api = VictoriaMetricsAPI()
        resp = vm_api.query_range(query, start, end, step)
        if detect_gaps:
            data = resp.setdefault("data", {})
            try:
                collection_interval = int(collection_interval_seconds)
            except (TypeError, ValueError):
                collection_interval = 0

            detection_limit = max_gap_detection_points or Metrics.MAX_GAP_DETECTION_POINTS
            detection_points = int((end - start) / collection_interval) + 1 if collection_interval > 0 else 0

            if collection_interval > 0 and detection_points > detection_limit:
                data["gaps"] = []
                data["gap_detection"] = {
                    "status": "limited",
                    "limited": True,
                    "reason": "max_points_exceeded",
                }
            elif collection_interval > 0:
                detection_resp = vm_api.query_range(query, start, end, f"{collection_interval}s")
                gaps = Metrics.detect_gap_intervals(
                    detection_resp.get("data", {}).get("result", []),
                    collection_interval,
                )
                data["gaps"] = gaps
                data["gap_detection"] = {"status": "ok", "limited": False}
            else:
                data["gaps"] = []
                data["gap_detection"] = {"status": "skipped", "limited": False}
        Metrics.fill_missing_points(start, end, step_seconds, resp.get("data", {}).get("result", []))
        return resp

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
    def detect_gap_intervals(data_list, collection_interval_seconds):
        try:
            collection_interval = int(collection_interval_seconds)
        except (TypeError, ValueError):
            return []
        if collection_interval <= 0:
            return []

        tolerance_seconds = max(collection_interval * 2, 60)
        gaps = []

        for item in data_list:
            real_points = sorted(
                float(timestamp)
                for timestamp, value in item.get("values", [])
                if value is not None
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

        return Metrics.merge_gap_intervals(gaps, collection_interval)

    @staticmethod
    def merge_gap_intervals(gaps, collection_interval_seconds):
        merged = []
        for gap in sorted(gaps, key=lambda item: (item["start"], item["end"])):
            if not merged or gap["start"] > merged[-1]["end"] + collection_interval_seconds:
                merged.append({**gap, "series": list(gap.get("series", []))})
                continue

            current = merged[-1]
            current["end"] = max(current["end"], gap["end"])
            current["duration"] = current["end"] - current["start"] + collection_interval_seconds
            current["series"].extend(gap.get("series", []))

        return merged

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
    def query_metric_by_instance(metric_query: str, instance_id: str, instance_id_keys: list, dimensions: list):
        """
        根据实例ID查询指标，按维度分组

        :param metric_query: 指标查询语句模板，包含 __$labels__ 占位符
        :param instance_id: 实例ID，字符串元组格式，如 "('aa', 'bb')"
        :param instance_id_keys: 实例ID对应的维度键列表，如 ["name", "id"]
        :param dimensions: 用于分组的维度列表
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
        metrics = Metric.objects.filter(monitor_object_id=monitor_object_id, name__in=supplementary).values(
            "name", "unit", "data_type"
        )
        unit_map = {m["name"]: m["unit"] for m in metrics}
        dtype_map = {m["name"]: m["data_type"] for m in metrics}
        return [(name, unit_map.get(name), dtype_map.get(name)) for name in supplementary]
