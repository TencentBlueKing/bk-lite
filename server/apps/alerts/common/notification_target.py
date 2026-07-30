"""告警分派通知目标的兼容归一化与运行时解析。"""

from typing import Any, Dict, Iterable, Optional

from apps.core.logger import alert_logger as logger

USER_TARGET = "user"
ORGANIZATION_TARGET = "organization"
VALID_TARGET_TYPES = {USER_TARGET, ORGANIZATION_TARGET}


def read_notification_target(container: Any) -> Optional[Dict[str, Any]]:
    """从配置容器读取目标，同时区分“字段缺失”和显式 ``null``。"""
    if not isinstance(container, dict) or "notification_target" not in container:
        return None
    target = container.get("notification_target")
    return target if target is not None else {}


def _deduplicate_strings(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return list(
        dict.fromkeys(
            value.strip()
            for value in values
            if isinstance(value, str) and value.strip()
        )
    )


def _deduplicate_integer_ids(values: Any) -> list[int]:
    if not isinstance(values, list):
        return []

    result: list[int] = []
    seen: set[int] = set()
    for value in values:
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def normalize_notification_target(
    target: Optional[Dict[str, Any]],
    legacy_personnel: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """把新目标或历史 ``personnel`` 归一化为稳定结构。

    缺失的新目标按历史用户格式解释；非法的新目标安全降级为空用户目标。
    """
    if target is None:
        target = {
            "type": USER_TARGET,
            "usernames": list(legacy_personnel)
            if isinstance(legacy_personnel, (list, tuple))
            else [],
        }
    elif not isinstance(target, dict) or target.get("type") not in VALID_TARGET_TYPES:
        target = {
            "type": USER_TARGET,
            "usernames": [],
        }

    target_type = target["type"]
    if target_type == ORGANIZATION_TARGET:
        return {
            "type": ORGANIZATION_TARGET,
            "usernames": [],
            "organization_ids": _deduplicate_integer_ids(
                target.get("organization_ids")
            ),
            "include_children": target.get("include_children") is True,
        }

    return {
        "type": USER_TARGET,
        "usernames": _deduplicate_strings(
            target.get("usernames", legacy_personnel)
        ),
        "organization_ids": [],
        "include_children": False,
    }


def resolve_notification_target(
    target: Optional[Dict[str, Any]],
    legacy_personnel: Optional[Iterable[str]] = None,
) -> list[str]:
    return resolve_notification_target_with_scope(
        target,
        legacy_personnel,
    )[0]


def resolve_notification_target_with_scope(
    target: Optional[Dict[str, Any]],
    legacy_personnel: Optional[Iterable[str]] = None,
) -> tuple[list[str], Optional[list[int]]]:
    """把通知目标解析为当前有效用户名列表。

    组织目标同时返回已展开的组织边界；用户目标的边界为 ``None``，调用方继续
    沿用告警所属组织校验。解析失败统一返回空结果。
    """
    normalized = normalize_notification_target(target, legacy_personnel)
    try:
        from apps.system_mgmt.models import Group, User
        from apps.system_mgmt.utils.group_filter_mixin import filter_queryset_by_group_ids
        from apps.system_mgmt.utils.group_utils import GroupUtils

        if normalized["type"] == USER_TARGET:
            # 历史 personnel 保持原语义；显式新目标每次解析当前有效用户。
            is_structured_user_target = (
                isinstance(target, dict) and target.get("type") == USER_TARGET
            )
            if not is_structured_user_target:
                return normalized["usernames"], None
            active_usernames = set(
                User.objects.filter(
                    username__in=normalized["usernames"],
                    disabled=False,
                ).values_list("username", flat=True)
            )
            return (
                [
                    username
                    for username in normalized["usernames"]
                    if username in active_usernames
                ],
                None,
            )

        requested_ids = normalized["organization_ids"]
        existing_ids = list(
            Group.objects.filter(id__in=requested_ids).values_list("id", flat=True)
        )
        if len(existing_ids) != len(requested_ids):
            return [], []

        group_ids = (
            GroupUtils.get_group_with_descendants(existing_ids)
            if normalized["include_children"]
            else existing_ids
        )
        users = filter_queryset_by_group_ids(
            User.objects.filter(disabled=False),
            group_ids,
        )
        return (
            list(
                users.order_by("username")
                .values_list("username", flat=True)
                .distinct()
            ),
            group_ids,
        )
    except Exception:
        logger.exception(
            "[AlertNotificationTarget] 通知目标解析失败: type=%s, organization_ids=%s",
            normalized["type"],
            normalized["organization_ids"],
        )
        return [], [] if normalized["type"] == ORGANIZATION_TARGET else None
