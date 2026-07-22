# Decouple Monitor Plugin Directory Identity

Status: done

## Migration Context

- Legacy source: `openspec/changes/decouple-monitor-plugin-directory-identity/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

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

## Implementation Decisions

## Context

The monitor plugin importer recursively finds built-in plugin `metrics.json` files under `server/apps/monitor/support-files/plugins` and the enterprise plugin directory. It currently extracts `collector` and `collect_type` from the path shape `plugins/<collector>/<collect_type>/<plugin>/metrics.json`, then overwrites the loaded plugin data before calling `MonitorPluginService.import_monitor_plugin`.

That path convention works for existing stable families such as `Telegraf/database/mysql` and `Telegraf/middleware/nginx`, but it makes the second directory level part of runtime identity. SNMP vendor plugins now occupy many top-level `snmp_*` collect type directories, and future plugin families could hit the same maintenance pressure. Current repository inspection shows existing community `metrics.json` files do not declare `collector` or `collect_type`, so compatibility fallback is required.

## Goals / Non-Goals

**Goals:**
- Allow `metrics.json` to explicitly declare `collector` and `collect_type`.
- Preserve existing plugin import behavior when explicit identity fields are absent.
- Keep plugin initialization idempotent across repeated `plugin_init` runs.
- Surface clear diagnostics when resolved plugin identity conflicts with adjacent plugin assets.
- Keep the change localized to monitor plugin import and validation logic.

**Non-Goals:**
- Do not migrate existing SNMP vendor directories.
- Do not require existing plugin files to add `collector` or `collect_type`.
- Do not add database tables or introduce a plugin registry service.
- Do not change collector runtime packaging, config delivery, frontend permissions, navigation, CMDB, alerting, or node management behavior.
- Do not support arbitrary-depth plugin directories in this phase; the existing three-level plugin scan remains the compatibility baseline.

## Decisions

### 1. Resolve identity through one helper

Introduce a single helper in the monitor plugin migration layer that receives `file_path` and loaded `plugin_data`, then returns the final `(collector, collect_type)` identity.

Resolution order:
1. Parse `(collector_from_path, collect_type_from_path)` using the existing path parser.
2. Use non-empty `plugin_data["collector"]` when present; otherwise use `collector_from_path`.
3. Use non-empty `plugin_data["collect_type"]` when present; otherwise use `collect_type_from_path`.
4. Store the final values back into `plugin_data` before import.

**Rationale**: This removes the hard dependency on the second directory level while preserving every existing plugin file. Keeping the logic in one helper prevents import, cleanup, and validation code from growing slightly different interpretations.

**Alternative considered**: Require all built-in `metrics.json` files to declare identity. This is cleaner long-term but would create broad metadata churn because existing files currently rely on path fallback.

### 2. Keep path fallback indefinitely for existing plugins

The path parser remains supported for plugins that do not declare explicit identity. No existing built-in plugin directory needs to move or add identity fields for this change.

**Rationale**: The immediate product value is unblocking future directory organization. Requiring a bulk metadata migration would couple a low-risk importer fix with many unrelated asset edits.

**Alternative considered**: Add identity fields to all existing `metrics.json` files in the same change. This would make the contract visible everywhere but increases review cost and the chance of accidental plugin metadata drift.

### 3. Validate final identity against local assets

After identity resolution, the importer should compare the final `collector` and `collect_type` with adjacent `UI.json` declarations when present. Config templates should be scanned for literal `collect_type = "..."` declarations and compared to the final `collect_type`.

Validation should emit clear file-specific diagnostics and fail the affected plugin import when an inconsistency would make runtime behavior ambiguous. If the implementation chooses warning-first rollout for existing assets, warnings must still include the final identity, conflicting value, and source file.

**Rationale**: Once directory layout stops being the only source of identity, inconsistent metadata becomes the main failure mode. Failing early is much cheaper than discovering mismatched collector config after deployment.

**Alternative considered**: Trust `metrics.json` completely and skip cross-file checks. This minimizes code but allows a plugin to import successfully while its UI or child template still emits a different `collect_type`.

### 4. Preserve plugin identity keying by plugin name

Existing import uses `MonitorPlugin.objects.update_or_create(name=plugin, ...)`, and cleanup uses the set of plugin names present in built-in directories. This change does not alter that stable key.

**Rationale**: The issue requires directory movement to update the same plugin rather than create a duplicate. Keeping `plugin` as the stable identity means changing explicit `collector` or `collect_type` updates the existing plugin record, while moving a directory without changing `plugin` does not create another plugin.

**Alternative considered**: Key by `(collector, collect_type, plugin)`. That would make runtime identity part of the database uniqueness contract and would create duplicate risks when correcting metadata.

## Risks / Trade-offs

- [Risk: Existing assets contain hidden identity mismatches] -> Mitigation: add targeted consistency tests and run importer tests before enabling strict failure; repository inspection currently shows no path-based `UI.json` or template `collect_type` mismatches.
- [Risk: Explicit identity typo changes runtime behavior] -> Mitigation: validate against `UI.json` and template declarations; include final identity in import logs.
- [Risk: Users expect arbitrary nested directories after "directory decoupling"] -> Mitigation: document that this phase only decouples the second-level identity requirement while keeping the current three-level scan.
- [Risk: Cleanup deletes moved plugins if plugin names change] -> Mitigation: scope acceptance to moves that preserve the `plugin` field; changing `plugin` remains a rename and should be handled as a separate migration.

## Migration Plan

1. Add identity resolution and validation helpers.
2. Update plugin import to use the helper instead of unconditionally overwriting `collector` and `collect_type` from the path.
3. Ensure template processing and cleanup continue using the same plugin name set and local plugin directory.
4. Add tests for legacy fallback, explicit identity precedence, consistency diagnostics, and repeated import idempotency.
5. Deploy without moving existing plugin directories.

Rollback is straightforward: revert the importer change. Existing plugin files and database schema are unchanged, and legacy path fallback remains compatible throughout.

## Open Questions

None for phase A. Directory migration batches and broader directory taxonomy should be handled by later changes after the importer contract is in place.

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-06-22
```

