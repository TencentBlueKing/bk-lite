import shlex

from asgiref.sync import async_to_sync
from django.db.models import Q

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.crypto.aes_crypto import AESCryptor
from apps.node_mgmt.constants.database import DatabaseConstants
from apps.node_mgmt.constants.installer import InstallerConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models import Node, PackageVersion, SidecarEnv
from apps.node_mgmt.models.installer import CollectorTask, CollectorTaskNode, ControllerTask, ControllerTaskNode
from apps.node_mgmt.services.install_token import InstallTokenService
from apps.node_mgmt.services.installer_session import InstallerSessionService
from apps.node_mgmt.services.package import PackageService
from apps.node_mgmt.utils.architecture import normalize_cpu_architecture
from apps.node_mgmt.utils.s3 import download_file_by_s3
from apps.node_mgmt.utils.task_result_schema import normalize_task_result_for_read


class InstallerService:
    AUTO_INSTALL_MODE = "auto"
    MANUAL_INSTALL_MODE = "manual"

    @staticmethod
    def normalize_required_cpu_architecture(os_name: str, cpu_architecture: str) -> str:
        normalized_arch = normalize_cpu_architecture(cpu_architecture)
        if not normalized_arch:
            raise BaseAppException(f"Missing or unsupported CPU architecture for os={os_name}")

        if os_name == NodeConstants.WINDOWS_OS and normalized_arch != NodeConstants.X86_64_ARCH:
            raise BaseAppException(f"Unsupported CPU architecture for os={os_name}: {normalized_arch}")

        return normalized_arch

    @staticmethod
    def resolve_package_by_architecture(package_seed_id: int, cpu_architecture: str) -> PackageVersion:
        package_obj = PackageService.resolve_package_by_architecture(package_seed_id, cpu_architecture)
        if not package_obj:
            raise BaseAppException("Package version not found")
        normalized_arch = normalize_cpu_architecture(cpu_architecture)
        is_legacy_x86_controller = (
            not package_obj.cpu_architecture
            and normalized_arch == NodeConstants.X86_64_ARCH
            and package_obj.type == "controller"
            and package_obj.object == "Controller"
        )
        if package_obj.cpu_architecture == normalized_arch or not normalized_arch or is_legacy_x86_controller:
            return package_obj
        raise BaseAppException(
            f"No package found for os={package_obj.os}, object={package_obj.object}, version={package_obj.version}, arch={normalized_arch}"
        )

    @staticmethod
    def installer_metadata(target_os: str, cpu_architecture: str = "") -> dict:
        if target_os not in {NodeConstants.WINDOWS_OS, NodeConstants.LINUX_OS}:
            raise BaseAppException(f"Unsupported operating system: {target_os}")
        normalized_arch = normalize_cpu_architecture(cpu_architecture)
        return {
            "os": target_os,
            "cpu_architecture": normalized_arch,
            **InstallerSessionService.installer_artifact(target_os, normalized_arch),
        }

    @staticmethod
    def installer_manifest() -> dict:
        return {
            "default_version": InstallerConstants.DEFAULT_INSTALLER_VERSION,
            "artifacts": {
                NodeConstants.WINDOWS_OS: {
                    NodeConstants.X86_64_ARCH: InstallerService.installer_metadata(NodeConstants.WINDOWS_OS, NodeConstants.X86_64_ARCH)
                },
                NodeConstants.LINUX_OS: {
                    NodeConstants.X86_64_ARCH: InstallerService.installer_metadata(NodeConstants.LINUX_OS, NodeConstants.X86_64_ARCH),
                    NodeConstants.ARM64_ARCH: InstallerService.installer_metadata(NodeConstants.LINUX_OS, NodeConstants.ARM64_ARCH),
                },
            },
        }

    @staticmethod
    def get_install_command(
        user,
        ip,
        node_id,
        os,
        package_id,
        cloud_region_id,
        organizations,
        node_name,
        install_mode=MANUAL_INSTALL_MODE,
        cpu_architecture: str = "",
    ):
        """
        获取安装命令（生成包含临时 token 的 curl 命令）

        :param user: 用户名
        :param ip: 节点IP
        :param node_id: 节点ID
        :param os: 操作系统
        :param package_id: 安装包ID
        :param cloud_region_id: 云区域ID
        :param organizations: 组织列表
        :param node_name: 节点名称
        :return: curl 命令字符串
        """
        # 从云区域环境变量中获取服务器地址
        normalized_arch = InstallerService.normalize_required_cpu_architecture(os, cpu_architecture)

        objs = SidecarEnv.objects.filter(cloud_region=cloud_region_id)
        server_url = None
        for obj in objs:
            if obj.key == NodeConstants.SERVER_URL_KEY:
                server_url = obj.value
                break

        if not server_url:
            raise BaseAppException(f"Missing NODE_SERVER_URL in cloud region {cloud_region_id}")

        # 生成限时令牌（30分钟有效，最多使用5次）
        token = InstallTokenService.generate_install_token(
            node_id=node_id,
            ip=ip,
            user=user,
            os=os,
            package_id=package_id,
            cloud_region_id=cloud_region_id,
            organizations=organizations,
            node_name=node_name,
            cpu_architecture=normalized_arch,
        )

        # 根据操作系统生成不同的安装命令
        if os == NodeConstants.LINUX_OS:
            install_command = InstallerService.get_linux_bootstrap_command(token, install_mode=install_mode)
        elif os == NodeConstants.WINDOWS_OS:
            # Windows: 返回新的 OpenAPI 接口地址，不走 webhook
            # 客户端直接调用此接口获取 JSON 配置信息
            install_command = f"{server_url.rstrip('/')}/api/v1/node_mgmt/open_api/installer/session?token={token}"
        else:
            raise BaseAppException(f"Unsupported operating system: {os}")

        return install_command

    @staticmethod
    def install_controller(
        cloud_region_id,
        work_node,
        package_version_id,
        nodes,
        cpu_architecture: str,
        created_by: str = "",
        domain: str = "domain.com",
    ):
        """安装控制器"""
        task_obj = ControllerTask.objects.create(
            cloud_region_id=cloud_region_id,
            work_node=work_node,
            package_version_id=package_version_id,
            type="install",
            status="waiting",
            created_by=created_by,
            updated_by=created_by,
            domain=domain,
            updated_by_domain=domain,
        )
        creates = []
        aes_obj = AESCryptor()
        for node in nodes:
            normalized_arch = InstallerService.normalize_required_cpu_architecture(
                node["os"],
                node.get("cpu_architecture") or cpu_architecture,
            )
            # 加密密码（如果有）
            password = aes_obj.encode(node["password"]) if node.get("password") else ""
            # 加密私钥（如果有）
            private_key = aes_obj.encode(node["private_key"]) if node.get("private_key") else ""
            # 加密密码短语（如果有）
            passphrase = aes_obj.encode(node["passphrase"]) if node.get("passphrase") else ""

            creates.append(
                ControllerTaskNode(
                    task_id=task_obj.id,
                    node_id=node.get("node_id", ""),
                    ip=node["ip"],
                    node_name=node["node_name"],
                    os=node["os"],
                    cpu_architecture=normalized_arch,
                    organizations=node["organizations"],
                    port=node["port"],
                    username=node["username"],
                    password=password,
                    private_key=private_key,
                    passphrase=passphrase,
                    status="waiting",
                )
            )
        ControllerTaskNode.objects.bulk_create(creates, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)
        return task_obj.id

    @staticmethod
    # 获取手动安装节点状态
    def get_manual_install_status(nodes):
        """获取手动安装节点状态"""
        exists_id = Node.objects.filter(id__in=nodes).values("id")
        exists_id_set = set([item["id"] for item in exists_id])
        result = []
        for node_id in nodes:
            info = {"node_id": node_id, "status": ""}
            if node_id in exists_id_set:
                info["status"] = "installed"
                result.append(info)
            else:
                info["status"] = "waiting"
                result.append(info)
        return result

    @staticmethod
    def uninstall_controller(
        cloud_region_id,
        work_node,
        nodes,
        created_by: str = "",
        domain: str = "domain.com",
    ):
        """卸载控制器"""
        task_obj = ControllerTask.objects.create(
            cloud_region_id=cloud_region_id,
            work_node=work_node,
            type="uninstall",
            status="waiting",
            created_by=created_by,
            updated_by=created_by,
            domain=domain,
            updated_by_domain=domain,
        )
        creates = []
        aes_obj = AESCryptor()
        for node in nodes:
            # 加密密码（如果有）
            password = aes_obj.encode(node["password"]) if node.get("password") else ""
            # 加密私钥（如果有）
            private_key = aes_obj.encode(node["private_key"]) if node.get("private_key") else ""
            # 加密密码短语（如果有）
            passphrase = aes_obj.encode(node["passphrase"]) if node.get("passphrase") else ""

            creates.append(
                ControllerTaskNode(
                    task_id=task_obj.id,
                    node_id=node.get("node_id", ""),
                    ip=node["ip"],
                    os=node["os"],
                    cpu_architecture=node.get("cpu_architecture", ""),
                    port=node["port"],
                    username=node["username"],
                    password=password,
                    private_key=private_key,
                    passphrase=passphrase,
                    status="waiting",
                )
            )
        ControllerTaskNode.objects.bulk_create(creates, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)
        return task_obj.id

    @staticmethod
    def get_authorized_controller_task_node_queryset(task_id, authorized_nodes=None, request_user=None):
        task_nodes = ControllerTaskNode.objects.filter(task_id=task_id).select_related("task").order_by("id")
        if authorized_nodes is not None and not getattr(request_user, "is_superuser", False):
            authorized_node_ids = list(authorized_nodes.values_list("id", flat=True))
            username = getattr(request_user, "username", "") if request_user is not None else ""
            domain = getattr(request_user, "domain", "") if request_user is not None else ""
            legacy_owner_filter = Q(pk__in=[])
            if username and domain:
                legacy_owner_filter = Q(node_id="") & Q(task__created_by=username, task__domain=domain)
            task_nodes = task_nodes.filter(
                (~Q(node_id="") & Q(node_id__in=authorized_node_ids)) | legacy_owner_filter
            )
        return task_nodes

    @staticmethod
    def install_controller_nodes(task_id, authorized_nodes=None, request_user=None):
        """获取控制器安装节点信息"""
        task_nodes = InstallerService.get_authorized_controller_task_node_queryset(
            task_id,
            authorized_nodes=authorized_nodes,
            request_user=request_user,
        )

        result = []
        for task_node in task_nodes:
            result.append(
                dict(
                    task_node_id=task_node.id,
                    node_id=task_node.node_id,
                    ip=task_node.ip,
                    os=task_node.os,
                    cpu_architecture=task_node.cpu_architecture,
                    node_name=task_node.node_name,
                    organizations=task_node.organizations,
                    username=task_node.username,
                    port=task_node.port,
                    status=task_node.status,
                    result=normalize_task_result_for_read(task_node.result),
                )
            )
        return result

    @staticmethod
    def install_collector(collector_package, nodes):
        """安装采集器"""
        task_obj = CollectorTask.objects.create(
            type="install",
            status="waiting",
            package_version_id=collector_package,
        )
        creates = []
        for node_id in nodes:
            creates.append(
                CollectorTaskNode(
                    task_id=task_obj.id,
                    node_id=node_id,
                    status="waiting",
                )
            )
        CollectorTaskNode.objects.bulk_create(creates, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)
        return task_obj.id

    @staticmethod
    def install_collector_nodes(task_id):
        """获取采集器安装节点信息"""
        task_nodes = CollectorTaskNode.objects.filter(task_id=task_id).select_related("node")
        result = []
        for task_node in task_nodes:
            result.append(
                dict(
                    node_id=task_node.node_id,
                    status=task_node.status,
                    result=normalize_task_result_for_read(task_node.result),
                    ip=task_node.node.ip,
                    os=task_node.node.operating_system,
                    # organizations=task_node.node.nodeorganization_set.values_list("organization", flat=True),
                )
            )
        return result

    @staticmethod
    def download_windows_installer(cpu_architecture: str = ""):
        installer = InstallerSessionService.installer_artifact(NodeConstants.WINDOWS_OS, cpu_architecture)
        return async_to_sync(download_file_by_s3)(installer["object_key"])

    @staticmethod
    def download_linux_installer(cpu_architecture: str = ""):
        installer = InstallerSessionService.installer_artifact(NodeConstants.LINUX_OS, cpu_architecture)
        return async_to_sync(download_file_by_s3)(installer["object_key"])

    @staticmethod
    def get_linux_bootstrap_command(token: str, install_mode: str = MANUAL_INSTALL_MODE) -> str:
        session = InstallerSessionService.build_session_config(token)
        server_url = session["server_url"].replace("/api/v1/node_mgmt/open_api/node", "")
        bootstrap_url = f"{server_url}/api/v1/node_mgmt/open_api/installer/linux_bootstrap?token={token}"
        quoted_bootstrap_url = shlex.quote(bootstrap_url)

        shell_detection = (
            'if command -v sh >/dev/null 2>&1; then bootstrap_shell="$(command -v sh)"; '
            'elif command -v bash >/dev/null 2>&1; then bootstrap_shell="$(command -v bash)"; '
            "else echo 'Error: controller installation requires sh or bash' >&2; exit 1; fi; "
        )

        if install_mode == InstallerService.AUTO_INSTALL_MODE:
            privilege_detection = (
                'if [ "$(id -u)" -eq 0 ]; then '
                "bootstrap_privilege=root; "
                "elif command -v sudo >/dev/null 2>&1; then "
                'if sudo -n "$bootstrap_shell" -c true >/dev/null 2>&1; then bootstrap_privilege=sudo_non_interactive; '
                "else echo 'Error: automatic installation requires root or passwordless sudo for the current user'; exit 1; fi; "
                "else echo 'Error: root or sudo is required to install controller'; exit 1; fi; "
            )
        else:
            privilege_detection = (
                'if [ "$(id -u)" -eq 0 ]; then '
                "bootstrap_privilege=root; "
                "elif command -v sudo >/dev/null 2>&1; then bootstrap_privilege=sudo_interactive; "
                "else echo 'Error: root or sudo is required to install controller'; exit 1; fi; "
            )

        return (
            f"{shell_detection}{privilege_detection}"
            'umask 077; bootstrap_file="$(mktemp)" || exit 1; '
            'cleanup_bootstrap() { rm -f "$bootstrap_file"; }; '
            "trap cleanup_bootstrap 0; trap 'exit 1' 1 2 15; "
            f'curl -fsSLk {quoted_bootstrap_url} -o "$bootstrap_file" || exit 1; '
            "bootstrap_status=0; "
            'if [ "$bootstrap_privilege" = root ]; then "$bootstrap_shell" "$bootstrap_file" || bootstrap_status=$?; '
            'elif [ "$bootstrap_privilege" = sudo_non_interactive ]; then '
            'sudo -n "$bootstrap_shell" "$bootstrap_file" || bootstrap_status=$?; '
            'else sudo "$bootstrap_shell" "$bootstrap_file" || bootstrap_status=$?; fi; '
            'exit "$bootstrap_status"'
        )
