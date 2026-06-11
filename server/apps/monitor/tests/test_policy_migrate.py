import json

from apps.monitor.management.services import policy_migrate


def test_migrate_policy_skips_empty_policy_file(tmp_path, monkeypatch):
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps([]), encoding="utf-8")
    find_results = iter([[str(policy_path)], []])
    imported = []

    monkeypatch.setattr(policy_migrate, "find_files_by_pattern", lambda *args, **kwargs: next(find_results))
    monkeypatch.setattr(policy_migrate.PolicyService, "import_monitor_policy", imported.append)

    policy_migrate.migrate_policy()

    assert imported == []
