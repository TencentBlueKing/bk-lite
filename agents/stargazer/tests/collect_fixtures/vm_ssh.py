# -*- coding: utf-8 -*-
"""
VM SSH 通信 — 薄包装 paramiko，用于测试时建的临时 ubuntu VM。

为什么不复用 stargazer core.ssh_client.SSHClient:
- 那个 SSHClient 默认 RejectPolicy，对每次启动的临时 VM 不友好（无 known_hosts）。
- VMSSH 使用场景是 dev/test 临时 VM，不需要严格 host key 校验。
- 因此 VMSSH 用 AutoAddPolicy 直接基于 paramiko 实现。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Optional

# 把 stargazer 根目录加到 sys.path（与 cli.py 一致）
_STARGAZER_ROOT = Path(__file__).parent.parent.parent
if str(_STARGAZER_ROOT) not in sys.path:
    sys.path.insert(0, str(_STARGAZER_ROOT))

import paramiko


class _SSHClient:
    """VMSSH 专用 SSH 客户端：AutoAddPolicy（接受任意 host key）。"""

    def __init__(self, timeout: int = 30, known_hosts_file=None):
        self.timeout = timeout
        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self._known_hosts_file = known_hosts_file

    def connect(self, host: str, username: str,
                password: Optional[str] = None, port: int = 22,
                key_filename: Optional[str] = None) -> None:
        self._client.connect(
            hostname=host,
            port=port,
            username=username,
            password=password,
            key_filename=key_filename,
            timeout=self.timeout,
            banner_timeout=self.timeout,
            allow_agent=False,
            look_for_keys=False,
        )

    def execute_command(self, command, timeout=None):
        """返回 (stdout, stderr, exit_code, exec_time) 元组。"""
        start = time.time()
        _stdin, stdout, stderr = self._client.exec_command(
            command, timeout=timeout or self.timeout,
        )
        exit_code = stdout.channel.recv_exit_status()
        stdout_bytes = stdout.read().decode("utf-8", errors="replace")
        stderr_bytes = stderr.read().decode("utf-8", errors="replace")
        return stdout_bytes, stderr_bytes, exit_code, time.time() - start

    def close(self):
        try:
            self._client.close()
        except Exception:
            pass


class VMSSH:
    """SSH 进 VM 跑命令的薄包装。"""

    def __init__(self, host: str, port: int, user: str, password: str, timeout: int = 30):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.timeout = timeout
        self._client: Optional[Any] = None

    def connect(self):
        """建立 SSH 连接。"""
        self._client = _SSHClient(timeout=self.timeout)
        # _SSHClient.connect 已经把 allow_agent/look_for_keys 写死为 False，这里不要再传
        try:
            self._client.connect(
                host=self.host, port=self.port, username=self.user, password=self.password,
            )
        except TypeError:
            # 兼容：_SSHClient.connect 可能用 host= 或 hostname= 关键字
            self._client.connect(
                hostname=self.host, port=self.port, username=self.user, password=self.password,
            )

    def exec(self, command: str, check: bool = True, timeout: Optional[int] = None) -> dict:
        """执行一条命令，返回 {stdout, stderr, exit_code}。

        兼容两种返回格式：
        - 4 元组 (stdout, stderr, exit_code, exec_time) — 本模块 _SSHClient.execute_command
        - SSHResult dataclass (stdout, stderr, exit_status, exec_time) — stargazer SSHClient.execute_command
        """
        if self._client is None:
            raise RuntimeError("VMSSH not connected, call connect() first")
        result = self._client.execute_command(command, timeout=timeout)
        # duck-type: dataclass 有 stdout/stderr/exit_status；tuple 用位置
        if hasattr(result, "exit_status"):
            stdout = result.stdout
            stderr = result.stderr
            exit_code = result.exit_status
        else:
            stdout, stderr, exit_code, _ = result
        if check and exit_code != 0:
            raise RuntimeError(
                f"SSH cmd failed (exit={exit_code}): {command[:200]!r}\n"
                f"stdout={stdout[:500]!r}\nstderr={stderr[:500]!r}"
            )
        return {"stdout": stdout, "stderr": stderr, "exit_code": exit_code}

    def close(self):
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None