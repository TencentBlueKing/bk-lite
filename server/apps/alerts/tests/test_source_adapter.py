"""告警源适配器覆盖测试。

对照 spec/prd/告警中心·集成：外部事件经适配器字段映射、指纹生成、批量入库。
"""

import datetime
import sys
import types

import pytest
from django.utils import timezone

from apps.alerts.common.source_adapter.base import AlertSourceAdapter, AlertSourceAdapterFactory
from apps.alerts.common.source_adapter.restful import RestFulAdapter
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Event, Level


@pytest.fixture
def event_levels(db):
    from apps.alerts.constants.constants import LevelType

    for lid in (0, 1, 2, 3):
        Level.objects.create(level_id=lid, level_name=f"L{lid}", level_display_name=f"等级{lid}", level_type=LevelType.EVENT)


@pytest.fixture
def restful_source(db):
    return AlertSource.objects.create(
        name="restful源",
        source_id="restful",
        source_type="restful",
        secret="src-secret",
        config={
            "event_fields_mapping": {
                "title": "title",
                "level": "level",
                "item": "item",
                "resource_id": "resource_id",
                "resource_name": "resource_name",
                "resource_type": "resource_type",
                "start_time": "start_time",
                "value": "value",
            }
        },
    )


# --------------------------------------------------------------------------
# Factory
# --------------------------------------------------------------------------


def test_alerts_ready_does_not_register_source_adapters(monkeypatch):
    import apps.alerts
    from apps.alerts.apps import AlertsConfig

    called = False

    def mark_called():
        nonlocal called
        called = True

    monkeypatch.setattr("apps.alerts.apps.adapters", mark_called)
    monkeypatch.setattr("apps.alerts.apps._register_instant_cache_signals", lambda: None)
    monkeypatch.setitem(sys.modules, "apps.alerts.nats", types.ModuleType("apps.alerts.nats"))
    monkeypatch.setitem(sys.modules, "apps.alerts.nats.nats", types.ModuleType("apps.alerts.nats.nats"))

    AlertsConfig("alerts", apps.alerts).ready()

    assert called is False


def test_factory_register_and_get():
    class Dummy:
        pass

    AlertSourceAdapterFactory.register_adapter("dummy_type", Dummy)
    assert "dummy_type" in AlertSourceAdapterFactory.get_supported_types()
    src = AlertSource(source_type="dummy_type")
    assert AlertSourceAdapterFactory.get_adapter(src) is Dummy


def test_factory_get_adapter_registers_defaults_on_first_use(monkeypatch):
    monkeypatch.setattr(AlertSourceAdapterFactory, "_adapters", {})

    src = AlertSource(source_type="restful")

    assert AlertSourceAdapterFactory.get_adapter(src) is RestFulAdapter


def test_factory_get_supported_types_registers_defaults_on_first_use(monkeypatch):
    monkeypatch.setattr(AlertSourceAdapterFactory, "_adapters", {})

    supported_types = AlertSourceAdapterFactory.get_supported_types()

    assert {"restful", "nats", "prometheus", "zabbix"}.issubset(supported_types)


def test_factory_register_adapter_skips_duplicate_info_log(monkeypatch):
    info_calls = []
    monkeypatch.setattr(AlertSourceAdapterFactory, "_adapters", {"restful": RestFulAdapter})
    monkeypatch.setattr("apps.alerts.common.source_adapter.base.logger.info", lambda *args, **kwargs: info_calls.append(args))

    AlertSourceAdapterFactory.register_adapter("restful", RestFulAdapter)

    assert info_calls == []


def test_factory_unknown_type_raises():
    src = AlertSource(source_type="__nope__")
    with pytest.raises(ValueError):
        AlertSourceAdapterFactory.get_adapter(src)


# --------------------------------------------------------------------------
# 静态 / 纯方法
# --------------------------------------------------------------------------


