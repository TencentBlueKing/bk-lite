"""Issue #3852：图片分类 serving 必须在解码前后限制请求资源成本。"""

import base64
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PIL import Image
from pydantic import ValidationError

from classify_image_classification_server.serving.schemas import (
    PredictRequest,
    api_schema,
)
from classify_image_classification_server.serving.service import MLService


def _encode_png(size: tuple[int, int] = (4, 4), mode: str = "RGB") -> tuple[str, int]:
    image = Image.new(mode, size)
    if mode == "RGB":
        image.putdata(
            [
                ((index * 17) % 256, (index * 31) % 256, (index * 47) % 256)
                for index in range(size[0] * size[1])
            ]
        )
    output = BytesIO()
    image.save(output, format="PNG")
    raw = output.getvalue()
    return base64.b64encode(raw).decode("ascii"), len(raw)


def _make_service():
    service = object.__new__(MLService.inner)
    service.config = SimpleNamespace(source="dummy", model_path=None)
    service.model = MagicMock()
    prediction = {"top5": [{"class_id": 0, "class_name": "demo", "confidence": 0.9}]}
    service.model.predict.return_value = [prediction, prediction]
    return service


def test_request_rejects_single_image_over_encoded_budget(monkeypatch):
    payload, _ = _encode_png()
    monkeypatch.setenv("MLOPS_PREDICT_MAX_IMAGE_BYTES", str(len(payload) - 1))

    with pytest.raises(ValidationError, match="单图编码量超限"):
        PredictRequest(images=[payload])


def test_request_rejects_batch_over_decoded_byte_budget(monkeypatch):
    payload, decoded_bytes = _encode_png()
    monkeypatch.setenv("MLOPS_PREDICT_MAX_IMAGE_BYTES", str(len(payload)))
    monkeypatch.setenv(
        "MLOPS_PREDICT_MAX_IMAGE_BATCH_BYTES", str(decoded_bytes * 2 - 1)
    )

    with pytest.raises(ValidationError, match="批次解码字节量超限"):
        PredictRequest(images=[payload, payload])


def test_request_rejects_batch_over_encoded_byte_budget(monkeypatch):
    payload, decoded_bytes = _encode_png()
    monkeypatch.setenv("MLOPS_PREDICT_MAX_IMAGE_BYTES", str(len(payload)))
    monkeypatch.setenv(
        "MLOPS_PREDICT_MAX_IMAGE_BATCH_BASE64_BYTES", str(len(payload) * 2 - 1)
    )
    monkeypatch.setenv("MLOPS_PREDICT_MAX_IMAGE_BATCH_BYTES", str(decoded_bytes * 2))

    with pytest.raises(ValidationError, match="批次编码量超限"):
        PredictRequest(images=[payload, payload])


def test_default_encoded_budget_does_not_preempt_decoded_budget():
    decoded_limit = api_schema.DEFAULT_MAX_IMAGE_BATCH_BYTES
    encoded_size = (decoded_limit + 2) // 3 * 4

    assert api_schema.DEFAULT_MAX_IMAGE_BATCH_BASE64_BYTES >= encoded_size


def test_request_rejects_invalid_base64_tail(monkeypatch):
    payload, _ = _encode_png()
    monkeypatch.setenv("MLOPS_PREDICT_MAX_IMAGE_BYTES", str(len(payload)))

    with pytest.raises(ValidationError, match="不是有效的base64编码"):
        PredictRequest(images=[f"{payload[:-1]}!"])


def test_request_preserves_legacy_data_uri_shape(monkeypatch):
    payload, decoded_bytes = _encode_png()
    value = f"data:image/png;base64,{payload}"
    monkeypatch.setenv("MLOPS_PREDICT_MAX_IMAGE_BYTES", str(len(value)))
    monkeypatch.setenv("MLOPS_PREDICT_MAX_IMAGE_BATCH_BYTES", str(decoded_bytes))

    assert PredictRequest(images=[value]).images == [value]


def test_request_counts_data_uri_prefix_in_encoded_budget(monkeypatch):
    payload, _ = _encode_png()
    value = f"data:image/png;base64,{payload}"
    monkeypatch.setenv("MLOPS_PREDICT_MAX_IMAGE_BYTES", str(len(value) - 1))

    with pytest.raises(ValidationError, match="单图编码量超限"):
        PredictRequest(images=[value])


def test_request_rejects_non_ascii_data_uri_metadata():
    payload, _ = _encode_png()

    with pytest.raises(ValidationError, match="Data URI格式错误"):
        PredictRequest(images=[f"data:image/png;名称=图片;base64,{payload}"])


