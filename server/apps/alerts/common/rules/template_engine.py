# -- coding: utf-8 --
# @File: template_engine.py
# @Time: 2025/9/17 10:30
# @Author: windyzhao
"""
基于Jinja2的SQL模板引擎模块

提供灵活的SQL模板渲染功能，支持：
1. 固定窗口告警检测SQL生成
2. 动态条件过滤和聚合配置
3. 可扩展的模板系统
4. 安全的参数验证和注入防护
"""

import os
from typing import Dict, List, Any, Optional, Union
from pathlib import Path
from dataclasses import dataclass, field
from jinja2 import Environment, FileSystemLoader, select_autoescape
from jinja2.exceptions import TemplateError, TemplateNotFound
from apps.core.logger import alert_logger as logger


@dataclass
class FilterCondition:
    """过滤条件配置"""
    field: str
    operator: str  # =, !=, >, <, >=, <=, IN, NOT IN, LIKE, NOT LIKE
    value: Union[str, int, float, List[Any]]

    def __post_init__(self):
        """验证操作符安全性和参数完整性"""
        allowed_operators = {'=', '!=', '>', '<', '>=', '<=', 'IN', 'NOT IN', 'LIKE', 'NOT LIKE'}
        if self.operator not in allowed_operators:
            raise ValueError(f"不支持的操作符: {self.operator}，支持的操作符: {allowed_operators}")

        # 验证字段名不为空
        if not self.field or not self.field.strip():
            raise ValueError("字段名不能为空")

        # 验证IN/NOT IN操作符的值必须是列表
        if self.operator in ('IN', 'NOT IN') and not isinstance(self.value, list):
            raise ValueError(f"操作符 {self.operator} 的值必须是列表类型")

        # 验证值不为空（除了空字符串的合法情况）
        if self.value is None:
            raise ValueError("过滤条件的值不能为None")


@dataclass
class AggregationRules:
    """聚合规则配置"""
    min_event_count: int = 1
    include_labels: bool = True
    include_stats: bool = True
    custom_aggregations: Dict[str, str] = field(default_factory=dict)


