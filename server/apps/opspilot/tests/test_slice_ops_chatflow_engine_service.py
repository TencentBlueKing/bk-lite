"""ops-tasks-engine 切片: ChatFlowEngine 同步执行引擎真实测试。

聚焦可测的真实编排与 DB 副作用，跳过纯 LLM 流式（sse_execute / agui）节点：
- 构造/解析（节点、边、入口节点、拓扑、node_map）
- validate_flow（空流程/无入口/循环依赖/不支持类型/全合法）
- _determine_entry_type / _get_execute_type
- set_start_node_variable 入口映射 + 节点明细落库
- _execute_prerequisite_nodes 串行执行 + 失败抛出与 TaskResult 落库
- execute() 全链路：成功（自定义节点执行器，非 LLM）、业务失败、无起始节点、
  异常路径；断言返回值、WorkFlowTaskResult/WorkFlowTaskNodeResult/对话历史 DB 副作用
- _record_execution_result / _record_conversation_history（含 celery 跳过、INTERRUPTED 不覆盖）
- _build_execution_output_data 汇总统计

真实外部边界：节点执行器用 register 注册的纯 Python 执行器（无 LLM/RAG/网络）。
DB 使用真实 Postgres。
"""

import pydantic.root_model  # noqa  预热

import pytest

from apps.opspilot.enum import WorkFlowExecuteType, WorkFlowTaskStatus
from apps.opspilot.models import Bot, BotWorkFlow
from apps.opspilot.models.bot_mgmt import (
    WorkFlowConversationHistory,
    WorkFlowTaskNodeResult,
    WorkFlowTaskResult,
)
from apps.opspilot.utils.chat_flow_utils.engine.core.base_executor import BaseNodeExecutor
from apps.opspilot.utils.chat_flow_utils.engine.core.enums import NodeStatus
from apps.opspilot.utils.chat_flow_utils.engine.core.models import NodeExecutionContext
from apps.opspilot.utils.chat_flow_utils.engine.engine import ChatFlowEngine
from apps.opspilot.utils.chat_flow_utils.engine.node_registry import node_registry

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# 测试用真实节点执行器（纯 Python，无 LLM/网络）。通过 node_registry 注册，
# 引擎按 node_type 解析后真实调用其 execute。
# ---------------------------------------------------------------------------
class _EchoExecutor(BaseNodeExecutor):
    """把 inputParams 的值原样回写到 outputParams（默认 last_message）。"""

    def execute(self, node_id, node_config, input_data):
        cfg = node_config.get("data", {}).get("config", {})
        in_key = cfg.get("inputParams", "last_message")
        out_key = cfg.get("outputParams", "last_message")
        suffix = cfg.get("suffix", "")
        return {out_key: f"{input_data.get(in_key, '')}{suffix}"}


class _BizFailExecutor(BaseNodeExecutor):
    """以 in-band {'success': False} 表达业务失败。"""

    def execute(self, node_id, node_config, input_data):
        return {"success": False, "error": "业务校验未通过"}


class _RaiseExecutor(BaseNodeExecutor):
    """抛出异常，触发节点执行 except 分支。"""

    def execute(self, node_id, node_config, input_data):
        raise RuntimeError("执行器炸了")


@pytest.fixture(autouse=True)
def _register_test_executors():
    """注册测试执行器到 node_registry，测试结束后清理，避免污染其它用例。"""
    node_registry.register_node_class("echo_test", _EchoExecutor)
    node_registry.register_node_class("bizfail_test", _BizFailExecutor)
    node_registry.register_node_class("raise_test", _RaiseExecutor)
    yield
    for t in ("echo_test", "bizfail_test", "raise_test"):
        node_registry._node_classes.pop(t, None)


@pytest.fixture
def bot():
    return Bot.objects.create(name="engine-bot", team=[1], usage_team=[1], online=True)


def _make_workflow(bot, nodes, edges=None):
    return BotWorkFlow.objects.create(bot=bot, flow_json={"nodes": nodes, "edges": edges or []})


def _node(node_id, node_type, config=None, label=None):
    data = {"config": config or {}}
    if label:
        data["label"] = label
    return {"id": node_id, "type": node_type, "data": data}


