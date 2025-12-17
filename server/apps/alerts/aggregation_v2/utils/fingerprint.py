# -- coding: utf-8 --
"""
指纹生成工具

提供事件和告警的指纹生成功能
"""
from typing import Dict, Any

# 复用现有的指纹生成逻辑
from apps.alerts.utils.util import generate_instance_fingerprint as _generate_fingerprint


class FingerprintGenerator:
    """指纹生成器"""
    
    @staticmethod
    def generate_event_fingerprint(event_data: Dict[str, Any]) -> str:
        """
        生成事件指纹
        
        基于以下字段生成唯一标识：
        - resource_id: 资源ID
        - item: 指标名称
        - source_id: 告警源ID
        - rule_id: 规则ID
        
        Args:
            event_data: 事件数据字典
            
        Returns:
            32位MD5哈希字符串
            
        Examples:
            >>> data = {
            ...     "resource_id": "host-001",
            ...     "item": "cpu_usage",
            ...     "source_id": "monitor",
            ...     "rule_id": "rule-123"
            ... }
            >>> FingerprintGenerator.generate_event_fingerprint(data)
            "a1b2c3d4e5f6..."
        """
        return _generate_fingerprint(event_data)
    
    @staticmethod
    def generate_session_key(fingerprint: str, session_id: int) -> str:
        """
        生成会话键
        
        Args:
            fingerprint: 事件指纹
            session_id: 会话序号
            
        Returns:
            会话键字符串
            
        Examples:
            >>> FingerprintGenerator.generate_session_key("abc123", 5)
            "session-abc123-S5"
        """
        return f"session-{fingerprint}-S{session_id}"
    
    @staticmethod
    def generate_window_id(window_type: str, timestamp: int, window_index: int = 0) -> str:
        """
        生成窗口ID
        
        Args:
            window_type: 窗口类型 (fixed/sliding/session)
            timestamp: 时间戳（秒）
            window_index: 窗口索引
            
        Returns:
            窗口ID字符串
            
        Examples:
            >>> FingerprintGenerator.generate_window_id("fixed", 1733841443, 0)
            "FIXED-1733841443-0"
        """
        return f"{window_type.upper()}-{timestamp}-{window_index}"
