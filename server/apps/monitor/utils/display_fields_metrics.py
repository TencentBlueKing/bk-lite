# 展示指标(display_fields)的取数 key 工具。
#
# 一个监控对象下可能挂多个插件,且不同插件常定义“同名”指标(如交换机各品牌都叫
# device_temperature_celsius)。若仅按指标名回填实例值,会出现“别的品牌也展示了温度”
# 以及同名指标互相覆盖。因此展示指标的回填 key 统一用 (plugin, metric) 复合 key,
# 前后端必须用同一套规则拼 key(见 web 端 displayFieldKey)。

DISPLAY_FIELD_KEY_SEP = "::"
FIELD_DISPLAY_KEY_PREFIX = "field"


def display_field_key(plugin, metric, field=None):
    """展示列回填 key。

    - 指标值列:有插件用 ``<plugin>::<metric>``,无插件(遗留/补充指标)退化为裸指标名。
    - 字段展示列:使用 ``field::<plugin>::<metric>::<field>``，避免和指标值 key 冲突。
    """
    if field:
        return f"{FIELD_DISPLAY_KEY_PREFIX}{DISPLAY_FIELD_KEY_SEP}{plugin}{DISPLAY_FIELD_KEY_SEP}{metric}{DISPLAY_FIELD_KEY_SEP}{field}"
    if plugin:
        return f"{plugin}{DISPLAY_FIELD_KEY_SEP}{metric}"
    return metric


def is_field_display_column(col):
    return (col.get("type") or "metric") == "field"


def extract_metric_bindings(display_fields):
    """从 display_fields 抽取 (plugin, metric) 绑定的并集(保持首次出现顺序,去重)。

    返回 ``[{"plugin": <插件名或空串>, "metric": <指标名>}, ...]``。
    """
    bindings = []
    seen = set()
    for col in display_fields or []:
        if is_field_display_column(col):
            continue
        for binding in col.get("metrics", []):
            metric = binding.get("metric")
            if not metric:
                continue
            plugin = binding.get("plugin") or ""
            dedup_key = (plugin, metric)
            if dedup_key not in seen:
                seen.add(dedup_key)
                bindings.append({"plugin": plugin, "metric": metric})
    return bindings


def extract_field_bindings(display_fields):
    """从字段展示列抽取 (plugin, metric, field) 绑定并集(保持首次出现顺序,去重)。"""
    bindings = []
    seen = set()
    for col in display_fields or []:
        if not is_field_display_column(col):
            continue
        for binding in col.get("metrics", []):
            metric = binding.get("metric")
            field = binding.get("field")
            if not metric or not field:
                continue
            plugin = binding.get("plugin") or ""
            dedup_key = (plugin, metric, field)
            if dedup_key not in seen:
                seen.add(dedup_key)
                bindings.append({"plugin": plugin, "metric": metric, "field": field})
    return bindings


def extract_metric_names(display_fields):
    """从 display_fields 抽取所有绑定指标名的并集(保持首次出现顺序,去重)。

    仅用于不区分插件的旧路径(如 supplementary_indicators 兜底)。展示指标取数请用
    ``extract_metric_bindings`` + ``display_field_key``。
    """
    names = []
    seen = set()
    for col in display_fields or []:
        for binding in col.get("metrics", []):
            metric = binding.get("metric")
            if metric and metric not in seen:
                seen.add(metric)
                names.append(metric)
    return names
