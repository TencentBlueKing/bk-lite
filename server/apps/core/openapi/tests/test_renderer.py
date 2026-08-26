"""渲染器契约测试（unit，无 DB / 无 NATS）。

覆盖 spec.md「验证」节：四类坏条目跳过、未知字段前向兼容、
gateway_versions 过滤、fail-closed 各分支、Traefik 配置结构。
"""

import pytest

from apps.core.openapi import renderer

pytestmark = pytest.mark.unit

GOOD = {
    "schema_version": 1,
    "type": "http",
    "base_url": "http://itsm-svc:8000",
    "strip_prefix": True,
    "paths": ["/tickets/*"],
    "auth_mode": "trusted-header",
    "shared_secret_ref": "env:TEST_ITSM_SECRET",
    "required_roles": [],
    "rate_limit": {"average": 50, "burst": 100},
    "enabled": True,
}


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("OPENAPI_BASEURL_ALLOWLIST", "itsm-svc,.internal")
    monkeypatch.setenv("OPENAPI_AUTH_ADDRESS", "http://server:8000/openapi/v1/_auth")
    monkeypatch.setenv("TEST_ITSM_SECRET", "s3cret")
    monkeypatch.setenv("TEST_ITSM_TOKEN", "tok-abc")


def render_one(entry, name="itsm", internal=()):
    return renderer.render_traefik_config({name: entry}, internal)


def test_good_entry_full_structure(env):
    config, report = render_one(dict(GOOD))
    assert report["rendered"] == ["itsm"]
    http = config["http"]

    router = http["routers"]["openapi-v1-itsm"]
    assert router["rule"] == "PathPrefix(`/openapi/v1/itsm/tickets`)"
    assert router["service"] == "openapi-itsm"
    assert router["middlewares"][0] == "openapi-clear-headers"
    assert "openapi-itsm-ratelimit" in router["middlewares"]
    assert "openapi-auth" in router["middlewares"]
    assert router["middlewares"][-1] == "openapi-itsm-strip-v1"

    clear = http["middlewares"]["openapi-clear-headers"]["headers"]["customRequestHeaders"]
    assert set(clear) == {"X-BK-User", "X-BK-Team", "X-BK-Gateway-Auth"}
    assert all(value == "" for value in clear.values())

    auth = http["middlewares"]["openapi-auth"]["forwardAuth"]
    assert auth["address"].endswith("/_auth")
    assert auth["authResponseHeaders"] == ["X-BK-User", "X-BK-Team", "X-On-Behalf-Of"]

    inject = http["middlewares"]["openapi-itsm-inject"]["headers"]["customRequestHeaders"]
    # 注入共享密钥的同时必须清除调用方的平台凭据，避免上游拿到 API 令牌后冒充调用方
    assert inject == {"X-BK-Gateway-Auth": "s3cret", "Authorization": ""}

    assert http["middlewares"]["openapi-itsm-strip-v1"]["stripPrefix"]["prefixes"] == [
        "/openapi/v1/itsm"
    ]
    assert http["services"]["openapi-itsm"]["loadBalancer"]["servers"] == [
        {"url": "http://itsm-svc:8000"}
    ]


def test_service_token_mode_injects_authorization(env):
    entry = dict(GOOD, auth_mode="service-token", token_ref="env:TEST_ITSM_TOKEN")
    entry.pop("shared_secret_ref")
    config, report = render_one(entry)
    assert report["rendered"] == ["itsm"]
    inject = config["http"]["middlewares"]["openapi-itsm-inject"]["headers"][
        "customRequestHeaders"
    ]
    assert inject == {"Authorization": "Bearer tok-abc"}


def test_no_paths_renders_whole_prefix(env):
    entry = dict(GOOD)
    entry.pop("paths")
    config, _ = render_one(entry)
    assert (
        config["http"]["routers"]["openapi-v1-itsm"]["rule"]
        == "PathPrefix(`/openapi/v1/itsm`)"
    )


def test_unknown_fields_ignored(env):
    entry = dict(GOOD, future_field={"x": 1})
    _, report = render_one(entry)
    assert report["rendered"] == ["itsm"]


