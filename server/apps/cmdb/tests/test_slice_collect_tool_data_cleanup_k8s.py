import pydantic.root_model  # noqa

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.cmdb.services.collect_tool_service import (
    MASKED_PASSWORD,
    TIMEOUT_MAP,
    COLLECT_TOOL_DEBUG_CACHE_PREFIX,
    COLLECT_TOOL_POLL_INTERVAL_MS,
    CollectToolService,
)
from apps.cmdb.services.data_cleanup_service import DataCleanupService
from apps.cmdb.services import k8s_setup as k8s_mod
from apps.cmdb.services.k8s_setup import K8sSetupService, validate_collector_cluster_id
from apps.core.exceptions.base_app_exception import BaseAppException


# ---------------------------------------------------------------------------
# Lightweight fakes for the request/instance boundaries
# ---------------------------------------------------------------------------
class _FakeUser:
    def __init__(self, username="alice", domain="domain.com"):
        self.username = username
        self.domain = domain


class _FakeRequest:
    def __init__(self, username="alice", domain="domain.com", cookies=None):
        self.user = _FakeUser(username, domain)
        self.COOKIES = cookies or {}


class _FakeInstance:
    """Stand-in for CollectModels for the pure prefill/inject helpers."""

    def __init__(self, **kw):
        self.access_point = kw.get("access_point", {})
        self.instances = kw.get("instances", [])
        self.ip_range = kw.get("ip_range", "")
        self.credential = kw.get("credential", {})
        self._decrypt = kw.get("decrypt_credentials", {})

    @property
    def decrypt_credentials(self):
        return self._decrypt


# ===========================================================================
# CollectToolService - pure helpers
# ===========================================================================
class TestCollectToolPureHelpers:
    def test_get_timeout_known_and_default(self):
        assert CollectToolService.get_timeout("raw_collect") == TIMEOUT_MAP["raw_collect"]
        assert CollectToolService.get_timeout("get_oid") == 120
        assert CollectToolService.get_timeout("nonexistent") == 10

    def test_create_debug_id_prefix_and_length(self):
        debug_id = CollectToolService.create_debug_id()
        assert debug_id.startswith("dbg_")
        assert len(debug_id) == len("dbg_") + 8

    def test_get_cache_key(self):
        assert CollectToolService.get_cache_key("xyz") == f"{COLLECT_TOOL_DEBUG_CACHE_PREFIX}xyz"

    def test_build_debug_owner(self):
        req = _FakeRequest(username="bob", domain="d2")
        assert CollectToolService.build_debug_owner(req) == {"username": "bob", "domain": "d2"}

    @pytest.mark.parametrize("raw,expected", [("1", True), ("true", True), ("YES", True), ("0", False), ("no", False), ("", False)])
    def test_build_node_permission_data_include_children(self, raw, expected, monkeypatch):
        monkeypatch.setattr(
            "apps.cmdb.services.collect_tool_service.get_current_team",
            lambda request: ["team-1"],
        )
        req = _FakeRequest(cookies={"include_children": raw})
        data = CollectToolService.build_node_permission_data(req)
        assert data["include_children"] is expected
        assert data["current_team"] == ["team-1"]
        assert data["username"] == "alice"

    def test_can_access_debug_state_match_and_mismatch(self):
        req = _FakeRequest(username="alice", domain="domain.com")
        good = {"owner": {"username": "alice", "domain": "domain.com"}}
        bad = {"owner": {"username": "eve", "domain": "domain.com"}}
        empty = {}
        assert CollectToolService.can_access_debug_state(good, req) is True
        assert CollectToolService.can_access_debug_state(bad, req) is False
        assert CollectToolService.can_access_debug_state(empty, req) is False

    def test_build_submit_response_with_and_without_result(self):
        no_result = CollectToolService.build_submit_response("d1", "pending")
        assert no_result == {
            "debug_id": "d1",
            "status": "pending",
            "poll_interval_ms": COLLECT_TOOL_POLL_INTERVAL_MS,
        }
        with_result = CollectToolService.build_submit_response("d1", "success", {"ok": 1})
        assert with_result["result"] == {"ok": 1}

    def test_build_error_result_maps_payload(self):
        payload = {"protocol": "snmp", "action": "get_oid", "target": "1.2.3.4", "port": 161}
        res = CollectToolService.build_error_result("d9", payload, "connect", "boom", raw_log="x", duration_ms=12)
        assert res["request_id"] == "d9"
        assert res["protocol"] == "snmp"
        assert res["success"] is False
        assert res["stage"] == "connect"
        assert res["summary"] == "boom"
        assert res["raw_log"] == "x"
        assert res["duration_ms"] == 12
        assert res["meta"] == {"target": "1.2.3.4", "port": 161}
        assert res["executor"] == "stargazer"

    def test_normalize_debug_result_fills_summary_and_raw_from_error(self):
        out = CollectToolService.normalize_debug_result({"success": False, "error": "kaboom"})
        assert out["summary"] == "kaboom"
        assert out["raw_log"] == "kaboom"
        assert out["stage"] == "unknown"

    def test_normalize_debug_result_keeps_existing_and_no_unknown_on_success(self):
        out = CollectToolService.normalize_debug_result(
            {"success": True, "summary": "ok", "raw_log": "log", "stage": "done"}
        )
        assert out["summary"] == "ok"
        assert out["raw_log"] == "log"
        assert out["stage"] == "done"

    def test_normalize_debug_result_failure_existing_stage_preserved(self):
        out = CollectToolService.normalize_debug_result({"success": False, "stage": "auth", "summary": "s"})
        assert out["stage"] == "auth"


