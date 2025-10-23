# -- coding: utf-8 --
# @File: init_default_namespace.py
# @Time: 2025/8/6 15:35
# @Author: windyzhao

import os
from urllib.parse import urlparse
from django.core.management import BaseCommand
from django.conf import settings

from apps.operation_analysis.models import NameSpace
from apps.core.logger import operation_analysis_logger as logger
from apps.operation_analysis.init_constants import INIT_NAMESPACE_DATA


class Command(BaseCommand):
    help = "初始化默认命名空间数据"

    def handle(self, *args, **options):
        """
        内置默认的namespace数据
        通过INIT_NAMESPACE_DATA常量配置 内置到模型NameSpace
        其中一些字段从环境变量NATS_SERVERS获取
        """
        try:
            # 从环境变量获取NATS服务器配置
            nats_servers = getattr(settings, 'NATS_SERVERS', '') or os.getenv('NATS_SERVERS', '')

            if not nats_servers:
                logger.error("NATS_SERVERS环境变量未配置! 请检查配置.")
                self.stdout.write(
                    self.style.ERROR("NATS_SERVERS环境变量未配置! 请检查配置.")
                )
                return
            else:
                # 解析NATS服务器URL，格式如: nats://admin:nats_password@127.0.0.1:4222
                if nats_servers.startswith('nats://'):
                    parsed_url = urlparse(nats_servers)
                    account = parsed_url.username or "admin"
                    password = parsed_url.password or "nats_password"
                    domain = f"{parsed_url.hostname}:{parsed_url.port}" if parsed_url.port else parsed_url.hostname
                else:
                    # 如果不是完整URL，直接作为域名使用
                    account = "admin"
                    password = "nats_password"
                    domain = nats_servers.replace('nats://', '')

            # 初始化默认命名空间数据
            for namespace_data in INIT_NAMESPACE_DATA:
                namespace_data.update({
                    'account': account,
                    'password': password,
                    'domain': domain
                })

                # 使用get_or_create避免重复创建
                namespace, created = NameSpace.objects.get_or_create(
                    name=namespace_data['name'],
                    defaults=namespace_data
                )

                if created:
                    logger.info(f"创建默认命名空间成功: {namespace.name}")
                    self.stdout.write(
                        self.style.SUCCESS(f"创建默认命名空间成功: {namespace.name}")
                    )
                else:
                    logger.info(f"默认命名空间已存在: {namespace.name}")
                    self.stdout.write(
                        self.style.WARNING(f"默认命名空间已存在: {namespace.name}")
                    )

        except Exception as e:
            logger.error(f"初始化默认命名空间失败: {e}")
            self.stdout.write(
                self.style.ERROR(f"初始化默认命名空间失败: {e}")
            )
