import copy
import inspect

from loguru import logger

# 静态导入所有工具模块
from apps.opspilot.metis.llm.tools import browser_use, date, fetch, github, jenkins, kubernetes, postgres, python, search, shell, ssh
from apps.opspilot.metis.utils.template_loader import TemplateLoader


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
        "browser_use": (browser_use, False),
        "current_time": (date, False),
        "duckduckgo": (search, False),
        "fetch": (fetch, False),
        "github": (github, False),
        "jenkins": (jenkins, False),
        "kubernetes": (kubernetes, False),
        "postgres": (postgres, False),
        "python": (python, False),
        "shell": (shell, False),
        "ssh": (ssh, False),
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
            tool_functions = ToolsLoader._extract_tools_from_module(module, enable_extra_prompt)

            if tool_functions:
                tools_map[tool_category] = tool_functions
                logger.info(f"从 {tool_category} 加载了 {len(tool_functions)} 个工具")

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
            if hasattr(obj, "__class__") and obj.__class__.__name__ == ToolsLoader.STRUCTURED_TOOL_CLASS:
                tool_functions.append({"func": obj, "enable_extra_prompt": enable_extra_prompt})

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
            processed_tool = ToolsLoader._process_tool(tool_info, extra_tools_prompt, extra_param_prompt)
            if processed_tool:
                tools.append(processed_tool)

        return tools

    @staticmethod
    def _process_tool(tool_info, extra_tools_prompt: str, extra_param_prompt: dict):
        """处理单个工具，应用额外提示"""
        try:
            func = copy.deepcopy(tool_info["func"])
            enable_extra_prompt = tool_info["enable_extra_prompt"]

            if enable_extra_prompt:
                ToolsLoader._apply_extra_prompts(func, extra_tools_prompt, extra_param_prompt)

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
            param_descriptions = [f"{key}:{value}" for key, value in extra_param_prompt.items()]

            # 使用模板加载器生成动态参数提示
            final_prompt = TemplateLoader.render_template(
                "prompts/tools/dynamic_param_generation", {"param_descriptions": ", ".join(param_descriptions)}
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
        tool_functions = ToolsLoader._extract_tools_from_module(module, enable_extra_prompt)

        if tool_functions:
            logger.info(f"从 {tool_category} 加载了 {len(tool_functions)} 个工具")

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

    @staticmethod
    def get_all_tools_metadata():
        """
        动态发现所有工具函数，返回工具元数据列表，用于 OpsPilot Agent 配置

        返回格式适配原 YAML 配置，包含工具名称、构造函数、描述等信息。
        对于包含多个工具的工具集(如 kubernetes)，会列出所有子工具。

        Returns:
            list: 工具元数据列表，格式为:
                [
                    {
                        'name': 'tool_category_name',              # 工具或工具集名称
                        'constructor': 'module.path',              # 模块路径
                        'constructor_description': 'module desc',  # 构造函数(模块)描述
                        'description': 'tool description',         # 工具描述
                        'parameters': {...},                       # 工具参数Schema(可选)
                        'tools': [                                 # 工具集包含的子工具(可选)
                            {
                                'name': 'sub_tool_name',
                                'description': 'sub tool desc',
                                'parameters': {...}                # 子工具参数Schema
                            }
                        ]
                    }
                ]
        """
        logger.info("开始提取所有工具的元数据")
        metadata_list = []

        for tool_category, (module, enable_extra_prompt) in ToolsLoader.TOOL_MODULES.items():
            tool_functions = ToolsLoader._extract_tools_from_module(module, enable_extra_prompt)

            if not tool_functions:
                continue

            # 获取模块路径
            module_path = module.__name__

            # 提取工具集描述(从模块的 docstring)
            category_description = module.__doc__.strip() if module.__doc__ else f"{tool_category} 工具集"

            # 提取构造参数(如果模块定义了 CONSTRUCTOR_PARAMS)
            constructor_params = getattr(module, "CONSTRUCTOR_PARAMS", None)

            # 如果只有一个工具，作为单一工具处理
            if len(tool_functions) == 1:
                tool_func = tool_functions[0]["func"]
                tool_metadata = {
                    "name": tool_category,
                    "constructor": module_path,
                    "constructor_description": category_description,
                    "description": tool_func.description or category_description,
                }
                # 添加构造参数信息
                if constructor_params:
                    tool_metadata["constructor_parameters"] = constructor_params
                # 添加工具参数信息
                if hasattr(tool_func, "args_schema") and tool_func.args_schema:
                    tool_metadata["parameters"] = tool_func.args_schema.schema()

                metadata_list.append(tool_metadata)
            else:
                # 多个工具，作为工具集处理
                sub_tools = []
                for tool_info in tool_functions:
                    tool_func = tool_info["func"]
                    sub_tool_info = {"name": tool_func.name, "description": tool_func.description or ""}
                    # 添加子工具参数信息
                    if hasattr(tool_func, "args_schema") and tool_func.args_schema:
                        sub_tool_info["parameters"] = tool_func.args_schema.schema()

                    sub_tools.append(sub_tool_info)

                tool_set_metadata = {
                    "name": tool_category,
                    "constructor": module_path,
                    "constructor_description": category_description,
                    "description": category_description,
                    "tools": sub_tools,
                }
                # 添加构造参数信息
                if constructor_params:
                    tool_set_metadata["constructor_parameters"] = constructor_params

                metadata_list.append(tool_set_metadata)

            logger.info(f"提取工具类别 '{tool_category}': {len(tool_functions)} 个工具")

        logger.info(f"总共提取 {len(metadata_list)} 个工具/工具集的元数据")
        return metadata_list
