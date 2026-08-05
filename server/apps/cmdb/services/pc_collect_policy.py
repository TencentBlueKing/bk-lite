# -- coding: utf-8 --
"""PC 发现采集任务的专用校验策略。

契约（见 docs/superpowers/specs/2026-07-22-cmdb-pc-configuration-software-discovery-design.md）：
- 一个任务一种 OS（windows 固定 WinRM，macos 固定 SSH），创建后 OS 不可修改；
- Windows 仅接受 5986/HTTPS 或显式 5985/HTTP，认证固定 NTLM；
- macOS 凭据必须且只能包含密码或私钥之一；
- 单台超时范围 30~300 秒；
- HTTP/5985 合法但写入 security_warning 提示码，不把提示文本当业务状态。
"""

PC_OS_TYPES = ("windows", "macos")
PC_TIMEOUT_MIN = 30
PC_TIMEOUT_MAX = 300
WINRM_HTTP_SECURITY_WARNING = "WINRM_HTTP_INSECURE"

_WINDOWS_PORT_SCHEME = {(5986, "https"), (5985, "http")}


def _normalize_port(raw_port, default):
    if raw_port in (None, ""):
        return default
    try:
        return int(raw_port)
    except (TypeError, ValueError) as err:
        raise ValueError("凭据端口必须是数字") from err


def _normalize_credentials(credential):
    if isinstance(credential, dict):
        return [credential]
    if isinstance(credential, list):
        return [item for item in credential if isinstance(item, dict)]
    return []


def _validate_windows(params, credentials):
    scheme = params.get("winrm_scheme") or "https"
    if scheme not in ("https", "http"):
        raise ValueError("WinRM 传输协议仅支持 https 或 http")
    if not credentials:
        raise ValueError("采集凭据不能为空")
    for credential in credentials:
        if not credential.get("username"):
            raise ValueError("Windows 凭据必须包含用户名")
        if not credential.get("password"):
            raise ValueError("Windows 凭据必须包含密码")
        port = _normalize_port(credential.get("port"), 5986)
        if (port, scheme) not in _WINDOWS_PORT_SCHEME:
            raise ValueError("WinRM 端口与传输协议不匹配：仅支持 5986/HTTPS 或 5985/HTTP")
    params["winrm_scheme"] = scheme
    params["winrm_transport"] = "ntlm"
    params["winrm_cert_validation"] = bool(params.get("winrm_cert_validation", False))
    if scheme == "http":
        params["security_warning"] = WINRM_HTTP_SECURITY_WARNING
    else:
        params.pop("security_warning", None)
    return params


def _validate_macos(params, credentials):
    if not credentials:
        raise ValueError("采集凭据不能为空")
    for credential in credentials:
        if not credential.get("username"):
            raise ValueError("macOS 凭据必须包含用户名")
        has_password = bool(credential.get("password"))
        has_key = bool(credential.get("private_key"))
        if has_password == has_key:
            raise ValueError("macOS 凭据必须且只能包含密码或私钥之一")
        _normalize_port(credential.get("port"), 22)
    params.pop("security_warning", None)
    return params


def validate_pc_collect_task(params, credential, timeout, instance_params=None):
    """校验并归一化 PC 任务参数，不合法时抛 ValueError。"""
    params = dict(params or {})
    os_type = params.get("os_type")
    if os_type not in PC_OS_TYPES:
        raise ValueError("操作系统仅支持 windows 或 macos")

    previous_os = (instance_params or {}).get("os_type")
    if previous_os and previous_os != os_type:
        raise ValueError("操作系统创建后不可修改，请复制并新建任务")

    try:
        timeout_value = int(timeout)
    except (TypeError, ValueError) as err:
        raise ValueError("超时时间必须是数字") from err
    if not PC_TIMEOUT_MIN <= timeout_value <= PC_TIMEOUT_MAX:
        raise ValueError(f"超时时间需在 {PC_TIMEOUT_MIN} 到 {PC_TIMEOUT_MAX} 秒之间")

    credentials = _normalize_credentials(credential)
    if os_type == "windows":
        return _validate_windows(params, credentials)
    return _validate_macos(params, credentials)
