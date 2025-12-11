"""SARIMA 参数优化工具

遵循渐进式设计原则，提供恰如其分的功能：
- 智能差分阶数检测 (基于 ADF 检验)
- 季节周期推断 (基于数据频率)
- 参数有效性验证
"""

from typing import Dict, Tuple, Optional
import pandas as pd
import numpy as np
from loguru import logger


def estimate_differencing(data: pd.Series, max_d: int = 2) -> Optional[int]:
    """
    估计差分阶数 (基于 ADF 检验)
    
    Args:
        data: 时间序列数据
        max_d: 最大差分阶数
        
    Returns:
        建议的差分阶数, 失败返回 None
    """
    try:
        from statsmodels.tsa.stattools import adfuller
        
        for d in range(max_d + 1):
            test_data = data.diff(d).dropna() if d > 0 else data
            
            if len(test_data) < 20:  # 样本太少
                continue
            
            adf_result = adfuller(test_data, autolag='AIC')
            p_value = adf_result[1]
            
            # p < 0.05 表示平稳
            if p_value < 0.05:
                logger.debug(f"ADF检验: d={d}, p-value={p_value:.4f} (平稳)")
                return d
        
        # 如果都不平稳，返回 1 阶差分
        logger.debug("ADF检验: 未检测到平稳性，默认返回 d=1")
        return 1
        
    except Exception as e:
        logger.warning(f"差分阶数估计失败: {e}")
        return None


def infer_seasonality(data: pd.Series) -> Optional[list]:
    """
    根据数据频率推断季节周期
    
    Args:
        data: 时间序列数据
        
    Returns:
        建议的周期列表, 失败返回 None
    """
    if not isinstance(data.index, pd.DatetimeIndex):
        return None
    
    try:
        freq = pd.infer_freq(data.index)
        if not freq:
            return None
        
        # 启发式规则
        freq_map = {
            'H': [24, 168],      # 小时: 日/周
            'D': [7, 30],        # 日: 周/月
            'W': [4, 52],        # 周: 月/年
            'M': [12],           # 月: 年
            'Q': [4],            # 季度: 年
        }
        
        for prefix, periods in freq_map.items():
            if freq.startswith(prefix):
                logger.debug(f"频率推断: {freq} → 周期 {periods}")
                return periods
        
        return None
        
    except Exception as e:
        logger.warning(f"季节周期推断失败: {e}")
        return None


def validate_params(p: int, d: int, q: int,
                   P: int, D: int, Q: int, s: int,
                   data_length: int) -> Tuple[bool, str]:
    """
    验证 SARIMA 参数有效性
    
    Args:
        p, d, q: ARIMA 参数
        P, D, Q, s: 季节 ARIMA 参数
        data_length: 数据长度
        
    Returns:
        (是否有效, 原因说明)
    """
    # 规则 1: 差分不能过度
    if d + D > 2:
        return False, f"差分过度: d+D={d+D}>2"
    
    # 规则 2: 参数总数限制
    if p + q + P + Q > 8:
        return False, f"参数过多: {p+q+P+Q}>8"
    
    # 规则 3: 避免全零模型
    if p == 0 and q == 0 and P == 0 and Q == 0:
        return False, "无效模型: p=q=P=Q=0"
    
    # 规则 4: 样本数量检查
    min_required = (p + P * s + d + D * s) * 3
    if data_length < min_required:
        return False, f"样本不足: {data_length}<{min_required}"
    
    # 规则 5: 季节周期合理性
    if s > data_length // 3:
        return False, f"周期过长: s={s}>数据长度/3"
    
    # 规则 6: D > 0 时必须 s > 1
    if D > 0 and s <= 1:
        return False, f"季节性差分要求周期>1: D={D}, s={s}"
    
    return True, "验证通过"
