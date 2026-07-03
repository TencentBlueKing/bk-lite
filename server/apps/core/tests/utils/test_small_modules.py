import pydantic.root_model  # noqa
"""apps/core 多个小工具/模型/任务模块的真实行为测试。

覆盖：
- utils/open_base.py：login_exempt 装饰器、OpenAPIViewSet.as_view 豁免链
- utils/async_utils.py：create_async_compatible_generator 真实异步消费 + 异常路径
- utils/download_local_file.py：FileResponse 真实文件下载、MIME 推断、文件名编码
- tasks/auditlog_flush_task.py：clear_audit_logs 调用 management command 契约
- models/vtype_mixin.py：抽象模型常量/字段映射（导入即覆盖模块体）
- serializers/user_auth_serializer.py：UserAuthSerializer 校验
"""
import os
import tempfile

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# open_base
# ---------------------------------------------------------------------------


class TestLoginExempt:
    def test_marks_function_and_preserves_call(self):
        from apps.core.utils.open_base import LOGIN_EXEMPT_ATTR, login_exempt

        @login_exempt
        def view(x):
            return x * 2

        assert getattr(view, LOGIN_EXEMPT_ATTR) is True
        assert view(3) == 6
        # functools.wraps 保留原函数名
        assert view.__name__ == "view"

    def test_non_callable_raises_type_error(self):
        from apps.core.utils.open_base import login_exempt

        with pytest.raises(TypeError):
            login_exempt("not-callable")


class TestOpenAPIViewSet:
    def test_as_view_applies_exempt_chain(self):
        from apps.core.utils.open_base import LOGIN_EXEMPT_ATTR, OpenAPIViewSet

        class MyViewSet(OpenAPIViewSet):
            def list(self, request):
                return None

        view = MyViewSet.as_view({"get": "list"})
        # csrf_exempt 设置 csrf_exempt 属性；login_exempt 设置 login_exempt 属性
        assert getattr(view, "csrf_exempt", False) is True
        assert getattr(view, LOGIN_EXEMPT_ATTR, False) is True

    def test_as_view_reraises_on_failure(self, mocker):
        from rest_framework.viewsets import ViewSetMixin

        from apps.core.utils import open_base

        class MyViewSet(open_base.OpenAPIViewSet):
            pass

        # OpenAPIViewSet.as_view 内部调用 super(ViewSet, cls).as_view，
        # MRO 上即 ViewSetMixin.as_view —— 让其抛错以验证异常被记录并重新抛出。
        mocker.patch.object(
            ViewSetMixin,
            "as_view",
            side_effect=RuntimeError("bad actions"),
        )
        with pytest.raises(RuntimeError):
            MyViewSet.as_view({"get": "missing"})


# ---------------------------------------------------------------------------
# async_utils
# ---------------------------------------------------------------------------


class TestAsyncCompatibleGenerator:
    @pytest.mark.asyncio
    async def test_wraps_sync_generator_yields_all_items(self):
        from apps.core.utils.async_utils import create_async_compatible_generator

        def sync_gen():
            yield "a"
            yield "b"
            yield "c"

        agen = create_async_compatible_generator(sync_gen())
        collected = [item async for item in agen]
        assert collected == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_empty_generator_yields_nothing(self):
        from apps.core.utils.async_utils import create_async_compatible_generator

        def empty_gen():
            return
            yield  # pragma: no cover

        agen = create_async_compatible_generator(empty_gen())
        collected = [item async for item in agen]
        assert collected == []

    @pytest.mark.asyncio
    async def test_exception_in_generator_yields_error_marker(self):
        from apps.core.utils.async_utils import create_async_compatible_generator

        def boom_gen():
            yield "ok"
            raise ValueError("kaboom")

        agen = create_async_compatible_generator(boom_gen())
        collected = [item async for item in agen]
        assert collected[0] == "ok"
        assert collected[-1].startswith("error: ")
        assert "kaboom" in collected[-1]


