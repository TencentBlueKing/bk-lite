"""作业管理 URL 配置"""

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

urlpatterns = router.urls
