## Why

Built-in monitor plugins currently derive `collector` and `collect_type` from their filesystem path, and the importer overwrites any values that may appear in `metrics.json`. This makes the second directory level part of the plugin runtime identity, so future plugin directory cleanup, especially for large SNMP vendor families, risks changing runtime behavior.

## What Changes

- Add an explicit monitor plugin identity resolution contract: `metrics.json` values for `collector` and `collect_type` take precedence when present.
- Preserve backward compatibility by falling back to the existing path-based parser when explicit identity fields are absent.
- Keep plugin template discovery rooted at the `metrics.json` directory; `UI.json`, `policy.json`, and `*.j2` files continue to live beside each plugin.
- Add import-time validation or clear diagnostics when the final resolved identity conflicts with `UI.json` or config template `collect_type` declarations.
- Keep existing plugin directories unchanged in this phase; no SNMP vendor directories are migrated by this change.
- Avoid new database tables, new registry services, or frontend/API behavior changes.

## Capabilities

### New Capabilities
- `monitor-plugin-directory-identity`: Defines how monitor plugin import resolves `collector` and `collect_type` independently from the plugin directory layout while preserving legacy path fallback.

### Modified Capabilities

None.

## Impact

- Affected backend code: `server/apps/monitor/management/services/plugin_migrate.py` and shared path helper usage in `server/apps/monitor/management/utils.py`.
- Affected command: `server/apps/monitor/management/commands/plugin_init.py` through its existing `migrate_plugin()` call.
- Affected assets: future monitor plugin `metrics.json` files may explicitly declare `collector` and `collect_type`; existing files do not need bulk edits.
- Affected tests: targeted monitor plugin importer tests for explicit identity precedence, path fallback, metadata/template consistency diagnostics, and idempotent repeated import.
