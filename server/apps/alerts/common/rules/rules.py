# -- coding: utf-8 --
# @File: rules.py
# @Time: 2025/9/16 18:31
# @Author: windyzhao

NEW_INIT_RULES = [
    # ==================== 规则1: 高级别事件聚合 ====================
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
        "strategy_type": "composite",
        # 策略特定配置（可选，用于表单配置和快速访问）
        "strategy_config": {
            "logic": "AND",  # 多条件组合逻辑
            "conditions": []
        },
        # ========== 窗口推荐配置（用于前端表单推荐）==========
        "default_window_config": {
            "recommended_types": ["fixed", "sliding"],  # 推荐的窗口类型
            "default_type": "fixed",  # 默认窗口类型
            "default_params": {
                "fixed": {
                    "window_size": "5min",
                    "alignment": "minute",
                    "description": "每5分钟检查一次，适合定期巡检",
                    "use_case": "定期统计"
                },
                "sliding": {
                    "window_size": "10min",
                    "slide_interval": "1min",
                    "description": "实时滑动监控，反应更灵敏",
                    "use_case": "实时监控"
                }
            },
            "not_recommended": ["session"],
            "reason": "性能指标监控是持续性的，不需要会话边界检测"
        },

        # 详细的执行条件（支持更复杂的配置）
        "condition": [
            {
                # ========== 过滤器配置 ==========
                "filter": {
                    # 简单过滤：字段名 -> 条件对象
                    "level": {
                        "operator": "<=",
                        "value": 2
                    },
                    # 支持自定义 SQL 表达式（高级用户）
                    "custom_sql": None  # 例如: "level <= 2 AND resource_type IN ('server', 'database')"
                },
                # ========== 分组配置 ==========
                "aggregation_key": ["fingerprint"],  # 按指纹分组
                # ========== 聚合配置 ==========
                "aggregation_rules": {
                    "min_event_count": 1,  # 最小事件数阈值
                    "include_labels": True,  # 是否包含标签聚合
                    "include_stats": True,  # 是否包含统计信息
                    # 自定义聚合表达式（DuckDB SQL）
                    "custom_aggregations": {
                        "min_severity_level": "MIN(level)",
                        "affected_items": "STRING_AGG(DISTINCT item, ',')",
                        "first_event_time": "MIN(start_time)",
                        "last_event_time": "MAX(start_time)",
                        "event_count": "COUNT(*)"
                    }
                }
            }
        ]
    },
    # ==================== 规则2: 关键事件频率聚合 ====================
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
        "strategy_type": "frequency",
        # 策略特定配置
        "strategy_config": {
            "logic": "AND",
            "conditions": []
        },
        # ========== 窗口推荐配置 ==========
        "default_window_config": {
            "recommended_types": ["sliding"],
            "default_type": "sliding",
            "default_params": {
                "sliding": {
                    "window_size": "5min",
                    "slide_interval": "30s",
                    "description": "实时监控最近5分钟的错误率，30秒滑动一次",
                    "use_case": "实时监控"
                }
            },
            "not_recommended": ["fixed", "session"],
            "reason": "频率监控需要实时计算，固定窗口延迟高，会话窗口不适用"
        },
        # 详细的执行条件
        "condition": [
            {
                # ========== 过滤器配置 ==========
                "filter": {
                    "resource_type": {
                        "operator": "=",
                        "value": "网站拨测"
                    },
                    "item": {
                        "operator": "=",
                        "value": "status"
                    },
                    "value": {
                        "operator": "=",
                        "value": 0  # 失败状态
                    },
                    "custom_sql": None
                },
                # ========== 分组配置 ==========
                "aggregation_key": ["fingerprint"],
                # ========== 聚合配置 ==========
                "aggregation_rules": {
                    "min_event_count": 1,
                    "include_labels": True,
                    "include_stats": True,
                    # 频率相关的聚合
                    "custom_aggregations": {
                        "failure_count": "COUNT(*)",
                        "first_failure_time": "MIN(start_time)",
                        "last_failure_time": "MAX(start_time)",
                        "affected_urls": "STRING_AGG(DISTINCT COALESCE(labels->>'url', 'N/A'), ',')",
                        "avg_response_time": "AVG(CAST(COALESCE(labels->>'response_time', '0') AS FLOAT))"
                    }
                }
            }
        ]
    },

    # ==================== 规则3: 会话窗口错误处理 ====================
    {
        "rule_id": "error_scenario_handling",
        "name": "Error Scenario Handling",
        "description": {
            "zh": "错误场景处理规则。当操作失败后10分钟内无修正动作则告警，如有持续操作或成功事件则不告警。适用于CI/CD流水线等需要智能判断人工介入的场景。",
            "en": "Error scenario handling rule. Alerts when operation fails and no corrective action within 10 minutes. No alert if continuous operations or success event. Suitable for CI/CD pipelines requiring intelligent detection of human intervention."
        },
        "severity": "warning",
        "is_active": True,
        "template_title": "Jenkins构建失败告警",
        "template_content": "Jenkins任务 {resource_name} 构建失败，失败次数: {failure_count}，持续时间: {session_duration_minutes}分钟",
        "type": "alert",
        "strategy_type": "composite",
        # 策略特定配置
        "strategy_config": {
            "logic": "AND",
            "conditions": []
        },

        # ========== 窗口推荐配置 ==========
        "default_window_config": {
            "recommended_types": ["session"],
            "default_type": "session",
            "default_params": {
                "session": {
                    "session_timeout": "10min",
                    "max_window_size": "1h",
                    "description": "适合追踪完整的构建流程（从失败到修复），10分钟无操作关闭会话",
                    "use_case": "监控CI/CD流程"
                }
            },
            "not_recommended": ["fixed", "sliding"],
            "reason": "构建流程有明确的开始和结束，需要会话窗口自动检测边界，固定和滑动窗口无法准确捕获完整流程"
        },

        # 详细的执行条件
        "condition": [
            {
                # ========== 过滤器配置 ==========
                "filter": {
                    "resource_type": {
                        "operator": "=",
                        "value": "jenkins"
                    },
                    "item": {
                        "operator": "=",
                        "value": "jenkins_build_status"
                    },
                    "value": {
                        "operator": "=",
                        "value": 0  # 失败状态
                    },
                    "custom_sql": None
                },

                # ========== 分组配置 ==========
                "aggregation_key": ["fingerprint"],
                # ========== 聚合配置 ==========
                "aggregation_rules": {
                    "min_event_count": 1,
                    "include_labels": True,
                    "include_stats": True,

                    # 使用 FILTER 子句统计不同状态的事件
                    "custom_aggregations": {
                        "failure_count": "COUNT(*) FILTER (WHERE value = 0)",
                        "success_count": "COUNT(*) FILTER (WHERE value = 1)",
                        "first_failure": "MIN(start_time) FILTER (WHERE value = 0)",
                        "last_operation": "MAX(start_time)",
                        "total_operations": "COUNT(*)",
                        "session_duration_minutes": "EXTRACT(EPOCH FROM (MAX(start_time) - MIN(start_time))) / 60",
                        "build_ids": "STRING_AGG(DISTINCT COALESCE(labels->>'build_id', 'unknown'), ',')"
                    }
                },

                # ========== 会话关闭条件（可选）==========
                "session_close": {
                    "enabled": True,
                    "filter": {
                        "resource_type": {
                            "operator": "=",
                            "value": "jenkins"
                        },
                        "item": {
                            "operator": "=",
                            "value": "jenkins_build_status"
                        },
                        "value": {
                            "operator": "=",
                            "value": 1  # 成功状态关闭会话
                        }
                    },
                    "action": "close_session",
                    "aggregation_key": ["fingerprint"]
                }
            }
        ]
    }
]
