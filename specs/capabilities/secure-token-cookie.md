## ADDED Requirements

### Requirement: bklite_token cookie SHALL be set by the server with secure attributes
The backend SHALL set the `bklite_token` cookie via `Set-Cookie` response header on successful login. The cookie SHALL include the attributes: `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, and `Max-Age` equal to the configured `login_expired_time` in seconds.

#### Scenario: Login response sets secure cookie
- **WHEN** a user successfully authenticates via the login endpoint
- **THEN** the HTTP response includes a `Set-Cookie` header for `bklite_token` with `HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=86400` (default)

#### Scenario: Cookie is not accessible to JavaScript
- **WHEN** client-side JavaScript attempts to read `document.cookie` for `bklite_token`
- **THEN** the cookie is not visible because it has the `HttpOnly` attribute

### Requirement: Frontend SHALL NOT write bklite_token via document.cookie
The frontend `crossDomainAuth.ts` module SHALL NOT set the `bklite_token` cookie via `document.cookie`. The `saveAuthToken` function SHALL be removed or refactored to rely on the server-set cookie. The `clearAuthToken` function SHALL call the backend logout endpoint which clears the cookie via `Set-Cookie` with `Max-Age=0`.

#### Scenario: Frontend login flow does not write cookie directly
- **WHEN** a user completes login on the frontend
- **THEN** the frontend does not execute `document.cookie = "bklite_token=..."` and instead relies on the backend `Set-Cookie` header

#### Scenario: Frontend logout clears cookie via backend
- **WHEN** a user logs out
- **THEN** the backend response includes `Set-Cookie: bklite_token=; Max-Age=0; HttpOnly; Secure; SameSite=Lax; Path=/` to clear the cookie

### Requirement: Backend SHALL clear bklite_token cookie on logout
The logout/revocation endpoint SHALL include a `Set-Cookie` header that expires the `bklite_token` cookie (setting `Max-Age=0` with the same attributes).

#### Scenario: Logout response clears the cookie
- **WHEN** the token revocation endpoint is called
- **THEN** the HTTP response includes a `Set-Cookie` header that sets `bklite_token` with `Max-Age=0` to delete the cookie from the browser