# ===========================================================================
# 构造 / 解析
# ===========================================================================
class TestEngineConstruction:
    def test_解析节点边入口与拓扑(self, bot):
        wf = _make_workflow(
            bot,
            nodes=[_node("a", "restful"), _node("b", "echo_test"), _node("c", "exit")],
            edges=[{"source": "a", "target": "b"}, {"source": "b", "target": "c"}],
        )
        engine = ChatFlowEngine(wf)
        assert [n["id"] for n in engine.nodes] == ["a", "b", "c"]
        assert len(engine.edges) == 2
        # 入口节点 = 无入边的节点
        assert engine.entry_nodes == ["a"]
        # node_map O(1) 查找
        assert engine._get_node_by_id("b")["type"] == "echo_test"
        assert engine._get_node_by_id("missing") is None
        # 默认入口类型 openai
        assert engine.entry_type == WorkFlowExecuteType.OPENAI
        # execution_id 自动生成
        assert engine.execution_id

    def test_显式execution_id与entry_type透传(self, bot):
        wf = _make_workflow(bot, nodes=[_node("a", "restful")])
        engine = ChatFlowEngine(wf, entry_type="restful", execution_id="exec-xyz")
        assert engine.execution_id == "exec-xyz"
        assert engine.entry_type == "restful"


# ===========================================================================
# validate_flow
# ===========================================================================
class TestValidateFlow:
    def test_空流程报错(self, bot):
        wf = _make_workflow(bot, nodes=[])
        errors = ChatFlowEngine(wf).validate_flow()
        assert errors == ["流程中没有节点"]

    def test_循环依赖被检出(self, bot):
        wf = _make_workflow(
            bot,
            nodes=[_node("a", "restful"), _node("b", "echo_test")],
            edges=[{"source": "a", "target": "b"}, {"source": "b", "target": "a"}],
        )
        errors = ChatFlowEngine(wf).validate_flow()
        # 无入口节点 + 循环依赖都应被报出
        assert "流程中没有入口节点" in errors
        assert "流程存在循环依赖" in errors

    def test_不支持的节点类型(self, bot):
        wf = _make_workflow(bot, nodes=[_node("a", "restful"), _node("x", "no_such_type")])
        errors = ChatFlowEngine(wf).validate_flow()
        assert any("不支持的节点类型: no_such_type" in e for e in errors)

    def test_全合法无错误(self, bot):
        wf = _make_workflow(
            bot,
            nodes=[_node("a", "restful"), _node("b", "echo_test")],
            edges=[{"source": "a", "target": "b"}],
        )
        assert ChatFlowEngine(wf).validate_flow() == []


# ===========================================================================
# entry_type / execute_type 推导
# ===========================================================================
class TestEntryType:
    def test_determine_entry_type_合法类型(self, bot):
        wf = _make_workflow(bot, nodes=[_node("a", "openai")])
        engine = ChatFlowEngine(wf)
        assert engine._determine_entry_type(engine.nodes[0]) == "openai"

    def test_determine_entry_type_非入口类型回退restful(self, bot):
        wf = _make_workflow(bot, nodes=[_node("a", "echo_test")])
        engine = ChatFlowEngine(wf)
        assert engine._determine_entry_type(engine.nodes[0]) == "restful"

    def test_determine_entry_type_无节点回退restful(self, bot):
        wf = _make_workflow(bot, nodes=[_node("a", "restful")])
        engine = ChatFlowEngine(wf)
        assert engine._determine_entry_type(None) == "restful"

    def test_get_execute_type_使用entry_type(self, bot):
        wf = _make_workflow(bot, nodes=[_node("a", "restful")])
        engine = ChatFlowEngine(wf, entry_type="restful")
        assert engine._get_execute_type() == "restful"

    def test_get_execute_type_非法回退openai(self, bot):
        wf = _make_workflow(bot, nodes=[_node("a", "restful")])
        engine = ChatFlowEngine(wf, entry_type="not_a_type")
        assert engine._get_execute_type() == WorkFlowExecuteType.OPENAI


