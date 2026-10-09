import pytest

from apps.workflow_orchestration.services.demo_templates import builtin_health_template_path, seed_builtin_health_template_snapshot


class MemoryStore:
    def __init__(self):
        self.objects = {}

    def put(self, key, content):
        payload = content.read() if hasattr(content, "read") else bytes(content)
        self.objects[key] = payload

    def get(self, key):
        payload = self.objects[key]
        return payload, key.rsplit("/", 1)[-1], len(payload)


@pytest.mark.parametrize("fmt", ["docx", "xlsx"])
def test_seed_builtin_health_template_snapshot_uploads_and_hashes(fmt):
    store = MemoryStore()

    snapshot = seed_builtin_health_template_snapshot(fmt, team_id=9, store=store)

    assert snapshot["format"] == fmt
    assert snapshot["size"] > 0
    assert len(snapshot["sha256"]) == 64
    assert snapshot["object_key"] in store.objects
    assert store.objects[snapshot["object_key"]] == builtin_health_template_path(fmt).read_bytes()


def test_builtin_health_template_path_rejects_unknown_format():
    with pytest.raises(ValueError, match="docx 或 xlsx"):
        builtin_health_template_path("pdf")
