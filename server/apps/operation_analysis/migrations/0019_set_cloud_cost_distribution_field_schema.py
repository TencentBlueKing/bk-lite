from django.db import migrations


_TARGET_REST_API = "cmdb/get_cloud_resource_cost_distribution"
_GROUP_BY_PARAM = {
    "name": "group_by",
    "alias_name": "排行主体",
    "type": "string",
    "value": "instance_type",
    "filterType": "params",
}
_DISTRIBUTION_FIELD_SCHEMA = [
    {"key": "key", "title": "排行主体", "value_type": "string"},
    {"key": "total_cost", "title": "总费用", "value_type": "number"},
    {"key": "instance_count", "title": "实例数", "value_type": "number"},
    {"key": "pct", "title": "费用占比", "value_type": "number"},
]


def _set_distribution_field_schema(apps, schema_editor):
    datasource_model = apps.get_model("operation_analysis", "DataSourceAPIModel")
    target = datasource_model.objects.filter(rest_api=_TARGET_REST_API).first()
    if target is None:
        return

    params = []
    group_by_found = False
    for param in target.params or []:
        if param.get("name") != "group_by":
            params.append(param)
            continue

        group_by_found = True
        normalized = dict(param)
        normalized.pop("options", None)
        normalized.update(_GROUP_BY_PARAM)
        params.append(normalized)

    if not group_by_found:
        params.append(dict(_GROUP_BY_PARAM))

    if params == target.params and target.field_schema == _DISTRIBUTION_FIELD_SCHEMA:
        return

    target.params = params
    target.field_schema = _DISTRIBUTION_FIELD_SCHEMA
    target.save(update_fields=["params", "field_schema", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("operation_analysis", "0018_dashboardsharelink_resource_type"),
    ]

    operations = [
        migrations.RunPython(
            _set_distribution_field_schema,
            migrations.RunPython.noop,
        ),
    ]
