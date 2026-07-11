# Production Readiness Assessment & Improvement Recommendations

> **Project:** AI Travel Assistant (LangGraph POC → Production)
> **Review Date:** 2025-07-16
> **Reviewer:** Senior Architect
> **Total Findings:** 30

---

## Table of Contents

1. [Security](#1-security)
2. [Architecture & Scalability](#2-architecture--scalability)
3. [Code Quality & Maintainability](#3-code-quality--maintainability)
4. [Testing](#4-testing)
5. [Deployment & DevOps](#5-deployment--devops)
6. [Monitoring & Observability](#6-monitoring--observability)
7. [Prioritized Roadmap](#7-prioritized-roadmap)
8. [Summary Checklist](#8-summary-checklist)

---

## 1. Security

### 🔴 Finding 1: Hardcoded Credentials in docker-compose.scalable.yml
**Severity:** Critical | **Effort:** 15 min

**Location:** `docker-compose.scalable.yml` lines 8-9, 62
```yaml
- POSTGRES_USER=nabeel
- POSTGRES_PASSWORD=momin.123
- DATABASE_URL=postgresql://nabeel:momin.123@postgres:5432/travel_db
```

**Impact:** Credentials exposed in source control. If this file ever reaches a public/private repo, database is compromised.

**Recommendation:** Use environment variables with no defaults:
```yaml
- POSTGRES_USER=${POSTGRES_USER}
- POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
- DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
```

---

### 🔴 Finding 2: Hardcoded Database Credentials in settings.py Fallback
**Severity:** Critical | **Effort:** 10 min

**Location:** `src/config/settings.py` line 47
```python
def validate_database_url(cls, v):
    if not v:
        return "postgresql://nabeel:momin.123@localhost:5432/travel_db"  # ← HARDCODED
```

**Impact:** If DATABASE_URL env var is missing, the app silently falls back to hardcoded credentials. This masks misconfiguration in production.

**Recommendation:** Raise an error instead of providing a fallback with credentials:
```python
@field_validator("database_url", mode="before")
@classmethod
def validate_database_url(cls, v):
    if not v:
        raise ValueError("DATABASE_URL environment variable is required")
    return v
```

---

### 🔴 Finding 3: CORS allow_origins=["*"] in main1.py
**Severity:** Critical | **Effort:** 5 min

**Location:** `main1.py` — `allow_origins=["*"]`

**Impact:** Any origin can make authenticated requests to the API. Combined with `allow_credentials=True`, this is a serious security vulnerability.

**Recommendation:** Use environment-specific CORS origins:
```python
allow_origins=settings.cors_origins,  # from Settings model, not ["*"]
```
And fix the commented-out validator in `settings.py`:
```python
@field_validator("cors_origins", mode="before")
@classmethod
def split_cors_origins(cls, v):
    if isinstance(v, str):
        return [origin.strip() for origin in v.split(",") if origin.strip()]
    return v
```

---

### 🔴 Finding 4: debug=True Hardcoded in main1.py
**Severity:** Critical | **Effort:** 5 min

**Location:** `main1.py` — `debug=True`

**Impact:** Debug mode in production exposes tracebacks, environment variables, and internal state to end users.

**Recommendation:**
```python
debug=settings.debug,  # defaults to False in Settings model
```

---

### 🟠 Finding 5: SECRET_KEY Auto-Generates if Missing
**Severity:** High | **Effort:** 10 min

**Location:** `src/config/settings.py` lines 20-23
```python
@field_validator("secret_key", mode="before")
@classmethod
def validate_secret_key(cls, v):
    if not v or v == "change-me-in-production":
        import secrets
        return secrets.token_urlsafe(32)  # ← Auto-generates!
```

**Impact:** If SECRET_KEY is not set in production, a new key is generated on every restart. This invalidates all existing sessions/tokens and breaks JWT verification across restarts. The app "works" but sessions are silently broken.

**Recommendation:** Require explicit configuration in non-development environments:
```python
@field_validator("secret_key", mode="before")
@classmethod
def validate_secret_key(cls, v):
    if not v or v == "change-me-in-production":
        if os.getenv("ENVIRONMENT", "development") != "development":
            raise ValueError("SECRET_KEY must be explicitly set in non-development environments")
        import secrets
        return secrets.token_urlsafe(32)
    if len(v) < 32:
        raise ValueError("SECRET_KEY must be at least 32 characters")
    return v
```

---

### 🟠 Finding 6: No Input Validation/Sanitization on User Messages
**Severity:** High | **Effort:** 2 hours

**Location:** `src/langgraph_core/nodes/travel_planner_nodes.py` — router, travel_node, chat_node

**Impact:** User input is passed directly to LLMs and tools without sanitization. Potential for prompt injection, excessively long inputs causing high API costs, or malicious content.

**Recommendation:** Add input validation middleware:
```python
# src/utils/input_validation.py
import re
from typing import Tuple

MAX_INPUT_LENGTH = 2000
BLOCKED_PATTERNS = [
    r"<script.*?>",           # XSS attempts
    r"ignore.*instructions",  # Prompt injection
    r"\[system\]",            # System prompt injection
]

def validate_user_input(text: str) -> Tuple[bool, str]:
    """Validate and sanitize user input."""
    if not text or not text.strip():
        return False, "Input cannot be empty"

    if len(text) > MAX_INPUT_LENGTH:
        return False, f"Input exceeds maximum length of {MAX_INPUT_LENGTH} characters"

    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return False, "Input contains blocked patterns"

    return True, text.strip()
```

---

### 🟡 Finding 7: Sensitive Data Logged (Emails)
**Severity:** Medium | **Effort:** 30 min

**Location:** `src/auth/authentication.py` lines 18, 55
```python
logger.info(f"Registration attempt for email: {email}")
logger.info(f"Login attempt for email: {email}")
```

**Impact:** PII (email addresses) in logs violates GDPR/CCPA and internal security policies.

**Recommendation:** Log anonymized identifiers instead:
```python
import hashlib

def anonymize_email(email: str) -> str:
    return hashlib.sha256(email.encode()).hexdigest()[:12]

logger.info(f"Registration attempt for user: {anonymize_email(email)}")
```

---

## 2. Architecture & Scalability

### 🔴 Finding 8: MemorySaver (In-Memory) Used Instead of RedisCheckpointer
**Severity:** Critical | **Effort:** 4 hours

**Location:** `src/langgraph_core/graphs/travel_planner_graph.py` lines 72-76
```python
@classmethod
def get_checkpointer(cls) -> MemorySaver:
    if cls._checkpointer is None:
        cls._checkpointer = MemorySaver()  # ← IN-MEMORY!
```

**Impact:** Conversation state is stored in process memory. With multiple replicas (docker-compose.scalable.yml has `replicas: 2`), a user's request may hit a different instance and lose all conversation context. This is the single biggest blocker for multi-instance deployment.

**Recommendation:** Use the already-implemented `RedisCheckpointer`:
```python
from src.langgraph_core.checkpoints.redis_checkpointer import RedisCheckpointer

@classmethod
def get_checkpointer(cls) -> RedisCheckpointer:
    if cls._checkpointer is None:
        cls._checkpointer = RedisCheckpointer(ttl_days=7)
        logger.info("Created RedisCheckpointer for distributed state")
    return cls._checkpointer
```

---

### 🔴 Finding 9: In-Memory Rate Limiter — Not Distributed
**Severity:** Critical | **Effort:** 3 hours

**Location:** `main.py` and `main1.py` — sliding window rate limiter with `threading.Lock`/`asyncio.Lock`

**Impact:** Rate limiting is per-process, not global. With 2+ replicas, each has its own counter. A user can make 2× the allowed requests by hitting different instances.

**Recommendation:** Use Redis-based rate limiting:
```python
# src/utils/redis_rate_limiter.py
import time
import redis.asyncio as redis

class RedisRateLimiter:
    def __init__(self, redis_client, window_seconds: int = 60, max_requests: int = 60):
        self.redis = redis_client
        self.window = window_seconds
        self.max_requests = max_requests

    async def is_allowed(self, key: str) -> bool:
        now = time.time()
        window_start = now - self.window
        pipe = self.redis.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)  # Remove old entries
        pipe.zcard(key)                                # Count current
        pipe.zadd(key, {str(now): now})               # Add current
        pipe.expire(key, self.window + 1)
        _, count, _, _ = await pipe.execute()
        return count <= self.max_requests
```

---

### 🟠 Finding 10: Three Entry Points — Confusing Architecture
**Severity:** High | **Effort:** 1 day

**Location:**
- `app.py` — Flask (sync, minimal)
- `main.py` — FastAPI (sync)
- `main1.py` — FastAPI (async)

**Impact:** Three different application entry points create confusion about which to use in production. Flask app has no auth, no rate limiting. Two FastAPI apps duplicate logic.

**Recommendation:** Consolidate to a single FastAPI async entry point (`main1.py` → rename to `main.py`). Remove `app.py` entirely. If Flask is needed for specific routes, mount it as a sub-app within FastAPI.

---

### 🟠 Finding 11: Session Expiry Too Short (900s = 15 min)
**Severity:** High | **Effort:** 5 min

**Location:** `src/cache/session_manager.py` line 14 — `session_expiry: int = 900`

**Impact:** Users are logged out after 15 minutes of inactivity. For a travel planning app where users may spend 30+ minutes researching, this is frustrating.

**Recommendation:** Use the settings value (already defined as 86400s):
```python
def __init__(self, session_prefix: str = "session:", session_expiry: int = None):
    self.session_expiry = session_expiry or settings.redis.session_ttl_seconds  # 86400 = 24h
```

---

### 🟠 Finding 12: Duplicate Sync/Async Code Throughout Codebase
**Severity:** High | **Effort:** 3 days

**Duplicates identified:**
| Sync | Async | Overlap |
|------|-------|---------|
| `ai_travel_planner.py` | `ai_travel_planner1.py` | ~90% |
| `src/auth/authentication.py` | `src/auth/async_authentication.py` | ~85% |
| `src/cache/redis_client.py` | `src/cache/redis_cluster.py` | ~95% |
| `src/database/databases.py` | `src/database/async_database.py` | ~80% |
| `main.py` | `main1.py` | ~70% |

**Impact:** Bug fixes must be applied in two places. Divergent behavior over time. 2× maintenance burden.

**Recommendation:** Choose async as the standard (FastAPI is async-native). Remove sync duplicates. For any remaining sync needs, use `asyncio.run()` or `loop.run_until_complete()`.

---

### 🟡 Finding 13: Singleton Pattern with Mutable Class Variables
**Severity:** Medium | **Effort:** 2 hours

**Location:** `TravelGraphBuilder`, `TravelPlannerNode`, `LoadLLMs`

**Impact:** Singleton state persists across tests. `_instance` and `_compiled_graph` class variables make unit testing difficult — tests can't get a fresh instance.

**Recommendation:** Add a `reset()` class method for testing:
```python
@classmethod
def reset(cls):
    """Reset singleton state (for testing)."""
    cls._instance = None
    cls._compiled_graph = None
    cls._checkpointer = None
```
Or use a dependency injection pattern instead of singletons.

---

### 🟡 Finding 14: No API Versioning
**Severity:** Medium | **Effort:** 1 hour

**Location:** `main.py`, `main1.py` — routes like `/chat`, `/travel`, `/login`

**Impact:** Breaking changes to the API cannot be introduced without affecting all clients simultaneously.

**Recommendation:** Prefix all routes with `/api/v1/`:
```python
app.include_router(chat_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1/auth")
```
The `api_v1_prefix` setting already exists in `settings.py` but is unused.

---

### 🟡 Finding 15: No Graceful Shutdown for Celery/Redis Connections
**Severity:** Medium | **Effort:** 1 hour

**Location:** `main.py`, `main1.py` — lifespan context managers

**Impact:** On SIGTERM (Kubernetes pod termination, Docker stop), in-flight LLM tasks are lost, Redis connections may leak.

**Recommendation:** Add proper shutdown handling:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await redis_client.connect()
    await async_database.create_tables()
    yield
    # Shutdown — graceful
    logger.info("Shutting down...")
    await task_manager.drain_pending_tasks(timeout=30)
    await redis_client.disconnect()
    await async_database.dispose()
    logger.info("Shutdown complete")
```

---

### 🟡 Finding 16: Router Uses Keyword Matching, Not LLM-Based Classification
**Severity:** Medium | **Effort:** 4 hours

**Location:** `src/langgraph_core/nodes/travel_planner_nodes.py` lines 232-240
```python
if any(word in user_input_lower for word in ["travel", "visit", "trip", ...]):
    route = "travel"
elif any(word in user_input_lower for word in ["weather", "temperature", ...]):
    route = "weather"
```

**Impact:** Brittle intent classification. "I want to travel to a place with good weather" routes to "travel" but loses the weather intent. "Search for travel deals" routes to "search" instead of "travel".

**Recommendation:** Use LLM-based intent classification with the existing LLM instance:
```python
async def classify_intent(self, user_input: str) -> str:
    prompt = f"""Classify this travel-related query into one of:
    - travel (trip planning, booking, itinerary)
    - weather (weather forecasts, climate info)
    - search (finding specific information)
    - chat (general conversation, greetings)

    Query: "{user_input}"
    Intent:"""
    response = await self._llm_invoke(prompt, timeout=5.0)
    return response.strip().lower() if response else "chat"
```

---

## 3. Code Quality & Maintainability

### 🟠 Finding 17: Windows-Only Hardcoded Path in Utilities.py
**Severity:** High | **Effort:** 10 min

**Location:** `src/utils/Utilities.py` line 52
```python
def load_llm_config(provider_name: str, config_path: str = r".\src\config\llm_configs.yml"):
```

**Impact:** Backslash path works only on Windows. The app cannot start on Linux/macOS (including Docker containers).

**Recommendation:** Use `pathlib` for cross-platform paths:
```python
from pathlib import Path

def load_llm_config(provider_name: str, config_path: str = None) -> Dict[str, Any]:
    if config_path is None:
        config_path = str(Path(__file__).parent.parent / "config" / "llm_configs.yml")
```

---

### 🟠 Finding 18: Celery Tasks Create New Event Loop Per Task (Anti-Pattern)
**Severity:** High | **Effort:** 2 hours

**Location:** `src/tasks/llm_queue.py` lines 60-63, 82-85
```python
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
response = loop.run_until_complete(run_llm())
loop.close()
```

**Impact:** Creating and destroying event loops per task is expensive and can leak resources. Not the intended Celery + asyncio pattern.

**Recommendation:** Use `asyncio.run()` or better, use Celery's native async support:
```python
@llm_app.task
def process_llm_request(prompt: str, provider: str = "groq"):
    return asyncio.run(_async_process_llm(prompt, provider))

async def _async_process_llm(prompt: str, provider: str):
    llm = get_llm(provider)
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    return response.content
```

---

### 🟠 Finding 19: docker-compose.scalable.yml Has Wrong Module Paths
**Severity:** High | **Effort:** 15 min

**Location:** `docker-compose.scalable.yml` lines 72, 88
```yaml
command: uvicorn src.main:app      # ← main.py is at root, not src/
command: celery -A tasks.llm_queue  # ← tasks is at src/tasks/
```

**Impact:** The scalable deployment configuration will fail on startup. These paths don't match the actual project structure.

**Recommendation:**
```yaml
command: uvicorn main1:app          # or main:app (both at root)
command: celery -A src.tasks.llm_queue worker
```

---

### 🟡 Finding 20: print() Statements Instead of Logger
**Severity:** Medium | **Effort:** 15 min

**Location:**
- `main.py` — `print(token)`
- `app.py` — `print(user_input)`

**Impact:** `print()` output goes to stdout without timestamps, levels, or structured format. In production, these are invisible to log aggregation systems.

**Recommendation:** Replace all `print()` with proper logger calls:
```python
logger.debug(f"Token: {token[:10]}...")  # Truncate sensitive data
```

---

### 🟡 Finding 21: User Model Uses Deprecated declarative_base
**Severity:** Medium | **Effort:** 1 hour

**Location:** `src/database/models/user.py` lines 5-6
```python
from sqlalchemy.ext.declarative import declarative_base
Base = declarative_base()
```

**Impact:** SQLAlchemy 2.0+ deprecates `declarative_base()` in favor of `DeclarativeBase`. Column-based attributes are legacy; Mapped[] types are the modern standard.

**Recommendation:**
```python
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

---

### 🟡 Finding 22: draw_mermaid_png Hardcoded to ./logs/ Path
**Severity:** Medium | **Effort:** 5 min

**Location:** `src/langgraph_core/graphs/travel_planner_graph.py` line 249
```python
self._compiled_graph.get_graph().draw_mermaid_png(
    output_file_path=r"./logs/travel_routing_3.png"
)
```

**Impact:** Hardcoded relative path. In Docker, the `./logs/` directory may not exist or be writable. The hardcoded filename means only one graph diagram is ever generated.

**Recommendation:** Make it configurable and ensure directory exists:
```python
import os
log_dir = settings.logging.log_dir
os.makedirs(log_dir, exist_ok=True)
output_path = os.path.join(log_dir, f"graph_{datetime.now():%Y%m%d_%H%M%S}.png")
```

---

### 🟡 Finding 23: No Database Migrations (Alembic)
**Severity:** Medium | **Effort:** 2 hours

**Location:** Project root — no `alembic/` directory or `alembic.ini`

**Impact:** `Base.metadata.create_all()` only creates tables, it cannot modify existing tables. Any schema change in production requires manual SQL or table drops.

**Recommendation:** Set up Alembic:
```bash
pip install alembic
alembic init alembic
# Configure alembic.ini with DATABASE_URL
# Run: alembic revision --autogenerate -m "initial"
# Run: alembic upgrade head
```

---

### 🟡 Finding 24: No Request ID Propagation Middleware
**Severity:** Medium | **Effort:** 1 hour

**Location:** `main.py`, `main1.py` — no request ID middleware

**Impact:** Cannot trace a single user request across logs, LLM calls, tool calls, and database queries. Debugging production issues requires time-correlation guessing.

**Recommendation:** Add request ID middleware:
```python
# src/utils/request_id.py
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import uuid

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        Logger.RequestContextFilter.set_context(request_id=request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
```

---

### 🟢 Finding 25: Minimal Exception Hierarchy
**Severity:** Low | **Effort:** 1 hour

**Location:** `src/exceptions/__init__.py` — single `ExceptionError` class

**Impact:** All errors wrapped in one generic exception. Cannot differentiate between auth errors, API errors, database errors, or validation errors for appropriate HTTP status codes.

**Recommendation:** Create a proper exception hierarchy:
```python
class TravelAppError(Exception): ...
class AuthenticationError(TravelAppError): ...
class ValidationError(TravelAppError): ...
class ExternalAPIError(TravelAppError): ...
class DatabaseError(TravelAppError): ...
class RateLimitExceededError(TravelAppError): ...
```

---

## 4. Testing

### 🔴 Finding 26: Zero Test Coverage — tests/ Directory Empty
**Severity:** Critical | **Effort:** 1-2 weeks

**Location:** `tests/` — completely empty

**Impact:** No automated verification that any feature works. Every deployment is a gamble. Refactoring is dangerous. This is the #1 blocker for production.

**Recommendation:** Implement test pyramid:

**Phase 1 — Critical Path Tests (Week 1):**
```python
# tests/test_auth.py
async def test_register_user_success():
    ...
async def test_login_with_valid_credentials():
    ...
async def test_login_with_invalid_password():
    ...

# tests/test_graph.py
async def test_router_classifies_travel_intent():
    ...
async def test_travel_node_extracts_destination():
    ...
async def test_graph_compiles_without_error():
    ...
```

**Phase 2 — Integration Tests (Week 2):**
```python
# tests/test_api.py
async def test_chat_endpoint_returns_response():
    ...
async def test_rate_limiter_blocks_excess():
    ...
```

**Phase 3 — Load Tests:**
- Use `load_test.py` (already exists) with locust or k6

---

## 5. Deployment & DevOps

### 🟠 Finding 27: No .env.example File
**Severity:** High | **Effort:** 15 min

**Impact:** New developers and operators don't know which environment variables are required. Leads to cryptic runtime errors.

**Recommendation:** Create `.env.example`:
```bash
# .env.example
ENVIRONMENT=development
DEBUG=false

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/travel_db
ASYNC_DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/travel_db

# Redis
REDIS_URL=redis://localhost:6379/0

# Security
SECRET_KEY=<generate-with: python -c "import secrets; print(secrets.token_urlsafe(32))">

# LLM API Keys
GROQ_API_KEY=
GOOGLE_API_KEY=
OPENAI_API_KEY=
DEEPSEEK_API_KEY=
TAVILY_API_KEY=
OPENWEATHERMAP_API_KEY=

# CORS (comma-separated origins)
CORS_ORIGINS=http://localhost:3000,http://localhost:8000
```

---

### 🟠 Finding 28: No Dockerfile
**Severity:** High | **Effort:** 30 min

**Location:** `docker-compose.yml` and `docker-compose.scalable.yml` both use `build: .` but no `Dockerfile` exists at project root.

**Impact:** `docker compose up` will fail with "Cannot locate specified Dockerfile".

**Recommendation:** Create a production-ready Dockerfile:
```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install spaCy model
RUN python -m spacy download en_core_web_md

# Copy application
COPY . .

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "main1:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

### 🟡 Finding 29: No .gitignore
**Severity:** Medium | **Effort:** 5 min

**Impact:** Risk of committing `.env` files, `__pycache__`, logs, virtual environments, and IDE files.

**Recommendation:** Create `.gitignore`:
```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
*.egg

# Environment
.env
.venv/
AI-Travel/
venv/

# IDE
.vscode/
.idea/

# Logs
logs/
*.log

# OS
.DS_Store
Thumbs.db

# Docker
pgdata/
redis_data/

# Testing
.pytest_cache/
.coverage
htmlcov/
```

---

### 🟡 Finding 30: No CI/CD Pipeline
**Severity:** Medium | **Effort:** 4 hours

**Impact:** No automated linting, testing, or deployment. Every change requires manual verification.

**Recommendation:** Add GitHub Actions workflow:
```yaml
# .github/workflows/ci.yml
name: CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: test_db
        ports: ["5432:5432"]
      redis:
        image: redis:7
        ports: ["6379:6379"]

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r requirements.txt
      - run: pip install pytest pytest-asyncio pytest-cov
      - run: python -m spacy download en_core_web_md
      - run: pytest tests/ --cov=src --cov-report=xml
      - run: flake8 src/ --max-line-length=120
      - run: mypy src/ --ignore-missing-imports
```

---

## 7. Prioritized Roadmap

### Phase 1: Critical — Must Fix Before Production (Week 1-2)
| # | Finding | Effort |
|---|---------|--------|
| 1 | Hardcoded credentials in docker-compose.scalable.yml | 15 min |
| 2 | Hardcoded DB URL fallback in settings.py | 10 min |
| 3 | CORS allow_origins=["*"] | 5 min |
| 4 | debug=True hardcoded | 5 min |
| 8 | MemorySaver → RedisCheckpointer | 4 hours |
| 9 | In-memory → Redis rate limiter | 3 hours |
| 26 | Basic test suite (auth + graph) | 1 week |
| 27 | .env.example file | 15 min |
| 28 | Dockerfile | 30 min |
| 29 | .gitignore | 5 min |

### Phase 2: High Priority — Before User Traffic (Week 3-4)
| # | Finding | Effort |
|---|---------|--------|
| 5 | SECRET_KEY validation in production | 10 min |
| 6 | Input validation/sanitization | 2 hours |
| 10 | Consolidate to single entry point | 1 day |
| 11 | Session expiry 900s → 86400s | 5 min |
| 12 | Remove sync/async duplicates | 3 days |
| 17 | Windows-only path → pathlib | 10 min |
| 18 | Celery event loop anti-pattern | 2 hours |
| 19 | Fix docker-compose.scalable.yml paths | 15 min |

### Phase 3: Medium Priority — Production Polish (Week 5-6)
| # | Finding | Effort |
|---|---------|--------|
| 7 | Anonymize PII in logs | 30 min |
| 13 | Singleton reset() for testing | 2 hours |
| 14 | API versioning (/api/v1/) | 1 hour |
| 15 | Graceful shutdown handling | 1 hour |
| 16 | LLM-based intent classification | 4 hours |
| 20 | Replace print() with logger | 15 min |
| 21 | Modern SQLAlchemy 2.0 mappings | 1 hour |
| 22 | Configurable graph diagram path | 5 min |
| 23 | Alembic migrations setup | 2 hours |
| 24 | Request ID middleware | 1 hour |
| 30 | CI/CD pipeline | 4 hours |

### Phase 4: Low Priority — Continuous Improvement
| # | Finding | Effort |
|---|---------|--------|
| 25 | Proper exception hierarchy | 1 hour |

---

## 8. Summary Checklist

```
Production Readiness Checklist:

Security:
☐ No hardcoded credentials anywhere
☐ CORS restricted to specific origins
☐ DEBUG=false in all environments
☐ SECRET_KEY explicitly set (≥32 chars)
☐ Input validation on all user inputs
☐ PII anonymized in logs
☐ .env.example committed, .env in .gitignore

Architecture:
☐ RedisCheckpointer used (not MemorySaver)
☐ Distributed rate limiting (Redis-backed)
☐ Single entry point (FastAPI async)
☐ Session TTL ≥ 24 hours
☐ No sync/async code duplication
☐ API versioning (/api/v1/)
☐ Graceful shutdown handling
☐ LLM-based intent classification

Code Quality:
☐ Cross-platform paths (pathlib)
☐ Celery tasks use asyncio.run()
☐ Docker paths match project structure
☐ No print() statements
☐ SQLAlchemy 2.0 Mapped[] types
☐ Alembic for migrations
☐ Request ID propagation
☐ Proper exception hierarchy

Testing:
☐ Unit tests for auth
☐ Unit tests for graph nodes
☐ Integration tests for API endpoints
☐ Load test scenarios defined
☐ CI pipeline runs tests automatically

DevOps:
☐ Dockerfile exists and works
☐ docker-compose.yml uses env vars (no hardcoded values)
☐ .gitignore present
☐ CI/CD pipeline (GitHub Actions)
☐ Health checks for all services
☐ Prometheus metrics endpoint
```

---

> **Bottom Line:** The project has a solid foundation with well-implemented components (circuit breaker, retry logic, structured logging, password hashing). The critical gaps are: (1) in-memory state preventing multi-instance deployment, (2) hardcoded credentials, (3) zero test coverage, and (4) missing Dockerfile/.env.example. Addressing Phase 1 items will make the system safe for a staging environment. Completing Phases 1-3 will make it production-ready.
