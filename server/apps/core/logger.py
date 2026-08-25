import logging
import traceback
from pathlib import Path

SAFE_EXCEPTION_MAX_FRAMES = 12


class SafeLogException(RuntimeError):
    """Controlled exception proxy used only for traceback rendering."""


def safe_log_value(value, *, max_length=160) -> str:
    """Return a bounded single-line copy for logs without changing the business value."""
    return str(value or "").replace("\r", "\\r").replace("\n", "\\n")[:max_length]


def safe_exception_call_chain(error: BaseException, *, max_frames=SAFE_EXCEPTION_MAX_FRAMES) -> str:
    """Keep bounded traceback ownership without formatting exception text or frame locals."""
    frames = traceback.extract_tb(error.__traceback__)
    if not frames:
        return "-"
    return ">".join(
        f"{safe_log_value(Path(frame.filename).name)}:{frame.lineno}:{safe_log_value(frame.name)}"
        for frame in frames[-max_frames:]
    )


def safe_exception_info(error: BaseException):
    """Preserve traceback frames while replacing the exception body with a controlled message."""
    safe_error = SafeLogException(type(error).__name__)
    return SafeLogException, safe_error, error.__traceback__

logger = logging.getLogger("app")
cmdb_logger = logging.getLogger("cmdb")
operation_analysis_logger = logging.getLogger("operation_analysis")
alert_logger = logging.getLogger("alert")
monitor_logger = logging.getLogger("monitor")
node_logger = logging.getLogger("node")
console_mgmt_logger = logging.getLogger("ops-console")
opspilot_logger = logging.getLogger("opspilot")
system_mgmt_logger = logging.getLogger("system-manager")
celery_logger = logging.getLogger("celery")
mlops_logger = logging.getLogger("mlops")
log_logger = logging.getLogger("log")
job_logger = logging.getLogger("job")
nats_logger = logging.getLogger("nats")
apm_logger = logging.getLogger("apm")
patch_mgmt_logger = logging.getLogger("patch-mgmt")
openapi_logger = logging.getLogger("openapi")
