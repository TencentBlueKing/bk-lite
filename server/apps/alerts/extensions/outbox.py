from apps.core.logger import alert_logger as logger


class OutboxHandlerRegistry:
    """Alerts Outbox 的可选能力注册表。

    社区版只负责可靠投递状态机；企业版通过公开接口注册业务处理器。
    """

    def __init__(self):
        self._handlers = {}
        self._observers = {}

    def clear(self):
        self._handlers.clear()
        self._observers.clear()

    def register(self, kind, handler):
        self._handlers[kind] = handler

    def register_observer(self, key, observer):
        self._observers[key] = observer

    def observe_backlog(self):
        for key, observer in tuple(self._observers.items()):
            try:
                observer()
            except Exception:
                logger.error(
                    "outbox extension observer failed: key=%s",
                    key,
                )

    def deliver(self, kind, payload, *, delivery_claim=None):
        handler = self._handlers.get(kind)
        if handler is None:
            return False
        handler.deliver(payload, delivery_claim=delivery_claim)
        return True

    def schedule(self, kind, record_id):
        handler = self._handlers.get(kind)
        scheduler = getattr(handler, "schedule", None) if handler is not None else None
        if scheduler is None:
            return False
        scheduler(record_id)
        return True

    def notify_exhausted(self, kind, payload, error, *, record_id):
        handler = self._handlers.get(kind)
        exhausted = getattr(handler, "exhausted", None) if handler is not None else None
        if exhausted is None:
            return False
        try:
            exhausted(payload, error)
        except Exception:
            logger.error(
                "outbox extension exhausted hook failed: outbox_id=%s kind=%s",
                record_id,
                kind,
            )
        return True


outbox_handlers = OutboxHandlerRegistry()