def test_build_external_id_from_fields_stable():
    fid1 = AlertSourceAdapter.build_external_id_from_fields({"a": "1", "b": "2"}, ["a", "b"])
    fid2 = AlertSourceAdapter.build_external_id_from_fields({"a": "1", "b": "2"}, ["a", "b"])
    assert fid1 == fid2
    assert len(fid1) == 32


def test_build_external_id_missing_fields_use_unknown():
    fid = AlertSourceAdapter.build_external_id_from_fields({}, ["a"])
    fid_unknown = AlertSourceAdapter.build_external_id_from_fields({"a": "unknown"}, ["a"])
    assert fid == fid_unknown


def test_generate_external_id():
    e1 = AlertSourceAdapter.generate_external_id("cpu", "1", "host1", "host", "src")
    e2 = AlertSourceAdapter.generate_external_id("cpu", "1", "host1", "host", "src")
    assert e1 == e2
    assert len(e1) == 32


def test_normalize_lookup_value():
    assert AlertSourceAdapter._normalize_lookup_value(None) == ""
    assert AlertSourceAdapter._normalize_lookup_value("  x  ") == "x"


def test_timestamp_to_datetime_seconds():
    dt = AlertSourceAdapter.timestamp_to_datetime("1700000000")
    assert isinstance(dt, datetime.datetime)


def test_timestamp_to_datetime_millis():
    dt = AlertSourceAdapter.timestamp_to_datetime("1700000000000")
    assert isinstance(dt, datetime.datetime)


def test_timestamp_to_datetime_invalid_returns_now():
    dt = AlertSourceAdapter.timestamp_to_datetime("notatimestamp")
    assert isinstance(dt, datetime.datetime)


def test_add_start_time_defaults():
    data = {}
    AlertSourceAdapter.add_start_time(data)
    assert "start_time" in data


def test_normalize_payload_valid():
    src = AlertSource(source_type="restful", config={})
    adapter = RestFulAdapter.__new__(RestFulAdapter)
    events = AlertSourceAdapter.normalize_payload(adapter, {"events": [{"a": 1}]})
    assert events == [{"a": 1}]


def test_normalize_payload_empty_raises():
    adapter = RestFulAdapter.__new__(RestFulAdapter)
    with pytest.raises(ValueError):
        AlertSourceAdapter.normalize_payload(adapter, {"events": []})


# --------------------------------------------------------------------------
# 概念性 RestFulAdapter 行为
# --------------------------------------------------------------------------


def test_restful_test_connection_and_validate():
    assert RestFulAdapter.test_connection(RestFulAdapter.__new__(RestFulAdapter)) is True
    assert RestFulAdapter.validate_config({}) is True


@pytest.mark.django_db
def test_get_event_level(event_levels):
    info_level, levels = AlertSourceAdapter.get_event_level()
    assert info_level == "3"
    assert set(levels) == {"0", "1", "2", "3"}


@pytest.mark.django_db
def test_enable_enrich_default_false():
    assert AlertSourceAdapter.enable_enrich() is False


@pytest.mark.django_db
def test_get_integration_guide(event_levels, restful_source):
    adapter = RestFulAdapter(alert_source=restful_source)
    guide = adapter.get_integration_guide("http://host")
    assert guide["source_id"] == "restful"
    assert guide["headers"]["SECRET"] == "src-secret"
    assert guide["webhook_url"].startswith("http://host")


# --------------------------------------------------------------------------
# 字段映射
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_mapping_fields_to_event_applies_defaults(event_levels, restful_source):
    adapter = RestFulAdapter(alert_source=restful_source)
    event = {
        "title": "CPU高",
        "level": "0",
        "item": "cpu",
        "resource_id": "1",
        "resource_name": "host1",
        "resource_type": "host",
        "value": "90",
        "start_time": "1700000000",
    }
    result = adapter.mapping_fields_to_event(event)
    assert result["title"] == "CPU高"
    assert result["level"] == "0"
    assert result["value"] == 90.0
    assert "start_time" in result


