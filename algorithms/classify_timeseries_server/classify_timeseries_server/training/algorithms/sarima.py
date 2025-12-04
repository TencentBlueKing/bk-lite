"""SARIMA 时间序列算法."""

from typing import Any, Dict, Union
import pandas as pd
import numpy as np
import mlflow
from statsmodels.tsa.statespace.sarimax import SARIMAX

from .base_algorithm import BaseTimeSeriesAlgorithm


class SARIMAWrapper(mlflow.pyfunc.PythonModel):
    """SARIMA 模型 MLflow 包装器."""
    
    def __init__(self, model, freq='D'):
        self.model = model
        self.freq = freq
    
    def predict(
        self, 
        context: mlflow.pyfunc.PythonModelContext, 
        model_input: Union[pd.DataFrame, int]
    ) -> np.ndarray:
        """
        预测接口.
        
        Args:
            context: MLflow context
            model_input: DataFrame with 'steps' column or int
            
        Returns:
            预测结果数组
        """
        if isinstance(model_input, pd.DataFrame):
            if 'steps' in model_input.columns:
                steps = int(model_input['steps'].iloc[0])
            else:
                steps = len(model_input)
        else:
            steps = int(model_input)
        
        forecast = self.model.forecast(steps=steps)
        return forecast.values if isinstance(forecast, pd.Series) else forecast


class SARIMAAlgorithm(BaseTimeSeriesAlgorithm):
    """SARIMA 算法实现."""
    
    @property
    def algorithm_name(self) -> str:
        return "SARIMA"
    
    def fit(self, train_data: pd.Series, hyperparams: Dict[str, Any]) -> Any:
        """
        训练 SARIMA 模型.
        
        Args:
            train_data: 训练数据（时间序列）
            hyperparams: 超参数，包含 order, seasonal_order, trend
            
        Returns:
            训练好的 SARIMAX 模型
        """
        order = tuple(hyperparams.get('order', [1, 1, 1]))
        seasonal_order = tuple(hyperparams.get('seasonal_order', [1, 1, 1, 12]))
        trend = hyperparams.get('trend', 'c')
        
        model = SARIMAX(
            train_data,
            order=order,
            seasonal_order=seasonal_order,
            trend=trend,
            enforce_stationarity=False,
            enforce_invertibility=False,
        )
        
        return model.fit(disp=False)
    
    def predict(self, model: Any, steps: int) -> np.ndarray:
        """
        SARIMA 预测.
        
        Args:
            model: SARIMAX 拟合模型
            steps: 预测步数
            
        Returns:
            预测结果数组
        """
        forecast = model.forecast(steps=steps)
        return forecast.values if isinstance(forecast, pd.Series) else forecast
    
    def get_model_wrapper(self, model: Any, freq: str):
        """
        获取 MLflow 包装器.
        
        Args:
            model: SARIMAX 模型
            freq: 时间频率
            
        Returns:
            SARIMAWrapper 实例
        """
        return SARIMAWrapper(model, freq=freq)
    
    def get_pip_requirements(self) -> list[str]:
        """
        SARIMA 依赖包.
        
        Returns:
            依赖包列表
        """
        import statsmodels
        import pandas as pd
        import numpy as np
        
        return [
            f"statsmodels=={statsmodels.__version__}",
            f"pandas=={pd.__version__}",
            f"numpy=={np.__version__}",
        ]
    
    def get_additional_metrics(self, model: Any) -> Dict[str, float]:
        """
        SARIMA 特有指标：AIC 和 BIC.
        
        Args:
            model: SARIMAX 模型
            
        Returns:
            包含 AIC 和 BIC 的字典
        """
        return {
            'aic': float(model.aic),
            'bic': float(model.bic),
        }
    
    def flatten_hyperparams(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        展平 SARIMA 超参数.
        
        将 order=[1,1,1] 展开为 order_p=1, order_d=1, order_q=1
        
        Args:
            config: 原始配置
            
        Returns:
            展平后的配置
        """
        flat = {}
        
        for k, v in config.items():
            if isinstance(v, (list, tuple)) and k == 'order':
                flat['order_p'] = v[0]
                flat['order_d'] = v[1]
                flat['order_q'] = v[2]
            elif isinstance(v, (list, tuple)) and k == 'seasonal_order':
                flat['seasonal_p'] = v[0]
                flat['seasonal_d'] = v[1]
                flat['seasonal_q'] = v[2]
                flat['seasonal_s'] = v[3]
            elif isinstance(v, (str, int, float, bool)):
                flat[k] = v
        
        return flat
