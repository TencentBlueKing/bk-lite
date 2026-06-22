"""引擎同步执行链失败传播回归测试。

Bug: `_execute_single_node` 只要执行器不抛异常就返回 `NodeResult(ok=True)`,而 agent/intent
节点以 in-band `{"success": False}` 表达业务失败(见 test_llm_error_propagation)。于是
`_check_chain_result`(只看包装层 success)把失败当成功 → 错误结果被当正常回复发给用户、
`WorkFlowTaskResult` 被误记为成功(celery / nats / 第三方渠道 的同步执行路径,非流式)。

本测试锁定修复后的行为:in-band `{"success": False}` → 节点判为失败 + `_check_chain_result`
捕获到失败 + 失败节点记为 FAILED + 不把错误写成全局 last_message;成功路径不受影响。
"""

import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

# node_runner 间接依赖的可选 C 扩展用空 stub 顶替(与同目录其它用例一致)
for _mod_name in ("oracledb", "pyodbc"):
    sys.modules.setdefault(_mod_name, types.ModuleType(_mod_name))
_falkordb = types.ModuleType("falkordb")
_falkordb.Graph = type("Graph", (), {})
sys.modules.setdefault("falkordb", _falkordb)
_falkordb_async = types.ModuleType("falkordb.asyncio")
_falkordb_async.FalkorDB = type("FalkorDB", (), {})
sys.modules.setdefault("falkordb.asyncio", _falkordb_async)

from apps.opspilot.utils.chat_flow_utils.engine.core.enums import NodeStatus  # noqa: E402
from apps.opspilot.utils.chat_flow_utils.engine.node_runner import NodeRunnerMixin  # noqa: E402


def _make_runner(executor_result, node_type="agent"):
    """构造一个最小 NodeRunnerMixin 宿主,桩掉引擎宿主类提供的协作方法。"""

    class _Runner(NodeRunnerMixin):
        def __init__(self):
            self.variable_manager = MagicMock()
            self.variable_manager.get_variable.side_effect = lambda key, *a, **k: (None if key == "intent_previous_output" else "input-text")
            self.recorded = []

        def _get_node_by_id(self, node_id):
            return {
                "id": node_id,
                "type": node_type,
                "data": {"config": {"inputParams": "last_message", "outputParams": "last_message"}},
            }

        def _raise_if_interrupted(self, *a, **k):
            return None

        def _create_node_execution_context(self, node, input_data, status):
            return SimpleNamespace(start_time=0.0, end_time=None, status=status, error_message=None, output_data=None)

        def _get_node_executor(self, _node_type):
            ex = MagicMock()
            ex.execute.return_value = executor_result
            return ex

        def _update_node_execution_order(self, node_id):
            return None

        def _record_node_execution_result(self, node_id, context):
            self.recorded.append((node_id, context.status))

    return _Runner()


class TestSyncChainFailurePropagation:
    def test_inband_failure_marked_failed_and_caught_by_chain_check(self):
        runner = _make_runner({"success": False, "error": "LLM timeout", "last_message": "调用失败"})
        result = runner._execute_single_node("n1", {"last_message": "hi"})

        # 节点结果判为失败
        assert result.get("success") is False
        assert "LLM timeout" in result.get("error", "")

        # 链校验捕获到失败
        is_success, error_info = runner._check_chain_result(result)
        assert is_success is False
        assert error_info.get("node_id") == "n1"

        # 失败节点记为 FAILED,且失败时不把错误文本写成全局 last_message
        assert runner.recorded[-1] == ("n1", NodeStatus.FAILED)
        runner.variable_manager.set_variable.assert_not_called()

    def test_success_path_unaffected(self):
        runner = _make_runner({"last_message": "正常回复"})
        result = runner._execute_single_node("n1", {"last_message": "hi"})

        assert result.get("success") is True
        is_success, _ = runner._check_chain_result(result)
        assert is_success is True
        assert runner.recorded[-1] == ("n1", NodeStatus.COMPLETED)
