from rest_framework import serializers

from apps.system_mgmt.models import Group, Role, User


class UserSerializer(serializers.ModelSerializer):
    group_role_list = serializers.SerializerMethodField()
    is_superuser = serializers.SerializerMethodField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._group_roles_map = None
        self.super_role_id = Role.objects.get(app="", name="admin").id

        # 仅在列表序列化时（many=True）进行批量查询
        if kwargs.get("many", False):
            # 获取所有用户的组ID
            instance = kwargs.get("instance")
            # 确保 instance 存在且可迭代（QuerySet 或 list）
            if instance is not None:
                all_group_ids = set()
                try:
                    for user in instance:
                        if hasattr(user, "group_list") and user.group_list:
                            all_group_ids.update(user.group_list)
                except TypeError:
                    # 如果 instance 不可迭代，跳过批量查询
                    pass

                # 批量查询所有相关组及其角色
                if all_group_ids:
                    groups = Group.objects.filter(id__in=list(all_group_ids)).prefetch_related("roles")

                    # 构建组ID到角色名称列表的映射
                    self._group_roles_map = {}
                    for group in groups:
                        role_names = []
                        for role in group.roles.all():
                            # 如果角色有app，使用 "app--name" 格式，否则直接使用name
                            role_name = f"{role.app}@@{role.name}" if role.app else role.name
                            role_names.append(role_name)
                        self._group_roles_map[group.id] = role_names

    class Meta:
        model = User
        fields = "__all__"

    def get_is_superuser(self, obj):
        return self.super_role_id in obj.role_list

    def get_group_role_list(self, obj):
        """
        获取用户所属组织的角色名称列表
        :param obj: User实例
        :return: 组角色名称列表
        """
        if not obj.group_list:
            return []

        # 如果有缓存的映射，使用缓存
        if self._group_roles_map is not None:
            role_names = set()
            for group_id in obj.group_list:
                if group_id in self._group_roles_map:
                    role_names.update(self._group_roles_map[group_id])
            return list(role_names)

        # 单个对象序列化时的降级处理
        groups = Group.objects.filter(id__in=obj.group_list).prefetch_related("roles")
        role_names = set()
        for group in groups:
            for role in group.roles.all():
                role_name = f"{role.app}@@{role.name}" if role.app else role.name
                role_names.add(role_name)

        return list(role_names)
