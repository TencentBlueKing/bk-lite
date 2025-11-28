"""
模板加载器模块
用于加载和渲染 Jinja2 模板
"""
import os
from pathlib import Path
from typing import Dict, Any, Optional, Union

from jinja2 import Environment, FileSystemLoader, Template, TemplateNotFound
from loguru import logger
import importlib.resources as resources

class TemplateLoader:
    """
    Jinja2 模板加载器

    用于加载 templates/{module}/{file} 路径下的模板文件并渲染
    使用类方法模式，无需实例化
    """

    _default_base_path: Optional[Path] = None
    _env_cache: Dict[str, Environment] = {}

    @classmethod
    def configure(cls, base_path: Optional[str] = None) -> None:
        """
        配置全局默认的模板基础路径

        Args:
            base_path: 模板文件的基础路径，默认为当前工作目录下的 templates 文件夹
        """
        if base_path is None:
            base_path = cls._get_package_support_files_path()

        cls._default_base_path = Path(base_path)
        # 清除环境缓存，强制重新创建
        cls._env_cache.clear()

    @classmethod
    def _get_package_support_files_path(cls) -> str:
        """
        获取包内 support-files 目录的路径
        
        Returns:
            support-files 目录的绝对路径
        """
        try:
            if hasattr(resources, 'files'):
                # Python 3.9+ 使用 importlib.resources.files
                package_path = resources.files('neco')
                support_files_path = package_path / 'support-files'
                
                # 如果是 Traversable 对象,需要转换为字符串路径
                if hasattr(support_files_path, '__fspath__'):
                    resource_path = os.fspath(support_files_path)
                else:
                    resource_path = str(support_files_path)
                    
                return resource_path
            else:
                # Python 3.8 及更早版本的回退方案
                import neco
                neco_path = Path(neco.__file__).parent
                support_files_path = neco_path / 'support-files'
                resource_path = str(support_files_path)
                return resource_path
        except Exception as e:
            # 最后的回退方案:使用当前工作目录
            fallback_path = str(Path.cwd() / 'support-files')
            return fallback_path
    @classmethod
    def _get_environment(cls, base_path: Optional[str] = None) -> Environment:
        """
        获取 Jinja2 环境对象，使用缓存避免重复创建

        Args:
            base_path: 模板文件的基础路径

        Returns:
            Jinja2 Environment 对象
        """
        if base_path is None:
            if cls._default_base_path is None:
                cls.configure()  # 使用默认配置
            base_path_obj = cls._default_base_path
        else:
            base_path_obj = Path(base_path)

        base_path_str = str(base_path_obj)

        # 检查缓存
        if base_path_str in cls._env_cache:
            return cls._env_cache[base_path_str]

        # 确保模板目录存在
        if not base_path_obj.exists():
            logger.warning(
                f"Templates directory does not exist: {base_path_obj}")
            base_path_obj.mkdir(parents=True, exist_ok=True)

        # 创建新的环境对象
        env = Environment(
            loader=FileSystemLoader(base_path_str),
            autoescape=True,  # 默认开启自动转义
            trim_blocks=True,
            lstrip_blocks=True
        )

        # 缓存环境对象
        cls._env_cache[base_path_str] = env
        return env

    @classmethod
    def _find_template_path(cls, filepath: str, base_path: Optional[str] = None) -> Optional[str]:
        """
        智能查找模板文件路径

        Args:
            filepath: 模板文件路径（可能不包含扩展名）
            base_path: 模板文件的基础路径

        Returns:
            找到的模板路径，如果没找到返回 None
        """
        if base_path is None:
            if cls._default_base_path is None:
                cls.configure()  # 使用默认配置
            base_path_obj = cls._default_base_path
        else:
            base_path_obj = Path(base_path)

        # 可能的扩展名
        extensions = ['', '.jinja2', '.j2', '.html', '.txt']

        # 可能的文件路径（支持自动添加 prompts/ 前缀）
        possible_paths = [
            filepath,
            f"prompts/{filepath}",
            f"templates/{filepath}"
        ]

        for path in possible_paths:
            for ext in extensions:
                # 如果已经有扩展名，跳过添加扩展名
                if any(path.endswith(e) for e in extensions[1:]):
                    template_path = path
                else:
                    template_path = f"{path}{ext}"

                full_path = base_path_obj / template_path

                if full_path.exists() and full_path.is_file():
                    return template_path

        return None

    @classmethod
    def load_template(cls, filepath: str, context: Optional[Dict[str, Any]] = None,
                      base_path: Optional[str] = None) -> Union[Template, str]:
        """
        加载指定路径的模板

        Args:
            filepath: 模板文件路径（如 "qa_pair/system_prompt" 或 "prompts/qa_pair/system_prompt"）
            context: 可选的模板渲染上下文变量，如果提供则直接返回渲染后的文本
            base_path: 模板文件的基础路径，默认使用全局配置

        Returns:
            如果提供了 context，返回渲染后的文本内容；否则返回 Jinja2 Template 对象

        Raises:
            TemplateNotFound: 当模板文件不存在时
        """
        # 首先尝试智能查找模板路径
        template_path = cls._find_template_path(filepath, base_path)

        if template_path is None:
            # 如果智能查找失败，回退到原始路径
            template_path = filepath

        env = cls._get_environment(base_path)

        try:
            template = env.get_template(template_path)

            # 如果提供了 context，直接渲染并返回文本
            if context is not None:
                rendered_text = template.render(**context)
                return rendered_text

            return template
        except TemplateNotFound as e:
            current_base_path = cls._default_base_path if base_path is None else base_path
            logger.error(
                f"Template not found: {template_path}, base_path: {current_base_path}")
            logger.error(f"Searched for filepath='{filepath}'")
            raise e

    @classmethod
    def render_template(cls, filepath: str, context: Optional[Dict[str, Any]] = None,
                        base_path: Optional[str] = None) -> str:
        """
        渲染指定路径的模板

        Args:
            filepath: 模板文件路径（如 "qa_pair/system_prompt" 或 "prompts/qa_pair/system_prompt"）
            context: 模板渲染上下文变量，默认为空字典
            base_path: 模板文件的基础路径，默认使用全局配置

        Returns:
            渲染后的文本内容

        Raises:
            TemplateNotFound: 当模板文件不存在时
        """
        if context is None:
            context = {}

        try:
            template = cls.load_template(filepath, base_path=base_path)
            rendered_text = template.render(**context)
            return rendered_text

        except Exception as e:
            logger.error(
                f"Failed to render template: {filepath}, error: {str(e)}")
            raise e

    @classmethod
    def template_exists(cls, filepath: str, base_path: Optional[str] = None) -> bool:
        """
        检查指定模板是否存在

        Args:
            filepath: 模板文件路径（如 "qa_pair/system_prompt" 或 "prompts/qa_pair/system_prompt"）
            base_path: 模板文件的基础路径，默认使用全局配置

        Returns:
            True 如果模板存在，否则 False
        """
        # 使用智能查找
        template_path = cls._find_template_path(filepath, base_path)
        exists = template_path is not None

        logger.debug(f"Template exists check: {filepath} -> {exists}")
        return exists

    @classmethod
    def list_templates(cls, directory: str = "", base_path: Optional[str] = None) -> list[str]:
        """
        列出指定目录下的所有模板文件

        Args:
            directory: 目录路径（如 "qa_pair" 或 "prompts/qa_pair"）
            base_path: 模板文件的基础路径，默认使用全局配置

        Returns:
            模板文件路径列表
        """
        if base_path is None:
            if cls._default_base_path is None:
                cls.configure()  # 使用默认配置
            base_path_obj = cls._default_base_path
        else:
            base_path_obj = Path(base_path)

        # 可能的目录路径
        possible_dirs = [
            directory,
            f"prompts/{directory}",
            f"templates/{directory}"
        ] if directory else ["", "prompts", "templates"]

        templates = []
        for dir_path in possible_dirs:
            search_path = base_path_obj / dir_path if dir_path else base_path_obj

            if not search_path.exists():
                continue

            for file_path in search_path.rglob("*"):
                if file_path.is_file() and file_path.suffix in ['.html', '.txt', '.j2', '.jinja2']:
                    # 返回相对于 base_path 的路径
                    relative_path = file_path.relative_to(base_path_obj)
                    # 移除扩展名，返回用户友好的路径
                    template_path = str(relative_path.with_suffix(''))
                    if template_path not in templates:
                        templates.append(template_path)

        logger.debug(
            f"Found {len(templates)} templates in directory: {directory}")
        return sorted(templates)
