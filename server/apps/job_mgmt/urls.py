"""作业管理 URL 配置"""

from django.urls import path
from rest_framework import routers

from apps.job_mgmt.views import (
    DangerousPathViewSet,
    DangerousRuleViewSet,
    DashboardViewSet,
    DistributionFileViewSet,
    JobExecutionViewSet,
    PlaybookViewSet,
    ScheduledTaskViewSet,
    ScriptViewSet,
    TargetViewSet,
)
from apps.job_mgmt.views.open_api import (
    OpenFileDeleteView,
    OpenFileUploadView,
    OpenJobDetailView,
    OpenJobListView,
    OpenJobStatusView,
    OpenScriptExecuteView,
)

router = routers.DefaultRouter(trailing_slash=True)

# 系统管理 - 高危命令
router.register(r"api/dangerous_rule", DangerousRuleViewSet, basename="dangerous_rule")

# 系统管理 - 高危路径
router.register(r"api/dangerous_path", DangerousPathViewSet, basename="dangerous_path")

# 目标管理
router.register(r"api/target", TargetViewSet, basename="target")

# 作业模板 - 脚本库
router.register(r"api/script", ScriptViewSet, basename="script")

# 作业模板 - Playbook库
router.register(r"api/playbook", PlaybookViewSet, basename="playbook")

# 作业执行
router.register(r"api/execution", JobExecutionViewSet, basename="execution")

# 定时任务
router.register(r"api/scheduled_task", ScheduledTaskViewSet, basename="scheduled_task")

# Dashboard
router.register(r"api/dashboard", DashboardViewSet, basename="dashboard")

# 分发文件
router.register(r"api/distribution_file", DistributionFileViewSet, basename="distribution_file")

urlpatterns = router.urls + [
    path("api/open/upload_file", OpenFileUploadView.as_view(), name="open_upload_file"),
    path("api/open/delete_file", OpenFileDeleteView.as_view(), name="open_delete_file"),
    path("api/open/job_list", OpenJobListView.as_view(), name="open_job_list"),
    path("api/open/script_execute", OpenScriptExecuteView.as_view(), name="open_script_execute"),
    path("api/open/job_status", OpenJobStatusView.as_view(), name="open_job_status"),
    path("api/open/job_detail/<int:task_id>", OpenJobDetailView.as_view(), name="open_job_detail"),
]
