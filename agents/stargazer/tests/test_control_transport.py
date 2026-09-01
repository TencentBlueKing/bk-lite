import pytest
from core.infra.control_transport import NatsControlTransport, UnsupportedControlSubject


@pytest.mark.asyncio
async def test_control_transport_only_publishes_registered_callback_protocol():
    published = []

    async def publish(subject, payload):
        published.append((subject, payload))

    transport = NatsControlTransport(namespace="bklite", publish=publish)

    await transport.publish_collection_callback(
        "receive_config_file_result",
        {"task_id": "task-1", "result": True},
    )

    assert published == [
        (
            "bklite.receive_config_file_result",
            {
                "args": [],
                "kwargs": {"data": {"task_id": "task-1", "result": True}},
            },
        )
    ]


@pytest.mark.asyncio
async def test_control_transport_rejects_removed_credential_result_subject():
    published = []

    async def publish(subject, payload):
        published.append((subject, payload))

    transport = NatsControlTransport(namespace="bklite", publish=publish)

    with pytest.raises(UnsupportedControlSubject, match="unsupported collection callback"):
        await transport.publish_collection_callback(
            "receive_collect_credential_result",
            {"credential_id": "must-not-be-published"},
        )

    assert published == []
