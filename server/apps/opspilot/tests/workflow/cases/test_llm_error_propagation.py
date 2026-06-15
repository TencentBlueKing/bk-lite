"""
Tests for LLM error propagation (Issue #2853).

Verifies that:
1. ChatService.invoke_chat returns success=False on exception
2. AgentNode propagates error when invoke_chat fails
3. IntentClassifierNode returns error instead of silent fallback
4. OpenAI-compatible API returns HTTP 500 on failure
"""

import sys
import types

# Stub out optional C-extension modules
for _mod_name in ("oracledb", "pyodbc"):
    sys.modules.setdefault(_mod_name, types.ModuleType(_mod_name))

_falkordb = types.ModuleType("falkordb")
_falkordb.Graph = type("Graph", (), {})
sys.modules.setdefault("falkordb", _falkordb)

_falkordb_asyncio = types.ModuleType("falkordb.asyncio")
_falkordb_asyncio.FalkorDB = type("FalkorDB", (), {})
sys.modules.setdefault("falkordb.asyncio", _falkordb_asyncio)


class TestChatServiceErrorPropagation:
    """Tests for ChatService.invoke_chat error handling."""

    def test_invoke_chat_returns_success_false_on_exception(self, mocker):
        """Verify invoke_chat returns success=False when exception occurs."""
        from apps.opspilot.services.chat_service import ChatService

        # Mock dependencies
        mock_llm_model = mocker.MagicMock()
        mock_llm_model.id = 1
        mocker.patch(
            "apps.opspilot.services.chat_service.LLMModel.objects.get",
            return_value=mock_llm_model,
        )
        mocker.patch(
            "apps.opspilot.services.chat_service.ChatService.format_chat_server_kwargs",
            return_value=({}, {}, {}),
        )
        mocker.patch(
            "apps.opspilot.services.chat_service.create_agent_instance",
            side_effect=RuntimeError("Test LLM failure"),
        )

        # Call invoke_chat
        result, doc_map, title_map = ChatService.invoke_chat({"llm_model": 1, "skill_type": "test"})

        # Verify error structure
        assert result.get("success") is False
        assert "error" in result
        assert result.get("error_type") == "RuntimeError"
        assert "Test LLM failure" in result.get("error", "")
        assert result.get("total_tokens") == 0
        assert result.get("prompt_tokens") == 0
        assert result.get("completion_tokens") == 0
        assert result.get("browser_steps") == []

    def test_invoke_chat_returns_success_true_on_success(self, mocker):
        """Verify invoke_chat returns success=True when execution succeeds."""
        from apps.opspilot.services.chat_service import ChatService

        # Mock dependencies
        mock_llm_model = mocker.MagicMock()
        mock_llm_model.id = 1
        mocker.patch(
            "apps.opspilot.services.chat_service.LLMModel.objects.get",
            return_value=mock_llm_model,
        )
        mocker.patch(
            "apps.opspilot.services.chat_service.ChatService.format_chat_server_kwargs",
            return_value=({}, {}, {}),
        )

        # Mock successful execution
        mock_response = mocker.MagicMock()
        mock_response.message = "Success response"
        mock_response.total_tokens = 100
        mock_response.prompt_tokens = 50
        mock_response.completion_tokens = 50
        mock_response.browser_steps = []

        mock_graph = mocker.MagicMock()
        mock_graph.execute = mocker.AsyncMock(return_value=mock_response)
        mocker.patch(
            "apps.opspilot.services.chat_service.create_agent_instance",
            return_value=(mock_graph, mocker.MagicMock()),
        )
        mocker.patch(
            "apps.opspilot.services.chat_service._is_eventlet_environment",
            return_value=False,
        )

        # Call invoke_chat
        result, doc_map, title_map = ChatService.invoke_chat({"llm_model": 1, "skill_type": "test"})

        # Verify success structure
        assert result.get("success") is True
        assert result.get("message") == "Success response"
        assert result.get("total_tokens") == 100


class TestAgentNodeErrorPropagation:
    """Tests for AgentNode error handling."""

    def test_agent_node_returns_error_when_invoke_chat_fails(self, mocker):
        """Verify AgentNode returns success=False when invoke_chat fails."""
        from apps.opspilot.utils.chat_flow_utils.nodes.agent.agent import AgentNode

        # Mock invoke_chat to return failure
        mocker.patch(
            "apps.opspilot.utils.chat_flow_utils.nodes.agent.agent.ChatService.invoke_chat",
            return_value=(
                {
                    "message": "Agent execution failed: Test error",
                    "success": False,
                    "error": "Test error",
                    "error_type": "RuntimeError",
                },
                {},
                {},
            ),
        )

        # Create AgentNode with mocked variable_manager
        mock_vm = mocker.MagicMock()
        mock_vm.get_variable.return_value = {}
        agent_node = AgentNode(mock_vm)

        # Mock set_llm_params (returns (llm_params, skill_name, supports_attachment_generation))
        mocker.patch.object(agent_node, "set_llm_params", return_value=({}, "test_skill", False))

        # Execute
        result = agent_node.execute(
            "test_node",
            {"data": {"config": {"outputParams": "last_message"}}},
            {"last_message": "test input"},
        )

        # Verify error propagation
        assert result.get("success") is False
        assert result.get("error") == "Test error"
        assert result.get("error_type") == "RuntimeError"


