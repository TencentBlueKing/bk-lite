from typing import Dict

from neco.llm.rag.naive_rag.recall_strategies.base_recall_strategy import BaseRecallStrategy
from neco.llm.rag.naive_rag.recall_strategies.chunk_recall_strategy import ChunkRecallStrategy
from neco.llm.rag.naive_rag.recall_strategies.origin_recall_strategy import OriginRecallStrategy
from neco.llm.rag.naive_rag.recall_strategies.segment_recall_strategy import SegmentRecallStrategy



class RecallStrategyFactory:
    """召回策略工厂类"""
    
    # 注册所有可用的召回策略
    _strategies: Dict[str, BaseRecallStrategy] = {
        'chunk': ChunkRecallStrategy(),
        'segment': SegmentRecallStrategy(),
        'origin': OriginRecallStrategy(),
    }
    
    @classmethod
    def get_strategy(cls, strategy_name: str) -> BaseRecallStrategy:
        """
        根据策略名称获取对应的召回策略
        
        Args:
            strategy_name: 策略名称
            
        Returns:
            召回策略实例
            
        Raises:
            ValueError: 当策略名称不存在时
        """
        if strategy_name not in cls._strategies:
            available_strategies = ', '.join(cls._strategies.keys())
            raise ValueError(f"不支持的召回策略: {strategy_name}。可用策略: {available_strategies}")
        
        return cls._strategies[strategy_name]
    
    @classmethod
    def get_available_strategies(cls) -> list:
        """
        获取所有可用的策略名称
        
        Returns:
            可用策略名称列表
        """
        return list(cls._strategies.keys())
    
    @classmethod
    def register_strategy(cls, strategy: BaseRecallStrategy) -> None:
        """
        注册新的召回策略
        
        Args:
            strategy: 召回策略实例
        """
        cls._strategies[strategy.get_strategy_name()] = strategy
