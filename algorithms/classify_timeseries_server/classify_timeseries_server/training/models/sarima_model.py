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
from sklearn.exceptions import ConvergenceWarning

from .base import BaseTimeSeriesModel, ModelRegistry
from ..utils.sarima_optimizer import validate_params

warnings.filterwarnings('ignore', category=ConvergenceWarning)


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
            merge_val: bool = True,
            **kwargs) -> 'SARIMAModel':
        """训练 SARIMA 模型
        
        Args:
            train_data: 训练数据（带 DatetimeIndex 的 Series）
            val_data: 验证数据（可选）
            merge_val: 是否合并验证数据进行训练（默认 True）
                      **使用场景说明：**
                      - True（默认）: 合并 train+val 训练
                        * 用于最终训练阶段（Trainer 的 final training）
                        * 目的：最大化历史数据，提升预测能力
                        * 无需额外验证集评估
                      
                      - False: 仅用 train 训练，val 用于评估
                        * 用于超参数优化阶段（Hyperopt 的 objective 函数）
                        * 目的：在独立验证集上评估泛化能力，避免过拟合
                        * val 数据用于计算优化目标 loss
            **kwargs: 其他训练参数
            
        Returns:
            self: 训练后的模型实例
            
        Raises:
            ValueError: 数据格式不正确
        """
        # 根据 merge_val 决定是否合并验证数据
        if merge_val and val_data is not None:
            combined_data = pd.concat([train_data, val_data])
            logger.info("训练模式: 合并训练集和验证集")
        else:
            combined_data = train_data
            if val_data is not None:
                logger.info("训练模式: 仅使用训练集（验证集用于评估）")
            else:
                logger.info("训练模式: 仅使用训练集（无验证集）")
        
        if not isinstance(combined_data, pd.Series):
            raise ValueError("train_data 必须是 pandas.Series")
        
        if not isinstance(combined_data.index, pd.DatetimeIndex):
            logger.warning("数据索引不是 DatetimeIndex，频率信息可能丢失")
        
        logger.info(
            f"开始训练 SARIMA 模型: "
            f"order={self.order}, seasonal={self.seasonal_order}, trend={self.trend}"
        )
        logger.info(f"训练数据: {len(combined_data)} 个数据点")
        
        # 存储频率信息
        if isinstance(combined_data.index, pd.DatetimeIndex):
            try:
                self.frequency = pd.infer_freq(combined_data.index)
            except:
                self.frequency = None
        
        # 创建并训练 SARIMAX 模型
        try:
            sarimax_model = SARIMAX(
                combined_data,
                order=self.order,
                seasonal_order=self.seasonal_order,
                trend=self.trend,
                enforce_stationarity=False,
                enforce_invertibility=False,
            )
            
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
    
    def evaluate(self, test_data: pd.Series, is_in_sample: bool = False, **kwargs) -> Dict[str, float]:
        """评估模型性能
        
        Args:
            test_data: 测试数据（带 DatetimeIndex 的 Series）
            is_in_sample: 评估模式选择器
                **参数语义说明：**
                - False（默认）: 样本外评估（Out-of-sample evaluation）
                  * 用于验证集/测试集评估
                  * 使用 forecast() 递归预测未来 N 步
                  * 模拟真实生产场景，评估泛化能力
                  * SARIMA 特性：无递归误差累积（基于状态空间模型）
                
                - True: 样本内评估（In-sample evaluation）
                  * 用于训练集评估（Hyperopt 中检测欠拟合）
                  * 使用 fittedvalues 获取拟合值（一步预测）
                  * 准确反映模型对已见数据的拟合能力
                  * 速度极快（直接读取拟合值）
                
                **使用场景：**
                - Hyperopt objective: 
                  * `evaluate(train_data, is_in_sample=True)` → 检测欠拟合
                  * `evaluate(val_data, is_in_sample=False)` → 检测过拟合
                - Trainer 训练后: 
                  * `evaluate(train+val, is_in_sample=True)` → 检查拟合度
                - Trainer 测试集: 
                  * `evaluate(test_data, is_in_sample=False)` → 评估泛化能力
            **kwargs: 其他参数（用于兼容 GradientBoosting 接口）
            
        Returns:
            评估指标字典 {"rmse": ..., "mae": ..., "mape": ..., "_predictions": ..., "_y_true": ...}
            注意: 以下划线开头的键为内部数据，供 Trainer 使用
            
        Raises:
            RuntimeError: 模型未训练
        """
        self._check_fitted()
        
        if not isinstance(test_data, pd.Series):
            raise ValueError("test_data 必须是 pandas.Series")
        
        # 根据评估类型选择预测方式
        if is_in_sample:
            # 样本内评估：使用拟合值（快速）
            # 获取对应 test_data 的拟合值
            fitted = self.model.fittedvalues
            if len(fitted) >= len(test_data):
                predictions = fitted[-len(test_data):].values
                y_true = test_data.values
            else:
                # 如果拟合值不够，使用 predict()
                logger.warning(f"拟合值长度 {len(fitted)} < 测试数据长度 {len(test_data)}，回退到 predict()")
                predictions = self.model.predict(start=0, end=len(test_data)-1).values
                y_true = test_data.values
        else:
            # 样本外预测：递归预测未来 N 步（原逻辑）
            steps = len(test_data)
            predictions = self.predict(steps)
            y_true = test_data.values
        
        # 计算指标
        metrics = self._calculate_metrics(y_true, predictions)
        
        # 计算预测偏差（系统性误差）
        prediction_bias = float((predictions - y_true).mean())
        prediction_bias_pct = float(prediction_bias / y_true.mean() * 100) if y_true.mean() != 0 else 0.0
        
        metrics['prediction_bias'] = prediction_bias
        metrics['prediction_bias_pct'] = prediction_bias_pct
        
        # 添加内部数据供 Trainer 使用（下划线前缀表示内部数据）
        metrics['_predictions'] = predictions
        metrics['_y_true'] = y_true
        metrics['_is_in_sample'] = is_in_sample
        
        logger.info(
            f"模型评估完成: RMSE={metrics['rmse']:.4f}, "
            f"MAE={metrics['mae']:.4f}, MAPE={metrics['mape']:.2f}%, "
            f"Bias={prediction_bias:.4f} ({prediction_bias_pct:+.2f}%)"
        )
        
        return metrics
    
    def evaluate_with_plot(
        self,
        train_data: pd.Series,
        test_data: pd.Series,
        plot_residuals: bool = True
    ) -> Dict[str, float]:
        """评估模型性能并绘制可视化图表
        
        Args:
            train_data: 训练数据（用于绘图对比）
            test_data: 测试数据（带 DatetimeIndex 的 Series）
            plot_residuals: 是否绘制残差分析图
            
        Returns:
            评估指标字典
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
        
        # 绘制预测结果图
        if mlflow.active_run():
            from ..mlflow_utils import MLFlowUtils
            
            # 1. 预测结果对比图
            MLFlowUtils.plot_prediction_results(
                train_data=train_data,
                test_data=test_data,
                predictions=predictions,
                title=f"SARIMA {self.order} 预测结果",
                artifact_name="sarima_prediction",
                metrics=metrics
            )
            
            # 2. 残差分析图
            if plot_residuals:
                residuals = y_true - predictions
                MLFlowUtils.plot_residuals_analysis(
                    residuals=residuals,
                    title="SARIMA 残差分析",
                    artifact_name="sarima_residuals"
                )
            
            logger.info("预测可视化图表已上传到 MLflow")
        
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
        
        # 获取早停配置
        early_stop_config = config.get("hyperparams", "search", "early_stopping")
        early_stop_enabled = early_stop_config.get("enabled", False) if early_stop_config else False
        patience = early_stop_config.get("patience", 15) if early_stop_config else 15
        
        # 异常值配置
        loss_cap_multiplier = early_stop_config.get("loss_cap_multiplier", 5.0) if early_stop_config else 5.0
        
        logger.info(
            f"开始超参数优化: max_evals={max_evals}, metric={metric}"
        )
        if early_stop_enabled:
            logger.info(
                f"早停机制: 启用 (patience={patience})"
            )
        
        # 计算动态上限值（用于截断异常 loss）
        data_std = train_data.std()
        cap_value = data_std * loss_cap_multiplier
        logger.info(
            f"Loss 上限阈值: {cap_value:.2f} "
            f"(std {data_std:.2f} × {loss_cap_multiplier})"
        )
        
        # 定义搜索空间
        space = self._build_search_space(search_space_config)
        
        # 优化状态跟踪
        trials = Trials()
        best_score = [float('inf')]
        eval_count = [0]
        failed_count = [0]  # 失败计数器
        
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
                
                # 参数验证
                is_valid, reason = validate_params(
                    *order, *seasonal_order, len(train_data)
                )
                if not is_valid:
                    logger.debug(
                        f"  [{current_eval}/{max_evals}] 参数无效: {reason}"
                    )
                    return {'loss': float('inf'), 'status': STATUS_OK}
                
                logger.debug(
                    f"  [{current_eval}/{max_evals}] 尝试参数: "
                    f"order={order}, seasonal={seasonal_order}, trend={trend}"
                )
                
                # 创建临时模型并训练（仅用 train_data，val_data 用于评估）
                temp_model = SARIMAModel(
                    order=order,
                    seasonal_order=seasonal_order,
                    trend=trend
                )
                
                temp_model.fit(train_data, val_data=val_data, merge_val=False)
                
                # 训练集评估（样本内评估，快速检测欠拟合）
                train_metrics = temp_model.evaluate(train_data, is_in_sample=True)
                train_score = train_metrics.get(metric, train_metrics['rmse'])
                
                # 验证集评估（样本外预测，检测过拟合）
                val_metrics = temp_model.evaluate(val_data, is_in_sample=False)
                val_score = val_metrics.get(metric, val_metrics['rmse'])
                score = val_score  # 用验证集 loss 进行优化
                
                logger.debug(
                    f"  [{current_eval}/{max_evals}] train_{metric}={train_score:.4f}, val_{metric}={val_score:.4f}, "
                    f"RMSE={val_metrics['rmse']:.4f}, MAPE={val_metrics['mape']:.2f}%"
                )
                
                # 异常值提前返回，不参与后续逻辑
                if score > cap_value:
                    failed_count[0] += 1
                    logger.debug(
                        f"  [{current_eval}/{max_evals}] ⚠ 异常 loss "
                        f"({score:.2f} > {cap_value:.2f})，返回惩罚值"
                    )
                    if mlflow.active_run():
                        mlflow.log_metric("hyperopt/loss_anomaly", cap_value * 1.2, step=current_eval)
                        mlflow.log_param(f"trial_{current_eval}_anomaly_value", f"{score:.2e}")
                        mlflow.log_metric("hyperopt/success", 0.5, step=current_eval)
                    
                    return {'loss': float(cap_value * 1.5), 'status': STATUS_OK}
                
                # 正常值：记录到 MLflow
                if mlflow.active_run():
                    # 记录训练集指标
                    mlflow.log_metric(f"hyperopt/train_{metric}", train_score, step=current_eval)
                    mlflow.log_metric("hyperopt/train_rmse", train_metrics['rmse'], step=current_eval)
                    mlflow.log_metric("hyperopt/train_mae", train_metrics['mae'], step=current_eval)
                    mlflow.log_metric("hyperopt/train_mape", train_metrics['mape'], step=current_eval)
                    
                    # 记录验证集指标
                    mlflow.log_metric(f"hyperopt/val_{metric}", val_score, step=current_eval)
                    mlflow.log_metric("hyperopt/val_rmse", val_metrics['rmse'], step=current_eval)
                    mlflow.log_metric("hyperopt/val_mae", val_metrics['mae'], step=current_eval)
                    mlflow.log_metric("hyperopt/val_mape", val_metrics['mape'], step=current_eval)
                    
                    # 记录过拟合指标（val_loss - train_loss）
                    overfit_gap = val_score - train_score
                    mlflow.log_metric("hyperopt/overfit_gap", overfit_gap, step=current_eval)
                    
                    mlflow.log_metric("hyperopt/success", 1.0, step=current_eval)
                    
                    # 记录本次 trial 的详细参数
                    mlflow.log_param(f"trial_{current_eval}_order", str(order))
                    mlflow.log_param(f"trial_{current_eval}_seasonal_order", str(seasonal_order))
                    mlflow.log_param(f"trial_{current_eval}_trend", trend)
                
                # 记录最优结果
                if score < best_score[0]:
                    # 计算改善率（仅用于日志）
                    improvement_pct = 0.0
                    if best_score[0] != float('inf'):
                        improvement_pct = (best_score[0] - score) / best_score[0] * 100
                    
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
                        if improvement_pct > 0:
                            mlflow.log_metric("hyperopt/improvement_pct", improvement_pct, step=current_eval)
                
                return {'loss': float(score), 'status': STATUS_OK}
                
            except Exception as e:
                failed_count[0] += 1
                
                logger.debug(
                    f"  [{current_eval}/{max_evals}] 参数评估失败 (第{failed_count[0]}次): "
                    f"{str(e)[:100]}"
                )
                
                # 记录失败的评估到 MLflow（作为异常标记）
                if mlflow.active_run():
                    # 失败也记录到异常 metric
                    mlflow.log_metric("hyperopt/loss_anomaly", cap_value * 1.5, step=current_eval)
                    mlflow.log_metric("hyperopt/success", 0.0, step=current_eval)
                    # 记录失败的参数（限制长度避免超出 MLflow 限制）
                    error_msg = str(e)[:150]
                    mlflow.log_param(f"trial_{current_eval}_error", error_msg)
                
                return {'loss': float('inf'), 'status': STATUS_OK}
        
        # 运行优化（使用hyperopt内置早停）
        from hyperopt.early_stop import no_progress_loss
        from hyperopt import space_eval
        
        best_params_raw = fmin(
            fn=objective,
            space=space,
            algo=tpe.suggest,
            max_evals=max_evals,
            trials=trials,
            early_stop_fn=no_progress_loss(patience) if early_stop_enabled else None,
            rstate=np.random.default_rng(None),
            verbose=False
        )
        
        logger.info("=" * 60)
        logger.info("Hyperopt 优化完成，转换最优参数...")
        logger.info(f"  fmin() 返回的原始值（索引）: {best_params_raw}")
        
        # 使用 space_eval 将索引转换为实际值（标准做法）
        best_params_actual = space_eval(space, best_params_raw)
        logger.info(f"  space_eval() 转换后的实际值: {best_params_actual}")
        logger.info("=" * 60)
        
        # 转换最优参数
        best_params = self._decode_params(best_params_actual, search_space_config)
        
        logger.info(
            f"超参数优化完成! 最优{metric}: {best_score[0]:.4f}"
        )
        logger.info(f"最优参数: {best_params}")
        
        # 记录优化摘要统计到 MLflow
        if mlflow.active_run():
            # 提取成功的评估
            success_losses = [
                t['result']['loss'] for t in trials.trials 
                if t['result']['status'] == 'ok' and t['result']['loss'] != float('inf')
            ]
            
            success_count = len(success_losses)
            actual_evals = len(trials.trials)  # 实际执行的评估次数
            is_early_stopped = actual_evals < max_evals  # 判断是否提前停止
            
            # 记录摘要指标
            summary_metrics = {
                "hyperopt_summary/total_evals": max_evals,
                "hyperopt_summary/actual_evals": actual_evals,
                "hyperopt_summary/successful_evals": success_count,
                "hyperopt_summary/failed_evals": failed_count[0],
                "hyperopt_summary/success_rate": (success_count / actual_evals * 100) if actual_evals > 0 else 0,
                "hyperopt_summary/best_loss": best_score[0],
            }
            
            # 添加早停统计
            if early_stop_enabled:
                summary_metrics["hyperopt_summary/early_stop_enabled"] = 1.0
                summary_metrics["hyperopt_summary/early_stopped"] = 1.0 if is_early_stopped else 0.0
                summary_metrics["hyperopt_summary/patience_used"] = patience
                
                if is_early_stopped:
                    # 计算节省的时间百分比
                    time_saved_pct = ((max_evals - actual_evals) / max_evals * 100) if max_evals > 0 else 0
                    summary_metrics["hyperopt_summary/time_saved_pct"] = time_saved_pct
                    
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
        """准备模型参数
        
        Args:
            params_raw: Hyperopt 返回的参数（经过 space_eval 转换后的实际值）
            search_space_config: 搜索空间配置（未使用，保留接口兼容性）
            
        Returns:
            模型参数字典
        """
        logger.debug("=" * 60)
        logger.debug("SARIMA _decode_params() 输入参数:")
        logger.debug(f"  params_raw: {params_raw}")
        for key, value in params_raw.items():
            logger.debug(f"    {key}: {value} (type: {type(value).__name__})")
        logger.debug("=" * 60)
        
        # 转换 numpy 类型为 Python 原生类型
        def _convert_value(value):
            if isinstance(value, np.integer):
                return int(value)
            elif isinstance(value, np.floating):
                return float(value)
            else:
                return value
        
        result = {
            'order': (
                _convert_value(params_raw['p']),
                _convert_value(params_raw['d']),
                _convert_value(params_raw['q'])
            ),
            'seasonal_order': (
                _convert_value(params_raw['P']),
                _convert_value(params_raw['D']),
                _convert_value(params_raw['Q']),
                _convert_value(params_raw['s'])
            ),
            'trend': params_raw['trend']
        }
        
        logger.debug("SARIMA _decode_params() 输出参数:")
        logger.debug(f"  result: {result}")
        logger.debug("=" * 60)
        
        return result
    
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
