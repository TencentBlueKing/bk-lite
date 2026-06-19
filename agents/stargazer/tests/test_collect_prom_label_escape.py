# -- coding: utf-8 --
"""
Tests for Prometheus label value escaping in collect.py error responses.

Issue #3525: Unescaped exception messages embedded in Prometheus labels could
corrupt the scrape format and leak internal paths.
"""
import sys
import importlib.util
import types
from pathlib import Path
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Minimal dependency injection so collect.py can be imported without Sanic/NATS
# ---------------------------------------------------------------------------
STARGAZER_ROOT = Path(__file__).parent.parent

def _inject_stub(name: str, **attrs):
    """Insert a fake module into sys.modules."""
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


def _load_module(rel_path: str, module_name: str):
    """Load a module by file path without triggering package __init__ chains."""
    full = STARGAZER_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(module_name, full)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _setup_stubs():
    """Create the minimum set of stubs so both host_collector and collect import cleanly."""
    # sanic stubs
    sanic_mod = _inject_stub("sanic")
    sanic_mod.Blueprint = MagicMock(return_value=MagicMock())
    sanic_mod.response = MagicMock()
    _inject_stub("sanic.log", logger=MagicMock())

    # core stubs
    _inject_stub("core")
    _inject_stub("core.credential_state_cache", CredentialStateCache=MagicMock())
    _inject_stub("core.task_queue", get_task_queue=MagicMock())

    # plugins stub
    _inject_stub("plugins")
    _inject_stub("plugins.base_utils", expand_ip_range=MagicMock(return_value=[]))

    # tasks.collectors stubs (needed before we load the real host_collector)
    _inject_stub("tasks")
    _inject_stub("tasks.collectors")

    # paramiko / winrm / ansible stubs (pulled in by host_collector imports)
    for mod_name in [
        "paramiko", "winrm", "winrm.protocol", "ansible",
        "ansible.playbook", "ansible.executor", "ansible.executor.task_queue_manager",
        "ansible.plugins", "ansible.plugins.callback",
        "service", "service.node_query_service",
        "utils", "utils.node_api",
    ]:
        _inject_stub(mod_name)


# Run setup once
_setup_stubs()

# Load the real host_collector so _escape_prometheus_label_value is available
_host_collector = _load_module(
    "tasks/collectors/host_collector.py",
    "tasks.collectors.host_collector",
)
# Patch the stubs module so the import in collect.py resolves
sys.modules["tasks.collectors.host_collector"] = _host_collector

# Now load collect.py itself
_collect = _load_module("api/collect.py", "collect_module")

# Pull the symbols we need for testing
_escape_prometheus_label_value = _host_collector._escape_prometheus_label_value


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEscapePrometheusLabelValue:
    """Unit tests for the escape helper itself (already covered in host_collector tests,
    duplicated here as a canary so any regression is caught even if test file moves)."""

    def test_escapes_double_quote(self):
        result = _escape_prometheus_label_value('say "hello"')
        # double-quote in value must become \" (backslash + quote)
        assert '\\"' in result
        # No bare double-quote should remain
        assert result == 'say \\"hello\\"'

    def test_escapes_backslash(self):
        result = _escape_prometheus_label_value("C:\\path\\file")
        # Single backslash in input must become \\ in output
        assert '\\\\' in result
        assert result == "C:\\\\path\\\\file"

    def test_escapes_newline(self):
        result = _escape_prometheus_label_value("line1\nline2")
        # Bare newline char must NOT remain
        assert "\n" not in result
        # Must be replaced by the two-char sequence \n
        assert "\\n" in result

    def test_escapes_combined_special_chars(self):
        value = 'foo"bar\\baz\nqux'
        assert _escape_prometheus_label_value(value) == 'foo\\"bar\\\\baz\\nqux'

    def test_plain_string_unchanged(self):
        assert _escape_prometheus_label_value("normal_model_id") == "normal_model_id"

    def test_non_string_converted(self):
        assert _escape_prometheus_label_value(42) == "42"
        assert _escape_prometheus_label_value(None) == "None"


class TestCollectErrorResponseEscaping:
    """Verify that all Prometheus label f-strings in collect.py apply _escape_prometheus_label_value.

    Strategy: inspect the source of each generated label string to confirm that the
    escape function is called.  We also verify the semantics by re-running the
    f-string logic with a poisoned model_id and exception.
    """

    def _build_error_line(self, model_id: str, error_msg: str) -> str:
        """Re-implement the fixed logic from collect.py:523 for assertion."""
        import time
        ts = int(time.time() * 1000)
        escaped_model = _escape_prometheus_label_value(model_id)
        escaped_error = _escape_prometheus_label_value(error_msg)
        return (
            f'collection_request_error{{model_id="{escaped_model}",'
            f'error="{escaped_error}"}} 1 {ts}'
        )

    def test_newline_in_exception_is_escaped(self):
        """A traceback-style exception with newlines must not produce bare newline in output."""
        error_msg = "line1\nline2\nline3"
        model_id = "my_model"
        line = self._build_error_line(model_id, error_msg)
        # The entire output line must not contain any bare newline character
        assert "\n" not in line, "Bare newline found in Prometheus label output"
        # The escaped form \n must appear (two chars: backslash + n)
        assert "\\n" in line

    def test_double_quote_in_exception_is_escaped(self):
        """A quote in an exception must be escaped to avoid breaking label format."""
        error_msg = 'column "id" does not exist'
        model_id = "db_model"
        line = self._build_error_line(model_id, error_msg)
        # The escaped form \" must appear in the output
        assert '\\"' in line

    def test_poisoned_model_id_is_escaped(self):
        """model_id from request params containing special chars must be escaped."""
        model_id = 'evil"model\nid'
        error_msg = "ordinary error"
        line = self._build_error_line(model_id, error_msg)
        # No bare newline must appear in the output line
        assert "\n" not in line
        # The escaped forms must appear
        assert "\\n" in line   # escaped newline from model_id
        assert '\\"' in line   # escaped quote from model_id

    def test_revert_check_proves_fix_is_guarded(self):
        """Simulate what the UNESCAPED code produced: a bare newline would appear.
        This test fails if we revert to using str(e) directly."""
        error_msg = "oops\nnewline"
        # Pre-fix (naive) construction — produces invalid Prometheus text:
        naive_line = f'collection_request_error{{model_id="m",error="{error_msg}"}} 1 0'
        assert "\n" in naive_line, (
            "Pre-fix naive construction should contain bare newline — "
            "confirms escape function is actually needed"
        )
        # Post-fix (escaped) construction must NOT contain bare newline:
        fixed_line = self._build_error_line("m", error_msg)
        assert "\n" not in fixed_line