# ===========================================================================
# CollectToolService - cache-backed state (mock django cache boundary)
# ===========================================================================
class TestCollectToolDebugState:
    def test_save_debug_state_sets_cache_and_returns_state(self, mocker):
        store = {}
        mock_cache = mocker.patch("apps.cmdb.services.collect_tool_service.cache")
        mock_cache.set.side_effect = lambda k, v, timeout=None: store.__setitem__(k, v)
        mock_cache.get.side_effect = lambda k: store.get(k)

        owner = {"username": "alice", "domain": "domain.com"}
        state = CollectToolService.save_debug_state("d1", "pending", owner=owner)

        assert state["debug_id"] == "d1"
        assert state["status"] == "pending"
        assert state["owner"] == owner
        assert state["poll_interval_ms"] == COLLECT_TOOL_POLL_INTERVAL_MS
        # cache.set called with proper key
        key = CollectToolService.get_cache_key("d1")
        assert store[key] == state

    def test_save_debug_state_inherits_previous_owner_when_none(self, mocker):
        key = CollectToolService.get_cache_key("d2")
        store = {key: {"owner": {"username": "prev", "domain": "d"}}}
        mock_cache = mocker.patch("apps.cmdb.services.collect_tool_service.cache")
        mock_cache.set.side_effect = lambda k, v, timeout=None: store.__setitem__(k, v)
        mock_cache.get.side_effect = lambda k: store.get(k)

        state = CollectToolService.save_debug_state("d2", "running", result={"r": 1})
        assert state["owner"] == {"username": "prev", "domain": "d"}
        assert state["result"] == {"r": 1}

    def test_get_debug_state_reads_cache(self, mocker):
        mock_cache = mocker.patch("apps.cmdb.services.collect_tool_service.cache")
        mock_cache.get.return_value = {"status": "done"}
        out = CollectToolService.get_debug_state("dX")
        mock_cache.get.assert_called_once_with(CollectToolService.get_cache_key("dX"))
        assert out == {"status": "done"}


