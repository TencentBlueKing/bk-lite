# -*- coding: utf-8 -*-
"""
Docker Compose 配置生成器
使用 Jinja2 模板生成 Lab 环境的 Docker Compose 配置
"""

import os
from typing import Dict, Any, List, Optional
from jinja2 import Environment, FileSystemLoader
from django.conf import settings
from apps.core.logger import opspilot_logger as logger


class ComposeGenerator:
    """Docker Compose 配置生成器"""

    # 模板文件路径
    TEMPLATE_DIR = os.path.join(
        settings.BASE_DIR, "apps", "lab", "support-files", "compose"
    )
    TEMPLATE_FILE = "docker-compose.yml.jinja2"

    @classmethod
    def generate(cls, lab_env) -> str:
        """
        生成 Lab 环境的 Docker Compose 配置

        Args:
            lab_env: LabEnv 对象

        Returns:
            str: docker-compose.yml 配置字符串

        Raises:
            ValueError: 模板文件不存在或模板渲染失败
        """
        from rest_framework import serializers
        from jinja2.exceptions import TemplateNotFound, TemplateError

        try:
            # 准备模板上下文
            context = cls._prepare_context(lab_env)

            # 使用 Jinja2 渲染模板
            env = Environment(loader=FileSystemLoader(cls.TEMPLATE_DIR))
            template = env.get_template(cls.TEMPLATE_FILE)
            compose_yaml = template.render(**context)

            return compose_yaml
        except TemplateNotFound as e:
            logger.error(f"模板文件不存在: {cls.TEMPLATE_FILE}", exc_info=True)
            raise serializers.ValidationError(f"模板配置错误: {str(e)}")
        except TemplateError as e:
            logger.error(f"模板渲染失败: {str(e)}", exc_info=True)
            raise serializers.ValidationError(f"生成配置失败: {str(e)}")
        except Exception as e:
            logger.exception("生成 Docker Compose 配置时发生未知错误")
            raise serializers.ValidationError("生成配置失败,请联系管理员")

    @classmethod
    def _prepare_context(cls, lab_env) -> Dict[str, Any]:
        """
        准备 Jinja2 模板上下文

        Args:
            lab_env: LabEnv 对象

        Returns:
            dict: 模板上下文数据
        """
        volumes_set = set()

        # 1. 准备 IDE 服务数据
        ide_service = cls._prepare_ide_service(lab_env, volumes_set)

        # 2. 准备基础设施服务数据
        infra_services = cls._prepare_infra_services(lab_env, volumes_set)

        return {
            "env_id": lab_env.id,
            "ide_service": ide_service,
            "infra_services": infra_services,
            "volumes": sorted(volumes_set),
        }

    @classmethod
    def _prepare_ide_service(cls, lab_env, volumes_set: set) -> Dict[str, Any]:
        """准备 IDE 服务配置"""
        # 拼接 IDE 镜像地址
        ide_image_address = (
            f"{lab_env.ide_image.name}:{lab_env.ide_image.version or ''}"
        )
        image_name = lab_env.ide_image.name.lower()

        # 优化服务名
        if "/" in lab_env.ide_image.name:
            ide_service_name = lab_env.ide_image.name.split("/")[-1]
        else:
            ide_service_name = lab_env.ide_image.name

        ide_service = {
            "name": ide_service_name,
            "image": ide_image_address,
            "container_name": f"lab-{lab_env.id}-ide",
        }

        # 运行用户
        if lab_env.ide_image.default_user:
            ide_service["user"] = lab_env.ide_image.default_user

        # 环境变量
        if lab_env.ide_image.default_env:
            ide_service["environment"] = lab_env.ide_image.default_env

        # 端口映射
        if lab_env.ide_image.expose_ports:
            ide_service["ports"] = [
                f"{port}:{port}" for port in lab_env.ide_image.expose_ports
            ]

        # 卷挂载
        volumes = cls._prepare_volume_mounts(
            lab_env.ide_image.volume_mounts, ide_service_name, volumes_set
        )
        if volumes:
            ide_service["volumes"] = volumes

        # 资源限制
        memory_str = cls._format_memory(lab_env.memory)
        ide_service["deploy"] = {
            "resources": {"limits": {"cpus": str(lab_env.cpu), "memory": memory_str}}
        }

        # GPU 需求
        if lab_env.gpu > 0:
            ide_service["deploy"]["resources"]["reservations"] = {
                "devices": [
                    {"driver": "nvidia", "count": lab_env.gpu, "capabilities": ["gpu"]}
                ]
            }

        # 启动命令和参数
        command = cls._prepare_command(
            lab_env.ide_image.default_command, lab_env.ide_image.default_args
        )

        if command:
            if "jupyter" in image_name:
                command.append(f"--ServerApp.base_url=/lab-{lab_env.id}")
            elif "code-server" in image_name:
                command.append(f"--abs-proxy-base-path=/lab-{lab_env.id}/")

            logger.info(command)
            ide_service["command"] = command

        # Traefik labels
        labels = cls._get_traefik_labels_for_ide(lab_env, ide_service["container_name"])
        if labels:
            ide_service["labels"] = labels

        return ide_service

    @classmethod
    def _prepare_infra_services(cls, lab_env, volumes_set: set) -> List[Dict[str, Any]]:
        """准备基础设施服务配置列表"""
        services = []

        for instance in lab_env.infra_instances.all():
            if not instance.image.name:
                logger.error(f"实例 {instance.name} 的镜像名称为空，跳过")
                continue

            # 处理服务名：移除 / 字符，只保留最后一部分，并替换特殊字符
            image_name = instance.image.name
            if "/" in image_name:
                image_name = image_name.split("/")[-1]
            service_name = image_name.lower().replace("_", "-").replace(" ", "-")
            image_address = (
                f"{instance.image.name}:{instance.image.version or 'latest'}"
            )

            service = {
                "name": service_name,
                "image": image_address,
            }

            # 运行用户(优先使用实例配置,其次使用镜像默认值)
            user = instance.user or instance.image.default_user
            if user:
                service["user"] = user

            # 环境变量
            if instance.env_vars:
                service["environment"] = instance.env_vars

            # 端口映射
            ports = cls._prepare_ports(instance)
            if ports:
                service["ports"] = ports

            # 卷挂载
            volumes = []

            # 实例的卷挂载配置
            if instance.volume_mounts:
                for mount in instance.volume_mounts:
                    host_path = mount.get("host_path")
                    container_path = mount.get("container_path")
                    read_only = mount.get("read_only", False)

                    # 绑定挂载(host_path 有效且不为 None/空)
                    if host_path and str(host_path).lower() != "none":
                        mount_str = f"{host_path}:{container_path}"
                        if read_only:
                            mount_str += ":ro"
                        volumes.append(mount_str)
                    # 命名卷(没有 host_path 或为 None)
                    elif container_path:
                        volume_name = mount.get("volume_name") or service_name
                        mount_str = f"{volume_name}:{container_path}"
                        if read_only:
                            mount_str += ":ro"
                        volumes.append(mount_str)
                        volumes_set.add(volume_name)

            # 持久化目录（命名卷）
            if instance.persistent_dirs:
                for dir_path in instance.persistent_dirs:
                    volume_name = service_name
                    volumes.append(f"{volume_name}:{dir_path}")
                    volumes_set.add(volume_name)

            if volumes:
                service["volumes"] = volumes

            # 资源限制
            deploy = cls._prepare_resource_limits(instance)
            if deploy:
                service["deploy"] = deploy

            # 启动命令和参数
            command = cls._prepare_command(instance.command, instance.args)
            if command:
                service["command"] = command

            # Traefik labels
            container_name = f"lab-{lab_env.id}-{service_name}"
            labels = cls._get_traefik_labels(
                service_name, instance, lab_env.id, container_name
            )
            if labels:
                service["labels"] = labels

            services.append(service)

        return services

    @classmethod
    def _prepare_volume_mounts(
        cls, volume_mounts, service_name: str, volumes_set: set
    ) -> List[str]:
        """准备卷挂载列表"""
        if not volume_mounts:
            return []

        volumes = []
        for mount in volume_mounts:
            host_path = mount.get("host_path")
            container_path = mount.get("container_path")
            read_only = mount.get("read_only", False)

            # 绑定挂载
            if host_path and host_path != "None":
                mount_str = f"{host_path}:{container_path}"
                if read_only:
                    mount_str += ":ro"
                volumes.append(mount_str)
            # 命名卷
            elif container_path:
                volume_name = mount.get("volume_name") or service_name
                mount_str = f"{volume_name}:{container_path}"
                if read_only:
                    mount_str += ":ro"
                volumes.append(mount_str)
                volumes_set.add(volume_name)

        return volumes

    @classmethod
    def _prepare_ports(cls, instance) -> List[str]:
        """准备端口映射列表"""
        ports = []

        # 优先使用镜像的 expose_ports
        if instance.image.expose_ports:
            for port in instance.image.expose_ports:
                ports.append(f"{port}:{port}")
        # 其次使用实例的 port_mappings
        elif instance.port_mappings:
            for container_port, host_port in instance.port_mappings.items():
                ports.append(f"{host_port}:{container_port}")

        return ports

    @classmethod
    def _prepare_resource_limits(cls, instance) -> Optional[Dict[str, Any]]:
        """准备资源限制配置"""
        if not (instance.cpu_limit or instance.memory_limit):
            return None

        deploy = {"resources": {"limits": {}}}

        if instance.cpu_limit:
            deploy["resources"]["limits"]["cpus"] = str(instance.cpu_limit)

        if instance.memory_limit:
            memory_str = cls._format_memory(instance.memory_limit)
            deploy["resources"]["limits"]["memory"] = memory_str

        return deploy

    @classmethod
    def _prepare_command(cls, command, args) -> Optional[Any]:
        """准备启动命令和参数"""
        if command:
            if args and isinstance(command, list):
                return command + list(args)
            return command
        return None

    @classmethod
    def _format_memory(cls, memory) -> str:
        """格式化内存为 Docker 支持的格式"""
        memory_str = str(memory) if not isinstance(memory, str) else memory

        # 统一转换为 Docker 支持的格式
        if memory_str.endswith("Gi"):
            return memory_str[:-2] + "G"
        elif memory_str.endswith("Mi"):
            return memory_str[:-2] + "M"

        return memory_str

    @classmethod
    def _get_traefik_labels_for_ide(
        cls, lab_env, container_name: str
    ) -> Optional[Dict[str, str]]:
        """为 IDE 服务生成 Traefik 路由标签"""
        endpoint = getattr(lab_env, "endpoint", None)
        if not endpoint:
            return None

        path_prefix = f"/lab-{lab_env.id}"
        image_name = lab_env.ide_image.name.lower()

        # 基础 labels 配置
        labels = {
            "traefik.enable": "true",
            f"traefik.http.routers.{container_name}.rule": f"Host(`{endpoint}`) && PathPrefix(`{path_prefix}`)",
            f"traefik.http.routers.{container_name}.entrypoints": "websecure",
        }

        # 根据镜像类型决定是否使用 StripPrefix
        if "jupyter" in image_name:
            # JupyterLab: 不使用 StripPrefix，直接处理完整路径
            pass
        elif "code-server" in image_name:
            # code-server: 使用 StripPrefix，处理根路径
            labels[
                f"traefik.http.middlewares.{container_name}-strip.stripprefix.prefixes"
            ] = path_prefix
            labels[f"traefik.http.routers.{container_name}.middlewares"] = (
                f"{container_name}-strip"
            )
        else:
            # 其他 IDE: 默认使用 StripPrefix
            labels[
                f"traefik.http.middlewares.{container_name}-strip.stripprefix.prefixes"
            ] = path_prefix
            labels[f"traefik.http.routers.{container_name}.middlewares"] = (
                f"{container_name}-strip"
            )

        # 只在配置了 expose_ports 时才指定端口
        if lab_env.ide_image.expose_ports:
            port = lab_env.ide_image.expose_ports[0]
            labels[
                f"traefik.http.services.{container_name}.loadbalancer.server.port"
            ] = str(port)

        return labels

    @classmethod
    def _get_traefik_labels(
        cls, service_name: str, instance, env_id: int, container_name: str
    ) -> Optional[Dict[str, str]]:
        """为基础设施服务生成 Traefik 路由标签（只为 traefik 镜像生成）"""
        # 只为 traefik 镜像生成 labels
        if "traefik" not in instance.image.name.lower():
            return None

        if not instance.endpoint:
            return None

        if not instance.port_mappings:
            return None

        container_port = list(instance.port_mappings.keys())[0]
        path_prefix = f"/lab-{env_id}-{service_name}"

        labels = {
            "traefik.enable": "true",
            f"traefik.http.routers.{container_name}.rule": f"Host(`{instance.endpoint}`) && PathPrefix(`{path_prefix}`)",
            f"traefik.http.routers.{container_name}.entrypoints": "websecure",
            f"traefik.http.middlewares.{container_name}-strip.stripprefix.prefixes": path_prefix,
            f"traefik.http.routers.{container_name}.middlewares": f"{container_name}-strip",
            f"traefik.http.services.{container_name}.loadbalancer.server.port": str(
                container_port
            ),
        }

        return labels
