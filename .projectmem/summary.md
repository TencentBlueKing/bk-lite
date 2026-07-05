# projectmem - bk-lite

_Last updated: 2026-07-05_

## Project purpose
BK-Lite is an AI-first lightweight operations platform for operations administrators. It combines a Django business backend, Next.js control consoles, mobile/desktop shells, distributed collection agents, and algorithm services to provide CMDB, monitoring, alerting, log, job, node, MLOps, and OpsPilot capabilities with low deployment cost and progressive operational workflows.

## Recent issues
- [DONE] #legacy_fd43 Legacy issue: bugfix: 修复运营分析命名空间密码编辑与视图取数缓存问题 -> bugfix: 修复运营分析命名空间密码编辑与视图取数缓存问题 (fixed)
- [DONE] #legacy_ab37 Legacy issue: fix: 修复日志采集编辑模式多行合并开关不回填 bug -> fix: 修复日志采集编辑模式多行合并开关不回填 bug (fixed)
- [DONE] #legacy_a9d9 Legacy issue: fix：应用拓扑遗漏文件。 -> fix：应用拓扑遗漏文件。 (fixed)
- [DONE] #legacy_9dc0 Legacy issue: fix: 监控采集测试完成不主动弹窗结果 -> fix: 监控采集测试完成不主动弹窗结果 (fixed)
- [DONE] #legacy_9a93 Legacy issue: fix(monitor): overlay enterprise public icons -> fix(monitor): overlay enterprise public icons (fixed)
- [DONE] #legacy_8a12 Legacy issue: fix：优化IP扫描和IP视图。调整配置采集下发逻辑，让采集周期能够生效到节点Telegraf的配置中。 -> fix：优化IP扫描和IP视图。调整配置采集下发逻辑，让采集周期能够生效到节点Telegraf的配置中。 (fixed)
- [DONE] #legacy_76f1 Legacy issue: bugfix: 保持 system_mgmt NATS 旧入口兼容 -> bugfix: 保持 system_mgmt NATS 旧入口兼容 (fixed)
- [DONE] #legacy_39f2 Legacy issue: Merge pull request #3901 from TencentBlueKing/codex/fix-system-mgmt-nats-compat -> Merge pull request #3901 from TencentBlueKing/codex/fix-system-mgmt-nats-compat (fixed)
- [DONE] #legacy_2d91 Legacy issue: fix: 修复 CMDB 关联关系页打包失败 -> fix: 修复 CMDB 关联关系页打包失败 (fixed)
- [DONE] #legacy_02d7 Legacy issue: fix：修改告警屏蔽文案的错误。 -> fix：修改告警屏蔽文案的错误。 (fixed)

## Decisions
- 项目级 projectmem 作为持久项目记忆与工作流审计入口；Claude 通过 .mcp.json，Codex 通过 .codex/config.toml 同时接入 projectmem MCP。 [.mcp.json]
- BK-Lite 的核心架构是 Django 后端、Next.js Web/Mobile、多采集 Agent 与算法服务协同；跨模块工作必须先读 CLAUDE.md、ARCHITECTURE.md、docs/operations.md 与 projectmem 三件套。 [ARCHITECTURE.md]
- 团队成员本机可能缺 openspec、projectmem(pjm)、CodeGraph CLI；仓库提供 scripts/agent-tooling-bootstrap 自动检测/安装基础工具，并用仓库相对 MCP 包装脚本避免个人绝对路径。 [scripts/agent-tooling-bootstrap]

## Notes
- minor: 合并
- Merge pull request #3904 from hongxixixi/feat-ops-analysis
- Merge branch 'TencentBlueKing:master' into master
- Merge pull request #3905 from baiyf-git/master
- Merge pull request #3906 from TencentBlueKing/roger
- Merge pull request #3907 from TencentBlueKing/roger
- 添加项目级 Superpowers 基础技能
- 接入项目级 CodeGraph 配置
- projectmem MCP 必须使用 uv tool 环境里的 Python：/Users/mac/.local/share/uv/tools/projectmem/bin/python；系统 python3 当前不能 import projectmem。 [.codex/config.toml]
- 本仓库 AGENTS.md 指向 CLAUDE.md，.agents 指向 .claude；项目级 Agent 入口变更时要同步照顾 Claude/Codex/MCP 配置，避免只对单一客户端生效。 [CLAUDE.md]

## Key files
- `.gitignore`
- `web/scripts/prepare-enterprise.mjs`
- `web/src/app/monitor/dashboards/registry.ts`
- `server/apps/system_mgmt/nats_api.py`
- `server/apps/system_mgmt/tests/test_nats_api_compat.py`
- `server/apps/system_mgmt/tests/test_nats_api_handlers.py`
- `web/package.json`
- `web/scripts/log-vector-config-test.ts`
- `web/src/app/log/hooks/integration/collectors/vector/docker.tsx`
- `web/src/app/log/hooks/integration/collectors/vector/dockerDefaults.ts`
- `web/src/app/log/hooks/integration/collectors/vector/file.tsx`
- `web/src/app/log/hooks/integration/collectors/vector/fileDefaults.ts`
- `web/scripts/cmdb-relationships-imports-test.mjs`
- `web/src/app/cmdb/(pages)/assetData/components/sub-layout/side-menu.tsx`
- `web/src/app/cmdb/(pages)/assetData/detail/relationships/page.tsx`
- `web/scripts/prepare-enterprise-assets-test.mjs`
- `server/apps/operation_analysis/tests/test_datasource_view.py`
- `web/src/app/ops-analysis/(pages)/settings/dataSource/page.tsx`
- `web/src/app/ops-analysis/(pages)/settings/dataSource/paramTable.tsx`
- `web/src/app/ops-analysis/(pages)/settings/dataSource/previewPanel.tsx`

## Open questions
- None logged yet.
