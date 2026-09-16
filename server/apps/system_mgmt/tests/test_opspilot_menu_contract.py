import json
from pathlib import Path


def test_opspilot_knowledge_base_menu_follows_agent():
    payload = json.loads(Path("support-files/system_mgmt/menus/opspilot.json").read_text(encoding="utf-8"))
    menu_names = [item["name"] for item in payload["menus"]]

    assert menu_names == [
        "Studio",
        "Agent",
        "Knowledge Base",
        "Tool",
        "Memory",
        "Model",
    ]
    wiki = next(child for item in payload["menus"] if item["name"] == "Knowledge Base" for child in item["children"])
    assert wiki["id"] == "wiki_list"
    assert wiki["operation"] == ["View", "Add", "Edit", "Delete"]
