# -- coding: utf-8 --
# @File: rule_adapter.py
# @Time: 2025/9/17 18:00
# @Author: windyzhao
"""
规则适配器模块

提供统一的规则处理接口，连接以下组件：
1. AggregationRules 模型 
2. JSONRuleConverter 规则转换器
3. TemplateEngine 模板引擎
4. AggregationController 聚合控制器

确保NEW_INIT_RULES能够正常运行在现有系统中。
"""

from typing import Dict, List, Any, Optional
from apps.alerts.models import AggregationRules
from apps.alerts.common.rules.json_converter_rule import JSONRuleConverter
from apps.alerts.common.rules.template_engine import TemplateEngine, TemplateContext
from apps.core.logger import alert_logger as logger


class RuleProcessingAdapter:
    """
    规则处理适配器
    
    负责协调各个组件，提供统一的规则处理接口：
    1. 从数据库加载AggregationRules
    2. 使用JSONRuleConverter转换为TemplateContext
    3. 使用TemplateEngine生成SQL
    4. 与聚合控制器集成
    """

    def __init__(self):
        self.converter = JSONRuleConverter()
        self.template_engine = TemplateEngine()

    def aggregation_rule_convert_rule(self, aggregation_rule: AggregationRules) -> Optional[TemplateContext]:
        """
        加载并转换单个规则
        
        Args:
            aggregation_rule: AggregationRules实例
            
        Returns:
            TemplateContext: 转换后的模板上下文，失败时返回None
        """
        try:
            if not aggregation_rule.condition:
                return None
            # 转换为TemplateContext
            context = self.converter.convert_aggregation_rule_to_context(aggregation_rule)

            logger.info(f"成功加载并转换规则: {aggregation_rule.rule_id}")
            return context

        except AggregationRules.DoesNotExist:
            logger.warning(f"规则不存在或未激活: {aggregation_rule.rule_id}")
            return None
        except Exception as e:
            logger.error(f"加载并转换规则失败: {aggregation_rule.rule_id} - {e}")
            return None

    def load_and_convert_all_active_rules(self) -> List[TemplateContext]:
        """
        加载并转换所有激活的规则
        
        Returns:
            List[TemplateContext]: 转换后的模板上下文列表
        """
        contexts = []

        try:
            # 获取所有激活的聚合规则
            active_rules = AggregationRules.objects.filter(is_active=True)

            for rule in active_rules:
                try:
                    context = self.converter.convert_aggregation_rule_to_context(rule)
                    contexts.append(context)
                    logger.debug(f"成功转换规则: {rule.rule_id}")
                except Exception as e:
                    logger.error(f"转换规则失败: {rule.rule_id} - {e}")
                    continue

            logger.info(f"成功加载并转换 {len(contexts)} 个激活规则")
            return contexts

        except Exception as e:
            logger.error(f"加载激活规则失败: {e}")
            return []

    def generate_rule_sql(self, aggregation_rule: AggregationRules) -> Optional[str]:
        """
        为指定规则生成SQL
        
        Args:
            aggregation_rule: AggregationRules实例
            
        Returns:
            str: 生成的SQL语句，失败时返回None
        """
        try:
            # 加载并转换规则
            context = self.aggregation_rule_convert_rule(aggregation_rule)
            if not context:
                return None

            # 生成SQL
            sql = self.template_engine.render_windows_template(context)

            logger.info(f"成功为规则 {aggregation_rule.rule_id} 生成SQL")
            return sql

        except Exception as e:
            logger.error(f"为规则 {aggregation_rule.rule_id} 生成SQL失败: {e}")
            return None

    def validate_rule_compatibility(self, aggregation_rule: AggregationRules) -> Dict[str, Any]:
        """
        验证规则的兼容性
        
        Args:
            aggregation_rule: AggregationRules实例
            
        Returns:
            Dict: 验证结果，包含成功标志、错误信息等
        """
        rule_id = aggregation_rule.rule_id
        result = {
            'rule_id': rule_id,
            'compatible': False,
            'errors': [],
            'warnings': [],
            'context': None,
            'sql': None
        }

        try:
            # 1. 尝试加载规则
            aggregation_rule = AggregationRules.objects.get(
                rule_id=rule_id,
                is_active=True
            )

            # 2. 验证condition字段结构
            if not aggregation_rule.condition:
                result['errors'].append("condition字段为空")
                return result

            if not isinstance(aggregation_rule.condition, list):
                result['errors'].append("condition字段不是列表格式")
                return result

            if not aggregation_rule.condition:
                result['errors'].append("condition列表为空")
                return result

            # 3. 尝试转换
            try:
                context = self.converter.convert_aggregation_rule_to_context(aggregation_rule)
                result['context'] = context.to_dict()
            except Exception as e:
                result['errors'].append(f"转换失败: {e}")
                return result

            # 4. 尝试生成SQL
            try:
                sql = self.template_engine.render_windows_template(context)
                result['sql'] = sql
            except Exception as e:
                result['errors'].append(f"SQL生成失败: {e}")
                return result

            # 5. 检查SQL有效性（基本验证）
            if not sql or len(sql.strip()) < 10:
                result['warnings'].append("生成的SQL可能无效")

            # 验证成功
            result['compatible'] = True
            logger.info(f"规则 {rule_id} 兼容性验证通过")

        except AggregationRules.DoesNotExist:
            result['errors'].append("规则不存在或未激活")
        except Exception as e:
            result['errors'].append(f"验证过程异常: {e}")

        return result


# 便捷函数
def create_rule_adapter() -> RuleProcessingAdapter:
    """创建规则处理适配器实例"""
    return RuleProcessingAdapter()


def quick_generate_sql(aggregation_rule: AggregationRules) -> Optional[str]:
    """快速为规则生成SQL"""
    adapter = create_rule_adapter()
    return adapter.generate_rule_sql(aggregation_rule)
