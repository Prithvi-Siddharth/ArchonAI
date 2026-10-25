# ☁️ ArchonAI — Multi-Agent Cloud Architecture Designer

ArchonAI takes a plain-English software requirement — "design an e-commerce platform for
500,000 concurrent users" — and runs it through a team of specialized AI agents, orchestrated
by **LangGraph**, that analyze the requirement, design an AWS architecture, attack it from
every angle (compute, database, networking, security, reliability, cost), critique it, and
revise it until it holds up. The output is a structured architecture recommendation report,
not a chat transcript.

This is a portfolio project built to demonstrate genuine **agentic AI system design** — a
graph of cooperating, stateful agents with a real decision loop — as opposed to a chatbot
wrapped around a single prompt.

## Problem Statement

Designing a production-grade cloud architecture requires reasoning across a dozen
simultaneously-moving concerns: will this scale, is it actually highly available or just
theoretically so, is the database going to fall over under this write pattern, is the
"secure" design actually enforcing least privilege, and what does all of this cost? A single
LLM call asked to "design an architecture" will happily produce something plausible-sounding
that quietly ignores half of those concerns, because nothing forces it to check its own work.

## Why Cloud Architecture Is Hard

- **Cross-cutting concerns compete.** Every extra 9 of availability, every millisecond of
  latency shaved off, and every additional layer of security tends to cost more and add
  operational complexity. There's rarely a single "correct" answer, only trade-offs.
- **Failure modes are non-obvious.** A design can look fine on a whiteboard and still have a
  single point of failure, an unprotected database, or a scaling bottleneck that only shows
  up under load.
- **Requirements are usually under-specified.** "High availability" and "must scale" are not
  numbers — turning them into concrete infrastructure decisions requires judgment.
- **Nobody reviews their own work objectively.** The entity that designed the system is a poor
  judge of what's wrong with it.

## The Solution

ArchonAI mirrors how a real architecture review actually happens: one team designs, several
specialists analyze the design from their own domain, and a critical reviewer — who did not
write the design — decides whether it's good enough, sending it back for rework if it isn't.
That review loop, with a hard cap on how many times it can bounce back and forth, is the crux
of the system and the reason it's built on LangGraph instead of a linear prompt chain.

## System Architecture

```
                          USER REQUEST
                               │
                               ▼
                     Requirements Analyzer
                               │
                               ▼
                     Architecture Planner
                               │
                               ▼
                     Architecture Designer  ◄── searches the AWS service
                               │                 knowledge base via real
                    ┌──────────┴──────────┐          LLM tool calls
                    ▼                     ▼
              Compute Agent         Database Agent
                    │                     │
                    └──────────┬──────────┘
                    ┌──────────┴──────────┐
                    ▼                     ▼
             Networking Agent       Security Agent
                    │                     │
                    └──────────┬──────────┘
                    ┌──────────┴──────────┐
                    ▼                     ▼
             Reliability Agent       Cost Agent
                    │                     │
                    └──────────┬──────────┘
                               ▼
                    Architecture Validator          (deterministic rule checks)
                               │
                               ▼
                     Architecture Critic  ◄─────────────┐
                               │                          │
                 ┌─────────────┴─────────────┐            │
              approved                    rejected        │
                 │                             │           │
                 │                             ▼           │
                 │                  Architecture Revision ─┘
                 ▼            (loops back to the critic, max 2 times)
                 │  ◄── also reached if MAX_REVISIONS is hit while still rejected
           Final Report
                 │
                 ▼
                END
```

Everything above is implemented as an actual `langgraph.graph.StateGraph` in
[graph/workflow.py](graph/workflow.py) — not a diagram that was drawn and then abandoned.

## Why This Is an Agentic AI Application (and not a chatbot)

It's tempting to build "agentic" systems that are really just `LLM → LLM → LLM → answer`. That
is a pipeline, not an agent system, because nothing in it makes a decision that changes the
control flow. ArchonAI is built specifically to avoid that:

1. **Real branching control flow.** `graph.add_conditional_edges` on the critic node routes to
   three different destinations (`final_report`, `architecture_revision`, or `final_report`
   again via the forced max-revision path) based on the *content* of the critic's structured
   output — not a fixed sequence.
