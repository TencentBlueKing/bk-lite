"""cmdb.utils.config_file_path 纯单元测试。

规格：校验 Linux/Windows 文件绝对路径，拒绝空串/通配符/目录路径；提取文件名跨平台。
配置文件采集相关，路径校验是安全边界。
"""

import pytest

from apps.cmdb.utils.config_file_path import extract_file_name, validate_absolute_path

pytestmark = pytest.mark.unit


class TestValidateAbsolutePath:
    @pytest.mark.parametrize("path", [
        "/etc/app/config.yaml",
        "/var/log/x.log",
        r"C:\Program Files\app\config.ini",
        r"D:\data\f.txt",
    ])
    def test_合法绝对文件路径(self, path):
        assert validate_absolute_path(path) is True

    @pytest.mark.parametrize("path", [
        "",                       # 空
        "   ",                    # 空白
        "relative/path.conf",     # 相对路径
        "/etc/app/",              # 目录(末尾 /)
        "C:\\dir\\",              # 目录(末尾 \)
        "/etc/*.conf",            # 通配符
        "/etc/conf?",             # 通配符
        "/",                      # 根
        "config.yaml",            # 无路径
    ])
    def test_非法路径(self, path):
        assert validate_absolute_path(path) is False

    def test_非字符串(self):
        assert validate_absolute_path(None) is False
        assert validate_absolute_path(123) is False


class TestExtractFileName:
    def test_linux(self):
        assert extract_file_name("/etc/app/config.yaml") == "config.yaml"

    def test_windows(self):
        assert extract_file_name(r"C:\Program Files\app\config.ini") == "config.ini"

    def test_空返回空串(self):
        assert extract_file_name("") == ""
        assert extract_file_name(None) == ""
