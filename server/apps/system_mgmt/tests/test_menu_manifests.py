import json
from pathlib import Path

MENU_PATH = Path(__file__).resolve().parents[3] / "support-files" / "system_mgmt" / "menus" / "rum.json"


def _group_ids(menu_data: dict) -> dict[str, list[str]]:
    return {group["name"]: [child["id"] for child in group.get("children") or []] for group in menu_data.get("menus") or []}


def test_rum_role_menu_entries_match_declared_operations():
    menu_data = json.loads(MENU_PATH.read_text(encoding="utf-8"))
    allowed = {
        f"{child['id']}-{operation}"
        for group in menu_data.get("menus") or []
        for child in group.get("children") or []
        for operation in child.get("operation") or []
    }
    for role in menu_data.get("roles") or []:
        for entry in role.get("menus") or []:
            assert entry in allowed, f"rum role {role.get('name')} references unknown menu {entry}"


def test_rum_applications_live_under_integration():
    menu_data = json.loads(MENU_PATH.read_text(encoding="utf-8"))
    groups = _group_ids(menu_data)
    assert groups["Experience"] == ["sessions", "views", "funnels"]
    assert groups["Quality"] == ["errors", "releases"]
    assert groups["Events"] == ["alert_events", "monitors"]
    assert groups["Integration"] == ["applications"]
    assert groups["Governance"] == ["compliance"]
    assert menu_data["tags"] == [
        "tag.rum_experience",
        "tag.rum_quality",
        "tag.rum_alerting",
        "tag.rum_integration",
        "tag.rum_governance",
    ]
    assert menu_data["url"] == "/rum/applications"
