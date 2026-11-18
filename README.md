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
deliberately thin: it validates the request, stores a job, and hands it to the background
worker -- **the API never runs the workflow itself**. The worker calls the existing
`run_workflow()` from [graph/workflow.py](graph/workflow.py) unchanged. All
design/analysis/critique logic stays in `agents/` and `graph/`.

Interactive docs are available at **http://localhost:8000/docs** once the server is running.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness check. Does not call the LLM. |
| `GET` | `/api/v1/architectures/examples` | Example prompts (stored in [data/example_prompts.json](data/example_prompts.json)). |
| `POST` | `/api/v1/auth/register` | Creates an account (`{"email", "password"}`, 8-128 characters) and signs in. |
| `POST` | `/api/v1/auth/login` | Signs in; sets the session cookie. |
| `POST` | `/api/v1/auth/logout` | Signs out (deletes the cookie). |
| `GET` | `/api/v1/auth/me` | The signed-in account. |
| `POST` | `/api/v1/architectures/jobs` | **Signed in.** Queues a design request as yours and returns a `job_id` immediately (`202`). |
| `GET` | `/api/v1/architectures/jobs/{job_id}` | **Signed in, owner only.** Job status, plus the full result once it has succeeded. |

**Accounts:** sign-in issues a JWT (8 hours by default) in an HttpOnly, SameSite=Strict cookie
named `archonai_session`. It needs `JWT_SECRET` (at least 32 random characters) in `.env`;
without it the auth and job endpoints answer `503`. Each job belongs to the account that
submitted it: anyone else, signed in or not, gets `404` (or `401` when signed out). Jobs created
before accounts existed have no owner and can no longer be opened through the API; they are
kept in the database unchanged.

