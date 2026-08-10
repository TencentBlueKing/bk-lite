"""补齐节点文件存储和默认云区域初始化的公共契约。"""

import io

import pytest

from apps.core.utils.crypto.aes_crypto import AESCryptor
from apps.node_mgmt.constants.cloudregion_service import (
    CloudRegionServiceConstants,
)
from apps.node_mgmt.constants.database import (
    CloudRegionConstants,
    EnvVariableConstants,
)
from apps.node_mgmt.management.services.node_init.cloud_init import cloud_init
from apps.node_mgmt.models.cloud_region import (
    CloudRegion,
    CloudRegionService,
    SidecarEnv,
)
from apps.node_mgmt.utils import s3


pytestmark = pytest.mark.unit


class _FakeJetStream:
    instances = []

    def __init__(self):
        self.calls = []
        self.closed = False
        self.__class__.instances.append(self)

    async def connect(self):
        self.calls.append(("connect",))

    async def close(self):
        self.closed = True
        self.calls.append(("close",))

    async def put(self, path, stream, description):
        self.calls.append(("put", path, stream.read(), description))

    async def get(self, path):
        self.calls.append(("get", path))
        return b"payload", "agent.tar.gz"

    async def get_streaming(self, path, chunk_size):
        self.calls.append(("get_streaming", path, chunk_size))
        yield b"first", "agent.tar.gz", 11
        yield b"second", "agent.tar.gz", 11

    async def delete(self, path):
        self.calls.append(("delete", path))

    async def list_objects(self):
        self.calls.append(("list_objects",))
        return [{"name": "agent.tar.gz", "size": 11}]


@pytest.fixture
def fake_jetstream(monkeypatch):
    _FakeJetStream.instances.clear()
    monkeypatch.setattr(s3, "JetStreamService", _FakeJetStream)
    return _FakeJetStream.instances


@pytest.mark.asyncio
async def test_storage_upload_rewinds_wrapped_file_and_preserves_its_name(
    fake_jetstream,
):
    stream = io.BytesIO(b"agent payload")
    stream.read(5)

    class Upload:
        name = "agent.tar.gz"
        file = stream

        def open(self, mode):
            assert mode == "rb"

    await s3.upload_file_to_s3(Upload(), "packages/linux/agent.tar.gz")

    assert fake_jetstream[0].calls == [
        ("connect",),
        (
            "put",
            "packages/linux/agent.tar.gz",
            b"agent payload",
            "agent.tar.gz",
        ),
        ("close",),
    ]


@pytest.mark.asyncio
async def test_storage_download_delete_and_listing_close_their_connections(
    fake_jetstream,
):
    assert await s3.download_file_by_s3("packages/agent") == (
        b"payload",
        "agent.tar.gz",
    )
    await s3.delete_s3_file("packages/agent")
    assert await s3.list_s3_files() == [
        {"name": "agent.tar.gz", "size": 11}
    ]

    assert [instance.calls for instance in fake_jetstream] == [
        [("connect",), ("get", "packages/agent"), ("close",)],
        [("connect",), ("delete", "packages/agent"), ("close",)],
        [("connect",), ("list_objects",), ("close",)],
    ]


@pytest.mark.asyncio
async def test_streaming_download_yields_all_chunks_and_closes_on_early_exit(
    fake_jetstream,
):
    chunks = []
    stream = s3.stream_download_file_by_s3("packages/agent", chunk_size=4)
    async for chunk in stream:
        chunks.append(chunk)
        break
    await stream.aclose()

    assert chunks == [(b"first", "agent.tar.gz", 11)]
    assert fake_jetstream[0].calls == [
        ("connect",),
        ("get_streaming", "packages/agent", 4),
        ("close",),
    ]


@pytest.mark.django_db
def test_cloud_init_is_idempotent_and_classifies_environment_values(
    monkeypatch,
):
    monkeypatch.setenv("DEFAULT_ZONE_VAR_TDD_NORMAL", "plain")
    monkeypatch.setenv("DEFAULT_ZONE_VAR_TDD_PASSWORD", "secret-value")
    monkeypatch.setenv("DEFAULT_ZONE_VAR_NATS_TLS_CA", "certificate")

    cloud_init()
    monkeypatch.setenv("DEFAULT_ZONE_VAR_TDD_NORMAL", "updated-plain")
    monkeypatch.setenv("DEFAULT_ZONE_VAR_TDD_PASSWORD", "updated-secret")
    cloud_init()

    region = CloudRegion.objects.get(
        pk=CloudRegionConstants.DEFAULT_CLOUD_REGION_ID
    )
    assert region.name == CloudRegionConstants.DEFAULT_CLOUD_REGION_NAME
    services = CloudRegionService.objects.filter(cloud_region=region)
    assert set(services.values_list("name", flat=True)) == set(
        CloudRegionServiceConstants.SERVICES
    )
    assert services.filter(
        status=CloudRegionServiceConstants.NORMAL,
        deployed_status=CloudRegionServiceConstants.DEPLOYED,
    ).count() == len(CloudRegionServiceConstants.SERVICES)

    values = {
        item.key: item
        for item in SidecarEnv.objects.filter(
            cloud_region=region,
            key__in=["TDD_NORMAL", "TDD_PASSWORD", "NATS_TLS_CA"],
        )
    }
    assert values["TDD_NORMAL"].value == "updated-plain"
    assert values["TDD_NORMAL"].type == EnvVariableConstants.TYPE_NORMAL
    assert values["NATS_TLS_CA"].type == EnvVariableConstants.TYPE_TEXT
    assert values["TDD_PASSWORD"].type == EnvVariableConstants.TYPE_SECRET
    assert (
        AESCryptor().decode(values["TDD_PASSWORD"].value) == "updated-secret"
    )
