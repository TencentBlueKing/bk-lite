"""补丁管理 URL 配置"""

from rest_framework import routers

from apps.patch_mgmt.views import (
    GovernanceTaskViewSet,
    PatchBaselineViewSet,
    PatchDashboardViewSet,
    PatchSourceViewSet,
    PatchTargetViewSet,
    PatchViewSet,
    RiskViewSet,
    ScanSettingViewSet,
)

router = routers.DefaultRouter(trailing_slash=True)

# 补丁源配置
router.register(r"api/patch_source", PatchSourceViewSet, basename="patch_source")

# 补丁库
router.register(r"api/patch", PatchViewSet, basename="patch")

# 目标管理
router.register(r"api/patch_target", PatchTargetViewSet, basename="patch_target")

# 基线管理
router.register(r"api/baseline", PatchBaselineViewSet, basename="baseline")

# 治理任务（统一执行记录）
router.register(r"api/governance", GovernanceTaskViewSet, basename="governance")

# 风险治理（动态计算，三视角聚合）
router.register(r"api/risk", RiskViewSet, basename="risk")

# Dashboard
router.register(r"api/dashboard", PatchDashboardViewSet, basename="patch_dashboard")

# 全局扫描设置
router.register(r"api/scan_setting", ScanSettingViewSet, basename="scan_setting")

urlpatterns = router.urls