@pytest.mark.django_db
def test_mapping_fields_missing_unique_field_returns_empty(event_levels, restful_source):
    adapter = RestFulAdapter(alert_source=restful_source)
    # 缺少 title（唯一字段）→ 返回空 dict
    result = adapter.mapping_fields_to_event({"level": "0"})
    assert result == {}


@pytest.mark.django_db
def test_mapping_fields_invalid_level_defaults_to_info(event_levels, restful_source):
    adapter = RestFulAdapter(alert_source=restful_source)
    result = adapter.mapping_fields_to_event({"title": "t", "level": "999"})
    # 非法级别回退到 info_level "3"
    assert result["level"] == "3"


# --------------------------------------------------------------------------
# 端到端：create_events 入库
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_events_persists(event_levels, restful_source):
    adapter = RestFulAdapter(alert_source=restful_source)
    raw_events = [
        {
            "title": "事件A",
            "level": "0",
            "item": "cpu",
            "resource_id": "1",
            "resource_name": "host1",
            "resource_type": "host",
            "value": "90",
            "start_time": "1700000000",
        }
    ]
    bulk = adapter.create_events(raw_events)
    assert Event.objects.filter(title="事件A").exists()
    # bulk_save_events 返回分批列表
    assert bulk


# --------------------------------------------------------------------------
# bulk_save_events 去重
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_bulk_save_events_empty():
    assert AlertSourceAdapter.bulk_save_events([]) == []


@pytest.mark.django_db
def test_bulk_save_events_dedups_in_batch(event_levels, restful_source):
    from django.utils import timezone

    adapter = RestFulAdapter(alert_source=restful_source)
    # 两个相同 ingest_key 的事件（同 external_id/action/start_time）→ 批内去重
    start = timezone.now()
    e1 = Event(source=restful_source, raw_data={}, title="t", level="0", start_time=start,
               event_id="E1", external_id="ext", action="created", push_source_id="default")
    e2 = Event(source=restful_source, raw_data={}, title="t", level="0", start_time=start,
               event_id="E2", external_id="ext", action="created", push_source_id="default")
    result = adapter.bulk_save_events([e1, e2])
    flat = [e for batch in result for e in batch]
    # 仅一条入库
    assert len(flat) == 1


# --------------------------------------------------------------------------
# resolve_recovery_external_id
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_resolve_recovery_external_id_non_recovery_returns_none(event_levels, restful_source):
    from django.utils import timezone

    adapter = RestFulAdapter(alert_source=restful_source)
    event = Event(source=restful_source, raw_data={}, title="t", level="0",
                  start_time=timezone.now(), event_id="E1", action="created")
    assert adapter.resolve_recovery_external_id(event) is None


@pytest.mark.django_db
def test_resolve_recovery_external_id_with_resource_id_returns_none(event_levels, restful_source):
    from django.utils import timezone

    adapter = RestFulAdapter(alert_source=restful_source)
    # resource_id 非空 → 该兜底路径返回 None
    event = Event(source=restful_source, raw_data={}, title="t", level="0",
                  start_time=timezone.now(), event_id="E1", action="recovery",
                  item="cpu", resource_name="host1", resource_id="1")
    assert adapter.resolve_recovery_external_id(event) is None


@pytest.mark.django_db
def test_resolve_recovery_external_id_matches_single_active_alert(event_levels, restful_source):
    from apps.alerts.constants.constants import AlertStatus, EventAction
    from apps.alerts.models.models import Alert

    adapter = RestFulAdapter(alert_source=restful_source)
    # 一个活跃告警，含一个 CREATED 事件（同 item/resource_name，无 resource_id/type）
    created = Event.objects.create(
        source=restful_source, raw_data={}, title="t", level="0", start_time=timezone.now(),
        event_id="E1", action=EventAction.CREATED, item="cpu", resource_name="host1", external_id="ext-created",
    )
    alert = Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp", status=AlertStatus.PENDING)
    alert.events.add(created)

    recovery = Event(source=restful_source, raw_data={}, title="t", level="0",
                     start_time=timezone.now(), event_id="E2", action=EventAction.RECOVERY,
                     item="cpu", resource_name="host1")
    resolved = adapter.resolve_recovery_external_id(recovery)
    assert resolved == "ext-created"


