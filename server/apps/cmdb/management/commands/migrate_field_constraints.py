# -- coding: utf-8 --
"""
字段约束数据迁移脚本

为现有模型字段添加默认约束配置,确保向后兼容性。

功能:
1. 为所有字段添加 user_prompt 字段(默认为空字符串)
2. 为字符串类型字段添加默认约束(无限制 + 单行)
3. 为数字类型字段添加默认约束(无最小最大值限制)
4. 为时间类型字段添加默认约束(完整日期时间 + 东八区)

使用方式:
    python manage.py migrate_field_constraints
    
    可选参数:
    --dry-run: 仅预览不实际修改
    --model-id: 仅迁移指定模型
    
示例:
    # 预览所有变更
    python manage.py migrate_field_constraints --dry-run
    
    # 仅迁移指定模型
    python manage.py migrate_field_constraints --model-id server
    
    # 执行完整迁移
    python manage.py migrate_field_constraints
"""
import json
from django.core.management.base import BaseCommand

from apps.cmdb.constants.field_constraints import (
    DEFAULT_USER_PROMPT,
    DEFAULT_STRING_CONSTRAINT,
    DEFAULT_NUMBER_CONSTRAINT,
    DEFAULT_TIME_CONSTRAINT, USER_PROMPT
)
from apps.cmdb.constants.constants import MODEL
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.services.model import ModelManage
from apps.core.logger import cmdb_logger as logger


