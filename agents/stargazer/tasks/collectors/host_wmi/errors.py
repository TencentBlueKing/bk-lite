class WmiError(Exception):
    def __init__(self, message: str, error_type: str = "unknown"):
        super().__init__(message)
        self.error_type = error_type


def classify_wmi_error(error: Exception) -> str:
    if isinstance(error, WmiError):
        return error.error_type
    if isinstance(error, TimeoutError):
        return "query_timeout"

    text = str(error).lower()
    if "access denied" in text or "permission" in text:
        return "dcom_access_denied"
    if "auth" in text or "login" in text or "password" in text:
        return "auth_failed"
    if "network" in text or "unreachable" in text:
        return "network_unreachable"
    if "rpc" in text:
        return "rpc_unavailable"
    if "namespace" in text:
        return "namespace_not_found"
    if "class" in text:
        return "class_unavailable"
    if "timeout" in text or "timed out" in text:
        return "query_timeout"
    return "unknown"
