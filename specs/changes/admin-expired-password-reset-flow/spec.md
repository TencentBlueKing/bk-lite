# Admin Expired Password Reset Flow

Status: done

## Migration Context

- Legacy source: `openspec/changes/admin-expired-password-reset-flow/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

The current web username/password login flow blocks admin users completely when their password has expired. This conflicts with the requirement in `requirements.md` that expired admin accounts must be forced to set a new password before entering the product, including both the main login page and the small re-login window flow.

## What Changes

- Change the backend username/password login flow so that **only** the account whose username is `admin` stops hard-failing on expired password and instead enters the existing forced password reset flow.
- Reuse the current `temporary_pwd -> PasswordResetForm` flow instead of creating a new login path, so the main `/auth/signin` page and the session-expired modal both inherit the behavior through the shared `SigninClient` state machine.
- Preserve the existing OTP ordering so OTP-enabled admin users still complete OTP before being forced to reset the expired password.
- Keep non-admin expired-password behavior unchanged to minimize product and security impact.
- Keep Mobile behavior out of scope for this change; any current Mobile handling for `temporary_pwd` remains unchanged in this iteration.
- Update automated coverage for admin expired-password login, OTP interaction, and non-admin regression behavior.

## Capabilities

### New Capabilities
- `admin-expired-password-login`: Force the account whose username is `admin` to complete password reset during username/password login when the password is expired, before product access is granted across both full-page and modal login entry points.

### Modified Capabilities
- `otp-challenge-flow`: clarify that when the `admin` account password is expired, existing OTP sequencing is preserved and password reset is enforced after OTP succeeds.

## Impact

- Backend auth logic in `server/apps/system_mgmt/nats_api.py`
- Existing password reset API consumption through `web/src/app/(core)/auth/signin/PasswordResetForm.tsx`
- Shared web login flow in `web/src/app/(core)/auth/signin/SigninClient.tsx`
- Session-expired re-login modal in `web/src/context/auth.tsx`
- Login and OTP-related tests in `server/apps/system_mgmt/tests/test_otp_login_flow.py`
- Mobile login is intentionally not updated as part of this change and remains outside the documented impact scope.

## Implementation Decisions

## Context

`requirements.md` requires a behavior change only for admin username/password login: when the admin password is expired, login must not hard-fail, and the user must enter a new password before entering the product. The same requirement applies to the main login page and the smaller session-expired re-login window.

The current implementation already has a shared forced-password-reset path in Web:

- `SigninClient` drives a multi-step auth state machine for both full-page and modal login.
- `PasswordResetForm` already submits new password data to the existing reset endpoint.
- `OtpVerificationForm` already preserves the ordering `password -> OTP -> password reset if temporary_pwd`.
- `layout.tsx` already prevents `temporary_pwd` sessions from being treated as authenticated product access.

The current gap is in backend `login()`: password expiry returns `result=false` immediately, which prevents the frontend from entering the existing reset-password step.

The key constraint is minimal change scope. The new behavior must only apply to the account whose username is `admin` during username/password login. Expired-password behavior for every other account must remain unchanged. Existing routes and modal wiring should be preserved. Mobile is explicitly out of scope for this change and should remain at its current behavior.

## Goals / Non-Goals

**Goals:**
- Satisfy the requirement that expired admin users must reset password before entering the product.
- Reuse the existing `temporary_pwd -> PasswordResetForm` flow with minimal changes.
- Preserve current OTP sequencing for OTP-enabled admin users.
- Cover both `/auth/signin` and the session-expired modal without duplicating logic.
- Avoid introducing new public reset endpoints or new login routes.

**Non-Goals:**
- Changing expired-password behavior for non-admin users.
- Introducing a generic forgot-password or email-reset flow.
- Redesigning the login UI or replacing the shared `SigninClient` architecture.
- Changing third-party login behavior (WeChat/BK login).
- Extending or fixing Mobile-specific `temporary_pwd` handling.

## Decisions

### Decision 1: Handle expired `admin` account login by reusing `temporary_pwd`

**Choice:** In backend `login()`, when the password is expired and the user's username is `admin`, set `temporary_pwd=True` and continue through the existing token/challenge issuance path instead of returning `result=false`.

**Why:**
- This is the narrowest change that fits the current architecture.
- The frontend already understands `temporary_pwd` and routes to `PasswordResetForm` in both page mode and modal mode.
- Existing session gating already prevents `temporary_pwd` users from entering the product before password reset completes.

**Alternatives considered:**
- **New unauthenticated expired-password reset endpoint**: cleaner separation, but requires new endpoint design, new frontend flow, extra security review, and separate modal handling.
- **New dedicated `password_expired` login state**: more explicit, but still requires parallel frontend flow changes and extra wiring across OTP, page mode, and modal mode.

### Decision 2: Limit the new behavior to the `admin` account only

**Choice:** Treat only the account whose username is exactly `admin` as eligible for the new expired-password-to-reset flow.

**Why:**
- Matches the current requested scope around the special `admin` account.
- Minimizes blast radius.
- Avoids silently changing behavior for other administrator accounts or ordinary users.

**Alternatives considered:**
- **Apply to all expired-password users**: simpler overall model, but violates the requested boundary of minimal scoped behavior change.
- **Use a broader administrator-role definition**: broader than the current requested scope because it would include other superuser accounts besides `admin`.

### Decision 3: Preserve current OTP ordering

**Choice:** Keep existing sequencing: password verification first, OTP second if enabled, then forced reset if `temporary_pwd=true`.

**Why:**
- This matches the current `SigninClient` and `OtpVerificationForm` behavior.
- Existing OpenSpec material for `otp-challenge-flow` already establishes that OTP completes before the forced reset path for `temporary_pwd` users.
- Changing ordering would expand both backend and frontend scope and could weaken existing guarantees.

**Alternatives considered:**
- **Reset before OTP for expired `admin` users**: would require bypassing current token/challenge assumptions and likely introduce a separate reset credential model.

### Decision 4: Keep existing routes and modal wiring unchanged

**Choice:** Do not add or rename frontend routes or modal-specific auth paths.

**Why:**
- Both the main login page and the small re-login window already share `SigninClient`.
- Reusing the same component state machine ensures requirement coverage for both entry points with a single behavior change.
- The current requested scope explicitly focuses on the Web entry points and does not require Mobile flow changes in this iteration.

**Alternatives considered:**
- **Special modal-specific expired-password flow**: unnecessary duplication and higher maintenance cost.

### Decision 5: Leave Mobile behavior unchanged in this iteration

**Choice:** Do not modify Mobile login or Mobile password-reset handling as part of this change.

**Why:**
- The stated requirement for this fix is limited to the main Web login page and the session-expired re-login window.
- Expanding the change into Mobile would increase scope beyond the requested minimal fix.
- Documenting this boundary keeps the current implementation and expected review scope aligned.

**Alternatives considered:**
- **Update Mobile to complete the same forced-reset flow**: potentially desirable later, but out of scope for this change.

## Risks / Trade-offs

- **[Persistent `temporary_pwd` state before successful reset]** → If the `admin` account abandons the flow after triggering expired-password handling, future logins will continue forcing reset. This is acceptable because the requirement is to block product access until reset completes.
- **[Semantic overload of `temporary_pwd`]** → The flag will represent both admin-assigned temporary passwords and admin password-expiry enforcement. Mitigation: keep the behavior identical and treat wording refinement as optional follow-up.
- **[Regression risk for non-admin expiry behavior]** → Mitigation: add explicit tests proving non-admin expired-password login still hard-fails.
- **[Special-account assumption drift]** → Mitigation: explicitly check `username == "admin"` in the implementation and document the operational assumption in the spec.
- **[Password reset endpoint dependency]** → The flow assumes the existing reset endpoint remains valid for `temporary_pwd` users after token/challenge issuance. Mitigation: verify with focused regression coverage for direct and OTP paths.
- **[Cross-client behavior differences]** → The backend login API is shared by more than Web, but this change intentionally documents only the Web main login page and session-expired modal as in scope. Mobile remains unchanged by design for this iteration.

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-19
```

