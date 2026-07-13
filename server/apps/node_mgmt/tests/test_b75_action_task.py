"""action_task 任务真实行为测试：状态收敛、超时处理、汇总统计。

仅 mock celery.delay 边界（任务直接同步调用函数本体）。
断言真实 DB 状态变更与 result 结构。
"""
import pytest

from apps.node_mgmt.models.action import CollectorActionTask, CollectorActionTaskNode
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.models.sidecar import Collector, Node
from apps.node_mgmt.tasks import action_task as at


@pytest.fixture
def base_objs(db):
    region = CloudRegion.objects.create(name="cr-action")
    collector = Collector.objects.create(
        id="col-action",
        name="Telegraf",
        service_type="svc",
        node_operating_system="linux",
        executable_path="/bin/telegraf",
        execute_parameters="-c",
    )
    node = Node.objects.create(
        id="node-action",
        name="n1",
        ip="10.0.0.1",
        operating_system="linux",
        collector_configuration_directory="/etc",
        cloud_region=region,
    )
    return region, collector, node


# --------------------------------------------------------------------------- #
# _is_expected_status
# --------------------------------------------------------------------------- #
def test_is_expected_status_failed():
    assert at._is_expected_status("start", at.FAILED_STATUS) == "error"


def test_is_expected_status_start_running_success():
    assert at._is_expected_status("start", at.RUNNING_STATUS) == "success"
    assert at._is_expected_status("restart", at.RUNNING_STATUS) == "success"


def test_is_expected_status_stop_success():
    assert at._is_expected_status("stop", 3) == "success"
    assert at._is_expected_status("stop", 4) == "success"


def test_is_expected_status_running_default():
    assert at._is_expected_status("start", 99) == "running"


# --------------------------------------------------------------------------- #
# _extract_collector_message
# --------------------------------------------------------------------------- #
def test_extract_collector_message_from_dict_message():
    item = {"message": {"final_message": "done"}}
    assert at._extract_collector_message(item) == "done"


def test_extract_collector_message_from_str_message():
    assert at._extract_collector_message({"message": "ok"}) == "ok"


def test_extract_collector_message_falls_back_to_verbose():
    assert at._extract_collector_message({"verbose_message": "verbose"}) == "verbose"


def test_extract_collector_message_non_dict_returns_empty():
    assert at._extract_collector_message("not-a-dict") == ""
    assert at._extract_collector_message({}) == ""


# --------------------------------------------------------------------------- #
# _reconcile_collector_action_tasks
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_reconcile_marks_finished_and_counts(base_objs):
    region, collector, node = base_objs
    task = CollectorActionTask.objects.create(
        collector=collector, cloud_region=region, action="start", status="running", total_count=2
    )
    node2 = Node.objects.create(
        id="node-action-2", name="n2", ip="10.0.0.2", operating_system="linux",
        collector_configuration_directory="/etc", cloud_region=region,
    )
    CollectorActionTaskNode.objects.create(task=task, node=node, status="success", result={})
    CollectorActionTaskNode.objects.create(task=task, node=node2, status="error", result={})

    at._reconcile_collector_action_tasks({task.id})

    task.refresh_from_db()
    assert task.status == "finished"
    assert task.success_count == 1
    assert task.error_count == 1


@pytest.mark.django_db
def test_reconcile_marks_running_when_pending(base_objs):
    region, collector, node = base_objs
    task = CollectorActionTask.objects.create(
        collector=collector, cloud_region=region, action="stop", status="waiting", total_count=1
    )
    CollectorActionTaskNode.objects.create(task=task, node=node, status="running", result={})

    at._reconcile_collector_action_tasks({task.id})
    task.refresh_from_db()
    assert task.status == "running"


@pytest.mark.django_db
def test_reconcile_empty_ids_noop():
    # 不应抛异常
    at._reconcile_collector_action_tasks(set())


# --------------------------------------------------------------------------- #
# converge_collector_action_task_for_node
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_converge_node_missing_returns_none():
    assert at.converge_collector_action_task_for_node("no-such-node") is None


