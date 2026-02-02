"""API Schema definitions for serving endpoints."""

from .api_schema import (
    BoundingBox,
    Detection,
    PredictConfig,
    PredictRequest,
    ImageResult,
    PredictionMetadata,
    ErrorDetail,
    PredictResponse,
)

__all__ = [
    "BoundingBox",
    "Detection",
    "PredictConfig",
    "PredictRequest",
    "ImageResult",
    "PredictionMetadata",
    "ErrorDetail",
    "PredictResponse",
]
