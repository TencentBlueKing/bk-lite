"""Issue #4619：公开 max_detections 契约必须到达 YOLO NMS。"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PIL import Image

from classify_object_detection_server.serving.service import MLService
from classify_object_detection_server.training.models.yolo_wrapper import (
    YOLODetectionWrapper,
)


EMPTY_PREDICTION = {
    "boxes": [],
    "classes": [],
    "confidences": [],
    "labels": [],
    "count": 0,
}


def make_service():
    service = object.__new__(MLService.inner)
    service.config = SimpleNamespace(
        source="dummy",
        model_path=None,
        mlflow_model_uri=None,
    )
    service.model = MagicMock()
    service.model.predict.return_value = [EMPTY_PREDICTION]
    service._decode_base64_image = MagicMock(
        return_value=Image.new("RGB", (2, 2))
    )
    return service


@pytest.mark.asyncio
@pytest.mark.parametrize("max_detections", [1, 300, 301, 1_000])
async def test_service_passes_max_detections_to_model(max_detections):
    service = make_service()

    response = await service.predict(
        ["A" * 100],
        {
            "conf_threshold": 0.25,
            "iou_threshold": 0.45,
            "max_detections": max_detections,
        },
    )

    assert response.success is True
    service.model.predict.assert_called_once_with(
        {
            "images": [service._decode_base64_image.return_value],
            "conf": 0.25,
            "iou": 0.45,
            "max_det": max_detections,
        }
    )


@pytest.mark.parametrize("max_det", [1, 300, 301, 1_000])
def test_wrapper_passes_max_det_to_ultralytics(max_det):
    wrapper = YOLODetectionWrapper()
    wrapper.model = MagicMock()
    wrapper.model.predict.return_value = [SimpleNamespace(boxes=None)]
    wrapper.class_names = []
    images = [object()]

    predictions = wrapper.predict(
        None,
        {
            "images": images,
            "conf": 0.25,
            "iou": 0.45,
            "imgsz": 640,
            "max_det": max_det,
        },
    )

    assert predictions == [EMPTY_PREDICTION]
    wrapper.model.predict.assert_called_once_with(
        images,
        conf=0.25,
        iou=0.45,
        imgsz=640,
        max_det=max_det,
        verbose=False,
    )


def test_wrapper_preserves_default_max_detections_for_legacy_input():
    wrapper = YOLODetectionWrapper()
    wrapper.model = MagicMock()
    wrapper.model.predict.return_value = [SimpleNamespace(boxes=None)]
    wrapper.class_names = []

    wrapper.predict(None, {"images": [object()]})

    assert wrapper.model.predict.call_args.kwargs["max_det"] == 300


@pytest.mark.asyncio
async def test_service_keeps_response_slice_as_defense_in_depth():
    service = make_service()
    detection_count = 305
    service.model.predict.return_value = [
        {
            "boxes": [[0.1, 0.1, 0.2, 0.2]] * detection_count,
            "classes": [0] * detection_count,
            "confidences": [0.9] * detection_count,
            "labels": ["object"] * detection_count,
            "count": detection_count,
        }
    ]

    response = await service.predict(
        ["A" * 100], {"max_detections": 301}
    )

    assert response.success is True
    assert len(response.results[0].detections) == 301
    assert response.metadata.total_detections == 301
