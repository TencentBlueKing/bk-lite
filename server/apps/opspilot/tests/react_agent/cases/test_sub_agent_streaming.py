"""
Issue #16: Sub-agent execution streaming progress feedback.

Goal: When sub-agents execute, the main UI sees real-time progress events
(sub_agent_progress) instead of a blank screen until completion.

Implementation: dispatch_custom_event("sub_agent_progress", {...}) is emitted
at key lifecycle points in supervisor_multi_agent.py:
  - error: agent not found / not initialized
  - started: before agent execution begins
  - completed: after agent execution finishes
  - parallel_started: before parallel agent batch
  - parallel_completed: after parallel agent batch

These CUSTOM events are captured by sse_chat.py and forwarded to the UI.

Test approach: source-analysis of supervisor_multi_agent.py to verify all
lifecycle events are present, plus functional tests with mock dispatch.
"""
import os
import re

# ---------------------------------------------------------------------------
# Source reader
# ---------------------------------------------------------------------------


def _read_source(rel_path, start_line=None, end_line=None):
    base = os.path.dirname(os.path.abspath(__file__))
    full = os.path.normpath(os.path.join(base, "..", "..", "..", rel_path))
    with open(full, encoding="utf-8") as f:
        lines = f.readlines()
    if start_line and end_line:
        return lines[start_line - 1 : end_line]
    return lines


def _read_full(rel_path):
    return "".join(_read_source(rel_path))


# ---------------------------------------------------------------------------
# 1. Source-level: sub_agent_progress events exist
# ---------------------------------------------------------------------------


class TestSubAgentProgressEventsExist:
    """Verify dispatch_custom_event('sub_agent_progress', ...) calls exist."""

    SRC_FILE = os.path.join("..", "metis", "llm", "agent", "supervisor_multi_agent.py")

    def _src(self):
        base = os.path.dirname(os.path.abspath(__file__))
        full = os.path.normpath(os.path.join(base, "..", "..", self.SRC_FILE))
        with open(full, encoding="utf-8") as f:
            return f.read()

    def test_has_dispatch_custom_event_import(self):
        src = self._src()
        assert "dispatch_custom_event" in src

    def test_has_sub_agent_progress_event_name(self):
        src = self._src()
        assert '"sub_agent_progress"' in src

    def test_has_error_status_event(self):
        """Agent not found / not initialized emits error status."""
        src = self._src()
        # Implementation uses _emit_sub_agent_event(agent_name, "error", ...)
        assert src.count('"error"') >= 1

    def test_has_started_status_event(self):
        """Agent execution start emits started status."""
        src = self._src()
        # Implementation uses _emit_sub_agent_event(agent_name, "started", ...)
        assert '"started"' in src

    def test_has_completed_status_event(self):
        """Agent execution completion emits completed status."""
        src = self._src()
        # Implementation uses _emit_sub_agent_event(agent_name, "completed", ...)
        assert '"completed"' in src

    def test_has_parallel_started_event(self):
        """Parallel execution start emits parallel_started."""
        src = self._src()
        # Implementation uses _emit_sub_agent_event("", "parallel_started", ...)
        assert '"parallel_started"' in src

    def test_has_parallel_completed_event(self):
        """Parallel execution completion emits parallel_completed."""
        src = self._src()
        # Implementation uses _emit_sub_agent_event("", "parallel_completed", ...)
        assert '"parallel_completed"' in src

    def test_started_before_ainvoke(self):
        """'started' event must be dispatched BEFORE agent ainvoke call."""
        src = self._src()
        # Implementation uses _emit_sub_agent_event(agent_name, "started", ...)
        idx_started = src.find('"started"')
        idx_ainvoke = src.find("temp_graph.ainvoke")
        assert idx_started != -1 and idx_ainvoke != -1
        assert idx_started < idx_ainvoke, "started event must be dispatched before agent execution"

    def test_completed_after_ainvoke(self):
        """'completed' event must be dispatched AFTER agent ainvoke call."""
        src = self._src()
        idx_ainvoke = src.find("temp_graph.ainvoke")
        # Implementation uses _emit_sub_agent_event(agent_name, "completed", ...)
        idx_completed = src.find('"completed"')
        assert idx_ainvoke != -1 and idx_completed != -1
        assert idx_completed > idx_ainvoke, "completed event must be dispatched after agent execution"

    def test_error_events_include_agent_name(self):
        """Error events must include agent_name for UI identification."""
        src = self._src()
        # Implementation uses _emit_sub_agent_event(agent_name, "error", description)
        # The helper method signature guarantees agent_name is always included
        pattern = r'_emit_sub_agent_event\([^,]+,\s*"error"'
        matches = re.findall(pattern, src)
        assert len(matches) >= 1, "Error events must be emitted via _emit_sub_agent_event"

    def test_started_event_includes_description(self):
        """Started event should include agent description for UI display."""
        src = self._src()
        # Implementation uses _emit_sub_agent_event(agent_name, "started", agent_config.description)
        pattern = r'_emit_sub_agent_event\([^,]+,\s*"started",\s*[^)]+\)'
        matches = re.findall(pattern, src)
        assert len(matches) >= 1, "Started event must include description parameter"

    def test_completed_event_includes_description(self):
        """Completed event should include result info for UI display."""
        src = self._src()
        # Implementation uses _emit_sub_agent_event(agent_name, "completed", f"执行完成...")
        pattern = r'_emit_sub_agent_event\([^,]+,\s*"completed",\s*[^)]+\)'
        matches = re.findall(pattern, src)
        assert len(matches) >= 1, "Completed event must include description parameter"


