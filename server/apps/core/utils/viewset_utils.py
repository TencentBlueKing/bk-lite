from django.db.models import Q
from rest_framework import viewsets
from rest_framework.response import Response


class MaintainerViewSet(viewsets.ModelViewSet):
    def perform_create(self, serializer):
        """创建时补充基础Model中的字段"""
        user = serializer.context.get("request").user
        username = getattr(user, "username", "guest")
        if hasattr(serializer.Meta.model, "created_by"):
            serializer.save(created_by=username, updated_by=username)
        return super().perform_create(serializer)

    def perform_update(self, serializer):
        """更新时补充基础Model中的字段"""
        user = serializer.context.get("request").user
        username = getattr(user, "username", "guest")
        if hasattr(serializer.Meta.model, "updated_by"):
            serializer.save(updated_by=username)
        return super().perform_update(serializer)


class AuthViewSet(MaintainerViewSet):
    def filter_rules(self, queryset, rules):
        if not rules:
            return queryset
        if len(rules) == 1 and str(rules[0]["id"]) == "0":
            return queryset
        return queryset.filter(id__in=[i["id"] for i in rules])

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        return self.query_by_groups(request, queryset)

    def query_by_groups(self, request, queryset):
        if not request.user.is_superuser:
            if hasattr(self, "permission_key"):
                if "." in self.permission_key:
                    keys = self.permission_key.split(".")
                    rules = request.user.rules.get(keys[0], {}).get(keys[1], [])
                else:
                    rules = request.user.rules.get(self.permission_key, [])
                queryset = self.filter_rules(queryset, rules)
            teams = [i["id"] for i in request.user.group_list]
            query = Q()
            for team_member in teams:
                query |= Q(team__contains=team_member)
            queryset = queryset.filter(query)
        return self._list(queryset.order_by("-id"))

    def _list(self, queryset):
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        data = request.data
        instance = self.get_object()
        if (not request.user.is_superuser) and (instance.created_by != request.user.username):
            data.pop("team", [])
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        if getattr(instance, "_prefetched_objects_cache", None):
            instance._prefetched_objects_cache = {}
        return Response(serializer.data)

    def _validate_name(self, name, group_list, team, exclude_id=None):
        queryset = self.queryset.filter(name=name)
        if exclude_id:
            queryset = queryset.exclude(id=exclude_id)
        team_list = list(queryset.values_list("team", flat=True))
        exist_teams = []
        for i in team_list:
            exist_teams.extend(i)
        team_name_map = {i["id"]: i["name"] for i in group_list}
        for i in team:
            if i in exist_teams:
                return team_name_map.get(i)
        return ""
