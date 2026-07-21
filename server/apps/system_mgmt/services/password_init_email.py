"""用户同步-初始密码邮件发送 helper。

通过 channel_utils.send_email 直接发送(不走 RuntimeApplicationService,
因为 email 通道没有对应的 provider manifest)。
"""
from apps.core.logger import system_mgmt_logger as logger


class PasswordEmailBatchConnectionError(Exception):
    """SMTP 连接或通道配置错误，整批可稍后重试。"""


def _email_content(user, raw_password: str) -> str:
    return (
        "<p>您好：</p>"
        "<p>您的 BK-Lite 账号已由管理员开通，账号信息如下：</p>"
        f"<p><strong>用户名：</strong>{user.username}</p>"
        f"<p><strong>初始密码：</strong>{raw_password}</p>"
        "<p>请使用以上初始密码登录，并在首次登录后立即修改密码。</p>"
        "<p><strong>安全提醒：</strong>请勿转发、截图或长期保存本邮件；如非本人操作，请联系管理员。</p>"
        "<p>此致<br>BK-Lite 平台</p>"
    )


def send_initial_password_emails(source, deliveries: list[dict]) -> dict:
    """在一条 SMTP 会话中发送多封个性化初始密码邮件。"""
    from apps.system_mgmt.models import Channel
    from apps.system_mgmt.utils.channel_utils import send_personalized_email_messages

    password_init = ((source.platform_config or {}).get("password_init") or {})
    channel_id = password_init.get("email_channel_id")
    channel = Channel.objects.filter(id=channel_id, channel_type="email").first() if channel_id else None
    if not channel:
        raise PasswordEmailBatchConnectionError("邮件通道不存在或类型不是 email")
    messages = []
    for delivery in deliveries:
        user = delivery["user"]
        if not user.email:
            continue
        messages.append({"key": user.username, "receiver": user.email, "title": "BK-Lite 账号开通通知", "content": _email_content(user, delivery["raw_password"])})
    try:
        return send_personalized_email_messages(channel, messages)
    except Exception as exc:
        raise PasswordEmailBatchConnectionError(str(exc)) from exc


def send_email_via_runtime(user, raw_password: str) -> dict:
    """
    发送初始密码邮件给同步用户。

    Args:
        user: User 实例(已包含 email + sync_source + temporary_pwd=True)
        raw_password: 明文密码(sentinel 模式不会调到这里)

    Returns:
        dict: {"result": bool, "message": str}
    """
    from apps.system_mgmt.models import Channel, User
    from apps.system_mgmt.utils.channel_utils import send_email as channel_send_email

    sync_source = getattr(user, "sync_source", None)
    password_init = ((sync_source.platform_config or {}).get("password_init") or {}) if sync_source else {}
    channel_id = password_init.get("email_channel_id")

    if not channel_id:
        return {"result": False, "message": "缺少 email_channel_id"}

    channel = Channel.objects.filter(id=channel_id, channel_type="email").first()
    if not channel:
        return {"result": False, "message": f"邮件通道 {channel_id} 不存在或类型不是 email"}

    if not user.email:
        return {"result": False, "message": "用户邮箱为空,无法发送"}

    try:
        # channel_utils.send_email(channel_obj, title, content, user_list_queryset)
        # 直接 SMTP 发邮件,不走 provider manifest 体系
        result = channel_send_email(
            channel,
            title="BK-Lite 账号开通通知",
            content=_email_content(user, raw_password),
            user_list=User.objects.filter(id=user.id),
        )
        if isinstance(result, dict):
            return result
        # 旧版 send_email 可能返回 True/False
        return {"result": bool(result), "message": "已发送" if result else "发送失败"}
    except Exception as e:
        logger.error(
            f"send_email_via_runtime 失败 user={user.username}: {e}",
            exc_info=True,
        )
        return {"result": False, "message": str(e)}
