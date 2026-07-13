#!/usr/bin/env python
"""把 monitor/language/{en,zh-Hans}.yaml 中 5 段拆到 core/ 子目录。

执行:
    python scripts/split_monitor_language.py [--dry-run]

注意:此脚本假设 monitor_object_plugin 段已由 Task 4 的 migrate_plugin_language.py 删除。
"""
import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
LANG_ROOT = REPO_ROOT / "server/apps/monitor/language"
CORE_DIR = LANG_ROOT / "core"

# 待拆段:每段一个独立文件
SECTIONS = [
    "monitor_object_metric",
    "monitor_object_metric_group",
    "monitor_object",
    "monitor_object_type",
    "flow_onboarding_ui",
]


def write_yaml(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)


def main(dry_run: bool = False) -> int:
    for lang in ("en", "zh-Hans"):
        src = LANG_ROOT / f"{lang}.yaml"
        if not src.exists():
            print(f"WARN: {src} 不存在,跳过")
            continue
        data = yaml.safe_load(src.read_text(encoding="utf-8")) or {}

        for section in SECTIONS:
            if section in data:
                target = CORE_DIR / f"{section}.yaml"
                if not dry_run:
                    write_yaml(target, data[section])
                print(f"{lang}.yaml -> core/{section}.yaml ({len(data[section])} entries)")

        # 写空壳到顶层
        if not dry_run:
            shell_content = (
                "# 空壳。翻译分布在:\n"
                "#   - 跨 plugin 共享翻译(metric/group/object/type/flow/legacy)在 core/\n"
                "#   - monitor_object_plugin 翻译在 support-files/plugins/*/language/\n"
                "# 该文件被 LanguageLoader 自动跳过(空 dict 不贡献内容)。\n"
                "{}\n"
            )
            src.write_text(shell_content, encoding="utf-8")
        print(f"{lang}.yaml -> 空壳")

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    sys.exit(main(dry_run=args.dry_run))