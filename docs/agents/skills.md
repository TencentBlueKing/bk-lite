# Repo-local Skills

Grill 主链固定来自 `mattpocock/skills@9603c1cc8118d08bc1b3bf34cf714f62178dea3b`，复制基线为 `saas-mono@97d8ab2868a61b6d7d844341ae59595f224cc858`。

## Grill 主链

- Alignment：`grill-me`、`grilling`、`grill-with-docs`、`domain-modeling`
- Delivery：`to-spec`、`to-tickets`、`implement`、`tdd`、`code-review`
- Engineering：`diagnosing-bugs`、`codebase-design`、`improve-codebase-architecture`
- Maintenance：`setup-matt-pocock-skills`

高成本入口通过 `agents/openai.yaml` 关闭隐式调用。

## BK-Lite 专属

- `bklite-ops-product-design`：运维产品模块、MVP、权限、审计和执行安全设计。
- `tech-debt-audit`：显式触发的全仓技术债审计。

仓库自有技能和 Grill 主链必须包含 `SKILL.md` 和 `agents/openai.yaml`。禁止重新引入 OpenSpec、OPSX、Superpowers 或并行 UI/UX Skill 套件；pstack 是唯一经确认的 vendored 工作流包，见下节。

## Vendored 工作流包：pstack

- 上游为 `cursor/plugins` 的 pstack `0.15.36`（缓存提交 `3dbd22ff12742fb28c9700b9760baa29ed41dc13`），按上游目录原样放在 `.agents/skills/`（即 `.claude/skills/`）。
- 入口是 `poteto-mode`。它通过 `playbooks/`、`references/` 和 `../<name>/SKILL.md` 相互引用，**禁止重命名技能目录或拆平其父级结构**。
- 与本地同名技能冲突时保留本地版本。当前 `tdd` 保留 Grill 版，pstack 的 `tdd` 未导入。
- `poteto-help` 未导入：它索引插件根的 `docs/`，而这里只 vendored `skills/`；使用入口统一看根 `AGENTS.md` 的「工作风格」段。
- Vendored 包保持上游 `SKILL.md` 结构，不补 `agents/openai.yaml`；该要求只约束仓库自有技能和 Grill 主链。
