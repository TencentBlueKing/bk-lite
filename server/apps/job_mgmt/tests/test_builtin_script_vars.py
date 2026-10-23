"""内置脚本变量：引用检测、字面量转义，以及下发副本不回写原文。"""

import subprocess
import sys

import pytest

from apps.job_mgmt.constants import ExecutionStatus, JobType, ScriptType, TargetSource
from apps.job_mgmt.models import JobExecution
from apps.job_mgmt.services.builtin_script_vars import render_builtin_script_vars, resolve_builtin_script_var_values
from apps.job_mgmt.services.script_execution_runner import ScriptExecutionRunner
from apps.system_mgmt.models.user import User

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

VALUES = {
    "BK_JOB_USER": "alice",
    "BK_JOB_USER_NAME": "王宏基",
    "BK_JOB_ID": "42",
}
HOSTILE_NAME = "a'; $(touch /tmp/bklite-builtin-var-pwned)\nrm -rf /"


def _render(content, script_type, values=None):
    return render_builtin_script_vars(content, script_type, values or VALUES)


class TestReferenceDetection:
    def test_shell_without_reference_is_unchanged(self):
        assert _render("echo hi", ScriptType.SHELL) == "echo hi"

    def test_shell_user_name_does_not_count_as_user(self):
        rendered = _render('echo "$BK_JOB_USER_NAME"', ScriptType.SHELL)
        assert "BK_JOB_USER=" not in rendered
        assert rendered.startswith("BK_JOB_USER_NAME=")

    def test_shell_brace_form_and_plain_form(self):
        rendered = _render('echo "${BK_JOB_USER}" "$BK_JOB_ID"', ScriptType.SHELL)
        assert rendered.startswith("BK_JOB_USER=")
        assert "BK_JOB_ID=" in rendered
        assert "BK_JOB_USER_NAME=" not in rendered

    def test_python_word_and_shell_dollar_are_separate(self):
        assert _render("print($BK_JOB_USER)", ScriptType.PYTHON) == "print($BK_JOB_USER)"
        assert _render("print(BK_JOB_ID)", ScriptType.PYTHON).startswith("BK_JOB_ID = ")

    def test_bat_percent_form(self):
        rendered = _render("echo %BK_JOB_USER%", ScriptType.BAT)
        assert rendered.startswith('set "BK_JOB_USER=')
        assert "%BK_JOB_USER%" in rendered.split("\n", 1)[1]

    def test_shebang_stays_first(self):
        rendered = _render('#!/bin/bash\necho "$BK_JOB_ID"\n', ScriptType.SHELL)
        assert rendered.startswith("#!/bin/bash\nBK_JOB_ID=")


class TestLiteralEscaping:
    def test_shell_hostile_name_is_quoted(self):
        rendered = _render('printf "%s" "$BK_JOB_USER_NAME"', ScriptType.SHELL, {"BK_JOB_USER_NAME": HOSTILE_NAME})
        completed = subprocess.run(["bash", "-c", rendered], capture_output=True, text=True, check=False)
        assert completed.returncode == 0
        assert completed.stdout == HOSTILE_NAME

    def test_python_hostile_name_is_literal(self):
        rendered = _render("print(BK_JOB_USER_NAME, end='')", ScriptType.PYTHON, {"BK_JOB_USER_NAME": HOSTILE_NAME})
        completed = subprocess.run([sys.executable, "-c", rendered], capture_output=True, text=True, check=False)
        assert completed.returncode == 0
        assert completed.stdout == HOSTILE_NAME

    def test_powershell_quotes_single_quote(self):
        rendered = _render("Write-Output $BK_JOB_USER_NAME", ScriptType.POWERSHELL, {"BK_JOB_USER_NAME": "a'b"})
        assert "$BK_JOB_USER_NAME = 'a''b'" in rendered

    def test_bat_percent_quote_newline_and_trailing_backslash(self):
        rendered = _render(
            "echo %BK_JOB_USER_NAME%",
            ScriptType.BAT,
            {"BK_JOB_USER_NAME": 'a%b"c\n\\'},
        )
        assert rendered.split("\n", 1)[0] == 'set "BK_JOB_USER_NAME=a%%b\'c \\\\"'

    def test_empty_display_name_still_assigns(self):
        rendered = _render('echo "$BK_JOB_USER_NAME"', ScriptType.SHELL, {"BK_JOB_USER_NAME": ""})
        assert rendered.startswith("BK_JOB_USER_NAME=''\n")


