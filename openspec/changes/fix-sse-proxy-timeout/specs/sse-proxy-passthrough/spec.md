## ADDED Requirements

### Requirement: SSE Response Detection
The Proxy SHALL detect SSE responses by checking if the upstream `Content-Type` header starts with `text/event-stream`.

#### Scenario: SSE response detected
- **WHEN** upstream response has `Content-Type: text/event-stream`
- **THEN** Proxy SHALL apply SSE-specific handling (streaming, headers, timeout)

#### Scenario: Non-SSE response unchanged
- **WHEN** upstream response has `Content-Type: application/json`
- **THEN** Proxy SHALL use default handling without SSE optimizations

### Requirement: SSE Header Passthrough
The Proxy SHALL transparently pass through all SSE-related headers from the upstream response, and ensure critical headers are present.

#### Scenario: Headers passed through
- **WHEN** upstream SSE response includes `Content-Type`, `Cache-Control`, `X-Accel-Buffering`
- **THEN** Proxy SHALL include all these headers in the client response

#### Scenario: Missing critical headers added
- **WHEN** upstream SSE response is missing `X-Accel-Buffering` header
- **THEN** Proxy SHALL add `X-Accel-Buffering: no` to disable Nginx buffering

### Requirement: SSE Stream Passthrough
The Proxy SHALL stream SSE data chunks to the client as they arrive, without buffering the entire response.

#### Scenario: Chunks streamed immediately
- **WHEN** upstream sends an SSE event chunk
- **THEN** Proxy SHALL forward the chunk to client within 100ms (no buffering delay)

#### Scenario: Stream remains open
- **WHEN** upstream SSE connection is active
- **THEN** Proxy SHALL keep client connection open until upstream closes or timeout

### Requirement: Extended Timeout for SSE
The Proxy SHALL use a 5-minute (300 second) timeout for SSE connections, matching the backend Agent total timeout.

#### Scenario: Long SSE connection allowed
- **WHEN** SSE connection has been active for 4 minutes with periodic data
- **THEN** Proxy SHALL keep the connection open

#### Scenario: Timeout after inactivity
- **WHEN** no data received from upstream for 5 minutes
- **THEN** Proxy SHALL close the connection and return 504 Gateway Timeout

### Requirement: LLM Call Timeout Extension
The default `llm_timeout_seconds` in `TimeoutConfig` SHALL be 300 seconds to support complex reasoning tasks.

#### Scenario: Default timeout is 300s
- **WHEN** a new `TimeoutConfig` is created without explicit `llm_timeout_seconds`
- **THEN** the default value SHALL be 300 seconds

#### Scenario: Custom timeout respected
- **WHEN** `TimeoutConfig` is created with `llm_timeout_seconds=600`
- **THEN** the LLM call timeout SHALL be 600 seconds
