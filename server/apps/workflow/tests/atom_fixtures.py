from typing import Any


def passthrough(inputs: dict[str, Any]) -> dict[str, Any]:
    return {"value": inputs.get("value")}


def uppercase(inputs: dict[str, Any]) -> dict[str, Any]:
    return {"value": str(inputs.get("value") or "").upper()}
