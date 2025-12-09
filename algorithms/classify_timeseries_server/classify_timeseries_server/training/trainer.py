"""通用时间序列训练器

支持多种模型的统一训练流程，包括：
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
from .models.base import ModelRegistry, BaseTimeSeriesModel
from .preprocessing import TimeSeriesPreprocessor
from .data_loader import load_dataset
from .mlflow_utils import MLFlowUtils


class UniversalTrainer:
    """通用时间序列训练器
    
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
        self.frequency = None
        
        logger.info(f"训练器初始化 - 模型类型: {config.model_type}")
    
    def train(self, 
              dataset_path: str,
              val_dataset_path: Optional[str] = None,
              test_dataset_path: Optional[str] = None) -> Dict[str, Any]:
        """执行完整训练流程
        
        Args:
            dataset_path: 训练数据集路径
            val_dataset_path: 验证数据集路径（可选）
            test_dataset_path: 测试数据集路径（可选）
            
        Returns:
            训练结果字典，包含：
            - model: 训练好的模型
            - test_metrics: 测试集评估指标
            - val_metrics: 验证集评估指标（如果有）
            - run_id: MLflow run ID
            - frequency: 推断的时间频率
            - best_params: 最优超参数（如果进行了优化）
        """
        logger.info("=" * 60)
        logger.info(f"开始训练 - 模型: {self.config.model_type}")
        logger.info("=" * 60)
        
        # 1. 设置 MLflow
        self._setup_mlflow()
        
        # 2. 加载数据
        train_df, val_df, test_df = self._load_data(
            dataset_path, 
            val_dataset_path, 
            test_dataset_path
        )
        
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
                
                # 6. 超参数优化（可选）
                best_params = None
                if self.config.is_hyperopt_enabled and val_data is not None:
                    best_params = self._optimize_hyperparams(train_data, val_data)
                    mlflow.log_params(best_params)
                
                # 7. 训练模型
                self._train_model(train_data, val_data)
                
                # 8. 评估模型
                test_metrics = self._evaluate_model(test_data)
                val_metrics = None
                if val_data is not None:
                    val_metrics = self.model.evaluate(val_data)
                    mlflow.log_metrics({f"val_{k}": v for k, v in val_metrics.items()})
                
                # 9. 记录指标
                mlflow.log_metrics({f"test_{k}": v for k, v in test_metrics.items()})
                
                # 10. 保存模型
                model_uri = None
                if self.config.get("mlflow", "log_model", default=True):
                    model_uri = self._save_model_to_mlflow()
                
                # 11. 注册模型（可选）
                if self.config.get("mlflow", "register_model", default=True):
                    self._register_model(model_uri)
                
                result = {
                    'model': self.model,
                    'test_metrics': test_metrics,
                    'val_metrics': val_metrics,
                    'run_id': run.info.run_id,
                    'frequency': self.frequency,
                    'best_params': best_params,
                }
                
                logger.info("=" * 60)
                logger.info("训练完成")
                logger.info(f"测试集指标: {test_metrics}")
                logger.info(f"MLflow Run ID: {run.info.run_id}")
                logger.info("=" * 60)
                
                return result
                
            except Exception as e:
                logger.error(f"训练过程出错: {e}")
                mlflow.log_param("status", "failed")
                mlflow.log_param("error", str(e))
                raise
    
    def _setup_mlflow(self):
        """设置 MLflow 实验"""
        tracking_uri = self.config.mlflow_tracking_uri
        experiment_name = self.config.mlflow_experiment_name
        
        MLFlowUtils.setup_experiment(tracking_uri, experiment_name)
        
        logger.info(f"MLflow 实验: {experiment_name}")
        if tracking_uri:
            logger.info(f"MLflow URI: {tracking_uri}")
    
    def _load_data(self,
                   train_path: str,
                   val_path: Optional[str],
                   test_path: Optional[str]) -> Tuple[pd.DataFrame, Optional[pd.DataFrame], Optional[pd.DataFrame]]:
        """加载数据集
        
        Args:
            train_path: 训练集路径
            val_path: 验证集路径
            test_path: 测试集路径
            
        Returns:
            (训练集, 验证集, 测试集)
        """
        logger.info("加载数据...")
        
        # 加载训练集
        train_df = load_dataset(train_path)
        logger.info(f"训练集: {len(train_df)} 条记录")
        
        # 加载验证集
        val_df = None
        if val_path:
            val_df = load_dataset(val_path)
            logger.info(f"验证集: {len(val_df)} 条记录")
        
        # 加载测试集
        test_df = None
        if test_path:
            test_df = load_dataset(test_path)
            logger.info(f"测试集: {len(test_df)} 条记录")
        
        return train_df, val_df, test_df
    
    def _preprocess_data(self,
                         train_df: pd.DataFrame,
                         val_df: Optional[pd.DataFrame],
                         test_df: Optional[pd.DataFrame]) -> Tuple[pd.Series, Optional[pd.Series], pd.Series]:
        """数据预处理
        
        Args:
            train_df: 训练数据框
            val_df: 验证数据框
            test_df: 测试数据框
            
        Returns:
            (训练序列, 验证序列, 测试序列)
        """
        logger.info("数据预处理...")
        
        # 初始化预处理器
        preprocess_config = self.config.get("preprocessing", default={})
        self.preprocessor = TimeSeriesPreprocessor(
            max_missing_ratio=preprocess_config.get("max_missing_ratio", 0.3),
            interpolation_limit=preprocess_config.get("interpolation_limit", 3),
            handle_missing=preprocess_config.get("handle_missing", "interpolate")
        )
        
        # 预处理训练集
        train_df_prep, frequency = self.preprocessor.preprocess(train_df)
        self.frequency = frequency
        train_data = train_df_prep.set_index('date')['value']
        logger.info(f"训练集预处理完成: {len(train_data)} 个数据点, 频率: {frequency or '未知'}")
        
        # 预处理验证集
        val_data = None
        if val_df is not None:
            val_df_prep, _ = self.preprocessor.preprocess(val_df, frequency)
            val_data = val_df_prep.set_index('date')['value']
            logger.info(f"验证集预处理完成: {len(val_data)} 个数据点")
        
        # 预处理测试集或从训练集分割
        if test_df is not None:
            test_df_prep, _ = self.preprocessor.preprocess(test_df, frequency)
            test_data = test_df_prep.set_index('date')['value']
            logger.info(f"测试集预处理完成: {len(test_data)} 个数据点")
        else:
            # 从训练集分割测试集
            test_size = self.config.test_size
            split_point = int(len(train_data) * (1 - test_size))
            test_data = train_data[split_point:]
            train_data = train_data[:split_point]
            logger.info(f"从训练集分割测试集: 训练={len(train_data)}, 测试={len(test_data)}")
            
            # 如果需要验证集，从训练集再分割
            if val_data is None and self.config.validation_size > 0:
                val_size = self.config.validation_size
                val_split = int(len(train_data) * (1 - val_size))
                val_data = train_data[val_split:]
                train_data = train_data[:val_split]
                logger.info(f"从训练集分割验证集: 训练={len(train_data)}, 验证={len(val_data)}")
        
        return train_data, val_data, test_data
    
    def _create_model(self) -> BaseTimeSeriesModel:
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
        model_params = self.config.get("hyperparams", "fixed", default={})
        
        logger.info(f"创建模型: {model_type}")
        logger.debug(f"模型参数: {model_params}")
        
        # 实例化模型
        model = model_class(**model_params)
        
        return model
    
    def _optimize_hyperparams(self,
                              train_data: pd.Series,
                              val_data: pd.Series) -> Dict[str, Any]:
        """超参数优化
        
        Args:
            train_data: 训练数据
            val_data: 验证数据
            
        Returns:
            最优超参数字典
        """
        logger.info("开始超参数优化...")
        
        # 检查模型是否支持超参数优化
        if not hasattr(self.model, 'optimize_hyperparams'):
            logger.warning(f"{self.config.model_type} 模型不支持超参数优化，跳过")
            return {}
        
        # 执行优化
        best_params = self.model.optimize_hyperparams(train_data, val_data, self.config)
        
        logger.info(f"超参数优化完成: {best_params}")
        
        return best_params
    
    def _train_model(self,
                     train_data: pd.Series,
                     val_data: Optional[pd.Series]):
        """训练模型
        
        Args:
            train_data: 训练数据
            val_data: 验证数据（可选）
        """
        logger.info("开始训练模型...")
        
        self.model.fit(train_data, val_data)
        
        logger.info("模型训练完成")
    
    def _evaluate_model(self, test_data: pd.Series) -> Dict[str, float]:
        """评估模型
        
        Args:
            test_data: 测试数据
            
        Returns:
            评估指标字典
        """
        logger.info("评估模型...")
        
        metrics = self.model.evaluate(test_data)
        
        logger.info(f"评估完成: {metrics}")
        
        return metrics
    
    def _log_config(self):
        """记录配置到 MLflow"""
        # 记录模型配置
        mlflow.log_param("model_type", self.config.model_type)
        mlflow.log_param("model_name", self.config.model_name)
        mlflow.log_param("model_version", self.config.model_version)
        
        # 记录训练配置
        mlflow.log_param("test_size", self.config.test_size)
        mlflow.log_param("validation_size", self.config.validation_size)
        
        # 记录预处理配置
        preprocess_config = self.config.get("preprocessing", default={})
        for key, value in preprocess_config.items():
            mlflow.log_param(f"preprocessing_{key}", value)
        
        # 记录模型参数
        model_params = self.model.get_params()
        for key, value in model_params.items():
            mlflow.log_param(f"model_{key}", value)
    
    def _save_model_to_mlflow(self) -> str:
        """保存模型到 MLflow
        
        Returns:
            模型 URI
        """
        logger.info("保存模型到 MLflow...")
        
        model_type = self.config.model_type
        
        # 对于 SARIMA，使用特殊的包装器
        if model_type == "sarima":
            from .models.sarima_model import SARIMAModel
            if isinstance(self.model, SARIMAModel):
                mlflow_wrapper = self.model.get_mlflow_wrapper()
                mlflow.pyfunc.log_model(
                    artifact_path="model",
                    python_model=mlflow_wrapper
                )
                logger.info("SARIMA 模型已保存（使用 pyfunc 包装器）")
            else:
                logger.warning("模型类型不匹配，跳过保存")
        else:
            # 其他模型类型的保存逻辑（未来扩展）
            logger.warning(f"模型类型 {model_type} 的 MLflow 保存尚未实现")
        
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
            mlflow.register_model(model_uri, model_name)
            logger.info(f"模型注册成功: {model_name}")
        except Exception as e:
            logger.warning(f"模型注册失败: {e}")
    
    def predict(self, steps: int) -> np.ndarray:
        """使用训练好的模型进行预测
        
        Args:
            steps: 预测步数
            
        Returns:
            预测结果数组
            
        Raises:
            RuntimeError: 模型未训练
        """
        if self.model is None:
            raise RuntimeError("模型未训练，请先调用 train() 方法")
        
        return self.model.predict(steps)
    
    def __repr__(self) -> str:
        model_info = f"model={self.model}" if self.model else "model=None"
        return f"UniversalTrainer(model_type={self.config.model_type}, {model_info})"
