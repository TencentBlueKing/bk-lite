"""check_plugin_languages 命令测试。

覆盖:
- 正常场景:所有 plugin 有 language 文件,命令返回 0
- 文件缺失:某 plugin 缺 en.yaml,命令抛 CommandError
- key 不一致:language/yaml 顶层 key != metrics.json plugin 字段,strict 模式报错
"""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

pytestmark = pytest.mark.unit


REPO = "/Users/fanzhongming/workspace/Weops/lite/bk-lite"
PLUGIN_DIR_LITERAL = (
    f"{REPO}/server/apps/monitor/support-files/plugins/Oracle-Exporter/exporter/oracle"
)


class TestCheckPluginLanguages:
    def test_正常情况通过(self):
        """所有 plugin 都有 language 文件,命令返回 0。"""
        try:
            call_command("check_plugin_languages")
        except CommandError as e:
            pytest.fail(f"check_plugin_languages 失败: {e}")

    def test_文件缺失报错(self):
        """临时移除某 plugin 的 en.yaml,命令应抛 CommandError。"""
        from pathlib import Path
        target = Path(PLUGIN_DIR_LITERAL) / "language" / "en.yaml"
        backup = Path(PLUGIN_DIR_LITERAL) / "language" / "en.yaml.bak"
        if not target.exists():
            pytest.skip("目标文件不存在,跳过")
        try:
            target.rename(backup)
            with pytest.raises(CommandError, match=r"1 errors|缺失"):
                call_command("check_plugin_languages")
        finally:
            backup.rename(target)

    def test_strict_key不一致报错(self):
        """修改某 plugin 的 language/en.yaml 顶层 key,strict 模式报错。"""
        from pathlib import Path
        target = Path(PLUGIN_DIR_LITERAL) / "language" / "en.yaml"
        backup = Path(PLUGIN_DIR_LITERAL) / "language" / "en.yaml.bak"
        if not target.exists():
            pytest.skip("目标文件不存在,跳过")
        try:
            target.rename(backup)
            target.write_text("WrongKey:\n  name: x\n  desc: y\n", encoding="utf-8")
            with pytest.raises(CommandError):
                call_command("check_plugin_languages", strict=True)
            # 非 strict 不报错
            try:
                call_command("check_plugin_languages")
            except CommandError as e:
                pytest.fail(f"非 strict 不应报错: {e}")
        finally:
            backup.rename(target)
