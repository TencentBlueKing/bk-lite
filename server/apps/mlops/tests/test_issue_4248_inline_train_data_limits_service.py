"""Issue #4248 serializer 与 storage 资源契约。"""

from io import BytesIO

import pytest
from rest_framework import serializers

from apps.mlops.tests._issue_4248_inline_helpers import (
    RECORD_LIMIT_CASES,
    SERIALIZER_CASES,
    _fixed_base_content,
    _install_file_reader,
    _instances,
    _request,
)

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize(("suffix", "basename", "seed"), SERIALIZER_CASES)
@pytest.mark.parametrize("record_count", (1, 10, 100))
def test_fixed_base_1_10_100_growth_is_bounded(
    monkeypatch,
    mlops_user,
    suffix,
    basename,
    seed,
    record_count,
):
    serializer_class, instances = _instances(suffix, basename, record_count)
    content = _fixed_base_content(seed)
    reads = _install_file_reader(monkeypatch, instances, content)
    serializer = serializer_class(
        instances,
        many=True,
        context={"request": _request(mlops_user)},
    )

    if record_count == 100:
        with pytest.raises(serializers.ValidationError) as exc:
            serializer.data
        assert exc.value.detail["reason"] == "list_items"
        assert reads == []
    else:
        assert len(serializer.data) == record_count
        assert len(reads) == record_count
        assert len(reads) * len(content) == record_count * len(content)


@pytest.mark.parametrize(("suffix", "basename", "content"), SERIALIZER_CASES)
def test_inline_list_over_item_limit_is_rejected_before_remote_reads(
    monkeypatch,
    mlops_user,
    suffix,
    basename,
    content,
):
    serializer_class, instances = _instances(suffix, basename, 100)
    reads = _install_file_reader(monkeypatch, instances, content)

    with pytest.raises(serializers.ValidationError) as exc:
        serializer_class(
            instances,
            many=True,
            context={"request": _request(mlops_user)},
        ).data

    assert exc.value.detail["error"] == "inline_train_data_limit_exceeded"
    assert exc.value.detail["reason"] == "list_items"
    assert reads == []


def test_inline_list_rechecks_item_limit_after_queryset_count(
    monkeypatch,
    mlops_user,
):
    serializer_class, instances = _instances("classification", "Classification", 21)
    reads = _install_file_reader(
        monkeypatch,
        instances,
        b"text,label\nhealthy,ok\n",
    )

    class GrowingQuerySet:
        def filter(self, **_kwargs):
            return self

        def exclude(self, **_kwargs):
            return self

        def count(self):
            return 20

        def __iter__(self):
            return iter(instances)

    with pytest.raises(serializers.ValidationError) as exc:
        serializer_class(
            GrowingQuerySet(),
            many=True,
            context={"request": _request(mlops_user)},
        ).data

    assert exc.value.detail["reason"] == "list_items"
    assert len(reads) == 20


@pytest.mark.parametrize(("suffix", "basename", "content"), SERIALIZER_CASES)
def test_inline_list_over_file_limit_has_stable_error(
    monkeypatch,
    mlops_user,
    suffix,
    basename,
    content,
):
    monkeypatch.setenv("MLOPS_INLINE_TRAIN_DATA_MAX_FILE_BYTES", "16")
    serializer_class, instances = _instances(suffix, basename, 1)
    reads = _install_file_reader(monkeypatch, instances, content)

    with pytest.raises(serializers.ValidationError) as exc:
        serializer_class(
            instances,
            many=True,
            context={"request": _request(mlops_user)},
        ).data

    assert exc.value.detail["error"] == "inline_train_data_limit_exceeded"
    assert exc.value.detail["reason"] == "file_bytes"
    assert reads == ["fixtures/0.data"]


def test_inline_list_over_total_limit_stops_at_bounded_prefix(
    monkeypatch,
    mlops_user,
):
    monkeypatch.setenv("MLOPS_INLINE_TRAIN_DATA_MAX_FILE_BYTES", "64")
    monkeypatch.setenv("MLOPS_INLINE_TRAIN_DATA_MAX_TOTAL_BYTES", "32")
    serializer_class, instances = _instances("classification", "Classification", 2)
    content = b"text,label\nhealthy,ok\n"
    reads = []
    transferred = []

    class TrackingStream(BytesIO):
        def read(self, size=-1):
            chunk = super().read(size)
            transferred.append(len(chunk))
            return chunk

    def open_file(name, *_args, **_kwargs):
        reads.append(name)
        return TrackingStream(content)

    monkeypatch.setattr(instances[0].train_data.storage, "open", open_file)

    with pytest.raises(serializers.ValidationError) as exc:
        serializer_class(
            instances,
            many=True,
            context={"request": _request(mlops_user)},
        ).data

    assert exc.value.detail["error"] == "inline_train_data_limit_exceeded"
    assert exc.value.detail["reason"] == "total_bytes"
    assert reads == ["fixtures/0.data", "fixtures/1.data"]
    assert sum(transferred) == 33


