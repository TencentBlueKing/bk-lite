class TelemetryStoreUnavailable(RuntimeError):
    """外部遥测数据面不可用或返回不可信响应。"""


class TelemetryQueryTooLarge(TelemetryStoreUnavailable):
    """本次查询响应或 VictoriaTraces 单次查询容量超过上限。"""


TELEMETRY_UNAVAILABLE_CODE = "telemetry_unavailable"
QUERY_TOO_LARGE_CODE = "query_too_large"


def telemetry_error_payload(exc: TelemetryStoreUnavailable) -> dict[str, str]:
    code = QUERY_TOO_LARGE_CODE if isinstance(exc, TelemetryQueryTooLarge) else TELEMETRY_UNAVAILABLE_CODE
    return {"detail": str(exc), "code": code}
