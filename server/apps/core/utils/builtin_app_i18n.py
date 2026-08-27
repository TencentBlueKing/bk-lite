"""内置应用展示名的语言包查找。"""

from typing import Any, MutableMapping, Optional


def translate_builtin_app_display_name(
    app: MutableMapping[str, Any],
    loader: Any,
) -> None:
    """按 app_name.{client_id} 覆盖内置应用 display_name；无词条则保持原值。"""
    if not app.get("is_build_in"):
        return
    name = app.get("name")
    if not name:
        return
    translated = localized_app_display_name(name, loader)
    if translated:
        app["display_name"] = translated


def localized_app_display_name(
    app_name: str,
    loader: Any,
    fallback: Optional[str] = None,
) -> Optional[str]:
    if not app_name:
        return fallback
    translated = loader.get(f"app_name.{app_name}")
    return translated or fallback