@pytest.mark.parametrize(
    "mutation, reason_part",
    [
        ({"schema_version": 2}, "schema_version"),
        ({"type": "grpc"}, "type"),
        ({"auth_mode": "magic"}, "auth_mode"),
        ({"base_url": "http://evil.example.com"}, "allowlist"),
        ({"base_url": "ftp://itsm-svc"}, "base_url"),
        ({"shared_secret_ref": "env:NOT_SET_VAR"}, "shared_secret_ref"),
        ({"paths": "not-a-list"}, "paths"),
        ({"rate_limit": {"average": "50"}}, "rate_limit"),
        ({"required_roles": "admin"}, "required_roles"),
        ({"gateway_versions": ["v9"]}, "gateway version"),
    ],
)
def test_bad_entries_skipped(env, mutation, reason_part):
    entry = dict(GOOD, **mutation)
    config, report = render_one(entry)
    assert report["rendered"] == []
    assert reason_part in report["skipped"]["itsm"]
    assert "routers" not in config["http"]


def test_disabled_entry_skipped_quietly(env):
    _, report = render_one(dict(GOOD, enabled=False))
    assert report["skipped"]["itsm"] == "disabled"


def test_non_dict_entry_skipped(env):
    _, report = render_one("garbage")
    assert "not an object" in report["skipped"]["itsm"]


def test_internal_name_conflict_skipped(env):
    _, report = render_one(dict(GOOD), name="cmdb", internal=("cmdb",))
    assert "internal" in report["skipped"]["cmdb"]


def test_reserved_name_rejected(env):
    _, report = render_one(dict(GOOD), name="_me")
    assert "invalid service name" in report["skipped"]["_me"]


@pytest.mark.parametrize(
    "host, allowed",
    [
        ("itsm-svc", True),           # 精确匹配
        ("a.itsm-svc", True),         # 点边界后缀
        ("evil-itsm-svc", False),     # 同尾但非点边界，必须拒绝
        ("xitsm-svc", False),
        ("svc.internal", True),       # allowlist 中的 .internal 后缀
        ("evilinternal", False),
    ],
)
def test_base_url_allowlist_requires_dot_boundary(env, host, allowed):
    entry = dict(GOOD, base_url=f"http://{host}:8000")
    _, report = render_one(entry)
    if allowed:
        assert report["rendered"] == ["itsm"], f"{host} 应被放行"
    else:
        assert "allowlist" in report["skipped"]["itsm"], f"{host} 应被拒绝"


def test_missing_allowlist_rejects_everything(env, monkeypatch):
    monkeypatch.delenv("OPENAPI_BASEURL_ALLOWLIST")
    _, report = render_one(dict(GOOD))
    assert "allowlist" in report["skipped"]["itsm"]


def test_missing_auth_address_renders_nothing(env, monkeypatch):
    monkeypatch.delenv("OPENAPI_AUTH_ADDRESS")
    config, report = render_one(dict(GOOD))
    assert "routers" not in config["http"]
    assert report["skipped"]["itsm"] == "auth address unconfigured"


def test_empty_sections_are_omitted_not_empty_maps(env):
    """Traefik 解码器拒绝空 map：出现 "routers": {} 会整份配置被拒
    （`routers cannot be a standalone element`），连合法的 middlewares 一起失效。
    未注册外部服务是常态，故空小节必须省略。回归自 .149 HA 真机验证。
    """
    config, report = renderer.render_traefik_config({}, ())
    assert report["rendered"] == []
    assert config == {"http": {}}
    for section in ("routers", "middlewares", "services"):
        assert section not in config["http"], f"{section} 为空时必须省略而非置为 {{}}"

    # 有条目被跳过时同样不得残留空 map
    skipped_config, _ = render_one(dict(GOOD, enabled=False))
    assert skipped_config == {"http": {}}


def test_gateway_versions_default_active(env):
    entry = dict(GOOD)
    entry.pop("paths")
    entry["gateway_versions"] = ["v1", "v9"]
    config, report = render_one(entry)
    assert report["rendered"] == ["itsm"]
    assert set(config["http"]["routers"]) == {"openapi-v1-itsm"}


