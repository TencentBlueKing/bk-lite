from rest_framework import routers

from apps.system_mgmt.viewset import (
    AppViewSet,
    ChannelViewSet,
    CustomMenuGroupViewSet,
    ErrorLogViewSet,
    GroupDataRuleViewSet,
    GroupViewSet,
    IMNotificationChannelViewSet,
    IntegrationInstanceViewSet,
    LoginAuthBindingViewSet,
    OperationLogViewSet,
    RoleViewSet,
    SystemSettingsViewSet,
    UserLoginLogViewSet,
    UserSyncSourceViewSet,
    UserViewSet,
)

router = routers.DefaultRouter()
router.register(r"group", GroupViewSet, basename="group_mgmt")
router.register(r"user", UserViewSet, basename="user_mgmt")
router.register(r"role", RoleViewSet, basename="role_mgmt")
router.register(r"integration_instance", IntegrationInstanceViewSet)
router.register(r"im_notification_channel", IMNotificationChannelViewSet)
router.register(r"login_auth_binding", LoginAuthBindingViewSet)
router.register(r"user_sync_source", UserSyncSourceViewSet)
router.register(r"channel", ChannelViewSet)
router.register(r"group_data_rule", GroupDataRuleViewSet)
router.register(r"system_settings", SystemSettingsViewSet)
router.register(r"app", AppViewSet)
router.register(r"custom_menu_group", CustomMenuGroupViewSet)
router.register(r"user_login_log", UserLoginLogViewSet)
router.register(r"operation_log", OperationLogViewSet)
router.register(r"error_log", ErrorLogViewSet)
urlpatterns = router.urls

try:
    enterprise_urls = __import__("apps.system_mgmt.enterprise.urls", fromlist=["urlpatterns"])
    urlpatterns += enterprise_urls.urlpatterns
except (ImportError, ModuleNotFoundError):
    pass
