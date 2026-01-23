# AGENTS.md - AI Coding Agent Guidelines

> BK-Lite: AI-First lightweight operations platform (Tencent BlueKing ecosystem)

## Quick Reference

| Component | Package Manager | Dev Command | Test Command |
|-----------|----------------|-------------|--------------|
| server | `uv` | `make dev` | `uv run pytest` |
| web | `pnpm` | `pnpm dev` | `pnpm lint && pnpm type-check` |
| webchat | `npm` | `npm run dev` | - |
| stargazer | `uv` | `make run` | - |
| mobile | `pnpm` | `pnpm dev` | - |

## Build/Test/Lint Commands

### Server (Django + Python)
```bash
cd server
make install              # uv sync --all-groups --all-extras
make migrate              # makemigrations + migrate + createcachetable
make dev                  # uvicorn on port 8001 with reload
make celery               # Celery worker with beat
make bootstrap            # Full setup (install + migrate + init)

# Testing
uv run pytest                                                    # Full suite
uv run pytest apps/core/tests/test_users.py                     # Single file
uv run pytest apps/cmdb/tests/test_api.py::TestCMDB::test_get -v  # Single test
uv run pytest -k "test_create" -x                               # Pattern + stop on fail
uv run pytest --cov=apps/core --cov-report=term                 # With coverage
```

### Web (Next.js 16 + React 19)
```bash
cd web
pnpm install && pnpm dev      # Dev server (port 3000)
pnpm lint                     # ESLint check
pnpm type-check               # TypeScript check
pnpm storybook                # Component testing (port 6006)
pnpm build                    # Production build
```

### Other Components
```bash
cd webchat && npm install && npm run build && npm run dev  # Webchat
cd agents/stargazer && uv sync && make run                 # Stargazer (port 8083)
cd mobile && pnpm dev                                      # Mobile (Tauri)
```

## Code Style

### Python
| Rule | Value |
|------|-------|
| Formatter | Black (line-length=150) |
| Import sorting | isort (profile="black") |
| Type hints | Required for public APIs |
| Logging | `logging.getLogger("module_name")` |

```python
# Early return pattern (preferred)
def get_permissions(user_id: str) -> list[str]:
    if not user_id:
        return []
    user = User.objects.filter(id=user_id).first()
    if not user:
        return []
    return list(user.permissions.values_list("code", flat=True))
```

### TypeScript
| Rule | Value |
|------|-------|
| Indent | 2 spaces |
| Type definitions | `interface` (ESLint enforced) |
| Quotes/Semicolons | Single / Required |
| any usage | Avoid (use `unknown` with guards) |

```typescript
// Use interface, not type (ESLint rule)
interface UserProps {
  id: string;
  name: string;
}
```

### Import Order
- **Python**: stdlib → third-party → local
- **TypeScript**: react/next → third-party → `@/` aliases → relative

## Error Handling

```python
# Python: Centralized logging + exception chaining
from apps.core.logger import logger  # or module-specific logger
try:
    result = external_api_call()
except RequestException as e:
    logger.exception("API failed", extra={"endpoint": url})
    raise ServiceUnavailableError("Service unavailable") from e
```

```typescript
// TypeScript: Centralized in hooks
const { data, error } = useApiCall('/api/endpoint');
if (error) message.error(error.message);
```

## Architecture

```
server/apps/
├── core/              # Shared utilities, Celery, base models, logging
├── opspilot/          # AI assistant (LangChain, LangGraph)
├── cmdb/              # Configuration management
├── monitor/           # Monitoring & alerts
├── node_mgmt/         # Infrastructure management
├── system_mgmt/       # System management
├── alerts/            # Alert management
├── log/               # Log management
└── mlops/             # ML operations

web/src/app/
├── (core)/            # Core layout group
├── [module]/          # Business modules
│   ├── (pages)/       # Page components
│   ├── api/           # API layer
│   ├── components/    # Module components
│   ├── hooks/         # Module hooks
│   ├── types/         # Module types
│   └── utils/         # Module utilities
```

## Critical Rules

### DO
- Use `uv` for Python, `pnpm` for web, `npm` for webchat
- Follow existing codebase patterns (check before creating new)
- Add type hints to public Python functions
- Use early returns to reduce nesting
- Use `select_related`/`prefetch_related` for Django queries
- Log at entry points, external calls, exceptions
- Use existing dependencies before adding new ones

### DO NOT
- Add dependencies without justification
- Use `any` in TypeScript (use `unknown` with guards)
- Suppress type errors (`@ts-ignore`, `as any`)
- Create new test files (inline validation only)
- Commit secrets or `.env` files
- Block main thread with CPU-intensive ops
- Output sensitive info to logs
- Bypass unified logging, config, or auth pipelines

## Core Principles

1. **Avoid speculation**: Missing context → search repo first, align with existing patterns
2. **Minimal changes**: Extend don't fork, configure don't hardcode, maintain backward compatibility
3. **Incremental delivery**: Each commit should be minimal runnable unit, no over-engineering
4. **Progressive design**: When uncertain, take small steps with clear boundaries

## Pre-commit Checklist
1. **Reuse**: Existing module/pattern available?
2. **Minimal**: Smallest runnable change with rollback plan?
3. **Compatible**: API inputs/outputs unchanged?
4. **Dependencies**: No unapproved deps?
5. **Observability**: Key path logging complete?
6. **Security**: Input validation, auth checks, no sensitive data in logs?
7. **Stability**: Timeout/retry/backoff/concurrency limits in place?

## Key Dependencies

| Python | TypeScript |
|--------|------------|
| httpx (async), requests (sync) | axios |
| pydantic | Ant Design 5 + Tailwind 4 |
| Django ORM, Celery | react-intl, React Context |
| loguru (new), logging (existing) | next-auth |

## Commit Convention
```
type(scope): subject
# Types: feat, fix, docs, style, refactor, test, chore
```
