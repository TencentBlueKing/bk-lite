# Webhook Private-Deployment Whitelist Support

Status: ready

## Problem Statement

The notification channel ("群聊小助手") currently rejects any webhook URL whose hostname isn't in a hard-coded 4-entry allowlist (`qyapi.weixin.qq.com`, `open.feishu.cn`, `open.larksuite.com`, `oapi.dingtalk.com`). For enterprises running private deployments of these IM platforms (private WeCom, on-prem DingTalk, internal Feishu instances), the webhook URL uses a custom domain that fails the check, even when the underlying IP is legitimate and the admin has explicitly configured the channel.

The same restriction also applies to `send_by_custom_webhook`, blocking admins from configuring arbitrary business-system callbacks until a domain can be added to the allowlist — but no UI surface exists to do so, because the allowlist lives in code constants, not configuration.

## Solution

Move the webhook allowlist from a code constant into the existing `NetworkWhiteList` model so admins can configure both CIDR ranges and trusted domains through the UI. Migrate the four official IM domains into the table on first deploy with a `is_build_in` flag that prevents accidental deletion. Expand `is_valid_webhook_url()` to accept:

1. Hostname equal to an entry in `NetworkWhiteList.domain` (string match, case-insensitive)
2. Every IP resolved from the hostname falls within an entry in `NetworkWhiteList.network` (CIDR match)
3. Hostname equal to a row marked `is_build_in=True` (preserves existing behaviour for official domains)

All webhook call sites (`send_by_wecom_bot`, `send_by_feishu_bot`, `send_by_dingtalk_bot`, `send_by_custom_webhook`) use the same validator. The previous constant `WEBHOOK_ALLOWED_DOMAINS` is removed; the table is the single source of truth.

The "测试" (test) button on the channel dialog continues to call the same backend validator. When validation fails it returns a short, non-leaking error; the server log captures the unresolved hostname and IP list so operators can audit.

## User Stories

1. As an admin running a private WeCom deployment, I want to add my internal webhook domain (`corp-wecom.example.com`) to the system whitelist, so that the channel "测试" button no longer rejects a legitimate webhook URL.

2. As an admin configuring a custom webhook to an internal business system whose host resolves to a private IP (e.g. `10.x.x.x`), I want to add that IP range as a CIDR entry, so that the custom webhook channel validates without me having to repackage the server.

3. As an operator triaging a failed channel test, I want the server log to record which hostname and which resolved IP did not match the whitelist, so that I can identify the right entry to add.

4. As a system administrator, I want the four official IM domains (WeCom, Feishu, Lark, DingTalk) to be pre-populated in the whitelist on first deploy and protected from accidental deletion, so that I do not need to manually add them and cannot accidentally break official webhook channels.

5. As a security reviewer, I want `0.0.0.0/0` and `::/0` entries rejected at the model layer, so that no admin (including a compromised or mistaken admin account) can disable the entire SSRF protection by mistake.

## Implementation Decisions

### Model change (`NetworkWhiteList`)

- Add `domain` field: `CharField(max_length=255, null=True, blank=True, db_index=True)` storing the lowercase hostname; uniqueness enforced at the serializer layer together with `network`.
- Add `is_build_in` field: `BooleanField(default=False, db_index=True)`.
- Migration keeps the existing `network` and `remark` fields intact; no destructive change to existing rows.
- The migration that adds `domain` is a separate additive migration (no data backfill required, as existing CIDR rows continue to function).
- `network_whitelist_cache.py` returns both `cidrs` and `domains` lists so the validator does not need a second DB hit. Add a parallel getter; cache key can be extended or split.

### Serializer change (`NetworkWhiteListSerializer`)

- `validate_network` continues to normalise CIDR and reject `0.0.0.0/0` / `::/0` (existing behaviour, see `test_network_white_list_serializer_pure.py`).
- Add `validate_domain` that:
  - lowercases and trims input
  - rejects values containing `*`, leading dots, `@`, `/`, or whitespace
  - rejects any value that already exists as another row's `network` or `domain`
  - rejects `0.0.0.0/0` form even if pasted into the wrong field