2. **A genuine feedback loop.** The Architecture Revision agent doesn't run once; it runs
   however many times the critic keeps rejecting the design (up to `MAX_REVISIONS = 2`), each
   time consuming the previous critique as input and producing a new architecture that's fed
   straight back to the same critic node.
3. **Bounded autonomy, not an infinite loop.** `_route_after_critic` in
   [graph/workflow.py](graph/workflow.py) checks `revision_count` against `MAX_REVISIONS` and
   forces termination via the final report even if the critic never approves — the graph is
   guaranteed to halt.
4. **Parallel, stateful fan-out/fan-in.** Compute and Database analysis run concurrently as
   independent graph branches, join, then Networking and Security run concurrently and join,
   then Reliability and Cost run concurrently and join again before the validator — three
   two-agent bursts instead of one large one, all coordinated through one shared, typed state
   object (`graph/state.py`) rather than each agent managing its own context. (Two agents per
   stage, rather than all six at once, was a deliberate choice to keep peak concurrent LLM
   calls low on rate-limited API keys — see the note in `graph/workflow.py`.)
5. **Real tool use.** The Architecture Designer agent binds a LangChain `@tool`
   (`search_aws_services_tool`) to the LLM and runs an actual tool-calling loop — the model
   decides what to search for, receives real tool output, and only then produces its design —
   rather than the "tool" being a function the Python code calls on the model's behalf.
6. **A deterministic check the LLM can't talk its way around.** The Architecture Validator
   node runs plain Python rule checks (no LLM) and hands its findings to the critic as
   ground truth, so the system doesn't rely entirely on an LLM's self-assessment.

## LangGraph Workflow

| # | Node | Type | Responsibility |
|---|------|------|-----------------|
| 1 | Requirements Analyzer | LLM (structured output) | Extracts structured requirements from free text |
| 2 | Architecture Planner | LLM (structured output) | Plans the 12 architectural concerns to address |
| 3 | Architecture Designer | LLM + real tool calls | Searches the AWS knowledge base, proposes the initial architecture |
| 4 | Compute Agent | LLM (structured output) | Analyzes compute service choice, scaling, statelessness |
| 5 | Database Agent | LLM (structured output) | Analyzes data model, replication, partitioning, backups |
| 6 | Networking Agent | LLM (structured output) | Analyzes VPC/subnet design, AZ distribution, load balancing |
| 7 | Security Agent | LLM (structured output) | Analyzes IAM, encryption, secrets, WAF, audit logging |
| 8 | Reliability Agent | LLM (structured output) | Analyzes HA, fault tolerance, disaster recovery |
| 9 | Cost Agent | Deterministic tool + LLM | Runs the rule-based cost estimator, then reasons about trade-offs |
| 10 | Architecture Validator | Deterministic (no LLM) | Rule-based anti-pattern detection |
| 11 | Architecture Critic | LLM (structured output) | Approves or rejects the architecture; this is the decision point |
| 12 | Architecture Revision | LLM (structured output) | Produces a new architecture addressing the critic's required changes |
| 13 | Final Report | LLM (structured output) | Synthesizes everything into the final recommendation |

Nodes run in three parallel pairs (a genuine LangGraph fan-out/fan-in each time): 4+5, then
6+7, then 8+9. Node 11 is a conditional-edge decision point; node 12 only runs when the critic
rejects, and always routes back to node 11.

### Shared State

Every node reads from and writes to one typed `ArchonState` (`graph/state.py`), so agents
never need to pass context to each other directly. It carries `user_request`, `requirements`,
`architecture_plan`, `architecture`, each specialist's analysis, `validation_results`,
`critic_review`, `revision_count`, a full `execution_trace`, and the `final_report`.

`execution_trace` is annotated with a LangGraph reducer (`Annotated[list[TraceEntry],
operator.add]`) because multiple parallel branches write to it in the same superstep —
LangGraph rejects concurrent writes to a plain field without a reducer telling it how to merge
them, which is a real constraint you run into the moment you build a genuinely parallel graph.

### Conditional Routing

```python
def _route_after_critic(state: ArchonState) -> str:
    review = state["critic_review"]
    revision_count = state.get("revision_count", 0)
    if review.approved:
        return "approved"
    if revision_count >= MAX_REVISIONS:
        return "max_revisions_reached"
    return "rejected"
```

This function is wired in via `graph.add_conditional_edges`, and is the only place that decides
whether the graph moves forward to the final report or loops back for another revision.

