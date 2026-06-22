## 1. Identity Resolution Contract

- [x] 1.1 Add a focused helper in the monitor plugin migration layer that resolves `collector` and `collect_type` from `metrics.json` first and path fallback second.
- [x] 1.2 Normalize empty strings and missing fields so partial explicit identity can safely fall back per field.
- [x] 1.3 Update plugin import logging to include the final resolved `collector` and `collect_type`.

## 2. Import Flow Integration

- [x] 2.1 Replace unconditional path-based identity overwrite in `_import_plugins_from_files` with the new resolver.
- [x] 2.2 Ensure `MonitorPluginService.import_monitor_plugin` receives plugin data with the final resolved identity.
- [x] 2.3 Confirm template collection still uses the `metrics.json` parent directory for `UI.json` and `*.j2` files.
- [x] 2.4 Confirm built-in plugin cleanup continues to use stable `plugin` names and does not depend on directory-derived `collect_type`.

## 3. Consistency Diagnostics

- [x] 3.1 Add validation for adjacent `UI.json` `collector` and `collect_type` values against the final resolved identity.
- [x] 3.2 Add validation for literal `collect_type = "..."` declarations in adjacent config templates against the final resolved `collect_type`.
- [x] 3.3 Make validation failures file-specific and explicit enough to identify the conflicting source and values.
- [x] 3.4 Decide strict failure vs warning-first behavior in code and align tests with the selected behavior.

## 4. Tests

- [x] 4.1 Add unit coverage for explicit `collector` and `collect_type` taking precedence over path-derived values.
- [x] 4.2 Add unit coverage for legacy path fallback when identity fields are absent.
- [x] 4.3 Add unit coverage for partial explicit identity fallback per missing field.
- [x] 4.4 Add coverage for a plugin under `Telegraf/snmp/<plugin>` importing as an explicit vendor `collect_type`.
- [x] 4.5 Add coverage for `UI.json` and config template identity mismatch diagnostics.
- [x] 4.6 Add idempotency coverage showing repeated import updates the same plugin and does not duplicate templates, metric groups, or metrics.

## 5. Verification

- [x] 5.1 Run the targeted monitor plugin importer tests.
- [x] 5.2 Run the existing monitor plugin asset consistency tests impacted by SNMP plugin metadata.
- [x] 5.3 Run the server-side minimum gate for this backend change, or document any environment blocker.
- [x] 5.4 Manually verify no existing plugin directory migration or bulk `metrics.json` metadata churn was introduced.

## Verification Notes

- `uv run pytest apps/monitor/tests/test_plugin_migrate_identity.py` passed: 8 passed.
- `DJANGO_SETTINGS_MODULE=settings uv run python ...` validated 100 existing plugin assets with the new identity resolver and strict validation.
- `uv run pytest apps/monitor/tests/test_*plugin.py --no-cov -q` ran; current repository state has 879 passed and 6 unrelated plugin asset failures.
- `uv run pytest apps/monitor/tests --no-cov --maxfail=1 -q` ran; current repository state stops on an unrelated existing 403 in `test_display_fields_api.py::test_save_display_fields_sets_customized`.
- No existing plugin directories or bulk `metrics.json` metadata files were migrated for this change.
