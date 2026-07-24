import io
import zipfile

import pytest

from apps.mlops.tasks import image_classification as image_task
from apps.mlops.tasks import object_detection as object_task


pytestmark = pytest.mark.unit

_CHUNK_SIZE = 64 * 1024
_IMAGE_BYTES = bytes(range(256)) * 768


def _make_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("sample.jpg", _IMAGE_BYTES)
    return buffer.getvalue()


class _ShortReadStream(io.BytesIO):
    def __init__(self, content: bytes):
        super().__init__(content)
        self.requested_sizes = []

    def read(self, size=-1):
        self.requested_sizes.append(size)
        if size >= 0:
            size = min(size, 8192)
        return super().read(size)


class _FakeFieldFile:
    name = "datasets/sample.zip"

    def __init__(self, content: bytes, opened_streams: list[_ShortReadStream]):
        self._content = content
        self._opened_streams = opened_streams

    def open(self, mode="rb"):
        assert mode == "rb"
        stream = _ShortReadStream(self._content)
        self._opened_streams.append(stream)
        return stream


def _patch_storage(monkeypatch, module):
    uploaded = {}

    class _FakeStorage:
        def __init__(self, *args, **kwargs):
            pass

        def save(self, path, content):
            uploaded["path"] = path
            uploaded["content"] = content.read()
            return path

        def url(self, path):
            return f"https://storage.invalid/{path}"

    monkeypatch.setattr(module, "MinioBackend", _FakeStorage)
    return uploaded


def _assert_streamed(opened_streams):
    assert len(opened_streams) == 3
    assert all(stream.requested_sizes for stream in opened_streams)
    requested_sizes = [stream.requested_sizes for stream in opened_streams]
    assert all(
        0 < requested_size <= _CHUNK_SIZE
        for stream_sizes in requested_sizes
        for requested_size in stream_sizes
    ), requested_sizes


@pytest.mark.django_db
def test_image_publish_streams_each_source_zip_in_bounded_chunks(monkeypatch):
    from apps.mlops.models.image_classification import (
        ImageClassificationDataset,
        ImageClassificationDatasetRelease,
        ImageClassificationTrainData,
    )

    dataset = ImageClassificationDataset.objects.create(
        name="image-dataset", description="", team=[1]
    )
    release = ImageClassificationDatasetRelease.objects.create(
        name="release",
        description="",
        dataset=dataset,
        version="v1",
        dataset_file="placeholder.zip",
        status="pending",
        metadata={},
        file_size=0,
    )
    train_data = [
        ImageClassificationTrainData.objects.create(
            name=name,
            dataset=dataset,
            metadata={"labels": {"sample.jpg": "cat"}, "classes": ["cat"]},
        )
        for name in ("train", "val", "test")
    ]

    source_zip = _make_zip()
    opened_streams = []
    original_get = ImageClassificationTrainData.objects.get

    def fake_get(*args, **kwargs):
        data = original_get(*args, **kwargs)
        data.train_data = _FakeFieldFile(source_zip, opened_streams)
        return data

    monkeypatch.setattr(ImageClassificationTrainData.objects, "get", fake_get)
    uploaded = _patch_storage(monkeypatch, image_task)

    result = image_task.publish_dataset_release_async.run(
        release.id, *(data.id for data in train_data)
    )

    assert result["result"] is True
    _assert_streamed(opened_streams)
    with zipfile.ZipFile(io.BytesIO(uploaded["content"])) as archive:
        assert archive.read("train/cat/sample.jpg") == _IMAGE_BYTES
        assert archive.read("val/cat/sample.jpg") == _IMAGE_BYTES
        assert archive.read("test/cat/sample.jpg") == _IMAGE_BYTES


@pytest.mark.django_db
def test_object_publish_streams_each_source_zip_in_bounded_chunks(monkeypatch):
    from apps.mlops.models.object_detection import (
        ObjectDetectionDataset,
        ObjectDetectionDatasetRelease,
        ObjectDetectionTrainData,
    )

    dataset = ObjectDetectionDataset.objects.create(
        name="object-dataset", description="", team=[1]
    )
    release = ObjectDetectionDatasetRelease.objects.create(
        name="release",
        description="",
        dataset=dataset,
        version="v1",
        dataset_file="placeholder.zip",
        status="pending",
        metadata={},
        file_size=0,
    )
    metadata = {
        "classes": ["cat"],
        "labels": {
            "sample.jpg": [
                {
                    "class_id": 0,
                    "x_center": 0.5,
                    "y_center": 0.5,
                    "width": 0.25,
                    "height": 0.25,
                }
            ]
        },
    }
    train_data = [
        ObjectDetectionTrainData.objects.create(
            name=name, dataset=dataset, metadata=metadata
        )
        for name in ("train", "val", "test")
    ]

    source_zip = _make_zip()
    opened_streams = []
    original_get = ObjectDetectionTrainData.objects.get

    def fake_get(*args, **kwargs):
        data = original_get(*args, **kwargs)
        data.train_data = _FakeFieldFile(source_zip, opened_streams)
        return data

    monkeypatch.setattr(ObjectDetectionTrainData.objects, "get", fake_get)
    uploaded = _patch_storage(monkeypatch, object_task)

    result = object_task.publish_dataset_release_async.run(
        release.id, *(data.id for data in train_data)
    )

    assert result["result"] is True
    _assert_streamed(opened_streams)
    with zipfile.ZipFile(io.BytesIO(uploaded["content"])) as archive:
        assert archive.read("images/train/sample.jpg") == _IMAGE_BYTES
        assert archive.read("images/val/sample.jpg") == _IMAGE_BYTES
        assert archive.read("images/test/sample.jpg") == _IMAGE_BYTES
