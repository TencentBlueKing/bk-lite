# 本地 Change 与 Ticket 约定

- 一个 material feature 一个目录：`specs/changes/<feature-slug>/`。
- 主规格固定为 `spec.md`。
- 状态使用 `draft | ready | in-progress | done | cancelled`。
- 只有工作超出一个上下文窗口或存在真实阻塞边时才创建 `tickets/`。
- Ticket 路径为 `tickets/<NN>-<slug>.md`，按依赖顺序编号。
- 不创建 proposal、design、plan、delta、tasks sidecar，不发布外部 issue。
- 完成后原地更新状态，不 archive。
