"""
MLOPS Module Exception Hierarchy

Provides structured exception handling for all MLOPS operations.
Replaces generic Exception handlers with specific exception types for better observability.
"""


class MLOpsException(Exception):
    """
    Base exception for all MLOPS operations.
    
    All MLOPS-specific exceptions should inherit from this class.
    This allows for targeted exception handling and better error reporting.
    """
    
    def __init__(self, message, error_code=None, details=None):
        """
        Initialize MLOpsException.
        
        Args:
            message: Human-readable error message
            error_code: Machine-readable error code (e.g., "WEBHOOK_TIMEOUT")
            details: Dictionary of additional context for debugging
        """
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.details = details or {}
        super().__init__(self.message)
    
    def to_dict(self):
        """Convert exception to dictionary for API responses."""
        return {
            "error_type": self.__class__.__name__,
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
        }


# ============================================================================
# Webhook-related Exceptions
# ============================================================================

class WebhookException(MLOpsException):
    """Base exception for webhook client operations."""
    pass


class WebhookConnectionError(WebhookException):
    """Failed to establish connection to webhook service."""
    
    def __init__(self, webhook_url, original_error=None):
        message = f"Failed to connect to webhook service at {webhook_url}"
        details = {"webhook_url": webhook_url}
        if original_error:
            details["original_error"] = str(original_error)
        super().__init__(message, "WEBHOOK_CONNECTION_ERROR", details)


class WebhookTimeoutError(WebhookException):
    """Webhook request timed out."""
    
    def __init__(self, webhook_url, timeout_seconds):
        message = f"Webhook request to {webhook_url} timed out after {timeout_seconds}s"
        details = {"webhook_url": webhook_url, "timeout_seconds": timeout_seconds}
        super().__init__(message, "WEBHOOK_TIMEOUT", details)


class WebhookResponseError(WebhookException):
    """Webhook returned an error response."""
    
    def __init__(self, status_code, response_body):
        message = f"Webhook returned error status {status_code}"
        details = {"status_code": status_code, "response_body": response_body}
        super().__init__(message, "WEBHOOK_RESPONSE_ERROR", details)


class WebhookInvalidResponseError(WebhookException):
    """Webhook response format is invalid."""
    
    def __init__(self, expected_format, actual_response):
        message = f"Webhook response format is invalid. Expected {expected_format}"
        details = {"expected_format": expected_format, "actual_response": str(actual_response)}
        super().__init__(message, "WEBHOOK_INVALID_RESPONSE", details)


# ============================================================================
# Dataset-related Exceptions
# ============================================================================

class DatasetException(MLOpsException):
    """Base exception for dataset operations."""
    pass


class DatasetNotFoundError(DatasetException):
    """Requested dataset not found."""
    
    def __init__(self, dataset_id=None, dataset_name=None):
        message = f"Dataset not found"
        details = {}
        if dataset_id:
            message += f" (id={dataset_id})"
            details["dataset_id"] = dataset_id
        if dataset_name:
            message += f" (name={dataset_name})"
            details["dataset_name"] = dataset_name
        super().__init__(message, "DATASET_NOT_FOUND", details)


class DatasetValidationError(DatasetException):
    """Dataset validation failed."""
    
    def __init__(self, validation_errors):
        message = "Dataset validation failed"
        details = {"errors": validation_errors}
        super().__init__(message, "DATASET_VALIDATION_ERROR", details)


class DatasetUploadError(DatasetException):
    """Failed to upload dataset file."""
    
    def __init__(self, filename, original_error=None):
        message = f"Failed to upload dataset file: {filename}"
        details = {"filename": filename}
        if original_error:
            details["original_error"] = str(original_error)
        super().__init__(message, "DATASET_UPLOAD_ERROR", details)


class DatasetDownloadError(DatasetException):
    """Failed to download dataset."""
    
    def __init__(self, dataset_id, original_error=None):
        message = f"Failed to download dataset (id={dataset_id})"
        details = {"dataset_id": dataset_id}
        if original_error:
            details["original_error"] = str(original_error)
        super().__init__(message, "DATASET_DOWNLOAD_ERROR", details)


class DatasetStorageError(DatasetException):
    """Failed to store dataset in MinIO/S3."""
    
    def __init__(self, bucket, key, original_error=None):
        message = f"Failed to store dataset in storage ({bucket}/{key})"
        details = {"bucket": bucket, "key": key}
        if original_error:
            details["original_error"] = str(original_error)
        super().__init__(message, "DATASET_STORAGE_ERROR", details)


