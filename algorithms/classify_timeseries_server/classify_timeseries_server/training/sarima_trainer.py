"""SARIMA 时间序列预测模型训练器 - 简化版本
"""

from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import pandas as pd
import numpy as np
import mlflow
from loguru import logger
from sklearn.metrics import mean_squared_error, mean_absolute_error
from statsmodels.tsa.statespace.sarimax import SARIMAX
import joblib
from hyperopt import fmin, tpe, hp, Trials, STATUS_OK

from .mlflow_utils import MLFlowUtils


class SARIMAWrapper(mlflow.pyfunc.PythonModel):
    """SARIMA 模型的 MLflow 包装器，用于部署"""
    
    def __init__(self, model, freq='D'):
        self.model = model
        self.freq = freq
    
    def predict(self, context: mlflow.pyfunc.PythonModelContext, model_input) -> np.ndarray:
        """预测接口
        
        Args:
            context: MLflow context
            model_input: DataFrame with 'steps' column or int
            
        Returns:
            预测结果数组
        """
        if isinstance(model_input, pd.DataFrame):
            steps = int(model_input['steps'].iloc[0]) if 'steps' in model_input.columns else len(model_input)
        else:
            steps = int(model_input)
        
        forecast = self.model.forecast(steps=steps)
        return forecast.values if isinstance(forecast, pd.Series) else forecast


