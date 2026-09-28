"""新任务使用真实 ORM 和守门路径，仅在 VM HTTP 与 Celery 派发边界打桩。"""

from unittest import mock

import pytest
import requests

from apps.cmdb.constants.constants import CollectPluginTypes, CollectRunStatusType
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.tasks import celery_tasks as ct

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize("probe_result", ["data", "empty", "error", "running"])
def test_new_three_minute_task_uses_compat_probe_without_manual_sync(probe_result):
    task = CollectModels.objects.create(
        name="cold-start-three-minutes",
        task_type=CollectPluginTypes.SNMP,
        model_id="network",
        is_interval=True,
        cycle_value_type="cycle",
        cycle_value="3",
        params={"has_network_topo": False},
    )
    assert task.exec_status == CollectRunStatusType.NOT_START
    if probe_result == "running":
        task.exec_status = CollectRunStatusType.RUNNING
        task.save(update_fields=["exec_status"])
    initial_digest = task.collect_digest
    compat_queries = []

    def vm_response(url, *, data, timeout):
        query = data["query"]
        rows = []
        if "cmdb_round_complete_gauge" not in query:
            compat_queries.append(query)
            assert query == f"count by (instance_id) (last_over_time({{instance_id=~'^(cmdb_{task.id})$'}}[1h]))"
            assert timeout == 10
            if probe_result == "error":
                raise requests.ConnectionError("VM unavailable")
            if probe_result == "data":
                rows = [{"metric": {"instance_id": f"cmdb_{task.id}"}, "value": [300, "61"]}]
        response = mock.Mock(status_code=200)
        response.json.return_value = {"status": "success", "data": {"result": rows}}
        return response

    with mock.patch("apps.cmdb.collection.query_vm.requests.post", side_effect=vm_response) as post:
        with mock.patch.object(ct.sync_collect_task, "delay") as dispatch:
            result = ct.sync_collect_tasks_gate()

    assert result["scanned"] == 1
    assert result["vm_query_failed"] == int(probe_result == "error")
    assert len(compat_queries) == int(probe_result != "running")
    if probe_result == "data":
        assert result["dispatched"] == 1
        dispatch.assert_called_once_with(task.id, sync_snapshot_complete=False)
    else:
        assert result["dispatched"] == 0
        assert result["skipped"] == 1
        dispatch.assert_not_called()
    if probe_result == "running":
        post.assert_not_called()
    task.refresh_from_db()
    assert task.collect_digest == initial_digest