- Model-level `save`/`update`: rows with `is_build_in=True` cannot be modified via `update` / `partial_update` and cannot be `destroy`ed. Enforce in the viewset (a check on `get_object().is_build_in`); the serializer's `read_only_fields` include `is_build_in` so the client cannot flip it.

### Viewset change (`NetworkWhiteListViewSet`)

- In `update` and `destroy`, return `403` if the target row has `is_build_in=True`. The error message references the built-in name so the operator understands why the action is blocked.
- `perform_create` and existing `invalidate_network_whitelist_cache()` calls remain in place; they now invalidate the extended cache (domains + cidrs).

### Validator change (`is_valid_webhook_url`)

- The constant `WEBHOOK_ALLOWED_DOMAINS` is removed.
- The function expands to:
  1. Reject malformed URLs (existing logic: scheme, backslash, userinfo, hostname character set, encoding — see `test_webhook_validation.py`).
  2. Lowercase the hostname.
  3. Check hostname against `get_network_whitelist_domains()` set (with `is_build_in` rows included implicitly).
  4. If step 3 misses, resolve the hostname via `socket.getaddrinfo()` and check every returned IP against `get_network_whitelist_cidrs()`.
  5. If any IP falls inside a whitelisted CIDR, accept. Otherwise reject.
- DNS resolution is performed every call. DNS-rebinding risk for entries added as `domain` is accepted: the admin explicitly added the hostname, so they own the consequence. CIDR matches still resolve on every send to defeat DNS pinning against rebinding.
- On reject, log `hostname` and the unresolved IP list at `WARNING` level; return a generic short message via the existing `{"result": False, "message": ...}` contract.

### Data migration (`0035_init_webhook_builtin_whitelist.py`)

