from django.contrib import admin
from django.urls import include, path, re_path
from rest_framework import routers

from apps.core.views import index_view
from apps.core.views.user_group import UserGroupViewSet

admin.site.site_title = "Opspilot Admin"
admin.site.site_header = admin.site.site_title
public_router = routers.DefaultRouter()
urlpatterns = [
    re_path(r"api/login/", index_view.login),
    re_path(r"api/bk_lite_login/", index_view.bk_lite_login),
    re_path(r"api/get_domain_list/", index_view.get_domain_list),
    re_path(r"api/get_wechat_settings/", index_view.get_wechat_settings),
    re_path(r"api/get_bk_settings/", index_view.get_bk_settings),
    re_path(r"api/wechat_user_register/", index_view.wechat_user_register),
    re_path(r"api/generate_qr_code/", index_view.generate_qr_code),
    re_path(r"api/verify_otp_code/", index_view.verify_otp_code),
    re_path(r"api/reset_pwd/", index_view.reset_pwd),
    re_path(r"api/login_info/", index_view.login_info),
    re_path(r"api/get_client/", index_view.get_client),
    re_path(r"api/get_my_client/", index_view.get_my_client),
    re_path(r"api/get_client_detail/", index_view.get_client_detail),
    re_path(r"api/get_user_menus/", index_view.get_user_menus),
    re_path(r"api/get_all_groups/", index_view.get_all_groups),
]

public_router.register(r"api/user_group", UserGroupViewSet, basename="user_group")

urlpatterns += public_router.urls
