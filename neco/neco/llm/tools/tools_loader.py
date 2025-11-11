import inspect
import copy
from loguru import logger

from neco.core.utils.template_loader import TemplateLoader

# 静态导入所有工具模块
from neco.llm.tools import date
from neco.llm.tools import github
from neco.llm.tools import jenkins
from neco.llm.tools import kubernetes
from neco.llm.tools import python
from neco.llm.tools import search
from neco.llm.tools import shell


class ToolsLoader:
    """
    工具加载器

    加载 tools 目录下所有 *_tools.py 和 *_tools_plus.py 文件中带有 @tool 装饰器的函数。
    支持根据工具文件名类型自动判断是否需要额外提示功能。

    特性:
    - 静态导入所有工具模块
    - 智能识别 @tool 装饰的函数
    - 根据文件名后缀自动设置 enable_extra_prompt:
      * _tools.py 文件: enable_extra_prompt = False
      * _tools_plus.py 文件: enable_extra_prompt = True
    """

    # 常量定义
    TOOLS_SUFFIX = "_tools"
    TOOLS_PLUS_SUFFIX = "_tools_plus"
    STRUCTURED_TOOL_CLASS = "StructuredTool"

    # 静态定义所有工具模块映射
    TOOL_MODULES = {
        'current_time': (date, False),
        'duckduckgo': (search, False),
        'github': (github, False),
        'jenkins': (jenkins, False),
        'kubernetes': (kubernetes, False),
        'python': (python, False),
        'shell': (shell, False),
    }

    @staticmethod
    def _discover_tools():
        """
        从静态导入的工具模块中提取所有带有 @tool 装饰器的函数

        Returns:
            dict: 工具映射字典，格式为 {tool_category: [tool_info_list]}
        """
        tools_map = {}

        for tool_category, (module, enable_extra_prompt) in ToolsLoader.TOOL_MODULES.items():
            tool_functions = ToolsLoader._extract_tools_from_module(
                module, enable_extra_prompt)

            if tool_functions:
                tools_map[tool_category] = tool_functions
                logger.info(
                    f"从 {tool_category} 加载了 {len(tool_functions)} 个工具")

        logger.info(f"总共发现 {len(tools_map)} 个工具类别")
        return tools_map

    @staticmethod
    def _extract_tools_from_module(module, enable_extra_prompt):
        """
        从已导入的模块中提取工具函数

        Args:
            module: 已导入的模块对象
            enable_extra_prompt: 是否启用额外提示

        Returns:
            list: 工具函数列表
        """
        tool_functions = []

        for name, obj in inspect.getmembers(module):
            if (hasattr(obj, '__class__') and
                    obj.__class__.__name__ == ToolsLoader.STRUCTURED_TOOL_CLASS):
                tool_functions.append({
                    "func": obj,
                    "enable_extra_prompt": enable_extra_prompt
                })

        return tool_functions

    @staticmethod
    def load_tools(tool_server_url: str, extra_tools_prompt: str = "", extra_param_prompt: dict = {}):
        """
        根据 tool_server_url 配置按需加载对应的工具

        Args:
            tool_server_url (str): 工具服务器URL    

        Returns:
            list: 加载的工具函数列表
        """

        # 解析工具名称
        url_parts = tool_server_url.split(":")
        if len(url_parts) < 2:
            logger.error(f"无效的工具服务器URL格式: {tool_server_url}")
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
            processed_tool = ToolsLoader._process_tool(
                tool_info, extra_tools_prompt, extra_param_prompt)
            if processed_tool:
                tools.append(processed_tool)

        return tools

    @staticmethod
    def _process_tool(tool_info, extra_tools_prompt: str, extra_param_prompt: dict):
        """处理单个工具，应用额外提示"""
        try:
            func = copy.deepcopy(tool_info['func'])
            enable_extra_prompt = tool_info['enable_extra_prompt']

            if enable_extra_prompt:
                ToolsLoader._apply_extra_prompts(
                    func, extra_tools_prompt, extra_param_prompt)

            return func

        except Exception as e:
            logger.error(f"处理工具时发生错误: {e}")
            return None

    @staticmethod
    def _apply_extra_prompts(func, extra_tools_prompt: str, extra_param_prompt: dict):
        """为工具函数应用额外提示"""
        if extra_tools_prompt:
            func.description += f"\n{extra_tools_prompt}"

        if extra_param_prompt:
            param_descriptions = [f"{key}:{value}" for key,
                                  value in extra_param_prompt.items()]

            # 使用模板加载器生成动态参数提示
            final_prompt = TemplateLoader.render_template(
                "prompts/tools/dynamic_param_generation",
                {"param_descriptions": ', '.join(param_descriptions)}
            )
            func.description += f"\n{final_prompt}"

    @staticmethod
    def _discover_specific_tool(tool_category):
        """
        按需加载特定工具类别

        Args:
            tool_category (str): 需要加载的工具类别名称

        Returns:
            list: 工具函数列表
        """
        if tool_category not in ToolsLoader.TOOL_MODULES:
            logger.warning(f"未找到工具类别 '{tool_category}'")
            return []

        module, enable_extra_prompt = ToolsLoader.TOOL_MODULES[tool_category]
        tool_functions = ToolsLoader._extract_tools_from_module(
            module, enable_extra_prompt)

        if tool_functions:
            logger.info(
                f"从 {tool_category} 加载了 {len(tool_functions)} 个工具")

        return tool_functions

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
