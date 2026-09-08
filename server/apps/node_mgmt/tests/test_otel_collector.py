import json
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from apps.node_mgmt.constants.collector import CollectorConstants
from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models import Collector, Node
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.models.sidecar import CollectorConfiguration
from apps.node_mgmt.services.sidecar import Sidecar

COLLECTOR_DIR = Path(__file__).resolve().parents[1] / "support-files" / "collectors"
OTEL_DEFINITION = COLLECTOR_DIR / "OTel-Collector.json"
OTEL_EXECUTABLE_PATH = "/opt/fusion-collectors/bin/bklite-otelcol"
OTEL_QUEUE_DIR = "/opt/fusion-collectors/cache/apm-queue"
LANGUAGE_DIR = Path(__file__).resolve().parents[1] / "language"


def _load_otel_collectors():
    collectors = json.loads(OTEL_DEFINITION.read_text())
    assert collectors
    return collectors


def test_community_keeps_single_x86_otel_collector():
    collectors = _load_otel_collectors()
    assert len(collectors) == 1
    assert not (COLLECTOR_DIR / "APM-OTEL.json").exists()

    collector = collectors[0]
    nats_config = collector["default_config"]["nats"]
    assert collector["id"] == "otelcollector_linux"
    assert collector["name"] == "OTel-Collector"
    assert collector["cpu_architecture"] == NodeConstants.X86_64_ARCH
    assert collector["package_name"] == "bklite-otelcol"
    assert collector["service_type"] == "exec"
    assert collector["controller_default_run"] is True
    assert collector["executable_path"] == OTEL_EXECUTABLE_PATH
    assert collector["execute_parameters"] == "--config %s"
    assert "apm" in collector["tags"]
    assert "arm64" not in collector["tags"]
    assert "endpoint: 0.0.0.0:4318" in nats_config
    assert f"directory: {OTEL_QUEUE_DIR}" in nats_config
    assert "${NATS_USERNAME}" in nats_config
    assert "${env:NATS_PASSWORD}" in nats_config
    assert "NATS_ADMIN" not in nats_config
    assert "subject: apm.traces.${node.cloud_region}" in nats_config
    assert 'cloud_region_id: "${node.cloud_region}"' in nats_config
    assert '{% if NATS_PROTOCOL == "tls" %}' in nats_config


def test_otel_is_the_only_default_container_trace_collector():
    assert "OTel-Collector" in CollectorConstants.DEFAULT_CONTAINER_COLLECTOR_CONFIGS
    assert "APM-OTEL" not in CollectorConstants.DEFAULT_CONTAINER_COLLECTOR_CONFIGS
    assert CollectorConstants.TAG_ENUM["apm"] == {"is_app": True, "name": "APM"}


def test_otel_language_covers_community_collector_id():
    zh = yaml.safe_load((LANGUAGE_DIR / "zh-Hans.yaml").read_text())
    en = yaml.safe_load((LANGUAGE_DIR / "en.yaml").read_text())
    assert zh["collector"]["otelcollector_linux"]["name"] == "OTel Collector"
    assert "区域" in zh["collector"]["otelcollector_linux"]["description"]
    assert en["collector"]["otelcollector_linux"]["name"] == "OTel Collector"
    assert "apm.traces" in en["collector"]["otelcollector_linux"]["description"]
    assert "apm_otel_linux" not in zh["collector"]
    assert "apm_otel_linux" not in en["collector"]
    assert zh["collector_tag"]["apm"] == "APM"
    assert en["collector_tag"]["apm"] == "APM"


def test_otel_template_keeps_env_password_placeholder():
    rendered = Sidecar.render_template(
        'urls: ["${NATS_PROTOCOL}://${NATS_USERNAME}:${env:NATS_PASSWORD}@${NATS_SERVERS}"]\n'
        "subject: apm.traces.${node.cloud_region}\n",
        {
            "NATS_PROTOCOL": "nats",
            "NATS_USERNAME": "region",
            "NATS_PASSWORD": "should-not-appear",
            "NATS_SERVERS": "nats.local:4222",
            "node__cloud_region": "9",
        },
    )
    assert "nats://region:${env:NATS_PASSWORD}@nats.local:4222" in rendered
    assert "should-not-appear" not in rendered
    assert "subject: apm.traces.9" in rendered


def _region():
    return CloudRegion.objects.create(name=f"cr-otel-{uuid.uuid4().hex[:8]}")


def _node(region, **over):
    data = dict(
        id=f"node-otel-{uuid.uuid4().hex[:8]}",
        name="fusion-collector",
        ip="10.9.9.9",
        operating_system="linux",
        collector_configuration_directory="/opt/fusion-collectors/generated",
        cloud_region=region,
        cpu_architecture="x86_64",
    )
    data.update(over)
    return Node.objects.create(**data)


def _otel_collector(suffix):
    nats_config = _load_otel_collectors()[0]["default_config"]["nats"]
    return Collector.objects.create(
        id=f"otelcollector_linux_{suffix}",
        name="OTel-Collector",
        service_type="exec",
        node_operating_system="linux",
        executable_path=OTEL_EXECUTABLE_PATH,
        execute_parameters="--config %s",
        validation_parameters="",
        controller_default_run=True,
        default_config={"nats": nats_config},
        tags=["linux", "apm", "x86_64"],
        package_name="bklite-otelcol",
    )


@pytest.mark.django_db
def test_create_default_config_skips_otel_on_host():
    region = _region()
    node = _node(region)
    collector = _otel_collector("host")
    with (
        patch.object(Sidecar, "_get_default_collectors_for_node", return_value={collector.name: collector}),
        patch.object(Sidecar, "get_cloud_region_envconfig", return_value={"SIDECAR_INPUT_MODE": "nats"}),
    ):
        Sidecar.create_default_config(node, [])
    assert not CollectorConfiguration.objects.filter(collector=collector).exists()


@pytest.mark.django_db
def test_create_default_config_builds_otel_for_container_node():
    region = _region()
    node = _node(region, node_type=ControllerConstants.NODE_TYPE_CONTAINER)
    collector = _otel_collector("ctr")
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
    assert OTEL_QUEUE_DIR in cfg.config_template
    assert "${env:NATS_PASSWORD}" in cfg.config_template
    assert "apm.traces.${node.cloud_region}" in cfg.config_template
    assert "NATS_ADMIN" not in cfg.config_template
