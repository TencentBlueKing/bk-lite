"""使用真实 Celery 路由器与内存 broker 检查投递结果，不执行业务函数。"""

import pytest
from celery import Celery

from apps.core.celery_runtime.routing import TASK_ROUTES, configure_routes

pytestmark = pytest.mark.unit


@pytest.fixture
def routing_app():
    app = Celery("routing_test", broker="memory://", set_as_current=False)
    configure_routes(app)
    yield app
    app.close()


@pytest.mark.parametrize(
    "name,queue",
    [
        ("apps.monitor.tasks.monitor_policy.scan_policy_task", "critical"),
        ("apps.node_mgmt.tasks.action_task.converge_collector_action_task_for_node", "state"),
        ("apps.alerts.tasks.tasks.sync_notify", "notification"),
        ("apps.cmdb.tasks.celery_tasks.reconcile_instance_auto_association_task", "background"),
        ("apps.future.tasks.new_task", "celery"),
    ],
)
def test_apply_async_reaches_expected_queue_without_changing_arguments(routing_app, name, queue):
    def unchanged(value):
        return value

    task = routing_app.task(name=name, shared=False)(unchanged)
    task.apply_async(args=["unchanged"])
    with routing_app.connection_for_read() as connection:
        message = connection.SimpleQueue(queue).get(block=False)
        assert message.headers["task"] == name
        assert message.payload[0] == ["unchanged"]
        message.ack()


def test_explicit_beat_queue_override_remains_visible(routing_app):
    name = "apps.monitor.tasks.monitor_policy.scan_policy_task"
    route = routing_app.amqp.router.route({"queue": "celery"}, name)
    assert route["queue"].name == "celery"


def test_django_component_wires_routes_and_does_not_activate_child_recycling(monkeypatch):
    import runpy

    monkeypatch.setenv("ENABLE_CELERY", "true")
    component = runpy.run_module("config.components.celery", init_globals={"INSTALLED_APPS": ()})
    app = Celery("component_test", broker="memory://", set_as_current=False, fixups=[])
    app.config_from_object(component, namespace="CELERY")
    name = "apps.monitor.tasks.monitor_policy.scan_policy_task"
    assert app.amqp.router.route({}, name)["queue"].name == "critical"
    assert app.conf.worker_max_tasks_per_child == 200
    assert app.conf.worker_max_memory_per_child == 512000
    assert app.conf.worker_pool == "prefork"
    assert app.conf.worker_prefetch_multiplier == 1
    app.close()


def test_static_manifest_covers_local_decorated_tasks_without_importing_them():
    from apps.core.tests.celery_task_inventory import collect_tasks

    definitions = collect_tasks()
    assert set(definitions) == set(TASK_ROUTES), "新增/删除任务需审核准确注册名称与资源分类"
    for name, item in definitions.items():
        if item["declared_queue"]:
            assert TASK_ROUTES[name] == item["declared_queue"]
