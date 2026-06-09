# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BK-Lite (Blueking Lite) is an AI-first lightweight operations & maintenance platform by Tencent BlueKing. It's a monorepo with microservices architecture: a Django backend, Next.js web/mobile frontends, distributed agents, and ML algorithm services.

## Development Commands

### Server (Django backend)
```bash
cd server
make install          # Install Python deps (uv sync)
make migrate          # Run makemigrations + migrate + create cache table
make dev              # Start Uvicorn on :8011 with reload
make test             # Run pytest
make celery           # Start Celery worker + Beat scheduler
make start-nats       # Start NATS listener
make shell            # IPython shell_plus
make i18n             # Generate and compile i18n messages
make setup-dev-user   # Create admin/password superuser
make server-init      # Run batch_init management command
```

Run a single test file or test:
```bash
cd server
uv run pytest apps/monitor/tests/test_something.py -v
uv run pytest apps/monitor/tests/test_something.py::TestClass::test_method -v
```

Run tests by marker: `uv run pytest -m unit`, `uv run pytest -m "not slow"`

### Web (Next.js 16 frontend)
```bash
cd web
pnpm install          # Install deps (pnpm enforced, npm/yarn blocked)
pnpm dev              # Next.js dev on :3000 with --turbo
pnpm build            # Production build
pnpm lint             # ESLint
pnpm type-check       # TypeScript type checking
pnpm storybook        # Storybook on :6006
```

### Mobile (Next.js 15 + Tauri)
```bash
cd mobile
pnpm install
pnpm dev              # Next.js dev on :3001
pnpm dev:tauri         # Tauri desktop dev
pnpm build:android     # Android release build
```

### Agents (Stargazer)
```bash
cd agents/stargazer
make install          # Install Python deps (uv)
make run              # Sanic server on :8083
make build            # Docker build
```

### Algorithms
```bash
cd algorithms/<service_name>
make install          # uv sync --all-groups --all-extras
make serving          # BentoML service on :3000
uv run pytest         # Run tests
```

## Architecture

### Monorepo Structure
- **server/** — Python 3.12, Django 4.2, Uvicorn (ASGI), Celery, DRF
- **web/** — Next.js 16, React 19, TypeScript, Ant Design, Tailwind CSS
- **mobile/** — Next.js 15, Tauri 2 (Rust), targets Android/desktop
- **webchat/** — npm monorepo (core, ui, demo packages) for chat components
- **agents/** — Distributed agents (stargazer: Sanic; nats-executor; ansible-executor; etc.)
- **algorithms/** — ML services using BentoML (anomaly, timeseries, log, text, image classification, object detection)
- **deploy/** — Kubernetes deployment templates

### Server Architecture
- **Django settings** use `split_settings` — config lives in `server/config/components/*.py` (base, app, database, cache, celery, nats, minio, mlflow, etc.)
- **URL routing** is auto-discovered: `server/urls.py` iterates `apps.*` and registers `api/v1/<app_name>/` for each app with a `urls.py`
- **App auto-discovery**: apps in `server/apps/` are auto-registered in `INSTALLED_APPS` (except `base`, `core`, `rpc` which are always loaded). Control with `INSTALL_APPS` env var.
- **Multi-database support**: PostgreSQL (default), MySQL, SQLite, Dameng, GaussDB, GoldenDB, OceanBase — selected via `DB_ENGINE` env var
- **Key Django apps**: `base` (auth/users), `core` (celery, middleware, utilities), `cmdb`, `monitor`, `alerts`, `log`, `node_mgmt`, `opspilot` (AI assistant using LangChain/LangGraph), `system_mgmt`, `job_mgmt`, `mlops`
- **Auth**: Custom user model `base.User` with multiple auth backends (session, API secret, standard)
- **Background tasks**: Celery with Beat for scheduling, NATS for distributed messaging
- **Object storage**: MinIO (S3-compatible) via `django_minio_backend`

### Web Architecture
- Next.js App Router with Ant Design component library
- i18n via `react-intl`
- Auth via `next-auth`
- API calls to server via `NEXTAPI_URL` env var
- Multi-module Docker builds (system-manager, console, node-manager, cmdb, monitor, opspilot)

### Algorithms Architecture
- Each algorithm service follows a classifier pattern with `ModelRegistry` decorator
- Config-driven training via `TrainingConfig` class
- MLflow integration for experiment tracking
- Traditional ML services (anomaly, timeseries, log, text): merge train+val data before final training
- Deep learning services (image, object_detection): keep train/val separate (YOLO requirement)

## Testing

### Server
- **Full TDD/BDD conventions: `server/docs/testing-guide.md`** (directory layout, test layering, BDD style) — follow it for all new/changed tests
- Stack: `pytest` + `pytest-django` + `pytest-bdd` + `factory_boy` (all in the `dev` dependency group)
- Config: `server/pytest.ini` — `testpaths = apps` (scans all apps), `--cov=apps`
- Markers (registered in `pytest.ini`): `unit`, `integration`, `bdd`, `slow`
- Layering by filename suffix: `_pure` (no DB/IO), `_service` (mocked deps), `_views` (DRF via `api_client`)
- Standard test dir per app: `apps/<app>/tests/`; BDD is flat — `apps/<app>/tests/bdd/<feature>.feature` + `test_<feature>_bdd.py` using `scenarios(FEATURE)` with 中文 Gherkin
- Global fixtures in `server/conftest.py`: `authenticated_user`, `api_client`, `request_factory`
- Async mode: `asyncio_mode = auto`

### Web
- Linting: `pnpm lint` (ESLint)
- Type checking: `pnpm type-check` (TypeScript)

## Code Style

### Python (server, agents, algorithms)
- Formatter: black (Python 3.10+ target)
- Import sorting: isort
- Linter: flake8
- Pre-commit hooks configured in `server/.pre-commit-config.yaml`

### TypeScript (web, mobile)
- ESLint with Next.js config
- Husky pre-commit hooks in `.husky/`
- pnpm enforced as package manager (web, mobile)

## Key Environment Variables
- `DB_ENGINE` — Database backend: `postgresql` (default), `mysql`, `sqlite`, `dameng`, `gaussdb`, `goldendb`, `oceanbase`
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` — Database connection
- `INSTALL_APPS` — Comma-separated list of apps to load (empty = load all)
- `NEXTAPI_URL` — Backend API URL for web/mobile frontends
- Env templates: `server/envs/.env.example`, `server/support-files/env/*.example`

## Package Managers
- **Python**: `uv` (all Python projects)
- **Web/Mobile**: `pnpm` (enforced, npm/yarn will fail)
- **WebChat**: `npm`

## Learnings & Decisions

### Authentication & Cookie Handling (2026-05-12)
- **Cookie 设置统一**: 所有登录入口（`login()`, `wechat_user_register()`）必须使用 `_set_auth_cookie_on_response()` 辅助函数设置 `bklite_token` cookie
- **`bk_lite_login` 是内部函数**: 它不是视图，只被 `login()` 视图内部调用（当 `domain != "domain.com"` 时）。不应暴露为 URL 路由。
- **登录流程**: Web 前端调用 `/api/proxy/core/api/login/` → 后端 `login()` 视图 → 根据 domain 调用 `SystemMgmt.login()` 或 `bk_lite_login()` → 统一设置 cookie
