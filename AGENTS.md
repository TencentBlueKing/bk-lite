# AGENTS.md - AI Coding Agent Guidelines

> BK-Lite: AI-First lightweight operations platform (Tencent BlueKing ecosystem)

## Project Structure

```
bk-lite/
├── server/              # Django REST backend (Python 3.12+)
├── web/                 # Next.js 16 frontend (React 19, TypeScript)
├── webchat/             # Embeddable chat widget (React, SSE)
├── agents/stargazer/    # Cloud resource collector (Sanic, ARQ)
├── algorithms/          # ML services (BentoML, MLflow)
└── mobile/              # Mobile app (React Native)
```

## Build/Test/Lint Commands

### Server (Django + Python)

```bash
cd server

# Install dependencies
make install              # uv sync --all-groups --all-extras

# Development
make dev                  # uvicorn on port 8001 with reload
make celery               # Start Celery worker with beat
make shell                # Django shell_plus

# Database
make migrate              # makemigrations + migrate + cache table
make server-init          # Initialize all server data

# Testing
make test                 # Run pytest
uv run pytest             # Full test suite
uv run pytest apps/core/tests/test_specific.py  # Single file
uv run pytest -k "test_name"                     # Single test by name
uv run pytest -x                                 # Stop on first failure

# i18n
make i18n                 # Generate and compile translations
```

### Web (Next.js + TypeScript)

```bash
cd web

# Package manager: pnpm ONLY (enforced by preinstall hook)
pnpm install

# Development
pnpm dev                  # Next.js dev server with turbo (port 3000)
pnpm build                # Production build
pnpm lint                 # ESLint check
pnpm type-check           # TypeScript check (no emit)
pnpm storybook            # Storybook on port 6006

# Analysis
pnpm analyze              # Bundle analyzer
```

### Webchat (Monorepo)

```bash
cd webchat
npm install && npm run build && npm run dev
```

### Stargazer Agent

```bash
cd agents/stargazer
uv sync
python server.py          # Sanic server
python start_worker.py    # ARQ worker (start BEFORE server)
```

## Code Style Guidelines

### Python (Server, Agents, Algorithms)

| Rule | Value |
|------|-------|
| Formatter | Black |
| Line length | 150 (server), 120 (agents) |
| Import sorting | isort (profile="black") |
| Type hints | Required for public APIs |
| Docstrings | Google style |

```python
# Good: Early return, clear naming
def get_user_permissions(user_id: str) -> list[str]:
    if not user_id:
        return []
    user = User.objects.filter(id=user_id).first()
    if not user:
        return []
    return list(user.permissions.values_list("code", flat=True))
```

### TypeScript/JavaScript (Web, Webchat)

| Rule | Value |
|------|-------|
| Indent | 2 spaces |
| Quotes | Single |
| Semicolons | Required |
| Trailing comma | ES5 |
| Type definitions | Use `interface` (not `type` for objects) |

```typescript
// ESLint enforces interface over type
interface UserProps {
  id: string;
  name: string;
  permissions: string[];
}
```

### Naming Conventions

| Context | Style | Example |
|---------|-------|---------|
| Python variables/functions | snake_case | `get_user_list` |
| Python classes | PascalCase | `UserSerializer` |
| TypeScript variables/functions | camelCase | `getUserList` |
| TypeScript components | PascalCase | `UserProfile` |
| Constants | SCREAMING_SNAKE | `MAX_RETRY_COUNT` |
| API endpoints | kebab-case | `/api/user-list/` |

### Import Order

**Python:**
1. Standard library
2. Third-party packages
3. Local imports (relative)

**TypeScript:**
1. React/Next.js
2. Third-party libraries
3. Internal aliases (`@/`)
4. Relative imports

## Error Handling

### Python
```python
# Use loguru for logging
from loguru import logger

try:
    result = external_api_call()
except RequestException as e:
    logger.exception("External API failed", extra={"endpoint": url})
    raise ServiceUnavailableError("External service unavailable") from e
```

### TypeScript
```typescript
// Centralized error handling in hooks
const { data, error, loading } = useApiCall('/api/endpoint');
if (error) {
  message.error(error.message);
}
```

## Key Dependencies (Prefer These)

### Python
- **HTTP**: httpx (async), requests (sync)
- **Validation**: pydantic
- **ORM**: Django ORM, SQLAlchemy
- **Tasks**: Celery, ARQ
- **Logging**: loguru

### TypeScript
- **UI**: Ant Design 5 + Tailwind CSS 4
- **State**: React Context (module-level)
- **HTTP**: axios
- **i18n**: react-intl

## Architecture Patterns

### Django Apps Structure
```
apps/
├── core/           # Shared utilities, base models
├── opspilot/       # AI assistant (LangChain, LangGraph)
├── cmdb/           # Configuration management
├── monitor/        # Monitoring & alerts
└── node_manager/   # Infrastructure management
```

### Next.js App Router Structure
```
src/app/
├── (core)/         # Core layout group
├── [module]/       # Business modules
│   ├── (pages)/    # Page components
│   ├── api/        # API layer
│   ├── components/ # Module components
│   ├── hooks/      # Module hooks
│   └── types/      # Module types
```

## Commit Conventions

```
type(scope): subject

# Types: feat, fix, docs, style, refactor, test, chore
# Examples:
feat(opspilot): add streaming chat support
fix(monitor): resolve alert notification race condition
```

## Critical Rules

### DO
- Use `uv` for Python package management
- Use `pnpm` for web package management
- Follow existing patterns in the codebase
- Add type hints to all public Python functions
- Use early returns to reduce nesting
- Log at entry points, external calls, and exceptions

### DO NOT
- Add new dependencies without justification
- Use `any` type in TypeScript (use `unknown` with guards)
- Suppress type errors with `@ts-ignore` or `as any`
- Commit secrets or `.env` files
- Create new test files (use inline validation only)
- Block main thread with CPU-intensive operations

## Testing Guidelines

```bash
# Python: pytest with Django
uv run pytest apps/core/tests/test_users.py::TestUserAPI::test_create -v

# TypeScript: No test framework configured
# Use Storybook for component verification
pnpm storybook
```

## Environment Setup

```bash
# Server
cp server/.env.example server/.env
cd server && make install && make migrate && make server-init

# Web
cd web && pnpm install
cp .env.example .env.local

# Required services: PostgreSQL, Redis, MinIO, NATS
```

## API Design

- REST endpoints under `/api/v1/`
- Use DRF serializers for validation
- Pagination: `page` and `page_size` params
- Error format: `{"error": {"code": "...", "message": "..."}}`

## Performance Considerations

- Use `select_related`/`prefetch_related` for Django queries
- Implement pagination for list endpoints
- Offload heavy tasks to Celery
- Use React.memo/useMemo for expensive renders
- Lazy load routes and components in Next.js
