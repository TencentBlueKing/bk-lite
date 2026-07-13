#!/usr/bin/env python
"""一次性迁移脚本:把 monitor/language/{en,zh-Hans}.yaml 中的 monitor_object_plugin 段
拆到各 plugin 目录的 language/{en,zh-Hans}.yaml,顺手修 L4 bug。

执行:
    cd /Users/fanzhongming/workspace/Weops/lite/bk-lite
    python scripts/migrate_plugin_language.py [--dry-run]

执行后:
- 289 个 plugin 目录各有 language/{en,zh-Hans}.yaml 空骨架(可能含翻译)
- monitor/language/core/_legacy.yaml 含 25 条历史翻译
- monitor/language/{en,zh-Hans}.yaml 的 monitor_object_plugin 段已删
- 顶层 en.yaml/zh-Hans.yaml 改空壳(仅注释)

回滚:git revert <merge-commit> 即可还原所有改动。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS_ROOT = REPO_ROOT / "server/apps/monitor/support-files/plugins"
LANG_ROOT = REPO_ROOT / "server/apps/monitor/language"
CORE_DIR = LANG_ROOT / "core"

# 5 个 B 组 plugin:yaml 现有 display_name key → plugin.name(内部 ID) + 中文 fallback
B_GROUP_TRANSLATIONS = {
    "Etcd": {
        "internal_id": "Etcd",
        "yaml_key": None,  # yaml 无,新增
        "zh_name": "Etcd 分布式 KV 存储",
        "zh_desc": "Etcd 分布式键值存储指标采集",
    },
    "InfluxDB": {
        "internal_id": "InfluxDB",
        "yaml_key": None,
        "zh_name": "InfluxDB 时序数据库",
        "zh_desc": "InfluxDB 时序数据库指标采集",
    },
    "Kafka-Exporter": {
        "internal_id": "Kafka-Exporter",
        "yaml_key": "Kafka",  # yaml 中 "Kafka" 已有翻译
    },
    "Oracle-Exporter": {
        "internal_id": "Oracle-Exporter",
        "yaml_key": "Oracle",
    },
    "Windows WMI": {
        "internal_id": "Windows WMI",
        "yaml_key": "Host",  # fs display_name 是 Host
    },
}


def collect_fs_plugins() -> dict[str, Path]:
    """返回 {plugin_name: metrics.json 路径}。"""
    result = {}
    for m in PLUGINS_ROOT.rglob("metrics.json"):
        try:
            data = json.loads(m.read_text(encoding="utf-8"))
        except Exception:
            continue
        pn = data.get("plugin")
        if pn and pn not in result:
            result[pn] = m
    return result


def collect_yaml_plugin_translations() -> dict[str, dict[str, dict[str, str]]]:
    """返回 {lang: {plugin_key: {name, desc}}}。"""
    out = {}
    for lang in ("en", "zh-Hans"):
        path = LANG_ROOT / f"{lang}.yaml"
        if not path.exists():
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        seg = data.get("monitor_object_plugin") or {}
        out[lang] = seg
    return out


def write_yaml(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)


def empty_skeleton(plugin_name: str) -> dict:
    """生成 plugin 翻译空骨架。"""
    return {plugin_name: {"name": "", "desc": ""}}


def main(dry_run: bool = False) -> int:
    fs_plugins = collect_fs_plugins()
    yaml_translations = collect_yaml_plugin_translations()

    # 分类 yaml plugin key
    yaml_keys_by_lang = {lang: set(trans.keys()) for lang, trans in yaml_translations.items()}
    fs_names = set(fs_plugins.keys())

    # A 组: yaml 有 fs 无
    A_keys = sorted(yaml_keys_by_lang["en"] - fs_names)
    # B 组 plugin 名
    B_plugin_names = set(B_GROUP_TRANSLATIONS.keys())
    # 双组: yaml 有 fs 有(284)
    both_keys = sorted(yaml_keys_by_lang["en"] & fs_names)

    print(f"plugin 总数 fs={len(fs_plugins)} yaml={len(yaml_keys_by_lang['en'])} "
          f"A={len(A_keys)} B={len(B_plugin_names)} 双组={len(both_keys)}")

    stats = {"skeleton_created": 0, "translated": 0, "legacy": 0, "B_new": 0}

    # 1) 为所有 fs plugin 生成空骨架(或带翻译)
    for plugin_name, metrics_path in fs_plugins.items():
        plugin_dir = metrics_path.parent
        for lang in ("en", "zh-Hans"):
            lang_file = plugin_dir / "language" / f"{lang}.yaml"

            # 决定内容
            if plugin_name in B_plugin_names:
                info = B_GROUP_TRANSLATIONS[plugin_name]
                if info["yaml_key"] and info["yaml_key"] in yaml_translations.get(lang, {}):
                    # 复用 yaml 现有翻译
                    content = {plugin_name: yaml_translations[lang][info["yaml_key"]]}
                else:
                    # 新增翻译
                    if lang == "en":
                        content = {plugin_name: {"name": plugin_name, "desc": plugin_name}}
                    else:
                        content = {
                            plugin_name: {"name": info["zh_name"], "desc": info["zh_desc"]}
                        }
                    stats["B_new"] += 1
            elif plugin_name in yaml_translations.get(lang, {}):
                # 双组: 直接迁移
                content = {plugin_name: yaml_translations[lang][plugin_name]}
                stats["translated"] += 1
            else:
                # 空骨架
                content = empty_skeleton(plugin_name)
                stats["skeleton_created"] += 1

            if not dry_run:
                write_yaml(lang_file, content)

    # 2) A 组迁到 _legacy.yaml
    if not dry_run:
        CORE_DIR.mkdir(parents=True, exist_ok=True)
    legacy_data_en = {}
    legacy_data_zh = {}
    for lang in ("en", "zh-Hans"):
        seg = yaml_translations.get(lang, {})
        for k in A_keys:
            if k in seg:
                if lang == "en":
                    legacy_data_en[k] = seg[k]
                else:
                    legacy_data_zh[k] = seg[k]
        stats["legacy"] += len(A_keys)

    if not dry_run:
        write_yaml(CORE_DIR / "_legacy.yaml", {"_legacy": True, "monitor_object_plugin": legacy_data_en})
        write_yaml(
            CORE_DIR / "_legacy_zh-Hans.yaml",
            {"_legacy": True, "monitor_object_plugin": legacy_data_zh},
        )

    # 3) 删除原 monitor_object_plugin 段
    if not dry_run:
        for lang in ("en", "zh-Hans"):
            path = LANG_ROOT / f"{lang}.yaml"
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if "monitor_object_plugin" in data:
                del data["monitor_object_plugin"]
            with path.open("w", encoding="utf-8") as f:
                yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    print(f"stats: {stats}")
    if dry_run:
        print("DRY RUN: no files written")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="只打印统计,不写文件")
    args = parser.parse_args()
    sys.exit(main(dry_run=args.dry_run))
