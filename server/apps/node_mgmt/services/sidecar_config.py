import logging

import yaml

from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models.sidecar import Node
from apps.rpc.executor import Executor

logger = logging.getLogger("node_mgmt")


class SidecarConfigService:
    @classmethod
    def _get_config_path(cls, node: Node) -> str:
        os_type = node.operating_system or NodeConstants.LINUX_OS
        return ControllerConstants.SIDECAR_CONFIG_PATH.get(
            os_type, ControllerConstants.SIDECAR_CONFIG_PATH[NodeConstants.LINUX_OS]
        )

    @classmethod
    def _get_restart_command(cls, node: Node) -> tuple[str, str | None]:
        os_type = node.operating_system or NodeConstants.LINUX_OS
        return ControllerConstants.SIDECAR_RESTART_CMD.get(
            os_type, ControllerConstants.SIDECAR_RESTART_CMD[NodeConstants.LINUX_OS]
        )

    @classmethod
    def _read_config(cls, node: Node) -> dict:
        """
        读取节点当前 sidecar.yaml 配置内容

        Returns:
            解析后的配置字典

        Raises:
            ValueError: 读取失败或解析失败
        """
        config_path = cls._get_config_path(node)
        executor = Executor(node.id)

        if node.operating_system == NodeConstants.WINDOWS_OS:
            command = f"Get-Content -Path '{config_path}' -Raw"
            shell = "powershell"
        else:
            command = f"cat {config_path}"
            shell = None

        result = executor.execute_local(command, timeout=30, shell=shell)

        if not result.get("success", False):
            error_msg = result.get("error", "Unknown error")
            stderr = result.get("stderr", "")
            if "No such file" in stderr or "not exist" in stderr.lower():
                raise ValueError(f"Configuration file not found: {config_path}")
            if "Permission denied" in stderr or "access" in stderr.lower():
                raise ValueError(f"Permission denied reading config: {config_path}")
            raise ValueError(f"Failed to read config: {error_msg} - {stderr}")

        content = result.get("stdout", "")
        if not content.strip():
            raise ValueError(f"Configuration file is empty: {config_path}")

        try:
            return yaml.safe_load(content)
        except yaml.YAMLError as e:
            raise ValueError(f"Failed to parse YAML config: {e}")

    @classmethod
    def _write_config(cls, node: Node, config: dict) -> None:
        """
        写入配置到节点 sidecar.yaml

        Raises:
            ValueError: 写入失败
        """
        config_path = cls._get_config_path(node)
        executor = Executor(node.id)

        config_content = yaml.safe_dump(
            config, default_flow_style=False, allow_unicode=True
        )

        if node.operating_system == NodeConstants.WINDOWS_OS:
            escaped_content = config_content.replace("'", "''")
            command = f"Set-Content -Path '{config_path}' -Value '{escaped_content}'"
            shell = "powershell"
        else:
            command = f"cat > {config_path} << 'EOF'\n{config_content}EOF"
            shell = "bash"

        result = executor.execute_local(command, timeout=30, shell=shell)

        if not result.get("success", False):
            error_msg = result.get("error", "Unknown error")
            stderr = result.get("stderr", "")
            if "Permission denied" in stderr or "access" in stderr.lower():
                raise ValueError(f"Permission denied writing config: {config_path}")
            raise ValueError(f"Failed to write config: {error_msg} - {stderr}")

    @classmethod
    def _restart_service(cls, node: Node) -> None:
        """
        重启 sidecar 服务

        Raises:
            ValueError: 重启失败
        """
        restart_cmd, shell = cls._get_restart_command(node)
        executor = Executor(node.id)

        result = executor.execute_local(restart_cmd, timeout=60, shell=shell)

        if not result.get("success", False):
            error_msg = result.get("error", "Unknown error")
            stderr = result.get("stderr", "")
            raise ValueError(
                f"Config updated but service restart failed: {error_msg} - {stderr}"
            )

    @classmethod
    def _deep_merge(cls, base: dict, updates: dict) -> dict:
        """
        深度合并两个字典，updates 中的值覆盖 base 中的值

        Args:
            base: 基础字典
            updates: 更新字典

        Returns:
            合并后的新字典
        """
        result = base.copy()
        for key, value in updates.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = cls._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    @classmethod
    def update_config(cls, node_id: str, config_updates: dict) -> dict:
        """
        更新节点 sidecar 配置

        流程：读取原配置 → 深度合并 → 写回 → 重启服务

        Args:
            node_id: 节点 ID
            config_updates: 要更新的配置项

        Returns:
            更新后的完整配置

        Raises:
            ValueError: 节点不存在或操作失败
        """
        try:
            node = Node.objects.get(id=node_id)
        except Node.DoesNotExist:
            raise ValueError(f"Node not found: {node_id}")

        current_config = cls._read_config(node)

        new_config = cls._deep_merge(current_config, config_updates)

        cls._write_config(node, new_config)

        cls._restart_service(node)

        logger.info(f"Sidecar config updated for node {node_id}")
        return new_config

    @classmethod
    def sync_node_properties(
        cls, node: Node, name: str | None = None, organizations: list[str] | None = None
    ) -> None:
        """
        同步节点名称和/或组织到远程节点的 sidecar.yaml

        当用户在 UI 编辑节点名称或组织时调用此方法，将变更同步到节点配置文件。
        组织通过 tags 字段同步，格式为 "group:<organization_id>"。

        Args:
            node: 节点对象
            name: 新的节点名称（可选）
            organizations: 新的组织 ID 列表（可选）

        Raises:
            ValueError: 读取/写入配置失败或重启服务失败
        """
        if name is None and organizations is None:
            return

        try:
            current_config = cls._read_config(node)
        except ValueError as e:
            logger.warning(f"Failed to read sidecar config for node {node.id}: {e}")
            raise

        if name is not None:
            current_config["node_name"] = name

        if organizations is not None:
            current_tags = current_config.get("tags", [])
            group_prefix = f"{ControllerConstants.GROUP_TAG}:"
            non_group_tags = [t for t in current_tags if not t.startswith(group_prefix)]
            new_group_tags = [f"{group_prefix}{org}" for org in organizations]
            current_config["tags"] = non_group_tags + new_group_tags

        cls._write_config(node, current_config)
        cls._restart_service(node)

        logger.info(
            f"Synced node properties to sidecar config for node {node.id}: "
            f"name={name}, organizations={organizations}"
        )