class DatasetReleaseError(DatasetException):
    """Failed to create/release dataset version."""
    
    def __init__(self, dataset_id, reason=None):
        message = f"Failed to release dataset (id={dataset_id})"
        details = {"dataset_id": dataset_id}
        if reason:
            message += f": {reason}"
            details["reason"] = reason
        super().__init__(message, "DATASET_RELEASE_ERROR", details)


# ============================================================================
# Training-related Exceptions
# ============================================================================

class TrainingException(MLOpsException):
    """Base exception for training operations."""
    pass


class TrainJobNotFoundError(TrainingException):
    """Requested training job not found."""
    
    def __init__(self, job_id=None):
        message = f"Training job not found"
        details = {}
        if job_id:
            message += f" (id={job_id})"
            details["job_id"] = job_id
        super().__init__(message, "TRAIN_JOB_NOT_FOUND", details)


class TrainJobValidationError(TrainingException):
    """Training job validation failed."""
    
    def __init__(self, validation_errors):
        message = "Training job validation failed"
        details = {"errors": validation_errors}
        super().__init__(message, "TRAIN_JOB_VALIDATION_ERROR", details)


class TrainJobStartError(TrainingException):
    """Failed to start training job."""
    
    def __init__(self, job_id, reason=None):
        message = f"Failed to start training job (id={job_id})"
        details = {"job_id": job_id}
        if reason:
            message += f": {reason}"
            details["reason"] = reason
        super().__init__(message, "TRAIN_JOB_START_ERROR", details)


class TrainJobStopError(TrainingException):
    """Failed to stop training job."""
    
    def __init__(self, job_id, reason=None):
        message = f"Failed to stop training job (id={job_id})"
        details = {"job_id": job_id}
        if reason:
            message += f": {reason}"
            details["reason"] = reason
        super().__init__(message, "TRAIN_JOB_STOP_ERROR", details)


class TrainJobTimeoutError(TrainingException):
    """Training job timed out."""
    
    def __init__(self, job_id, timeout_seconds):
        message = f"Training job timed out after {timeout_seconds}s (id={job_id})"
        details = {"job_id": job_id, "timeout_seconds": timeout_seconds}
        super().__init__(message, "TRAIN_JOB_TIMEOUT", details)


class TrainJobFailedError(TrainingException):
    """Training job failed."""
    
    def __init__(self, job_id, error_message=None):
        message = f"Training job failed (id={job_id})"
        details = {"job_id": job_id}
        if error_message:
            message += f": {error_message}"
            details["error_message"] = error_message
        super().__init__(message, "TRAIN_JOB_FAILED", details)


# ============================================================================
# Model Serving-related Exceptions
# ============================================================================

class ServingException(MLOpsException):
    """Base exception for model serving operations."""
    pass


class ServingNotFoundError(ServingException):
    """Requested serving instance not found."""
    
    def __init__(self, serving_id=None):
        message = f"Serving instance not found"
        details = {}
        if serving_id:
            message += f" (id={serving_id})"
            details["serving_id"] = serving_id
        super().__init__(message, "SERVING_NOT_FOUND", details)


class ServingValidationError(ServingException):
    """Serving instance validation failed."""
    
    def __init__(self, validation_errors):
        message = "Serving validation failed"
        details = {"errors": validation_errors}
        super().__init__(message, "SERVING_VALIDATION_ERROR", details)


class ServingStartError(ServingException):
    """Failed to start serving container."""
    
    def __init__(self, serving_id, reason=None):
        message = f"Failed to start serving (id={serving_id})"
        details = {"serving_id": serving_id}
        if reason:
            message += f": {reason}"
            details["reason"] = reason
        super().__init__(message, "SERVING_START_ERROR", details)


class ServingStopError(ServingException):
    """Failed to stop serving container."""
    
    def __init__(self, serving_id, reason=None):
        message = f"Failed to stop serving (id={serving_id})"
        details = {"serving_id": serving_id}
        if reason:
            message += f": {reason}"
            details["reason"] = reason
        super().__init__(message, "SERVING_STOP_ERROR", details)


class ServingPredictionError(ServingException):
    """Prediction request failed."""
    
    def __init__(self, serving_id, reason=None):
        message = f"Prediction failed for serving (id={serving_id})"
        details = {"serving_id": serving_id}
        if reason:
            message += f": {reason}"
            details["reason"] = reason
        super().__init__(message, "SERVING_PREDICTION_ERROR", details)


class ServingContainerError(ServingException):
    """Container operation failed."""
    
    def __init__(self, container_id, operation, reason=None):
        message = f"Container operation '{operation}' failed (container={container_id})"
        details = {"container_id": container_id, "operation": operation}
        if reason:
            message += f": {reason}"
            details["reason"] = reason
        super().__init__(message, "SERVING_CONTAINER_ERROR", details)