# ===========================================================================
# set_start_node_variable：入口映射 + 节点明细落库
# ===========================================================================
class TestSetStartNodeVariable:
    def test_映射outputParams并落库节点明细(self, bot):
        wf = _make_workflow(
            bot,
            nodes=[_node("entry", "agui", {"inputParams": "last_message", "outputParams": "agui_msg"}, label="入口")],
        )
        engine = ChatFlowEngine(wf, execution_id="exec-map")
        out = engine.set_start_node_variable({"last_message": "你好"}, engine.nodes[0])
        assert out == {"agui_msg": "你好"}
        # 节点明细落库且为 completed
        nr = WorkFlowTaskNodeResult.objects.get(execution_id="exec-map", node_id="entry")
        assert nr.status == NodeStatus.COMPLETED.value
        assert nr.node_name == "入口"
        assert nr.output_data == {"agui_msg": "你好"}
        # 执行顺序计数从 1 开始
        assert nr.node_index == 1


# ===========================================================================
# _execute_prerequisite_nodes：串行执行 + 失败抛出 + TaskResult 落库
# ===========================================================================
class TestExecutePrerequisiteNodes:
    def test_串行执行更新输入(self, bot):
        wf = _make_workflow(
            bot,
            nodes=[
                _node("p1", "echo_test", {"inputParams": "last_message", "outputParams": "step1", "suffix": "-A"}),
                _node("p2", "echo_test", {"inputParams": "step1", "outputParams": "step2", "suffix": "-B"}),
            ],
        )
        engine = ChatFlowEngine(wf, execution_id="exec-pre")
        result = engine._execute_prerequisite_nodes(engine.nodes, {"last_message": "x"})
        assert result["step1"] == "x-A"
        assert result["step2"] == "x-A-B"
        # 两个前置节点明细落库
        assert WorkFlowTaskNodeResult.objects.filter(execution_id="exec-pre").count() == 2

    def test_空前置节点直接返回输入(self, bot):
        wf = _make_workflow(bot, nodes=[_node("a", "restful")])
        engine = ChatFlowEngine(wf)
        data = {"last_message": "x"}
        assert engine._execute_prerequisite_nodes([], data) is data

    def test_前置节点异常抛出并记录失败结果(self, bot):
        wf = _make_workflow(bot, nodes=[_node("boom", "raise_test")])
        engine = ChatFlowEngine(wf, execution_id="exec-pre-fail")
        with pytest.raises(RuntimeError):
            engine._execute_prerequisite_nodes(engine.nodes, {"last_message": "x"})
        # 失败结果落库为 FAIL
        tr = WorkFlowTaskResult.objects.get(execution_id="exec-pre-fail")
        assert tr.status == WorkFlowTaskStatus.FAIL
        # 节点明细记录为 failed
        nr = WorkFlowTaskNodeResult.objects.get(execution_id="exec-pre-fail", node_id="boom")
        assert nr.status == NodeStatus.FAILED.value
        assert "执行器炸了" in nr.error_message


