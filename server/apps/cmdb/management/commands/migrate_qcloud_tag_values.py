# -- coding: utf-8 --
"""把腾讯云模型实例上仍是字符串的 tag 收成 key:value 列表。

模型定义由 model_init 把 attr_type 从 str 迁到 tag + free。
本命令只改实例属性：已是 list 的不动；空串写成 []；非法项跳过并计数，不打印标签内容。

    python manage.py migrate_qcloud_tag_values --dry-run
    python manage.py migrate_qcloud_tag_values
"""

import json

from django.core.management.base import BaseCommand

from apps.cmdb.constants.constants import INSTANCE, MODEL
from apps.cmdb.constants.field_constraints import TAG_ATTR_ID
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.validators.field_validator import backfill_tag_property


class Command(BaseCommand):
    help = "将腾讯云模型上的字符串 tag 回填为 key:value 列表"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="只统计，不写图")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        updated = 0
        skipped = 0
        truncated = 0
        with GraphClient() as client:
            models, _count = client.query_entity(MODEL, [])
            model_ids = []
            for model in models:
                model_id = str(model.get("model_id") or "")
                if not model_id.startswith("qcloud"):
                    continue
                try:
                    attrs = json.loads(model.get("attrs") or "[]")
                except (TypeError, json.JSONDecodeError):
                    attrs = []
                if any(isinstance(attr, dict) and attr.get("attr_id") == TAG_ATTR_ID for attr in attrs):
                    model_ids.append(model_id)

            for model_id in model_ids:
                instances, _count = client.query_entity(INSTANCE, [{"field": "model_id", "type": "str=", "value": model_id}])
                model_updated = 0
                for inst in instances:
                    if TAG_ATTR_ID not in inst:
                        continue
                    new_value, item_skipped, item_truncated = backfill_tag_property(inst.get(TAG_ATTR_ID))
                    skipped += item_skipped
                    truncated += item_truncated
                    if new_value is None:
                        continue
                    model_updated += 1
                    updated += 1
                    if dry_run:
                        continue
                    try:
                        client.set_entity_properties(INSTANCE, [inst["_id"]], {TAG_ATTR_ID: new_value}, {}, [], False)
                    except Exception as err:
                        self.stdout.write(self.style.ERROR(f"model={model_id} inst_id={inst.get('_id')} error_type={type(err).__name__}"))
                self.stdout.write(f"model={model_id} checked={len(instances)} updated={model_updated}")
        self.stdout.write(self.style.SUCCESS(f"updated={updated} skipped_illegal={skipped} truncated={truncated} dry_run={dry_run}"))
