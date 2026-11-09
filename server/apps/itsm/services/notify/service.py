from jinja2 import Template

from apps.core.logger import itsm_logger
from apps.itsm.models import NotifyTemplate


def render_template(event: str, variables: dict) -> tuple[str, str]:
    template = NotifyTemplate.objects.filter(event=event).first()
    if template is None:
        return event, ""
    return Template(template.title_tpl).render(**variables), Template(template.content_tpl).render(**variables)


def dispatch_notification(event: str, variables: dict, receivers: list[str]) -> dict:
    title, content = render_template(event, variables)
    itsm_logger.info("ITSM 通知 %s -> %s", event, ",".join(receivers))
    return {"title": title, "content": content, "receivers": receivers}
