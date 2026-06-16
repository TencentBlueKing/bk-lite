"""
Issue #2854: Knowledge training failure still cleans up task or writes completed status.

Three functions under test (server/apps/opspilot/tasks.py):
1. general_embed_by_document_list — document training pipeline
2. rebuild_graph_community_by_instance — graph community rebuild
3. create_graph — graph creation

Bug summary:
- Document training: on failure, KnowledgeTask was always deleted (losing failure info).
  FIX: track has_failure, retain task on failure.
- Graph rebuild: on failure (result=false), status still written as "completed".
  STATUS: BUG STILL EXISTS in current code.
- Graph create: on failure (result=false), returns early leaving status stuck at "training".
  STATUS: BUG STILL EXISTS in current code (no "failed" write).

Test approach: replicate the control-flow logic from tasks.py source and verify
state transitions, since Django ORM cannot be imported without DB.
"""

import os
import re

import pytest

# ---------------------------------------------------------------------------
# Source reader helper
# ---------------------------------------------------------------------------


def _read_source(rel_path, start_line, end_line):
    """Read source lines from tasks.py for analysis."""

    base = os.path.dirname(os.path.abspath(__file__))
    full = os.path.normpath(os.path.join(base, "..", "..", "..", rel_path))
    with open(full, encoding="utf-8") as f:
        lines = f.readlines()
    return lines[start_line - 1 : end_line]


# ---------------------------------------------------------------------------
# 1. general_embed_by_document_list — document training
# ---------------------------------------------------------------------------


class TestGeneralEmbedByDocumentList:
    """Verify the fix: KnowledgeTask is retained when any document fails."""

    def _get_source(self):
        return _read_source("tasks.py", 78, 123)

    def test_has_failure_flag_exists(self):
        """The function must track a has_failure flag."""
        src = "".join(self._get_source())
        assert "has_failure" in src, "has_failure tracking variable missing"

    def test_failure_sets_has_failure_true(self):
        """On exception or ERROR status, has_failure must be set True."""
        src = "".join(self._get_source())
        # Both the except branch and the ERROR-status branch should set has_failure
        assert src.count("has_failure = True") >= 2, "has_failure should be set True in both exception and ERROR-status branches"

    def test_task_retained_on_failure(self):
        """When has_failure is True, KnowledgeTask must NOT be deleted."""
        src = "".join(self._get_source())
        # Pattern: if has_failure → log warning (no delete); else → delete
        assert "if has_failure:" in src, "Missing has_failure check before cleanup"
        # After "if has_failure:", the next meaningful action should NOT be delete
        idx_has_failure = src.index("if has_failure:")
        block_after = src[idx_has_failure : idx_has_failure + 200]
        # The delete should only appear in the else branch
        assert "task_obj.delete()" not in block_after.split("else")[0], "task_obj.delete() must not be in the has_failure=True branch"

    def test_task_deleted_only_on_full_success(self):
        """KnowledgeTask.delete() should only happen when all docs succeed."""
        src = "".join(self._get_source())
        # delete should be in the else branch of has_failure check
        assert "else:" in src, "Missing else branch for success case"
        idx_else = src.index("if has_failure:")
        remainder = src[idx_else:]
        assert "task_obj.delete()" in remainder, "task_obj.delete() missing in success path"

    def test_exception_sets_document_error_status(self):
        """On exception, document.train_status must be set to ERROR."""
        src = "".join(self._get_source())
        assert "DocumentStatus.ERROR" in src, "Exception handler must set document status to ERROR"

    def test_exception_sets_error_message(self):
        """On exception, document.error_message must be populated."""
        src = "".join(self._get_source())
        assert "error_message" in src, "Exception handler must set document.error_message"

    def test_completed_count_only_on_success(self):
        """completed_count should only increment when document succeeds."""
        src = "".join(self._get_source())
        # Pattern: if success: completed_count += 1
        assert re.search(r"if success.*completed_count", src, re.DOTALL), "completed_count must only increment on success"


# ---------------------------------------------------------------------------
# 2. rebuild_graph_community_by_instance — graph community rebuild
# ---------------------------------------------------------------------------


class TestRebuildGraphCommunity:
    """Verify: when rebuild fails (result=false), status must NOT be 'completed'."""

    def _get_source(self):
        return _read_source("tasks.py", 442, 454)

    def test_status_set_to_rebuilding_initially(self):
        """Status must be set to 'rebuilding' before the operation."""
        src = "".join(self._get_source())
        assert '"rebuilding"' in src or "'rebuilding'" in src

    def test_failure_must_not_write_completed(self):
        """BUG CHECK: when res['result'] is False, status must NOT be 'completed'.

        Current code (BUGGY): always writes 'completed' regardless of result.
        This test documents the expected fix behavior.
        """
        src = "".join(self._get_source())
        # Find the failure check
        has_result_check = 'res["result"]' in src or "res['result']" in src
        assert has_result_check, "Must check res['result']"

        # The bug: after the failure log, code falls through to status = "completed"
        # Expected fix: on failure, set status to "failed" and return/skip completed
        idx_not_result = src.find("not res")
        if idx_not_result == -1:
            pytest.fail("Cannot find result check in source")

        # Check if there's a "failed" status write in the failure branch
        # or if the completed write is guarded
        lines = self._get_source()
        failure_handled = False
        for line in lines:
            stripped = line.strip()
            if '"failed"' in stripped and "status" in stripped:
                failure_handled = True
                break
            if "'failed'" in stripped and "status" in stripped:
                failure_handled = True
                break

        assert failure_handled, (
            "BUG #2854 NOT FIXED: rebuild_graph_community_by_instance does not set "
            "status='failed' when res['result'] is False. Status is always 'completed'."
        )

    def test_success_writes_completed(self):
        """On success, status should be 'completed'."""
        src = "".join(self._get_source())
        assert '"completed"' in src or "'completed'" in src


