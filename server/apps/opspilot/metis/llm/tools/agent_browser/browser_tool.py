"""agent-browser CLI 工具包装器。"""

import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from langchain_core.tools import tool
from loguru import logger

from apps.opspilot.utils.execution_interrupt import is_interrupt_requested

_DEFAULT_SCREENSHOT_DIR = Path(__file__).resolve().parents[6] / "tmp" / "agent-browser"
_URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+")
_REF_PATTERN = re.compile(r"ref=([A-Za-z0-9_-]+)")
_SECURITY_INTERSTITIAL_TEXTS = (
    "此网站不支持安全连接",
    "继续访问网站",
    "Continue to site",
    "Your connection is not secure",
)


def _ensure_directory(path: Path) -> Path:
    """确保目录存在。"""
    path.mkdir(parents=True, exist_ok=True)
    return path


def _build_default_screenshot_path(filename: Optional[str] = None, image_format: str = "png") -> str:
    """构建默认截图输出路径。"""
    screenshot_dir = _ensure_directory(_DEFAULT_SCREENSHOT_DIR)
    normalized_format = (image_format or "png").lower()
    if normalized_format not in {"png", "jpeg", "jpg"}:
        normalized_format = "png"
    normalized_suffix = ".jpg" if normalized_format == "jpg" else f".{normalized_format}"

    if filename:
        output_path = screenshot_dir / filename
        if output_path.suffix.lower() not in {".png", ".jpeg", ".jpg"}:
            output_path = output_path.with_suffix(normalized_suffix)
        return str(output_path.resolve())

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_path = screenshot_dir / f"agent-browser-{timestamp}{normalized_suffix}"
    return str(output_path.resolve())


def _extract_url_candidates(*texts: str) -> list[str]:
    """从文本中提取 URL 候选，便于排查跳转或拦截问题。"""
    seen = set()
    results = []
    for text in texts:
        if not text:
            continue
        for url in _URL_PATTERN.findall(text):
            if url not in seen:
                seen.add(url)
                results.append(url)
    return results


def _extract_security_interstitial_continue_ref(snapshot_result: Dict[str, Any]) -> str:
    """从 snapshot 结果中提取安全提示页“继续访问网站”按钮 ref。"""
    if not snapshot_result.get("success"):
        return ""

    stdout = snapshot_result.get("stdout") or ""
    if not stdout:
        return ""

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return ""

    data = payload.get("data") or {}
    snapshot_text = data.get("snapshot") or ""
    refs = data.get("refs") or {}
    if not isinstance(refs, dict):
        return ""

    if not any(text in snapshot_text for text in _SECURITY_INTERSTITIAL_TEXTS):
        return ""

    for ref, metadata in refs.items():
        if not isinstance(metadata, dict):
            continue
        name = str(metadata.get("name") or "")
        role = str(metadata.get("role") or "")
        if name in {"继续访问网站", "Continue to site"} and role == "button":
            return f"@{ref}"

    for line in snapshot_text.splitlines():
        if "继续访问网站" not in line and "Continue to site" not in line:
            continue
        matched_ref = _REF_PATTERN.search(line)
        if matched_ref:
            return f"@{matched_ref.group(1)}"

    return ""


def _run_security_interstitial_recovery(session_name: str = "", timeout: int = 120) -> Dict[str, Any]:
    """检测并尝试跨过 HTTP 安全提示页。"""
    snapshot_result = _run_snapshot_command(interactive_only=True, compact=True, session_name=session_name, timeout=timeout)
    continue_selector = _extract_security_interstitial_continue_ref(snapshot_result)
    if not continue_selector:
        return {
            "success": False,
            "detected": False,
            "continue_selector": "",
            "snapshot_result": snapshot_result,
            "click_result": None,
            "wait_result": None,
            "error": snapshot_result.get("error") if not snapshot_result.get("success") else "未检测到可继续访问的安全提示页。",
        }

    click_result = _run_agent_browser_command(command=[*_build_session_flags(session_name), "click", continue_selector], timeout=timeout)
    if not click_result.get("success"):
        return {
            "success": False,
            "detected": True,
            "continue_selector": continue_selector,
            "snapshot_result": snapshot_result,
            "click_result": click_result,
            "wait_result": None,
            "error": click_result.get("error"),
        }

    wait_result = _run_wait_command(load_state="networkidle", session_name=session_name, timeout=timeout)
    return {
        "success": bool(wait_result.get("success")),
        "detected": True,
        "continue_selector": continue_selector,
        "snapshot_result": snapshot_result,
        "click_result": click_result,
        "wait_result": wait_result,
        "error": wait_result.get("error"),
    }


