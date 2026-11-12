from django.dispatch import Signal, receiver

from apps.itsm.services.notify.service import deliver_with_retry

itsm_event = Signal()


@receiver(itsm_event)
def send_itsm_notification(sender, event, receivers, variables, event_key="", **kwargs):
    deliver_with_retry(event, variables or {}, list(receivers or []), event_key or "", site_only=bool(getattr(sender, "is_test", False)))