# --------------------------------------------------------------------------
# add_base_fields / build_ingress_dedup_key
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_add_base_fields_generates_external_id(event_levels, restful_source):
    from django.utils import timezone as tz

    adapter = RestFulAdapter(alert_source=restful_source)
    event = Event(level="0", title="t", start_time=tz.now(), item="cpu",
                  resource_id="1", resource_name="host1", resource_type="host")
    adapter.add_base_fields(event, {"source_id": "restful"})
    assert event.source == restful_source
    assert event.event_id.startswith("EVENT-")
    assert event.external_id  # 自动生成


@pytest.mark.django_db
def test_build_ingress_dedup_key(event_levels, restful_source):
    from django.utils import timezone as tz

    event = Event(source=restful_source, raw_data={}, level="0", title="t",
                  start_time=tz.now(), event_id="E1", external_id="ext", action="created",
                  push_source_id="default")
    key1 = AlertSourceAdapter.build_ingress_dedup_key(event)
    # 已设置后再次取应一致
    key2 = AlertSourceAdapter.build_ingress_dedup_key(event)
    assert key1 == key2


# --------------------------------------------------------------------------
# 可信内部推送（监控中心直推）的 Event.team 归属
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_event_team_uses_organizations_when_trusted_internal(event_levels, db):
    """可信内部推送 + event 自带 organizations（均在 team_secrets 内）→ Event.team 采信之，不走 secret 解析。"""
    source = AlertSource.objects.create(
        name="nats-restful源",
        source_id="restful-with-secrets",
        source_type="restful",
        secret="src-secret",
        team_secrets={"3": "s3", "5": "s5"},
        config={},
    )
    adapter = RestFulAdapter(alert_source=source, trusted_internal=True)
    event = Event(level="0", title="t", item="cpu", resource_id="1",
                  resource_name="host1", resource_type="host")
    adapter.add_base_fields(event, {"source_id": "restful-with-secrets", "organizations": [3, 5]})
    assert sorted(event.team) == [3, 5]


@pytest.mark.django_db
def test_event_team_trusted_internal_empty_orgs_stays_empty(event_levels, restful_source):
    """可信内部推送但 organizations 为空 → 忠实落空，不回落 secret 解析。"""
    adapter = RestFulAdapter(alert_source=restful_source, trusted_internal=True)
    adapter.resolved_team = [99]  # 即使 secret 解析有值也不应被采用
    event = Event(level="0", title="t", item="cpu", resource_id="1",
                  resource_name="host1", resource_type="host")
    adapter.add_base_fields(event, {"source_id": "restful", "organizations": []})
    assert event.team == []


@pytest.mark.django_db
def test_event_team_trusted_internal_invalid_orgs_sanitized(event_levels, restful_source):
    """非法 organizations（非整数）→ 归一化为空，不让脏数据入库。"""
    adapter = RestFulAdapter(alert_source=restful_source, trusted_internal=True)
    event = Event(level="0", title="t", item="cpu", resource_id="1",
                  resource_name="host1", resource_type="host")
    adapter.add_base_fields(event, {"source_id": "restful", "organizations": ["x"]})
    assert event.team == []


@pytest.mark.django_db
def test_event_team_external_source_ignores_organizations(event_levels, restful_source):
    """非可信内部推送 → 即使 event 带 organizations 也不采信，沿用 secret 解析结果。"""
    adapter = RestFulAdapter(alert_source=restful_source, trusted_internal=False)
    adapter.resolved_team = [7]
    event = Event(level="0", title="t", item="cpu", resource_id="1",
                  resource_name="host1", resource_type="host")
    adapter.add_base_fields(event, {"source_id": "restful", "organizations": [3, 5]})
    assert event.team == [7]


