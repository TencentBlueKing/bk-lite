"""
训练任务状态轮询 Celery 任务

在训练启动后，定期检查 MLflow 中对应实验的运行状态，
当训练完成或失败时更新 TrainJob 状态，并触发后续自动化流程。
"""

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

from apps.core.logger import mlops_logger as logger


@shared_task(
    bind=True,
    max_retries=360,  # 最多重试 360 次 × 30 秒 ≈ 3 小时
    default_retry_delay=30,  # 每 30 秒轮询一次
    soft_time_limit=60,  # 单次执行超时 60 秒
    time_limit=90,
    acks_late=True,
    reject_on_worker_lost=True,
)
def poll_train_job_status(
    self, train_job_id: int, mlflow_prefix: str, expected_run_count: int = 0
) -> dict:
    """
    轮询 MLflow 训练运行状态

    Args:
        train_job_id: TrainJob 的主键 ID
        mlflow_prefix: MLflow 命名前缀，如 "AnomalyDetection"
        expected_run_count: 预期的 run 数量（用于防止竞态条件，读取到旧的已完成 run）

    Returns:
        dict: 执行结果
    """
    from apps.mlops.constants import MLflowRunStatus, TrainJobStatus
    from apps.mlops.utils import mlflow_service

    try:
        # 延迟导入模型，避免循环依赖
        train_job = _load_train_job(train_job_id, mlflow_prefix)
        if train_job is None:
            return {"result": False, "reason": "train_job not found or not running"}

        # 构建实验名称并查询 MLflow
        experiment_name = mlflow_service.build_experiment_name(
            prefix=mlflow_prefix,
            algorithm=train_job.algorithm,
            train_job_id=train_job.id,
        )

        experiment = mlflow_service.get_experiment_by_name(experiment_name)
        if not experiment:
            logger.warning(
                f"训练状态查询: 实验{experiment_name}不存在, "
                f"TrainJob ID: {train_job_id}, 将继续重试"
            )
            raise self.retry()

        # 获取最新运行记录
        runs = mlflow_service.get_experiment_runs(experiment.experiment_id)
        if runs.empty:
            logger.warning(
                f"训练状态查询: 实验{experiment_name}无运行记录 , "
                f"TrainJob ID: {train_job_id}, 将继续重试"
            )
            raise self.retry()

        # 校验 run 数量，防止读取到旧的已完成 run（竞态条件）
        current_run_count = len(runs)
        if expected_run_count > 0 and current_run_count < expected_run_count:
            logger.info(
                f"训练状态查询: 实验{experiment_name}等待新 run 注册, "
                f"TrainJob ID: {train_job_id}, "
                f"当前 run 数量: {current_run_count}, 预期: {expected_run_count}"
            )
            raise self.retry()

        latest_run_status = str(runs.iloc[0].get("status", MLflowRunStatus.UNKNOWN))

        # 训练仍在运行，继续轮询
        if latest_run_status == MLflowRunStatus.RUNNING:
            logger.info(
                f"训练状态查询: 实验{experiment_name}仍在运行, "
                f"TrainJob ID: {train_job_id}"
            )
            raise self.retry()

        # 训练结束（完成/失败/终止），映射状态
        new_status = MLflowRunStatus.TO_TRAIN_JOB_STATUS.get(
            latest_run_status, TrainJobStatus.FAILED
        )
        train_job.status = new_status
        train_job.save(update_fields=["status"])

        logger.info(
            f"训练状态查询: 实验{experiment_name}训练结束, "
            f"TrainJob ID: {train_job_id}, "
            f"MLflow 状态: {latest_run_status}, "
            f"更新为: {new_status}"
        )

        return {
            "result": True,
            "train_job_id": train_job_id,
            "final_status": new_status,
        }

    except SoftTimeLimitExceeded:
        logger.error(f"训练状态查询超时: 将继续重试TrainJob ID  {train_job_id}")
        raise self.retry()

    except self.MaxRetriesExceededError:
        logger.error(f"超过最大重试次数: TrainJob ID: {train_job_id}")
        _mark_train_job_failed(train_job_id, mlflow_prefix)
        return {"result": False, "reason": "max retries exceeded"}


def _load_train_job(train_job_id: int, mlflow_prefix: str):
    """
    根据 mlflow_prefix 加载对应的 TrainJob 对象

    仅在任务状态为 RUNNING 时返回，否则返回 None（跳过已完成的任务）
    """
    from apps.mlops.constants import TrainJobStatus

    model_class = _get_train_job_model(mlflow_prefix)
    if model_class is None:
        logger.error(f"未知的 mlflow_prefix: {mlflow_prefix}")
        return None

    try:
        train_job = model_class.objects.get(id=train_job_id)
    except model_class.DoesNotExist:
        logger.error(f"TrainJob 不存在: ID={train_job_id}, prefix={mlflow_prefix}")
        return None

    if train_job.status != TrainJobStatus.RUNNING:
        logger.info(
            f"TrainJob 状态非 RUNNING，跳过轮询: "
            f"ID={train_job_id}, status={train_job.status}"
        )
        return None

    return train_job


def _get_train_job_model(mlflow_prefix: str):
    """根据 mlflow_prefix 返回对应的 TrainJob Model 类"""
    prefix_model_map = {
        "AnomalyDetection": "apps.mlops.models.anomaly_detection.AnomalyDetectionTrainJob",
        "Classification": "apps.mlops.models.classification.ClassificationTrainJob",
        "ImageClassification": "apps.mlops.models.image_classification.ImageClassificationTrainJob",
        "ObjectDetection": "apps.mlops.models.object_detection.ObjectDetectionTrainJob",
        "LogClustering": "apps.mlops.models.log_clustering.LogClusteringTrainJob",
        "TimeseriesPredict": "apps.mlops.models.timeseries_predict.TimeSeriesPredictTrainJob",
    }

    model_path = prefix_model_map.get(mlflow_prefix)
    if model_path is None:
        return None

    # 动态导入
    module_path, class_name = model_path.rsplit(".", 1)
    import importlib

    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def _mark_train_job_failed(train_job_id: int, mlflow_prefix: str) -> None:
    """超过最大重试次数时标记训练任务为失败"""
    from apps.mlops.constants import TrainJobStatus

    model_class = _get_train_job_model(mlflow_prefix)
    if model_class is None:
        return

    try:
        model_class.objects.filter(
            id=train_job_id, status=TrainJobStatus.RUNNING
        ).update(status=TrainJobStatus.FAILED)
        logger.info(f"已标记 TrainJob 为失败: ID={train_job_id}")
    except Exception as e:
        logger.error(f"标记 TrainJob 失败时出错: ID={train_job_id}, error={e}")
