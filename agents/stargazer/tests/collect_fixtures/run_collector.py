# -*- coding: utf-8 -*-
"""
Collector 执行 — 加载 collector 类,调采集方法,拿到 raw_stdout。

入口形态分 2 种（spec.entry_type）：
- "python": importlib 加载模块 + 类,实例化,调 entry_method（默认 list_all_resources）
- "shell":  通过 container.exec_run() 执行 init_script（采集脚本），stdout parse JSON

设计原则：
- 只调采集,不发布、不入库、不推送 NATS。
- 错误明确:导入失败 → CollectorImportError;调用失败 → 透传原始异常。
"""
from __future__ import annotations

import asyncio
import base64
import importlib
import inspect
import io
import json
import tarfile
from pathlib import Path
from typing import Any, Dict, Optional

from tests.collect_fixtures.catalog import Spec
from tests.collect_fixtures.vm_ssh import VMSSH  # noqa: E402


class CollectorImportError(Exception):
    """collector 模块/类无法导入。"""


def _load_collector_class(spec: Spec):
    """动态加载 collector 类。"""
    try:
        module = importlib.import_module(spec.entry_module)
        return getattr(module, spec.entry_class)
    except (ImportError, AttributeError) as e:
        raise CollectorImportError(
            f"无法导入 collector: module={spec.entry_module} class={spec.entry_class}: {e}"
        ) from e


def collect_once(spec: Spec, handle: Optional["ContainerHandle"] = None) -> Any:
    """执行一次采集,返回 raw_stdout（dict / list / str）。

    - spec.entry_type == "python": 动态加载类,实例化,调 entry_method
    - spec.entry_type == "shell":  在 handle 容器内 exec_run 采集脚本,捕获 stdout
    - spec.entry_type == "ssh":    通过 VMSSH 上传脚本到 VM 执行,捕获 stdout
    """
    if spec.entry_type == "shell":
        if handle is None:
            raise ValueError("shell 入口必须传 handle（已启动的容器）")
        return _run_shell(spec, handle)
    if spec.entry_type == "ssh":
        if handle is None:
            raise ValueError("ssh 入口必须传 handle（已启动的 VM 容器）")
        return _run_ssh(spec, handle)
    return _run_python(spec)


def _run_python(spec: Spec) -> Any:
    collector_class = _load_collector_class(spec)
    instance = collector_class(spec.collector_kwargs)
    method = getattr(instance, spec.entry_method)

    if inspect.iscoroutinefunction(method):
        return asyncio.run(method())
    return method()


def _run_shell(spec: Spec, handle: "ContainerHandle") -> Any:
    """在容器内执行采集脚本,stdout 解析为 JSON dict 返回。"""
    script_path = _resolve_shell_script_path(spec)
    interpreter = _detect_interpreter(script_path)
    env = _build_shell_env(spec)

    # 把 host 上的脚本 put_archive 到容器内 /tmp,然后在容器内执行
    remote_script_path = _upload_script_to_container(handle, script_path)

    result = handle.container.exec_run(
        cmd=[interpreter, remote_script_path],
        environment=env,
    )

    # docker SDK 7.x 返回 ExecResult dataclass;旧版本返回 tuple
    if hasattr(result, "exit_code"):
        exit_code = result.exit_code
        output = result.output
    elif isinstance(result, tuple):
        # 旧 docker-py ≤ 4.x 返回 (exit_code: int, output: bytes)
        # 某些中间版本返回 ({"ExitCode": int}, bytes) 或 (ExecResult-like, bytes)
        first = result[0]
        if isinstance(first, dict):
            exit_code = first.get("ExitCode", 0)
        elif hasattr(first, "exit_code"):
            exit_code = first.exit_code
        else:
            exit_code = int(first) if first else 0
        output = result[1]
    else:
        exit_code = 0
        output = result

    output_text = output.decode("utf-8", errors="replace") if isinstance(output, bytes) else str(output)

    if exit_code != 0:
        raise RuntimeError(
            f"shell 脚本执行失败（model_id={spec.model_id}）: "
            f"exit={exit_code} output={output_text[:500]!r}"
        )

    return _parse_shell_stdout(output_text, spec)


def _upload_script_to_container(handle: "ContainerHandle", script_path: Path) -> str:
    """把脚本通过 put_archive 传进容器,返回容器内路径。"""
    remote_name = f"/tmp/{script_path.name}"
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w") as tar:
        data = script_path.read_bytes()
        info = tarfile.TarInfo(name=script_path.name)
        info.size = len(data)
        info.mode = 0o755
        tar.addfile(info, io.BytesIO(data))
    tar_buf.seek(0)
    ok = handle.container.put_archive("/tmp", tar_buf.read())
    if not ok:
        raise RuntimeError(f"put_archive 上传采集脚本失败: {script_path}")
    return remote_name


