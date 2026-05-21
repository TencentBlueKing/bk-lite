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