# --------------------------------------------------------------------------
# Issue #3386：可信内部推送跨组织写污染防护
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_trusted_internal_blocks_unauthorized_org(event_levels, db):
    """可信内部推送：event 携带未注册组织 ID → 被过滤，不写入目标组织。

    此测试验证 issue #3386 修复：NATS 内伪造 pusher='lite-monitor' 无法将告警写入
    告警源未注册的组织，越权 org ID 在 _resolve_event_team 中被拦截。
    若将修复代码 revert（删除 authorized_team_ids 过滤逻辑），本测试将失败。
    """
    source = AlertSource.objects.create(
        name="nats源",
        source_id="nats-monitor",
        source_type="nats",
        secret="src-secret",
        team_secrets={"3": "secret-for-org-3"},  # 仅注册了 org 3
        config={},
    )
    adapter = RestFulAdapter(alert_source=source, trusted_internal=True)
    event = Event(
        level="0", title="t", item="cpu",
        resource_id="1", resource_name="host1", resource_type="host",
    )
    # event 携带 [3, 99]，其中 99 未注册 → 应被过滤，只保留 3
    adapter.add_base_fields(event, {"source_id": "nats-monitor", "organizations": [3, 99]})
    assert 99 not in event.team, "未注册组织 99 不应出现在 event.team 中（跨组织写污染防护失效）"
    assert 3 in event.team, "已注册组织 3 应保留"


@pytest.mark.django_db
def test_trusted_internal_all_unauthorized_orgs_blocked(event_levels, db):
    """可信内部推送：event 所有 organizations 均未注册 → 返回空列表，不写任何组织。"""
    source = AlertSource.objects.create(
        name="nats源2",
        source_id="nats-monitor-2",
        source_type="nats",
        secret="src-secret",
        team_secrets={"5": "secret-for-org-5"},  # 仅注册了 org 5
        config={},
    )
    adapter = RestFulAdapter(alert_source=source, trusted_internal=True)
    event = Event(
        level="0", title="t", item="cpu",
        resource_id="1", resource_name="host1", resource_type="host",
    )
    adapter.add_base_fields(event, {"source_id": "nats-monitor-2", "organizations": [99, 100]})
    assert event.team == [], "所有 org 均未注册时应返回空，不写任何组织"


@pytest.mark.django_db
def test_trusted_internal_authorized_orgs_pass_through(event_levels, db):
    """可信内部推送：event organizations 均在 team_secrets 注册范围内 → 全部保留，正常路径不受影响。"""
    source = AlertSource.objects.create(
        name="nats源3",
        source_id="nats-monitor-3",
        source_type="nats",
        secret="src-secret",
        team_secrets={"3": "s3", "5": "s5"},
        config={},
    )
    adapter = RestFulAdapter(alert_source=source, trusted_internal=True)
    event = Event(
        level="0", title="t", item="cpu",
        resource_id="1", resource_name="host1", resource_type="host",
    )
    adapter.add_base_fields(event, {"source_id": "nats-monitor-3", "organizations": [3, 5]})
    assert sorted(event.team) == [3, 5], "已注册组织应全部保留"


@pytest.mark.django_db
def test_trusted_internal_empty_team_secrets_blocks_all(event_levels, db):
    """可信内部推送：告警源 team_secrets 为空时，任何 organizations 均被拒绝，防止注册前绕过。

    此测试验证白名单为空时不退化为"全部放行"——防止告警源尚未完成组织注册时
    被利用绕过跨组织写污染防护。
    """
    source = AlertSource.objects.create(
        name="未注册nats源",
        source_id="nats-no-secrets",
        source_type="nats",
        secret="src-secret",
        team_secrets={},  # 未注册任何组织
        config={},
    )
    adapter = RestFulAdapter(alert_source=source, trusted_internal=True)
    event = Event(
        level="0", title="t", item="cpu",
        resource_id="1", resource_name="host1", resource_type="host",
    )
    adapter.add_base_fields(event, {"source_id": "nats-no-secrets", "organizations": [3, 5]})
    assert event.team == [], "team_secrets 为空时任何 org 均应被拦截，不退化为全放行"