def _run_ssh(spec: Spec, handle: "ContainerHandle") -> Any:
    """SSH 进 VM 跑采集脚本,stdout parse 为 JSON dict。"""
    from tests.collect_fixtures.docker_lifecycle import _extract_ssh_port

    script_local = _resolve_shell_script_path(spec)
    script_remote = f"/tmp/{spec.model_id}_discover.sh"

    ssh = VMSSH(
        host="127.0.0.1",
        port=_extract_ssh_port(handle),
        user=spec.vm_ssh_user,
        password=spec.vm_ssh_password,
    )
    ssh.connect()
    try:
        _upload_script_via_ssh(ssh, script_local, script_remote)
        ssh.exec(f"chmod +x {script_remote}", check=False)
        run_cmd = f"bash {script_remote}"
        try:
            result = ssh.exec(run_cmd, check=True, timeout=120)
        except RuntimeError as e:
            # VMSSH 在 check=True && exit!=0 时 raise,包成"ssh 脚本执行失败"
            raise RuntimeError(
                f"ssh 脚本执行失败（model_id={spec.model_id}）: {e}"
            ) from e
        if result["exit_code"] != 0:
            raise RuntimeError(
                f"ssh 脚本执行失败（model_id={spec.model_id}）: "
                f"exit={result['exit_code']} stderr={result['stderr'][:500]!r}"
            )
        output_text = result["stdout"]
    finally:
        ssh.close()

    return _parse_shell_stdout(output_text, spec)


def _upload_script_via_ssh(ssh, local_path: Path, remote_path: str) -> None:
    """通过 SSH base64 + heredoc 上传脚本到 VM。"""
    content = local_path.read_text(encoding="utf-8")
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    chunk_size = 700
    chunks = [encoded[i:i + chunk_size] for i in range(0, len(encoded), chunk_size)]
    ssh.exec(f"rm -f {remote_path}", check=False)
    ssh.exec(f"touch {remote_path}", check=False)
    for chunk in chunks:
        ssh.exec(f"echo -n '{chunk}' >> {remote_path}", check=True)
    ssh.exec(
        f"base64 -d < {remote_path} > {remote_path}.tmp && mv {remote_path}.tmp {remote_path}",
        check=True,
    )


def _resolve_shell_script_path(spec: Spec) -> Path:
    """定位采集脚本路径。spec.init_script 承担 shell 脚本路径角色。"""
    script = Path(__file__).parent / "init" / spec.init_script
    if not script.exists():
        raise FileNotFoundError(f"shell 脚本不存在: {script}")
    return script


def _detect_interpreter(script_path: Path) -> str:
    """从 shebang 行检测解释器（sh / bash）。
    如果 shebang 是 bash 则用 bash，否则默认 sh（兼容 alpine 的 ash）。
    若首选解释器不存在，回退到 sh。
    """
    try:
        text = script_path.read_text(encoding="utf-8", errors="replace")
        first_line = text.splitlines()[:1]
        if first_line:
            shebang = first_line[0].strip()
            if "bash" in shebang:
                return "bash"
    except Exception:
        pass
    return "sh"


def _build_shell_env(spec: Spec) -> Dict[str, str]:
    """构造 shell 脚本执行所需的环境变量。

    优先级（高 → 低 覆盖）:
    1. spec.env（catalog 显式声明,优先级最低,先填底）
    2. collector_kwargs.ports（list,生成 REDIS_TARGET_PORTS=逗号分隔）
    3. collector_kwargs.port（单值,生成 REDIS_TARGET_PORTS=单值;向后兼容 redis Spec）
    4. collector_kwargs.host / user / password 等其他字段

    注释：kwargs 字段在 spec.env 之后写入,所以 spec.env["REDIS_TARGET_PORTS"]
    在没有 kwargs.port/ports 时保留;有则被覆盖（这是有意设计,kwargs 是权威）。
    """
    env: Dict[str, str] = {}
    env.update(spec.env)
    kwargs = spec.collector_kwargs
    if "host" in kwargs:
        env["REDIS_TARGET_HOST"] = kwargs["host"]
        env["BK_HOST_INNERIP"] = kwargs["host"]
    # 端口：ports(list)优先于 port(scalar)。list 走 comma-sep,让 redis_sentinel /
    # redis-cluster 这类"多端口探测"对象自然支持。G2.1 引入。
    if "ports" in kwargs and isinstance(kwargs["ports"], (list, tuple)):
        env["REDIS_TARGET_PORTS"] = ",".join(str(int(p)) for p in kwargs["ports"])
    elif "port" in kwargs:
        env["REDIS_TARGET_PORTS"] = str(kwargs["port"])
    if "user" in kwargs:
        env.setdefault("REDIS_USER", kwargs["user"])
    if "password" in kwargs:
        env["REDISCLI_AUTH"] = kwargs["password"]
    return env


def _parse_shell_stdout(text: str, spec: Spec) -> Any:
    """解析 shell 脚本 stdout。

    G2.1 2026-07-07 修复:支持多 JSON 行(redis_default_discover.sh 在多端口探测时
    会逐行 emit_instance,输出 N 个独立 JSON object)。原版实现遇到多行 JSON 时
    只返第一个,导致 sentinel 等多端口对象被吞。

    解析顺序:
    1. 整段当 JSON parse(单 object / 单 array)
    2. 按行 split,收集所有 `{...}` 或 `[...]` 行,逐行 JSON parse
       - 多个 object → 返 list[dict]
       - 单个 object → 返 dict(向后兼容,保持 fixture schema 不变)
    3. 都失败 → 返回原始 text(str fallback)
    """
    text = text.strip()
    if not text:
        return {}
    # 1) 整段 JSON parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2) 按行收集所有 JSON 行(G2.1 修复:不再只返第一个)
    objs: list = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("{") or line.startswith("["):
            try:
                obj = json.loads(line)
                objs.append(obj)
            except json.JSONDecodeError:
                continue
    if objs:
        # 单个 object → 保持 dict(向后兼容 redis Spec 等单 instance 对象)
        # 多个 → 返 list(G2.1:redis_sentinel 多端口场景)
        if len(objs) == 1:
            return objs[0]
        return objs

    # 3) 兜底:原样字符串
    return text
