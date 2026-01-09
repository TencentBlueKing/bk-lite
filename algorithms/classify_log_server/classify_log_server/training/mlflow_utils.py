"""MLflow 工具类 - 日志聚类."""

from typing import Any, Dict, List, Optional, Union
import mlflow
import mlflow.pyfunc
from loguru import logger
import math
import pandas as pd
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from collections import Counter
from pathlib import Path

# 跨平台中文字体配置
matplotlib.rc("font", family=['WenQuanYi Zen Hei', 'sans-serif'])
plt.rcParams['axes.unicode_minus'] = False


class MLFlowUtils:
    """MLflow 工具类 - 日志聚类专用."""
    
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
                # 跳过以 _ 开头的内部数据（如 _predictions, _cluster_details）
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
    def plot_template_distribution(
        cluster_ids: List[int],
        templates: Optional[List[str]] = None,
        title: str = "日志模板分布",
        artifact_name: str = "template_distribution",
        top_n: int = 20
    ) -> str:
        """
        绘制日志模板分布直方图（展示最常见的模板）
        
        Args:
            cluster_ids: 聚类ID列表
            templates: 模板内容列表（可选）
            title: 图表标题
            artifact_name: 保存的文件名
            top_n: 显示 Top N 个最常见的模板
            
        Returns:
            保存的图片路径
        """
        # 统计各模板出现次数
        cluster_counts = Counter(cluster_ids)
        
        # 获取 Top N
        top_clusters = cluster_counts.most_common(top_n)
        
        # 准备数据
        labels = []
        counts = []
        for cluster_id, count in top_clusters:
            if templates and cluster_id < len(templates):
                # 截断长模板
                template = templates[cluster_id]
                if len(template) > 60:
                    template = template[:60] + "..."
                labels.append(f"T{cluster_id}: {template}")
            else:
                labels.append(f"Template {cluster_id}")
            counts.append(count)
        
        # 绘图
        fig, ax = plt.subplots(figsize=(12, 8))
        
        bars = ax.barh(range(len(labels)), counts, color='#2E86AB', alpha=0.8)
        
        # 添加数值标签
        for i, (bar, count) in enumerate(zip(bars, counts)):
            width = bar.get_width()
            percentage = count / len(cluster_ids) * 100
            ax.text(width, bar.get_y() + bar.get_height()/2, 
                   f' {count} ({percentage:.1f}%)',
                   ha='left', va='center', fontsize=9)
        
        ax.set_yticks(range(len(labels)))
        ax.set_yticklabels(labels, fontsize=8)
        ax.set_xlabel('日志数量', fontsize=10)
        ax.set_title(f'{title} (Top {top_n})', fontsize=12, fontweight='bold')
        ax.grid(True, alpha=0.3, axis='x')
        
        # 反转y轴，让最常见的在上面
        ax.invert_yaxis()
        
        plt.tight_layout()
        
        # 保存图片
        img_path = f"{artifact_name}.png"
        plt.savefig(img_path, dpi=150, bbox_inches='tight')
        
        # 上传到 MLflow
        if mlflow.active_run():
            mlflow.log_artifact(img_path)
            logger.info(f"模板分布图已上传到 MLflow: {img_path}")
            
            # 清理本地临时文件
            try:
                import os
                os.remove(img_path)
            except Exception as e:
                logger.warning(f"删除临时文件失败: {img_path}, 错误: {e}")
        
        plt.close()
        
        return img_path
    
    @staticmethod
    def plot_cluster_size_distribution(
        cluster_ids: List[int],
        title: str = "聚类大小分布",
        artifact_name: str = "cluster_size_distribution"
    ) -> str:
        """
        绘制聚类大小分布（展示各个聚类的样本数量分布）
        
        Args:
            cluster_ids: 聚类ID列表
            title: 图表标题
            artifact_name: 保存的文件名
            
        Returns:
            保存的图片路径
        """
        # 统计各聚类大小
        cluster_counts = Counter(cluster_ids)
        sizes = list(cluster_counts.values())
        
        # 绘图
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
        
        # 左图: 直方图
        ax1.hist(sizes, bins=min(50, len(set(sizes))), color='#06A77D', 
                alpha=0.7, edgecolor='black')
        ax1.set_xlabel('聚类大小（日志数量）', fontsize=10)
        ax1.set_ylabel('聚类数量', fontsize=10)
        ax1.set_title('聚类大小直方图', fontsize=11, fontweight='bold')
        ax1.grid(True, alpha=0.3, axis='y')
        
        # 右图: 箱线图
        ax2.boxplot([sizes], vert=True, patch_artist=True,
                   boxprops=dict(facecolor='#F24236', alpha=0.7),
                   medianprops=dict(color='darkred', linewidth=2))
        ax2.set_ylabel('聚类大小（日志数量）', fontsize=10)
        ax2.set_title('聚类大小箱线图', fontsize=11, fontweight='bold')
        ax2.grid(True, alpha=0.3, axis='y')
        
        # 添加统计信息（调整到右上角，避免遮挡数据）
        stats_text = (
            f"总聚类数: {len(cluster_counts)}\n"
            f"平均大小: {np.mean(sizes):.1f}\n"
            f"中位数: {np.median(sizes):.0f}\n"
            f"最大: {max(sizes)}\n"
            f"最小: {min(sizes)}"
        )
        ax2.text(1.02, 0.98, stats_text, transform=ax2.transAxes,
                fontsize=9, verticalalignment='top', horizontalalignment='left',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
        
        plt.suptitle(title, fontsize=12, fontweight='bold', y=1.00)
        plt.tight_layout()
        
        # 保存图片
        img_path = f"{artifact_name}.png"
        plt.savefig(img_path, dpi=150, bbox_inches='tight')
        
        # 上传到 MLflow
        if mlflow.active_run():
            mlflow.log_artifact(img_path)
            logger.info(f"聚类大小分布图已上传到 MLflow: {img_path}")
            
            # 记录统计指标
            mlflow.log_metric("cluster_count", len(cluster_counts))
            mlflow.log_metric("cluster_size_mean", float(np.mean(sizes)))
            mlflow.log_metric("cluster_size_median", float(np.median(sizes)))
            mlflow.log_metric("cluster_size_max", int(max(sizes)))
            mlflow.log_metric("cluster_size_min", int(min(sizes)))
            
            # 清理本地临时文件
            try:
                import os
                os.remove(img_path)
            except Exception as e:
                logger.warning(f"删除临时文件失败: {img_path}, 错误: {e}")
        
        plt.close()
        
        return img_path
    
    @staticmethod
    def plot_coverage_overview(
        cluster_ids: List[int],
        noise_label: int = -1,
        title: str = "日志模板覆盖率分析",
        artifact_name: str = "coverage_overview"
    ) -> str:
        """
        绘制日志模板覆盖率概览（饼图 + 关键指标）
        
        Args:
            cluster_ids: 聚类ID列表
            noise_label: 噪声/未匹配日志的标签值（默认-1）
            title: 图表标题
            artifact_name: 保存的文件名
            
        Returns:
            保存的图片路径
        """
        total_logs = len(cluster_ids)
        if total_logs == 0:
            logger.warning("cluster_ids 为空，无法生成覆盖率可视化")
            return ""
        
        # 统计覆盖情况
        covered_count = sum(1 for cid in cluster_ids if cid != noise_label)
        uncovered_count = total_logs - covered_count
        coverage_rate = covered_count / total_logs
        
        # 统计有效聚类数（排除噪声标签）
        valid_clusters = set(cid for cid in cluster_ids if cid != noise_label)
        num_valid_clusters = len(valid_clusters)
        
        # 创建图表（1行2列：左侧饼图，右侧指标）
        fig = plt.figure(figsize=(14, 6))
        gs = fig.add_gridspec(1, 2, width_ratios=[1, 1.2])
        
        # 左侧：饼图
        ax1 = fig.add_subplot(gs[0])
        colors = ['#06A77D', '#F24236']  # 绿色（覆盖）、红色（未覆盖）
        labels = [f'已覆盖\n{covered_count:,} 条', f'未覆盖\n{uncovered_count:,} 条']
        sizes = [covered_count, uncovered_count]
        
        wedges, texts, autotexts = ax1.pie(
            sizes, 
            labels=labels, 
            colors=colors,
            autopct='%1.1f%%',
            startangle=90,
            textprops={'fontsize': 11, 'weight': 'bold'},
            explode=(0.05, 0.05)
        )
        
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontsize(13)
            autotext.set_weight('bold')
        
        ax1.set_title('覆盖率分布', fontsize=12, fontweight='bold', pad=20)
        
        # 右侧：关键指标展示
        ax2 = fig.add_subplot(gs[1])
        ax2.axis('off')
        
        # 大数字展示区域
        metrics_data = [
            ('覆盖率', f'{coverage_rate*100:.2f}%', '#06A77D'),
            ('未覆盖日志数', f'{uncovered_count:,}', '#F24236'),
            ('有效聚类数', f'{num_valid_clusters:,}', '#2E86AB'),
            ('总日志数', f'{total_logs:,}', '#555555')
        ]
        
        y_start = 0.85
        y_step = 0.20
        
        for i, (metric_name, metric_value, color) in enumerate(metrics_data):
            y_pos = y_start - i * y_step
            
            # 指标名称
            ax2.text(0.1, y_pos, metric_name, 
                    fontsize=13, color='#333333',
                    verticalalignment='top')
            
            # 指标值（大号显示）
            ax2.text(0.1, y_pos - 0.08, metric_value,
                    fontsize=28, weight='bold', color=color,
                    verticalalignment='top')
        
        # 添加健康度评估
        health_y = 0.05
        if coverage_rate >= 0.95:
            health_status = "优秀"
            health_color = '#06A77D'
            health_icon = "✓"
        elif coverage_rate >= 0.85:
            health_status = "良好"
            health_color = '#FFA500'
            health_icon = "○"
        elif coverage_rate >= 0.70:
            health_status = "一般"
            health_color = '#FF8C00'
            health_icon = "△"
        else:
            health_status = "较差"
            health_color = '#F24236'
            health_icon = "✗"
        
        ax2.text(0.1, health_y, f'健康度评估: {health_icon} {health_status}',
                fontsize=14, weight='bold', color=health_color,
                bbox=dict(boxstyle='round,pad=0.5', facecolor=health_color, 
                         alpha=0.2, edgecolor=health_color, linewidth=2))
        
        # 主标题
        fig.suptitle(title, fontsize=14, fontweight='bold', y=0.98)
        plt.tight_layout()
        
        # 保存图片
        img_path = f"{artifact_name}.png"
        plt.savefig(img_path, dpi=150, bbox_inches='tight')
        
        # 上传到 MLflow
        if mlflow.active_run():
            mlflow.log_artifact(img_path)
            logger.info(f"覆盖率分析图已上传到 MLflow: {img_path}")
            
            # 记录覆盖率指标
            mlflow.log_metric("coverage_rate", coverage_rate)
            mlflow.log_metric("uncovered_count", uncovered_count)
            mlflow.log_metric("num_valid_clusters", num_valid_clusters)
            
            # 清理本地临时文件
            try:
                import os
                os.remove(img_path)
            except Exception as e:
                logger.warning(f"删除临时文件失败: {img_path}, 错误: {e}")
        
        plt.close()
        
        return img_path
    
    @staticmethod
    def plot_clustering_metrics_comparison(
        train_metrics: Dict[str, float],
        test_metrics: Optional[Dict[str, float]] = None,
        title: str = "样本内拟合 vs 样本外泛化指标对比",
        artifact_name: str = "metrics_comparison"
    ) -> str:
        """
        绘制训练集和测试集指标对比图
        
        注：训练集包含 train+val（如果有验证集），评估的是样本内拟合度；
            测试集评估的是样本外泛化能力。
        
        Args:
            train_metrics: 训练集指标字典（final_train 或 train）
            test_metrics: 测试集指标字典（可选）
            title: 图表标题
            artifact_name: 保存的文件名
            
        Returns:
            保存的图片路径
        """
        # 过滤数值指标
        train_numerical = {k: v for k, v in train_metrics.items() 
                          if not k.startswith('_') and isinstance(v, (int, float))}
        
        if test_metrics:
            test_numerical = {k: v for k, v in test_metrics.items() 
                            if not k.startswith('_') and isinstance(v, (int, float))}
            
            # 只比较共同的指标
            common_metrics = set(train_numerical.keys()) & set(test_numerical.keys())
            metrics_to_plot = sorted(common_metrics)
        else:
            metrics_to_plot = sorted(train_numerical.keys())
        
        if not metrics_to_plot:
            logger.warning("没有可绘制的指标")
            return ""
        
        # 绘图
        fig, ax = plt.subplots(figsize=(10, 6))
        
        x = np.arange(len(metrics_to_plot))
        width = 0.35
        
        train_values = [train_numerical[m] for m in metrics_to_plot]
        
        bars1 = ax.bar(x - width/2, train_values, width, 
                      label='样本内（训练拟合）', color='#2E86AB', alpha=0.8)
        
        if test_metrics:
            test_values = [test_numerical[m] for m in metrics_to_plot]
            bars2 = ax.bar(x + width/2, test_values, width, 
                          label='样本外（测试泛化）', color='#F24236', alpha=0.8)
            
            # 添加数值标签
            for bar in bars2:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       f'{height:.3f}', ha='center', va='bottom', fontsize=8)
        
        # 添加训练集数值标签
        for bar in bars1:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{height:.3f}', ha='center', va='bottom', fontsize=8)
        
        ax.set_xlabel('指标', fontsize=10)
        ax.set_ylabel('数值', fontsize=10)
        ax.set_title(title, fontsize=12, fontweight='bold')
        ax.set_xticks(x)
        # 优化：减少倾斜角度（45° → 30°），提升可读性
        ax.set_xticklabels(metrics_to_plot, rotation=30, ha='right', fontsize=9)
        ax.legend(loc='upper left', framealpha=0.9)
        ax.grid(True, alpha=0.3, axis='y')
        
        plt.tight_layout()
        
        # 保存图片
        img_path = f"{artifact_name}.png"
        plt.savefig(img_path, dpi=150, bbox_inches='tight')
        
        # 上传到 MLflow
        if mlflow.active_run():
            mlflow.log_artifact(img_path)
            logger.info(f"指标对比图已上传到 MLflow: {img_path}")
            
            # 清理本地临时文件
            try:
                import os
                os.remove(img_path)
            except Exception as e:
                logger.warning(f"删除临时文件失败: {img_path}, 错误: {e}")
        
        plt.close()
        
        return img_path
    
    @staticmethod
    def save_templates_artifact(
        templates: List[str],
        cluster_counts: Optional[Dict[int, int]] = None,
        artifact_name: str = "templates.txt"
    ) -> str:
        """
        保存模板列表为文本文件并上传到 MLflow
        
        Args:
            templates: 模板列表
            cluster_counts: 各聚类的样本数量（可选）
            artifact_name: 文件名
            
        Returns:
            保存的文件路径
        """
        with open(artifact_name, 'w', encoding='utf-8') as f:
            f.write(f"总模板数: {len(templates)}\n")
            f.write("=" * 80 + "\n\n")
            
            for i, template in enumerate(templates):
                count_info = ""
                if cluster_counts and i in cluster_counts:
                    count_info = f" (日志数: {cluster_counts[i]})"
                
                f.write(f"模板 {i}{count_info}:\n")
                f.write(f"{template}\n")
                f.write("-" * 80 + "\n")
        
        # 上传到 MLflow
        if mlflow.active_run():
            mlflow.log_artifact(artifact_name)
            logger.info(f"模板文件已上传到 MLflow: {artifact_name}")
            
            # 清理本地临时文件
            try:
                import os
                os.remove(artifact_name)
            except Exception as e:
                logger.warning(f"删除临时文件失败: {artifact_name}, 错误: {e}")
        
        return artifact_name
    
    @staticmethod
    def flatten_dict(d: Dict[str, Any], parent_key: str = "", sep: str = ".") -> Dict[str, Any]:
        """
        展开嵌套字典为扁平结构（用于 MLflow 参数记录）
        
        Args:
            d: 嵌套字典
            parent_key: 父键前缀
            sep: 分隔符
            
        Returns:
            扁平化的字典
        """
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(MLFlowUtils.flatten_dict(v, new_key, sep=sep).items())
            else:
                items.append((new_key, v))
        return dict(items)
