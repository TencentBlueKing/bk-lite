import json

from django.core.management.base import BaseCommand

from apps.monitor.constants.plugin import PluginConstants
from apps.monitor.management.utils import find_files_by_pattern
from apps.monitor.models import MonitorObject


def _load_seed_by_object():
    """扫描所有 metrics.json,返回 {对象名: display_fields 块}(后扫者覆盖,与导入序一致)。"""
    seed = {}
    files = find_files_by_pattern(PluginConstants.DIRECTORY, filename_pattern="metrics.json")
    files.extend(find_files_by_pattern(PluginConstants.ENTERPRISE_DIRECTORY, filename_pattern="metrics.json"))
    for path in files:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        objs = data.get("objects") if data.get("is_compound_object") else [data]
        for obj in objs:
            block = obj.get("display_fields")
            if block:
                seed[obj.get("name")] = block
    return seed


class Command(BaseCommand):
    help = "把所有监控对象 DB 的 display_fields 重写为 metrics.json 最新种子并清除 customized 标记"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="落库(默认 dry-run 只打印)")
        parser.add_argument("--only", nargs="*", default=None, help="仅处理指定对象名")

    def handle(self, *args, **options):
        apply = options["apply"]
        only = set(options["only"]) if options["only"] else None
        seed = _load_seed_by_object()
        changed = 0
        for obj in MonitorObject.objects.all():
            if only and obj.name not in only:
                continue
            block = seed.get(obj.name)
            if not block:
                continue
            old = [c.get("name") for c in (obj.display_fields or [])]
            new = [c.get("name") for c in block]
            if old == new and obj.display_fields_customized is False:
                continue
            self.stdout.write(f"{obj.name}: {old} -> {new}")
            changed += 1
            if apply:
                obj.display_fields = block
                obj.display_fields_customized = False
                obj.save(update_fields=["display_fields", "display_fields_customized"])
        verb = "applied" if apply else "dry-run"
        self.stdout.write(self.style.SUCCESS(f"{verb}: {changed} objects"))