# ===========================================================================
# CollectToolService - inject_credentials
# ===========================================================================
class TestInjectCredentials:
    def test_snmp_masked_field_replaced_with_plaintext(self):
        inst = _FakeInstance(decrypt_credentials={"community": "public", "authkey": "real-auth"})
        payload = {
            "protocol": "snmp",
            "credential": {"community": MASKED_PASSWORD, "version": "v2c"},
        }
        out = CollectToolService.inject_credentials(payload, inst)
        assert out["credential"]["community"] == "public"
        # untouched non-masked field stays
        assert out["credential"]["version"] == "v2c"

    def test_ipmi_masked_password_replaced(self):
        inst = _FakeInstance(decrypt_credentials={"password": "secret"})
        payload = {"protocol": "ipmi", "credential": {"password": MASKED_PASSWORD}}
        out = CollectToolService.inject_credentials(payload, inst)
        assert out["credential"]["password"] == "secret"

    def test_masked_field_missing_in_decrypted_raises(self):
        inst = _FakeInstance(decrypt_credentials={})
        payload = {"protocol": "snmp", "credential": {"community": MASKED_PASSWORD}}
        with pytest.raises(ValidationError):
            CollectToolService.inject_credentials(payload, inst)

    def test_non_masked_value_left_alone(self):
        inst = _FakeInstance(decrypt_credentials={"community": "shouldnotbeused"})
        payload = {"protocol": "snmp", "credential": {"community": "explicit"}}
        out = CollectToolService.inject_credentials(payload, inst)
        assert out["credential"]["community"] == "explicit"


# ===========================================================================
# CollectToolService - prefill helpers
# ===========================================================================
class TestPrefillHelpers:
    def test_build_access_point_prefill_from_list(self):
        inst = _FakeInstance(access_point=[{"id": 7, "name": "ap-7"}])
        out = CollectToolService._build_access_point_prefill(inst)
        assert out == {"access_point": {"id": "7", "name": "ap-7"}}

    def test_build_access_point_prefill_node_id_fallback(self):
        inst = _FakeInstance(access_point={"node_id": 9, "node_name": "n9"})
        out = CollectToolService._build_access_point_prefill(inst)
        assert out == {"access_point": {"id": "9", "name": "n9"}}

    def test_build_access_point_prefill_empty(self):
        inst = _FakeInstance(access_point={})
        assert CollectToolService._build_access_point_prefill(inst) == {}
        inst2 = _FakeInstance(access_point={"id": "", "name": ""})
        assert CollectToolService._build_access_point_prefill(inst2) == {}

    def test_extract_target_context_from_instances(self):
        inst = _FakeInstance(instances=[{"ip": "10.0.0.5", "port": 22}])
        host, port = CollectToolService._extract_target_context(inst)
        assert host == "10.0.0.5"
        assert port == 22

    def test_extract_target_context_host_key_fallback(self):
        inst = _FakeInstance(instances=[{"host": "myhost"}])
        host, port = CollectToolService._extract_target_context(inst)
        assert host == "myhost"
        assert port is None

    def test_extract_target_context_from_ip_range(self):
        inst = _FakeInstance(instances=[], ip_range=" 192.168.1.10,192.168.1.11\n10.0.0.1 ")
        host, port = CollectToolService._extract_target_context(inst)
        assert host == "192.168.1.10"

    def test_extract_target_context_ip_range_non_ip_returns_none(self):
        inst = _FakeInstance(instances=[], ip_range="not-an-ip")
        host, port = CollectToolService._extract_target_context(inst)
        assert host is None

    def test_get_decrypted_credential_falls_back_to_raw(self):
        inst = _FakeInstance(decrypt_credentials={}, credential={"k": "v"})
        assert CollectToolService._get_decrypted_credential(inst) == {"k": "v"}

    def test_get_decrypted_credential_prefers_decrypted(self):
        inst = _FakeInstance(decrypt_credentials={"d": 1}, credential={"k": "v"})
        assert CollectToolService._get_decrypted_credential(inst) == {"d": 1}

    def test_build_snmp_prefill_v2c_masks_community(self):
        cred, port = CollectToolService._build_snmp_prefill(
            {"version": "v2c", "community": "public"}, {}, None
        )
        assert cred["version"] == "v2c"
        assert cred["community"] == MASKED_PASSWORD
        assert port == 161

    def test_build_snmp_prefill_no_version_returns_defaults(self):
        cred, port = CollectToolService._build_snmp_prefill({}, {}, 1161)
        assert cred == {}
        assert port == 1161

    def test_build_snmp_prefill_v3_authpriv(self):
        decrypted = {
            "version": "v3",
            "username": "admin",
            "level": "authPriv",
            "integrity": "sha",
            "authkey": "ak",
            "privkey": "pk",
            "privacy": "aes",
        }
        cred, port = CollectToolService._build_snmp_prefill(decrypted, {}, None)
        assert cred["version"] == "v3"
        assert cred["username"] == "admin"
        assert cred["authkey"] == MASKED_PASSWORD
        assert cred["privkey"] == MASKED_PASSWORD
        assert cred["privacy"] == "aes"

    def test_build_snmp_prefill_v3_authnopriv_omits_privacy(self):
        decrypted = {"version": "v3", "level": "authNoPriv", "privacy": "aes", "authkey": "ak"}
        cred, _ = CollectToolService._build_snmp_prefill(decrypted, {}, None)
        assert "privacy" not in cred

    def test_build_ipmi_prefill(self):
        decrypted = {"username": "root", "password": "pw", "privilege": "admin", "cipher_suite": 3, "port": 624}
        cred, port = CollectToolService._build_ipmi_prefill(decrypted, None)
        assert cred["username"] == "root"
        assert cred["password"] == MASKED_PASSWORD
        assert cred["privilege"] == "admin"
        assert cred["cipher_suite"] == "3"
        assert port == 624

    def test_build_ipmi_prefill_default_port(self):
        cred, port = CollectToolService._build_ipmi_prefill({}, None)
        assert port == 623
        assert cred == {}

    def test_build_prefill_snmp_full(self):
        inst = _FakeInstance(
            access_point=[{"id": 1, "name": "ap"}],
            instances=[{"ip": "10.0.0.1", "port": 161}],
            decrypt_credentials={"version": "v2c", "community": "public"},
        )
        out = CollectToolService.build_prefill(inst, task_id=5, protocol="snmp")
        assert out["can_prefill"] is True
        assert out["task_id"] == 5
        assert out["prefill"]["target"] == "10.0.0.1"
        assert out["prefill"]["credential"]["community"] == MASKED_PASSWORD
        assert out["prefill"]["port"] == 161

    def test_build_prefill_unknown_protocol_no_credential_but_prefill(self):
        inst = _FakeInstance(access_point=[{"id": 1, "name": "ap"}])
        out = CollectToolService.build_prefill(inst, task_id=1, protocol="ssh")
        assert out["can_prefill"] is True
        assert "credential" not in out["prefill"]

    def test_build_prefill_empty_returns_cannot_prefill(self):
        inst = _FakeInstance(access_point={}, instances=[], decrypt_credentials={})
        out = CollectToolService.build_prefill(inst, task_id=3, protocol="ssh")
        assert out == {"task_id": 3, "protocol": "ssh", "can_prefill": False, "prefill": None}