## Capability Deltas

### admin-expired-password-login

## ADDED Requirements

### Requirement: Expired `admin` account password enters forced reset flow during username/password login
When the account whose username is `admin` logs in with correct username and password and the password is expired, the system SHALL require password reset before allowing access to the product instead of hard-failing the login.

#### Scenario: Expired `admin` account password on main login page
- **WHEN** the user whose username is `admin` submits correct username and password on the main web login page
- **AND** the user's password is expired according to `pwd_set_validity_period`
- **THEN** the system SHALL continue into the existing forced password reset flow
- **AND** the user SHALL be required to enter a new password before product access is granted

#### Scenario: Expired `admin` account password on re-login window
- **WHEN** the user whose username is `admin` submits correct username and password in the session-expired re-login window
- **AND** the user's password is expired according to `pwd_set_validity_period`
- **THEN** the system SHALL continue into the existing forced password reset flow
- **AND** the user SHALL be required to enter a new password before product access is granted

#### Scenario: Password reset not completed
- **WHEN** the user whose username is `admin` has entered the forced password reset flow because the password is expired
- **AND** the user has not successfully completed password reset yet
- **THEN** the system SHALL continue preventing access to product pages

### Requirement: Non-`admin` expired-password behavior remains unchanged
The system SHALL keep existing expired-password behavior for every account whose username is not `admin`.

