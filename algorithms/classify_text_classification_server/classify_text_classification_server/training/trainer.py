"""通用训练器 - 实现标准10步训练流程"""

import os
from pathlib import Path
from typing import Optional
import mlflow
from loguru import logger

from .config.loader import TrainingConfig
from .data_loader import load_and_split, encode_labels
from .preprocessing.text_preprocessor import ChineseTextPreprocessor
from .preprocessing.feature_engineering import TextFeatureEngineer
from .models.base import ModelRegistry
from .models.xgboost_wrapper import create_mlflow_model
from .mlflow_utils import MLFlowUtils


class UniversalTrainer:
    """通用训练器

    实现标准10步训练流程：
    1. MLflow 实验设置
    2. 数据加载
    3. 数据预处理（文本清洗+分词）
    4. 特征工程（TF-IDF + 统计特征）
    5. 模型实例化
    6. 开始 MLflow run
    7. 记录配置参数
    8. 超参数优化（Hyperopt）
    9. 模型训练
    10. 模型评估（train/val/test）
    11. 模型保存和注册
    """

    def __init__(
        self, config: TrainingConfig, dataset_path: str, run_name: Optional[str] = None
    ):
        """初始化训练器

        Args:
            config: 训练配置对象
            dataset_path: 数据集路径（文件或目录）
            run_name: MLflow run 名称（可选）
        """
        self.config = config
        self.dataset_path = dataset_path
        self.run_name = run_name

        # 初始化组件（在训练过程中创建）
        self.preprocessor: Optional[ChineseTextPreprocessor] = None
        self.feature_engineer: Optional[TextFeatureEngineer] = None
        self.model = None
        self.label_encoder = None

        logger.info("训练器初始化完成")

    def train(self):
        """执行完整训练流程"""
        logger.info("=" * 60)
        logger.info(f"开始训练 - 模型: {self.config.get('model.type')}")
        logger.info("=" * 60)

        # 步骤1: MLflow 实验设置
        self._setup_mlflow()

        # 步骤2: 数据加载
        self._load_data()

        # 步骤3: 数据预处理
        train_texts_processed, val_texts_processed, test_texts_processed = (
            self._preprocess_data(self.train_df, self.val_df, self.test_df)
        )

        # 步骤4: 特征工程
        X_train, X_val, X_test = self._feature_engineering(
            train_texts_processed,
            val_texts_processed,
            test_texts_processed,
            self.train_df["text"].tolist(),
            self.val_df["text"].tolist(),
            self.test_df["text"].tolist(),
        )

        # 编码标签
        y_train, y_val, y_test, self.label_encoder = encode_labels(
            self.train_df["label"], self.val_df["label"], self.test_df["label"]
        )

        # 步骤5: 模型实例化
        self._create_model()

        # 步骤6-11: 在 MLflow run 中执行训练
        with mlflow.start_run(run_name=self.run_name) as run:
            logger.info(f"MLflow Run ID: {run.info.run_id}")

            # 步骤7: 记录配置参数和数据统计
            self._log_config()
            self._log_dataset_statistics(y_train, y_val, y_test)

            # 步骤8: 超参数优化
            self._optimize_hyperparams(X_train, y_train, X_val, y_val)

            # 步骤9: 使用 train + val 合并数据训练最终模型
            logger.info("步骤9: 使用 train + val 合并数据训练最终模型")
            import numpy as np
            from scipy.sparse import vstack

            X_train_val = vstack([X_train, X_val])
            y_train_val = np.concatenate([y_train, y_val])
            logger.info(f"合并后训练数据: {X_train_val.shape[0]} 条样本")
            self._train_model(X_train_val, y_train_val)

            # 步骤10: 模型评估
            # 10.1 评估训练数据（train+val）拟合度（样本内评估）
            logger.info("评估训练数据（train+val）拟合度（样本内评估）...")
            train_val_metrics = self._evaluate_model(
                X_train_val, y_train_val, prefix="train_val"
            )
            # 使用 MLFlowUtils 批量记录（自动过滤内部数据）
            MLFlowUtils.log_metrics_batch(train_val_metrics, prefix="")
            # 只输出数值统计指标到日志
            train_val_summary = {
                k: v
                for k, v in train_val_metrics.items()
                if not k.startswith("_") and isinstance(v, (int, float))
            }
            logger.info(f"训练数据拟合度评估完成: {train_val_summary}")

            # 10.2 评估测试集
            logger.info("评估测试集...")
            test_metrics = self._evaluate_model(X_test, y_test, prefix="test")
            MLFlowUtils.log_metrics_batch(test_metrics, prefix="")
            # 只输出数值统计指标到日志
            test_summary = {
                k: v
                for k, v in test_metrics.items()
                if not k.startswith("_") and isinstance(v, (int, float))
            }
            logger.info(f"测试集评估完成: {test_summary}")

            # 记录混淆矩阵和分类报告（训练数据 vs 测试数据）
            class_labels = self.label_encoder.classes_.tolist()

            # 记录训练数据（train+val）的混淆矩阵和分类报告
            if "_confusion_matrix" in train_val_metrics:
                MLFlowUtils.log_confusion_matrix(
                    train_val_metrics["_confusion_matrix"],
                    labels=class_labels,
                    title="训练集+验证集混淆矩阵",
                    filename="train_val_confusion_matrix.png",
                )
            if "_classification_report" in train_val_metrics:
                MLFlowUtils.log_classification_report(
                    train_val_metrics["_classification_report"],
                    filename="train_val_classification_report.txt",
                )

            # 记录测试集的混淆矩阵和分类报告
            if "_confusion_matrix" in test_metrics:
                MLFlowUtils.log_confusion_matrix(
                    test_metrics["_confusion_matrix"],
                    labels=class_labels,
                    title="测试集混淆矩阵",
                    filename="test_confusion_matrix.png",
                )
            if "_classification_report" in test_metrics:
                MLFlowUtils.log_classification_report(
                    test_metrics["_classification_report"],
                    filename="test_classification_report.txt",
                )

            # P0-2: 记录数据分布可视化
            logger.info("记录数据分布可视化...")
            MLFlowUtils.log_class_distribution(
                y_train,
                y_val,
                y_test,
                labels=class_labels,
                dataset_names=["训练集", "验证集", "测试集"],
                title="数据集类别分布",
                filename="class_distribution.png",
            )

            # P0-3: 记录测试集错误样本分析
            logger.info("记录测试集错误样本分析...")
            y_test_pred = self.model.predict(X_test)
            y_test_proba = self.model.predict_proba(X_test)
            MLFlowUtils.log_error_analysis(
                X_texts=self.test_df["text"].tolist(),
                y_true=y_test,
                y_pred=y_test_pred,
                y_proba=y_test_proba,
                labels=class_labels,
                max_samples=100,
                filename="test_error_analysis.csv",
            )

            # P0-4: 记录特征重要性可视化
            logger.info("记录特征重要性可视化...")
            xgb_model = self.model.get_model()
            if hasattr(xgb_model, "feature_importances_"):
                feature_names = None
                if self.feature_engineer and hasattr(
                    self.feature_engineer, "get_feature_names"
                ):
                    try:
                        feature_names = self.feature_engineer.get_feature_names()
                    except:
                        pass

                MLFlowUtils.log_feature_importance(
                    feature_importance=xgb_model.feature_importances_,
                    feature_names=feature_names,
                    top_n=30,
                    title="Top 30 重要特征",
                    filename="feature_importance.png",
                )

            # P1-1: 记录 ROC 曲线（测试集）
            logger.info("记录 ROC 曲线...")
            MLFlowUtils.log_roc_curve(
                y_true=y_test,
                y_proba=y_test_proba,
                labels=class_labels,
                title="测试集 ROC 曲线",
                filename="test_roc_curve.png",
            )

            # P1-2: 记录 PR 曲线（测试集）
            logger.info("记录 PR 曲线...")
            MLFlowUtils.log_pr_curve(
                y_true=y_test,
                y_proba=y_test_proba,
                labels=class_labels,
                title="测试集 PR 曲线",
                filename="test_pr_curve.png",
            )

            # 步骤11: 模型保存和注册
            self._save_and_register_model()

            logger.info("=" * 60)
            logger.info("训练完成")
            logger.info(f"MLflow Run ID: {run.info.run_id}")
            logger.info(f"测试集指标: {test_summary}")
            logger.info("=" * 60)

    def _setup_mlflow(self):
        """步骤1: 设置 MLflow 实验"""
        logger.info("步骤1: 设置 MLflow 实验")

        tracking_uri = self.config.mlflow_tracking_uri
        experiment_name = self.config.mlflow_experiment_name

        # 使用 MLFlowUtils 统一设置
        MLFlowUtils.setup_experiment(tracking_uri, experiment_name)

        logger.info(f"MLflow 实验: {experiment_name}")
        if tracking_uri:
            logger.info(f"MLflow URI: {tracking_uri}")

    def _load_data(self):
        """步骤2: 加载数据"""
        logger.info("步骤2: 加载数据")

        train_df, val_df, test_df = load_and_split(
            self.dataset_path,
            train_ratio=0.7,
            val_ratio=0.15,
            test_ratio=0.15,
            random_state=self.config.get("hyperparams.random_state", 42),
        )

        logger.info(f"✓ 训练集: {len(train_df)} 条样本")
        logger.info(f"✓ 验证集: {len(val_df)} 条样本")
        logger.info(f"✓ 测试集: {len(test_df)} 条样本")

        # 保存为实例变量，供后续使用（如错误分析）
        self.train_df = train_df
        self.val_df = val_df
        self.test_df = test_df

        return train_df, val_df, test_df

    def _preprocess_data(self, train_df, val_df, test_df):
        """步骤3: 数据预处理"""
        logger.info("步骤3: 数据预处理（文本清洗+分词）")

        # 创建预处理器
        preprocessing_config = self.config["preprocessing"]
        self.preprocessor = ChineseTextPreprocessor(preprocessing_config)

        # 批量预处理
        train_texts_processed = self.preprocessor.preprocess_batch(
            train_df["text"].tolist()
        )
        val_texts_processed = self.preprocessor.preprocess_batch(
            val_df["text"].tolist()
        )
        test_texts_processed = self.preprocessor.preprocess_batch(
            test_df["text"].tolist()
        )

        return train_texts_processed, val_texts_processed, test_texts_processed

    def _feature_engineering(
        self,
        train_texts_processed,
        val_texts_processed,
        test_texts_processed,
        train_texts_original,
        val_texts_original,
        test_texts_original,
    ):
        """步骤4: 特征工程"""
        use_fe = self.config.get("hyperparams.use_feature_engineering", True)

        if not use_fe:
            logger.warning("步骤4: 特征工程已禁用（use_feature_engineering=false）")
            logger.warning("将直接使用预处理后的文本，性能可能受影响")
            # 返回简单的文本表示（这里需要模型支持文本输入）
            # 对于XGBoost等需要数值特征的模型，仍需基础的向量化
            # 使用最小化的TF-IDF
            from sklearn.feature_extraction.text import TfidfVectorizer

            vectorizer = TfidfVectorizer(max_features=1000)
            X_train = vectorizer.fit_transform(train_texts_processed)
            X_val = vectorizer.transform(val_texts_processed)
            X_test = vectorizer.transform(test_texts_processed)
            logger.info(f"使用基础TF-IDF特征，维度: {X_train.shape}")
            return X_train, X_val, X_test

        logger.info("步骤4: 特征工程（TF-IDF + 统计特征）")

        # 创建特征工程器
        feature_engineering_config = self.config["feature_engineering"]
        self.feature_engineer = TextFeatureEngineer(feature_engineering_config)

        # 训练并转换
        X_train = self.feature_engineer.fit_transform(
            train_texts_processed, original_texts=train_texts_original
        )

        X_val = self.feature_engineer.transform(
            val_texts_processed, original_texts=val_texts_original
        )

        X_test = self.feature_engineer.transform(
            test_texts_processed, original_texts=test_texts_original
        )

        # 显示特征维度
        dims = self.feature_engineer.get_feature_dimensions()
        logger.info(f"特征维度: {dims}")

        return X_train, X_val, X_test

    def _create_model(self):
        """步骤5: 创建模型实例"""
        logger.info("步骤5: 创建模型实例")

        model_type = self.config.get("model.type")
        model_params = self.config.get("model", {})

        # 移除非模型参数
        model_params_filtered = {
            k: v for k, v in model_params.items() if k not in ["type", "name"]
        }

        self.model = ModelRegistry.create(model_type, **model_params_filtered)

    def _log_config(self):
        """步骤7: 记录配置参数"""
        logger.info("步骤7: 记录配置参数")

        # 递归展平并记录配置参数
        config_dict = self.config.to_dict()
        flat_config = MLFlowUtils.flatten_dict(config_dict)
        MLFlowUtils.log_params_batch(flat_config)

        # 记录特征维度
        if self.feature_engineer:
            dims = self.feature_engineer.get_feature_dimensions()
            MLFlowUtils.log_params_batch({"features": dims})

        # 记录分类信息
        if self.label_encoder:
            class_labels = self.label_encoder.classes_.tolist()
            n_classes = len(class_labels)

            # 记录类别数量
            MLFlowUtils.log_params_batch(
                {
                    "classification.n_classes": n_classes,
                    "classification.class_names": ", ".join(class_labels),
                }
            )

            # 记录每个类别名称（用于详细查看）
            for idx, label in enumerate(class_labels):
                MLFlowUtils.log_params_batch({f"classification.class_{idx}": label})

            logger.info(f"✓ 记录分类信息: {n_classes} 个类别 - {class_labels}")

    def _log_dataset_statistics(self, y_train, y_val, y_test):
        """记录数据集统计信息"""
        logger.info("记录数据集统计信息")

        if self.label_encoder is None:
            return

        class_labels = self.label_encoder.classes_.tolist()

        # 统计各数据集的类别分布
        import numpy as np
        from collections import Counter

        train_dist = Counter(y_train)
        val_dist = Counter(y_val)
        test_dist = Counter(y_test)

        # 记录总体统计
        dataset_stats = {
            "dataset.train_samples": len(y_train),
            "dataset.val_samples": len(y_val),
            "dataset.test_samples": len(y_test),
            "dataset.total_samples": len(y_train) + len(y_val) + len(y_test),
        }
        MLFlowUtils.log_params_batch(dataset_stats)

        # 记录每个类别在各数据集中的分布
        for idx, label in enumerate(class_labels):
            train_count = train_dist.get(idx, 0)
            val_count = val_dist.get(idx, 0)
            test_count = test_dist.get(idx, 0)
            total_count = train_count + val_count + test_count

            # 使用 metrics 记录数量（这样可以在 UI 中对比）
            MLFlowUtils.log_metrics_batch(
                {
                    f"class_distribution/{label}/train": train_count,
                    f"class_distribution/{label}/val": val_count,
                    f"class_distribution/{label}/test": test_count,
                    f"class_distribution/{label}/total": total_count,
                    f"class_distribution/{label}/train_ratio": train_count
                    / len(y_train)
                    if len(y_train) > 0
                    else 0,
                    f"class_distribution/{label}/imbalance_ratio": total_count
                    / (len(y_train) + len(y_val) + len(y_test)),
                }
            )

        logger.info(
            f"✓ 记录数据集统计: 训练集={len(y_train)}, 验证集={len(y_val)}, 测试集={len(y_test)}"
        )

    def _optimize_hyperparams(self, X_train, y_train, X_val, y_val):
        """步骤8: 超参数优化"""
        logger.info("步骤8: 超参数优化（Hyperopt）")

        # 检查配置
        max_evals = self.config.get("hyperparams.max_evals", 0)
        logger.info(f"检查超参数优化配置: max_evals={max_evals}")

        if max_evals == 0:
            logger.info("max_evals=0，跳过超参数优化")
            return

        # 检查模型是否支持超参数优化
        if not hasattr(self.model, "optimize_hyperparams"):
            logger.warning(
                f"模型不支持超参数优化（缺少 optimize_hyperparams 方法），跳过"
            )
            return

        hyperparams_config = self.config["hyperparams"]

        try:
            logger.info(f"开始超参数优化: max_evals={max_evals}")
            best_params = self.model.optimize_hyperparams(
                X_train, y_train, X_val, y_val, hyperparams_config
            )

            if best_params:
                # 记录最优超参数
                MLFlowUtils.log_params_batch(
                    {f"best_{k}": v for k, v in best_params.items()}
                )
                logger.info(f"✓ 超参数优化完成: {best_params}")
            else:
                logger.warning("超参数优化未返回有效参数")
        except Exception as e:
            logger.error(f"超参数优化失败: {e}", exc_info=True)
            MLFlowUtils.log_params_batch(
                {"hyperopt_failed": True, "hyperopt_error": str(e)}
            )

    def _train_model(self, X_train, y_train):
        """步骤9: 训练最终模型

        注意：此时的 X_train, y_train 实际是 train+val 的合并数据
        """
        logger.info("开始训练最终模型...")

        # 最终训练不需要验证集（已经通过超参数优化确定了最优参数）
        self.model.fit(X_train, y_train, X_val=None, y_val=None)

    def _evaluate_model(self, X, y, prefix: str):
        """步骤10: 评估模型"""
        logger.info(f"评估模型（{prefix}集）")

        metrics = self.model.evaluate(X, y, prefix=prefix)

        return metrics

    def _save_and_register_model(self):
        """步骤11: 保存和注册模型"""
        logger.info("步骤11: 保存和注册模型")

        # 创建 MLflow 包装器
        mlflow_model = create_mlflow_model(
            model=self.model.get_model(),
            preprocessor=self.preprocessor,
            feature_engineer=self.feature_engineer,
            label_encoder=self.label_encoder,
        )

        # 保存模型
        artifact_path = "model"
        mlflow.pyfunc.log_model(
            artifact_path=artifact_path,
            python_model=mlflow_model,
            registered_model_name=None,  # 先不注册，稍后统一注册
        )

        logger.info("模型已保存到 MLflow")

        # 注册模型到 Model Registry
        model_name = self.config.get("model.name")
        if model_name:
            version = MLFlowUtils.register_model(
                model_name=model_name,
                artifact_path=artifact_path,
                tags={
                    "model_type": self.config.get("model.type"),
                    "framework": "xgboost",
                    "task": "text_classification",
                },
            )
            logger.info(f"模型已注册: {model_name} (version: {version})")
        else:
            logger.warning("未指定模型名称，跳过模型注册")
