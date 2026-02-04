"""MLflow 工具类 - 分类任务."""

from typing import Dict, Any, Optional
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import seaborn as sns
import mlflow
from loguru import logger
import math

# 跨平台中文字体配置
matplotlib.rc("font", family=["WenQuanYi Zen Hei", "sans-serif"])
plt.rcParams["axes.unicode_minus"] = False  # 解决负号显示问题


class MLFlowUtils:
    """MLflow 工具类 - 分类任务专用."""

    @staticmethod
    def setup_experiment(tracking_uri: Optional[str], experiment_name: str) -> str:
        """设置 MLflow 实验

        Args:
            tracking_uri: MLflow tracking URI（可选，默认使用本地文件系统）
            experiment_name: 实验名称

        Returns:
            实验 ID
        """
        if tracking_uri:
            mlflow.set_tracking_uri(tracking_uri)
            logger.info(f"MLflow 跟踪地址: {tracking_uri}")
        else:
            mlflow.set_tracking_uri("file:./mlruns")
            logger.info("MLflow 跟踪地址: file:./mlruns")

        mlflow.set_experiment(experiment_name)
        logger.info(f"MLflow 实验: {experiment_name}")

        # 创建或获取实验
        experiment = mlflow.get_experiment_by_name(experiment_name)
        if experiment is None:
            experiment_id = mlflow.create_experiment(experiment_name)
            logger.info(f"创建 MLflow 实验: {experiment_name} (ID: {experiment_id})")
        else:
            experiment_id = experiment.experiment_id
            logger.info(
                f"使用现有 MLflow 实验: {experiment_name} (ID: {experiment_id})"
            )

        return experiment_id

    @staticmethod
    def flatten_dict(d: dict, parent_key: str = "", sep: str = ".") -> dict:
        """
        递归展平嵌套字典.

        用于将多层嵌套的配置字典展平为单层字典，以便记录到 MLflow。

        Args:
            d: 待展平的字典
            parent_key: 父级键名（递归时使用）
            sep: 键名分隔符（默认为 "."）

        Returns:
            展平后的字典

        Examples:
            >>> config = {
            ...     "hyperparams": {
            ...         "search_space": {
            ...             "max_depth": [3, 5, 7]
            ...         },
            ...         "max_evals": 20
            ...     }
            ... }
            >>> MLFlowUtils.flatten_dict(config)
            {
                "hyperparams.search_space.max_depth": [3, 5, 7],
                "hyperparams.max_evals": 20
            }
        """
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k

            if isinstance(v, dict):
                # 递归展平嵌套字典
                items.extend(MLFlowUtils.flatten_dict(v, new_key, sep=sep).items())
            else:
                # 叶子节点（保留原始类型：int, float, bool, str, list, tuple）
                items.append((new_key, v))

        return dict(items)

    @staticmethod
    def log_params_batch(params: Dict[str, Any]):
        """批量记录参数到 MLflow

        Args:
            params: 参数字典（可包含嵌套结构，建议先用 flatten_dict 展平）
        """
        if not params:
            return

        # 过滤掉不支持的参数类型
        valid_params = {}

        for k, v in params.items():
            if isinstance(v, (str, int, float, bool)):
                valid_params[k] = v
            elif isinstance(v, (list, tuple)):
                str_v = str(v)
                if len(str_v) <= 500:  # MLflow 参数值长度限制
                    valid_params[k] = str_v
                else:
                    logger.warning(
                        f"参数 {k} 过长 ({len(str_v)} 字符)，已截断前500字符"
                    )
                    valid_params[k] = str_v[:497] + "..."
            else:
                logger.warning(f"跳过不支持类型 {type(v)} 的参数 {k}")

        if valid_params:
            mlflow.log_params(valid_params)
            logger.debug(f"已记录 {len(valid_params)} 个参数")

    @staticmethod
    def log_metrics_batch(
        metrics: Dict[str, float], prefix: str = "", step: Optional[int] = None
    ):
        """批量记录指标到 MLflow

        自动过滤以下划线开头的内部数据（如 _confusion_matrix）

        Args:
            metrics: 指标字典
            prefix: 指标名称前缀，如 "train_", "val_", "test_"
            step: 步数（可选）
        """
        if not metrics:
            return

        # 过滤有效的指标值和内部数据
        prefixed_metrics = {}
        for k, v in metrics.items():
            # 跳过以 _ 开头的内部数据（如 _confusion_matrix, _classification_report）
            if k.startswith("_"):
                continue
            # 跳过非数值类型和非有限值
            if isinstance(v, (int, float, np.integer, np.floating)) and math.isfinite(
                float(v)
            ):
                prefixed_metrics[f"{prefix}{k}"] = float(v)

        if not prefixed_metrics:
            logger.warning("没有有效的指标需要记录")
            return

        logger.debug(f"已记录 {len(prefixed_metrics)} 个指标 (前缀={prefix})")

        # 批量记录
        if step is not None:
            for key, value in prefixed_metrics.items():
                mlflow.log_metric(key, value, step=step)
        else:
            mlflow.log_metrics(prefixed_metrics)

    @staticmethod
    def log_confusion_matrix(
        cm: np.ndarray,
        labels: Optional[list] = None,
        title: str = "混淆矩阵",
        filename: str = "confusion_matrix.png",
    ):
        """记录混淆矩阵图到 MLflow

        Args:
            cm: 混淆矩阵 (n_classes, n_classes)
            labels: 类别标签列表（可选）
            title: 图表标题
            filename: 保存的文件名
        """
        logger.info(f"生成混淆矩阵图: {filename}")
        logger.info(f"生成混淆矩阵图: {filename}")

        plt.figure(figsize=(10, 8))

        # 使用 seaborn 绘制热力图
        sns.heatmap(
            cm,
            annot=True,
            fmt="d",
            cmap="Blues",
            xticklabels=labels if labels else range(len(cm)),
            yticklabels=labels if labels else range(len(cm)),
            cbar_kws={"label": "数量"},
        )

        plt.title(title, fontsize=14, pad=20)
        plt.xlabel("预测标签", fontsize=12)
        plt.ylabel("真实标签", fontsize=12)
        plt.tight_layout()

        # 记录到 MLflow
        mlflow.log_figure(plt.gcf(), filename)
        plt.close()

        logger.info(f"混淆矩阵图已记录: {filename}")

    @staticmethod
    def log_classification_report(
        report_text: str, filename: str = "classification_report.txt"
    ):
        """记录分类报告到 MLflow

        Args:
            report_text: 分类报告文本
            filename: 保存的文件名
        """
        logger.info(f"记录分类报告: {filename}")
        mlflow.log_text(report_text, filename)

    @staticmethod
    def log_artifact_dict(data: Dict[str, Any], filename: str):
        """将字典保存为 JSON 并记录到 MLflow

        Args:
            data: 数据字典
            filename: 保存的文件名（必须以 .json 结尾）
        """
        import json
        import tempfile
        from pathlib import Path

        if not filename.endswith(".json"):
            filename += ".json"

        logger.info(f"记录 artifact 字典: {filename}")

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / filename

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)

            mlflow.log_artifact(str(filepath))

    @staticmethod
    def log_class_distribution(
        *datasets,
        labels: Optional[list] = None,
        dataset_names: Optional[list] = None,
        title: str = "类别分布",
        filename: str = "class_distribution.png",
    ):
        """记录类别分布图到 MLflow

        Args:
            *datasets: 数据集标签数组（可以传入多个，如 train_labels, val_labels, test_labels）
            labels: 类别标签名称列表（可选）
            dataset_names: 数据集名称列表（如 ['训练集', '验证集', '测试集']）
            title: 图表标题
            filename: 保存的文件名
        """
        import pandas as pd

        logger.info(f"生成类别分布图: {filename}")

        if dataset_names is None:
            dataset_names = [f"数据集 {i + 1}" for i in range(len(datasets))]

        # 准备数据
        distribution_data = []
        for dataset, name in zip(datasets, dataset_names):
            unique, counts = np.unique(dataset, return_counts=True)
            for cls, count in zip(unique, counts):
                cls_label = labels[cls] if labels and cls < len(labels) else str(cls)
                distribution_data.append(
                    {"Class": cls_label, "Count": count, "Dataset": name}
                )

        df = pd.DataFrame(distribution_data)

        # 绘制分组柱状图
        fig, ax = plt.subplots(figsize=(12, 6))

        # 获取唯一类别和数据集
        classes = df["Class"].unique()
        n_classes = len(classes)
        n_datasets = len(dataset_names)

        x = np.arange(n_classes)
        width = 0.8 / n_datasets

        colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"]

        for i, dataset_name in enumerate(dataset_names):
            data = df[df["Dataset"] == dataset_name]
            counts = [
                data[data["Class"] == cls]["Count"].values[0]
                if cls in data["Class"].values
                else 0
                for cls in classes
            ]
            offset = width * (i - n_datasets / 2 + 0.5)
            ax.bar(
                x + offset,
                counts,
                width,
                label=dataset_name,
                color=colors[i % len(colors)],
            )

        ax.set_xlabel("类别", fontsize=12)
        ax.set_ylabel("数量", fontsize=12)
        ax.set_title(title, fontsize=14, pad=20)
        ax.set_xticks(x)
        ax.set_xticklabels(
            classes,
            rotation=45 if n_classes > 10 else 0,
            ha="right" if n_classes > 10 else "center",
        )
        ax.legend()
        ax.grid(axis="y", alpha=0.3)

        plt.tight_layout()
        mlflow.log_figure(plt.gcf(), filename)
        plt.close()

        logger.info(f"类别分布图已记录: {filename}")

    @staticmethod
    def log_error_analysis(
        X_texts,
        y_true,
        y_pred,
        y_proba,
        labels: Optional[list] = None,
        max_samples: int = 100,
        filename: str = "error_analysis.csv",
    ):
        """记录错误样本分析到 MLflow

        Args:
            X_texts: 原始文本列表
            y_true: 真实标签
            y_pred: 预测标签
            y_proba: 预测概率矩阵
            labels: 类别标签名称列表（可选）
            max_samples: 最大记录样本数
            filename: 保存的文件名
        """
        import pandas as pd
        import tempfile
        from pathlib import Path

        logger.info(f"生成错误样本分析: {filename}")

        # 找出错误样本
        error_indices = np.where(y_true != y_pred)[0]

        if len(error_indices) == 0:
            logger.info("没有错误样本，跳过错误分析")
            return

        logger.info(f"发现 {len(error_indices)} 个错误样本")

        # 限制样本数量
        if len(error_indices) > max_samples:
            # 优先选择低置信度的错误样本
            confidences = y_proba[error_indices].max(axis=1)
            sorted_indices = error_indices[np.argsort(confidences)[:max_samples]]
        else:
            sorted_indices = error_indices

        # 构建错误分析数据
        error_data = []
        for idx in sorted_indices:
            true_label = labels[y_true[idx]] if labels else str(y_true[idx])
            pred_label = labels[y_pred[idx]] if labels else str(y_pred[idx])
            confidence = y_proba[idx][y_pred[idx]]
            true_prob = y_proba[idx][y_true[idx]]

            error_data.append(
                {
                    "text": X_texts[idx][:200]
                    if len(X_texts[idx]) > 200
                    else X_texts[idx],  # 截断长文本
                    "true_label": true_label,
                    "pred_label": pred_label,
                    "confidence": f"{confidence:.4f}",
                    "true_prob": f"{true_prob:.4f}",
                    "prob_diff": f"{confidence - true_prob:.4f}",
                }
            )

        df = pd.DataFrame(error_data)

        # 保存为 CSV
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / filename
            df.to_csv(filepath, index=False, encoding="utf-8-sig")
            mlflow.log_artifact(str(filepath))

        logger.info(f"错误样本分析已记录: {filename} ({len(error_data)} 个样本)")

    @staticmethod
    def log_feature_importance(
        feature_importance,
        feature_names: Optional[list] = None,
        top_n: int = 30,
        title: str = "特征重要性",
        filename: str = "feature_importance.png",
    ):
        """记录特征重要性图到 MLflow

        Args:
            feature_importance: 特征重要性数组
            feature_names: 特征名称列表（可选）
            top_n: 显示前 N 个最重要的特征
            title: 图表标题
            filename: 保存的文件名
        """
        logger.info(f"生成特征重要性图: {filename}")

        # 获取 top N 特征
        top_indices = np.argsort(feature_importance)[-top_n:][::-1]
        top_importance = feature_importance[top_indices]

        if feature_names:
            top_features = [
                feature_names[i] if i < len(feature_names) else f"特征_{i}"
                for i in top_indices
            ]
        else:
            top_features = [f"特征_{i}" for i in top_indices]

        # 绘制水平柱状图
        fig, ax = plt.subplots(figsize=(10, max(6, top_n * 0.3)))

        y_pos = np.arange(len(top_features))
        ax.barh(y_pos, top_importance, color="steelblue")
        ax.set_yticks(y_pos)
        ax.set_yticklabels(top_features, fontsize=9)
        ax.invert_yaxis()
        ax.set_xlabel("重要性", fontsize=12)
        ax.set_title(title, fontsize=14, pad=20)
        ax.grid(axis="x", alpha=0.3)

        plt.tight_layout()
        mlflow.log_figure(plt.gcf(), filename)
        plt.close()

        logger.info(f"特征重要性图已记录: {filename}")

    @staticmethod
    def log_roc_curve(
        y_true,
        y_proba,
        labels: Optional[list] = None,
        title: str = "ROC 曲线",
        filename: str = "roc_curve.png",
    ):
        """记录 ROC 曲线到 MLflow（支持多分类 OVR）

        Args:
            y_true: 真实标签（整数编码）
            y_proba: 预测概率矩阵 (n_samples, n_classes)
            labels: 类别标签名称列表（可选）
            title: 图表标题
            filename: 保存的文件名
        """
        from sklearn.metrics import roc_curve, auc
        from sklearn.preprocessing import label_binarize

        logger.info(f"生成 ROC 曲线: {filename}")

        n_classes = y_proba.shape[1]

        # 二值化标签（用于 OVR）
        y_true_bin = label_binarize(y_true, classes=range(n_classes))

        # 计算每个类别的 ROC 曲线和 AUC
        fpr = dict()
        tpr = dict()
        roc_auc = dict()

        for i in range(n_classes):
            fpr[i], tpr[i], _ = roc_curve(y_true_bin[:, i], y_proba[:, i])
            roc_auc[i] = auc(fpr[i], tpr[i])

        # 计算 macro-average ROC 曲线和 AUC
        all_fpr = np.unique(np.concatenate([fpr[i] for i in range(n_classes)]))
        mean_tpr = np.zeros_like(all_fpr)
        for i in range(n_classes):
            mean_tpr += np.interp(all_fpr, fpr[i], tpr[i])
        mean_tpr /= n_classes
        fpr["macro"] = all_fpr
        tpr["macro"] = mean_tpr
        roc_auc["macro"] = auc(fpr["macro"], tpr["macro"])

        # 绘图
        fig, ax = plt.subplots(figsize=(10, 8))

        # 绘制对角线（随机分类器）
        ax.plot([0, 1], [0, 1], "k--", lw=2, label="随机分类器 (AUC = 0.50)")

        # 绘制 macro-average ROC 曲线
        ax.plot(
            fpr["macro"],
            tpr["macro"],
            label=f"Macro-average (AUC = {roc_auc['macro']:.3f})",
            color="navy",
            linestyle="--",
            linewidth=2,
        )

        # 绘制每个类别的 ROC 曲线
        colors = plt.cm.Set1(np.linspace(0, 1, n_classes))
        for i, color in zip(range(n_classes), colors):
            class_label = labels[i] if labels and i < len(labels) else f"类别 {i}"
            ax.plot(
                fpr[i],
                tpr[i],
                color=color,
                lw=2,
                label=f"{class_label} (AUC = {roc_auc[i]:.3f})",
            )

        ax.set_xlim([0.0, 1.0])
        ax.set_ylim([0.0, 1.05])
        ax.set_xlabel("假正例率 (FPR)", fontsize=12)
        ax.set_ylabel("真正例率 (TPR)", fontsize=12)
        ax.set_title(title, fontsize=14, pad=20)
        ax.legend(loc="lower right", fontsize=9)
        ax.grid(alpha=0.3)

        plt.tight_layout()
        mlflow.log_figure(plt.gcf(), filename)
        plt.close()

        # 记录 AUC 值到 metrics
        prefix = filename.replace(".png", "").replace("_", "/")
        mlflow.log_metric(f"{prefix}/macro_auc", roc_auc["macro"])
        for i in range(n_classes):
            class_label = labels[i] if labels and i < len(labels) else f"class_{i}"
            mlflow.log_metric(f"{prefix}/{class_label}_auc", roc_auc[i])

        logger.info(f"ROC 曲线已记录: {filename} (Macro AUC = {roc_auc['macro']:.3f})")

    @staticmethod
    def log_pr_curve(
        y_true,
        y_proba,
        labels: Optional[list] = None,
        title: str = "PR 曲线",
        filename: str = "pr_curve.png",
    ):
        """记录 Precision-Recall 曲线到 MLflow（支持多分类 OVR）

        Args:
            y_true: 真实标签（整数编码）
            y_proba: 预测概率矩阵 (n_samples, n_classes)
            labels: 类别标签名称列表（可选）
            title: 图表标题
            filename: 保存的文件名
        """
        from sklearn.metrics import precision_recall_curve, average_precision_score
        from sklearn.preprocessing import label_binarize

        logger.info(f"生成 PR 曲线: {filename}")

        n_classes = y_proba.shape[1]

        # 二值化标签（用于 OVR）
        y_true_bin = label_binarize(y_true, classes=range(n_classes))

        # 计算每个类别的 PR 曲线和 AP
        precision = dict()
        recall = dict()
        ap = dict()

        for i in range(n_classes):
            precision[i], recall[i], _ = precision_recall_curve(
                y_true_bin[:, i], y_proba[:, i]
            )
            ap[i] = average_precision_score(y_true_bin[:, i], y_proba[:, i])

        # 计算 macro-average AP
        ap["macro"] = np.mean([ap[i] for i in range(n_classes)])

        # 绘图
        fig, ax = plt.subplots(figsize=(10, 8))

        # 绘制每个类别的 PR 曲线
        colors = plt.cm.Set1(np.linspace(0, 1, n_classes))
        for i, color in zip(range(n_classes), colors):
            class_label = labels[i] if labels and i < len(labels) else f"类别 {i}"
            ax.plot(
                recall[i],
                precision[i],
                color=color,
                lw=2,
                label=f"{class_label} (AP = {ap[i]:.3f})",
            )

        # 添加 macro-average 信息到标题
        ax.set_xlim([0.0, 1.0])
        ax.set_ylim([0.0, 1.05])
        ax.set_xlabel("召回率 (Recall)", fontsize=12)
        ax.set_ylabel("精确率 (Precision)", fontsize=12)
        ax.set_title(
            f"{title}\nMacro-Average AP = {ap['macro']:.3f}", fontsize=14, pad=20
        )
        ax.legend(loc="best", fontsize=9)
        ax.grid(alpha=0.3)

        plt.tight_layout()
        mlflow.log_figure(plt.gcf(), filename)
        plt.close()

        # 记录 AP 值到 metrics
        prefix = filename.replace(".png", "").replace("_", "/")
        mlflow.log_metric(f"{prefix}/macro_ap", ap["macro"])
        for i in range(n_classes):
            class_label = labels[i] if labels and i < len(labels) else f"class_{i}"
            mlflow.log_metric(f"{prefix}/{class_label}_ap", ap[i])

        logger.info(f"PR 曲线已记录: {filename} (Macro AP = {ap['macro']:.3f})")

    @staticmethod
    def load_model(model_name: str, model_version: str = "latest"):
        """从 MLflow 加载模型

        Args:
            model_name: 模型名称
            model_version: 模型版本，默认为 "latest"

        Returns:
            加载的模型对象
        """
        model_uri = f"models:/{model_name}/{model_version}"
        logger.info(f"从以下位置加载模型: {model_uri}")
        return mlflow.pyfunc.load_model(model_uri)

    @staticmethod
    def register_model(
        model_name: str,
        run_id: Optional[str] = None,
        artifact_path: str = "model",
        tags: Optional[Dict[str, str]] = None,
    ) -> str:
        """注册模型到 MLflow Model Registry

        Args:
            model_name: 模型注册名称
            run_id: MLflow run ID（如果为 None，使用当前 active run）
            artifact_path: 模型 artifact 路径
            tags: 模型标签（可选）

        Returns:
            模型版本号
        """
        if run_id is None:
            run_id = mlflow.active_run().info.run_id

        model_uri = f"runs:/{run_id}/{artifact_path}"

        logger.info(f"注册模型到 Model Registry: {model_name}")
        logger.info(f"模型 URI: {model_uri}")

        # 注册模型
        model_version = mlflow.register_model(model_uri, model_name)

        # 添加标签
        if tags:
            client = mlflow.tracking.MlflowClient()
            for key, value in tags.items():
                client.set_model_version_tag(
                    name=model_name, version=model_version.version, key=key, value=value
                )

        logger.info(f"模型注册成功: {model_name} (version: {model_version.version})")

        return model_version.version


def _flatten_dict(
    d: Dict[str, Any], parent_key: str = "", sep: str = "."
) -> Dict[str, Any]:
    """扁平化嵌套字典

    Args:
        d: 嵌套字典
        parent_key: 父键（用于递归）
        sep: 分隔符

    Returns:
        扁平化后的字典
    """
    items = []

    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k

        if isinstance(v, dict):
            items.extend(_flatten_dict(v, new_key, sep=sep).items())
        else:
            # 转换为字符串（MLflow 参数只支持字符串）
            items.append((new_key, str(v)))

    return dict(items)
