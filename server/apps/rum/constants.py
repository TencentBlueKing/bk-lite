"""RUM control-plane subject and budget defaults (wire parity)."""

API_VERSION = "rum.control/v1"

SUBJECT_APPLICATION_APPLY = "rum.v1.control.application.apply"
SUBJECT_APPLICATION_GET = "rum.v1.control.application.get"
SUBJECT_APPLICATION_LIST = "rum.v1.control.application.list"
SUBJECT_ERASURE_SUBMIT = "rum.v1.control.erasure.submit"
SUBJECT_ERASURE_FENCE_RELEASE = "rum.v1.control.erasure.fence.release"
SUBJECT_PROJECTION_APPLY = "rum.v1.control.projection.apply"
SUBJECT_PROJECTION_RECONCILE = "rum.v1.control.projection.reconcile"
SUBJECT_OPERATION_GET = "rum.v1.control.operation.get"

# Controller operation statuses that will not change any more.
OPERATION_TERMINAL_STATUSES = frozenset({"completed", "failed"})

_MIB = 1 << 20
_GIB = 1 << 30

DEFAULT_BUDGETS = {
    "requestsPerMinute": 6_000,
    "compressedBytesPerMinute": 32 * _MIB,
    "decompressedBytesPerMinute": 128 * _MIB,
    "eventsPerMinute": 20_000,
}

MAX_BUDGETS = {
    "requestsPerMinute": 120_000,
    "compressedBytesPerMinute": 256 * _MIB,
    "decompressedBytesPerMinute": _GIB,
    "eventsPerMinute": 200_000,
}

EVIDENCE_WINDOW_SECONDS = 15 * 60

FARO_WEB_SDK_VERSION = "2.8.2"
BKLITE_RUM_SDK_VERSION = "0.1.0"
GRAFANA_RRWEB_VERSION = "2.0.0-grafana.2"
DEFAULT_REPLAY_SAMPLING_RATE = 0.1

REPLAY_PRIVACY_MASK_TEXT = ".faro-mask, [data-faro-mask], [contenteditable]"
REPLAY_PRIVACY_BLOCK = (
    "input[type='password'], [autocomplete='current-password'], "
    "[autocomplete='new-password'], [autocomplete='one-time-code'], "
    "form[action*='login' i], form[action*='signin' i], "
    "form[action*='checkout' i], form[action*='payment' i]"
)

MAX_ORIGINS = 20
