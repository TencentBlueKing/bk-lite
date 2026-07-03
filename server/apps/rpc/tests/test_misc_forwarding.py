"""rpc 各业务封装的转发契约测试。

覆盖 cmdb / log / mlops / opspilot / job_mgmt / console_mgmt /
operation_analysis / alerts / stargazer 客户端的方法名 + 参数转发契约。
统一把 self.client 替换为记录器，断言转发的方法名与入参，不触达真实 NATS。
"""
import pydantic.root_model  # noqa

import pytest

pytestmark = pytest.mark.unit


class _Recorder:
    def __init__(self, ret=None):
        self.calls = []
        self.ret = ret if ret is not None else {"result": True}

    def run(self, method_name, *args, **kwargs):
        self.calls.append(("run", method_name, args, kwargs))
        return self.ret

    def request(self, method_name, *args, **kwargs):
        self.calls.append(("request", method_name, args, kwargs))
        return self.ret


def _last(rec):
    return rec.calls[-1]


# --------------------------- CMDB ---------------------------

@pytest.fixture
def cmdb(monkeypatch):
    monkeypatch.setenv("IS_LOCAL_RPC", "0")
    from apps.rpc.cmdb import CMDB

    c = CMDB(is_local_client=False)
    c.client = _Recorder()
    return c


def test_cmdb_get_module_data(cmdb):
    out = cmdb.get_module_data(module="host", page=2)
    assert out == {"result": True}
    assert _last(cmdb.client) == ("run", "get_cmdb_module_data", (), {"module": "host", "page": 2})


def test_cmdb_get_module_list(cmdb):
    cmdb.get_module_list(module="host")
    assert _last(cmdb.client) == ("run", "get_cmdb_module_list", (), {"module": "host"})


def test_cmdb_search_instances(cmdb):
    cmdb.search_instances(ip="1.1.1.1")
    assert _last(cmdb.client) == ("run", "search_instances", (), {"ip": "1.1.1.1"})


def test_cmdb_search_instances_batch(cmdb):
    cmdb.search_instances_batch(items=[1, 2])
    assert _last(cmdb.client) == ("run", "search_instances_batch", (), {"items": [1, 2]})


def test_cmdb_list_instances(cmdb):
    cmdb.list_instances(model_id="host", page=1)
    assert _last(cmdb.client) == ("run", "list_instances", (), {"model_id": "host", "page": 1})


def test_cmdb_search_model_attrs(cmdb):
    cmdb.search_model_attrs(model_id="host")
    assert _last(cmdb.client) == ("run", "search_model_attrs", (), {"model_id": "host"})


def test_cmdb_search_models(cmdb):
    cmdb.search_models(classification_id="biz")
    assert _last(cmdb.client) == ("run", "search_models", (), {"classification_id": "biz"})


def test_cmdb_search_classifications(cmdb):
    cmdb.search_classifications(include_hidden=False)
    assert _last(cmdb.client) == ("run", "search_classifications", (), {"include_hidden": False})


def test_cmdb_search_model_associations(cmdb):
    cmdb.search_model_associations(model_id="host")
    assert _last(cmdb.client) == ("run", "search_model_associations", (), {"model_id": "host"})


def test_cmdb_search_instance_associations(cmdb):
    cmdb.search_instance_associations(model_id="host", inst_id=1)
    assert _last(cmdb.client) == ("run", "search_instance_associations", (), {"model_id": "host", "inst_id": 1})


def test_cmdb_create_instance_association(cmdb):
    cmdb.create_instance_association(src_inst_id=1, dst_inst_id=2)
    assert _last(cmdb.client) == ("run", "create_instance_association", (), {"src_inst_id": 1, "dst_inst_id": 2})


def test_cmdb_delete_instance_association(cmdb):
    cmdb.delete_instance_association(asso_id=9)
    assert _last(cmdb.client) == ("run", "delete_instance_association", (), {"asso_id": 9})


def test_cmdb_sync_display_fields(cmdb):
    cmdb.sync_display_fields(organizations=[{"id": 1}])
    assert _last(cmdb.client) == ("run", "sync_display_fields", (), {"organizations": [{"id": 1}]})


def test_cmdb_model_inst_count(cmdb):
    cmdb.model_inst_count(model_id="host")
    assert _last(cmdb.client) == ("run", "model_inst_count", (), {"model_id": "host"})


