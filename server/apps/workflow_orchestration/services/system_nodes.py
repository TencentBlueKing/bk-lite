from __future__ import annotations

from typing import Any


def system_node_catalog_payload() -> list[dict[str, Any]]:
    """Return engine-owned nodes that are compiled into workflow control semantics."""
    nodes = [
        ("builtin.trigger.form", "表单触发器", "触发", "以 Schema 生成运行表单并接收输入"),
        ("builtin.trigger.schedule", "定时触发器", "触发", "按 Cron 表达式和平台时区启动流程"),
        ("builtin.trigger.webhook", "Webhook 触发器", "触发", "通过受控 Webhook 入口启动流程"),
        ("builtin.trigger.nats", "事件触发器（NATS）", "触发", "接收平台内部系统通过受控 NATS 通道发送的事件并启动流程"),
        ("builtin.control.condition", "条件分支", "控制", "根据结构化条件选择后续路径"),
        ("builtin.control.approval", "人工审批", "控制", "暂停当前执行并等待审批决定"),
        ("builtin.return.webhook", "Webhook 响应", "响应", "向等待模式的 Webhook 返回结果"),
    ]
    return [
        {
            "key": key,
            "name": name,
            "category": category,
            "node_type": {"触发": "TRIGGER", "控制": "CONTROL", "响应": "RETURN"}[category],
            "description": description,
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "safety_level": "READ_ONLY",
            "resource_scope": "ORGANIZATION",
            "source_type": "SYSTEM",
        }
        for key, name, category, description in nodes
    ]
