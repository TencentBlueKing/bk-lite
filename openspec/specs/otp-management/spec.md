# Capability: OTP Management

## Purpose

Defines the secure management of OTP (One-Time Password) configuration, including QR code generation and OTP code verification for binding purposes. This capability ensures that OTP management operations are properly authenticated and cannot be exploited to compromise other users' accounts.

## Requirements

### Requirement: OTP QR code generation requires authentication
The system SHALL require user authentication before generating OTP QR codes, and MUST only generate for the authenticated user.

#### Scenario: Authenticated user generates own QR code
- **WHEN** authenticated user calls `GET /api/generate_qr_code/`
- **THEN** system generates new OTP secret for `request.user`
- **AND** returns QR code for the authenticated user
- **AND** does NOT accept `username` parameter

#### Scenario: Unauthenticated request to generate QR code
- **WHEN** unauthenticated user calls `GET /api/generate_qr_code/`
- **THEN** system returns 401 Unauthorized
- **AND** no OTP secret is generated or modified

#### Scenario: Attempt to generate QR code for another user
- **WHEN** authenticated user attempts to specify another username
- **THEN** system ignores the parameter and generates for `request.user` only

### Requirement: OTP verification requires authentication
The system SHALL require user authentication before verifying OTP codes for binding purposes, and MUST only verify for the authenticated user.

#### Scenario: Authenticated user verifies own OTP
- **WHEN** authenticated user calls `POST /api/verify_otp_code/` with valid OTP code
- **THEN** system verifies OTP for `request.user`
- **AND** does NOT accept `username` parameter

#### Scenario: Unauthenticated request to verify OTP
- **WHEN** unauthenticated user calls `POST /api/verify_otp_code/`
- **THEN** system returns 401 Unauthorized

#### Scenario: Invalid OTP code during binding verification
- **WHEN** authenticated user submits incorrect OTP code
- **THEN** system returns verification failed error
- **AND** user can retry with correct code

### Requirement: OTP management endpoints remove api_exempt
The system SHALL NOT exempt OTP management endpoints from authentication middleware.

#### Scenario: generate_qr_code without api_exempt
- **WHEN** `generate_qr_code` view is defined
- **THEN** it MUST NOT have `@api_exempt` decorator
- **AND** AuthMiddleware processes the request normally

#### Scenario: verify_otp_code without api_exempt
- **WHEN** `verify_otp_code` view is defined
- **THEN** it MUST NOT have `@api_exempt` decorator
- **AND** AuthMiddleware processes the request normally

### Requirement: OTP secret regeneration overwrites existing
The system SHALL overwrite existing OTP secret when generating a new QR code, invalidating previous authenticator bindings.

#### Scenario: Regenerate QR code for user with existing OTP
- **WHEN** user with existing OTP binding calls `generate_qr_code`
- **THEN** system generates new `otp_secret`
- **AND** overwrites the previous `otp_secret`
- **AND** previous authenticator app binding becomes invalid
- **AND** user must scan new QR code to rebind