class SARIMATrainer:
    """SARIMA 时间序列模型训练器
    
    提供完整的训练流程：数据预处理、模型训练、评估、MLflow 记录。
    支持可选的超参数优化。
    """
    
    def __init__(self):
        self.frequency = None
    
    def preprocess(
        self, 
        df: pd.DataFrame, 
        frequency: Optional[str] = None
    ) -> Tuple[pd.DataFrame, str]:
        """数据预处理：时间标准化、排序、缺失值填充
        
        Args:
            df: 包含 'date' 和 'value' 列的数据框
            frequency: 时间频率，如 'D', 'H', 'min' 等，None 则自动推断
            
        Returns:
            (处理后的数据框, 推断的频率)
        """
        if df is None or df.empty:
            return None, frequency
        
        df = df.copy()
        
        # 标准化时间列并排序
        if 'date' not in df.columns:
            raise ValueError("DataFrame must contain 'date' column")
        
        if not np.issubdtype(df["date"].dtype, np.datetime64):
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        
        df = df.dropna(subset=["date"]).sort_values("date")
        
        # 设置时间索引，推断频率
        df = df.set_index("date")
        if frequency is None:
            try:
                frequency = pd.infer_freq(df.index)
                if frequency:
                    logger.info(f"Inferred frequency: {frequency}")
            except Exception as e:
                logger.warning(f"Cannot infer frequency: {e}")
                frequency = None
        
        # 处理缺失值：时间插值 -> 前后填充 -> 中位数兜底
        if 'value' in df.columns:
            value_series = df["value"].astype(float)
            value_series = value_series.interpolate(method="time", limit_direction="both")
            value_series = value_series.ffill().bfill()
            
            if value_series.isna().any():
                median_value = value_series.median() if not np.isnan(value_series.median()) else 0.0
                value_series = value_series.fillna(median_value)
                logger.warning(f"Filled {value_series.isna().sum()} NaN values with median {median_value}")
            
            df["value"] = value_series
        
        df = df.reset_index()
        return df, frequency
    
    def fit_sarima(
        self,
        train_data: pd.Series,
        order: tuple = (1, 1, 1),
        seasonal_order: tuple = (1, 1, 1, 12),
        trend: str = 'c'
    ):
        """训练 SARIMA 模型
        
        Args:
            train_data: 训练数据时间序列
            order: ARIMA 参数 (p, d, q)
            seasonal_order: 季节性参数 (P, D, Q, s)
            trend: 趋势参数
            
        Returns:
            训练好的 SARIMAX 模型
        """
        model = SARIMAX(
            train_data,
            order=order,
            seasonal_order=seasonal_order,
            trend=trend,
            enforce_stationarity=False,
            enforce_invertibility=False,
        )
        
        return model.fit(disp=False)
    
    def predict(self, model, steps: int) -> np.ndarray:
        """使用模型进行预测
        
        Args:
            model: 训练好的 SARIMAX 模型
            steps: 预测步数
            
        Returns:
            预测结果数组
        """
        forecast = model.forecast(steps=steps)
        return forecast.values if isinstance(forecast, pd.Series) else forecast
    
    def calculate_metrics(self, y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
        """计算评估指标
        
        Args:
            y_true: 真实值
            y_pred: 预测值
            
        Returns:
            包含 MSE, RMSE, MAE, MAPE 的字典
        """
        mse = mean_squared_error(y_true, y_pred)
        rmse = np.sqrt(mse)
        mae = mean_absolute_error(y_true, y_pred)
        
        # 计算 MAPE，避免除零错误
        mape_values = np.abs((y_true - y_pred) / y_true)
        mape_values = mape_values[np.isfinite(mape_values)]
        mape = np.mean(mape_values) * 100 if len(mape_values) > 0 else 0.0
        
        return {
            'mse': float(mse),
            'rmse': float(rmse),
            'mae': float(mae),
            'mape': float(mape),
        }
    
    def save_prediction_plot(self, y_true: np.ndarray, y_pred: np.ndarray, rmse: float):
        """保存预测对比图表
        
        Args:
            y_true: 真实值
            y_pred: 预测值
            rmse: RMSE 指标
        """
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            
            plot_index = range(len(y_true))
            
            plt.figure(figsize=(12, 6))
            plt.plot(plot_index, y_true, label='Actual', marker='o', markersize=3, alpha=0.7)
            plt.plot(plot_index, y_pred, label='Predicted', marker='x', markersize=3, alpha=0.7)
            plt.xlabel('Time Steps')
            plt.ylabel('Value')
            plt.title(f'SARIMA Predictions vs Actual (RMSE: {rmse:.2f})')
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.tight_layout()
            
            plot_path = Path('predictions_plot.png')
            plt.savefig(plot_path, dpi=100)
            MLFlowUtils.log_artifact(str(plot_path))
            plot_path.unlink()
            plt.close()
            
            logger.info("Prediction plot saved to MLflow")
        except Exception as e:
            logger.warning(f"Failed to create plot: {e}")
    
    def optimize_hyperparams(
        self,
        train_data: pd.Series,
        val_data: pd.Series,
        max_evals: int = 50,
        metric: str = "rmse"
    ) -> Dict[str, Any]:
        """使用 Hyperopt 优化 SARIMA 超参数
        
        Args:
            train_data: 训练数据
            val_data: 验证数据
            max_evals: 最大评估次数
            metric: 优化目标指标 (rmse/mae/mape)
            
        Returns:
            最优超参数字典
        """
        logger.info(f"Starting hyperparameter optimization, max_evals={max_evals}, metric={metric}")
        
        # 定义搜索空间 - 只针对 SARIMA 实际需要的参数
        space = {
            'p': hp.randint('p', 3),  # 0-2
            'd': hp.randint('d', 3),  # 0-2
            'q': hp.randint('q', 3),  # 0-2
            'P': hp.randint('P', 3),  # 0-2
            'D': hp.randint('D', 2),  # 0-1
            'Q': hp.randint('Q', 3),  # 0-2
            's': hp.choice('s', [12, 24, 7]),  # 常见周期
            'trend': hp.choice('trend', ['n', 'c', 't', 'ct']),
        }
        
        trials = Trials()
        best_score = float('inf')
        
        def objective(params):
            nonlocal best_score
            try:
                # 构建参数
                order = (int(params['p']), int(params['d']), int(params['q']))
                seasonal_order = (int(params['P']), int(params['D']), int(params['Q']), int(params['s']))
                trend = params['trend']
                
                # 训练模型
                model = self.fit_sarima(train_data, order, seasonal_order, trend)
                
                # 验证集预测
                predictions = self.predict(model, len(val_data))
                val_values = val_data.values
                
                # 计算指标
                metrics = self.calculate_metrics(val_values, predictions)
                score = metrics.get(metric, metrics['rmse'])
                
                # 记录进度
                if score < best_score:
                    best_score = score
                    logger.info(f"New best {metric}: {score:.4f} - order={order}, seasonal={seasonal_order}, trend={trend}")
                
                return {'loss': float(score), 'status': STATUS_OK}
                
            except Exception as e:
                logger.debug(f"Hyperparameter evaluation failed: {e}")
                return {'loss': float('inf'), 'status': STATUS_OK}
        
        # 运行优化
        best_params_raw = fmin(
            fn=objective,
            space=space,
            algo=tpe.suggest,
            max_evals=max_evals,
            trials=trials,
            rstate=np.random.default_rng(2025),
            verbose=False
        )
        
        # 转换最优参数
        best_params = {
            'order': (int(best_params_raw['p']), int(best_params_raw['d']), int(best_params_raw['q'])),
            'seasonal_order': (
                int(best_params_raw['P']), 
                int(best_params_raw['D']), 
                int(best_params_raw['Q']), 
                [12, 24, 7][best_params_raw['s']]
            ),
            'trend': ['n', 'c', 't', 'ct'][best_params_raw['trend']],
        }
        
        logger.info(f"Optimization complete. Best {metric}: {best_score:.4f}")
        logger.info(f"Best params: {best_params}")
        
        return best_params
    
    def train(
        self,
        model_name: str,
        train_dataframe: pd.DataFrame,
        val_dataframe: Optional[pd.DataFrame] = None,
        test_dataframe: Optional[pd.DataFrame] = None,
        order: tuple = (1, 1, 1),
        seasonal_order: tuple = (1, 1, 1, 12),
        trend: str = 'c',
        mlflow_tracking_uri: Optional[str] = None,
        experiment_name: str = "timeseries_sarima",
        test_size: float = 0.2,
        max_evals: int = 0,
        optimization_metric: str = "rmse",
        **kwargs
    ) -> Dict[str, Any]:
        """训练 SARIMA 模型的完整流程
        
        Args:
            model_name: 模型名称，用于 MLflow 注册
            train_dataframe: 训练数据，包含 'date' 和 'value' 列
            val_dataframe: 验证数据（可选，用于超参数优化）
            test_dataframe: 测试数据（可选，如果没有则从训练数据分割）
            order: ARIMA 参数 (p, d, q)，默认 (1, 1, 1)
            seasonal_order: 季节性参数 (P, D, Q, s)，默认 (1, 1, 1, 12)
            trend: 趋势参数，默认 'c'
            mlflow_tracking_uri: MLflow tracking 服务地址
            experiment_name: MLflow 实验名称
            test_size: 测试集比例，当 test_dataframe 为 None 时使用
            max_evals: 超参数优化轮次，0 表示不优化，使用提供的参数
            optimization_metric: 优化目标指标 (rmse/mae/mape)
            **kwargs: 其他参数（保留扩展性）
            
        Returns:
            训练结果字典，包含:
            - model: 训练好的模型
            - test_metrics: 测试集指标
            - val_metrics: 验证集指标（如果有）
            - run_id: MLflow run ID
            - frequency: 推断的时间频率
            - best_params: 最优参数（如果进行了优化）
        """
        logger.info("=" * 60)
        logger.info("Starting SARIMA model training")
        logger.info("=" * 60)
        
        # 设置 MLflow
        MLFlowUtils.setup_experiment(mlflow_tracking_uri, experiment_name)
        
        # 数据预处理
        logger.info("Preprocessing training data...")
        train_df_prep, frequency = self.preprocess(train_dataframe, None)
        self.frequency = frequency
        
        ts = train_df_prep.set_index('date')['value']
        
        # 处理验证集
        val_data = None
        if val_dataframe is not None and not val_dataframe.empty:
            val_df_prep, _ = self.preprocess(val_dataframe, frequency)
            val_data = val_df_prep.set_index('date')['value']
            logger.info(f"Validation set size: {len(val_data)}")
        
        # 处理测试集
        if test_dataframe is not None and not test_dataframe.empty:
            test_df_prep, _ = self.preprocess(test_dataframe, frequency)
            test_data = test_df_prep.set_index('date')['value']
            train_data = ts
        else:
            split_point = int(len(ts) * (1 - test_size))
            train_data = ts[:split_point]
            test_data = ts[split_point:]
        
        logger.info(f"Train size: {len(train_data)}, Test size: {len(test_data)}")
        
        # 超参数优化（如果需要）
        final_params = {'order': order, 'seasonal_order': seasonal_order, 'trend': trend}
        
        if max_evals > 0:
            logger.info(f"Hyperparameter optimization enabled (max_evals={max_evals})")
            
            # 准备验证集
            if val_data is None:
                # 从训练集分割
                val_split = int(len(train_data) * 0.8)
                opt_train_data = train_data[:val_split]
                opt_val_data = train_data[val_split:]
                logger.info(f"Split validation set: train={len(opt_train_data)}, val={len(opt_val_data)}")
            else:
                opt_train_data = train_data
                opt_val_data = val_data
            
            # 优化超参数
            final_params = self.optimize_hyperparams(
                opt_train_data,
                opt_val_data,
                max_evals,
                optimization_metric
            )
        else:
            logger.info(f"Using provided parameters: order={order}, seasonal={seasonal_order}, trend={trend}")
        
        # 开始 MLflow run
        with mlflow.start_run() as run:
            # 记录参数
            params = {
                'algorithm': 'SARIMA',
                'train_size': len(train_data),
                'test_size': len(test_data),
                'frequency': frequency or 'unknown',
                'order_p': final_params['order'][0],
                'order_d': final_params['order'][1],
                'order_q': final_params['order'][2],
                'seasonal_p': final_params['seasonal_order'][0],
                'seasonal_d': final_params['seasonal_order'][1],
                'seasonal_q': final_params['seasonal_order'][2],
                'seasonal_s': final_params['seasonal_order'][3],
                'trend': final_params['trend'],
                'max_evals': max_evals,
                'optimization_enabled': max_evals > 0,
            }
            if max_evals > 0:
                params['optimization_metric'] = optimization_metric
            
            logger.info(f"Model parameters: {params}")
            MLFlowUtils.log_params_batch(params)
            
            # 训练模型
            logger.info("Fitting SARIMA model...")
            try:
                fitted_model = self.fit_sarima(
                    train_data,
                    final_params['order'],
                    final_params['seasonal_order'],
                    final_params['trend']
                )
                logger.info("Model fitting completed successfully")
            except Exception as e:
                logger.error(f"Model fitting failed: {e}")
                raise
            
            # 测试集预测和评估
            logger.info("Generating predictions on test set...")
            test_predictions = self.predict(fitted_model, len(test_data))
            test_values = test_data.values
            test_metrics = self.calculate_metrics(test_values, test_predictions)
            
            # 添加 SARIMA 特有指标
            test_metrics['aic'] = float(fitted_model.aic)
            test_metrics['bic'] = float(fitted_model.bic)
            
            logger.info(f"Test metrics: RMSE={test_metrics['rmse']:.4f}, "
                       f"MAE={test_metrics['mae']:.4f}, MAPE={test_metrics['mape']:.2f}%")
            logger.info(f"Model selection: AIC={test_metrics['aic']:.2f}, BIC={test_metrics['bic']:.2f}")
            MLFlowUtils.log_metrics_batch(test_metrics, prefix="test_")
            
            # 验证集评估（如果有）
            val_metrics = {}
            if val_data is not None:
                logger.info("Evaluating on validation set...")
                val_predictions = self.predict(fitted_model, len(val_data))
                val_values = val_data.values
                val_metrics = self.calculate_metrics(val_values, val_predictions)
                logger.info(f"Validation metrics: RMSE={val_metrics['rmse']:.4f}, "
                           f"MAE={val_metrics['mae']:.4f}, MAPE={val_metrics['mape']:.2f}%")
                MLFlowUtils.log_metrics_batch(val_metrics, prefix="val_")
            
            # 保存图表
            self.save_prediction_plot(test_values, test_predictions, test_metrics['rmse'])
            
            # 保存模型到 MLflow
            logger.info("Saving model to MLflow...")
            wrapped_model = SARIMAWrapper(fitted_model, frequency or 'D')
            
            import statsmodels
            pip_requirements = [
                f"statsmodels=={statsmodels.__version__}",
                f"pandas=={pd.__version__}",
                f"numpy=={np.__version__}",
            ]
            
            MLFlowUtils.log_model(
                model=wrapped_model,
                artifact_path="model",
                registered_model_name=model_name,
                pip_requirements=pip_requirements,
            )
            
            # 额外保存原始模型
            model_path = Path('model.pkl')
            try:
                joblib.dump(fitted_model, model_path)
                MLFlowUtils.log_artifact(str(model_path))
            finally:
                if model_path.exists():
                    model_path.unlink()
            
            run_id = run.info.run_id
            logger.info(f"Model saved successfully. Run ID: {run_id}")
            
            if model_name:
                logger.info(f"Model registered as: {model_name}")
        
        logger.info("=" * 60)
        logger.info("Training completed successfully")
        logger.info("=" * 60)
        
        return {
            "model": fitted_model,
            "test_metrics": test_metrics,
            "val_metrics": val_metrics,
            "run_id": run_id,
            "frequency": frequency,
            "best_params": final_params,
        }