See [Background Jobs](#background-jobs) below for the full flow and examples.

**Request body:** `{"user_request": "<10-4000 characters>"}`. Surrounding whitespace is
trimmed; blank, too-short, or too-long input is rejected with `422` before anything is stored.

**Result** (the job's `result` field once it has succeeded): `approved`,
`max_revisions_reached`, `revision_count`, `requirements`, `architecture_plan`, `architecture`
(services + data flow), the five specialist analyses, `cost_analysis`, `validation_results`,
`critic_review`, `final_report`, and the `execution_trace`. These reuse the Pydantic models in
[models/schemas.py](models/schemas.py).

**Errors** return `{"detail": "<message>"}` with a generic, client-safe message. Full
exception details are logged server-side only and never returned to the client.

Note that if only the critic, revision, or report LLM call fails, the workflow's existing
fallbacks still complete the run, so the job still `succeeded` -- check `approved` and the
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
# Sign in once; -c/-b keep the session cookie in a file.
curl -c cookies.txt -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "your-password"}' \
  http://localhost:8000/api/v1/auth/login

curl -b cookies.txt -X POST http://localhost:8000/api/v1/architectures/jobs \
  -H "Content-Type: application/json" \
  -d '{"user_request": "Design a blogging platform for 10,000 users"}'
# {"job_id":"3f2a…","status":"queued","status_url":"/api/v1/architectures/jobs/3f2a…"}

curl -b cookies.txt http://localhost:8000/api/v1/architectures/jobs/3f2a…
# {"job_id":"3f2a…","status":"running","attempts":1,…,"result":null}
# … later: "status":"succeeded" with the full "result"
```

| Status | When |
|--------|------|
| `202` | Job accepted |
| `401` | Not signed in, or the session has expired |
| `404` | Unknown `job_id`, or a job that belongs to someone else |
| `422` | Invalid request body |
| `503` | MySQL (job store) or Redis (job queue) unavailable |

A failed job is still a `200` on `GET` -- its `error` field holds the status code and message:

| `error.status_code` | When |
|--------|------|
| `429` | Groq rate limit still exceeded after automatic retries |
| `500` | Unexpected internal error, or the job was interrupted too many times |
| `502` | LLM provider error or invalid structured output |
| `503` | `GROQ_API_KEY` is not configured |
| `504` | LLM provider timed out, or the job exceeded `JOB_TIMEOUT_SECONDS` |

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

## Logging & CloudWatch

### Structured logs and timings

Every job, workflow run, and LangGraph node logs one structured `key=value` line
([graph/observability.py](graph/observability.py)), timed with a monotonic clock:

```
event=job_started job_id=3f2a… attempt=1 redelivered=false
event=node_finished job_id=3f2a… node=compute_agent iteration=0 outcome=success duration_ms=4120
event=workflow_finished job_id=3f2a… outcome=success approved=true revision_count=1 duration_ms=142350
event=job_succeeded job_id=3f2a… attempt=1 duration_ms=142400
```

Every successful LLM call logs its real token usage next to its `max_tokens` cap. Groq's
output-tokens-per-minute limit reserves the cap up front, so this shows how much budget each agent
holds back; `finish_reason=length` means the answer was cut off at the cap:

```
event=llm_call_finished job_id=3f2a… node=security_agent max_tokens=750 input_tokens=812 output_tokens=311 reasoning_tokens=120 finish_reason=tool_calls
```

A failed LLM request logs what the provider said, without its message text:

```
event=llm_request_failed job_id=3f2a… error_type=RateLimitError provider_status=429 provider_error_code=rate_limit_exceeded will_retry=true call_attempt=1 retry_in_ms=5420
event=llm_request_failed job_id=3f2a… error_type=BadRequestError provider_status=400 provider_error_code=tool_use_failed will_retry=false schema=AnalysisResult call_attempt=3
```

Both also carry `call_id`, `model` and (failures) `max_tokens`, `sdk_retries` and
`usage_available=false`, since providers report no usage for a failed request.

Each logical LLM call (one agent's structured call, or one designer research round) ends with
exactly one `llm_call_summary`, whether it succeeded or failed:

```
event=llm_call_summary job_id=3f2a… call_id=8e4ac47b0798 node=security_agent call_type=structured schema=AnalysisResult provider=groq model=qwen/qwen3.8-27b max_tokens=750 outcome=success total_ms=7000 http_requests=5 sdk_retries=2 sdk_retry_wait_ms=4000 app_retries=1 app_retry_wait_ms=3000 tool_use_retries=1 llm_responses=1 input_tokens=800 output_tokens=300 reasoning_tokens=90 finish_reason=tool_calls usage_available=partial
```

| Field | Meaning |
|---|---|
| `http_requests` | Every HTTP request the call made, including failed ones |
| `sdk_retries`, `sdk_retry_wait_ms` | Retries inside the Groq SDK, read from its `x-stainless-retry-count` request header, and the measured time between an attempt ending and its retry starting |
| `app_retries`, `app_retry_wait_ms` | ArchonAI's own rate-limit/network retries and their measured sleep |
| `tool_use_retries` | Corrective retries after an invalid structured answer (no wait) |
| `input_tokens` … `reasoning_tokens` | Sums of the provider's reported usage -- never estimated |
| `usage_available` | `true`: all usage reported; `partial`: a failed attempt (e.g. `tool_use_failed`, timeout) may have generated tokens the provider didn't report; `false`: none reported |

Anything that can't be measured is logged as `unavailable` rather than guessed -- e.g. the
HTTP/SDK fields with `LLM_PROVIDER=gemini`, whose HTTP traffic is not instrumented.

Nodes are wrapped, not modified, so parallel nodes are timed independently, and every line
logged during a job carries its `job_id`. Only metadata is logged -- never request text, LLM
output, API keys, or exception messages (failures log `error_type` and `status_code`; full
tracebacks only appear at DEBUG level).

```bash
docker compose logs -f worker | grep "event="          # or the celery terminal locally
docker compose logs worker | grep "job_id=<your-id>"   # everything for one job
```

### Shipping logs to AWS CloudWatch (optional)

With `CLOUDWATCH_ENABLED=true`, the same lines are **also** sent to CloudWatch Logs
([graph/cloudwatch_logs.py](graph/cloudwatch_logs.py)); console output is unchanged.

| Service | Log group |
|---------|-----------|
| API | `/archonai/api` |
| Worker (incl. all job and node events) | `/archonai/worker` |

- **Batched and non-blocking** -- logs are queued and sent every few seconds from a background
  thread ([watchtower](https://github.com/kislyuk/watchtower)), so a slow or unreachable AWS
  never delays a request or job.
- **One log stream per process per day** (`<date>/<host>/<pid>`), not one per event.
- **Failures are harmless** -- missing credentials or a bad profile disable CloudWatch with an
  `event=cloudwatch_disabled` warning at startup; delivery errors become warnings. The app and
  console logging keep working.
- **Log groups are not created by the app.** Create them beforehand (with a retention policy);
  the app only needs `logs:CreateLogStream` and `logs:PutLogEvents` on them.

**Configuration** (`.env`; see [.env.example](.env.example)):

| Variable | Default | Meaning |
|----------|---------|---------|
| `CLOUDWATCH_ENABLED` | `false` | Turn shipping on |
| `AWS_REGION` | `ap-south-1` | Region of the log groups |
| `AWS_PROFILE` | *(unset)* | **Local development only**, e.g. `archonai-dev`. Leave unset in production so the AWS SDK's default credential chain (environment variables, IAM role) is used |
| `CLOUDWATCH_API_LOG_GROUP` / `CLOUDWATCH_WORKER_LOG_GROUP` | `/archonai/api` / `/archonai/worker` | Log group names |
| `CLOUDWATCH_SEND_INTERVAL_SECONDS` | `5` | How often batches are sent |

Credentials are never stored in the project. Locally they stay in `~/.aws` (docker-compose mounts
it read-only into the `api` and `worker` containers). Tests force CloudWatch off and use a
stubbed AWS client, so they never need credentials or reach AWS.

**Enable it locally:** add to `.env`

```
CLOUDWATCH_ENABLED=true
AWS_PROFILE=archonai-dev
```

then restart (`docker compose up -d --build`, or restart uvicorn/celery). Startup logs
`event=cloudwatch_enabled service=api log_group=/archonai/api …`.

**Check the logs in AWS:**

```bash
aws logs tail /archonai/worker --follow --profile archonai-dev
aws logs tail /archonai/api --since 15m --profile archonai-dev
aws logs filter-log-events --log-group-name /archonai/worker \
  --filter-pattern '"event=node_finished"' --profile archonai-dev
```

or open **CloudWatch → Log groups → /archonai/worker** in the AWS console (region `ap-south-1`).

### Custom metrics, dashboard and alarms (optional)

With `CLOUDWATCH_METRICS_ENABLED=true`, the worker also publishes metrics to the CloudWatch
namespace **`ArchonAI`** ([graph/cloudwatch_metrics.py](graph/cloudwatch_metrics.py)). They come
from the same structured events as the logs above; nothing is instrumented twice.

| Metric | Dimensions | Unit | From event |
|--------|------------|------|------------|
| `WorkflowDuration` | `Outcome` (`success`/`failure`) | Milliseconds | `workflow_finished` (one per attempt) |
| `AgentDuration` | `Agent` (graph node name) | Milliseconds | `node_finished` |
| `JobsCompleted` | `Outcome` (`succeeded`/`failed`) | Count | `job_succeeded`, final `job_failed` |
| `JobRetries` | – | Count | `job_failed` with `will_retry=true`, `job_resumed_after_crash` |
| `WorkflowFailures` | – | Count | `workflow_finished` with `outcome=failure` (one per failed attempt) |

- **Low-cardinality dimensions only.** Job ids stay in the logs; every distinct dimension
  value is a separately billed metric.
- **No double counting.** Job outcomes are de-duplicated per job and attempt, and the runner only
  reports an outcome when its guarded status update succeeded.
- **Batched and non-blocking.** Datapoints are buffered and sent in one `PutMetricData` call
  every `CLOUDWATCH_METRICS_FLUSH_INTERVAL_SECONDS` from a background thread.
- **Failures are harmless.** botocore retries throttling and network errors with backoff, a
  failed batch gets one more try on the next flush, and is then dropped with an
  `event=metrics_publish_failed` warning. The buffer is bounded. Jobs and console logging are
  never affected.

| Variable | Default | Meaning |
|----------|---------|---------|
| `CLOUDWATCH_METRICS_ENABLED` | `false` | Turn metrics on (separate from `CLOUDWATCH_ENABLED`) |
| `CLOUDWATCH_METRICS_NAMESPACE` | `ArchonAI` | Metric namespace (the dashboard, alarms and IAM policy assume `ArchonAI`) |
| `CLOUDWATCH_METRICS_FLUSH_INTERVAL_SECONDS` | `10` | How often batches are sent |

`AWS_REGION` and `AWS_PROFILE` are shared with logging. Tests force metrics off and use stubbed
clients.

**IAM permissions** (policy documents in [monitoring/iam/](monitoring/iam/), attach them in the
IAM console; nothing here changes IAM for you):

| Who | Policy | Actions |
|-----|--------|---------|
| The app (`archonai-dev` locally, the instance/task role in production) | [archonai-metrics-publish-policy.json](monitoring/iam/archonai-metrics-publish-policy.json) | `cloudwatch:PutMetricData`, only for namespace `ArchonAI` |
| Whoever creates and views the dashboard/alarms | [archonai-monitoring-setup-policy.json](monitoring/iam/archonai-monitoring-setup-policy.json) | View: `GetMetricData`, `GetMetricStatistics`, `ListMetrics`, `ListDashboards`, `DescribeAlarms`. Manage: `PutDashboard`/`GetDashboard` on `ArchonAI`, `PutMetricAlarm`/`SetAlarmState`/`DeleteAlarms` on `ArchonAI-*` alarms |

`PutMetricData` doesn't support resource ARNs, so the publish policy is limited by the
`cloudwatch:namespace` condition instead.

**Create or update the dashboard** ([monitoring/archonai-dashboard.json](monitoring/archonai-dashboard.json)).
It shows jobs by outcome, retries and failures, workflow duration and per-agent duration.

```bash
aws cloudwatch put-dashboard --dashboard-name ArchonAI \
  --dashboard-body file://monitoring/archonai-dashboard.json --region ap-south-1
```

Re-run the same command after editing the file. Then open **CloudWatch → Dashboards → ArchonAI**.

**Create or update the alarms** ([monitoring/alarms/](monitoring/alarms/)):

| Alarm | Fires when | Why it stays quiet at low traffic |
|-------|-----------|-----------------------------------|
| `ArchonAI-JobFailures` | ≥ 3 jobs fail permanently (after retries) within 1 hour | Absolute count, not a rate; missing data = OK |
| `ArchonAI-SlowWorkflows` | Successful runs exceed 12 min (80% of the default 900 s timeout) in 2 of the last 3 hours | Needs sustained slowness; missing data = OK |

```bash
aws cloudwatch put-metric-alarm --cli-input-json file://monitoring/alarms/job-failures.json --region ap-south-1
aws cloudwatch put-metric-alarm --cli-input-json file://monitoring/alarms/workflow-duration.json --region ap-south-1
```

To change a threshold, edit `Threshold` (and `Period`/`DatapointsToAlarm`) in the JSON file and
re-run the command. If you raise `JOB_TIMEOUT_SECONDS`, set the duration threshold to about 80% of
it, in milliseconds. To get notified, create an SNS topic with an email subscription and put its
ARN in `AlarmActions`.

**Test an alarm** without waiting for real failures (it returns to normal at the next evaluation):

```bash
aws cloudwatch set-alarm-state --alarm-name ArchonAI-JobFailures \
  --state-value ALARM --state-reason "Manual test" --region ap-south-1
aws cloudwatch describe-alarms --alarm-name-prefix ArchonAI- \
  --query 'MetricAlarms[].[AlarmName,StateValue]' --output table --region ap-south-1
```

Run these with an identity that has the setup policy, by adding `--profile <name>`. The app's
`archonai-dev` user only needs to publish.

**Check that metrics arrive.** Run a job; datapoints appear within a few minutes. Reading metrics
needs [archonai-metrics-read-policy.json](monitoring/iam/archonai-metrics-read-policy.json)
(`ListMetrics`, `GetMetricData`, `GetMetricStatistics`); the publish-only policy can't read.
[monitoring/verify_metrics.py](monitoring/verify_metrics.py) discovers every published metric
and dimension combination and prints its datapoints for a UTC window:

```bash
python monitoring/verify_metrics.py --start 2026-10-28T07:00:00Z --end 2026-10-28T07:15:00Z --profile archonai-dev
```

Each dimension combination is a separate metric in CloudWatch: `AgentDuration` has data only
with an `Agent` dimension, `WorkflowDuration` and `JobsCompleted` only with `Outcome`. Querying
them without those dimensions returns nothing.

**Cost.** CloudWatch's free tier includes 10 custom metrics. This setup creates up to about 19
(13 agents, plus 2 workflow durations, plus 2 job outcomes, plus retries and failures), roughly
$0.30 per extra metric per month, and only while data is being published. The dashboard (3 free)
and the 2 alarms (10 free) are within the free tier.

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
│   ├── llm.py                   # LLM provider layer (Groq or Gemini; Bedrock-ready)
│   ├── requirements.py / planner.py / architecture.py
│   ├── compute.py / database.py / networking.py
│   ├── security.py / reliability.py / cost.py
│   ├── critic.py / revision.py / report.py
├── graph/
│   ├── state.py                 # Typed ArchonState + trace helpers
│   ├── workflow.py              # StateGraph wiring, routing, streaming
│   ├── observability.py         # Structured log events + per-node timing
│   ├── cloudwatch_logs.py       # Optional CloudWatch Logs shipping
│   └── cloudwatch_metrics.py    # Optional CloudWatch custom metrics (from the same events)
├── tools/
│   ├── aws_service_search.py
│   ├── architecture_validator.py
│   └── cost_estimator.py
├── models/schemas.py             # All Pydantic structured-output schemas
├── data/
│   ├── aws_services.json         # AWS service knowledge base
│   └── example_prompts.json      # Example prompts served by the API
├── monitoring/                   # CloudWatch dashboard, alarm and IAM policy definitions
├── tests/                        # pytest suite, LLM calls mocked
├── Dockerfile                    # Image used by both the api and worker services
└── docker-compose.yml            # mysql, redis, api, worker
```

## Setup

### Prerequisites

- Python 3.11+
- A [Groq API key](https://console.groq.com/keys) or a [Gemini API key](https://aistudio.google.com/apikey) (both have free tiers)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) -- for MySQL and Redis
  (needed by the job endpoints), or to run everything in containers

### Environment Variables

Copy the example file and fill in your key:

```bash
cp .env.example .env
```

| Variable | Required | Description |
|----------|----------|--------------|
| `LLM_PROVIDER` | No (defaults to `groq`) | Which LLM provider the agents use: `groq` or `gemini` |
| `GROQ_API_KEY` | When using Groq | Your Groq API key. Get one at https://console.groq.com/keys |
| `GROQ_MODEL` | No (defaults to `qwen/qwen3.8-27b`) | Must reliably honor forced tool-calling, since this app uses `with_structured_output` everywhere and real tool calls in the Architecture Designer. Groq's free-tier quotas are per-model (both a rolling tokens-per-minute limit and a separate tokens-per-day limit), so which model works best for you varies with what you've already used that day. Of the three tested during development, `openai/gpt-oss-120b` is the most reliable at structured output but has the lowest free-tier daily cap; `openai/gpt-oss-20b` occasionally mis-cases a tool name in a way Groq rejects. Groq's lineup changes over time -- list what's available to your key with `python -c "from groq import Groq; import os; [print(m.id) for m in Groq(api_key=os.environ['GROQ_API_KEY']).models.list().data]"` |
| `GEMINI_API_KEY` | When using Gemini | Your Gemini API key. Get one at https://aistudio.google.com/apikey |
| `GEMINI_MODEL` | No (defaults to `gemini-3.8-flash`) | Gemini model name, exactly as shown in AI Studio. The free tier is limited mainly by requests per day rather than tokens per minute, so a run is much faster than on Groq's free tier, but only a limited number of runs fit in a day |
| `GEMINI_THINKING_LEVEL` | No (defaults to `low`) | `minimal`, `low`, `medium`, `high`, or `default`. Thinking tokens count toward each agent's output cap, so deep thinking can cut answers off |

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

`/health` and `/examples` work without MySQL or Redis; the job endpoints need both, plus a
running worker -- without one, jobs simply wait as `queued`.

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
