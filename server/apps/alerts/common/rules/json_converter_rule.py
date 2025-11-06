# -- coding: utf-8 --
# @File: json_converter_rule.py
# @Time: 2025/9/17 14:45
# @Author: windyzhao
from typing import Dict, List, Any

from apps.core.logger import alert_logger as logger

from apps.alerts.common.rules.template_engine import TemplateContext, FilterCondition, AggregationRules


class JSONRuleConverter:
    """JSON规则转换器

    负责将从数据库读取的JSON格式规则转换为TemplateContext对象，
    用于SQL模板渲染和DuckDB执行。

    转换流程：
    1. 从数据库读取JSON规则
    2. 验证JSON结构和字段类型
    3. 转换为TemplateContext对象
    4. 用于SQL模板渲染
    5. 执行生成的SQL
    
    支持两种规则格式：
    1. 新格式：配置嵌入在condition字段中（用于AggregationRules模型）
    2. 旧格式：独立的window_config、data_source、conditions字段
    """

    def __init__(self):
        self.conversion_stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'warnings': []
        }

    def convert_aggregation_rule_to_context(self, aggregation_rule) -> TemplateContext:
        """将AggregationRule模型转换为TemplateContext
        
        Args:
            aggregation_rule: AggregationRules模型实例
            
        Returns:
            TemplateContext: 可用于模板渲染的上下文对象
        """
        try:
            # 从condition字段提取配置
            conditions = aggregation_rule.condition

            # 取第一个条件配置（主要配置）
            main_condition = conditions[0]

            # 提取窗口配置
            window_config = aggregation_rule.window_config

            # 提取聚合配置
            aggregation_rules_config = main_condition.get('aggregation_rules', {})

            _filter = main_condition.get('filter', {})
            # 构建资源过滤条件
            resource_filters = []
            for field, value_dict in _filter.items():
                operator = value_dict.get('operator')
                value = value_dict.get('value')
                if not operator or value is None:
                    continue
                resource_filters.append(FilterCondition(field, operator, value))

            # 构建阈值条件
            threshold_conditions = []

            # 处理新统一格式的条件
            if 'level' in main_condition:
                threshold_conditions.append(FilterCondition(
                    'level',
                    main_condition.get('operator', '<='),
                    main_condition['level']
                ))

            # 事件计数条件
            threshold_conditions.append(FilterCondition('event_count', '>=', 1))

            # 转换聚合规则
            aggregation_rules = AggregationRules(
                min_event_count=aggregation_rules_config.get('min_event_count', 1),
                include_labels=aggregation_rules_config.get('include_labels', True),
                include_stats=aggregation_rules_config.get('include_stats', True),
                custom_aggregations=aggregation_rules_config.get('custom_aggregations', {})
            )

            # 创建TemplateContext
            context = TemplateContext(
                table='alerts_event',
                time_column=window_config.get('time_column', 'received_at'),
                window_size=window_config.get('window_size', 10),
                window_type=window_config.get('window_type', 'fixed'),
                slide_interval=window_config.get('slide_interval', 1),
                resource_filters=resource_filters,
                threshold_conditions=threshold_conditions,
                group_by_fields=main_condition.get('aggregation_key', ['fingerprint']),
                aggregation_rules=aggregation_rules
            )

            logger.info(f"成功转换聚合规则: {aggregation_rule.rule_id}")
            return context

        except Exception as e:
            logger.error(f"转换聚合规则失败: {aggregation_rule.rule_id} - {e}")
            # 返回默认上下文而不是抛出异常，确保系统稳定性
            return self._create_default_context()

    def _create_default_context(self) -> TemplateContext:
        """创建默认的TemplateContext"""
        return TemplateContext(
            table='alerts_event',
            time_column='received_at',
            window_size=10,
            window_type='fixed',
            slide_interval=1,
            resource_filters=[],
            threshold_conditions=[FilterCondition('event_count', '>=', 1)],
            group_by_fields=['fingerprint'],
            aggregation_rules=AggregationRules()
        )

    def convert_json_rule_to_context(self, json_rule: Dict[str, Any]) -> TemplateContext:
        """将JSON规则转换为TemplateContext

        Args:
            json_rule: 从数据库读取的JSON规则字典

        Returns:
            TemplateContext: 可用于模板渲染的上下文对象

        Raises:
            ValueError: 转换失败时抛出错误
        """
        try:
            # 验证必要字段
            self._validate_json_rule(json_rule)

            # 提取窗口配置
            window_config = json_rule.get('window_config', {})

            # 提取数据源配置
            data_source = json_rule.get('data_source', {})

            # 提取条件配置
            conditions = json_rule.get('conditions', {})

            # 转换过滤条件
            resource_filters = self._convert_filter_conditions(
                conditions.get('resource_filters', [])
            )
            threshold_conditions = self._convert_filter_conditions(
                conditions.get('threshold_conditions', [])
            )

            # 转换聚合规则
            aggregation_rules = self._convert_aggregation_rules(
                conditions.get('aggregation_rules', {})
            )

            # 创建TemplateContext
            context = TemplateContext(
                table=data_source.get('table', 'alerts_event'),
                time_column=window_config.get('time_column', 'start_time'),
                window_size=window_config.get('window_size', 5),
                window_type=window_config.get('window_type', 'fixed'),
                slide_interval=window_config.get('slide_interval', 1),
                resource_filters=resource_filters,
                threshold_conditions=threshold_conditions,
                group_by_fields=conditions.get('group_by_fields', []),
                aggregation_rules=aggregation_rules
            )

            logger.info(f"成功转换规则: {json_rule.get('rule_id')}")
            return context

        except Exception as e:
            logger.error(f"转换规则失败: {json_rule.get('rule_id', 'unknown')} - {e}")
            raise ValueError(f"转换规则失败: {e}")

    def _validate_json_rule(self, json_rule: Dict[str, Any]):
        """验证JSON规则的完整性"""
        required_fields = ['rule_id', 'name', 'window_config', 'data_source', 'conditions']

        for field in required_fields:
            if field not in json_rule:
                raise ValueError(f"缺少必要字段: {field}")

        # 验证窗口配置
        window_config = json_rule['window_config']
        if window_config.get('window_type') not in ['fixed', 'sliding']:
            raise ValueError(f"不支持的窗口类型: {window_config.get('window_type')}")

        if not isinstance(window_config.get('window_size'), int) or window_config.get('window_size') <= 0:
            raise ValueError(f"窗口大小必须是正整数: {window_config.get('window_size')}")

    def _convert_filter_conditions(self, json_conditions: List[Dict[str, Any]]) -> List[FilterCondition]:
        """转换过滤条件"""
        conditions = []

        for json_cond in json_conditions:
            try:
                condition = FilterCondition(
                    field=json_cond['field'],
                    operator=json_cond['operator'],
                    value=json_cond['value']
                )
                conditions.append(condition)
            except Exception as e:
                logger.warning(f"转换过滤条件失败: {json_cond} - {e}")
                # 可以选择跳过无效条件或抛出异常
                continue

        return conditions

    def _convert_aggregation_rules(self, json_agg: Dict[str, Any]) -> AggregationRules:
        """转换聚合规则"""
        return AggregationRules(
            min_event_count=json_agg.get('min_event_count', 1),
            include_labels=json_agg.get('include_labels', True),
            include_stats=json_agg.get('include_stats', True),
            custom_aggregations=json_agg.get('custom_aggregations', {})
        )

    def batch_convert_rules(self, json_rules: List[Dict[str, Any]]) -> List[TemplateContext]:
        """批量转换规则

        Args:
            json_rules: JSON规则列表

        Returns:
            List[TemplateContext]: 转换后的上下文列表
        """
        contexts = []
        self.conversion_stats['total'] = len(json_rules)

        for json_rule in json_rules:
            try:
                context = self.convert_json_rule_to_context(json_rule)
                contexts.append(context)
                self.conversion_stats['success'] += 1
            except Exception as e:
                self.conversion_stats['failed'] += 1
                warning = f"转换失败: {json_rule.get('rule_id', 'unknown')} - {e}"
                self.conversion_stats['warnings'].append(warning)
                logger.warning(warning)

        return contexts

    def print_conversion_summary(self):
        """打印转换摘要"""
        stats = self.conversion_stats
        print("\n" + "=" * 50)
        print("JSON规则转换摘要")
        print("=" * 50)
        print(f"总规则数: {stats['total']}")
        print(f"成功转换: {stats['success']}")
        print(f"转换失败: {stats['failed']}")
        print(f"成功率: {stats['success'] / stats['total'] * 100:.1f}%" if stats['total'] > 0 else "N/A")

        if stats['warnings']:
            print("\n警告和错误:")
            for warning in stats['warnings']:
                print(f"  {warning}")
