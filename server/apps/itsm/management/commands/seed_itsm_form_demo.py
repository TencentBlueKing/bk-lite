"""显式执行的表单演示数据，可重复运行，不覆盖已有数据。"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.itsm.models import DataDictionary, DataDictionaryItem, DataTable, DataTableField, DataTableRow
from apps.itsm.models.integration import Integration


class Command(BaseCommand):
    help = "插入 [测试] 表单字典、数据表和 Python 动作，不覆盖已有资源"

    def add_arguments(self, parser):
        parser.add_argument("--domain", required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        domain = options["domain"]
        audit = {"domain": domain, "created_by": "form_demo", "updated_by": "form_demo"}
        dictionaries = {
            "priority": ("优先级", [("p1", "紧急", None), ("p2", "高", None), ("p3", "中", None), ("p4", "低", None)]),
            "environment": (
                "部署环境",
                [("dev", "开发环境", None), ("test", "测试环境", None), ("stage", "预发布环境", None), ("prod", "生产环境", None)],
            ),
            "region": (
                "地区与机房（级联）",
                [
                    ("east", "华东", None),
                    ("sh", "上海机房", "east"),
                    ("hz", "杭州机房", "east"),
                    ("south", "华南", None),
                    ("sz", "深圳机房", "south"),
                    ("gz", "广州机房", "south"),
                    ("north", "华北", None),
                    ("bj", "北京机房", "north"),
                ],
            ),
            "category": (
                "故障分类（级联）",
                [
                    ("hardware", "硬件", None),
                    ("disk", "磁盘", "hardware"),
                    ("memory", "内存", "hardware"),
                    ("software", "软件", None),
                    ("database", "数据库", "software"),
                    ("app", "应用服务", "software"),
                ],
            ),
        }
        for key, (name, rows) in dictionaries.items():
            dictionary, _ = DataDictionary.objects.get_or_create(domain=domain, key="demo_form_" + key, defaults={"name": "[测试] " + name, **audit})
            parents = {}
            for order, (value, label, parent) in enumerate(rows):
                item, _ = DataDictionaryItem.objects.get_or_create(
                    dictionary=dictionary, key=value, defaults={"label": label, "parent": parents.get(parent), "order": order, **audit}
                )
                parents[value] = item
        definitions = [
            (
                "assets",
                "设备台账",
                [
                    ("id", "string"),
                    ("name", "string"),
                    ("department", "string"),
                    ("environment", "string"),
                    ("amount", "number"),
                    ("region", "string"),
                ],
                [
                    {
                        "id": f"host-{i:03}",
                        "name": f'{["研发", "运维", "财务"][(i - 1) % 3]}服务器 {i:02}',
                        "department": ["研发部", "运维部", "财务部"][(i - 1) % 3],
                        "environment": ["dev", "test", "prod"][(i - 1) % 3],
                        "amount": 5000 + i * 500,
                        "region": ["上海", "深圳", "北京"][(i - 1) % 3],
                    }
                    for i in range(1, 13)
                ],
            ),
            (
                "plans",
                "服务套餐",
                [("id", "string"), ("name", "string"), ("category", "string"), ("amount", "number"), ("description", "string")],
                [
                    {
                        "id": f"plan-{i}",
                        "name": name,
                        "category": "基础设施" if i <= 4 else "应用服务",
                        "amount": i * 100,
                        "description": f"{name}演示套餐，用于表单选择与价格回填",
                    }
                    for i, name in enumerate(["云主机小型", "云主机中型", "云主机大型", "对象存储", "MySQL 标准版", "Redis 标准版", "应用发布", "数据备份"], 1)
                ],
            ),
        ]
        for key, name, columns, rows in definitions:
            table, _ = DataTable.objects.get_or_create(domain=domain, key="demo_form_" + key, defaults={"name": "[测试] " + name, **audit})
            for column, kind in columns:
                DataTableField.objects.get_or_create(table=table, key=column, defaults={"field_type": kind, **audit})
            for row in rows:
                DataTableRow.objects.get_or_create(table=table, domain=domain, data=row, defaults=audit)
        scripts = {
            "按环境筛选服务": (
                "def transform(rows, params):\n"
                '    env = params.get("environment", "")\n'
                '    items = [{"id":"dev", "name":"开发服务", "amount":100}, '
                '{"id":"test", "name":"测试服务", "amount":200}, {"id":"prod", "name":"生产服务", "amount":500}]\n'
                '    return [item for item in items if not env or item["id"] == env]\n'
                ""
            ),
            "费用计算": (
                "def transform(rows, params):\n"
                '    return [{"amount": float(params.get("price", 100)) * int(params.get("quantity", 2)), "name": "计算结果"}]\n'
                ""
            ),
        }
        for name, script in scripts.items():
            Integration.objects.get_or_create(domain=domain, name="[测试] " + name, kind="python", defaults={"config": {"script": script}, **audit})
        self.stdout.write(self.style.SUCCESS("已准备 4 个字典、2 张数据表（20 行）和 2 个 Python 动作；重复执行不会覆盖已有数据。"))
