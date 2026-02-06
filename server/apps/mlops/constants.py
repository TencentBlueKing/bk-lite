# -- coding: utf-8 --
# @File: constants.py
# @Description: MLOps status constants to avoid magic strings


class TrainJobStatus:
    """训练任务状态"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

    CHOICES = (
        (PENDING, "待训练"),
        (RUNNING, "训练中"),
        (COMPLETED, "已完成"),
        (FAILED, "训练失败"),
    )


class DatasetReleaseStatus:
    """数据集发布版本状态"""

    PENDING = "pending"
    PROCESSING = "processing"
    PUBLISHED = "published"
    FAILED = "failed"
    ARCHIVED = "archived"

    CHOICES = (
        (PENDING, "待发布"),
        (PROCESSING, "发布中"),
        (PUBLISHED, "已发布"),
        (FAILED, "发布失败"),
        (ARCHIVED, "归档"),
    )


class MLflowRunStatus:
    """MLflow 运行状态 (来自 MLflow API)"""

    RUNNING = "RUNNING"
    FINISHED = "FINISHED"
    FAILED = "FAILED"
    KILLED = "KILLED"
    UNKNOWN = "UNKNOWN"

    # MLflow 状态到 TrainJob 状态的映射
    TO_TRAIN_JOB_STATUS = {
        FINISHED: TrainJobStatus.COMPLETED,
        FAILED: TrainJobStatus.FAILED,
        KILLED: TrainJobStatus.FAILED,
    }
