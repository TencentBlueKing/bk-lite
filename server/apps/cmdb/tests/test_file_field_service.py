"""附件/图片字段企业版核心逻辑单测（DB，mock 对象存储）。

依赖企业版 overlay（apps.cmdb.enterprise）；无 overlay 时整体跳过，保证社区检出绿。
"""

import json

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException

from apps.cmdb.models.file_object import CmdbFileObject, CmdbFileObjectStatus

# 缺企业 overlay 时跳过整个模块（社区版 tracked 测试约定）
service = pytest.importorskip("apps.cmdb.enterprise.instance_ops.service")

ATTACHMENT_ATTR = {"attr_id": "contract", "attr_type": "attachment"}
IMAGE_ATTR = {"attr_id": "photo", "attr_type": "image"}


def _make_row(**kwargs):
    defaults = dict(
        bucket="cmdb-attachment",
        object_key=f"attachment/202606/{kwargs.get('file_name', 'a.pdf')}-{kwargs.get('uploader','u')}",
        file_name="contract.pdf",
        file_size=1024,
        mime_type="application/pdf",
        model_id="server",
        attr_id="contract",
        uploader="admin",
        status=CmdbFileObjectStatus.PENDING,
    )
    defaults.update(kwargs)
    return CmdbFileObject.objects.create(**defaults)


# ---- 上传校验 ----


class _FakeUpload:
    def __init__(self, name, size, content_type=""):
        self.name = name
        self.size = size
        self.content_type = content_type


def test_validate_upload_rejects_bad_extension():
    with pytest.raises(BaseAppException, match="不支持的文件类型"):
        service.validate_upload("image", _FakeUpload("evil.exe", 100))


def test_validate_upload_rejects_oversize_image():
    with pytest.raises(BaseAppException, match="大小"):
        service.validate_upload("image", _FakeUpload("big.png", 11 * 1024 * 1024))


def test_validate_upload_accepts_pdf_attachment():
    # 不抛即通过
    service.validate_upload("attachment", _FakeUpload("doc.pdf", 1024))


# ---- normalize 写路径校验 ----


@pytest.mark.django_db
def test_normalize_rejects_too_many_files():
    ids = []
    for i in range(6):
        row = _make_row(file_name="a.pdf", object_key=f"k{i}")
        ids.append(str(row.file_id))
    data = {"contract": ids}
    with pytest.raises(BaseAppException, match="最多上传"):
        service.normalize_file_fields("server", data, [ATTACHMENT_ATTR], operator="admin")


@pytest.mark.django_db
def test_normalize_rejects_unknown_file():
    data = {"contract": ["00000000-0000-0000-0000-000000000000"]}
    with pytest.raises(BaseAppException, match="不存在"):
        service.normalize_file_fields("server", data, [ATTACHMENT_ATTR], operator="admin")


@pytest.mark.django_db
def test_normalize_rejects_other_uploaders_pending_file():
    row = _make_row(uploader="bob", object_key="kbob")
    data = {"contract": [str(row.file_id)]}
    with pytest.raises(BaseAppException, match="无权引用|不存在"):
        service.normalize_file_fields("server", data, [ATTACHMENT_ATTR], operator="admin")


@pytest.mark.django_db
def test_normalize_builds_metadata_json():
    row = _make_row(file_name="合同.pdf", object_key="kok")
    data = {"contract": [str(row.file_id)]}
    out = service.normalize_file_fields("server", data, [ATTACHMENT_ATTR], operator="admin")
    meta = json.loads(out["contract"])
    assert len(meta) == 1
    assert meta[0]["file_name"] == "合同.pdf"
    assert meta[0]["object_key"] == "kok"
    assert meta[0]["file_id"] == str(row.file_id)


@pytest.mark.django_db
def test_normalize_empty_clears_field():
    data = {"contract": []}
    out = service.normalize_file_fields("server", data, [ATTACHMENT_ATTR], operator="admin")
    assert json.loads(out["contract"]) == []


# ---- commit 落账 ----


@pytest.mark.django_db
def test_commit_marks_referenced_committed_and_removed_orphaned():
    keep = _make_row(object_key="keep")
    remove = _make_row(object_key="remove")
    # 先把两者落到实例 42
    saved = {"contract": json.dumps([service._row_metadata(keep), service._row_metadata(remove)])}
    service.commit_instance_files("server", 42, saved, [ATTACHMENT_ATTR], operator="admin")
    keep.refresh_from_db(); remove.refresh_from_db()
    assert keep.status == CmdbFileObjectStatus.COMMITTED and keep.inst_id == 42
    assert remove.status == CmdbFileObjectStatus.COMMITTED

    # 再次保存只留 keep → remove 变 orphaned
    saved2 = {"contract": json.dumps([service._row_metadata(keep)])}
    service.commit_instance_files("server", 42, saved2, [ATTACHMENT_ATTR], operator="admin")
    keep.refresh_from_db(); remove.refresh_from_db()
    assert keep.status == CmdbFileObjectStatus.COMMITTED
    assert remove.status == CmdbFileObjectStatus.ORPHANED


@pytest.mark.django_db
def test_mark_instance_files_orphaned():
    r1 = _make_row(object_key="d1", inst_id=7, status=CmdbFileObjectStatus.COMMITTED)
    r2 = _make_row(object_key="d2", inst_id=7, status=CmdbFileObjectStatus.COMMITTED)
    service.mark_instance_files_orphaned(7)
    r1.refresh_from_db(); r2.refresh_from_db()
    assert r1.status == CmdbFileObjectStatus.ORPHANED
    assert r2.status == CmdbFileObjectStatus.ORPHANED


# ---- 下载校权 ----


@pytest.mark.django_db
def test_download_committed_follows_instance_read_permission(monkeypatch):
    monkeypatch.setattr(service.storage, "presigned_get_url", lambda key: f"https://minio/{key}")
    row = _make_row(object_key="dl", inst_id=9, status=CmdbFileObjectStatus.COMMITTED)

    class _Req:
        class user:
            username = "admin"

    # 有权
    url = service.resolve_download_url(_Req(), str(row.file_id), check_read_permission=lambda inst_id: True)
    assert url == "https://minio/dl"
    # 无权
    with pytest.raises(BaseAppException, match="权限"):
        service.resolve_download_url(_Req(), str(row.file_id), check_read_permission=lambda inst_id: False)


@pytest.mark.django_db
def test_download_pending_only_uploader(monkeypatch):
    monkeypatch.setattr(service.storage, "presigned_get_url", lambda key: f"https://minio/{key}")
    row = _make_row(object_key="dlp", uploader="bob", status=CmdbFileObjectStatus.PENDING)

    class _Req:
        class user:
            username = "admin"

    with pytest.raises(BaseAppException, match="无权"):
        service.resolve_download_url(_Req(), str(row.file_id))
