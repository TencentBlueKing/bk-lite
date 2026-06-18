"""Playbook 序列化器 + 归档解析 + 模型属性测试"""

import io
import tarfile
import zipfile
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import serializers as drf_serializers

from apps.job_mgmt.models import Playbook
from apps.job_mgmt.models.playbook import PLAYBOOK_BUCKET, playbook_upload_path
from apps.job_mgmt.serializers import playbook as pb

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _zip(files: dict, name="pb.zip") -> SimpleUploadedFile:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for path, content in files.items():
            z.writestr(path, content)
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type="application/zip")


def _targz(files: dict, name="pb.tar.gz") -> SimpleUploadedFile:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for path, content in files.items():
            data = content.encode()
            info = tarfile.TarInfo(name=path)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type="application/gzip")


class TestArchiveParsing:
    def test_parse_zip_extracts_readme_params_tree(self):
        f = _zip({"pb/README.md": "hello readme", "pb/roles/x/vars/main.yml": "key1: val1\nkey2: 2\n", "pb/playbook.yml": "x"})
        result = pb.parse_playbook_zip(f)
        assert result["readme"] == "hello readme"
        names = {p["name"] for p in result["params"]}
        assert {"key1", "key2"} <= names
        assert result["file_list"][0]["name"] == "pb"

    def test_parse_tarball(self):
        f = _targz({"pb/README.txt": "tar readme", "pb/defaults/main.yaml": "a: 1\n"})
        result = pb.parse_playbook_zip(f)
        assert result["readme"] == "tar readme"
        assert any(p["name"] == "a" for p in result["params"])

    def test_build_file_tree(self):
        tree = pb._build_file_tree(["a/b.yml", "a/c/d.yml", "a/c/"])
        assert tree[0]["name"] == "a" and tree[0]["type"] == "directory"

    def test_extract_params_dict(self):
        params = pb._extract_params_from_yaml(b"k: v\nnested:\n  x: 1\n")
        names = {p["name"] for p in params}
        assert "k" in names and "nested" in names

    def test_extract_params_non_dict_returns_empty(self):
        assert pb._extract_params_from_yaml(b"- 1\n- 2\n") == []

    def test_extract_params_invalid_yaml_returns_empty(self):
        assert pb._extract_params_from_yaml(b"::: not valid :::") == []


class TestIncrementVersion:
    def setup_method(self):
        self.s = pb.PlaybookUpgradeSerializer()

    @pytest.mark.parametrize(
        "current,expected",
        [
            ("v1.0.0", "v1.0.1"),
            ("1.2.3", "1.2.4"),
            ("v1.0", "v1.0.1"),
            ("vbad", "v1.0.1"),
            ("v1.0.x", "v1.0.1"),
        ],
    )
    def test_increment(self, current, expected):
        assert self.s._increment_version(current) == expected


class TestValidateFile:
    def test_valid_zip(self):
        s = pb.PlaybookCreateSerializer()
        f = _zip({"a/b": "c"})
        assert s.validate_file(f) is f

    def test_invalid_extension(self):
        s = pb.PlaybookCreateSerializer()
        with pytest.raises(drf_serializers.ValidationError):
            s.validate_file(SimpleUploadedFile("bad.txt", b"x"))


def _patch_storage_save():
    storage = Playbook._meta.get_field("file").storage
    return patch.object(storage, "save", return_value="playbooks/pb.zip")


class TestCreateAndUpgrade:
    def test_create_persists_parsed_content(self):
        f = _zip({"pb/README.md": "RM", "pb/vars/main.yml": "k: v\n"})
        s = pb.PlaybookCreateSerializer(data={"file": f, "version": "v1.0.0", "team": [1]})
        s.is_valid(raise_exception=True)
        with _patch_storage_save():
            instance = s.save()
        assert instance.name == "pb"
        assert instance.readme == "RM"
        assert instance.version == "v1.0.0"

    def test_upgrade_increments_version(self):
        existing = Playbook.objects.create(name="pb", version="v1.0.0", team=[1])
        f = _zip({"pb/README.md": "RM2"})
        s = pb.PlaybookUpgradeSerializer(instance=existing, data={"file": f})
        s.is_valid(raise_exception=True)
        with _patch_storage_save():
            instance = s.update(existing, s.validated_data)
        assert instance.version == "v1.0.1"
        assert instance.readme == "RM2"


class TestPlaybookModel:
    def test_upload_path(self):
        path = playbook_upload_path(None, "x.zip")
        assert path.startswith("playbooks/") and path.endswith("x.zip")

    def test_str(self):
        p = Playbook.objects.create(name="n", version="v1.0.0", team=[1])
        assert "n" in str(p) and "v1.0.0" in str(p)

    def test_properties_without_file(self):
        p = Playbook.objects.create(name="n", version="v1.0.0", team=[1])
        assert p.file_name == ""
        assert p.file_size == 0
        assert p.file_key == ""
        assert p.bucket_name == PLAYBOOK_BUCKET

    def test_properties_with_file(self):
        p = Playbook.objects.create(name="n", version="v1.0.0", team=[1])
        p.file = "playbooks/2026/06/16/a.zip"
        assert p.file_name == "a.zip"
        assert p.file_key == "playbooks/2026/06/16/a.zip"

    def test_file_size_with_file_handles_storage(self):
        p = Playbook.objects.create(name="n", version="v1.0.0", team=[1])
        p.file = "playbooks/x.zip"
        storage = Playbook._meta.get_field("file").storage
        with patch.object(storage, "size", return_value=123):
            assert p.file_size == 123

    def test_delete_with_file_calls_file_delete(self):
        p = Playbook.objects.create(name="n", version="v1.0.0", team=[1])
        p.file = "playbooks/x.zip"
        p.save()
        with patch.object(type(p.file), "delete") as mdel:
            p.delete()
        mdel.assert_called_once()