def _build_session_flags(session_name: str = "") -> list[str]:
    """构建 agent-browser 会话参数。"""
    normalized_session = (session_name or "").strip()
    if not normalized_session:
        return []
    return ["--session", normalized_session]


def _find_agent_browser_binary() -> Optional[str]:
    """查找 agent-browser CLI 二进制路径。"""
    configured_path = os.getenv("AGENT_BROWSER_CLI")
    if configured_path:
        logger.info(f"agent_browser: 使用环境变量 AGENT_BROWSER_CLI 指定的二进制: {configured_path}")
        return configured_path
    discovered_path = shutil.which("agent-browser")
    logger.info(f"agent_browser: PATH 中查找到的 agent-browser 二进制: {discovered_path}")
    return discovered_path


def _should_enable_headed_mode() -> bool:
    """判断是否启用 agent-browser 有头模式。"""
    browser_headed_env = os.getenv("AGENT_BROWSER_HEADED")
    if browser_headed_env is not None:
        return browser_headed_env.lower() in ("true", "1", "yes")

    browser_headless_env = os.getenv("AGENT_BROWSER_HEADLESS")
    if browser_headless_env is not None:
        return browser_headless_env.lower() in ("false", "0", "no")

    try:
        if getattr(settings, "configured", False) and getattr(settings, "DEBUG", False):
            logger.info("agent_browser: DEBUG 模式下自动启用 headed 模式，便于本地调试")
            return True
    except ImproperlyConfigured:
        logger.info("agent_browser: Django settings 未配置，跳过 DEBUG headed 自动判断")

    return False


def _run_agent_browser_command(command: list[str], timeout: int, execution_id: str = "") -> Dict[str, Any]:
    """执行 agent-browser CLI 命令并返回结构化结果。"""
    logger.info(f"agent_browser: 准备执行 CLI，command={command}, timeout={timeout}s, execution_id={execution_id!r}")
    binary = _find_agent_browser_binary()
    if not binary:
        logger.warning("agent_browser: 未找到 agent-browser CLI，无法进入 subprocess 执行阶段")
        return {
            "success": False,
            "command": command,
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "error": "未找到 agent-browser CLI，请先执行 `npm install -g agent-browser && agent-browser install`，或设置 AGENT_BROWSER_CLI 环境变量。",
        }

    full_command = [binary, "--json"]
    if _should_enable_headed_mode():
        full_command.append("--headed")
    full_command.extend(command)
    logger.info(f"agent_browser: 即将执行 subprocess 命令: {' '.join(full_command)}")

    started_at = time.monotonic()
    process = None
    try:
        process = subprocess.Popen(
            full_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
            encoding="utf-8",
            errors="replace",
        )
        stdout = ""
        stderr = ""
        while True:
            if execution_id and is_interrupt_requested(execution_id):
                logger.info(f"agent_browser: 检测到中断请求，准备终止 CLI, execution_id={execution_id}")
                process.terminate()
                try:
                    stdout, stderr = process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    stdout, stderr = process.communicate()
                return {
                    "success": False,
                    "command": full_command,
                    "exit_code": process.returncode,
                    "stdout": stdout,
                    "stderr": stderr,
                    "error": "agent-browser 执行已中断",
                    "interrupted": True,
                }

            if time.monotonic() - started_at > timeout:
                logger.warning(f"agent_browser: subprocess 执行超时, timeout={timeout}s")
                process.terminate()
                try:
                    stdout, stderr = process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    stdout, stderr = process.communicate()
                return {
                    "success": False,
                    "command": full_command,
                    "exit_code": process.returncode,
                    "stdout": stdout,
                    "stderr": stderr,
                    "error": f"agent-browser 执行超时（>{timeout}s）",
                }

            if process.poll() is not None:
                stdout, stderr = process.communicate()
                logger.info(f"agent_browser: subprocess 执行完成, exit_code={process.returncode}, stdout_len={len(stdout)}, stderr_len={len(stderr)}")
                completed = subprocess.CompletedProcess(full_command, process.returncode, stdout, stderr)
                break

            time.sleep(0.2)
    except OSError as exc:
        logger.exception(f"agent_browser: subprocess 启动失败: {exc}")
        return {
            "success": False,
            "command": full_command,
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "error": f"agent-browser 执行失败: {exc}",
        }

    success = completed.returncode == 0
    stdout_preview = completed.stdout[:500]
    stderr_preview = completed.stderr[:500]
    url_candidates = _extract_url_candidates(" ".join(full_command), completed.stdout, completed.stderr)
    if success:
        logger.info(
            f"agent_browser: CLI 返回成功结果, stdout_preview={stdout_preview!r}, stderr_preview={stderr_preview!r}, url_candidates={url_candidates}"
        )
    else:
        logger.warning(
            "agent_browser: CLI 返回非 0 退出码, "
            f"exit_code={completed.returncode}, stderr_preview={stderr_preview!r}, stdout_preview={stdout_preview!r}, "
            f"url_candidates={url_candidates}"
        )
    return {
        "success": success,
        "command": full_command,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "stdout_preview": stdout_preview,
        "stderr_preview": stderr_preview,
        "url_candidates": url_candidates,
        "error": None if success else (completed.stderr.strip() or completed.stdout.strip() or "agent-browser 执行失败"),
    }


