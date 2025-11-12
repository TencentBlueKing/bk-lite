"""
工具导出CLI

将 ToolsLoader 加载的所有工具导出为 YAML 格式，供其他系统导入使用。

使用方法:
    # 导出完整工具信息
    uv run python -m neco.cli.tools_cli export --output=neco_tools.yml
    
    # 导出工具集概览
    uv run python -m neco.cli.tools_cli summary --output=neco_tools_summary.yml
    
    # 输出到标准输出
    uv run python -m neco.cli.tools_cli export --stdout
"""

import fire
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional
from loguru import logger

from neco.llm.tools.tools_loader import ToolsLoader


class ToolsCLI:
    """工具导出CLI"""

    # 工具类别中文映射
    TOOLKIT_NAMES = {
        'current_time': '时间工具',
        'duckduckgo': '搜索工具',
        'github': 'GitHub工具',
        'jenkins': 'Jenkins工具',
        'kubernetes': 'Kubernetes工具',
        'python': 'Python工具',
    }

    @staticmethod
    def _extract_tool_info(tool_obj) -> Dict[str, Any]:
        """
        从工具对象中提取信息

        Args:
            tool_obj: LangChain StructuredTool 对象

        Returns:
            包含工具信息的字典
        """
        tool_info = {
            'name': tool_obj.name,
            'description': tool_obj.description or '',
            'parameters': {}
        }

        # 提取参数信息
        if hasattr(tool_obj, 'args_schema') and tool_obj.args_schema:
            schema = tool_obj.args_schema.schema()
            properties = schema.get('properties', {})
            required = schema.get('required', [])

            for param_name, param_info in properties.items():
                tool_info['parameters'][param_name] = {
                    'type': param_info.get('type', 'string'),
                    'description': param_info.get('description', ''),
                    'required': param_name in required
                }

        return tool_info

    def export(self, output: str = 'neco_tools.yml', stdout: bool = False) -> Optional[str]:
        """
        导出所有工具为 YAML 格式

        Args:
            output: 输出文件路径 (默认: neco_tools.yml)
            stdout: 是否输出到标准输出而不是文件

        Returns:
            YAML 格式的字符串（当 stdout=True 时）
        """
        logger.info("开始导出工具信息")

        # 加载所有工具
        all_tools = ToolsLoader.load_all_tools()

        # 构建导出数据结构
        export_data = {
            'version': '1.0',
            'description': 'Neco工具集合',
            'toolkits': []
        }

        # 遍历所有工具类别
        for tool_category, tool_list in all_tools.items():
            toolkit_name = self.TOOLKIT_NAMES.get(
                tool_category, tool_category)

            toolkit = {
                'id': tool_category,
                'name': toolkit_name,
                'description': f'{toolkit_name}集合',
                'tools': []
            }

            # 提取每个工具的信息
            for tool_info in tool_list:
                tool_obj = tool_info['func']
                extracted_info = self._extract_tool_info(tool_obj)
                toolkit['tools'].append(extracted_info)

            export_data['toolkits'].append(toolkit)

            logger.info(
                f"导出工具类别: {toolkit_name} ({len(toolkit['tools'])} 个工具)")

        # 转换为 YAML
        yaml_content = yaml.dump(
            export_data,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            indent=2
        )

        # 保存到文件或输出
        if stdout:
            print(yaml_content)
        else:
            output_file = Path(output)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(yaml_content, encoding='utf-8')
            logger.info(f"工具信息已导出到: {output}")

        logger.info(f"导出完成，共 {len(export_data['toolkits'])} 个工具集")

        return yaml_content if stdout else None

    def summary(self, output: str = 'neco_tools_summary.yml', stdout: bool = False) -> Optional[str]:
        """
        导出工具集概览（简化版本）

        Args:
            output: 输出文件路径 (默认: neco_tools_summary.yml)
            stdout: 是否输出到标准输出而不是文件

        Returns:
            YAML 格式的字符串（当 stdout=True 时）
        """
        logger.info("开始导出工具集概览")

        all_tools = ToolsLoader.load_all_tools()

        summary_data = {
            'version': '1.0',
            'toolkits': []
        }

        for tool_category, tool_list in all_tools.items():
            toolkit_name = self.TOOLKIT_NAMES.get(
                tool_category, tool_category)

            toolkit = {
                'id': tool_category,
                'name': toolkit_name,
                'tool_count': len(tool_list),
                'tool_names': [tool_info['func'].name for tool_info in tool_list]
            }

            summary_data['toolkits'].append(toolkit)

        yaml_content = yaml.dump(
            summary_data,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            indent=2
        )

        if stdout:
            print(yaml_content)
        else:
            output_file = Path(output)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(yaml_content, encoding='utf-8')
            logger.info(f"工具集概览已导出到: {output}")

        return yaml_content if stdout else None


def main():
    """主函数"""
    fire.Fire(ToolsCLI)


if __name__ == '__main__':
    main()