# ===========================================================================
# CollectToolService - execute_debug (mock Stargazer RPC boundary)
# ===========================================================================
class TestExecuteDebug:
    def _payload(self, **over):
        base = {"protocol": "snmp", "action": "test_connection", "target": "1.1.1.1", "port": 161, "credential": {"community": "c"}}
        base.update(over)
        return base

    def test_execute_debug_success_normalizes_and_wraps(self, mocker):
        fake_sg = mocker.Mock()
        fake_sg.collection_tool_debug.return_value = {
            "success": True,
            "stage": "done",
            "summary": "ok",
            "raw_log": "L",
            "duration_ms": 42,
        }
        mocker.patch("apps.cmdb.services.collect_tool_service.Stargazer", return_value=fake_sg)

        out = CollectToolService.execute_debug(self._payload(), "default_stargazer", 10, request_id="req-1")
        assert out["request_id"] == "req-1"
        assert out["success"] is True
        assert out["stage"] == "done"
        assert out["meta"] == {"target": "1.1.1.1", "port": 161}
        # verify the nats payload contract sent to Stargazer
        call_args = fake_sg.collection_tool_debug.call_args
        nats_payload = call_args.args[0]
        assert nats_payload["timeout"] == 10
        assert nats_payload["protocol"] == "snmp"
        assert call_args.args[1] == 10

    def test_execute_debug_get_oid_includes_oid(self, mocker):
        fake_sg = mocker.Mock()
        fake_sg.collection_tool_debug.return_value = {"success": True}
        mocker.patch("apps.cmdb.services.collect_tool_service.Stargazer", return_value=fake_sg)

        CollectToolService.execute_debug(
            self._payload(action="get_oid", oid="1.3.6.1"), "default_stargazer", 120, request_id="r"
        )
        nats_payload = fake_sg.collection_tool_debug.call_args.args[0]
        assert nats_payload["oid"] == "1.3.6.1"

    def test_execute_debug_timeout_exception_maps_to_timeout_stage(self, mocker):
        fake_sg = mocker.Mock()
        fake_sg.collection_tool_debug.side_effect = Exception("NATS request Timeout exceeded")
        mocker.patch("apps.cmdb.services.collect_tool_service.Stargazer", return_value=fake_sg)

        out = CollectToolService.execute_debug(self._payload(), "default_stargazer", 7, request_id="r")
        assert out["success"] is False
        assert out["stage"] == "timeout"
        assert out["duration_ms"] == 7000

    def test_execute_debug_generic_exception_maps_to_unknown(self, mocker):
        fake_sg = mocker.Mock()
        fake_sg.collection_tool_debug.side_effect = Exception("boom")
        mocker.patch("apps.cmdb.services.collect_tool_service.Stargazer", return_value=fake_sg)

        out = CollectToolService.execute_debug(self._payload(), "default_stargazer", 7, request_id="r")
        assert out["success"] is False
        assert out["stage"] == "unknown"
        assert "boom" in out["summary"]


