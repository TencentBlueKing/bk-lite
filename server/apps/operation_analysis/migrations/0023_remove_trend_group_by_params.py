from django.db import migrations

# 与 apps.core.utils.trend_granularity.TREND_GROUP_BY_AUTO_REST_APIS 保持一致。
# 迁移内联副本，避免历史迁移依赖可变运行时模块。
_TREND_GROUP_BY_AUTO_REST_APIS = frozenset(
    {
        "alert/get_alert_trend_data",
        "alert/get_alert_level_trend",
        "cmdb/get_change_trend",
    }
)


def _strip_group_by_params(params):
    if not isinstance(params, list):
        return params, False
    next_params = [param for param in params if not (isinstance(param, dict) and param.get("name") == "group_by")]
    return next_params, next_params != params


def _extract_rest_api(data_source, name_to_rest_api):
    if not isinstance(data_source, str):
        return None
    text = data_source.strip()
    if not text:
        return None
    if "::" in text:
        return text.rsplit("::", 1)[-1].strip() or None
    if text in _TREND_GROUP_BY_AUTO_REST_APIS:
        return text
    return name_to_rest_api.get(text)


def _is_trend_auto_widget(value_config, name_to_rest_api):
    if not isinstance(value_config, dict):
        return False
    rest_api = _extract_rest_api(value_config.get("dataSource"), name_to_rest_api)
    return rest_api in _TREND_GROUP_BY_AUTO_REST_APIS


def _strip_widget_group_by(value_config, name_to_rest_api):
    if not _is_trend_auto_widget(value_config, name_to_rest_api):
        return value_config, False
    changed = False
    next_config = dict(value_config)
    for key in ("dataSourceParams", "params"):
        stripped, did_change = _strip_group_by_params(next_config.get(key))
        if did_change:
            next_config[key] = stripped
            changed = True
    return next_config, changed


def _iter_view_items(view_sets):
    if isinstance(view_sets, list):
        return view_sets
    if isinstance(view_sets, dict):
        items = view_sets.get("items")
        if isinstance(items, list):
            return items
    return []


def _strip_view_sets_group_by(view_sets, name_to_rest_api):
    items = _iter_view_items(view_sets)
    if not items:
        return view_sets, False

    changed = False
    next_items = []
    for item in items:
        if not isinstance(item, dict):
            next_items.append(item)
            continue
        next_item = dict(item)
        value_config = next_item.get("valueConfig")
        next_value_config, did_change = _strip_widget_group_by(value_config, name_to_rest_api)
        if did_change:
            next_item["valueConfig"] = next_value_config
            changed = True
        next_items.append(next_item)

    if not changed:
        return view_sets, False

    if isinstance(view_sets, list):
        return next_items, True

    next_view_sets = dict(view_sets)
    next_view_sets["items"] = next_items
    return next_view_sets, True


def _save_canvas(canvas, next_view_sets):
    canvas.view_sets = next_view_sets
    update_fields = ["view_sets"]
    if hasattr(canvas, "updated_at"):
        update_fields.append("updated_at")
    canvas.save(update_fields=update_fields)


def _build_name_to_rest_api(datasource_model):
    mapping = {}
    for datasource in datasource_model.objects.all().iterator():
        name = getattr(datasource, "name", None)
        rest_api = getattr(datasource, "rest_api", None)
        if isinstance(name, str) and name.strip() and isinstance(rest_api, str) and rest_api.strip():
            mapping[name.strip()] = rest_api.strip()
    return mapping


def remove_trend_group_by_residuals(apps, schema_editor):
    """仅清理三类趋势数据源及其绑定 widget 的 group_by 残留。

    reverse 为 noop：运行时代码已忽略客户端 group_by，回滚代码后残留参数也不会再被采用；
    数据侧不重建已删除的 schema/widget 参数。
    """
    datasource_model = apps.get_model("operation_analysis", "DataSourceAPIModel")
    for datasource in datasource_model.objects.filter(rest_api__in=sorted(_TREND_GROUP_BY_AUTO_REST_APIS)):
        next_params, changed = _strip_group_by_params(datasource.params)
        if changed:
            datasource.params = next_params
            update_fields = ["params"]
            if hasattr(datasource, "updated_at"):
                update_fields.append("updated_at")
            datasource.save(update_fields=update_fields)

    name_to_rest_api = _build_name_to_rest_api(datasource_model)
    for model_name in ("Dashboard", "Screen", "Report"):
        canvas_model = apps.get_model("operation_analysis", model_name)
        for canvas in canvas_model.objects.all().iterator():
            next_view_sets, changed = _strip_view_sets_group_by(canvas.view_sets, name_to_rest_api)
            if changed:
                _save_canvas(canvas, next_view_sets)


class Migration(migrations.Migration):
    dependencies = [
        ("operation_analysis", "0022_prometheus_source_type"),
    ]

    operations = [
        migrations.RunPython(
            remove_trend_group_by_residuals,
            migrations.RunPython.noop,
        ),
    ]
