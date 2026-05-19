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
