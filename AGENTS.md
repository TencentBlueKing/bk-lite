# AGENTS.md - AI Coding Agent Guidelines

> BK-Lite: AI-First lightweight operations platform (Tencent BlueKing ecosystem)

## Quick Reference

| Component | Package Manager | Dev Command | Test Command |
|-----------|----------------|-------------|--------------|
| server | `uv` | `make dev` | `uv run pytest` |
| web | `pnpm` | `pnpm dev` | `pnpm storybook` |
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

# Testing
uv run pytest                                                    # Full suite
uv run pytest apps/core/tests/test_users.py                     # Single file
uv run pytest apps/cmdb/tests/test_api.py::TestCMDB::test_get -v  # Single test
uv run pytest -k "test_create" -x                               # Pattern + stop on fail
```

### Web (Next.js 16 + React 19)
```bash
cd web
pnpm install && pnpm dev      # Dev server (port 3000)
pnpm lint && pnpm type-check  # Lint + type check
pnpm storybook                # Component testing (port 6006)
```

### Other Components
```bash
cd webchat && npm install && npm run build && npm run dev  # Webchat
cd agents/stargazer && uv sync && make run                 # Stargazer
cd mobile && pnpm dev                                      # Mobile (Tauri)
```

## Code Style

### Python
| Rule | Value |
|------|-------|
| Formatter | Black (line-length=150) |
| Import sorting | isort (profile="black") |
| Type hints | Required for public APIs |
| Logging | loguru |

```python
# Early return pattern preferred
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

```typescript
interface UserProps {  // Use interface, not type
  id: string;
  name: string;
}
```

### Import Order
- **Python**: stdlib → third-party → local
- **TypeScript**: react/next → third-party → `@/` aliases → relative

## Error Handling

```python
# Python: loguru + exception chaining
from loguru import logger
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
├── core/        # Shared utilities, Celery, base models
├── opspilot/    # AI assistant (LangChain, LangGraph)
├── cmdb/        # Configuration management
├── monitor/     # Monitoring & alerts
├── node_mgmt/   # Infrastructure management
└── system_mgmt/ # System management

web/src/app/
├── (core)/      # Core layout group
└── [module]/    # Business modules (pages, api, components, types)
```

## Critical Rules

### DO
- Use `uv` for Python, `pnpm` for web
- Follow existing codebase patterns
- Add type hints to public Python functions
- Use early returns to reduce nesting
- Use `select_related`/`prefetch_related` for Django queries
- Log at entry points, external calls, exceptions

### DO NOT
- Add dependencies without justification
- Use `any` in TypeScript (use `unknown` with guards)
- Suppress type errors (`@ts-ignore`, `as any`)
- Create new test files (inline validation only)
- Commit secrets or `.env` files
- Block main thread with CPU-intensive ops
- Output sensitive info to logs

## Pre-commit Checklist
1. **Reuse**: Existing module/pattern available?
2. **Minimal**: Smallest runnable change with rollback plan?
3. **Compatible**: API inputs/outputs unchanged?
4. **Dependencies**: No unapproved deps?
5. **Observability**: Key path logging complete?
6. **Security**: Input validation, auth checks?

## Key Dependencies

| Python | TypeScript |
|--------|------------|
| httpx (async), requests (sync) | axios |
| pydantic | Ant Design 5 + Tailwind 4 |
| Django ORM, Celery | react-intl, React Context |
| loguru | - |

## Commit Convention
```
type(scope): subject
# Types: feat, fix, docs, style, refactor, test, chore
```