def _run_snapshot_command(
    interactive_only: bool = True,
    compact: bool = True,
    max_depth: int = 0,
    selector: str = "",
    session_name: str = "",
    timeout: int = 120,
    execution_id: str = "",
) -> Dict[str, Any]:
    """执行 snapshot 命令的内部帮助函数。"""
    command_args = [*_build_session_flags(session_name), "snapshot"]
    if interactive_only:
        command_args.append("-i")
    if compact:
        command_args.append("-c")
    if max_depth > 0:
        command_args.extend(["-d", str(max_depth)])
    if selector:
        command_args.extend(["-s", selector])
    return _run_agent_browser_command(command=command_args, timeout=timeout, execution_id=execution_id)


def _run_wait_command(
    selector_or_ms: str = "",
    text: str = "",
    url_pattern: str = "",
    load_state: str = "",
    state: str = "",
    js_condition: str = "",
    session_name: str = "",
    timeout: int = 120,
    execution_id: str = "",
) -> Dict[str, Any]:
    """执行 wait 命令的内部帮助函数。"""
    command_args = [*_build_session_flags(session_name), "wait"]
    if selector_or_ms:
        command_args.append(selector_or_ms)
    if text:
        command_args.extend(["--text", text])
    if url_pattern:
        command_args.extend(["--url", url_pattern])
    if load_state:
        command_args.extend(["--load", load_state])
    if state:
        command_args.extend(["--state", state])
    if js_condition:
        command_args.extend(["--fn", js_condition])
    return _run_agent_browser_command(command=command_args, timeout=timeout, execution_id=execution_id)


def _run_screenshot_command(
    filename: str = "",
    full_page: bool = False,
    annotate: bool = False,
    image_format: str = "png",
    session_name: str = "",
    timeout: int = 120,
    execution_id: str = "",
) -> Dict[str, Any]:
    """执行 screenshot 命令的内部帮助函数。"""
    screenshot_path = _build_default_screenshot_path(filename=filename or None, image_format=image_format)
    command_args = [*_build_session_flags(session_name), "screenshot"]
    if full_page:
        command_args.append("--full")
    if annotate:
        command_args.append("--annotate")
    if image_format:
        command_args.extend(["--screenshot-format", image_format])
    command_args.append(screenshot_path)

    result = _run_agent_browser_command(command=command_args, timeout=timeout, execution_id=execution_id)
    result["screenshot_path"] = screenshot_path
    return result


