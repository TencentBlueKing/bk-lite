# -- coding: utf-8 --
# @File: init_field_groups.py
# @Time: 2026/1/4
# @Author: windyzhao
import json

from django.core.management.base import BaseCommand

from apps.cmdb.models.field_group import FieldGroup
from apps.cmdb.services.model import ModelManage
from apps.cmdb.constants.constants import MODEL
from apps.cmdb.graph.drivers.graph_client import GraphClient


class Command(BaseCommand):
    help = "为所有现有模型初始化字段分组（从模型属性中提取现有分组）"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="强制重新创建分组（会删除已存在的分组记录）",
        )

    def handle(self, *args, **options):
        force = options.get("force", False)

        self.stdout.write(self.style.SUCCESS("开始初始化字段分组..."))
        model_count = 0
        # 1. 获取所有模型
        with GraphClient() as ag:
            models, _ = ag.query_entity(MODEL, [])

        # 2. 为每个模型提取并创建分组
        total_created = 0
        total_skipped = 0
        total_updated = 0

        for model in models:
            model_id = model.get("model_id")
            model_name = model.get("model_name", model_id)

            self.stdout.write(f"\n处理模型: {model_id} ({model_name})")

            # 检查是否已有分组
            existing_groups = FieldGroup.objects.filter(model_id=model_id)

            if force and existing_groups.exists():
                # 强制模式：删除已有分组
                count = existing_groups.count()
                existing_groups.delete()
                self.stdout.write(
                    self.style.WARNING(f"  删除模型 {model_id} 的 {count} 个已有分组")
                )

            # 解析模型属性，提取分组信息
            attrs = ModelManage.parse_attrs(model.get("attrs", "[]"))

            if not attrs:
                self.stdout.write(self.style.WARNING(f"  模型 {model_id} 没有属性，跳过"))
                total_skipped += 1
                continue

            # 收集所有不重复的分组名称（保持顺序）
            group_names = []
            group_name_set = set()

            for attr in attrs:
                attr_group = attr.get("attr_group")
                if attr_group and attr_group not in group_name_set:
                    group_names.append(attr_group)
                    group_name_set.add(attr_group)

            # 处理没有分组的字段
            has_ungrouped = any(not attr.get("attr_group") for attr in attrs)

            if not group_names:
                # 如果没有任何分组，创建一个默认分组
                group_names = ["默认分组"]
                has_ungrouped = True

            # 创建或更新分组记录
            created_count = 0
            updated_count = 0
            try:
                # 重新查询现有分组（force模式下已删除，这里为空）
                existing_groups_dict = {
                    g.group_name: g
                    for g in FieldGroup.objects.filter(model_id=model_id)
                }
                
                for idx, group_name in enumerate(group_names, start=1):
                    # 收集该分组下的所有属性ID（按attrs中的顺序）
                    group_attr_orders = [
                        attr.get("attr_id")
                        for attr in attrs
                        if attr.get("attr_group") == group_name and attr.get("attr_id")
                    ]
                    
                    if group_name in existing_groups_dict:
                        # 更新已存在的分组
                        group = existing_groups_dict[group_name]
                        group.attr_orders = group_attr_orders
                        group.order = idx
                        group.save(update_fields=["attr_orders", "order"])
                        updated_count += 1
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"  ✓ 更新分组 '{group_name}' (order: {idx}, 包含 {len(group_attr_orders)} 个属性)"
                            )
                        )
                    else:
                        # 创建新分组
                        FieldGroup.objects.create(
                            model_id=model_id,
                            group_name=group_name,
                            order=idx,
                            is_collapsed=False,
                            description=f"从模型属性中提取的分组",
                            created_by="system",
                            attr_orders=group_attr_orders,
                        )
                        created_count += 1
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"  ✓ 创建分组 '{group_name}' (order: {idx}, 包含 {len(group_attr_orders)} 个属性)"
                            )
                        )

                total_created += created_count
                total_updated += updated_count

                # 如果有未分组的字段，将它们分配到第一个分组
                if has_ungrouped:
                    target_group = group_names[0]
                    updated = False

                    for attr in attrs:
                        if not attr.get("attr_group"):
                            attr["attr_group"] = target_group
                            updated = True

                    if updated:
                        with GraphClient() as ag:
                            ag.set_entity_properties(
                                MODEL,
                                [model["_id"]],
                                {"attrs": json.dumps(attrs)},
                                {},
                                [],
                                False,
                            )
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"  ✓ 将未分组的字段分配到 '{target_group}'"
                            )
                        )
                        
                        # 更新目标分组的attr_orders，补充未分组的字段
                        target_group_obj = FieldGroup.objects.get(
                            model_id=model_id, group_name=target_group
                        )
                        ungrouped_attr_ids = [
                            attr.get("attr_id") 
                            for attr in attrs 
                            if attr.get("attr_group") == target_group and attr.get("attr_id")
                        ]
                        target_group_obj.attr_orders = ungrouped_attr_ids
                        target_group_obj.save(update_fields=["attr_orders"])

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"  ✗ 为模型 {model_id} 创建分组失败: {str(e)}")
                )

            model_count += 1

        # 3. 输出统计信息
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("初始化完成！"))
        self.stdout.write(f"  - 处理模型数: {model_count}")
        self.stdout.write(f"  - 创建分组数: {total_created}")
        self.stdout.write(f"  - 更新分组数: {total_updated}")
        self.stdout.write(f"  - 跳过模型数: {total_skipped}")
        self.stdout.write("=" * 60)