### Critic / Revision Loop

The critic (`agents/critic.py`) is given the requirements, the full architecture, every
specialist analysis, and the deterministic validator's findings, and is instructed that any
unresolved *critical* validator finding forces rejection, and that approval requires a score
of 80+ with no critical issues. If rejected, the revision agent (`agents/revision.py`) takes
the critic's `required_changes` and produces a new architecture version with a `change_log`
explaining what changed and why — then the graph sends it straight back to the critic. This
can happen at most `MAX_REVISIONS = 2` times before the graph forces a final report regardless
of approval status, so it can never loop forever.

## Tools

| Tool | File | Type | Purpose |
|------|------|------|---------|
| AWS Service Search | [tools/aws_service_search.py](tools/aws_service_search.py) | Real LangChain `@tool`, LLM-invoked | Searches [data/aws_services.json](data/aws_services.json) so the Architecture Designer grounds its service choices in real service data instead of hallucinating |
| Architecture Validator | [tools/architecture_validator.py](tools/architecture_validator.py) | Deterministic Python | Rule-based checks for anti-patterns (missing load balancer, single-AZ HA claims, unbacked databases, public database exposure, missing caching under high read load, etc.) |
| Cost Estimator | [tools/cost_estimator.py](tools/cost_estimator.py) | Deterministic Python | Rule-based, order-of-magnitude monthly cost range, explicitly labeled as an educational estimate — not an AWS quote |

## AWS Services

[data/aws_services.json](data/aws_services.json) is a curated knowledge base of 26 AWS
services (Route 53, CloudFront, API Gateway, ALB, ECS, EKS, Lambda, EC2, RDS, Aurora,
DynamoDB, ElastiCache, S3, SQS, SNS, EventBridge, VPC, IAM, WAF, CloudWatch, Secrets Manager,
KMS, Auto Scaling, AWS Backup, X-Ray, and Shield), each with a description, common use cases,
strengths, and limitations. The Architecture Designer is explicitly instructed not to select
every available service — only what the specific requirements justify — and must give a
concrete reason for each one it picks.

## REST API

ArchonAI is served as a **FastAPI** application ([api/main.py](api/main.py)). The API layer is
deliberately thin: it validates the request, calls the existing `run_workflow()` from
[graph/workflow.py](graph/workflow.py) unchanged, and serializes the result. All
design/analysis/critique logic stays in `agents/` and `graph/`.

Interactive docs are available at **http://localhost:8000/docs** once the server is running.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness check. Does not call the LLM. |
| `GET` | `/api/v1/architectures/examples` | Example prompts (stored in [data/example_prompts.json](data/example_prompts.json)). |
| `POST` | `/api/v1/architectures` | Runs the full multi-agent workflow and returns the result (synchronous). |
| `POST` | `/api/v1/architectures/jobs` | Queues a design request and returns a `job_id` immediately (`202`). |
| `GET` | `/api/v1/architectures/jobs/{job_id}` | Job status, plus the full result once it has succeeded. |

