# Web 组件治理分支合并 Master 设计

## 背景

`codex/web-component-governance-merged` 是 Storybook-first 的前端组件治理分支。当前工作区承载大量尚未提交的 shared component、Storybook stories/fixtures、应用迁移与重复实现清理；本地 `master` 已更新到 `5d572c848`，治理分支相对其落后 211 个提交。

本次工作的目标不是用一侧代码整体覆盖另一侧，而是在吸收 master 最新业务修复的同时，保住治理分支已经形成的组件契约、复用边界与 Storybook 事实源。

## 合并策略

采用“治理成果 checkpoint + 常规 merge + 语义化解冲突”策略：

1. 对当前治理工作区做完整状态清单和备份校验。
2. 运行合并前最小基线检查，记录既有失败，不把基线问题误判为 merge 回归。
3. 将全部治理成果提交为独立中文 checkpoint commit，使每个文件都进入 Git 对象库。
4. 执行 `git merge master`，保留真实 merge ancestry。
5. 按文件职责逐项解决冲突，不使用全局 `ours` 或 `theirs`。

不采用 `stash -u` 作为主要承载方式：本分支文件量大，且历史上发生过未跟踪文件被普通 `mv` 静默覆盖的数据丢失；checkpoint commit 更容易审计、回滚和比较。

## 冲突裁决矩阵

### Shared components、barrels、Storybook 与治理文档

- 以治理分支的组件边界、公共 API、目录归属和 stories 为骨架。
- 吸收 master 新增的业务能力、类型修复、可访问性修复和错误处理。
- master 若恢复已被治理分支收敛的重复组件，不直接恢复旧入口；将新增逻辑移植到现有 shared contract，并同步 stories。
- 所有最终保留的 shared component 必须有 Storybook 契约；组件行为或 props 变化必须同步更新 stories/fixtures。

### App 页面与业务消费者

- 以 master 最新业务流程、接口字段、权限逻辑和 bugfix 为准。
- 以治理分支的 shared component 接入方式为准，避免重新引入 app-local 重复实现。
- 若 master 修改了被抽取组件原实现，先识别新增差异维度，再决定扩展 shared props、保留 app adapter，或判定其不应共享；禁止仅为解冲突复制实现。

### 删除、重命名与目录迁移

- 若治理分支已将旧文件迁移到明确的新 source of truth，保留旧文件删除，并把 master 新逻辑迁到新位置。
- 若删除的是零消费者、重复 wrapper 或多余 barrel，除非 master 引入新的真实消费者，否则继续删除。
- 若治理分支的目标文件只是临时 stub，而 master 存在完整真实实现，优先恢复真实业务逻辑，再适配治理后的组件契约。
- 对每个 modify/delete、rename/add 和 untracked collision 单独检查引用，禁止批量选择一侧。

## 数据安全与可回滚性

- checkpoint 前记录 `git status`、stash 列表、HEAD/master/merge-base，并确认历史 stash 保留。
- checkpoint commit 是本次 merge 的恢复点；不删除既有 stash，不执行 `git reset --hard`、`git checkout --` 或全仓覆盖。
- 合并过程中只处理本次冲突和其直接引发的类型/引用问题，不顺手扩展治理范围。
- 若发现治理成果与 master 新架构根本不兼容，停止该冲突的实现并记录证据，不以高风险猜测继续。

## 验证设计

验证分为四层：

1. **Git 完整性**：无未合并索引项、无冲突标记、merge parent 正确、checkpoint 可达。
2. **静态门禁**：在 `web/` 执行 `pnpm type-check` 与 `pnpm lint`，区分合并前既有失败和本次新增失败。
3. **Storybook 契约**：执行 Storybook build 或仓库现有等价验证；检查所有 shared component 的 stories/fixtures 引用可解析。
4. **运行时 smoke**：启动前端，验证登录、`ops-console`、`cmdb`、`monitor`、`opspilot`、`job`、`alarm` 等代表性入口及关键代理接口。

完成标准：Git 冲突清零；不存在本次合并新增的 lint/type 错误；Storybook 契约可构建；代表性页面不因缺模块、断裂 import 或权限配置而退化为 404/500。

## 非目标

- 不在本次合并中继续发掘新的组件候选。
- 不重写现有组件治理架构。
- 不修改后端业务逻辑，除非仅为验证 master 已有接口契约。
- 不处理与 merge 无关的全仓技术债。
