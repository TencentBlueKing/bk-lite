import json
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from apps.node_mgmt.constants.collector import CollectorConstants
from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models import Collector, Node
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.models.sidecar import CollectorConfiguration
from apps.node_mgmt.services.sidecar import Sidecar

APM_OTEL_DEFINITION = (
    Path(__file__).resolve().parents[1] / "support-files" / "collectors" / "APM-OTEL.json"
)
APM_OTEL_EXECUTABLE_PATH = "/opt/fusion-collectors/bin/bklite-otelcol"
APM_OTEL_QUEUE_DIR = "/opt/fusion-collectors/cache/otelcol/queue"


def _load_apm_otel_collectors():
    collectors = json.loads(APM_OTEL_DEFINITION.read_text())
    assert collectors
    return collectors


def test_apm_otel_collector_json_registers_linux_exec():
    collectors = _load_apm_otel_collectors()
    assert len(collectors) == 1
    assert collectors[0]["id"] == "apm_otel_linux"
    assert collectors[0]["cpu_architecture"] == NodeConstants.X86_64_ARCH
    for collector in collectors:
        nats_config = collector["default_config"]["nats"]
        assert collector["name"] == "APM-OTEL"
        assert collector["package_name"] == "bklite-otelcol"
        assert collector["service_type"] == "exec"
        assert collector["controller_default_run"] is True
        assert collector["executable_path"] == APM_OTEL_EXECUTABLE_PATH
        assert collector["execute_parameters"] == "--config %s"
        assert collector["validation_parameters"] == "validate --config %s"
        assert "apm" in collector["tags"]
        assert "endpoint: 0.0.0.0:4318" in nats_config
        assert f"directory: {APM_OTEL_QUEUE_DIR}" in nats_config
        assert "${env:NATS_ADMIN_PASSWORD}" in nats_config
        assert "subject: apm.traces.${node.cloud_region}" in nats_config
        assert 'cloud_region_id: "${node.cloud_region}"' in nats_config
        assert '{% if NATS_PROTOCOL == "tls" %}' in nats_config


def test_apm_otel_is_default_container_collector():
    assert "APM-OTEL" in CollectorConstants.DEFAULT_CONTAINER_COLLECTOR_CONFIGS
    assert CollectorConstants.TAG_ENUM["apm"] == {"is_app": True, "name": "APM"}


def test_apm_otel_template_keeps_env_password_placeholder():
    rendered = Sidecar.render_template(
        'urls: ["${NATS_PROTOCOL}://${NATS_ADMIN_USERNAME}:${env:NATS_ADMIN_PASSWORD}@${NATS_SERVERS}"]\n'
        "subject: apm.traces.${node.cloud_region}\n",
        {
            "NATS_PROTOCOL": "nats",
            "NATS_ADMIN_USERNAME": "admin",
            "NATS_ADMIN_PASSWORD": "should-not-appear",
            "NATS_SERVERS": "nats.local:4222",
            "node__cloud_region": "9",
        },
    )
    assert "nats://admin:${env:NATS_ADMIN_PASSWORD}@nats.local:4222" in rendered
    assert "should-not-appear" not in rendered
    assert "subject: apm.traces.9" in rendered


def _region():
    return CloudRegion.objects.create(name=f"cr-apm-{uuid.uuid4().hex[:8]}")


def _node(region, **over):
    data = dict(
        id=f"node-apm-{uuid.uuid4().hex[:8]}",
        name="fusion-collector",
        ip="10.9.9.9",
        operating_system="linux",
        collector_configuration_directory="/opt/fusion-collectors/generated",
        cloud_region=region,
        cpu_architecture="x86_64",
    )
    data.update(over)
    return Node.objects.create(**data)


def _apm_collector(suffix):
    nats_config = _load_apm_otel_collectors()[0]["default_config"]["nats"]
    return Collector.objects.create(
        id=f"apm_otel_linux_{suffix}",
        name="APM-OTEL",
        service_type="exec",
        node_operating_system="linux",
        executable_path=APM_OTEL_EXECUTABLE_PATH,
        execute_parameters="--config %s",
        validation_parameters="validate --config %s",
        controller_default_run=True,
        default_config={"nats": nats_config},
        tags=["linux", "apm", "x86_64"],
        package_name="bklite-otelcol",
    )


@pytest.mark.django_db
def test_create_default_config_skips_apm_otel_on_host():
    region = _region()
    node = _node(region)
    collector = _apm_collector("host")
    with (
        patch.object(Sidecar, "_get_default_collectors_for_node", return_value={collector.name: collector}),
        patch.object(Sidecar, "get_cloud_region_envconfig", return_value={"SIDECAR_INPUT_MODE": "nats"}),
    ):
        Sidecar.create_default_config(node, [])
    assert not CollectorConfiguration.objects.filter(collector=collector).exists()


@pytest.mark.django_db
def test_create_default_config_builds_apm_otel_for_container_node():
    region = _region()
    node = _node(region, node_type=ControllerConstants.NODE_TYPE_CONTAINER)
    collector = _apm_collector("ctr")
    with (
        patch.object(Sidecar, "_get_default_collectors_for_node", return_value={collector.name: collector}),
        patch.object(
            Sidecar,
            "get_cloud_region_envconfig",
            return_value={"SIDECAR_INPUT_MODE": "nats", "NATS_PROTOCOL": "nats"},
        ),
    ):
        Sidecar.create_default_config(node, [ControllerConstants.NODE_TYPE_CONTAINER])

    cfg = CollectorConfiguration.objects.get(collector=collector, nodes=node, is_pre=True)
    assert "endpoint: 0.0.0.0:4318" in cfg.config_template
    assert APM_OTEL_QUEUE_DIR in cfg.config_template
    assert "${env:NATS_ADMIN_PASSWORD}" in cfg.config_template
    assert "apm.traces.${node.cloud_region}" in cfg.config_template