For anything beyond a quick test, prefer the **job endpoints** (see
[Background Jobs](#background-jobs) below): they don't hold a connection open for minutes.

### Example requests

```bash
curl http://localhost:8000/health
# {"status":"ok"}

curl http://localhost:8000/api/v1/architectures/examples

curl -X POST http://localhost:8000/api/v1/architectures \
  -H "Content-Type: application/json" \
  -d '{"user_request": "Design a blogging platform for 10,000 users"}' \
  --max-time 900
```

`POST /api/v1/architectures` is **synchronous** -- the request stays open until the whole
workflow finishes, which typically takes a few minutes (longer if Groq rate limits trigger
backoff). Use a generous client timeout.

**Request body:** `{"user_request": "<10-4000 characters>"}`. Surrounding whitespace is
trimmed; blank, too-short, or too-long input is rejected with `422` before any LLM call.

**Response (`200`):** the full run result -- `approved`, `max_revisions_reached`,
`revision_count`, `requirements`, `architecture_plan`, `architecture` (services + data flow),
the five specialist analyses, `cost_analysis`, `validation_results`, `critic_review`,
`final_report`, and the `execution_trace`. These reuse the Pydantic models in
[models/schemas.py](models/schemas.py).

**Errors** return `{"detail": "<message>"}` with a generic, client-safe message. Full
exception details are logged server-side only and never returned to the client.

| Status | When |
|--------|------|
| `422` | Invalid request body |
| `429` | Groq rate limit still exceeded after automatic retries |
| `500` | Unexpected internal error |
| `502` | LLM provider error or invalid structured output |
| `503` | `GROQ_API_KEY` is not configured |
| `504` | LLM provider timed out |

Note that if only the critic, revision, or report LLM call fails, the workflow's existing
fallbacks still complete the run, so the API returns `200` -- check `approved` and the
`execution_trace` to see what happened.

## Background Jobs

A design run takes minutes, so the job endpoints run it in the background instead of inside
the HTTP request:

```
POST /jobs ──► MySQL (job saved as queued) ──► Redis queue ──► Celery worker
                                                                   │
GET /jobs/{id} ◄── MySQL (status + result) ◄── run_workflow() ◄────┘
```

1. `POST /api/v1/architectures/jobs` stores the job in **MySQL**, sends its id to **Redis**,
   and returns `202` with a `job_id` straight away.
2. A **Celery worker** ([jobs/tasks.py](jobs/tasks.py)) picks it up and runs the same
   `run_workflow()` -- via [jobs/runner.py](jobs/runner.py) -- then stores the result (or a
   client-safe error) in MySQL.
3. `GET /api/v1/architectures/jobs/{job_id}` reads the job from MySQL. Poll it until the
   status is `succeeded` or `failed`.

**Job statuses:** `queued → running → succeeded | failed`. Every change is a guarded database
update ([jobs/repository.py](jobs/repository.py)), so a job can't run twice or change after
it has finished.

**Reliability** (configured in [jobs/celery_app.py](jobs/celery_app.py)):
- **Retries** -- temporary failures (Groq rate limit, timeout, network error) put the job back
  to `queued` and retry after `JOB_RETRY_DELAY_SECONDS`, up to `JOB_MAX_RETRIES` times.
  Permanent failures (missing key, invalid model output) fail immediately.
- **Time limit** -- a job running longer than `JOB_TIMEOUT_SECONDS` is stopped and marked
  `failed` with `504`.
- **Crash recovery** -- jobs are acknowledged to Redis only after they finish, so if a worker
  dies mid-run the job is handed back and run again (within the retry limit).

### Example

```bash
curl -X POST http://localhost:8000/api/v1/architectures/jobs \
  -H "Content-Type: application/json" \
  -d '{"user_request": "Design a blogging platform for 10,000 users"}'
# {"job_id":"3f2a…","status":"queued","status_url":"/api/v1/architectures/jobs/3f2a…"}

curl http://localhost:8000/api/v1/architectures/jobs/3f2a…
# {"job_id":"3f2a…","status":"running","attempts":1,…,"result":null}
# … later: "status":"succeeded" with the full "result"
```

| Status | When |
|--------|------|
| `202` | Job accepted |
| `404` | Unknown `job_id` |
| `422` | Invalid request body |
| `503` | MySQL (job store) or Redis (job queue) unavailable |

A failed job is still a `200` on `GET` -- its `error` field holds the status code and message
(e.g. `429`, `502`, `503`, `504`) using the same rules as the synchronous endpoint.

### Job settings

All optional; the defaults match the docker-compose setup (see [.env.example](.env.example)).

| Variable | Default | Meaning |
|----------|---------|---------|
| `DATABASE_URL` | `mysql+pymysql://archon:archon@localhost:3306/archonai` | Job store |
| `REDIS_URL` | `redis://localhost:6379/0` | Job queue |
| `WORKER_CONCURRENCY` | `1` | Jobs a worker runs at once |
| `JOB_MAX_RETRIES` | `1` | Retries after a temporary failure |
| `JOB_RETRY_DELAY_SECONDS` | `60` | Wait before a retry |
| `JOB_TIMEOUT_SECONDS` | `900` | Time limit per job |

**Worker concurrency:** keep it at `1` on a Groq free-tier key. Each run already makes several
LLM calls in parallel, so the Groq rate limit -- not CPU -- is the bottleneck; more concurrent
jobs mostly means more `429`s. To change it, set `WORKER_CONCURRENCY` in `.env` and restart the
worker (or pass `--concurrency=N` when starting it locally). Raise it only while measured
jobs-per-hour keeps improving.

## Project Structure

```
archonai/
├── api/                         # FastAPI layer (thin: validate, run workflow, serialize)
│   ├── main.py                  # App entry point + /health
│   ├── routes/architectures.py  # /api/v1/architectures endpoints (sync + jobs)
│   ├── errors.py                # Shared failure -> status code/message rules
│   ├── schemas.py               # Request/response models
│   └── examples.py              # Loads data/example_prompts.json
├── jobs/                        # Background job system (shared by API and worker)
│   ├── config.py                # Job settings from the environment
│   ├── db.py / models.py        # MySQL connection + architecture_jobs table
│   ├── repository.py            # Create/read jobs, guarded status changes
│   ├── runner.py                # execute_job(): run the workflow, store the outcome
│   ├── celery_app.py            # Celery app (Redis broker, retries, time limits)
│   └── tasks.py                 # Celery task wrapping execute_job()
├── agents/                      # One module per graph node's LLM logic
│   ├── llm.py                   # Modular LLM provider layer (Groq today, Bedrock-ready)
│   ├── requirements.py / planner.py / architecture.py
│   ├── compute.py / database.py / networking.py
│   ├── security.py / reliability.py / cost.py
│   ├── critic.py / revision.py / report.py
├── graph/
│   ├── state.py                 # Typed ArchonState + trace helpers
│   └── workflow.py               # StateGraph wiring, routing, streaming
├── tools/
│   ├── aws_service_search.py
│   ├── architecture_validator.py
│   └── cost_estimator.py
├── models/schemas.py             # All Pydantic structured-output schemas
├── data/
│   ├── aws_services.json         # AWS service knowledge base
│   └── example_prompts.json      # Example prompts served by the API
├── tests/                        # pytest suite, LLM calls mocked
├── Dockerfile                    # Image used by both the api and worker services
└── docker-compose.yml            # mysql, redis, api, worker
```

## Setup

### Prerequisites

- Python 3.11+
- A [Groq API key](https://console.groq.com/keys) (free tier available)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) -- for MySQL and Redis
  (needed by the job endpoints), or to run everything in containers

### Environment Variables

Copy the example file and fill in your key:

```bash
cp .env.example .env
```

| Variable | Required | Description |
|----------|----------|--------------|
| `GROQ_API_KEY` | Yes | Your Groq API key. Get one at https://console.groq.com/keys |
| `GROQ_MODEL` | No (defaults to `qwen/qwen3.8-27b`) | Must reliably honor forced tool-calling, since this app uses `with_structured_output` everywhere and real tool calls in the Architecture Designer. Groq's free-tier quotas are per-model (both a rolling tokens-per-minute limit and a separate tokens-per-day limit), so which model works best for you varies with what you've already used that day. Of the three tested during development, `openai/gpt-oss-120b` is the most reliable at structured output but has the lowest free-tier daily cap; `openai/gpt-oss-20b` occasionally mis-cases a tool name in a way Groq rejects. Groq's lineup changes over time -- list what's available to your key with `python -c "from groq import Groq; import os; [print(m.id) for m in Groq(api_key=os.environ['GROQ_API_KEY']).models.list().data]"` |

`.env` is git-ignored — never commit real credentials. `.env.example` contains placeholders
only.

### Option A: Run everything with Docker (one command)

```bash
cp .env.example .env               # then edit .env with your real GROQ_API_KEY
docker compose up -d --build       # starts mysql, redis, api, worker
docker compose ps                  # all four should be up (api/mysql/redis "healthy")
```

Open http://localhost:8000/docs. Useful commands:

```bash
docker compose logs -f worker      # watch jobs being processed
docker compose restart worker      # e.g. after changing WORKER_CONCURRENCY in .env
docker compose up -d --build       # rebuild after code changes
docker compose down                # stop everything (MySQL data is kept)
docker compose down -v             # stop and DELETE all stored jobs
```

### Option B: Local development (code changes reload quickly)

Run only MySQL and Redis in Docker, and the API and worker from your virtualenv:

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then edit .env with your real GROQ_API_KEY

docker compose up -d mysql redis

# terminal 1 -- the API (auto-reloads on code changes)
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# terminal 2 -- the worker (restart it manually after code changes)
celery -A jobs.celery_app worker --loglevel=info
```

Use **one option at a time**: if the Docker `api`/`worker` containers are running, stop them
(`docker compose stop api worker`) before starting uvicorn/celery locally, or port 8000 will
clash and two workers will share the queue.

`/health` and the synchronous `POST /api/v1/architectures` work without MySQL or Redis; only the
job endpoints need them.

### Run the Tests

```bash
pytest -v
```

The entire test suite mocks the LLM layer (`agents.llm.get_llm` / `invoke_structured`), so it
runs with no API key and no network access, including full end-to-end graph runs that exercise
the critic/revision loop and the max-revision cutoff. `tests/test_api.py` drives the same
mocked workflow through the HTTP API with FastAPI's `TestClient`, covering validation, JSON
serialization, and the error-to-status-code mapping. `tests/test_jobs.py` covers the job
system -- submission, status, success, retries, time limits, crash recovery and outages --
using in-memory SQLite and Celery's eager mode, so no Docker, MySQL, Redis or worker is
needed either.

## Example Prompts

- *"Design an e-commerce platform that supports 500,000 concurrent users, requires high
  availability, low latency, secure payment processing, and must scale during traffic spikes."*
- *"Design a banking transaction system that processes 10,000 transactions per second, requires
  strong consistency, end-to-end encryption, regulatory compliance (PCI-DSS and SOC 2), and
  zero data loss during failures."*
- *"Design an AI inference platform serving machine learning models to 100,000 requests per
  minute with low-latency GPU-backed inference, autoscaling based on demand, and support for
  multiple model versions."*

All six example prompts (including video streaming, ride-sharing, and social media) are
available from `GET /api/v1/architectures/examples`.

## Limitations

- **This is a design/simulation tool.** It never creates real AWS resources and produces no
  Infrastructure-as-Code — it reasons about architecture in natural language and structured
  data, nothing more.
- **Cost figures are order-of-magnitude estimates**, explicitly labeled as such, derived from a
  simple configurable rule table — not the AWS Pricing Calculator and not a quote.
- **The critic and specialist agents are LLM-based** and can occasionally miss issues or be
  miscalibrated on scoring; the deterministic validator exists specifically to catch a fixed
  set of known anti-patterns the LLM might rubber-stamp past, but it isn't exhaustive.
- **Single-cloud, AWS-only** by design, to keep the service knowledge base and reasoning
  tractable and explainable.
- **Results are only stored for jobs** — the job endpoints save every run in MySQL; the
  synchronous endpoint returns its result in the response and stores nothing.
- **Polling, no live progress** — clients poll `GET /jobs/{id}`; there's no per-agent progress
  or push notification yet.
- **Stale jobs** — crash recovery relies on Redis handing an unacknowledged job back. If Redis
  itself loses that message (e.g. it restarts mid-run, since it isn't persisted), the job can
  stay at `running`; there is no automatic sweeper for that case yet.
- **No database migrations** — the jobs table is created automatically on first use;
  changing its schema later would need a migration tool such as Alembic.
- **No frontend yet** — the previous Streamlit UI has been removed. Use `/docs` or any HTTP
  client. The Graphviz/Mermaid diagrams it drew are no longer generated; a frontend can
  rebuild them from `architecture.data_flow`.
- **Free-tier Groq accounts have both a tokens-per-minute and a tokens-per-day limit**, each
  enforced per model. The graph's parallel fan-out (two agents at a time, three times per run)
  is deliberately kept small to reduce how often a burst trips the per-minute ceiling, and
  ArchonAI retries automatically with backoff (`agents/llm.py`) when it does happen, so a run
  may pause briefly
  rather than fail — this is expected behavior on a free-tier key, not a bug.

## Future Enhancements

- Add Amazon Bedrock as a second LLM provider (the `agents/llm.py` layer is already factored
  to make this a single new branch, not a rewrite).
- Add a LangGraph checkpointer for persistence and resumable runs.
- Build a web frontend on top of the REST API.
- Add a streaming endpoint for live per-agent progress (`stream_workflow_updates()` in
  `graph/workflow.py` already yields node-by-node updates).
- Cache completed design results so repeated requests don't re-run the LLM workflow.
- Deploy the docker-compose stack to a free cloud VM (e.g. Oracle Cloud Always Free).
- Export the final report as PDF/Markdown.
- Add multi-cloud service knowledge bases (Azure, GCP) behind the same tool interface.
- Let a human reviewer inject their own required changes into the revision loop alongside the
  critic's.

## License

MIT — see [LICENSE](LICENSE).
