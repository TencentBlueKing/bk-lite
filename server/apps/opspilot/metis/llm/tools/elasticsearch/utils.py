from typing import Any, Dict


def ensure_json_serializable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.hex()
    if isinstance(value, dict):
        return {str(k): ensure_json_serializable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [ensure_json_serializable(item) for item in value]
    return str(value)


def build_success_response(data: Any, **kwargs: Any) -> Dict[str, Any]:
    response = {"success": True, "data": ensure_json_serializable(data)}
    response.update({key: ensure_json_serializable(val) for key, val in kwargs.items()})
    return response


def build_error_response(error: Any, error_type: str = "es_error") -> Dict[str, Any]:
    return {"success": False, "error": str(error), "error_type": error_type}


def require_confirm(confirm: bool, operation: str):
    if confirm:
        return None
    return build_error_response(f"Operation '{operation}' requires confirm=True", error_type="confirmation_required")
