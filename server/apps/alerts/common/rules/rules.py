# -- coding: utf-8 --
# @File: rules.py
# @Time: 2025/9/16 18:31
# @Author: windyzhao
INIT_RULES = [
    {
        'rule_id': 'high_level_event_aggregation',
        'name': 'High Level Event Aggregation',
        'description': {
            "en": "Rule definition: \n1. Filtering method: event level higher than \"warning\"\n2. Aggregation dimension: Object instances of events\n3. Aggregation strategy: Aggregate based on the same object instance of the event, with the alert level being the lowest level of the event.\nCommonly used in scenarios where performance evaluation of a single operational object requires a combination of multiple dimensions for analysis, such as abnormal server performance, abnormal database performance, etc",
            "zh": "规则定义： \n1，过滤方式：event等级高于“warning”\n2，汇聚维度：event的对象实例\n3，聚合策略：按照event相同对象实例进行聚合，alert等级为event的最低等级。\n常用于单种运维对象的性能判断需要多个维度结合分析的场景，例如：服务器的性能异常、数据库的性能异常等"
        },
        'template_title': '',
        'template_content': '',
        'severity': "warning",
        'is_active': True,
        'condition': [
            {
                'filter': {},
                'level': 'warning',
                'operator': '<=',
                'aggregation_key': ['resource_type', 'resource_name']
            }
        ]
    },
    {
        'rule_id': 'critical_event_aggregation',
        'name': 'Critical Event Aggregation',
        'description': {
            "en": "Rule definition:\nRule definition: 1. Filtering method: event type\n2. Aggregation strategy: Every minute, when a certain event is abnormal, it will aggregate the repeated events of this object within 1 minute and immediately generate an alert.Commonly used scenarios for website testing",
            "zh": "规则定义：\n1，过滤方式：event类型\n2，聚合策略：每隔1分钟，检测当某个事件异常时，将1分钟内这个对象重复的事件聚合，立刻产生alert。常用于网站拨测的场景"
        },
        'template_title': '',
        'template_content': '',
        'severity': "warning",
        'is_active': True,
        'condition': [
            {
                'type': 'filter_and_check',
                'filter': {
                    'resource_type': '网站拨测'
                },
                'target_field': 'item',
                'target_field_value': 'status',
                'target_value_field': 'value',
                'target_value': 0,  # 保持为数字类型
                'operator': '==',
                'aggregation_key': ['resource_type', 'resource_name']
            }
        ]
    },
    {
        'rule_id': 'error_scenario_handling',
        'name': 'Error Scenario Handling',
        'description': {
            "zh": "当某个操作失败时，如果10分钟内没有继续修正的动作，则意味着构建失败，发出告警。如果10分钟内依旧持续操作但是依旧失败，意味着有人在介入，此时持续等待不发出告警。如果10分钟内收到操作成功的事件，则关闭等待，不发出告警。\n 常用于比如流水线构建场景，如果某流水线构建失败后，10分钟内没有继续操作的事件，则意味着短时间内代码问题无法解决，发出告警",
            "en": "When an operation fails and there are no further corrective actions within 10 minutes, it means that the build has failed and an alarm is raised. If the operation continues for 10 minutes but still fails, it means that someone is intervening and waiting continuously without issuing an alarm. If a successful operation event is received within 10 minutes, turn off waiting and no alarm will be issued.\n Commonly used in scenarios such as pipeline construction, if there is no event to continue operating within 10 minutes after a pipeline construction failure, it means that the code problem cannot be solved in a short period of time and an alarm is issued",
        },
        'template_title': '',
        'template_content': '',
        'severity': "warning",
        'is_active': True,
        'condition': [
            {
                'type': 'filter_and_check',
                'filter': {
                    'resource_type': 'jenkins',
                },
                'target_field': 'item',
                'target_field_value': 'jenkins_build_status',
                'target_value_field': 'value',
                'target_value': 0,
                'operator': '==',
                'aggregation_key': ['resource_type', 'resource_name'],
                # 新增：成功事件关闭会话的条件
                'session_close': {
                    'type': 'session_close_condition',
                    'filter': {
                        'resource_type': 'jenkins',
                    },
                    'target_field': 'item',
                    'target_field_value': 'jenkins_build_status',
                    'target_value_field': 'value',
                    'target_value': 1,  # 成功状态
                    'operator': '==',
                    'action': 'close_session',  # 关闭会话动作
                    'aggregation_key': ['resource_type', 'resource_name']
                }
            }
        ]

    }
]

