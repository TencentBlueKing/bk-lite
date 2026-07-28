# Website Probe Monitoring Guide

Uses Telegraf `inputs.http_response` to probe an HTTP/HTTPS URL from the selected node and collect availability, response time, and status code metrics.

## Basic configuration

- **Node**: Choose a collection node that can reach the target.
- **URL**: Enter an HTTP/HTTPS address without a query string; wrap IPv6 in brackets, for example `https://[2001:db8::1]/`.
- **Interval**: Collection period in seconds.
- **Request Method**: GET, HEAD, or POST only.

## Advanced configuration

Expand **Advanced Configuration** only when needed. Empty optional fields are omitted from the Telegraf config and keep native defaults.

### Request

- **Query Parameters**: The URL field must not include a query string; parameters are encoded in order and appended. Duplicate names are allowed.
- **Request Headers**: Non-sensitive headers only (for example `Content-Type`); do not add `Authorization`.
- **Request Body**: Available for POST; set `Content-Type` for JSON, XML, or form data.

### Authentication

Supports none, Basic Auth, and Bearer Token. Credentials are injected via environment variables and are not written into the Telegraf config body.

### Expected Response

Optionally set expected status code, expected response content, response timeout, and follow redirects. Leave blank to keep Telegraf defaults (response timeout defaults to 5 seconds).

### TLS

For HTTPS, enable **Skip Certificate Verification** when needed.