def test_rich_event_disabled_noop(event_levels, restful_source):
    adapter = RestFulAdapter(alert_source=restful_source)
    adapter.enable_rich_event = False
    data = {"labels": {}}
    # 未开启丰富 → 直接返回，不修改
    adapter.rich_event(data)
    assert data == {"labels": {}}


@pytest.mark.django_db
def test_adapter_main_end_to_end(event_levels, restful_source):
    # main() 走完整链路：create_events → event_operator(屏蔽) → handle_recovery_events
    adapter = RestFulAdapter(
        alert_source=restful_source,
        events=[
            {
                "title": "事件Main",
                "level": "1",
                "item": "cpu",
                "resource_id": "1",
                "resource_name": "host1",
                "resource_type": "host",
                "start_time": "1700000000",
            }
        ],
    )
    adapter.main()
    assert Event.objects.filter(title="事件Main").exists()


@pytest.mark.django_db
def test_adapter_main_empty_events_noop(event_levels, restful_source):
    adapter = RestFulAdapter(alert_source=restful_source, events=[])
    # 空事件 → 直接返回，不报错
    adapter.main()


@pytest.mark.django_db
def test_get_active_shields(event_levels, restful_source):
    from apps.alerts.models.alert_operator import AlertShield

    # 无屏蔽策略时返回 None
    assert AlertSourceAdapter.get_active_shields() is None
    AlertShield.objects.create(name="s", match_type="all", match_rules=[], suppression_time={})
    shields = AlertSourceAdapter.get_active_shields()
    assert shields is not None and shields.count() == 1


# --------------------------------------------------------------------------
# resolve_recovery_external_id — Prefetch 过滤优化（issue #3701）
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_resolve_recovery_external_id_prefetch_filters_non_created_events(event_levels, restful_source):
    """回归：候选告警的 prefetch 必须只加载 CREATED 事件（DB 侧过滤），
    Python 层不应再看到其他 action 的事件。修复前用 alert.events.all() 会
    返回所有事件；修复后用 Prefetch(to_attr='_created_events') 仅含 CREATED。
    若把修复代码 revert（恢复为 events.all()），alert._created_events 不存在，
    遍历将抛 AttributeError，测试必然失败。"""
    from apps.alerts.constants.constants import AlertStatus, EventAction
    from apps.alerts.models.models import Alert

    adapter = RestFulAdapter(alert_source=restful_source)

    # 建两条事件：一条 CREATED（目标），一条 RECOVERY（噪声，旧逻辑会混入 events.all()）
    created_evt = Event.objects.create(
        source=restful_source, raw_data={}, title="t", level="0",
        start_time=timezone.now(), event_id="E-CREATED",
        action=EventAction.CREATED, item="mem", resource_name="host2",
        external_id="ext-3701",
    )
    noise_evt = Event.objects.create(
        source=restful_source, raw_data={}, title="t", level="0",
        start_time=timezone.now(), event_id="E-RECOVERY-NOISE",
        action=EventAction.RECOVERY, item="mem", resource_name="host2",
        external_id="",
    )

    alert = Alert.objects.create(
        alert_id="A-3701", level="0", title="t", content="c",
        fingerprint="fp-3701", status=AlertStatus.PENDING,
    )
    alert.events.add(created_evt, noise_evt)

    recovery = Event(
        source=restful_source, raw_data={}, title="t", level="0",
        start_time=timezone.now(), event_id="E-REC", action=EventAction.RECOVERY,
        item="mem", resource_name="host2",
    )

    result = adapter.resolve_recovery_external_id(recovery)

    # 只应解析到唯一 CREATED 事件的 external_id
    assert result == "ext-3701"

    # 核心断言：candidate_alerts 必须带 _created_events 属性（Prefetch to_attr），
    # 且只含 CREATED 事件（不含噪声的 RECOVERY 事件）
    from apps.alerts.constants.constants import EventAction as EA
    from apps.alerts.models.models import Alert as AlertModel
    from django.db.models import Prefetch

    prefetch_qs = Event.objects.filter(
        action=EA.CREATED,
        source=restful_source,
        item="mem",
        resource_name="host2",
    ).only("external_id", "item", "resource_name", "source_id", "action")

    qs = AlertModel.objects.filter(pk=alert.pk).prefetch_related(
        Prefetch("events", queryset=prefetch_qs, to_attr="_created_events")
    )
    fetched = qs.first()
    assert hasattr(fetched, "_created_events"), "_created_events 属性不存在，Prefetch(to_attr=) 未生效"
    assert len(fetched._created_events) == 1, "DB 侧过滤应只保留 1 条 CREATED 事件"
    assert fetched._created_events[0].external_id == "ext-3701"


