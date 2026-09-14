"""图片分类 / 目标检测发布解压 ZIP 的成员数与实际字节预算。"""

from __future__ import annotations

import inspect
import tempfile
import zipfile
from pathlib import Path

import pydantic.root_model  # noqa
import pytest

from apps.mlops.tasks import image_classification as image_task
from apps.mlops.tasks import object_detection as object_task
from apps.mlops.utils.zip_extract_budget import (
    ZIP_EXTRACT_CHUNK_SIZE,
    ZipExtractBudget,
    ZipExtractBudgetExceeded,
    extract_zip_with_budget,
)

pytestmark = pytest.mark.unit

_CHUNK_SIZE = 64 * 1024


def _write_zip(path: Path, files: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)


def _budget(**overrides) -> ZipExtractBudget:
    params = {
        "mode": "enforce",
        "max_members": 1000,
        "max_member_bytes": 1024 * 1024,
        "max_total_bytes": 4 * 1024 * 1024,
    }
    params.update(overrides)
    return ZipExtractBudget(**params)


def test_three_small_splits_extract_successfully(tmp_path):
    budget = _budget()
    extracted = []
    for split in ("train", "val", "test"):
        zip_path = tmp_path / f"{split}.zip"
        _write_zip(zip_path, {f"{split}.txt": f"{split}-payload".encode()})
        dest = tmp_path / f"{split}_extract"
        extract_zip_with_budget(zip_path, dest, budget)
        extracted.append(dest / f"{split}.txt")

    assert [path.read_text() for path in extracted] == [
        "train-payload",
        "val-payload",
        "test-payload",
    ]
    assert budget.member_count == 3
    assert budget.total_bytes == sum(len(f"{split}-payload".encode()) for split in ("train", "val", "test"))


def test_cumulative_bytes_across_splits_exceed(tmp_path):
    budget = _budget(max_total_bytes=1500)
    first_zip = tmp_path / "train.zip"
    second_zip = tmp_path / "val.zip"
    _write_zip(first_zip, {"a.bin": b"a" * 1000})
    _write_zip(second_zip, {"b.bin": b"b" * 1000})

    extract_zip_with_budget(first_zip, tmp_path / "train_extract", budget)
    with pytest.raises(ZipExtractBudgetExceeded) as exc:
        extract_zip_with_budget(second_zip, tmp_path / "val_extract", budget)
    assert "total_bytes" in str(exc.value)


def test_too_many_small_members_exceed(tmp_path):
    files = {f"f{i}.txt": b"x" for i in range(20)}
    zip_path = tmp_path / "many.zip"
    _write_zip(zip_path, files)
    dest = tmp_path / "extract"
    with pytest.raises(ZipExtractBudgetExceeded) as exc:
        extract_zip_with_budget(zip_path, dest, _budget(max_members=5))
    assert "members" in str(exc.value)


def test_high_ratio_member_counts_actual_bytes_not_declared_size(tmp_path, monkeypatch):
    payload = b"\x00" * (256 * 1024)
    zip_path = tmp_path / "bomb.zip"
    _write_zip(zip_path, {"bomb.bin": payload})

    original_infolist = zipfile.ZipFile.infolist

    def lying_infolist(self):
        infos = original_infolist(self)
        for info in infos:
            info.file_size = 1
        return infos

    monkeypatch.setattr(zipfile.ZipFile, "infolist", lying_infolist)

    dest = tmp_path / "extract"
    with pytest.raises(ZipExtractBudgetExceeded) as exc:
        extract_zip_with_budget(
            zip_path,
            dest,
            _budget(max_member_bytes=8 * 1024, max_total_bytes=8 * 1024),
        )
    message = str(exc.value)
    assert "member_bytes" in message or "total_bytes" in message


def test_extract_reads_in_64kib_chunks(tmp_path, monkeypatch):
    zip_path = tmp_path / "chunked.zip"
    _write_zip(zip_path, {"blob.bin": b"n" * (200 * 1024)})
    requested = []
    original_read = zipfile.ZipExtFile.read

    def tracked_read(self, n=-1):
        requested.append(n)
        return original_read(self, n)

    monkeypatch.setattr(zipfile.ZipExtFile, "read", tracked_read)
    extract_zip_with_budget(zip_path, tmp_path / "extract", _budget())

    assert requested
    assert all(0 < size <= _CHUNK_SIZE for size in requested)
    assert ZIP_EXTRACT_CHUNK_SIZE == _CHUNK_SIZE


def test_exceed_cleans_dest_and_caller_temp_leaves_no_residue(tmp_path):
    zip_path = tmp_path / "big.zip"
    _write_zip(zip_path, {"big.bin": b"z" * 50_000})
    dest = tmp_path / "extract"
    dest.mkdir()
    with pytest.raises(ZipExtractBudgetExceeded):
        extract_zip_with_budget(zip_path, dest, _budget(max_total_bytes=100))
    leftover_files = [path for path in dest.rglob("*") if path.is_file()]
    assert leftover_files == []

    with tempfile.TemporaryDirectory() as temp_dir:
        caller_temp = Path(temp_dir)
        nested = caller_temp / "extract"
        nested.mkdir()
        with pytest.raises(ZipExtractBudgetExceeded):
            extract_zip_with_budget(zip_path, nested, _budget(max_total_bytes=100))
        leftover_nested = [path for path in nested.rglob("*") if path.is_file()]
        assert leftover_nested == []
    assert not caller_temp.exists()


def test_observe_mode_still_extracts_when_over_budget(tmp_path):
    zip_path = tmp_path / "over.zip"
    _write_zip(zip_path, {"a.bin": b"a" * 1000})
    dest = tmp_path / "extract"
    extract_zip_with_budget(
        zip_path,
        dest,
        _budget(mode="observe", max_total_bytes=100),
    )
    assert (dest / "a.bin").read_bytes() == b"a" * 1000


def test_from_env_defaults_to_enforce(monkeypatch):
    monkeypatch.delenv("MLOPS_DATASET_ZIP_BUDGET_MODE", raising=False)
    budget = ZipExtractBudget.from_env()
    assert budget.mode == "enforce"
    assert budget.max_members > 0
    assert budget.max_member_bytes > 0
    assert budget.max_total_bytes > 0


def test_path_escape_is_rejected(tmp_path):
    zip_path = tmp_path / "escape.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("../escape.txt", b"nope")
    dest = tmp_path / "extract"
    dest.mkdir()
    with pytest.raises(ValueError):
        extract_zip_with_budget(zip_path, dest, _budget())
    assert not (tmp_path / "escape.txt").exists()


def test_publish_tasks_no_longer_call_extractall():
    image_src = inspect.getsource(image_task.publish_dataset_release_async)
    object_src = inspect.getsource(object_task.publish_dataset_release_async)
    assert "extractall" not in image_src
    assert "extractall" not in object_src
    assert "extract_zip_with_budget" in image_src
    assert "extract_zip_with_budget" in object_src
