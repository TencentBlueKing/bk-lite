"""时间序列递归推理的组合工作量预算。"""

import os

from loguru import logger


DEFAULT_MAX_RECURSIVE_FEATURE_ENGINEERING_WORK = 2_000_000
RECURSIVE_FEATURE_ENGINEERING_WRAPPERS = {
    "GradientBoostingWrapper",
    "RandomForestWrapper",
}


class RecursiveFeatureEngineeringBudgetExceeded(ValueError):
    """递归特征工程请求超过组合工作量预算。"""

    def __init__(
        self,
        history_points: int,
        steps: int,
        estimated_work: int,
        limit: int,
    ) -> None:
        self.history_points = history_points
        self.steps = steps
        self.estimated_work = estimated_work
        self.limit = limit
        super().__init__(
            "递归特征工程工作量超限："
            f"历史点数 {history_points}、预测步数 {steps}、"
            f"预计处理 {estimated_work} 行，当前上限 {limit}；"
            "请减少历史点数或预测步数"
        )


def get_max_recursive_feature_engineering_work() -> int:
    """读取递归特征工程组合工作量上限。"""
    raw_limit = os.getenv(
        "MAX_RECURSIVE_FEATURE_ENGINEERING_WORK",
        str(DEFAULT_MAX_RECURSIVE_FEATURE_ENGINEERING_WORK),
    )
    try:
        limit = int(raw_limit)
    except ValueError:
        raise ValueError(
            "MAX_RECURSIVE_FEATURE_ENGINEERING_WORK must be a positive integer"
        ) from None
    if limit <= 0:
        raise ValueError(
            "MAX_RECURSIVE_FEATURE_ENGINEERING_WORK must be a positive integer"
        )
    return limit


def estimate_recursive_feature_engineering_work(
    history_points: int, steps: int
) -> int:
    """估算旧递归实现逐步增长历史后需处理的总行数。"""
    return history_points * steps + steps * (steps - 1) // 2


def _unwrap_python_model(model):
    unwrap = getattr(model, "unwrap_python_model", None)
    if not callable(unwrap):
        return model
    try:
        return unwrap()
    except Exception as error:
        # 旧 MLflow 或第三方模型不支持解包时不改变既有推理行为。
        logger.warning(
            "无法解包 Python 模型，跳过递归特征工程预算："
            f"{type(error).__name__}: {error}"
        )
        return model


def _uses_recursive_feature_engineering(model) -> bool:
    python_model = _unwrap_python_model(model)
    model_type = type(python_model)
    return (
        model_type.__name__ in RECURSIVE_FEATURE_ENGINEERING_WRAPPERS
        and model_type.__module__.startswith(
            "classify_timeseries_server.training.models."
        )
        and getattr(python_model, "use_feature_engineering", False) is True
        and getattr(python_model, "feature_engineer", None) is not None
    )


def enforce_recursive_feature_engineering_budget(
    model, history_points: int, steps: int, limit: int
) -> None:
    """仅对 GB/RF 特征工程递归推理执行组合预算保护。"""
    if not _uses_recursive_feature_engineering(model):
        return

    estimated_work = estimate_recursive_feature_engineering_work(
        history_points, steps
    )
    if estimated_work > limit:
        raise RecursiveFeatureEngineeringBudgetExceeded(
            history_points=history_points,
            steps=steps,
            estimated_work=estimated_work,
            limit=limit,
        )
