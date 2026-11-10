from rest_framework.views import APIView

from apps.cmdb.services.change_record_retention import job_is_blocking, present_job, read_policy, save_policy
from apps.cmdb.tasks.change_record_retention import cleanup_change_record_retention
from apps.core.decorators.api_permission import HasPermission
from apps.core.exceptions.base_app_exception import ValidationAppException
from apps.core.utils.web_utils import WebUtils


class ChangeRecordRetentionView(APIView):
    @HasPermission("model_management-View")
    def get(self, request):
        return WebUtils.response_success({"policy": read_policy(), "job": present_job()})

    @HasPermission("model_management-Edit Model")
    def put(self, request):
        if job_is_blocking():
            return WebUtils.response_error(error_message="操作日志清理正在进行，请稍后再改策略", status_code=409)
        try:
            policy = save_policy(request.data)
        except ValidationAppException as exc:
            return WebUtils.response_error(error_message=exc.message, status_code=400)
        if policy["mode"] != "off":
            cleanup_change_record_retention.delay(trigger="save")
        return WebUtils.response_success({"policy": policy, "job": present_job()})