class Command(BaseCommand):
    help = '为现有模型字段添加默认约束配置'

    def add_arguments(self, parser):
        """添加命令行参数"""
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='仅预览变更,不实际修改数据'
        )
        parser.add_argument(
            '--model-id',
            type=str,
            help='仅迁移指定模型ID的字段'
        )

    def handle(self, *args, **options):
        """执行迁移"""
        dry_run = options.get('dry_run', False)
        target_model_id = options.get('model_id')

        if dry_run:
            self.stdout.write(self.style.WARNING("=" * 60))
            self.stdout.write(self.style.WARNING("  DRY RUN 模式 - 仅预览变更,不会实际修改数据"))
            self.stdout.write(self.style.WARNING("=" * 60))
            self.stdout.write("")

        self.stdout.write(self.style.MIGRATE_HEADING("开始迁移字段约束..."))
        self.stdout.write("")

        # 统计信息
        stats = {
            "total_models": 0,
            "updated_models": 0,
            "total_fields": 0,
            "updated_fields": 0,
            "errors": 0
        }

        try:
            with GraphClient() as ag:
                # 查询所有模型
                params = []
                if target_model_id:
                    params.append({
                        "field": "model_id",
                        "type": "str=",
                        "value": target_model_id
                    })

                models, _ = ag.query_entity(MODEL, params)
                count = len(models)
                stats["total_models"] = count

                if count == 0:
                    if target_model_id:
                        self.stdout.write(
                            self.style.ERROR(f"未找到模型: {target_model_id}")
                        )
                    else:
                        self.stdout.write(
                            self.style.WARNING("未找到任何模型")
                        )
                    return

                self.stdout.write(f"找到 {count} 个模型")
                self.stdout.write("")

                # 逐个迁移模型
                for idx, model in enumerate(models, 1):
                    model_id = model.get("model_id")
                    self.stdout.write(
                        f"[{idx}/{count}] 处理模型: {model_id}"
                    )

                    try:
                        updated, field_count = self._migrate_model(
                            ag,
                            model,
                            dry_run
                        )

                        stats["total_fields"] += field_count

                        if updated:
                            stats["updated_models"] += 1
                            stats["updated_fields"] += field_count
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"  ✓ 更新了 {field_count} 个字段"
                                )
                            )
                        else:
                            self.stdout.write(
                                self.style.WARNING("  - 无需更新")
                            )

                    except Exception as e:
                        stats["errors"] += 1
                        self.stdout.write(
                            self.style.ERROR(f"  ✗ 迁移失败: {e}")
                        )
                        logger.error(
                            f"模型 {model_id} 迁移失败",
                            exc_info=True
                        )

                    self.stdout.write("")

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"迁移过程发生错误: {e}")
            )
            logger.error("字段约束迁移失败", exc_info=True)
            return

        # 输出统计信息
        self.stdout.write("=" * 60)
        self.stdout.write(self.style.MIGRATE_HEADING("迁移完成统计"))
        self.stdout.write("=" * 60)
        self.stdout.write(f"总模型数: {stats['total_models']}")
        self.stdout.write(f"更新模型数: {stats['updated_models']}")
        self.stdout.write(f"总字段数: {stats['total_fields']}")
        self.stdout.write(f"更新字段数: {stats['updated_fields']}")
        self.stdout.write(f"错误数: {stats['errors']}")
        self.stdout.write("=" * 60)

        if dry_run:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING("提示: 这是 DRY RUN 模式,未实际修改数据")
            )
            self.stdout.write(
                self.style.WARNING("执行实际迁移请移除 --dry-run 参数")
            )
        elif stats["errors"] == 0:
            self.stdout.write("")
            self.stdout.write(
                self.style.SUCCESS("✓ 迁移成功完成!")
            )
        else:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(
                    f"⚠ 迁移完成,但有 {stats['errors']} 个错误"
                )
            )

    def _migrate_model(self, ag, model: dict, dry_run: bool = False):
        """
        迁移单个模型的字段约束
        
        Args:
            ag: GraphClient 实例
            model: 模型数据
            dry_run: 是否为预览模式
        
        Returns:
            tuple: (是否有更新, 更新字段数)
        """
        attrs_json = model.get("attrs", "[]")

        # 解析属性列表
        try:
            attrs = ModelManage.parse_attrs(attrs_json)
        except Exception as e:
            raise Exception(f"解析属性列表失败: {e}")

        updated_count = 0
        updated = False

        for attr in attrs:
            attr_id = attr.get("attr_id")
            attr_type = attr.get("attr_type")
            option = attr.get("option", {})

            if not option:
                if attr_type == "enum":
                    option = []
                else:
                    option = {}
            else:
                if not isinstance(option, dict) and attr_type != "enum":
                    option = {}

            attr["option"] = option

            # 1. 添加 user_prompt 字段(所有类型)
            if USER_PROMPT not in attr:
                attr.update(DEFAULT_USER_PROMPT)
                updated = True
                self.stdout.write(
                    f"    + {attr_id}: 添加 user_prompt 字段"
                )

            # 2. 字符串类型添加默认约束
            if attr_type == "str":
                attr["option"].pop('string_constraint', None)  # 清理旧字段
                if "validation_type" not in attr["option"]:
                    attr["option"].update(DEFAULT_STRING_CONSTRAINT.copy())
                    updated = True
                    updated_count += 1
                    self.stdout.write(
                        f"    + {attr_id}: 添加字符串约束(默认:无限制+单行)"
                    )

            # 3. 数字类型添加默认约束
            elif attr_type in ["int", "float"]:
                attr["option"].pop('number_constraint', None)  # 清理旧字段
                if "min_value" not in attr["option"] and "max_value" not in attr["option"]:
                    attr["option"].update(DEFAULT_NUMBER_CONSTRAINT.copy())
                    updated = True
                    updated_count += 1
                    self.stdout.write(
                        f"    + {attr_id}: 添加数字约束(默认:无限制)"
                    )

            # 4. 时间类型添加默认约束
            elif attr_type == "time":
                attr["option"].pop('time_constraint', None)  # 清理旧字段
                if "display_format" not in attr["option"]:
                    attr["option"].update(DEFAULT_TIME_CONSTRAINT.copy())
                    updated = True
                    updated_count += 1
                    self.stdout.write(
                        f"    + {attr_id}: 添加时间约束(默认:日期时间+东八区)"
                    )

        # 如果有更新且不是 dry_run,则保存到数据库
        if updated and not dry_run:
            try:
                new_attrs_json = json.dumps(attrs, ensure_ascii=False)
                ag.set_entity_properties(
                    MODEL,
                    [model["_id"]],
                    {"attrs": new_attrs_json},
                    {},
                    [],
                    False
                )
            except Exception as e:
                raise Exception(f"更新模型失败: {e}")

        return updated, updated_count
