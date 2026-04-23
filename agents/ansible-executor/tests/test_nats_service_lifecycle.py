import asyncio

from core.config import ServiceConfig
from service.nats_service import AnsibleNATSService


class FakeMsg:
    def __init__(self):
        self.in_progress_calls = 0

    async def in_progress(self):
        self.in_progress_calls += 1


def test_callback_retry_preserves_failed_task_status(tmp_path):
    service = AnsibleNATSService(
        ServiceConfig(
            nats_servers=["nats://127.0.0.1:4222"],
            nats_instance_id="default",
            state_db_path=str(tmp_path / "state.db"),
        )
    )

    assert service._callback_retry_final_status({"status": "failed", "success": False}) == "failed"
    assert service._callback_retry_final_status({"status": "success", "success": True}) == "success"
    assert service._callback_retry_final_status({"success": False}) == "failed"


def test_ack_wait_is_extended_while_task_runs(tmp_path):
    async def run_case():
        service = AnsibleNATSService(
            ServiceConfig(
                nats_servers=["nats://127.0.0.1:4222"],
                nats_instance_id="default",
                js_ack_wait=2,
                state_db_path=str(tmp_path / "state.db"),
            )
        )
        msg = FakeMsg()
        running_task = asyncio.create_task(asyncio.sleep(1.2))
        await service._keep_message_in_progress(msg, running_task)
        await running_task
        return msg.in_progress_calls

    assert asyncio.run(run_case()) >= 1
