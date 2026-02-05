"""XGBoost 文本分类器实现"""
from typing import Dict, Any, Optional
import numpy as np
import xgboost as xgb
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    confusion_matrix,
    classification_report
)
from hyperopt import fmin, tpe, hp, STATUS_OK, Trials, space_eval
from loguru import logger
import mlflow

from .base import BaseTextClassifier, ModelRegistry


@ModelRegistry.register("XGBoost")
class XGBoostTextClassifier(BaseTextClassifier):
    """XGBoost 文本分类器
    
    支持多分类和二分类任务，集成 Hyperopt 超参数优化。
    """
    
    def __init__(self, **kwargs):
        """初始化 XGBoost 分类器
        
        Args:
            **kwargs: XGBoost 参数（如 max_depth, learning_rate 等）
        """
        self.params = kwargs
        self.model: Optional[xgb.XGBClassifier] = None
        self.best_params: Optional[Dict[str, Any]] = None
        self.n_classes: Optional[int] = None
        
        logger.info(f"初始化 XGBoost 分类器，参数: {self.params}")
    
    def fit(self, X_train, y_train, X_val=None, y_val=None, **kwargs):
        """训练 XGBoost 模型
        
        Args:
            X_train: 训练集特征矩阵
            y_train: 训练集标签
            X_val: 验证集特征矩阵（可选，用于早停）
            y_val: 验证集标签（可选）
            **kwargs: 其他训练参数
        """
        logger.info(f"开始训练 XGBoost 模型，训练集大小: {X_train.shape}")
        
        # 确定类别数
        self.n_classes = len(np.unique(y_train))
        logger.info(f"类别数: {self.n_classes}")
        
        # 合并参数
        model_params = {
            "n_estimators": 100,
            "max_depth": 6,
            "learning_rate": 0.1,
            "random_state": 42,
            "n_jobs": -1,
            "tree_method": "hist",  # 使用直方图算法加速
            "eval_metric": "mlogloss" if self.n_classes > 2 else "logloss",
        }
        
        # 使用最优参数（如果已优化）
        if self.best_params:
            model_params.update(self.best_params)
        
        # 使用传入的参数
        model_params.update(self.params)
        model_params.update(kwargs)
        
        logger.info(f"模型参数: {model_params}")
        
        # 创建模型
        self.model = xgb.XGBClassifier(**model_params)
        
        # 早停配置
        fit_params = {}
        if X_val is not None and y_val is not None:
            fit_params["eval_set"] = [(X_train, y_train), (X_val, y_val)]
            fit_params["verbose"] = False
            
            # XGBoost 2.0+ 使用 early_stopping_rounds
            if hasattr(self.model, 'early_stopping_rounds'):
                self.model.early_stopping_rounds = 50
        
        # 训练模型
        logger.info("开始训练 XGBoost...")
        self.model.fit(X_train, y_train, **fit_params)
        
        # 训练完成后记录训练过程到 MLflow
        if mlflow.active_run() and X_val is not None:
            try:
                # 使用 evals_result() 获取训练过程中的评估指标
                evals_result = self.model.evals_result()
                if evals_result:
                    logger.info("✓ 记录训练过程指标到 MLflow")
                    # evals_result 格式: {'validation_0': {'logloss': [...]}, 'validation_1': {'logloss': [...]}}
                    for data_name, metrics in evals_result.items():
                        for metric_name, values in metrics.items():
                            for epoch, value in enumerate(values):
                                mlflow.log_metric(
                                    f"training/{data_name}_{metric_name}",
                                    value,
                                    step=epoch
                                )
                else:
                    logger.warning("无法获取训练过程指标（evals_result 为空）")
            except Exception as e:
                logger.warning(f"记录训练过程到 MLflow 失败: {e}")
        
        # 记录训练完成信息到 MLflow
        if mlflow.active_run():
            try:
                mlflow.log_metrics({
                    "model/n_features": X_train.shape[1],
                    "model/n_samples_train": X_train.shape[0],
                    "model/n_classes": self.n_classes,
                })
                if hasattr(self.model, 'best_iteration') and self.model.best_iteration is not None:
                    mlflow.log_metric("model/best_iteration", self.model.best_iteration)
            except Exception as e:
                logger.warning(f"记录模型信息到 MLflow 失败: {e}")
        
        logger.info("XGBoost 模型训练完成")
        
        return self
    
    def predict(self, X):
        """预测类别
        
        Args:
            X: 特征矩阵
            
        Returns:
            预测的类别标签
        """
        if self.model is None:
            raise ValueError("模型未训练，请先调用 fit()")
        
        return self.model.predict(X)
    
    def predict_proba(self, X):
        """预测类别概率
        
        Args:
            X: 特征矩阵
            
        Returns:
            类别概率矩阵
        """
        if self.model is None:
            raise ValueError("模型未训练，请先调用 fit()")
        
        return self.model.predict_proba(X)
    
    def evaluate(self, X_test, y_test, prefix: str = "test") -> Dict[str, float]:
        """评估模型性能
        
        Args:
            X_test: 测试集特征矩阵
            y_test: 测试集标签
            prefix: 指标名称前缀
            
        Returns:
            评估指标字典
        """
        logger.info(f"评估模型性能（{prefix}集），样本数: {X_test.shape[0]}")
        
        # 预测
        y_pred = self.predict(X_test)
        y_proba = self.predict_proba(X_test)
        
        # 计算指标
        metrics = {}
        
        # 基础指标
        metrics[f"{prefix}_accuracy"] = accuracy_score(y_test, y_pred)
        metrics[f"{prefix}_f1_weighted"] = f1_score(y_test, y_pred, average="weighted", zero_division=0)
        metrics[f"{prefix}_f1_macro"] = f1_score(y_test, y_pred, average="macro", zero_division=0)
        metrics[f"{prefix}_precision_weighted"] = precision_score(y_test, y_pred, average="weighted", zero_division=0)
        metrics[f"{prefix}_recall_weighted"] = recall_score(y_test, y_pred, average="weighted", zero_division=0)
        
        # 混淆矩阵（不记录到 MLflow，使用 _ 前缀）
        metrics["_confusion_matrix"] = confusion_matrix(y_test, y_pred)
        
        # 分类报告（不记录到 MLflow）
        metrics["_classification_report"] = classification_report(y_test, y_pred, zero_division=0)
        
        # 记录日志
        logger.info(f"{prefix} 指标:")
        for key, value in metrics.items():
            if not key.startswith("_"):
                logger.info(f"  {key}: {value:.4f}")
        
        return metrics
    
    def optimize_hyperparams(
        self,
        X_train,
        y_train,
        X_val,
        y_val,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """使用 Hyperopt 优化超参数
        
        Args:
            X_train: 训练集特征矩阵
            y_train: 训练集标签
            X_val: 验证集特征矩阵
            y_val: 验证集标签
            config: 优化配置
                - max_evals: 最大评估次数
                - metric: 优化目标指标（如 "f1_weighted"）
                - search_space: 搜索空间定义
                - random_state: 随机种子
                
        Returns:
            最优超参数字典
        """
        logger.info("开始超参数优化（Hyperopt TPE）")
        
        # 初始化 n_classes（如果尚未设置）
        if self.n_classes is None:
            self.n_classes = len(np.unique(y_train))
            logger.info(f"检测到类别数: {self.n_classes}")
        
        max_evals = config.get("max_evals", 20)
        metric = config.get("metric", "f1_weighted")
        random_state = config.get("random_state", 42)
        search_space_config = config.get("search_space", {})
        
        # 获取早停配置
        early_stop_config = config.get("early_stopping", {})
        early_stop_enabled = early_stop_config.get("enabled", True)
        patience = early_stop_config.get("patience", max(10, int(max_evals * 0.2)))
        
        # 定义搜索空间
        search_space = {
            "max_depth": hp.choice("max_depth", search_space_config.get("max_depth", [3, 5, 7, 10])),
            "learning_rate": hp.choice("learning_rate", search_space_config.get("learning_rate", [0.01, 0.05, 0.1, 0.2])),
            "n_estimators": hp.choice("n_estimators", search_space_config.get("n_estimators", [50, 100, 200, 300])),
            "min_child_weight": hp.choice("min_child_weight", search_space_config.get("min_child_weight", [1, 3, 5])),
            "subsample": hp.choice("subsample", search_space_config.get("subsample", [0.7, 0.8, 0.9, 1.0])),
            "colsample_bytree": hp.choice("colsample_bytree", search_space_config.get("colsample_bytree", [0.7, 0.8, 0.9, 1.0])),
            "gamma": hp.choice("gamma", search_space_config.get("gamma", [0, 0.1, 0.2, 0.3])),
        }
        
        logger.info(f"搜索空间: {search_space_config}")
        logger.info(f"优化目标: {metric}, 最大评估次数: {max_evals}")
        
        if early_stop_enabled:
            logger.info(f"早停机制: 启用 (patience={patience})")
        else:
            logger.info("早停机制: 禁用")
        
        # 进度跟踪
        eval_count = [0]
        failed_count = [0]
        best_score_tracker = [0.0]
        
        # 定义目标函数
        def objective(params):
            eval_count[0] += 1
            current_eval = eval_count[0]
            
            try:
                # 输出当前尝试的参数
                logger.info(f"[{current_eval}/{max_evals}] 尝试参数:")
                logger.info(f"  max_depth={params['max_depth']}")
                logger.info(f"  learning_rate={params['learning_rate']}")
                logger.info(f"  n_estimators={params['n_estimators']}")
                logger.info(f"  min_child_weight={params['min_child_weight']}")
                logger.info(f"  subsample={params['subsample']}")
                logger.info(f"  colsample_bytree={params['colsample_bytree']}")
                logger.info(f"  gamma={params['gamma']}")
                
                # 创建临时模型
                temp_model = xgb.XGBClassifier(
                    **params,
                    random_state=random_state,
                    n_jobs=-1,
                    tree_method="hist",
                    eval_metric="mlogloss" if self.n_classes > 2 else "logloss",
                )
                
                # 训练
                temp_model.fit(
                    X_train, y_train,
                    eval_set=[(X_val, y_val)],
                    verbose=False
                )
                
                # 评估验证集
                y_val_pred = temp_model.predict(X_val)
                
                if metric == "accuracy":
                    val_score = accuracy_score(y_val, y_val_pred)
                elif metric == "f1_weighted":
                    val_score = f1_score(y_val, y_val_pred, average="weighted", zero_division=0)
                elif metric == "f1_macro":
                    val_score = f1_score(y_val, y_val_pred, average="macro", zero_division=0)
                else:
                    raise ValueError(f"不支持的优化指标: {metric}")
                
                # 同时评估训练集，检测过拟合
                y_train_pred = temp_model.predict(X_train)
                if metric == "accuracy":
                    train_score = accuracy_score(y_train, y_train_pred)
                elif metric == "f1_weighted":
                    train_score = f1_score(y_train, y_train_pred, average="weighted", zero_division=0)
                elif metric == "f1_macro":
                    train_score = f1_score(y_train, y_train_pred, average="macro", zero_division=0)
                else:
                    train_score = 0.0
                
                overfit_gap = train_score - val_score
                
                logger.info(f"  训练集 {metric}: {train_score:.4f}")
                logger.info(f"  验证集 {metric}: {val_score:.4f}")
                logger.info(f"  过拟合差距: {overfit_gap:.4f}")
                
                # 记录到 MLflow
                if mlflow.active_run():
                    # 记录性能指标
                    mlflow.log_metric(f"hyperopt/train_{metric}", train_score, step=current_eval)
                    mlflow.log_metric(f"hyperopt/val_{metric}", val_score, step=current_eval)
                    mlflow.log_metric("hyperopt/overfit_gap", overfit_gap, step=current_eval)
                    mlflow.log_metric("hyperopt/success", 1.0, step=current_eval)
                    
                    # 记录参数
                    for key, value in params.items():
                        mlflow.log_metric(f"hyperopt/{key}", value, step=current_eval)
                        mlflow.log_param(f"trial_{current_eval}_{key}", value)
                
                # 记录最优结果
                if val_score > best_score_tracker[0]:
                    best_score_tracker[0] = val_score
                    logger.info(f"  ✓ 发现更优参数! [{current_eval}/{max_evals}] {metric}={val_score:.4f}")
                    
                    if mlflow.active_run():
                        mlflow.log_metric("hyperopt/best_so_far", val_score, step=current_eval)
                
                # Hyperopt 最小化目标，所以返回负值
                return {"loss": -val_score, "status": STATUS_OK}
            
            except Exception as e:
                failed_count[0] += 1
                logger.error(f"  [{current_eval}/{max_evals}] 参数评估失败: {type(e).__name__}: {str(e)}")
                
                if mlflow.active_run():
                    mlflow.log_metric("hyperopt/success", 0.0, step=current_eval)
                    mlflow.log_param(f"trial_{current_eval}_error", str(e)[:150])
                
                return {"loss": float('inf'), "status": STATUS_OK}
        
        # 运行优化
        from hyperopt.early_stop import no_progress_loss
        
        trials = Trials()
        best = fmin(
            fn=objective,
            space=search_space,
            algo=tpe.suggest,
            max_evals=max_evals,
            trials=trials,
            early_stop_fn=no_progress_loss(patience) if early_stop_enabled else None,
            rstate=np.random.default_rng(random_state),
            verbose=False
        )
        
        # 转换最优参数
        self.best_params = space_eval(search_space, best)
        
        best_score = -trials.best_trial['result']['loss']
        actual_evals = len(trials.trials)
        success_count = sum(1 for t in trials.trials 
                           if t['result']['status'] == 'ok' 
                           and t['result']['loss'] != float('inf'))
        is_early_stopped = actual_evals < max_evals
        
        logger.info("=" * 50)
        logger.info(f"✓ 超参数优化完成!")
        logger.info(f"  最优参数: {self.best_params}")
        logger.info(f"  最优 {metric}: {best_score:.4f}")
        logger.info(f"  总评估次数: {actual_evals}/{max_evals}")
        logger.info(f"  成功评估: {success_count}, 失败: {failed_count[0]}")
        if early_stop_enabled and is_early_stopped:
            logger.info(f"  ⚠ 提前停止: 连续 {patience} 次无改进")
        logger.info("=" * 50)
        
        # 记录优化摘要统计到 MLflow
        if mlflow.active_run():
            summary_metrics = {
                "hyperopt_summary/total_trials": actual_evals,
                "hyperopt_summary/success_count": success_count,
                "hyperopt_summary/failed_count": failed_count[0],
                "hyperopt_summary/best_score": best_score,
                "hyperopt_summary/early_stop_enabled": 1.0 if early_stop_enabled else 0.0,
            }
            if early_stop_enabled:
                summary_metrics["hyperopt_summary/early_stopped"] = 1.0 if is_early_stopped else 0.0
                summary_metrics["hyperopt_summary/patience"] = patience
            mlflow.log_metrics(summary_metrics)
        
        return self.best_params
    
    def save_mlflow(self, artifact_path: str = "model"):
        """保存模型到 MLflow
        
        Args:
            artifact_path: MLflow artifact 路径
        """
        if self.model is None:
            raise ValueError("模型未训练，无法保存")
        
        logger.info(f"保存模型到 MLflow: {artifact_path}")
        
        # 使用 mlflow.xgboost 记录模型
        mlflow.xgboost.log_model(
            self.model,
            artifact_path=artifact_path,
            registered_model_name=None  # 模型注册在 trainer 中统一处理
        )
        
        # 记录特征重要性（如果可用）
        if hasattr(self.model, "feature_importances_"):
            feature_importance = self.model.feature_importances_
            logger.info(f"特征重要性: top 10 = {np.argsort(feature_importance)[-10:][::-1]}")
        
        logger.info("模型保存完成")
    
    def get_model(self):
        """获取底层 XGBoost 模型
        
        Returns:
            XGBClassifier 对象
        """
        return self.model
