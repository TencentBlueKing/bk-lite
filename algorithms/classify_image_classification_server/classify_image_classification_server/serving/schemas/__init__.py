"""API Schema definitions for serving endpoints."""

from .api_schema import (
    PredictRequest, 
    PredictResponse,
    PredictConfig,
    ClassPrediction,
    ImageResult,
    PredictionMetadata,
    ErrorDetail
)

__all__ = [
    "PredictRequest", 
    "PredictResponse",
    "PredictConfig",
    "ClassPrediction",
    "ImageResult",
    "PredictionMetadata",
    "ErrorDetail"
]
