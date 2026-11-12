import requests

from apps.core.logger import itsm_logger as logger
from apps.core.utils.ssrf_validator import SSRFError, SSRFValidator
from apps.itsm.models.extend import TodoSync


def push_todo(ticket, task) -> None:
    item = TodoSync.objects.exclude(url="").first()
    if item is None:
        return
    try:
        SSRFValidator().validate_url(item.url)
        requests.post(item.url, json={"sn": ticket.sn, "node": task.node_id}, timeout=3)
    except (SSRFError, requests.RequestException) as exc:
        logger.warning("待办同步失败 ticket_id=%s error_type=%s", ticket.id, type(exc).__name__)