def test_cmdb_local_client_appclient_path(monkeypatch):
    monkeypatch.setenv("IS_LOCAL_RPC", "0")
    from apps.rpc.cmdb import CMDB

    c = CMDB(is_local_client=True)
    assert c.client.path == "apps.cmdb.nats.nats"


def test_cmdb_remote_client_is_rpcclient(monkeypatch):
    monkeypatch.setenv("IS_LOCAL_RPC", "0")
    from apps.rpc.base import RpcClient
    from apps.rpc.cmdb import CMDB

    c = CMDB(is_local_client=False)
    assert isinstance(c.client, RpcClient)


def test_cmdb_env_forces_local(monkeypatch):
    monkeypatch.setenv("IS_LOCAL_RPC", "1")
    from apps.rpc.base import AppClient
    from apps.rpc.cmdb import CMDB

    c = CMDB(is_local_client=False)
    assert isinstance(c.client, AppClient)
    assert c.client.path == "apps.cmdb.nats.nats"


# --------------------------- Log ---------------------------

@pytest.fixture
def log(monkeypatch):
    monkeypatch.setenv("IS_LOCAL_RPC", "0")
    from apps.rpc.log import Log

    obj = Log(is_local_client=False)
    obj.client = _Recorder()
    return obj


def test_log_get_module_data(log):
    log.get_module_data(module="syslog", page=1)
    assert _last(log.client) == ("run", "get_log_module_data", (), {"module": "syslog", "page": 1})


def test_log_get_module_list(log):
    log.get_module_list(module="syslog")
    assert _last(log.client) == ("run", "get_log_module_list", (), {"module": "syslog"})


def test_log_local_client_appclient_path(monkeypatch):
    monkeypatch.setenv("IS_LOCAL_RPC", "0")
    from apps.rpc.log import Log

    obj = Log(is_local_client=True)
    assert obj.client.path == "apps.log.nats.permission"


def test_log_env_forces_local(monkeypatch):
    monkeypatch.setenv("IS_LOCAL_RPC", "1")
    from apps.rpc.base import AppClient
    from apps.rpc.log import Log

    obj = Log(is_local_client=False)
    assert isinstance(obj.client, AppClient)


@pytest.fixture
def log_ana():
    from apps.rpc.log import LogOperationAnaRpc

    rpc = LogOperationAnaRpc()
    rpc.client = _Recorder()
    return rpc


def test_log_ana_get_vmlogs_disk_usage(log_ana):
    log_ana.get_vmlogs_disk_usage(foo="bar")
    assert _last(log_ana.client) == ("run", "get_vmlogs_disk_usage", (), {"foo": "bar"})


def test_log_ana_search_defaults(log_ana):
    log_ana.search("q", "1h")
    assert _last(log_ana.client) == (
        "run",
        "log_search",
        (),
        {"query": "q", "time_range": "1h", "limit": 10},
    )


def test_log_ana_search_custom_limit(log_ana):
    log_ana.search("q", "1h", limit=50, extra="x")
    assert _last(log_ana.client) == (
        "run",
        "log_search",
        (),
        {"query": "q", "time_range": "1h", "limit": 50, "extra": "x"},
    )


def test_log_ana_hits_defaults(log_ana):
    log_ana.hits("q", "1h", "host")
    assert _last(log_ana.client) == (
        "run",
        "log_hits",
        (),
        {"query": "q", "time_range": "1h", "field": "host", "fields_limit": 5, "step": "5m"},
    )


def test_log_ana_hits_custom(log_ana):
    log_ana.hits("q", "1h", "host", fields_limit=3, step="10m")
    assert _last(log_ana.client) == (
        "run",
        "log_hits",
        (),
        {"query": "q", "time_range": "1h", "field": "host", "fields_limit": 3, "step": "10m"},
    )


def test_log_ana_query_alert_segments(log_ana):
    qd = {"collect_type_id": "c1", "page": 1}
    log_ana.query_log_alert_segments(qd, user_info={"team": 1})
    assert _last(log_ana.client) == (
        "run",
        "query_log_alert_segments",
        (),
        {"query_data": qd, "user_info": {"team": 1}},
    )


# --------------------------- MLOps ---------------------------

@pytest.fixture
def mlops(monkeypatch):
    monkeypatch.setenv("IS_LOCAL_RPC", "0")
    from apps.rpc.mlops import MLOps

    obj = MLOps(is_local_client=False)
    obj.client = _Recorder()
    return obj


