from celery.app import shared_task
from apps.mlops.models.anomaly_detection import AnomalyDetectionTrainJob
from apps.mlops.algorithm.anomaly_detection.random_forest_detector import RandomForestAnomalyDetector
from apps.core.logger import celery_logger as logger


@shared_task
def start_anomaly_detection_train(train_job_id: int) -> dict:
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
        # 获取训练任务
        train_job = AnomalyDetectionTrainJob.objects.get(id=train_job_id)

        # 更新任务状态为训练中
        train_job.status = 'running'
        train_job.save()

        # 根据算法类型选择对应的检测器
        if train_job.algorithm == 'RandomForest':
            detector = RandomForestAnomalyDetector()
        else:
            raise ValueError(f"不支持的算法类型: {train_job.algorithm}")

        # 启动训练
        detector.train(train_job)

        # 训练完成，更新状态
        train_job.status = 'completed'
        train_job.save()

        return {
            'success': True,
            'message': '训练任务已完成',
            'train_job_id': train_job_id,
            'status': train_job.status
        }

    except AnomalyDetectionTrainJob.DoesNotExist:
        raise ValueError(f"训练任务 ID {train_job_id} 不存在")
    except Exception as e:
        # 训练失败，更新状态
        if 'train_job' in locals():
            train_job.status = 'failed'
            train_job.save()

        raise ValueError(f"训练失败: {str(e)}")
