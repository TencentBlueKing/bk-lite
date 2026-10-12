"""作业模板版本：日期版本号、快照、对比和恢复。"""

import io
import json
import zipfile
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import patch

import pytest
from django.core.files.storage import InMemoryStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.job_mgmt.constants import DangerousLevel
from apps.job_mgmt.models import DangerousRule, Playbook, PlaybookRevision, Script, ScriptRevision
from apps.job_mgmt.services.template_revision import version_label

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

SCRIPT_URL = "/api/v1/job_mgmt/api/script/"
PLAYBOOK_URL = "/api/v1/job_mgmt/api/playbook/"
SECRET = "sentinel-secret-do-not-leak"
NEW_SECRET = "sentinel-secret-replaced"


def test_version_label_uses_shanghai_date_and_starts_extra_same_day_at_two():
    morning = datetime(2026, 9, 28, 2, 0, tzinfo=timezone.utc)
    assert version_label(morning, []) == "v2026.09.28"
    assert version_label(morning, ["v2026.09.28"]) == "v2026.09.28.2"
    assert version_label(morning, ["v2026.09.28", "v2026.09.28.2"]) == "v2026.09.28.3"

    after_shanghai_midnight = datetime(2026, 9, 28, 16, 30, tzinfo=timezone.utc)
    assert version_label(after_shanghai_midnight, []) == "v2026.09.29"


def _script_body(**over):
    body = {"name": "巡检", "content": "echo v1", "script_type": "shell", "team": [1], "timeout": 60}
    body.update(over)
    return body


