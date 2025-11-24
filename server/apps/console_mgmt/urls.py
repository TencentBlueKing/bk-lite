from django.contrib import admin
from django.urls import re_path
from rest_framework import routers

from apps.console_mgmt import views

admin.site.site_title = "Console Management"
admin.site.site_header = admin.site.site_title
router = routers.DefaultRouter()
urlpatterns = [
    re_path(r"init_user_set/", views.init_user_set),
    re_path(r"update_user_base_info/", views.update_user_base_info),
    re_path(r"validate_pwd/", views.validate_pwd),
    re_path(r"validate_email_code/", views.validate_email_code),
    re_path(r"send_email_code/", views.send_email_code),
    re_path(r"get_user_info/", views.get_user_info),
    re_path(r"reset_pwd/", views.reset_pwd),
]
urlpatterns += router.urls
