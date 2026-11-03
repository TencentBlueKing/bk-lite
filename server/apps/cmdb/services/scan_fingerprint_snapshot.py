from apps.cmdb.services.port_fingerprint import enabled_port_fingerprints
from apps.cmdb.services.process_fingerprint import enabled_process_fingerprints


def build_scan_fingerprint_snapshot() -> dict:
    return {
        "port_fingerprints": enabled_port_fingerprints(),
        "process_fingerprints": enabled_process_fingerprints(),
    }
