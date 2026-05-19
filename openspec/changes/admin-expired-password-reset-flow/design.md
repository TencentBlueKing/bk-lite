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
