"""Prophet 模型的 MLflow 推理包装器

此文件仅包含推理所需的代码，避免导入训练相关的重型依赖。
Prophet 是原生时间序列模型，不需要特征工程，预测模式简单直接。
"""

from typing import Optional
import pandas as pd
import numpy as np
import mlflow
from loguru import logger


class ProphetWrapper(mlflow.pyfunc.PythonModel):
    """Prophet 模型的 MLflow 包装器
    
    Prophet 是原生时间序列预测模型，直接使用 sktime 的 Prophet 进行预测。
    无需特征工程和递归预测，Prophet 内部处理趋势、季节性和节假日效应。
    """
    
    def __init__(
        self,
        model,
        training_frequency: Optional[str],
        prophet_params: Optional[dict] = None
    ):
        """初始化包装器
        
        Args:
            model: 训练好的 sktime Prophet 模型
            training_frequency: 训练时的时间序列频率（如 'MS', 'D', 'H'）
            prophet_params: Prophet 参数字典（用于记录）
        """
        self.model = model
        self.training_frequency = training_frequency
        self.prophet_params = prophet_params or {}
        
        logger.debug(
            f"ProphetWrapper 初始化: "
            f"freq={training_frequency}, "
            f"params={prophet_params}"
        )
    
    def predict(self, context, model_input) -> np.ndarray:
        """预测接口
        
        支持多种输入格式（与 GradientBoostingWrapper 保持一致）：
        1. {'history': pd.Series, 'steps': int} - 标准格式（history 用于未来扩展）
        2. {'steps': int} - 简化格式（仅指定预测步数）
        3. int - 最简格式（直接传入预测步数）
        
        Args:
            context: MLflow context
            model_input: 输入数据（多种格式）
            
        Returns:
            预测结果数组
        """
        # 解析输入
        history, steps = self._parse_input(model_input)
        
        # Prophet 直接预测未来 N 步
        # 注意：当前 Prophet 不使用 history（模型训练时已固定），
        # 但保留接口以支持未来可能的扩展（如在线学习）
        return self._predict_direct(steps)
    
    def _parse_input(self, model_input) -> tuple:
        """解析输入数据（支持多种格式）
        
        Args:
            model_input: 输入数据
                - dict: {'history': pd.Series, 'steps': int} 或 {'steps': int}
                - int: 直接传入预测步数
            
        Returns:
            (history, steps) 元组
            - history: 历史数据（可为 None）
            - steps: 预测步数
        """
        if isinstance(model_input, dict):
            # 字典格式
            steps = model_input.get('steps')
            history = model_input.get('history', None)
            
            if steps is None:
                raise ValueError("输入字典必须包含 'steps' 字段")
            
            # 验证 history（如果提供）
            if history is not None and not isinstance(history, pd.Series):
                logger.warning(f"history 类型错误: 期望 pd.Series，实际 {type(history)}，将忽略")
                history = None
            
            return history, int(steps)
        
        elif isinstance(model_input, (int, np.integer)):
            # 整数格式
            return None, int(model_input)
        
        else:
            raise ValueError(
                f"输入格式错误: 期望 dict 或 int，实际为 {type(model_input)}\n"
                f"支持的格式:\n"
                f"  1. {{'history': pd.Series, 'steps': int}}\n"
                f"  2. {{'steps': int}}\n"
                f"  3. int"
            )
    
    def _predict_direct(self, steps: int) -> np.ndarray:
        """直接预测未来 N 步
        
        Prophet 模型已经在训练时拟合了完整的历史数据，
        预测时直接调用 sktime 的 predict 方法即可。
        
        Args:
            steps: 预测步数
            
        Returns:
            预测结果数组
        """
        try:
            from sktime.forecasting.base import ForecastingHorizon
            
            # 构建预测范围
            fh = ForecastingHorizon(range(1, steps + 1), is_relative=True)
            
            # 调用 Prophet 预测
            y_pred = self.model.predict(fh)
            
            # 转换为 numpy 数组
            if isinstance(y_pred, pd.Series):
                predictions = y_pred.values
            elif isinstance(y_pred, pd.DataFrame):
                predictions = y_pred.iloc[:, 0].values
            else:
                predictions = np.asarray(y_pred)
            
            logger.debug(f"Prophet 预测完成: steps={steps}, shape={predictions.shape}")
            
            return predictions
            
        except Exception as e:
            logger.error(f"Prophet 预测失败: {e}")
            raise RuntimeError(f"Prophet 预测失败: {e}") from e
    
    def get_params(self) -> dict:
        """获取模型参数
        
        Returns:
            参数字典
        """
        return {
            'training_frequency': self.training_frequency,
            'prophet_params': self.prophet_params,
            'model_type': 'Prophet'
        }