class TestScriptRevisions:
    def test_create_update_and_unchanged_save(self, su_client):
        created = su_client.post(SCRIPT_URL, _script_body(), format="json")
        assert created.status_code == 201
        script_id = created.data["id"]
        assert ScriptRevision.objects.filter(script_id=script_id).count() == 1

        same = su_client.put(f"{SCRIPT_URL}{script_id}/", _script_body(), format="json")
        assert same.status_code == 200
        assert ScriptRevision.objects.filter(script_id=script_id).count() == 1

        changed = su_client.put(f"{SCRIPT_URL}{script_id}/", _script_body(content="echo v2"), format="json")
        assert changed.status_code == 200
        assert ScriptRevision.objects.filter(script_id=script_id).count() == 2
        labels = list(ScriptRevision.objects.filter(script_id=script_id).order_by("id").values_list("label", flat=True))
        assert labels[1] == f"{labels[0]}.2" or not labels[1].startswith(labels[0])

    def test_first_edit_of_existing_script_keeps_previous_content(self, su_client):
        script = Script.objects.create(name="旧脚本", content="echo old", script_type="shell", team=[1], updated_by="old-user")

        resp = su_client.put(
            f"{SCRIPT_URL}{script.id}/",
            {"name": "旧脚本", "content": "echo new", "script_type": "shell", "team": [1]},
            format="json",
        )

        assert resp.status_code == 200
        revisions = list(ScriptRevision.objects.filter(script=script).order_by("id"))
        assert [item.content for item in revisions] == ["echo old", "echo new"]
        assert revisions[0].created_by == "old-user"

    def test_list_backfills_current_script_once(self, su_client):
        script = Script.objects.create(name="现网", content="echo now", script_type="shell", team=[1], updated_by="keeper")

        first = su_client.get(f"{SCRIPT_URL}{script.id}/revisions/")
        second = su_client.get(f"{SCRIPT_URL}{script.id}/revisions/")

        assert first.status_code == 200
        assert first.data["count"] == 1
        assert first.data["items"][0]["is_current"] is True
        assert first.data["items"][0]["label"].startswith("v")
        assert first.data["items"][0]["created_by"] == "keeper"
        assert second.data["count"] == 1

    def test_list_shows_latest_date_version_without_copying_history(self, su_client):
        bare = Script.objects.create(name="无历史", content="echo now", script_type="shell", team=[1])
        Script.objects.filter(pk=bare.pk).update(updated_at=datetime(2026, 9, 28, 2, 0, tzinfo=timezone.utc))
        tracked = Script.objects.create(name="有历史", content="echo now", script_type="shell", team=[1])
        common = {"script": tracked, "name": tracked.name, "script_type": "shell", "created_by": "admin"}
        ScriptRevision.objects.create(
            **common,
            label="v2026.09.28",
            content="echo old",
            content_hash="a" * 64,
            created_at=datetime(2026, 9, 28, 2, 0, tzinfo=timezone.utc),
        )
        ScriptRevision.objects.create(
            **common,
            label="v2026.09.28.2",
            content="echo now",
            content_hash="b" * 64,
            created_at=datetime(2026, 9, 28, 3, 0, tzinfo=timezone.utc),
        )

        with patch("apps.core.utils.viewset_utils.get_permission_rules", return_value={"team": [1], "instance": []}):
            listed = su_client.get(f"{SCRIPT_URL}?page_size=50")

        assert listed.status_code == 200
        labels = {item["name"]: item["current_revision_label"] for item in listed.data["items"]}
        assert labels["无历史"] == "v2026.09.28"
        assert labels["有历史"] == "v2026.09.28.2"
        assert ScriptRevision.objects.filter(script=bare).count() == 0

    def test_compare_hides_encrypted_default_and_reports_change(self, su_client):
        created = su_client.post(
            SCRIPT_URL,
            _script_body(
                content="echo v1",
                params=[{"name": "pwd", "label": "密码", "default": SECRET, "is_encrypted": True}],
            ),
            format="json",
        )
        script_id = created.data["id"]
        su_client.put(
            f"{SCRIPT_URL}{script_id}/",
            _script_body(
                content="echo v2",
                params=[{"name": "pwd", "label": "密码", "default": NEW_SECRET, "is_encrypted": True}],
            ),
            format="json",
        )
        older = ScriptRevision.objects.filter(script_id=script_id).order_by("id").first()

        compared = su_client.get(f"{SCRIPT_URL}{script_id}/revisions/{older.id}/compare/")

        assert compared.status_code == 200
        rendered = json.dumps(compared.data, ensure_ascii=False)
        assert SECRET not in rendered
        assert NEW_SECRET not in rendered
        assert compared.data["content"]["selected"] == "echo v1"
        assert compared.data["content"]["current"] == "echo v2"
        assert compared.data["params"][0]["default_changed"] is True
        assert compared.data["params"][0]["current"]["default"] == "******"
        assert compared.data["params"][0]["selected"]["default"] == "******"

    def test_restore_rewrites_current_and_appends_a_new_revision(self, su_client):
        created = su_client.post(SCRIPT_URL, _script_body(content="echo v1"), format="json")
        script_id = created.data["id"]
        su_client.put(f"{SCRIPT_URL}{script_id}/", _script_body(content="echo v2"), format="json")
        older = ScriptRevision.objects.filter(script_id=script_id).order_by("id").first()
        current = ScriptRevision.objects.filter(script_id=script_id).order_by("-id").first()

        rejected = su_client.post(f"{SCRIPT_URL}{script_id}/revisions/{current.id}/restore/")
        restored = su_client.post(f"{SCRIPT_URL}{script_id}/revisions/{older.id}/restore/")

        assert rejected.status_code == 400
        assert restored.status_code == 200
        script = Script.objects.get(pk=script_id)
        assert script.content == "echo v1"
        assert ScriptRevision.objects.filter(script_id=script_id).count() == 3
        assert ScriptRevision.objects.filter(script_id=script_id).order_by("-id").first().content == "echo v1"

    def test_restore_rejects_dangerous_command_and_name_conflict(self, su_client):
        script = Script.objects.create(name="可恢复", content="rm -rf /", script_type="shell", team=[1])
        ScriptRevision.objects.create(
            script=script,
            label="v2026.09.28",
            name="可恢复",
            script_type="shell",
            content="rm -rf /",
            timeout=60,
            content_hash="old",
            created_by="old",
        )
        ScriptRevision.objects.create(
            script=script,
            label="v2026.09.28.2",
            name="可恢复",
            script_type="shell",
            content="echo safe",
            timeout=60,
            content_hash="new",
            created_by="new",
        )
        script.content = "echo safe"
        script.save(update_fields=["content", "updated_at"])
        DangerousRule.objects.create(name="no-rm", pattern="rm -rf", level=DangerousLevel.FORBIDDEN, is_enabled=True, team=[])
        older = ScriptRevision.objects.get(script=script, label="v2026.09.28")

        blocked = su_client.post(f"{SCRIPT_URL}{script.id}/revisions/{older.id}/restore/")

        assert blocked.status_code == 400
        assert "高危命令" in blocked.data["error"] or "high-risk" in blocked.data["error"]
        script.refresh_from_db()
        assert script.content == "echo safe"

        other = Script.objects.create(name="占用名", content="echo other", script_type="shell", team=[1])
        ScriptRevision.objects.create(
            script=script,
            label="v2026.09.27",
            name=other.name,
            script_type="shell",
            content="echo renamed",
            timeout=60,
            content_hash="name",
            created_by="old",
        )
        named = ScriptRevision.objects.get(script=script, label="v2026.09.27")
        conflict = su_client.post(f"{SCRIPT_URL}{script.id}/revisions/{named.id}/restore/")
        assert conflict.status_code == 400
        assert "组织内" in str(conflict.data)

    def test_missing_revision_and_invalid_page(self, su_client):
        script = Script.objects.create(name="s", content="echo", script_type="shell", team=[1])
        assert su_client.get(f"{SCRIPT_URL}{script.id}/revisions/999/compare/").status_code == 404
        assert su_client.get(f"{SCRIPT_URL}{script.id}/revisions/?page=0").status_code == 400

    def test_revision_stays_inside_template_permission(self, api_client, authenticated_user):
        foreign = Script.objects.create(name="外部", content="echo foreign", script_type="shell", team=[2])
        authenticated_user.is_superuser = False
        authenticated_user.group_list = [{"id": 1, "name": "Current"}, {"id": 2, "name": "Foreign"}]
        authenticated_user.permission = {"job": {"script_library-View"}}
        api_client.cookies["current_team"] = "1"
        rules = {"team": [], "instance": [{"id": foreign.id, "permission": ["View"]}]}

        with patch("apps.core.utils.viewset_utils.get_permission_rules", return_value=rules):
            response = api_client.get(f"{SCRIPT_URL}{foreign.id}/revisions/")

        assert response.status_code == 200
        assert response.json()["result"] is False
        assert "items" not in response.json()


