"""RUM control-plane subject and budget defaults (wire parity)."""

API_VERSION = "rum.control/v1"

SUBJECT_APPLICATION_APPLY = "rum.v1.control.application.apply"
SUBJECT_APPLICATION_GET = "rum.v1.control.application.get"
SUBJECT_APPLICATION_LIST = "rum.v1.control.application.list"
SUBJECT_ERASURE_SUBMIT = "rum.v1.control.erasure.submit"
SUBJECT_OPERATION_GET = "rum.v1.control.operation.get"

# Controller operation statuses that will not change any more.
OPERATION_TERMINAL_STATUSES = frozenset({"completed", "failed"})

DEFAULT_BUDGETS = {
    "requestsPerMinute": 1_000_000,
    "compressedBytesPerMinute": 1 << 30,
    "decompressedBytesPerMinute": 4 << 30,
    "eventsPerMinute": 1_000_000,
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
