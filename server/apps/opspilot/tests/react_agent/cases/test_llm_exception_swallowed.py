"""
Tests for Issue #2853: LLM 异常被吞并按成功落库

Reproduces the bug where ChatService.invoke_chat() catches LLM/Agent
exceptions and returns a plain {"message": error_text} dict without any
failure indicator, causing downstream consumers to treat failures as
successes.

Bug chain:
1. invoke_chat swallows exception → returns {"message": ...} without success=False
2. AgentNode.execute() treats error message as successful output
3. IntentClassifier uses error text as intent → wrong routing
4. Engine records SUCCESS + stores error text as bot conversation history

These tests verify the LOGIC of each component via source analysis and
logic replication (no Django DB required).
Tests are written to FAIL against the current (buggy) code and PASS after fix.
"""

import re

# ---------------------------------------------------------------------------
# Helper: read source code for static analysis
# ---------------------------------------------------------------------------


def _read_source(filepath, start_line, end_line):
    """Read source lines from a file."""
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()
    return "".join(lines[start_line - 1 : end_line])


# ---------------------------------------------------------------------------
# 1. ChatService.invoke_chat: exception handler analysis
# ---------------------------------------------------------------------------


class TestInvokeChatExceptionHandler:
    """Verify invoke_chat's except block returns a failure-distinguishable result."""

    def test_except_block_must_include_failure_signal(self):
        """The except block in invoke_chat must return a result that
        downstream consumers can distinguish from a successful response.

        Current bug: returns {"message": error_text} — identical shape
        to a successful response, with no success/error/status field.
        """
        source_path = "apps/opspilot/services/chat_service.py"
        source = _read_source(source_path, 145, 165)

        # The except block currently returns {"message": message}
        # After fix, it should include at least one of:
        # - "success": False
        # - "error": ...
        # - raise (re-raise the exception)
        has_failure_signal = (
            '"success": False' in source or "'success': False" in source or '"success":False' in source or '"error"' in source or "'error'" in source
        )

        # Check if the except block re-raises
        except_section = source[source.index("except") :]
        has_reraise = bool(re.search(r"^\s+raise\b", except_section, re.MULTILINE))

        assert has_failure_signal or has_reraise, (
            "invoke_chat except block returns {'message': error_text} without "
            "any failure indicator (success=False, error key, or re-raise). "
            "Downstream consumers cannot distinguish this from a successful response.\n"
            f"Current except block:\n{except_section[:500]}"
        )

    def test_return_shape_differs_from_success(self):
        """The error return must have a different shape or extra fields
        compared to the success return, so callers can tell them apart.
        """
        source_path = "apps/opspilot/services/chat_service.py"
        source = _read_source(source_path, 136, 158)

        except_section = source[source.index("except") :]

        # Check that error return has MORE than just "message"
        # or that it raises instead of returning
        returns_only_message = bool(
            re.search(
                r'return\s+\{\s*"message"\s*:\s*\w+\s*\}',
                except_section,
            )
        )
        has_reraise = bool(re.search(r"^\s+raise\b", except_section, re.MULTILINE))

        assert not returns_only_message or has_reraise, (
            "invoke_chat error path returns ONLY {'message': ...} — "
            "indistinguishable from success for consumers that only check 'message'. "
            "Must add success=False, error field, or re-raise."
        )


# ---------------------------------------------------------------------------
# 2. AgentNode.execute: must check for failure from invoke_chat
# ---------------------------------------------------------------------------


class TestAgentNodeFailureCheck:
    """AgentNode.execute must not blindly pass invoke_chat result as success."""

    def test_agent_node_checks_invoke_chat_failure(self):
        """AgentNode.execute should check if invoke_chat returned a failure
        before writing the result as successful node output.

        Current bug: directly reads data["message"] without checking
        for failure indicators.
        """
        source_path = "apps/opspilot/utils/chat_flow_utils/nodes/agent/agent.py"
        source = _read_source(source_path, 254, 271)

        # After invoke_chat, the code should check for failure
        has_failure_check = (
            "success" in source or "error" in source or "failed" in source.lower() or "raise" in source or "exception" in source.lower()
        )

        assert has_failure_check, (
            "AgentNode.execute() reads data['message'] from invoke_chat "
            "without checking for failure. If invoke_chat failed, the error "
            "text gets silently passed as successful output.\n"
            f"Current code:\n{source}"
        )


# ---------------------------------------------------------------------------
# 3. IntentClassifier: error text used as intent
# ---------------------------------------------------------------------------


