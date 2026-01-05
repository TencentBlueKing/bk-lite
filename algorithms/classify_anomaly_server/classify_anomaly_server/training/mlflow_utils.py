"""MLflow 工具类 - 异常检测."""

from typing import Any, Dict, List, Optional, Union, Tuple
import mlflow
import mlflow.pyfunc
from loguru import logger
import math
import pandas as pd
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import io
from pathlib import Path

# 跨平台中文字体配置
matplotlib.rc("font", family=['WenQuanYi Zen Hei', 'sans-serif'])
plt.rcParams['axes.unicode_minus'] = False


class MLFlowUtils:
    """MLflow 工具类 - 异常检测专用."""
    
    @staticmethod
    def setup_experiment(tracking_uri: Optional[str], experiment_name: str):
        """
        设置 MLflow 实验.
        
        Args:
            tracking_uri: MLflow tracking 服务地址，如果为 None 则使用本地文件系统
            experiment_name: 实验名称
        """
        if tracking_uri:
            mlflow.set_tracking_uri(tracking_uri)
            logger.info(f"MLflow 跟踪地址: {tracking_uri}")
        else:
            mlflow.set_tracking_uri("file:./mlruns")
            logger.info("MLflow 跟踪地址: file:./mlruns")
        
        mlflow.set_experiment(experiment_name)
        logger.info(f"MLflow 实验: {experiment_name}")
    
    @staticmethod
    def load_model(model_name: str, model_version: str = "latest"):
        """
        从 MLflow 加载模型.
        
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
    def log_params_batch(params: Dict[str, Any]):
        """
        批量记录参数到 MLflow.
        
        Args:
            params: 参数字典
        """
        if params:
            # 过滤掉不支持的参数类型
            valid_params = {}
            for k, v in params.items():
                if isinstance(v, (str, int, float, bool)):
                    valid_params[k] = v
                elif isinstance(v, (list, tuple)):
                    valid_params[k] = str(v)
                else:
                    logger.warning(f"跳过不支持类型 {type(v)} 的参数 {k}")
            
            mlflow.log_params(valid_params)
            logger.debug(f"已记录 {len(valid_params)} 个参数")
    
    @staticmethod
    def log_metrics_batch(
        metrics: Dict[str, float], 
        prefix: str = "", 
        step: Optional[int] = None
    ):
        """
        批量记录指标到 MLflow.
        
        Args:
            metrics: 指标字典
            prefix: 指标名称前缀，如 "train_", "val_", "test_"
            step: 记录步骤（用于时间序列指标）
        """
        if metrics:
            # 过滤有效的指标值和内部数据
            prefixed_metrics = {}
            for k, v in metrics.items():
                # 跳过以 _ 开头的内部数据（如 _predictions, _scores）
                if k.startswith('_'):
                    continue
                # 跳过非数值类型
                if isinstance(v, (int, float)) and math.isfinite(v):
                    prefixed_metrics[f"{prefix}{k}"] = v
            
            if step is not None:
                for key, value in prefixed_metrics.items():
                    mlflow.log_metric(key, value, step=step)
            else:
                mlflow.log_metrics(prefixed_metrics)
            
            logger.debug(f"已记录 {len(prefixed_metrics)} 个指标 (前缀={prefix})")
    
    @staticmethod
    def log_artifact(local_path: str, artifact_path: Optional[str] = None):
        """
        记录文件到 MLflow.
        
        Args:
            local_path: 本地文件路径
            artifact_path: MLflow 中的artifact路径
        """
        mlflow.log_artifact(local_path, artifact_path)
        logger.debug(f"已记录 artifact: {local_path}")
    
    @staticmethod
    def plot_anomaly_detection_results(
        timestamps: Union[pd.DatetimeIndex, np.ndarray],
        values: np.ndarray,
        predictions: np.ndarray,
        scores: np.ndarray,
        true_labels: Optional[np.ndarray] = None,
        threshold: Optional[float] = None,
        title: str = "异常检测结果",
        artifact_name: str = "anomaly_detection_plot",
        metrics: Optional[Dict[str, float]] = None
    ) -> str:
        """
        绘制异常检测结果图并上传到 MLflow
        
        Args:
            timestamps: 时间戳索引
            values: 原始数值
            predictions: 预测标签 (0=正常, 1=异常)
            scores: 异常分数
            true_labels: 真实标签（可选）
            threshold: 异常阈值
            title: 图表标题
            artifact_name: 保存的文件名
            metrics: 评估指标字典（可选）
            
        Returns:
            保存的图片路径
        """
        fig, axes = plt.subplots(2, 1, figsize=(14, 10))
        
        # 准备索引
        if isinstance(timestamps, pd.DatetimeIndex):
            index = timestamps
        else:
            index = range(len(values))
        
        # 上图: 原始数据 + 异常标记
        ax1 = axes[0]
        
        # 绘制原始数据
        ax1.plot(index, values, color='#2E86AB', linewidth=1.5, 
                alpha=0.8, label='原始数据')
        
        # 标记预测的异常点
        anomaly_mask = predictions == 1
        if anomaly_mask.any():
            ax1.scatter(index[anomaly_mask], values[anomaly_mask], 
                       color='#F24236', s=80, marker='o', 
                       label='检测到的异常', zorder=5, alpha=0.8)
        
        # 如果有真实标签，标记真实异常点
        if true_labels is not None:
            true_anomaly_mask = true_labels == 1
            if true_anomaly_mask.any():
                ax1.scatter(index[true_anomaly_mask], values[true_anomaly_mask], 
                           color='#06A77D', s=50, marker='x', 
                           label='真实异常', zorder=4, alpha=0.8, linewidths=2)
        
        ax1.set_title(f'{title} - 数据视图', fontsize=12, fontweight='bold')
        ax1.set_xlabel('时间', fontsize=10)
        ax1.set_ylabel('数值', fontsize=10)
        ax1.legend(loc='best', framealpha=0.9, fontsize=9)
        ax1.grid(True, alpha=0.3, linestyle='--')
        
        # 下图: 异常分数
        ax2 = axes[1]
        
        # 绘制异常分数
        ax2.plot(index, scores, color='#9D4EDD', linewidth=1.5, 
                alpha=0.8, label='异常分数')
        
        # 绘制阈值线
        if threshold is not None:
            ax2.axhline(y=threshold, color='#F24236', linestyle='--', 
                       linewidth=2, label=f'阈值={threshold:.3f}', alpha=0.8)
        
        # 填充异常区域
        if anomaly_mask.any():
            # 创建异常区域的mask
            ax2.fill_between(index, 0, scores.max(), 
                            where=anomaly_mask, 
                            color='#F24236', alpha=0.2, 
                            label='异常区域')
        
        ax2.set_title('异常分数时间序列', fontsize=12, fontweight='bold')
        ax2.set_xlabel('时间', fontsize=10)
        ax2.set_ylabel('异常分数', fontsize=10)
        ax2.legend(loc='best', framealpha=0.9, fontsize=9)
        ax2.grid(True, alpha=0.3, linestyle='--')
        
        # 如果有评估指标，添加文本框
        if metrics:
            # 过滤掉内部数据
            display_metrics = {k: v for k, v in metrics.items() 
                             if not k.startswith('_') and isinstance(v, (int, float))}
            metrics_text = '\n'.join([f"{k}: {v:.4f}" for k, v in display_metrics.items()])
            ax1.text(0.02, 0.98, metrics_text, 
                    transform=ax1.transAxes,
                    fontsize=9, verticalalignment='top',
                    bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
        
        plt.tight_layout()
        
        # 保存图片
        img_path = f"{artifact_name}.png"
        plt.savefig(img_path, dpi=150, bbox_inches='tight')
        
        # 上传到 MLflow
        if mlflow.active_run():
            mlflow.log_artifact(img_path)
            logger.info(f"异常检测结果图已上传到 MLflow: {img_path}")
            
            # 清理本地临时文件
            try:
                import os
                os.remove(img_path)
                logger.debug(f"本地临时文件已删除: {img_path}")
            except Exception as e:
                logger.warning(f"删除临时文件失败: {img_path}, 错误: {e}")
        
        plt.close()
        
        return img_path
    
    @staticmethod
    def plot_confusion_matrix(
        confusion_matrix: np.ndarray,
        title: str = "混淆矩阵",
        artifact_name: str = "confusion_matrix"
    ) -> str:
        """
        绘制混淆矩阵热力图
        
        Args:
            confusion_matrix: 混淆矩阵 [[TN, FP], [FN, TP]]
            title: 图表标题
            artifact_name: 保存的文件名
            
        Returns:
            保存的图片路径
        """
        fig, ax = plt.subplots(figsize=(8, 6))
        
        # 绘制热力图
        im = ax.imshow(confusion_matrix, interpolation='nearest', cmap='Blues')
        ax.figure.colorbar(im, ax=ax)
        
        # 设置标签
        classes = ['正常', '异常']
        ax.set(xticks=np.arange(confusion_matrix.shape[1]),
               yticks=np.arange(confusion_matrix.shape[0]),
               xticklabels=classes, yticklabels=classes,
               title=title,
               ylabel='真实标签',
               xlabel='预测标签')
        
        # 旋转标签
        plt.setp(ax.get_xticklabels(), rotation=45, ha="right",
                rotation_mode="anchor")
        
        # 在每个单元格中显示数值
        fmt = 'd'
        thresh = confusion_matrix.max() / 2.
        for i in range(confusion_matrix.shape[0]):
            for j in range(confusion_matrix.shape[1]):
                ax.text(j, i, format(confusion_matrix[i, j], fmt),
                       ha="center", va="center",
                       color="white" if confusion_matrix[i, j] > thresh else "black",
                       fontsize=14, fontweight='bold')
        
        plt.tight_layout()
        
        # 保存图片
        img_path = f"{artifact_name}.png"
        plt.savefig(img_path, dpi=150, bbox_inches='tight')
        
        # 上传到 MLflow
        if mlflow.active_run():
            mlflow.log_artifact(img_path)
            logger.info(f"混淆矩阵已上传到 MLflow: {img_path}")
            
            # 清理本地临时文件
            try:
                import os
                os.remove(img_path)
            except Exception as e:
                logger.warning(f"删除临时文件失败: {img_path}, 错误: {e}")
        
        plt.close()
        
        return img_path
    
    @staticmethod
    def plot_score_distribution(
        normal_scores: np.ndarray,
        anomaly_scores: np.ndarray,
        threshold: float,
        title: str = "异常分数分布",
        artifact_name: str = "score_distribution"
    ) -> str:
        """
        绘制正常样本和异常样本的分数分布对比
        
        Args:
            normal_scores: 正常样本的异常分数
            anomaly_scores: 异常样本的异常分数
            threshold: 异常阈值
            title: 图表标题
            artifact_name: 保存的文件名
            
        Returns:
            保存的图片路径
        """
        fig, ax = plt.subplots(figsize=(10, 6))
        
        # 绘制直方图
        ax.hist(normal_scores, bins=50, alpha=0.6, color='#2E86AB', 
               label=f'正常样本 (n={len(normal_scores)})', edgecolor='black')
        ax.hist(anomaly_scores, bins=50, alpha=0.6, color='#F24236', 
               label=f'异常样本 (n={len(anomaly_scores)})', edgecolor='black')
        
        # 绘制阈值线
        ax.axvline(x=threshold, color='green', linestyle='--', 
                  linewidth=2, label=f'阈值={threshold:.3f}')
        
        ax.set_title(title, fontsize=12, fontweight='bold')
        ax.set_xlabel('异常分数', fontsize=10)
        ax.set_ylabel('频数', fontsize=10)
        ax.legend(loc='best', framealpha=0.9)
        ax.grid(True, alpha=0.3, axis='y')
        
        plt.tight_layout()
        
        # 保存图片
        img_path = f"{artifact_name}.png"
        plt.savefig(img_path, dpi=150, bbox_inches='tight')
        
        # 上传到 MLflow
        if mlflow.active_run():
            mlflow.log_artifact(img_path)
            logger.info(f"分数分布图已上传到 MLflow: {img_path}")
            
            # 清理本地临时文件
            try:
                import os
                os.remove(img_path)
            except Exception as e:
                logger.warning(f"删除临时文件失败: {img_path}, 错误: {e}")
        
        plt.close()
        
        return img_path
    
    @staticmethod
    def plot_roc_curve(
        y_true: np.ndarray,
        y_scores: np.ndarray,
        title: str = "ROC 曲线",
        artifact_name: str = "roc_curve"
    ) -> str:
        """
        绘制 ROC 曲线（Receiver Operating Characteristic）
        
        ROC 曲线展示了不同阈值下，模型的真正例率（TPR）vs 假正例率（FPR）的关系。
        适合用于整体性能评估和类别相对平衡的场景。
        
        Args:
            y_true: 真实标签 (0=正常, 1=异常)
            y_scores: 异常分数（模型输出的概率或分数）
            title: 图表标题
            artifact_name: 保存的文件名（不含扩展名）
            
        Returns:
            保存的图片路径
            
        注意:
            - AUC = 1.0: 完美模型
            - AUC = 0.5: 随机猜测（无区分能力）
            - AUC > 0.9: 优秀
            - AUC > 0.8: 良好
            - AUC > 0.7: 可接受
        """
        from sklearn.metrics import roc_curve, auc
        
        # 计算 ROC 曲线
        fpr, tpr, thresholds = roc_curve(y_true, y_scores)
        roc_auc = auc(fpr, tpr)
        
        # 绘图
        fig, ax = plt.subplots(figsize=(8, 6))
        
        # ROC 曲线
        ax.plot(fpr, tpr, color='#F24236', linewidth=2.5, 
                label=f'ROC 曲线 (AUC = {roc_auc:.3f})')
        
        # 随机猜测基准线（对角线）
        ax.plot([0, 1], [0, 1], color='gray', linestyle='--', 
                linewidth=1.5, label='随机猜测 (AUC = 0.5)')
        
        # 样式设置
        ax.set_xlim([0.0, 1.0])
        ax.set_ylim([0.0, 1.05])
        ax.set_xlabel('假正例率 (FPR)', fontsize=11)
        ax.set_ylabel('真正例率 (TPR / Recall)', fontsize=11)
        ax.set_title(title, fontsize=12, fontweight='bold')
        ax.legend(loc='lower right', framealpha=0.9, fontsize=10)
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        # 保存图片
        img_path = f"{artifact_name}.png"
        plt.savefig(img_path, dpi=150, bbox_inches='tight')
        
        # 上传到 MLflow
        if mlflow.active_run():
            mlflow.log_artifact(img_path)
            mlflow.log_metric(f"{artifact_name}_auc", roc_auc)
            logger.info(f"ROC 曲线已上传到 MLflow: {img_path}, AUC={roc_auc:.3f}")
            
            # 清理本地临时文件
            try:
                import os
                os.remove(img_path)
            except Exception as e:
                logger.warning(f"删除临时文件失败: {img_path}, 错误: {e}")
        
        plt.close()
        
        return img_path
    
    @staticmethod
    def plot_precision_recall_curve(
        y_true: np.ndarray,
        y_scores: np.ndarray,
        title: str = "Precision-Recall 曲线",
        artifact_name: str = "pr_curve"
    ) -> str:
        """
        绘制 Precision-Recall 曲线（推荐用于异常检测）
        
        PR 曲线展示了不同阈值下，模型的精确率（Precision）vs 召回率（Recall）的关系。
        特别适合类别不平衡的场景（如异常检测中异常样本很少），更能反映少数类的性能。
        
        Args:
            y_true: 真实标签 (0=正常, 1=异常)
            y_scores: 异常分数（模型输出的概率或分数）
            title: 图表标题
            artifact_name: 保存的文件名（不含扩展名）
            
        Returns:
            保存的图片路径
            
        注意:
            - AP (Average Precision): PR 曲线下的面积，越高越好
            - 比 ROC 更适合不平衡数据（异常检测的常态）
            - 基准线 = 数据集中的异常率（而非 0.5）
            
        权衡关系:
            - 高 Precision, 低 Recall: 保守策略（少误报，多漏报）
            - 低 Precision, 高 Recall: 激进策略（少漏报，多误报）
        """
        from sklearn.metrics import precision_recall_curve, average_precision_score
        
        # 计算 PR 曲线
        precision, recall, thresholds = precision_recall_curve(y_true, y_scores)
        ap = average_precision_score(y_true, y_scores)
        
        # 计算基准线（随机猜测 = 数据集中的异常率）
        baseline = y_true.sum() / len(y_true)
        
        # 绘图
        fig, ax = plt.subplots(figsize=(8, 6))
        
        # PR 曲线
        ax.plot(recall, precision, color='#06A77D', linewidth=2.5,
                label=f'PR 曲线 (AP = {ap:.3f})')
        
        # 随机猜测基准线（水平线，值为异常率）
        ax.axhline(y=baseline, color='gray', linestyle='--', linewidth=1.5,
                   label=f'随机猜测 (异常率 = {baseline:.2%})')
        
        # 样式设置
        ax.set_xlim([0.0, 1.0])
        ax.set_ylim([0.0, 1.05])
        ax.set_xlabel('召回率 (Recall)', fontsize=11)
        ax.set_ylabel('精确率 (Precision)', fontsize=11)
        ax.set_title(title, fontsize=12, fontweight='bold')
        ax.legend(loc='best', framealpha=0.9, fontsize=10)
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        # 保存图片
        img_path = f"{artifact_name}.png"
        plt.savefig(img_path, dpi=150, bbox_inches='tight')
        
        # 上传到 MLflow
        if mlflow.active_run():
            mlflow.log_artifact(img_path)
            mlflow.log_metric(f"{artifact_name}_ap", ap)
            mlflow.log_metric(f"{artifact_name}_baseline", baseline)
            logger.info(f"PR 曲线已上传到 MLflow: {img_path}, AP={ap:.3f}")
            
            # 清理本地临时文件
            try:
                import os
                os.remove(img_path)
            except Exception as e:
                logger.warning(f"删除临时文件失败: {img_path}, 错误: {e}")
        
        plt.close()
        
        return img_path
