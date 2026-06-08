# Changelog Versioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update the changelog workflow so community release notes use date versions while enterprise release notes use monthly formal versions in the `enterprise/web` overlay.

**Architecture:** Keep `docs/changelog/release.md` as the single manual source and update `docs/changelog/ai-release-workflow.md` so AI performs parsing, migration, generation, module sync, and validation. Split standardized sources into `docs/changelog/release/community`, `docs/changelog/release/enterprise`, and `docs/changelog/release/legacy`.

**Tech Stack:** Markdown documentation, existing Next.js static Markdown version-note directories, Git file moves, `rg`/shell validation.

---

## File Structure

- Modify: `docs/changelog/ai-release-workflow.md`
  - Replace the old `3.1.x` weekly version rules with the new community date version and enterprise monthly version rules.
  - Document source markers, output paths, module mapping, migration, and validation.
- Create directory: `docs/changelog/release/community/`
  - Holds community standard Chinese release notes named `YYYY-MM-DD.md`.
- Create directory: `docs/changelog/release/enterprise/`
  - Holds enterprise standard Chinese release notes named `3.1.md`, `3.2.md`, and later monthly versions.
- Create directory: `docs/changelog/release/legacy/`
  - Holds archived old standard files named `3.1.x.md`.
- Modify: `web/src/app/<module>/public/versions/<module>/zh`
  - Remove old community `3.1.x.md` files and regenerate date files.
- Modify: `web/src/app/<module>/public/versions/<module>/en`
  - Remove old community `3.1.x.md` files and regenerate date files.
- Create or modify: `enterprise/web/src/app/<module>/public/versions/<module>/zh`
  - Generate enterprise monthly Chinese module release notes.
- Create or modify: `enterprise/web/src/app/<module>/public/versions/<module>/en`
  - Generate enterprise monthly English module release notes.

Do not modify `web/src/app/(core)/api/versions/route.ts` for this change. It already reads Markdown files from the active version directory and sorts names with numeric collation. Date file names such as `2026-05-29` and enterprise names such as `3.1` remain usable.

## Module List

Use these module paths and mappings for both community and enterprise generation:

| Module path | Matched source modules |
| --- | --- |
| `ops-console` | all modules |
| `system-manager` | `系统管理` |
| `monitor` | `监控系统`, `监控中心`, `监控管理` |
| `log` | `日志系统`, `日志中心`, `日志管理` |
| `node-manager` | `节点管理` |
| `cmdb` | `CMDB`, `cmdb` |
| `alarm` | `告警中心` |
| `job` | `作业管理` |
| `ops-analysis` | `运营分析` |
| `opspilot` | `OpsPilot`, `OpsPilot 模块` |
| `mlops` | `MLOps` |

## Task 1: Rewrite The AI Workflow Document

**Files:**
- Modify: `docs/changelog/ai-release-workflow.md`

- [ ] **Step 1: Open the current workflow**

Run:

```bash
sed -n '1,260p' docs/changelog/ai-release-workflow.md
```

Expected: The file still describes the old `docs/changelog/release/*.md` and `3.1.x.md` weekly version workflow.

- [ ] **Step 2: Replace the workflow with the new rules**

Use `apply_patch` to replace the full file with a document containing these sections in this order:

```md
# 更新日志维护工作流

当用户引用本文件，并要求“更新日志”时，按以下规则执行。

## 目标

完成四类产物：

1. 社区版标准日志：`docs/changelog/release/community/YYYY-MM-DD.md`
2. 商业版标准日志：`docs/changelog/release/enterprise/3.1.md`
3. 社区版模块日志：`web/src/app/<module>/public/versions/<module>/<zh|en>/YYYY-MM-DD.md`
4. 商业版模块日志：`enterprise/web/src/app/<module>/public/versions/<module>/<zh|en>/3.1.md`

## 总原则

- `docs/changelog/release.md` 是唯一人工维护的原始版本记录。
- 社区版以日期作为版本号，文件名为 `YYYY-MM-DD.md`。
- 商业版以自然月聚合为正式版本，`2026年5月 -> 3.1`，`2026年6月 -> 3.2`，后续自然月递增。
- 大版本升级必须由用户明确说明，AI 不得自行从 `3.x` 切换到 `4.x`。
- 默认日期块同时进入社区版和商业版。
- `[商业版] YYYY.M.D` 日期块只进入商业版，并参与该月商业版聚合。
- `[商业版]` 标识只支持日期行，不支持单条内容标识。
- 商业版按模块聚合当月内容，不按日期分组展示。
- 商业版标准文件只保留中文；英文只生成到商业版模块目录。
- 商业版标准文件和商业版模块文件不包含“了解更多产品能力...”文案。
- 社区版标准文件和社区版模块文件保留“了解更多产品能力...”文案。
- `ops-console` 是全量汇总页；其他模块只保留命中模块映射的内容。
- 英文版本必须完整翻译，不能出现中文正文残留。

## 日期块识别规则

### 默认日期块

```text
2026.5.29
```

进入社区版和商业版。

### 商业版专属日期块

```text
[商业版] 2026.6.5
```

只进入商业版，完全不进入社区版。

## 标准目录

- 社区版：`docs/changelog/release/community/`
- 商业版：`docs/changelog/release/enterprise/`
- 旧标准文件归档：`docs/changelog/release/legacy/`

## 首次迁移规则

- 将 `docs/changelog/release/3.1.x.md` 移动到 `docs/changelog/release/legacy/3.1.x.md`。
- 清理社区版 Web 目录下旧的 `3.1.x.md` 文件。
- 按新规则重新生成社区版日期文件和商业版月版本文件。

## 社区版文件格式

```md
# YYYY年M月D日 更新日志
版本发布时间：YYYY年M月D日
了解更多产品能力，欢迎查阅[官方文档](https://www.bklite.ai)或直接体验[Demo环境](https://bklite.canway.net)

### 功能新增

| 模块 | 新增功能 |
| --- | --- |
| 模块名 | 中文内容 |

### 功能优化

| 模块 | 功能优化 |
| --- | --- |
| 模块名 | 中文内容 |
```

## 商业版中文文件格式

```md
# 3.1 版本日志
版本发布时间：2026年5月

### 功能新增

| 模块 | 新增功能 |
| --- | --- |
| 模块名 | 中文内容 |

### 功能优化

| 模块 | 功能优化 |
| --- | --- |
| 模块名 | 中文内容 |
```

## 英文模块文件格式

社区版英文文件使用：

```md
# Month D, YYYY Release Notes
Release Date: Month D, YYYY
Learn more about product capabilities in the [official documentation](https://www.bklite.ai) or try the [Demo environment](https://bklite.canway.net).
```

商业版英文文件使用：

```md
# 3.1 Release Notes
Release Month: May 2026
```

## 输出目录

社区版输出目录：

- `web/src/app/ops-console/public/versions/ops-console/zh`
- `web/src/app/ops-console/public/versions/ops-console/en`
- `web/src/app/system-manager/public/versions/system-manager/zh`
- `web/src/app/system-manager/public/versions/system-manager/en`
- `web/src/app/monitor/public/versions/monitor/zh`
- `web/src/app/monitor/public/versions/monitor/en`
- `web/src/app/log/public/versions/log/zh`
- `web/src/app/log/public/versions/log/en`
- `web/src/app/node-manager/public/versions/node-manager/zh`
- `web/src/app/node-manager/public/versions/node-manager/en`
- `web/src/app/cmdb/public/versions/cmdb/zh`
- `web/src/app/cmdb/public/versions/cmdb/en`
- `web/src/app/alarm/public/versions/alarm/zh`
- `web/src/app/alarm/public/versions/alarm/en`
- `web/src/app/job/public/versions/job/zh`
- `web/src/app/job/public/versions/job/en`
- `web/src/app/ops-analysis/public/versions/ops-analysis/zh`
- `web/src/app/ops-analysis/public/versions/ops-analysis/en`
- `web/src/app/opspilot/public/versions/opspilot/zh`
- `web/src/app/opspilot/public/versions/opspilot/en`
- `web/src/app/mlops/public/versions/mlops/zh`
- `web/src/app/mlops/public/versions/mlops/en`

商业版输出目录：

- `enterprise/web/src/app/ops-console/public/versions/ops-console/zh`
- `enterprise/web/src/app/ops-console/public/versions/ops-console/en`
- `enterprise/web/src/app/system-manager/public/versions/system-manager/zh`
- `enterprise/web/src/app/system-manager/public/versions/system-manager/en`
- `enterprise/web/src/app/monitor/public/versions/monitor/zh`
- `enterprise/web/src/app/monitor/public/versions/monitor/en`
- `enterprise/web/src/app/log/public/versions/log/zh`
- `enterprise/web/src/app/log/public/versions/log/en`
- `enterprise/web/src/app/node-manager/public/versions/node-manager/zh`
- `enterprise/web/src/app/node-manager/public/versions/node-manager/en`
- `enterprise/web/src/app/cmdb/public/versions/cmdb/zh`
- `enterprise/web/src/app/cmdb/public/versions/cmdb/en`
- `enterprise/web/src/app/alarm/public/versions/alarm/zh`
- `enterprise/web/src/app/alarm/public/versions/alarm/en`
- `enterprise/web/src/app/job/public/versions/job/zh`
- `enterprise/web/src/app/job/public/versions/job/en`
- `enterprise/web/src/app/ops-analysis/public/versions/ops-analysis/zh`
- `enterprise/web/src/app/ops-analysis/public/versions/ops-analysis/en`
- `enterprise/web/src/app/opspilot/public/versions/opspilot/zh`
- `enterprise/web/src/app/opspilot/public/versions/opspilot/en`
- `enterprise/web/src/app/mlops/public/versions/mlops/zh`
- `enterprise/web/src/app/mlops/public/versions/mlops/en`

模块映射规则：

- `ops-console`：汇总所有模块内容。
- `system-manager`：模块名为 `系统管理`。
- `monitor`：模块名为 `监控系统`、`监控中心`、`监控管理`。
- `log`：模块名为 `日志系统`、`日志中心`、`日志管理`。
- `node-manager`：模块名为 `节点管理`。
- `cmdb`：模块名为 `CMDB`、`cmdb`。
- `alarm`：模块名为 `告警中心`。
- `job`：模块名为 `作业管理`。
- `ops-analysis`：模块名为 `运营分析`。
- `opspilot`：模块名为 `OpsPilot`、`OpsPilot 模块`。
- `mlops`：模块名为 `MLOps`。

## 执行顺序

1. 读取 `docs/changelog/release.md`。
2. 识别默认日期块和 `[商业版]` 日期块。
3. 首次迁移时归档旧标准文件并清理社区版 Web 旧文件。
4. 生成社区版标准文件。
5. 按自然月生成或更新商业版标准文件。
6. 从社区版标准文件同步到 `web/src/app`。
7. 从商业版标准文件同步到 `enterprise/web/src/app`。
8. 生成全部英文模块文件。
9. 运行校验。

## 校验规则

完成后至少校验以下内容：

1. 社区版标准文件是否覆盖所有默认日期块。
2. 商业版标准文件是否包含默认日期块和 `[商业版]` 日期块。
3. `[商业版]` 日期块内容是否没有进入社区版文件。
4. 社区版文件名是否全部为 `YYYY-MM-DD.md`。
5. 商业版文件名是否全部为 `大版本.小版本.md`，例如 `3.1.md`。
6. 商业版月份映射是否正确：`2026年5月 -> 3.1`、`2026年6月 -> 3.2`。
7. `ops-console` 是否包含全量内容。
8. 各模块文件是否只包含本模块命中的内容。
9. 英文模块文件是否不包含中文字符。
10. 商业版标准文件和商业版模块文件是否不包含“了解更多产品能力...”文案。
11. 旧 `3.1.x.md` 标准文件是否只存在于 `docs/changelog/release/legacy/`。
12. 社区版 Web 版本目录是否不再包含旧 `3.1.x.md` 文件。
```

- [ ] **Step 3: Check that no old wording remains**

Run:

```bash
rg -n "3\\.1\\.x|纯版本号|当前最大版本号|不能直接把" docs/changelog/ai-release-workflow.md
```

Expected: No output.

- [ ] **Step 4: Commit workflow doc update**

Run:

```bash
git add docs/changelog/ai-release-workflow.md
git commit -m "docs: update changelog workflow for community and enterprise"
```

Expected: Commit succeeds with only `docs/changelog/ai-release-workflow.md` staged.

## Task 2: Archive Old Standard Files

**Files:**
- Move: `docs/changelog/release/3.1.*.md`
- Create: `docs/changelog/release/legacy/`
- Create: `docs/changelog/release/community/`
- Create: `docs/changelog/release/enterprise/`

- [ ] **Step 1: Inspect old standard files**

Run:

```bash
find docs/changelog/release -maxdepth 1 -type f -name '3.1.*.md' | sort -V
```

Expected: Existing old weekly standard files are listed.

- [ ] **Step 2: Create new standard directories**

Run:

```bash
mkdir -p docs/changelog/release/community docs/changelog/release/enterprise docs/changelog/release/legacy
```

Expected: Command exits with status 0.

- [ ] **Step 3: Move old standard files into legacy**

Run:

```bash
for file in $(find docs/changelog/release -maxdepth 1 -type f -name '3.1.*.md' | sort -V); do
  git mv "$file" "docs/changelog/release/legacy/$(basename "$file")"
done
```

Expected: `docs/changelog/release/legacy/` contains the old `3.1.x.md` files and `docs/changelog/release/` no longer contains root-level `3.1.x.md` files.

- [ ] **Step 4: Verify archive state**

Run:

```bash
find docs/changelog/release -maxdepth 1 -type f -name '3.1.*.md'
find docs/changelog/release/legacy -maxdepth 1 -type f -name '3.1.*.md' | sort -V | tail
```

Expected: First command prints nothing. Second command prints legacy files.

- [ ] **Step 5: Commit standard-file archive**

Run:

```bash
git add docs/changelog/release
git commit -m "docs: archive legacy changelog standard files"
```

Expected: Commit succeeds and stages only files under `docs/changelog/release`.

## Task 3: Generate Community Standard Files

**Files:**
- Create: `docs/changelog/release/community/YYYY-MM-DD.md`

- [ ] **Step 1: Read source date blocks**

Run:

```bash
sed -n '1,260p' docs/changelog/release.md
```

Expected: Source date blocks are visible, including current dates such as `2026.5.22` and `2026.5.29`.

- [ ] **Step 2: Generate one community standard file per default date block**

Use `apply_patch` to create files named with ISO dates. For the existing May 29 block, create:

```text
docs/changelog/release/community/2026-05-29.md
```

with this structure:

```md
# 2026年5月29日 更新日志
版本发布时间：2026年5月29日
了解更多产品能力，欢迎查阅[官方文档](https://www.bklite.ai)或直接体验[Demo环境](https://bklite.canway.net)

### 功能新增

| 模块 | 新增功能 |
| --- | --- |
| CMDB | 支持手动上传配置文件 |
| CMDB | 支持查看配置文件不同版本内容，并进行差异对比 |
| 监控中心 | 告警通知渠道支持多选 |
| 日志中心 | 新增内置日志分析视图，覆盖常见数据库、中间件等 15 类场景 |
| 告警中心 | 新增告警级别管理能力，支持统一管理事件、告警、事故等级 |
| 告警中心 | 新增「相关告警推荐」能力，可通过相关性规则自动匹配并展示关联告警 |
| 运营分析 | 支持在单值、Top 等视图中展示周期相对变化，帮助快速识别趋势波动 |
| 运营分析 | 新增内置监控中心仪表板，快速掌握监控纳管情况 |
| OpsPilot | 新增记忆能力，支持在 workflow 中读取与写入记忆，帮助沉淀经验、复用上下文 |

### 功能优化

| 模块 | 功能优化 |
| --- | --- |
| 系统管理 | 优化 admin 账号密码到期机制：到期后不再直接锁定账号，登录时将强制引导修改密码 |
| 节点管理 | 修复 Windows 节点内置 Vector、Winlogbeat 异常问题 |
| 监控中心 | 修复主机节点因缺少 MIB 翻译器导致 SNMP 监控异常的问题 |
```

Create one `YYYY-MM-DD.md` file for every default date block in `docs/changelog/release.md`. Do not create a community standard file for any `[商业版]` date block.

- [ ] **Step 3: Verify community standard file names**

Run:

```bash
find docs/changelog/release/community -maxdepth 1 -type f -name '*.md' -print | sort
find docs/changelog/release/community -maxdepth 1 -type f -name '[[]商业版[]]*.md' -print
```

Expected: Community files are named `YYYY-MM-DD.md`. Second command prints nothing.

- [ ] **Step 4: Commit community standard files**

Run:

```bash
git add docs/changelog/release/community
git commit -m "docs: add community date changelog standards"
```

Expected: Commit succeeds and only community standard files are staged.

## Task 4: Generate Enterprise Standard Files

**Files:**
- Create: `docs/changelog/release/enterprise/3.1.md`
- Later months: `docs/changelog/release/enterprise/3.2.md`, `3.3.md`, and onward.

- [ ] **Step 1: Identify month-to-version mapping**

Use this mapping for the current implementation:

```text
2026-05 -> 3.1
2026-06 -> 3.2
2026-07 -> 3.3
```

For months after July 2026, increment the minor number by one per natural month until the user explicitly changes the major version.

- [ ] **Step 2: Generate the May 2026 enterprise standard file**

Use `apply_patch` to create:

```text
docs/changelog/release/enterprise/3.1.md
```

Aggregate all May 2026 default and `[商业版]` blocks. The file must use:

```md
# 3.1 版本日志
版本发布时间：2026年5月
```

It must not include:

```text
了解更多产品能力
```

Rows should be grouped under `### 功能新增` and `### 功能优化`, preserving module names and deduplicating exact duplicate items.

- [ ] **Step 3: Verify enterprise standard file format**

Run:

```bash
rg -n "了解更多产品能力" docs/changelog/release/enterprise
rg -n "^# 3\\.1 版本日志|^版本发布时间：2026年5月" docs/changelog/release/enterprise/3.1.md
```

Expected: First command prints nothing. Second command prints the heading and release month lines.

- [ ] **Step 4: Commit enterprise standard files**

Run:

```bash
git add docs/changelog/release/enterprise
git commit -m "docs: add enterprise monthly changelog standards"
```

Expected: Commit succeeds and only enterprise standard files are staged.

## Task 5: Regenerate Community Web Module Files

**Files:**
- Delete old: `web/src/app/*/public/versions/*/{zh,en}/3.1.*.md`
- Create: `web/src/app/*/public/versions/*/{zh,en}/YYYY-MM-DD.md`

- [ ] **Step 1: Remove old community web version files**

Run:

```bash
find web/src/app -path '*/public/versions/*/zh/3.1.*.md' -delete
find web/src/app -path '*/public/versions/*/en/3.1.*.md' -delete
```

Expected: Old `3.1.x.md` files are removed from community web version directories.

- [ ] **Step 2: Generate community module files from community standards**

For each file in `docs/changelog/release/community/*.md`, generate matching module files under `web/src/app`.

For `ops-console`, copy all rows from the community standard file.

For module-specific files, filter rows using the module mapping. If a date has no matching rows for a module, do not create that module/date file.

Use these community file formats:

```md
# 2026年5月29日 更新日志
版本发布时间：2026年5月29日
了解更多产品能力，欢迎查阅[官方文档](https://www.bklite.ai)或直接体验[Demo环境](https://bklite.canway.net)
```

```md
# May 29, 2026 Release Notes
Release Date: May 29, 2026
Learn more about product capabilities in the [official documentation](https://www.bklite.ai) or try the [Demo environment](https://bklite.canway.net).
```

- [ ] **Step 3: Verify community web file names and old-file cleanup**

Run:

```bash
find web/src/app -path '*/public/versions/*/zh/3.1.*.md' -o -path '*/public/versions/*/en/3.1.*.md'
find web/src/app -path '*/public/versions/*/zh/*.md' -o -path '*/public/versions/*/en/*.md' | rg '/[0-9]{4}-[0-9]{2}-[0-9]{2}\\.md$' | head
```

Expected: First command prints nothing. Second command prints date-based community files.

- [ ] **Step 4: Verify community English has no Chinese**

Run:

```bash
rg -n '[\p{Han}]' web/src/app/*/public/versions/*/en/*.md
```

Expected: No output.

- [ ] **Step 5: Commit community web module files**

Run:

```bash
git add web/src/app
git commit -m "docs: regenerate community date version logs"
```

Expected: Commit succeeds and only community web version files are staged.

## Task 6: Generate Enterprise Web Module Files

**Files:**
- Create: `enterprise/web/src/app/<module>/public/versions/<module>/zh/3.1.md`
- Create: `enterprise/web/src/app/<module>/public/versions/<module>/en/3.1.md`

- [ ] **Step 1: Create enterprise module directories**

Run:

```bash
for module in ops-console system-manager monitor log node-manager cmdb alarm job ops-analysis opspilot mlops; do
  mkdir -p "enterprise/web/src/app/$module/public/versions/$module/zh"
  mkdir -p "enterprise/web/src/app/$module/public/versions/$module/en"
done
```

Expected: All enterprise module version directories exist.

- [ ] **Step 2: Generate enterprise module files from enterprise standards**

For each file in `docs/changelog/release/enterprise/*.md`, generate matching module files under `enterprise/web/src/app`.

For `ops-console`, copy all rows from the enterprise standard file.

For module-specific files, filter rows using the module mapping. If a monthly version has no matching rows for a module, do not create that module/version file.

Use these enterprise file formats:

```md
# 3.1 版本日志
版本发布时间：2026年5月
```

```md
# 3.1 Release Notes
Release Month: May 2026
```

Do not include the community product-documentation sentence in any enterprise file.

- [ ] **Step 3: Verify enterprise web output**

Run:

```bash
find enterprise/web/src/app -path '*/public/versions/*/zh/3.1.md' -o -path '*/public/versions/*/en/3.1.md' | sort
rg -n "了解更多产品能力|official documentation|Demo environment" enterprise/web/src/app/*/public/versions/*/*.md
```

Expected: First command prints generated enterprise module files. Second command prints nothing.

- [ ] **Step 4: Verify enterprise English has no Chinese**

Run:

```bash
rg -n '[\p{Han}]' enterprise/web/src/app/*/public/versions/*/en/*.md
```

Expected: No output.

- [ ] **Step 5: Commit enterprise web module files**

Run:

```bash
git add enterprise/web/src/app
git commit -m "docs: add enterprise monthly version logs"
```

Expected: Commit succeeds and only enterprise web version files are staged.

## Task 7: Run End-To-End Validation

**Files:**
- Read: `docs/changelog/release.md`
- Read: `docs/changelog/release/community`
- Read: `docs/changelog/release/enterprise`
- Read: `web/src/app/*/public/versions`
- Read: `enterprise/web/src/app/*/public/versions`

- [ ] **Step 1: Validate root-level legacy archive**

Run:

```bash
find docs/changelog/release -maxdepth 1 -type f -name '3.1.*.md'
find docs/changelog/release/legacy -maxdepth 1 -type f -name '3.1.*.md' | wc -l
```

Expected: First command prints nothing. Second command prints a positive count.

- [ ] **Step 2: Validate community and enterprise naming**

Run:

```bash
find docs/changelog/release/community -maxdepth 1 -type f -name '*.md' | rg -v '/[0-9]{4}-[0-9]{2}-[0-9]{2}\\.md$'
find docs/changelog/release/enterprise -maxdepth 1 -type f -name '*.md' | rg -v '/[0-9]+\\.[0-9]+\\.md$'
```

Expected: Both commands print nothing.

- [ ] **Step 3: Validate enterprise marker exclusion from community**

Run:

```bash
rg -n "\\[商业版\\]" docs/changelog/release/community web/src/app/*/public/versions/*/*.md
```

Expected: No output.

- [ ] **Step 4: Validate enterprise files omit community product-documentation sentence**

Run:

```bash
rg -n "了解更多产品能力|official documentation|Demo environment" docs/changelog/release/enterprise enterprise/web/src/app/*/public/versions/*/*.md
```

Expected: No output.

- [ ] **Step 5: Validate English files**

Run:

```bash
rg -n '[\p{Han}]' web/src/app/*/public/versions/*/en/*.md enterprise/web/src/app/*/public/versions/*/en/*.md
```

Expected: No output.

- [ ] **Step 6: Validate working tree scope**

Run:

```bash
git status --short
```

Expected: Only changelog workflow, changelog standard files, community web version files, enterprise web version files, and known pre-existing unrelated changes are present.

## Task 8: Final Commit And Handoff

**Files:**
- All files changed by Tasks 1-7.

- [ ] **Step 1: Confirm no generated file violates naming rules**

Run:

```bash
find web/src/app -path '*/public/versions/*/*.md' | rg '/3\\.1\\.[0-9]+\\.md$'
find enterprise/web/src/app -path '*/public/versions/*/*.md' | rg '/[0-9]{4}-[0-9]{2}-[0-9]{2}\\.md$'
```

Expected: Both commands print nothing.

- [ ] **Step 2: Commit any remaining implementation files**

Run:

```bash
git add docs/changelog web/src/app enterprise/web/src/app
git commit -m "docs: migrate changelog versioning"
```

Expected: Commit succeeds if previous tasks left any staged implementation changes. If all previous task commits already captured the changes, Git reports no changes to commit.

- [ ] **Step 3: Summarize the result**

Report:

```text
Community logs now use date versions under docs/changelog/release/community and web/src/app.
Enterprise logs now use monthly versions under docs/changelog/release/enterprise and enterprise/web/src/app.
Legacy 3.1.x standard files are archived under docs/changelog/release/legacy.
Validation commands passed.
```