def _run_open_wait_and_snapshot(
    url: str,
    session_name: str = "",
    load_state: str = "networkidle",
    wait_ms: int = 0,
    interactive_only: bool = True,
    compact: bool = True,
    timeout: int = 120,
    execution_id: str = "",
) -> Dict[str, Any]:
    """执行 open + wait + snapshot 的内部组合流程。"""
    if not url:
        return {
            "success": False,
            "error": "url 不能为空。",
            "open_result": None,
            "wait_result": None,
            "snapshot_result": None,
            "interstitial_result": None,
        }

    open_result = _run_agent_browser_command(command=[*_build_session_flags(session_name), "open", url], timeout=timeout, execution_id=execution_id)
    if not open_result.get("success"):
        interstitial_result = _run_security_interstitial_recovery(session_name=session_name, timeout=timeout)
        if interstitial_result.get("success"):
            wait_result = None
            if load_state:
                wait_result = _run_wait_command(
                    selector_or_ms="",
                    load_state=load_state,
                    session_name=session_name,
                    timeout=timeout,
                    execution_id=execution_id,
                )
                if not wait_result.get("success"):
                    return {
                        "success": False,
                        "error": wait_result.get("error"),
                        "open_result": open_result,
                        "wait_result": wait_result,
                        "snapshot_result": None,
                        "interstitial_result": interstitial_result,
                    }

            if wait_ms > 0:
                wait_result = _run_wait_command(
                    selector_or_ms=str(wait_ms),
                    session_name=session_name,
                    timeout=timeout,
                    execution_id=execution_id,
                )
                if not wait_result.get("success"):
                    return {
                        "success": False,
                        "error": wait_result.get("error"),
                        "open_result": open_result,
                        "wait_result": wait_result,
                        "snapshot_result": None,
                        "interstitial_result": interstitial_result,
                    }

            snapshot_result = _run_snapshot_command(
                interactive_only=interactive_only,
                compact=compact,
                session_name=session_name,
                timeout=timeout,
                execution_id=execution_id,
            )
            return {
                "success": bool(snapshot_result.get("success")),
                "error": snapshot_result.get("error"),
                "open_result": open_result,
                "wait_result": wait_result,
                "snapshot_result": snapshot_result,
                "interstitial_result": interstitial_result,
            }

        return {
            "success": False,
            "error": open_result.get("error"),
            "open_result": open_result,
            "wait_result": None,
            "snapshot_result": None,
            "interstitial_result": interstitial_result,
        }

    wait_result = None
    if load_state:
        wait_result = _run_wait_command(
            selector_or_ms="",
            load_state=load_state,
            session_name=session_name,
            timeout=timeout,
            execution_id=execution_id,
        )
        if not wait_result.get("success"):
            return {
                "success": False,
                "error": wait_result.get("error"),
                "open_result": open_result,
                "wait_result": wait_result,
                "snapshot_result": None,
            }

    if wait_ms > 0:
        wait_result = _run_wait_command(
            selector_or_ms=str(wait_ms),
            session_name=session_name,
            timeout=timeout,
            execution_id=execution_id,
        )
        if not wait_result.get("success"):
            return {
                "success": False,
                "error": wait_result.get("error"),
                "open_result": open_result,
                "wait_result": wait_result,
                "snapshot_result": None,
            }

    snapshot_result = _run_snapshot_command(
        interactive_only=interactive_only,
        compact=compact,
        session_name=session_name,
        timeout=timeout,
        execution_id=execution_id,
    )
    return {
        "success": bool(snapshot_result.get("success")),
        "error": snapshot_result.get("error"),
        "open_result": open_result,
        "wait_result": wait_result,
        "snapshot_result": snapshot_result,
        "interstitial_result": None,
    }


