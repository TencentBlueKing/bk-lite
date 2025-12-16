# -- coding: utf-8 --
# @File: init_default_namespace.py
# @Time: 2025/8/6 15:35
# @Author: windyzhao

import os
from urllib.parse import urlparse
from django.core.management import BaseCommand
from django.conf import settings

from apps.operation_analysis.models.datasource_models import NameSpace
from apps.operation_analysis.common.load_json_data import load_support_json
from apps.core.logger import operation_analysis_logger as logger


class Command(BaseCommand):
    help = "初始化或更新默认命名空间数据,支持TLS配置"

    def handle(self, *args, **options):
        """
        内置默认的namespace数据
        通过namespace.json文件配置 内置到模型NameSpace
        其中一些字段从环境变量NATS_SERVERS获取
        
        支持的NATS_SERVERS格式:
        - nats://admin:password@host:4222 (普通连接)
        - tls://admin:password@host:4222 (TLS安全连接)
        - host:4222 (默认使用普通连接)
        
        功能:
        - 如果命名空间不存在,则创建
        - 如果命名空间已存在,则更新配置(account、domain、enable_tls、password)
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

            # 解析NATS服务器URL，支持 nats:// 和 tls:// 协议
            if nats_servers.startswith('tls://'):
                enable_tls = True
                parsed_url = urlparse(nats_servers)
                account = parsed_url.username or "admin"
                password = parsed_url.password or "nats_password"
                domain = f"{parsed_url.hostname}:{parsed_url.port}" if parsed_url.port else parsed_url.hostname
            elif nats_servers.startswith('nats://'):
                enable_tls = False
                parsed_url = urlparse(nats_servers)
                account = parsed_url.username or "admin"
                password = parsed_url.password or "nats_password"
                domain = f"{parsed_url.hostname}:{parsed_url.port}" if parsed_url.port else parsed_url.hostname
            else:
                # 如果不是完整URL，直接作为域名使用，默认不启用TLS
                enable_tls = False
                account = "admin"
                password = "nats_password"
                domain = nats_servers.replace('nats://', '').replace('tls://', '')

            # 从JSON文件加载命名空间数据
            namespace_data_list = load_support_json('namespace.json')

            # 初始化默认命名空间数据
            for namespace_data in namespace_data_list:
                if namespace_data["name"] == '默认命名空间':
                    namespace_data.update({
                        'account': account,
                        'password': password,
                        'domain': domain,
                        'enable_tls': enable_tls
                    })

                # 使用get_or_create获取或创建命名空间
                namespace, created = NameSpace.objects.get_or_create(
                    name=namespace_data['name'],
                    defaults=namespace_data
                )

                if created:
                    logger.info(f"创建默认命名空间成功: {namespace.name} (TLS: {enable_tls})")
                    self.stdout.write(
                        self.style.SUCCESS(f"创建默认命名空间成功: {namespace.name} (TLS: {enable_tls})")
                    )
                else:
                    # 如果已存在，更新配置信息（除了name之外的字段）
                    updated = False
                    if namespace.account != account:
                        namespace.account = account
                        updated = True
                    if namespace.domain != domain:
                        namespace.domain = domain
                        updated = True
                    if namespace.enable_tls != enable_tls:
                        namespace.enable_tls = enable_tls
                        updated = True
                    # 注意：密码需要特殊处理，因为存储的是加密后的密码
                    if password and namespace.decrypt_password != password:
                        namespace.set_password(password)
                        updated = True
                    
                    if updated:
                        namespace.save()
                        logger.info(f"更新默认命名空间成功: {namespace.name} (TLS: {enable_tls})")
                        self.stdout.write(
                            self.style.SUCCESS(f"更新默认命名空间成功: {namespace.name} (TLS: {enable_tls})")
                        )
                    else:
                        logger.info(f"默认命名空间配置未变化: {namespace.name}")
                        self.stdout.write(
                            self.style.WARNING(f"默认命名空间配置未变化: {namespace.name}")
                        )

        except Exception as e:
            logger.error(f"初始化默认命名空间失败: {e}")
            self.stdout.write(
                self.style.ERROR(f"初始化默认命名空间失败: {e}")
            )
