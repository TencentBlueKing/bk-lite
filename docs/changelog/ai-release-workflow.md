# 更新日志维护工作流

当用户引用本文件，并要求“更新日志”时，按以下规则执行。

## 目标

完成两件事：

1. 检查 `docs/changelog/release.md` 是否有尚未同步的新版本内容。
2. 将标准化后的版本日志同步到各模块目录，生成中英文版本文件。

## 总原则

- `docs/changelog/release.md` 是人工维护的原始版本记录。
- `docs/changelog/release/*.md` 是标准化后的版本日志，文件名必须使用纯版本号，例如 `3.1.24.md`，不能使用 `V3.1.24.md`。
- 处理新版本时，必须先找出 `release.md` 中所有尚未同步的发布日期块，再按发布时间从旧到新依次补齐；禁止只处理最新一版。
- 版本号分配必须与未同步发布日期块一一对应，按顺序连续递增，不允许跳号、插空或把多个日期块合并到同一个版本文件。
- 模块同步时，必须以 `docs/changelog/release/*.md` 为唯一来源，不要直接再从 `release.md` 给模块目录产出内容。
- 英文版本必须是完整英文文案，不能出现“英文标题 + 中文正文”的混合内容。
- `ops-console` 是全量汇总页，包含所有模块与平台更新；各模块目录只保留各自模块命中的内容。

## 第一步：检查并生成 release 目录版本文件

### 检查规则

- 读取 `docs/changelog/release.md`。
- 读取 `docs/changelog/release/` 目录下现有版本文件。
- 以 `release/` 目录中当前最大版本号对应的发布日期为基准，找出 `release.md` 中所有晚于该日期、且尚未生成版本文件的发布日期块。
- 如果存在多个未同步的发布日期块，必须一次性全部补齐，不能只生成其中最新的一个版本文件。
- 每新增一个发布日期块，就新增一个对应的版本文件。

### 版本号规则

- 现有版本文件以 `docs/changelog/release/` 中最大版本号为准。
- 新增内容按发布时间顺序向后递增补齐版本号。
- 当前版本文件命名规则为 `3.1.x.md`。
- 例如：若当前最大版本 `3.1.24.md` 对应 `2026年4月10日`，而 `release.md` 里新增了 `2026年4月17日`、`2026年4月24日` 两个发布日期块，则必须生成 `3.1.25.md`、`3.1.26.md`，不能直接把 `2026年4月24日` 写入 `3.1.25.md`。

### 生成规则

每个版本文件格式统一为：

```md
# 3.1.x 版本日志
版本发布时间：YYYY年M月D日
了解更多产品能力，欢迎查阅[官方文档](https://www.bklite.ai)或直接体验[Demo环境](https://bklite.canway.net)

### 功能新增

| 模块 | 新增功能 |
| --- | --- |
| 模块名 | 内容 |

### 功能优化

| 模块 | 功能优化 |
| --- | --- |
| 模块名 | 内容 |
```

要求：

- 只在有内容时保留对应章节和表格。
- 模块名保持与 `release.md` 中拆分后的标准名称一致。
- 输出路径为 `docs/changelog/release/<版本号>.md`。

## 第二步：基于 release 目录同步到各模块

### 同步来源

- 只读取 `docs/changelog/release/*.md`。
- 不再直接读取 `docs/changelog/release.md` 生成模块文件。

### 输出目录

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

### 模块映射规则

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

### 同步规则

- 每个模块都按 `release` 目录中的版本文件名生成对应文件，例如 `3.1.24.md`。
- 中文文件输出到 `zh/`，英文文件输出到 `en/`。
- `ops-console` 保留所有模块内容；其他模块只保留命中映射规则的条目。
- 如果某个版本对某个模块没有命中内容，则该模块不生成该版本文件。
- 如果本轮新增了多个版本文件，则每个新增版本都必须逐个完成模块同步，不能只同步最后一个版本。
- 原有旧版本文件如果不符合当前版本体系，可以删除后按 `release` 目录重新生成。

## 模块文件格式

### 中文

```md
# 3.1.x 版本日志
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

### 英文

```md
# 3.1.x Release Notes
Release Date: Month D, YYYY
Learn more about product capabilities in the [official documentation](https://www.bklite.ai) or try the [Demo environment](https://bklite.canway.net).

### New Features

| Module | New Features |
| --- | --- |
| Module Name | Fully translated English content. |

### Improvements

| Module | Improvements |
| --- | --- |
| Module Name | Fully translated English content. |
```

要求：

- 英文模块名需要标准化翻译。
- 英文描述必须完整翻译，不能残留中文字符。
- 同步完成后，必须检查 `en` 目录下文件是否仍包含中文字符。

## 执行完成后的校验

完成后至少校验以下内容：

1. `docs/changelog/release/` 是否补齐新增版本文件。
2. `release.md` 中所有未同步发布日期块，是否都已与 `release/*.md` 中新增版本一一对应。
3. 版本号与发布日期是否严格按时间顺序连续递增，例如 `3.1.25 -> 2026年4月17日`、`3.1.26 -> 2026年4月24日`。
4. 新生成的版本文件名是否全部为 `3.1.x.md` 这种纯版本号形式。
5. 各模块目录是否已同步新增版本。
6. `ops-console` 是否包含全量内容。
7. `system-manager`、`monitor`、`log` 等模块是否只包含本模块相关内容。
8. 所有英文文件是否不包含中文字符。

## 防错要求

- 在开始生成文件前，先列出“已存在的最大版本号及其发布日期”与“本次待补齐的所有发布日期列表”。
- 在写入完成后，再逐项复核“版本号 -> 发布日期”映射，确认不存在日期跳跃或版本错位。
- 如果发现中间日期缺失，必须先补齐缺失版本，再处理后续日期，不能跳过。

## 建议给 AI 的使用方式

可直接对 AI 说：

```text
请按照 docs/changelog/ai-release-workflow.md 更新日志。
```

如果需要更明确一点，可直接说：

```text
请按照 docs/changelog/ai-release-workflow.md：
1. 检查 docs/changelog/release.md 是否有新的内容，并同步生成 docs/changelog/release/*.md
2. 基于 docs/changelog/release/*.md 同步到各模块，中英文都生成
3. 完成后校验英文文件中不能有中文
```