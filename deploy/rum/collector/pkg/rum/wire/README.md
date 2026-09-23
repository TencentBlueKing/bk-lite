# RUM NATS wire contract

`pkg/rum/wire` is the only public management seam for the RUM data plane. It owns
the `rum.control/v1` envelopes, DTOs, fixed error codes, subjects and NATS
client behavior. Controller storage and service implementations remain under
`apps/collector/internal/rum`.

Subjects:

- `rum.v1.control.application.apply`
- `rum.v1.control.application.get`
- `rum.v1.control.application.rotate`
- `rum.v1.control.application.retire`
- `rum.v1.control.application.disable`
- `rum.v1.control.erasure.submit`
- `rum.v1.control.reconcile.submit`
- `rum.v1.control.operation.get`
- `rum.v1.control.status.get`

All commands use NATS request-reply. A timed-out caller retries the exact
payload with the same `idempotencyKey`. Controller instances join queue group
`rum-controller`; commands are not stored in JetStream for delayed execution.
An accepted erasure or reconciliation operation is durable in Redis and no
longer depends on NATS.

The application payload never accepts a tenant identifier. Tenant identity is
deployment authority shared by Controller and Gateway, exposed by
`status.get`, and checked against Redis during every admission. This prevents
an operator-supplied tenant from changing the HMAC/fence identity domain.

Future Server integration must connect as a separately provisioned NATS
principal and use this package or its JSON contract. It must not import
`internal/rum/controller`, access Redis directly, or receive ClickHouse/MinIO
credentials.