def test_mlops_get_module_data(mlops):
    mlops.get_module_data(module="m")
    assert _last(mlops.client) == ("run", "get_mlops_module_data", (), {"module": "m"})


def test_mlops_get_module_list(mlops):
    mlops.get_module_list()
    assert _last(mlops.client) == ("run", "get_mlops_module_list", (), {})


def test_mlops_local_client_appclient_path(monkeypatch):
    monkeypatch.setenv("IS_LOCAL_RPC", "0")
    from apps.rpc.mlops import MLOps

    obj = MLOps(is_local_client=True)
    assert obj.client.path == "apps.mlops.nats_api"


# --------------------------- OpsPilot ---------------------------

@pytest.fixture
def opspilot(monkeypatch):
    monkeypatch.setenv("IS_LOCAL_RPC", "0")
    from apps.rpc.opspilot import OpsPilot

    obj = OpsPilot(is_local_client=False)
    obj.client = _Recorder()
    return obj


def test_opspilot_get_module_data(opspilot):
    opspilot.get_module_data(module="bot")
    assert _last(opspilot.client) == ("run", "get_opspilot_module_data", (), {"module": "bot"})


def test_opspilot_get_module_list(opspilot):
    opspilot.get_module_list()
    assert _last(opspilot.client) == ("run", "get_opspilot_module_list", (), {})


def test_opspilot_get_guest_provider(opspilot):
    opspilot.get_guest_provider(group_id=7)
    assert _last(opspilot.client) == ("run", "get_guest_provider", (), {"group_id": 7})


def test_opspilot_local_client_appclient_path(monkeypatch):
    monkeypatch.setenv("IS_LOCAL_RPC", "0")
    from apps.rpc.opspilot import OpsPilot

    obj = OpsPilot(is_local_client=True)
    assert obj.client.path == "apps.opspilot.nats_api"


# --------------------------- JobMgmt ---------------------------

@pytest.fixture
def job(monkeypatch):
    monkeypatch.setenv("IS_LOCAL_RPC", "0")
    from apps.rpc.job_mgmt import JobMgmt

    obj = JobMgmt(is_local_client=False)
    obj.client = _Recorder()
    return obj


def test_job_get_module_data(job):
    job.get_module_data(module="j", page=1)
    assert _last(job.client) == ("run", "get_job_mgmt_module_data", (), {"module": "j", "page": 1})


def test_job_get_module_list(job):
    job.get_module_list()
    assert _last(job.client) == ("run", "get_job_mgmt_module_list", (), {})


def test_job_local_client_appclient_path(monkeypatch):
    monkeypatch.setenv("IS_LOCAL_RPC", "0")
    from apps.rpc.job_mgmt import JobMgmt

    obj = JobMgmt(is_local_client=True)
    assert obj.client.path == "apps.job_mgmt.nats_api"


def test_job_env_forces_local(monkeypatch):
    monkeypatch.setenv("IS_LOCAL_RPC", "1")
    from apps.rpc.base import AppClient
    from apps.rpc.job_mgmt import JobMgmt

    obj = JobMgmt(is_local_client=False)
    assert isinstance(obj.client, AppClient)


# --------------------------- ConsoleMgmt ---------------------------

@pytest.fixture
def console(monkeypatch):
    monkeypatch.setenv("IS_LOCAL_RPC", "0")
    from apps.rpc.console_mgmt import ConsoleMgmt

    obj = ConsoleMgmt(is_local_client=False)
    obj.client = _Recorder()
    return obj


def test_console_create_notification(console):
    console.create_notification("monitor", "hello")
    assert _last(console.client) == ("run", "create_notification", (), {"app": "monitor", "message": "hello"})


def test_console_local_client_appclient_path():
    from apps.rpc.console_mgmt import ConsoleMgmt

    obj = ConsoleMgmt(is_local_client=True)
    assert obj.client.path == "apps.console_mgmt.nats_api"


def test_console_remote_client_is_rpcclient():
    from apps.rpc.base import RpcClient
    from apps.rpc.console_mgmt import ConsoleMgmt

    obj = ConsoleMgmt(is_local_client=False)
    assert isinstance(obj.client, RpcClient)


# --------------------------- OperationAnalysisRPC ---------------------------

