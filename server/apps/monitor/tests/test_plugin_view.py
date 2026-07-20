"""MonitorPluginViewSet 视图规格测试。"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models import MonitorPlugin
from apps.monitor.models.monitor_object import MonitorObject, MonitorObjectType
from apps.monitor.views.plugin import MonitorPluginViewSet

pytestmark = pytest.mark.django_db

BASE = "/api/v1/monitor"


class TestEnsureModifiable:
    def test_builtin_plugin_raises(self):
        plugin = MonitorPlugin(name="x", is_pre=True)
        with pytest.raises(BaseAppException):
            MonitorPluginViewSet._ensure_modifiable(plugin)

    def test_custom_plugin_ok(self):
        plugin = MonitorPlugin(name="x", is_pre=False)
        assert MonitorPluginViewSet._ensure_modifiable(plugin) is None


class TestPluginList:
    def test_list_marks_custom_and_display(self, api_client):
        MonitorPlugin.objects.create(name="builtinp", template_type="builtin", description="d1")
        MonitorPlugin.objects.create(
            name="apip",
            template_type="api",
            display_name="API插件",
            description="d2",
        )
        resp = api_client.get(f"{BASE}/api/monitor_plugin/")
        assert resp.status_code == 200
        rows = {r["name"]: r for r in resp.json()["data"]}
        assert rows["apip"]["is_custom"] is True
        assert rows["apip"]["display_name"] == "API插件"
        assert rows["builtinp"]["is_custom"] is False

    def test_list_preserves_related_object_order_and_parent_choice(self, api_client):
        later_type = MonitorObjectType.objects.create(id="PVLaterType", name="Later", order=200)
        earlier_type = MonitorObjectType.objects.create(id="PVEarlierType", name="Earlier", order=100)
        lower_id_later = MonitorObject.objects.create(
            name="PVParentOrderedLater",
            level="base",
            type=later_type,
            order=1,
        )
        higher_id_earlier = MonitorObject.objects.create(
            name="PVParentOrderedEarlier",
            level="base",
            type=earlier_type,
            order=300,
        )
        child = MonitorObject.objects.create(
            name="PVChildOrderedFirst",
            level="derivative",
            parent=higher_id_earlier,
            type=earlier_type,
            order=50,
        )
        plugin = MonitorPlugin.objects.create(
            name="PVOrderingPlugin",
            template_type="builtin",
        )
        plugin.monitor_object.add(lower_id_later, higher_id_earlier, child)

        response = api_client.get(f"{BASE}/api/monitor_plugin/?name=PVOrderingPlugin")

        assert response.status_code == 200
        rows = response.json()["data"]
        assert len(rows) == 1
        assert rows[0]["monitor_object"] == [child.id, higher_id_earlier.id, lower_id_later.id]
        assert rows[0]["parent_monitor_object"] == higher_id_earlier.id

    def test_list_queries_remain_constant_for_multiple_plugins(self, api_client):
        parent = MonitorObject.objects.create(name="PVPerfParent", level="base")
        expected_names = []
        for index in range(4):
            plugin = MonitorPlugin.objects.create(
                name=f"PVPerfPlugin{index}",
                template_type="builtin",
            )
            plugin.monitor_object.add(parent)
            expected_names.append(plugin.name)
        MonitorPlugin.objects.create(name="PVPerfPluginUnbound", template_type="builtin")

        responses = []
        for path in (
            f"{BASE}/api/monitor_plugin/?name=PVPerfPlugin",
            f"{BASE}/api/monitor_plugin/?monitor_object_id=&name=PVPerfPlugin",
        ):
            with CaptureQueriesContext(connection) as queries:
                response = api_client.get(path)
            assert response.status_code == 200
            assert len(queries) == 2
            responses.append(response.json()["data"])

        assert responses[0] == responses[1]
        assert {row["name"] for row in responses[0]} == {*expected_names, "PVPerfPluginUnbound"}

        with CaptureQueriesContext(connection) as queries:
            response = api_client.get(f"{BASE}/api/monitor_plugin/?monitor_object_id={parent.id}&name=PVPerfPlugin")

        assert response.status_code == 200
        assert len(queries) == 2
        assert {row["name"] for row in response.json()["data"]} == set(expected_names)

    @pytest.mark.parametrize(
        ("query", "expected_names"),
        [
            ("template_type=api", {"PVFilterApi", "PVFilterApiOther"}),
            ("template_id=filter-template", {"PVFilterApi", "PVFilterBuiltin"}),
            ("name=PVFilterApiOther", {"PVFilterApiOther"}),
        ],
    )
    def test_list_keeps_plugin_field_filters(self, api_client, query, expected_names):
        MonitorPlugin.objects.create(
            name="PVFilterApi",
            template_type="api",
            template_id="filter-template",
            display_name="FilterName",
        )
        MonitorPlugin.objects.create(
            name="PVFilterApiOther",
            template_type="api",
            template_id="other-template",
            display_name="Other",
        )
        MonitorPlugin.objects.create(name="PVFilterBuiltin", template_type="builtin", template_id="filter-template-builtin")

        response = api_client.get(f"{BASE}/api/monitor_plugin/?{query}")

        assert response.status_code == 200
        assert {row["name"] for row in response.json()["data"]} == expected_names

    def test_list_keeps_default_plugin_order(self, api_client):
        first = MonitorPlugin.objects.create(name="PVCompatibilityOrderFirst")
        second = MonitorPlugin.objects.create(name="PVCompatibilityOrderSecond")

        response = api_client.get(f"{BASE}/api/monitor_plugin/?name=PVCompatibilityOrder")

        assert response.status_code == 200
        assert [row["name"] for row in response.json()["data"]] == list(
            MonitorPlugin.objects.filter(id__in=[first.id, second.id]).values_list("name", flat=True)
        )

    @pytest.mark.parametrize(
        ("locale", "translations", "expected_builtin"),
        [
            ("en", {"name": "Builtin EN"}, ("Builtin EN", "Builtin database description")),
            ("zh-Hans", {"name": "内置中文", "desc": "内置中文描述"}, ("内置中文", "内置中文描述")),
        ],
    )
    def test_list_keeps_locale_display_and_custom_template_semantics(
        self,
        api_client,
        authenticated_user,
        mocker,
        locale,
        translations,
        expected_builtin,
    ):
        class FakeLanguageLoader:
            def __init__(self, active_locale):
                self.active_locale = active_locale

            def get(self, key):
                if self.active_locale != locale:
                    return None
                if key.endswith("PVLocaleBuiltin.name"):
                    return translations.get("name")
                if key.endswith("PVLocaleBuiltin.desc"):
                    return translations.get("desc")
                return None

        authenticated_user.locale = locale
        authenticated_user.save(update_fields=["locale"])
        mocker.patch(
            "apps.monitor.views.plugin.LanguageLoader",
            side_effect=lambda app, default_lang: FakeLanguageLoader(default_lang),
        )
        MonitorPlugin.objects.create(
            name="PVLocaleBuiltin",
            template_type="builtin",
            display_name="Builtin database name",
            description="Builtin database description",
        )
        for template_type in ("api", "pull", "snmp"):
            MonitorPlugin.objects.create(
                name=f"PVLocale{template_type}",
                template_type=template_type,
                display_name=f"{template_type} database name",
                description=f"{template_type} database description",
                template_id=f"locale-{template_type}",
            )

        response = api_client.get(f"{BASE}/api/monitor_plugin/?name=PVLocale")

        assert response.status_code == 200
        rows = {row["name"]: row for row in response.json()["data"]}
        assert (rows["PVLocaleBuiltin"]["display_name"], rows["PVLocaleBuiltin"]["display_description"]) == expected_builtin
        assert rows["PVLocaleBuiltin"]["is_custom"] is False
        for template_type in ("api", "pull", "snmp"):
            row = rows[f"PVLocale{template_type}"]
            assert (row["display_name"], row["display_description"], row["is_custom"]) == (
                f"{template_type} database name",
                f"{template_type} database description",
                True,
            )

    def test_non_list_actions_start_from_unprefetched_base_queryset(self):
        assert MonitorPluginViewSet().get_queryset()._prefetch_related_lookups == ()


class TestGetAccessGuide:
    def test_non_api_template_errors(self, api_client):
        plugin = MonitorPlugin.objects.create(name="snmpp", template_type="snmp", template_id="t1")
        resp = api_client.get(f"{BASE}/api/monitor_plugin/{plugin.id}/access_guide/")
        body = resp.json()
        assert body.get("result") is False or resp.status_code != 200

    def test_api_template_returns_document(self, api_client, mocker):
        obj = MonitorObject.objects.create(name="AGObj", level="base", instance_id_keys=["instance_id"])
        plugin = MonitorPlugin.objects.create(
            name="apip2",
            template_type="api",
            template_id="t-api",
            display_name="API2",
        )
        plugin.monitor_object.add(obj)
        mocker.patch("apps.monitor.services.template_access_guide.NodeMgmt").return_value.get_cloud_region_envconfig.return_value = {
            "NODE_SERVER_URL": "https://node.example.com:8080"
        }
        resp = api_client.get(f"{BASE}/api/monitor_plugin/{plugin.id}/access_guide/?organization_id=1&cloud_region_id=2")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["template_id"] == "t-api"
        assert data["endpoint"].endswith("/telegraf/api")
