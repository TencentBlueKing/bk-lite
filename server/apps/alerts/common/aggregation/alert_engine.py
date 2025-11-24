# -- coding: utf-8 --
# @File: alert_engine.py
# @Time: 2025/5/21 11:02
# @Author: windyzhao
import pandas as pd
import numpy as np
from typing import Dict, List, Callable, Tuple, Any
from dataclasses import dataclass

from apps.alerts.constants import AlertStatus
from apps.alerts.models import Alert
from apps.alerts.utils.util import generate_instance_fingerprint
from apps.core.logger import alert_logger as logger


@dataclass
class AlertRule:
    name: str
    condition: Callable[[pd.DataFrame], Tuple[bool, List[List[str]]]]  # 修正类型注解
    aggregation: Dict[str, List[str]]
    description: str
    rule_id: str
    title: str = ""
    content: str = ""
    severity: str = "medium"
    is_active: bool = True
    alert_sources: List[str] = None
    aggregation_key: List[str] = None
    # 聚合策略配置详解：
    aggregation_strategy: str = "group_by"
    """
    告警聚合策略，决定如何处理相似的告警：

    1. "group_by": 按指定字段分组聚合（默认）
       - 相同主机+实例+指标的告警会聚合到一个告警中
       - 例如：host1的CPU使用率高，多次触发只产生1个告警
       - 适用场景：避免同一问题产生大量重复告警

    2. "merge_all": 合并所有相同规则的告警
       - 不管主机、实例等字段，只要是同一个规则触发就合并
       - 例如：多台主机CPU都超标，合并成1个"批量CPU告警"
       - 适用场景：集群级别的告警，关注整体趋势

    3. "create_new": 总是创建新告警
       - 每次规则触发都创建独立的告警，不进行任何聚合
       - 例如：每次CPU超标都产生新告警，保留完整历史
       - 适用场景：需要详细记录每次异常的场景
    """

    aggregation_window: str = "0"
    """
    聚合时间窗口，控制告警聚合的时间范围：

    作用：
    - 只有在此时间窗口内的告警才会被聚合
    - 超过时间窗口的告警即使条件相同也不会聚合

    示例：
    - 设置为"5m"：5分钟内的相似告警会聚合
    - 设置为"1h"：1小时内的相似告警会聚合
    - 设置为"0"：禁用时间窗口限制

    实际场景：
    - CPU告警在10:00触发，10:03再次触发 → 聚合到同一告警
    - CPU告警在10:00触发，10:07再次触发 → 创建新告警（超过5分钟）

    好处：
    - 避免长时间累积过多事件到单个告警
    - 确保告警的时效性和相关性
    """

    max_alerts_per_group: int = 100  # 未使用
    """
    每个分组最大告警数量限制：

    作用：
    - 防止单个告警组包含过多的事件或子告警
    - 避免告警爆炸导致系统性能问题

    实际场景：
    - 网络抖动导致1000台主机同时告警
    - 限制为100，只保留最新的100个相关告警
    - 超出部分会被丢弃或创建新的告警组

    保护机制：
    - 防止单个告警包含过多数据导致查询缓慢
    - 避免告警通知包含过多信息难以阅读
    - 保护数据库和内存使用
    """