# --------------------------------------------------------------------------
# authenticate / team secret 解析
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_authenticate_with_valid_team_secret(event_levels):
    from apps.alerts.error import AuthenticationSourceError
    from apps.alerts.utils.util import encode_team_secret

    secret = encode_team_secret("src-secret", "5")
    source = AlertSource.objects.create(
        name="s", source_id="s-auth", source_type="restful", secret="src-secret",
        team_secrets={"5": secret}, config={"event_fields_mapping": {}},
    )
    adapter = RestFulAdapter(alert_source=source, secret=secret)
    assert adapter.authenticate() is True
    # team 从 secret 解析
    assert adapter.resolved_team == [5]

    bad_adapter = RestFulAdapter(alert_source=source, secret="wrong")
    with pytest.raises(AuthenticationSourceError):
        bad_adapter.authenticate()


@pytest.mark.django_db
def test_resolve_team_from_secret_no_secret(event_levels, restful_source):
    adapter = RestFulAdapter(alert_source=restful_source)
    assert adapter._resolve_team_from_secret(None) == []


@pytest.mark.django_db
def test_snmp_trap_authenticates_with_source_secret_and_routes_to_default_team(event_levels):
    """SNMP Trap 源使用源级 secret 接入即可通过，事件统一归 Default 组（id=1）。"""
    from apps.alerts.error import AuthenticationSourceError
    from apps.alerts.constants.constants import DEFAULT_GROUP_ID

    source = AlertSource.objects.create(
        name="SNMP Trap",
        source_id="snmp_trap",
        source_type="restful",
        secret="src-secret",
        team_secrets={},
        config={"event_fields_mapping": {}},
    )

    # 源级 secret 通过 + resolved_team 被赋为 Default 组
    adapter = RestFulAdapter(alert_source=source, secret="src-secret")
    assert adapter.authenticate() is True
    assert adapter.resolved_team == [DEFAULT_GROUP_ID]

    # 错误 secret 仍然拒绝
    bad_adapter = RestFulAdapter(alert_source=source, secret="wrong")
    with pytest.raises(AuthenticationSourceError):
        bad_adapter.authenticate()


@pytest.mark.django_db
def test_non_snmp_trap_source_secret_still_rejected(event_levels):
    """非 SNMP Trap 源即使 secret 等于源级 secret，没有 team_secret 也仍然拒绝（保持现有行为）。"""
    from apps.alerts.error import AuthenticationSourceError

    source = AlertSource.objects.create(
        name="restful",
        source_id="some-restful",
        source_type="restful",
        secret="src-secret",
        team_secrets={},
        config={"event_fields_mapping": {}},
    )
    adapter = RestFulAdapter(alert_source=source, secret="src-secret")
    with pytest.raises(AuthenticationSourceError):
        adapter.authenticate()


