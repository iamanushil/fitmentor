# FitMentor — Architecture & Key Flows

Reference doc for interviews, onboarding, and project understanding.
See [ROADMAP.md](ROADMAP.md) for the phase-by-phase build plan.

---

## Flow Diagrams

### 1. System architecture

```mermaid
flowchart LR
    User["👤 User"] --> FE["Next.js 14\nVercel"]
    FE -->|"JWT RS256"| API["FastAPI\nECS Fargate"]
    API --> PG["PostgreSQL\nRDS"]
    API --> RD["Redis\nElastiCache"]
    API --> PK["Portkey\nGateway"]
    PK --> OAI["OpenAI\nGPT-4o-mini"]
    API -->|"enqueue job"| SQS["AWS SQS\nFIFO"]
    SQS --> Worker["Worker\nECS Fargate"]
    Worker --> PK
    Worker --> S3["AWS S3\nPDF store"]
    Worker --> PG
    S3 -->|"presigned URL"| FE
```

---

### 2. Auth + lazy user provisioning

> **Interview hook:** How do you validate JWTs without a DB call to an auth server on every request?

```mermaid
sequenceDiagram
    participant C as Client
    participant API as FastAPI middleware
    participant RD as Redis
    participant Clerk as Clerk JWKS endpoint
    participant DB as PostgreSQL

    C->>API: Any request (Bearer JWT)
    API->>RD: GET jwks_cache
    alt cache HIT (24h TTL)
        RD-->>API: JWKS keys
    else cache MISS
        API->>Clerk: GET /.well-known/jwks.json
        Clerk-->>API: JWKS public keys
        API->>RD: SET jwks_cache EX 86400
    end
    API->>API: Verify JWT (RS256, exp, iss, sub)
    API->>DB: SELECT user WHERE clerk_user_id = sub
    alt user exists
        DB-->>API: User row
    else first-ever request (lazy provisioning)
        API->>DB: INSERT user (clerk_user_id, email)
        DB-->>API: New user row
    end
    API-->>C: Request handled with user context
```

---

### 3. Multi-turn chat (Responses API + response_id chaining)

> **Interview hook:** How do you maintain conversation memory without sending full history in every LLM call?

```mermaid
sequenceDiagram
    participant C as Client
    participant API as FastAPI
    participant DB as PostgreSQL
    participant PK as Portkey → OpenAI

    C->>API: POST /conversations/{id}/messages {content}
    API->>DB: SELECT conversation (openai_response_id, status)
    API->>DB: SELECT fitness_profile (system prompt context)
    Note over API: Build system prompt injected with profile
    API->>PK: POST /responses\n{previous_response_id, input, instructions}
    Note over PK: OpenAI resolves prior context\nfrom response_id server-side
    PK-->>API: {id, output, usage {input_tokens, output_tokens}}
    API->>DB: UPDATE conversation SET openai_response_id = new_id
    API->>DB: INSERT message (role, content, tokens, cost_usd)
    API-->>C: {message, tokens_used, cost_usd}
```

---

### 4. SSE streaming

> **Interview hook:** How do you stream LLM tokens to the browser without WebSockets?

```mermaid
sequenceDiagram
    participant C as Client (EventSource)
    participant API as FastAPI StreamingResponse
    participant PK as Portkey → OpenAI

    C->>API: GET /conversations/{id}/stream
    activate API
    API->>PK: POST /responses (stream=True)
    loop Each token delta
        PK-->>API: chunk {delta, finish_reason=null}
        API-->>C: data: {"delta": "..."}\n\n
    end
    PK-->>API: chunk {finish_reason=stop, usage}
    API->>DB: INSERT message + UPDATE conversation response_id
    API-->>C: data: [DONE]\n\n
    deactivate API
```

---

### 5. Async workout plan — SQS claim-check pattern

> **Interview hook:** How do you handle long-running LLM jobs without blocking the HTTP response?

```mermaid
sequenceDiagram
    participant C as Client
    participant API as FastAPI
    participant SQS as AWS SQS FIFO
    participant W as Worker (ECS)
    participant OAI as Portkey → OpenAI
    participant S3 as AWS S3
    participant DB as PostgreSQL

    C->>API: POST /workout-plan/generate
    API->>DB: INSERT workout_plan_job (status=pending)
    API->>SQS: SendMessage {job_id, user_id, params}
    API-->>C: 202 Accepted {job_id}

    Note over W: Long-polling loop (WaitTimeSeconds=20)
    W->>SQS: ReceiveMessage
    SQS-->>W: {job_id, receipt_handle}
    W->>DB: UPDATE job status=processing
    W->>DB: SELECT fitness_profile
    W->>OAI: structured output (WeeklyPlan JSON schema)
    OAI-->>W: {days: [{exercises: [...]}]}
    W->>W: Jinja2 HTML → WeasyPrint PDF
    W->>S3: PutObject (s3_key)
    W->>DB: UPDATE job (status=ready, s3_key)
    W->>SQS: DeleteMessage (ack)

    C->>API: GET /workout-plan/{job_id}
    API->>DB: SELECT job
    API->>S3: generate_presigned_url (TTL 15min)
    API-->>C: {status: ready, pdf_url}
```

---

### 6. User journey end-to-end