@pytest.mark.django_db
def test_converge_no_collectors_in_status_returns(base_objs):
    region, collector, node = base_objs
    node.status = {}
    node.save()
    assert at.converge_collector_action_task_for_node(node.id) is None


@pytest.mark.django_db
def test_converge_success_updates_task_node_and_task(base_objs):
    region, collector, node = base_objs
    # 节点上报采集器状态为 running（status=0），对应 start 操作 -> success
    node.status = {"collectors": [{"collector_id": collector.id, "status": 0, "message": "ok"}]}
    node.save()

    task = CollectorActionTask.objects.create(
        collector=collector, cloud_region=region, action="start", status="running", total_count=1
    )
    tn = CollectorActionTaskNode.objects.create(
        task=task,
        node=node,
        status="running",
        result={"steps": [{"action": "consume_ack", "status": "running", "message": "wait"}]},
    )

    at.converge_collector_action_task_for_node(node.id)

    tn.refresh_from_db()
    assert tn.status == "success"
    assert tn.result["overall_status"] == "success"
    task.refresh_from_db()
    assert task.status == "finished"
    assert task.success_count == 1


@pytest.mark.django_db
def test_converge_failed_collector_marks_error(base_objs):
    region, collector, node = base_objs
    node.status = {"collectors": [{"collector_id": collector.id, "status": at.FAILED_STATUS, "verbose_message": "crash"}]}
    node.save()

    task = CollectorActionTask.objects.create(
        collector=collector, cloud_region=region, action="start", status="running", total_count=1
    )
    tn = CollectorActionTaskNode.objects.create(
        task=task,
        node=node,
        status="running",
        result={"steps": [{"action": "consume_ack", "status": "running", "message": "wait"}]},
    )

    at.converge_collector_action_task_for_node(node.id)

    tn.refresh_from_db()
    assert tn.status == "error"
    assert tn.result["overall_status"] == "error"


@pytest.mark.django_db
def test_converge_running_status_unchanged(base_objs):
    region, collector, node = base_objs
    # status=99 -> running，不收敛
    node.status = {"collectors": [{"collector_id": collector.id, "status": 99}]}
    node.save()
    task = CollectorActionTask.objects.create(
        collector=collector, cloud_region=region, action="start", status="running", total_count=1
    )
    tn = CollectorActionTaskNode.objects.create(
        task=task, node=node, status="running",
        result={"steps": [{"action": "consume_ack", "status": "running", "message": "wait"}]},
    )
    at.converge_collector_action_task_for_node(node.id)
    tn.refresh_from_db()
    assert tn.status == "running"


# --------------------------------------------------------------------------- #
# timeout_collector_action_task
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_timeout_task_missing_returns_none():
    assert at.timeout_collector_action_task(999999) is None


@pytest.mark.django_db
def test_timeout_already_finished_noop(base_objs):
    region, collector, node = base_objs
    task = CollectorActionTask.objects.create(
        collector=collector, cloud_region=region, action="start", status="finished", total_count=1
    )
    # 不应改任何状态
    assert at.timeout_collector_action_task(task.id) is None
    task.refresh_from_db()
    assert task.status == "finished"


@pytest.mark.django_db
def test_timeout_marks_pending_nodes_error(base_objs):
    region, collector, node = base_objs
    task = CollectorActionTask.objects.create(
        collector=collector, cloud_region=region, action="start", status="running", total_count=1
    )
    tn = CollectorActionTaskNode.objects.create(
        task=task, node=node, status="running",
        result={"steps": [{"action": "consume_ack", "status": "running", "message": "wait"}]},
    )

    at.timeout_collector_action_task(task.id)

    tn.refresh_from_db()
    assert tn.status == "error"
    # 追加了 callback_or_timeout step
    actions = [s["action"] for s in tn.result["steps"]]
    assert "callback_or_timeout" in actions
    task.refresh_from_db()
    assert task.status == "finished"
    assert task.error_count == 1
