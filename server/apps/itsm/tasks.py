from celery import shared_task

from apps.itsm.services.notify.service import deliver_with_retry


@shared_task(bind=True, max_retries=3)
def send_notify(self, event: str, variables: dict, receivers: list[str], event_key: str = ""):
    """异步发送通知。调用方未启动 Celery 时也可直接执行本函数完成三次重试。"""
    try:
        return deliver_with_retry(event, variables, receivers, event_key)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2)