class RuleEngine:
    """高性能Pandas规则引擎（优化版：按实例分组处理）"""

    OPERATORS = {
        '>': np.greater,
        '>=': np.greater_equal,
        '<': np.less,
        '<=': np.less_equal,
        '==': np.equal,
        'in': lambda x, y: np.isin(x, y),  # 添加in操作符支持
        'not_in': lambda x, y: ~np.isin(x, y)  # 添加not_in操作符支持
    }

    # 定义实例分组字段
    INSTANCE_GROUP_FIELDS = ['item', 'resource_id', 'resource_type', 'alert_source']

    def __init__(self, window_size: str = "10min"):
        self.window_size = pd.to_timedelta(window_size)  # 事件处理窗口
        self.rules: Dict[str, AlertRule] = {}
        self.required_fields = ['item', 'resource_id', 'resource_type', 'alert_source', 'rule_id']

    def add_rule(self, rule_config: dict):
        try:
            condition_func = self._create_condition(rule_config)
            self.rules[rule_config['rule_id']] = AlertRule(
                name=rule_config['name'],
                rule_id=rule_config['rule_id'],
                title=rule_config.get('title', ''),
                content=rule_config.get('content', ''),
                condition=condition_func,
                aggregation=rule_config.get('', {}),
                description=rule_config.get('description', ''),
                severity=rule_config.get('severity', 'medium'),
                is_active=rule_config.get('is_active', True),
                # alert_sources=rule_config.get('alert_sources', None),
                # 新增聚合策略配置
                aggregation_strategy=rule_config.get('aggregation_strategy', 'group_by'),
                aggregation_window=rule_config.get('aggregation_window', '0'),
                max_alerts_per_group=rule_config.get('max_alerts_per_group', 100),
                aggregation_key=rule_config.get("condition", {}).get("aggregation_key") or ["resource_name",
                                                                                            "resource_type"]
            )
        except Exception as e:
            logger.error(f"Rule {rule_config.get('name')} add failed: {e}")
            raise

    def _create_condition(self, rule_config: dict) -> Callable:
        condition_type = rule_config['condition']['type']
        config = rule_config['condition']

        condition_map = {
            'threshold': self._create_threshold_condition,
            'sustained': self._create_sustained_condition,
            'trend': self._create_trend_condition,
            'prev_field_equals': self._create_status_condition,
            'level_filter': self._create_level_filter_condition,
            'website_monitoring': self._create_website_monitoring_condition,
            'filter_and_check': self._create_filter_and_check_condition  # 新增
        }

        if condition_type not in condition_map:
            raise ValueError(f"Unknown condition type: {condition_type}")

        return condition_map[condition_type](config)

    def _create_threshold_condition(self, config: dict) -> Callable:
        # 创建阈值条件函数
        field = config['field']
        threshold = config['threshold']
        op_func = self.OPERATORS[config['operator']]

        def condition(df: pd.DataFrame) -> Tuple[bool, List[List[str]]]:
            if df.empty:
                return False, []
            # 只取 item=field 的行
            field_df = df[df["item"] == field]
            if field_df.empty:
                return False, []
            mask = op_func(field_df["value"], threshold)
            # 将每个触发事件ID作为单独的组返回
            event_groups = [[event_id] for event_id in field_df.loc[mask, 'event_id'].tolist()]
            return len(event_groups) > 0, event_groups

        return condition

    def _create_sustained_condition(self, config: dict) -> Callable:
        # 创建持续条件函数
        field = config['field']
        threshold = config['threshold']
        op_func = self.OPERATORS[config['operator']]
        consecutive = config['required_consecutive']

        def condition(df: pd.DataFrame) -> Tuple[bool, List[List[str]]]:
            field_df = df[df["item"] == field].sort_values('received_at')
            if len(field_df) < consecutive:
                return False, []

            # 计算每个点是否满足条件
            mask = op_func(field_df["value"], threshold)

            # 寻找连续满足条件的组
            event_groups = []
            current_group = []

            # 遍历数据帧中的每一行
            for idx, row in field_df.iterrows():
                if mask[idx]:
                    # 如果满足条件，添加到当前组
                    current_group.append(row['event_id'])
                else:
                    # 不满足条件，检查之前的组是否达到了连续阈值
                    if len(current_group) >= consecutive:
                        event_groups.append(current_group)
                    # 重置当前组
                    current_group = []

            # 检查循环结束后最后一个分组
            if len(current_group) >= consecutive:
                event_groups.append(current_group)

            return len(event_groups) > 0, event_groups

        return condition

    def _create_trend_condition(self, config: dict) -> Callable:
        field = config['field']
        threshold = config['threshold']
        op_func = self.OPERATORS[config['operator']]
        baseline_window = config['baseline_window']
        method = config.get('trend_method', 'absolute')

        def condition(df: pd.DataFrame) -> Tuple[bool, List[List[str]]]:
            field_df = df[df["item"] == field]
            if len(field_df) <= baseline_window:
                return False, []
            baseline = field_df["value"].iloc[:-1].rolling(baseline_window).mean().iloc[-1]
            current = field_df["value"].iloc[-1]
            if method == 'percentage':
                change = (current - baseline) / baseline * 100 if baseline != 0 else 0
            else:
                change = current - baseline

            # 检查是否满足条件
            triggered = op_func(change, threshold)

            # 创建事件组列表
            event_groups = []
            if triggered:
                # 获取最新事件ID作为触发事件
                latest_event_id = field_df['event_id'].iloc[-1]
                event_groups.append([latest_event_id])

            return len(event_groups) > 0, event_groups

        return condition

    def _create_status_condition(self, config: dict) -> Callable:
        # 创建状态条件函数
        group_fields = config['group_by']
        status_field = config['prev_status_field']
        target_status = config['prev_status_value']

        def condition(df: pd.DataFrame) -> Tuple[bool, List[List[str]]]:
            if len(df) < 2:
                return False, []
            df_sorted = df.sort_values('received_at')
            df_sorted = df_sorted[df_sorted[status_field] == target_status]
            grouped = df_sorted.groupby(group_fields)
            event_groups = []
            for _, group in grouped:
                if len(group) < 2:
                    continue
                prev_status = group[status_field].iloc[-2]
                if prev_status == target_status:
                    # 每个触发事件作为独立的组
                    event_groups.append([group['event_id'].iloc[-1]])
            return len(event_groups) > 0, event_groups

        return condition

    def _create_website_monitoring_condition(self, config: dict) -> Callable:
        """创建网站拨测条件函数"""
        resource_type_field = config['resource_type_field']
        target_resource_type = config['target_resource_type']
        status_field = config['status_field']
        abnormal_value = config['abnormal_value']
        aggregation_key = config.get('aggregation_key', ['resource_id'])
        immediate_alert = config.get('immediate_alert', True)

        def condition(df: pd.DataFrame) -> Tuple[bool, List[List[str]]]:
            if df.empty:
                return False, []

            # 过滤网站拨测类型的事件
            website_df = df[df[resource_type_field] == target_resource_type]
            if website_df.empty:
                return False, []

            # 过滤异常状态的事件 - 改为基于数值判断
            abnormal_df = website_df[website_df[status_field] == abnormal_value]
            if abnormal_df.empty:
                return False, []

            event_groups = []

            if immediate_alert:
                # 立即告警模式：每个异常事件都产生告警，但按网站聚合
                grouped = abnormal_df.groupby(aggregation_key)
                for group_key, group_df in grouped:
                    # 每个网站的所有异常事件作为一个组
                    event_ids = group_df['event_id'].tolist()
                    event_groups.append(event_ids)
            else:
                # 普通模式：每个异常事件单独处理
                for _, row in abnormal_df.iterrows():
                    event_groups.append([row['event_id']])

            return len(event_groups) > 0, event_groups

        return condition

    def _create_level_filter_condition(self, config: dict) -> Callable:
        """创建等级过滤条件函数"""
        filter_criteria = config.get('filter', {})
        target_field = config.get('target_field')
        target_field_value = config.get('target_field_value')
        target_value_field = config.get('target_value_field', 'level')
        target_value = config.get('target_value')
        operator = config.get('operator', '<=')
        aggregation_key = config.get('aggregation_key', ['resource_id'])

        # 等级优先级映射
        level_priority = {'info': 3, 'warning': 2, 'error': 1, 'critical': 0}
        threshold_priority = level_priority.get(target_value, 3)

        def condition(df: pd.DataFrame) -> Tuple[bool, List[List[str]]]:
            if df.empty:
                return False, []

            # 应用过滤条件
            filtered_df = df.copy()
            for key, value in filter_criteria.items():
                if key in filtered_df.columns:
                    filtered_df = filtered_df[filtered_df[key] == value]

            # 不是网站拨测类型的规则，过滤掉网站拨测
            filtered_df = filtered_df[filtered_df['resource_type'] != '网站拨测']

            if filtered_df.empty:
                return False, []

            # 做类型转换，确保 level 列是int类型
            filtered_df['level_priority'] = filtered_df[target_value_field].astype(int)

            if operator == '>=':
                result_df = filtered_df[filtered_df['level_priority'] >= threshold_priority]
            elif operator == '>':
                result_df = filtered_df[filtered_df['level_priority'] > threshold_priority]
            elif operator == '<=':
                result_df = filtered_df[filtered_df['level_priority'] <= threshold_priority]
            elif operator == '<':
                result_df = filtered_df[filtered_df['level_priority'] < threshold_priority]
            else:  # '=='
                result_df = filtered_df[filtered_df['level_priority'] == threshold_priority]

            if result_df.empty:
                return False, []

            # 按聚合键分组
            event_groups = []
            grouped = result_df.groupby(aggregation_key)
            for group_key, group_df in grouped:
                event_ids = group_df['event_id'].tolist()
                event_groups.append(event_ids)

            return len(event_groups) > 0, event_groups

        return condition

    def _create_filter_and_check_condition(self, config: dict) -> Callable:
        """创建通用过滤检查条件"""
        filter_criteria = config.get('filter', {})
        target_field = config.get('target_field')
        target_field_value = config.get('target_field_value')
        target_value_field = config.get('target_value_field', 'value')
        target_value = config.get('target_value')
        operator = config.get('operator', '==')
        aggregation_key = config.get('aggregation_key', ['resource_id'])

        def condition(df: pd.DataFrame) -> Tuple[bool, List[List[str]]]:
            if df.empty:
                return False, []

            # 应用过滤条件
            filtered_df = df.copy()
            for key, value in filter_criteria.items():
                if key in filtered_df.columns:
                    filtered_df = filtered_df[filtered_df[key] == value]

            if filtered_df.empty:
                return False, []

            # 如果指定了target_field检查
            if target_field and target_field_value:
                filtered_df = filtered_df[filtered_df[target_field] == target_field_value]

            if filtered_df.empty:
                return False, []

            # 检查目标值条件
            if target_field in filtered_df.columns:
                if operator in ['in', 'not_in']:
                    # 处理数组值比较
                    if operator == 'in':
                        mask = filtered_df[target_field].isin(target_value)
                    else:  # not_in
                        mask = ~filtered_df[target_field].isin(target_value)
                else:
                    # 处理单值比较
                    op_func = self.OPERATORS[operator]
                    if target_value_field in filtered_df.columns:
                        mask = op_func(filtered_df[target_value_field], target_value)
                    else:
                        # 如果没有指定target_value_field，直接比较target_field
                        mask = op_func(filtered_df[target_field], target_value)

                matched_df = filtered_df[mask]

                if not matched_df.empty:
                    # 按聚合键分组
                    event_groups = []
                    grouped = matched_df.groupby(aggregation_key)
                    for group_key, group_df in grouped:
                        event_ids = group_df['event_id'].tolist()
                        event_groups.append(event_ids)
                    return True, event_groups

            return False, []

        return condition

    def group_events_by_instance(self, events: pd.DataFrame, fields: List = []) -> Dict[str, pd.DataFrame]:
        """
        按实例分组事件数据

        Args:
            events: 原始事件DataFrame
            fields: 用于生成实例指纹的字段列表（可选）

        Returns:
            按实例指纹分组的事件字典
        """
        # 为每个事件生成实例指纹
        events = events.copy()

        # 确保必要的字段存在

        missing_fields = [field for field in self.required_fields if field not in events.columns]
        if missing_fields:
            # 为缺失的字段填充默认值
            for field in missing_fields:
                events[field] = 'unknown'

        # 生成实例指纹
        events['instance_fingerprint'] = events.apply(
            lambda row: generate_instance_fingerprint(row.to_dict(), fields),
            axis=1
        )

        # 按实例指纹分组
        grouped_events = {}
        for fingerprint, group_df in events.groupby('instance_fingerprint'):
            # **关键修复：保留 instance_fingerprint 列，而不是删除它**
            clean_group = group_df.reset_index(drop=True)
            # 按照时间排序
            clean_group = clean_group.sort_values(by='received_at', ascending=True)

            # 确保分组不为空
            if not clean_group.empty:
                grouped_events[fingerprint] = clean_group
            else:
                logger.warning(f"Empty group found for fingerprint: {fingerprint}")

        logger.info(f"Grouped {len(events)} events into {len(grouped_events)} instances")
        return grouped_events

    def _check_instance_alert_status(self, instance_fingerprint: str, rule: AlertRule) -> Tuple[bool, List[Dict], str]:
        """
        检查实例是否已有活跃告警

        Args:
            instance_fingerprint: 实例指纹
            rule: 告警规则

        Returns:
            (是否需要创建新告警, 相关告警列表, 操作类型)
        """
        # 查询该实例是否已有活跃告警
        query_conditions = {
            # 'rule_name': rule.name,
            'status__in': AlertStatus.ACTIVATE_STATUS,
            'fingerprint': instance_fingerprint,  # 使用实例指纹查询
            'rule_id': rule.rule_id,  # 使用规则ID查询
        }

        # 添加时间窗口限制
        if rule.aggregation_window and rule.aggregation_window != "0":
            aggregation_window = pd.to_timedelta(rule.aggregation_window)
            current_time = pd.Timestamp.now()
            query_conditions['created_at__gte'] = current_time - aggregation_window

        related_alerts = self._query_alerts_from_db(query_conditions)

        if not related_alerts:
            return True, [], "create_new"
        else:
            # 已有活跃告警，更新现有告警
            return False, related_alerts, "update_existing"

    @staticmethod
    def _query_alerts_from_db(query_conditions: Dict) -> List[Dict]:
        """
        从数据库查询告警实例

        Args:
            query_conditions: 查询条件字典

        Returns:
            告警实例列表
        """
        alerts = Alert.objects.filter(**query_conditions).values()
        return list(alerts)

    def _process_instance_events(self, events: pd.DataFrame) -> List[Dict[str, Dict[str, Any]]]:
        """
        处理单个实例的事件

        Args:
            events: 单个实例的事件数据

        Returns:
            该实例的规则处理结果
        """
        result_list = []

        for rule_id, rule in self.rules.items():
            if not rule.is_active:
                continue

            aggregation_key = self.rules[rule_id].aggregation_key if rule_id in self.rules else []

            # **关键：按实例分组处理**
            grouped_events = self.group_events_by_instance(events, fields=aggregation_key)

            if not grouped_events:
                logger.info("No events to process after grouping")
                continue

            # 对每个实例分别应用规则
            for instance_fingerprint, instance_events in grouped_events.items():
                logger.debug(f"Processing {len(instance_events)} events for instance: {instance_fingerprint}")
                results = {}

                try:
                    # 对单个实例应用规则（这样保证了持续条件等规则的正确性）
                    triggered, event_groups = rule.condition(instance_events)

                    if triggered:
                        # 展平事件ID列表
                        flat_event_ids = [event_id for group in event_groups for event_id in group]

                        # 检查是否需要创建新告警（基于实例指纹）
                        should_create_new, related_alerts, operation_type = self._check_instance_alert_status(
                            instance_fingerprint, rule
                        )

                        results[rule_id] = {
                            'triggered': True,
                            'event_ids': flat_event_ids,
                            'instance_fingerprint': instance_fingerprint,
                            'instance_events': instance_events,
                            'severity': rule.severity,
                            'description': rule.description,
                            'rule': rule,
                            'should_create_new': should_create_new,
                            'related_alerts': related_alerts,
                            'operation_type': operation_type,
                        }
                    else:
                        results[rule_id] = {'triggered': False}

                except Exception as e:
                    logger.error(f"Rule {rule_id} evaluation failed for instance {instance_fingerprint}: {e}")
                    results[rule_id] = {'triggered': False, 'error': str(e)}

                finally:
                    result_list.append(results)

        return result_list

    def process_events(self, events: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
        """
        处理事件并返回告警结果（按实例分组处理）
        """

        results = {}

        if events.empty:
            return results

        # 确保存在alert_source字段
        events['alert_source'] = events['source__name']

        # 按实例分组事件 分别应用规则
        rule_instance_results = self._process_instance_events(events)

        for instance_events in rule_instance_results:
            # 合并结果
            for rule_name, rule_result in instance_events.items():
                if rule_name not in results:
                    results[rule_name] = {
                        'triggered': False,
                        'instances': {},
                        'total_event_ids': [],
                        'severity': None,
                        'description': None,
                        'source_name': '',
                        'rule': ''
                    }

                if rule_result['triggered']:
                    results[rule_name]['rule'] = rule_result['rule']
                    results[rule_name]['triggered'] = True
                    results[rule_name]['instances'][rule_result['instance_fingerprint']] = rule_result
                    results[rule_name]['total_event_ids'].extend(rule_result['event_ids'])
                    results[rule_name]['severity'] = rule_result['severity']
                    results[rule_name]['description'] = rule_result['description']
                    results[rule_name]['source_name'] = rule_result['instance_events']['alert_source'].iloc[0]

        logger.info(f"Processing completed. {len(results)} rules triggered.")
        return results