class TestIntentClassifierErrorPropagation:
    """Tests for IntentClassifierNode error handling."""

    def test_intent_classifier_returns_error_when_invoke_chat_fails(self, mocker):
        """Verify IntentClassifier returns error when invoke_chat fails."""
        from apps.opspilot.utils.chat_flow_utils.nodes.intent.intent_classifier import IntentClassifierNode

        # Mock invoke_chat to return failure
        mocker.patch(
            "apps.opspilot.utils.chat_flow_utils.nodes.intent.intent_classifier.ChatService.invoke_chat",
            return_value=(
                {
                    "message": "Agent execution failed: Test error",
                    "success": False,
                    "error": "Test error",
                    "error_type": "RuntimeError",
                },
                {},
                {},
            ),
        )

        # Create IntentClassifierNode with mocked variable_manager
        mock_vm = mocker.MagicMock()
        mock_vm.get_variable.return_value = {}
        intent_node = IntentClassifierNode(mock_vm)

        # Mock _build_llm_params
        mocker.patch.object(intent_node, "_build_llm_params", return_value={})

        # Execute
        result = intent_node.execute(
            "test_node",
            {
                "data": {
                    "config": {
                        "inputParams": "last_message",
                        "outputParams": "intent_output",
                        "intents": [{"name": "intent_a"}, {"name": "intent_b"}],
                    }
                }
            },
            {"last_message": "test input"},
        )

        # Verify error propagation
        assert result.get("success") is False
        assert result.get("intent_result") == "error"
        assert result.get("error") == "Test error"

    def test_intent_classifier_returns_error_when_intent_not_in_list(self, mocker):
        """Verify IntentClassifier returns error when intent not in configured list."""
        from apps.opspilot.utils.chat_flow_utils.nodes.intent.intent_classifier import IntentClassifierNode

        # Mock invoke_chat to return unknown intent
        mocker.patch(
            "apps.opspilot.utils.chat_flow_utils.nodes.intent.intent_classifier.ChatService.invoke_chat",
            return_value=(
                {
                    "message": "unknown_intent",
                    "success": True,
                },
                {},
                {},
            ),
        )

        # Create IntentClassifierNode with mocked variable_manager
        mock_vm = mocker.MagicMock()
        mock_vm.get_variable.return_value = {}
        intent_node = IntentClassifierNode(mock_vm)

        # Mock _build_llm_params
        mocker.patch.object(intent_node, "_build_llm_params", return_value={})

        # Execute
        result = intent_node.execute(
            "test_node",
            {
                "data": {
                    "config": {
                        "inputParams": "last_message",
                        "outputParams": "intent_output",
                        "intents": [{"name": "intent_a"}, {"name": "intent_b"}],
                    }
                }
            },
            {"last_message": "test input"},
        )

        # Verify error - should NOT silently fallback to first intent
        assert result.get("success") is False
        assert result.get("intent_result") == "error"
        assert "unknown_intent" in result.get("error", "")
        assert "不在配置列表中" in result.get("error", "")


class TestOpenAICompatibleAPIErrorPropagation:
    """Tests for OpenAI-compatible API error handling."""

    def test_get_chat_msg_returns_error_when_invoke_chat_fails(self, mocker):
        """Verify get_chat_msg returns error structure when invoke_chat fails."""
        from apps.opspilot.views import get_chat_msg

        # Mock ChatService.invoke_chat to return failure
        mocker.patch(
            "apps.opspilot.views.ChatService.invoke_chat",
            return_value=(
                {
                    "message": "Agent execution failed: Test error",
                    "success": False,
                    "error": "Test error",
                    "error_type": "RuntimeError",
                },
                {},
                {},
            ),
        )

        # Create mock skill_obj
        mock_skill = mocker.MagicMock()
        mock_skill.enable_rag_knowledge_source = False

        # Call get_chat_msg
        return_data, content, is_error = get_chat_msg(
            current_ip="127.0.0.1",
            kwargs={"model": "gpt-4"},
            params={},
            skill_obj=mock_skill,
            user_message="test",
        )

        # Verify error response
        assert is_error is True
        assert "error" in return_data
        assert return_data["error"]["code"] == "execution_failed"
        assert return_data["error"]["type"] == "RuntimeError"
        assert "Test error" in return_data["error"]["message"]
