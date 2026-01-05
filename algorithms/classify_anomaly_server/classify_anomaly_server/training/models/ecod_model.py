"""ECOD (Empirical Cumulative Distribution-based Outlier Detection) 模型

基于经验累积分布函数的异常检测算法。
核心思想：对每个特征计算左尾和右尾的累积概率，异常点会有极端的概率值。

算法优势：
- 无需标签（无监督）
- 参数少（主要是 contamination）
- 快速高效（线性时间复杂度）
- 可解释性强（基于统计分布）
"""

from typing import Dict, Any, Optional
import pandas as pd
import numpy as np
import mlflow
from loguru import logger

from .base import BaseAnomalyModel, ModelRegistry


@ModelRegistry.register("ECOD")
class ECODModel(BaseAnomalyModel):
    """ECOD 异常检测模型
    
    使用经验累积分布函数检测异常：
    1. 对每个特征计算经验累积分布
    2. 计算每个样本在各特征上的左尾和右尾概率
    3. 聚合所有特征的异常分数
    4. 根据 contamination 确定阈值
    
    参数说明：
    - contamination: 预期异常比例（默认0.1，即10%）
    
    算法参考：
    Zheng Li, Yue Zhao, Xiyang Hu, Nicola Botta, Cezar Ionescu, George Chen.
    "ECOD: Unsupervised Outlier Detection Using Empirical Cumulative Distribution Functions"
    IEEE TKDE, 2022.
    """
    
    def __init__(self,
                 contamination: float = 0.1,
                 **kwargs):
        """初始化 ECOD 模型
        
        Args:
            contamination: 预期异常比例（理论范围 0~1，建议 < 0.5）
            **kwargs: 其他参数
        """
        super().__init__(contamination=contamination, **kwargs)
        
        # 验证 contamination 范围
        if not 0 < contamination < 1.0:
            raise ValueError(f"contamination 必须在 (0, 1.0) 之间，当前值: {contamination}")
        
        if contamination >= 0.5:
            logger.warning(
                f"contamination={contamination:.4f} >= 0.5，异常率超过50%通常不合理，请确认数据标签"
            )
        
        self.contamination = contamination
        
        # 模型参数（训练后设置）
        self.feature_names_ = None
        self.n_features_ = None
        self.n_samples_train_ = None
        
        logger.debug(f"ECOD 模型初始化: contamination={contamination}")
    
    def fit(self,
            train_data: pd.DataFrame,
            val_data: Optional[pd.DataFrame] = None,
            verbose: bool = True,
            log_to_mlflow: bool = True,
            **kwargs) -> 'ECODModel':
        """训练 ECOD 模型
        
        ECOD 是无监督算法，不需要标签。训练过程主要是记录训练数据分布。
        
        Args:
            train_data: 训练数据（特征矩阵）
            val_data: 验证数据（未使用，保留接口一致性）
            verbose: 是否输出详细日志
            log_to_mlflow: 是否记录到 MLflow（超参数优化时设为False）
            **kwargs: 其他训练参数
            
        Returns:
            self: 训练后的模型实例
        """
        if not isinstance(train_data, pd.DataFrame):
            raise ValueError("train_data 必须是 pandas.DataFrame")
        
        if verbose:
            logger.info(f"开始训练 ECOD 模型: contamination={self.contamination}")
            logger.info(f"训练数据: {train_data.shape}")
        
        # 保存训练数据（ECOD 需要参考分布）
        self.train_data_ = train_data.copy()
        self.feature_names_ = train_data.columns.tolist()
        self.n_features_ = len(self.feature_names_)
        self.n_samples_train_ = len(train_data)
        
        # 计算训练数据的异常分数
        train_scores = self._calculate_scores(train_data)
        
        # 根据 contamination 确定阈值
        self.threshold_ = np.percentile(train_scores, 100 * (1 - self.contamination))
        
        if verbose:
            logger.info(f"训练完成: 特征={self.n_features_}, 样本={self.n_samples_train_}")
            logger.info(f"异常阈值: {self.threshold_:.4f}")
        
        self.is_fitted = True
        
        # 记录到 MLflow（仅在非优化模式下）
        if log_to_mlflow and mlflow.active_run():
            try:
                mlflow.log_param("model_type", "ECOD")
                mlflow.log_param("contamination", self.contamination)
                mlflow.log_metric("model/n_features", self.n_features_)
                mlflow.log_metric("model/n_samples_train", self.n_samples_train_)
                mlflow.log_metric("model/threshold", self.threshold_)
            except Exception as e:
                logger.debug(f"MLflow 记录参数失败（可能已存在）: {e}")
        
        return self
    
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """预测异常标签
        
        Args:
            X: 特征矩阵
            
        Returns:
            预测标签数组（0=正常, 1=异常）
        """
        self._check_fitted()
        
        scores = self.predict_proba(X)
        predictions = (scores > self.threshold_).astype(int)
        
        return predictions
    
    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """预测异常分数
        
        Args:
            X: 特征矩阵
            
        Returns:
            异常分数数组（值越大越异常）
        """
        self._check_fitted()
        
        if not isinstance(X, pd.DataFrame):
            raise ValueError("X 必须是 pandas.DataFrame")
        
        # 验证特征列
        if list(X.columns) != self.feature_names_:
            raise ValueError(
                f"特征列不匹配。期望: {self.feature_names_}, "
                f"实际: {list(X.columns)}"
            )
        
        scores = self._calculate_scores(X)
        
        return scores
    
    def _calculate_scores(self, X: pd.DataFrame) -> np.ndarray:
        """计算异常分数（ECOD 核心算法）
        
        算法步骤：
        1. 对每个特征，计算每个样本的左尾和右尾累积概率
        2. 取左尾和右尾的最小值（最极端的概率）
        3. 聚合所有特征的分数
        
        Args:
            X: 特征矩阵
            
        Returns:
            异常分数数组
        """
        n_samples = len(X)
        n_features = len(self.feature_names_)
        
        # 存储每个特征的异常分数
        feature_scores = np.zeros((n_samples, n_features))
        
        for i, col in enumerate(self.feature_names_):
            # 获取训练数据的该特征值
            train_values = self.train_data_[col].values
            test_values = X[col].values
            
            # 计算经验累积分布函数（ECDF）
            # 左尾概率：P(X <= x)
            left_probs = self._empirical_cdf(test_values, train_values)
            
            # 右尾概率：P(X >= x) = 1 - P(X < x)
            right_probs = 1 - left_probs
            
            # 取左右尾概率的最小值（最极端的那个）
            # 然后取负对数，使得极端值（接近0的概率）得到高分
            min_probs = np.minimum(left_probs, right_probs)
            
            # 避免 log(0)
            min_probs = np.clip(min_probs, 1e-10, 1.0)
            
            # 异常分数：-log(min_prob)
            # 概率越小，分数越高
            feature_scores[:, i] = -np.log(min_probs)
        
        # 聚合所有特征的分数（取最大值）
        # 如果任何一个特征异常，整体就异常
        anomaly_scores = np.max(feature_scores, axis=1)
        
        return anomaly_scores
    
    def _empirical_cdf(self, test_values: np.ndarray, train_values: np.ndarray) -> np.ndarray:
        """计算经验累积分布函数
        
        对每个测试值，计算训练集中小于等于它的比例。
        
        Args:
            test_values: 测试数据的特征值
            train_values: 训练数据的特征值（参考分布）
            
        Returns:
            累积概率数组
        """
        # 对训练数据排序
        sorted_train = np.sort(train_values)
        n_train = len(sorted_train)
        
        # 对每个测试值，计算 ECDF
        probabilities = np.zeros(len(test_values))
        
        for i, value in enumerate(test_values):
            # 使用 searchsorted 快速找到位置
            # 返回 value 应该插入的位置，即小于等于 value 的元素个数
            count = np.searchsorted(sorted_train, value, side='right')
            probabilities[i] = count / n_train
        
        return probabilities
    
    def get_feature_importance(self) -> Dict[str, float]:
        """获取特征重要性（基于训练数据的异常贡献）
        
        Returns:
            特征重要性字典
        """
        self._check_fitted()
        
        # 计算训练数据每个特征的异常分数方差
        n_samples = len(self.train_data_)
        n_features = len(self.feature_names_)
        
        feature_scores = np.zeros((n_samples, n_features))
        
        for i, col in enumerate(self.feature_names_):
            train_values = self.train_data_[col].values
            left_probs = self._empirical_cdf(train_values, train_values)
            right_probs = 1 - left_probs
            min_probs = np.minimum(left_probs, right_probs)
            min_probs = np.clip(min_probs, 1e-10, 1.0)
            feature_scores[:, i] = -np.log(min_probs)
        
        # 计算每个特征的方差（方差越大，对异常检测贡献越大）
        feature_importance = {}
        total_variance = feature_scores.var(axis=0).sum()
        
        for i, col in enumerate(self.feature_names_):
            variance = feature_scores[:, i].var()
            importance = variance / total_variance if total_variance > 0 else 0
            feature_importance[col] = importance
        
        return feature_importance
    
    def optimize_hyperparams(
        self,
        train_data: pd.DataFrame,
        val_data: pd.DataFrame,
        train_labels: np.ndarray,
        val_labels: np.ndarray,
        config: Any
    ) -> Dict[str, Any]:
        """优化 ECOD 超参数
        
        使用 Hyperopt 进行贝叶斯优化。
        主要优化 contamination 参数。
        
        Args:
            train_data: 训练特征数据
            val_data: 验证特征数据
            train_labels: 训练标签（用于评估）
            val_labels: 验证标签（用于评估）
            config: 训练配置对象（包含搜索空间和优化设置）
            
        Returns:
            最优超参数字典
        """
        from hyperopt import fmin, tpe, hp, Trials, STATUS_OK, space_eval
        
        # 获取搜索配置
        search_config = config.get_search_config()
        max_evals = search_config["max_evals"]
        metric = search_config["metric"]  # precision, recall, f1
        search_space_config = search_config["search_space"]
        
        # 获取早停配置
        early_stop_config = search_config["early_stopping"]
        early_stop_enabled = early_stop_config.get("enabled", True)
        patience = early_stop_config.get("patience", 10)
        
        logger.info(
            f"开始超参数优化: max_evals={max_evals}, metric={metric}"
        )
        if early_stop_enabled:
            logger.info(f"早停机制: 启用 (patience={patience})")
        
        # 定义搜索空间
        space = self._build_search_space(search_space_config)
        
        # 优化状态跟踪
        trials = Trials()
        best_score = [0.0]  # 异常检测指标越大越好（f1, precision, recall）
        eval_count = [0]
        failed_count = [0]
        
        def objective(params):
            eval_count[0] += 1
            current_eval = eval_count[0]
            
            try:
                # 准备参数
                decoded_params = self._decode_params(params, search_space_config)
                contamination = decoded_params['contamination']
                
                logger.info(f"[{current_eval}/{max_evals}] 尝试参数: contamination={contamination:.4f}")
                
                # 创建临时模型并训练
                temp_model = ECODModel(contamination=contamination)
                temp_model.fit(train_data, verbose=False, log_to_mlflow=False)
                
                # 验证集评估
                val_predictions = temp_model.predict(val_data)
                val_metrics = temp_model.evaluate(val_data, val_labels)
                
                # 获取优化目标分数（越大越好，所以用负数作为 loss）
                score = val_metrics.get(metric, val_metrics['f1'])
                loss = -score  # hyperopt 最小化 loss，所以取负数
                
                # 记录到 MLflow
                if mlflow.active_run():
                    # 记录性能指标
                    mlflow.log_metric(f"hyperopt/val_{metric}", score, step=current_eval)
                    mlflow.log_metric("hyperopt/val_precision", val_metrics['precision'], step=current_eval)
                    mlflow.log_metric("hyperopt/val_recall", val_metrics['recall'], step=current_eval)
                    mlflow.log_metric("hyperopt/val_f1", val_metrics['f1'], step=current_eval)
                    mlflow.log_metric("hyperopt/val_auc", val_metrics.get('auc', 0), step=current_eval)
                    mlflow.log_metric("hyperopt/success", 1.0, step=current_eval)
                    # 记录contamination（同时作为参数和指标，方便可视化）
                    mlflow.log_metric("hyperopt/contamination", contamination, step=current_eval)
                    mlflow.log_param(f"trial_{current_eval}_contamination", contamination)
                
                # 记录最优结果
                if score > best_score[0]:
                    best_score[0] = score
                    logger.info(f"  ✓ 发现更优参数! [{current_eval}/{max_evals}] {metric}={score:.4f}, contamination={contamination:.4f}")
                    
                    if mlflow.active_run():
                        mlflow.log_metric("hyperopt/best_so_far", score, step=current_eval)
                
                return {'loss': float(loss), 'status': STATUS_OK}
                
            except Exception as e:
                failed_count[0] += 1
                logger.error(
                    f"  [{current_eval}/{max_evals}] 参数评估失败: {type(e).__name__}: {str(e)}"
                )
                
                if mlflow.active_run():
                    mlflow.log_metric("hyperopt/success", 0.0, step=current_eval)
                    error_msg = str(e)[:150]
                    mlflow.log_param(f"trial_{current_eval}_error", error_msg)
                
                return {'loss': float('inf'), 'status': STATUS_OK}
        
        # 运行优化
        from hyperopt.early_stop import no_progress_loss
        
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
        
        # 使用 space_eval 将索引转换为实际值
        best_params_actual = space_eval(space, best_params_raw)
        best_params = self._decode_params(best_params_actual, search_space_config)
        
        logger.info(f"超参数优化完成! 最优{metric}: {best_score[0]:.4f}")
        logger.info(f"最优参数: {best_params}")
        
        # 记录优化摘要统计到 MLflow
        if mlflow.active_run():
            success_losses = [
                t['result']['loss'] for t in trials.trials 
                if t['result']['status'] == 'ok' and t['result']['loss'] != float('inf')
            ]
            
            success_count = len(success_losses)
            actual_evals = len(trials.trials)
            is_early_stopped = actual_evals < max_evals
            
            summary_metrics = {
                "hyperopt_summary/total_evals": max_evals,
                "hyperopt_summary/actual_evals": actual_evals,
                "hyperopt_summary/successful_evals": success_count,
                "hyperopt_summary/failed_evals": failed_count[0],
                "hyperopt_summary/success_rate": (success_count / actual_evals * 100) if actual_evals > 0 else 0,
                "hyperopt_summary/best_score": best_score[0],
            }
            
            if early_stop_enabled:
                summary_metrics["hyperopt_summary/early_stop_enabled"] = 1.0
                summary_metrics["hyperopt_summary/early_stopped"] = 1.0 if is_early_stopped else 0.0
                summary_metrics["hyperopt_summary/patience_used"] = patience
                
                if is_early_stopped:
                    time_saved_pct = ((max_evals - actual_evals) / max_evals * 100) if max_evals > 0 else 0
                    summary_metrics["hyperopt_summary/time_saved_pct"] = time_saved_pct
                    logger.info(
                        f"早停统计: 在 {actual_evals}/{max_evals} 次停止, "
                        f"节省 {time_saved_pct:.1f}% 时间"
                    )
            
            if success_losses:
                # 注意：loss 是负数，需要转回正数
                success_scores = [-loss for loss in success_losses]
                summary_metrics.update({
                    "hyperopt_summary/worst_score": min(success_scores),
                    "hyperopt_summary/mean_score": np.mean(success_scores),
                    "hyperopt_summary/median_score": np.median(success_scores),
                    "hyperopt_summary/std_score": np.std(success_scores),
                })
            
            mlflow.log_metrics(summary_metrics)
            logger.info(
                f"优化摘要: 成功率 {summary_metrics['hyperopt_summary/success_rate']:.1f}% "
                f"({success_count}/{actual_evals})"
            )
        
        # 更新当前模型参数
        self.contamination = best_params['contamination']
        self.config['contamination'] = best_params['contamination']
        
        return best_params
    
    def _build_search_space(self, search_space_config: Dict) -> Dict:
        """构建 Hyperopt 搜索空间
        
        Args:
            search_space_config: 搜索空间配置
            
        Returns:
            Hyperopt 搜索空间字典
        """
        from hyperopt import hp
        
        if not search_space_config or 'contamination' not in search_space_config:
            # 默认搜索空间
            return {
                'contamination': hp.choice('contamination', [0.01, 0.05, 0.1, 0.15, 0.2, 0.25])
            }
        
        # 从配置构建搜索空间
        space = {}
        
        if 'contamination' in search_space_config:
            space['contamination'] = hp.choice('contamination', search_space_config['contamination'])
        
        return space
    
    def _decode_params(self, params_raw: Dict, search_space_config: Dict) -> Dict:
        """准备模型参数
        
        Args:
            params_raw: Hyperopt 返回的参数（经过 space_eval 转换后的实际值）
            search_space_config: 搜索空间配置（未使用，保留接口兼容性）
            
        Returns:
            模型参数字典
        """
        # 转换 numpy 类型为 Python 原生类型
        decoded = {}
        for key, value in params_raw.items():
            if isinstance(value, np.floating):
                decoded[key] = float(value)
            else:
                decoded[key] = value
        
        # 参数验证和修正
        if 'contamination' in decoded:
            contamination = decoded['contamination']
            # contamination 理论范围是 (0, 1)，通常建议 < 0.5，但允许用户自行决定
            if not 0 < contamination < 1.0:
                logger.warning(
                    f"contamination={contamination} 超出有效范围 (0, 1.0)，"
                    f"已修正为 0.1"
                )
                decoded['contamination'] = 0.1
            elif contamination >= 0.5:
                logger.warning(
                    f"contamination={contamination:.4f} >= 0.5，异常率超过50%可能不合理，"
                    f"但仍允许继续（用户决策）"
                )
        
        return decoded    
    def save_mlflow(self, artifact_path: str = "model"):
        """保存模型到 MLflow
        
        保存 ECOD 模型的训练数据、阈值和配置，使其可用于推理。
        
        Args:
            artifact_path: MLflow artifact 路径
            
        Raises:
            RuntimeError: 模型未训练或序列化失败
        """
        self._check_fitted()
        
        logger.info("开始保存 ECOD 模型到 MLflow")
        logger.info(f"artifact_path: {artifact_path}")
        
        # 记录模型元数据
        if mlflow.active_run():
            metadata = {
                'model_type': 'ECOD',
                'contamination': self.contamination,
                'threshold': float(self.threshold_),
                'n_features': self.n_features_,
                'n_samples_train': self.n_samples_train_,
                'feature_names': self.feature_names_,
            }
            
            try:
                mlflow.log_dict(metadata, "model_metadata.json")
                logger.info("✓ 元数据已记录")
            except Exception as e:
                logger.warning(f"元数据记录失败: {e}")
        
        # 创建 Wrapper
        logger.info("创建 ECODWrapper...")
        from .ecod_wrapper import ECODWrapper
        wrapped_model = ECODWrapper(
            model=self.model,
            feature_names=self.feature_names_,
            threshold=self.threshold_
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
                signature=None  # 设置为 None，支持灵活的 DataFrame 输入
            )
            logger.info(f"✓ mlflow.pyfunc.log_model() 调用完成")
            logger.info(f"✓ 模型已保存到 MLflow: {artifact_path}")
        except Exception as e:
            logger.error(f"✗ 模型保存失败: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"详细错误:\n{traceback.format_exc()}")
            raise
