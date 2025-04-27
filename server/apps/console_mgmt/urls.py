from django.contrib import admin
from django.urls import re_path
from rest_framework import routers

from apps.console_mgmt import views

admin.site.site_title = "Console Management"
admin.site.site_header = admin.site.site_title
router = routers.DefaultRouter()
urlpatterns = [
    re_path(r"init_user_set/", views.init_user_set),
]
urlpatterns += router.urls
