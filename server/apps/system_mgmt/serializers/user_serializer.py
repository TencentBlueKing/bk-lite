from rest_framework import serializers

from apps.system_mgmt.models import Group, Role, User


class UserSerializer(serializers.ModelSerializer):
    group_role_list = serializers.SerializerMethodField()
    is_superuser = serializers.SerializerMethodField()

    # 类级别缓存，避免每次实例化都查询数据库
    _super_role_id_cache = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._group_roles_map = None
        self.super_role_id = self._get_super_role_id()

        # 仅在列表序列化时（many=True）进行批量查询
        if kwargs.get("many", False):
            instance = kwargs.get("instance")
            if instance:
                self._group_roles_map = self._build_group_roles_map(instance)

    @classmethod
    def _get_super_role_id(cls):
        """获取 admin 角色 ID（使用类级别缓存）"""
        if cls._super_role_id_cache is None:
            try:
                cls._super_role_id_cache = Role.objects.get(app="", name="admin").id
            except Role.DoesNotExist:
                cls._super_role_id_cache = -1  # 使用不存在的 ID 作为默认值
        return cls._super_role_id_cache

    def _collect_group_ids(self, instance):
        """从用户实例中收集所有组 ID"""
        all_group_ids = set()
        try:
            for user in instance:
                if hasattr(user, "group_list") and user.group_list:
                    all_group_ids.update(user.group_list)
        except (TypeError, AttributeError):
            # 如果 instance 不可迭代或没有 group_list，返回空集合
            pass
        return all_group_ids

    def _build_group_roles_map(self, instance):
        """构建组 ID 到角色名称列表的映射"""
        all_group_ids = self._collect_group_ids(instance)
        if not all_group_ids:
            return None

        groups = Group.objects.filter(id__in=list(all_group_ids)).prefetch_related("roles")

        group_roles_map = {}
        for group in groups:
            role_names = [f"{role.app}@@{role.name}" if role.app else role.name for role in group.roles.all()]
            group_roles_map[group.id] = role_names

        return group_roles_map

    class Meta:
        model = User
        fields = "__all__"

    def get_is_superuser(self, obj):
        return self.super_role_id in obj.role_list

    def get_group_role_list(self, obj):
        """获取用户所属组织的角色名称列表"""
        if not obj.group_list:
            return []

        # 如果有缓存的映射，使用缓存
        if self._group_roles_map is not None:
            return self._get_roles_from_cache(obj.group_list)

        # 单个对象序列化时的降级处理
        return self._get_roles_from_database(obj.group_list)

    def _get_roles_from_cache(self, group_list):
        """从缓存映射中获取角色列表"""
        role_names = set()
        for group_id in group_list:
            if group_id in self._group_roles_map:
                role_names.update(self._group_roles_map[group_id])
        return list(role_names)

    def _get_roles_from_database(self, group_list):
        """从数据库查询角色列表（单对象序列化降级处理）"""
        groups = Group.objects.filter(id__in=group_list).prefetch_related("roles")
        role_names = {f"{role.app}@@{role.name}" if role.app else role.name for group in groups for role in group.roles.all()}
        return list(role_names)
