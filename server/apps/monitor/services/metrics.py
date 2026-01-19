import ast

import pandas as pd

from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI


class Metrics:
    @staticmethod
    def get_metrics(query):
        """查询指标信息"""
        return VictoriaMetricsAPI().query(query)

    @staticmethod
    def get_metrics_range(query, start, end, step):
        """查询指标（范围）"""
        start = int(start) / 1000  # Convert milliseconds to seconds
        end = int(end) / 1000  # Convert milliseconds to seconds
        resp = VictoriaMetricsAPI().query_range(query, start, end, step)
        Metrics.fill_missing_points(
            start, end, step, resp.get("data", {}).get("result", [])
        )
        return resp

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
            original_df["timestamp"] = pd.to_datetime(
                original_df["timestamp"].astype(float), unit="s"
            )
            original_df.set_index("timestamp", inplace=True)

            # Create complete time range DataFrame (start and end are now in seconds)
            full_time_index = pd.date_range(
                start=pd.to_datetime(start, unit="s"),
                end=pd.to_datetime(end, unit="s"),
                freq=f"{step}S",
            )
            full_df = pd.DataFrame(index=full_time_index, columns=["value"])
            full_df["value"] = None

            # Concatenate and sort all timestamps
            all_df = pd.concat([original_df, full_df])
            all_df = all_df[
                ~all_df.index.duplicated(keep="first")
            ]  # Keep original values for duplicates
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
    def query_metric_by_instance(
        metric_query: str, instance_id: str, instance_id_keys: list, dimensions: list
    ):
        """
        根据实例ID查询指标，按维度分组

        :param metric_query: 指标查询语句模板，包含 __$labels__ 占位符
        :param instance_id: 实例ID，字符串元组格式，如 "('aa', 'bb')"
        :param instance_id_keys: 实例ID对应的维度键列表，如 ["name", "id"]
        :param dimensions: 用于分组的维度列表
        :return: 查询结果
        """
        # 解析 instance_id 字符串元组
        try:
            instance_id_values = ast.literal_eval(instance_id)
            if not isinstance(instance_id_values, tuple):
                instance_id_values = (instance_id_values,)
        except (ValueError, SyntaxError):
            instance_id_values = (instance_id,)

        # 构建标签过滤条件: name="aa", id="bb"
        label_conditions = []
        for key, value in zip(instance_id_keys, instance_id_values):
            label_conditions.append(f'{key}="{value}"')
        labels_str = ", ".join(label_conditions)

        # 替换查询语句中的占位符
        query = metric_query.replace("__$labels__", labels_str)

        # 构建分组条件
        group_by = ", ".join(dimensions) if dimensions else ""

        # 使用 any() 聚合函数进行即时查询
        if group_by:
            final_query = f"any({query}) by ({group_by})"
        else:
            final_query = f"any({query})"

        return VictoriaMetricsAPI().query(final_query)