@pytest.fixture
def op_ana():
    from apps.rpc.operation_analysis import OperationAnalysisRPC

    obj = OperationAnalysisRPC()
    obj.client = _Recorder()
    return obj


def test_op_ana_get_module_data(op_ana):
    op_ana.get_module_data(module="x")
    assert _last(op_ana.client) == ("run", "get_operation_analysis_module_data", (), {"module": "x"})


def test_op_ana_get_module_list(op_ana):
    op_ana.get_module_list(module="x")
    assert _last(op_ana.client) == ("run", "get_operation_analysis_module_list", (), {"module": "x"})


def test_op_ana_construct_uses_rpcclient():
    from apps.rpc.base import RpcClient
    from apps.rpc.operation_analysis import OperationAnalysisRPC

    obj = OperationAnalysisRPC()
    assert isinstance(obj.client, RpcClient)


# --------------------------- AlertOperationAnaRpc ---------------------------

@pytest.fixture
def alert_ana():
    from apps.rpc.alerts import AlertOperationAnaRpc

    obj = AlertOperationAnaRpc()
    obj.client = _Recorder()
    return obj


def test_alert_get_trend_data_kwargs(alert_ana):
    alert_ana.get_alert_trend_data(group_by="level", filters={"a": 1})
    assert _last(alert_ana.client) == ("run", "get_alert_trend_data", (), {"group_by": "level", "filters": {"a": 1}})


def test_alert_get_trend_data_positional(alert_ana):
    alert_ana.get_alert_trend_data("level", {"a": 1})
    assert _last(alert_ana.client) == ("run", "get_alert_trend_data", ("level", {"a": 1}), {})


def test_alert_ana_uses_operation_analysis_rpc():
    from apps.rpc.alerts import AlertOperationAnaRpc
    from apps.rpc.base import OperationAnalysisRpc

    obj = AlertOperationAnaRpc()
    assert isinstance(obj.client, OperationAnalysisRpc)


# --------------------------- Stargazer ---------------------------

@pytest.fixture
def stargazer():
    from apps.rpc.stargazer import Stargazer

    obj = Stargazer()
    obj.client = _Recorder()
    obj.health_check_client = _Recorder()
    return obj


def test_stargazer_default_instance_id():
    from apps.rpc.stargazer import Stargazer

    obj = Stargazer()
    assert obj.instance_id == "stargazer"
    assert obj.client.namespace == "stargazer"
    assert obj.health_check_client.namespace == "stargazer"


def test_stargazer_custom_instance_id():
    from apps.rpc.stargazer import Stargazer

    obj = Stargazer(instance_id="sg-2")
    assert obj.instance_id == "sg-2"
    assert obj.client.namespace == "sg-2"


def test_stargazer_list_regions(stargazer):
    stargazer.list_regions({"region": "cn"})
    assert _last(stargazer.client) == ("request", "list_regions", (), {"region": "cn"})


def test_stargazer_health_check_default_timeout(stargazer):
    stargazer.health_check()
    assert _last(stargazer.health_check_client) == (
        "run",
        "health_check",
        ({"execute_timeout": 5},),
        {"_timeout": 5},
    )


def test_stargazer_health_check_custom_timeout(stargazer):
    stargazer.health_check(timeout=20)
    assert _last(stargazer.health_check_client) == (
        "run",
        "health_check",
        ({"execute_timeout": 20},),
        {"_timeout": 20},
    )


def test_stargazer_collection_tool_debug_default_protocol(stargazer):
    stargazer.collection_tool_debug({"host": "h"}, timeout=10)
    # protocol 默认 snmp -> handler debug_snmp, nats_timeout = 10 + 5
    assert _last(stargazer.client) == (
        "request",
        "debug_snmp",
        (),
        {"_timeout": 15, "host": "h"},
    )


def test_stargazer_collection_tool_debug_ipmi(stargazer):
    stargazer.collection_tool_debug({"protocol": "ipmi", "host": "h"}, timeout=3)
    assert _last(stargazer.client) == (
        "request",
        "debug_ipmi",
        (),
        {"_timeout": 8, "protocol": "ipmi", "host": "h"},
    )


def test_stargazer_rpc_client_subclass_namespace():
    from apps.rpc.stargazer import StargazerRpcClient

    c = StargazerRpcClient("ns-x")
    assert c.namespace == "ns-x"