def test_request_rejects_data_uri_without_base64_marker():
    payload, _ = _encode_png()

    with pytest.raises(ValidationError, match="Data URI格式错误"):
        PredictRequest(images=[f"data:image/png,{payload}"])


def test_request_validation_does_not_materialize_decoded_batch(monkeypatch):
    payload, _ = _encode_png()
    decoder = MagicMock(side_effect=AssertionError("schema 不应完整解码图片"))
    monkeypatch.setattr(
        api_schema, "base64", SimpleNamespace(b64decode=decoder), raising=False
    )

    assert PredictRequest(images=[payload]).images == [payload]
    decoder.assert_not_called()


@pytest.mark.parametrize("value", ["", "invalid", "0", "-1"])
def test_invalid_resource_budget_falls_back_to_safe_default(monkeypatch, value):
    payload, _ = _encode_png()
    monkeypatch.setenv("MLOPS_PREDICT_MAX_IMAGE_BYTES", value)

    assert PredictRequest(images=[payload]).images == [payload]


def test_decode_helper_preserves_legacy_single_argument_call():
    payload, _ = _encode_png()
    service = _make_service()

    image = service._decode_base64_image(payload)

    assert image.size == (4, 4)
    image.close()


@pytest.mark.asyncio
async def test_service_stops_accumulating_images_over_pixel_budget(monkeypatch):
    payload, decoded_bytes = _encode_png(size=(2, 2))
    monkeypatch.setenv("MLOPS_PREDICT_MAX_IMAGE_BYTES", str(len(payload)))
    monkeypatch.setenv("MLOPS_PREDICT_MAX_IMAGE_BATCH_BYTES", str(decoded_bytes * 2))
    monkeypatch.setenv("MLOPS_PREDICT_MAX_IMAGE_BATCH_PIXELS", "4")
    service = _make_service()

    response = await service.predict([payload, payload])

    assert response.success is True
    assert response.results[0].success is True
    assert response.results[1].success is False
    assert "批次像素量超限" in response.results[1].error
    service.model.predict.assert_called_once()
    assert len(service.model.predict.call_args.args[0]) == 1


@pytest.mark.asyncio
async def test_service_checks_grayscale_pixels_before_rgb_conversion(monkeypatch):
    payload, decoded_bytes = _encode_png(size=(8, 8), mode="L")
    payload = f"data:image/png;base64,{payload}"
    monkeypatch.setenv("MLOPS_PREDICT_MAX_IMAGE_BYTES", str(len(payload)))
    monkeypatch.setenv("MLOPS_PREDICT_MAX_IMAGE_BATCH_BYTES", str(decoded_bytes * 3))
    monkeypatch.setenv("MLOPS_PREDICT_MAX_IMAGE_BATCH_PIXELS", "64")
    converted_sizes = []
    original_convert = Image.Image.convert

    def track_convert(image, *args, **kwargs):
        converted_sizes.append(image.size)
        return original_convert(image, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "convert", track_convert)
    service = _make_service()

    response = await service.predict([payload, payload, payload])

    assert [result.success for result in response.results] == [True, False, False]
    assert converted_sizes == [(8, 8)]


@pytest.mark.asyncio
async def test_public_predict_returns_e1000_for_invalid_request():
    service = _make_service()

    response = await service.predict(["not-base64" * 10])

    assert response.success is False
    assert response.error.code == "E1000"


@pytest.mark.asyncio
async def test_public_predict_returns_e1001_when_all_images_fail_to_decode():
    service = _make_service()
    payload = base64.b64encode(b"x" * 75).decode("ascii")

    response = await service.predict([payload])

    assert response.success is False
    assert response.error.code == "E1001"


@pytest.mark.asyncio
async def test_service_allows_legacy_batch_when_pixel_budget_is_raised(monkeypatch):
    payload, decoded_bytes = _encode_png(size=(2, 2))
    monkeypatch.setenv("MLOPS_PREDICT_MAX_IMAGE_BYTES", str(len(payload)))
    monkeypatch.setenv("MLOPS_PREDICT_MAX_IMAGE_BATCH_BYTES", str(decoded_bytes * 2))
    monkeypatch.setenv("MLOPS_PREDICT_MAX_IMAGE_BATCH_PIXELS", "8")
    service = _make_service()

    response = await service.predict([payload, payload])

    assert response.success is True
    assert [result.success for result in response.results] == [True, True]
    assert len(service.model.predict.call_args.args[0]) == 2
