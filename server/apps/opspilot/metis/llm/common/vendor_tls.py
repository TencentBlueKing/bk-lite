"""TLS overrides scoped to requests to a configured model vendor."""

import httpx


def vendor_skips_ssl_verify(model) -> bool:
    return getattr(getattr(model, "vendor", None), "skip_ssl_verify", False) is True


def sdk_http_options(skip_ssl_verify: bool) -> dict:
    if skip_ssl_verify:
        return {"http_client": httpx.Client(verify=False)}
    return {}
