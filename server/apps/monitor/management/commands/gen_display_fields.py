import json
import re

from django.core.management.base import BaseCommand

from apps.monitor.constants.plugin import PluginConstants
from apps.monitor.management.utils import find_files_by_pattern

# 匹配某个对象的 supplementary_indicators 键所在行（捕获其缩进）
_SUPP_KEY_RE = re.compile(r'^(\s*)"supplementary_indicators"\s*:')


def build_display_fields_for_object(obj, plugin_name):
    """从单个对象的 supplementary_indicators 生成 display_fields 块。"""
    display_name_map = {m["name"]: m.get("display_name") or m["name"] for m in obj.get("metrics", [])}
    columns = []
    for idx, metric_name in enumerate(obj.get("supplementary_indicators", []) or []):
        if metric_name not in display_name_map:
            continue
        columns.append({
            "name": display_name_map[metric_name],
            "sort_order": idx,
            "metrics": [{"plugin": plugin_name, "metric": metric_name}],
        })
    return columns


def insert_display_fields_lines(text, blocks):
    """在每个对象的 supplementary_indicators 数组结束行之后，插入一行 display_fields。

    仅新增行、保留原文件其余格式（最小 diff）。blocks 与文件中
    supplementary_indicators 的出现顺序一一对应（基础对象 1 个，复合对象按 objects 顺序）。
    """
    lines = text.split("\n")
    result = []
    block_idx = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        result.append(line)
        match = _SUPP_KEY_RE.match(line)
        if match and block_idx < len(blocks):
            # 跳到该数组的结束行（兼容单行与多行写法）。
            # 假设：supplementary_indicators 的值均为不含 "]" 字符的简单指标名字符串，
            # 因此可用朴素的 "]" 文本扫描定位数组结束行（当前所有指标名均满足）。
            while "]" not in lines[i]:
                i += 1
                result.append(lines[i])
            block = blocks[block_idx]
            block_idx += 1
            if block:
                indent = match.group(1)
                snippet = json.dumps(block, ensure_ascii=False)
                result.append(f'{indent}"display_fields": {snippet},')
        i += 1
    return "\n".join(result)


class Command(BaseCommand):
    help = "为每个 metrics.json 的对象插入 display_fields 块（最小 diff，幂等：已存在则跳过）"

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="即使文件已含 display_fields 也处理（可能重复插入）")

    def handle(self, *args, **options):
        force = options["force"]
        files = find_files_by_pattern(PluginConstants.DIRECTORY, filename_pattern="metrics.json")
        files.extend(find_files_by_pattern(PluginConstants.ENTERPRISE_DIRECTORY, filename_pattern="metrics.json"))
        changed = 0
        for path in files:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            if '"display_fields"' in text and not force:
                continue
            data = json.loads(text)
            plugin_name = data.get("plugin", "")
            objects = data.get("objects") if data.get("is_compound_object") else [data]
            blocks = [build_display_fields_for_object(obj, plugin_name) for obj in objects]
            if not any(blocks):
                continue
            new_text = insert_display_fields_lines(text, blocks)
            if new_text != text:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(new_text)
                changed += 1
                self.stdout.write(f"updated: {path}")
        self.stdout.write(self.style.SUCCESS(f"done, {changed} files updated"))
