
from django.core.management.base import BaseCommand
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.constants.constants import MODEL, INSTANCE
import json

class Command(BaseCommand):
    # cmdb_migrate_scalar_to_list
    help = "自动发现所有模型的list类型字段，并将CMDB实例节点的标量字段批量迁移为list，修复Cypher类型不一致问题"

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='仅预演，不实际写入数据库')
        parser.add_argument('--model', type=str, help='仅处理指定模型ID（可选）')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        only_model = options.get('model')
        self.stdout.write(self.style.NOTICE(f"开始迁移，dry_run={dry_run}, 仅处理模型: {only_model or '全部'}"))

        with GraphClient() as client:
            # 1. 查询所有模型
            models, _ = client.query_entity(MODEL, [])
            if only_model:
                models = [m for m in models if m.get('model_id') == only_model]
                if not models:
                    self.stdout.write(self.style.ERROR(f"未找到模型: {only_model}"))
                    return

            # 2. 遍历模型，收集所有list类型字段（attr_type为organization/user/enum或自定义list类型）
            model_list_fields = {}  # model_id -> set(fields)
            for model in models:
                model_id = model.get('model_id')
                attrs_json = model.get('attrs', '[]')
                try:
                    attrs = json.loads(attrs_json)
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"模型 {model_id} attrs 解析失败: {e}"))
                    continue
                list_fields = set()
                for attr in attrs:
                    attr_id = attr.get('attr_id')
                    attr_type = attr.get('attr_type')
                    # 只要是 organization/user/enum 或 attr_type 里带 list/array 的都视为list类型
                    if attr_type in ('organization', 'user', 'enum') or (attr_type and ('list' in attr_type or 'array' in attr_type)):
                        list_fields.add(attr_id)
                if list_fields:
                    model_list_fields[model_id] = list_fields

            if not model_list_fields:
                self.stdout.write(self.style.WARNING("未发现任何模型的list类型字段，无需迁移。"))
                return

            # 3. 遍历每个模型的实例，批量修正list类型字段
            total_instances = 0
            migrated_instances = 0
            for model_id, fields in model_list_fields.items():
                self.stdout.write(self.style.NOTICE(f"\n处理模型 {model_id}，需检查的list类型字段: {sorted(fields)}"))
                # 查询该模型下所有实例
                instances, _ = client.query_entity(INSTANCE, [{"field": "model_id", "type": "str=", "value": model_id}])
                self.stdout.write(f"  查询到 {len(instances)} 个实例")
                
                for inst in instances:
                    total_instances += 1
                    node_id = inst.get('_id')
                    inst_name = inst.get('inst_name', 'N/A')
                    update_fields = {}
                    
                    # 检查每个list类型字段
                    for field in fields:
                        if field not in inst:
                            # 字段不存在于实例中，跳过
                            continue
                        
                        field_value = inst[field]
                        
                        if field_value is None:
                            # 字段值为 None，跳过
                            continue
                        
                        if isinstance(field_value, list):
                            # 字段值已经是 list 类型，格式正确，跳过
                            continue
                        
                        # 字段值是标量（非list），需要转换为 [value]
                        update_fields[field] = [field_value]
                    
                    if update_fields:
                        migrated_instances += 1
                        self.stdout.write(f"  实例 {node_id} ({inst_name}) 需迁移字段: {update_fields}")
                        if not dry_run:
                            try:
                                client.set_entity_properties(INSTANCE, [node_id], update_fields, {}, [], False)
                                self.stdout.write(self.style.SUCCESS(f"    ✓ 已更新"))
                            except Exception as e:
                                self.stdout.write(self.style.ERROR(f"    ✗ 更新失败: {e}"))
            
            self.stdout.write(self.style.SUCCESS(f"\n迁移完成！共检查 {total_instances} 个实例，需迁移 {migrated_instances} 个实例"))
            if dry_run:
                self.stdout.write(self.style.WARNING("本次为 dry-run，未实际写入数据库。"))
