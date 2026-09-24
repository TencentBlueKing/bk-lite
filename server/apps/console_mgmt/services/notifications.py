from apps.console_mgmt.models import Notification


def create_targeted_notification(
    *,
    app_module: str,
    content: str,
    recipient_usernames: list[str],
    target_url: str,
    source: str,
    event_key: str,
) -> Notification | None:
    """创建可重试的定向站内通知。"""
    recipients = list(dict.fromkeys(username.strip()[:32] for username in recipient_usernames if username.strip()))[:20]
    if not recipients:
        return None
    notification, _ = Notification.objects.get_or_create(
        event_key=event_key[:200],
        defaults={
            "app_module": app_module[:100],
            "content": content,
            "recipient_usernames": recipients,
            "target_url": target_url[:512],
            "source": source[:100],
        },
    )
    return notification
