"""Database Agent.

Specialist analysis node. Evaluates the data layer of the proposed
architecture: SQL vs NoSQL fit, replication, partitioning/sharding,
consistency, backups, and caching.
"""

from __future__ import annotations

from agents import llm as llm_module
from agents.formatting import compact_architecture
from graph.state import ArchonState, make_trace_entry
from models.schemas import AnalysisResult, Architecture, Requirements

PROMPT_TEMPLATE = """You are a database architecture specialist reviewing a proposed AWS architecture.

Requirements:
{requirements}

Proposed Architecture:
{architecture}

Analyze the database/data layer of this architecture. Specifically address:
- SQL vs NoSQL fit for the described access patterns (RDS/Aurora vs DynamoDB)
- Read/write pattern support, including read replicas where relevant
- Partitioning or sharding strategy where appropriate at this scale
- Consistency model trade-offs
- Backup and recovery strategy
- Whether a caching layer is needed in front of the database

Return concrete recommendations, your reasoning, and any risks. Be concise: keep reasoning to 2-3 sentences, and limit recommendations/risks to short bullet phrases, not paragraphs.
"""


def run(state: ArchonState) -> dict:
    """Analyze the data layer for the current state['architecture']."""
    requirements: Requirements = state["requirements"]
    architecture: Architecture = state["architecture"]

    llm = llm_module.get_llm(temperature=0.2)
    prompt = PROMPT_TEMPLATE.format(
        requirements=requirements.model_dump_json(),
        architecture=compact_architecture(architecture),
    )
    analysis = llm_module.invoke_structured(llm, AnalysisResult, prompt)
    analysis.domain = "Database"

    entry = make_trace_entry(
        node="Database Agent",
        action="Analyzed data layer: consistency, replication, partitioning, and backups.",
        output_summary="; ".join(analysis.recommendations[:2]),
    )
    return {"database_analysis": analysis, "execution_trace": [entry]}
