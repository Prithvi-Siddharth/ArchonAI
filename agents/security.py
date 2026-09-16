"""Security Agent.

Specialist analysis node. Evaluates the security posture of the proposed
architecture: IAM, authn/authz, encryption, secrets management, WAF,
security groups, private networking, and audit logging.
"""

from __future__ import annotations

from agents import llm as llm_module
from agents.formatting import compact_architecture
from graph.state import ArchonState, make_trace_entry
from models.schemas import AnalysisResult, Architecture, Requirements

PROMPT_TEMPLATE = """You are a cloud security specialist reviewing a proposed AWS architecture.

Requirements:
{requirements}

Proposed Architecture:
{architecture}

Analyze the security posture of this architecture. Specifically address:
- IAM roles and least-privilege access
- Authentication and authorization for end users and services
- Encryption in transit and at rest
- Secrets management
- WAF and security group coverage for internet-facing components
- Private networking / isolation of sensitive components
- Audit logging for compliance and incident response

Return concrete recommendations, your reasoning, and any risks. Be concise: keep reasoning to 2-3 sentences, and limit recommendations/risks to short bullet phrases, not paragraphs.
"""


def run(state: ArchonState) -> dict:
    """Analyze security for the current state['architecture'].

    Note this agent focuses only on the compute/database/networking outputs
    plus the architecture itself, since security cuts across all layers.
    """
    requirements: Requirements = state["requirements"]
    architecture: Architecture = state["architecture"]

    llm = llm_module.get_llm(temperature=0.15)
    prompt = PROMPT_TEMPLATE.format(
        requirements=requirements.model_dump_json(),
        architecture=compact_architecture(architecture),
    )
    analysis = llm_module.invoke_structured(llm, AnalysisResult, prompt)
    analysis.domain = "Security"

    entry = make_trace_entry(
        node="Security Agent",
        action="Analyzed IAM, encryption, secrets management, WAF, and audit logging coverage.",
        output_summary="; ".join(analysis.recommendations[:2]),
    )
    return {"security_analysis": analysis, "execution_trace": [entry]}
