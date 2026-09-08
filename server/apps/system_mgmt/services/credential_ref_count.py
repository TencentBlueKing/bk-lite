"""Ask CMDB and Monitor how many tasks reference vault credential IDs."""

from __future__ import annotations

from apps.core.logger import system_mgmt_logger as logger
from apps.rpc.base import RpcClient
from apps.system_mgmt.services.credential_service import CredentialServiceError

REF_QUERY_TIMEOUT = 5
REF_QUERY_MAX_IDS = 100
REF_MODULE_CMDB = "cmdb"
REF_MODULE_MONITOR = "monitor"
REF_NATS_METHODS = {
    REF_MODULE_CMDB: "cmdb_count_credential_refs",
    REF_MODULE_MONITOR: "monitor_count_credential_refs",
}
INQUIRY_STARTED_TEMPLATE = "event=credential_ref_count_inquiry_started method=%s module=%s id_count=%s"
INQUIRY_FINISHED_TEMPLATE = "event=credential_ref_count_inquiry_finished method=%s module=%s outcome=%s id_count=%s"
INQUIRY_FAILED_TEMPLATE = (
    "event=credential_ref_count_inquiry_failed method=%s module=%s failed_stage=rpc id_count=%s error_type=%s"
)


def _nats_querier(method):
    def query(ids, **kwargs):
        return RpcClient().run(method, credential_ids=list(ids or ()), **kwargs)

    return query


def _live_queriers():
    return (
        (REF_MODULE_CMDB, _nats_querier(REF_NATS_METHODS[REF_MODULE_CMDB])),
        (REF_MODULE_MONITOR, _nats_querier(REF_NATS_METHODS[REF_MODULE_MONITOR])),
    )


def parse_counts(payload, expected_ids):
    if not isinstance(payload, dict) or payload.get("result") is False:
        raise ValueError("invalid")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("invalid")
    raw = data.get("counts")
    if not isinstance(raw, dict):
        raise ValueError("invalid")
    counts = {}
    for credential_id in expected_ids:
        if credential_id not in raw:
            raise ValueError("invalid")
        try:
            counts[credential_id] = int(raw[credential_id])
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid") from exc
        if counts[credential_id] < 0:
            raise ValueError("invalid")
    return counts


def query_module_counts(credential_ids, queriers=None):
    ids = list(dict.fromkeys(credential_ids or ()))
    result = {}
    if not ids:
        return result
    chunks = [ids[index : index + REF_QUERY_MAX_IDS] for index in range(0, len(ids), REF_QUERY_MAX_IDS)]
    for module, querier in queriers if queriers is not None else _live_queriers():
        method = REF_NATS_METHODS.get(module, module)
        logger.info(INQUIRY_STARTED_TEMPLATE, method, module, len(ids))
        merged = {}
        try:
            for chunk in chunks:
                payload = querier(chunk, _timeout=REF_QUERY_TIMEOUT)
                merged.update(parse_counts(payload, chunk))
        except Exception as exc:
            logger.warning(INQUIRY_FAILED_TEMPLATE, method, module, len(ids), type(exc).__name__)
            result[module] = None
            continue
        logger.info(INQUIRY_FINISHED_TEMPLATE, method, module, "ok", len(ids))
        result[module] = merged
    return result


def list_ref_chips(credential_ids, queriers=None):
    ids = list(dict.fromkeys(credential_ids or ()))
    by_id = {credential_id: None for credential_id in ids}
    if not ids:
        return by_id
    module_counts = query_module_counts(ids, queriers=queriers)
    any_success = any(counts is not None for counts in module_counts.values())
    if not any_success:
        return by_id
    for credential_id in ids:
        chips = []
        for module, counts in module_counts.items():
            if counts is None:
                continue
            n = counts.get(credential_id, 0)
            if n > 0:
                chips.append({"module": module, "count": n})
        by_id[credential_id] = chips
    return by_id


def attach_public_refs(items, queriers=None):
    chips = list_ref_chips(
        [item.get("credential_id") for item in items if item.get("credential_id")],
        queriers=queriers,
    )
    for item in items:
        item["refs"] = chips.get(item.get("credential_id"))
    return items


def assert_credential_unreferenced(credential_id, queriers=None):
    module_counts = query_module_counts([credential_id], queriers=queriers)
    if any(counts is None for counts in module_counts.values()) or not module_counts:
        raise CredentialServiceError("in_use")
    total = sum(counts.get(credential_id, 0) for counts in module_counts.values())
    if total > 0:
        raise CredentialServiceError("in_use")
