# -*- coding: utf-8 -*-
"""
Lab 模块 URL 配置
"""

from rest_framework.routers import DefaultRouter
from django.urls import path, include

from apps.lab.views import (
    LabImageViewSet,
    InfraInstanceViewSet,
    LabEnvViewSet,
)

# 创建路由器
router = DefaultRouter()

# 注册视图集
router.register(r'images', LabImageViewSet, basename='labimage')
router.register(r'infra-instances', InfraInstanceViewSet, basename='infrainstance')
router.register(r'environments', LabEnvViewSet, basename='labenv')

# URL 模式
urlpatterns = router.urls
