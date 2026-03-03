"""BentoML service definition."""

import time
from collections import Counter

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
        logger.info("=== Deployment setup started ===")
        # 可以在这里做全局初始化,例如:
        # - 预热模型缓存
        # - 下载共享资源
        # - 初始化全局连接池
        logger.info("=== Deployment setup completed ===")

    def __init__(self) -> None:
        """初始化服务,加载配置和模型."""
        logger.info("Service instance initializing...")
        self.config = get_model_config()
        logger.info(f"Config loaded: {self.config}")

        try:
            self.model = load_model(self.config)
            model_load_counter.labels(
                source=self.config.source, status="success").inc()
            logger.info("Model loaded successfully")
        except Exception as e:
            model_load_counter.labels(
                source=self.config.source, status="failure").inc()
            logger.error(f"Failed to load model: {e}")
            raise

    @bentoml.on_shutdown
    def cleanup(self) -> None:
        """
        服务关闭时的清理操作.

        用于释放资源、关闭连接等.
        """
        logger.info("=== Service shutdown: cleaning up resources ===")
        # 清理逻辑,例如:
        # - 关闭数据库连接
        # - 保存缓存状态
        # - 释放 GPU 显存
        logger.info("=== Cleanup completed ===")

    @bentoml.api
    async def predict(self, data: list[str], config: dict | None = None) -> LogClusterResponseV2:
        """
        日志聚类预测接口.
        
        P0优化点：
        1. 返回聚合数据，减少90%网络传输
        2. 标记未知日志（异常检测基础）
        3. 详细性能指标
        4. 可选的详细模式

        Args:
            data: 日志消息列表
            config: 聚类配置参数（可选）

        Returns:
            聚合的日志聚类响应

        Raises:
            ModelInferenceError: 模型推理失败
        """
        # 构建请求对象
        from .schemas import LogClusterConfig
        req_config = LogClusterConfig(**(config or {}))
        
        start_time = time.time()
        logger.info(
            f"收到日志聚类请求: {len(data)} 条日志, "
            f"return_details={req_config.return_details}, sort_by={req_config.sort_by}"
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
            matched_logs = len(result_df[result_df['cluster_id'] != -1])
            
            # 统计每个模板的出现次数
            cluster_counts = result_df['cluster_id'].value_counts().to_dict()
            
            # 构建模板分组
            template_groups = []
            for cluster_id, count in cluster_counts.items():
                if cluster_id == -1:
                    continue  # 未知日志单独处理
                
                # 获取该模板的所有日志索引
                mask = result_df['cluster_id'] == cluster_id
                indices = result_df[mask].index.tolist()
                
                # 采样代表性日志
                sample_size = min(req_config.max_samples, count)
                sample_indices = indices[:sample_size]
                sample_logs = [data[i] for i in sample_indices]
                
                # 获取模板字符串
                template_str = result_df[mask]['template'].iloc[0]
                
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
            unknown_mask = result_df['cluster_id'] == -1
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
                f"聚类完成: {summary.num_templates} 个模板, "
                f"覆盖率 {summary.coverage_rate:.2%}, "
                f"未知日志 {summary.unknown_logs} 条, "
                f"耗时 {total_time:.0f}ms (预测={predict_time:.0f}ms, 聚合={aggregate_time:.0f}ms)"
            )
            
            return response
            
        except ValueError as e:
            # 输入验证错误
            logger.error(f"输入验证失败: {e}")
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
            logger.error(f"日志聚类失败: {type(e).__name__}: {e}")
            raise ModelInferenceError(f"Log clustering failed: {str(e)}") from e

    @bentoml.api
    async def health(self) -> dict:
        """健康检查接口."""
        health_check_counter.inc()
        return {
            "status": "healthy",
            "model_source": self.config.source,
            "model_version": getattr(self.model, "version", "unknown"),
        }


