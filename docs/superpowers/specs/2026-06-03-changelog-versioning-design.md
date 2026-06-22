# Changelog Versioning Design

## Context

BK-Lite has two product lines in one delivery workflow:

- Community edition lives in the main `bklite` repository tree.
- Enterprise edition lives as an overlay under `enterprise/`. During enterprise packaging, files under `enterprise/` replace files at the repository root.

The existing release-note workflow uses `docs/changelog/release.md` as the manually maintained source and generates Markdown files under `web/src/app/*/public/versions/*/{zh,en}`. The new design keeps `release.md` as the only manual changelog input, but separates community date-based logs from enterprise monthly release logs.

## Goals

- Community edition uses the release date as the version identifier.
- Enterprise edition uses formal monthly versions, starting with `3.1` for May 2026.
- The same `release.md` source can generate both product lines.
- Enterprise-only date blocks can be marked in `release.md`.
- Enterprise logs are written into the `enterprise/web` overlay with the same path shape as community logs.
- Existing `3.1.x` standard files are archived instead of deleted during the first migration.

## Source Format

`docs/changelog/release.md` remains the only file edited manually.

Date blocks use two forms:

```text
2026.5.29
```

This is a default block. It is included in both community and enterprise logs.

```text
[商业版] 2026.6.5
```

This is an enterprise-only block. It is included in enterprise logs and excluded from community logs.

The enterprise-only marker applies to the whole date block. Item-level enterprise markers are out of scope for this design.

## Version Rules

### Community

Community edition uses dates as versions.

- File name: `YYYY-MM-DD.md`
- Title: `# YYYY年M月D日 更新日志`
- Release date line: `版本发布时间：YYYY年M月D日`
- Default date blocks are included.
- `[商业版]` date blocks are excluded.

Community standard logs are written to:

```text
docs/changelog/release/community/YYYY-MM-DD.md
```

Community module logs are written to:

```text
web/src/app/<module>/public/versions/<module>/zh/YYYY-MM-DD.md
web/src/app/<module>/public/versions/<module>/en/YYYY-MM-DD.md
```

Community logs keep the existing product-documentation sentence:

```text
了解更多产品能力，欢迎查阅[官方文档](https://www.bklite.ai)或直接体验[Demo环境](https://bklite.canway.net)
```

### Enterprise

Enterprise edition uses monthly formal versions.

- `3.1` corresponds to May 2026.
- Later natural months increment the minor version: June 2026 is `3.2`, July 2026 is `3.3`, and so on.
- Major version changes are manual decisions. AI must not switch from `3.x` to `4.x` unless the user explicitly says the major version has changed.
- Default blocks and `[商业版]` blocks both participate in enterprise month aggregation.

Enterprise standard logs are written to:

```text
docs/changelog/release/enterprise/3.1.md
```

Enterprise module logs are written to the overlay:

```text
enterprise/web/src/app/<module>/public/versions/<module>/zh/3.1.md
enterprise/web/src/app/<module>/public/versions/<module>/en/3.1.md
```

Enterprise standard files are Chinese only. English files are generated only for enterprise module logs.

Enterprise logs do not include the product-documentation sentence used by community logs.

## Enterprise Aggregation

Enterprise monthly logs aggregate all date blocks in the same natural month.

The output is grouped by feature category, then by module. It does not keep date subheadings.

Example Chinese standard file:

```md
# 3.1 版本日志
版本发布时间：2026年5月

### 功能新增

| 模块 | 新增功能 |
| --- | --- |
| CMDB | 支持手动上传配置文件 |

### 功能优化

| 模块 | 功能优化 |
| --- | --- |
| 系统管理 | 优化 admin 账号密码到期机制 |
```

Example English module file:

```md
# 3.1 Release Notes
Release Month: May 2026

### New Features

| Module | New Features |
| --- | --- |
| CMDB | Supports manually uploading configuration files. |

### Improvements

| Module | Improvements |
| --- | --- |
| System Management | Optimized the admin account password expiration mechanism. |
```

Aggregation rules:

- Read date blocks in chronological order within a month.
- Keep separate rows for separate changelog items.
- Deduplicate exact repeated items in the same month.
- Preserve the existing "new feature" and "improvement" split.
- `ops-console` receives all modules.
- Other modules receive only rows matching the module mapping.

## Module Mapping

The existing module mapping remains:

- `ops-console`: all modules.
- `system-manager`: `系统管理`.
- `monitor`: `监控系统`, `监控中心`, `监控管理`.
- `log`: `日志系统`, `日志中心`, `日志管理`.
- `node-manager`: `节点管理`.
- `cmdb`: `CMDB`, `cmdb`.
- `alarm`: `告警中心`.
- `job`: `作业管理`.
- `ops-analysis`: `运营分析`.
- `opspilot`: `OpsPilot`, `OpsPilot 模块`.
- `mlops`: `MLOps`.

English module names must be standardized in generated English files.

## Migration And Archival

The first run of the new workflow migrates the old standard-file shape.

Move old standard files:

```text
docs/changelog/release/3.1.x.md
```

to:

```text
docs/changelog/release/legacy/3.1.x.md
```

Create:

```text
docs/changelog/release/community/
docs/changelog/release/enterprise/
```

Community web directories must no longer contain old `3.1.x.md` files. They should be regenerated as date files:

```text
web/src/app/<module>/public/versions/<module>/<zh|en>/YYYY-MM-DD.md
```

Enterprise web directories are created under `enterprise/web` using the same path shape and monthly version files.

The enterprise packaging pipeline will clean the community `web` changelog directories before applying the `enterprise` overlay. The AI workflow does not manage packaging cleanup; it only writes enterprise logs into `enterprise/web`.

## AI Workflow Changes

`docs/changelog/ai-release-workflow.md` should be updated so AI follows this sequence:

1. Read `docs/changelog/release.md`.
2. Identify default date blocks and `[商业版]` date blocks.
3. Read existing community standard files and enterprise standard files.
4. Generate missing community date standard files from default blocks.
5. Generate or update enterprise monthly standard files from default and enterprise-only blocks.
6. Sync community standard files to `web/src/app`.
7. Sync enterprise standard files to `enterprise/web/src/app`.
8. Generate complete English module files.
9. Validate file names, dates, module filtering, enterprise month mapping, and English output.

The workflow document must explicitly state:

```text
商业版 3.1 对应 2026年5月。
后续自然月递增。
大版本升级必须由用户明确说明，AI 不得自行切换。
```

## Validation

Each update must verify:

- Community standard files exist for default date blocks.
- Enterprise standard files include default and `[商业版]` blocks for the target month.
- `[商业版]` blocks do not appear in community files.
- Community file names use `YYYY-MM-DD.md`.
- Enterprise file names use formal monthly versions such as `3.1.md`.
- May 2026 maps to `3.1`; June 2026 maps to `3.2`.
- `ops-console` includes all modules.
- Module-specific files include only matching modules.
- English module files contain no Chinese characters.
- Enterprise files do not contain the product-documentation sentence.
- Old `3.1.x.md` standard files exist only under `docs/changelog/release/legacy/`.
- Community web version directories no longer contain old `3.1.x.md` files after migration.

## Out Of Scope

- Adding a generator script.
- Changing `release.md` into JSON, YAML, or another structured format.
- Supporting item-level enterprise-only markers.
- Automatically deciding major version upgrades.
- Managing the enterprise packaging cleanup step in the AI workflow.