```mermaid
flowchart TD
    A([Sign up via Clerk]) --> B["FastAPI lazy-provisions\nuser row on first JWT"]
    B --> C[Profile setup wizard\ngoals, injuries, equipment]
    C --> D[POST /profile — upsert]
    D --> E{Profile complete?}
    E -- No --> C
    E -- Yes --> F[POST /conversations\ncreate thread]
    F --> G[POST /conversations/id/messages]
    G --> H["OpenAI via Portkey\n(previous_response_id chain)"]
    H --> G
    G --> I{Generate plan?}
    I -- Keep chatting --> G
    I -- Yes --> J[POST /workout-plan/generate]
    J --> K[202 — job_id]
    K --> L[Poll GET /workout-plan/job_id]
    L --> M{status = ready?}
    M -- pending/processing --> L
    M -- ready --> N[Presigned S3 URL → PDF download]
```

---

## Schema diagram (ER)

> **Interview hook:** Walk me through your data model and why you chose these relationships.

```mermaid
erDiagram
    users {
        uuid id PK
        text clerk_user_id UK
        text email
        timestamp created_at
        timestamp updated_at
    }
    fitness_profiles {
        uuid id PK
        uuid user_id FK
        jsonb goals
        text experience
        jsonb injuries
        jsonb equipment
        int days_per_week
        int session_minutes
        int height_cm
        numeric weight_kg
        text status
        int version
        timestamp created_at
        timestamp updated_at
    }
    conversations {
        uuid id PK
        uuid user_id FK
        text title
        text openai_response_id
        text status
        timestamptz expires_at
        timestamp created_at
        timestamp updated_at
    }
    messages {
        uuid id PK
        uuid conversation_id FK
        text role
        int tokens_input
        int tokens_output
        numeric cost_usd
        timestamp created_at
    }
    workout_plan_jobs {
        uuid id PK
        uuid user_id FK
        text status
        text s3_key
        text pdf_url
        jsonb params
        text error
        timestamp created_at
        timestamp updated_at
    }

    users ||--o| fitness_profiles : "has one profile"
    users ||--o{ conversations : "owns many"
    users ||--o{ workout_plan_jobs : "requests many"
    conversations ||--o{ messages : "contains many"
```

**Key design decisions:**
- `users.clerk_user_id` — Clerk is source of truth; we store a local row for FK relationships only (lazy-provisioned on first JWT)
- `fitness_profiles.goals / injuries / equipment` — JSONB for flexibility; shape changes as product evolves without migrations
- `conversations.openai_response_id` — stores last Responses API ID, enabling multi-turn memory server-side without sending full history
- `workout_plan_jobs.pdf_url` — presigned URL refreshed on each `GET`; never stale in DB
- `messages.cost_usd` — tracked per message for observability and rate-limit budgeting

---

## Class diagram (service + ORM layer)

> **Interview hook:** How is your backend code organised? What does the service layer do?

```mermaid
classDiagram
    direction TB

    class User {
        +UUID id
        +str clerk_user_id
        +str email
        +datetime created_at
    }
    class FitnessProfile {
        +UUID id
        +UUID user_id
        +list goals
        +str experience
        +list injuries
        +list equipment
        +int days_per_week
        +int session_minutes
        +str status
        +int version
    }
    class Conversation {
        +UUID id
        +UUID user_id
        +str openai_response_id
        +str status
        +datetime expires_at
        +is_expired() bool
    }
    class Message {
        +UUID id
        +UUID conversation_id
        +str role
        +str content
        +int tokens_input
        +int tokens_output
        +Decimal cost_usd
    }
    class WorkoutPlanJob {
        +UUID id
        +UUID user_id
        +str status
        +str s3_key
        +str pdf_url
        +dict params
        +is_terminal() bool
    }

    class ProfileService {
        +upsert(user_id, data) FitnessProfile
        +get_me(user_id) FitnessProfile
        -invalidate_cache(user_id)
    }
    class ConversationService {
        +create(user_id, first_msg) Conversation
        +append(conv_id, content) Message
        +get_history(conv_id) list~Message~
        +expire_stale() int
    }
    class WorkoutPlanService {
        +enqueue(user_id, params) WorkoutPlanJob
        +get_status(job_id) WorkoutPlanJob
    }
    class LLMService {
        +chat(prev_response_id, input, system) Response
        +structured_output(prompt, schema) dict
        +estimate_cost(model, usage) Decimal
    }
    class WorkerHandler {
        +handle(job_id)
        -fetch_profile(user_id) FitnessProfile
        -generate_plan(profile) dict
        -render_pdf(plan) bytes
        -upload_s3(pdf_bytes) str
        -update_job(job_id, s3_key)
    }

    %% ORM relationships
    User "1" --> "0..1" FitnessProfile : has
    User "1" --> "*" Conversation : owns
    User "1" --> "*" WorkoutPlanJob : requests
    Conversation "1" --> "*" Message : contains

    %% Service → model dependencies
    ProfileService ..> FitnessProfile : manages
    ConversationService ..> Conversation : manages
    ConversationService ..> Message : creates
    ConversationService ..> LLMService : calls
    WorkoutPlanService ..> WorkoutPlanJob : manages
    WorkerHandler ..> LLMService : calls
    WorkerHandler ..> WorkoutPlanJob : updates
    WorkerHandler ..> FitnessProfile : reads
```

**Layering rule:** routers → services → repositories → ORM models. Services own business logic; repositories own DB queries; routers own HTTP shape only.
