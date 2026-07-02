"""apps.core.fields.s3_json_field.S3JSONField 单元测试。

S3JSONField 是 JSONField 的透明替代：DB 存路径，实际数据存 MinIO。
仅 mock 真实外部边界（MinioBackend storage 的 save/open/exists/delete）。
断言真实行为：序列化+gzip 压缩内容正确、上传路径生成、从 S3 读回 round-trip、
descriptor 读写拦截、pre_save/get_prep_value 类型分支、deconstruct 迁移序列化。
"""

import gzip
import io
import json

import pytest

from apps.core.fields import s3_json_field as mod
from apps.core.fields.s3_json_field import (
    S3JSONField,
    S3JSONFieldDescriptor,
    s3_json_upload_path,
)

pytestmark = pytest.mark.unit


class _FakeStorage:
    """模拟 MinioBackend 的最小存储后端。"""

    def __init__(self):
        self.objects = {}
        self.deleted = []

    def save(self, filename, content):
        # 模拟 storage 真实行为：读取 ContentFile 字节并以路径为键存储
        content.seek(0)
        self.objects[filename] = content.read()
        return filename

    def exists(self, path):
        return path in self.objects

    def open(self, path, mode="rb"):
        return io.BytesIO(self.objects[path])

    def delete(self, path):
        self.deleted.append(path)
        self.objects.pop(path, None)


class _Instance:
    """模拟带 pk 与 _state.db 的模型实例。"""

    class _State:
        db = "default"

    def __init__(self, pk=1):
        self.pk = pk
        self._state = self._State()
        self.__dict__["__name_marker__"] = True


def _make_field(compressed=True, bucket="b1"):
    field = S3JSONField(bucket_name=bucket, compressed=compressed)
    field.set_attributes_from_name("data")
    # 注入假 storage，绕过真实 MinioBackend 初始化
    field._minio_storage = _FakeStorage()
    return field


class TestUploadPath:
    def test_path_format_contains_model_and_uuid(self):
        inst = _Instance(pk=42)
        inst.__class__.__name__  # noqa
        path = s3_json_upload_path(inst, "data.json.gz")
        # 形如 YYYY/MM/DD/instance_42_xxxx.json.gz
        parts = path.split("/")
        assert len(parts) == 4
        assert parts[-1].endswith(".json.gz")
        assert "_42_" in parts[-1]

    def test_new_instance_uses_new_marker(self):
        inst = _Instance(pk=None)
        path = s3_json_upload_path(inst, "x")
        assert "_new_" in path


class TestUploadAndLoadRoundTrip:
    def test_upload_compressed_then_load(self):
        field = _make_field(compressed=True)
        inst = _Instance()
        data = [{"log": "hello"}, {"n": 1}]
        path = field._upload_to_s3(inst, data)
        # 实际存储的是 gzip 字节
        raw = field.storage.objects[path]
        assert gzip.decompress(raw) == json.dumps(data, ensure_ascii=False).encode("utf-8")
        # 从 S3 读回还原
        assert field._load_from_s3(path) == data

    def test_upload_uncompressed(self):
        field = _make_field(compressed=False)
        inst = _Instance()
        data = {"a": "中文"}
        path = field._upload_to_s3(inst, data)
        raw = field.storage.objects[path]
        # 未压缩：直接是 json 字节
        assert json.loads(raw.decode("utf-8")) == data
        assert field._load_from_s3(path) == data

    def test_load_non_gzip_raw_json(self):
        field = _make_field(compressed=True)
        field.storage.objects["p.json"] = b'{"plain": true}'
        assert field._load_from_s3("p.json") == {"plain": True}


class TestLoadFromS3EdgeCases:
    def test_empty_path_returns_none(self):
        field = _make_field()
        assert field._load_from_s3("") is None

    def test_missing_file_returns_none(self):
        field = _make_field()
        assert field._load_from_s3("nope.json") is None

    def test_empty_content_returns_none(self):
        field = _make_field()
        field.storage.objects["empty"] = b""
        assert field._load_from_s3("empty") is None

    def test_invalid_json_returns_none(self):
        field = _make_field()
        field.storage.objects["bad"] = b"{not valid json"
        assert field._load_from_s3("bad") is None

    def test_storage_error_returns_none(self, mocker):
        field = _make_field()
        mocker.patch.object(field.storage, "exists", side_effect=RuntimeError("s3 down"))
        assert field._load_from_s3("x") is None


class TestToPythonAndPrep:
    def test_to_python_none_and_empty(self):
        field = _make_field()
        assert field.to_python(None) is None
        assert field.to_python("") is None

    def test_to_python_passthrough_objects(self):
        field = _make_field()
        assert field.to_python([1, 2]) == [1, 2]
        assert field.to_python({"k": "v"}) == {"k": "v"}

    def test_to_python_string_loads_from_s3(self):
        field = _make_field()
        field.storage.objects["p"] = gzip.compress(b'{"x": 1}')
        assert field.to_python("p") == {"x": 1}

    def test_from_db_value_returns_path_or_none(self):
        field = _make_field()
        assert field.from_db_value(None, None, None) is None
        assert field.from_db_value("", None, None) is None
        assert field.from_db_value("some/path.json.gz", None, None) == "some/path.json.gz"

    def test_get_prep_value_branches(self):
        field = _make_field()
        assert field.get_prep_value(None) is None
        assert field.get_prep_value("path/x") == "path/x"
        # list/dict -> None（上传在 pre_save 完成）
        assert field.get_prep_value([1]) is None
        assert field.get_prep_value({"a": 1}) is None

    def test_get_internal_type(self):
        assert _make_field().get_internal_type() == "CharField"


