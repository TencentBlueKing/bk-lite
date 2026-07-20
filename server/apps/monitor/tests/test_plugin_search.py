"""MonitorPluginViewSet list 视图关键字搜索规格测试。

搜索语义:按当前界面可见文本搜索,匹配下列四个字段(任一命中即返回):
  1) plugin.name                       — 技术标识,兼容老用法
  2) display_name                      — i18n 翻译,fallback 到 DB 字段
  3) display_description               — i18n 翻译,fallback 到 DB 字段
  4) parent_object_display_name        — 父监控对象 DB 字段(卡片 tag「交换机/路由器」)

注意:keyword 过滤在 i18n 翻译**之后**做(内存匹配),不依赖 DB icontains,
所以中文/英文/父对象 tag 翻译后字段都能命中。

注意:DB 字段 `description`(技术细节:OID / MIB / 企业号)不参与搜索。
否则会引入 3Com 这种「MIB 名带 HUAWEI 引用」导致的误命中
(例如 3Com 的 A3COM-HUAWEI-LswDEVM-MIB,i18n display_description 是干净的短版)。

兼容:历史 ?name=xxx 参数仍可作为 keyword 别名(过滤语义相同),
keyword 优先,二者同时传时 keyword 生效。
"""

import pytest

from apps.monitor.models import MonitorPlugin
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.views.plugin import MonitorPluginViewSet

pytestmark = pytest.mark.django_db

BASE = "/api/v1/monitor"


@pytest.fixture(autouse=True)
def disable_license_guard(settings):
    """让视图测试绕过企业版许可证守卫，专注验证搜索行为。"""
    settings.LICENSE_MGMT_ENABLED = False


@pytest.fixture
def switch_object():
    return MonitorObject.objects.create(name="switch", display_name="交换机", level="base")


@pytest.fixture
def router_object():
    return MonitorObject.objects.create(name="router", display_name="路由器", level="base")


@pytest.fixture
def storage_object():
    return MonitorObject.objects.create(name="storage", display_name="存储设备", level="base")


@pytest.fixture
def huawei_switch_plugin(switch_object):
    p = MonitorPlugin.objects.create(
        name="huawei_switch",
        template_type="builtin",
        display_name="华为 (Telegraf)",
        description="Huawei Ethernet switch SNMP plugin",
    )
    p.monitor_object.add(switch_object)
    return p


@pytest.fixture
def huawei_ar_plugin(router_object):
    p = MonitorPlugin.objects.create(
        name="huawei_ar",
        template_type="builtin",
        display_name="Huawei AR (Telegraf)",
        description="Huawei AR router SNMP plugin",
    )
    p.monitor_object.add(router_object)
    return p


@pytest.fixture
def cisco_switch_plugin(switch_object):
    p = MonitorPlugin.objects.create(
        name="cisco_switch",
        template_type="builtin",
        display_name="Cisco (SNMP)",
        description="Cisco Catalyst SNMP plugin",
    )
    p.monitor_object.add(switch_object)
    return p


@pytest.fixture
def huawei_oceanstor_plugin(storage_object):
    p = MonitorPlugin.objects.create(
        name="huawei_oceanstor",
        template_type="builtin",
        display_name="华为 OceanStor (Stargazer)",
        description="Huawei OceanStor V3/V5/Dorado storage plugin",
    )
    p.monitor_object.add(storage_object)
    return p


@pytest.fixture
def threecom_switch_plugin(switch_object):
    """3Com 插件(DB description 包含 A3COM-HUAWEI-LswDEVM-MIB,
    但 i18n display_description 是干净的短版,这是 3Com MIB 误命中场景的复现)。

    在测试里通过 mocker 模拟 LanguageLoader.get 返回短版。
    """
    p = MonitorPlugin.objects.create(
        name="switch_3com",
        template_type="builtin",
        display_name="3Com (Telegraf)",
        description=(
            "3Com 交换机专用 SNMP 采集模板（A3COM-HUAWEI-LswDEVM-MIB，企业号 43）。"
            "除标准 IF-MIB 接口指标外，额外采集 3Com 私有 OID 的设备健康指标。"
            "该 MIB（企业号 43.45）与已支持的 H3C（企业号 25506 HH3C-ENTITY-EXT）不同，故单独支持。"
            "适用品牌型号——3Com 网管交换机（Switch 4200/4500/5500 等 A3COM-HUAWEI 平台，企业号 43）。"
        ),
    )
    p.monitor_object.add(switch_object)
    return p


