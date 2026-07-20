"""check_plugin_languages 命令。

复用 find_files_by_pattern 扫所有 metrics.json,校验每个 plugin 的
language/{en,zh-Hans}.yaml 存在,且文件内顶层 key == metrics.json 的 plugin 字段。
任一校验失败返回非 0 退出码。

用法:
    cd server && uv run python manage.py check_plugin_languages [--strict]
"""

import json
from pathlib import Path

import yaml
from django.core.management.base import BaseCommand, CommandError

from apps.monitor.constants.plugin import PluginConstants
from apps.monitor.management.utils import find_files_by_pattern


class Command(BaseCommand):
    help = "校验每个 plugin 的 language/{en,zh-Hans}.yaml 存在且 key 正确"

    LANGUAGES = ("en", "zh-Hans")

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help="严格要求文件内 key == metrics.json plugin 字段(默认仅警告)",
        )

    def handle(self, *args, **options):
        strict = options["strict"]
        errors: list[str] = []
        warnings: list[str] = []
        checked = 0

        for root in (PluginConstants.DIRECTORY, PluginConstants.ENTERPRISE_DIRECTORY):
            if not Path(root).is_dir():
                continue
            for metrics_path in find_files_by_pattern(root, filename_pattern="metrics.json"):
                try:
                    data = json.loads(Path(metrics_path).read_text(encoding="utf-8"))
                except Exception as e:
                    errors.append(f"无法解析 {metrics_path}: {e}")
                    continue
                plugin_name = data.get("plugin")
                if not plugin_name:
                    warnings.append(f"{metrics_path}: 缺 plugin 字段,跳过")
                    continue

                plugin_dir = Path(metrics_path).parent
                for lang in self.LANGUAGES:
                    lang_file = plugin_dir / "language" / f"{lang}.yaml"
                    checked += 1
                    if not lang_file.is_file():
                        errors.append(f"缺失: {lang_file}")
                        continue
                    try:
                        content = yaml.safe_load(lang_file.read_text(encoding="utf-8")) or {}
                    except Exception as e:
                        errors.append(f"无法解析 {lang_file}: {e}")
                        continue
                    if plugin_name not in content:
                        msg = f"{lang_file}: 顶层 key {list(content.keys())} 不含 {plugin_name!r}"
                        if strict:
                            errors.append(msg)
                        else:
                            warnings.append(msg)
                    elif not content[plugin_name].get("name"):
                        warnings.append(f"{lang_file}: {plugin_name}.name 为空")

        self.stdout.write(f"checked {checked} plugin-language files")
        for w in warnings:
            self.stdout.write(self.style.WARNING(f"  WARN: {w}"))
        for e in errors:
            self.stdout.write(self.style.ERROR(f"  ERR: {e}"))

        if errors:
            raise CommandError(f"{len(errors)} errors, {len(warnings)} warnings")
        self.stdout.write(self.style.SUCCESS(f"OK: {len(warnings)} warnings"))