class TestPreSave:
    def test_pre_save_string_returns_as_is(self):
        field = _make_field()
        inst = _Instance()
        inst.__dict__["data"] = "already/uploaded.json.gz"
        assert field.pre_save(inst, add=False) == "already/uploaded.json.gz"

    def test_pre_save_none_returns_empty(self):
        field = _make_field()
        inst = _Instance()
        inst.__dict__["data"] = None
        assert field.pre_save(inst, add=True) == ""

    def test_pre_save_object_uploads_and_sets_path(self):
        field = _make_field()
        inst = _Instance()
        inst.__dict__["data"] = [{"k": 1}]
        path = field.pre_save(inst, add=True)
        assert path in field.storage.objects
        # 实例字段被改写为路径
        assert inst.__dict__["data"] == path

    def test_pre_save_promotes_pending_value(self):
        field = _make_field()
        inst = _Instance()
        inst.__dict__[field._pending_value_attr_name] = {"pending": True}
        path = field.pre_save(inst, add=True)
        assert path in field.storage.objects
        assert field._load_from_s3(path) == {"pending": True}

    def test_pre_save_upload_error_propagates(self, mocker):
        field = _make_field()
        inst = _Instance()
        inst.__dict__["data"] = [{"k": 1}]
        mocker.patch.object(field.storage, "save", side_effect=RuntimeError("upload fail"))
        with pytest.raises(RuntimeError):
            field.pre_save(inst, add=True)


class TestDescriptor:
    def test_get_on_class_returns_descriptor(self):
        field = _make_field()
        desc = S3JSONFieldDescriptor(field)
        assert desc.__get__(None, object) is desc

    def test_get_loads_string_path_and_caches(self):
        field = _make_field()
        field.storage.objects["p"] = gzip.compress(b"[1,2,3]")
        desc = S3JSONFieldDescriptor(field)
        inst = _Instance()
        inst.__dict__["data"] = "p"
        loaded = desc.__get__(inst, _Instance)
        assert loaded == [1, 2, 3]
        # 已缓存为对象
        assert inst.__dict__["data"] == [1, 2, 3]

    def test_get_load_failure_preserves_path_returns_none(self):
        field = _make_field()
        desc = S3JSONFieldDescriptor(field)
        inst = _Instance()
        inst.__dict__["data"] = "missing"
        assert desc.__get__(inst, _Instance) is None

    def test_set_object_stores_pending(self):
        field = _make_field()
        desc = S3JSONFieldDescriptor(field)
        inst = _Instance()
        desc.__set__(inst, {"x": 1})
        assert inst.__dict__[field._pending_value_attr_name] == {"x": 1}
        assert inst.__dict__["data"] == {"x": 1}

    def test_set_object_when_current_is_path_keeps_path(self):
        field = _make_field()
        desc = S3JSONFieldDescriptor(field)
        inst = _Instance()
        inst.__dict__["data"] = "existing/path.json.gz"
        desc.__set__(inst, [9])
        # current 是字符串路径时，不覆盖 attname
        assert inst.__dict__["data"] == "existing/path.json.gz"
        assert inst.__dict__[field._pending_value_attr_name] == [9]

    def test_set_string_directly_assigns(self):
        field = _make_field()
        desc = S3JSONFieldDescriptor(field)
        inst = _Instance()
        desc.__set__(inst, "raw/path")
        assert inst.__dict__["data"] == "raw/path"


class TestDeconstructAndSerialization:
    def test_deconstruct_includes_custom_kwargs(self):
        field = S3JSONField(bucket_name="mybucket", compressed=False)
        field.set_attributes_from_name("data")
        name, path, args, kwargs = field.deconstruct()
        assert kwargs["bucket_name"] == "mybucket"
        assert kwargs["compressed"] is False
        assert kwargs["delete_previous_on_update"] is False
        assert "storage" not in kwargs

    def test_value_to_string(self, mocker):
        field = _make_field()
        obj = _Instance()
        mocker.patch.object(field, "value_from_object", return_value="some/path")
        assert field.value_to_string(obj) == "some/path"
        mocker.patch.object(field, "value_from_object", return_value=None)
        assert field.value_to_string(obj) == ""

    def test_storage_lazy_init(self, mocker):
        field = S3JSONField(bucket_name="lazy")
        field.set_attributes_from_name("data")
        fake = object()
        mb = mocker.patch.object(mod, "MinioBackend", return_value=fake)
        assert field.storage is fake
        # 再次访问走缓存，不重复构造
        assert field.storage is fake
        mb.assert_called_once_with(bucket_name="lazy")
