"""脚本库 ZIP 打包服务单测。"""

import io
import json
import zipfile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.job_mgmt.constants import DangerousLevel
from apps.job_mgmt.models import DangerousRule, Script
from apps.job_mgmt.services.param_crypto import ParamCrypto
from apps.job_mgmt.services.script_pack_service import ScriptPackService, sanitize_folder_name, strip_encrypted_defaults

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _zip_bytes(files: dict[str, bytes | str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            payload = content.encode("utf-8") if isinstance(content, str) else content
            zf.writestr(name, payload)
    return buf.getvalue()


class TestStripEncryptedDefaults:
    def test_clears_encrypted_default_only(self):
        params = [
            {"name": "pwd", "default": "secret", "is_encrypted": True},
            {"name": "host", "default": "1.1.1.1", "is_encrypted": False},
        ]
        stripped = strip_encrypted_defaults(params)
        assert stripped[0]["default"] == ""
        assert stripped[0]["is_encrypted"] is True
        assert stripped[1]["default"] == "1.1.1.1"
        assert params[0]["default"] == "secret"

    def test_empty_input(self):
        assert strip_encrypted_defaults(None) == []
        assert strip_encrypted_defaults([]) == []


class TestSanitizeFolderName:
    def test_replaces_unsafe_chars(self):
        assert sanitize_folder_name('a/b:c*?"<>|') == "a_b_c______"
        assert sanitize_folder_name("  ..  ") == "script"


class TestScriptPackService:
    def test_build_export_zip_structure_and_strip_secrets(self):
        params = [{"name": "pwd", "default": "secret", "is_encrypted": True}]
        ParamCrypto.encrypt_param_defaults(params)
        script = Script.objects.create(
            name="巡检",
            description="desc",
            content="echo hi",
            script_type="shell",
            timeout=120,
            params=params,
            team=[1],
        )

        buffer = ScriptPackService.build_export_zip([script])
        with zipfile.ZipFile(buffer) as zf:
            names = set(zf.namelist())
            assert "manifest.json" in names
            assert "巡检/meta.json" in names
            assert "巡检/script.sh" in names
            meta = json.loads(zf.read("巡检/meta.json"))
            assert meta["name"] == "巡检"
            assert meta["timeout"] == 120
            assert meta["params"][0]["default"] == ""
            assert meta["params"][0]["is_encrypted"] is True
            assert zf.read("巡检/script.sh").decode("utf-8") == "echo hi"
            manifest = json.loads(zf.read("manifest.json"))
            assert manifest["script_count"] == 1

    def test_parse_and_import_roundtrip(self):
        script = Script.objects.create(
            name="demo",
            content="echo demo",
            script_type="shell",
            params=[{"name": "host", "default": "x", "is_encrypted": False}],
            team=[1],
        )
        buffer = ScriptPackService.build_export_zip([script])
        upload = SimpleUploadedFile("script-pack.zip", buffer.read(), content_type="application/zip")

        drafts = ScriptPackService.parse_import_zip(upload)
        assert len(drafts) == 1
        assert drafts[0].name == "demo"

        # 同组织同名应跳过
        result = ScriptPackService.import_scripts(drafts, [1], username="admin")
        assert len(result.skipped) == 1
        assert result.created == []

        # 换组织可创建；加密 default 保持空
        drafts[0].params = [{"name": "pwd", "default": "should-clear", "is_encrypted": True}]
        result = ScriptPackService.import_scripts(drafts, [2], username="admin")
        assert len(result.created) == 1
        created = Script.objects.get(pk=result.created[0].id)
        assert created.team == [2]
        assert created.params[0]["default"] in ("", None) or created.params[0]["default"] == ""
        # 空 default 不会被加密成密文
        assert created.params[0]["default"] == ""

    def test_import_skips_dangerous_as_failed(self):
        DangerousRule.objects.create(
            name="no-rm",
            pattern="rm -rf",
            level=DangerousLevel.FORBIDDEN,
            is_enabled=True,
            team=[],
        )
        files = {
            "manifest.json": json.dumps({"format_version": 1, "script_count": 1}),
            "bad/meta.json": json.dumps(
                {
                    "format_version": 1,
                    "name": "bad",
                    "description": "",
                    "script_type": "shell",
                    "timeout": 60,
                    "params": [],
                }
            ),
            "bad/script.sh": "rm -rf /",
            "ok/meta.json": json.dumps(
                {
                    "format_version": 1,
                    "name": "ok",
                    "description": "",
                    "script_type": "shell",
                    "timeout": 60,
                    "params": [],
                }
            ),
            "ok/script.sh": "echo ok",
        }
        upload = SimpleUploadedFile("pack.zip", _zip_bytes(files), content_type="application/zip")
        drafts = ScriptPackService.parse_import_zip(upload)
        result = ScriptPackService.import_scripts(drafts, [1], username="admin")
        assert len(result.created) == 1
        assert result.created[0].name == "ok"
        assert len(result.failed) == 1
        assert "高危" in result.failed[0].reason

    def test_parse_rejects_invalid_zip(self):
        upload = SimpleUploadedFile("pack.zip", b"not-a-zip", content_type="application/zip")
        with pytest.raises(ValueError, match="无效"):
            ScriptPackService.parse_import_zip(upload)

    def test_parse_rejects_empty_pack(self):
        upload = SimpleUploadedFile(
            "pack.zip",
            _zip_bytes({"manifest.json": json.dumps({"format_version": 1, "script_count": 0})}),
            content_type="application/zip",
        )
        with pytest.raises(ValueError, match="未找到"):
            ScriptPackService.parse_import_zip(upload)

    def test_parse_accepts_macos_wrapped_pack(self):
        """macOS 重命名/重压后常见：根目录多一层包装文件夹，并夹带 __MACOSX。"""
        files = {
            "script-pack (11111)/manifest.json": json.dumps({"format_version": 1, "script_count": 1}),
            "script-pack (11111)/demo/meta.json": json.dumps(
                {
                    "format_version": 1,
                    "name": "加密参数验证",
                    "description": "",
                    "script_type": "powershell",
                    "timeout": 600,
                    "params": [{"name": "pwd", "default": "", "is_encrypted": True}],
                }
            ),
            "script-pack (11111)/demo/script.ps1": 'Write-Host "hi"',
            "script-pack (11111)/.DS_Store": b"junk",
            "__MACOSX/script-pack (11111)/._manifest.json": b"junk",
            "__MACOSX/script-pack (11111)/demo/._meta.json": b"junk",
        }
        upload = SimpleUploadedFile("pack.zip", _zip_bytes(files), content_type="application/zip")
        drafts = ScriptPackService.parse_import_zip(upload)
        assert len(drafts) == 1
        assert drafts[0].name == "加密参数验证"
        assert drafts[0].script_type == "powershell"
        assert drafts[0].content == 'Write-Host "hi"'
        assert drafts[0].source_folder == "script-pack (11111)/demo"