@tool(parse_docstring=True)
def agent_browser_run(command_args: list[str], timeout: int = 120, config: Optional[dict] = None) -> Dict[str, Any]:
    """
    执行 agent-browser CLI 命令，用于浏览器自动化能力验证。

    Args:
        command_args: 传递给 agent-browser 的命令参数列表，例如 ["open", "https://example.com"] 或 ["snapshot", "-i"]。
        timeout: 命令超时时间（秒），默认 120 秒。

    Returns:
        结构化执行结果，包含 success、command、exit_code、stdout、stderr、error。
    """
    logger.info(f"agent_browser_run: 进入工具执行, command_args={command_args}, timeout={timeout}")

    if not command_args:
        logger.warning("agent_browser_run: 参数校验失败，command_args 为空")
        return {
            "success": False,
            "command": [],
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "error": "args 不能为空，至少需要一个 agent-browser CLI 参数。",
        }

    if timeout <= 0:
        logger.warning(f"agent_browser_run: 参数校验失败，timeout 非法: {timeout}")
        return {
            "success": False,
            "command": command_args,
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "error": "timeout 必须大于 0。",
        }

    configurable = config.get("configurable", {}) if config else {}
    execution_id = configurable.get("execution_id", "")
    result = _run_agent_browser_command(command=command_args, timeout=timeout, execution_id=execution_id)
    logger.info(f"agent_browser_run: 工具执行结束, success={result.get('success')}, exit_code={result.get('exit_code')}, error={result.get('error')!r}")
    return result


@tool(parse_docstring=True)
def agent_browser_screenshot(
    filename: str = "",
    full_page: bool = False,
    annotate: bool = False,
    image_format: str = "png",
    session_name: str = "",
    timeout: int = 120,
    config: Optional[dict] = None,
) -> Dict[str, Any]:
    """
    使用 agent-browser 截图，并默认保存到 server/tmp/agent-browser 目录。

    Args:
        filename: 可选文件名，例如 "baidu-home.png"。不传则自动生成时间戳文件名。
        full_page: 是否截取整页，对应 --full。
        annotate: 是否添加元素编号标注，对应 --annotate。
        image_format: 图片格式，支持 png、jpeg、jpg，默认 png。
        session_name: 可选浏览器会话名，用于复用同一个服务端浏览器实例。
        timeout: 命令超时时间（秒），默认 120 秒。

    Returns:
        结构化执行结果，额外包含 screenshot_path 字段，便于手动查看截图文件。
    """
    logger.info(
        f"agent_browser_screenshot: 进入工具执行, filename={filename!r}, full_page={full_page}, "
        f"annotate={annotate}, image_format={image_format!r}, session_name={session_name!r}, timeout={timeout}"
    )

    if timeout <= 0:
        logger.warning(f"agent_browser_screenshot: 参数校验失败，timeout 非法: {timeout}")
        return {
            "success": False,
            "command": [],
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "error": "timeout 必须大于 0。",
            "screenshot_path": None,
        }

    configurable = config.get("configurable", {}) if config else {}
    execution_id = configurable.get("execution_id", "")
    result = _run_screenshot_command(
        filename=filename,
        full_page=full_page,
        annotate=annotate,
        image_format=image_format,
        session_name=session_name,
        timeout=timeout,
        execution_id=execution_id,
    )
    screenshot_path = result.get("screenshot_path")
    logger.info(
        f"agent_browser_screenshot: 工具执行结束, success={result.get('success')}, "
        f"exit_code={result.get('exit_code')}, screenshot_path={screenshot_path!r}, error={result.get('error')!r}"
    )
    return result


