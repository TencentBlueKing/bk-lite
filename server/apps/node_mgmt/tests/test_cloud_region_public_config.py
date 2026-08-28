from pathlib import Path

import pytest

from apps.core.utils.crypto.aes_crypto import AESCryptor
from apps.node_mgmt.models import CloudRegion, SidecarEnv
from apps.node_mgmt.nats import node as node_nats

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_public_config_only_returns_node_server_url():
    region = CloudRegion.objects.create(name="public-config-region")
    SidecarEnv.objects.create(
        cloud_region=region,
        key="NODE_SERVER_URL",
        value="https://node.example.com",
        type="text",
    )
    SidecarEnv.objects.create(
        cloud_region=region,
        key="NATS_PASSWORD",
        value=AESCryptor().encode("region-secret"),
        type="secret",
    )

    result = node_nats.get_cloud_region_public_config(str(region.id))

    assert result == {"NODE_SERVER_URL": "https://node.example.com"}
    assert node_nats.get_cloud_region_envconfig(str(region.id)) == {
        "NODE_SERVER_URL": "https://node.example.com",
        "NATS_PASSWORD": "region-secret",
    }


PUBLIC_CALLERS = {
    "apm/services/integration_configuration.py": (1, 0),
    "cmdb/services/k8s_setup.py": (1, 0),
    "log/services/cloud_region_receiver.py": (1, 0),
    "monitor/services/flow_access_guide.py": (1, 0),
    "monitor/services/manual_collect.py": (1, 0),
    "monitor/services/template_access_guide.py": (1, 0),
}
MIXED_CALLERS = {
    "log/services/k8s_collect.py": (2, 2),
    "monitor/services/k3s_onboarding.py": (1, 1),
}
SENSITIVE_RENDERERS = {
    "cmdb/services/infra.py": (0, 1),
    "monitor/services/infra.py": (0, 1),
}
REGISTERED_CONFIG_CALLERS = PUBLIC_CALLERS | MIXED_CALLERS | SENSITIVE_RENDERERS


@pytest.mark.parametrize(
    ("relative_path", "expected_counts"),
    sorted(REGISTERED_CONFIG_CALLERS.items()),
)
def test_cloud_region_config_callsites_are_split_by_purpose(relative_path, expected_counts):
    apps_dir = Path(__file__).resolve().parents[2]
    source = (apps_dir / relative_path).read_text(encoding="utf-8")

    assert (
        source.count(".get_cloud_region_public_config("),
        source.count(".get_cloud_region_envconfig("),
    ) == expected_counts


def test_no_unregistered_business_caller_reads_full_cloud_region_config():
    apps_dir = Path(__file__).resolve().parents[2]
    full_config_callers = set()
    for app_name in ("apm", "cmdb", "log", "monitor"):
        for source_file in (apps_dir / app_name).rglob("*.py"):
            if "tests" in source_file.parts:
                continue
            source = source_file.read_text(encoding="utf-8")
            if ".get_cloud_region_envconfig(" in source:
                full_config_callers.add(source_file.relative_to(apps_dir).as_posix())

    assert full_config_callers == set(MIXED_CALLERS | SENSITIVE_RENDERERS)
