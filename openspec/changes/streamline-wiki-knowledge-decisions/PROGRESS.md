# 实施进度报告 — streamline-wiki-knowledge-decisions

> 更新时间：2026-07-15
> 状态：功能实现已落盘，质量门禁部分完成。

## 实现状态

| Phase | 状态 | 主要交付 |
|-------|------|----------|
| 1 决策规则数据模型与迁移 | ✅ 完成 | `WikiDecisionRule`、决策 key/context 与数据库迁移 |
| 2 稳定签名与规则服务 | ✅ 完成 | 来源规范化、稳定签名、规则回放/upsert/撤销 |
| 3 知识冲突审批 | ✅ 完成 | 仅保留当前/采用新知识/编辑后采用，并冻结决策上下文 |
| 4 构建、更新与重建接入 | ✅ 完成 | 普通构建、资料更新和全库重建统一复用决策规则 |
| 5 页面身份合并 | ✅ 完成 | 保持独立/确认合并、稳定目标身份与生命周期撤销 |
| 6 删除与确定性维护 | ✅ 完成 | 物理删除级联维护、失效自动关闭与可重试维护 |
| 7 生产 API 与决策中心 | ✅ 完成 | 两类人工决策、语义化 API、生产 UI 与 Storybook stories |
| 8 并发、回归与质量门禁 | 🟡 部分完成 | 8.1-8.3、8.6 已完成；8.4-8.5 待执行完整门禁 |

## 已验证证据

### 后端

- 受影响的 20 个测试文件：`356 passed`。
- 终审补充回归覆盖：历史不完整审批自动关闭、重建 Schema/完整资料集合复核、页面身份完整漂移清扫、页面生命周期 KB→Page 锁顺序。
- 变更 Python 文件 Ruff 检查通过。
- `compileall` 通过。
- `git diff --check` 通过。
- `makemigrations --check --dry-run` 返回 `No changes detected`；执行时出现本地非测试数据库连接 warning，不将该 warning 记为测试通过或失败。

### 前端

- `test:wiki-decision-center` 通过。
- QA save-answer 脚本通过。
- 定向 TypeScript 检查通过。
- 定向 ESLint 检查通过。
- fresh Storybook 静态构建通过。

### OpenSpec

- strict validate 通过。
- status 显示 `4/4 artifacts complete`。


## 待完成门禁

- 8.4：尚未运行 `cd server; make test`，因此不声明全量后端测试或覆盖率门禁完成。
- 8.5：fresh Storybook build、定向脚本、TypeScript 和 ESLint 已通过；尚未运行全 Web 工作区的 `pnpm lint` 与 `pnpm type-check`，组合门禁仍保持未完成。
