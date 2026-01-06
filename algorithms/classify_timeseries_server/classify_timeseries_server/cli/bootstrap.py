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
        run_name: str = None,
    ):
        """
        训练时间序列模型
        
        Args:
            dataset_path: 数据集路径（目录或单个CSV文件）
                         - 目录模式：包含 train_data.csv/val_data.csv/test_data.csv
                         - 文件模式：单个CSV文件，自动划分
            config: 配置文件路径（可选，默认使用内置配置）
            run_name: MLflow run 名称（可选）
                     大多数情况下使用自动生成的名称即可
                     用于批量实验标识或 CI/CD 集成时关联构建号
        
        Environment Variables:
            MLFLOW_TRACKING_URI: MLflow 服务地址（必需）
        
        Example:
            # 目录模式（标准）
            export MLFLOW_TRACKING_URI=http://mlflow:5000
            classify_timeseries_server train --dataset-path ./data/
            
            # 文件模式（快速实验）
            classify_timeseries_server train --dataset-path data.csv
            
            # 自定义配置
            classify_timeseries_server train \\
                --dataset-path ./data/ \\
                --config custom-train.json
        """
        from ..training import UniversalTrainer, TrainingConfig
        import os
        
        try:
            return self._train_with_config(
                dataset_path=dataset_path,
                config_path=config,
                run_name=run_name,
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
        run_name: str = None,
    ):
        """配置文件驱动的训练流程
        
        Args:
            dataset_path: 数据集路径（目录或文件）
            config_path: 配置文件路径（None 时查找默认配置）
            run_name: MLflow run 名称（可选）
            
        Returns:
            0: 成功, 1: 失败
        """
        from ..training import UniversalTrainer, TrainingConfig
        import os
        
        # 1. 检查配置文件参数
        if config_path is None:
            raise ValueError(
                "必须提供配置文件路径。\n"
                "使用方式: classify_timeseries_server train --dataset-path <path> --config <config.json>"
            )
        
        # 2. 加载配置
        training_config = TrainingConfig(config_path)
        logger.info(f"配置加载完成: {training_config}")
        
        # 3. 设置默认 experiment_name（如果配置文件没有）
        if not training_config.get("mlflow", "experiment_name"):
            logger.info(
                "💡 配置文件未指定 mlflow.experiment_name，使用默认值 'default'。\n"
                "   建议在配置文件中添加有意义的实验名称。"
            )
            training_config.set("mlflow", "experiment_name", value="timeseries_gradient_boosting_default")
        
        # 4. 注入 tracking_uri（从环境变量）
        tracking_uri = os.getenv("MLFLOW_TRACKING_URI")
        if tracking_uri:
            training_config.set("mlflow", "tracking_uri", value=tracking_uri)
        else:
            logger.warning("⚠️  未设置 MLFLOW_TRACKING_URI 环境变量，MLflow 将使用本地文件系统")
        
        # 5. 注入 run_name（如果命令行指定）
        if run_name:
            training_config.set("mlflow", "run_name", value=run_name)
        
        # 3. 显示配置信息
        logger.info("=" * 60)
        logger.info(f"训练配置:")
        logger.info(f"  模型类型: {training_config.model_type}")
        logger.info(f"  模型名称: {training_config.model_name}")
        logger.info(f"  数据集: {dataset_path}")
        logger.info(f"  MLflow 实验: {training_config.mlflow_experiment_name}")
        logger.info(f"  超参数搜索: max_evals={training_config.max_evals}")
        logger.info("=" * 60)
        
        # 4. 创建训练器并训练
        trainer = UniversalTrainer(training_config)
        result = trainer.train(dataset_path=dataset_path)
        
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

