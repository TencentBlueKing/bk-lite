# -*- coding: utf-8 -*-
"""
Lab 环境序列化器
"""

from rest_framework import serializers
from apps.core.utils.serializers import AuthSerializer
from apps.lab.models import LabEnv, LabImage, InfraInstance


class LabEnvSerializer(AuthSerializer):
    """Lab 环境序列化器"""
    permission_key = "dataset.lab_labenv"


    state_display = serializers.CharField(source='get_state_display', read_only=True)
    ide_image_name = serializers.CharField(source='ide_image.name', read_only=True)
    ide_image_version = serializers.CharField(source='ide_image.version', read_only=True)
    
    # 关联的基础设施实例信息
    infra_instances_info = serializers.SerializerMethodField()
    # 基础设施实例数量（用于列表视图）
    infra_instances_count = serializers.SerializerMethodField()
    
    # 新增：接收前端传递的镜像ID列表，系统会自动创建对应实例
    infra_images = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False,
        help_text="基础设施镜像ID列表，系统会自动创建对应实例"
    )
    
    class Meta:
        model = LabEnv
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'state_display',
                           'ide_image_name', 'ide_image_version',
                           'infra_instances_info', 'infra_instances_count']
        
    def get_infra_instances_info(self, obj):
        """获取关联的基础设施实例信息"""
        instances = obj.infra_instances.all()
        return [
            {
                'id': instance.id,
                'name': instance.name,
                'status': instance.status,
                'status_display': instance.get_status_display(),
                'image': instance.image.id,  # 添加镜像ID用于前端回显
                'image_name': instance.image.name,
                'image_version': instance.image.version,
                'endpoint': instance.endpoint
            }
            for instance in instances
        ]
        
    def get_infra_instances_count(self, obj):
        """获取关联的基础设施实例数量"""
        return obj.infra_instances.count()
    
    def create(self, validated_data):
        """创建环境时，根据镜像ID自动创建实例"""
        infra_images = validated_data.pop('infra_images', [])
        lab_env = super().create(validated_data)
        
        # 根据镜像ID自动创建实例
        if infra_images:
            self._create_infra_instances_from_images(lab_env, infra_images)
        
        return lab_env
    
    def update(self, instance, validated_data):
        """更新环境时，如果提供了镜像列表，则更新实例"""
        infra_images = validated_data.pop('infra_images', None)
        lab_env = super().update(instance, validated_data)
        
        # 如果提供了镜像列表，更新实例
        if infra_images is not None:
            self._update_infra_instances_from_images(lab_env, infra_images)
        
        return lab_env
    
    def _create_infra_instances_from_images(self, lab_env, image_ids):
        """
        根据镜像ID创建实例并关联到环境
        
        Args:
            lab_env: Lab环境对象
            image_ids: 镜像ID列表
        """
        from apps.lab.models import LabImage, InfraInstance
        from apps.core.logger import opspilot_logger as logger
        
        instances = []
        for image_id in image_ids:
            try:
                # 获取基础设施镜像
                image = LabImage.objects.get(id=image_id, image_type='infra')
                
                # 自动生成实例名称（环境名_镜像名_镜像ID）
                # 使用镜像ID确保唯一性，避免过长的时间戳
                instance_name = f"{lab_env.name}_{image.name}_{image.id}"
                
                # 创建实例（使用镜像的默认配置）
                instance = InfraInstance.objects.create(
                    name=instance_name,
                    image=image,
                    env_vars=image.default_env or {},
                    command=image.default_command or [],
                    args=image.default_args or [],
                    status='stopped',
                    created_by=lab_env.created_by,
                    updated_by=lab_env.updated_by,
                    domain=lab_env.domain,
                    updated_by_domain=lab_env.updated_by_domain
                )
                instances.append(instance)
                logger.info(f"自动创建基础设施实例: {instance_name} (镜像: {image.name}:{image.version})")
                
            except LabImage.DoesNotExist:
                logger.warning(f"镜像ID {image_id} 不存在或不是基础设施镜像，跳过")
                continue
            except Exception as e:
                logger.error(f"创建基础设施实例失败 (镜像ID: {image_id}): {e}")
                continue
        
        # 关联实例到环境
        if instances:
            lab_env.infra_instances.set(instances)
            logger.info(f"环境 {lab_env.name} 关联了 {len(instances)} 个基础设施实例")
    
    def _update_infra_instances_from_images(self, lab_env, image_ids):
        """
        更新环境的基础设施实例
        策略：只有在镜像列表真正改变时才重新创建实例
        
        Args:
            lab_env: Lab环境对象
            image_ids: 镜像ID列表
        """
        from apps.core.logger import opspilot_logger as logger
        
        # 获取当前环境的实例及其对应的镜像ID
        current_instances = list(lab_env.infra_instances.all())
        current_image_ids = set(instance.image.id for instance in current_instances)
        new_image_ids = set(image_ids)
        
        # 比较镜像ID列表，判断是否有变化
        if current_image_ids == new_image_ids:
            logger.info(f"环境 {lab_env.name} 的镜像配置未变化，跳过实例更新")
            return
        
        logger.info(f"环境 {lab_env.name} 的镜像配置已变化，从 {current_image_ids} 更新为 {new_image_ids}")
        
        # 清空旧的关联关系
        lab_env.infra_instances.clear()
        
        # 删除旧实例（如果实例只属于当前环境）
        for instance in current_instances:
            # 检查实例是否还被其他环境使用
            if instance.lab_envs.count() == 0:
                logger.info(f"删除未被使用的实例: {instance.name}")
                instance.delete()
        
        # 根据新的镜像列表创建实例
        self._create_infra_instances_from_images(lab_env, image_ids)