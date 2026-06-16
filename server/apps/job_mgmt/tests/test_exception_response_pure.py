"""异常 → HTTP 响应映射的纯单测（B4）"""

import pytest
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.job_mgmt.services.error_response import DEFAULT_5XX_MESSAGE, NOT_FOUND_MESSAGE, SERVICE_UNAVAILABLE_MESSAGE, exception_to_response


@pytest.mark.unit
class TestExceptionToResponse:
    def test_base_app_exception_returns_400_with_detail(self):
        resp = exception_to_response(BaseAppException("缺少 current_team 参数"))
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "current_team" in resp.data["detail"]
        # 响应体只承载 detail，外层 result/code/message 由 CustomRenderer 填充
        assert "result" not in resp.data

    @pytest.mark.parametrize(
        "exc",
        [
            ValueError("非法值"),
            DRFValidationError({"field": ["错误"]}),
            DjangoValidationError("校验错误"),
        ],
    )
    def test_validation_like_exceptions_return_400(self, exc):
        resp = exception_to_response(exc)
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "detail" in resp.data

    def test_object_does_not_exist_returns_404_with_generic_message(self):
        resp = exception_to_response(ObjectDoesNotExist("内部细节"))
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        assert resp.data["detail"] == NOT_FOUND_MESSAGE
        # 重要：不泄漏内部异常细节
        assert "内部细节" not in resp.data["detail"]

    @pytest.mark.parametrize("exc", [TimeoutError("超时"), ConnectionError("拒绝")])
    def test_network_exceptions_return_503(self, exc):
        resp = exception_to_response(exc)
        assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert resp.data["detail"] == SERVICE_UNAVAILABLE_MESSAGE

    def test_nats_error_returns_503(self):
        """nats.errors.* 系列（包括 NoRespondersError）归类为上游不可达 → 503"""
        from nats.errors import NoRespondersError

        resp = exception_to_response(NoRespondersError())
        assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert resp.data["detail"] == SERVICE_UNAVAILABLE_MESSAGE

    def test_unexpected_exception_returns_500_without_leaking_details(self):
        resp = exception_to_response(RuntimeError("SECRET_DB_PASSWORD=xxxx"))
        assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert resp.data["detail"] == DEFAULT_5XX_MESSAGE
        # 安全：内部细节不出现在响应里
        assert "SECRET" not in str(resp.data)

    def test_custom_default_message_used_for_500(self):
        resp = exception_to_response(RuntimeError("oops"), default_message="查询节点失败")
        assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert resp.data["detail"] == "查询节点失败"

    def test_custom_body_key_overrides_default(self):
        """body_key 允许覆盖默认 ``detail``（特殊路由需要其他字段名时用）。"""
        resp = exception_to_response(ValueError("invalid"), body_key="message")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "message" in resp.data
        assert "detail" not in resp.data
