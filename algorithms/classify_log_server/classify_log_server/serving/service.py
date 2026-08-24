"""BentoML service definition."""

import time
import os
import sys
import traceback
from collections import Counter
from pathlib import Path

import bentoml
from loguru import logger

from .config import get_model_config
from .exceptions import ModelInferenceError
from .metrics import (
    health_check_counter,
    model_load_counter,
    prediction_counter,
    prediction_duration,
)
from .models import load_model
from .schemas import (
    ClusteringSummary,
    LogClusterRequest,
    LogClusterResponseV2,
    LogClusterResult,
    TemplateGroup,
)

def _configure_production_logger(sink=sys.stderr) -> None:
    logger.configure(handlers=[{"sink": sink, "diagnose": False, "backtrace": True}])


_configure_production_logger()


def _safe_exception_call_chain(error: BaseException, max_frames: int = 12) -> str:
    frames = traceback.extract_tb(error.__traceback__)
    return ">".join(f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}" for frame in frames[-max_frames:]) or "-"


class _SafeLogException(RuntimeError):
    pass


def _safe_exception_info(error: BaseException):
    safe_error = _SafeLogException(type(error).__name__)
    return _SafeLogException, safe_error, error.__traceback__


@bentoml.service(
    name="classify_log_service",
    traffic={"timeout": 30},
)
class MLService:
    """机器学习模型服务."""

    @bentoml.on_deployment
    def setup() -> None:
        """
        部署时执行一次的全局初始化.

        用于预热缓存、下载资源等全局操作.
        不接收 self 参数,类似静态方法.
        """
        # 可以在这里做全局初始化,例如:
        # - 预热模型缓存
        # - 下载共享资源
        # - 初始化全局连接池
        logger.info("event=log_classification_deployment_setup_completed")

    def __init__(self) -> None:
        """初始化服务,加载配置和模型."""
        logger.debug("event=log_classification_service_initializing")
        self.config = get_model_config()
        logger.debug("event=log_classification_config_loaded model_source={}", self.config.source)

        try:
            self.model = load_model(self.config)
            model_load_counter.labels(
                source=self.config.source, status="success").inc()
            logger.info("event=log_classification_model_load_succeeded model_source={}", self.config.source)
        except Exception as e:
            model_load_counter.labels(
                source=self.config.source, status="failure").inc()
            logger.opt(exception=_safe_exception_info(e)).error(
                "event=log_classification_model_load_failed failed_stage=model_load error_type={} call_chain={}",
                type(e).__name__,
                _safe_exception_call_chain(e),
            )
            raise

    @bentoml.on_shutdown
    def cleanup(self) -> None:
        """
        服务关闭时的清理操作.

        用于释放资源、关闭连接等.
        """
        # 清理逻辑,例如:
        # - 关闭数据库连接
        # - 保存缓存状态
        # - 释放 GPU 显存
        logger.info("event=log_classification_cleanup_completed")

    @bentoml.api
    async def predict(self, request: LogClusterRequest) -> LogClusterResponseV2:
        """
        日志聚类预测接口.

        通过 LogClusterRequest schema 接收请求，确保 BentoML 在反序列化时
        触发 Pydantic 校验（max_length=10000 + 单条 10KB 大小限制）。

        P0优化点：
        1. 返回聚合数据，减少90%网络传输
        2. 标记未知日志（异常检测基础）
        3. 详细性能指标
        4. 可选的详细模式

        Args:
            request: 日志聚类请求（含 data 列表和 config 配置）

        Returns:
            聚合的日志聚类响应

        Raises:
            ModelInferenceError: 模型推理失败
        """
        data = request.data
        req_config = request.config
        
        start_time = time.time()
        logger.debug(
            "event=log_classification_request_received logs={} return_details={} sort_by={}",
            len(data),
            req_config.return_details,
            req_config.sort_by,
        )

        try:
            # 1. 模型预测阶段
            predict_start = time.time()
            
            import pandas as pd

            if hasattr(self.model, "predict"):
                result_df = self.model.predict(data)
            else:
                result_df = pd.DataFrame(
                    {
                        "log": data,
                        "cluster_id": [-1] * len(data),
                        "template": [None] * len(data),
                    }
                )
            
            predict_time = (time.time() - predict_start) * 1000
            
            # 2. 结果聚合阶段（P0核心优化）
            aggregate_start = time.time()
            
            # 统计基本信息
            total_logs = len(data)
            unknown_mask = result_df["cluster_id"] == -1
            matched_logs = int((~unknown_mask).sum())
            
            # 构建模板分组
            template_groups = []
            matched_groups = result_df.loc[~unknown_mask].groupby(
                "cluster_id", sort=False
            )
            for cluster_id, group in matched_groups:
                count = len(group)
                indices = group.index.tolist()
                
                # 采样代表性日志
                sample_size = min(req_config.max_samples, count)
                sample_indices = indices[:sample_size]
                sample_logs = [data[i] for i in sample_indices]
                
                # 获取模板字符串
                template_str = group["template"].iloc[0]
                
                template_groups.append(TemplateGroup(
                    cluster_id=int(cluster_id),
                    template=template_str if template_str else "<unknown>",
                    count=count,
                    percentage=round(count / total_logs * 100, 2),
                    log_indices=indices,
                    sample_logs=sample_logs
                ))
            
            # 排序模板分组
            if req_config.sort_by == "count":
                template_groups.sort(key=lambda x: x.count, reverse=True)
            else:  # cluster_id
                template_groups.sort(key=lambda x: x.cluster_id)
            
            # 处理未知日志
            unknown_logs = []
            if unknown_mask.any():
                unknown_indices = result_df[unknown_mask].index.tolist()
                unknown_logs = [
                    {
                        'index': idx,
                        'log': data[idx],
                        'reason': 'no_matching_template'
                    }
                    for idx in unknown_indices
                ]
            
            aggregate_time = (time.time() - aggregate_start) * 1000
            total_time = (time.time() - start_time) * 1000
            
            # 3. 构建响应
            summary = ClusteringSummary(
                total_logs=total_logs,
                matched_logs=matched_logs,
                unknown_logs=len(unknown_logs),
                num_templates=len(template_groups),
                coverage_rate=round(matched_logs / total_logs if total_logs > 0 else 0.0, 4),
                processing_time_ms=round(total_time, 2)
            )
            
            response = LogClusterResponseV2(
                summary=summary,
                template_groups=template_groups,
                unknown_logs=unknown_logs,
                model_info={
                    'model_version': getattr(self.model, 'version', 'unknown'),
                    'source': self.config.source,
                    'tau': getattr(self.model, 'tau', None),
                }
            )
            
            # 4. 可选：返回原始明细
            if req_config.return_details:
                results = [
                    LogClusterResult(
                        log=row["log"],
                        cluster_id=int(row["cluster_id"]),
                        template=row["template"],
                    )
                    for _, row in result_df.iterrows()
                ]
                response.details = results
            
            # 5. 记录指标
            prediction_counter.labels(
                model_source=self.config.source,
                status="success",
            ).inc()
            
            logger.info(
                "event=log_classification_completed templates={} coverage_rate={:.4f} unknown_logs={} "
                "duration_ms={:.3f} predict_duration_ms={:.3f} aggregate_duration_ms={:.3f}",
                summary.num_templates,
                summary.coverage_rate,
                summary.unknown_logs,
                total_time,
                predict_time,
                aggregate_time,
            )
            
            return response
            
        except ValueError as e:
            # 输入验证错误
            logger.warning(
                "event=log_classification_failed failed_stage=input_validation error_type={}",
                type(e).__name__,
            )
            prediction_counter.labels(
                model_source=self.config.source,
                status="failure",
            ).inc()
            raise ModelInferenceError(f"输入验证失败: {str(e)}") from e
            
        except Exception as e:
            # 模型推理错误
            prediction_counter.labels(
                model_source=self.config.source,
                status="failure",
            ).inc()
            logger.opt(exception=_safe_exception_info(e)).error(
                "event=log_classification_failed failed_stage=model_predict error_type={} call_chain={}",
                type(e).__name__,
                _safe_exception_call_chain(e),
            )
            raise ModelInferenceError(f"Log clustering failed: {str(e)}") from e

    @bentoml.api
    async def health(self) -> dict:
        """健康检查接口."""
        health_check_counter.inc()
        return {
            "status": "healthy",
            "startup_instance_id": os.getenv("SERVING_INSTANCE_ID", ""),
            "model_source": self.config.source,
            "model_version": getattr(self.model, "version", "unknown"),
        }
