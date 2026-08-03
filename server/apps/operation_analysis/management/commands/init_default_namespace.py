# -- coding: utf-8 --
# @File: init_default_namespace.py
# @Time: 2025/8/6 15:35
# @Author: windyzhao

import os
from urllib.parse import unquote, urlparse

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.core.logger import operation_analysis_logger as logger
from apps.operation_analysis.common.load_json_data import load_support_json
from apps.operation_analysis.models.datasource_models import NameSpace


class Command(BaseCommand):
    help = "初始化或更新默认命名空间数据,支持TLS配置"

    @staticmethod
    def _parse_nats_config(nats_servers):
        if not isinstance(nats_servers, str) or not nats_servers.strip():
            raise CommandError("NATS_SERVERS 未配置，禁止初始化默认命名空间")

        nats_servers = nats_servers.strip()
        has_scheme = "://" in nats_servers
        try:
            parsed_url = urlparse(nats_servers if has_scheme else f"//{nats_servers}")
            hostname = parsed_url.hostname
            port = parsed_url.port
        except ValueError as error:
            raise CommandError("NATS_SERVERS 配置非法") from error

        if has_scheme and parsed_url.scheme not in {"nats", "tls"}:
            raise CommandError("NATS_SERVERS 仅支持 nats:// 或 tls:// 协议")
        enable_tls = parsed_url.scheme == "tls"
        decoded_hostname = unquote(hostname) if hostname else ""

        if (
            not hostname
            or ("%" in hostname and ":" not in hostname)
            or any(character.isspace() or not character.isprintable() for character in decoded_hostname)
            or port is None
            or port <= 0
            or parsed_url.path not in {"", "/"}
            or parsed_url.params
            or parsed_url.query
            or parsed_url.fragment
        ):
            raise CommandError("NATS_SERVERS 必须包含合法主机和端口")

        raw_user = parsed_url.username
        raw_password = parsed_url.password
        has_url_credentials = raw_user is not None or raw_password is not None
        if not has_scheme and has_url_credentials:
            raise CommandError("纯主机 NATS_SERVERS 必须通过 NATS_USER 和 NATS_PASSWORD 配置凭据")
        if (raw_user is None) != (raw_password is None):
            raise CommandError("NATS_SERVERS 账号和密码必须同时配置")

        if has_url_credentials:
            account = unquote(raw_user)
            password = unquote(raw_password)
            if not account.strip() or not password.strip():
                raise CommandError("NATS_SERVERS 账号和密码不能为空")
        else:
            nats_options = getattr(settings, "NATS_OPTIONS", {})
            account = nats_options.get("user") if isinstance(nats_options, dict) else None
            password = nats_options.get("password") if isinstance(nats_options, dict) else None
            if not isinstance(account, str) or not account.strip() or not isinstance(password, str) or not password.strip():
                raise CommandError("NATS_SERVERS 未包含凭据，请通过 NATS_USER 和 NATS_PASSWORD 显式配置")

        domain = f"[{hostname}]:{port}" if ":" in hostname else f"{hostname}:{port}"
        return account, password, domain, enable_tls

    def handle(self, *args, **options):
        """
        内置默认的namespace数据
        通过namespace.json文件配置 内置到模型NameSpace
        其中一些字段从环境变量NATS_SERVERS获取

        支持的NATS_SERVERS格式:
        - nats://admin:password@host:4222 (普通连接)
        - tls://admin:password@host:4222 (TLS安全连接)
        - host:4222 (默认使用普通连接，凭据读取NATS_USER/NATS_PASSWORD)

        功能:
        - 如果命名空间不存在,则创建
        - 如果命名空间已存在,则更新配置(account、domain、enable_tls、password)
        """
        try:
            # 从环境变量获取NATS服务器配置
            nats_servers = getattr(settings, "NATS_SERVERS", "") or os.getenv("NATS_SERVERS", "")
            account, password, domain, enable_tls = self._parse_nats_config(nats_servers)

            # 从JSON文件加载命名空间数据
            namespace_data_list = load_support_json("namespace.json")

            # 初始化默认命名空间数据
            for namespace_data in namespace_data_list:
                if namespace_data["name"] == "默认命名空间":
                    namespace_data.update({"account": account, "password": password, "domain": domain, "enable_tls": enable_tls})

                # 使用get_or_create获取或创建命名空间
                namespace, created = NameSpace.objects.get_or_create(name=namespace_data["name"], defaults=namespace_data)

                if created:
                    logger.info("[NamespaceInit] 创建默认命名空间成功：%s (TLS: %s)", namespace.name, enable_tls)
                    self.stdout.write(self.style.SUCCESS(f"创建默认命名空间成功: {namespace.name} (TLS: {enable_tls})"))
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
                        logger.info("[NamespaceInit] 更新默认命名空间成功：%s (TLS: %s)", namespace.name, enable_tls)
                        self.stdout.write(self.style.SUCCESS(f"更新默认命名空间成功: {namespace.name} (TLS: {enable_tls})"))
                    else:
                        logger.info("[NamespaceInit] 默认命名空间配置未变化：%s", namespace.name)
                        self.stdout.write(self.style.WARNING(f"默认命名空间配置未变化: {namespace.name}"))

        except CommandError:
            raise
        except Exception as e:
            logger.error("[NamespaceInit] 初始化默认命名空间失败：%s", e, exc_info=True)
            self.stdout.write(self.style.ERROR(f"初始化默认命名空间失败: {e}"))
