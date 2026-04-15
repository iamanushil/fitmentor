# FitMentor — 2-Week Build Roadmap

An AI Fitness Coach backend + frontend, architected like a production system.

---

## Elevator pitch

FitMentor is an async, LLM-powered fitness coaching platform. Users create a fitness profile (goals, injuries, equipment, schedule, experience), chat with an AI coach that's aware of that profile, and trigger background jobs that generate a personalized weekly workout PDF delivered via S3 presigned URL.

---

## Tech stack

**Backend:** Python 3.11, FastAPI, SQLAlchemy 2.0 (async), asyncpg, Alembic, Pydantic v2, structlog

**Data:** PostgreSQL 15, Redis 7

**AI:** OpenAI GPT-4o-mini via Portkey gateway

**Async jobs:** AWS SQS (FIFO), S3

**Auth:** Clerk (JWT RS256, JWKS)

**Frontend:** Next.js 14 (App Router), TypeScript, TailwindCSS, shadcn/ui

**PDF:** WeasyPrint or ReportLab

**Deploy:** Docker, AWS ECS Fargate, RDS, ElastiCache, GitHub Actions

---

## Architecture

```
┌─────────────────────┐       ┌──────────────────────────┐
│  Next.js (Vercel)   │──JWT─▶│  FastAPI API (ECS)       │
└─────────────────────┘       │  • /auth validates JWKS  │
                              │  • /profile (CRUD)       │
                              │  • /conversations        │
                              │  • /workout-plan/generate│
                              └──────────┬───────────────┘
                                         │
                    ┌────────────────────┼──────────────────┬─────────────┐
                    ▼                    ▼                  ▼             ▼
              PostgreSQL (RDS)       Redis (EC)         Portkey→OpenAI   AWS SQS
              profiles, convos,      profile cache      chat + plan gen  (FIFO)
              messages, jobs                                              │
                    ▲                                                     │
                    │                                                     ▼
                    │                                            ┌─────────────────┐
                    └────────────────────────────────────────────│  Worker (ECS)   │
                                                                 │  • poll SQS     │
                                                                 │  • LLM plan gen │
                                                                 │  • render PDF   │
                                                                 │  • upload S3    │
                                                                 │  • update DB    │
                                                                 └─────────────────┘
```

---

## Data model

```sql
-- users (optional if using Clerk as source of truth)
users(id uuid PK, clerk_user_id text unique, email text, created_at, updated_at)

-- profile: the "who is this person"
fitness_profiles(
  id uuid PK,
  user_id uuid FK,
  goals jsonb,              -- ["lose_fat", "build_strength"]
  experience text,          -- "beginner" | "intermediate" | "advanced"
  injuries jsonb,           -- [{body_part, notes}]
  equipment jsonb,          -- ["dumbbells", "pullup_bar"]
  days_per_week int,
  session_minutes int,
  height_cm int, weight_kg numeric,
  status text,              -- "pending" | "ready"
  version int,
  created_at, updated_at
)

-- conversation threading (mirrors Digii)
conversations(
  id uuid PK,
  user_id uuid FK,
  title text,
  openai_response_id text,  -- last response_id for multi-turn
  status text,              -- "active" | "expired"
  expires_at timestamptz,
  created_at, updated_at
)

messages(
  id uuid PK,
  conversation_id uuid FK,
  role text,                -- "user" | "assistant" | "system"
  content text,
  tokens_input int,
  tokens_output int,
  cost_usd numeric(10,6),
  created_at
)

-- background jobs
workout_plan_jobs(
  id uuid PK,
  user_id uuid FK,
  status text,              -- "pending" | "processing" | "ready" | "failed"
  s3_key text,
  pdf_url text,             -- presigned, refreshed on fetch
  params jsonb,             -- week date range, focus
  error text,
  created_at, updated_at
)
```

---

## Day-by-day plan

### Day 1 — Foundation ✅
- [x] `git init`, repo structure (see SCAFFOLD below)
- [x] `docker-compose.yml`: postgres, redis
- [x] FastAPI app with `/health`, structlog JSON logging, request-id middleware
- [x] Pydantic Settings from `.env`
- [x] Pre-commit: ruff, black, mypy

