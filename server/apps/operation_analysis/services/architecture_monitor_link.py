from typing import NoReturn

from rest_framework.exceptions import ValidationError

from apps.core.logger import operation_analysis_logger as logger
from apps.core.logger import safe_exception_info, safe_log_value
from apps.operation_analysis.common.get_nats_source_data import build_nats_user_info
from apps.operation_analysis.services.user_messages import oa_message
from apps.rpc.monitor import Monitor

_FAILED = "messages.architecture_monitor_link_failed"
_FAILED_DEFAULT = "监控链接解析失败"
_EMPTY = {"monitor_object": None, "instance": None, "plugins": []}


class ArchitectureMonitorLinkService:
    @classmethod
    def resolve(cls, request, monitor_id) -> dict:
        instance_id = _monitor_id(monitor_id)
        user_info = build_nats_user_info(request)
        lookup = _call(
            "lookup",
            lambda: Monitor().lookup_monitor_instance(instance_id=instance_id, user_info=user_info),
            instance_id,
        )
        if not isinstance(lookup, dict):
            return dict(_EMPTY)
        monitor_object = lookup.get("monitor_object")
        instance = lookup.get("instance")
        if not isinstance(monitor_object, dict) or not isinstance(instance, dict):
            return dict(_EMPTY)
        object_id = monitor_object.get("id")
        if object_id in (None, ""):
            return dict(_EMPTY)
        locale = user_info.get("locale")
        plugins = _call(
            "plugins",
            lambda: Monitor().get_monitor_effective_plugins(
                monitor_object_id=object_id,
                instance_id=instance_id,
                user_info=user_info,
                locale=locale if isinstance(locale, str) and locale.strip() else "zh-Hans",
            ),
            instance_id,
        )
        if plugins is None:
            return dict(_EMPTY)
        if not isinstance(plugins, list):
            _unexpected("plugins", instance_id)
        return {
            "monitor_object": monitor_object,
            "instance": instance,
            "plugins": plugins,
        }


def _monitor_id(value) -> str:
    if value in (None, ""):
        raise _monitor_id_error("messages.architecture_monitor_link_required", "请提供 monitor_id")
    if not isinstance(value, str):
        raise _monitor_id_error("messages.architecture_monitor_link_text", "monitor_id 必须是非空字符串")
    text = value.strip()
    if not text:
        raise _monitor_id_error("messages.architecture_monitor_link_required", "请提供 monitor_id")
    return text


def _monitor_id_error(message_key: str, default: str) -> ValidationError:
    return ValidationError({"monitor_id": oa_message(message_key, default)})


def _call(stage: str, call, monitor_id: str):
    try:
        result = call()
    except Exception as exc:
        _log_failure(stage, exc, type(exc).__name__, monitor_id)
        raise _failed() from None
    if isinstance(result, dict) and result.get("result") is False:
        _log_failure(stage, None, "NatsResultFalse", monitor_id)
        raise _failed()
    if isinstance(result, dict) and result.get("result") is True and "data" in result:
        return result.get("data")
    _unexpected(stage, monitor_id)


def _failed() -> ValidationError:
    return ValidationError({"detail": oa_message(_FAILED, _FAILED_DEFAULT)})


def _unexpected(stage: str, monitor_id: str) -> NoReturn:
    _log_failure(stage, None, "UnexpectedResult", monitor_id)
    raise _failed()


def _log_failure(stage: str, exc: BaseException | None, error_type: str, monitor_id: str) -> None:
    logger.error(
        "event=architecture_monitor_link_failed failed_stage=%s error_type=%s monitor_id=%s",
        stage,
        error_type,
        safe_log_value(monitor_id) or "-",
        exc_info=safe_exception_info(exc) if exc is not None else None,
    )
