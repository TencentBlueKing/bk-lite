import numpy as np
import pandas as pd
from scipy.special import expit
from sklearn.metrics import (
    precision_recall_fscore_support,
    roc_auc_score,
    accuracy_score
)
from typing import Dict, Any, Callable
from hyperopt import hp, STATUS_OK, space_eval
from loguru import logger

class MLUtils:
    
    @staticmethod
    def get_prediction_scores(model, X: pd.DataFrame) -> np.ndarray:
        """获取模型预测分数
        
        Args:
            model: 训练好的模型对象
            X: 特征数据
            
        Returns:
            预测分数数组，范围通常在 [0, 1] 之间
        """
        if hasattr(model, "predict_proba"):
            proba = model.predict_proba(X)
            if isinstance(proba, np.ndarray) and proba.ndim == 2 and proba.shape[1] >= 2:
                return proba[:, 1]
            else:
                return model.predict(X).astype(float)
        elif hasattr(model, "decision_function"):
            decision_scores = model.decision_function(X)
            return expit(decision_scores)
        else:
            return model.predict(X).astype(float)

    @staticmethod
    def calculate_metric_score(
        y_true: pd.Series,
        scores: np.ndarray,
        metric: str,
        threshold: float,
        positive_label: int
    ) -> float:
        """计算指定指标的分数
        
        Args:
            y_true: 真实标签
            scores: 预测分数
            metric: 指标名称 ("f1", "precision", "recall", "accuracy", "auc")
            threshold: 分类阈值
            positive_label: 正类标签
            
        Returns:
            指标分数
            
        Raises:
            ValueError: 当指标名称不支持时
        """
        metric = metric.lower()
        scores = np.asarray(scores)
        is_continuous = (np.issubdtype(scores.dtype, np.floating) and
                         np.unique(scores).size > 2)

        if metric == "auc" and is_continuous:
            return roc_auc_score(y_true, scores)

        # 其他指标需要离散预测
        y_pred = ((scores >= threshold).astype(int) if is_continuous
                  else scores.astype(int))

        if metric == "auc":  # 离散情况下的AUC用准确率代替
            return accuracy_score(y_true, y_pred)

        P, R, F1, _ = precision_recall_fscore_support(
            y_true, y_pred, pos_label=positive_label, average="binary", zero_division=0
        )

        metric_map = {
            "f1": F1,
            "precision": P,
            "recall": R,
            "accuracy": accuracy_score(y_true, y_pred)
        }

        if metric not in metric_map:
            raise ValueError(f"不支持的指标: {metric}")

        return metric_map[metric]

    @staticmethod
    def apply_threshold(scores: np.ndarray, threshold: float) -> np.ndarray:
        """根据阈值生成离散标签
        
        Args:
            scores: 预测分数数组
            threshold: 分类阈值
            
        Returns:
            离散标签数组
        """
        scores = np.asarray(scores)
        if np.issubdtype(scores.dtype, np.floating) and (np.unique(scores).size > 2):
            return (scores >= threshold).astype(int)
        else:
            return scores.astype(int)

    @staticmethod
    def build_search_space(train_config: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """根据训练配置构建 Hyperopt 搜索空间

        Args:
            train_config: 训练配置字典，格式如:
                {
                    "param1": {"type": "randint", "min": 1, "max": 10},
                    "param2": {"type": "choice", "choice": ["a", "b", "c"]},
                }

        Returns:
            Hyperopt 搜索空间字典

        Raises:
            ValueError: 当参数配置无效时
        """
        space = {}

        for key, cfg in train_config.items():
            param_type = str(cfg.get("type", "")).lower()

            if param_type == "randint":
                vmin, vmax = int(cfg["min"]), int(cfg["max"])
                if vmax < vmin:
                    raise ValueError(f"参数 {key}: max({vmax}) < min({vmin})")
                space[key] = hp.randint(key, vmax - vmin + 1) + vmin

            elif param_type == "choice":
                opts = []
                for c in cfg["choice"]:
                    if isinstance(c, str):
                        lc = c.strip().lower()
                        if lc == "none":
                            opts.append(None)
                        elif lc == "true":
                            opts.append(True)
                        elif lc == "false":
                            opts.append(False)
                        else:
                            opts.append(c)
                    else:
                        opts.append(c)
                space[key] = hp.choice(key, opts)

            else:
                logger.warning(f"不支持的参数类型: {param_type} for {key}")

        if space:
            logger.info(f"构建超参数搜索空间: {list(space.keys())}")

        return space

    @staticmethod
    def create_hyperopt_objective(
        evaluate_func: Callable,
        space: Dict[str, Any],
        maximize: bool = True
    ) -> Callable:
        """创建通用的 Hyperopt 目标函数
        
        Args:
            evaluate_func: 评估函数，接收解析后的参数字典，返回分数
            space: Hyperopt 搜索空间
            maximize: 是否最大化目标（True=最大化，False=最小化）
            
        Returns:
            可用于 Hyperopt 的目标函数
        """
        def objective(params_raw):
            try:
                params = space_eval(space, params_raw)
                score = evaluate_func(params)
                
                # Hyperopt 总是最小化，所以最大化时需要取负值
                loss = -float(score) if maximize else float(score)
                return {"loss": loss, "status": STATUS_OK}
                
            except Exception as e:
                logger.error(f"超参数评估失败: {e}")
                return {"loss": float('inf') if not maximize else -float('inf'), "status": STATUS_OK}
        
        return objective
    
    @staticmethod
    def create_model_evaluator(
        build_model_func: Callable,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: pd.DataFrame,
        y_val: pd.Series,
        metric: str = "f1",
        threshold: float = 0.5,
        positive_label: int = 1,
        history_callback: Callable = None
    ) -> Callable:
        """创建标准的模型评估函数
        
        Args:
            build_model_func: 构建模型的函数
            X_train, y_train: 训练数据
            X_val, y_val: 验证数据  
            metric: 评估指标
            threshold: 分类阈值
            positive_label: 正类标签
            history_callback: 可选的回调函数，用于记录训练历史
            
        Returns:
            评估函数，接收参数字典并返回验证分数
        """
        def evaluate(params):
            model = build_model_func(train_params=params)
            model.fit(X_train, y_train)
            
            # 计算验证分数
            val_scores = MLUtils.get_prediction_scores(model, X_val)
            val_score = MLUtils.calculate_metric_score(
                y_val, val_scores, metric, threshold, positive_label
            )
            
            # 可选：记录训练历史
            if history_callback:
                train_scores = MLUtils.get_prediction_scores(model, X_train)
                train_score = MLUtils.calculate_metric_score(
                    y_train, train_scores, metric, threshold, positive_label
                )
                history_callback(train_score, val_score)
            
            return val_score
            
        return evaluate