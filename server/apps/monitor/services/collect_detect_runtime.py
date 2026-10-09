import base64
import re
import shlex

from apps.monitor.utils.plugin_controller import Controller

DEFAULT_OUTPUT_LIMIT = 8192
_OUTPUT_BLOCK_PATTERN = re.compile(r"(?ms)^\s*\[\[outputs\.[^\]]+\]\].*?(?=^\s*\[\[|\Z)")
_SECRET_ASSIGNMENT_PATTERN = re.compile(r"(?i)\b(password|passwd|token|secret|private_key|passphrase)\s*=\s*([^\s,;]+)")


def sidecar_node_render_variables(node) -> dict:
    """与 Sidecar.get_variables 的 node__* 键对齐，供探测路径做 ${node.*} 替换。"""
    ip = str(getattr(node, "ip", "") or "")
    return {
        "node__id": str(getattr(node, "id", "") or ""),
        "node__cloud_region": str(getattr(node, "cloud_region_id", "") or ""),
        "node__name": str(getattr(node, "name", "") or ""),
        "node__ip": ip,
        "node__ip_filter": ip.replace(".", "-").replace("*", "-").replace("*", ">"),
        "node__operating_system": str(getattr(node, "operating_system", "") or ""),
        "node__collector_configuration_directory": str(
            getattr(node, "collector_configuration_directory", "") or ""
        ),
    }


def substitute_sidecar_node_variables(config_content: str, node) -> str:
    """探测不走 Sidecar 拉配置，用正式下发同一套 ${node.*} 替换。"""
    if node is None or not config_content:
        return config_content
    from apps.node_mgmt.services.sidecar import Sidecar

    return Sidecar.render_template(config_content, sidecar_node_render_variables(node))


def script_isolation_name_prefixes(config_id) -> list:
    """child name_prefix 可能是 bklite_script_{id}_ 或仅 {id}_，调试展示都要剥掉。"""
    text = str(config_id or "").strip()
    if not text:
        return []
    prefixes = []
    for item in (f"bklite_script_{text}_", f"{text}_"):
        if item not in prefixes:
            prefixes.append(item)
    return prefixes


def render_preflight_telegraf_config(template_content: str, context: dict) -> str:
    rendered = render_telegraf_config_template(template_content, context)
    return disable_real_outputs(rendered)


def render_telegraf_config_template(template_content: str, context: dict) -> str:
    return Controller({}).render_template(
        template_content,
        context,
        escape_toml_strings=True,
    )


def disable_real_outputs(config_content: str) -> str:
    """探测与正式采集共用同一套 input 配置；仅去掉真实 output，避免写入 VictoriaMetrics。"""
    without_outputs = _OUTPUT_BLOCK_PATTERN.sub("", config_content).rstrip()
    stdout_output = """

[[outputs.file]]
  files = ["stdout"]
  data_format = "influx"
"""
    return f"{without_outputs}{stdout_output}"


def _quote_powershell_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def build_telegraf_detect_execution(
    operating_system: str,
    executable_path: str,
    config_file_name: str,
    config_content: str,
) -> tuple[str, str]:
    if operating_system == "linux":
        config_path = f"/tmp/{config_file_name}"
        quoted_path = shlex.quote(config_path)
        quoted_telegraf = shlex.quote(executable_path)
        command = (
            "set -e\n"
            f"trap 'rm -f {quoted_path}' EXIT\n"
            f"cat > {quoted_path} <<'BK_LITE_TELEGRAF_PREFLIGHT_EOF'\n"
            f"{config_content}\n"
            "BK_LITE_TELEGRAF_PREFLIGHT_EOF\n"
            f"{quoted_telegraf} --once --config {quoted_path}"
        )
        return command, "sh"

    if operating_system == "windows":
        encoded_content = base64.b64encode(config_content.encode("utf-8")).decode("ascii")
        quoted_name = _quote_powershell_literal(config_file_name)
        quoted_telegraf = _quote_powershell_literal(executable_path)
        command = (
            "$ErrorActionPreference = 'Stop'\n"
            f"$configPath = Join-Path $env:TEMP {quoted_name}\n"
            "$telegrafExitCode = 1\n"
            "try {\n"
            f"  [IO.File]::WriteAllBytes($configPath, [Convert]::FromBase64String('{encoded_content}'))\n"
            f"  & {quoted_telegraf} --once --config $configPath\n"
            "  $telegrafExitCode = $LASTEXITCODE\n"
            "} finally {\n"
            "  Remove-Item -LiteralPath $configPath -Force -ErrorAction SilentlyContinue\n"
            "}\n"
            "exit $telegrafExitCode"
        )
        return command, "powershell"

    raise ValueError(f"不支持的节点操作系统: {operating_system}")


def sanitize_execution_result(raw_result, sensitive_values=None, output_limit=DEFAULT_OUTPUT_LIMIT) -> dict:
    """成功判定只信任执行器返回的 success / exit_code，不做 stdout/stderr 文案推断。"""
    sensitive_values = [str(item) for item in (sensitive_values or []) if item not in (None, "")]
    if not isinstance(raw_result, dict):
        stdout, stdout_truncated = _redact_and_truncate(raw_result, sensitive_values, output_limit)
        return {
            "success": True,
            "stdout": stdout,
            "stderr": "",
            "exit_code": 0,
            "code": "",
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": False,
        }

    stdout = raw_result.get("stdout", raw_result.get("result", ""))
    stderr = raw_result.get("stderr", raw_result.get("error", ""))
    stdout, stdout_truncated = _redact_and_truncate(stdout, sensitive_values, output_limit)
    stderr, stderr_truncated = _redact_and_truncate(stderr, sensitive_values, output_limit)

    success = bool(raw_result.get("success"))
    exit_code = raw_result.get("exit_code")
    if exit_code is None:
        exit_code = 0 if success else 1
    else:
        try:
            exit_code = int(exit_code)
        except (TypeError, ValueError):
            exit_code = 0 if success else 1
        success = exit_code == 0

    return {
        "success": success,
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
        "code": raw_result.get("code", ""),
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
    }


def _redact_and_truncate(value, sensitive_values, output_limit):
    text = "" if value is None else str(value)
    text = _SECRET_ASSIGNMENT_PATTERN.sub(lambda match: f"{match.group(1)}=***", text)
    for sensitive_value in sensitive_values:
        text = text.replace(sensitive_value, "***")

    if len(text) <= output_limit:
        return text, False

    return text[:output_limit] + "\n...[truncated]", True
