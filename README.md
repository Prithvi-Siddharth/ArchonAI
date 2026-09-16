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

## Streamlit UI

[app.py](app.py) is presentation-only; all design/analysis/critique logic lives in `agents/`
and `graph/`. It streams the graph's execution via `graph.stream(..., stream_mode="updates")`
so the UI shows each agent completing in real time (inside a `st.status(...)` live log),
including explicit "⚠ requires revision" / "↻ Revising" / re-review messages when the
critic/revision loop actually fires. Once finished, it renders the architecture overview, AWS
service table, a native Graphviz architecture diagram (with the underlying Mermaid source also
shown, since Streamlit has no first-party Mermaid renderer), data flow, scalability, security,
reliability, cost, trade-offs, bottlenecks, final recommendations, and a fully expandable
LangGraph execution trace.

## Project Structure

```
archonai/
├── app.py                       # Streamlit UI (presentation only)
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
├── data/aws_services.json        # AWS service knowledge base
└── tests/                        # pytest suite, LLM calls mocked
```

## Setup

### Prerequisites

- Python 3.11+
- A [Groq API key](https://console.groq.com/keys) (free tier available)

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

### Install & Run Locally

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then edit .env with your real GROQ_API_KEY
streamlit run app.py
```

Open the URL Streamlit prints (typically http://localhost:8501).

### Run the Tests

```bash
pytest -v
```

The entire test suite mocks the LLM layer (`agents.llm.get_llm` / `invoke_structured`), so it
runs with no API key and no network access, including full end-to-end graph runs that exercise
the critic/revision loop and the max-revision cutoff.

### Docker

```bash
docker build -t archonai .
docker run -p 8501:8501 --env-file .env archonai
```

The container runs `streamlit run app.py --server.address=0.0.0.0 --server.port=8501` and
exposes port 8501.

## Example Prompts

- *"Design an e-commerce platform that supports 500,000 concurrent users, requires high
  availability, low latency, secure payment processing, and must scale during traffic spikes."*
- *"Design a banking transaction system that processes 10,000 transactions per second, requires
  strong consistency, end-to-end encryption, regulatory compliance (PCI-DSS and SOC 2), and
  zero data loss during failures."*
- *"Design an AI inference platform serving machine learning models to 100,000 requests per
  minute with low-latency GPU-backed inference, autoscaling based on demand, and support for
  multiple model versions."*

Four more (video streaming, ride-sharing, social media) are built into the UI as one-click
example buttons.

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
- **No persistence** — each run is stateless; closing the browser loses the result unless
  you've copied it out (there's no checkpointer configured).
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
- Export the final report as PDF/Markdown.
- Add multi-cloud service knowledge bases (Azure, GCP) behind the same tool interface.
- Let a human reviewer inject their own required changes into the revision loop alongside the
  critic's.

## License

MIT — see [LICENSE](LICENSE).
