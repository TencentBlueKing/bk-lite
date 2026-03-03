from dotenv import load_dotenv
import fire
from loguru import logger
import os
import sys

load_dotenv()


class CLI:
    """命令行接口"""
    
    def train(
        self,
        dataset_path: str,
        config: str,
        run_name: str = None
    ):
        """训练文本分类模型
        
        Args:
            dataset_path: 数据集路径（CSV文件或包含train.csv的目录）
            config: 训练配置文件路径（JSON格式）
            run_name: MLflow run名称（可选）
            
        示例:
            classify_text_classification_server train \\
                --dataset_path=./support-files/scripts/data/train.csv \\
                --config=./support-files/scripts/train.json \\
                --run_name="text_classification_experiment"
        """
        logger.info("=" * 80)
        logger.info("文本分类模型训练")
        logger.info("=" * 80)
        logger.info(f"数据集路径: {dataset_path}")
        logger.info(f"配置文件: {config}")
        logger.info(f"Run 名称: {run_name or '(自动生成)'}")
        logger.info("=" * 80)
        
        try:
            # 导入训练器和配置
            from classify_text_classification_server.training.trainer import UniversalTrainer
            from classify_text_classification_server.training.config.loader import TrainingConfig
            
            # 加载配置
            training_config = TrainingConfig(config)
            
            # 注入 tracking_uri（从环境变量）
            tracking_uri = os.getenv("MLFLOW_TRACKING_URI")
            if tracking_uri:
                training_config.set("mlflow", "tracking_uri", value=tracking_uri)
                logger.info(f"✓ MLflow Tracking URI: {tracking_uri}")
            else:
                logger.warning("⚠️  未设置 MLFLOW_TRACKING_URI 环境变量，MLflow 将使用本地文件系统")
            
            # 注入 run_name（如果命令行指定）
            if run_name:
                training_config.set("mlflow", "run_name", value=run_name)
            
            # 创建训练器（传递配置对象）
            trainer = UniversalTrainer(
                config=training_config,
                dataset_path=dataset_path,
                run_name=run_name
            )
            
            # 执行训练
            trainer.train()
            
            logger.info("训练成功完成！")
            
        except Exception as e:
            logger.error(f"训练失败: {e}")
            logger.exception(e)
            sys.exit(1)
    
def main():
    """主入口函数"""
    fire.Fire(CLI)

