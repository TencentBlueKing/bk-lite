"""同一套 NATS 上，不同节点的执行器不能共用任务 stream 和 consumer。"""

from types import SimpleNamespace

import pytest
from core.config import load_config
from nats.js.api import ConsumerInfo
from nats.js.errors import NotFoundError
from service.nats_topology_service import NATSTopologyMixin


def _tokens(subject):
    return subject.split(".")


def _subjects_overlap(left, right):
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    for index in range(max(len(left_tokens), len(right_tokens))):
        if index >= len(left_tokens) or index >= len(right_tokens):
            return False
        left_token = left_tokens[index]
        right_token = right_tokens[index]
        if left_token == ">" or right_token == ">":
            return True
        if left_token != right_token and left_token != "*" and right_token != "*":
            return False
    return True


class SharedJetStream:
    """只实现拓扑声明会调用的 JetStream 方法，并保留 subject 重叠语义。"""

    def __init__(self):
        self.streams = {}
        self.consumers = {}
        self.subscriptions = []

    async def find_stream_name_by_subject(self, subject):
        for name, config in self.streams.items():
            if any(_subjects_overlap(subject, existing) for existing in config.subjects):
                return name
        raise NotFoundError(code=404, description="stream not found")

    async def stream_info(self, name):
        if name not in self.streams:
            raise NotFoundError(code=404, description="stream not found")
        return self.streams[name]

    async def add_stream(self, config):
        for name, existing in self.streams.items():
            if name == config.name:
                continue
            if any(_subjects_overlap(subject, owned) for subject in config.subjects for owned in existing.subjects):
                raise RuntimeError(f"subjects overlap with stream {name}")
        self.streams[config.name] = config
        return config

    async def update_stream(self, config):
        if config.name not in self.streams:
            raise NotFoundError(code=404, description="stream not found")
        await self.add_stream(config)
        return config

    async def consumers_info(self, stream):
        return [ConsumerInfo(name=name, stream_name=stream, config=config) for (owner, name), config in self.consumers.items() if owner == stream]

    async def consumer_info(self, stream, durable):
        if (stream, durable) not in self.consumers:
            raise NotFoundError(code=404, description="consumer not found")
        return self.consumers[(stream, durable)]

    async def delete_consumer(self, stream, durable):
        self.consumers.pop((stream, durable), None)

    async def add_consumer(self, stream, config):
        self.consumers[(stream, config.durable_name)] = config
        return config

    async def pull_subscribe(self, subject, durable, stream):
        self.subscriptions.append((subject, durable, stream))
        return SimpleNamespace(subject=subject, durable=durable, stream=stream)


class _TopologyService(NATSTopologyMixin):
    def __init__(self, config, jetstream):
        self.config = config
        self.js = jetstream


def _config(tmp_path, node_id, namespace, dlq_subject=None):
    path = tmp_path / f"{node_id}.yml"
    path.write_text(
        "\n".join(
            [
                "nats:",
                "  servers:",
                "    - nats://127.0.0.1:4222",
                f"  instance_id: {node_id}",
                "jetstream:",
                f"  namespace: {namespace}",
                f"  dlq_subject: {dlq_subject or f'{namespace}.dlq'}",
            ]
        ),
        encoding="utf-8",
    )
    return load_config(str(path))


def _task_streams(jetstream):
    return {name: config for name, config in jetstream.streams.items() if not name.endswith("_CALLBACK_RETRY") and not name.endswith("_DLQ")}


@pytest.mark.asyncio
async def test_distinct_namespaces_keep_separate_streams_and_consumers(tmp_path):
    jetstream = SharedJetStream()
    services = []
    for node_id in ("node-a", "node-b"):
        service = _TopologyService(config=_config(tmp_path, node_id, f"bk.ans_exec.{node_id}"), jetstream=jetstream)
        await service._ensure_stream_and_consumer()
        services.append(service)

    task_streams = _task_streams(jetstream)
    assert set(task_streams) == {service.config.js_stream for service in services}
    assert len(task_streams) == 2
    main_subscriptions = [item for item in jetstream.subscriptions if item[0].endswith(".tasks.>")]
    assert len(main_subscriptions) == 2
    assert main_subscriptions[0][1] != main_subscriptions[1][1]
    assert main_subscriptions[0][2] != main_subscriptions[1][2]
    dlq_streams = [name for name in jetstream.streams if name.endswith("_DLQ")]
    assert len(dlq_streams) == 2
    assert not any(subject.endswith(".dlq") for subject, _durable, _stream in jetstream.subscriptions)


@pytest.mark.asyncio
async def test_shared_namespace_reuses_the_first_stream_and_consumer(tmp_path):
    jetstream = SharedJetStream()
    services = []
    for node_id in ("node-a", "node-b"):
        service = _TopologyService(config=_config(tmp_path, node_id, "bk.ans_exec"), jetstream=jetstream)
        await service._ensure_stream_and_consumer()
        services.append(service)

    assert services[0].config.js_stream == services[1].config.js_stream
    assert len(_task_streams(jetstream)) == 1
    main_subscriptions = [item for item in jetstream.subscriptions if item[0] == "bk.ans_exec.tasks.>"]
    assert main_subscriptions[0][1:] == main_subscriptions[1][1:]


@pytest.mark.asyncio
async def test_legacy_dlq_inside_work_subject_does_not_open_another_stream(tmp_path):
    jetstream = SharedJetStream()
    service = _TopologyService(
        config=_config(tmp_path, "node-a", "bk.ans_exec.node-a", dlq_subject="bk.ans_exec.node-a.tasks.dlq"),
        jetstream=jetstream,
    )

    await service._ensure_stream_and_consumer()

    assert not any(name.endswith("_DLQ") for name in jetstream.streams)
    assert any(subject.endswith(".tasks.>") for subject, _durable, _stream in jetstream.subscriptions)