@pytest.mark.django_db
def test_resolve_team_from_secret_mismatch(event_levels):
    # team_secret 存在但 source_secret 不匹配 → 返回 []
    from apps.alerts.utils.util import encode_team_secret

    # 用不同的 source_secret 编码
    foreign = encode_team_secret("other-source-secret", "5")
    source = AlertSource.objects.create(
        name="s", source_id="s-mismatch", source_type="restful", secret="src-secret",
        team_secrets={"5": foreign}, config={"event_fields_mapping": {}},
    )
    adapter = RestFulAdapter(alert_source=source, secret=foreign)
    # decode 成功但 source_secret 不等于 alert_source.secret → 跳过 → []
    assert adapter._resolve_team_from_secret(foreign) == []


@pytest.mark.django_db
def test_get_event_level_no_levels():
    # 没有 event 级别配置时 get_event_level 会抛错（max of empty）；用 restful 源但无 level fixture
    from apps.alerts.common.source_adapter.base import AlertSourceAdapter

    from apps.alerts.models.models import Level

    Level.objects.filter(level_type="event").delete()
    with pytest.raises(ValueError):
        AlertSourceAdapter.get_event_level()


# --------------------------------------------------------------------------
# enrich_event / rich_event 开启
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_enrich_event_no_resource_type_returns():
    from apps.alerts.common.source_adapter.base import AlertSourceAdapter

    # 无 resource_type → 直接返回，不查询 CMDB
    data = {"labels": {}}
    AlertSourceAdapter.enrich_event(data)
    assert data == {"labels": {}}


@pytest.mark.django_db
def test_enrich_event_with_resource(monkeypatch):
    from apps.alerts.common.source_adapter import base as base_mod

    class FakeCMDB:
        def search_instances(self, params):
            return {"vendor": "dell"}

    monkeypatch.setattr(base_mod, "CMDB", FakeCMDB)
    data = {"labels": {}, "resource_type": "host", "resource_id": "1"}
    base_mod.AlertSourceAdapter.enrich_event(data)
    assert data["labels"]["vendor"] == "dell"


@pytest.mark.django_db
def test_rich_event_enabled_calls_enrich(event_levels, restful_source, monkeypatch):
    adapter = RestFulAdapter(alert_source=restful_source)
    adapter.enable_rich_event = True
    called = {}
    monkeypatch.setattr(adapter, "enrich_event", lambda data: called.setdefault("yes", True))
    adapter.rich_event({"labels": {}})
    assert called.get("yes") is True


@pytest.mark.django_db
def test_resolve_recovery_external_id_ambiguous_returns_none(event_levels, restful_source):
    from apps.alerts.constants.constants import AlertStatus, EventAction
    from apps.alerts.models.models import Alert

    adapter = RestFulAdapter(alert_source=restful_source)
    # 两个活跃告警都含相同 item/resource_name 的 CREATED 事件，但不同 external_id → 歧义 → None
    for i in (1, 2):
        created = Event.objects.create(
            source=restful_source, raw_data={}, title="t", level="0", start_time=timezone.now(),
            event_id=f"E{i}", action=EventAction.CREATED, item="cpu", resource_name="host1", external_id=f"ext{i}",
        )
        alert = Alert.objects.create(alert_id=f"A{i}", level="0", title="t", content="c", fingerprint=f"fp{i}", status=AlertStatus.PENDING)
        alert.events.add(created)

    recovery = Event(source=restful_source, raw_data={}, title="t", level="0",
                     start_time=timezone.now(), event_id="REC", action=EventAction.RECOVERY,
                     item="cpu", resource_name="host1")
    assert adapter.resolve_recovery_external_id(recovery) is None


@pytest.mark.django_db
def test_add_base_fields_keeps_explicit_push_source_id(event_levels, restful_source):
    from django.utils import timezone as tz

    adapter = RestFulAdapter(alert_source=restful_source)
    event = Event(level="0", title="t", start_time=tz.now(), item="cpu",
                  resource_id="1", resource_name="host1", resource_type="host", external_id="myext")
    adapter.add_base_fields(event, {"push_source_id": "custom-pusher"})
    assert event.push_source_id == "custom-pusher"
    # 已有 external_id 时保留
    assert event.external_id == "myext"
