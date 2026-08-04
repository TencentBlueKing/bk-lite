from apps.core.logger import alert_logger as logger


class IncidentExtensionRegistry:
    def __init__(self) -> None:
        self._handlers = {}

    def clear(self) -> None:
        self._handlers.clear()

    def register(self, key: str, handler) -> None:
        self._handlers[key] = handler

    def _dispatch(self, operation: str, incident_id: int) -> list:
        results = []
        for key, handler in tuple(self._handlers.items()):
            try:
                results.append(getattr(handler, operation)(incident_id))
            except Exception:
                logger.error(
                    "incident extension handler failed: key=%s operation=%s incident_id=%s",
                    key,
                    operation,
                    incident_id,
                )
        return results

    def participants_changed(self, incident_id: int) -> list:
        return self._dispatch("participants_changed", incident_id)

    def incident_closed(self, incident_id: int) -> list:
        return self._dispatch("incident_closed", incident_id)

    def incident_reopened(self, incident_id: int) -> list:
        return self._dispatch("incident_reopened", incident_id)


incident_extensions = IncidentExtensionRegistry()
