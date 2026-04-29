from asgiref.sync import async_to_sync
from django.core.management import BaseCommand, CommandError

from apps.node_mgmt.constants.installer import InstallerConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models import Node, PackageVersion
from apps.node_mgmt.utils.s3 import list_s3_files


class Command(BaseCommand):
    help = "校验多架构安装器/控制器包发布状态，并输出待补齐节点架构情况"

    def add_arguments(self, parser):
        parser.add_argument(
            "--version",
            type=str,
            default="",
            help="指定需要校验的控制器版本；为空时仅校验各架构是否存在至少一个控制器包",
        )

    def handle(self, *args, **options):
        target_version = options["version"]
        object_keys = set(async_to_sync(list_s3_files)())

        required_installer_paths = [
            InstallerConstants.build_latest_alias_path(NodeConstants.WINDOWS_OS, NodeConstants.X86_64_ARCH),
            InstallerConstants.build_latest_alias_path(NodeConstants.LINUX_OS, NodeConstants.X86_64_ARCH),
            InstallerConstants.build_latest_alias_path(NodeConstants.LINUX_OS, NodeConstants.ARM64_ARCH),
        ]

        missing_installer_paths = [path for path in required_installer_paths if path not in object_keys]

        controller_query = PackageVersion.objects.filter(type="controller", os=NodeConstants.LINUX_OS)
        if target_version:
            controller_query = controller_query.filter(version=target_version)

        linux_x86_exists = controller_query.filter(cpu_architecture=NodeConstants.X86_64_ARCH).exists()
        linux_arm_exists = controller_query.filter(cpu_architecture=NodeConstants.ARM64_ARCH).exists()
        missing_nodes_count = Node.objects.filter(cpu_architecture="").count()

        self.stdout.write(self.style.SUCCESS("Architecture rollout verification summary"))
        self.stdout.write(f"- Linux x86_64 controller package present: {'yes' if linux_x86_exists else 'no'}")
        self.stdout.write(f"- Linux ARM64 controller package present: {'yes' if linux_arm_exists else 'no'}")
        self.stdout.write(f"- Nodes missing cpu_architecture: {missing_nodes_count}")

        if missing_installer_paths:
            self.stdout.write(self.style.ERROR("- Missing installer artifacts:"))
            for path in missing_installer_paths:
                self.stdout.write(f"  * {path}")
        else:
            self.stdout.write("- Installer artifacts present for windows/x86_64, linux/x86_64, linux/arm64")

        if target_version:
            self.stdout.write(f"- Verified controller package version: {target_version}")

        failures = []
        if missing_installer_paths:
            failures.append("installer artifacts")
        if not linux_x86_exists:
            failures.append("linux x86_64 controller package")
        if not linux_arm_exists:
            failures.append("linux arm64 controller package")

        if failures:
            raise CommandError(f"Architecture rollout verification failed: missing {', '.join(failures)}")