def _zip(files: dict, name: str) -> SimpleUploadedFile:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return SimpleUploadedFile(name, buf.getvalue(), content_type="application/zip")


@contextmanager
def _memory_playbook_storage():
    storage = InMemoryStorage()
    with (
        patch.object(Playbook._meta.get_field("file"), "storage", storage),
        patch.object(PlaybookRevision._meta.get_field("file"), "storage", storage),
    ):
        yield storage


def _zip_text(file_field) -> str:
    file_field.open("rb")
    try:
        with zipfile.ZipFile(io.BytesIO(file_field.read())) as archive:
            return archive.read("playbook.yml").decode("utf-8")
    finally:
        file_field.close()


class TestPlaybookRevisions:
    def test_upgrade_keeps_old_archive_and_restore_puts_it_back(self, su_client):
        with _memory_playbook_storage():
            created = su_client.post(
                PLAYBOOK_URL,
                {"file": _zip({"playbook.yml": "one", "README.md": "readme-one"}, "one.zip"), "version": "v1.0.0", "team": [1]},
                format="multipart",
            )
            assert created.status_code == 201
            playbook_id = created.data["id"]
            upgraded = su_client.post(
                f"{PLAYBOOK_URL}{playbook_id}/upgrade/",
                {"file": _zip({"playbook.yml": "two", "README.md": "readme-two"}, "two.zip")},
                format="multipart",
            )
            assert upgraded.status_code == 200
            assert upgraded.data["version"] == "v1.0.1"

            revisions = list(PlaybookRevision.objects.filter(playbook_id=playbook_id).order_by("id"))
            assert len(revisions) == 2
            assert _zip_text(revisions[0].file) == "one"
            playbook = Playbook.objects.get(pk=playbook_id)
            assert _zip_text(playbook.file) == "two"

            compared = su_client.get(f"{PLAYBOOK_URL}{playbook_id}/revisions/{revisions[0].id}/compare/")
            assert compared.status_code == 200
            playbook_file = next(item for item in compared.data["files"] if item["path"] == "playbook.yml")
            assert playbook_file["status"] == "modified"
            assert playbook_file["selected_text"] == "one"
            assert playbook_file["current_text"] == "two"
            assert compared.data["readme"]["selected"] == "readme-one"
            assert compared.data["readme"]["current"] == "readme-two"
            assert all(item["key"] != "version" for item in compared.data["fields"])

            restored = su_client.post(f"{PLAYBOOK_URL}{playbook_id}/revisions/{revisions[0].id}/restore/")
            assert restored.status_code == 200
            playbook.refresh_from_db()
            assert playbook.version == "v1.0.0"
            assert playbook.readme == "readme-one"
            assert _zip_text(playbook.file) == "one"
            assert PlaybookRevision.objects.filter(playbook_id=playbook_id).count() == 3
            assert _zip_text(revisions[0].file) == "one"

    def test_list_shows_latest_date_version_without_copying_history(self, su_client):
        bare = Playbook.objects.create(name="无历史作业", team=[1], version="v1.0.0")
        Playbook.objects.filter(pk=bare.pk).update(updated_at=datetime(2026, 10, 9, 2, 0, tzinfo=timezone.utc))
        tracked = Playbook.objects.create(name="有历史作业", team=[1], version="v1.0.2")
        common = {"playbook": tracked, "name": tracked.name, "created_by": "admin"}
        PlaybookRevision.objects.create(
            **common,
            label="v2026.10.09",
            version="v1.0.0",
            content_hash="c" * 64,
            created_at=datetime(2026, 10, 8, 16, 0, tzinfo=timezone.utc),
        )
        PlaybookRevision.objects.create(
            **common,
            label="v2026.10.10.2",
            version="v1.0.2",
            content_hash="d" * 64,
            created_at=datetime(2026, 10, 10, 7, 0, tzinfo=timezone.utc),
        )

        with patch("apps.core.utils.viewset_utils.get_permission_rules", return_value={"team": [1], "instance": []}):
            listed = su_client.get(f"{PLAYBOOK_URL}?page_size=50")

        assert listed.status_code == 200
        rows = {item["name"]: item for item in listed.data["items"]}
        assert rows["无历史作业"]["current_revision_label"] == "v2026.10.09"
        assert rows["有历史作业"]["current_revision_label"] == "v2026.10.10.2"
        assert rows["有历史作业"]["version"] == "v1.0.2"
        assert PlaybookRevision.objects.filter(playbook=bare).count() == 0
