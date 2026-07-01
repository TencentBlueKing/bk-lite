def _escape_prometheus_label_value(value):
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def convert_to_influxdb(data):
    """数据格式转换"""
    influxdb_data = []

    # 遍历所有 resource_id
    for resource_id, metrics in data["data"].items():
        for metric_name, metric_data in metrics.items():

            # 判断 metric_data 是否包含 'dims' 这个 key
            if isinstance(metric_data, dict) and "dims" in metric_data and "values" in metric_data:
                # 说明这个指标是 **有维度的**
                dims = metric_data['dims']  # 维度列表
                values = metric_data['values']  # 时间序列数据

                # 构建维度的 tag 字符串
                tag_str = f"resource_id={resource_id}"
                for dim_key, dim_value in dims:
                    tag_str += f",{dim_key}={dim_value}"

                # 遍历时间序列数据，构造 InfluxDB 行协议
                for timestamp, value in values:
                    influxdb_line = f"{metric_name},{tag_str} value={value} {timestamp}"
                    influxdb_data.append(influxdb_line)

            elif isinstance(metric_data, list):
                # 说明这个指标是 **无维度的**
                for timestamp, value in metric_data:
                    influxdb_line = f"{metric_name},resource_id={resource_id} value={value} {timestamp}"
                    influxdb_data.append(influxdb_line)

    return influxdb_data


def convert_to_prometheus(data):
    """数据格式转换为 Prometheus"""
    metrics_map = {}  # {metric_name: [所有该指标的数据]}

    # **第一步：遍历数据，按 `metric_name` 进行分组**
    for resource_tup, metrics in data.items():
        resource_id = _escape_prometheus_label_value(resource_tup[0])
        resource_type = _escape_prometheus_label_value(resource_tup[1])
        for metric_name, metric_data in metrics.items():
            if metric_name not in metrics_map:
                metrics_map[metric_name] = []  # 初始化该指标的存储列表

            if isinstance(metric_data, dict):
                # **有维度的指标**
                for dims_tuple, values in metric_data.items():
                    # **构建 Prometheus 标签字符串**
                    label_str = f'resource_id="{resource_id}", resource_type="{resource_type}"'
                    for dim_key, dim_value in dims_tuple:
                        label_str += f', {dim_key}="{_escape_prometheus_label_value(dim_value)}"'

                    # **遍历时间序列数据**
                    for timestamp, value in values:
                        if timestamp:
                            prometheus_line = f'{metric_name}{{{label_str}}} {value} {int(timestamp)}'
                        else:
                            prometheus_line = f'{metric_name}{{{label_str}}} {value}'
                        metrics_map[metric_name].append(prometheus_line)

            elif isinstance(metric_data, list):
                # **无维度的指标**
                for item in metric_data:
                    if isinstance(item, (tuple, list)) and len(item) == 2:
                        timestamp, value = item
                        label_str = (
                            f'resource_id="{resource_id}", '
                            f'resource_type="{resource_type}"'
                        )
                        if timestamp:
                            prometheus_line = (
                                f"{metric_name}{{{label_str}}} "
                                f"{value} {int(timestamp)}"
                            )
                        else:
                            prometheus_line = f"{metric_name}{{{label_str}}} {value}"
                        metrics_map[metric_name].append(prometheus_line)

    # **第二步：遍历 `metrics_map`，生成最终 Prometheus 格式**
    prometheus_data = []
    for metric_name, metric_lines in metrics_map.items():
        # **先添加 HELP 和 TYPE**
        prometheus_data.append(f"# HELP {metric_name} Auto-generated help for {metric_name}")
        prometheus_data.append(f"# TYPE {metric_name} gauge")
        # **再添加所有数据**
        prometheus_data.extend(metric_lines)

    return prometheus_data
