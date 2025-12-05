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
        config: str = None,
        # 命令行参数（可覆盖配置文件）
        algorithm: str = None,
        experiment_name: str = None,
        run_name: str = None,
        model_name: str = None,
        test_size: float = None,
        mlflow_tracking_uri: str = None,
        max_evals: int = None,
        optimization_metric: str = None,
        val_dataset_path: str = None,
        test_dataset_path: str = None,
    ):
        """
        训练时间序列模型（支持多种模型）
        
        Args:
            dataset_path: 数据集文件或文件夹路径
            config: train.json 配置文件路径（推荐使用）
            algorithm: 算法名称（sarima, prophet, xgboost, lstm）
            experiment_name: MLflow 实验名称
            run_name: MLflow run 名称（可选）
            model_name: 注册到 MLflow 的模型名称（可选）
            test_size: 测试集比例，默认 0.2
            mlflow_tracking_uri: MLflow tracking 服务地址
            max_evals: 超参数优化轮次 (0=不优化)
            optimization_metric: 优化目标指标 (rmse/mae/mape)
            val_dataset_path: 验证集路径（可选）
            test_dataset_path: 测试集路径（可选）
            
        Example:
            # 使用配置文件（推荐）
            classify_timeseries_server train --dataset-path ./data.csv --config ./train.json
            
            # 使用命令行参数
            classify_timeseries_server train --dataset-path ./data.csv --algorithm sarima --max-evals 50
        """
        from ..training import UniversalTrainer, TrainingConfig
        import os
        
        try:
            return self._train_with_config(
                dataset_path=dataset_path,
                config_path=config,
                val_dataset_path=val_dataset_path,
                test_dataset_path=test_dataset_path,
                # 命令行参数覆盖
                algorithm=algorithm,
                model_name=model_name,
                experiment_name=experiment_name,
                run_name=run_name,
                test_size=test_size,
                mlflow_tracking_uri=mlflow_tracking_uri,
                max_evals=max_evals,
                optimization_metric=optimization_metric,
            )
                
        except Exception as e:
            logger.error(f"训练失败: {e}")
            import traceback
            traceback.print_exc()
            return 1
    
    def _train_with_config(
        self,
        dataset_path: str,
        config_path: str = None,
        val_dataset_path: str = None,
        test_dataset_path: str = None,
        **override_params
    ):
        """使用新架构训练（配置文件驱动）
        
        Args:
            dataset_path: 数据集路径
            config_path: train.json 配置文件路径
            val_dataset_path: 验证集路径
            test_dataset_path: 测试集路径
            **override_params: 命令行参数覆盖
            
        Returns:
            0: 成功, 1: 失败
        """
        from ..training import UniversalTrainer, TrainingConfig
        import os
        
        # 1. 加载配置
        training_config = TrainingConfig(config_path)
        logger.info(f"配置加载完成: {training_config}")
        
        # 2. 命令行参数覆盖配置文件
        if override_params.get('algorithm'):
            training_config.set("model", "type", value=override_params['algorithm'])
        if override_params.get('model_name'):
            training_config.set("model", "name", value=override_params['model_name'])
        if override_params.get('experiment_name'):
            training_config.set("mlflow", "experiment_name", value=override_params['experiment_name'])
        if override_params.get('run_name'):
            training_config.set("mlflow", "run_name", value=override_params['run_name'])
        if override_params.get('test_size') is not None:
            training_config.set("training", "test_size", value=float(override_params['test_size']))
        if override_params.get('mlflow_tracking_uri'):
            training_config.set("mlflow", "tracking_uri", value=override_params['mlflow_tracking_uri'])
        elif os.getenv("MLFLOW_TRACKING_URI"):
            training_config.set("mlflow", "tracking_uri", value=os.getenv("MLFLOW_TRACKING_URI"))
        
        # 超参数优化配置
        if override_params.get('max_evals') is not None:
            max_evals = int(override_params['max_evals'])
            training_config.set("hyperparams", "search", "enabled", value=max_evals > 0)
            if max_evals > 0:
                training_config.set("hyperparams", "search", "max_evals", value=max_evals)
        if override_params.get('optimization_metric'):
            training_config.set("hyperparams", "search", "metric", value=override_params['optimization_metric'])
        
        # 3. 显示配置信息
        logger.info("=" * 60)
        logger.info(f"训练配置:")
        logger.info(f"  模型类型: {training_config.model_type}")
        logger.info(f"  模型名称: {training_config.model_name}")
        logger.info(f"  数据集: {dataset_path}")
        if val_dataset_path:
            logger.info(f"  验证集: {val_dataset_path}")
        if test_dataset_path:
            logger.info(f"  测试集: {test_dataset_path}")
        logger.info(f"  MLflow 实验: {training_config.mlflow_experiment_name}")
        if training_config.is_hyperopt_enabled:
            logger.info(f"  超参数优化: 启用 (max_evals={training_config.hyperopt_max_evals})")
        logger.info("=" * 60)
        
        # 4. 创建训练器并训练
        trainer = UniversalTrainer(training_config)
        result = trainer.train(
            dataset_path=dataset_path,
            val_dataset_path=val_dataset_path,
            test_dataset_path=test_dataset_path
        )
        
        # 5. 输出结果
        metrics = result["test_metrics"]
        logger.info("=" * 60)
        logger.info("训练完成!")
        logger.info(f"测试集指标:")
        logger.info(f"  RMSE: {metrics['rmse']:.4f}")
        logger.info(f"  MAE: {metrics['mae']:.4f}")
        logger.info(f"  MAPE: {metrics['mape']:.2f}%")
        logger.info(f"MLflow Run ID: {result['run_id']}")
        logger.info("=" * 60)
        
        return 0

    
def main():
    """主入口函数"""
    fire.Fire(CLI)

