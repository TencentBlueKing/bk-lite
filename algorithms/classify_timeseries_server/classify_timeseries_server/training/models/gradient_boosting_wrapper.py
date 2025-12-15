"""Gradient Boosting 模型的 MLflow 推理包装器

此文件仅包含推理所需的代码，避免导入训练相关的重型依赖。
"""

from typing import Optional
import pandas as pd
import numpy as np
import mlflow
from loguru import logger


class GradientBoostingWrapper(mlflow.pyfunc.PythonModel):
    """Gradient Boosting 模型的 MLflow 包装器
    
    支持两种预测模式：
    1. 特征工程模式：使用完整的特征工程器进行预测
    2. 简单模式：使用滞后窗口进行递归预测
    """
    
    def __init__(
        self,
        model,
        lag_features: int,
        use_feature_engineering: bool,
        feature_engineer,
        training_frequency: Optional[str],
        feature_names: Optional[list] = None
    ):
        """初始化包装器
        
        Args:
            model: 训练好的 GradientBoostingRegressor 模型
            lag_features: 滞后特征数量
            use_feature_engineering: 是否使用特征工程
            feature_engineer: TimeSeriesFeatureEngineer 对象（或 None）
            training_frequency: 训练时的时间序列频率（如 'MS', 'D'）
            feature_names: 特征名称列表（用于调试）
        """
        self.model = model
        self.lag_features = lag_features
        self.use_feature_engineering = use_feature_engineering
        self.feature_engineer = feature_engineer
        self.training_frequency = training_frequency
        self.feature_names = feature_names
    
    def predict(self, context, model_input) -> np.ndarray:
        """预测接口
        
        Args:
            context: MLflow context
            model_input: 字典格式 {'history': pd.Series, 'steps': int}
            
        Returns:
            预测结果数组
        """
        # 解析输入
        history, steps = self._parse_input(model_input)
        
        if self.use_feature_engineering and self.feature_engineer:
            return self._predict_with_feature_engineering(history, steps)
        else:
            return self._predict_simple(history, steps)
    
    def _parse_input(self, model_input) -> tuple[pd.Series, int]:
        """解析输入数据
        
        Args:
            model_input: 字典格式 {'history': pd.Series, 'steps': int}
            
        Returns:
            (history, steps) 元组
        """
        if isinstance(model_input, dict):
            history = model_input.get('history')
            steps = model_input.get('steps')
            
            if history is None or steps is None:
                raise ValueError("输入必须包含 'history' 和 'steps' 字段")
            
            if not isinstance(history, pd.Series):
                raise ValueError("'history' 必须是 pandas.Series 类型")
            
            return history, int(steps)
        else:
            raise ValueError("输入格式错误，需要 dict 类型")
    
    def _predict_with_feature_engineering(self, history: pd.Series, steps: int) -> np.ndarray:
        """使用特征工程的递归预测
        
        策略：维护完整的时间序列历史，每步预测后追加到历史，
        重新调用 feature_engineer.transform() 提取特征。
        
        Args:
            history: 历史时间序列数据
            steps: 预测步数
            
        Returns:
            预测结果数组
        """
        history = history.copy()
        predictions = []
        
        for step in range(steps):
            # 1. 从完整历史中提取特征
            try:
                X, _ = self.feature_engineer.transform(history)
            except Exception as e:
                logger.warning(f"特征提取失败（第{step+1}步）: {e}，回退到简单预测")
                # 回退到简单预测
                remaining = steps - step
                simple_preds = self._predict_simple(history, remaining)
                predictions.extend(simple_preds)
                break
            
            if len(X) == 0:
                logger.warning(f"第 {step+1} 步特征提取结果为空，停止预测")
                break
            
            # 2. 使用最后一行特征进行预测
            last_features = X.iloc[-1:].copy()
            pred = self.model.predict(last_features)[0]
            predictions.append(pred)
            
            # 3. 推断下一个时间步（基于频率）
            last_timestamp = history.index[-1]
            if isinstance(history.index, pd.DatetimeIndex):
                # 尝试使用频率推断
                if self.training_frequency:
                    try:
                        next_timestamp = last_timestamp + pd.tseries.frequencies.to_offset(self.training_frequency)
                    except:
                        # 频率解析失败，使用平均间隔
                        avg_delta = (history.index[-1] - history.index[-2])
                        next_timestamp = last_timestamp + avg_delta
                else:
                    # 无频率信息，使用平均间隔
                    avg_delta = (history.index[-1] - history.index[-2])
                    next_timestamp = last_timestamp + avg_delta
            else:
                # 非时间索引，简单递增
                next_timestamp = last_timestamp + 1
            
            # 4. 将预测值追加到历史（构造新的 Series）
            new_point = pd.Series([pred], index=[next_timestamp])
            history = pd.concat([history, new_point])
        
        return np.array(predictions)
    
    def _predict_simple(self, history: pd.Series, steps: int) -> np.ndarray:
        """简单滞后窗口预测
        
        Args:
            history: 历史时间序列数据
            steps: 预测步数
            
        Returns:
            预测结果数组
        """
        predictions = []
        current_window = history.values[-self.lag_features:].copy()
        
        for _ in range(steps):
            X = current_window[-self.lag_features:].reshape(1, -1)
            pred = self.model.predict(X)[0]
            predictions.append(pred)
            current_window = np.append(current_window[1:], pred)
        
        return np.array(predictions)
