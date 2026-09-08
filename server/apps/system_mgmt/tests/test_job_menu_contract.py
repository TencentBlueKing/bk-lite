import json
from pathlib import Path


def test_job_normal_role_grants_execution_and_template_operations():
    payload = json.loads(Path("support-files/system_mgmt/menus/job.json").read_text(encoding="utf-8"))
    normal_role = next(role for role in payload["roles"] if role["name"] == "normal")

    expected_permissions = {
        f"{child['id']}-{operation}"
        for menu in payload["menus"]
        if menu["name"] in {"Execution", "Template"}
        for child in menu["children"]
        for operation in child["operation"]
    }

    assert expected_permissions <= set(normal_role["menus"])