### Day 2 — Auth + DB
- [ ] Alembic init + first migration (users, fitness_profiles)
- [ ] Async SQLAlchemy session factory
- [ ] Clerk JWT verification middleware (fetch JWKS, cache in Redis 24h)
- [ ] Dependency: `get_current_user()` → pulls/creates user row from Clerk sub

### Day 3 — Profile service
- [ ] `POST /api/v1/profile` — upsert
- [ ] `GET /api/v1/profile/me`
- [ ] Redis cache layer (24h TTL, invalidated on update)
- [ ] Repository + service layer separation
- [ ] Unit tests for profile service (pytest + pytest-asyncio)

### Day 4 — Portkey + LLM wrapper
- [ ] Sign up for Portkey free tier, create virtual key for OpenAI
- [ ] `services/llm.py`: wraps Portkey client, retry/backoff via tenacity
- [ ] Cost tracker: maps model → $/1M tokens, computes per-call cost
- [ ] System prompt template with profile injection

### Day 5–6 — Chat service
- [ ] Migration: conversations, messages
- [ ] `POST /api/v1/conversations` → create + first message
- [ ] `POST /api/v1/conversations/{id}/messages` → append
- [ ] Use OpenAI Responses API with `previous_response_id` for memory
- [ ] Persist tokens + cost per message
- [ ] `GET /api/v1/conversations/{id}` → full history
- [ ] APScheduler cleanup job: mark conversations expired after 2h inactive

### Day 7 — Streaming + polish
- [ ] SSE endpoint: `GET /api/v1/conversations/{id}/stream`
- [ ] Rate limiter (slowapi or custom Redis token bucket)
- [ ] OpenAPI docs cleanup, examples
- [ ] Integration tests hitting real Postgres (use testcontainers)

### Day 8 — SQS + S3 setup
- [ ] Terraform or AWS CLI: create SQS FIFO queue, S3 bucket, IAM roles
- [ ] `services/sqs.py`: aioboto3 wrapper (send, receive, delete)
- [ ] `services/storage.py`: S3 upload + presigned URL
- [ ] Migration: `workout_plan_jobs`

### Day 9 — Worker process
- [ ] Separate entrypoint: `python -m fitmentor.worker`
- [ ] SQS long-poll loop with graceful shutdown (SIGTERM)
- [ ] Job handler: fetch profile → LLM structured output → PDF render → S3 upload → DB update
- [ ] Use OpenAI JSON mode with a Pydantic schema for the plan structure
- [ ] Retry logic: on failure, increment attempt count, dead-letter queue after 3

### Day 10 — PDF generation
- [ ] Plan schema: `WeeklyPlan(days: [DayPlan(exercises: [Exercise])])`
- [ ] Jinja2 HTML template → WeasyPrint PDF (branded, clean)
- [ ] `POST /api/v1/workout-plan/generate` → enqueue + return job_id
- [ ] `GET /api/v1/workout-plan/{job_id}` → status + presigned URL when ready

### Day 11 — Frontend scaffold
- [ ] `npx create-next-app@latest fitmentor-web --ts --tailwind --app`
- [ ] Clerk setup (middleware, sign-in page)
- [ ] API client with auth token injection
- [ ] Profile setup wizard (multi-step form, react-hook-form + zod)

### Day 12 — Frontend chat
- [ ] Chat page with message list + composer
- [ ] SSE streaming of assistant responses
- [ ] "Generate weekly plan" CTA → polls job status → downloads PDF
- [ ] Past plans list

### Day 13 — Containerize + deploy
- [ ] Dockerfile (multi-stage, ~150MB image)
- [ ] ECS task definitions: api, worker (separate services)
- [ ] RDS Postgres (db.t4g.micro), ElastiCache Redis
- [ ] Secrets Manager for OPENAI_API_KEY, PORTKEY_API_KEY, DB_URL, JWT secrets
- [ ] Application Load Balancer + HTTPS via ACM
- [ ] Vercel for Next.js

### Day 14 — CI/CD, docs, demo
- [ ] GitHub Actions: test → build → push ECR → update ECS service
- [ ] README with architecture diagram (draw.io or excalidraw)
- [ ] Loom demo video (3–5 min)
- [ ] LinkedIn post announcing the project

---

## What you'll learn (map to resume bullets)