@dataclass
class TemplateContext:
    """模板渲染上下文

    封装SQL模板渲染所需的所有参数和配置。
    这个类定义了动态窗口告警检测的完整配置模型，支持固定窗口和滑动窗口两种模式。

    主要配置项说明：
    - table: 数据源表名，通常是事件表
    - time_column: 时间戳字段，用于窗口切分和排序
    - window_size: 窗口大小（分钟），决定时间切分粒度
    - window_type: 窗口类型，'fixed'(固定窗口) 或 'sliding'(滑动窗口)
    - slide_interval: 滑动间隔（分钟），仅用于滑动窗口，默认1分钟
    - resource_filters: 资源级别的过滤条件，用于筛选监控对象
    - threshold_conditions: 阈值级别的过滤条件，用于判断是否触发告警
    - group_by_fields: 分组字段列表，决定聚合维度
    - aggregation_rules: 聚合计算规则，控制统计指标的计算

    窗口类型对比：
    1. 固定窗口(fixed)：
       - 窗口边界严格对齐到时间间隔的倍数
       - 窗口之间不重叠，适用于定期检查场景
       - 性能更好，资源消耗较低

    2. 滑动窗口(sliding)：
       - 窗口按指定间隔滑动，可以重叠
       - 更敏感的异常检测，能更快发现问题
       - 适用于实时监控，但资源消耗较高

    使用建议：
    1. 窗口大小应根据监控频率合理设置（1-60分钟常见）
    2. 滑动间隔通常设置为窗口大小的1/5到1/2，如5分钟窗口配1分钟滑动
    3. 分组字段应包含关键的业务维度（如主机ID、服务名等）
    4. 过滤条件应尽量具体，避免扫描过多无关数据
    5. 阈值条件应结合业务场景设置合理的触发条件
    """
    table: str = 'alerts_event'
    time_column: str = 'start_time'
    window_size: int = 5
    window_type: str = 'fixed'  # 'fixed' | 'sliding'
    slide_interval: int = 1  # 仅用于滑动窗口，单位分钟
    resource_filters: List[FilterCondition] = field(default_factory=list)
    threshold_conditions: List[FilterCondition] = field(default_factory=list)
    group_by_fields: List[str] = field(default_factory=list)
    aggregation_rules: AggregationRules = field(default_factory=AggregationRules)

    def __post_init__(self):
        """后初始化验证"""
        # 验证窗口类型
        if self.window_type not in ['fixed', 'sliding', 'session']:
            raise ValueError(f"不支持的窗口类型: {self.window_type}，只支持 'fixed' 或 'sliding' 或 'session'")

        # 验证滑动间隔（仅对滑动窗口）
        if self.window_type == 'sliding':
            if self.slide_interval <= 0:
                raise ValueError("滑动间隔必须大于0")
            if self.slide_interval > self.window_size:
                raise ValueError("滑动间隔不能大于窗口大小")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式，用于模板渲染"""
        return {
            'table': self.table,
            'time_column': self.time_column,
            'window_size': self.window_size,
            'resource_filters': [
                {
                    'field': f.field,
                    'operator': f.operator,
                    'value': f.value
                } for f in self.resource_filters
            ],
            'threshold_conditions': [
                {
                    'field': f.field,
                    'operator': f.operator,
                    'value': f.value
                } for f in self.threshold_conditions
            ],
            'group_by_fields': self.group_by_fields,
            'aggregation_rules': {
                'min_event_count': self.aggregation_rules.min_event_count,
                'include_labels': self.aggregation_rules.include_labels,
                'include_stats': self.aggregation_rules.include_stats,
                'custom_aggregations': self.aggregation_rules.custom_aggregations,
            }
        }


class AlertSQLTemplateEngine:
    """告警SQL模板引擎

    基于Jinja2的SQL模板渲染引擎，专为告警检测场景设计。
    主要功能：
    1. 固定窗口告警检测SQL生成 - 将时间轴按固定间隔切分，适用于定期检查场景
    2. 安全的SQL参数验证和注入防护 - 防止SQL注入攻击
    3. 灵活的过滤和聚合配置 - 支持多种过滤条件和聚合规则
    4. 可扩展的模板系统 - 支持自定义模板和过滤器

    使用场景：
    - 主机性能监控（CPU、内存、磁盘等）
    - 应用服务监控（响应时间、错误率等）
    - 网络设备监控（带宽、丢包率等）
    - 业务指标监控（订单量、用户活跃度等）

    安全特性：
    - SQL注入防护：自动转义危险字符
    - 字段名验证：只允许安全的标识符
    - 操作符白名单：限制可用的SQL操作符
    - 参数完整性检查：确保必要参数不为空
    """
    TEMPLATE_FILE = 'windows_template.jinja'

    def __init__(self, template_dir: Optional[str] = None):
        """
        初始化模板引擎

        Args:
            template_dir: 模板文件目录路径，默认使用当前目录
        """
        if template_dir is None:
            template_dir = os.path.dirname(os.path.abspath(__file__))

        self.template_dir = Path(template_dir)

        # 初始化Jinja2环境
        self.env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=select_autoescape(['html', 'xml']),
            trim_blocks=True,
            lstrip_blocks=True
        )

        # 注册自定义过滤器和函数
        self._register_custom_filters()

        logger.info(f"SQL模板引擎初始化完成，模板目录: {self.template_dir}")

    def _register_custom_filters(self):
        """注册自定义Jinja2过滤器"""

        def sql_escape(value):
            """SQL注入防护过滤器 - 转义特殊字符"""
            if isinstance(value, str):
                # 转义单引号、分号、注释符号等危险字符
                return value.replace("'", "''").replace(";", "").replace("--", "").replace("/*", "").replace("*/", "")
            elif isinstance(value, list):
                # 处理列表类型（用于IN操作）
                return [str(item).replace("'", "''").replace(";", "").replace("--", "") for item in value]
            return str(value)

        def field_validate(field_name):
            """字段名验证过滤器 - 确保字段名安全"""
            if not isinstance(field_name, str):
                raise ValueError(f"字段名必须是字符串类型: {field_name}")

            # 只允许字母、数字、下划线
            allowed_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789')
            if not all(c in allowed_chars for c in field_name):
                raise ValueError(f"非法字段名，只允许字母、数字、下划线: {field_name}")

            # 不能以数字开头
            if field_name and field_name[0].isdigit():
                raise ValueError(f"字段名不能以数字开头: {field_name}")

            return field_name

        # 注册过滤器到Jinja2环境
        self.env.filters['sql_escape'] = sql_escape
        self.env.filters['field_validate'] = field_validate

    def render_dynamic_window_sql(self, context: TemplateContext) -> str:
        """
        渲染动态窗口告警检测SQL（支持固定窗口和滑动窗口）

        根据context.window_type自动选择合适的窗口算法：

        固定窗口(fixed)算法说明：
        1. 时间轴按固定间隔切分（如每5分钟一个窗口）
        2. 窗口边界严格对齐到指定间隔的倍数
        3. 事件根据时间戳分配到对应窗口
        4. 按窗口和分组条件聚合统计
        5. 应用阈值条件过滤结果

        滑动窗口(sliding)算法说明：
        1. 生成多个重叠的时间窗口，每个窗口大小相同
        2. 窗口按指定间隔(slide_interval)滑动
        3. 每个事件可能属于多个重叠窗口
        4. 分别对每个窗口进行聚合统计
        5. 返回所有窗口的统计结果

        适用场景对比：
        - 固定窗口：定期检查、批量统计、资源消耗低
        - 滑动窗口：实时监控、敏感检测、快速响应

        Args:
            context: 模板渲染上下文，必须包含：
                - window_type: 'fixed' 或 'sliding'
                - window_size: 窗口大小（分钟）
                - slide_interval: 滑动间隔（分钟，仅滑动窗口使用）
                - 其他标准配置项

        Returns:
            渲染后的SQL字符串，自动适配不同窗口类型

        Raises:
            TemplateError: 模板渲染错误
            ValueError: 参数验证错误
            TemplateNotFound: 模板文件未找到

        示例用法：
            # 固定窗口示例
            context = TemplateContext(
                window_type="fixed",
                window_size=5,
                threshold_conditions=[FilterCondition("event_count", ">=", 3)]
            )

            # 滑动窗口示例
            context = TemplateContext(
                window_type="sliding",
                window_size=5,
                slide_interval=1,
                threshold_conditions=[FilterCondition("event_count", ">=", 3)]
            )

            sql = engine.render_dynamic_window_sql(context)
        """
        try:
            # 验证上下文参数
            self._validate_context(context)

            # 获取模板
            template = self.env.get_template(self.TEMPLATE_FILE)

            # 渲染SQL
            sql = template.render(**context.to_dict())

            logger.info(f"动态窗口SQL渲染成功，窗口类型: {context.window_type}, 窗口大小: {context.window_size}分钟")

            if context.window_type == 'sliding':
                logger.info(f"滑动窗口配置 - 滑动间隔: {context.slide_interval}分钟")

            return sql.strip()

        except TemplateNotFound as e:
            logger.error(f"模板文件未找到: {e}")
            raise TemplateError(f"模板文件未找到: {e}")
        except TemplateError as e:
            logger.error(f"模板渲染错误: {e}")
            raise
        except Exception as e:
            logger.error(f"SQL渲染失败: {e}")
            raise TemplateError(f"SQL渲染失败: {e}")

    def render_sliding_window_sql(self, context: TemplateContext) -> str:
        """
        渲染滑动窗口告警检测SQL

        这是一个便捷方法，强制使用滑动窗口模式。
        等价于设置 context.window_type = 'sliding' 后调用 render_dynamic_window_sql()

        滑动窗口算法说明：
        1. 生成多个重叠的时间窗口，每个窗口大小相同
        2. 窗口按指定间隔(slide_interval)滑动
        3. 每个事件可能属于多个重叠窗口
        4. 分别对每个窗口进行聚合统计
        5. 返回所有窗口的统计结果，按窗口序号排序

        适用场景：
        - 实时监控和敏感异常检测
        - 需要快速响应的告警场景
        - 连续性问题检测（如连续N分钟超阈值）

        性能考虑：
        - 滑动窗口会产生重叠数据，查询复杂度较高
        - 建议合理设置slide_interval，避免过于频繁的滑动
        - 适合小到中等数据量的实时监控场景

        Args:
            context: 模板渲染上下文，window_type将被强制设置为'sliding'
                    如果未设置slide_interval，将使用默认值1分钟

        Returns:
            渲染后的滑动窗口SQL字符串，包含多个重叠窗口的统计结果

        示例用法：
            context = TemplateContext(
                window_size=5,
                slide_interval=1,  # 每分钟滑动一次
                threshold_conditions=[FilterCondition("event_count", ">=", 3)]
            )
            sql = engine.render_sliding_window_sql(context)
        """
        # 强制设置为滑动窗口
        context.window_type = 'sliding'

        # 设置默认滑动间隔（如果未设置）
        if not hasattr(context, 'slide_interval') or context.slide_interval is None:
            context.slide_interval = 1

        return self.render_dynamic_window_sql(context)

    def render_fixed_window_sql(self, context: TemplateContext) -> str:
        """
        渲染固定窗口告警检测SQL

        这是一个便捷方法，强制使用固定窗口模式。
        等价于设置 context.window_type = 'fixed' 后调用 render_dynamic_window_sql()

        固定窗口算法说明：
        1. 时间轴按固定间隔切分（如每5分钟一个窗口）
        2. 窗口边界严格对齐到指定间隔的倍数
        3. 事件根据时间戳分配到对应窗口
        4. 按窗口和分组条件聚合统计
        5. 应用阈值条件过滤结果

        适用场景：
        - 需要定期检查的监控场景（如每5分钟检查一次CPU使用率）
        - 要求严格时间对齐的告警规则
        - 多资源批量监控和统计

        Args:
            context: 模板渲染上下文，window_type将被强制设置为'fixed'

        Returns:
            渲染后的固定窗口SQL字符串

        示例用法：
            context = TemplateContext(
                window_size=5,
                threshold_conditions=[FilterCondition("event_count", ">=", 3)]
            )
            sql = engine.render_fixed_window_sql(context)
        """
        # 强制设置为固定窗口
        context.window_type = 'fixed'
        return self.render_dynamic_window_sql(context)

    def render_custom_sql(self, template_name: str, context: Dict[str, Any]) -> str:
        """
        渲染自定义模板SQL

        Args:
            template_name: 模板文件名
            context: 模板渲染上下文字典

        Returns:
            渲染后的SQL字符串
        """
        try:
            template = self.env.get_template(template_name)
            sql = template.render(**context)

            logger.debug(f"自定义模板 {template_name} 渲染完成")
            return sql.strip()

        except Exception as e:
            logger.error(f"渲染自定义模板 {template_name} 时发生错误: {e}")
            raise

    def _validate_context(self, context: TemplateContext):
        """
        验证模板上下文参数

        Args:
            context: 模板渲染上下文

        Raises:
            ValueError: 参数验证失败
        """
        # 验证表名和字段名
        self._validate_identifier(context.table, "表名")
        self._validate_identifier(context.time_column, "时间字段")

        # 验证窗口大小
        if context.window_size <= 0 or context.window_size > 1440:  # 最大24小时
            raise ValueError(f"窗口大小必须在1-1440分钟之间，当前值: {context.window_size}")

        # 验证窗口类型
        if context.window_type not in ['fixed', 'sliding']:
            raise ValueError(f"不支持的窗口类型: {context.window_type}，只支持 'fixed' 或 'sliding'")

        # 验证滑动间隔（仅对滑动窗口）
        if context.window_type == 'sliding':
            if not hasattr(context, 'slide_interval') or context.slide_interval is None:
                context.slide_interval = 1  # 设置默认值
            elif context.slide_interval <= 0:
                raise ValueError(f"滑动间隔必须大于0，当前值: {context.slide_interval}")
            elif context.slide_interval > context.window_size:
                raise ValueError(f"滑动间隔({context.slide_interval})不能大于窗口大小({context.window_size})")

        # 验证分组字段
        for field in context.group_by_fields:
            self._validate_identifier(field, "分组字段")

        # 验证过滤条件
        for filter_cond in context.resource_filters + context.threshold_conditions:
            self._validate_identifier(filter_cond.field, "过滤字段")

        # 验证聚合规则
        if context.aggregation_rules.min_event_count < 0:
            raise ValueError(f"最小事件数不能为负数: {context.aggregation_rules.min_event_count}")

        logger.debug(
            f"模板上下文验证通过: 表={context.table}, 窗口类型={context.window_type}, 窗口={context.window_size}分钟")
        if context.window_type == 'sliding':
            logger.debug(f"滑动窗口配置: 滑动间隔={context.slide_interval}分钟")

    def _validate_identifier(self, identifier: str, field_type: str):
        """
        验证SQL标识符安全性

        Args:
            identifier: 标识符字符串
            field_type: 字段类型描述

        Raises:
            ValueError: 标识符不安全
        """
        if not identifier:
            raise ValueError(f"{field_type}不能为空")

        # 检查危险字符
        dangerous_chars = {';', '--', '/*', '*/', 'xp_', 'sp_'}
        if any(char in identifier.lower() for char in dangerous_chars):
            raise ValueError(f"{field_type}包含危险字符: {identifier}")

        # 检查SQL关键字
        sql_keywords = {
            'drop', 'delete', 'insert', 'update', 'alter', 'create',
            'truncate', 'exec', 'execute', 'union', 'script'
        }
        if identifier.lower() in sql_keywords:
            raise ValueError(f"{field_type}不能使用SQL关键字: {identifier}")

    def get_available_templates(self) -> List[str]:
        """
        获取可用的模板列表

        Returns:
            模板文件名列表
        """
        try:
            template_files = []
            for file_path in self.template_dir.glob('*.jinja'):
                template_files.append(file_path.name)

            logger.debug(f"发现 {len(template_files)} 个模板文件")
            return template_files

        except Exception as e:
            logger.error(f"获取模板列表时发生错误: {e}")
            return []

    def validate_sql_syntax(self, sql: str) -> bool:
        """
        基础SQL语法验证

        Args:
            sql: SQL字符串

        Returns:
            是否通过基础验证
        """
        try:
            # 基础安全检查
            sql_lower = sql.lower()

            # 检查危险SQL操作
            dangerous_keywords = [
                'drop', 'delete', 'insert', 'update', 'alter', 'create',
                'truncate', 'exec', 'execute', 'xp_', 'sp_'
            ]

            for keyword in dangerous_keywords:
                if keyword in sql_lower:
                    logger.warning(f"SQL包含危险关键字: {keyword}")
                    return False

            # 检查必要的SELECT语句
            if not sql_lower.strip().startswith('with') and not sql_lower.strip().startswith('select'):
                logger.warning("SQL必须以WITH或SELECT开始")
                return False

            return True

        except Exception as e:
            logger.error(f"SQL语法验证时发生错误: {e}")
            return False


class TemplateEngine:
    """模板引擎
    
    这是一个简化的模板引擎包装类，主要用于兼容现有的测试代码。
    内部使用 AlertSQLTemplateEngine 来实现具体功能。
    
    主要方法：
    - render_windows_template: 渲染窗口模板
    """
    
    def __init__(self, template_dir: Optional[str] = None):
        """初始化模板引擎
        
        Args:
            template_dir: 模板文件目录路径，默认使用当前目录
        """
        self.alert_engine = AlertSQLTemplateEngine(template_dir)
    
    def render_windows_template(self, context: TemplateContext) -> str:
        """渲染窗口模板
        
        这是一个便捷方法，用于渲染动态窗口告警检测SQL。
        
        Args:
            context: 模板渲染上下文
            
        Returns:
            渲染后的SQL字符串
            
        Raises:
            TemplateError: 模板渲染错误
            ValueError: 参数验证错误
        """
        return self.alert_engine.render_dynamic_window_sql(context)
    
    def render_custom_sql(self, template_name: str, context: Dict[str, Any]) -> str:
        """渲染自定义模板SQL
        
        Args:
            template_name: 模板文件名
            context: 模板渲染上下文字典
            
        Returns:
            渲染后的SQL字符串
        """
        return self.alert_engine.render_custom_sql(template_name, context)
    
    def get_available_templates(self) -> List[str]:
        """获取可用的模板列表
        
        Returns:
            模板文件名列表
        """
        return self.alert_engine.get_available_templates()
    
    def validate_sql_syntax(self, sql: str) -> bool:
        """基础SQL语法验证
        
        Args:
            sql: SQL字符串
            
        Returns:
            是否通过基础验证
        """
        return self.alert_engine.validate_sql_syntax(sql)