# ============================================================================
# MLflow-related Exceptions
# ============================================================================

class MLflowException(MLOpsException):
    """Base exception for MLflow operations."""
    pass


class MLflowConnectionError(MLflowException):
    """Failed to connect to MLflow service."""
    
    def __init__(self, mlflow_url, original_error=None):
        message = f"Failed to connect to MLflow service at {mlflow_url}"
        details = {"mlflow_url": mlflow_url}
        if original_error:
            details["original_error"] = str(original_error)
        super().__init__(message, "MLFLOW_CONNECTION_ERROR", details)


class MLflowExperimentError(MLflowException):
    """MLflow experiment operation failed."""
    
    def __init__(self, experiment_name, operation, reason=None):
        message = f"MLflow {operation} failed for experiment '{experiment_name}'"
        details = {"experiment_name": experiment_name, "operation": operation}
        if reason:
            message += f": {reason}"
            details["reason"] = reason
        super().__init__(message, "MLFLOW_EXPERIMENT_ERROR", details)


class MLflowRunError(MLflowException):
    """MLflow run operation failed."""
    
    def __init__(self, run_id, operation, reason=None):
        message = f"MLflow {operation} failed for run '{run_id}'"
        details = {"run_id": run_id, "operation": operation}
        if reason:
            message += f": {reason}"
            details["reason"] = reason
        super().__init__(message, "MLFLOW_RUN_ERROR", details)


class MLflowModelError(MLflowException):
    """MLflow model operation failed."""
    
    def __init__(self, model_name, version, operation, reason=None):
        message = f"MLflow {operation} failed for model '{model_name}' version '{version}'"
        details = {"model_name": model_name, "version": version, "operation": operation}
        if reason:
            message += f": {reason}"
            details["reason"] = reason
        super().__init__(message, "MLFLOW_MODEL_ERROR", details)


# ============================================================================
# Configuration-related Exceptions
# ============================================================================

class ConfigException(MLOpsException):
    """Base exception for configuration operations."""
    pass


class AlgorithmConfigNotFoundError(ConfigException):
    """Algorithm configuration not found."""
    
    def __init__(self, algorithm_type=None, name=None):
        message = "Algorithm configuration not found"
        details = {}
        if algorithm_type:
            details["algorithm_type"] = algorithm_type
        if name:
            details["name"] = name
        if details:
            message += f" ({', '.join(f'{k}={v}' for k, v in details.items())})"
        super().__init__(message, "ALGORITHM_CONFIG_NOT_FOUND", details)


class AlgorithmConfigValidationError(ConfigException):
    """Algorithm configuration validation failed."""
    
    def __init__(self, validation_errors):
        message = "Algorithm configuration validation failed"
        details = {"errors": validation_errors}
        super().__init__(message, "ALGORITHM_CONFIG_VALIDATION_ERROR", details)


# ============================================================================
# Permission and Authentication Exceptions
# ============================================================================

class PermissionException(MLOpsException):
    """Base exception for permission-related operations."""
    pass


class InsufficientPermissionError(PermissionException):
    """User does not have required permission."""
    
    def __init__(self, permission_key=None, user=None):
        message = "Insufficient permission"
        details = {}
        if permission_key:
            message += f" for '{permission_key}'"
            details["permission_key"] = permission_key
        if user:
            details["user"] = str(user)
        super().__init__(message, "INSUFFICIENT_PERMISSION", details)


__all__ = [
    # Base
    "MLOpsException",
    # Webhook
    "WebhookException",
    "WebhookConnectionError",
    "WebhookTimeoutError",
    "WebhookResponseError",
    "WebhookInvalidResponseError",
    # Dataset
    "DatasetException",
    "DatasetNotFoundError",
    "DatasetValidationError",
    "DatasetUploadError",
    "DatasetDownloadError",
    "DatasetStorageError",
    "DatasetReleaseError",
    # Training
    "TrainingException",
    "TrainJobNotFoundError",
    "TrainJobValidationError",
    "TrainJobStartError",
    "TrainJobStopError",
    "TrainJobTimeoutError",
    "TrainJobFailedError",
    # Serving
    "ServingException",
    "ServingNotFoundError",
    "ServingValidationError",
    "ServingStartError",
    "ServingStopError",
    "ServingPredictionError",
    "ServingContainerError",
    # MLflow
    "MLflowException",
    "MLflowConnectionError",
    "MLflowExperimentError",
    "MLflowRunError",
    "MLflowModelError",
    # Configuration
    "ConfigException",
    "AlgorithmConfigNotFoundError",
    "AlgorithmConfigValidationError",
    # Permission
    "PermissionException",
    "InsufficientPermissionError",
]