NEW_INIT_RULES = [
    # 规则1: 高级别事件聚合 (high_level_event_aggregation)
    {
        "rule_id": "high_level_event_aggregation",
        "name": "High Level Event Aggregation",
        "description": {
            "zh": "高级别事件聚合规则。过滤warning以上级别事件，按对象实例聚合，告警级别取事件最低级别。适用于服务器性能异常、数据库性能异常等需要多维度综合分析的场景。",
            "en": "High level event aggregation rule. Filters events above warning level, aggregates by object instance, alert level is the lowest event level. Suitable for scenarios requiring multi-dimensional analysis like server performance anomalies and database performance issues."
        },
        "severity": "warning",
        "is_active": True,
        "template_title": "高级别事件聚合告警",
        "template_content": "检测到 {resource_type} {resource_name} 发生高级别事件聚合，涉及事件数量: {event_count}",
        "type": "alert",
        "condition": [
            {
                'filter': {
                    'level': {
                        "operator": '<=',
                        "value": 2
                    }
                },
                'aggregation_key': ['fingerprint'],
                'window_config': {
                    'window_type': 'fixed',
                    'window_size': 5,
                    'time_column': 'start_time'
                },
                'aggregation_rules': {
                    'min_event_count': 1,
                    'include_labels': True,
                    'include_stats': True,
                    'custom_aggregations': {
                        'min_severity_level': 'MIN(severity_score)',
                        'affected_items': 'STRING_AGG(DISTINCT item, \',\')',
                        'first_event_time': 'MIN(start_time)',
                        'last_event_time': 'MAX(start_time)'
                    }
                }
            }
        ],
        "image": None,
        # 继承字段使用默认值，在创建时设置
        "created_by": "system",
        "updated_by": "system",
        "domain": "domain.com",
        "updated_by_domain": "domain.com"
    },

    # 规则2: 关键事件聚合 (critical_event_aggregation)
    {
        "rule_id": "critical_event_aggregation",
        "name": "Critical Event Aggregation",
        "description": {
            "zh": "关键事件聚合规则。针对网站拨测场景，每分钟检测异常事件，1分钟内重复事件聚合并立即产生告警。适用于网站可用性监控等需要快速响应的场景。",
            "en": "Critical event aggregation rule. For website monitoring scenarios, detects abnormal events every minute, aggregates repeated events within 1 minute and generates alerts immediately. Suitable for website availability monitoring requiring rapid response."
        },
        "severity": "warning",
        "is_active": True,
        "template_title": "网站拨测异常告警",
        "template_content": "网站拨测 {resource_name} 检测到状态异常，连续失败 {failure_count} 次",
        "type": "alert",
        "condition": [
            {
                'filter': {
                    'resource_type': {
                        "operator": '==',
                        "value": '网站拨测'
                    },
                    'item': {
                        "operator": '==',
                        "value": 'status'
                    },
                    'value': {
                        "operator": '==',
                        "value": 0
                    }
                },
                'level': 'warning',
                'operator': '>=',
                'aggregation_key': ['fingerprint'],
                'window_config': {
                    'window_type': 'sliding',
                    'window_size': 1,
                    'slide_interval': 1,
                    'time_column': 'start_time'
                },
                'aggregation_rules': {
                    'min_event_count': 1,
                    'include_labels': True,
                    'include_stats': True,
                    'custom_aggregations': {
                        'failure_count': 'COUNT(*)',
                        'first_failure_time': 'MIN(start_time)',
                        'last_failure_time': 'MAX(start_time)',
                        'affected_urls': 'STRING_AGG(DISTINCT labels->\'url\', \',\')'
                    }
                }
            }
        ],
        "image": None,
        "created_by": "system",
        "updated_by": "system",
        "domain": "domain.com",
        "updated_by_domain": "domain.com"
    },

    # 规则3: 错误场景处理 (error_scenario_handling)
    {
        "rule_id": "error_scenario_handling",
        "name": "Error Scenario Handling",
        "description": {
            "zh": "错误场景处理规则。当操作失败后10分钟内无修正动作则告警，如有持续操作或成功事件则不告警。适用于CI/CD流水线等需要智能判断人工介入的场景。",
            "en": "Error scenario handling rule. Alerts when no corrective actions within 10 minutes after operation failure. No alert if continuous operations or success events occur. Suitable for CI/CD pipelines requiring intelligent detection of human intervention."
        },
        "severity": "warning",
        "is_active": True,
        "template_title": "CI/CD流水线构建失败告警",
        "template_content": "Jenkins构建 {resource_name} 失败，10分钟内无人工干预，请及时处理",
        "type": "alert",
        "condition": [
            {
                'filter': {
                    'resource_type': {
                        "operator": '==',
                        "value": 'jenkins'
                    },
                    'item': {
                        "operator": '==',
                        "value": 'jenkins_build_status'
                    },
                    'value': {
                        "operator": '==',
                        "value": 0
                    }
                },
                'level': 'warning',
                'operator': '>=',
                'aggregation_key': ['fingerprint'],
                'window_config': {
                    'window_type': 'sliding',
                    'window_size': 10,
                    'slide_interval': 1,
                    'time_column': 'start_time'
                },
                'aggregation_rules': {
                    'min_event_count': 1,
                    'include_labels': True,
                    'include_stats': True,
                    'custom_aggregations': {
                        'failure_count': 'COUNT(*) FILTER (WHERE value = 0)',
                        'success_count': 'COUNT(*) FILTER (WHERE value = 1)',
                        'first_failure': 'MIN(start_time) FILTER (WHERE value = 0)',
                        'last_operation': 'MAX(start_time)',
                        'build_status_summary': 'STRING_AGG(DISTINCT value::text, \',\')'
                    }
                },
                # 会话关闭条件保留，但简化结构
                'session_close': {
                    'filter': {
                        'resource_type': {
                            "operator": '==',
                            "value": 'jenkins'
                        },
                        'item': {
                            "operator": '==',
                            "value": 'jenkins_build_status'
                        },
                        'value': {
                            "operator": '==',
                            "value": 1
                        }
                    },
                    'action': 'close_session',
                    'aggregation_key': ['fingerprint']
                }
            }
        ],
        "image": None,
        "created_by": "system",
        "updated_by": "system",
        "domain": "domain.com",
        "updated_by_domain": "domain.com"
    }
]