@pytest.mark.parametrize(("suffix", "basename", "content"), RECORD_LIMIT_CASES)
def test_inline_list_record_limit_bounds_parser_object_expansion(
    monkeypatch,
    mlops_user,
    suffix,
    basename,
    content,
):
    monkeypatch.setenv("MLOPS_INLINE_TRAIN_DATA_MAX_RECORDS", "1")
    serializer_class, instances = _instances(suffix, basename, 1)
    reads = _install_file_reader(monkeypatch, instances, content)

    with pytest.raises(serializers.ValidationError) as exc:
        serializer_class(
            instances,
            many=True,
            context={"request": _request(mlops_user)},
        ).data

    assert exc.value.detail["error"] == "inline_train_data_limit_exceeded"
    assert exc.value.detail["reason"] == "records"
    assert reads == ["fixtures/0.data"]


@pytest.mark.parametrize(("suffix", "basename", "content"), SERIALIZER_CASES)
def test_inline_list_reads_short_remote_chunks_until_eof(
    monkeypatch,
    mlops_user,
    suffix,
    basename,
    content,
):
    class ShortReadStream(BytesIO):
        def read(self, size=-1):
            return super().read(min(size, 3))

    serializer_class, instances = _instances(suffix, basename, 1)
    reads = _install_file_reader(
        monkeypatch,
        instances,
        content,
        stream_factory=ShortReadStream,
    )

    data = serializer_class(
        instances,
        many=True,
        context={"request": _request(mlops_user)},
    ).data

    assert len(data[0]["train_data"]) >= 1
    assert "error" not in data[0]
    assert reads == ["fixtures/0.data"]


def test_inline_txt_invalid_utf8_keeps_item_level_error_contract(
    monkeypatch,
    mlops_user,
):
    serializer_class, instances = _instances("log_clustering", "LogClustering", 1)
    reads = _install_file_reader(monkeypatch, instances, b"\xff")

    data = serializer_class(
        instances,
        many=True,
        context={"request": _request(mlops_user)},
    ).data

    assert data[0]["train_data"] == []
    assert "error" in data[0]
    assert reads == ["fixtures/0.data"]


def test_inline_storage_missing_does_not_block_following_item(
    monkeypatch,
    mlops_user,
):
    serializer_class, instances = _instances("classification", "Classification", 2)
    reads = []

    def open_file(name, *_args, **_kwargs):
        reads.append(name)
        if name == "fixtures/0.data":
            raise FileNotFoundError(name)
        return BytesIO(b"text,label\nhealthy,ok\n")

    monkeypatch.setattr(instances[0].train_data.storage, "open", open_file)

    data = serializer_class(
        instances,
        many=True,
        context={"request": _request(mlops_user)},
    ).data

    assert data[0]["train_data"] == []
    assert "error" in data[0]
    assert data[1]["train_data"][0]["text"] == "healthy"
    assert reads == ["fixtures/0.data", "fixtures/1.data"]


def test_normal_inline_list_preserves_order_and_duplicate_instances(
    monkeypatch,
    mlops_user,
):
    serializer_class, instances = _instances("classification", "Classification", 2)
    instances = [instances[1], instances[0], instances[1]]
    reads = _install_file_reader(
        monkeypatch,
        instances,
        b"text,label\nhealthy,ok\n",
    )

    data = serializer_class(
        instances,
        many=True,
        context={"request": _request(mlops_user)},
    ).data

    assert [item["id"] for item in data] == [2, 1, 2]
    assert reads == ["fixtures/1.data", "fixtures/0.data", "fixtures/1.data"]
    assert [item["train_data"][0]["text"] for item in data] == [
        "healthy",
        "healthy",
        "healthy",
    ]


def test_detail_inline_read_keeps_existing_unbounded_behavior(
    monkeypatch,
    mlops_user,
):
    monkeypatch.setenv("MLOPS_INLINE_TRAIN_DATA_MAX_FILE_BYTES", "16")
    serializer_class, instances = _instances("classification", "Classification", 1)
    content = b"text,label\nhealthy,ok\n"
    reads = _install_file_reader(monkeypatch, instances, content)

    data = serializer_class(
        instances[0],
        context={"request": _request(mlops_user)},
    ).data

    assert data["train_data"][0]["text"] == "healthy"
    assert reads == ["fixtures/0.data"]


@pytest.mark.parametrize(("suffix", "basename", "content"), SERIALIZER_CASES)
def test_list_without_inline_data_keeps_zero_remote_reads(
    monkeypatch,
    mlops_user,
    suffix,
    basename,
    content,
):
    serializer_class, instances = _instances(suffix, basename, 100)
    reads = _install_file_reader(monkeypatch, instances, content)

    data = serializer_class(
        instances,
        many=True,
        context={"request": _request(mlops_user, include_train_data=False)},
    ).data

    assert len(data) == 100
    assert reads == []
    assert all("train_data" not in item for item in data)
