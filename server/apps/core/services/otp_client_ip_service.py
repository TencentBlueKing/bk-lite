import os
from ipaddress import ip_address, ip_network


DIRECT_MODE = "direct"
LEGACY_MODE = "legacy"
TRUSTED_PROXY_MODE = "trusted_proxy"


def get_otp_client_ip(request) -> str:
    """Return the fail-safe client IP used by OTP rate limiting."""
    remote_addr = request.META.get("REMOTE_ADDR", "")
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    mode = os.getenv("OTP_CLIENT_IP_MODE", DIRECT_MODE).strip().lower()

    if mode == LEGACY_MODE:
        return forwarded_for.split(",")[0].strip() if forwarded_for else remote_addr
    if mode != TRUSTED_PROXY_MODE or not forwarded_for:
        return remote_addr

    try:
        remote_ip = ip_address(remote_addr)
        trusted_networks = [
            ip_network(value.strip(), strict=False)
            for value in os.getenv("OTP_TRUSTED_PROXY_CIDRS", "").split(",")
            if value.strip()
        ]
        expected_proxy_hops = int(os.getenv("OTP_TRUSTED_PROXY_HOPS", ""))
        forwarded_ips = [ip_address(value.strip()) for value in forwarded_for.split(",")]
    except (TypeError, ValueError):
        return remote_addr

    if (
        expected_proxy_hops < 1
        or not trusted_networks
        or not any(remote_ip in network for network in trusted_networks)
    ):
        return remote_addr

    trusted_hops = 1  # REMOTE_ADDR is the nearest proxy hop.
    for candidate in reversed(forwarded_ips):
        if any(candidate in network for network in trusted_networks):
            trusted_hops += 1
            continue
        if trusted_hops != expected_proxy_hops:
            return remote_addr
        return str(candidate)
    return remote_addr
