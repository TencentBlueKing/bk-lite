"""内置 Linux 补丁源定义与本地数据库初始化。"""

from dataclasses import dataclass

from django.db import transaction

from apps.patch_mgmt.constants import PatchSourceType
from apps.patch_mgmt.models import PatchSource
from apps.patch_mgmt.utils.architecture import X86_64


@dataclass(frozen=True)
class BuiltinPatchSourceDefinition:
    key: str
    name: str
    source_type: str
    url: str
    distro_name: str
    os_version: str
    arch: str = X86_64

    def as_defaults(self) -> dict:
        return {
            "name": self.name,
            "source_type": self.source_type,
            "url": self.url,
            "distro_name": self.distro_name,
            "os_version": self.os_version,
            "arch": self.arch,
            "is_builtin": True,
            "is_enabled": True,
            "team": [],
            "created_by": "system",
            "updated_by": "system",
        }


BUILTIN_PATCH_SOURCES = (
    BuiltinPatchSourceDefinition(
        key="oracle-linux-9-yum-baseos",
        name="Oracle Linux 9 BaseOS (YUM)",
        source_type=PatchSourceType.YUM_REPO,
        url="https://yum.oracle.com/repo/OracleLinux/OL9/baseos/latest/x86_64",
        distro_name="Oracle Linux",
        os_version="9",
    ),
    BuiltinPatchSourceDefinition(
        key="rocky-linux-9-dnf-baseos",
        name="Rocky Linux 9 BaseOS (DNF)",
        source_type=PatchSourceType.DNF_REPO,
        url="https://download.rockylinux.org/pub/rocky/9/BaseOS/x86_64/os",
        distro_name="Rocky Linux",
        os_version="9",
    ),
    BuiltinPatchSourceDefinition(
        key="ubuntu-24-04-apt-main-security",
        name="Ubuntu 24.04 main-security (APT)",
        source_type=PatchSourceType.APT_REPO,
        url="https://security.ubuntu.com/ubuntu",
        distro_name="Ubuntu",
        os_version="24.04",
    ),
)


@transaction.atomic
def initialize_builtin_patch_sources() -> tuple[int, int]:
    """幂等补齐内置源，保留已存在记录的运行期配置。"""
    created = existing = 0
    for definition in BUILTIN_PATCH_SOURCES:
        source, is_created = PatchSource.objects.get_or_create(
            builtin_key=definition.key,
            defaults=definition.as_defaults(),
        )
        if is_created:
            created += 1
            continue
        existing += 1
        if not source.is_builtin:
            source.is_builtin = True
            source.save(update_fields=["is_builtin", "updated_at"])
    return created, existing
