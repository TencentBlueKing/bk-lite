from apps.core.utils.user_display import build_user_display_map, format_user_identifiers

__all__ = ["build_user_display_map", "format_user_identifiers", "enrich_alerts_handlers_display"]


def enrich_alerts_handlers_display(alerts: list[dict]) -> None:
    identifiers = []
    for alert in alerts:
        identifiers.extend(alert.get("handlers") or [])
    user_map = build_user_display_map(identifiers)
    for alert in alerts:
        alert["handlers_display"] = format_user_identifiers(alert.get("handlers") or [], user_map)
