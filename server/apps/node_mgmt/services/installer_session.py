from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.crypto.aes_crypto import AESCryptor
from apps.node_mgmt.constants.installer import InstallerConstants
from config.components.nats import NATS_NAMESPACE
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models import SidecarEnv
from apps.node_mgmt.services.install_token import InstallTokenService
from apps.node_mgmt.services.package import PackageService
from apps.node_mgmt.utils.architecture import normalize_cpu_architecture
from apps.node_mgmt.utils.token_auth import generate_node_token


class InstallerSessionService:
    @staticmethod
    def installer_artifact(os_name: str, cpu_architecture: str = "") -> dict:
        normalized_arch = normalize_cpu_architecture(cpu_architecture) or "generic"
        if os_name == NodeConstants.WINDOWS_OS:
            return {
                "filename": InstallerConstants.WINDOWS_INSTALLER_FILENAME,
                "object_key": InstallerConstants.build_latest_alias_path(NodeConstants.WINDOWS_OS, normalized_arch),
                "download_url": f"/api/proxy/node_mgmt/api/installer/windows/download/?arch={normalized_arch}",
                "alias_object_key": InstallerConstants.build_latest_alias_path(NodeConstants.WINDOWS_OS, normalized_arch),
                "version": InstallerConstants.DEFAULT_INSTALLER_VERSION,
                "architecture": normalized_arch,
            }
        if os_name == NodeConstants.LINUX_OS:
            return {
                "filename": InstallerConstants.LINUX_INSTALLER_FILENAME,
                "object_key": InstallerConstants.build_latest_alias_path(NodeConstants.LINUX_OS, normalized_arch),
                "download_url": f"/api/proxy/node_mgmt/api/installer/linux/download/?arch={normalized_arch}",
                "alias_object_key": InstallerConstants.build_latest_alias_path(NodeConstants.LINUX_OS, normalized_arch),
                "version": InstallerConstants.DEFAULT_INSTALLER_VERSION,
                "architecture": normalized_arch,
            }
        raise BaseAppException(f"Unsupported operating system: {os_name}")

    @staticmethod
    def _get_cloud_region_env(cloud_region_id):
        envs = SidecarEnv.objects.filter(cloud_region=cloud_region_id)
        aes_obj = AESCryptor()
        result = {}
        for env in envs:
            if env.type == "secret":
                result[env.key] = aes_obj.decode(env.value)
            else:
                result[env.key] = env.value
        return result

    @staticmethod
    def build_session_config(token: str, cpu_architecture: str = ""):
        token_data = InstallTokenService.validate_and_get_token_data(token)

        resolved_arch = normalize_cpu_architecture(cpu_architecture or token_data.get("cpu_architecture", ""))

        package_obj = PackageService.resolve_package_by_architecture(
            token_data["package_id"],
            resolved_arch,
        )
        if not package_obj:
            raise BaseAppException("Package not found")

        envs = InstallerSessionService._get_cloud_region_env(token_data["cloud_region_id"])
        server_url = envs.get(NodeConstants.SERVER_URL_KEY)
        if not server_url:
            raise BaseAppException(f"Missing NODE_SERVER_URL in cloud region {token_data['cloud_region_id']}")

        nats_servers = envs.get(NodeConstants.NATS_SERVERS_KEY)
        # TODO: temporary fallback for rollout. Split installer direct-download
        # access into a dedicated download-only NATS account/bucket permission
        # model instead of reusing admin credentials.
        nats_username = envs.get("NATS_ADMIN_USERNAME")
        nats_password = envs.get(NodeConstants.NATS_ADMIN_PASSWORD_KEY)
        installer_bucket = NATS_NAMESPACE
        if not nats_servers or not nats_username or not nats_password:
            raise BaseAppException("Missing NATS direct download configuration")

        sidecar_token = generate_node_token(token_data["node_id"], token_data["ip"], token_data["user"])
        groups = ",".join([str(org_id) for org_id in token_data.get("organizations", [])])

        nats_tls_ca = envs.get("NATS_TLS_CA") or ""
        nats_protocol = envs.get("NATS_PROTOCOL") or "nats"

        install_dir = (
            InstallerConstants.WINDOWS_INSTALL_DEFAULT_DIR
            if token_data["os"] == NodeConstants.WINDOWS_OS
            else InstallerConstants.LINUX_INSTALL_DEFAULT_DIR
        )

        config = {
            "api_token": sidecar_token,
            "group_id": groups,
            "install_dir": install_dir,
            "node_id": token_data["node_id"],
            "node_name": token_data["node_name"],
            "os": token_data["os"],
            "cpu_architecture": resolved_arch,
            "remaining_usage": token_data["remaining_usage"],
            "server_url": f"{server_url.rstrip('/')}/api/v1/node_mgmt/open_api/node",
            "storage": {
                "bucket": installer_bucket,
                "file_key": PackageService.build_file_path(package_obj),
                "file_name": package_obj.name,
                "nats_password": nats_password,
                "nats_protocol": nats_protocol,
                "nats_servers": nats_servers,
                "nats_tls_ca": nats_tls_ca,
                "nats_username": nats_username,
            },
            "zone_id": str(token_data["cloud_region_id"]),
        }
        config["installer"] = InstallerSessionService.installer_artifact(
            token_data["os"],
            resolved_arch,
        )
        return config
