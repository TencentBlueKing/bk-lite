from typing import Any, NoReturn

from rest_framework.exceptions import ValidationError

from apps.core.logger import operation_analysis_logger as logger
from apps.core.logger import safe_exception_info, safe_log_value
from apps.operation_analysis.common.get_nats_source_data import build_nats_user_info
from apps.operation_analysis.services.user_messages import oa_message
from apps.rpc.cmdb import CMDB

_MAX_PAGE_SIZE = 100
_DEFAULT_PAGE_SIZE = 30
_FAILED = "messages.architecture_resource_search_failed"
_FAILED_DEFAULT = "资源搜索失败"


class ArchitectureResourceSearchService:
    @classmethod
    def list_models(cls, request) -> list:
        user_info = build_nats_user_info(request)
        payload = _call("models", lambda: CMDB().search_models_for_llm(user_info=user_info))
        if not isinstance(payload, list):
            _unexpected("models")
        return payload

    @classmethod
    def search(cls, request, payload: dict) -> dict:
        keyword, model_id, page, page_size, case_sensitive = _parse_search(payload)
        user_info = build_nats_user_info(request)
        if model_id and not keyword:
            hits, total = _by_type(user_info, model_id, page, page_size)
            mode = "by-type"
        elif model_id and keyword:
            hits, total = _by_model_text(user_info, keyword, model_id, page, page_size, case_sensitive)
            mode = "by-model-text"
        else:
            # fulltext_search 不接受分页；整表放进 hits，页切片留在前端。
            hits, total = _fulltext(user_info, keyword, case_sensitive)
            mode = "fulltext"
        return {
            "mode": mode,
            "hits": hits,
            "total": total,
            "page": page,
            "page_size": page_size,
        }


def _by_type(user_info: dict, model_id: str, page: int, page_size: int) -> tuple[list[dict], int]:
    payload = _call(
        "by-type",
        lambda: CMDB().list_instances_for_llm(
            protocol_version="2",
            user_info=user_info,
            model_id=model_id,
            params=[],
            page=page,
            page_size=page_size,
        ),
        model_id,
    )
    body = _expect_dict(payload, "by-type", model_id)
    return _hits(body.get("items"), "by-type", model_id), _count(body.get("count"), "by-type", model_id)


def _by_model_text(
    user_info: dict,
    keyword: str,
    model_id: str,
    page: int,
    page_size: int,
    case_sensitive: bool,
) -> tuple[list[dict], int]:
    payload = _call(
        "by-model-text",
        lambda: CMDB().fulltext_search_by_model(
            search=keyword,
            model_id=model_id,
            page=page,
            page_size=page_size,
            case_sensitive=case_sensitive,
            user_info=user_info,
        ),
        model_id,
    )
    body = _expect_dict(payload, "by-model-text", model_id)
    return (
        _hits(body.get("data"), "by-model-text", model_id),
        _count(body.get("total"), "by-model-text", model_id),
    )


def _fulltext(user_info: dict, keyword: str, case_sensitive: bool) -> tuple[list[dict], int]:
    payload = _call(
        "fulltext",
        lambda: CMDB().fulltext_search(
            search=keyword,
            case_sensitive=case_sensitive,
            user_info=user_info,
        ),
    )
    hits = _hits(payload, "fulltext")
    return hits, len(hits)


def _parse_search(payload: dict) -> tuple[str, str, int, int, bool]:
    if not isinstance(payload, dict):
        raise ValidationError(
            {
                "detail": oa_message(
                    "messages.architecture_resource_search_body",
                    "请求体必须是对象",
                )
            }
        )
    page = _bounded_int(
        payload.get("page", 1),
        "page",
        "messages.architecture_resource_search_page",
        "page 必须大于等于 1",
        minimum=1,
    )
    page_size = _bounded_int(
        payload.get("page_size", _DEFAULT_PAGE_SIZE),
        "page_size",
        "messages.architecture_resource_search_page_size",
        "page_size 必须在 1 到 100 之间",
        minimum=1,
        maximum=_MAX_PAGE_SIZE,
    )
    keyword = _text_field(payload, "keyword")
    model_id = _text_field(payload, "model_id")
    if not keyword and not model_id:
        raise ValidationError(
            {
                "detail": oa_message(
                    "messages.architecture_resource_search_required",
                    "请输入关键词或选择模型",
                )
            }
        )
    return keyword, model_id, page, page_size, _flag(payload.get("case_sensitive", False))


def _text_field(payload: dict, key: str) -> str:
    if key not in payload or payload[key] in (None, ""):
        return ""
    value = payload[key]
    if not isinstance(value, str):
        raise ValidationError(
            {
                key: oa_message(
                    "messages.architecture_resource_search_text",
                    "{field} 必须是字符串",
                    field=key,
                )
            }
        )
    return value.strip()


def _flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    raise ValidationError(
        {
            "case_sensitive": oa_message(
                "messages.architecture_resource_search_case",
                "case_sensitive 必须是布尔值",
            )
        }
    )


def _bounded_int(
    value: Any,
    field: str,
    message_key: str,
    default: str,
    *,
    minimum: int,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _range_error(field, message_key, default)
    if value < minimum or (maximum is not None and value > maximum):
        raise _range_error(field, message_key, default)
    return value


def _range_error(field: str, message_key: str, default: str) -> ValidationError:
    return ValidationError({field: oa_message(message_key, default)})


def _call(stage: str, call, model_id: str = ""):
    try:
        result = call()
    except Exception as exc:
        _log_failure(stage, exc, type(exc).__name__, model_id)
        raise _failed() from None
    if isinstance(result, dict) and result.get("result") is False:
        _log_failure(stage, None, "NatsResultFalse", model_id)
        raise _failed()
    if isinstance(result, dict) and result.get("result") is True and "data" in result:
        return result.get("data")
    return result


def _expect_dict(payload: Any, stage: str, model_id: str = "") -> dict:
    if isinstance(payload, dict):
        return payload
    _unexpected(stage, model_id)


def _count(value: Any, stage: str, model_id: str = "") -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _unexpected(stage, model_id)
    return value


def _hits(raw: Any, stage: str, model_id: str = "") -> list[dict]:
    if not isinstance(raw, list):
        _unexpected(stage, model_id)
    hits = []
    for item in raw:
        hit = _hit(item)
        if hit is not None:
            hits.append(hit)
    return hits


def _hit(item: Any) -> dict | None:
    if not isinstance(item, dict):
        return None
    inst_uuid = _identity(item.get("inst_uuid"))
    model_id = _identity(item.get("model_id"))
    if not inst_uuid or not model_id:
        return None
    return {
        "inst_uuid": inst_uuid,
        "inst_name": _plain(item.get("inst_name")),
        "ip_addr": _plain(item.get("ip_addr")),
        "model_id": model_id,
    }


def _identity(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _plain(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bool) or value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    return ""


def _failed() -> ValidationError:
    return ValidationError({"detail": oa_message(_FAILED, _FAILED_DEFAULT)})


def _unexpected(stage: str, model_id: str = "") -> NoReturn:
    _log_failure(stage, None, "UnexpectedResult", model_id)
    raise _failed()


def _log_failure(stage: str, exc: BaseException | None, error_type: str, model_id: str = "") -> None:
    logger.error(
        "event=architecture_resource_search_failed failed_stage=%s error_type=%s model_id=%s",
        stage,
        error_type,
        safe_log_value(model_id) or "-",
        exc_info=safe_exception_info(exc) if exc is not None else None,
    )