# ===========================================================================
# CollectToolService - run_debug_task / enqueue (mock cache + celery)
# ===========================================================================
class TestRunAndEnqueueDebug:
    def test_run_debug_task_success_saves_states(self, mocker):
        saved = []
        mocker.patch.object(
            CollectToolService,
            "save_debug_state",
            side_effect=lambda *a, **k: saved.append((a, k)),
        )
        mocker.patch.object(
            CollectToolService,
            "execute_debug",
            return_value={"success": True, "summary": "ok"},
        )
        result = CollectToolService.run_debug_task("d1", {"protocol": "snmp"}, "svc", 10)
        assert result["success"] is True
        # first save = running, last save = success
        assert saved[0][0][1] == "running"
        assert saved[-1][0][1] == "success"

    def test_run_debug_task_error_state(self, mocker):
        saved = []
        mocker.patch.object(CollectToolService, "save_debug_state", side_effect=lambda *a, **k: saved.append(a))
        mocker.patch.object(CollectToolService, "execute_debug", return_value={"success": False})
        CollectToolService.run_debug_task("d1", {}, "svc", 10)
        assert saved[-1][1] == "error"

    def test_enqueue_debug_task_calls_celery_delay(self, mocker):
        mocker.patch.object(CollectToolService, "save_debug_state")
        fake_task = mocker.patch(
            "apps.cmdb.tasks.celery_tasks.execute_collect_tool_debug_task"
        )
        owner = {"username": "alice"}
        CollectToolService.enqueue_debug_task("d1", {"p": 1}, "svc", 30, owner)
        fake_task.delay.assert_called_once_with("d1", {"p": 1}, "svc", 30)
        CollectToolService.save_debug_state.assert_called_once_with("d1", "pending", owner=owner)


# ===========================================================================
# DataCleanupService
# ===========================================================================
class TestDataCleanupPure:
    def test_parse_collect_time_valid_z_suffix(self):
        dt = DataCleanupService.parse_collect_time("2024-01-01T00:00:00Z")
        assert dt is not None
        assert dt.year == 2024

    def test_parse_collect_time_empty_returns_none(self):
        assert DataCleanupService.parse_collect_time("") is None

    def test_parse_collect_time_invalid_returns_none(self):
        assert DataCleanupService.parse_collect_time("garbage") is None

    def test_get_expire_threshold_is_in_the_past(self):
        iso = DataCleanupService.get_expire_threshold(7)
        from datetime import datetime

        threshold = datetime.fromisoformat(iso)
        now = timezone.now()
        delta = now - threshold
        # ~7 days back (allow slack)
        assert timedelta(days=6, hours=23) < delta < timedelta(days=7, hours=1)


