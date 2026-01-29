from dotenv import load_dotenv
import fire
from loguru import logger
import json
import os
from pathlib import Path

from classify_image_classification_server.training.trainer import UniversalTrainer
from classify_image_classification_server.training.config.loader import TrainingConfig

load_dotenv()


class CLI:
    """图片分类服务CLI命令."""
    
    def train(
        self,
        dataset_path: str,
        config: str,
        run_name: str = None
    ):
        """
        训练图片分类模型.
        
        Args:
            dataset_path: 数据集路径（ImageFolder格式）
                预期结构: dataset/train|val|test/class_name/*.jpg
            config: 训练配置文件路径
            run_name: MLflow运行名称，默认使用配置文件中的值
        
        Example:
            # 使用默认配置训练
            classify_image_classification_server train \\
                --dataset-path=/path/to/dataset \\
                --config=support-files/scripts/train.json
            
            # 指定运行名称
            classify_image_classification_server train \\
                --dataset-path=/path/to/dataset \\
                --config=my_config.json \\
                --run-name=experiment_001
        """
        logger.info("=" * 80)
        logger.info("图片分类模型训练")
        logger.info("=" * 80)
        
        # 验证配置文件存在
        config_file = Path(config)
        if not config_file.exists():
            raise FileNotFoundError(
                f"配置文件不存在: {config}\n"
                f"请确保配置文件存在，或使用 --config 参数指定正确的路径"
            )
        
        logger.info(f"使用配置文件: {config}")
        
        # 创建配置对象
        config_obj = TrainingConfig(config)
        
        # 如果命令行指定了run_name，覆盖配置文件中的值
        if run_name:
            config_obj.set('mlflow', 'run_name', value=run_name)
            logger.info(f"使用命令行指定的运行名称: {run_name}")
        
        # 从环境变量读取MLflow tracking URI（如果未在配置中指定）
        mlflow_uri = os.environ.get('MLFLOW_TRACKING_URI')
        if mlflow_uri:
            config_obj.set('mlflow', 'tracking_uri', value=mlflow_uri)
            logger.info(f"使用MLflow Tracking URI: {mlflow_uri}")
        elif not config_obj.get('mlflow', 'tracking_uri'):
            # 如果配置文件和环境变量都没有，使用默认值
            config_obj.set('mlflow', 'tracking_uri', value='mlruns')
            logger.info("使用默认MLflow Tracking URI: mlruns")
        
        # 验证数据集路径
        dataset_path = Path(dataset_path).resolve()
        if not dataset_path.exists():
            raise FileNotFoundError(f"数据集路径不存在: {dataset_path}")
        
        logger.info(f"数据集路径: {dataset_path}")
        logger.info(f"模型类型: {config_obj.model_type}")
        logger.info(f"设备配置: {config_obj.get_device_config()}")
        
        # 创建训练器并开始训练
        try:
            trainer = UniversalTrainer(config_obj)
            result = trainer.train(str(dataset_path))
            
            logger.info("=" * 80)
            logger.info("✓ 训练成功完成！")
            logger.info(f"  Run ID: {result['run_id']}")
            if result.get('test_metrics'):
                logger.info(f"  测试指标: {result['test_metrics']}")
            logger.info("=" * 80)
            
            return 0  # 返回整数表示成功，避免 Python Fire 展示交互式帮助
            
        except Exception as e:
            logger.error(f"✗ 训练失败: {e}", exc_info=True)
            return 1  # 返回 1 表示失败
    
def main():
    """主入口函数"""
    fire.Fire(CLI)

