import os
from unittest import result
from celery.app import shared_task
from fastapi.background import P
import pandas as pd
from apps import log
from apps.mlops.models.classification import ClassificationTrainJob
from loguru import logger
from neco.mlops.classification.random_forest_classifier import RandomForestClassifier
from config.components.mlflow import MLFLOW_TRACKER_URL


@shared_task
def start_classification_train(train_job_id: int) -> dict: 
  """
    启动异常检测训练任务

    Args:
        train_job_id: 训练任务ID

    Returns:
        dict: 训练结果信息

    Raises:
        ValueError: 当训练任务不存在或状态不允许训练时
    """
  try:
        
      # 获取训练任务，使用select_related预加载相关对象
        train_job = ClassificationTrainJob.objects.select_related(
            'train_data_id', 'val_data_id', 'test_data_id'
        ).get(id=train_job_id)

        # 检查必要的数据是否存在
        if not train_job.train_data_id:
            raise ValueError("训练数据不存在")
        if not train_job.val_data_id:
            raise ValueError("验证数据不存在")
        if not train_job.test_data_id:
            raise ValueError("测试数据不存在")

        # 更新任务状态为训练中
        train_job.status = 'running'
        train_job.save()

        # 根据算法类型选择对应的检测器
        if train_job.algorithm == 'RandomForest':
            detector = RandomForestClassifier()
        else: 
            raise ValueError(f"不支持的算法类型: {train_job.algorithm}")

        # 启动训练
        experiment_name = f"{train_job.id}_{train_job.name}"
        logger.info(f"实验名称：{experiment_name}")

        # 准备训练数据
        train_df = pd.DataFrame(train_job.train_data_id.train_data)

        # 准备验证数据
        val_df = pd.DataFrame(train_job.val_data_id.train_data)

        # 准备测试数据
        test_df = pd.DataFrame(train_job.test_data_id.train_data)

        # 记录训练开始信息
        logger.info(f"开始训练异常检测模型: {experiment_name}")
        logger.info(f"训练数据形状: {train_df.shape}, 符合分类数量: {sum(train_df['label'])}")
        logger.info(f"验证数据形状: {val_df.shape}, 符合分类数量: {sum(val_df['label'])}")
        logger.info(f"测试数据形状: {test_df.shape}, 符合分类数量: {sum(test_df['label'])}")

        # 调用统一的训练接口，符合用户测试用例的预期
        model_name = f"{train_job.id}_{train_job.name}"
        result = detector.train(
            model_name=model_name,
            train_dataframe=train_df,
            val_dataframe=val_df,
            test_dataframe=test_df,
            train_config=train_job.hyperopt_config,
            # ordinal_features= {},
            max_evals=train_job.max_evals,
            primary_metric="f1_weighted",
            mlflow_tracking_url=MLFLOW_TRACKER_URL,
        )

        logger.info(f"训练完成: {model_name}")
        if result and isinstance(result, dict):
            if "val_metrics" in result:
                logger.info(f"验证集指标: {result['val_metrics']}")
            if "test_metrics" in result:
                logger.info(f"测试集指标: {result['test_metrics']}")
            if "best_params" in result:
                logger.info(f"最佳参数: {result['best_params']}")

        # 训练完成，更新状态
        train_job.status = 'completed'
        train_job.save()

        return {
            'success': True,
            'message': '训练任务已完成',
            'train_job_id': train_job_id,
            'status': train_job.status
        }
        
  except ClassificationTrainJob.DoesNotExist:
    raise ValueError(f"训练任务 ID {train_job_id} 不存在")
  except Exception as e:
    # 训练失败，更新状态
    if 'train_job' in locals():
        train_job.status = 'failed'
        train_job.save()

    raise ValueError(f"训练失败: {str(e)}")