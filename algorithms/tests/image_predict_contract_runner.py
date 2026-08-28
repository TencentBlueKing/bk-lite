"""在单一算法运行时中验证共享图片预测契约。"""

import importlib
import json
import os
import sys
from pathlib import Path

from pydantic import ValidationError

ALGORITHMS_DIR = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ALGORITHMS_DIR / "contracts/image_predict_v1.json"
SERVICES = {
    "image_classification": "classify_image_classification_server",
    "object_detection": "classify_object_detection_server",
}


def _load_runtime(service_name):
    package = SERVICES[service_name]
    sys.path.insert(0, str(ALGORITHMS_DIR / package))
    schema = importlib.import_module(f"{package}.serving.schemas.api_schema")
    service_module = importlib.import_module(f"{package}.serving.service")
    return schema, service_module.MLService


def _validate_request_contract(contract, schema):
    json_schema = schema.PredictRequest.model_json_schema()
    assert set(schema.PredictRequest.model_fields) == set(contract["request_fields"])
    assert json_schema["properties"]["images"]["minItems"] == contract["images"]["min_items"]
    assert json_schema["properties"]["images"]["maxItems"] == contract["images"]["max_items"]

    for case in contract["request_cases"]:
        if case["valid"]:
            assert schema.PredictRequest(images=case["images"]).images == case["images"]
        else:
            try:
                schema.PredictRequest(images=case["images"])
            except ValidationError:
                continue
            raise AssertionError(f"invalid request case accepted: {case['name']}")


def _validate_budget_defaults(contract, schema):
    budget = contract["budget_defaults"]
    os.environ.pop("MLOPS_PREDICT_IMAGE_BUDGET_MODE", None)
    assert schema.get_image_budget_mode() == budget["mode"]
    assert schema.DEFAULT_MAX_IMAGE_BASE64_BYTES == budget["max_image_base64_bytes"]
    assert schema.DEFAULT_MAX_IMAGE_BATCH_BASE64_BYTES == budget["max_batch_base64_bytes"]
    assert schema.DEFAULT_MAX_IMAGE_BATCH_BYTES == budget["max_batch_decoded_bytes"]
    assert schema.DEFAULT_MAX_IMAGE_BATCH_PIXELS == budget["max_batch_pixels"]


def _validate_response_contract(contract, service_name, schema):
    service_contract = contract["services"][service_name]
    assert set(schema.ErrorDetail.model_fields) == set(contract["error_fields"])
    error = schema.ErrorDetail.model_validate(contract["error_example"])
    assert error.model_dump(mode="json") == contract["error_example"]
    assert set(schema.PredictResponse.model_fields) == set(contract["response_fields"])
    assert set(schema.ImageResult.model_fields) == set(contract["result_common_fields"]) | {service_contract["result_payload_field"]}
    assert set(schema.PredictionMetadata.model_fields) == set(contract["metadata_common_fields"]) | set(service_contract["metadata_extension_fields"])
    assert set(schema.PredictConfig.model_fields) == set(service_contract["config_defaults"])
    assert {name: field.default for name, field in schema.PredictConfig.model_fields.items()} == service_contract["config_defaults"]

    response = schema.PredictResponse.model_validate(service_contract["response_example"])
    assert response.model_dump(mode="json") == service_contract["response_example"]


def _validate_decoder_contract(contract, service_class):
    service = object.__new__(service_class.inner)
    for value in contract["decoder_valid_inputs"]:
        image = service._decode_base64_image(value)
        try:
            assert image.size == tuple(contract["decoded_image"]["size"])
            assert image.mode == contract["decoded_image"]["mode"]
        finally:
            image.close()


def main():
    service_name = sys.argv[1]
    if service_name not in SERVICES:
        raise SystemExit(f"unknown service: {service_name}")

    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert contract["contract"] == "image-predict"
    assert contract["version"] == 1
    schema, service_class = _load_runtime(service_name)
    _validate_budget_defaults(contract, schema)
    os.environ["MLOPS_PREDICT_IMAGE_BUDGET_MODE"] = "enforce"
    _validate_request_contract(contract, schema)
    _validate_response_contract(contract, service_name, schema)
    _validate_decoder_contract(contract, service_class)
    print(json.dumps({"contract": contract["contract"], "service": service_name, "version": contract["version"]}))


if __name__ == "__main__":
    main()
