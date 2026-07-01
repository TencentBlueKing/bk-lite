"""rpc.ansible.AnsibleExecutor 转发契约与校验测试。

AnsibleExecutor 把 adhoc/playbook/task_query 转发到不同 namespace 的 RpcClient。
本测试替换三个 client 为记录器，断言：参数缺失校验抛错、request_data 组装、
默认值填充、task_id 自动生成、可选字段（stream_log_topic/execution_id）只在传入时加入。
不触达真实 NATS。
"""
import pydantic.root_model  # noqa

import pytest

from apps.rpc.ansible import AnsibleExecutor, AnsibleRpcClient

pytestmark = pytest.mark.unit


class _Recorder:
    def __init__(self):
        self.calls = []

    def run(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return {"accepted": True}


@pytest.fixture
def ex():
    e = AnsibleExecutor("server-1")
    e.adhoc_client = _Recorder()
    e.playbook_client = _Recorder()
    return e


def test_namespaces_构造():
    e = AnsibleExecutor("inst")
    assert e.instance_id == "inst"
    assert e.adhoc_client.namespace == "ansible.adhoc"
    assert e.playbook_client.namespace == "ansible.playbook"


def test_rpc_client_subclass_namespace():
    c = AnsibleRpcClient("ns")
    assert c.namespace == "ns"


# --------------------------- adhoc ---------------------------

def test_adhoc_缺少所有目标源抛错(ex):
    with pytest.raises(ValueError, match="inventory or inventory_content or host_credentials is required"):
        ex.adhoc()


def test_adhoc_仅host_credentials也可执行(ex):
    ex.adhoc(host_credentials=[{"host": "h"}])
    args, kwargs = ex.adhoc_client.calls[-1]
    assert args[0] == "server-1"
    assert kwargs == {"_timeout": 60}
    rd = args[1]
    assert rd["host_credentials"] == [{"host": "h"}]
    assert rd["execute_timeout"] == 60


def test_adhoc_默认值与task_id自动生成(ex):
    ex.adhoc(inventory="localhost,")
    rd = ex.adhoc_client.calls[-1][0][1]
    assert rd["hosts"] == "all"
    assert rd["module"] == "ping"
    assert rd["extra_vars"] == {}
    assert rd["callback"] == {}
    assert rd["task_id"] and len(rd["task_id"]) == 32
    assert "stream_log_topic" not in rd
    assert "execution_id" not in rd


def test_adhoc_显式task_id被保留(ex):
    ex.adhoc(inventory="localhost,", task_id="fixed-id")
    rd = ex.adhoc_client.calls[-1][0][1]
    assert rd["task_id"] == "fixed-id"


def test_adhoc_可选字段仅在传入时加入(ex):
    ex.adhoc(
        inventory_content="[t]\nh",
        stream_log_topic="log.topic",
        execution_id="exec-9",
        timeout=120,
    )
    args, kwargs = ex.adhoc_client.calls[-1]
    assert kwargs == {"_timeout": 120}
    rd = args[1]
    assert rd["stream_log_topic"] == "log.topic"
    assert rd["execution_id"] == "exec-9"
    assert rd["execute_timeout"] == 120


# --------------------------- playbook ---------------------------

def test_playbook_缺少playbook源抛错(ex):
    with pytest.raises(ValueError, match="playbook_path or playbook_content is required"):
        ex.playbook(inventory="localhost,")


def test_playbook_缺少目标源抛错(ex):
    with pytest.raises(ValueError, match="inventory or inventory_content or host_credentials is required"):
        ex.playbook(playbook_content="- hosts: all")


def test_playbook_file_distribution满足playbook源校验(ex):
    ex.playbook(file_distribution={"x": 1}, host_credentials=[{"host": "h"}])
    rd = ex.playbook_client.calls[-1][0][1]
    assert rd["file_distribution"] == {"x": 1}


def test_playbook_request_data组装与默认(ex):
    ex.playbook(playbook_content="- hosts: all", inventory_content="[t]\nh")
    args, kwargs = ex.playbook_client.calls[-1]
    assert args[0] == "server-1"
    assert kwargs == {"_timeout": 600}
    rd = args[1]
    assert rd["playbook_content"] == "- hosts: all"
    assert rd["inventory_content"] == "[t]\nh"
    assert rd["files"] == []
    assert rd["file_distribution"] == {}
    assert rd["extra_vars"] == {}
    assert rd["callback"] == {}
    assert rd["execute_timeout"] == 600
    assert len(rd["task_id"]) == 32


def test_playbook_显式task_id与timeout(ex):
    ex.playbook(
        playbook_path="/p.yml",
        inventory="localhost,",
        task_id="pb-1",
        timeout=300,
    )
    args, kwargs = ex.playbook_client.calls[-1]
    assert kwargs == {"_timeout": 300}
    rd = args[1]
    assert rd["task_id"] == "pb-1"
    assert rd["playbook_path"] == "/p.yml"


# --------------------------- task_query ---------------------------

def test_task_query_组装并转发(ex, monkeypatch):
    rec = _Recorder()

    def fake_client(namespace):
        rec.namespace = namespace
        return rec

    monkeypatch.setattr("apps.rpc.ansible.AnsibleRpcClient", fake_client)
    out = ex.task_query("t-123", timeout=15)
    assert out == {"accepted": True}
    assert rec.namespace == "ansible.task.query"
    args, kwargs = rec.calls[-1]
    assert args == ("server-1", {"task_id": "t-123"})
    assert kwargs == {"_timeout": 15}


def test_task_query_默认timeout(ex, monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr("apps.rpc.ansible.AnsibleRpcClient", lambda ns: rec)
    ex.task_query("t-1")
    assert ex  # 占位
    assert rec.calls[-1][1] == {"_timeout": 10}