# ---------- 读侧 TTL 回源（_me / _docs / _auth 数据新鲜度） ----------


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    """FakeClock + 干净快照；后台对账默认改为同步执行以保证测试确定性。

    需要验证真实异步行为的测试自行 setattr 回线程版 _refresh_in_background。
    """
    fake = FakeClock()
    monkeypatch.setattr(renderer, "time", fake)
    monkeypatch.setattr(
        renderer,
        "_snapshot",
        {
            "config": None,
            "services": [],
            "entries": {},
            "checked_at": 0.0,
            "fetch_started_at": 0.0,
        },
    )
    monkeypatch.setattr(renderer, "_internal_services", lambda: [])
    monkeypatch.setattr(renderer, "_refresh_in_background", renderer._background_refresh_run)
    return fake


def install_fetch(monkeypatch, result):
    """monkeypatch fetch_entries 为可计数、可换返回值的 fake。"""
    state = {"calls": 0, "result": result}

    def fake():
        state["calls"] += 1
        value = state["result"]
        return dict(value) if isinstance(value, dict) else value

    monkeypatch.setattr(renderer, "fetch_entries", fake)
    return state


def test_read_side_refreshes_stale_snapshot(env, clock, monkeypatch):
    """冷启动（无任何成功快照）首读同步回源并立即可见，无需等 provider 轮询。"""
    fetch = install_fetch(monkeypatch, {"itsm": dict(GOOD, doc_url="http://d/x")})
    assert renderer.get_external_services() == ["itsm"]
    assert renderer.get_external_catalog() == [{"name": "itsm", "doc_url": "http://d/x"}]
    assert renderer.get_external_entry("itsm") is not None
    assert fetch["calls"] == 1  # 三次读共享同一次回源


def test_reads_within_ttl_hit_snapshot(env, clock, monkeypatch):
    fetch = install_fetch(monkeypatch, {"itsm": dict(GOOD)})
    renderer.get_external_services()
    clock.advance(renderer.DEFAULT_REGISTRY_CACHE_TTL - 1)
    renderer.get_external_services()
    assert fetch["calls"] == 1
    clock.advance(2)
    renderer.get_external_services()
    assert fetch["calls"] == 2


def test_new_registration_visible_after_ttl(env, clock, monkeypatch):
    """覆盖 _auth miss 场景：新注册条目最迟 TTL + 一次对账后本进程可见。

    clock fixture 将后台对账同步化，故过期读在此直接命中新条目；真实
    异步下过期首读先返回旧快照（见 test_warm_expiry_serves_stale_without_waiting）。
    """
    fetch = install_fetch(monkeypatch, {})
    assert renderer.get_external_entry("itsm") is None
    fetch["result"] = {"itsm": dict(GOOD)}
    assert renderer.get_external_entry("itsm") is None  # TTL 内维持 miss，不重复回源
    assert fetch["calls"] == 1
    clock.advance(renderer.DEFAULT_REGISTRY_CACHE_TTL + 1)
    assert renderer.get_external_entry("itsm") is not None
    assert fetch["calls"] == 2


def test_kv_down_falls_back_without_hammering(env, clock, monkeypatch):
    """KV 故障期间读侧降级快照，且 TTL 窗口内不重复付 NATS 往返。"""
    fetch = install_fetch(monkeypatch, {"itsm": dict(GOOD)})
    renderer.get_external_services()
    fetch["result"] = None
    clock.advance(renderer.DEFAULT_REGISTRY_CACHE_TTL + 1)
    assert renderer.get_external_services() == ["itsm"]  # 降级到最近成功快照
    assert fetch["calls"] == 2
    renderer.get_external_services()
    renderer.get_external_entry("itsm")
    assert fetch["calls"] == 2  # 失败也占用 TTL 窗口，不放大故障


def test_provider_refresh_warms_read_cache(env, clock, monkeypatch):
    fetch = install_fetch(monkeypatch, {"itsm": dict(GOOD)})
    renderer.refresh_snapshot()
    renderer.get_external_services()
    assert fetch["calls"] == 1


