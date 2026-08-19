"""技能包参数运行时注入：按包隔离、fail-closed、脱敏、并发不串染。"""

from __future__ import annotations

import sys
import threading
import time
from types import SimpleNamespace

import pytest

from apps.opspilot.services.skill_executor.path_rewriting_backend import PathRewritingBackend

pytestmark = pytest.mark.unit


class RecordingInner:
    def __init__(self, delay: float = 0.0):
        self._env = {"PATH": "/bin", "HOME": "/sandbox"}
        self.seen: list[tuple[str, dict[str, str]]] = []
        self.delay = delay

    def execute(self, command: str, *, timeout=None):
        if self.delay:
            time.sleep(self.delay)
        snapshot = dict(self._env)
        self.seen.append((command, snapshot))
        token = snapshot.get("TOKEN") or snapshot.get("A_TOKEN") or snapshot.get("B_TOKEN") or ""
        return SimpleNamespace(output=f"ran token={token}", exit_code=0)


def _backend(tmp_path, inner, params=None, secrets=None):
    return PathRewritingBackend(
        inner=inner,
        sandbox_dir=tmp_path,
        skills_root="/skills",
        params_by_package=params or {},
        secret_values=secrets or [],
    )


def test_execute_sandbox_deny_returns_result_instead_of_raising(tmp_path):
    """黑名单命令应回传工具结果，避免 PermissionError 导致前端「未收到结果事件」。"""
    inner = RecordingInner()
    backend = _backend(tmp_path, inner, params={"ad-domain-ops": {"AD_HOST": "dc"}})
    result = backend.execute("echo $AD_HOST $AD_BIND_DN $AD_BASE_DN")
    assert inner.seen == []
    assert result.exit_code == 126
    assert "命令被黑名单拦截" in result.output or "沙箱拒绝" in result.output
    assert "[OPSPILOT_SKILL_RESULT]" in result.output
    assert "不要探测环境变量" in result.output


def test_execute_injects_only_matched_package_and_restores(tmp_path):
    inner = RecordingInner()
    original = dict(inner._env)
    backend = _backend(
        tmp_path,
        inner,
        params={
            "pkg-a": {"A_TOKEN": "aaa", "SHARED": "from-a"},
            "pkg-b": {"B_TOKEN": "bbb", "SHARED": "from-b"},
        },
    )
    result = backend.execute("python /skills/pkg-a/run.sh")
    assert inner.seen[0][1]["A_TOKEN"] == "aaa"
    assert inner.seen[0][1]["SHARED"] == "from-a"
    assert "B_TOKEN" not in inner.seen[0][1]
    assert inner._env == original
    assert "aaa" in result.output


def test_fail_closed_zero_hits_does_not_inject_or_hint(tmp_path):
    inner = RecordingInner()
    backend = _backend(tmp_path, inner, params={"pkg-a": {"A_TOKEN": "aaa"}})
    result = backend.execute("ls /tmp/x")
    assert "A_TOKEN" not in inner.seen[0][1]
    assert "请用" not in result.output


def test_fail_closed_multiple_hits_skips_inject_and_hints(tmp_path):
    inner = RecordingInner()
    backend = _backend(
        tmp_path,
        inner,
        params={"pkg-a": {"A_TOKEN": "aaa"}, "pkg-b": {"B_TOKEN": "bbb"}},
    )
    result = backend.execute("python /skills/pkg-a/a.py /skills/pkg-b/b.py")
    assert "A_TOKEN" not in inner.seen[0][1]
    assert "B_TOKEN" not in inner.seen[0][1]
    assert "请用 `/skills/<包名>/` 绝对路径调用对应技能包" in result.output


def test_redact_replaces_password_values_only(tmp_path):
    inner = RecordingInner()

    def execute(command, *, timeout=None):
        inner.seen.append((command, dict(inner._env)))
        return SimpleNamespace(output="user=svc secret=s3cret host=dc.local", exit_code=0)

    inner.execute = execute
    backend = _backend(
        tmp_path,
        inner,
        params={"pkg-a": {"USER": "svc", "PASS": "s3cret"}},
        secrets=["s3cret"],
    )
    result = backend.execute("python /skills/pkg-a/run.sh")
    assert "s3cret" not in result.output
    assert "***" in result.output
    assert "dc.local" in result.output
    assert "svc" in result.output


def test_execute_strips_export_prefix_and_still_injects_package_env(tmp_path):
    inner = RecordingInner()
    backend = _backend(tmp_path, inner, params={"ad-domain-ops": {"AD_TIMEOUT": "10"}})
    backend.execute('export AD_TIMEOUT=10 && python /skills/ad-domain-ops/scripts/ad_search.py --query "administrator"')
    command, snapshot = inner.seen[0]
    assert sys.executable in command or command.split()[0].strip('"') == "python"
    assert "/usr/bin/" not in command
    assert snapshot["AD_TIMEOUT"] == "10"


def test_execute_rewrites_usr_bin_python3_to_service_interpreter(tmp_path):
    inner = RecordingInner()
    backend = _backend(tmp_path, inner, params={"ad-domain-ops": {"AD_TIMEOUT": "10"}})
    backend.execute('/usr/bin/python3 /skills/ad-domain-ops/scripts/ad_search.py --query "administrator"')
    command, snapshot = inner.seen[0]
    assert sys.executable in command or command.startswith('"')
    assert "/usr/bin/python3" not in command
    assert snapshot["AD_TIMEOUT"] == "10"


def test_concurrent_execute_does_not_leak_across_packages(tmp_path):
    inner = RecordingInner(delay=0.08)
    backend = _backend(
        tmp_path,
        inner,
        params={"pkg-a": {"A_TOKEN": "aaa"}, "pkg-b": {"B_TOKEN": "bbb"}},
    )
    errors: list[BaseException] = []

    def run(command: str):
        try:
            backend.execute(command)
        except BaseException as exc:  # pragma: no cover - 测试收集
            errors.append(exc)

    threads = [
        threading.Thread(target=run, args=("python /skills/pkg-a/run.sh",)),
        threading.Thread(target=run, args=("python /skills/pkg-b/run.sh",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    assert len(inner.seen) == 2
    by_token = {snapshot.get("A_TOKEN") or snapshot.get("B_TOKEN"): snapshot for _, snapshot in inner.seen}
    assert by_token["aaa"]["A_TOKEN"] == "aaa"
    assert "B_TOKEN" not in by_token["aaa"]
    assert by_token["bbb"]["B_TOKEN"] == "bbb"
    assert "A_TOKEN" not in by_token["bbb"]
    assert inner._env == {"PATH": "/bin", "HOME": "/sandbox"}