class TestResolveAndDispatch:
    def test_resolve_uses_executor_domain_and_job_id(self):
        User.objects.create(
            username="alice",
            display_name="王宏基",
            domain="corp.example",
            email="alice@example.com",
            password="x",
        )
        User.objects.create(
            username="alice",
            display_name="另一个域",
            domain="domain.com",
            email="other@example.com",
            password="x",
        )
        execution = JobExecution.objects.create(
            name="builtin",
            job_type=JobType.SCRIPT,
            status=ExecutionStatus.PENDING,
            script_type=ScriptType.SHELL,
            script_content='echo "$BK_JOB_USER"',
            executor_user="alice",
            domain="corp.example",
            team=[1],
        )
        values = resolve_builtin_script_var_values(execution)
        assert values == {
            "BK_JOB_USER": "alice",
            "BK_JOB_USER_NAME": "王宏基",
            "BK_JOB_ID": str(execution.id),
        }

    def test_missing_user_yields_empty_display_name(self):
        execution = JobExecution.objects.create(
            name="builtin",
            job_type=JobType.SCRIPT,
            status=ExecutionStatus.PENDING,
            script_type=ScriptType.SHELL,
            script_content="echo hi",
            executor_user="missing",
            domain="corp.example",
            team=[1],
        )
        assert resolve_builtin_script_var_values(execution)["BK_JOB_USER_NAME"] == ""

    def test_runner_sends_rendered_copy_and_keeps_stored_script(self):
        from unittest.mock import patch

        User.objects.create(
            username="alice",
            display_name=HOSTILE_NAME,
            domain="domain.com",
            email="alice@example.com",
            password="x",
        )
        original = 'echo "$BK_JOB_USER_NAME"'
        execution = JobExecution.objects.create(
            name="builtin-dispatch",
            job_type=JobType.SCRIPT,
            status=ExecutionStatus.PENDING,
            script_type=ScriptType.SHELL,
            script_content=original,
            target_source=TargetSource.NODE_MGMT,
            target_list=[{"node_id": "n1", "name": "h", "ip": "1.1.1.1"}],
            executor_user="alice",
            domain="domain.com",
            team=[1],
        )
        with patch("apps.job_mgmt.services.script_execution_runner.ensure_stream_sync"), patch(
            "apps.job_mgmt.services.script_execution_runner.publish_done_sentinel"
        ), patch("apps.job_mgmt.services.script_execution_runner.ExecutionTimeoutService.renew_running", return_value=execution.id), patch(
            "apps.job_mgmt.services.script_execution_runner.Executor"
        ) as executor:
            executor.return_value.execute_local_stream.return_value = "ok"
            ScriptExecutionRunner(execution.id).run()

        sent = executor.return_value.execute_local_stream.call_args.args[0]
        assert sent.startswith("BK_JOB_USER_NAME=")
        assert original in sent
        completed = subprocess.run(["bash", "-c", sent], capture_output=True, text=True, check=False)
        assert completed.returncode == 0
        assert completed.stdout.strip() == HOSTILE_NAME
        execution.refresh_from_db()
        assert execution.script_content == original

    def test_params_are_applied_after_builtin_vars(self):
        rendered = _render('echo "$BK_JOB_ID" "$1"', ScriptType.SHELL)
        merged = ScriptExecutionRunner.merge_script_with_params(None, rendered, "a", ScriptType.SHELL)
        assert merged.startswith("set -- a\n")
        assert "BK_JOB_ID=" in merged