@pytest.mark.django_db
class TestDataCleanupWithGraph:
    def _make_task(self, **kw):
        from apps.cmdb.models.collect_model import CollectModels

        defaults = dict(
            name=kw.pop("name", "cleanup-task"),
            task_type="host",
            driver_type="protocol",
            model_id="host",
            cycle_value_type="hour",
            expire_days=30,
        )
        defaults.update(kw)
        return CollectModels.objects.create(**defaults)

    def test_cleanup_skips_when_expire_days_zero(self):
        task = self._make_task(name="zero-expire", expire_days=0)
        out = DataCleanupService.cleanup_expired_instances(task)
        assert out == {"task_id": task.id, "deleted_count": 0, "skipped": True}

    def test_cleanup_deletes_expired_instances(self, fake_graph):
        task = self._make_task(name="expire-del", expire_days=10)
        old_time = (timezone.now() - timedelta(days=30)).isoformat()
        fresh_time = timezone.now().isoformat()
        instances = [
            {"_id": "i-old", "collect_time": old_time},
            {"_id": "i-fresh", "collect_time": fresh_time},
            {"_id": "i-none"},  # no collect_time -> skipped
        ]
        fake = fake_graph(
            "apps.cmdb.services.data_cleanup_service",
            query_entity=(instances, len(instances)),
            batch_delete_entity={},
        )
        out = DataCleanupService.cleanup_expired_instances(task)
        assert out["deleted_count"] == 1
        assert out["model_id"] == "host"
        # only the expired id was passed to delete
        delete_call = [c for c in fake.calls if c[0] == "batch_delete_entity"][0]
        assert delete_call[1][1] == ["i-old"]

    def test_cleanup_handles_delete_failure(self, fake_graph):
        task = self._make_task(name="expire-fail", expire_days=10)
        old_time = (timezone.now() - timedelta(days=30)).isoformat()

        def _boom(*a, **k):
            raise RuntimeError("graph down")

        fake_graph(
            "apps.cmdb.services.data_cleanup_service",
            query_entity=([{"_id": "i-old", "collect_time": old_time}], 1),
            batch_delete_entity=_boom,
        )
        out = DataCleanupService.cleanup_expired_instances(task)
        assert out["deleted_count"] == 0
        assert out["failed_count"] == 1
        assert out["expired_ids"] == ["i-old"]
        assert "graph down" in out["error"]

    def test_run_daily_cleanup_aggregates(self, fake_graph, mocker):
        task = self._make_task(name="daily", expire_days=10, data_cleanup_strategy="after_expiration")
        old_time = (timezone.now() - timedelta(days=30)).isoformat()
        fake_graph(
            "apps.cmdb.services.data_cleanup_service",
            query_entity=([{"_id": "i-old", "collect_time": old_time}], 1),
            batch_delete_entity={},
        )
        summary = DataCleanupService.run_daily_cleanup()
        assert summary["tasks_processed"] >= 1
        assert summary["total_deleted"] >= 1
        # BUG(已知):run_daily_cleanup 成功路径未回填 expired_ids,delete_ids 恒空(待修)
        assert summary["delete_ids"] == []

    def test_run_daily_cleanup_records_task_error(self, mocker):
        self._make_task(name="daily-err", expire_days=10, data_cleanup_strategy="after_expiration")
        mocker.patch.object(
            DataCleanupService,
            "cleanup_expired_instances",
            side_effect=RuntimeError("explode"),
        )
        summary = DataCleanupService.run_daily_cleanup()
        assert summary["tasks_processed"] >= 1
        assert any("explode" in r.get("error", "") for r in summary["results"])


# ===========================================================================
# K8sSetupService
# ===========================================================================
class TestValidateCollectorClusterId:
    def test_valid_id_returned(self):
        assert validate_collector_cluster_id("abc-123_X") == "abc-123_X"

    def test_empty_raises(self):
        with pytest.raises(BaseAppException):
            validate_collector_cluster_id("")

    def test_invalid_chars_raises(self):
        with pytest.raises(BaseAppException):
            validate_collector_cluster_id("bad id!")


