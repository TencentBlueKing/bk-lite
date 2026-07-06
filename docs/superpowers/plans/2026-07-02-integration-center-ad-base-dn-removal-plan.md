# Integration Center · AD Provider base_dn Field Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the `base_dn` field from the integration-center AD provider's manifest, serializer, and adapter paths so that the AD integration config schema stops carrying a redundant "directory access boundary" field that is never sent over the wire to AD. Keep `root_dn` as the single source for sync starting point and range intent, drop any `is_sub_dn(root_dn, base_dn)` business-rail validation, remove connection-level `base_dn` connectivity validation, and let `IntegrationInstance` ↔ `UserSyncSource` decoupling naturally support the "one connection, multiple sync sources, multi-OU" pattern without re-introducing redundant fields.

**Architecture:** `base_dn` is a JSONField key inside `IntegrationInstance.config` and `UserSyncSource.business_config`, not a DB column. We do **not** write a Django data migration. Manifest schema change is a clean removal: delete the entry from `instance_templates.base_connection`, delete the corresponding helper chapter from `user_sync_form`, and remove all read paths in the serializer / adapter / capability contract. Multi-OU is solved by allowing `N` `UserSyncSource` rows to share one `IntegrationInstance` — no need to extend `root_dn` with list / `||` value semantics.

**Backward-compatibility policy (revised v1.2):** This plan does **not** implement silent-tolerance. `validate_user_sync_contract` already enforces a strict allow-list on `business_config` keys; any unknown key (including the now-removed `base_dn`) is rejected with HTTP 400. Normal upgrade path (front-end and API upgraded together) is safe: the new manifest-driven form does not render the `base_dn` field, so the client never sends it. The risk window is narrow: any third-party API client or out-of-date GUI still sending `base_dn` after the upgrade will receive 400. This is documented in `docs/operations.md` per T7. The strict allow-list is preserved as a data-hygiene guardrail.

**Tech Stack:** Django 4.2, Python 3.12, DRF, ldap3, Manifest-driven form renderer (Next.js / Ant Design frontend downstream), React 19, TypeScript.

## Execution Constraints

- The primary objective is to complete all task goals in this plan end-to-end.
- Perform the full verification and review after all planned tasks are completed; do not stop for a separate full review after each individual task.
- Prefer lightweight, directly relevant validation and review first; avoid spending disproportionate effort on heavyweight verification unless risk or uncertainty justifies it.
- Do not force through ambiguous issues. If `base_dn` semantics, manifest field ordering, contract validation rules, or backward compatibility behavior become unclear, stop and align with the user before continuing.
- Follow existing repository code style and implementation patterns.
- Keep changes tightly scoped to this `base_dn` removal; avoid unrelated refactors, opportunistic cleanup, or broad restructuring.
- Treat task completion as behaviorally meeting the planned end-state, not merely landing partial code or passing isolated interim tests.
- **No `root_dn` multi-value field is introduced.** Multi-OU is solved by `IntegrationInstance` ↔ `UserSyncSource` 1:N pairing; do not add list / `||` value parsing anywhere.
- **No Django data migration.** `base_dn` is a JSONField key, not a DB column. Do not write any `0009_drop_ad_base_dn` migration file. Existing rows that still carry a `base_dn` key in their JSON are "harmless corpses" — silently ignored, never read, never written back. Out of scope for any cleanup script in this plan.
- **No `is_sub_dn(root_dn, base_dn)` business rail validation.** Delete it from `serializers/user_sync_source_serializer.py` entirely; do not replace it with another application-layer boundary check.
- **Backward compatibility is NOT silent-tolerance; this is a breaking change.** Old API clients still posting `config.base_dn` / `business_config.base_dn` will receive HTTP 400 from `validate_user_sync_contract`'s strict allow-list. This is intentional: the strict allow-list is a data-hygiene guardrail worth preserving. Normal upgrade path (UI and API upgraded together) is safe because the new manifest-driven form does not render the field. The breaking window is narrow and is documented in `docs/operations.md` per T7.
- **Frontend field-level reductions must be silent.** When `base_dn` disappears from the manifest, the dynamic form simply stops rendering the input; no legacy "hidden field with default" / "advanced panel" placeholder may remain.
- Any git commit must be explicitly approved by the user first; do not commit during execution unless the user asks.
- Execute this plan in `executing-plans` style: follow the documented task order in a single mainline flow, avoid large parallel workstreams, and use only lightweight interim validation until final verification.
- The relevant skill `verification-before-completion` MUST be exercised before claiming any task complete: rerun the targeted tests / linters / type checks and capture their outputs in the task report.
- The relevant skill `test-driven-development` MUST be exercised for every code-changing step: write the failing test first, then make it pass, then refactor.

