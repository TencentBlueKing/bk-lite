"""达梦 migrate_patch 副本必须和源码迁移保持同一套分页锁逻辑。"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SERVER_ROOT = Path(__file__).resolve().parents[3]
PAIRS = (
    (
        "apps/node_mgmt/migrations/0044_encrypt_installer_passwords.py",
        "migrate_patch/patches/dameng/node_mgmt/0044_encrypt_installer_passwords.py",
    ),
    (
        "apps/node_mgmt/migrations/0046_urldecode_snmp_v3_env_secrets.py",
        "migrate_patch/patches/dameng/node_mgmt/0046_urldecode_snmp_v3_env_secrets.py",
    ),
    (
        "apps/node_mgmt/migrations/0047_urldecode_custom_pull_env_password.py",
        "migrate_patch/patches/dameng/node_mgmt/0047_urldecode_custom_pull_env_password.py",
    ),
    (
        "apps/alerts/migrations/0033_migrate_legacy_match_rules.py",
        "migrate_patch/patches/dameng/alerts/0033_migrate_legacy_match_rules.py",
    ),
)
LOCK_IMPORT = "from apps.core.utils.queryset_lock import list_locked_batch"
PATCH_LOCK_IMPORT = "from migrate_patch.patches.lock_compat import list_locked_batch"


def _normalize(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if line.startswith("# 达梦补丁") or line.startswith("# 原始文件"):
            continue
        lines.append(line.replace(PATCH_LOCK_IMPORT, LOCK_IMPORT))
    return "\n".join(lines).strip() + "\n"


@pytest.mark.parametrize(("source_rel", "patch_rel"), PAIRS)
def test_dameng_lock_migrate_patch_matches_source_migration(source_rel, patch_rel):
    source = _normalize((SERVER_ROOT / source_rel).read_text(encoding="utf-8"))
    patch = _normalize((SERVER_ROOT / patch_rel).read_text(encoding="utf-8"))
    assert patch == source
