## MODIFIED Requirements

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

## ADDED Requirements

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
