"""BentoML service definition."""

import time
from datetime import datetime
from typing import Optional
import numpy as np
import pandas as pd

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
    PredictRequest,
    PredictResponse,
    PredictionConfig,
    ClassificationResult,
    ClassificationLabel,
    FeatureImportance,
    TextWarning,
    PredictionSummary,
    ResponseMetadata,
    ErrorDetail,
)


# 常量定义
MAX_TEXT_LENGTH = 5000
TEXT_SNIPPET_LENGTH = 100


@bentoml.service(
    name="classify_text_classification_service",
    traffic={"timeout": 60},
)
class MLService:
    """文本分类模型服务."""

    @bentoml.on_deployment
    def setup() -> None:
        """
        部署时执行一次的全局初始化.

        用于预热缓存、下载资源等全局操作.
        不接收 self 参数,类似静态方法.
        """
        logger.info("=== Deployment setup started ===")
        logger.info("=== Deployment setup completed ===")

    def __init__(self) -> None:
        """初始化服务,加载配置和模型."""
        logger.info("Service instance initializing...")
        self.config = get_model_config()
        logger.info(f"Config loaded: {self.config}")

        try:
            load_start = time.time()
            self.model = load_model(self.config)
            load_time = time.time() - load_start

            model_load_counter.labels(source=self.config.source, status="success").inc()
            logger.info(f"⏱️  Model loaded successfully in {load_time:.3f}s")

        except Exception as e:
            model_load_counter.labels(source=self.config.source, status="failure").inc()
            logger.error(f"❌ Failed to load model: {e}", exc_info=True)
            raise RuntimeError(
                f"Failed to load model from source '{self.config.source}'. "
                "Service cannot start without a valid model."
            ) from e

    @bentoml.on_shutdown
    def cleanup(self) -> None:
        """
        服务关闭时的清理操作.

        用于释放资源、关闭连接等.
        """
        logger.info("=== Service shutdown: cleaning up resources ===")
        logger.info("=== Cleanup completed ===")

    @bentoml.api
    async def predict(self, texts: list[str], config: dict = None) -> PredictResponse:
        """
        文本分类预测接口（支持批量）.

        Args:
            texts: 待分类的文本列表（1-1000条）
            config: 预测配置（可选）
                - top_k: 返回Top-K结果，默认3
                - return_probabilities: 是否返回所有类别概率，默认True
                - return_feature_importance: 是否返回特征重要性，默认True
                - max_features: 返回最多N个重要特征，默认10

        Returns:
            结构化预测响应，包含results、summary、metadata
        """
        request_start = time.time()
        request_time = datetime.utcnow().isoformat() + "Z"

        # 快速失败：前置验证（在 try 块外）
        try:
            # 构造配置对象
            pred_config = PredictionConfig(**config) if config else PredictionConfig()

            # 构造请求对象进行验证
            request = PredictRequest(texts=texts, config=pred_config)

        except Exception as e:
            logger.error(f"Request validation failed: {e}")
            return self._create_error_response(
                code="E1000",
                message=f"请求验证失败: {str(e)}",
                details={
                    "error_type": type(e).__name__,
                    "input_size": len(texts) if texts else 0,
                },
                request_time=request_time,
                execution_time_ms=(time.time() - request_start) * 1000,
            )

        logger.info(f"📥 Received classification request: {len(request.texts)} texts")

        # 2. 文本预处理（截断处理）
        processed_texts, text_warnings = self._preprocess_texts(request.texts)
        logger.debug(f"Preprocessed texts: {processed_texts}")
        logger.debug(
            f"Processed texts type: {type(processed_texts)}, length: {len(processed_texts) if processed_texts else 0}"
        )

        try:
            # 3. 批量推理
            with prediction_duration.labels(model_source=self.config.source).time():
                predict_start = time.time()

                # 调用模型预测（MLflow PyFunc标准接口）
                # MLflow加载后的模型使用标准接口：predict(data)
                # MLflow内部会自动将data传递给自定义包装器的model_input参数
                logger.debug(f"Calling model.predict with texts: {processed_texts}")
                model_output = self.model.predict(processed_texts)

                predict_time = (time.time() - predict_start) * 1000
                logger.info(f"⏱️  Model prediction completed in {predict_time:.1f}ms")

            # 4. 解析模型输出并构造结果
            results = self._build_results(
                original_texts=request.texts,
                processed_texts=processed_texts,
                model_output=model_output,
                text_warnings=text_warnings,
                config=request.config,
            )

            # 5. 计算汇总统计
            summary = self._compute_summary(
                results=results, processing_time_ms=(time.time() - request_start) * 1000
            )

            # 6. 构造元数据
            metadata = self._build_metadata(
                config=request.config,
                request_time=request_time,
                execution_time_ms=(time.time() - request_start) * 1000,
            )

            # 7. 记录指标
            prediction_counter.labels(
                model_source=self.config.source, status="success"
            ).inc()

            logger.info(
                f"✅ Classification completed: {summary.total_samples} texts, "
                f"avg_probability={summary.avg_probability:.4f}, "
                f"time={summary.processing_time_ms:.1f}ms"
            )

            return PredictResponse(
                success=True,
                results=results,
                summary=summary,
                metadata=metadata,
                error=None,
            )

        except Exception as e:
            logger.error(f"❌ Prediction failed: {e}", exc_info=True)

            prediction_counter.labels(
                model_source=self.config.source, status="failure"
            ).inc()

            return self._create_error_response(
                code="E2001",
                message=f"模型推理失败: {str(e)}",
                details={
                    "error_type": type(e).__name__,
                    "model_source": self.config.source,
                },
                request_time=request_time,
                execution_time_ms=(time.time() - request_start) * 1000,
            )

    def _preprocess_texts(
        self, texts: list[str]
    ) -> tuple[list[str], list[list[TextWarning]]]:
        """
        预处理文本（截断超长文本）.

        Args:
            texts: 原始文本列表

        Returns:
            (处理后的文本列表, 每条文本的警告列表)
        """
        processed_texts = []
        all_warnings = []

        for text in texts:
            warnings = []
            processed_text = text

            # 检查并截断超长文本
            if len(text) > MAX_TEXT_LENGTH:
                processed_text = text[:MAX_TEXT_LENGTH]
                warnings.append(
                    TextWarning(
                        type="TEXT_TRUNCATED",
                        message=f"文本超过最大长度限制（{MAX_TEXT_LENGTH}字符），已自动截断",
                        original_length=len(text),
                        truncated_length=MAX_TEXT_LENGTH,
                    )
                )
                logger.warning(
                    f"Text truncated: {len(text)} -> {MAX_TEXT_LENGTH} chars"
                )

            processed_texts.append(processed_text)
            all_warnings.append(warnings)

        return processed_texts, all_warnings

    def _build_results(
        self,
        original_texts: list[str],
        processed_texts: list[str],
        model_output: pd.DataFrame,
        text_warnings: list[list[TextWarning]],
        config: PredictionConfig,
    ) -> list[ClassificationResult]:
        """
        构造分类结果列表.

        Args:
            original_texts: 原始文本列表
            processed_texts: 处理后的文本列表
            model_output: 模型输出DataFrame
            text_warnings: 文本警告列表
            config: 预测配置

        Returns:
            分类结果列表
        """
        results = []

        for i, (original_text, processed_text) in enumerate(
            zip(original_texts, processed_texts)
        ):
            # 提取当前样本的预测结果
            row = model_output.iloc[i]

            prediction = row["prediction"]
            probability = float(row["probability"])

            # 提取所有类别概率
            prob_columns = [
                col for col in model_output.columns if col.startswith("prob_")
            ]
            all_probs = {
                col.replace("prob_", ""): float(row[col]) for col in prob_columns
            }

            # 构造Top-K结果
            top_predictions = self._get_top_k_predictions(all_probs, config.top_k)

            # 概率保留4位小数
            probability = round(float(row["probability"]), 4)

            # 特征重要性（如果需要）
            feature_importance = None
            if config.return_feature_importance:
                feature_importance = self._get_feature_importance_dummy(
                    processed_text, config.max_features
                )

            # 创建文本片段
            text_snippet = original_text[:TEXT_SNIPPET_LENGTH]
            if len(original_text) > TEXT_SNIPPET_LENGTH:
                text_snippet += "..."

            # 估算token数量（简单按空格分割）
            token_count = len(processed_text.split()) if processed_text else 0

            result = ClassificationResult(
                index=i,
                text_snippet=text_snippet,
                prediction=prediction,
                probability=probability,
                top_predictions=top_predictions,
                feature_importance=feature_importance,
                text_length=len(original_text),
                token_count=token_count,
                warnings=text_warnings[i],
            )

            results.append(result)

        return results

    def _get_top_k_predictions(
        self, all_probs: dict[str, float], top_k: int
    ) -> list[ClassificationLabel]:
        """
        获取Top-K预测结果.

        Args:
            all_probs: 所有类别概率字典
            top_k: Top-K数量

        Returns:
            Top-K分类标签列表
        """
        # 按概率降序排序
        sorted_probs = sorted(all_probs.items(), key=lambda x: x[1], reverse=True)

        top_k_results = []
        for rank, (label, prob) in enumerate(sorted_probs[:top_k], start=1):
            top_k_results.append(
                ClassificationLabel(
                    label=label,
                    probability=round(prob, 4),  # 保留4位小数
                    rank=rank,
                )
            )

        return top_k_results

    def _get_feature_importance_dummy(
        self, text: str, max_features: int
    ) -> list[FeatureImportance]:
        """
        获取特征重要性（Dummy实现，返回文本中的词语）.

        注意：这是简化实现，实际应该从模型中提取真实的特征重要性。
        在真实MLflow模型中，需要访问模型内部的预处理器和特征工程器。

        Args:
            text: 文本内容
            max_features: 最多返回N个特征

        Returns:
            特征重要性列表
        """
        # 简单分词（实际应该使用训练时的预处理器）
        words = text.split()[:max_features]

        # 生成模拟的重要性得分
        features = []
        for i, word in enumerate(words):
            importance = 1.0 / (i + 1)  # 简单递减
            features.append(
                FeatureImportance(
                    feature=word, importance=importance, contribution="positive"
                )
            )

        return features

    def _compute_summary(
        self, results: list[ClassificationResult], processing_time_ms: float
    ) -> PredictionSummary:
        """
        计算批量预测汇总统计.

        Args:
            results: 分类结果列表
            processing_time_ms: 处理耗时（毫秒）

        Returns:
            预测汇总统计
        """
        total_samples = len(results)

        # 统计类别分布
        class_distribution = {}
        probabilities = []
        warnings_count = 0

        for result in results:
            # 统计预测类别
            pred = result.prediction
            class_distribution[pred] = class_distribution.get(pred, 0) + 1

            # 收集概率
            probabilities.append(result.probability)

            # 统计警告数
            warnings_count += len(result.warnings)

        # 计算平均概率
        avg_probability = (
            sum(probabilities) / len(probabilities) if probabilities else 0.0
        )

        return PredictionSummary(
            total_samples=total_samples,
            class_distribution=class_distribution,
            avg_probability=avg_probability,
            processing_time_ms=processing_time_ms,
            warnings_count=warnings_count,
        )

    def _build_metadata(
        self, config: PredictionConfig, request_time: str, execution_time_ms: float
    ) -> ResponseMetadata:
        """
        构造响应元数据.

        Args:
            config: 预测配置
            request_time: 请求时间
            execution_time_ms: 执行耗时

        Returns:
            响应元数据
        """
        model_uri = None
        if self.config.source == "mlflow":
            model_uri = self.config.mlflow_model_uri
        elif self.config.source == "local":
            model_uri = self.config.model_path

        return ResponseMetadata(
            model_uri=model_uri,
            model_source=self.config.source,
            config_used=config.model_dump(),
            request_time=request_time,
            execution_time_ms=execution_time_ms,
        )

    def _create_error_response(
        self,
        code: str,
        message: str,
        details: dict,
        request_time: str,
        execution_time_ms: float,
    ) -> PredictResponse:
        """
        创建错误响应.

        Args:
            code: 错误代码
            message: 错误消息
            details: 错误详情
            request_time: 请求时间
            execution_time_ms: 执行耗时

        Returns:
            错误响应
        """
        return PredictResponse(
            success=False,
            results=None,
            summary=None,
            metadata=ResponseMetadata(
                model_uri=None,
                model_source=self.config.source,
                config_used={},
                request_time=request_time,
                execution_time_ms=execution_time_ms,
            ),
            error=ErrorDetail(code=code, message=message, details=details),
        )

    @bentoml.api
    async def health(self) -> dict:
        """健康检查接口."""
        health_check_counter.inc()
        return {
            "status": "healthy",
            "model_source": self.config.source,
            "model_version": getattr(self.model, "version", "unknown"),
        }
