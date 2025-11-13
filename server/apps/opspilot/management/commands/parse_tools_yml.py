"""
解析 tools.yml 文件的 Django management command

将 tools.yml 解析为指定的 JSON 格式，并写入 SkillTools 表
"""

from pathlib import Path

import yaml
from django.core.management import BaseCommand

from apps.opspilot.models import SkillTools


class Command(BaseCommand):
    help = "解析 tools.yml 文件为 JSON 格式"

    def handle(self, *args, **options):
        """执行命令"""
        # 固定路径
        yaml_path = Path("apps/opspilot/management/tools/tools.yml")

        # 检查文件是否存在
        if not yaml_path.exists():
            self.stdout.write(self.style.ERROR(f"文件不存在: {yaml_path}"))
            return

        try:
            self.stdout.write(f"正在解析文件: {yaml_path}")
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            # 转换为目标格式
            result = self.convert_to_target_format(data)

            # 写入数据库
            self.save_to_database(result)

        except yaml.YAMLError as e:
            self.stdout.write(self.style.ERROR(f"YAML 解析失败: {e}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"解析失败: {e}"))
            import traceback

            traceback.print_exc()

    @staticmethod
    def convert_to_target_format(data: dict) -> list:
        """
        将 YAML 数据转换为目标 JSON 格式

        Args:
            data (dict): YAML 解析后的数据

        Returns:
            list: 转换后的列表格式
        """
        result = []

        toolkits = data.get("toolkits", [])

        for toolkit in toolkits:
            toolkit_id = toolkit.get("id", "")
            toolkit_name = toolkit.get("name", "")
            toolkit_description = toolkit.get("description", "")
            toolkit_tools = toolkit.get("tools", [])

            # 收集该工具集所有工具的参数
            all_params = {}
            tool_list = []

            for tool in toolkit_tools:
                tool_name = tool.get("name", "")
                tool_description = tool.get("description", "")
                parameters = tool.get("parameters", {})

                # 添加工具基本信息
                tool_list.append(
                    {
                        "name": tool_name,
                        "description": tool_description,
                    }
                )

                # 合并参数（去重）
                for param_name, param_config in parameters.items():
                    if param_name not in all_params:
                        all_params[param_name] = param_config

            toolkit_info = {
                "id": toolkit_id,
                "name": toolkit_name,
                "description": toolkit_description,
                "tools": tool_list,
                "params": all_params,  # 所有参数合并到外层
            }

            result.append(toolkit_info)

        return result

    def save_to_database(self, toolkits: list):
        """
        将工具集数据保存到 SkillTools 表

        Args:
            toolkits (list): 工具集列表
        """
        created_count = 0
        updated_count = 0

        for toolkit in toolkits:
            toolkit_id = toolkit.get("id", "")
            toolkit_name = toolkit.get("name", "")
            toolkit_description = toolkit.get("description", "")
            tools = toolkit.get("tools", [])
            params = toolkit.get("params", {})

            # 转换 params 为目标格式
            kwargs = []
            for param_name, param_config in params.items():
                param_type = param_config.get("type", "string")
                is_required = param_config.get("required", False)
                param_description = param_config.get("description", "")

                # 类型映射
                type_mapping = {
                    "string": "text",
                    "integer": "number",
                    "boolean": "checkbox",
                    "array": "text",
                    "object": "text",
                }
                mapped_type = type_mapping.get(param_type, "text")

                kwargs.append(
                    {
                        "key": param_name,
                        "type": mapped_type,
                        "value": "",
                        "isRequired": is_required,
                        "description": param_description,
                    }
                )

            # 构造 params 字段
            params_data = {
                "name": toolkit_name,
                "kwargs": kwargs,
            }

            # 构造 tools 列表（只保留工具名称）
            tools_list = [tool["name"] for tool in tools]

            # 检查是否已存在
            skill_tool, created = SkillTools.objects.update_or_create(
                name=toolkit_id,
                defaults={
                    "description": toolkit_description,
                    "params": params_data,
                    "tools": tools_list,
                    "tags": [toolkit_id],
                    "is_build_in": True,
                    "team": [],
                },
            )

            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"✓ 创建工具集: {toolkit_name} ({toolkit_id})"))
            else:
                updated_count += 1
                self.stdout.write(self.style.WARNING(f"↻ 更新工具集: {toolkit_name} ({toolkit_id})"))

        # 显示统计信息
        self.stdout.write(self.style.SUCCESS(f"\n完成！创建 {created_count} 个，更新 {updated_count} 个工具集"))
