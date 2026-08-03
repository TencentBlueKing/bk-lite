from pathlib import Path


def test_apm_production_code_only_uses_public_cross_app_contracts():
    app_root = Path(__file__).resolve().parents[1]
    forbidden_imports = ("apps.alerts", "apps.system_mgmt", "apps.monitor", "apps.log")
    offenders = []
    for path in app_root.rglob("*.py"):
        if "tests" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        for forbidden_import in forbidden_imports:
            if forbidden_import in source:
                offenders.append(f"{path.relative_to(app_root)}: {forbidden_import}")

    assert offenders == []
