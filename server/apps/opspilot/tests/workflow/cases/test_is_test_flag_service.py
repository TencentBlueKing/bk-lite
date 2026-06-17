"""WorkFlowTaskResult.is_test 标识的行为测试。

背景：配置页此前无法区分一次执行是「配置页测试发起」还是「真实对话发起」，
导致真实对话运行时也被配置页恢复展示（bot 详情接口回填了正在运行的 execution_id）。
新增 ``WorkFlowTaskResult.is_test`` 标识后：

- 引擎创建执行主记录时按 ``engine.is_test`` 落库（测试任务置 True，真实对话默认 False）。
- bot 详情接口仅恢复 ``is_test=True`` 的运行中执行（见 ``BotViewSet.retrieve``）。

这些测试在持久化层钉住上述语义，不触发真实 LLM / 网络。
"""

import pytest

from apps.opspilot.enum import WorkFlowTaskStatus
from apps.opspilot.models.bot_mgmt import WorkFlowTaskResult
from apps.opspilot.utils.chat_flow_utils.engine.factory import create_chat_flow_engine

pytestmark = pytest.mark.django_db


def test_engine_marks_test_execution(bot_workflow):
    """engine.is_test=True 时，创建的执行主记录 is_test 落库为 True，execute_type 仍为入口节点类型。"""
    engine = create_chat_flow_engine(bot_workflow, "entry_node", entry_type="openai")
    engine.is_test = True

    task_result = engine._ensure_execution_result_started({"last_message": "hi"}, "openai")

    assert task_result.is_test is True
    assert task_result.execute_type == "openai"
    # 复查数据库落库结果
    assert WorkFlowTaskResult.objects.get(execution_id=engine.execution_id).is_test is True


def test_engine_real_execution_not_marked(bot_workflow):
    """默认（真实对话）执行不标记 is_test。"""
    engine = create_chat_flow_engine(bot_workflow, "entry_node", entry_type="openai")

    task_result = engine._ensure_execution_result_started({"last_message": "hi"}, "openai")

    assert task_result.is_test is False


def test_config_page_restore_selects_only_test_execution(bot_workflow):
    """配置页恢复语义：同时存在运行中的真实对话与测试执行时，仅恢复测试执行。

    这里复刻 ``BotViewSet.retrieve`` 用于回填 ``execution_id`` 的查询，
    防止真实对话执行被配置页画布展示。
    """
    # 运行中的真实对话执行（不应被配置页恢复）
    WorkFlowTaskResult.objects.create(
        bot_work_flow=bot_workflow,
        execution_id="real-conversation-exec",
        status=WorkFlowTaskStatus.RUNNING,
        input_data="{}",
        output_data={},
        is_test=False,
    )
    # 运行中的测试执行（应被配置页恢复）
    WorkFlowTaskResult.objects.create(
        bot_work_flow=bot_workflow,
        execution_id="test-exec",
        status=WorkFlowTaskStatus.RUNNING,
        input_data="{}",
        output_data={},
        is_test=True,
    )

    restored = (
        WorkFlowTaskResult.objects.filter(
            bot_work_flow__bot_id=bot_workflow.bot_id,
            status=WorkFlowTaskStatus.RUNNING,
            finished_at__isnull=True,
            is_test=True,
        )
        .order_by("-run_time", "-id")
        .values_list("execution_id", flat=True)
        .first()
    )

    assert restored == "test-exec"