@tool(parse_docstring=True)
def agent_browser_open_and_screenshot(
    url: str,
    filename: str = "",
    full_page: bool = True,
    annotate: bool = False,
    image_format: str = "png",
    session_name: str = "",
    timeout: int = 120,
    config: Optional[dict] = None,
) -> Dict[str, Any]:
    """
    打开指定 URL 后立即截图，便于调试跳转页面和页面阻塞问题。

    Args:
        url: 要访问的页面 URL。
        filename: 可选截图文件名，例如 "login-debug.png"。不传则自动生成。
        full_page: 是否截取整页，默认 True。
        annotate: 是否添加元素编号标注，默认 False。
        image_format: 图片格式，支持 png、jpeg、jpg，默认 png。
        session_name: 可选浏览器会话名，用于复用同一个服务端浏览器实例。
        timeout: 每个命令的超时时间（秒），默认 120 秒。

    Returns:
        包含 open_result、screenshot_result 和 screenshot_path 的结构化结果。
    """
    logger.info(
        f"agent_browser_open_and_screenshot: 开始执行, url={url!r}, filename={filename!r}, "
        f"full_page={full_page}, annotate={annotate}, image_format={image_format!r}, session_name={session_name!r}, timeout={timeout}"
    )

    if not url:
        return {
            "success": False,
            "error": "url 不能为空。",
            "open_result": None,
            "screenshot_result": None,
            "screenshot_path": None,
        }

    configurable = config.get("configurable", {}) if config else {}
    execution_id = configurable.get("execution_id", "")
    open_result = _run_agent_browser_command(
        command=[*_build_session_flags(session_name), "open", url],
        timeout=timeout,
        execution_id=execution_id,
    )
    if not open_result.get("success"):
        logger.warning(
            f"agent_browser_open_and_screenshot: 打开页面失败, error={open_result.get('error')!r}, url_candidates={open_result.get('url_candidates')}"
        )
        return {
            "success": False,
            "error": open_result.get("error"),
            "open_result": open_result,
            "screenshot_result": None,
            "screenshot_path": None,
        }

    screenshot_result = _run_screenshot_command(
        filename=filename,
        full_page=full_page,
        annotate=annotate,
        image_format=image_format,
        session_name=session_name,
        timeout=timeout,
        execution_id=execution_id,
    )
    screenshot_path = screenshot_result.get("screenshot_path")
    final_result = {
        "success": bool(screenshot_result.get("success")),
        "error": screenshot_result.get("error"),
        "open_result": open_result,
        "screenshot_result": screenshot_result,
        "screenshot_path": screenshot_path,
    }
    logger.info(
        f"agent_browser_open_and_screenshot: 执行结束, success={final_result.get('success')}, "
        f"screenshot_path={final_result.get('screenshot_path')!r}, error={final_result.get('error')!r}"
    )
    return final_result


@tool(parse_docstring=True)
def agent_browser_snapshot(
    interactive_only: bool = True,
    compact: bool = True,
    max_depth: int = 0,
    selector: str = "",
    session_name: str = "",
    timeout: int = 120,
    config: Optional[dict] = None,
) -> Dict[str, Any]:
    """
    获取当前页面的 snapshot，用于巡检时读取稳定的页面结构和交互元素引用。

    Args:
        interactive_only: 是否仅输出可交互元素，对应 -i，默认 True。
        compact: 是否输出紧凑格式，对应 -c，默认 True。
        max_depth: 可选最大深度，对应 -d。传 0 表示不限制。
        selector: 可选 CSS 选择器范围，对应 -s。
        session_name: 可选浏览器会话名，用于复用同一个服务端浏览器实例。
        timeout: 命令超时时间（秒），默认 120 秒。

    Returns:
        结构化执行结果，包含 snapshot 原始输出，便于后续解析或让模型继续决策。
    """
    logger.info(
        f"agent_browser_snapshot: 开始执行, interactive_only={interactive_only}, compact={compact}, "
        f"max_depth={max_depth}, selector={selector!r}, session_name={session_name!r}, timeout={timeout}"
    )

    configurable = config.get("configurable", {}) if config else {}
    execution_id = configurable.get("execution_id", "")
    result = _run_snapshot_command(
        interactive_only=interactive_only,
        compact=compact,
        max_depth=max_depth,
        selector=selector,
        session_name=session_name,
        timeout=timeout,
        execution_id=execution_id,
    )
    logger.info(f"agent_browser_snapshot: 执行结束, success={result.get('success')}, exit_code={result.get('exit_code')}, error={result.get('error')!r}")
    return result


