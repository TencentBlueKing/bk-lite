# -- coding: utf-8 --
# @File: base_collector.py
# @Time: 2025/12/19
# @Author: AI Assistant
"""
采集器基类
定义采集器的通用接口
"""
from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseCollector(ABC):
    """采集器基类"""

    def __init__(self, params: Dict[str, Any]):
        """
        初始化采集器

        Args:
            params: 采集参数
        """
        self.params = params

    @abstractmethod
    async def collect(self) -> str:
        """
        执行采集

        Returns:
            Prometheus 格式的指标数据
        """
        pass

