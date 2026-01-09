"""通用异常检测训练器

支持多种异常检测模型的统一训练流程，包括：
- 数据加载和预处理
- 动态模型选择
- 超参数优化
- 模型训练和评估
- MLflow 集成
"""

from typing import Dict, Any, Optional, Tuple
import pandas as pd
import numpy as np
import mlflow
from pathlib import Path
from loguru import logger

from .config.loader import TrainingConfig
from .models.base import ModelRegistry, BaseAnomalyModel
from .preprocessing import AnomalyDataPreprocessor, AnomalyFeatureEngineer
from .data_loader import load_dataset, split_train_test
from .mlflow_utils import MLFlowUtils


class UniversalTrainer:
    """通用异常检测训练器
    
    核心功能：
    1. 配置驱动的训练流程
    2. 动态模型加载（通过 ModelRegistry）
    3. 完整的数据处理 Pipeline
    4. 可选的超参数优化
    5. MLflow 实验跟踪
    
    使用示例：
        config = TrainingConfig("train.json")
        trainer = UniversalTrainer(config)
        result = trainer.train("data.csv")
    """
    
    def __init__(self, config: TrainingConfig):
        """初始化训练器
        
        Args:
            config: 训练配置对象
        """
        self.config = config
        self.model = None
        self.preprocessor = None
        self.feature_engineer = None
        
        logger.info(f"训练器初始化 - 模型类型: {config.model_type}")
    
    def train(self, dataset_path: str) -> Dict[str, Any]:
        """执行完整训练流程
        
        数据加载支持两种模式：
        - 目录模式：dataset_path 为目录，自动查找 train_data.csv/val_data.csv/test_data.csv
        - 文件模式：dataset_path 为单个CSV文件，自动按固定比例(0.2/0.1)划分
        
        Args:
            dataset_path: 数据集路径（目录或单个文件）
            
        Returns:
            训练结果字典，包含：
            - model: 训练好的模型
            - test_metrics: 测试集评估指标
            - val_metrics: 验证集评估指标（如果有）
            - run_id: MLflow run ID
            - best_params: 最优超参数（如果进行了优化）
        """
        logger.info("=" * 60)
        logger.info(f"开始训练 - 模型: {self.config.model_type}")
        logger.info("=" * 60)
        
        # 1. 设置 MLflow
        self._setup_mlflow()
        
        # 2. 加载数据
        train_df, val_df, test_df = self._load_data(dataset_path)
        
        # 3. 数据预处理
        train_data, val_data, test_data = self._preprocess_data(
            train_df, 
            val_df, 
            test_df
        )
        
        # 4. 创建模型实例
        self.model = self._create_model()
        
        # 5. 开始 MLflow run
        with mlflow.start_run(run_name=self.config.mlflow_run_name) as run:
            try:
                # 记录配置
                self._log_config()
                
                # 6. 超参数优化（默认启用）
                best_params = None
                if val_data is not None:
                    best_params = self._optimize_hyperparams(train_data, val_data)
                    if best_params:
                        MLFlowUtils.log_params_batch(best_params)
                
                # 7. 训练模型
                self._train_model(train_data, val_data)
                
                # 8. 评估训练集拟合度（样本内评估）
                val_metrics = None
                if val_data is not None:
                    # 在训练+验证集上评估
                    final_train_data = pd.concat([train_data[0], val_data[0]], axis=0)
                    final_train_labels = pd.concat([train_data[1], val_data[1]], axis=0)
                    logger.info("评估最终训练数据拟合度（train+val样本内评估）...")
                    final_train_metrics = self.model.evaluate(
                        final_train_data, 
                        final_train_labels,
                        prefix="final_train"
                    )
                    # 使用 MLFlowUtils 批量记录（自动过滤内部数据和非数值类型）
                    MLFlowUtils.log_metrics_batch(final_train_metrics, prefix="")
                    MLFlowUtils.log_params_batch({
                        "final_train_samples": len(final_train_data),
                        "final_train_merge_val": True
                    })
                    # 只输出数值统计指标到日志
                    summary = {
                        k: v for k, v in final_train_metrics.items() 
                        if not k.startswith('_') and isinstance(v, (int, float))
                    }
                    logger.info(f"最终训练数据拟合度评估完成: {summary}")
                else:
                    # 无验证集，只评估训练集
                    logger.info("评估训练集拟合度（样本内评估）...")
                    train_metrics = self.model.evaluate(
                        train_data[0],
                        train_data[1],
                        prefix="train"
                    )
                    # 使用 MLFlowUtils 批量记录（自动过滤）
                    MLFlowUtils.log_metrics_batch(train_metrics, prefix="")
                    # 只输出数值统计指标到日志
                    summary = {
                        k: v for k, v in train_metrics.items() 
                        if not k.startswith('_') and isinstance(v, (int, float))
                    }
                    logger.info(f"训练集拟合度评估完成: {summary}")
                
                # 9. 评估测试集
                test_metrics = self._evaluate_model_on_test(test_data)
                # 使用 MLFlowUtils 批量记录（自动过滤）
                MLFlowUtils.log_metrics_batch(test_metrics, prefix="")
                
                # 10. 保存模型到 MLflow
                model_uri = self._save_model_to_mlflow()
                
                # 11. 注册模型到 MLflow Model Registry
                self._register_model(model_uri)
                
                result = {
                    'model': self.model,
                    'test_metrics': test_metrics,
                    'val_metrics': val_metrics,
                    'run_id': run.info.run_id,
                    'best_params': best_params
                }
                
                # 过滤测试集指标，只输出数值统计
                test_summary = {
                    k: v for k, v in test_metrics.items() 
                    if not k.startswith('_') and isinstance(v, (int, float))
                }
                
                logger.info("=" * 60)
                logger.info("训练完成")
                logger.info(f"MLflow Run ID: {run.info.run_id}")
                logger.info(f"测试集指标: {test_summary}")
                logger.info("=" * 60)
                
                return result
                
            except Exception as e:
                logger.error(f"训练过程出错: {e}")
                mlflow.log_param("training_failed", True)
                raise
    
    def _setup_mlflow(self):
        """设置 MLflow 实验"""
        tracking_uri = self.config.mlflow_tracking_uri
        experiment_name = self.config.mlflow_experiment_name
        
        # 使用 MLFlowUtils 统一设置
        MLFlowUtils.setup_experiment(tracking_uri, experiment_name)
    
    def _load_data(self, dataset_path: str) -> Tuple[pd.DataFrame, Optional[pd.DataFrame], pd.DataFrame]:
        """加载数据集
        
        支持两种模式：
        1. 目录模式：dataset_path 为目录
           - 必须包含 train_data.csv
           - 可选 val_data.csv 和 test_data.csv
        2. 文件模式：dataset_path 为单个 CSV 文件
           - 自动按固定比例划分（测试集 0.2，验证集 0.1）
        
        Args:
            dataset_path: 数据集路径（目录或文件）
            
        Returns:
            (训练集, 验证集, 测试集) 的 DataFrame 元组
            
        Raises:
            FileNotFoundError: 目录模式下未找到 train_data.csv
        """
        import os
        
        if os.path.isdir(dataset_path):
            # 目录模式
            logger.info(f"📁 检测到目录模式: {dataset_path}")
            
            train_path = os.path.join(dataset_path, "train_data.csv")
            if not os.path.exists(train_path):
                raise FileNotFoundError(
                    f"目录模式下未找到训练数据文件: {train_path}\n"
                    f"目录中必须包含 train_data.csv"
                )
            
            train_df = load_dataset(train_path)
            logger.info(f"✓ 训练集: {len(train_df)} 条记录 (train_data.csv)")
            
            # 可选的验证集
            val_df = None
            val_path = os.path.join(dataset_path, "val_data.csv")
            if os.path.exists(val_path):
                val_df = load_dataset(val_path)
                logger.info(f"✓ 验证集: {len(val_df)} 条记录 (val_data.csv)")
            else:
                logger.info("⚠ 未找到 val_data.csv，将从训练集自动划分")
            
            # 可选的测试集
            test_df = None
            test_path = os.path.join(dataset_path, "test_data.csv")
            if os.path.exists(test_path):
                test_df = load_dataset(test_path)
                logger.info(f"✓ 测试集: {len(test_df)} 条记录 (test_data.csv)")
            else:
                logger.info("⚠ 未找到 test_data.csv，将从训练集自动划分")
            
            return train_df, val_df, test_df
        
        elif os.path.isfile(dataset_path):
            # 文件模式
            logger.info(f"📄 检测到文件模式: {dataset_path}")
            df = load_dataset(dataset_path)
            logger.info(f"✓ 加载数据: {len(df)} 条记录")
            logger.info("ℹ 将按固定比例自动划分（测试集 0.2，验证集 0.1）")
            return df, None, None
        
        else:
            raise ValueError(
                f"无效的数据集路径: {dataset_path}\n"
                f"路径必须是以下之一：\n"
                f"  1. 包含 train_data.csv 的目录\n"
                f"  2. 单个 CSV 文件"
            )
    
    def _preprocess_data(self,
                         train_df: pd.DataFrame,
                         val_df: Optional[pd.DataFrame],
                         test_df: Optional[pd.DataFrame]) -> Tuple[Tuple[pd.DataFrame, pd.Series], 
                                                                     Optional[Tuple[pd.DataFrame, pd.Series]], 
                                                                     Tuple[pd.DataFrame, pd.Series]]:
        """数据预处理（清洗 + 特征工程 + 自动划分）
        
        如未提供测试集/验证集，从训练集按固定比例自动划分（测试集0.2，验证集0.1）。
        
        Args:
            train_df: 训练数据框（单文件模式时包含完整数据）
            val_df: 验证数据框（可选）
            test_df: 测试数据框（可选）
            
        Returns:
            ((训练特征, 训练标签), (验证特征, 验证标签), (测试特征, 测试标签))
        """
        logger.info("数据预处理（清洗 + 特征工程）...")
        
        # 1. 获取配置
        preprocess_config = self.config.preprocessing_config
        fe_config = self.config.feature_engineering_config if self.config.use_feature_engineering else {}
        label_column = self.config.label_column
        
        # 2. 创建预处理器
        self.preprocessor = AnomalyDataPreprocessor(
            max_missing_ratio=preprocess_config.get("max_missing_ratio", 0.3),
            handle_missing=preprocess_config.get("handle_missing", "interpolate")
        )
        
        logger.info(f"预处理配置: {preprocess_config}")
        
        # 3. 清洗并提取标签
        def clean_and_extract_labels(df):
            """清洗数据并提取标签"""
            cleaned_df, frequency = self.preprocessor.clean(df.copy(), label_column=label_column)
            if label_column in cleaned_df.columns:
                labels = cleaned_df.pop(label_column)
            else:
                labels = None
            return cleaned_df, labels
        
        # 处理训练集
        train_data, train_labels = clean_and_extract_labels(train_df)
        logger.info(f"训练集清洗完成: {len(train_data)} 个数据点")
        
        # 处理验证集
        val_data, val_labels = None, None
        if val_df is not None:
            val_data, val_labels = clean_and_extract_labels(val_df)
            logger.info(f"验证集清洗完成: {len(val_data)} 个数据点")
        
        # 处理测试集或从训练集分割
        if test_df is not None:
            test_data, test_labels = clean_and_extract_labels(test_df)
            logger.info(f"测试集清洗完成: {len(test_data)} 个数据点")
        else:
            # 从训练集分割测试集（20%）
            test_size = 0.2
            split_point = int(len(train_data) * (1 - test_size))
            test_data = train_data[split_point:].copy()
            test_labels = train_labels[split_point:].copy() if train_labels is not None else None
            train_data = train_data[:split_point].copy()
            train_labels = train_labels[:split_point].copy() if train_labels is not None else None
            logger.info(f"从训练集分割测试集: 训练={len(train_data)}, 测试={len(test_data)}")
            
            # 如果需要验证集，从训练集再分割（12.5% * 80% = 10%）
            if val_data is None:
                val_size = 0.125
                val_split = int(len(train_data) * (1 - val_size))
                val_data = train_data[val_split:].copy()
                val_labels = train_labels[val_split:].copy() if train_labels is not None else None
                train_data = train_data[:val_split].copy()
                train_labels = train_labels[:val_split].copy() if train_labels is not None else None
                logger.info(f"从训练集分割验证集: 训练={len(train_data)}, 验证={len(val_data)}")
        
        # 4. 特征工程（如果启用）
        if self.config.use_feature_engineering and fe_config:
            logger.info("应用特征工程...")
            self.feature_engineer = AnomalyFeatureEngineer(**fe_config)
            
            # 在训练集上拟合并转换（将 DataFrame['value'] 转为 Series）
            train_data = self.feature_engineer.fit_transform(train_data['value'])
            # 对齐标签索引（特征工程可能删除了NaN行）
            train_labels = train_labels.loc[train_data.index] if train_labels is not None else None
            logger.info(f"训练集特征工程完成: {train_data.shape[1]} 个特征, {len(train_data)} 样本")
            
            # 转换验证集和测试集
            if val_data is not None:
                val_data = self.feature_engineer.transform(val_data['value'])
                # 对齐验证集标签索引
                val_labels = val_labels.loc[val_data.index] if val_labels is not None else None
                logger.info(f"验证集特征工程完成: {val_data.shape[1]} 个特征, {len(val_data)} 样本")
            
            test_data = self.feature_engineer.transform(test_data['value'])
            # 对齐测试集标签索引
            test_labels = test_labels.loc[test_data.index] if test_labels is not None else None
            logger.info(f"测试集特征工程完成: {test_data.shape[1]} 个特征, {len(test_data)} 样本")
        
        # 5. 记录数据信息到 MLflow
        if mlflow.active_run():
            self._log_data_info(train_data, val_data, test_data, train_labels, val_labels, test_labels)
        
        logger.info("数据预处理完成")
        
        return (train_data, train_labels), (val_data, val_labels) if val_data is not None else None, (test_data, test_labels)
    
    def _log_data_info(self, train_data, val_data, test_data, train_labels, val_labels, test_labels):
        """记录数据信息到 MLflow"""
        # 数据基本信息
        if isinstance(train_data.index, pd.DatetimeIndex):
            mlflow.log_param("train_start_date", str(train_data.index[0]))
            mlflow.log_param("train_end_date", str(train_data.index[-1]))
            if val_data is not None and isinstance(val_data.index, pd.DatetimeIndex):
                mlflow.log_param("val_start_date", str(val_data.index[0]))
                mlflow.log_param("val_end_date", str(val_data.index[-1]))
            if test_data is not None and isinstance(test_data.index, pd.DatetimeIndex):
                mlflow.log_param("test_start_date", str(test_data.index[0]))
                mlflow.log_param("test_end_date", str(test_data.index[-1]))
        
        mlflow.log_param("train_samples", len(train_data))
        if val_data is not None:
            mlflow.log_param("val_samples", len(val_data))
        if test_data is not None:
            mlflow.log_param("test_samples", len(test_data))
        
        mlflow.log_param("num_features", train_data.shape[1])
        
        # 标签分布
        if train_labels is not None:
            anomaly_count = train_labels.sum()
            anomaly_ratio = anomaly_count / len(train_labels)
            mlflow.log_metric("train_anomaly_count", int(anomaly_count))
            mlflow.log_metric("train_anomaly_ratio", float(anomaly_ratio))
        
        if val_labels is not None:
            anomaly_count = val_labels.sum()
            anomaly_ratio = anomaly_count / len(val_labels)
            mlflow.log_metric("val_anomaly_count", int(anomaly_count))
            mlflow.log_metric("val_anomaly_ratio", float(anomaly_ratio))
        
        if test_labels is not None:
            anomaly_count = test_labels.sum()
            anomaly_ratio = anomaly_count / len(test_labels)
            mlflow.log_metric("test_anomaly_count", int(anomaly_count))
            mlflow.log_metric("test_anomaly_ratio", float(anomaly_ratio))
        
        logger.info("数据信息已记录到 MLflow")
    
    def _create_model(self) -> BaseAnomalyModel:
        """创建模型实例
        
        Returns:
            模型实例
            
        Raises:
            ValueError: 模型类型未注册
        """
        model_type = self.config.model_type
        
        # 从注册表获取模型类
        model_class = ModelRegistry.get(model_type)
        
        # 获取模型参数
        random_state = self.config.random_state
        
        logger.info(f"创建模型: {model_type}")
        logger.debug(f"随机种子: {random_state}")
        
        # 实例化模型
        model = model_class(random_state=random_state)
        
        return model
    
    def _optimize_hyperparams(self,
                              train_data: Tuple[pd.DataFrame, pd.Series],
                              val_data: Tuple[pd.DataFrame, pd.Series]) -> Dict[str, Any]:
        """超参数优化
        
        Args:
            train_data: (训练特征, 训练标签)
            val_data: (验证特征, 验证标签)
            
        Returns:
            最优超参数字典
        """
        logger.info("开始超参数优化...")
        
        # 检查模型是否支持超参数优化
        if not hasattr(self.model, 'optimize_hyperparams'):
            logger.warning(f"{self.config.model_type} 模型不支持超参数优化，跳过")
            return {}
        
        # 解包特征和标签
        train_X, train_y = train_data
        val_X, val_y = val_data
        
        # 检查验证集是否有标签
        if val_y is None:
            logger.warning("验证集没有标签，无法进行超参数优化，跳过")
            return {}
        
        # 执行优化（传递解包后的参数）
        best_params = self.model.optimize_hyperparams(train_X, val_X, train_y, val_y, self.config)
        
        logger.info(f"超参数优化完成: {best_params}")
        
        return best_params
    
    def _train_model(self,
                     train_data: Tuple[pd.DataFrame, pd.Series],
                     val_data: Optional[Tuple[pd.DataFrame, pd.Series]]):
        """训练模型
        
        Args:
            train_data: (训练特征, 训练标签)
            val_data: (验证特征, 验证标签)（可选）
        """
        logger.info("开始训练模型...")
        
        # 合并训练集和验证集（异常检测通常使用所有正常数据训练）
        if val_data is not None and val_data[0] is not None:
            X_train = pd.concat([train_data[0], val_data[0]], axis=0)
            y_train = pd.concat([train_data[1], val_data[1]], axis=0) if train_data[1] is not None else None
            logger.info(f"合并训练集和验证集: {len(X_train)} 个样本")
        else:
            X_train = train_data[0]
            y_train = train_data[1]
        
        self.model.fit(X_train, y_train)
        
        logger.info("模型训练完成")
    
    def _evaluate_model_on_test(self, test_data: Tuple[pd.DataFrame, pd.Series]) -> Dict[str, float]:
        """评估测试集
        
        Args:
            test_data: (测试特征, 测试标签)
            
        Returns:
            评估指标字典
        """
        logger.info("评估测试集...")
        
        X_test, y_test = test_data
        
        # 使用模型的 evaluate() 方法进行评估
        metrics = self.model.evaluate(X_test, y_test, prefix="test")
        
        # 只输出数值统计指标到日志（过滤列表和内部数据）
        summary = {
            k: v for k, v in metrics.items() 
            if not k.startswith('_') and isinstance(v, (int, float))
        }
        logger.info(f"测试集评估完成: {summary}")
        
        # 绘制可视化图表
        if mlflow.active_run():
            y_pred = self.model.predict(X_test)
            y_scores = self.model.predict_proba(X_test)
            y_true = y_test.values if hasattr(y_test, 'values') else y_test
            
            # 1. 异常检测结果图（时序可视化）
            # 使用第一个特征或索引作为时间序列值
            values = X_test.iloc[:, 0].values if X_test.shape[1] > 0 else np.arange(len(X_test))
            MLFlowUtils.plot_anomaly_detection_results(
                timestamps=X_test.index,
                values=values,
                predictions=y_pred,
                scores=y_scores,
                true_labels=y_true,
                threshold=self.model.threshold_,
                title=f"{self.config.model_type} 异常检测结果",
                artifact_name=f"{self.config.model_type}_detection",
                metrics=metrics
            )
            
            # 2. 混淆矩阵（从 metrics 中提取）
            if 'test_confusion_matrix' in metrics:
                cm = np.array(metrics['test_confusion_matrix'])
                MLFlowUtils.plot_confusion_matrix(
                    confusion_matrix=cm,
                    title=f"{self.config.model_type} 混淆矩阵",
                    artifact_name=f"{self.config.model_type}_confusion_matrix"
                )
            
            # 3. 异常分数分布（分离正常和异常样本）
            normal_mask = y_true == 0
            anomaly_mask = y_true == 1
            if normal_mask.any() and anomaly_mask.any():
                MLFlowUtils.plot_score_distribution(
                    normal_scores=y_scores[normal_mask],
                    anomaly_scores=y_scores[anomaly_mask],
                    threshold=self.model.threshold_,
                    title=f"{self.config.model_type} 异常分数分布",
                    artifact_name=f"{self.config.model_type}_score_distribution"
                )
            
            # 4. ROC 曲线（整体性能评估）
            try:
                MLFlowUtils.plot_roc_curve(
                    y_true=y_true,
                    y_scores=y_scores,
                    title=f"{self.config.model_type} ROC 曲线",
                    artifact_name=f"{self.config.model_type}_roc"
                )
            except Exception as e:
                logger.warning(f"ROC 曲线绘制失败: {e}")
            
            # 5. Precision-Recall 曲线（推荐用于不平衡数据）
            try:
                MLFlowUtils.plot_precision_recall_curve(
                    y_true=y_true,
                    y_scores=y_scores,
                    title=f"{self.config.model_type} Precision-Recall 曲线",
                    artifact_name=f"{self.config.model_type}_pr"
                )
            except Exception as e:
                logger.warning(f"PR 曲线绘制失败: {e}")
            
            # 6. ECOD 异常分数分解图（仅对ECOD模型）
            if self.config.model_type.upper() == "ECOD":
                try:
                    # 获取PyOD ECOD模型实例
                    pyod_model = self.model.model if hasattr(self.model, 'model') else None
                    if pyod_model is not None:
                        MLFlowUtils.plot_ecod_decomposition(
                            model=pyod_model,
                            X=X_test,
                            feature_names=X_test.columns.tolist(),
                            top_n=10,  # 展示异常分数最高的10个样本
                            title=f"{self.config.model_type} 异常分数分解",
                            artifact_name=f"{self.config.model_type}_decomposition"
                        )
                        logger.info("✓ ECOD分解图已生成")
                    else:
                        logger.warning("无法获取ECOD模型实例，跳过分解可视化")
                except Exception as e:
                    logger.warning(f"ECOD分解图绘制失败: {e}")
            
            logger.info("✓ 可视化图表已全部上传到 MLflow")
        
        return metrics
    
    def _log_config(self):
        """记录配置到 MLflow"""
        # 记录模型配置
        logger.info(f"记录到mlflow的模型配置: ")
        mlflow.log_param("model_type", self.config.model_type)
        mlflow.log_param("model_name", self.config.model_name)
        logger.info(f"模型配置: model_type: {self.config.model_type} model_name: {self.config.model_name}")
        
        # 记录超参数配置
        mlflow.log_param("use_feature_engineering", self.config.use_feature_engineering)
        mlflow.log_param("random_state", self.config.random_state)
        mlflow.log_param("max_evals", self.config.max_evals)
        mlflow.log_param("metric", self.config.metric)
        logger.info(f"超参数配置: use_fe={self.config.use_feature_engineering}, random_state={self.config.random_state}, max_evals={self.config.max_evals}, metric={self.config.metric}")
        
        # 记录预处理配置
        preprocess_config = self.config.preprocessing_config
        logger.info(f"预处理配置: {preprocess_config}")
        for key, value in preprocess_config.items():
            mlflow.log_param(f"preprocessing_{key}", value)
        
        # 记录特征工程配置
        if self.config.use_feature_engineering:
            fe_config = self.config.feature_engineering_config
            logger.info(f"特征工程配置: {fe_config}")
            for key, value in fe_config.items():
                if isinstance(value, (list, dict)):
                    mlflow.log_param(f"fe_{key}", str(value))
                else:
                    mlflow.log_param(f"fe_{key}", value)
    
    def _save_model_to_mlflow(self) -> str:
        """保存模型到 MLflow
        
        Returns:
            模型 URI
        """
        logger.info("保存模型到 MLflow...")
        
        model_type = self.config.model_type
        
        # 检查模型是否有 save_mlflow 方法
        if hasattr(self.model, 'save_mlflow') and callable(getattr(self.model, 'save_mlflow')):
            try:
                self.model.save_mlflow(artifact_path="model")
                logger.info(f"{model_type} 模型已保存")
            except Exception as e:
                logger.error(f"模型保存失败: {e}")
                raise
        else:
            logger.warning(f"模型类型 {model_type} 没有实现 save_mlflow 方法")
        
        model_uri = f"runs:/{mlflow.active_run().info.run_id}/model"
        return model_uri
    
    def _register_model(self, model_uri: Optional[str]):
        """注册模型到 MLflow Model Registry
        
        Args:
            model_uri: 模型 URI
        """
        if not model_uri:
            logger.warning("模型 URI 为空，跳过注册")
            return
        
        model_name = self.config.model_name
        
        try:
            logger.info(f"注册模型到 Model Registry: {model_name}")
            model_version = mlflow.register_model(model_uri, model_name)
            logger.info(f"模型注册成功: {model_name}, 版本: {model_version.version}")
        except Exception as e:
            logger.warning(f"模型注册失败: {e}")
    
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """使用训练好的模型进行预测
        
        Args:
            X: 特征数据
            
        Returns:
            预测结果数组（0=正常，1=异常）
            
        Raises:
            RuntimeError: 模型未训练
        """
        if self.model is None:
            raise RuntimeError("模型未训练，请先调用 train() 方法")
        
        return self.model.predict(X)
    
    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """使用训练好的模型预测异常得分
        
        Args:
            X: 特征数据
            
        Returns:
            异常得分数组
            
        Raises:
            RuntimeError: 模型未训练
        """
        if self.model is None:
            raise RuntimeError("模型未训练，请先调用 train() 方法")
        
        return self.model.predict_proba(X)
    
    def __repr__(self) -> str:
        model_info = f"model={self.model}" if self.model else "model=None"
        return f"UniversalTrainer(model_type={self.config.model_type}, {model_info})"
