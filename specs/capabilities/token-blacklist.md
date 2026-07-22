## ADDED Requirements

### Requirement: JWT payload SHALL contain jti and exp standard claims
The system SHALL include a `jti` claim (UUID4 hex string) and an `exp` claim (UNIX timestamp) in every JWT token issued at login. The `exp` value SHALL equal the current time plus the configured `login_expired_time` (in seconds). The `login_time` claim SHALL be retained for backward compatibility during the transition period.

#### Scenario: New token contains jti and exp
- **WHEN** a user successfully authenticates and a JWT is issued
- **THEN** the token payload contains `user_id`, `login_time`, `jti` (32-char hex string), and `exp` (integer UNIX timestamp equal to current time + login_expired_time)

#### Scenario: Each token has a unique jti
- **WHEN** two tokens are issued for the same user in sequence
- **THEN** each token has a distinct `jti` value

### Requirement: Token verification SHALL use PyJWT exp auto-validation
The system SHALL decode tokens with PyJWT's built-in `exp` verification enabled for tokens that contain an `exp` claim. Tokens with an expired `exp` SHALL be rejected with a 401 response.

#### Scenario: Expired new-format token is rejected
- **WHEN** a request includes a JWT whose `exp` is in the past
- **THEN** the system returns HTTP 401 and does not process the request

#### Scenario: Valid new-format token is accepted
- **WHEN** a request includes a JWT whose `exp` is in the future and `jti` is not blacklisted
- **THEN** the system processes the request normally

### Requirement: System SHALL maintain a Redis-based token blacklist
The system SHALL store revoked token identifiers in Redis using `django.core.cache` with key format `jwt:blacklist:{jti}`, value `1`, and TTL equal to the token's remaining time until `exp`. A token SHALL be considered blacklisted if its `jti` key exists in Redis.

#### Scenario: Blacklisted token entry auto-expires
- **WHEN** a token with `jti=abc` and 3600 seconds remaining until `exp` is blacklisted
- **THEN** Redis key `jwt:blacklist:abc` is set with TTL=3600 and automatically deleted after 3600 seconds

### Requirement: Token verification SHALL check the blacklist
The system SHALL check whether a token's `jti` exists in the blacklist during verification. If the `jti` is blacklisted, the system SHALL reject the request with HTTP 401. The blacklist check SHALL occur after JWT decode and before returning user info.

#### Scenario: Request with blacklisted token is rejected
- **WHEN** a request includes a valid JWT whose `jti` is present in the blacklist
- **THEN** the system returns HTTP 401

#### Scenario: Request with non-blacklisted token proceeds
- **WHEN** a request includes a valid JWT whose `jti` is not in the blacklist
- **THEN** the system proceeds with normal authentication

### Requirement: Logout SHALL revoke the current token
The system SHALL provide a token revocation endpoint (NATS RPC `revoke_token`). When invoked, the endpoint SHALL decode the token, write its `jti` to the blacklist with appropriate TTL, and clear the user's verify_token cache. The frontend logout flows (federated-logout, forceLogout) SHALL call this endpoint before clearing client-side state.

#### Scenario: User logs out and token is immediately revoked
- **WHEN** a user triggers logout
- **THEN** the backend adds the token's `jti` to the blacklist, clears the user's token info cache, and subsequent requests with that token receive HTTP 401

#### Scenario: Force logout revokes token
- **WHEN** a forced logout is triggered (e.g., on 401/460 response)
- **THEN** the system attempts to call the revocation endpoint before clearing client state

### Requirement: Legacy tokens SHALL be accepted during transition period
The system SHALL accept tokens without `jti`/`exp` claims by falling back to the existing `login_time`-based expiry check. Legacy tokens SHALL NOT be subject to blacklist checks. This compatibility behavior SHALL be removed after one release cycle.

#### Scenario: Old-format token is accepted during transition
- **WHEN** a request includes a JWT with `user_id` and `login_time` but no `jti` or `exp`
- **THEN** the system verifies the token using the legacy `login_time` comparison and processes the request if valid

#### Scenario: Old-format token naturally expires
- **WHEN** a legacy token's `login_time` is older than `login_expired_time`
- **THEN** the system rejects the token with HTTP 401