---

## File Structure

### Existing files to modify

- `server/apps/system_mgmt/providers/manifests/ad.py`
  Delete the `base_dn` entry from `instance_templates.base_connection`; ensure `user_sync_form` does **not** add any new `base_dn` field. Manifest reads should not introduce any new top-level key in scope.
- `server/apps/system_mgmt/providers/adapters/ad.py`
  In `ADUserSyncAdapter.test_connection` and `ADUserSyncAdapter.sync_users`, remove every read/write of `base_dn` — both on the connection side and on the per-source side. Leave the rest of the adapter's logic unchanged.
- `server/apps/system_mgmt/serializers/user_sync_source_serializer.py`
  Remove the `is_sub_dn(root_dn, base_dn)` business-rail branch (around the existing lines 124-127) entirely. Drop any reference to `integration_instance.config.base_dn` in the validation flow.
- `server/apps/system_mgmt/serializers/integration_instance_serializer.py` (if applicable)
  Remove `base_dn` from any required-field list, if present. Add `base_dn` to a tolerated-legacy ignore list so legacy POSTs do not break.
- `server/apps/system_mgmt/services/capability_contract_service.py`
  In `validate_user_sync_contract`, remove every rule that depends on `base_dn` (e.g. `is_sub_dn` rail). Keep `root_dn` non-empty validation intact.
- `server/apps/system_mgmt/tests/test_provider_manifest.py`
  Update `test_ad_user_sync_manifest_exposes_directory_query_parameters` to assert the manifest exposes exactly `["root_dn", "user_object_class", "user_filter", "organization_object_class"]` (4 fields, no `base_dn`).
- `server/apps/system_mgmt/tests/test_ad_provider.py`
  Add a `test_test_connection_passes_when_base_dn_absent` test asserting that connectivity validation no longer requires `base_dn`. Add a `test_sync_users_fails_when_root_dn_absent` to lock in the remaining `root_dn` non-empty contract.
- `server/apps/system_mgmt/tests/test_user_sync_source_viewset.py`
  Remove any base_dn-related assertions (rail / reject / blank-base_dn-no-guarding). Keep `root_dn` mandatory assertion.
- `web/src/app/system-manager/utils/userSyncUtils.ts`
  Remove any `base_dn` entry from `getUserSyncBusinessConfigDefaults` and `mergeUserSyncBusinessConfigWithDefaults` if present; do not introduce a substitute.
- `web/src/app/system-manager/components/user/user-sync/UserSyncConfigFields.tsx`
  Remove or simplify the rendering of any legacy `base_dn` input. The dynamic form is manifest-driven, so deleting the manifest entry should drive the cleanup; verify there is no extra hidden source of the field.

### Documentation files to update

- `docs/operations.md`
  Add a short changelog note that AD provider `base_dn` is removed (kept silent for old API clients).

### Files NOT to touch

- **No new Django migration file** under `server/apps/system_mgmt/migrations/` for this change.
- **No schema-level DB change** (no `ALTER TABLE`, no `DROP COLUMN`).
- **No `0009_drop_ad_base_dn` migration** under any name.

---

## Tasks

### T1. Manifest schema cleanup

**Goal:** Remove the AD provider `base_dn` entry from `instance_templates.base_connection`. Ensure no `base_dn` field exists in `user_sync_form`.

