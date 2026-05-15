# Capability: OTP Challenge Flow

## Purpose

Defines the two-phase authentication flow for users with OTP (One-Time Password) enabled. This capability ensures that OTP-enabled users must complete both password verification AND OTP verification before receiving an access token, preventing security bypass vulnerabilities.

## Requirements

### Requirement: Two-phase login for OTP-enabled users
When a user has OTP enabled, the system SHALL require both password verification AND OTP verification before issuing an access token. Password verification alone MUST NOT grant API access.

#### Scenario: Password correct, OTP enabled
- **WHEN** user submits correct username and password
- **AND** user has OTP enabled
- **THEN** system returns a temporary `challenge_id` (not a JWT token)
- **AND** system does NOT set `bklite_token` cookie
- **AND** response includes `require_otp: true`

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

#### Scenario: Rate limit exceeded
- **WHEN** user exceeds 5 failed OTP attempts within 5 minutes (per IP + username)
- **THEN** system blocks further OTP verification attempts
- **AND** returns rate limit error with retry-after time

#### Scenario: Rate limit reset
- **WHEN** user successfully verifies OTP
- **THEN** system resets the failure counter for that IP + username

#### Scenario: Rate limit expiry
- **WHEN** 5 minutes pass since last failed attempt
- **THEN** rate limit counter resets automatically