## Capability Deltas

### monitor-plugin-directory-identity

## ADDED Requirements

### Requirement: Monitor plugin import uses explicit identity first
The monitor plugin importer SHALL resolve a built-in plugin's `collector` and `collect_type` from explicit non-empty fields in `metrics.json` before using path-derived values.

#### Scenario: Explicit collector and collect_type are present
- **WHEN** a built-in plugin `metrics.json` includes non-empty `collector` and `collect_type` fields
- **THEN** the importer SHALL use those explicit values as the final plugin identity
- **AND** the importer SHALL NOT overwrite them with values derived from the directory path

#### Scenario: Explicit collect_type differs from the second directory level
- **WHEN** a plugin file is located under `plugins/Telegraf/snmp/<plugin>/metrics.json`
- **AND** its `metrics.json` declares `collector` as `Telegraf` and `collect_type` as `snmp_a10`
- **THEN** the imported `MonitorPlugin` SHALL have `collector=Telegraf` and `collect_type=snmp_a10`

### Requirement: Legacy plugins continue using path fallback
The monitor plugin importer SHALL preserve current behavior for built-in plugins whose `metrics.json` files omit `collector` or `collect_type`.

#### Scenario: No explicit identity fields
- **WHEN** a built-in plugin `metrics.json` does not include `collector` or `collect_type`
- **THEN** the importer SHALL derive `collector` and `collect_type` from the existing path parser

#### Scenario: Partial explicit identity
- **WHEN** a built-in plugin `metrics.json` includes only one of `collector` or `collect_type`
- **THEN** the importer SHALL use the explicit non-empty field
- **AND** the importer SHALL derive the missing field from the existing path parser

### Requirement: Plugin identity consistency is checked during import
The monitor plugin importer SHALL detect conflicts between the final resolved plugin identity and identity declarations in adjacent plugin assets.

#### Scenario: UI identity matches resolved identity
- **WHEN** adjacent `UI.json` declares the same `collector` and `collect_type` as the resolved plugin identity
- **THEN** the importer SHALL allow the plugin import to continue

#### Scenario: UI collect_type conflicts with resolved identity
- **WHEN** adjacent `UI.json` declares a `collect_type` that differs from the resolved plugin `collect_type`
- **THEN** the importer SHALL emit a clear file-specific diagnostic
- **AND** the affected plugin import SHALL fail or be skipped rather than silently importing ambiguous identity

#### Scenario: Config template collect_type conflicts with resolved identity
- **WHEN** an adjacent config template contains a literal `collect_type = "<value>"` declaration that differs from the resolved plugin `collect_type`
- **THEN** the importer SHALL emit a clear file-specific diagnostic
- **AND** the affected plugin import SHALL fail or be skipped rather than silently importing ambiguous identity

### Requirement: Existing plugin directories are not migrated by identity decoupling
The directory identity decoupling change SHALL NOT require existing built-in plugin directories to move or existing `metrics.json` files to add identity fields.

#### Scenario: Current SNMP vendor directory remains unchanged
- **WHEN** an existing plugin remains under a current path such as `plugins/Telegraf/snmp_cisco/switch/metrics.json`
- **THEN** the importer SHALL continue importing it with the same resolved identity as before

### Requirement: Repeated plugin initialization remains idempotent
The monitor plugin importer SHALL keep `plugin_init` idempotent when explicit identity fields are introduced without changing the plugin's stable `plugin` name.

#### Scenario: plugin_init runs repeatedly after explicit identity is added
- **WHEN** `plugin_init` imports the same built-in plugin multiple times
- **AND** the plugin has the same `plugin` field and resolved identity on each run
- **THEN** the importer SHALL update the existing plugin record and templates
- **AND** it SHALL NOT create duplicate plugins, duplicate templates, duplicate metric groups, or duplicate metrics

#### Scenario: Directory moves while plugin name remains stable
- **WHEN** a built-in plugin is moved to another supported plugin directory location
- **AND** its `plugin` field and explicit identity remain stable
- **THEN** the importer SHALL update the same plugin record instead of creating a second plugin

## Work Checklist

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