def test_ttl_zero_fetches_every_read(env, clock, monkeypatch):
    """TTL=0（读时点新鲜度档位）：每次读同步回源，不得转后台线程。"""
    monkeypatch.setenv("OPENAPI_REGISTRY_CACHE_TTL", "0")
    fetch = install_fetch(monkeypatch, {"itsm": dict(GOOD)})

    def must_not_spawn():
        raise AssertionError("TTL=0 必须走同步回源，不得转后台")

    monkeypatch.setattr(renderer, "_refresh_in_background", must_not_spawn)
    renderer.get_external_services()
    renderer.get_external_services()
    assert fetch["calls"] == 2


def test_warm_expiry_serves_stale_without_waiting(env, clock, monkeypatch):
    """温快照过期读绝不阻塞在在途对账上（stale-while-revalidate 真异步验证）。

    后台 fetch 被 Event 挂起时，读立即返回现有快照；放行后对账结果生效。
    """
    import threading
    import time as real_time

    monkeypatch.setattr(
        renderer,
        "_refresh_in_background",
        lambda: threading.Thread(target=renderer._background_refresh_run, daemon=True).start(),
    )
    release = threading.Event()
    state = {"calls": 0}

    def fake_fetch():
        state["calls"] += 1
        if state["calls"] == 1:
            return {"itsm": dict(GOOD)}
        release.wait(5)  # 后台对账挂起，模拟 NATS 慢/半死
        return {}

    monkeypatch.setattr(renderer, "fetch_entries", fake_fetch)

    assert renderer.get_external_services() == ["itsm"]  # 冷启动同步预热
    clock.advance(renderer.DEFAULT_REGISTRY_CACHE_TTL + 1)
    # 在途对账被挂起期间，读立即以现有快照响应（若同步等待，这两行会卡 5 秒）
    assert renderer.get_external_services() == ["itsm"]
    assert renderer.get_external_entry("itsm") is not None
    assert state["calls"] == 2  # 且只触发了一次后台对账

    release.set()
    deadline = real_time.monotonic() + 5
    while renderer.get_external_services() == ["itsm"]:
        assert real_time.monotonic() < deadline, "后台对账结果未在期限内生效"
        real_time.sleep(0.01)
    assert renderer.get_external_services() == []


def test_stale_fetch_does_not_overwrite_newer_snapshot(env, clock, monkeypatch):
    """写回围栏：发起早、完成晚的旧回源不得覆盖更新的数据（已删条目不复活）。"""
    import threading

    old_inflight = threading.Event()
    old_release = threading.Event()
    state = {"calls": 0}

    def fake_fetch():
        state["calls"] += 1
        if state["calls"] == 1:
            old_inflight.set()
            old_release.wait(5)
            return {"itsm": dict(GOOD)}  # 旧数据：itsm 尚存
        return {}  # 新数据：itsm 已从 KV 删除

    monkeypatch.setattr(renderer, "fetch_entries", fake_fetch)

    old_thread = threading.Thread(target=renderer.refresh_snapshot)
    old_thread.start()  # 旧回源先发起（started=t0），随即挂起
    assert old_inflight.wait(5)
    clock.advance(1)
    renderer.refresh_snapshot()  # 新回源后发起（started=t0+1）、先完成
    assert renderer.get_external_services() == []

    old_release.set()
    old_thread.join(5)
    assert not old_thread.is_alive()
    assert renderer.get_external_services() == []  # 乱序旧结果被围栏丢弃


def test_invalid_ttl_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("OPENAPI_REGISTRY_CACHE_TTL", "abc")
    assert renderer._cache_ttl() == renderer.DEFAULT_REGISTRY_CACHE_TTL
    monkeypatch.setenv("OPENAPI_REGISTRY_CACHE_TTL", "-5")
    assert renderer._cache_ttl() == 0.0
    monkeypatch.setenv("OPENAPI_REGISTRY_CACHE_TTL", "30")
    assert renderer._cache_ttl() == 30.0
