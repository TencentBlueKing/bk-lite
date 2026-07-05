# Project Map - bk-lite

## Project purpose
BK-Lite is an AI-first lightweight operations platform for operations administrators. It combines a Django business backend, Next.js control consoles, mobile/desktop shells, distributed collection agents, and algorithm services to provide CMDB, monitoring, alerting, log, job, node, MLOps, and OpsPilot capabilities with low deployment cost and progressive operational workflows.

## Stack
- Backend: Python 3.12, Django 4.2, DRF, Uvicorn, Celery/Beat, NATS, MinIO, FalkorDB, PostgreSQL/MySQL/SQLite/Dameng/GaussDB/GoldenDB/OceanBase via `DB_ENGINE`.
- Web: Next.js 16, React 19, TypeScript, Ant Design, Tailwind, pnpm.
- Mobile/Desktop: Next.js 15, Tauri 2, TypeScript, pnpm.
- WebChat: npm monorepo for embedded chat components.
- Stargazer: Python 3.12, Sanic collection agent.
- Algorithms: Python algorithm services managed with `uv`, BentoML, and MLflow.

## Main folders
- `server/` — main Django backend, APIs, async tasks, permissions, app modules, migrations, tests, and release startup.
- `web/` — main operations console; module pages and shared frontend infrastructure.
- `mobile/` — mobile and desktop shell.
- `webchat/` — embedded conversation component packages and demo app.
- `agents/stargazer/` — cloud/resource collection agent and plugins.
- `algorithms/` — anomaly, time-series, log, text, image, and detection algorithm services.
- `deploy/` — Docker/Kubernetes deployment assets and collector manifests.
- `docs/` — operations, generated schema, design, references, and contribution docs.
- `openspec/` — structured change/spec workflow.
- `.claude/` — project-level Claude commands, skills, settings, and local Claude instructions.
- `.codex/` — project-level Codex configuration, including MCP servers.
- `.projectmem/` — projectmem distilled memory, project map, AI instructions, and issue summaries. Raw `events.jsonl` is intentionally ignored.
- `.codegraph/` — local CodeGraph index storage. The database is local-only and ignored.
- `scripts/agent-tooling-bootstrap` — team/agent bootstrap for OpenSpec, projectmem, CodeGraph, projectmem hooks, and local CodeGraph indexing.
- `scripts/projectmem-mcp`, `scripts/codegraph-mcp` — stable repository-relative MCP launchers used by Claude and Codex.

## First reads
- `CLAUDE.md` / `AGENTS.md` — repository agent rules and current single source of truth.
- `.projectmem/AI_INSTRUCTIONS.md`, `.projectmem/summary.md`, `.projectmem/PROJECT_MAP.md` — mandatory projectmem workflow and distilled memory.
- `docs/operations.md` — commands, runbooks, environment templates, and workflow details.
- `ARCHITECTURE.md` — module boundaries, data flow, deployment shape, and core backend architecture.
- `docs/backend-coding-guide.md` — backend coding rules and common traps.
- `docs/design-docs/core-beliefs.md` — engineering principles and rationale.
- `DESIGN.md`, `FRONTEND.md`, `web/DESIGN.md` — design and frontend guidance.
- `SECURITY.md`, `RELIABILITY.md`, `QUALITY_SCORE.md` — safety, rollout, testing, and quality bars.

## Entry points and common commands
- Server dev: `cd server && make install && make migrate && make dev` (port 8011).
- Server test: `cd server && make test`.
- Web dev: `cd web && pnpm install && pnpm dev` (port 3000).
- Web gate: `cd web && pnpm lint && pnpm type-check`.
- Mobile dev: `cd mobile && pnpm dev` (port 3001) or `pnpm dev:tauri`.
- Mobile gate: `cd mobile && pnpm lint && pnpm type-check`.
- WebChat dev/test: `cd webchat && npm install && npm run dev`; gate is `npm run build && npm run test`.
- Stargazer dev/lint: `cd agents/stargazer && make install && make run` (port 8083); gate is `make lint`.
- Algorithms: `cd algorithms/<svc> && make install && make serving`; gate is `uv run pytest`.

## Key relationships
- `server/config/components/*.py` owns split settings; do not collapse configuration into one settings file.
- `server/apps/*/urls.py` are auto-registered under `api/v1/<app_name>/`.
- Stargazer and Kubernetes collectors send data through NATS into `server/node_mgmt` and `server/monitor`.
- Celery/Beat runs scheduled and async work for monitoring, alerts, jobs, and backend workflows.
- Web and mobile call backend APIs through the project proxy/auth conventions and shared token cookie.
- CMDB graph storage uses FalkorDB; do not introduce Neo4j-only assumptions.
- OpsPilot uses LangChain/LangGraph-style AI workflows and surfaces through web/webchat integrations.

## Non-negotiable constraints
- Keep diffs minimal and scoped to the requested module.
- Do not commit secrets, `.env`, keystores, local databases, dependency folders, caches, or generated runtime artifacts.
- New features and bug fixes follow TDD: failing test first, minimal implementation, then verification.
- Backend database access must use Django ORM; raw SQL, `.raw()`, `RawSQL`, and `cursor.execute` are forbidden because `DB_ENGINE` supports multiple dialects.
- High-risk deployment, plugin dispatch, or host-side job changes require dry-run, resource bounds, idempotency, rollback path, and matching tests.
- Agent entrypoints are maintained together: `.claude/`, `.agents` symlink, `.opencode/`, `.github/prompts/`, and `.codex/` where applicable.

## Project-level agent tooling
- `AGENTS.md` is a symlink to `CLAUDE.md`; `.agents` is a symlink to `.claude`.
- Superpowers skills live at `.claude/skills`.
- CodeGraph is configured in `.mcp.json` and `.codex/config.toml`; use it before grep/find for code understanding when `.codegraph/` exists.
- projectmem is configured in `.mcp.json` and `.codex/config.toml`; use it at session start and before modifying files.
- If `openspec`, `pjm`, or `codegraph` is missing on a team member's machine, agents must run `scripts/agent-tooling-bootstrap` before using those workflows.
