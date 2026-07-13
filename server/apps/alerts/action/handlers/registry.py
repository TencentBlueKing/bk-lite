from apps.alerts.action.handlers.job import JobActionHandler

_HANDLERS = {JobActionHandler.action_type: JobActionHandler()}


def get_handler(action_type: str):
    """按动作类型取 handler。未来 itsm/webhook 只在此登记。"""
    return _HANDLERS[action_type]