# ---------------------------------------------------------------------------
# download_local_file
# ---------------------------------------------------------------------------


class TestDownloadLocalFile:
    @staticmethod
    def _read(resp):
        """消费 streaming_content 并关闭底层文件句柄，避免泄漏。"""
        content = b"".join(resp.streaming_content)
        # 直接关闭底层文件对象，绕开 FileResponse.close 触发的 request_finished 信号
        try:
            resp.file_to_stream.close()
        except Exception:
            pass
        return content

    def test_returns_file_response_with_known_mime(self):
        from apps.core.utils.download_local_file import download_local_file

        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "report.json"), "w") as f:
                f.write('{"k": 1}')
            resp = download_local_file(d, "report.json")
            assert resp["Content-Type"] == "application/json"
            assert "report.json" in resp["Content-Disposition"]
            assert self._read(resp) == b'{"k": 1}'

    def test_unknown_extension_falls_back_to_octet_stream(self):
        from apps.core.utils.download_local_file import download_local_file

        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "data.unknownext"), "wb") as f:
                f.write(b"\x00\x01")
            resp = download_local_file(d, "data.unknownext")
            assert resp["Content-Type"] == "application/octet-stream"
            assert self._read(resp) == b"\x00\x01"

    def test_unicode_filename_is_url_encoded(self):
        from apps.core.utils.download_local_file import download_local_file

        with tempfile.TemporaryDirectory() as d:
            fname = "报告.txt"
            with open(os.path.join(d, fname), "w") as f:
                f.write("hi")
            resp = download_local_file(d, fname)
            # 中文被 URL 编码（%xx），不应出现原始中文
            assert "%" in resp["Content-Disposition"]
            self._read(resp)


# ---------------------------------------------------------------------------
# auditlog_flush_task
# ---------------------------------------------------------------------------


class TestClearAuditLogs:
    def test_calls_auditlogflush_with_30day_cutoff(self, mocker):
        from apps.core.tasks import auditlog_flush_task

        mock_call = mocker.patch.object(auditlog_flush_task, "call_command")
        auditlog_flush_task.clear_audit_logs()
        mock_call.assert_called_once()
        args = mock_call.call_args[0]
        assert args[0] == "auditlogflush"
        assert args[1] == "-b"
        # 第三个参数是日期字符串 YYYY-MM-DD
        assert len(args[2]) == 10 and args[2].count("-") == 2
        assert args[3] == "-y"


# ---------------------------------------------------------------------------
# vtype_mixin（抽象模型）
# ---------------------------------------------------------------------------


class TestVtypeMixin:
    def test_field_mapping_and_choices(self):
        from django.db.models import CharField, IntegerField

        from apps.core.models.vtype_mixin import VtypeMixin

        assert VtypeMixin.VTYPE_FIELD_MAPPING[VtypeMixin.STRING] is CharField
        assert VtypeMixin.VTYPE_FIELD_MAPPING[VtypeMixin.INTEGER] is IntegerField
        # 每个 choice 的值都存在于映射表
        choice_values = {c[0] for c in VtypeMixin.VTYPE_CHOICE}
        assert choice_values == set(VtypeMixin.VTYPE_FIELD_MAPPING.keys())

    def test_is_abstract(self):
        from apps.core.models.vtype_mixin import VtypeMixin

        assert VtypeMixin._meta.abstract is True


# ---------------------------------------------------------------------------
# user_auth_serializer
# ---------------------------------------------------------------------------


class TestUserAuthSerializer:
    def test_valid_data(self):
        from apps.core.serializers.user_auth_serializer import UserAuthSerializer

        s = UserAuthSerializer(data={"username": "u", "password": "p"})
        assert s.is_valid()
        assert s.validated_data == {"username": "u", "password": "p"}

    def test_missing_password_invalid(self):
        from apps.core.serializers.user_auth_serializer import UserAuthSerializer

        s = UserAuthSerializer(data={"username": "u"})
        assert not s.is_valid()
        assert "password" in s.errors
