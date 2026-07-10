"""normalize_script_line_endings 纯函数单测。"""

import pytest

from apps.job_mgmt.constants import ScriptType
from apps.job_mgmt.services.script_normalize import normalize_script_line_endings

pytestmark = pytest.mark.unit


class TestNormalizeScriptLineEndings:
    """脚本换行符规范化函数: CRLF/CR → LF，Windows 原生类型保留。"""

    def test_none_returns_empty(self):
        assert normalize_script_line_endings(None, ScriptType.SHELL) == ""

    def test_empty_string_returns_empty(self):
        assert normalize_script_line_endings("", ScriptType.SHELL) == ""

    def test_shell_crlf_to_lf(self):
        assert normalize_script_line_endings("echo\r\nhi", ScriptType.SHELL) == "echo\nhi"

    def test_python_crlf_to_lf(self):
        assert normalize_script_line_endings("import os\r\nprint(1)\r\n", ScriptType.PYTHON) == "import os\nprint(1)\n"

    def test_bare_cr_to_lf(self):
        """老 Mac 编辑器残留的裸 \\r 也应转 LF。"""
        assert normalize_script_line_endings("a\rb\rc", ScriptType.SHELL) == "a\nb\nc"

    def test_mixed_crlf_and_cr(self):
        assert normalize_script_line_endings("a\r\nb\rc\nd", ScriptType.SHELL) == "a\nb\nc\nd"

    def test_already_lf_unchanged(self):
        lf = "#!/bin/bash\necho hi\n"
        assert normalize_script_line_endings(lf, ScriptType.SHELL) == lf

    def test_idempotent(self):
        once = normalize_script_line_endings("echo\r\n", ScriptType.SHELL)
        twice = normalize_script_line_endings(once, ScriptType.SHELL)
        assert once == twice == "echo\n"

    def test_bat_preserves_crlf(self):
        crlf = "@echo off\r\nset x=1\r\n"
        assert normalize_script_line_endings(crlf, ScriptType.BAT) == crlf

    def test_powershell_preserves_crlf(self):
        crlf = "Write-Host hi\r\n$x = 1\r\n"
        assert normalize_script_line_endings(crlf, ScriptType.POWERSHELL) == crlf

    def test_powershell_preserves_bare_cr(self):
        # Windows PowerShell ISE 等可能产生混合
        cr = "Write-Host hi\r$x = 1"
        assert normalize_script_line_endings(cr, ScriptType.POWERSHELL) == cr

    def test_unknown_script_type_treated_as_unix(self):
        """未注册的 script_type 按 LF 处理,与 worker 兜底行为一致。"""
        assert normalize_script_line_endings("echo\r\n", "bash") == "echo\n"

    def test_unicode_preserved(self):
        """含中文的 CRLF 脚本中文不应被破坏。"""
        s = "# 中文注释\r\necho 你好\r\n"
        assert normalize_script_line_endings(s, ScriptType.SHELL) == "# 中文注释\necho 你好\n"

    def test_empty_script_type_treated_as_unix(self):
        """空 script_type 不在 BAT/POWERSHELL 白名单, 按 LF 处理。"""
        assert normalize_script_line_endings("echo\r\n", "") == "echo\n"