#### Scenario: Expired non-`admin` password
- **WHEN** a user whose username is not `admin` submits correct username and password
- **AND** the user's password is expired according to `pwd_set_validity_period`
- **THEN** the system SHALL reject the login with the existing expired-password failure behavior

### Requirement: This change is scoped to Web login entry points only
This change SHALL document and guarantee behavior only for the main Web login page and the session-expired re-login window. Mobile handling remains out of scope and unchanged in this iteration.

#### Scenario: Mobile client behavior
- **WHEN** the Mobile client uses the same backend login API
- **THEN** this change SHALL NOT be interpreted as requiring Mobile-specific reset-flow updates
- **AND** Mobile behavior SHALL remain outside the implementation scope of this change

### otp-challenge-flow

## MODIFIED Requirements

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

#### Scenario: Password correct, OTP enabled, `admin` account password expired
- **WHEN** the user whose username is `admin` submits correct username and password
- **AND** user has OTP enabled
- **AND** the password is expired according to `pwd_set_validity_period`
- **THEN** system SHALL preserve the existing OTP-first flow
- **AND** system returns a temporary `challenge_id`
- **AND** response preserves forced-reset state so password reset is required after OTP verification succeeds

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

#### Scenario: OTP succeeds for `admin` account with expired password
- **WHEN** the user whose username is `admin` submits valid `challenge_id` and correct `otp_code`
- **AND** the user's password-expired state was already converted into forced reset during login
- **THEN** the system SHALL issue the post-OTP response in a way that still requires password reset before product access

## Work Checklist

## 1. Backend login gating

- [x] 1.1 Update `server/apps/system_mgmt/nats_api.py` so only the account whose username is `admin` stops hard-failing on expired password and instead continues through the existing forced reset path.
- [x] 1.2 Use the `admin` username check when deciding whether the expired-password override applies.
- [x] 1.3 Keep expired-password login behavior for every other account unchanged.

## 2. Existing reset-flow compatibility

- [x] 2.1 Verify the admin-expired path reuses the current `temporary_pwd` flow for direct username/password login without adding new routes or endpoints.
- [x] 2.2 Verify OTP-enabled admin users still follow the current OTP-first sequence and are forced into password reset only after OTP succeeds.
- [x] 2.3 Verify the same shared `SigninClient` flow covers both the main login page and the session-expired modal re-login window.
- [x] 2.4 Document that this change only guarantees the Web main login page and session-expired modal flows; Mobile remains out of scope and unchanged in this iteration.

## 3. Regression coverage

- [x] 3.1 Update backend login tests to cover `username=admin + expired password` resulting in forced reset instead of hard failure.
- [x] 3.2 Add or update OTP coverage for `username=admin + expired password + OTP enabled` so the response still requires reset after OTP verification.
- [x] 3.3 Add or update regression coverage proving every other expired-password account still receives the existing login failure behavior.
