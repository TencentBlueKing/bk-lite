# Capability: OTP Challenge Flow

## Purpose

Defines the two-phase authentication flow for users with OTP (One-Time Password) enabled. This capability ensures that OTP-enabled users must complete both password verification AND OTP verification before receiving an access token, preventing security bypass vulnerabilities.
## Requirements
### Requirement: Two-phase login for OTP-enabled users
When a user has OTP enabled, the system SHALL require both password verification AND OTP verification before issuing an access token. Password verification alone MUST NOT grant API access. The first phase response SHALL include `temporary_pwd` status to enable proper post-OTP flow handling.

#### Scenario: Password correct, OTP enabled
- **WHEN** user submits correct username and password
- **AND** user has OTP enabled
- **THEN** system returns a temporary `challenge_id` (not a JWT token)
- **AND** system does NOT set `bklite_token` cookie
- **AND** response includes `require_otp: true`
- **AND** response includes `temporary_pwd: <user.temporary_pwd>` to indicate if forced password change is required after OTP verification

#### Scenario: Password correct, OTP enabled, temporary password user
- **WHEN** user submits correct username and password
- **AND** user has OTP enabled
- **AND** user has `temporary_pwd=true`
- **THEN** system returns a temporary `challenge_id` (not a JWT token)
- **AND** response includes `require_otp: true`
- **AND** response includes `temporary_pwd: true`
- **AND** after successful OTP verification, user SHALL be redirected to password reset before completing authentication

#### Scenario: Password correct, OTP disabled
- **WHEN** user submits correct username and password
- **AND** user does NOT have OTP enabled
- **THEN** system returns JWT token (existing behavior unchanged)
- **AND** system sets `bklite_token` cookie

#### Scenario: Password incorrect
- **WHEN** user submits incorrect password
- **THEN** system returns authentication error
- **AND** no challenge_id or token is issued

### Requirement: Challenge-based OTP verification
The system SHALL provide an endpoint to verify OTP code with a challenge_id, and only issue JWT token after successful verification.

#### Scenario: Valid OTP with valid challenge
- **WHEN** user submits valid `challenge_id` and correct `otp_code` to `/api/verify_otp_login/`
- **THEN** system issues JWT token
- **AND** system sets `bklite_token` cookie
- **AND** system invalidates the `challenge_id` (one-time use)

#### Scenario: Invalid OTP code
- **WHEN** user submits valid `challenge_id` but incorrect `otp_code`
- **THEN** system returns OTP verification error
- **AND** no token is issued
- **AND** `challenge_id` remains valid for retry (until expiry or max attempts)

#### Scenario: Expired challenge
- **WHEN** user submits `challenge_id` that has expired (>5 minutes)
- **THEN** system returns challenge expired error
- **AND** user must restart login process

#### Scenario: Invalid or already-used challenge
- **WHEN** user submits `challenge_id` that does not exist or was already used
- **THEN** system returns invalid challenge error

### Requirement: Challenge storage and expiration
The system SHALL store challenges in a distributed cache with automatic expiration.

#### Scenario: Challenge creation
- **WHEN** password verification succeeds for OTP-enabled user
- **THEN** system generates a unique `challenge_id` (UUID)
- **AND** stores challenge data in cache with 5-minute TTL
- **AND** challenge data includes: user_id, username, created_at

#### Scenario: Challenge auto-expiration
- **WHEN** challenge reaches 5-minute TTL
- **THEN** cache automatically removes the challenge
- **AND** subsequent verification attempts with this challenge_id fail

### Requirement: OTP verification rate limiting
The system SHALL limit OTP verification attempts to prevent brute-force attacks.

The Core HTTP boundary SHALL derive the IP from one of these explicit modes:

- `direct` (default): use the direct peer address and ignore forwarding headers.
- `trusted_proxy`: accept `X-Forwarded-For` only when the direct peer is in
  `OTP_TRUSTED_PROXY_CIDRS`; require the inventoried proxy count in
  `OTP_TRUSTED_PROXY_HOPS`, then walk the chain from the nearest hop and use
  the first untrusted address.
- `legacy`: temporarily preserve the former first-`X-Forwarded-For` behavior as
  an operational rollback while trusted proxy ranges are being inventoried.

Before enabling `trusted_proxy`, operators SHALL inventory every proxy hop and
configure its CIDR. Invalid or incomplete configuration SHALL fail safe to the
direct peer. A deployment can roll back without data migration by selecting
`legacy`; rate-limit counters are reconstructable cache entries with a
five-minute TTL.

The bundled Next proxy removes inbound `X-Forwarded-For` by default
(`OTP_WEB_XFF_MODE=strip`). `trusted_upstream` may be selected only when its
upstream overwrites client-supplied forwarding headers and appends the observed
client address; `legacy` preserves the former transparent forwarding behavior
only as a bounded rollback. Rollout order is: inventory the fixed proxy chain,
configure the server CIDRs and hop count, verify upstream header sanitation,
then enable both trusted modes. Roll back the Web proxy and server to `legacy`
without a data migration; cached counters expire within five minutes.

#### Scenario: Rate limit exceeded
- **WHEN** user exceeds 5 failed OTP attempts within 5 minutes (per IP + username)
- **THEN** system blocks further OTP verification attempts
- **AND** returns rate limit error with retry-after time

#### Scenario: Untrusted forwarding header
- **WHEN** a direct client supplies `X-Forwarded-For`
- **AND** the direct peer is not configured as trusted
- **THEN** the forwarding header does not affect the rate-limit key

#### Scenario: Trusted multi-hop proxy
- **WHEN** the direct peer and intermediate proxy hops are configured as trusted
- **THEN** the nearest untrusted address in the forwarding chain is used
- **AND** attacker-prepended forwarding values do not affect the rate-limit key

#### Scenario: Proxy configuration rollback
- **WHEN** an existing deployment cannot yet provide its complete trusted proxy ranges
- **THEN** operators can select `legacy` temporarily without an application or data rollback

#### Scenario: Rate limit reset
- **WHEN** user successfully verifies OTP
- **THEN** system resets the failure counter for that IP + username

#### Scenario: Rate limit expiry
- **WHEN** 5 minutes pass since last failed attempt
- **THEN** rate limit counter resets automatically

### Requirement: OTP verification preserves temporary_pwd semantics
After successful OTP verification, the system SHALL check `temporary_pwd` status and enforce password reset before completing authentication.

#### Scenario: OTP success with temporary password
- **WHEN** user completes OTP verification successfully
- **AND** user has `temporary_pwd=true`
- **THEN** system returns JWT token with `temporary_pwd: true` in response
- **AND** frontend SHALL redirect user to password reset flow
- **AND** user SHALL NOT be able to access protected resources until password is changed

#### Scenario: OTP success without temporary password
- **WHEN** user completes OTP verification successfully
- **AND** user has `temporary_pwd=false`
- **THEN** system returns JWT token with `temporary_pwd: false` in response
- **AND** frontend completes authentication normally
- **AND** user can access protected resources immediately
