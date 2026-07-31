from pathlib import Path


def test_apm_production_code_has_no_alerts_app_dependency():
    app_root = Path(__file__).resolve().parents[1]
    offenders = []
    for path in app_root.rglob("*.py"):
        if "tests" in path.parts:
            continue
        if "apps.alerts" in path.read_text(encoding="utf-8"):
            offenders.append(str(path.relative_to(app_root)))

    assert offenders == []
