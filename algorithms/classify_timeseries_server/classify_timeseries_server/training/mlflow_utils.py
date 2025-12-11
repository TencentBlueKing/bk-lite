"""MLflow 工具类."""

from typing import Any, Dict, List, Optional, Union
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
matplotlib.rc("font", family='Microsoft YaHei')


class MLFlowUtils:
    """MLflow 工具类，提供可复用的 MLflow 操作."""
    
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
            # 过滤有效的指标值
            prefixed_metrics = {}
            for k, v in metrics.items():
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
    def log_model(
        model: Any,
        artifact_path: str,
        registered_model_name: Optional[str] = None,
        pip_requirements: Optional[List[str]] = None
    ):
        """
        记录模型到 MLflow.
        
        Args:
            model: 模型对象
            artifact_path: artifact 路径
            registered_model_name: 注册的模型名称
            pip_requirements: pip 依赖列表
        """
        mlflow.pyfunc.log_model(
            artifact_path=artifact_path,
            python_model=model,
            registered_model_name=registered_model_name,
            pip_requirements=pip_requirements
        )
        logger.info(f"模型已记录: {registered_model_name or artifact_path}")
    
    @staticmethod
    def plot_prediction_results(
        train_data: Union[pd.Series, np.ndarray],
        test_data: Union[pd.Series, np.ndarray],
        predictions: np.ndarray,
        title: str = "时间序列预测结果",
        artifact_name: str = "prediction_plot",
        metrics: Optional[Dict[str, float]] = None,
        show_confidence: bool = False,
        confidence_interval: Optional[tuple] = None
    ) -> str:
        """
        绘制时间序列预测结果图并上传到 MLflow
        
        Args:
            train_data: 训练数据 (Series 或 array)
            test_data: 测试数据 (真实值)
            predictions: 预测值
            title: 图表标题
            artifact_name: 保存的文件名(不含扩展名)
            metrics: 评估指标字典 (可选，会显示在图上)
            show_confidence: 是否显示置信区间
            confidence_interval: 置信区间 (lower, upper)
            
        Returns:
            保存的图片路径
        """

        plt.figure(figsize=(14, 6))
        
        # 准备数据索引
        if isinstance(train_data, pd.Series):
            train_index = train_data.index
            train_values = train_data.values
        else:
            train_index = range(len(train_data))
            train_values = train_data
        
        if isinstance(test_data, pd.Series):
            test_index = test_data.index
            test_values = test_data.values
        else:
            # 如果训练数据有索引,测试数据接续
            if isinstance(train_data, pd.Series) and isinstance(train_data.index, pd.DatetimeIndex):
                freq = pd.infer_freq(train_data.index) or 'D'
                test_index = pd.date_range(
                    start=train_data.index[-1] + pd.Timedelta(1, freq),
                    periods=len(test_data),
                    freq=freq
                )
            else:
                test_index = range(len(train_data), len(train_data) + len(test_data))
            test_values = test_data
        
        # 绘制训练数据
        plt.plot(train_index, train_values, 
                label='训练数据', color='#2E86AB', linewidth=1.5, alpha=0.8)
        
        # 绘制测试数据(真实值)
        plt.plot(test_index, test_values, 
                label='真实值', color='#06A77D', linewidth=2, marker='o', 
                markersize=4, alpha=0.9)
        
        # 绘制预测值
        plt.plot(test_index, predictions, 
                label='预测值', color='#F24236', linewidth=2, marker='s', 
                markersize=4, alpha=0.9, linestyle='--')
        
        # 绘制置信区间
        if show_confidence and confidence_interval is not None:
            lower, upper = confidence_interval
            plt.fill_between(test_index, lower, upper, 
                           color='#F24236', alpha=0.2, label='95% 置信区间')
        
        # 添加分割线
        if len(train_index) > 0:
            split_point = train_index[-1]
            plt.axvline(x=split_point, color='gray', linestyle=':', 
                       linewidth=1.5, alpha=0.7, label='训练/测试分割点')
        
        # 设置标题和标签
        plt.title(title, fontsize=14, fontweight='bold', pad=15)
        plt.xlabel('时间', fontsize=11)
        plt.ylabel('数值', fontsize=11)
        plt.legend(loc='best', framealpha=0.9, fontsize=10)
        plt.grid(True, alpha=0.3, linestyle='--')
        
        # 如果有评估指标,添加文本框
        if metrics:
            metrics_text = '\n'.join([f"{k.upper()}: {v:.4f}" for k, v in metrics.items()])
            plt.text(0.02, 0.98, metrics_text, 
                    transform=plt.gca().transAxes,
                    fontsize=10, verticalalignment='top',
                    bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
        
        plt.tight_layout()
        
        # 保存图片
        img_path = f"{artifact_name}.png"
        plt.savefig(img_path, dpi=150, bbox_inches='tight')
        
        # 上传到 MLflow
        if mlflow.active_run():
            mlflow.log_artifact(img_path)
            logger.info(f"预测结果图已上传到 MLflow: {img_path}")
        
        plt.close()
        
        return img_path
    
    @staticmethod
    def plot_residuals_analysis(
        residuals: np.ndarray,
        title: str = "残差分析",
        artifact_name: str = "residuals_analysis"
    ) -> str:
        """
        绘制残差分析图(包含残差分布、QQ图、ACF图)
        
        Args:
            residuals: 残差数组
            title: 图表标题
            artifact_name: 保存的文件名
            
        Returns:
            保存的图片路径
        """
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        
        # 1. 残差时间序列图
        axes[0, 0].plot(residuals, color='#2E86AB', linewidth=1)
        axes[0, 0].axhline(y=0, color='red', linestyle='--', linewidth=1.5)
        axes[0, 0].set_title('残差时间序列', fontsize=12, fontweight='bold')
        axes[0, 0].set_xlabel('时间点')
        axes[0, 0].set_ylabel('残差值')
        axes[0, 0].grid(True, alpha=0.3)
        
        # 2. 残差分布直方图
        axes[0, 1].hist(residuals, bins=30, color='#06A77D', alpha=0.7, edgecolor='black')
        axes[0, 1].axvline(x=0, color='red', linestyle='--', linewidth=1.5)
        axes[0, 1].set_title('残差分布', fontsize=12, fontweight='bold')
        axes[0, 1].set_xlabel('残差值')
        axes[0, 1].set_ylabel('频数')
        axes[0, 1].grid(True, alpha=0.3, axis='y')
        
        # 3. QQ图
        from scipy import stats
        stats.probplot(residuals, dist="norm", plot=axes[1, 0])
        axes[1, 0].set_title('QQ图 (正态性检验)', fontsize=12, fontweight='bold')
        axes[1, 0].grid(True, alpha=0.3)
        
        # 4. ACF图
        from statsmodels.graphics.tsaplots import plot_acf
        plot_acf(residuals, lags=min(40, len(residuals)//2), ax=axes[1, 1], alpha=0.05)
        axes[1, 1].set_title('残差自相关图 (ACF)', fontsize=12, fontweight='bold')
        axes[1, 1].grid(True, alpha=0.3)
        
        fig.suptitle(title, fontsize=14, fontweight='bold', y=0.995)
        plt.tight_layout()
        
        # 保存图片
        img_path = f"{artifact_name}.png"
        plt.savefig(img_path, dpi=150, bbox_inches='tight')
        
        # 上传到 MLflow
        if mlflow.active_run():
            mlflow.log_artifact(img_path)
            logger.info(f"残差分析图已上传到 MLflow: {img_path}")
        
        plt.close()
        
        return img_path
    
    @staticmethod
    def plot_forecast_comparison(
        actual_data: Union[pd.Series, np.ndarray],
        forecasts_dict: Dict[str, np.ndarray],
        title: str = "多模型预测对比",
        artifact_name: str = "forecast_comparison"
    ) -> str:
        """
        绘制多个模型的预测结果对比图
        
        Args:
            actual_data: 真实数据
            forecasts_dict: 预测结果字典 {模型名: 预测值数组}
            title: 图表标题
            artifact_name: 保存的文件名
            
        Returns:
            保存的图片路径
        """
        plt.figure(figsize=(14, 6))
        
        # 准备索引
        if isinstance(actual_data, pd.Series):
            index = actual_data.index
            values = actual_data.values
        else:
            index = range(len(actual_data))
            values = actual_data
        
        # 绘制真实值
        plt.plot(index, values, label='真实值', 
                color='black', linewidth=2.5, marker='o', markersize=5)
        
        # 颜色列表
        colors = ['#F24236', '#2E86AB', '#06A77D', '#F18F01', '#9D4EDD', '#FF006E']
        
        # 绘制各模型预测值
        for i, (model_name, forecast) in enumerate(forecasts_dict.items()):
            color = colors[i % len(colors)]
            plt.plot(index, forecast, label=model_name, 
                    color=color, linewidth=2, marker='s', 
                    markersize=4, alpha=0.8, linestyle='--')
        
        plt.title(title, fontsize=14, fontweight='bold', pad=15)
        plt.xlabel('时间', fontsize=11)
        plt.ylabel('数值', fontsize=11)
        plt.legend(loc='best', framealpha=0.9, fontsize=10)
        plt.grid(True, alpha=0.3, linestyle='--')
        plt.tight_layout()
        
        # 保存图片
        img_path = f"{artifact_name}.png"
        plt.savefig(img_path, dpi=150, bbox_inches='tight')
        
        # 上传到 MLflow
        if mlflow.active_run():
            mlflow.log_artifact(img_path)
            logger.info(f"预测对比图已上传到 MLflow: {img_path}")
        
        plt.close()
        
        return img_path
