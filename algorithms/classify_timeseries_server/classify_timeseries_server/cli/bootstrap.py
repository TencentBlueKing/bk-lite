from dotenv import load_dotenv
import fire
from loguru import logger
from pathlib import Path
import json

load_dotenv()


class CLI:
    """命令行工具."""
    
    def train(
        self,
        dataset_path: str,
        algorithm: str = "sarima",
        hyperparams: str = None,
        experiment_name: str = "timeseries_training",
        run_name: str = None,
        model_name: str = None,
        test_size: float = 0.2,
        mlflow_tracking_uri: str = None,
        max_evals: int = 0,
        optimization_metric: str = "rmse",
    ):
        """
        训练时间序列模型.
        
        Args:
            dataset_path: 数据集文件或文件夹路径
            algorithm: 算法名称，默认 sarima（未来支持 prophet、lstm 等）
            hyperparams: 超参数 JSON 文件路径，支持固定值或搜索范围定义
            experiment_name: MLflow 实验名称
            run_name: MLflow run 名称（可选）
            model_name: 注册到 MLflow 的模型名称（可选）
            test_size: 测试集比例，默认 0.2
            mlflow_tracking_uri: MLflow tracking 服务地址，如 http://127.0.0.1:15000
            max_evals: 超参数优化轮次 (0=不优化, >0=优化轮次)，默认 0
            optimization_metric: 优化目标指标 (rmse/mae/mape)，默认 rmse
            
        Example:
            classify_timeseries_server train --dataset-path ./data/train.csv
            classify_timeseries_server train --algorithm sarima --dataset-path ./data --hyperparams ./params.json --mlflow-tracking-uri http://127.0.0.1:15000
        """
        from ..training import load_dataset, TimeSeriesTrainer
        from ..training.algorithms import SARIMAAlgorithm
        
        # 确保参数类型正确
        test_size = float(test_size)
        algorithm = algorithm.lower()
        
        # 从环境变量获取 MLflow URI（如果未通过参数传递）
        if mlflow_tracking_uri is None:
            import os
            mlflow_tracking_uri = os.getenv("MLFLOW_TRACKING_URI")
        
        logger.info(f"=== Starting {algorithm.upper()} Training ===")
        logger.info(f"Algorithm: {algorithm}")
        logger.info(f"Dataset path: {dataset_path}")
        logger.info(f"Experiment: {experiment_name}")
        logger.info(f"Test size: {test_size}")
        if mlflow_tracking_uri:
            logger.info(f"MLflow Tracking URI: {mlflow_tracking_uri}")
        
        try:
            # 加载数据
            logger.info("Loading dataset...")
            df = load_dataset(dataset_path)
            
            # 加载超参数
            if hyperparams and Path(hyperparams).exists():
                logger.info(f"Loading hyperparameters from: {hyperparams}")
                with open(hyperparams, 'r', encoding='utf-8') as f:
                    params = json.load(f)
                    # 移除注释字段
                    params.pop('comments', None)
            else:
                logger.info("Using default hyperparameters")
                # SARIMA 默认参数
                params = {
                    'order': [1, 1, 1],
                    'seasonal_order': [1, 1, 1, 12],
                    'trend': 'c',
                }
            
            logger.info(f"Hyperparameters: {params}")
            
            # 创建算法实例（目前仅支持 SARIMA）
            if algorithm == "sarima":
                algo = SARIMAAlgorithm()
            else:
                raise ValueError(f"Unsupported algorithm: {algorithm}. Currently only 'sarima' is supported.")
            
            # 训练模型
            trainer = TimeSeriesTrainer(algo)
            result = trainer.train(
                model_name=model_name or f"{algorithm}_model",
                train_dataframe=df,
                train_config=params,
                experiment_name=experiment_name,
                test_size=test_size,
                mlflow_tracking_uri=mlflow_tracking_uri,
                max_evals=max_evals,
                optimization_metric=optimization_metric,
            )
            
            model = result["model"]
            metrics = result["test_metrics"]
            
            logger.info("=== Training completed successfully ===")
            logger.info(f"Metrics: {metrics}")
            
            return 0
            
        except Exception as e:
            logger.error(f"Training failed: {e}")
            import traceback
            traceback.print_exc()
            return 1

    
def main():
    """主入口函数"""
    fire.Fire(CLI)

