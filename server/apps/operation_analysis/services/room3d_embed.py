from typing import Any

from apps.core.logger import operation_analysis_logger as logger
from apps.core.logger import safe_exception_info
from apps.operation_analysis.common.get_nats_source_data import build_nats_user_info
from apps.rpc.cmdb import CMDB

_NATS_TO_HTTP_CODE = {
    400: "invalid_request",
    403: "permission_denied",
    404: "not_found",
    409: "invalid_request",
    "invalid_inst_uuid": "invalid_request",
    "not_found": "not_found",
    "permission_denied": "permission_denied",
}

_NATS_MESSAGES = {
    "invalid_request": "inst_uuid 不合法",
    "not_found": "机房不存在",
    "permission_denied": "无权限查看该机房",
    "source_failure": "3D 机房查询失败",
}


class Room3DEmbedError(Exception):
    def __init__(self, code: str, message: str | None = None):
        self.code = code
        self.message = message or _NATS_MESSAGES.get(code, _NATS_MESSAGES["source_failure"])
        super().__init__(self.message)


class Room3DEmbedService:
    @classmethod
    def build(cls, request, inst_uuid: str) -> dict[str, Any]:
        user_info = build_nats_user_info(request)
        try:
            result = CMDB().get_room3d_layout(server_room_id=inst_uuid, user_info=user_info)
        except Exception as exc:
            logger.error(
                "event=room3d_embed_source_failed failed_stage=%s error_type=%s inst_uuid=%s",
                "layout",
                type(exc).__name__,
                inst_uuid,
                exc_info=safe_exception_info(exc),
            )
            raise Room3DEmbedError("source_failure") from exc
        return cls._unwrap_layout(result, inst_uuid)

    @classmethod
    def _unwrap_layout(cls, result: Any, inst_uuid: str) -> dict[str, Any]:
        if not isinstance(result, dict) or result.get("result") is not True:
            code = "source_failure"
            data = result.get("data") if isinstance(result, dict) and isinstance(result.get("data"), dict) else {}
            nats_code = data.get("code") if data else None
            if nats_code is None and isinstance(result, dict):
                nats_code = result.get("code")
            if nats_code in _NATS_TO_HTTP_CODE:
                code = _NATS_TO_HTTP_CODE[nats_code]
            if code == "source_failure":
                logger.error(
                    "event=room3d_embed_source_failed failed_stage=%s error_type=%s inst_uuid=%s",
                    "layout",
                    "NatsResultFalse",
                    inst_uuid,
                )
                raise Room3DEmbedError("source_failure")
            raise Room3DEmbedError(code)
        data = result.get("data")
        return data if isinstance(data, dict) else {}
