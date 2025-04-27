# -*- coding: utf-8 -*-
"""
自定义ModelViewSet 补充create 和 update 时的用户相关信息
"""
from rest_framework import viewsets


class ModelViewSet(viewsets.ModelViewSet):
    """按需改造DRF默认的ModelViewSet类"""

    def perform_create(self, serializer):
        """创建时补充基础Model中的字段"""
        user = serializer.context.get("request").user
        username = getattr(user, "username", "guest")
        if hasattr(serializer.Meta.model, "created_by"):
            serializer.save(created_by=username, updated_by=username)

    def perform_update(self, serializer):
        """更新时补充基础Model中的字段"""
        user = serializer.context.get("request").user
        username = getattr(user, "username", "guest")
        if hasattr(serializer.Meta.model, "updated_by"):
            serializer.save(updated_by=username)
