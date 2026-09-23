"""用户同步-初始密码邮件发送 helper。

通过 channel_utils.send_email 直接发送(不走 RuntimeApplicationService,
因为 email 通道没有对应的 provider manifest)。
"""
from apps.core.logger import system_mgmt_logger as logger
from apps.system_mgmt.utils.i18n import system_mgmt_message


class PasswordEmailBatchConnectionError(Exception):
    """SMTP 连接或通道配置错误，整批可稍后重试。"""


def _email_locale(user) -> str:
    return getattr(user, "locale", None) or "zh-Hans"


def _email_title(user) -> str:
    return system_mgmt_message(_email_locale(user), "error.initial_password_email_title")


def _email_content(user, raw_password: str) -> str:
    template = system_mgmt_message(_email_locale(user), "error.initial_password_email_body")
    return template.replace("{username}", str(user.username)).replace("{password}", str(raw_password))


def send_initial_password_emails(source, deliveries: list[dict]) -> dict:
    """在一条 SMTP 会话中发送多封个性化初始密码邮件。"""
    from apps.system_mgmt.models import Channel
    from apps.system_mgmt.utils.channel_utils import send_personalized_email_messages

    password_init = ((source.platform_config or {}).get("password_init") or {})
    channel_id = password_init.get("email_channel_id")
    channel = Channel.objects.filter(id=channel_id, channel_type="email").first() if channel_id else None
    if not channel:
        raise PasswordEmailBatchConnectionError(system_mgmt_message("zh-Hans", "error.initial_password_email_channel_absent"))
    messages = []
    for delivery in deliveries:
        user = delivery["user"]
        if not user.email:
            continue
        messages.append({"key": user.username, "receiver": user.email, "title": _email_title(user), "content": _email_content(user, delivery["raw_password"])})
    try:
        return send_personalized_email_messages(channel, messages)
    except Exception as exc:
        raise PasswordEmailBatchConnectionError(str(exc)) from exc


def _send_initial_password_email_via_channel(user, raw_password: str, channel_id) -> dict:
    """通过指定 email channel_id 发送初始密码邮件。

    内部 helper，shared by:
    - 用户同步 send_email_via_runtime(从 sync_source.platform_config.password_init.email_channel_id 取)
    - 本地用户 create_user(从 SystemSettings.user_create_initial_password_random_email_channel_id 取)
    """
    from apps.system_mgmt.models import Channel, User
    from apps.system_mgmt.utils.channel_utils import send_email as channel_send_email

    locale = _email_locale(user)
    if not channel_id:
        return {"result": False, "message": system_mgmt_message(locale, "error.email_channel_id_required")}

    channel = Channel.objects.filter(id=channel_id, channel_type="email").first()
    if not channel:
        return {"result": False, "message": system_mgmt_message(locale, "error.email_channel_missing", channel_id=channel_id)}

    if not user.email:
        return {"result": False, "message": system_mgmt_message(locale, "error.user_email_empty")}

    try:
        # channel_utils.send_email(channel_obj, title, content, user_list_queryset)
        # 直接 SMTP 发邮件,不走 provider manifest 体系
        result = channel_send_email(
            channel,
            title=_email_title(user),
            content=_email_content(user, raw_password),
            user_list=User.objects.filter(id=user.id),
        )
        if isinstance(result, dict):
            return result
        # 旧版 send_email 可能返回 True/False
        return {
            "result": bool(result),
            "message": system_mgmt_message(locale, "error.email_sent" if result else "error.email_send_failed"),
        }
    except Exception as e:
        logger.error(
            f"发送初始密码邮件失败 user={user.username}: {e}",
            exc_info=True,
        )
        return {"result": False, "message": str(e)}


def send_email_via_runtime(user, raw_password: str) -> dict:
    """
    发送初始密码邮件给同步用户。

    Args:
        user: User 实例(已包含 email + sync_source + temporary_pwd=True)
        raw_password: 明文密码(sentinel 模式不会调到这里)

    Returns:
        dict: {"result": bool, "message": str}
    """
    sync_source = getattr(user, "sync_source", None)
    password_init = ((sync_source.platform_config or {}).get("password_init") or {}) if sync_source else {}
    channel_id = password_init.get("email_channel_id")
    return _send_initial_password_email_via_channel(user, raw_password, channel_id)


def send_local_user_initial_password_email(user, raw_password: str, channel_id) -> dict:
    """发送初始密码邮件给本地用户。

    与用户同步 send_email_via_runtime 共享同一邮件模板和 channel 路径,
    但 channel_id 来自 SystemSettings.user_create_initial_password_random_email_channel_id
    而不是 user.sync_source.platform_config.password_init.email_channel_id,
    因为本地用户没有 sync_source。
    """
    return _send_initial_password_email_via_channel(user, raw_password, channel_id)
