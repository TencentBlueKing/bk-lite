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

import ast
import os
import re
from types import SimpleNamespace

import pytest

def _read_function_source(func_name):
    """Read a function body by name, so tests survive unrelated line movement."""

    base = os.path.dirname(os.path.abspath(__file__))
    full = os.path.normpath(os.path.join(base, "..", "..", "..", "tasks.py"))
    with open(full, encoding="utf-8") as f:
        content = f.read()
    tree = ast.parse(content, filename=full)
    target = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == func_name
    )
    return ast.get_source_segment(content, target).splitlines(keepends=True)


def _load_tasks_function(func_name, **overrides):
    """Load one function body from tasks.py with lightweight fakes.

    This keeps the test focused on the real task behavior without importing the
    full Django settings stack or relying on fixed source line numbers.
    """

    base = os.path.dirname(os.path.abspath(__file__))
    full = os.path.normpath(os.path.join(base, "..", "..", "..", "tasks.py"))
    with open(full, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=full)

    target = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == func_name
    )
    module = ast.Module(body=[target], type_ignores=[])
    ast.fix_missing_locations(module)

    namespace = {
        "DocumentStatus": SimpleNamespace(ERROR=2, READY=1),
        "KnowledgeTaskStatus": SimpleNamespace(RUNNING="running", FAILED="failed"),
        "KnowledgeTask": SimpleNamespace(objects=None),
        "logger": SimpleNamespace(
            info=lambda *args, **kwargs: None,
            warning=lambda *args, **kwargs: None,
            exception=lambda *args, **kwargs: None,
        ),
        "tqdm": lambda iterable: iterable,
    }
    namespace.update(overrides)
    exec(compile(module, full, "exec"), namespace)
    return namespace[func_name]


# ---------------------------------------------------------------------------
# 1. general_embed_by_document_list — document training
# ---------------------------------------------------------------------------


class TestGeneralEmbedByDocumentList:
    """Verify the fix: KnowledgeTask is retained when any document fails."""

    class FakeTask:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            self.id = kwargs.get("id", 1)
            self.completed_count = kwargs.get("completed_count", 0)
            self.deleted = False
            self.save_count = 0

        def save(self):
            self.save_count += 1

        def delete(self):
            self.deleted = True

    class FakeTaskManager:
        def __init__(self):
            self.created = []

        def create(self, **kwargs):
            task = TestGeneralEmbedByDocumentList.FakeTask(**kwargs)
            self.created.append(task)
            return task

    class FakeDocument:
        def __init__(self, doc_id, name):
            self.id = doc_id
            self.name = name
            self.knowledge_base_id = 42
            self.train_status = 0
            self.error_message = None
            self.save_count = 0

        def save(self):
            self.save_count += 1

    def _run_training(self, documents, invoke_document_to_es):
        manager = self.FakeTaskManager()
        func = _load_tasks_function(
            "general_embed_by_document_list",
            KnowledgeTask=SimpleNamespace(objects=manager),
            invoke_document_to_es=invoke_document_to_es,
        )
        func(documents, username="alice", domain="example.com", delete_qa_pairs=True)
        return manager.created[0]

    def test_retains_failed_task_when_document_ingest_returns_error(self):
        """A document-level ERROR must keep the task visible as failed."""
        docs = [self.FakeDocument(1, "bad.md"), self.FakeDocument(2, "ok.md")]
        seen_delete_flags = []

        def invoke_document_to_es(document, delete_qa_pairs=False):
            seen_delete_flags.append(delete_qa_pairs)
            document.train_status = 2 if document.id == 1 else 1

        task = self._run_training(docs, invoke_document_to_es)

        assert task.deleted is False
        assert task.status == "failed"
        assert task.completed_count == 1
        assert seen_delete_flags == [True, True]

    def test_retains_failed_task_and_marks_document_error_on_exception(self):
        """Unexpected ingestion exceptions must set document error state."""
        docs = [self.FakeDocument(1, "bad.md")]

        def invoke_document_to_es(document, delete_qa_pairs=False):
            raise RuntimeError("ingest failed")

        task = self._run_training(docs, invoke_document_to_es)

        assert task.deleted is False
        assert task.status == "failed"
        assert task.completed_count == 0
        assert docs[0].train_status == 2
        assert docs[0].error_message == "训练过程中发生异常"
        assert docs[0].save_count == 1

    def test_deletes_task_only_when_all_documents_succeed(self):
        """The tracking row is cleaned only for a full-success training run."""
        docs = [self.FakeDocument(1, "one.md"), self.FakeDocument(2, "two.md")]

        def invoke_document_to_es(document, delete_qa_pairs=False):
            document.train_status = 1

        task = self._run_training(docs, invoke_document_to_es)

        assert task.deleted is True
        assert task.completed_count == 2


# ---------------------------------------------------------------------------
# 2. rebuild_graph_community_by_instance — graph community rebuild
# ---------------------------------------------------------------------------


class TestRebuildGraphCommunity:
    """Verify: when rebuild fails (result=false), status must NOT be 'completed'."""

    def _get_source(self):
        return _read_function_source("rebuild_graph_community_by_instance")

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
        return _read_function_source("create_graph")

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
        return _read_function_source("update_graph")

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