# ===========================================================================
# execute() 全链路
# ===========================================================================
class TestExecuteFullChain:
    def test_单节点成功返回last_message并落库成功(self, bot):
        wf = _make_workflow(
            bot,
            nodes=[_node("only", "echo_test", {"inputParams": "last_message", "outputParams": "last_message", "suffix": "!!"})],
        )
        engine = ChatFlowEngine(wf, start_node_id="only", entry_type="restful", execution_id="exec-ok")
        result = engine.execute({"last_message": "hi", "user_id": "u1", "session_id": "s1"})
        assert result == "hi!!"
        tr = WorkFlowTaskResult.objects.get(execution_id="exec-ok")
        assert tr.status == WorkFlowTaskStatus.SUCCESS
        assert tr.last_output == "hi!!"
        assert tr.execute_type == "restful"
        # 用户输入 + bot 输出两条对话历史
        roles = set(
            WorkFlowConversationHistory.objects.filter(execution_id="exec-ok").values_list("conversation_role", flat=True)
        )
        assert roles == {"user", "bot"}

    def test_两节点链路传递(self, bot):
        wf = _make_workflow(
            bot,
            nodes=[
                _node("n1", "echo_test", {"inputParams": "last_message", "outputParams": "last_message", "suffix": "-1"}),
                _node("n2", "echo_test", {"inputParams": "last_message", "outputParams": "last_message", "suffix": "-2"}),
            ],
            edges=[{"source": "n1", "target": "n2"}],
        )
        engine = ChatFlowEngine(wf, start_node_id="n1", entry_type="restful", execution_id="exec-chain")
        result = engine.execute({"last_message": "v", "user_id": "u"})
        assert result == "v-1-2"
        # 两节点都落库
        assert WorkFlowTaskNodeResult.objects.filter(execution_id="exec-chain").count() == 2

    def test_业务失败返回错误并记录FAIL(self, bot):
        wf = _make_workflow(bot, nodes=[_node("bad", "bizfail_test")])
        engine = ChatFlowEngine(wf, start_node_id="bad", entry_type="restful", execution_id="exec-biz")
        result = engine.execute({"last_message": "x", "user_id": "u"})
        # 业务失败节点把 in-band 结果存入 output_data，execute() 直接回传该 output_data
        assert result["success"] is False
        assert result["error"] == "业务校验未通过"
        tr = WorkFlowTaskResult.objects.get(execution_id="exec-biz")
        assert tr.status == WorkFlowTaskStatus.FAIL
        # 节点明细记录为 failed
        nr = WorkFlowTaskNodeResult.objects.get(execution_id="exec-biz", node_id="bad")
        assert nr.status == NodeStatus.FAILED.value

    def test_异常节点返回error并记录FAIL(self, bot):
        wf = _make_workflow(bot, nodes=[_node("boom", "raise_test")])
        engine = ChatFlowEngine(wf, start_node_id="boom", entry_type="restful", execution_id="exec-exc")
        result = engine.execute({"last_message": "x", "user_id": "u"})
        assert result["failed_node_id"] == "boom"
        assert "执行器炸了" in result["error"]
        tr = WorkFlowTaskResult.objects.get(execution_id="exec-exc")
        assert tr.status == WorkFlowTaskStatus.FAIL

    def test_验证失败短路不落库(self, bot):
        wf = _make_workflow(bot, nodes=[_node("x", "no_such_type")])
        engine = ChatFlowEngine(wf, execution_id="exec-invalid")
        result = engine.execute({"last_message": "x"})
        assert result["success"] is False
        assert "流程验证失败" in result["error"]
        # 验证失败在创建 TaskResult 之前短路
        assert not WorkFlowTaskResult.objects.filter(execution_id="exec-invalid").exists()

    def test_起始节点不存在记录失败(self, bot):
        wf = _make_workflow(bot, nodes=[_node("a", "restful")])
        engine = ChatFlowEngine(wf, start_node_id="ghost", entry_type="restful", execution_id="exec-nostart")
        result = engine.execute({"last_message": "x"})
        assert result["success"] is False
        assert "指定的起始节点不存在" in result["error"]
        tr = WorkFlowTaskResult.objects.get(execution_id="exec-nostart")
        assert tr.status == WorkFlowTaskStatus.FAIL


