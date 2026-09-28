"""只读回放真实冷启动故障时刻；不写 VM，也不触发采集或同步。

设置 CMDB_VM_REPLAY_URL（完整 query 端点）、CMDB_VM_REPLAY_INSTANCE_ID 和
CMDB_VM_REPLAY_TIME（已确认存在原始样本、但旧探测漏检的 Unix 时间戳）后运行。
历史数据过期后应重新选取故障样本，不能用 mock 替代 VM 的查询语义。
"""

import json
import os
import re
from unittest import mock

import pytest
import requests

from apps.cmdb.collection.query_vm import Collection
from apps.cmdb.collection.round_sync import query_instance_ids_with_vm_data
from apps.cmdb.constants.constants import CollectPluginTypes
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.tasks import celery_tasks as ct

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.getenv("CMDB_VM_REPLAY_URL"), reason="需要显式指定真实 VM 历史回放环境"),
]


def test_compat_probe_detects_real_cold_start_samples():
    url = os.environ["CMDB_VM_REPLAY_URL"]
    instance_id = os.environ["CMDB_VM_REPLAY_INSTANCE_ID"]
    evaluation_time = float(os.environ["CMDB_VM_REPLAY_TIME"])

    class HistoricalCollection(Collection):
        def __init__(self):
            self.url = url

        def _execute_query(self, query, **kwargs):
            kwargs["evaluation_time"] = evaluation_time
            return super()._execute_query(query, **kwargs)

    # 直接数原始样本，独立确认这确实是有数据的冷启动现场。
    response = requests.post(
        url,
        data={
            "query": f"count_over_time({{instance_id={json.dumps(instance_id)}}}[1h])",
            "time": evaluation_time,
            "nocache": "1",
        },
        timeout=10,
    )
    response.raise_for_status()
    rows = response.json()["data"]["result"]
    assert rows and any(float(row["value"][1]) > 0 for row in rows), "回放前置条件：该历史窗口必须存在原始样本"
    assert query_instance_ids_with_vm_data([instance_id], collection=HistoricalCollection()) == {instance_id}


@pytest.mark.django_db
def test_real_vm_samples_drive_new_task_gate_across_scans(monkeypatch):
    """真实 VM + 测试数据库运行守门，队列边界只记录派发意图。"""
    url = os.environ["CMDB_VM_REPLAY_URL"]
    instance_id = os.environ["CMDB_VM_REPLAY_INSTANCE_ID"]
    matched = re.fullmatch(r"cmdb_(\d+)", instance_id)
    assert matched, "回放任务必须使用 cmdb_<task_id> 形式的 instance_id"
    task = CollectModels.objects.create(
        id=int(matched.group(1)),
        name="cold-start-history-replay",
        task_type=CollectPluginTypes.SNMP,
        model_id="network",
        is_interval=True,
        cycle_value_type="cycle",
        cycle_value="3",
        params={"has_network_topo": False},
    )
    initial_digest = task.collect_digest
    original_execute = Collection._execute_query
    first_evaluation = float(os.environ["CMDB_VM_REPLAY_TIME"])
    for offset in (0, 300, 600):
        evaluation_time = first_evaluation + offset

        def execute_at_history(self, query, **kwargs):
            self.url = url
            kwargs["evaluation_time"] = evaluation_time
            return original_execute(self, query, **kwargs)

        monkeypatch.setattr(Collection, "_execute_query", execute_at_history)
        # 查询和守门判断均走真实代码；测试不得向环境的 Celery 队列发送任务。
        with mock.patch.object(ct.sync_collect_task, "delay") as dispatched:
            result = ct.sync_collect_tasks_gate()
        assert result["vm_query_failed"] == 0
        assert result["dispatched"] == 1
        dispatched.assert_called_once_with(task.id, sync_snapshot_complete=False)
    task.refresh_from_db()
    assert task.collect_digest == initial_digest
