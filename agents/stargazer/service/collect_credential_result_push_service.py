# -- coding: utf-8 --
import os

from core.credential_state_cache import CredentialStateCache
from core.nats_utils import nats_publish


COLLECT_CREDENTIAL_RESULT_PUSH_INTERVAL_SECONDS = int(os.getenv("COLLECT_CREDENTIAL_RESULT_PUSH_INTERVAL", "900"))
COLLECT_CREDENTIAL_RESULT_PUSH_BATCH_LIMIT = int(os.getenv("COLLECT_CREDENTIAL_RESULT_PUSH_BATCH_LIMIT", "1000"))
COLLECT_CREDENTIAL_RESULT_PUSH_SUBJECT = os.getenv(
    "COLLECT_CREDENTIAL_RESULT_PUSH_SUBJECT", "receive_collect_credential_result"
)


class CollectCredentialResultPushService:
    @staticmethod
    def build_results_payload(events: list[dict]) -> dict:
        next_since = ""
        for item in events or []:
            finished_at = str((item or {}).get("finished_at") or "")
            if finished_at and finished_at > next_since:
                next_since = finished_at
        return {"results": events or [], "next_since": next_since}

    @staticmethod
    async def list_results(since: str = "", limit: int = 500) -> dict:
        try:
            bounded_limit = max(1, min(int(limit or 500), 2000))
        except (TypeError, ValueError):
            bounded_limit = 500

        events = await CredentialStateCache.list_result_events(
            since=str(since or ""),
            limit=bounded_limit,
        )
        return CollectCredentialResultPushService.build_results_payload(events)

    @staticmethod
    async def push_once() -> dict:
        since = await CredentialStateCache.get_push_cursor()
        events = await CredentialStateCache.list_result_events(
            since=since,
            limit=COLLECT_CREDENTIAL_RESULT_PUSH_BATCH_LIMIT,
        )
        if not events:
            return {"pushed": 0, "next_since": since}

        next_since = CollectCredentialResultPushService.build_results_payload(events).get("next_since") or since
        payload = {
            "events": events,
            "next_since": next_since,
        }
        nats_namespace = os.getenv("NATS_NAMESPACE", "bklite")
        subject = f"{nats_namespace}.{COLLECT_CREDENTIAL_RESULT_PUSH_SUBJECT}"
        await nats_publish(subject, {"args": [], "kwargs": {"data": payload}})

        if next_since:
            await CredentialStateCache.set_push_cursor(next_since)
        return {"pushed": len(events), "next_since": next_since}