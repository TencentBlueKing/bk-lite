# -*- coding: utf-8 -*-
"""
Lab 环境序列化器
"""

import os
import requests
from rest_framework import serializers
from apps.core.utils.serializers import AuthSerializer
from apps.lab.models import LabEnv, LabImage, InfraInstance
from apps.lab.models import LabImage, InfraInstance
from apps.core.logger import opspilot_logger as logger
from apps.lab.utils.webhook_client import WebhookClient


class LabEnvSerializer(AuthSerializer):
    """Lab 环境序列化器"""
    permission_key = "dataset.lab_labenv"


    state_display = serializers.CharField(source='get_state_display', read_only=True)
    ide_image_name = serializers.CharField(source='ide_image.name', read_only=True)
    ide_image_version = serializers.CharField(source='ide_image.version', read_only=True)
    
    # 关联的基础设施实例信息和实例数量，通过命名约定关联到对应的方法
    infra_instances_info = serializers.SerializerMethodField()
    infra_instances_count = serializers.SerializerMethodField()
    
    # 接收前端传递的镜像ID列表，系统会自动创建对应实例
    infra_images = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False,
        help_text="基础设施镜像ID列表,系统会自动创建对应实例"
    )
    
    class Meta:
        model = LabEnv
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'state_display',
                           'ide_image_name', 'ide_image_version',
                           'infra_instances_info', 'infra_instances_count']
        
    # 关联到字段infra_instances_info的方法
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
    
    # 关联到字段infra_instances_count的方法
    def get_infra_instances_count(self, obj):
        """获取关联的基础设施实例数量"""
        return obj.infra_instances.count()
    
    def create(self, validated_data):
        """创建环境时,根据镜像ID自动创建实例并生成 docker-compose 配置"""
        infra_images = validated_data.pop('infra_images', [])
        lab_env = super().create(validated_data)
        
        # 根据镜像ID自动创建实例
        if infra_images:
            self._create_infra_instances_from_images(lab_env, infra_images)
        
        # 生成并发送 docker-compose 配置
        self._setup_docker_compose(lab_env)
        
        return lab_env
    
    def update(self, instance, validated_data):
        """更新环境时，如果提供了镜像列表，则更新实例并重新生成配置"""
        infra_images = validated_data.pop('infra_images', None)
        lab_env = super().update(instance, validated_data)
        
        # 如果提供了镜像列表，更新实例
        if infra_images is not None:
            self._update_infra_instances_from_images(lab_env, infra_images)
            # 重新生成 docker-compose 配置
            self._setup_docker_compose(lab_env)
        
        return lab_env
    
    def _create_infra_instances_from_images(self, lab_env, image_ids):
        """
        根据镜像ID创建实例并关联到环境
        
        Args:
            lab_env: Lab环境对象
            image_ids: 镜像ID列表
        """
        
        
        instances = []
        for image_id in image_ids:
            try:
                # 获取基础设施镜像
                image = LabImage.objects.get(id=image_id, image_type='infra')
                
                # 自动生成实例名称（环境名_镜像名_镜像ID）
                instance_name = f"{lab_env.name}_{image.name}_{image.id}"
                
                # 创建实例（使用镜像的默认配置）
                instance = InfraInstance.objects.create(
                    name=instance_name,
                    image=image,
                    user=image.default_user or '',
                    env_vars=image.default_env or {},
                    command=image.default_command or [],
                    args=image.default_args or [],
                    volume_mounts=image.volume_mounts or [],
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
        策略：
        1. 镜像ID列表变化 -> 删除旧实例，创建新实例
        2. 镜像ID列表不变 -> 同步更新现有实例的配置（从镜像默认配置）
        
        Args:
            lab_env: Lab环境对象
            image_ids: 镜像ID列表
        """
        from apps.core.logger import opspilot_logger as logger
        
        # 获取当前环境的实例及其对应的镜像ID
        current_instances = list(lab_env.infra_instances.all())
        current_image_ids = set(instance.image.id for instance in current_instances)
        new_image_ids = set(image_ids)
        
        # 情况1: 镜像ID列表相同，更新现有实例配置
        if current_image_ids == new_image_ids:
            logger.info(f"环境 {lab_env.name} 的镜像列表未变化，检查并同步镜像配置到实例")
            
            for instance in current_instances:
                image = instance.image
                updated_fields = []
                
                # 同步运行用户
                if image.default_user and instance.user != image.default_user:
                    instance.user = image.default_user
                    updated_fields.append('user')
                
                # 同步环境变量（如果实例的配置为空或与镜像默认配置不一致）
                if image.default_env and instance.env_vars != image.default_env:
                    instance.env_vars = image.default_env
                    updated_fields.append('env_vars')
                
                # 同步命令和参数
                if image.default_command and instance.command != image.default_command:
                    instance.command = image.default_command
                    updated_fields.append('command')
                
                if image.default_args and instance.args != image.default_args:
                    instance.args = image.default_args
                    updated_fields.append('args')
                
                # 同步卷挂载配置
                if image.volume_mounts and instance.volume_mounts != image.volume_mounts:
                    instance.volume_mounts = image.volume_mounts
                    updated_fields.append('volume_mounts')
                
                # 如果有字段更新，保存实例
                if updated_fields:
                    instance.save()
                    logger.info(f"实例 {instance.name} 已同步镜像配置，更新字段: {', '.join(updated_fields)}")
                else:
                    logger.debug(f"实例 {instance.name} 配置已是最新")
            
            return
        
        # 情况2: 镜像ID列表变化，删除旧实例并创建新实例
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
    
    def _setup_docker_compose(self, lab_env):
        """
        生成并发送 docker-compose 配置到 webhook
        
        Args:
            lab_env: Lab环境对象
        """
        from apps.lab.utils.compose_generator import ComposeGenerator
        from apps.core.logger import opspilot_logger as logger
        
        try:
            # 生成 docker-compose 配置
            compose_config = ComposeGenerator.generate(lab_env)     
            
            # 使用 WebhookClient 构建 URL
            setup_url = WebhookClient.build_url('setup')
            if not setup_url:
                logger.error("Webhook URL 配置缺失")
                return None

            # 准备请求数据
            payload = {
                "id": f"lab-env-{lab_env.id}",
                "compose": compose_config
            }
            
            logger.info(f"正在为环境 {lab_env.name} (ID: {lab_env.id}) 生成 docker-compose 配置")
            logger.debug(f"Docker Compose 配置:\n{compose_config}")
            
            # 发送请求到 webhook
            response = requests.post(
                setup_url,
                json=payload,
                timeout=30,
                headers={'Content-Type': 'application/json'}
            )
            
            # 检查响应
            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 'success':
                    logger.info(f"环境 {lab_env.name} 的 docker-compose 配置已成功发送")
                else:
                    error_msg = result.get('error', result.get('message', '未知错误'))
                    logger.error(f"环境 {lab_env.name} 配置失败: {error_msg}")
            else:
                logger.error(f"Webhook 请求失败: HTTP {response.status_code}")
                
        except requests.exceptions.Timeout:
            logger.error(f"Webhook 请求超时")
        except requests.exceptions.RequestException as e:
            logger.error(f"Webhook 请求异常: {e}")
        except Exception as e:
            logger.exception(f"生成配置时发生异常: {e}")