# ===========================================================================
# _record_execution_result / _record_conversation_history
# ===========================================================================
class TestRecording:
    def test_record_execution_result_创建并复用TaskResult(self, bot):
        wf = _make_workflow(bot, nodes=[_node("a", "restful")])
        engine = ChatFlowEngine(wf, entry_type="restful", execution_id="exec-rec")
        engine._record_execution_result({"last_message": "in"}, "out-text", True)
        tr = WorkFlowTaskResult.objects.get(execution_id="exec-rec")
        assert tr.status == WorkFlowTaskStatus.SUCCESS
        assert tr.last_output == "out-text"
        # 再次记录复用同一行（不重复创建）
        engine._record_execution_result({"last_message": "in"}, {"k": "v"}, False)
        assert WorkFlowTaskResult.objects.filter(execution_id="exec-rec").count() == 1
        tr.refresh_from_db()
        assert tr.status == WorkFlowTaskStatus.FAIL

    def test_interrupted结果不被非中断结果覆盖(self, bot):
        wf = _make_workflow(bot, nodes=[_node("a", "restful")])
        engine = ChatFlowEngine(wf, entry_type="restful", execution_id="exec-int")
        engine._record_execution_result({}, {"interrupted": True, "error": "stop"}, False)
        tr = WorkFlowTaskResult.objects.get(execution_id="exec-int")
        assert tr.status == WorkFlowTaskStatus.INTERRUPTED
        # 后续成功结果不应覆盖中断状态
        engine._record_execution_result({}, "later", True)
        tr.refresh_from_db()
        assert tr.status == WorkFlowTaskStatus.INTERRUPTED

    def test_对话历史celery入口被跳过(self, bot):
        wf = _make_workflow(bot, nodes=[_node("a", "restful")])
        engine = ChatFlowEngine(wf)
        engine._record_conversation_history("u1", "msg", "user", "celery")
        assert not WorkFlowConversationHistory.objects.filter(user_id="u1").exists()

    def test_对话历史缺user或message跳过(self, bot):
        wf = _make_workflow(bot, nodes=[_node("a", "restful")])
        engine = ChatFlowEngine(wf)
        engine._record_conversation_history("", "msg", "user", "restful")
        engine._record_conversation_history("u1", "", "user", "restful")
        assert WorkFlowConversationHistory.objects.count() == 0

    def test_对话历史dict消息序列化为json(self, bot):
        wf = _make_workflow(bot, nodes=[_node("a", "restful")])
        engine = ChatFlowEngine(wf, execution_id="exec-hist")
        engine._record_conversation_history("u1", {"a": 1}, "bot", "restful", node_id="n", session_id="s")
        h = WorkFlowConversationHistory.objects.get(user_id="u1")
        assert h.conversation_content == '{"a": 1}'
        assert h.bot_id == bot.id
        assert h.entry_type == "restful"


# ===========================================================================
# _build_execution_output_data 汇总
# ===========================================================================
class TestBuildExecutionOutputData:
    def test_统计完成失败与最终失败节点(self, bot):
        wf = _make_workflow(bot, nodes=[_node("a", "restful"), _node("b", "echo_test")])
        engine = ChatFlowEngine(wf)
        # 构造两个执行上下文：a 完成，b 失败
        ctx_a = NodeExecutionContext(node_id="a", flow_id=str(wf.id))
        ctx_a.status = NodeStatus.COMPLETED
        ctx_b = NodeExecutionContext(node_id="b", flow_id=str(wf.id))
        ctx_b.status = NodeStatus.FAILED
        ctx_b.error_message = "boom"
        engine.execution_contexts = {"a": ctx_a, "b": ctx_b}
        engine.variable_manager.set_variable("node_a_index", 1)
        engine.variable_manager.set_variable("node_b_index", 2)
        engine.variable_manager.set_variable("node_b_type", "echo_test")
        engine.variable_manager.set_variable("node_b_name", "节点B")

        summary = engine._build_execution_output_data()["summary"]
        assert summary["total_nodes"] == 2
        assert summary["completed_nodes"] == 1
        assert summary["failed_nodes"] == 1
        # 最终节点取 index 最大者 b
        assert summary["final_node"]["node_id"] == "b"
        assert summary["failed_node"]["node_id"] == "b"
        assert summary["failed_node"]["error"] == "boom"

    def test_无失败节点failed_node为None(self, bot):
        wf = _make_workflow(bot, nodes=[_node("a", "restful")])
        engine = ChatFlowEngine(wf)
        ctx = NodeExecutionContext(node_id="a", flow_id=str(wf.id))
        ctx.status = NodeStatus.COMPLETED
        engine.execution_contexts = {"a": ctx}
        engine.variable_manager.set_variable("node_a_index", 1)
        summary = engine._build_execution_output_data()["summary"]
        assert summary["failed_node"] is None
        assert summary["completed_nodes"] == 1


