import importlib


def _migration():
    return importlib.import_module("apps.operation_analysis.migrations.0023_remove_trend_group_by_params")


class _SavedModel:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.save_calls = []

    def save(self, update_fields=None):
        self.save_calls.append(tuple(update_fields or []))


class _QuerySet:
    def __init__(self, items, rest_api_filter=None):
        self._items = items
        self._rest_api_filter = rest_api_filter

    def filter(self, **kwargs):
        rest_apis = kwargs.get("rest_api__in")
        if rest_apis is None:
            return self
        allowed = set(rest_apis)
        return _QuerySet([item for item in self._items if item.rest_api in allowed], rest_api_filter=allowed)

    def all(self):
        return self

    def iterator(self):
        return iter(self._items)

    def __iter__(self):
        return iter(self._items)


class _Manager:
    def __init__(self, items):
        self._items = items

    def filter(self, **kwargs):
        return _QuerySet(self._items).filter(**kwargs)

    def all(self):
        return _QuerySet(self._items)


class _Model:
    def __init__(self, items):
        self.objects = _Manager(items)


class _Apps:
    def __init__(self, datasources, canvases_by_model):
        self._datasources = datasources
        self._canvases_by_model = canvases_by_model

    def get_model(self, app_label, model_name):
        assert app_label == "operation_analysis"
        if model_name == "DataSourceAPIModel":
            return _Model(self._datasources)
        return _Model(self._canvases_by_model[model_name])


def test_remove_trend_group_by_strips_trend_datasource_and_matching_widgets_only():
    migration = _migration()
    trend_ds = _SavedModel(
        name="告警趋势",
        rest_api="alert/get_alert_trend_data",
        params=[
            {"name": "time", "filterType": "filter"},
            {"name": "group_by", "filterType": "fixed", "value": "day"},
        ],
        updated_at=None,
    )
    cost_ds = _SavedModel(
        name="云资源费用分布",
        rest_api="cmdb/get_cloud_cost_distribution",
        params=[
            {"name": "group_by", "filterType": "params", "value": "instance_type"},
        ],
        updated_at=None,
    )
    dashboard = _SavedModel(
        view_sets=[
            {
                "valueConfig": {
                    "dataSource": "告警趋势::alert/get_alert_trend_data",
                    "dataSourceParams": [
                        {"name": "time", "value": 10080},
                        {"name": "group_by", "value": "day"},
                    ],
                }
            },
            {
                "valueConfig": {
                    "dataSource": "云资源费用分布::cmdb/get_cloud_cost_distribution",
                    "dataSourceParams": [
                        {"name": "group_by", "value": "department"},
                    ],
                }
            },
            {
                "valueConfig": {
                    "dataSource": "CMDB 变更趋势",
                    "params": [{"name": "group_by", "value": "hour"}],
                }
            },
        ],
        updated_at=None,
    )
    # 名称映射：仅名字、无 ::rest_api 的 widget 依赖 DataSourceAPIModel.name
    change_ds = _SavedModel(
        name="CMDB 变更趋势",
        rest_api="cmdb/get_change_trend",
        params=[{"name": "group_by", "value": "day"}],
        updated_at=None,
    )

    apps = _Apps(
        datasources=[trend_ds, cost_ds, change_ds],
        canvases_by_model={
            "Dashboard": [dashboard],
            "Screen": [],
            "Report": [],
        },
    )

    migration.remove_trend_group_by_residuals(apps, schema_editor=None)

    assert [p["name"] for p in trend_ds.params] == ["time"]
    assert [p["name"] for p in change_ds.params] == []
    assert cost_ds.params == [
        {"name": "group_by", "filterType": "params", "value": "instance_type"},
    ]
    assert cost_ds.save_calls == []

    widgets = dashboard.view_sets
    assert [p["name"] for p in widgets[0]["valueConfig"]["dataSourceParams"]] == ["time"]
    assert widgets[1]["valueConfig"]["dataSourceParams"] == [
        {"name": "group_by", "value": "department"},
    ]
    assert widgets[2]["valueConfig"]["params"] == []
    assert dashboard.save_calls == [("view_sets", "updated_at")]


def test_remove_trend_group_by_is_idempotent():
    migration = _migration()
    trend_ds = _SavedModel(
        name="告警等级趋势",
        rest_api="alert/get_alert_level_trend",
        params=[{"name": "time", "filterType": "filter"}],
        updated_at=None,
    )
    dashboard = _SavedModel(
        view_sets={
            "items": [
                {
                    "valueConfig": {
                        "dataSource": "告警等级趋势::alert/get_alert_level_trend",
                        "dataSourceParams": [{"name": "time", "value": 10080}],
                    }
                }
            ]
        },
        updated_at=None,
    )
    apps = _Apps(
        datasources=[trend_ds],
        canvases_by_model={"Dashboard": [dashboard], "Screen": [], "Report": []},
    )

    migration.remove_trend_group_by_residuals(apps, schema_editor=None)
    migration.remove_trend_group_by_residuals(apps, schema_editor=None)

    assert trend_ds.save_calls == []
    assert dashboard.save_calls == []


def test_extract_rest_api_supports_name_lookup_and_namespaced_key():
    migration = _migration()
    mapping = {"变更趋势": "cmdb/get_change_trend"}
    assert migration._extract_rest_api("变更趋势::cmdb/get_change_trend", mapping) == "cmdb/get_change_trend"
    assert migration._extract_rest_api("cmdb/get_change_trend", mapping) == "cmdb/get_change_trend"
    assert migration._extract_rest_api("变更趋势", mapping) == "cmdb/get_change_trend"
    assert migration._extract_rest_api("云费用", mapping) is None
