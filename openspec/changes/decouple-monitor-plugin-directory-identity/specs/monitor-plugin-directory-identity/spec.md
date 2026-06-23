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
