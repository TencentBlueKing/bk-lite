import inspect
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.opspilot.metis.llm.agent.supervisor_multi_agent import AgentConfig, SupervisorMultiAgentNode, SupervisorMultiAgentRequest


class TestToModelOutput:
    def test_agent_config_output_schema(self):
        schema = {"type": "object", "properties": {"status": {"type": "string"}}, "required": ["status"]}
        config = AgentConfig(name="test", description="test agent", output_schema=schema)
        assert config.output_schema == schema

    def test_agent_config_output_schema_default_none(self):
        config = AgentConfig(name="test", description="test agent")
        assert config.output_schema is None

    @pytest.mark.asyncio
    async def test_structured_extract_basic(self):
        node = SupervisorMultiAgentNode()
        schema = {"type": "object", "properties": {"status": {"type": "string"}}}
        mock_llm = MagicMock()
        mock_structured = AsyncMock(return_value={"status": "healthy"})
        mock_llm.with_structured_output.return_value = MagicMock(ainvoke=mock_structured)
        request = MagicMock(spec=SupervisorMultiAgentRequest)
        with patch.object(node, "get_llm_client", return_value=mock_llm):
            result = await node._structured_extract("System is healthy", schema, request, "test_agent")
        parsed = json.loads(result)
        assert parsed["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_structured_extract_fallback_on_error(self):
        node = SupervisorMultiAgentNode()
        schema = {"type": "object"}
        mock_llm = MagicMock()
        mock_llm.with_structured_output.side_effect = Exception("LLM error")
        request = MagicMock(spec=SupervisorMultiAgentRequest)
        with patch.object(node, "get_llm_client", return_value=mock_llm):
            result = await node._structured_extract("raw text", schema, request, "test_agent")
        assert result == "raw text"


from langchain_core.messages import AIMessage  # noqa: E402


class TestParallelExecution:
    def test_parse_decision_single_agent(self):
        node = SupervisorMultiAgentNode()
        request = MagicMock(spec=SupervisorMultiAgentRequest)
        request.agents = [MagicMock(name="agent_a"), MagicMock(name="agent_b")]
        # Mocking name property because MagicMock handles it weirdly sometimes
        request.agents[0].name = "agent_a"
        request.agents[1].name = "agent_b"
        result = node._parse_supervisor_decision("agent_a", request)
        assert result == ["agent_a"]

    def test_parse_decision_multiple_agents(self):
        node = SupervisorMultiAgentNode()
        request = MagicMock(spec=SupervisorMultiAgentRequest)
        request.agents = [MagicMock(name="agent_a"), MagicMock(name="agent_b")]
        request.agents[0].name = "agent_a"
        request.agents[1].name = "agent_b"
        result = node._parse_supervisor_decision("agent_a, agent_b", request)
        assert result == ["agent_a", "agent_b"]

    def test_parse_decision_finish(self):
        node = SupervisorMultiAgentNode()
        request = MagicMock(spec=SupervisorMultiAgentRequest)
        request.agents = []
        result = node._parse_supervisor_decision("FINISH", request)
        assert result == ["FINISH"]

    @pytest.mark.asyncio
    async def test_parallel_executor_success(self):
        node = SupervisorMultiAgentNode()
        state = {"parallel_agents": ["a", "b"], "executed_agents": [], "messages": []}
        config = MagicMock()

        # Mock agent_executor_node to return async functions
        async def mock_exec_a(s, c):
            return {"messages": [AIMessage(content="[Agent: a]\nresult a")], "executed_agents": ["a"]}

        async def mock_exec_b(s, c):
            return {"messages": [AIMessage(content="[Agent: b]\nresult b")], "executed_agents": ["b"]}

        executors = {"a": mock_exec_a, "b": mock_exec_b}

        async def mock_agent_executor(name):
            return executors[name]

        with patch.object(node, "agent_executor_node", side_effect=mock_agent_executor):
            result = await node.parallel_executor_node(state, config)
        assert len(result["messages"]) == 2
        assert set(result["executed_agents"]) == {"a", "b"}

    @pytest.mark.asyncio
    async def test_parallel_executor_partial_failure(self):
        node = SupervisorMultiAgentNode()
        state = {"parallel_agents": ["a", "b"], "executed_agents": [], "messages": []}
        config = MagicMock()

        async def mock_exec_a(s, c):
            return {"messages": [AIMessage(content="[Agent: a]\nok")], "executed_agents": ["a"]}

        async def mock_exec_b(s, c):
            raise RuntimeError("connection failed")

        executors = {"a": mock_exec_a, "b": mock_exec_b}

        async def mock_agent_executor(name):
            return executors[name]

        with patch.object(node, "agent_executor_node", side_effect=mock_agent_executor):
            result = await node.parallel_executor_node(state, config)
        assert "a" in result["executed_agents"]
        assert "b" in result["executed_agents"]
        assert any("执行失败" in m.content for m in result["messages"])

    def test_should_continue_parallel(self):
        node = SupervisorMultiAgentNode()
        assert node.should_continue({"next_action": "PARALLEL"}) == "parallel_executor"
        assert node.should_continue({"next_action": "FINISH"}) == "FINISH"
        assert node.should_continue({"next_action": "agent_a"}) == "agent_a"


class TestSubAgentProgress:
    def test_step_progress_includes_agent_name(self):
        '""Verify _emit_step_progress includes agent_name in event data""'
        # This tests that build_react_nodes accepts agent_name parameter
        from apps.opspilot.metis.llm.chain.node import ToolsNodes

        node = ToolsNodes()
        # Verify the parameter exists in the signature

        sig = inspect.signature(node.build_react_nodes)
        assert "agent_name" in sig.parameters