@pytest.fixture
def zh_user(db):
    """中文 locale 用户(用于验证「华为」/「交换机」类关键词)。"""
    from apps.base.models import User

    return User.objects.create_user(
        username="zhuser",
        password="x",
        domain="d.com",
        locale="zh-Hans",
        group_list=[{"id": 1, "name": "T"}],
        roles=["admin"],
    )


@pytest.fixture
def zh_client(zh_user):
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user=zh_user)
    return client


def _mock_i18n_get(mocker, mapping):
    """模拟 LanguageLoader.get,按 key 返回 mapping 里的值,缺省 None。

    mapping: {key_path: value}
    """
    return mocker.patch(
        "apps.monitor.views.plugin.LanguageLoader.get",
        side_effect=lambda key: mapping.get(key),
    )


class TestKeywordFields:
    """搜索字段集本身的契约(防止误改 KEYWORD_FIELDS)。"""

    def test_description_db_field_excluded(self):
        """DB 字段 description 不参与搜索(避免 3Com MIB 误命中)。"""
        assert "description" not in MonitorPluginViewSet.KEYWORD_FIELDS

    def test_keyword_fields_are_visible_card_fields(self):
        """搜索字段必须是用户能在卡片上看到的字段。"""
        expected = {"name", "display_name", "display_description", "parent_object_display_name"}
        assert set(MonitorPluginViewSet.KEYWORD_FIELDS) == expected


