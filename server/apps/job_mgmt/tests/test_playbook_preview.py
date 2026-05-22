"""Playbook 文件预览功能单元测试"""

import io
import tarfile
import zipfile

import pytest

from apps.job_mgmt.serializers.playbook import extract_file_from_archive, get_file_type, is_binary_file, validate_file_path


class MockFile:
    """模拟 Django FileField 对象"""

    def __init__(self, name: str, content: bytes):
        self.name = name
        self._content = content
        self._position = 0

    def read(self):
        return self._content

    def seek(self, position):
        self._position = position


def create_zip_file(files: dict) -> bytes:
    """创建测试用 ZIP 文件"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in files.items():
            zf.writestr(path, content)
    return buffer.getvalue()


def create_tar_gz_file(files: dict) -> bytes:
    """创建测试用 tar.gz 文件"""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tf:
        for path, content in files.items():
            data = content.encode() if isinstance(content, str) else content
            info = tarfile.TarInfo(name=path)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


@pytest.mark.unit
class TestGetFileType:
    """文件类型检测测试"""

    def test_yaml_files(self):
        assert get_file_type("playbook.yml") == "yaml"
        assert get_file_type("vars/main.yaml") == "yaml"

    def test_markdown_files(self):
        assert get_file_type("README.md") == "markdown"

    def test_python_files(self):
        assert get_file_type("script.py") == "python"

    def test_shell_files(self):
        assert get_file_type("deploy.sh") == "bash"

    def test_json_files(self):
        assert get_file_type("config.json") == "json"

    def test_jinja2_files(self):
        assert get_file_type("template.j2") == "jinja2"
        assert get_file_type("config.jinja2") == "jinja2"

    def test_ini_files(self):
        assert get_file_type("config.ini") == "ini"
        assert get_file_type("settings.cfg") == "ini"
        assert get_file_type("nginx.conf") == "ini"

    def test_unknown_files(self):
        assert get_file_type("unknown.xyz") == "text"
        assert get_file_type("noextension") == "text"


@pytest.mark.unit
class TestIsBinaryFile:
    """二进制文件检测测试"""

    def test_binary_extension(self):
        assert is_binary_file("module.pyc", b"") is True
        assert is_binary_file("lib.so", b"") is True
        assert is_binary_file("app.exe", b"") is True
        assert is_binary_file("archive.zip", b"") is True

    def test_binary_content(self):
        # 包含 null 字节的内容
        binary_content = b"some\x00binary\x00content"
        assert is_binary_file("data.txt", binary_content) is True

    def test_text_file(self):
        text_content = b"Hello, World!\nThis is a text file."
        assert is_binary_file("readme.txt", text_content) is False

    def test_yaml_file(self):
        yaml_content = b"---\nname: test\nvalue: 123\n"
        assert is_binary_file("config.yml", yaml_content) is False


@pytest.mark.unit
class TestValidateFilePath:
    """路径安全验证测试"""

    def test_valid_path(self):
        valid_paths = ["playbook.yml", "roles/example/tasks/main.yml"]
        is_valid, error = validate_file_path("playbook.yml", valid_paths)
        assert is_valid is True
        assert error == ""

    def test_path_traversal_dotdot(self):
        valid_paths = ["playbook.yml"]
        is_valid, error = validate_file_path("../../../etc/passwd", valid_paths)
        assert is_valid is False
        assert "非法" in error

    def test_absolute_path_unix(self):
        valid_paths = ["playbook.yml"]
        is_valid, error = validate_file_path("/etc/passwd", valid_paths)
        assert is_valid is False
        assert "非法" in error

    def test_absolute_path_windows(self):
        valid_paths = ["playbook.yml"]
        is_valid, error = validate_file_path("\\Windows\\System32", valid_paths)
        assert is_valid is False
        assert "非法" in error

    def test_file_not_in_archive(self):
        valid_paths = ["playbook.yml"]
        is_valid, error = validate_file_path("nonexistent.yml", valid_paths)
        assert is_valid is False
        assert "不存在" in error


@pytest.mark.unit
class TestExtractFileFromArchive:
    """文件提取测试"""

    def test_extract_from_zip(self):
        """从 ZIP 文件提取"""
        files = {
            "playbook-template/playbook.yml": "---\n- name: Test\n  hosts: all\n",
            "playbook-template/README.md": "# Test Playbook\n",
        }
        zip_content = create_zip_file(files)
        mock_file = MockFile("test.zip", zip_content)

        result = extract_file_from_archive(mock_file, "playbook-template/playbook.yml")

        assert result["file_name"] == "playbook.yml"
        assert result["file_path"] == "playbook-template/playbook.yml"
        assert result["file_type"] == "yaml"
        assert "- name: Test" in result["content"]
        assert result["file_size"] > 0

    def test_extract_from_tar_gz(self):
        """从 tar.gz 文件提取"""
        files = {
            "playbook-template/playbook.yml": "---\n- name: Test\n  hosts: all\n",
        }
        tar_content = create_tar_gz_file(files)
        mock_file = MockFile("test.tar.gz", tar_content)

        result = extract_file_from_archive(mock_file, "playbook-template/playbook.yml")

        assert result["file_name"] == "playbook.yml"
        assert result["file_type"] == "yaml"

    def test_file_not_found(self):
        """文件不存在"""
        files = {"playbook.yml": "content"}
        zip_content = create_zip_file(files)
        mock_file = MockFile("test.zip", zip_content)

        with pytest.raises(ValueError) as exc_info:
            extract_file_from_archive(mock_file, "nonexistent.yml")
        assert "不存在" in str(exc_info.value)

    def test_path_traversal_blocked(self):
        """路径遍历被阻止"""
        files = {"playbook.yml": "content"}
        zip_content = create_zip_file(files)
        mock_file = MockFile("test.zip", zip_content)

        with pytest.raises(ValueError) as exc_info:
            extract_file_from_archive(mock_file, "../../../etc/passwd")
        assert "非法" in str(exc_info.value)

    def test_binary_file_rejected(self):
        """二进制文件被拒绝"""
        files = {"module.pyc": b"\x00\x00\x00\x00binary"}
        zip_content = create_zip_file(files)
        mock_file = MockFile("test.zip", zip_content)

        with pytest.raises(ValueError) as exc_info:
            extract_file_from_archive(mock_file, "module.pyc")
        assert "二进制" in str(exc_info.value)

    def test_large_file_rejected(self):
        """大文件被拒绝"""
        # 创建超过 1MB 的文件
        large_content = "x" * (1024 * 1024 + 1)
        files = {"large.txt": large_content}
        zip_content = create_zip_file(files)
        mock_file = MockFile("test.zip", zip_content)

        with pytest.raises(ValueError) as exc_info:
            extract_file_from_archive(mock_file, "large.txt")
        assert "过大" in str(exc_info.value)