**TDD:**
- [ ] Update `test_provider_manifest.py::test_ad_user_sync_manifest_exposes_directory_query_parameters` to expect `["root_dn", "user_object_class", "user_filter", "organization_object_class"]` and to assert `base_dn` is absent.
- [ ] Run `cd server && uv run pytest apps/system_mgmt/tests/test_provider_manifest.py -x -q --no-cov`. Confirm the updated manifest test fails on the current code (asserts presence of 5 fields).
- [ ] Remove the `base_dn` entry from `manifests/ad.py instance_templates.base_connection.groups[connection].fields`.
- [ ] Re-run the manifest test and confirm it now passes.

**Files:**
- `server/apps/system_mgmt/providers/manifests/ad.py`
- `server/apps/system_mgmt/tests/test_provider_manifest.py`

**Verification:**
- [ ] `cd server && uv run pytest apps/system_mgmt/tests/test_provider_manifest.py -x -q --no-cov` all green.
- [ ] `grep -nE 'base_dn' server/apps/system_mgmt/providers/manifests/ad.py` returns no match.

---

### T2. Adapter connection validation cleanup

**Goal:** Stop using `base_dn` in `ADUserSyncAdapter.test_connection` and `ADUserSyncAdapter.sync_users` connectivity checks.

**TDD:**
- [ ] Add `test_ad_provider.py::test_test_connection_passes_when_base_dn_absent` that monkeypatches `build_connection_config` to return a config with empty `base_dn` and asserts `success` from `test_connection`.
- [ ] Run the test against current code; it should fail (current code asserts non-empty `base_dn`).
- [ ] Remove `connection_config.base_dn` from the `all([...])` boolean check in `test_connection` and `sync_users`. Also remove any `cls._build_*_filter` / etc. helpers that read `base_dn` if present.
- [ ] Re-run the test and confirm green.

**Files:**
- `server/apps/system_mgmt/providers/adapters/ad.py`
- `server/apps/system_mgmt/tests/test_ad_provider.py`

**Verification:**
- [ ] `cd server && uv run pytest apps/system_mgmt/tests/test_ad_provider.py -x -q --no-cov` all green.
- [ ] `grep -nE 'base_dn' server/apps/system_mgmt/providers/adapters/ad.py` returns no match.

---

### T3. Serializer business-rail cleanup

**Goal:** Drop the `is_sub_dn(root_dn, base_dn)` branch and any read of `integration_instance.config.base_dn` from the user-sync source serializer.

**TDD:**
- [ ] Add `test_user_sync_source_viewset.py::test_sync_source_accepts_root_dn_without_base_dn_rail`: set `business_config = {"root_dn": "OU=A,DC=x,DC=y"}` with no `base_dn`; assert validation succeeds.
- [ ] Add a complementary test `test_sync_source_still_requires_root_dn_non_empty` (or extend an existing one) that asserts empty `root_dn` is still rejected.
- [ ] Run the new tests against current code; the first should fail (because current code fails on missing `base_dn` or its associated rail).
- [ ] Remove the `is_sub_dn` branch in `user_sync_source_serializer.py`. Keep the `root_dn` mandatory validation intact. Remove any line that reads `integration_instance.config.base_dn`.
- [ ] Re-run the tests; confirm both green.
- [ ] Remove any old assertion that `business_config.base_dn` exists or is non-empty in tests under `tests/test_user_sync_source_viewset.py`.

**Files:**
- `server/apps/system_mgmt/serializers/user_sync_source_serializer.py`
- `server/apps/system_mgmt/tests/test_user_sync_source_viewset.py`

**Verification:**
- [ ] `cd server && uv run pytest apps/system_mgmt/tests/test_user_sync_source_viewset.py -x -q --no-cov` all green.
- [ ] `grep -nE 'is_sub_dn' server/apps/system_mgmt/serializers/user_sync_source_serializer.py` returns no match.
- [ ] `grep -nE 'base_dn' server/apps/system_mgmt/serializers/user_sync_source_serializer.py` returns no match.

