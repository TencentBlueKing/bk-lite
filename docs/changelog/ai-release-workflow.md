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
- 不修改 `docs/changelog/release.md`，不把旧周版本文件移动到社区版或商业版目录。

## 社区版文件格式

社区版标准文件和社区版中文模块文件使用相同中文格式：

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

要求：

- 只在有内容时保留对应章节和表格。
- 标准文件包含该默认日期块的全部模块内容。
- `ops-console` 模块文件包含该日期块的全部模块内容。
- 其他模块文件只包含命中模块映射的内容。

## 商业版中文文件格式

商业版标准文件和商业版中文模块文件使用月版本格式：

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

要求：

- 商业版 3.1 对应 2026年5月。
- 商业版 3.2 对应 2026年6月。
- 后续自然月递增。
- 大版本升级必须由用户明确说明，AI 不得自行切换。
- 聚合同一自然月内的默认日期块和 `[商业版]` 日期块。
- 按功能分类和模块展示，不按日期分组。
- 同一月内完全重复的条目只保留一次。
- 商业版标准文件只生成中文。
- 商业版文件不包含“了解更多产品能力...”文案。

## 英文模块文件格式

英文只生成到模块目录。英文模块名需要标准化翻译，英文描述必须完整翻译，不能残留中文字符。

社区版英文文件使用：

```md
# Month D, YYYY Release Notes
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

商业版英文文件使用：

```md
# 3.1 Release Notes
Release Month: May 2026

### New Features

| Module | New Features |
| --- | --- |
| Module Name | Fully translated English content. |

### Improvements

| Module | Improvements |
| --- | --- |
| Module Name | Fully translated English content. |
```

商业版英文文件不包含官方文档和 Demo 环境文案。

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

## 模块映射规则

沿用现有映射：

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
3. 读取现有社区版标准文件、商业版标准文件和旧标准文件归档状态。
4. 首次迁移时，将旧标准文件归档到 `docs/changelog/release/legacy/`，并清理社区版 Web 目录下旧的 `3.1.x.md` 文件。
5. 从默认日期块生成缺失的社区版标准文件，输出到 `docs/changelog/release/community/YYYY-MM-DD.md`。
6. 从默认日期块和 `[商业版]` 日期块按自然月生成或更新商业版标准文件，输出到 `docs/changelog/release/enterprise/<月版本>.md`。
7. 从社区版标准文件同步到 `web/src/app` 下 11 个模块的 `zh` 和 `en` 目录。
8. 从商业版标准文件同步到 `enterprise/web/src/app` 下 11 个模块的 `zh` 和 `en` 目录。
9. 运行校验，确认命名、日期、月版本映射、模块过滤、商业专属内容排除、英文输出和旧文件归档都符合规则。

## 校验规则

完成后至少校验以下 12 项：

1. 社区版标准文件是否覆盖 `docs/changelog/release.md` 中所有默认日期块。
2. 商业版标准文件是否包含目标自然月内的默认日期块和 `[商业版]` 日期块。
3. `[商业版]` 日期块内容是否没有进入社区版标准文件和社区版模块文件。
4. 社区版标准文件和社区版模块文件名是否全部为 `YYYY-MM-DD.md`。
5. 商业版标准文件和商业版模块文件名是否全部为 `大版本.小版本.md`，例如 `3.1.md`。
6. 商业版月份映射是否正确：`2026年5月 -> 3.1`、`2026年6月 -> 3.2`。
7. `ops-console` 是否包含全量模块内容。
8. `system-manager`、`monitor`、`log`、`node-manager`、`cmdb`、`alarm`、`job`、`ops-analysis`、`opspilot`、`mlops` 是否只包含本模块命中的内容。
9. 所有英文模块文件是否不包含中文字符，且不是“英文标题 + 中文正文”的混合内容。
10. 商业版标准文件和商业版模块文件是否不包含“了解更多产品能力...”以及官方文档和 Demo 环境文案。
11. 旧 `3.1.x.md` 标准文件是否只存在于 `docs/changelog/release/legacy/`。
12. 社区版 Web 版本目录是否不再包含旧 `3.1.x.md` 文件。

## 防错要求

- 写入任何产物前，先列出本次识别到的默认日期块、商业版专属日期块、社区版待生成日期文件、商业版待生成月版本文件。
- 社区版生成必须排除 `[商业版]` 日期块。
- 商业版生成必须同时纳入默认日期块和 `[商业版]` 日期块。
- 商业版聚合只按自然月和模块聚合，不保留日期小节。
- 如果发现英文模块文件残留中文字符，必须重新翻译后再完成。
- 如果发现商业版文件包含官方文档或 Demo 环境文案，必须删除该文案后再完成。
- 如果发现旧标准文件仍在 `docs/changelog/release/` 根目录，必须先归档到 `legacy/`。
- 不要修改任何日志源文件之外的业务代码。

## 建议给 AI 的使用方式

可直接对 AI 说：

```text
请按照 docs/changelog/ai-release-workflow.md 更新日志。
```

如果需要更明确一点，可直接说：

```text
请按照 docs/changelog/ai-release-workflow.md：
1. 检查 docs/changelog/release.md 是否有新的默认日期块和商业版专属日期块
2. 生成社区版日期标准日志和商业版月版本标准日志
3. 基于标准日志同步社区版和商业版模块日志，中英文都生成
4. 完成后按 12 项校验规则逐项校验
```
