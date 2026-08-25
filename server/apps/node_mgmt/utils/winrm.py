WINRM_HTTP_PORT = 5985
WINRM_HTTPS_PORT = 5986
WINRM_ALLOWED_SCHEMES = ("http", "https")
WINRM_ALLOWED_TRANSPORTS = ("ntlm",)


def default_winrm_port(scheme: str) -> int:
    return WINRM_HTTP_PORT if scheme == "http" else WINRM_HTTPS_PORT


def winrm_profile_error(scheme: str, port: int, transport: str) -> str | None:
    if transport not in WINRM_ALLOWED_TRANSPORTS:
        return "Windows remote operation currently requires NTLM"
    if scheme not in WINRM_ALLOWED_SCHEMES:
        return "Windows remote operation requires HTTP or HTTPS"
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        return "Windows remote operation requires a valid port"
    if scheme == "https" and port == WINRM_HTTP_PORT:
        return "WinRM HTTPS cannot use port 5985; use 5986 or a custom HTTPS listener port"
    if scheme == "http" and port == WINRM_HTTPS_PORT:
        return "WinRM HTTP cannot use port 5986; use 5985 or a custom HTTP listener port"
    return None
