"""API Schema definitions for serving endpoints."""

from .api_schema import (
    PredictRequest,
    PredictResponse,
    TimeSeriesPoint,
    PredictionConfig,
    ResponseMetadata,
    ErrorDetail
)

__all__ = [
    "PredictRequest",
    "PredictResponse",
    "TimeSeriesPoint",
    "PredictionConfig",
    "ResponseMetadata",
    "ErrorDetail"
]