class TestKeywordSearch:
    def test_keyword_matches_chinese_display_name(self, zh_client, huawei_switch_plugin, huawei_ar_plugin, cisco_switch_plugin):
        """中文界面搜「华为」应命中 display_name 含「华为」的插件。"""
        resp = zh_client.get(f"{BASE}/api/monitor_plugin/?keyword=华为")
        assert resp.status_code == 200
        names = {r["name"] for r in resp.json()["data"]}
        assert "huawei_switch" in names
        assert "cisco_switch" not in names

    def test_keyword_matches_english_technical_name(self, api_client, huawei_switch_plugin, huawei_ar_plugin, cisco_switch_plugin):
        """搜技术标识「huawei」应命中 plugin.name 含「huawei」的插件(兼容老用法)。"""
        resp = api_client.get(f"{BASE}/api/monitor_plugin/?keyword=huawei")
        assert resp.status_code == 200
        names = {r["name"] for r in resp.json()["data"]}
        assert "huawei_switch" in names
        assert "huawei_ar" in names
        assert "cisco_switch" not in names

    def test_keyword_matches_parent_object_tag(self, zh_client, huawei_switch_plugin, huawei_ar_plugin, cisco_switch_plugin):
        """搜「交换机」(父对象 display_name)应命中所有父对象是「交换机」的插件。"""
        resp = zh_client.get(f"{BASE}/api/monitor_plugin/?keyword=交换机")
        assert resp.status_code == 200
        names = {r["name"] for r in resp.json()["data"]}
        assert "huawei_switch" in names
        assert "cisco_switch" in names
        # 父对象是「路由器」的插件不应被命中
        assert "huawei_ar" not in names

    def test_keyword_is_case_insensitive(self, api_client, huawei_switch_plugin, huawei_ar_plugin):
        """搜索「HUAWEI」(大写)也应命中 plugin.name 的小写匹配。"""
        resp = api_client.get(f"{BASE}/api/monitor_plugin/?keyword=HUAWEI")
        assert resp.status_code == 200
        names = {r["name"] for r in resp.json()["data"]}
        assert "huawei_switch" in names
        assert "huawei_ar" in names

    def test_keyword_matches_display_description(self, api_client, mocker, huawei_switch_plugin, cisco_switch_plugin):
        """关键词「Ethernet」只出现在 i18n display_description(不在 name / display_name / 父对象)
        也应命中 — 验证 i18n 描述路径。"""
        _mock_i18n_get(
            mocker,
            {
                "monitor_object_plugin.huawei_switch.desc": "面向华为交换机的 SNMP 监控模板，支持 Ethernet 接口与 CPU 内存指标采集。",
                "monitor_object_plugin.cisco_switch.desc": "面向 Cisco 交换机的 SNMP 监控模板。",
            },
        )

        resp = api_client.get(f"{BASE}/api/monitor_plugin/?keyword=Ethernet")
        assert resp.status_code == 200
        names = {r["name"] for r in resp.json()["data"]}
        assert "huawei_switch" in names
        assert "cisco_switch" not in names

    def test_keyword_i18n_missing_falls_back_to_db_description(self, api_client, huawei_switch_plugin, cisco_switch_plugin):
        """i18n 缺失时,display_description 走 DB description fallback(无 i18n yaml 时也会命中)。"""
        # huawei_switch.description = "Huawei Ethernet switch SNMP plugin"
        # 无 i18n mock,lan.get 返回 None,display_description 走 fallback 到 DB description
        resp = api_client.get(f"{BASE}/api/monitor_plugin/?keyword=Ethernet")
        assert resp.status_code == 200
        names = {r["name"] for r in resp.json()["data"]}
        assert "huawei_switch" in names
        assert "cisco_switch" not in names

    def test_keyword_does_not_match_db_description_only(self, api_client, mocker, threecom_switch_plugin, huawei_switch_plugin):
        """3Com 回归测试:DB description 含「HUAWEI」(A3COM-HUAWEI-LswDEVM-MIB),
        但 i18n display_description 是干净短版(用户实际看到的)。
        搜「huawei」应**不**命中 3Com,因为只搜 display_description(用户所见),不搜 description(技术细节)。
        """
        _mock_i18n_get(
            mocker,
            {
                # 3Com 的 i18n 短版:用户实际看到的卡片描述
                "monitor_object_plugin.switch_3com.desc": "面向 3Com 交换机的 SNMP 监控模板，可采集 CPU 使用率、每端口流量速率等主要指标。",
                # 华为的 i18n 短版
                "monitor_object_plugin.huawei_switch.desc": "面向华为交换机的 SNMP 监控模板。",
            },
        )

        resp = api_client.get(f"{BASE}/api/monitor_plugin/?keyword=huawei")
        assert resp.status_code == 200
        names = {r["name"] for r in resp.json()["data"]}
        # 真实命中:huawei_switch(display_name + i18n desc)
        assert "huawei_switch" in names
        # 不应命中:3Com 的 description 里有 A3COM-HUAWEI-... MIB 引用,但 i18n desc 是干净的
        # 如果 description 字段被搜,3Com 会误命中(回归 bug)
        assert "switch_3com" not in names

    def test_search_huawei_full_scenario(
        self, api_client, mocker, threecom_switch_plugin, huawei_switch_plugin, huawei_ar_plugin, huawei_oceanstor_plugin, cisco_switch_plugin
    ):
        """端到端场景:搜「huawei」应只命中真正的华为产品,3Com 不命中。"""
        _mock_i18n_get(
            mocker,
            {
                "monitor_object_plugin.switch_3com.desc": "面向 3Com 交换机的 SNMP 监控模板。",
                "monitor_object_plugin.huawei_switch.desc": "面向华为交换机的 SNMP 监控模板。",
                "monitor_object_plugin.huawei_ar.desc": "面向 Huawei AR 路由器的 SNMP 监控模板。",
                "monitor_object_plugin.huawei_oceanstor.desc": "面向华为 OceanStor V3/V5/Dorado 存储的 Telegraf 模板。",
                "monitor_object_plugin.cisco_switch.desc": "面向 Cisco 交换机的 SNMP 监控模板。",
            },
        )

        resp = api_client.get(f"{BASE}/api/monitor_plugin/?keyword=huawei")
        assert resp.status_code == 200
        names = {r["name"] for r in resp.json()["data"]}
        # 3 个真华为插件都命中(name 或 display_name 匹配)
        assert {"huawei_switch", "huawei_ar", "huawei_oceanstor"} <= names
        # 3Com 误命中场景(关键断言)
        assert "switch_3com" not in names
        # cisco 不命中
        assert "cisco_switch" not in names

    def test_keyword_empty_returns_all(self, api_client, huawei_switch_plugin, huawei_ar_plugin, cisco_switch_plugin):
        """空 keyword 应返回全量(只受 monitor_object_id 过滤影响)。"""
        resp = api_client.get(f"{BASE}/api/monitor_plugin/?keyword=")
        assert resp.status_code == 200
        names = {r["name"] for r in resp.json()["data"]}
        assert {"huawei_switch", "huawei_ar", "cisco_switch"} <= names

    def test_keyword_missing_param_returns_all(self, api_client, huawei_switch_plugin, huawei_ar_plugin, cisco_switch_plugin):
        """不带 keyword 参数(完全省略)也应返回全量。"""
        resp = api_client.get(f"{BASE}/api/monitor_plugin/")
        assert resp.status_code == 200
        names = {r["name"] for r in resp.json()["data"]}
        assert {"huawei_switch", "huawei_ar", "cisco_switch"} <= names

    def test_keyword_combines_with_monitor_object_filter(
        self,
        zh_client,
        huawei_switch_plugin,
        huawei_ar_plugin,
        cisco_switch_plugin,
        switch_object,
    ):
        """监控对象筛选 + keyword 双重过滤(交集)。"""
        resp = zh_client.get(f"{BASE}/api/monitor_plugin/?monitor_object_id={switch_object.id}&keyword=Cisco")
        assert resp.status_code == 200
        names = {r["name"] for r in resp.json()["data"]}
        # 命中的 cisco_switch 既在 switch 对象下又匹配 keyword=Cisco
        assert "cisco_switch" in names
        # 父对象是 router 的 huawei_ar 应被对象筛选挡住
        assert "huawei_ar" not in names

    def test_keyword_miss_returns_empty(self, api_client, huawei_switch_plugin, huawei_ar_plugin):
        """不存在的 keyword 返回 0 条(不会因兜底逻辑误命中)。"""
        resp = api_client.get(f"{BASE}/api/monitor_plugin/?keyword=nonexistent_xyz_zzz")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_result_includes_parent_object_display_name(self, api_client, huawei_switch_plugin, huawei_ar_plugin):
        """每条结果应包含 parent_object_display_name 字段(供前端展示 + 搜索覆盖)。"""
        resp = api_client.get(f"{BASE}/api/monitor_plugin/")
        assert resp.status_code == 200
        rows = {r["name"]: r for r in resp.json()["data"]}
        assert rows["huawei_switch"]["parent_object_display_name"] == "交换机"
        assert rows["huawei_ar"]["parent_object_display_name"] == "路由器"

    def test_keyword_whitespace_only_treated_as_empty(self, api_client, huawei_switch_plugin, huawei_ar_plugin, cisco_switch_plugin):
        """纯空格 keyword 应被 strip 后视为空,返回全量。"""
        resp = api_client.get(f"{BASE}/api/monitor_plugin/?keyword=%20%20%20")
        assert resp.status_code == 200
        names = {r["name"] for r in resp.json()["data"]}
        assert {"huawei_switch", "huawei_ar", "cisco_switch"} <= names

    def test_legacy_name_param_compat_as_keyword_alias(self, api_client, huawei_switch_plugin, huawei_ar_plugin, cisco_switch_plugin):
        """历史 ?name=xxx 参数仍可作为 keyword 别名工作,过滤语义与 keyword 一致。

        这是接口兼容:前端可以只传 keyword,但不破坏既有 API 调用。
        老调用方传 ?name=cisco 应等同于 ?keyword=cisco,只命中 Cisco 插件。
        """
        resp = api_client.get(f"{BASE}/api/monitor_plugin/?name=cisco")
        assert resp.status_code == 200
        names = {r["name"] for r in resp.json()["data"]}
        assert names == {"cisco_switch"}

    def test_keyword_takes_precedence_over_name(self, api_client, huawei_switch_plugin, huawei_ar_plugin, cisco_switch_plugin):
        """当 keyword 与 name 同时存在时,keyword 优先(name 被忽略)。"""
        resp = api_client.get(f"{BASE}/api/monitor_plugin/?keyword=huawei&name=cisco")
        assert resp.status_code == 200
        names = {r["name"] for r in resp.json()["data"]}
        # 应按 keyword=huawei 命中,不按 name=cisco
        assert "huawei_switch" in names
        assert "huawei_ar" in names
        assert "cisco_switch" not in names

    def test_list_query_count_constant_with_parent_prefetch(
        self, api_client, huawei_switch_plugin, huawei_ar_plugin, cisco_switch_plugin, huawei_oceanstor_plugin
    ):
        """list 接口的 SQL 查询数应与插件数量无关(两个 prefetch 把关联一次拉完)。

        期望查询数(3 次,与插件数无关):
          1. 主 queryset(SELECT plugins)
          2. prefetch_related("monitor_object") 默认关联(供 DRF __all__ 序列化用)
          3. parent_prefetch 父对象子集(供 get_parent_monitor_object + view 用)
        若退化为 N+1(prefetch 失效 / 序列化器重新 filter),数字会随插件数线性增长。
        """
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        # 触发一次访问以稳定 connection(避免 cold start 的 SET TIME ZONE 等)
        api_client.get(f"{BASE}/api/monitor_plugin/")

        with CaptureQueriesContext(connection) as ctx:
            resp = api_client.get(f"{BASE}/api/monitor_plugin/")
        assert resp.status_code == 200
        # 4 个插件若 N+1 至少 6 次查询(1 主 + 1 默认 prefetch + 4 父 filter);
        # 3 次 prefetch 方案是上界,留 1-2 次余量给其他 hook(middleware / permission / savepoint)
        assert len(ctx.captured_queries) <= 5, (
            f"查询数 {len(ctx.captured_queries)} 偏多,疑似 Prefetch 失效 / N+1 回归。\n"
            f"SQL:\n{chr(10).join(q['sql'] for q in ctx.captured_queries)}"
        )
