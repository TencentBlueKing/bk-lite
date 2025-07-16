import importlib
import inspect
from pathlib import Path
from libs.metis.entity.basic.tools_server import ToolsServer
import copy
import logging
logger = logging.getLogger(__name__)


class ToolsLoader:
    """
    插件化工具加载器

    自动扫描 tools 目录下所有 *_tools.py 和 *_tools_plus.py 文件，发现并加载带有 @tool 装饰器的函数。
    支持根据工具文件名类型自动判断是否需要额外提示功能。

    特性:
    - 自动发现工具文件
    - 动态导入工具模块
    - 智能识别 @tool 装饰的函数
    - 根据文件名后缀自动设置 enable_extra_prompt:
      * _tools.py 文件: enable_extra_prompt = False
      * _tools_plus.py 文件: enable_extra_prompt = True
    """

    # 常量定义
    TOOLS_SUFFIX = "_tools"
    TOOLS_PLUS_SUFFIX = "_tools_plus"
    STRUCTURED_TOOL_CLASS = "StructuredTool"

    @staticmethod
    def _discover_tools():
        """
        自动扫描 tools 目录下所有 *_tools.py 和 *_tools_plus.py 文件，发现带有 @tool 注解的函数

        文件名规则:
        - *_tools.py: enable_extra_prompt = False
        - *_tools_plus.py: enable_extra_prompt = True

        Returns:
            dict: 工具映射字典，格式为:
                {
                    'tool_category': [
                        {
                            'func': tool_function,
                            'enable_extra_prompt': boolean
                        }
                    ]
                }
        """
        tools_map = {}
        tools_dir = Path(__file__).parent

        # 扫描所有相关文件
        pattern_files = list(tools_dir.glob("*_tools*.py"))
        logger.info(f"发现 {len(pattern_files)} 个潜在工具文件")

        for tools_file in pattern_files:
            if tools_file.name == "tools_loader.py":
                continue

            # 解析文件类型和工具类别
            file_info = ToolsLoader._parse_tool_file(tools_file)
            if not file_info:
                continue

            tool_category, enable_extra_prompt = file_info

            # 导入模块并提取工具函数
            tool_functions = ToolsLoader._extract_tools_from_module(
                tools_file, enable_extra_prompt)

            if tool_functions:
                tools_map[tool_category] = tool_functions
                logger.info(
                    f"从 {tools_file.name} 加载了 {len(tool_functions)} 个工具")

        logger.info(f"总共发现 {len(tools_map)} 个工具类别")
        return tools_map

    @staticmethod
    def _parse_tool_file(tools_file):
        """解析工具文件，返回工具类别和额外提示标志"""
        stem = tools_file.stem

        if stem.endswith(ToolsLoader.TOOLS_PLUS_SUFFIX):
            tool_category = stem.replace(ToolsLoader.TOOLS_PLUS_SUFFIX, "")
            return tool_category, True
        elif stem.endswith(ToolsLoader.TOOLS_SUFFIX):
            tool_category = stem.replace(ToolsLoader.TOOLS_SUFFIX, "")
            return tool_category, False

        return None

    @staticmethod
    def _extract_tools_from_module(tools_file, enable_extra_prompt):
        """从模块中提取工具函数"""
        module_name = f"src.tools.{tools_file.stem}"

        try:
            module = importlib.import_module(module_name)
            tool_functions = []

            for name, obj in inspect.getmembers(module):
                if (hasattr(obj, '__class__') and
                        obj.__class__.__name__ == ToolsLoader.STRUCTURED_TOOL_CLASS):
                    tool_functions.append({
                        "func": obj,
                        "enable_extra_prompt": enable_extra_prompt
                    })

            return tool_functions

        except ImportError as e:
            logger.error(f"导入模块 {module_name} 失败: {e}")
            return []

    @staticmethod
    def load_tools(tool_server: ToolsServer):
        """
        根据 tool_server 配置按需加载对应的工具

        Args:
            tool_server (ToolsServer): 工具服务器配置对象

        Returns:
            list: 加载的工具函数列表
        """
        if not hasattr(tool_server, 'url') or not tool_server.url:
            logger.error("tool_server.url 为空或不存在")
            return []

        # 解析工具名称
        url_parts = tool_server.url.split(":")
        if len(url_parts) < 2:
            logger.error(f"无效的工具服务器URL格式: {tool_server.url}")
            return []

        tools_name = url_parts[1]
        logger.info(f"按需加载工具类别: {tools_name}")

        # 按需加载特定工具类别
        tool_functions = ToolsLoader._discover_specific_tool(tools_name)

        if not tool_functions:
            logger.warning(f"未找到工具类别 '{tools_name}' 或加载失败")
            return []

        tools = []
        for tool_info in tool_functions:
            processed_tool = ToolsLoader._process_tool(tool_info, tool_server)
            if processed_tool:
                tools.append(processed_tool)

        logger.info(f"成功加载 {len(tools)} 个 '{tools_name}' 类别的工具")
        return tools

    @staticmethod
    def _process_tool(tool_info, tool_server):
        """处理单个工具，应用额外提示"""
        try:
            func = copy.deepcopy(tool_info['func'])
            enable_extra_prompt = tool_info['enable_extra_prompt']

            if enable_extra_prompt:
                ToolsLoader._apply_extra_prompts(func, tool_server)

            return func

        except Exception as e:
            logger.error(f"处理工具时发生错误: {e}")
            return None

    @staticmethod
    def _apply_extra_prompts(func, tool_server):
        """为工具函数应用额外提示"""
        if hasattr(tool_server, 'extra_tools_prompt') and tool_server.extra_tools_prompt:
            func.description += f"\n{tool_server.extra_tools_prompt}"

        if hasattr(tool_server, 'extra_param_prompt') and tool_server.extra_param_prompt:
            param_descriptions = [f"{key}:{value}" for key,
                                  value in tool_server.extra_param_prompt.items()]
            final_prompt = f"""以下是函数的动态参数生成要求，param json 参数说明:\n{', '.join(param_descriptions)}
                    请根据以上要求生成函数的动态参数, param为json字典字符串
                """
            func.description += final_prompt

    @staticmethod
    def _discover_specific_tool(tool_category):
        """
        按需加载特定工具类别，避免扫描所有工具文件

        Args:
            tool_category (str): 需要加载的工具类别名称

        Returns:
            list: 工具函数列表，格式为:
                [
                    {
                        'func': tool_function,
                        'enable_extra_prompt': boolean
                    }
                ]
        """
        tools_dir = Path(__file__).parent

        # 尝试查找对应的工具文件
        possible_files = [
            tools_dir / f"{tool_category}{ToolsLoader.TOOLS_PLUS_SUFFIX}.py",
            tools_dir / f"{tool_category}{ToolsLoader.TOOLS_SUFFIX}.py"
        ]

        for tools_file in possible_files:
            if tools_file.exists():
                logger.info(f"找到工具文件: {tools_file.name}")

                # 解析文件类型
                file_info = ToolsLoader._parse_tool_file(tools_file)
                if not file_info:
                    continue

                _, enable_extra_prompt = file_info

                # 导入模块并提取工具函数
                tool_functions = ToolsLoader._extract_tools_from_module(
                    tools_file, enable_extra_prompt)

                if tool_functions:
                    logger.info(
                        f"从 {tools_file.name} 加载了 {len(tool_functions)} 个工具")
                    return tool_functions

        logger.warning(f"未找到工具类别 '{tool_category}' 对应的文件")
        return []

    @staticmethod
    def load_all_tools():
        """
        加载所有可用的工具类别 (保留原有功能作为备用)

        Returns:
            dict: 工具映射字典，格式为:
                {
                    'tool_category': [
                        {
                            'func': tool_function,
                            'enable_extra_prompt': boolean
                        }
                    ]
                }
        """
        logger.info("开始加载所有工具类别")
        return ToolsLoader._discover_tools()
