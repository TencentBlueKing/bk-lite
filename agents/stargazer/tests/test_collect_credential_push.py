from pathlib import Path


def test_stargazer_has_no_credential_result_transport_or_projection():
    root = Path(__file__).parents[1]
    source_paths = (
        root / "api" / "collect.py",
        root / "core" / "collection" / "application.py",
        root / "core" / "collection" / "result_publisher.py",
        root / "server.py",
    )
    production_source = "\n".join(path.read_text(encoding="utf-8") for path in source_paths)

    assert "/credential_results" not in production_source
    assert "credential_projection" not in production_source
    assert "CredentialStateCache" not in production_source
    assert "credential_result_subject" not in production_source
    assert not (root / "core" / "infra" / "credential_state_cache.py").exists()
    assert not (root / "service" / "collect_credential_result_push_service.py").exists()
    assert not (root / "service" / "collect_credential_result_push_task.py").exists()
