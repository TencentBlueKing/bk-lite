"""
从代码动态发现工具并同步到数据库的 Django management command

使用 ToolsLoader.get_all_tools_metadata() 动态获取工具元数据，并写入 SkillTools 表
"""

from django.core.management import BaseCommand

from apps.opspilot.metis.llm.tools.tools_loader import ToolsLoader
from apps.opspilot.models import SkillTools


class Command(BaseCommand):
    help = "从代码动态发现工具并同步到数据库"

    def handle(self, *args, **options):
        """执行命令"""
        try:
            self.stdout.write("正在动态发现工具...")
            # 从代码中获取所有工具元数据
            tools_metadata = ToolsLoader.get_all_tools_metadata()

            # 转换为目标格式
            result = self.convert_to_target_format(tools_metadata)

            # 写入数据库
            self.save_to_database(result)

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"同步失败: {e}"))
            import traceback

            traceback.print_exc()

    @staticmethod
    def convert_to_target_format(tools_metadata: list) -> list:
        """
        将工具元数据转换为目标 JSON 格式

        Args:
            tools_metadata (list): ToolsLoader.get_all_tools_metadata() 返回的元数据列表

        Returns:
            list: 转换后的列表格式
        """
        result = []

        for toolkit in tools_metadata:
            toolkit_id = toolkit.get("name", "")
            toolkit_name = toolkit.get("name", "")
            toolkit_description = toolkit.get("description", "")
            toolkit_tools = toolkit.get("tools", [])
            constructor_parameters = toolkit.get("constructor_parameters", [])
            constructor = toolkit.get("constructor", "")  # 获取 constructor 路径

            # 只使用构造参数，不包含工具函数的参数
            all_params = {}

            for constructor_param in constructor_parameters:
                param_name = constructor_param.get("name", "")
                if param_name:
                    if "pwd" in param_name or "password" in param_name:
                        param_type = "password"
                    else:
                        param_type = constructor_param.get("type", "string")
                    all_params[param_name] = {
                        "type": param_type,
                        "required": constructor_param.get("required", False),
                        "description": constructor_param.get("description", ""),
                    }

            toolkit_info = {
                "id": toolkit_id,
                "name": toolkit_name,
                "description": toolkit_description,
                "constructor": constructor,  # 保留 constructor
                "tools": toolkit_tools,
                "params": all_params,  # 只包含构造参数
                "constructor_parameters": constructor_parameters,  # 保留构造参数信息
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
            # constructor = toolkit.get("constructor", "")

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
                    "password": "password",
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
                "url": f"langchain:{toolkit_id}",  # 内置协议格式
                "name": toolkit_name,
                "kwargs": kwargs,
            }

            # 构造 tools 列表（只保留工具名称）

            # 检查是否已存在
            skill_tool, created = SkillTools.objects.update_or_create(
                name=toolkit_id,
                is_build_in=True,
                defaults={
                    "description": toolkit_description,
                    "params": params_data,
                    "tools": tools,
                    "tags": ["other"],
                },
            )
            if not skill_tool.team:
                skill_tool.team = [1]
                skill_tool.save()

            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"✓ 创建工具集: {toolkit_name} ({toolkit_id})"))
            else:
                updated_count += 1
                self.stdout.write(self.style.WARNING(f"↻ 更新工具集: {toolkit_name} ({toolkit_id})"))

        # 显示统计信息
        self.stdout.write(self.style.SUCCESS(f"\n完成！创建 {created_count} 个，更新 {updated_count} 个工具集"))
