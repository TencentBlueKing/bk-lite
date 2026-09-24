from typing import Any

from apps.core.logger import operation_analysis_logger as logger
from apps.operation_analysis.common.get_nats_source_data import build_nats_user_info
from apps.operation_analysis.services.user_messages import oa_message
from apps.rpc.cmdb import CMDB

_NATS_CODE_TO_ERROR = {
    400: "invalid_request",
    403: "permission_denied",
    404: "not_found",
}

_ERROR_MESSAGES = {
    "invalid_request": ("messages.room3d_invalid", "server_room_id 不合法"),
    "not_found": ("messages.room3d_not_found", "机房不存在"),
    "permission_denied": ("messages.room3d_denied", "无权限查看该机房"),
    "source_failure": ("messages.room3d_query_failed", "3D机房查询失败"),
}


class Room3DError(Exception):
    def __init__(self, code: str, message: str | None = None):
        self.code = code
        key, default = _ERROR_MESSAGES.get(code, _ERROR_MESSAGES["source_failure"])
        self.message = message or oa_message(key, default)
        super().__init__(self.message)


class Room3DService:
    @classmethod
    def list_rooms(cls, request) -> dict[str, Any]:
        user_info = build_nats_user_info(request)
        result = cls._call_cmdb("rooms", lambda: CMDB().get_room_list(user_info=user_info))
        items = cls._extract_items(result)
        rooms = []
        for item in items:
            room_id = str(item.get("inst_uuid") or "").strip()
            if not room_id:
                continue
            rooms.append(
                {
                    "id": room_id,
                    "name": str(item.get("inst_name") or room_id),
                }
            )
        return {"items": rooms}

    @classmethod
    def layout(cls, request, server_room_id: str) -> dict[str, Any]:
        user_info = build_nats_user_info(request)
        result = cls._call_cmdb(
            "layout",
            lambda: CMDB().get_room3d_layout(server_room_id=server_room_id, user_info=user_info),
            server_room_id=server_room_id,
        )
        if not isinstance(result, dict) or result.get("result") is not True:
            cls._raise_nats_result(result, "layout", server_room_id)
        data = result.get("data")
        return data if isinstance(data, dict) else {}

    @classmethod
    def _call_cmdb(cls, failed_stage: str, runner, server_room_id: str = "-"):
        try:
            return runner()
        except Exception as exc:
            cls._log_source_failure(failed_stage, server_room_id, exc)
            raise Room3DError("source_failure") from exc

    @classmethod
    def _extract_items(cls, result: Any) -> list[dict]:
        if not isinstance(result, dict):
            cls._raise_nats_false_result("rooms")
        if "result" in result and result.get("result") is not True:
            cls._raise_nats_result(result, "rooms")
        data = result.get("data") if isinstance(result.get("data"), dict) else result
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return []
        return [item for item in items if isinstance(item, dict)]

    @classmethod
    def _raise_nats_result(cls, result: Any, failed_stage: str, server_room_id: str = "-") -> None:
        data = result.get("data") if isinstance(result, dict) and isinstance(result.get("data"), dict) else {}
        nats_code = result.get("code") if isinstance(result, dict) else None
        if nats_code is None:
            nats_code = data.get("code")
        mapped = _NATS_CODE_TO_ERROR.get(nats_code)
        if mapped:
            raise Room3DError(mapped)
        cls._raise_nats_false_result(failed_stage, server_room_id)

    @classmethod
    def _raise_nats_false_result(cls, failed_stage: str, server_room_id: str = "-") -> None:
        logger.error(
            "event=room3d_source_failed failed_stage=%s error_type=%s server_room_id=%s",
            failed_stage,
            "NatsResultFalse",
            server_room_id,
        )
        raise Room3DError("source_failure")

    @staticmethod
    def _log_source_failure(failed_stage: str, server_room_id: str, exc: BaseException) -> None:
        logger.exception(
            "event=room3d_source_failed failed_stage=%s error_type=%s server_room_id=%s",
            failed_stage,
            type(exc).__name__,
            server_room_id,
        )