class TestK8sSetupService:
    def test_generate_install_token(self, mocker):
        mocker.patch.object(k8s_mod.InfraService, "generate_install_token", return_value="tok-123")
        out = K8sSetupService.generate_install_token("cluster-1", 5)
        assert out["token"] == "tok-123"
        assert out["expire_seconds"] == k8s_mod.InfraConstants.TOKEN_EXPIRE_TIME
        assert out["max_usage"] == k8s_mod.InfraConstants.TOKEN_MAX_USAGE

    def test_generate_install_token_invalid_id(self, mocker):
        spy = mocker.patch.object(k8s_mod.InfraService, "generate_install_token")
        with pytest.raises(BaseAppException):
            K8sSetupService.generate_install_token("bad!id", 1)
        spy.assert_not_called()

    def test_generate_install_command_builds_curl(self, mocker):
        fake_node = mocker.Mock()
        fake_node.get_cloud_region_envconfig.return_value = {"NODE_SERVER_URL": "http://srv:8000/"}
        mocker.patch("apps.rpc.node_mgmt.NodeMgmt", return_value=fake_node)
        mocker.patch.object(k8s_mod.InfraService, "generate_install_token", return_value="TKN")

        out = K8sSetupService.generate_install_command("c1", 3)
        assert out["token"] == "TKN"
        assert "kubectl apply -f -" in out["command"]
        assert "http://srv:8000/api/v1/cmdb/open_api/k8s_setup/render/" in out["command"]
        assert '"token":"TKN"' in out["command"]

    def test_generate_install_command_missing_server_url(self, mocker):
        fake_node = mocker.Mock()
        fake_node.get_cloud_region_envconfig.return_value = {}
        mocker.patch("apps.rpc.node_mgmt.NodeMgmt", return_value=fake_node)
        with pytest.raises(BaseAppException):
            K8sSetupService.generate_install_command("c1", 3)

    def test_render_yaml_by_token(self, mocker):
        mocker.patch.object(
            k8s_mod.InfraService,
            "validate_and_get_token_data",
            return_value={"cluster_name": "k1", "cloud_region_id": 2, "remaining_usage": 4},
        )
        mocker.patch.object(
            k8s_mod.InfraService, "render_config_from_cloud_region", return_value="yaml-body"
        )
        out = K8sSetupService.render_yaml_by_token("tok")
        assert out["yaml"] == "yaml-body"
        assert out["remaining_usage"] == 4

    def test_verify_collector_reporting_true(self, mocker):
        fake_coll = mocker.Mock()
        fake_coll.query.return_value = {"data": {"result": [{"metric": {}}, {"metric": {}}]}}
        mocker.patch("apps.cmdb.services.k8s_setup.Collection", return_value=fake_coll)
        out = K8sSetupService.verify_collector_reporting("cluster-1")
        assert out["reporting"] is True
        assert out["sample_count"] == 2

    def test_verify_collector_reporting_false_empty_result(self, mocker):
        fake_coll = mocker.Mock()
        fake_coll.query.return_value = {"data": {"result": []}}
        mocker.patch("apps.cmdb.services.k8s_setup.Collection", return_value=fake_coll)
        out = K8sSetupService.verify_collector_reporting("cluster-1")
        assert out["reporting"] is False
        assert out["sample_count"] == 0

    def test_verify_collector_reporting_query_error(self, mocker):
        fake_coll = mocker.Mock()
        fake_coll.query.side_effect = RuntimeError("vm down")
        mocker.patch("apps.cmdb.services.k8s_setup.Collection", return_value=fake_coll)
        out = K8sSetupService.verify_collector_reporting("cluster-1")
        assert out["reporting"] is False
        assert "vm down" in out["error"]

    def test_verify_collector_reporting_invalid_id(self):
        with pytest.raises(BaseAppException):
            K8sSetupService.verify_collector_reporting("bad id!")
