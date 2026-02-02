"""Random Forest 时间序列预测模型

使用 sklearn 的 RandomForestRegressor 进行时间序列预测。
通过滑动窗口特征工程将时间序列问题转换为监督学习问题。
"""

from typing import Dict, Any, Optional
import pandas as pd
import numpy as np
import mlflow
from loguru import logger
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error

from .base import BaseTimeSeriesModel, ModelRegistry
from .random_forest_wrapper import RandomForestWrapper


@ModelRegistry.register("RandomForest")
class RandomForestModel(BaseTimeSeriesModel):
    """Random Forest 时间序列预测模型
    
    使用滑动窗口方法将时间序列转换为监督学习问题：
    - lag_features: 使用过去N个时间步作为特征
    - 支持多步预测
    - 适合非线性、复杂模式的时间序列
    
    参数说明：
    - lag_features: 滞后特征数量（默认12）
    - n_estimators: 树的数量（默认100）
    - max_depth: 树的最大深度（默认None，不限制）
    - min_samples_split: 分裂所需的最小样本数（默认2）
    - min_samples_leaf: 叶子节点最小样本数（默认1）
    - max_features: 每棵树使用的最大特征数（默认'sqrt'）
    """
    
    def __init__(self,
                 lag_features: int = 12,
                 n_estimators: int = 100,
                 max_depth: Optional[int] = None,
                 min_samples_split: int = 2,
                 min_samples_leaf: int = 1,
                 max_features: str = 'sqrt',
                 random_state: int = 42,
                 use_feature_engineering: bool = True,
                 feature_engineering_config: Optional[Dict] = None,
                 **kwargs):
        """初始化 Random Forest 模型
        
        Args:
            lag_features: 滞后特征数量
            n_estimators: 树的数量
            max_depth: 树的最大深度（None表示不限制）
            min_samples_split: 分裂所需的最小样本数
            min_samples_leaf: 叶子节点最小样本数
            max_features: 每棵树使用的最大特征数（'sqrt', 'log2', None）
            random_state: 随机种子
            use_feature_engineering: 是否使用完整的特征工程（推荐）
            feature_engineering_config: 特征工程配置字典
            **kwargs: 其他参数
        """
        super().__init__(
            lag_features=lag_features,
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_split=min_samples_split,
            min_samples_leaf=min_samples_leaf,
            max_features=max_features,
            random_state=random_state,
            use_feature_engineering=use_feature_engineering,
            **kwargs
        )
        
        self.lag_features = lag_features
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_samples_split = min_samples_split
        self.min_samples_leaf = min_samples_leaf
        self.max_features = max_features
        self.random_state = random_state
        self.use_feature_engineering = use_feature_engineering
        self.feature_engineering_config = feature_engineering_config
        
        # 用于预测的最后观测值
        self.last_train_values = None
        
        # 特征工程器
        self.feature_engineer = None
        
        # 特征名称（用于预测时转换为DataFrame）
        self.feature_names_ = None
        
        logger.debug(
            f"RandomForest 模型初始化: lag={self.lag_features}, "
            f"n_estimators={self.n_estimators}, max_depth={self.max_depth}, "
            f"use_feature_engineering={self.use_feature_engineering}"
        )
    
    
    def _create_supervised_data(self, data: pd.Series) -> tuple:
        """将时间序列转换为监督学习数据
        
        Args:
            data: 时间序列数据
            
        Returns:
            (X, y): 特征矩阵和目标向量
        """
        values = data.values
        X, y = [], []
        
        for i in range(self.lag_features, len(values)):
            X.append(values[i - self.lag_features:i])
            y.append(values[i])
        
        return np.array(X), np.array(y)
    
    def fit(self,
            train_data: pd.Series,
            val_data: Optional[pd.Series] = None,
            merge_val: bool = True,
            verbose: bool = True,
            **kwargs) -> 'RandomForestModel':
        """训练 Random Forest 模型
        
        Args:
            train_data: 训练数据（带 DatetimeIndex 的 Series）
            val_data: 验证数据（可选）
            merge_val: 是否合并验证数据进行训练（默认 True）
            verbose: 是否输出详细训练日志（默认 True）
                     - True: 输出完整训练过程（用于正常训练）
                     - False: 只输出关键信息（用于超参数优化）
            **kwargs: 其他训练参数
            
        Returns:
            self: 训练后的模型实例
            
        Raises:
            ValueError: 数据格式不正确或数据量不足
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
        
        if verbose:
            logger.info(
                f"开始训练 RandomForest 模型: "
                f"n_estimators={self.n_estimators}, max_depth={self.max_depth}"
            )
            logger.info(f"训练数据: {len(combined_data)} 个数据点")
        
        # 存储频率信息
        if isinstance(combined_data.index, pd.DatetimeIndex):
            try:
                self.frequency = pd.infer_freq(combined_data.index)
            except:
                self.frequency = None
        
        # 选择特征工程策略
        if self.use_feature_engineering:
            # 使用完整的特征工程
            from ..preprocessing.feature_engineering import TimeSeriesFeatureEngineer
            
            if not self.feature_engineering_config:
                raise ValueError(
                    "use_feature_engineering=true 但未提供 feature_engineering_config 配置"
                )
            
            logger.info("使用完整的特征工程（配置驱动）...")
            fe_cfg = self.feature_engineering_config
            
            self.feature_engineer = TimeSeriesFeatureEngineer(
                lag_periods=fe_cfg["lag_periods"],
                rolling_windows=fe_cfg["rolling_windows"],
                rolling_features=fe_cfg["rolling_features"],
                use_temporal_features=fe_cfg["use_temporal_features"],
                use_cyclical_features=fe_cfg["use_cyclical_features"],
                use_diff_features=fe_cfg["use_diff_features"],
                diff_periods=fe_cfg.get("diff_periods", [1]),
                drop_na=True
            )
            
            if verbose:
                logger.info(f"特征工程配置: lag_periods={fe_cfg['lag_periods']}, "
                           f"rolling_windows={fe_cfg['rolling_windows']}, "
                           f"use_temporal={fe_cfg['use_temporal_features']}")
            
            X_train, y_train = self.feature_engineer.fit_transform(combined_data)
            if verbose:
                logger.info(f"特征工程后样本: X={X_train.shape}, y={y_train.shape}")
                logger.info(f"生成 {len(self.feature_engineer.get_feature_names())} 个特征")
            
            # 保存特征名称
            self.feature_names_ = X_train.columns.tolist()
            
            # 记录特征工程信息到MLflow
            if mlflow.active_run():
                try:
                    mlflow.log_param("feature_engineering_enabled", True)
                except:
                    pass
                
                mlflow.log_metric("model/n_features", X_train.shape[1])
                mlflow.log_metric("model/lag_features", self.lag_features)
                
                if not merge_val or val_data is None:
                    pass
                else:
                    try:
                        mlflow.log_param("feature_lag_periods", str(list(range(1, self.lag_features + 1))))
                        mlflow.log_param("feature_rolling_windows", str([7, 14, 30] if self.lag_features >= 30 else [self.lag_features // 2]))
                        mlflow.log_param("feature_use_temporal", True)
                        mlflow.log_param("feature_use_diff", True)
                        
                        feature_names_sample = self.feature_names_[:20]
                        mlflow.log_param("feature_names_sample", str(feature_names_sample))
                        mlflow.log_text("\n".join(self.feature_names_), "features/feature_names.txt")
                    except:
                        pass
                
                logger.info(f"特征工程信息已记录到MLflow: {X_train.shape[1]} 个特征")
        else:
            # 使用简单的滞后窗口
            if verbose:
                logger.info(f"使用简单滞后窗口: lag={self.lag_features}")
            X_train, y_train = self._create_supervised_data(combined_data)
            if verbose:
                logger.info(f"监督学习样本: X={X_train.shape}, y={y_train.shape}")
            
            if mlflow.active_run():
                try:
                    mlflow.log_param("feature_engineering_enabled", False)
                    mlflow.log_param("feature_type", "simple_lag")
                except:
                    pass
                
                mlflow.log_metric("model/n_features", X_train.shape[1])
                mlflow.log_metric("model/lag_features", self.lag_features)
                
                logger.info(f"简单滞后特征信息已记录到MLflow: {X_train.shape[1]} 个特征")
        
        # 创建并训练模型
        try:
            self.model = RandomForestRegressor(
                n_estimators=self.n_estimators,
                max_depth=self.max_depth,
                min_samples_split=self.min_samples_split,
                min_samples_leaf=self.min_samples_leaf,
                max_features=self.max_features,
                random_state=self.random_state,
                n_jobs=-1,  # 使用所有CPU核心
                verbose=0
            )
            
            self.model.fit(X_train, y_train)
            if verbose:
                logger.info("模型训练完成")
            
            # 保存最后的观测值用于预测
            self.last_train_values = train_data.values[-max(self.lag_features, 50):].copy()
            self.last_train_data = combined_data.copy()
            
            self.is_fitted = True
            
            # 记录特征重要性
            feature_importance = self.model.feature_importances_
            logger.debug(f"特征重要性: {feature_importance[:5]}... (前5个)")
            
            return self
            
        except Exception as e:
            logger.error(f"RandomForest 模型训练失败: {e}")
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
        
        if self.use_feature_engineering and self.feature_engineer:
            logger.info(f"使用特征工程的递归预测")
            return self._predict_with_feature_engineering(steps)
        else:
            logger.info(f"使用简单滞后窗口的递归预测")
            return self._predict_simple(steps)
    
    def _predict_simple(self, steps: int) -> np.ndarray:
        """简单滞后窗口预测"""
        predictions = []
        current_window = self.last_train_values.copy()
        
        for i in range(steps):
            X = current_window[-self.lag_features:].reshape(1, -1)
            pred = self.model.predict(X)[0]
            predictions.append(pred)
            current_window = np.append(current_window[1:], pred)
        
        return np.array(predictions)
    
    def _predict_with_feature_engineering(self, steps: int) -> np.ndarray:
        """使用特征工程的递归预测"""
        if not hasattr(self, 'last_train_data') or self.last_train_data is None:
            raise RuntimeError("last_train_data 未初始化，无法进行预测")
        
        history = self.last_train_data.copy()
        predictions = []
        
        for step in range(steps):
            try:
                X, _ = self.feature_engineer.transform(history)
            except Exception as e:
                logger.error(f"特征提取失败: {e}")
                logger.warning("回退到简单预测方法")
                return self._predict_simple(steps - step)
            
            if len(X) == 0:
                logger.warning(f"第 {step+1} 步特征提取结果为空，停止预测")
                break
            
            last_features = X.iloc[-1:].copy()
            pred = self.model.predict(last_features)[0]
            predictions.append(pred)
            
            last_timestamp = history.index[-1]
            if isinstance(history.index, pd.DatetimeIndex):
                freq = history.index.freq
                if freq is None:
                    try:
                        freq = pd.infer_freq(history.index[-12:])
                    except:
                        freq = None
                
                if freq:
                    next_timestamp = last_timestamp + pd.tseries.frequencies.to_offset(freq)
                else:
                    avg_delta = (history.index[-1] - history.index[-2])
                    next_timestamp = last_timestamp + avg_delta
            else:
                next_timestamp = last_timestamp + 1
            
            new_point = pd.Series([pred], index=[next_timestamp])
            history = pd.concat([history, new_point])
        
        return np.array(predictions)
    
    def evaluate(
        self,
        test_data: pd.Series,
        mode: str = 'auto',
        horizon: Optional[int] = None,
        warn_threshold: Optional[int] = None,
        is_in_sample: bool = False,
        verbose: bool = True
    ) -> Dict[str, float]:
        """评估模型性能
        
        Args:
            test_data: 测试数据
            mode: 预测模式 ('auto', 'recursive', 'rolling')
            horizon: 滚动预测的单次预测步数
            warn_threshold: 长期预测警告阈值
            is_in_sample: 是否为样本内评估
            verbose: 是否输出详细日志
            
        Returns:
            评估指标字典
        """
        self._check_fitted()
        
        if not isinstance(test_data, pd.Series):
            raise ValueError("test_data 必须是 pandas.Series")
        
        steps = len(test_data)
        
        # 样本内评估
        if is_in_sample:
            if verbose:
                logger.info(f"使用样本内评估模式")
            if self.use_feature_engineering and self.feature_engineer:
                X, y_true = self.feature_engineer.transform(test_data)
                if len(X) == 0:
                    raise ValueError("特征提取失败")
                predictions = self.model.predict(X)
            else:
                X, y_true = self._create_supervised_data(test_data)
                predictions = self.model.predict(X)
        else:
            # 样本外评估：简化版本，只支持递归预测
            predictions = self.predict(steps)
            y_true = test_data.values
        
        # 计算指标
        metrics = self._calculate_metrics(y_true, predictions)
        
        prediction_bias = float((predictions - y_true).mean())
        prediction_bias_pct = float(prediction_bias / y_true.mean() * 100) if y_true.mean() != 0 else 0.0
        
        metrics['prediction_bias'] = prediction_bias
        metrics['prediction_bias_pct'] = prediction_bias_pct
        metrics['_predictions'] = predictions
        metrics['_y_true'] = y_true
        
        logger.info(
            f"模型评估完成: RMSE={metrics['rmse']:.4f}, "
            f"MAE={metrics['mae']:.4f}, MAPE={metrics['mape']:.2f}%"
        )
        
        return metrics
    
    def get_params(self) -> Dict[str, Any]:
        """获取模型参数"""
        return {
            'lag_features': self.lag_features,
            'n_estimators': self.n_estimators,
            'max_depth': self.max_depth,
            'min_samples_split': self.min_samples_split,
            'min_samples_leaf': self.min_samples_leaf,
            'max_features': self.max_features,
            'random_state': self.random_state
        }
    
    def optimize_hyperparams(
        self,
        train_data: pd.Series,
        val_data: pd.Series,
        config: Any
    ) -> Dict[str, Any]:
        """优化 Random Forest 超参数
        
        Args:
            train_data: 训练数据
            val_data: 验证数据
            config: 训练配置对象
            
        Returns:
            最优超参数字典
        """
        from hyperopt import fmin, tpe, hp, Trials, STATUS_OK
        
        search_config = config.get_search_config()
        max_evals = search_config["max_evals"]
        metric = search_config["metric"]
        search_space_config = search_config["search_space"]
        
        early_stop_config = search_config["early_stopping"]
        early_stop_enabled = early_stop_config.get("enabled", True)
        patience = early_stop_config.get("patience", 15)
        
        loss_cap_multiplier = early_stop_config.get("loss_cap_multiplier", 5.0)
        
        logger.info(f"开始超参数优化: max_evals={max_evals}, metric={metric}")
        if early_stop_enabled:
            logger.info(f"早停机制: 启用 (patience={patience})")
        
        data_std = train_data.std()
        cap_value = data_std * loss_cap_multiplier
        logger.info(f"Loss 上限阈值: {cap_value:.2f}")
        
        # 输出共享配置信息（所有 trial 通用，只输出一次）
        logger.info("=" * 60)
        logger.info("特征工程配置（所有 trial 共享）:")
        if self.use_feature_engineering:
            fe_cfg = self.feature_engineering_config
            logger.info(f"  lag_periods: {fe_cfg['lag_periods']}")
            logger.info(f"  rolling_windows: {fe_cfg['rolling_windows']}")
            logger.info(f"  rolling_features: {fe_cfg['rolling_features']}")
            logger.info(f"  use_temporal_features: {fe_cfg['use_temporal_features']}")
            logger.info(f"  use_cyclical_features: {fe_cfg['use_cyclical_features']}")
            logger.info(f"  use_diff_features: {fe_cfg['use_diff_features']}")
        else:
            logger.info(f"  使用简单滞后窗口: lag={self.lag_features}")
        logger.info("=" * 60)
        
        space = self._build_search_space(search_space_config)
        
        trials = Trials()
        best_score = [float('inf')]
        eval_count = [0]
        failed_count = [0]
        
        def objective(params):
            eval_count[0] += 1
            current_eval = eval_count[0]
            
            try:
                decoded_params = self._decode_params(params, search_space_config)
                
                # 输出当前尝试的核心超参数（排除固定参数和配置字典）
                exclude_keys = {'random_state', 'use_feature_engineering', 'feature_engineering_config'}
                core_params = {k: v for k, v in decoded_params.items() if k not in exclude_keys}
                logger.info(f"[{current_eval}/{max_evals}] 尝试参数:")
                for k, v in core_params.items():
                    logger.info(f"  {k}={v}")
                
                temp_model = RandomForestModel(**decoded_params)
                temp_model.fit(train_data, val_data=val_data, merge_val=False, verbose=False)
                
                train_metrics = temp_model.evaluate(train_data, is_in_sample=True, verbose=False)
                train_score = train_metrics.get(metric, train_metrics['rmse'])
                
                val_metrics = temp_model.evaluate(val_data, is_in_sample=False, verbose=False)
                val_score = val_metrics.get(metric, val_metrics['rmse'])
                score = val_score
                
                if score > cap_value:
                    failed_count[0] += 1
                    if mlflow.active_run():
                        mlflow.log_metric("hyperopt/loss_anomaly", cap_value * 1.2, step=current_eval)
                        mlflow.log_metric("hyperopt/success", 0.5, step=current_eval)
                    return {'loss': float(cap_value * 1.5), 'status': STATUS_OK}
                
                if mlflow.active_run():
                    mlflow.log_metric(f"hyperopt/train_{metric}", train_score, step=current_eval)
                    mlflow.log_metric(f"hyperopt/val_{metric}", val_score, step=current_eval)
                    mlflow.log_metric("hyperopt/overfit_gap", val_score - train_score, step=current_eval)
                    mlflow.log_metric("hyperopt/success", 1.0, step=current_eval)
                    
                    # 记录本次 trial 的参数
                    for key, value in decoded_params.items():
                        mlflow.log_param(f"trial_{current_eval}_{key}", value)
                
                if score < best_score[0]:
                    best_score[0] = score
                    logger.info(f"  ✓ 发现更优参数! [{current_eval}/{max_evals}] {metric}={score:.4f}")
                    for k, v in core_params.items():
                        logger.info(f"    {k}={v}")
                    
                    if mlflow.active_run():
                        mlflow.log_metric("hyperopt/best_so_far", score, step=current_eval)
                
                return {'loss': float(score), 'status': STATUS_OK}
                
            except Exception as e:
                failed_count[0] += 1
                logger.error(f"  [{current_eval}/{max_evals}] 参数评估失败: {e}")
                
                if mlflow.active_run():
                    mlflow.log_metric("hyperopt/loss_anomaly", cap_value * 1.5, step=current_eval)
                    mlflow.log_metric("hyperopt/success", 0.0, step=current_eval)
                
                return {'loss': float('inf'), 'status': STATUS_OK}
        
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
        
        best_params_actual = space_eval(space, best_params_raw)
        best_params = self._decode_params(best_params_actual, search_space_config)
        
        logger.info(f"超参数优化完成! 最优{metric}: {best_score[0]:.4f}")
        logger.info(f"最优参数: {best_params}")
        
        # 记录优化摘要统计到 MLflow
        if mlflow.active_run():
            actual_evals = len(trials.trials)
            success_count = sum(1 for t in trials.trials if t['result']['status'] == 'ok' and t['result']['loss'] != float('inf'))
            
            success_losses = [
                t['result']['loss'] for t in trials.trials 
                if t['result']['status'] == 'ok' and t['result']['loss'] != float('inf')
            ]
            
            summary_metrics = {
                "hyperopt_summary/total_trials": actual_evals,
                "hyperopt_summary/success_count": success_count,
                "hyperopt_summary/failed_count": failed_count[0],
                "hyperopt_summary/success_rate": (success_count / actual_evals * 100) if actual_evals > 0 else 0,
                "hyperopt_summary/best_loss": best_score[0],
            }
            
            # 早停统计
            is_early_stopped = (actual_evals < max_evals)
            if early_stop_enabled:
                summary_metrics["hyperopt_summary/early_stopped"] = 1.0 if is_early_stopped else 0.0
                summary_metrics["hyperopt_summary/patience_used"] = patience
                
                if is_early_stopped:
                    time_saved_pct = ((max_evals - actual_evals) / max_evals * 100) if max_evals > 0 else 0
                    summary_metrics["hyperopt_summary/time_saved_pct"] = time_saved_pct
                    logger.info(
                        f"早停统计: 在 {actual_evals}/{max_evals} 次停止, "
                        f"节省 {time_saved_pct:.1f}% 时间"
                    )
            else:
                summary_metrics["hyperopt_summary/early_stop_enabled"] = 0.0
            
            # Loss 分布统计
            if success_losses:
                summary_metrics.update({
                    "hyperopt_summary/worst_loss": max(success_losses),
                    "hyperopt_summary/mean_loss": np.mean(success_losses),
                    "hyperopt_summary/median_loss": np.median(success_losses),
                    "hyperopt_summary/std_loss": np.std(success_losses),
                })
                
                # 改进百分比
                first_success_loss = success_losses[0] if success_losses else best_score[0]
                if first_success_loss > 0 and best_score[0] < first_success_loss:
                    improvement_pct = (first_success_loss - best_score[0]) / first_success_loss * 100
                    summary_metrics["hyperopt_summary/improvement_pct"] = improvement_pct
            
            mlflow.log_metrics(summary_metrics)
            logger.info(
                f"优化摘要: 成功率 {summary_metrics['hyperopt_summary/success_rate']:.1f}% "
                f"({success_count}/{actual_evals})"
            )
        
        # 更新当前模型参数
        for key, value in best_params.items():
            setattr(self, key, value)
        self.config.update(best_params)
        
        return best_params
    
    def _build_search_space(self, search_space_config: Dict) -> Dict:
        """构建 Hyperopt 搜索空间"""
        from hyperopt import hp
        
        if not search_space_config:
            return {
                'n_estimators': hp.choice('n_estimators', [50, 100, 200, 300]),
                'max_depth': hp.choice('max_depth', [3, 5, 10, 15, None]),
                'min_samples_split': hp.choice('min_samples_split', [2, 5, 10]),
                'min_samples_leaf': hp.choice('min_samples_leaf', [1, 2, 4]),
                'max_features': hp.choice('max_features', ['sqrt', 'log2']),
                'lag_features': hp.choice('lag_features', [6, 12, 18, 24]),
            }
        
        space = {}
        
        if 'n_estimators' in search_space_config:
            space['n_estimators'] = hp.choice('n_estimators', search_space_config['n_estimators'])
        
        if 'max_depth' in search_space_config:
            space['max_depth'] = hp.choice('max_depth', search_space_config['max_depth'])
        
        if 'min_samples_split' in search_space_config:
            space['min_samples_split'] = hp.choice('min_samples_split', search_space_config['min_samples_split'])
        
        if 'min_samples_leaf' in search_space_config:
            space['min_samples_leaf'] = hp.choice('min_samples_leaf', search_space_config['min_samples_leaf'])
        
        if 'max_features' in search_space_config:
            space['max_features'] = hp.choice('max_features', search_space_config['max_features'])
        
        if 'lag_features' in search_space_config:
            space['lag_features'] = hp.choice('lag_features', search_space_config['lag_features'])
        
        return space
    
    def _decode_params(self, params_raw: Dict, search_space_config: Dict) -> Dict:
        """准备模型参数"""
        decoded = {}
        for key, value in params_raw.items():
            if isinstance(value, np.integer):
                decoded[key] = int(value)
            elif isinstance(value, np.floating):
                decoded[key] = float(value)
            else:
                decoded[key] = value
        
        decoded['random_state'] = self.random_state
        decoded['use_feature_engineering'] = self.use_feature_engineering
        decoded['feature_engineering_config'] = self.feature_engineering_config
        
        # 参数验证
        if 'min_samples_split' in decoded:
            if decoded['min_samples_split'] < 2:
                decoded['min_samples_split'] = 2
        
        if 'min_samples_leaf' in decoded:
            if decoded['min_samples_leaf'] < 1:
                decoded['min_samples_leaf'] = 1
        
        return decoded
    
    def save_mlflow(self, artifact_path: str = "model"):
        """保存模型到 MLflow
        
        Args:
            artifact_path: MLflow artifact 路径
            
        Raises:
            RuntimeError: 模型未训练
            Exception: 模型序列化失败
        """
        self._check_fitted()
        
        logger.info("开始保存 RandomForest 模型到 MLflow")
        logger.info(f"artifact_path: {artifact_path}")
        logger.info(f"use_feature_engineering: {self.use_feature_engineering}")
        if hasattr(self, 'last_train_data') and self.last_train_data is not None:
            logger.info(f"last_train_data 长度: {len(self.last_train_data)}")
        logger.info(f"feature_engineer: {type(self.feature_engineer) if self.feature_engineer else None}")
        
        # 记录模型元数据
        if mlflow.active_run():
            import sklearn
            try:
                import feature_engine
                fe_version = feature_engine.__version__
            except:
                fe_version = "unknown"
            
            metadata = {
                'model_type': 'RandomForest',
                'lag_features': self.lag_features,
                'use_feature_engineering': self.use_feature_engineering,
                'n_features': len(self.feature_names_) if self.feature_names_ else self.lag_features,
                'frequency': self.frequency,
                'data_length': len(self.last_train_data) if hasattr(self, 'last_train_data') and self.last_train_data is not None else 0,
                'sklearn_version': sklearn.__version__,
                'feature_engine_version': fe_version,
            }
            
            try:
                mlflow.log_dict(metadata, "model_metadata.json")
                logger.info("✓ 元数据已记录")
            except Exception as e:
                logger.warning(f"元数据记录失败: {e}")
        
        # 测试 feature_engineer 可序列化性
        if self.use_feature_engineering and self.feature_engineer:
            logger.info("测试 feature_engineer 序列化...")
            try:
                import cloudpickle
                serialized = cloudpickle.dumps(self.feature_engineer)
                logger.info(f"✓ feature_engineer 序列化成功，大小: {len(serialized)} bytes")
                # 测试反序列化
                deserialized = cloudpickle.loads(serialized)
                logger.info(f"✓ feature_engineer 反序列化成功: {type(deserialized)}")
            except Exception as e:
                logger.error(f"✗ feature_engineer 序列化测试失败: {type(e).__name__}: {e}")
                import traceback
                logger.error(f"详细错误:\n{traceback.format_exc()}")
                raise RuntimeError(f"feature_engineer 不可序列化: {e}")
        
        # 创建 Wrapper
        logger.info("创建 RandomForestWrapper...")
        wrapped_model = RandomForestWrapper(
            model=self.model,
            lag_features=self.lag_features,
            use_feature_engineering=self.use_feature_engineering,
            feature_engineer=self.feature_engineer if self.use_feature_engineering else None,
            training_frequency=self.frequency,
            feature_names=self.feature_names_,
            feature_engineering_config=self.feature_engineering_config
        )
        logger.info("✓ Wrapper 创建成功")
        
        # 测试 Wrapper 序列化
        logger.info("测试 Wrapper 序列化...")
        try:
            import cloudpickle
            serialized = cloudpickle.dumps(wrapped_model)
            logger.info(f"✓ Wrapper 序列化成功，大小: {len(serialized)} bytes")
        except Exception as e:
            logger.error(f"✗ Wrapper 序列化测试失败: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"详细错误:\n{traceback.format_exc()}")
            raise RuntimeError(f"Wrapper 不可序列化: {e}")
        
        # 保存模型
        logger.info("调用 mlflow.pyfunc.log_model()...")
        try:
            mlflow.pyfunc.log_model(
                artifact_path=artifact_path,
                python_model=wrapped_model,
                signature=None  # 设置为 None，支持灵活的字典输入
            )
            logger.info(f"✓ mlflow.pyfunc.log_model() 调用完成")
            
            # 验证模型是否真的保存了
            if mlflow.active_run():
                run_id = mlflow.active_run().info.run_id
                logger.info(f"验证模型文件是否存在 (Run ID: {run_id})...")
                try:
                    # 尝试列出 artifacts
                    client = mlflow.tracking.MlflowClient()
                    artifacts = client.list_artifacts(run_id, artifact_path)
                    if artifacts:
                        logger.info(f"✓ 发现 {len(artifacts)} 个 artifact 文件:")
                        for art in artifacts[:5]:  # 只显示前5个
                            logger.info(f"  - {art.path}")
                    else:
                        logger.error(f"✗ artifact path '{artifact_path}' 下没有文件！")
                        raise RuntimeError(f"模型保存失败：artifact path '{artifact_path}' 为空")
                except Exception as e:
                    logger.warning(f"无法验证 artifacts: {e}")
            
            logger.info(f"✓ 模型已保存到 MLflow: {artifact_path}")
        except Exception as e:
            logger.error(f"✗ 模型保存失败: {type(e).__name__}: {e}")
            logger.error("可能原因:")
            logger.error("  1. feature_engineer 包含不可序列化的对象")
            logger.error("  2. feature-engine 库版本不兼容")
            logger.error("  3. 内存不足或磁盘空间不足")
            logger.error(f"调试信息: use_feature_engineering={self.use_feature_engineering}")
            if self.feature_engineer:
                logger.error(f"  feature_engineer 类型: {type(self.feature_engineer)}")
            import traceback
            logger.error(f"详细错误:\n{traceback.format_exc()}")
            raise
