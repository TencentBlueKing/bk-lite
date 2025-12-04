"""通用时间序列模型训练器."""

from pathlib import Path
from typing import Dict, Any, Optional, Callable
import pandas as pd
import numpy as np
import mlflow
from loguru import logger
from sklearn.metrics import mean_squared_error, mean_absolute_error
import joblib
from hyperopt import fmin, tpe, hp, Trials, space_eval, STATUS_OK

from .base_model import BaseTimeSeriesModel
from .mlflow_utils import MLFlowUtils
from .algorithms.base_algorithm import BaseTimeSeriesAlgorithm


class TimeSeriesTrainer(BaseTimeSeriesModel):
    """
    通用时间序列训练器.
    
    通过组合模式注入具体算法实现，实现算法可插拔.
    """
    
    def __init__(self, algorithm: BaseTimeSeriesAlgorithm):
        """
        初始化训练器.
        
        Args:
            algorithm: 具体算法实现（SARIMA、Prophet、LSTM 等）
        """
        super().__init__()
        self.algorithm = algorithm
    
    def build_model(self, train_params: dict):
        """构建模型（委托给算法实现）."""
        return train_params
    
    def train(
        self,
        model_name: str,
        train_dataframe: pd.DataFrame,
        val_dataframe: Optional[pd.DataFrame] = None,
        test_dataframe: Optional[pd.DataFrame] = None,
        train_config: dict = {},
        mlflow_tracking_uri: Optional[str] = None,
        experiment_name: str = "timeseries_training",
        test_size: float = 0.2,
        max_evals: int = 0,
        optimization_metric: str = "rmse",
        **kwargs
    ) -> Dict[str, Any]:
        """
        通用训练流程.
        
        核心逻辑：
        1. 数据预处理（通用）
        2. 超参数优化（可选，根据 max_evals 和 train_config）
        3. 模型训练（委托给算法）
        4. 评估预测（通用）
        5. MLflow 记录（通用）
        
        Args:
            model_name: 模型名称
            train_dataframe: 训练数据,包含 'date' 和 'value' 列
            val_dataframe: 验证数据（可选，用于超参数优化和验证集评估）
            test_dataframe: 测试数据（可选，如果没有则从训练数据分割）
            train_config: 训练配置，支持固定值或搜索空间定义
                - 固定值模式: {"order": [1,1,1], "seasonal_order": [1,1,1,12]}
                - 搜索空间模式: {"order_p": {"type": "randint", "min": 0, "max": 2}, ...}
            mlflow_tracking_uri: MLflow tracking 地址
            experiment_name: 实验名称
            test_size: 测试集比例
            max_evals: 超参数优化轮次 (0=不优化，使用固定值; >0=从train_config构建搜索空间)
            optimization_metric: 优化目标指标 (rmse/mae/mape)
            **kwargs: 其他参数
            
        Returns:
            训练结果字典，包含 model, test_metrics, run_id, frequency, best_params
        """
        logger.info(f"🚀 开始训练 {self.algorithm.algorithm_name} 模型")
        
        # 设置 MLflow
        MLFlowUtils.setup_experiment(mlflow_tracking_uri, experiment_name)
        
        # 数据预处理(通用逻辑)
        logger.info("📊 数据预处理中...")
        train_df_prep, frequency = self.preprocess(train_dataframe, None)
        self.frequency = frequency
        
        ts = train_df_prep.set_index('date')['value']
        
        # 处理验证集
        val_data = None
        if val_dataframe is not None and not val_dataframe.empty:
            val_df_prep, _ = self.preprocess(val_dataframe, frequency)
            val_data = val_df_prep.set_index('date')['value']
            logger.info(f"验证集大小: {len(val_data)}")
        
        # 分割数据（通用逻辑）
        if test_dataframe is not None and not test_dataframe.empty:
            test_df_prep, _ = self.preprocess(test_dataframe, frequency)
            test_data = test_df_prep.set_index('date')['value']
            train_data = ts
        else:
            split_point = int(len(ts) * (1 - test_size))
            train_data = ts[:split_point]
            test_data = ts[split_point:]
        
        logger.info(f"训练集大小: {len(train_data)}, 测试集大小: {len(test_data)}")
        
        # 超参数优化（根据 max_evals 和 train_config 判断）
        best_config = train_config
        optimization_history = []
        enable_hyperparam_tuning = max_evals > 0
        
        if enable_hyperparam_tuning:
            # 从 train_config 构建搜索空间
            hyperparam_space = self._build_search_space_from_config(train_config)
            
            if not hyperparam_space:
                logger.warning(f"max_evals={max_evals} 但 train_config 不包含搜索范围定义，将使用固定值")
                enable_hyperparam_tuning = False
            else:
                logger.info(f"🔍 开始超参数优化，最大评估次数: {max_evals}, 优化指标: {optimization_metric}")
                logger.info(f"搜索空间参数: {list(hyperparam_space.keys())}")
                
                # 如果没有验证集，从训练集分割
                opt_val_data = val_data
                if opt_val_data is None:
                    val_split = int(len(train_data) * 0.8)
                    opt_train_data = train_data[:val_split]
                    opt_val_data = train_data[val_split:]
                    logger.info(f"从训练集分割验证集: 训练 {len(opt_train_data)}, 验证 {len(opt_val_data)}")
                else:
                    opt_train_data = train_data
                
                best_config, optimization_history = self._tune_hyperparams(
                    opt_train_data,
                    opt_val_data,
                    train_config,
                    hyperparam_space,
                    max_evals,
                    optimization_metric
                )
                
                logger.info(f"✅ 超参数优化完成，最优配置: {best_config}")
        else:
            logger.info(f"跳过超参数优化 (max_evals={max_evals})，使用提供的 train_config")
        
        # 开始 MLflow run
        with mlflow.start_run() as run:
            # 记录通用参数
            params = {
                'algorithm': self.algorithm.algorithm_name,
                'train_size': len(train_data),
                'test_size': len(test_data),
                'frequency': frequency or 'unknown',
            }
            
            # 添加算法特定的超参数（展平处理）
            flattened_params = self.algorithm.flatten_hyperparams(best_config)
            params.update(flattened_params)
            
            # 添加优化相关参数
            params.update({
                'max_evals': max_evals,
                'optimization_enabled': enable_hyperparam_tuning,
            })
            if enable_hyperparam_tuning:
                params['optimization_metric'] = optimization_metric
            
            logger.info(f"{self.algorithm.algorithm_name} 参数: {flattened_params}")
            MLFlowUtils.log_params_batch(params)
            
            # 训练模型(委托给算法实现，使用最优配置)
            logger.info(f"🔧 拟合 {self.algorithm.algorithm_name} 模型中...")
            try:
                fitted_model = self.algorithm.fit(train_data, best_config)
                logger.info("✅ 模型拟合成功")
            except Exception as e:
                logger.error(f"❌ 模型拟合失败: {e}")
                raise
            
            # 预测(委托给算法实现)
            logger.info("📈 生成预测结果中...")
            predictions = self.algorithm.predict(fitted_model, len(test_data))
            
            # 评估验证集（如果存在）
            val_metrics = {}
            if val_data is not None:
                logger.info("📊 验证集评估中...")
                val_predictions = self.algorithm.predict(fitted_model, len(val_data))
                val_values = val_data.values if isinstance(val_data, pd.Series) else val_data
                val_metrics = self._calculate_metrics(val_values, val_predictions)
                logger.info(f"📊 验证集指标: {val_metrics}")
                MLFlowUtils.log_metrics_batch(val_metrics, prefix="val_")
            
            # 评估（通用逻辑）
            test_values = test_data.values if isinstance(test_data, pd.Series) else test_data
            test_metrics = self._calculate_metrics(test_values, predictions)
            
            # 算法特定指标
            additional_metrics = self.algorithm.get_additional_metrics(fitted_model)
            test_metrics.update(additional_metrics)
            
            logger.info(f"📊 测试指标: {test_metrics}")
            MLFlowUtils.log_metrics_batch(test_metrics, prefix="test_")
            
            # 保存图表(通用逻辑)
            self._save_prediction_plot(test_values, predictions, test_metrics['rmse'])
            
            # 保存模型(算法提供包装器)
            logger.info("💾 保存模型到 MLflow...")
            wrapped_model = self.algorithm.get_model_wrapper(fitted_model, frequency or 'D')
            
            MLFlowUtils.log_model(
                model=wrapped_model,
                artifact_path="model",
                registered_model_name=model_name,
                pip_requirements=self.algorithm.get_pip_requirements(),
            )
            
            # 额外保存原始模型
            model_path = Path('model.pkl')
            try:
                joblib.dump(fitted_model, model_path)
                MLFlowUtils.log_artifact(str(model_path))
            finally:
                # 确保清理临时文件
                if model_path.exists():
                    model_path.unlink()
            
            run_id = run.info.run_id
            logger.info(f"✅ 模型保存成功. Run ID: {run_id}")
            
            if model_name:
                logger.info(f"✅ 模型已注册为: {model_name}")
        
        return {
            "model": fitted_model,
            "test_metrics": test_metrics,
            "val_metrics": val_metrics,
            "run_id": run_id,
            "frequency": frequency,
            "best_params": best_config,
            "optimization_history": optimization_history,
        }
    
    def _tune_hyperparams(
        self,
        train_data: pd.Series,
        val_data: pd.Series,
        base_config: Dict[str, Any],
        hyperparam_space: Dict,
        max_evals: int = 50,
        optimization_metric: str = "rmse"
    ) -> tuple[Dict[str, Any], list]:
        """
        使用 Hyperopt 进行超参数优化.
        
        Args:
            train_data: 训练数据
            val_data: 验证数据
            base_config: 基础配置（固定值参数）
            hyperparam_space: 超参数搜索空间
            max_evals: 最大评估次数
            optimization_metric: 优化指标
            
        Returns:
            (最优配置, 优化历史)
        """
        trials = Trials()
        history = []
        
        def objective(params_raw):
            """优化目标函数"""
            try:
                # 评估超参数
                params = space_eval(hyperparam_space, params_raw)
                
                # 合并搜索参数和固定参数
                full_params = {}
                for k, v in base_config.items():
                    if not k.startswith('_') and not isinstance(v, dict):
                        full_params[k] = v
                full_params.update(params)
                
                # 训练模型
                model = self.algorithm.fit(train_data, full_params)
                
                # 验证集预测
                val_predictions = self.algorithm.predict(model, len(val_data))
                val_values = val_data.values if isinstance(val_data, pd.Series) else val_data
                
                # 计算目标指标
                metrics = self._calculate_metrics(val_values, val_predictions)
                score = metrics.get(optimization_metric, metrics['rmse'])
                
                # 记录历史
                history.append({
                    'params': full_params,
                    'score': score,
                    'metrics': metrics
                })
                
                # 定期日志
                if len(history) % 10 == 0:
                    logger.info(f"第 {len(history)} 次评估 - {optimization_metric}: {score:.4f}")
                
                # Hyperopt 最小化 loss
                return {
                    'loss': float(score),
                    'status': STATUS_OK,
                    'params': full_params
                }
                
            except Exception as e:
                logger.warning(f"超参数评估失败: {e}")
                return {
                    'loss': float('inf'),
                    'status': STATUS_OK
                }
        
        # 运行优化
        best_params_raw = fmin(
            fn=objective,
            space=hyperparam_space,
            algo=tpe.suggest,
            max_evals=max_evals,
            trials=trials,
            rstate=np.random.default_rng(2025),
            verbose=False
        )
        
        best_params = space_eval(hyperparam_space, best_params_raw)
        
        # 合并固定参数
        full_best_params = {}
        for k, v in base_config.items():
            if not k.startswith('_') and not isinstance(v, dict):
                full_best_params[k] = v
        full_best_params.update(best_params)
        
        # 找到最优结果
        best_result = min(history, key=lambda x: x['score'])
        logger.info(f"最优 {optimization_metric}: {best_result['score']:.4f}")
        
        return full_best_params, history
    
    def _build_search_space_from_config(self, train_config: Dict[str, Any]) -> Optional[Dict]:
        """
        从训练配置构建 Hyperopt 搜索空间.
        
        支持的配置格式:
        1. 固定值: {"order": [1, 1, 1], "trend": "c"}
        2. 搜索范围: {"order_p": {"type": "randint", "min": 0, "max": 2}}
        
        Args:
            train_config: 训练配置字典
            
        Returns:
            Hyperopt 搜索空间字典，如果不包含搜索范围则返回 None
        """
        space = {}
        has_search_space = False
        
        for key, value in train_config.items():
            # 跳过注释和模式字段
            if key.startswith('_'):
                continue
            
            # 如果是字典且包含 type 字段，说明是搜索范围定义
            if isinstance(value, dict) and 'type' in value:
                has_search_space = True
                param_type = str(value.get('type', '')).lower()
                
                if param_type == 'randint':
                    vmin = int(value['min'])
                    vmax = int(value['max'])
                    space[key] = hp.randint(key, vmax - vmin + 1) + vmin
                    
                elif param_type == 'uniform':
                    vmin = float(value['min'])
                    vmax = float(value['max'])
                    space[key] = hp.uniform(key, vmin, vmax)
                    
                elif param_type == 'loguniform':
                    vmin = float(value['min'])
                    vmax = float(value['max'])
                    space[key] = hp.loguniform(key, np.log(vmin), np.log(vmax))
                    
                elif param_type == 'choice':
                    choices = value.get('choice', value.get('choices', []))
                    # 处理字符串转换
                    processed_choices = []
                    for c in choices:
                        if isinstance(c, str):
                            lc = c.strip().lower()
                            if lc == 'none':
                                processed_choices.append(None)
                            elif lc == 'true':
                                processed_choices.append(True)
                            elif lc == 'false':
                                processed_choices.append(False)
                            else:
                                processed_choices.append(c)
                        else:
                            processed_choices.append(c)
                    space[key] = hp.choice(key, processed_choices)
                    
                elif param_type == 'choice_list':
                    # 支持列表选择，如 [[0,1,0], [1,1,1], [2,1,2]]
                    choices = value.get('choices', [])
                    space[key] = hp.choice(key, [tuple(c) if isinstance(c, list) else c for c in choices])
                    
                else:
                    logger.warning(f"不支持的参数类型: {param_type} for {key}")
            
            # 否则是固定值，不添加到搜索空间
        
        if not has_search_space:
            return None
        
        logger.info(f"从配置构建搜索空间: {list(space.keys())}")
        return space
    
    def _calculate_metrics(self, y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
        """
        计算通用评估指标.
        
        Args:
            y_true: 真实值
            y_pred: 预测值
            
        Returns:
            指标字典
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
    
    def _save_prediction_plot(self, y_true: np.ndarray, y_pred: np.ndarray, rmse: float):
        """
        保存预测图表.
        
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
            plt.title(f'{self.algorithm.algorithm_name} Predictions vs Actual (RMSE: {rmse:.2f})')
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.tight_layout()
            
            plot_path = Path('predictions_plot.png')
            plt.savefig(plot_path, dpi=100)
            MLFlowUtils.log_artifact(str(plot_path))
            plot_path.unlink()
            plt.close()
            
            logger.info("📊 预测图表已保存")
        except Exception as e:
            logger.warning(f"⚠️  创建图表失败: {e}")
