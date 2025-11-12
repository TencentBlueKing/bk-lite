from rest_framework import routers

from apps.system_mgmt.viewset import (
    AppViewSet,
    ChannelViewSet,
    CustomMenuGroupViewSet,
    GroupDataRuleViewSet,
    GroupViewSet,
    LoginModuleViewSet,
    OperationLogViewSet,
    RoleViewSet,
    SystemSettingsViewSet,
    UserLoginLogViewSet,
    UserViewSet,
)

router = routers.DefaultRouter()
router.register(r"group", GroupViewSet, basename="group_mgmt")
router.register(r"user", UserViewSet, basename="user_mgmt")
router.register(r"role", RoleViewSet, basename="role_mgmt")
router.register(r"channel", ChannelViewSet)
router.register(r"group_data_rule", GroupDataRuleViewSet)
router.register(r"system_settings", SystemSettingsViewSet)
router.register(r"app", AppViewSet)
router.register(r"login_module", LoginModuleViewSet)
router.register(r"custom_menu_group", CustomMenuGroupViewSet)
router.register(r"user_login_log", UserLoginLogViewSet)
router.register(r"operation_log", OperationLogViewSet)
urlpatterns = router.urls