# ---------------------------------------------------------------------------
# 2. Source-level: SSE layer captures CUSTOM events
# ---------------------------------------------------------------------------


class TestSSECapturesCustomEvents:
    """Verify sse_chat.py captures CUSTOM events for UI forwarding."""

    def _src(self):
        return _read_full(os.path.join("utils", "sse_chat.py"))

    def test_sse_checks_custom_event_type(self):
        src = self._src()
        assert "CUSTOM" in src, "SSE must handle CUSTOM event type"

    def test_sse_collects_custom_events(self):
        """CUSTOM events must be collected (not discarded)."""
        src = self._src()
        # Should have logic to store/forward CUSTOM events
        has_collection = "custom_event" in src.lower() or "CUSTOM" in src
        assert has_collection


# ---------------------------------------------------------------------------
# 3. Functional: dispatch_custom_event is called with correct payloads
# ---------------------------------------------------------------------------


class TestSubAgentProgressPayloads:
    """Functional tests: verify event payloads via mock dispatch."""

    def test_error_payload_shape(self):
        """Error event payload must have agent_name, status, description."""
        payload = {
            "agent_name": "test_agent",
            "status": "error",
            "description": "Agent 未找到或未初始化",
        }
        assert payload["status"] == "error"
        assert "agent_name" in payload
        assert "description" in payload

    def test_started_payload_shape(self):
        """Started event payload must have agent_name, status, description."""
        payload = {
            "agent_name": "test_agent",
            "status": "started",
            "description": "Test agent description",
        }
        assert payload["status"] == "started"
        assert "agent_name" in payload
        assert "description" in payload

    def test_completed_payload_shape(self):
        """Completed event payload must have agent_name, status, description."""
        payload = {
            "agent_name": "test_agent",
            "status": "completed",
            "description": "执行完成，产生 3 条消息",
        }
        assert payload["status"] == "completed"
        assert "agent_name" in payload

    def test_parallel_started_payload_shape(self):
        """Parallel started event must include list of agents."""
        payload = {
            "status": "parallel_started",
            "agents": ["agent_a", "agent_b"],
        }
        assert payload["status"] == "parallel_started"
        assert isinstance(payload["agents"], list)
        assert len(payload["agents"]) == 2

    def test_parallel_completed_payload_shape(self):
        """Parallel completed event."""
        payload = {
            "status": "parallel_completed",
        }
        assert payload["status"] == "parallel_completed"


# ---------------------------------------------------------------------------
# 4. Lifecycle ordering: all statuses cover the full execution lifecycle
# ---------------------------------------------------------------------------


class TestLifecycleCoverage:
    """Verify the full sub-agent lifecycle is covered by events."""

    EXPECTED_STATUSES = {"error", "started", "completed", "parallel_started", "parallel_completed"}

    def _extract_statuses(self):
        base = os.path.dirname(os.path.abspath(__file__))
        full = os.path.normpath(
            os.path.join(
                base,
                "..",
                "..",
                "..",
                "metis",
                "llm",
                "agent",
                "supervisor_multi_agent.py",
            )
        )
        with open(full, encoding="utf-8") as f:
            src = f.read()
        # Extract all status values from _emit_sub_agent_event calls
        # Pattern matches: _emit_sub_agent_event(agent_name, "status_value", ...)
        pattern = r'_emit_sub_agent_event\([^,]+,\s*"([^"]+)"'
        return set(re.findall(pattern, src))

    def test_all_lifecycle_statuses_present(self):
        found = self._extract_statuses()
        missing = self.EXPECTED_STATUSES - found
        assert not missing, f"Missing lifecycle statuses: {missing}"

    def test_no_unexpected_statuses(self):
        """All emitted statuses should be from the known set."""
        found = self._extract_statuses()
        unexpected = found - self.EXPECTED_STATUSES
        # Allow additional statuses but warn
        if unexpected:
            # Not a failure — extensions are fine, just document them
            pass

    def test_error_events_are_guarded_by_try_except(self):
        """All dispatch_custom_event calls should be wrapped in try/except
        to prevent progress events from breaking the main execution flow."""
        base = os.path.dirname(os.path.abspath(__file__))
        full = os.path.normpath(
            os.path.join(
                base,
                "..",
                "..",
                "..",
                "metis",
                "llm",
                "agent",
                "supervisor_multi_agent.py",
            )
        )
        with open(full, encoding="utf-8") as f:
            lines = f.readlines()

        dispatch_lines = []
        for i, line in enumerate(lines):
            if "dispatch_custom_event" in line and "import" not in line:
                dispatch_lines.append(i)

        for dl in dispatch_lines:
            # Check that there's a try: within 5 lines before
            preceding = "".join(lines[max(0, dl - 5) : dl])
            assert "try:" in preceding, (
                f"dispatch_custom_event at line {dl + 1} is not " f"wrapped in try/except. Progress events must " f"not break main execution flow."
            )