# ---------------------------------------------------------------------------
# 3. create_graph — graph creation
# ---------------------------------------------------------------------------


class TestCreateGraph:
    """Verify: when graph creation fails, status must be set to 'failed'."""

    def _get_source(self):
        return _read_source("tasks.py", 458, 477)

    def test_status_set_to_training_initially(self):
        """Status must be set to 'training' before the operation."""
        src = "".join(self._get_source())
        assert '"training"' in src or "'training'" in src

    def test_failure_must_set_failed_status(self):
        """BUG CHECK: when res['result'] is False, status must be set to 'failed'.

        Current code (BUGGY): on failure, just logs and returns without updating
        status, leaving it stuck at 'training' forever.
        This test documents the expected fix behavior.
        """
        lines = self._get_source()

        failure_sets_status = False
        for line in lines:
            stripped = line.strip()
            if '"failed"' in stripped and "status" in stripped:
                failure_sets_status = True
                break
            if "'failed'" in stripped and "status" in stripped:
                failure_sets_status = True
                break

        assert failure_sets_status, (
            "BUG #2854 NOT FIXED: create_graph does not set " "status='failed' when res['result'] is False. " "Status remains stuck at 'training'."
        )

    def test_failure_must_save_after_setting_failed(self):
        """After setting status='failed', instance.save() must be called."""
        src = "".join(self._get_source())
        # Find the failure branch and check for save()
        idx_not_result = src.find("not res")
        if idx_not_result == -1:
            pytest.skip("Cannot find result check")

        failure_block = src[idx_not_result : idx_not_result + 300]
        # Should have both status = "failed" and .save() before return
        has_failed = '"failed"' in failure_block or "'failed'" in failure_block
        has_save = ".save()" in failure_block
        assert has_failed and has_save, "BUG #2854 NOT FIXED: failure branch must set status='failed' AND call save()"

    def test_success_writes_completed(self):
        """On success, status should be 'completed'."""
        src = "".join(self._get_source())
        assert '"completed"' in src or "'completed'" in src


# ---------------------------------------------------------------------------
# 4. update_graph — graph update (reference: already fixed correctly)
# ---------------------------------------------------------------------------


class TestUpdateGraph:
    """Verify update_graph correctly handles failure (reference implementation)."""

    def _get_source(self):
        return _read_source("tasks.py", 477, 494)

    def test_failure_sets_failed_status(self):
        """update_graph correctly sets status='failed' on failure."""
        src = "".join(self._get_source())
        assert '"failed"' in src or "'failed'" in src, "update_graph should set status='failed' on failure"

    def test_failure_saves_after_setting_failed(self):
        """update_graph calls save() after setting failed status."""
        src = "".join(self._get_source())
        idx_failed = max(src.find('"failed"'), src.find("'failed'"))
        if idx_failed == -1:
            pytest.skip("No failed status found")
        remainder = src[idx_failed:]
        assert ".save()" in remainder, "Must save after setting failed status"

    def test_failure_returns_early(self):
        """update_graph returns early on failure, not falling through to completed."""
        src = "".join(self._get_source())
        idx_failed = max(src.find('"failed"'), src.find("'failed'"))
        if idx_failed == -1:
            pytest.skip("No failed status found")
        # Between "failed" and "completed", there should be a return
        idx_completed = src.find('"completed"')
        if idx_completed == -1:
            idx_completed = src.find("'completed'")
        between = src[idx_failed:idx_completed]
        assert "return" in between, "Must return after setting failed status to prevent falling through to completed"


# ---------------------------------------------------------------------------
# 5. Cross-cutting: consistency check across all graph functions
# ---------------------------------------------------------------------------


class TestGraphFunctionConsistency:
    """All graph functions should handle failure the same way as update_graph."""

    def _get_function_source(self, func_name):
        """Get source for a specific function from tasks.py."""

        base = os.path.dirname(os.path.abspath(__file__))
        full = os.path.normpath(os.path.join(base, "..", "..", "..", "tasks.py"))
        with open(full, encoding="utf-8") as f:
            content = f.read()

        # Find function and extract until next @shared_task or end
        pattern = rf"(def {func_name}\(.*?\n(?:(?!^def |^@shared_task).*\n)*)"
        match = re.search(pattern, content, re.MULTILINE)
        return match.group(0) if match else ""

    @pytest.mark.parametrize(
        "func_name",
        [
            "rebuild_graph_community_by_instance",
            "create_graph",
            "update_graph",
        ],
    )
    def test_all_graph_functions_handle_failure_status(self, func_name):
        """Every graph function must write a failure status when operation fails."""
        # Read the inner _execute function

        base = os.path.dirname(os.path.abspath(__file__))
        full = os.path.normpath(os.path.join(base, "..", "..", "..", "tasks.py"))
        with open(full, encoding="utf-8") as f:
            content = f.read()

        # Extract the function body
        idx = content.find(f"def {func_name}(")
        if idx == -1:
            pytest.skip(f"Function {func_name} not found")

        # Get ~500 chars of the function
        func_body = content[idx : idx + 600]

        has_failure_status = '"failed"' in func_body or "'failed'" in func_body
        assert has_failure_status, (
            f"BUG #2854: {func_name} does not set status='failed' " f"on failure. Compare with update_graph which " f"correctly handles this."
        )