@tool(parse_docstring=True)
def agent_browser_wait(
    selector_or_ms: str = "",
    text: str = "",
    url_pattern: str = "",
    load_state: str = "",
    state: str = "",
    js_condition: str = "",
    session_name: str = "",
    timeout: int = 120,
    config: Optional[dict] = None,
) -> Dict[str, Any]:
    """
    等待页面进入稳定状态，用于巡检流程中的加载完成判定。

    Args:
        selector_or_ms: 选择器、元素 ref 或毫秒数，例如 "@e1"、"#main"、"2000"。
        text: 等待出现的文本，对应 --text。
        url_pattern: 等待 URL 匹配的模式，对应 --url。
        load_state: 等待页面 load 状态，例如 networkidle、domcontentloaded、load，对应 --load。
        state: 元素状态，如 hidden，用于配合 selector_or_ms，对应 --state。
        js_condition: 等待 JavaScript 条件成立，对应 --fn。
        session_name: 可选浏览器会话名，用于复用同一个服务端浏览器实例。
        timeout: 命令超时时间（秒），默认 120 秒。

    Returns:
        结构化执行结果，便于上层状态机判断页面是否稳定。
    """
    logger.info(
        f"agent_browser_wait: 开始执行, selector_or_ms={selector_or_ms!r}, text={text!r}, url_pattern={url_pattern!r}, "
        f"load_state={load_state!r}, state={state!r}, js_condition={js_condition!r}, session_name={session_name!r}, timeout={timeout}"
    )

    configurable = config.get("configurable", {}) if config else {}
    execution_id = configurable.get("execution_id", "")
    result = _run_wait_command(
        selector_or_ms=selector_or_ms,
        text=text,
        url_pattern=url_pattern,
        load_state=load_state,
        state=state,
        js_condition=js_condition,
        session_name=session_name,
        timeout=timeout,
        execution_id=execution_id,
    )
    logger.info(f"agent_browser_wait: 执行结束, success={result.get('success')}, exit_code={result.get('exit_code')}, error={result.get('error')!r}")
    return result


@tool(parse_docstring=True)
def agent_browser_open_wait_and_snapshot(
    url: str,
    session_name: str = "",
    load_state: str = "networkidle",
    wait_ms: int = 0,
    interactive_only: bool = True,
    compact: bool = True,
    timeout: int = 120,
    config: Optional[dict] = None,
) -> Dict[str, Any]:
    """
    打开页面、等待稳定、再抓取 snapshot，是服务端巡检最常用的稳定读取组合。

    Args:
        url: 要访问的页面 URL。
        session_name: 可选浏览器会话名，用于复用同一个服务端浏览器实例。
        load_state: 打开后等待的 load 状态，默认 networkidle。
        wait_ms: 额外等待毫秒数，传 0 表示不额外等待。
        interactive_only: snapshot 是否仅输出可交互元素。
        compact: snapshot 是否使用紧凑格式。
        timeout: 每个命令超时时间（秒），默认 120 秒。

    Returns:
        包含 open_result、wait_result、snapshot_result、interstitial_result 的结构化结果。
    """
    logger.info(
        f"agent_browser_open_wait_and_snapshot: 开始执行, url={url!r}, session_name={session_name!r}, "
        f"load_state={load_state!r}, wait_ms={wait_ms}, interactive_only={interactive_only}, compact={compact}, timeout={timeout}"
    )

    configurable = config.get("configurable", {}) if config else {}
    execution_id = configurable.get("execution_id", "")
    final_result = _run_open_wait_and_snapshot(
        url=url,
        session_name=session_name,
        load_state=load_state,
        wait_ms=wait_ms,
        interactive_only=interactive_only,
        compact=compact,
        timeout=timeout,
        execution_id=execution_id,
    )
    logger.info(f"agent_browser_open_wait_and_snapshot: 执行结束, success={final_result.get('success')}, error={final_result.get('error')!r}")
    return final_result


