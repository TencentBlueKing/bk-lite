# -- coding: utf-8 --
"""
模板引擎

提供 Jinja2 模板加载、渲染、缓存功能
"""
from typing import Dict, Any, Optional
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, Template
from jinja2.exceptions import TemplateError

from apps.core.logger import alert_logger as logger
from apps.alerts.aggregation_v2.templates.context import TemplateContext
from apps.alerts.models import CorrelationRules


class TemplateEngine:
    """
    Jinja2 模板引擎
    
    职责：
    1. 加载和管理 Jinja2 模板
    2. 渲染 SQL 模板
    3. 模板缓存
    4. 错误处理
    """
    
    # 模板目录
    TEMPLATE_DIR = Path(__file__).parent
    
    # 主模板文件
    UNIFIED_TEMPLATE = "unified_aggregation.jinja"
    
    # 单例模式
    _instance = None
    _env = None
    
    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self) -> None:
        """初始化 Jinja2 环境"""
        if self._env is None:
            self._env = Environment(
                loader=FileSystemLoader(str(self.TEMPLATE_DIR)),
                trim_blocks=True,
                lstrip_blocks=True,
                autoescape=False  # SQL 不需要自动转义
            )
            
            # 添加自定义过滤器
            self._register_filters()
            
            logger.info(f"Jinja2 环境初始化完成: 模板目录={self.TEMPLATE_DIR}")
    
    def _register_filters(self) -> None:
        """注册自定义过滤器"""
        # SQL 安全过滤器（防止注入）
        def sql_safe(value):
            """SQL 值安全转义"""
            if value is None:
                return 'NULL'
            elif isinstance(value, str):
                # 转义单引号
                return f"'{value.replace(chr(39), chr(39) + chr(39))}'"
            elif isinstance(value, (int, float)):
                return str(value)
            else:
                return str(value)
        
        self._env.filters['sql_safe'] = sql_safe
    
    def render_sql(
        self,
        correlation_rule: CorrelationRules,
        current_time: Optional[Any] = None
    ) -> str:
        """
        渲染 SQL 模板
        
        Args:
            correlation_rule: 关联规则对象
            current_time: 当前时间（可选）
            
        Returns:
            渲染后的 SQL 语句
            
        Raises:
            TemplateError: 模板渲染失败
            
        Examples:
            >>> engine = TemplateEngine()
            >>> rule = CorrelationRules.objects.get(id=1)
            >>> sql = engine.render_sql(rule)
            >>> print(sql)
        """
        try:
            # 构建模板上下文
            context = TemplateContext.build_context(correlation_rule, current_time)
            
            # 加载模板
            template = self._env.get_template(self.UNIFIED_TEMPLATE)
            
            # 渲染 SQL
            sql = template.render(**context)
            
            # 清理 SQL（移除多余空行）
            sql = self._clean_sql(sql)
            
            logger.debug(
                f"SQL 模板渲染完成: 规则={correlation_rule.name}, "
                f"窗口={context['window_type']}, 策略={context['strategy_type']}"
            )
            
            return sql
            
        except TemplateError as e:
            logger.error(f"模板渲染失败: {e}")
            raise
        except Exception as e:
            logger.error(f"SQL 渲染异常: {e}")
            raise
    
    def render_custom_template(
        self,
        template_str: str,
        context: Dict[str, Any]
    ) -> str:
        """
        渲染自定义模板字符串
        
        Args:
            template_str: 模板字符串
            context: 模板上下文
            
        Returns:
            渲染结果
        """
        try:
            template = self._env.from_string(template_str)
            result = template.render(**context)
            return result
        except TemplateError as e:
            logger.error(f"自定义模板渲染失败: {e}")
            raise
    
    def validate_template(self, template_name: str) -> bool:
        """
        验证模板是否存在且语法正确
        
        Args:
            template_name: 模板文件名
            
        Returns:
            True=有效，False=无效
        """
        try:
            template = self._env.get_template(template_name)
            # 尝试渲染一个空上下文（仅检查语法）
            template.render()
            return True
        except TemplateError as e:
            logger.error(f"模板验证失败: {template_name}, 错误={e}")
            return False
    
    def _clean_sql(self, sql: str) -> str:
        """
        清理 SQL 语句
        
        - 移除多余空行
        - 统一换行符
        - 移除行尾空格
        
        Args:
            sql: 原始 SQL
            
        Returns:
            清理后的 SQL
        """
        # 分割为行
        lines = sql.split('\n')
        
        # 处理每一行
        cleaned_lines = []
        for line in lines:
            # 移除行尾空格
            line = line.rstrip()
            
            # 跳过空行和注释行（仅在非 SQL 内容时）
            if not line or line.strip().startswith('--'):
                continue
            
            cleaned_lines.append(line)
        
        # 重新组合
        cleaned_sql = '\n'.join(cleaned_lines)
        
        return cleaned_sql
    
    @classmethod
    def get_template_info(cls, template_name: str) -> Dict[str, Any]:
        """
        获取模板信息（调试用）
        
        Args:
            template_name: 模板文件名
            
        Returns:
            模板信息字典
        """
        template_path = cls.TEMPLATE_DIR / template_name
        
        if not template_path.exists():
            return {
                "exists": False,
                "path": str(template_path)
            }
        
        with open(template_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return {
            "exists": True,
            "path": str(template_path),
            "size": len(content),
            "lines": len(content.split('\n')),
            "content": content
        }
    
    @classmethod
    def preview_sql(
        cls,
        correlation_rule: CorrelationRules,
        pretty: bool = True
    ) -> str:
        """
        预览 SQL（用于调试和展示）
        
        Args:
            correlation_rule: 关联规则对象
            pretty: 是否美化输出
            
        Returns:
            SQL 语句
        """
        engine = cls()
        sql = engine.render_sql(correlation_rule)
        
        if pretty:
            # 简单的 SQL 美化（可以后续用 sqlparse 替换）
            sql = sql.replace(' WHERE ', '\nWHERE ')
            sql = sql.replace(' FROM ', '\nFROM ')
            sql = sql.replace(' GROUP BY ', '\nGROUP BY ')
            sql = sql.replace(' ORDER BY ', '\nORDER BY ')
            sql = sql.replace(' AND ', '\n  AND ')
            sql = sql.replace(' OR ', '\n  OR ')
        
        return sql
