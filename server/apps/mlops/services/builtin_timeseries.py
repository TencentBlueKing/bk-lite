"""部署预置时序模型在发布列表中的记录。

增加一只时序算法时，把算法名加入 BUILTIN_TIMESERIES_ALGORITHMS。
初始化会按这个名字写入训练任务和发布记录。预测地址使用训练任务的 algorithm。
"""

import os

from django.db.models import Q

PRESET_BASE_URL_ENV = "MLOPS_PRESET_BASE_URL"
BUILTIN_TIMESERIES_ALGORITHMS = ("GradientBoosting",)


def preset_base_url() -> str:
    """部署注入的预置服务基址。空字符串表示这次部署没有拉起预置容器。"""
    return os.getenv(PRESET_BASE_URL_ENV, "").strip().rstrip("/")


def exclude_hidden_builtin(queryset):
    """变量不存在时，内置记录不出现在列表里。"""
    if preset_base_url():
        return queryset
    return queryset.exclude(is_builtin=True)


def predictable_timeseries_servings(queryset):
    """可预测列表保留有端口的普通发布，并在预置容器存在时放行内置记录。"""
    queryset = exclude_hidden_builtin(queryset)
    unavailable_port = Q(container_info__port__isnull=True) | Q(container_info__port="") | Q(container_info__port=0)
    if preset_base_url():
        return queryset.exclude(Q(is_builtin=False) & unavailable_port)
    return queryset.exclude(unavailable_port)


def builtin_predict_url(algorithm: str) -> str:
    base_url = preset_base_url()
    if not base_url:
        raise ValueError("error.preset_base_url_missing")
    if not algorithm or any(marker in algorithm for marker in ("/", "\\", "..", "?", "#")):
        raise ValueError("error.preset_algorithm_invalid")
    return f"{base_url}/{algorithm}/predict"


def ensure_builtin_timeseries_records() -> dict[str, int | bool]:
    """按算法幂等写入内置训练任务和发布记录。只写数据库。"""
    from django.core.management.base import CommandError

    from apps.core.logger import mlops_logger as logger
    from apps.mlops.models.timeseries_predict import TimeSeriesPredictServing, TimeSeriesPredictTrainJob
    from apps.system_mgmt.utils.group_utils import GroupUtils

    if not preset_base_url():
        logger.info("event=builtin_timeseries_init_skipped reason=preset_base_url_absent")
        return {"created_train_jobs": 0, "created_servings": 0, "skipped": True}

    group = GroupUtils.builtin_root()
    if group is None:
        raise CommandError("默认组织 Default 不存在，无法写入预置时序发布记录")

    created_train_jobs = 0
    created_servings = 0
    for algorithm in BUILTIN_TIMESERIES_ALGORITHMS:
        train_job = TimeSeriesPredictTrainJob.objects.filter(is_builtin=True, algorithm=algorithm).first()
        if train_job is None:
            train_job = TimeSeriesPredictTrainJob(
                name=algorithm,
                description="",
                team=[group.id],
                algorithm=algorithm,
                is_builtin=True,
                dataset_version=None,
                hyperopt_config={},
            )
            train_job.save()
            created_train_jobs += 1
        serving = TimeSeriesPredictServing.objects.filter(is_builtin=True, train_job=train_job).first()
        if serving is None:
            TimeSeriesPredictServing.objects.create(
                name=algorithm,
                description="",
                team=[group.id],
                train_job=train_job,
                is_builtin=True,
                model_version="latest",
                container_info={},
            )
            created_servings += 1

    logger.info(
        "event=builtin_timeseries_init_finished created_train_jobs=%s created_servings=%s",
        created_train_jobs,
        created_servings,
    )
    return {
        "created_train_jobs": created_train_jobs,
        "created_servings": created_servings,
        "skipped": False,
    }
