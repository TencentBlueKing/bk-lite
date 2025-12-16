from apps.core.exceptions.base_app_exception import BaseAppException


def period_to_seconds(period):
    """周期转换为秒"""
    if not period:
        raise BaseAppException("policy period is empty")

    period_type = period.get("type")
    period_value = period.get("value")

    if not period_type or period_value is None:
        raise BaseAppException("invalid period format, missing type or value")

    if period_type == "min":
        return period_value * 60
    elif period_type == "hour":
        return period_value * 3600
    elif period_type == "day":
        return period_value * 86400
    else:
        raise BaseAppException(f"invalid period type: {period_type}")


def format_period(period):
    """格式化周期为VictoriaLogs格式"""
    if not period:
        raise BaseAppException("policy period is empty")

    period_type = period.get("type")
    period_value = period.get("value")

    if not period_type or period_value is None:
        raise BaseAppException("invalid period format, missing type or value")

    if period_type == "min":
        return f'{period_value}m'
    elif period_type == "hour":
        return f'{period_value}h'
    elif period_type == "day":
        return f'{period_value}d'
    else:
        raise BaseAppException(f"invalid period type: {period_type}")
