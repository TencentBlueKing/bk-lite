"""SARIMA 时间序列预测模型

从 sarima_trainer.py 迁移并重构的 SARIMA 模型实现。
"""

from typing import Dict, Any, Optional
import pandas as pd
import numpy as np
import mlflow
from loguru import logger
from statsmodels.tsa.statespace.sarimax import SARIMAX
from hyperopt import fmin, tpe, hp, Trials, STATUS_OK
import warnings

from .base import BaseTimeSeriesModel, ModelRegistry


class SARIMAWrapper(mlflow.pyfunc.PythonModel):
    """SARIMA 模型的 MLflow 包装器
    
    用于 MLflow 模型部署和服务化。
    """
    
    def __init__(self, model, freq='D'):
        """初始化包装器
        
        Args:
            model: 训练好的 SARIMAX 模型
            freq: 时间频率
        """
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


@ModelRegistry.register("sarima")
class SARIMAModel(BaseTimeSeriesModel):
    """SARIMA 时间序列预测模型
    
    实现了 BaseTimeSeriesModel 接口，支持：
    - 模型训练和预测
    - 超参数优化
    - 模型评估
    - MLflow 集成
    
    参数说明：
    - order: (p, d, q) - AR阶数, 差分阶数, MA阶数
    - seasonal_order: (P, D, Q, s) - 季节性AR, 季节性差分, 季节性MA, 季节周期
    - trend: 趋势参数 ('n', 'c', 't', 'ct')
    """
    
    def __init__(self,
                 order: tuple = (1, 1, 1),
                 seasonal_order: tuple = (1, 1, 1, 12),
                 trend: str = 'c',
                 **kwargs):
        """初始化 SARIMA 模型
        
        Args:
            order: ARIMA 参数 (p, d, q)
            seasonal_order: 季节性参数 (P, D, Q, s)
            trend: 趋势参数
            **kwargs: 其他参数
        """
        super().__init__(
            order=order,
            seasonal_order=seasonal_order,
            trend=trend,
            **kwargs
        )
        self.order = tuple(order)
        self.seasonal_order = tuple(seasonal_order)
        self.trend = trend
        
        logger.debug(
            f"SARIMA 模型初始化: order={self.order}, "
            f"seasonal_order={self.seasonal_order}, trend={self.trend}"
        )
    
    def fit(self,
            train_data: pd.Series,
            val_data: Optional[pd.Series] = None,
            **kwargs) -> 'SARIMAModel':
        """训练 SARIMA 模型
        
        Args:
            train_data: 训练数据（带 DatetimeIndex 的 Series）
            val_data: 验证数据（可选，未使用）
            **kwargs: 其他训练参数
            
        Returns:
            self: 训练后的模型实例
            
        Raises:
            ValueError: 数据格式不正确
        """
        if not isinstance(train_data, pd.Series):
            raise ValueError("train_data 必须是 pandas.Series")
        
        if not isinstance(train_data.index, pd.DatetimeIndex):
            logger.warning("train_data 索引不是 DatetimeIndex，频率信息可能丢失")
        
        logger.info(
            f"开始训练 SARIMA 模型: "
            f"order={self.order}, seasonal={self.seasonal_order}, trend={self.trend}"
        )
        logger.info(f"训练数据: {len(train_data)} 个数据点")
        
        # 存储频率信息
        if isinstance(train_data.index, pd.DatetimeIndex):
            try:
                self.frequency = pd.infer_freq(train_data.index)
            except:
                self.frequency = None
        
        # 创建并训练 SARIMAX 模型
        try:
            sarimax_model = SARIMAX(
                train_data,
                order=self.order,
                seasonal_order=self.seasonal_order,
                trend=self.trend,
                enforce_stationarity=False,
                enforce_invertibility=False,
            )
            
            # 抑制收敛警告
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore', category=Warning)
                self.model = sarimax_model.fit(disp=False, maxiter=100)
            
            self.is_fitted = True
            logger.info("SARIMA 模型训练完成")
            
            return self
            
        except Exception as e:
            logger.error(f"SARIMA 模型训练失败: {e}")
            raise
    
    def predict(self, steps: int) -> np.ndarray:
        """预测未来N步
        
        Args:
            steps: 预测步数
            
        Returns:
            预测结果数组
            
        Raises:
            RuntimeError: 模型未训练
        """
        self._check_fitted()
        
        if steps <= 0:
            raise ValueError(f"预测步数必须大于0，当前值: {steps}")
        
        logger.debug(f"预测未来 {steps} 步")
        
        forecast = self.model.forecast(steps=steps)
        result = forecast.values if isinstance(forecast, pd.Series) else forecast
        
        return result
    
    def evaluate(self, test_data: pd.Series) -> Dict[str, float]:
        """评估模型性能
        
        Args:
            test_data: 测试数据（带 DatetimeIndex 的 Series）
            
        Returns:
            评估指标字典 {"rmse": ..., "mae": ..., "mape": ...}
            
        Raises:
            RuntimeError: 模型未训练
        """
        self._check_fitted()
        
        if not isinstance(test_data, pd.Series):
            raise ValueError("test_data 必须是 pandas.Series")
        
        # 预测
        steps = len(test_data)
        predictions = self.predict(steps)
        
        # 计算指标
        y_true = test_data.values
        metrics = self._calculate_metrics(y_true, predictions)
        
        logger.info(
            f"模型评估完成: RMSE={metrics['rmse']:.4f}, "
            f"MAE={metrics['mae']:.4f}, MAPE={metrics['mape']:.2f}%"
        )
        
        return metrics
    
    def optimize_hyperparams(
        self,
        train_data: pd.Series,
        val_data: pd.Series,
        config: Any
    ) -> Dict[str, Any]:
        """优化 SARIMA 超参数
        
        使用 Hyperopt 进行贝叶斯优化。
        
        Args:
            train_data: 训练数据
            val_data: 验证数据
            config: 训练配置对象（包含搜索空间和优化设置）
            
        Returns:
            最优超参数字典
        """
        max_evals = config.hyperopt_max_evals
        metric = config.hyperopt_metric
        search_space_config = config.get("hyperparams", "search", "search_space")
        
        # ✨ 获取早停配置
        early_stop_config = config.get("hyperparams", "search", "early_stopping")
        early_stop_enabled = early_stop_config.get("enabled", False) if early_stop_config else False
        min_evals = early_stop_config.get("min_evals", 20) if early_stop_config else 20
        patience = early_stop_config.get("patience", 15) if early_stop_config else 15
        min_improvement_pct = early_stop_config.get("min_improvement_pct", 1.0) if early_stop_config else 1.0
        
        logger.info(
            f"开始超参数优化: max_evals={max_evals}, metric={metric}"
        )
        if early_stop_enabled:
            logger.info(
                f"早停机制: 启用 (min_evals={min_evals}, patience={patience}, "
                f"min_improvement={min_improvement_pct}%)"
            )
        
        # ✨ 计算动态上限值（用于截断异常 loss）
        # 使用训练数据标准差的 5 倍作为合理上限
        data_std = train_data.std()
        cap_value = data_std * 5
        logger.info(f"Loss 上限阈值: {cap_value:.2f} (基于数据标准差 {data_std:.2f})")
        
        # 定义搜索空间
        space = self._build_search_space(search_space_config)
        
        # 优化状态跟踪
        trials = Trials()
        best_score = [float('inf')]
        eval_count = [0]
        failed_count = [0]  # 失败计数器
        
        # ✨ 早停状态跟踪
        no_improvement_count = [0]
        early_stopped = [False]
        stop_reason = [""]
        
        def objective(params):
            eval_count[0] += 1
            current_eval = eval_count[0]
            
            try:
                # 构建参数
                order = (int(params['p']), int(params['d']), int(params['q']))
                seasonal_order = (
                    int(params['P']),
                    int(params['D']),
                    int(params['Q']),
                    int(params['s'])
                )
                trend = params['trend']
                
                logger.debug(
                    f"  [{current_eval}/{max_evals}] 尝试参数: "
                    f"order={order}, seasonal={seasonal_order}, trend={trend}"
                )
                
                # 创建临时模型并训练
                temp_model = SARIMAModel(
                    order=order,
                    seasonal_order=seasonal_order,
                    trend=trend
                )
                
                with warnings.catch_warnings():
                    warnings.filterwarnings('ignore')
                    temp_model.fit(train_data)
                
                # 验证集评估
                metrics = temp_model.evaluate(val_data)
                score = metrics.get(metric, metrics['rmse'])
                
                logger.debug(
                    f"  [{current_eval}/{max_evals}] {metric}={score:.4f}, "
                    f"RMSE={metrics['rmse']:.4f}, MAPE={metrics['mape']:.2f}%"
                )
                
                # ✨ 根据 score 大小分别记录到 MLflow
                if mlflow.active_run():
                    if score > cap_value:
                        # 异常值：记录到单独的 metric（用于标记异常点）
                        mlflow.log_metric("hyperopt/loss_anomaly", cap_value * 1.2, step=current_eval)
                        mlflow.log_param(f"trial_{current_eval}_anomaly_value", f"{score:.2e}")
                        logger.debug(f"    ⚠ 异常 loss ({score:.2f} > {cap_value:.2f})，已标记")
                    else:
                        # 正常值：记录到主 metric（用于折线图）
                        mlflow.log_metric(f"hyperopt/{metric}", score, step=current_eval)
                        mlflow.log_metric("hyperopt/rmse", metrics['rmse'], step=current_eval)
                        mlflow.log_metric("hyperopt/mae", metrics['mae'], step=current_eval)
                        mlflow.log_metric("hyperopt/mape", metrics['mape'], step=current_eval)
                    
                    # 成功标记（无论是否异常都记录）
                    mlflow.log_metric("hyperopt/success", 1.0, step=current_eval)
                
                # 记录最优结果
                if score < best_score[0]:
                    # ✨ 计算改善率
                    if best_score[0] != float('inf'):
                        improvement = (best_score[0] - score) / best_score[0] * 100
                        if improvement >= min_improvement_pct:
                            # 有显著改善，重置计数器
                            no_improvement_count[0] = 0
                        else:
                            # 改善不明显
                            no_improvement_count[0] += 1
                    else:
                        # 首次有效结果
                        no_improvement_count[0] = 0
                    
                    best_score[0] = score
                    logger.info(
                        f"  ✓ 发现更优参数! [{current_eval}/{max_evals}] "
                        f"{metric}={score:.4f}"
                    )
                    logger.info(
                        f"    order={order}, seasonal={seasonal_order}, "
                        f"trend={trend}"
                    )
                    
                    # 记录当前最优值
                    if mlflow.active_run():
                        mlflow.log_metric("hyperopt/best_so_far", score, step=current_eval)
                else:
                    # ✨ 无改善，增加计数
                    no_improvement_count[0] += 1
                
                # ✨ 检查早停条件
                if early_stop_enabled and current_eval >= min_evals:
                    if no_improvement_count[0] >= patience:
                        early_stopped[0] = True
                        stop_reason[0] = "no_improvement"
                        logger.warning(
                            f"  ⏹ 早停触发! 连续 {patience} 次无显著改善 (>{min_improvement_pct}%), "
                            f"在第 {current_eval}/{max_evals} 次评估时停止"
                        )
                        # 通过返回特殊状态触发 fmin 停止（需要修改策略）
                        # 注意：hyperopt 的 fmin 不支持中途停止，需要在外层处理
                
                return {'loss': float(score), 'status': STATUS_OK}
                
            except Exception as e:
                failed_count[0] += 1
                
                logger.debug(
                    f"  [{current_eval}/{max_evals}] 参数评估失败 (第{failed_count[0]}次): "
                    f"{str(e)[:100]}"
                )
                
                # ✨ 记录失败的评估到 MLflow（作为异常标记）
                if mlflow.active_run():
                    # 失败也记录到异常 metric
                    mlflow.log_metric("hyperopt/loss_anomaly", cap_value * 1.5, step=current_eval)
                    mlflow.log_metric("hyperopt/success", 0.0, step=current_eval)
                    # 记录失败的参数（限制长度避免超出 MLflow 限制）
                    error_msg = str(e)[:150]
                    mlflow.log_param(f"trial_{current_eval}_error", error_msg)
                
                return {'loss': float('inf'), 'status': STATUS_OK}
        
        # ✨ 运行优化（支持早停）
        if early_stop_enabled:
            # 使用循环方式支持早停
            from hyperopt import Trials as HyperoptTrials
            for i in range(max_evals):
                # 每次执行一次评估
                best_params_raw = fmin(
                    fn=objective,
                    space=space,
                    algo=tpe.suggest,
                    max_evals=len(trials.trials) + 1,  # 只执行一次新的评估
                    trials=trials,
                    rstate=np.random.default_rng(2025),
                    verbose=False,
                    show_progressbar=False
                )
                
                # 检查是否触发早停
                if early_stopped[0]:
                    break
        else:
            # 不启用早停，正常运行
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
        best_params = self._decode_params(best_params_raw, search_space_config)
        
        logger.info(
            f"超参数优化完成! 最优{metric}: {best_score[0]:.4f}"
        )
        logger.info(f"最优参数: {best_params}")
        
        # ✨ 记录优化摘要统计到 MLflow
        if mlflow.active_run():
            # 提取成功的评估
            success_losses = [
                t['result']['loss'] for t in trials.trials 
                if t['result']['status'] == 'ok' and t['result']['loss'] != float('inf')
            ]
            
            success_count = len(success_losses)
            actual_evals = eval_count[0]  # 实际执行的评估次数
            
            # 记录摘要指标
            summary_metrics = {
                "hyperopt_summary/total_evals": max_evals,
                "hyperopt_summary/actual_evals": actual_evals,
                "hyperopt_summary/successful_evals": success_count,
                "hyperopt_summary/failed_evals": failed_count[0],
                "hyperopt_summary/success_rate": (success_count / actual_evals * 100) if actual_evals > 0 else 0,
                "hyperopt_summary/best_loss": best_score[0],
            }
            
            # ✨ 添加早停统计
            if early_stop_enabled:
                summary_metrics["hyperopt_summary/early_stop_enabled"] = 1.0
                summary_metrics["hyperopt_summary/early_stopped"] = 1.0 if early_stopped[0] else 0.0
                
                if early_stopped[0]:
                    summary_metrics["hyperopt_summary/early_stop_at_eval"] = actual_evals
                    summary_metrics["hyperopt_summary/patience_used"] = patience
                    summary_metrics["hyperopt_summary/no_improve_count"] = no_improvement_count[0]
                    # 计算节省的时间百分比
                    time_saved_pct = ((max_evals - actual_evals) / max_evals * 100) if max_evals > 0 else 0
                    summary_metrics["hyperopt_summary/time_saved_pct"] = time_saved_pct
                    
                    mlflow.log_param("early_stop_reason", stop_reason[0])
                    
                    logger.info(
                        f"早停统计: 在 {actual_evals}/{max_evals} 次停止, "
                        f"节省 {time_saved_pct:.1f}% 时间"
                    )
            else:
                summary_metrics["hyperopt_summary/early_stop_enabled"] = 0.0
            
            # 如果有成功的评估，添加更多统计
            if success_losses:
                summary_metrics.update({
                    "hyperopt_summary/worst_loss": max(success_losses),
                    "hyperopt_summary/mean_loss": np.mean(success_losses),
                    "hyperopt_summary/median_loss": np.median(success_losses),
                    "hyperopt_summary/std_loss": np.std(success_losses),
                })
                
                # 计算改善率（首次成功 vs 最优）
                first_success_loss = success_losses[0] if success_losses else best_score[0]
                if first_success_loss > 0 and best_score[0] < first_success_loss:
                    improvement_pct = (first_success_loss - best_score[0]) / first_success_loss * 100
                    summary_metrics["hyperopt_summary/improvement_pct"] = improvement_pct
            
            mlflow.log_metrics(summary_metrics)
            
            logger.info(
                f"优化统计: 成功={success_count}/{actual_evals} "
                f"({success_count/actual_evals*100:.1f}%), "
                f"失败={failed_count[0]}"
            )
        
        # 更新当前模型参数
        self.order = best_params['order']
        self.seasonal_order = best_params['seasonal_order']
        self.trend = best_params['trend']
        self.config.update(best_params)
        
        return best_params
    
    def _build_search_space(self, search_space_config: Dict) -> Dict:
        """构建 Hyperopt 搜索空间
        
        Args:
            search_space_config: 搜索空间配置
            
        Returns:
            Hyperopt 搜索空间字典
        """
        if not search_space_config:
            # 使用默认搜索空间
            return {
                'p': hp.randint('p', 3),  # 0-2
                'd': hp.randint('d', 3),  # 0-2
                'q': hp.randint('q', 3),  # 0-2
                'P': hp.randint('P', 3),  # 0-2
                'D': hp.randint('D', 2),  # 0-1
                'Q': hp.randint('Q', 3),  # 0-2
                's': hp.choice('s', [12, 24, 7]),
                'trend': hp.choice('trend', ['n', 'c', 't', 'ct']),
            }
        
        # 从配置构建搜索空间
        space = {}
        
        order_config = search_space_config.get('order', {})
        space['p'] = hp.choice('p', order_config.get('p', [0, 1, 2]))
        space['d'] = hp.choice('d', order_config.get('d', [0, 1, 2]))
        space['q'] = hp.choice('q', order_config.get('q', [0, 1, 2]))
        
        seasonal_config = search_space_config.get('seasonal_order', {})
        space['P'] = hp.choice('P', seasonal_config.get('P', [0, 1, 2]))
        space['D'] = hp.choice('D', seasonal_config.get('D', [0, 1]))
        space['Q'] = hp.choice('Q', seasonal_config.get('Q', [0, 1, 2]))
        space['s'] = hp.choice('s', seasonal_config.get('s', [12, 24, 7]))
        
        trend_options = search_space_config.get('trend', ['n', 'c', 't', 'ct'])
        space['trend'] = hp.choice('trend', trend_options)
        
        return space
    
    def _decode_params(self, params_raw: Dict, search_space_config: Dict) -> Dict:
        """解码 Hyperopt 优化结果
        
        Args:
            params_raw: Hyperopt 返回的原始参数
            search_space_config: 搜索空间配置
            
        Returns:
            解码后的参数字典
        """
        order_config = search_space_config.get('order', {})
        seasonal_config = search_space_config.get('seasonal_order', {})
        trend_options = search_space_config.get('trend', ['n', 'c', 't', 'ct'])
        
        p_options = order_config.get('p', [0, 1, 2])
        d_options = order_config.get('d', [0, 1, 2])
        q_options = order_config.get('q', [0, 1, 2])
        P_options = seasonal_config.get('P', [0, 1, 2])
        D_options = seasonal_config.get('D', [0, 1])
        Q_options = seasonal_config.get('Q', [0, 1, 2])
        s_options = seasonal_config.get('s', [12, 24, 7])
        
        return {
            'order': (
                p_options[params_raw['p']],
                d_options[params_raw['d']],
                q_options[params_raw['q']]
            ),
            'seasonal_order': (
                P_options[params_raw['P']],
                D_options[params_raw['D']],
                Q_options[params_raw['Q']],
                s_options[params_raw['s']]
            ),
            'trend': trend_options[params_raw['trend']]
        }
    
    def get_mlflow_wrapper(self) -> SARIMAWrapper:
        """获取 MLflow 包装器
        
        Returns:
            SARIMAWrapper 实例
        """
        self._check_fitted()
        return SARIMAWrapper(self.model, self.frequency or 'D')
    
    def __repr__(self) -> str:
        status = "fitted" if self.is_fitted else "not fitted"
        return (
            f"SARIMAModel(status={status}, "
            f"order={self.order}, "
            f"seasonal_order={self.seasonal_order}, "
            f"trend='{self.trend}')"
        )
