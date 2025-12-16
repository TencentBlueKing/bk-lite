# -*- coding: utf-8 -*-
"""
Lab 镜像初始化命令
从预定义配置中初始化 IDE 和基础设施镜像
"""

from django.core.management import BaseCommand
from apps.lab.models import LabImage
from apps.lab.constants.image_init import INIT_IMAGES
from apps.core.logger import opspilot_logger as logger


class Command(BaseCommand):
    help = "初始化IDE镜像和基础设施镜像"
    
    def add_arguments(self, parser):
        """添加命令参数"""
        parser.add_argument(
            '--force',
            action='store_true',
            help='强制更新已存在的镜像',
        )
    
    def handle(self, *args, **options):
        """执行初始化"""
        force_update = options.get('force', False)
        
        created_count = 0
        updated_count = 0
        skip_count = 0
        error_count = 0
        
        self.stdout.write(self.style.NOTICE(f"开始初始化 Lab 镜像，共 {len(INIT_IMAGES)} 个配置..."))
        
        for image_config in INIT_IMAGES:
            try:
                name = image_config.get('name')
                version = image_config.get('version')
                image_type = image_config.get('image_type')
                
                # 准备镜像数据
                defaults = {
                    'description': image_config.get('description', f"{name} {version}"),
                    'image': image_config.get('image', 'null'),
                    'default_port': image_config.get('default_port', 8888),
                    'default_env': image_config.get('default_env', {}),
                    'default_command': image_config.get('default_command', []),
                    'default_args': image_config.get('default_args', []),
                    'expose_ports': image_config.get('expose_ports', []),
                    'volume_mounts': image_config.get('volume_mounts', []),
                }
                
                # 使用 get_or_create
                lab_image, created = LabImage.objects.get_or_create(
                    name=name,
                    version=version,
                    image_type=image_type,
                    defaults=defaults
                )
                
                if created:
                    # 新创建
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"创建: {image_type} - {name}:{version}"
                        )
                    )
                    created_count += 1
                elif force_update:
                    # 强制更新
                    for key, value in defaults.items():
                        setattr(lab_image, key, value)
                    lab_image.save()
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"更新: {image_type} - {name}:{version}"
                        )
                    )
                    updated_count += 1
                else:
                    # 已存在且不强制更新
                    self.stdout.write(
                        self.style.WARNING(
                            f"跳过: {image_type} - {name}:{version} (已存在)"
                        )
                    )
                    skip_count += 1
                
            except Exception as e:
                error_count += 1
                error_msg = f"失败: {image_config.get('name')}:{image_config.get('version')} - {str(e)}"
                self.stdout.write(self.style.ERROR(error_msg))
                logger.exception(f"初始化镜像失败: {error_msg}")
        
        # 输出统计信息
        self.stdout.write(self.style.NOTICE("\n初始化完成:"))
        self.stdout.write(self.style.SUCCESS(f"  ✓ 创建: {created_count}"))
        if updated_count > 0:
            self.stdout.write(self.style.SUCCESS(f"  ✓ 更新: {updated_count}"))
        if skip_count > 0:
            self.stdout.write(self.style.WARNING(f"  - 跳过: {skip_count}"))
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f"  ✗ 失败: {error_count}"))
        
        self.stdout.write(self.style.NOTICE(f"\n当前 Lab 镜像总数: {LabImage.objects.count()}"))
        self.stdout.write(self.style.NOTICE(f"  - IDE 镜像: {LabImage.objects.filter(image_type='ide').count()}"))
        self.stdout.write(self.style.NOTICE(f"  - 基础设施镜像: {LabImage.objects.filter(image_type='infra').count()}"))
