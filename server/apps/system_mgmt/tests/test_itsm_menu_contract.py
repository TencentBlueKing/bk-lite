import json
from pathlib import Path

from apps.core.utils.loader import LanguageLoader, clear_language_cache


def _permission_names(payload):
    names = []
    for group in payload["menus"]:
        for child in group["children"]:
            for operation in child["operation"]:
                names.append(f"{child['id']}-{operation}")
    return names


def test_itsm_menu_matches_design_roles():
    payload = json.loads(Path("support-files/system_mgmt/menus/itsm.json").read_text(encoding="utf-8"))
    assert payload["client_id"] == "itsm"
    assert payload["url"] == "/itsm/portal"
    assert payload["description"] == "app.itsm"
    permissions = _permission_names(payload)
    roles = {role["name"]: role for role in payload["roles"]}
    assert roles["admin"]["role_name"] == "itsm--admin"
    assert roles["admin"]["menus"] == permissions
    assert "manager" not in roles
    assert set(roles["handler"]["menus"]) == {"ticket-View", "ticket-Operate", "knowledge-View"}
    assert set(roles["user"]["menus"]) == {"portal-View", "ticket-View", "ticket-Add"}

    frontend = json.loads(Path("../web/src/app/itsm/constants/menu.json").read_text(encoding="utf-8"))
    backend_ids = {child["id"] for group in payload["menus"] for child in group["children"]}
    for locale in ("zh", "en"):
        titles = [item["title"] for item in frontend[locale]]
        assert len(titles) == 7
        for item in frontend[locale]:
            assert item["name"] in backend_ids
            for child in item.get("children", []):
                assert child["name"] in backend_ids


def test_itsm_system_mgmt_language_covers_app_detail():
    clear_language_cache(app="system_mgmt", lang="zh-Hans")
    clear_language_cache(app="system_mgmt", lang="en")
    zh = LanguageLoader(app="system_mgmt", default_lang="zh-Hans")
    en = LanguageLoader(app="system_mgmt", default_lang="en")
    assert zh.get("app_name.itsm") == "ITSM"
    assert en.get("app_name.itsm") == "ITSM"
    assert zh.get("app.itsm")
    assert en.get("app.itsm")
    assert zh.get("tag.itsm_portal")
    assert en.get("tag.itsm_portal")