| Skill | Where you learn it |
|---|---|
| Async Python, FastAPI | Days 1–7 |
| SQLAlchemy 2.0 async + Alembic | Days 2, 5 |
| LLM integration patterns (gateway, retries, cost tracking) | Day 4 |
| Multi-turn conversation memory (Responses API) | Day 6 |
| SSE streaming | Day 7 |
| AWS SQS / claim-check pattern | Days 8–9 |
| PDF generation | Day 10 |
| JWT RS256 + JWKS validation | Day 2 |
| Dockerizing Python services | Day 13 |
| AWS ECS Fargate deployment | Day 13 |
| GitHub Actions CI/CD | Day 14 |
| Next.js 14 App Router + Clerk auth | Days 11–12 |

---

## Resume bullet examples

- Designed and shipped FitMentor, a production-grade AI fitness coach serving personalized chat and generating branded PDF workout plans on demand.
- Built an async FastAPI backend with PostgreSQL, Redis, and AWS SQS; achieved p95 chat latency of <2s using Portkey gateway caching and OpenAI Responses API threading.
- Implemented claim-check pattern (SQS + S3) to decouple long-running PDF generation from the request path, supporting retry, dead-letter, and idempotent workers.
- Deployed on AWS ECS Fargate with RDS, ElastiCache, ALB, and Secrets Manager, orchestrated via GitHub Actions CI/CD.
- Frontend in Next.js 14 with Clerk JWT auth; streamed assistant responses via SSE.

---

## Starter scaffold

Expected repo layout:

```
fitmentor/
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── migrations/
│   ├── docker-compose.yml
│   ├── Dockerfile
│   ├── .env.example
│   └── src/fitmentor/
│       ├── __init__.py
│       ├── main.py              # FastAPI app factory
│       ├── worker.py            # SQS worker entrypoint
│       ├── config.py            # Pydantic settings
│       ├── logging_config.py
│       ├── auth/
│       │   ├── clerk.py         # JWKS fetch + verify
│       │   └── deps.py          # get_current_user dependency
│       ├── db/
│       │   ├── session.py
│       │   └── models.py
│       ├── api/v1/
│       │   ├── router.py
│       │   ├── profile.py
│       │   ├── conversations.py
│       │   └── workout_plan.py
│       ├── schemas/
│       ├── services/
│       │   ├── llm.py           # Portkey wrapper
│       │   ├── profile.py
│       │   ├── conversation.py
│       │   ├── sqs.py
│       │   ├── storage.py
│       │   └── pdf.py
│       ├── repositories/
│       ├── cache/redis_client.py
│       └── workers/
│           └── workout_plan_worker.py
├── frontend/                    # Next.js 14 app (Day 11)
└── infra/
    └── terraform/               # optional but nice
```

---

## First commands to run

```bash
cd fitmentor/backend
poetry init -n
poetry add fastapi uvicorn[standard] sqlalchemy[asyncio] asyncpg alembic \
  pydantic-settings structlog python-jose[cryptography] httpx tenacity \
  redis aioboto3 portkey-ai openai apscheduler weasyprint jinja2
poetry add --group dev pytest pytest-asyncio ruff black mypy testcontainers

docker compose up -d postgres redis
alembic init migrations
uvicorn fitmentor.main:app --reload
```

---

## Reference patterns to steal from the Digii codebase

Open the Digii repo alongside yours. Specifically study:

- `src/student_mentor/main.py` — app factory, lifespan
- `src/student_mentor/auth/` — JWT RS256 + JWKS caching
- `src/student_mentor/services/llm.py` — Portkey wrapper with retries
- `src/student_mentor/services/conversation.py` — response_id threading
- `src/student_mentor/workers/queue_consumer.py` — SQS poll loop
- `src/student_mentor/cache/` — Redis wrapper
- `migrations/` — Alembic async setup

Read them to understand the *shape*; don't copy-paste. Retyping teaches you more than copying.

---

## Success criteria

By end of Day 14 you should be able to demo:
1. Sign up on the web app, fill out profile
2. Chat with the AI coach and get profile-aware responses
3. Click "generate weekly plan," wait ~30s, download a branded PDF
4. Show the deployed URLs + GitHub repo + architecture diagram

That's a portfolio-grade project that tells a clear story in interviews.
