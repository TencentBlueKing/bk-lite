import sys
import types

for _mod_name in ("oracledb", "pyodbc"):
    sys.modules.setdefault(_mod_name, types.ModuleType(_mod_name))

_falkordb = types.ModuleType("falkordb")
_falkordb.Graph = type("Graph", (), {})
sys.modules.setdefault("falkordb", _falkordb)

_falkordb_asyncio = types.ModuleType("falkordb.asyncio")
_falkordb_asyncio.FalkorDB = type("FalkorDB", (), {})
sys.modules.setdefault("falkordb.asyncio", _falkordb_asyncio)

import asyncio
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage

from apps.opspilot.metis.llm.agent.plan_and_execute_agent import PlanAndExecuteAgentNode, PlanAndExecuteAgentRequest


def test_summary_node_reuses_existing_k8s_report_instead_of_generating_second_summary():
    node = PlanAndExecuteAgentNode()
    config = {
        "configurable": {
            "graph_request": PlanAndExecuteAgentRequest(
                openai_api_base="http://localhost:8000/v1",
                openai_api_key="test-key",
                model="gpt-4o",
                user_message="检查k8s集群所有工作负载的配置有没有问题",
            )
        }
    }
    existing_report = """# 配置问题摘要（Kubernetes - 1 集群）

## Critical / High

### 未配置存活探针
影响 28 个工作负载。"""
    state = {
        "original_plan": ["检查工作负载配置"],
        "current_plan": [],
        "messages": [AIMessage(content=existing_report)],
        "execution_count": 1,
        "step_history": ["[步骤 1] 执行: 检查工作负载配置"],
        "final_response": None,
    }

    node.structured_output_parser = MagicMock()
    node.llm = MagicMock(model_name="gpt-4o", temperature=0.7)
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="这是第二次总结"))]
    )
    node.structured_output_parser._get_openai_client.return_value = fake_client

    result = asyncio.run(node.summary_node(state, config))

    assert result["final_response"] == existing_report
    assert result["messages"] == [AIMessage(content=existing_report)]
    node.structured_output_parser._get_openai_client.assert_not_called()
