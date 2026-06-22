"""工作流执行结果三接口的跨租户越权(IDOR)回归测试。

锁定 `WorkFlowTaskResultViewSet` 的 execution_detail / execution_output_data /
node_execution_detail 必须经 team 作用域 get_queryset() 鉴权:他团队的 execution_id /
task_result id 一律 404,不得读到节点 input_data/output_data。

实现细节:用 superuser + current_team cookie 调用——superuser 可稳定通过 @HasPermission
角色闸,而本视图的 get_queryset() 对 superuser 同样按 current_team 过滤
(filter(bot_work_flow__bot__team__contains=[current_team])),因此跨租户隔离逻辑
(IDOR 修复的所在)被真实执行。
"""

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.opspilot.models import Bot, BotWorkFlow, WorkFlowTaskNodeResult, WorkFlowTaskResult
from apps.opspilot.viewsets.workflow_task_result_view import WorkFlowTaskResultViewSet

pytestmark = pytest.mark.django_db


def _make_superuser(team_id):
    from apps.base.models import User

    user = User.objects.create_user(
        username=f"idor_su_{team_id}",
        password="x",
        domain="domain.com",
        locale="en",
        group_list=[{"id": team_id, "name": f"T{team_id}"}],
        roles=["admin"],
    )
    user.is_superuser = True
    user.save()
    return user


def _setup_execution(team_id, execution_id):
    bot = Bot.objects.create(name=f"bot-{team_id}", team=[team_id], usage_team=[team_id])
    wf = BotWorkFlow.objects.create(bot=bot)
    task_result = WorkFlowTaskResult.objects.create(bot_work_flow=wf, execution_id=execution_id, status="completed", input_data="")
    node = WorkFlowTaskNodeResult.objects.create(
        task_result=task_result,
        execution_id=execution_id,
        node_id="n1",
        status="completed",
        input_data={"secret": team_id},
        output_data={"out": team_id},
    )
    return bot, task_result, node


def _call(action, user, current_team, params):
    factory = APIRequestFactory()
    request = factory.get("/", params)
    force_authenticate(request, user=user)
    request.COOKIES["current_team"] = str(current_team)
    view = WorkFlowTaskResultViewSet.as_view({"get": action})
    return view(request)


class TestWorkflowResultTenantIsolation:
    def test_node_execution_detail_cross_team_404(self):
        _setup_execution(1, "exec-team1")
        _setup_execution(2, "exec-team2")
        resp = _call("node_execution_detail", _make_superuser(1), 1, {"execution_id": "exec-team2", "node_id": "n1"})
        assert resp.status_code == 404

    def test_node_execution_detail_same_team_200(self):
        _setup_execution(1, "exec-team1")
        resp = _call("node_execution_detail", _make_superuser(1), 1, {"execution_id": "exec-team1", "node_id": "n1"})
        assert resp.status_code == 200
        assert resp.data["input_params"] == {"secret": 1}
        assert resp.data["output_params"] == {"out": 1}

    def test_execution_detail_cross_team_404(self):
        _setup_execution(1, "exec-team1")
        _setup_execution(2, "exec-team2")
        resp = _call("execution_detail", _make_superuser(1), 1, {"execution_id": "exec-team2"})
        assert resp.status_code == 404

    def test_execution_detail_same_team_200(self):
        _setup_execution(1, "exec-team1")
        resp = _call("execution_detail", _make_superuser(1), 1, {"execution_id": "exec-team1"})
        assert resp.status_code == 200
        assert any(n["node_id"] == "n1" for n in resp.data)

    def test_execution_output_data_cross_team_404(self):
        _setup_execution(1, "exec-team1")
        _setup_execution(2, "exec-team2")
        resp = _call("execution_output_data", _make_superuser(1), 1, {"execution_id": "exec-team2"})
        assert resp.status_code == 404

    def test_execution_output_data_via_task_result_id_cross_team_404(self):
        _setup_execution(1, "exec-team1")
        _, tr2, _ = _setup_execution(2, "exec-team2")
        # 用他团队的 task_result id 也必须被 team 作用域挡住
        resp = _call("execution_output_data", _make_superuser(1), 1, {"id": tr2.id})
        assert resp.status_code == 404

    def test_node_execution_detail_missing_node_id_400(self):
        _setup_execution(1, "exec-team1")
        resp = _call("node_execution_detail", _make_superuser(1), 1, {"execution_id": "exec-team1"})
        assert resp.status_code == 400