- New migration depends on the field-add migration.
- Uses `RunPython` with `get_or_create` to insert the four official domains (`qyapi.weixin.qq.com`, `open.feishu.cn`, `open.larksuite.com`, `oapi.dingtalk.com`) with `is_build_in=True`, `enabled=True`.
- Idempotent: re-running the migration is a no-op.
- `network` field is left empty for these rows (the model's `network` CharField is non-null with no default; the migration must either allow blank/null or pass a sentinel — decision: make `network` `blank=True` and rely on serializer cross-field validation rather than tightening the DB constraint, so existing rows are untouched).

### Call-site change

- `send_by_wecom_bot`, `send_by_feishu_bot`, `send_by_dingtalk_bot`, `send_by_custom_webhook` already share `is_valid_webhook_url`; no per-call edits required.
- The error messages returned to the UI become uniform ("webhook domain or IP not in whitelist") regardless of channel type.

### Cache

- `network_whitelist_cache.py` exposes two functions:
  - `get_network_whitelist_cidrs()` (existing, unchanged contract)
  - `get_network_whitelist_domains()` (new, returns list of lowercase hostnames)
- Both share a single cache key (`NETWORK_WHITELIST_CACHE_KEY`) and TTL (300s). The cached payload becomes a tuple `(cidrs, domains)` for one round-trip per call.
- Write paths (create / update / destroy in the viewset) call `invalidate_network_whitelist_cache()` once; the existing test `test_get_network_whitelist_cidrs_returns_enabled_only` keeps passing.

### Frontend

- Channel "测试" dialog surfaces the existing short error message; no UI change required for the happy path. The webhook URL input does not change.
- "Network White List" admin page (existing UI) gains a `domain` input alongside `network`; the serializer marks them mutually exclusive (one must be present, both cannot). The page only displays custom entries; `is_build_in` rows remain active in the backend and are hidden from the management UI.
- Locale files (`web/src/app/system-manager/locales/zh.json` / `en.json`) gain two new keys: `notInWhitelist` ("webhook 域名或 IP 不在白名单") and `builtinEntryProtected` ("内置条目不可修改").

## Testing Decisions

Tests assert external behaviour, not implementation. The validator stays a pure function over (url, cache contents) where possible, so existing `test_webhook_validation.py` patterns continue to apply.

### Unit tests (`apps/system_mgmt/tests/test_webhook_validation.py`)

- Existing test classes (`TestWebhookValidURLs`, `TestWebhookBlockedDomains`, `TestWebhookBypassAttempts`, `TestWebhookInvalidInputs`, `TestWebhookCaseInsensitivity`, `TestWebhookEdgeCases`) keep passing with a fixture-provided whitelist.
- New classes:
  - `TestWebhookNetworkWhitelistCIDRMatch`: hostname resolves to an IP inside a whitelisted CIDR → accept. Outside → reject. Mixed (one IP in, one out) → reject.
  - `TestWebhookNetworkWhitelistDomainMatch`: hostname exactly equals a whitelisted domain → accept (DNS resolution skipped). Different case → accept (lowercase comparison). Different hostname → fall through to CIDR check.
  - `TestWebhookBuiltinDomains`: the four official domains auto-seeded by the migration are accepted; admin attempts to delete them raise `PermissionDenied`.
- The fixture provides a stub for `get_network_whitelist_cidrs` / `get_network_whitelist_domains` so tests do not touch the DB.

### Unit tests (`apps/system_mgmt/tests/test_network_whitelist_serializer_pure.py`)

- Add cases for `validate_domain`:
  - Lowercase normalisation.
  - Reject `*`, `@`, `/`, leading dot, whitespace.
  - Reject empty / null.
  - Reject domain that duplicates an existing `network` or `domain` row.
- `is_build_in` field must be in `read_only_fields` — covered by inspecting `NetworkWhiteListSerializer.Meta.read_only_fields`.

### Migration test

- `apps/system_mgmt/tests/test_init_builtin_whitelist.py`: run the `0035` migration forward and assert that the four official domains exist with `is_build_in=True` and `enabled=True`. Run it twice; second run is a no-op.

### Integration tests

- `test_send` endpoint (`channel_viewset.test_send`) for each channel type — mock `requests.post`, assert the validator rejects unknown URLs and accepts URLs whose host resolves to a CIDR-allowed IP. Use `unittest.mock.patch` on `socket.getaddrinfo` to make resolution deterministic.
- `NetworkWhiteListViewSet.destroy` / `update` integration test: attempting to delete or modify a `is_build_in=True` row returns `403` and the row remains in the DB.

### Manual acceptance checklist (run on a staging environment before merge)

1. Fresh deploy: `python manage.py migrate` creates the four built-in rows. They remain active in the backend but are not displayed in the management UI.
2. Add a custom domain `corp-wecom.example.com` via the UI. Configure a channel pointing at `https://corp-wecom.example.com/hook`. Click "测试" → success.
3. Configure a custom channel whose host resolves to a private IP `10.x.x.x`. Add `10.x.x.0/24` to the whitelist. Test → success.
4. Attempt to delete a built-in row through the API directly (`DELETE /api/system_mgmt/network_white_list/<id>/`) → 403. Row still in DB.
5. Server log on a rejected webhook: contains the failed hostname and the unresolved IP list (use a custom domain pointing to `127.0.0.1` to trigger).

## Out of Scope

- Pinning resolved IPs at channel-creation time to defeat DNS rebinding for `domain` entries (rejected: admins who add a `domain` entry accept the rebinding risk themselves).
- Per-tenant or per-channel whitelist scope (the table is currently global; per-tenant scoping is a separate change).
- Replacing `NetworkWhiteList` as a general SSRF allowlist with a more granular policy DSL.
- Notification when a built-in domain migrates (e.g. WeCom adds a new official endpoint); that flows through a future migration update.
- Frontend wiring for "auto-add failed IP to whitelist" or one-click approval flows; the "测试" button only reports failure.

## Further Notes

- Migration ordering matters: the field-add migration must run before `0035` so the `domain` and `is_build_in` columns exist when `RunPython` runs. The new field-add migration should depend on `0034_networkwhitelist`.
- Backward compatibility: existing `NetworkWhiteList` rows (CIDR-only) continue to function; no data migration needed for them. Their `domain` column will be `NULL`, which the validator tolerates.
- The cache module's payload change (tuple of `(cidrs, domains)`) is backward-incompatible at the cache-key level; deploys with warm caches must flush, or the validator can defensively handle the old shape on first read.
- The `WEBHOOK_ALLOWED_DOMAINS` constant is removed in this change; downstream tests that import it (`test_webhook_validation.py`) must be updated to import from the fixture or omit the `TestWebhookAllowedDomains` class. The fixture seeds the four built-ins so the assertion shape remains "domain is reachable", not "constant exists".
