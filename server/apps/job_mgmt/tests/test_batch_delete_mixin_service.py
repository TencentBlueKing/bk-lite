"""BatchDeleteMixin 的 service 层测试（C3）

验证：

- ``perform_batch_delete`` 校验入参、限定鉴权范围、调用钩子、写操作日志；
- 子类通过 ``pre_batch_delete`` 钩子可执行删除前清理；
- 未声明 ``batch_delete_serializer_class`` 时抛 ``NotImplementedError``。
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from rest_framework import serializers

from apps.job_mgmt.views.mixins import BatchDeleteMixin


def _request(data):
    """构造一个具备 ``.data`` 属性的轻量假 Request，满足 mixin 仅读 ``request.data`` 的需求。"""
    return SimpleNamespace(data=data)


class _IdsSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.IntegerField(), min_length=1)


class _FakeViewSet(BatchDeleteMixin):
    """最小子类，模拟 ViewSet 行为。"""

    batch_delete_serializer_class = _IdsSerializer
    batch_delete_log_label = "测试条目"

    def __init__(self, deleted_count=3, instances=None):
        self._deleted_count = deleted_count
        self._instances = instances or MagicMock(name="instances")

    def filter_queryset(self, qs):
        return qs

    def get_queryset(self):
        qs = MagicMock(name="queryset")
        qs.filter.return_value = self._instances
        self._instances.delete.return_value = (self._deleted_count, {})
        return qs


@pytest.fixture
def request_with_data():
    return _request({"ids": [1, 2, 3]})


@pytest.mark.unit
class TestPerformBatchDelete:
    def test_happy_path_returns_deleted_count(self, request_with_data):
        vs = _FakeViewSet(deleted_count=3)
        with patch("apps.job_mgmt.views.mixins.log_operation") as log_op:
            resp = vs.perform_batch_delete(request_with_data)
        assert resp.status_code == 200
        assert resp.data == {"deleted_count": 3}
        # 日志被调用，含中文标签
        assert log_op.called
        call_args = log_op.call_args.args
        assert "批量删除测试条目" in call_args[3]
        assert "共3个" in call_args[3]

    def test_invalid_payload_raises_validation_error(self):
        vs = _FakeViewSet()
        with pytest.raises(serializers.ValidationError):
            vs.perform_batch_delete(_request({"ids": []}))

    def test_missing_payload_raises_validation_error(self):
        vs = _FakeViewSet()
        with pytest.raises(serializers.ValidationError):
            vs.perform_batch_delete(_request({}))

    def test_pre_batch_delete_hook_invoked_before_delete(self, request_with_data):
        invocations = []

        class _WithHook(_FakeViewSet):
            def pre_batch_delete(self, instances):
                invocations.append(("pre", instances))
                # 钩子调用后 .delete() 才被调用
                assert not instances.delete.called

        vs = _WithHook()
        with patch("apps.job_mgmt.views.mixins.log_operation"):
            vs.perform_batch_delete(request_with_data)
        assert len(invocations) == 1, "pre_batch_delete 应被恰好调用一次"

    def test_missing_serializer_class_raises_not_implemented(self, request_with_data):
        class _NoSerializer(BatchDeleteMixin):
            pass

        with pytest.raises(NotImplementedError):
            _NoSerializer().perform_batch_delete(request_with_data)

    def test_filter_queryset_used_to_enforce_authz_scope(self, request_with_data):
        """默认实现必须经过 filter_queryset，以保证团队鉴权范围生效"""
        vs = _FakeViewSet()
        with patch.object(vs, "filter_queryset", wraps=vs.filter_queryset) as filter_spy:
            with patch("apps.job_mgmt.views.mixins.log_operation"):
                vs.perform_batch_delete(request_with_data)
        assert filter_spy.called