@tool(parse_docstring=True)
def agent_browser_inspect(
    url: str,
    session_name: str = "",
    load_state: str = "networkidle",
    wait_ms: int = 0,
    interactive_only: bool = True,
    compact: bool = True,
    screenshot: bool = True,
    screenshot_filename: str = "",
    full_page: bool = True,
    annotate: bool = False,
    image_format: str = "png",
    timeout: int = 120,
    config: Optional[dict] = None,
) -> Dict[str, Any]:
    """
    打开页面、等待稳定、抓取 snapshot，并按需截图，是面向巡检 MVP 的统一入口。

    Args:
        url: 要访问的页面 URL。
        session_name: 可选浏览器会话名，用于复用同一个服务端浏览器实例。
        load_state: 打开后等待的 load 状态，默认 networkidle。
        wait_ms: 额外等待毫秒数，传 0 表示不额外等待。
        interactive_only: snapshot 是否仅输出可交互元素。
        compact: snapshot 是否使用紧凑格式。
        screenshot: 是否在 snapshot 后截图，默认 True。
        screenshot_filename: 可选截图文件名，不传则自动生成。
        full_page: 截图是否截取整页，默认 True。
        annotate: 截图是否添加元素标注，默认 False。
        image_format: 图片格式，支持 png、jpeg、jpg，默认 png。
        timeout: 每个命令超时时间（秒），默认 120 秒。

    Returns:
        包含 open_result、wait_result、snapshot_result、interstitial_result、screenshot_result、screenshot_path 的结构化结果。
    """
    logger.info(
        f"agent_browser_inspect: 开始执行, url={url!r}, session_name={session_name!r}, load_state={load_state!r}, "
        f"wait_ms={wait_ms}, interactive_only={interactive_only}, compact={compact}, screenshot={screenshot}, "
        f"screenshot_filename={screenshot_filename!r}, full_page={full_page}, annotate={annotate}, image_format={image_format!r}, timeout={timeout}"
    )

    configurable = config.get("configurable", {}) if config else {}
    execution_id = configurable.get("execution_id", "")
    base_result = _run_open_wait_and_snapshot(
        url=url,
        session_name=session_name,
        load_state=load_state,
        wait_ms=wait_ms,
        interactive_only=interactive_only,
        compact=compact,
        timeout=timeout,
        execution_id=execution_id,
    )
    if not base_result.get("success"):
        return {
            "success": False,
            "error": base_result.get("error"),
            "open_result": base_result.get("open_result"),
            "wait_result": base_result.get("wait_result"),
            "snapshot_result": base_result.get("snapshot_result"),
            "interstitial_result": base_result.get("interstitial_result"),
            "screenshot_result": None,
            "screenshot_path": None,
        }

    screenshot_result = None
    screenshot_path = None
    if screenshot:
        screenshot_result = _run_screenshot_command(
            filename=screenshot_filename,
            full_page=full_page,
            annotate=annotate,
            image_format=image_format,
            session_name=session_name,
            timeout=timeout,
            execution_id=execution_id,
        )
        screenshot_path = screenshot_result.get("screenshot_path")
        if not screenshot_result.get("success"):
            final_result = {
                "success": False,
                "error": screenshot_result.get("error"),
                "open_result": base_result.get("open_result"),
                "wait_result": base_result.get("wait_result"),
                "snapshot_result": base_result.get("snapshot_result"),
                "interstitial_result": base_result.get("interstitial_result"),
                "screenshot_result": screenshot_result,
                "screenshot_path": screenshot_path,
            }
            logger.warning(f"agent_browser_inspect: 截图失败, screenshot_path={screenshot_path!r}, error={final_result.get('error')!r}")
            return final_result

    final_result = {
        "success": True,
        "error": None,
        "open_result": base_result.get("open_result"),
        "wait_result": base_result.get("wait_result"),
        "snapshot_result": base_result.get("snapshot_result"),
        "interstitial_result": base_result.get("interstitial_result"),
        "screenshot_result": screenshot_result,
        "screenshot_path": screenshot_path,
    }
    logger.info(
        f"agent_browser_inspect: 执行结束, success={final_result.get('success')}, "
        f"screenshot_path={screenshot_path!r}, error={final_result.get('error')!r}"
    )
    return final_result