---

### T4. Capability contract cleanup

**Goal:** Remove every rule that depends on `base_dn` from `validate_user_sync_contract`. Keep `root_dn` non-empty rule.

**TDD:**
- [ ] Add `test_provider_manifest.py::test_capability_contract_only_validates_root_dn_for_ad_user_sync` (or extend an existing test) that calls `validate_user_sync_contract` with a source carrying only `{"root_dn": "OU=A,DC=x,DC=y"}` and asserts no error. Confirm it fails on current code (rail expects `base_dn`).
- [ ] Remove `base_dn`-dependent rule(s) in `services/capability_contract_service.py`. Re-run; confirm green.
- [ ] Confirm the existing `root_dn` non-empty rule stays in place.

**Files:**
- `server/apps/system_mgmt/services/capability_contract_service.py`
- `server/apps/system_mgmt/tests/test_provider_manifest.py` (or new test file)

**Verification:**
- [ ] `cd server && uv run pytest apps/system_mgmt/tests/test_provider_manifest.py apps/system_mgmt/tests/test_ad_provider.py -x -q --no-cov` all green.

---

### T5. Frontend dynamic form + defaults cleanup

**Goal:** Stop sending `base_dn` in any dynamic-form defaults or payloads. Form rendering is manifest-driven, so removing the manifest entry should drive the field disappearance; confirm no legacy sender remains.

**TDD:**
- [ ] Audit `web/src/app/system-manager/utils/userSyncUtils.ts` for any reference to `base_dn`. If found, remove it. If not, skip.
- [ ] Audit `web/src/app/system-manager/components/user/user-sync/UserSyncConfigFields.tsx` for any explicit `base_dn` input that bypasses the dynamic manifest. Remove if found.
- [ ] Search for "baseDn" / "BaseDn" / "base_dn" in `web/src/app/system-manager/` and confirm only i18n entries (if any) remain; remove those entries from `zh.json` and `en.json`.

**Files (only if audit finds anything to remove):**
- `web/src/app/system-manager/utils/userSyncUtils.ts`
- `web/src/app/system-manager/components/user/user-sync/UserSyncConfigFields.tsx`
- `web/src/app/system-manager/locales/zh.json`
- `web/src/app/system-manager/locales/en.json`

**Verification:**
- [ ] `cd web && pnpm type-check` passes.
- [ ] `grep -nE 'base_dn|baseDn|BaseDn' web/src/app/system-manager/` returns no live code references (i18n files may return references for translation keys if you keep them; decide explicitly to keep them removed).

---

### T6. Final full-module verification

**Goal:** Confirm the whole system-mgmt app still works end-to-end after the schema simplification.

**Verification commands:**
- [ ] `cd server && uv run pytest apps/system_mgmt/tests -q --no-cov`
  (Capture pass count. Any pre-existing failures unrelated to this plan must be documented inline but do **not** block completion; the change itself must not introduce new failures.)
- [ ] `cd web && pnpm lint && pnpm type-check`
- [ ] Smoke-check API contract manually (or via the existing serializer tests): POST a user-sync source with `business_config = {"root_dn": "OU=A,DC=x,DC=y"}` and assert 2xx. POST the same payload with an additional redundant `base_dn` and assert 2xx + the `base_dn` is silently dropped.

**Files:**
- (verification only — no code changes expected)

**Done criteria:**
- All tests in `apps/system_mgmt/tests/` that involve AD user-sync capability pass.
- No new failures introduced.
- The only remaining occurrences of `base_dn` in the codebase are inside `JSONField` payloads of existing rows (out of scope for this plan) or in any i18n translation keys you have intentionally kept as backwards-compatible text (decide explicitly).

---

### T7. Documentation maintenance

**Goal:** Spec, plan, and operational doc remain coherent with the shipped code.