class TestIntentClassifierErrorHandling:
    """IntentClassifier must handle invoke_chat failure gracefully."""

    def test_intent_classifier_checks_invoke_chat_failure(self):
        """IntentClassifier should detect invoke_chat failure before
        using the result as intent classification.

        Current bug: reads result["message"] as intent text, and if
        it doesn't match any configured intent, silently defaults to
        the first one — masking the actual failure.
        """
        source_path = "apps/opspilot/utils/chat_flow_utils/nodes/intent/intent_classifier.py"
        source = _read_source(source_path, 156, 175)

        # After invoke_chat, should check for failure before using as intent
        has_failure_check = (
            "success" in source or "error" in source or "failed" in source.lower() or "raise" in source or "exception" in source.lower()
        )

        assert has_failure_check, (
            "IntentClassifier reads invoke_chat result as intent text without "
            "checking for failure. Error text like 'Agent execution failed: ...' "
            "gets used as intent classification, then silently defaults to first "
            "intent when it doesn't match.\n"
            f"Current code:\n{source}"
        )


# ---------------------------------------------------------------------------
# 4. Engine._check_chain_result: logic verification (replicated)
# ---------------------------------------------------------------------------


class TestEngineCheckChainResult:
    """Engine must detect failures from agent nodes in chain results."""

    @staticmethod
    def _check_chain_result(chain_result):
        """Replicated from engine.py _check_chain_result to avoid Django import."""
        if not isinstance(chain_result, dict):
            return True, {}
        if chain_result.get("success") is False:
            return False, {
                "node_id": chain_result.get("node_id"),
                "node_type": chain_result.get("node_type"),
                "error": chain_result.get("error", "未知错误"),
            }
        current_node = chain_result.get("current_node")
        if current_node and isinstance(current_node, dict):
            if current_node.get("success") is False:
                return False, {
                    "node_id": current_node.get("node_id"),
                    "node_type": current_node.get("node_type"),
                    "error": current_node.get("error", "未知错误"),
                }
        return True, {}

    def test_missing_success_false_treated_as_success_documents_bug(self):
        """Documents the bug: chain_result without success=False is
        treated as success, even when the actual execution failed.

        This test PASSES on buggy code (documenting the bug exists).
        After fix, this test should be UPDATED to expect is_success=False.
        """
        chain_result_buggy = {
            "current_node": {
                "node_id": "agent_1",
                "node_type": "agent",
                # No "success": False — this is the bug
                "output": {"last_message": "Agent execution failed: timeout"},
            },
        }

        is_success, _ = self._check_chain_result(chain_result_buggy)

        # BUG: is_success=True even though execution failed
        assert is_success is True, "This test documents the current buggy behavior. " "If this fails, the fix has been applied — update this test."

    def test_success_false_correctly_detected(self):
        """Verify detection logic works when success=False IS present."""
        chain_result_fixed = {
            "current_node": {
                "node_id": "agent_1",
                "node_type": "agent",
                "success": False,
                "error": "LLM connection timeout",
            },
        }

        is_success, error_info = self._check_chain_result(chain_result_fixed)
        assert not is_success
        assert error_info["error"] == "LLM connection timeout"


# ---------------------------------------------------------------------------
# 5. End-to-end: error propagation chain (logic simulation)
# ---------------------------------------------------------------------------


class TestErrorPropagationChain:
    """Verify the full error propagation path is broken (documents bug)."""

    def test_no_stage_marks_failure_documents_bug(self):
        """Simulate the full chain: invoke_chat error → AgentNode → Engine.

        Documents that NO stage currently marks the failure.
        This test PASSES on buggy code. After fix, update expectations.
        """
        # Stage 1: invoke_chat returns error (current buggy format)
        invoke_chat_result = {"message": "Agent execution failed: connection refused"}

        # Stage 2: AgentNode reads it blindly
        agent_output = {"last_message": invoke_chat_result["message"]}

        # Stage 3: Engine checks chain result
        chain_result = {
            "current_node": {
                "node_id": "agent_1",
                "node_type": "agent",
                **agent_output,
            },
        }

        # No stage marks failure
        has_failure_at_invoke = invoke_chat_result.get("success") is False
        has_failure_at_agent = agent_output.get("success") is False
        has_failure_at_engine = chain_result["current_node"].get("success") is False

        # BUG: all three are False (no failure marked anywhere)
        assert not has_failure_at_invoke, "Documents bug: invoke_chat has no failure flag"
        assert not has_failure_at_agent, "Documents bug: agent has no failure flag"
        assert not has_failure_at_engine, "Documents bug: engine has no failure flag"

    def test_error_text_detectable_in_last_message(self):
        """Error text in last_message should be detectable by keywords.
        After fix, this detection should happen at invoke_chat level,
        not by keyword matching on the message text.
        """
        last_message = "Agent execution failed: LLM timeout"

        is_error_like = any(kw in last_message.lower() for kw in ["failed", "error", "timeout", "exception", "refused"])
        assert is_error_like, "Error text should contain detectable keywords"
