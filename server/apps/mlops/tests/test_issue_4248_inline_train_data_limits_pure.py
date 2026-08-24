"""Issue #4248 纯预算与内存边界契约。"""

import tracemalloc
from io import BytesIO
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize(
    ("name", "hard_limit"),
    (
        ("MLOPS_INLINE_TRAIN_DATA_MAX_LIST_ITEMS", 20),
        ("MLOPS_INLINE_TRAIN_DATA_MAX_FILE_BYTES", 4 * 1024 * 1024),
        ("MLOPS_INLINE_TRAIN_DATA_MAX_TOTAL_BYTES", 8 * 1024 * 1024),
        ("MLOPS_INLINE_TRAIN_DATA_MAX_RECORDS", 50_000),
        ("MLOPS_INLINE_TRAIN_DATA_MAX_CSV_COLUMNS", 256),
        ("MLOPS_INLINE_TRAIN_DATA_MAX_CSV_CELLS", 500_000),
    ),
)
@pytest.mark.parametrize("configured", ("equal", "above", "zero", "negative", "invalid"))
def test_inline_limit_configuration_cannot_disable_hard_boundary(
    monkeypatch,
    name,
    hard_limit,
    configured,
):
    from apps.mlops.serializers.train_data_inline import _configured_limit

    values = {
        "equal": str(hard_limit),
        "above": str(hard_limit + 1),
        "zero": "0",
        "negative": "-1",
        "invalid": "invalid",
    }
    monkeypatch.setenv(name, values[configured])

    assert _configured_limit(name, hard_limit) == hard_limit


def test_one_byte_remote_short_reads_keep_near_limit_memory_bounded():
    from apps.mlops.serializers.train_data_inline import _read_until_eof_or_limit

    content = b"abc" * (256 * 1024 // 3)

    class OneByteStream(BytesIO):
        def read(self, _size=-1):
            return super().read(1)

    tracemalloc.start()
    result = _read_until_eof_or_limit(OneByteStream(content), len(content))
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert result == content
    assert peak_bytes < len(content) * 4


def test_transferred_bytes_remain_charged_after_midstream_error(monkeypatch):
    from apps.mlops.serializers.train_data_inline import InlineTrainDataLimitExceeded, _InlineTrainDataBudget

    monkeypatch.setenv("MLOPS_INLINE_TRAIN_DATA_MAX_FILE_BYTES", "16")
    monkeypatch.setenv("MLOPS_INLINE_TRAIN_DATA_MAX_TOTAL_BYTES", "20")
    transferred = []

    class FaultAfterChunk:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size=-1):
            if not transferred:
                transferred.append(12)
                return b"x" * 12
            raise OSError("stream interrupted")

    class TrackingStream(BytesIO):
        def read(self, size=-1):
            chunk = super().read(size)
            transferred.append(len(chunk))
            return chunk

    class Storage:
        def open(self, name, _mode):
            if name == "first":
                return FaultAfterChunk()
            return TrackingStream(b"y" * 20)

    storage = Storage()
    budget = _InlineTrainDataBudget()
    with pytest.raises(OSError, match="stream interrupted"):
        budget.read(SimpleNamespace(storage=storage, name="first"))

    assert budget.used_bytes == 12
    with pytest.raises(InlineTrainDataLimitExceeded) as exc:
        budget.read(SimpleNamespace(storage=storage, name="second"))

    assert exc.value.detail["reason"] == "total_bytes"
    assert sum(transferred) == 21