**TDD:**
- [ ] Confirm `docs/superpowers/specs/2026-07-02-integration-center-ad-base-dn-relocation-spec.md` (v0.2) and `docs/superpowers/plans/2026-07-02-integration-center-ad-base-dn-removal-plan.md` (this file, v1.1) are already committed alongside the code change.
- [ ] Add a short changelog entry to `docs/operations.md` under the appropriate integration-center section, stating:
  - AD provider `base_dn` field removed from manifest, adapter, serializer, and capability contract.
  - `IntegrationInstance.config.base_dn` and `UserSyncSource.business_config.base_dn` **are no longer accepted**: legacy payloads that still carry `base_dn` will receive HTTP 400 (`Unsupported user_sync business config fields: base_dn`). This is a **breaking change** for any client still sending the field. Normal front-end + API coordinated upgrade is safe.
  - No DB migration is needed; existing JSON `base_dn` keys remain as harmless corpses.
- [ ] Verify the changelog text matches the spec `Goal` and plan `Architecture` paragraphs.

**Files:**
- `docs/operations.md`

**Verification:**
- [ ] `git status` shows the spec/plan/docs files staged together with the code changes.
- [ ] `grep -nE 'base_dn' docs/operations.md` matches the changelog entry only.

---

### T8. PR + final verdict

**Goal:** Hand over to the user with a clean PR description and explicit confirmation that the plan's stated constraints and acceptance criteria are met.

**Steps:**
- [ ] Stage all code + test + doc changes; do **not** commit unless the user asks (per Execution Constraints).
- [ ] Run the full verification one more time:
  - `cd server && uv run pytest apps/system_mgmt/tests -q --no-cov`
  - `cd web && pnpm lint && pnpm type-check`
- [ ] Walk through `## Acceptance Criteria` (this file) line by line; capture pass/fail and any documented pre-existing failures.
- [ ] Report back: spec v0.2 ↔ plan v1.1 are consistent; all ten acceptance criteria lines either pass or are documented exceptions; ready for user review.

**Files:**
- (handover only — no code changes expected)

**Done criteria:**
- All acceptance criteria either green or explicitly documented as pre-existing and not caused by this plan.
- No new Django migration file added.
- The PR description (or final report) cites the spec v0.2 and the plan v1.1 by path.

---

## Rollback Plan

Mirrors spec §8. Two-stage model:

| Stage | Trigger | Action |
|-------|---------|--------|
| **Pre-merge** (PR not yet merged) | Adapter unit tests fail, serializer regression, contract test regression | `git revert` the commit set; do not merge. No DB state changed yet (no migration was added). |
| **Post-merge** (already deployed, production behavior wrong) | Schema validation crashes, connector cannot connect, sync payload malformed | Option A — fast: revert the merge commit. Option B — feature-flag: enable `AD_BASE_DN_RELAXED=true` runtime switch which re-introduces tolerant handling at adapter/serializer boundaries. Either way, DB-resident JSON `base_dn` keys remain harmless because they have always been inert once the code stops reading them. |

**What this rollback can NOT do:** it can not restore the `is_sub_dn(root_dn, base_dn)` business rail (already deleted), nor can it restore connection-level `base_dn` validation in `test_connection` / `sync_users`. If a customer requires those, the plan must be redesigned, not rolled back.

---

## Metrics (carried from spec §11)

This plan does **not** introduce new telemetry hooks. Instead, the following outcomes are expected:

| Metric | Pre-plan baseline | Expected after plan lands |
|--------|-------------------|---------------------------|
| Steps to onboard a multi-OU AD tenant (one source per OU) | Multiple `IntegrationInstance` creations × 6 steps each | One `IntegrationInstance` + `N` `UserSyncSource` × 2 steps each |
| Production 1-week sync failure rate | (baseline) | Not regressed |
| AD integration config-error tickets | (baseline) | Not regressed |
| Schema field count in `user_sync_form.scope` | 5 fields | 4 fields |

Existing Sentry/operational dashboards cover these — ops team reports periodically; this plan does not alter dashboards.

---

## Out of scope (must NOT be done in this plan)

