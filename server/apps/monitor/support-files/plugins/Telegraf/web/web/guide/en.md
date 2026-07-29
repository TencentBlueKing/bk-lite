# Website Probe Monitoring Guide

This plugin uses Telegraf `inputs.http_response` to send GET, HEAD, or POST probes to an HTTP/HTTPS URL from the selected node.

## Prerequisites

- The selected node can resolve the target name and reach the URL. IPv6 literals must be enclosed in brackets.
- The target provides a read-only probe endpoint. Even for POST, use a health request that does not mutate business resources.
- For Basic Auth or a Bearer token, use only the dedicated credential fields. Do not put credentials in the URL or ordinary headers.
- Production HTTPS probes should use a valid certificate. Skip verification only for a controlled, temporary self-signed or incomplete-chain case.

## Setup Steps

1. Run the pre-check from the node you plan to select.
2. Enter the URL, collection interval, and request method. Keep query data out of the URL field and enter it under **Query Parameters**.
3. As needed, configure the POST body, headers, authentication, expected status, expected-response regex, timeout, and redirect policy.
4. In the monitored-objects table, select a node and enter the URL, instance name, and optional group.
5. Save and wait for at least one collection interval. The default interval is `60` seconds.

## Pre-checks

Basic HTTP check:

```bash
PROBE_URL=https://example.com/
curl --fail-with-body --silent --show-error --location \
  --request GET "$PROBE_URL" --output /tmp/website-probe-response.txt
```

If **Expected Response Content** is configured, test a compatible extended-regex subset against the saved body:

```bash
grep -E -q 'service[[:space:]]+ready' /tmp/website-probe-response.txt
```

Both commands must exit with status `0`. If a non-2xx response is expected, use a controlled test tool that displays and validates the actual status; do not treat a command that ignores HTTP failures as success evidence.

## Field Reference

| Field | Required | Default | Description |
| --- | --- | --- | --- |
| URL | Yes | None | HTTP/HTTPS URL without a query string; IPv6 example: `https://[2001:db8::1]/`. The base URL is not editable later. |
| Interval | Yes | `60` seconds | Collection interval, minimum `1` second; short intervals increase target traffic. |
| Skip Certificate Verification | No | Off | Disables HTTPS server-certificate verification. Keep it off in production. |
| Request Method | Yes | `GET` | Supports `GET`, `HEAD`, and `POST`. The body field is shown only for POST. |
| Request Body | No | None | Raw POST body; declare JSON, XML, or form format with `Content-Type`. |
| Query Parameters | No | None | URL-encoded and appended in entry order; duplicate names are allowed and blank rows are ignored. |
| Request Headers | No | None | Non-sensitive headers. Use the authentication fields instead of manually setting `Authorization`. |
| Authentication | Yes | None | Supports none, Basic Auth, and Bearer Token. |
| Username | No | None | Basic Auth username; enter it when Basic Auth is selected. |
| Password | No | None | Basic Auth password, injected through an environment variable. |
| Bearer Token | No | None | Token value only, without the `Bearer` prefix; injected through an environment variable. |
| Expected Status Code | No | None | Value from `100` to `599`; when empty, the template does not set status matching. |
| Expected Response Content | No | None | Regular expression evaluated against the response body; empty disables body matching. |
| Response Timeout | No | Telegraf default `5` seconds | Value from `1` to `600` seconds; a timeout is a probe failure. |
| Follow Redirects | No | Telegraf default behavior | When explicitly enabled, evaluate the final page; when disabled, evaluate the first response. |
| Node | Yes | None | Collector node that runs the probe. |
| URL (monitored object) | Yes | None | Instance HTTP/HTTPS address; bracket IPv6 literals. |
| Instance Name | Yes | None | Display name in the platform. |
| Group | No | None | Optional instance group. |

## Post-setup Verification

After at least one collection interval, confirm that the instance appears and check these registered metrics:

- `http_response_result_code`: expected success enum value is `0`.
- `http_response_response_time`: response time should continue reporting.
- `http_response_http_response_code`: should match the actual target status.
- `http_response_content_length`: use it to confirm response size when a body is present.

## Troubleshooting

### Expected response content never matches

Telegraf evaluates this field as a regular expression, not a literal substring. Use a compatible `grep -E -q` expression against the saved body to pre-check escaping, case, and newlines; the actual probe result remains authoritative.

### Basic Auth or Bearer authentication fails

Match the authentication mode to its credential field. Do not add the `Bearer` prefix in the token field, and do not also set an `Authorization` header manually.

### Redirected status does not match

With redirects enabled, the final response is evaluated. With redirects disabled, the first response is evaluated. Select the behavior required by the monitored contract.

### HTTPS certificate verification fails

Fix the certificate chain, validity, or hostname. Skip verification only for a controlled temporary case.
