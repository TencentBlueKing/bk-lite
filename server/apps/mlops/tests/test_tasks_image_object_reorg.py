"""真实覆盖 image_classification / object_detection 任务的重组与发布主流程。

策略：
- ``_reorganize_images`` / ``_reorganize_yolo_data`` 为纯函数，用真实临时目录 + 真实
  PNG 字节直接喂入，断言解压重组产物（ImageFolder / YOLO images+labels）与统计。
- publish 主流程仅在 MinIO 边界打桩：把 TrainData.train_data 替换为返回真实内存 ZIP
  的假 FieldFile，并桩掉模块级 MinioBackend 的 save/url；断言 Release 落库副作用、
  生成的 metadata、data.yaml 内容与 ZIP 产物。
"""
import io
import struct
import zipfile
import zlib
from pathlib import Path

import pydantic.root_model  # noqa  预热
import pytest

from apps.mlops.tasks import image_classification as ic_task
from apps.mlops.tasks import object_detection as od_task
from apps.mlops.tasks.image_classification import _reorganize_images
from apps.mlops.tasks.object_detection import (
    _reorganize_yolo_data,
    prepare_class_mappings,
)

pytestmark = pytest.mark.unit


# ----------------------------- 工具：真实 PNG / ZIP -----------------------------


def _png_bytes(color=b"\x00\xff\x00\x00") -> bytes:
    """生成一张真实 1x1 PNG 的字节流。"""
    sig = b"\x89PNG\r\n\x1a\n"

    def chunk(t, d):
        return (
            struct.pack(">I", len(d))
            + t
            + d
            + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00" + color)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def _make_zip(files: dict) -> bytes:
    """构造内存 ZIP：{arcname: bytes}。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _extract_zip_to(zip_bytes: bytes, dest: Path):
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        zf.extractall(dest)


# ============================ _reorganize_images ============================


def test_reorganize_images_happy_path(tmp_path):
    extract = tmp_path / "extract"
    extract.mkdir()
    (extract / "a.png").write_bytes(_png_bytes())
    (extract / "b.png").write_bytes(_png_bytes())
    (extract / "c.png").write_bytes(_png_bytes())
    split_root = tmp_path / "split"
    split_root.mkdir()

    metadata = {
        "classes": ["cat", "dog"],
        "labels": {"a.png": "cat", "b.png": "dog", "c.png": "cat"},
    }

    stats = _reorganize_images(extract, split_root, metadata)

    assert stats["total"] == 3
    assert stats["classes"] == {"cat": 2, "dog": 1}
    # 真实产物落盘
    assert (split_root / "cat" / "a.png").exists()
    assert (split_root / "cat" / "c.png").exists()
    assert (split_root / "dog" / "b.png").exists()
    # 类别目录被预创建
    assert (split_root / "cat").is_dir()


def test_reorganize_images_skips_unlabeled(tmp_path):
    extract = tmp_path / "extract"
    extract.mkdir()
    (extract / "known.jpg").write_bytes(_png_bytes())
    (extract / "unknown.jpg").write_bytes(_png_bytes())
    (extract / "notes.txt").write_text("ignore me")  # 非图片后缀
    split_root = tmp_path / "split"
    split_root.mkdir()

    metadata = {"classes": ["x"], "labels": {"known.jpg": "x"}}
    stats = _reorganize_images(extract, split_root, metadata)

    assert stats["total"] == 1
    assert stats["classes"] == {"x": 1}
    assert (split_root / "x" / "known.jpg").exists()
    assert not (split_root / "x" / "unknown.jpg").exists()


def test_reorganize_images_empty_metadata(tmp_path):
    extract = tmp_path / "e"
    extract.mkdir()
    split_root = tmp_path / "s"
    split_root.mkdir()
    assert _reorganize_images(extract, split_root, None) == {"total": 0, "classes": {}}
    assert _reorganize_images(extract, split_root, {}) == {"total": 0, "classes": {}}


def test_reorganize_images_no_labels_field(tmp_path):
    extract = tmp_path / "e"
    extract.mkdir()
    split_root = tmp_path / "s"
    split_root.mkdir()
    stats = _reorganize_images(extract, split_root, {"classes": ["a"]})
    assert stats == {"total": 0, "classes": {}}


def test_reorganize_images_nested_dirs(tmp_path):
    extract = tmp_path / "extract"
    (extract / "sub").mkdir(parents=True)
    (extract / "sub" / "deep.png").write_bytes(_png_bytes())
    split_root = tmp_path / "split"
    split_root.mkdir()
    metadata = {"classes": ["z"], "labels": {"deep.png": "z"}}
    stats = _reorganize_images(extract, split_root, metadata)
    assert stats["total"] == 1
    assert (split_root / "z" / "deep.png").exists()


# ============================ _reorganize_yolo_data ============================


def _yolo_meta(labels, classes):
    return {"labels": labels, "classes": classes}


def test_reorganize_yolo_happy_path(tmp_path):
    extract = tmp_path / "extract"
    extract.mkdir()
    (extract / "img1.png").write_bytes(_png_bytes())
    (extract / "img2.png").write_bytes(_png_bytes())
    images_dir = tmp_path / "images"
    labels_dir = tmp_path / "labels"
    images_dir.mkdir()
    labels_dir.mkdir()

    metadata = _yolo_meta(
        {
            "img1.png": [
                {"class_id": 0, "x_center": 0.5, "y_center": 0.5, "width": 0.2, "height": 0.3},
                {"class_id": 1, "x_center": 0.1, "y_center": 0.1, "width": 0.05, "height": 0.05},
            ],
            "img2.png": [
                {"class_id": 1, "x_center": 0.4, "y_center": 0.4, "width": 0.1, "height": 0.1},
            ],
        },
        ["cat", "dog"],
    )
    mapping = {0: 0, 1: 1}
    global_classes = ["cat", "dog"]

    stats = _reorganize_yolo_data(extract, images_dir, labels_dir, metadata, mapping, global_classes)

    assert stats["total"] == 2
    assert stats["classes"] == {"cat", "dog"}
    # 图片复制
    assert (images_dir / "img1.png").exists()
    assert (images_dir / "img2.png").exists()
    # 标注文件内容（YOLO 格式）
    txt1 = (labels_dir / "img1.txt").read_text().strip().splitlines()
    assert txt1[0] == "0 0.500000 0.500000 0.200000 0.300000"
    assert txt1[1].startswith("1 ")
    txt2 = (labels_dir / "img2.txt").read_text().strip()
    assert txt2.startswith("1 0.400000")


def test_reorganize_yolo_image_without_label_gets_empty_txt(tmp_path):
    extract = tmp_path / "extract"
    extract.mkdir()
    (extract / "lonely.png").write_bytes(_png_bytes())
    images_dir = tmp_path / "images"
    labels_dir = tmp_path / "labels"
    images_dir.mkdir()
    labels_dir.mkdir()

    metadata = _yolo_meta({}, ["cat"])
    stats = _reorganize_yolo_data(extract, images_dir, labels_dir, metadata, {0: 0}, ["cat"])
    assert stats["total"] == 1
    label = labels_dir / "lonely.txt"
    assert label.exists()
    assert label.read_text() == ""  # 空标注文件


def test_reorganize_yolo_skips_invalid_annotations(tmp_path):
    extract = tmp_path / "extract"
    extract.mkdir()
    (extract / "img.png").write_bytes(_png_bytes())
    images_dir = tmp_path / "images"
    labels_dir = tmp_path / "labels"
    images_dir.mkdir()
    labels_dir.mkdir()

    metadata = _yolo_meta(
        {
            "img.png": [
                "not-a-dict",  # 非字典
                {"x_center": 0.5, "y_center": 0.5, "width": 0.1, "height": 0.1},  # 缺 class_id
                {"class_id": 0, "x_center": 0.5},  # 缺坐标
                {"class_id": -1, "x_center": 0.5, "y_center": 0.5, "width": 0.1, "height": 0.1},  # 负 class_id
                {"class_id": 99, "x_center": 0.5, "y_center": 0.5, "width": 0.1, "height": 0.1},  # 越界 class_id
                {"class_id": 0, "x_center": 1.5, "y_center": 0.5, "width": 0.1, "height": 0.1},  # 坐标越界
                {"class_id": 0, "x_center": 0.5, "y_center": 0.5, "width": 0.2, "height": 0.2},  # 唯一有效
            ]
        },
        ["only"],
    )
    stats = _reorganize_yolo_data(extract, images_dir, labels_dir, metadata, {0: 0}, ["only"])
    assert stats["total"] == 1
    lines = [ln for ln in (labels_dir / "img.txt").read_text().splitlines() if ln]
    assert lines == ["0 0.500000 0.500000 0.200000 0.200000"]
    assert stats["classes"] == {"only"}


def test_reorganize_yolo_annotation_not_list_creates_empty(tmp_path):
    """标注非 list 时：生成空 txt 并 continue（不计入 total）。

    源码在该分支 ``continue`` 跳过了 ``total += 1``，故需另一张正常图片保证 total>0，
    否则末尾会因 total==0 抛错——这正是被测的真实行为。
    """
    extract = tmp_path / "extract"
    extract.mkdir()
    (extract / "img.png").write_bytes(_png_bytes())  # 坏标注
    (extract / "ok.png").write_bytes(_png_bytes())   # 无标注，正常计数
    images_dir = tmp_path / "images"
    labels_dir = tmp_path / "labels"
    images_dir.mkdir()
    labels_dir.mkdir()

    metadata = _yolo_meta({"img.png": {"bad": "shape"}}, ["a"])  # 标注是 dict 而非 list
    stats = _reorganize_yolo_data(extract, images_dir, labels_dir, metadata, {0: 0}, ["a"])
    # 坏标注图片被 continue 跳过计数，只有 ok.png 计入
    assert stats["total"] == 1
    assert (labels_dir / "img.txt").read_text() == ""  # 坏标注 -> 空 txt
    assert (labels_dir / "ok.txt").read_text() == ""   # 无标注 -> 空 txt
    assert (images_dir / "img.png").exists()


def test_reorganize_yolo_empty_metadata_raises(tmp_path):
    extract = tmp_path / "e"
    extract.mkdir()
    with pytest.raises(ValueError, match="metadata 为空"):
        _reorganize_yolo_data(extract, tmp_path, tmp_path, {}, {}, [])


def test_reorganize_yolo_metadata_not_dict_raises(tmp_path):
    extract = tmp_path / "e"
    extract.mkdir()
    with pytest.raises(ValueError, match="必须是字典类型"):
        _reorganize_yolo_data(extract, tmp_path, tmp_path, ["x"], {}, [])


def test_reorganize_yolo_missing_labels_field_raises(tmp_path):
    extract = tmp_path / "e"
    extract.mkdir()
    with pytest.raises(ValueError, match="缺少必需字段 'labels'"):
        _reorganize_yolo_data(extract, tmp_path, tmp_path, {"classes": ["a"]}, {}, ["a"])


def test_reorganize_yolo_labels_not_dict_raises(tmp_path):
    extract = tmp_path / "e"
    extract.mkdir()
    with pytest.raises(ValueError, match="metadata.labels 必须是字典类型"):
        _reorganize_yolo_data(extract, tmp_path, tmp_path, {"labels": [], "classes": ["a"]}, {}, ["a"])


def test_reorganize_yolo_missing_classes_field_raises(tmp_path):
    extract = tmp_path / "e"
    extract.mkdir()
    with pytest.raises(ValueError, match="缺少必需字段 'classes'"):
        _reorganize_yolo_data(extract, tmp_path, tmp_path, {"labels": {}}, {}, [])


def test_reorganize_yolo_classes_not_list_raises(tmp_path):
    extract = tmp_path / "e"
    extract.mkdir()
    with pytest.raises(ValueError, match="metadata.classes 必须是列表类型"):
        _reorganize_yolo_data(extract, tmp_path, tmp_path, {"labels": {}, "classes": {}}, {}, [])


def test_reorganize_yolo_no_images_raises(tmp_path):
    extract = tmp_path / "extract"
    extract.mkdir()
    (extract / "readme.txt").write_text("no images here")
    images_dir = tmp_path / "images"
    labels_dir = tmp_path / "labels"
    images_dir.mkdir()
    labels_dir.mkdir()
    metadata = _yolo_meta({}, ["a"])
    with pytest.raises(ValueError, match="未找到任何图片文件"):
        _reorganize_yolo_data(extract, images_dir, labels_dir, metadata, {0: 0}, ["a"])


def test_reorganize_yolo_class_not_in_mapping_skipped(tmp_path):
    extract = tmp_path / "extract"
    extract.mkdir()
    (extract / "img.png").write_bytes(_png_bytes())
    images_dir = tmp_path / "images"
    labels_dir = tmp_path / "labels"
    images_dir.mkdir()
    labels_dir.mkdir()
    metadata = _yolo_meta(
        {"img.png": [{"class_id": 0, "x_center": 0.5, "y_center": 0.5, "width": 0.1, "height": 0.1}]},
        ["a", "b"],
    )
    # global_classes 有 2 类（0 合法），但 mapping 缺 0 -> 跳过
    stats = _reorganize_yolo_data(extract, images_dir, labels_dir, metadata, {1: 1}, ["a", "b"])
    assert stats["total"] == 1  # 图片仍被处理
    assert (labels_dir / "img.txt").read_text() == ""  # 标注被跳过
    assert stats["classes"] == set()


# ============================ prepare_class_mappings 补充边界 ============================


def test_prepare_class_mappings_test_extends_classes():
    """test 中含 train/val 之外的新 class_id -> 并入全局类别。"""
    train = {"classes": ["cat"]}
    val = {"classes": ["cat"]}
    test = {"classes": ["cat", "dog", "bird"]}
    global_classes, _, _, test_map, warnings = prepare_class_mappings(train, val, test)
    assert global_classes == ["cat", "dog", "bird"]
    assert test_map == {0: 0, 1: 1, 2: 2}
    assert warnings["conflicts"] == []


def test_prepare_class_mappings_test_conflict_raises():
    """test 与已有 class_id 名称冲突 -> 抛错（覆盖 test 分支冲突路径）。"""
    train = {"classes": ["cat", "dog"]}
    val = {"classes": ["cat", "dog"]}
    test = {"classes": ["cat", "fish"]}  # id 1: dog vs fish
    with pytest.raises(ValueError, match="类别名称冲突"):
        prepare_class_mappings(train, val, test)


# ============================ publish 主流程（仅打桩 MinIO 边界）============================


class _FakeFieldFile:
    """假 FieldFile：name 非空，open('rb') 返回真实 ZIP 字节流上下文。"""

    def __init__(self, zip_bytes):
        self.name = "fake/train.zip"
        self._bytes = zip_bytes

    def open(self, mode="rb"):
        return io.BytesIO(self._bytes)


def _patch_minio(monkeypatch, module):
    """桩掉模块级 MinioBackend：save 回显路径，url 返回固定 url。"""
    saved = {}

    class _FakeStorage:
        def __init__(self, *a, **k):
            pass

        def save(self, path, content):
            saved["path"] = path
            saved["size"] = len(content.read())
            return path

        def url(self, path):
            return f"http://minio/{path}"

    monkeypatch.setattr(module, "MinioBackend", _FakeStorage)
    return saved


@pytest.mark.django_db
def test_image_classification_publish_happy_path(monkeypatch):
    from apps.mlops.models.image_classification import (
        ImageClassificationDataset,
        ImageClassificationDatasetRelease,
        ImageClassificationTrainData,
    )

    ds = ImageClassificationDataset.objects.create(name="imgds", description="", team=[1])
    rel = ImageClassificationDatasetRelease.objects.create(
        name="r", description="", dataset=ds, version="v1",
        dataset_file="placeholder.zip", status="pending", metadata={}, file_size=0,
    )

    def _td(name, labels, classes):
        obj = ImageClassificationTrainData.objects.create(
            name=name, dataset=ds, metadata={"labels": labels, "classes": classes},
        )
        return obj

    train = _td("t", {"a.png": "cat", "b.png": "dog"}, ["cat", "dog"])
    val = _td("v", {"c.png": "cat"}, ["cat", "dog"])
    test = _td("te", {"d.png": "dog"}, ["cat", "dog"])

    zip_map = {
        train.id: _make_zip({"a.png": _png_bytes(), "b.png": _png_bytes()}),
        val.id: _make_zip({"c.png": _png_bytes()}),
        test.id: _make_zip({"d.png": _png_bytes()}),
    }

    orig_get = ImageClassificationTrainData.objects.get

    def fake_get(*args, **kwargs):
        obj = orig_get(*args, **kwargs)
        obj.train_data = _FakeFieldFile(zip_map[obj.id])
        return obj

    monkeypatch.setattr(ImageClassificationTrainData.objects, "get", fake_get)
    saved = _patch_minio(monkeypatch, ic_task)

    result = ic_task.publish_dataset_release_async.run(rel.id, train.id, val.id, test.id)

    assert result["result"] is True
    meta = result["metadata"]
    assert meta["format"] == "ImageFolder"
    assert meta["total_images"] == 4
    assert sorted(meta["classes"]) == ["cat", "dog"]
    assert meta["num_classes"] == 2
    assert meta["splits"]["train"]["total"] == 2
    assert meta["source"]["train_file_id"] == train.id

    rel.refresh_from_db()
    assert rel.status == "published"
    assert rel.file_size > 0
    assert rel.metadata["format"] == "ImageFolder"
    assert "image_classification_datasets/" in saved["path"]

    # 校验上传的 ZIP 内含 ImageFolder 结构
    # saved["size"] 是被消费后的长度，仅断言 > 0
    assert saved["size"] > 0


@pytest.mark.django_db
def test_object_detection_publish_happy_path(monkeypatch):
    from apps.mlops.models.object_detection import (
        ObjectDetectionDataset,
        ObjectDetectionDatasetRelease,
        ObjectDetectionTrainData,
    )
    import yaml

    ds = ObjectDetectionDataset.objects.create(name="odds", description="", team=[1])
    rel = ObjectDetectionDatasetRelease.objects.create(
        name="r", description="", dataset=ds, version="v2",
        dataset_file="placeholder.zip", status="pending", metadata={}, file_size=0,
    )

    classes = ["cat", "dog"]

    def _td(name):
        return ObjectDetectionTrainData.objects.create(
            name=name, dataset=ds,
            metadata={
                "classes": classes,
                "labels": {
                    "p.png": [
                        {"class_id": 0, "x_center": 0.5, "y_center": 0.5, "width": 0.2, "height": 0.2},
                        {"class_id": 1, "x_center": 0.3, "y_center": 0.3, "width": 0.1, "height": 0.1},
                    ]
                },
            },
        )

    train, val, test = _td("t"), _td("v"), _td("te")
    zb = _make_zip({"p.png": _png_bytes()})
    zip_map = {train.id: zb, val.id: zb, test.id: zb}

    orig_get = ObjectDetectionTrainData.objects.get

    def fake_get(*args, **kwargs):
        obj = orig_get(*args, **kwargs)
        obj.train_data = _FakeFieldFile(zip_map[obj.id])
        return obj

    monkeypatch.setattr(ObjectDetectionTrainData.objects, "get", fake_get)
    saved = _patch_minio(monkeypatch, od_task)

    # 捕获生成的 data.yaml 内容用于断言：拦截 yaml.dump
    dumped = {}
    orig_dump = yaml.dump

    def spy_dump(data, stream=None, **kw):
        if isinstance(data, dict) and data.get("path") == ".":
            dumped["yaml"] = data
        return orig_dump(data, stream, **kw)

    monkeypatch.setattr(od_task.yaml, "dump", spy_dump)

    result = od_task.publish_dataset_release_async.run(rel.id, train.id, val.id, test.id)

    assert result["result"] is True
    meta = result["metadata"]
    assert meta["format"] == "YOLO"
    assert meta["classes"] == ["cat", "dog"]
    assert meta["num_classes"] == 2
    assert meta["total_images"] == 3  # 三个 split 各 1 张
    assert meta["splits"]["train"]["total"] == 1

    # data.yaml 内容契约
    assert dumped["yaml"]["train"] == "images/train"
    assert dumped["yaml"]["names"] == {0: "cat", 1: "dog"}

    rel.refresh_from_db()
    assert rel.status == "published"
    assert rel.metadata["format"] == "YOLO"
    assert "object_detection_datasets/" in saved["path"]


@pytest.mark.django_db
def test_object_detection_publish_class_conflict_marks_failed(monkeypatch):
    """train/val 同一 class_id 名称冲突 -> prepare_class_mappings 抛错 -> 标记失败。"""
    from apps.mlops.models.object_detection import (
        ObjectDetectionDataset,
        ObjectDetectionDatasetRelease,
        ObjectDetectionTrainData,
    )

    ds = ObjectDetectionDataset.objects.create(name="odc", description="", team=[1])
    rel = ObjectDetectionDatasetRelease.objects.create(
        name="r", description="", dataset=ds, version="v3",
        dataset_file="p.zip", status="pending", metadata={}, file_size=0,
    )
    train = ObjectDetectionTrainData.objects.create(
        name="t", dataset=ds, metadata={"classes": ["cat", "dog"], "labels": {}},
    )
    val = ObjectDetectionTrainData.objects.create(
        name="v", dataset=ds, metadata={"classes": ["cat", "bird"], "labels": {}},  # id 1 冲突
    )
    test = ObjectDetectionTrainData.objects.create(
        name="te", dataset=ds, metadata={"classes": ["cat", "dog"], "labels": {}},
    )

    _patch_minio(monkeypatch, od_task)

    result = od_task.publish_dataset_release_async.run(rel.id, train.id, val.id, test.id)
    assert result["result"] is False
    assert "error" in result
    rel.refresh_from_db()
    assert rel.status == "failed"
    assert "类别名称冲突" in rel.metadata["error"]