# ===========================================================================
# _get_start_node / _record_node_execution_result / _summarize_execution_contexts
# ===========================================================================
class TestStartNodeAndRecording:
    def test_get_start_node_显式id优先(self, bot):
        wf = _make_workflow(bot, nodes=[_node("a", "restful"), _node("b", "echo_test")])
        engine = ChatFlowEngine(wf, start_node_id="b")
        assert engine._get_start_node()["id"] == "b"

    def test_get_start_node_无id取首个(self, bot):
        wf = _make_workflow(bot, nodes=[_node("a", "restful"), _node("b", "echo_test")])
        engine = ChatFlowEngine(wf)
        assert engine._get_start_node()["id"] == "a"

    def test_get_start_node_空流程返回None(self, bot):
        wf = _make_workflow(bot, nodes=[])
        assert ChatFlowEngine(wf)._get_start_node() is None

    def test_record_node_execution_result_幂等upsert(self, bot):
        wf = _make_workflow(bot, nodes=[_node("a", "restful")])
        engine = ChatFlowEngine(wf, execution_id="exec-node")
        engine.variable_manager.set_variable("node_a_index", 1)
        engine.variable_manager.set_variable("node_a_type", "restful")
        engine.variable_manager.set_variable("node_a_name", "入口A")
        ctx = NodeExecutionContext(node_id="a", flow_id=str(wf.id))
        ctx.status = NodeStatus.RUNNING
        ctx.start_time = 1000.0
        engine._record_node_execution_result("a", ctx)
        # 再次记录同 (execution_id, node_id) 更新而非新增
        ctx.status = NodeStatus.COMPLETED
        ctx.end_time = 1001.5
        engine._record_node_execution_result("a", ctx)
        rows = WorkFlowTaskNodeResult.objects.filter(execution_id="exec-node", node_id="a")
        assert rows.count() == 1
        nr = rows.get()
        assert nr.status == NodeStatus.COMPLETED.value
        assert nr.node_name == "入口A"
        assert nr.duration_ms == 1500

    def test_record_node_空node_id跳过(self, bot):
        wf = _make_workflow(bot, nodes=[_node("a", "restful")])
        engine = ChatFlowEngine(wf, execution_id="exec-skip")
        engine._record_node_execution_result("", NodeExecutionContext(node_id=""))
        assert WorkFlowTaskNodeResult.objects.filter(execution_id="exec-skip").count() == 0

    def test_summarize_execution_contexts_仅保留键名脱敏(self, bot):
        wf = _make_workflow(bot, nodes=[_node("a", "restful")])
        engine = ChatFlowEngine(wf)
        ctx = NodeExecutionContext(node_id="a", flow_id=str(wf.id))
        ctx.status = NodeStatus.COMPLETED
        ctx.input_data = {"prompt": "敏感提示词", "user_id": "u"}
        ctx.output_data = {"last_message": "敏感回复"}
        engine.execution_contexts = {"a": ctx}
        summary = engine._summarize_execution_contexts()
        # 只保留键名，绝不回显敏感值
        assert summary["a"]["input_keys"] == ["prompt", "user_id"]
        assert summary["a"]["output_keys"] == ["last_message"]
        assert "敏感提示词" not in str(summary)
        assert "敏感回复" not in str(summary)
        assert summary["a"]["status"] == "completed"


# ===========================================================================
# execute() 中断路径
# ===========================================================================
class TestExecuteInterrupt:
    def test_启动前已请求中断记录INTERRUPTED(self, bot, mocker):
        # 中断检查是缓存/DB 边界，直接在引擎导入处打桩为“已请求中断”
        import apps.opspilot.utils.chat_flow_utils.engine.engine as engine_mod

        mocker.patch.object(engine_mod, "is_interrupt_requested", return_value=True)
        wf = _make_workflow(bot, nodes=[_node("only", "echo_test", {"outputParams": "last_message"})])
        engine = ChatFlowEngine(wf, start_node_id="only", entry_type="restful", execution_id="exec-intr")
        result = engine.execute({"last_message": "x", "user_id": "u"})
        assert result["interrupted"] is True
        tr = WorkFlowTaskResult.objects.get(execution_id="exec-intr")
        assert tr.status == WorkFlowTaskStatus.INTERRUPTED
