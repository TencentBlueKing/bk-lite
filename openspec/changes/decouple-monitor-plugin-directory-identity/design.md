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