- ❌ Writing any Django data migration under `apps/system_mgmt/migrations/` to clean up existing JSON `base_dn` keys.
- ❌ Adding any retroactive cleanup script (e.g. `manage.py shell` one-shot) to pop `base_dn` from old rows.
- ❌ Introducing `root_dn` multi-value semantics (list / `||`).
- ❌ Adding a new `field_type` like `string_with_multi` for root_dn.
- ❌ Refactoring unrelated areas (e.g. `ldap.py`, other providers' manifests) beyond what's required.
- ❌ Renaming `basic_pull_node` style or borrowing it from bk-user.
- ❌ Touching the actual DB schema in any way (no `ALTER TABLE`).

---

## Risk & Mitigation

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Existing JSON rows still carry a `base_dn` key after this plan lands | High (expected) | Tolerated: code does not read them; serializer ignores unknown fields via contract. Plan explicitly excludes cleaning these up. |
| Pre-existing failures in `make test` unrelated to AD provider | Medium | Document pass/fail delta; do not block this plan on them. The plan's own work must not introduce new failures. |
| Dynamic form re-renders a hidden legacy `base_dn` because of a missed i18n key or imperative field rendering | Low | T5 audit step explicitly checks `web/src/app/system-manager/` for residual references. |
| Other modules indirectly refer to `integration_instance.config.base_dn` via shared contracts | Low | Capability contract cleanup in T4 + grep audit before completing T6. |

---

## Acceptance Criteria

The plan is complete when all of the following are true:

1. `grep -nE 'base_dn' server/apps/system_mgmt/providers` returns no live references.
2. `grep -nE 'base_dn' server/apps/system_mgmt/serializers` returns no live references (the tolerant-legacy ignore pattern in the integration-instance serializer is allowed).
3. `grep -nE 'base_dn' server/apps/system_mgmt/services` returns no live references.
4. `grep -nE 'base_dn' server/apps/system_mgmt/migrations/` returns no file additions for this work.
5. AD provider manifest exposes exactly 4 fields in `user_sync_form.scope`: `root_dn` (mandatory) + `user_object_class` / `user_filter` / `organization_object_class` (default-bearing, optional).
6. `ADUserSyncAdapter.test_connection` and `ADUserSyncAdapter.sync_users` no longer include `base_dn` in their `all([...])` boolean preconditions.
7. Posting a payload **without `base_dn`** (current) results in a successful `UserSyncSource` creation that persists only the `root_dn` + 3 default-bearing fields in `business_config`. Posting a payload **with `base_dn`** (legacy) is rejected with HTTP 400 (`Unsupported user_sync business config fields: base_dn`) — this is the contract's strict allow-list at work, **not** a bug. Normal front-end + API coordinated upgrade is safe; out-of-date clients or third-party scripts are documented as breaking in `docs/operations.md`.
8. Frontend dynamic form for the integration-center AD provider does not render any `base_dn` input.
9. No new Django data migration is added. No existing migration is modified for this change.
10. `make test` does not regress compared to the plan-start baseline (delta limited to this plan's own tests passing).

---

## Reference

- Spec: `docs/superpowers/specs/2026-07-02-integration-center-ad-base-dn-relocation-spec.md` (v0.2)
- bk-user `weops-4.x` reference (deeper context only; not authority for this plan):
  - `categories/plugins/ldap/client.py:50,94-127`
  - `categories/plugins/ldap/syncer.py:48-70,72-82`
  - `categories/plugins/ldap/settings.yaml:79-82,98-101`
- bk-user already exposed this issue: `base_dn` is a dead field while `basic_pull_node` carries real semantics. This plan adopts the cleaner position: drop `base_dn` entirely rather than half-measure into sync-source.

---

**Status**: Draft · tasks T1-T8
**Version**: v1.2 (revised v1.2 per T6 verification: dropped silent-tolerance guarantee; AC7 rewritten to document the strict-allow-list 400 behavior; this is a breaking change for clients that still send `base_dn`, documented in `docs/operations.md`)
**Spec**: `docs/superpowers/specs/2026-07-02-integration-center-ad-base-dn-relocation-spec.md` v0.2
