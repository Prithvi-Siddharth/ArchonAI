"""ArchonAI -- Multi-Agent Cloud Architecture Designer.

Streamlit front-end for the LangGraph workflow in graph/workflow.py. This
file only handles presentation: it streams node-by-node progress from the
graph, merges it into a running state, and renders the final architecture
report. All the actual design/analysis/critique logic lives in agents/.
"""

from __future__ import annotations

import os

import streamlit as st
from dotenv import load_dotenv

from agents.llm import MissingAPIKeyError
from graph.state import MAX_REVISIONS, create_initial_state
from graph.workflow import NODE_DISPLAY_NAMES, WorkflowError, stream_workflow_updates
from models.schemas import AnalysisResult, Architecture, CostAnalysis, DataFlowStep

# override=True: Streamlit re-executes this module top-to-bottom on every
# rerun (button click, widget change, file-watcher reload), so this is the
# one chance to pick up a .env edit made mid-session without restarting the
# server process. Without override=True, python-dotenv leaves any
# already-set os.environ value untouched, silently ignoring the file change.
load_dotenv(override=True)

st.set_page_config(page_title="ArchonAI", page_icon="☁️", layout="wide")

EXAMPLE_PROMPTS = {
    "E-commerce platform": (
        "Design an e-commerce platform that supports 500,000 concurrent users, requires "
        "high availability, low latency, secure payment processing, and must scale during "
        "traffic spikes."
    ),
    "Video streaming platform": (
        "Design a video streaming platform serving 2 million daily active users, needing "
        "4K adaptive bitrate streaming, low-latency global content delivery, and resilient "
        "storage for large media files."
    ),
    "Real-time ride-sharing platform": (
        "Design a real-time ride-sharing platform that matches drivers and riders within 5 "
        "seconds, tracks live GPS location for 200,000 concurrent trips, and requires high "
        "availability across multiple regions."
    ),
    "Banking transaction system": (
        "Design a banking transaction system that processes 10,000 transactions per second, "
        "requires strong consistency, end-to-end encryption, regulatory compliance (PCI-DSS "
        "and SOC 2), and zero data loss during failures."
    ),
    "Social media platform": (
        "Design a social media platform supporting 5 million monthly active users with a "
        "personalized news feed, real-time notifications, photo and video uploads, and the "
        "ability to handle viral traffic spikes."
    ),
    "AI inference platform": (
        "Design an AI inference platform serving machine learning models to 100,000 requests "
        "per minute with low-latency GPU-backed inference, autoscaling based on demand, and "
        "support for multiple model versions."
    ),
}


def _api_key_configured() -> bool:
    key = os.getenv("GROQ_API_KEY", "").strip()
    return bool(key) and key != "your_groq_api_key_here"


def _mermaid_diagram(architecture: Architecture) -> str:
    """Generate Mermaid flowchart syntax from the architecture's data flow."""
    ids: dict[str, str] = {}

    def node_id(label: str) -> str:
        if label not in ids:
            ids[label] = f"N{len(ids)}"
        return ids[label]

    lines = ["graph TD"]
    steps: list[DataFlowStep] = sorted(architecture.data_flow, key=lambda s: s.step)
    if steps:
        for step in steps:
            src, dst = node_id(step.source), node_id(step.destination)
            lines.append(f'    {src}["{step.source}"] --> {dst}["{step.destination}"]')
    else:
        prev_id = node_id("User")
        lines.append(f'    {prev_id}["User"]')
        for service in architecture.services:
            svc_id = node_id(service.name)
            lines.append(f'    {prev_id} --> {svc_id}["{service.name}"]')
            prev_id = svc_id
    return "\n".join(lines)


def _graphviz_diagram(architecture: Architecture) -> str:
    """DOT-language fallback, rendered natively via st.graphviz_chart (no
    external JS/CDN dependency, so it always renders)."""
    lines = [
        "digraph Architecture {",
        "    rankdir=LR;",
        '    node [shape=box, style="rounded,filled", fillcolor="#EEF2FF", fontname="Helvetica", color="#4F46E5"];',
        '    edge [color="#6366F1"];',
    ]
    steps: list[DataFlowStep] = sorted(architecture.data_flow, key=lambda s: s.step)
    if steps:
        for step in steps:
            lines.append(f'    "{step.source}" -> "{step.destination}";')
    else:
        prev = "User"
        for service in architecture.services:
            lines.append(f'    "{prev}" -> "{service.name}";')
            prev = service.name
    lines.append("}")
    return "\n".join(lines)


def _render_analysis(analysis: AnalysisResult) -> None:
    st.markdown("**Recommendations**")
    for rec in analysis.recommendations:
        st.markdown(f"- {rec}")
    st.markdown("**Reasoning**")
    st.write(analysis.reasoning)
    if analysis.risks:
        st.markdown("**Risks**")
        for risk in analysis.risks:
            st.markdown(f"- {risk}")


def _render_results(state: dict) -> None:
    report = state["final_report"]
    architecture: Architecture = state["architecture"]
    requirements = state["requirements"]
    cost: CostAnalysis = state["cost_analysis"]
    review = state["critic_review"]

    if not review.approved:
        st.warning(
            f"The critic did not fully approve this design after {MAX_REVISIONS} revision "
            "cycles. The report below reflects the best architecture produced, with any "
            "remaining concerns called out in the Final Recommendation section."
        )

    with st.expander("📝 Requirements ArchonAI extracted from your request", expanded=False):
        st.json(requirements.model_dump())

    st.header("📐 Architecture Overview")
    st.write(report.executive_summary)
    st.write(report.architecture_overview)

    st.header("🧩 AWS Services")
    st.write(report.aws_services_summary)
    st.dataframe(
        [
            {"Service": s.name, "Category": s.category, "Purpose": s.purpose, "Why this service": s.justification}
            for s in architecture.services
        ],
        width="stretch",
        hide_index=True,
    )

    st.header("🗺️ Architecture Diagram")
    diagram_col, source_col = st.columns([2, 1])
    with diagram_col:
        st.graphviz_chart(_graphviz_diagram(architecture))
    with source_col:
        st.caption("Mermaid source (paste into mermaid.live or a Markdown renderer):")
        st.code(_mermaid_diagram(architecture), language="mermaid")

    st.header("🔀 Data Flow")
    st.write(report.data_flow_summary)
    for step in sorted(architecture.data_flow, key=lambda s: s.step):
        st.markdown(f"**{step.step}.** {step.source} → {step.destination} — {step.description}")

    st.header("📈 Scalability")
    st.write(report.scalability_strategy)
    st.write(f"**High availability:** {report.high_availability_strategy}")
    col1, col2, col3 = st.columns(3)
    with col1:
        with st.expander("Compute analysis"):
            _render_analysis(state["compute_analysis"])
    with col2:
        with st.expander("Database analysis"):
            _render_analysis(state["database_analysis"])
    with col3:
        with st.expander("Networking analysis"):
            _render_analysis(state["networking_analysis"])

    st.header("🛡️ Security")
    st.write(report.security_summary)
    with st.expander("Security analysis details"):
        _render_analysis(state["security_analysis"])

    st.header("🧯 Reliability")
    st.write(report.reliability_summary)
    with st.expander("Reliability analysis details"):
        _render_analysis(state["reliability_analysis"])
    st.caption(f"Observability: {report.observability_summary}")

    st.header("💰 Cost")
    st.metric("Estimated monthly cost", cost.estimated_monthly_range)
    st.caption(cost.disclaimer)
    st.write(report.cost_summary)
    st.markdown("**Major cost drivers:** " + ", ".join(cost.major_cost_drivers))
    with st.expander("Cost optimizations & breakdown"):
        st.markdown("**Optimizations**")
        for opt in cost.optimizations:
            st.markdown(f"- {opt}")
        if cost.relative_cost_breakdown:
            st.markdown("**Relative cost breakdown**")
            st.json(cost.relative_cost_breakdown)

    st.header("⚖️ Trade-offs")
    for trade_off in report.trade_offs:
        st.markdown(f"- {trade_off}")

    st.header("🚧 Potential Bottlenecks")
    for bottleneck in report.bottlenecks:
        st.markdown(f"- {bottleneck}")

    st.header("✅ Final Recommendation")
    st.write(report.critic_findings_summary)
    for rec in report.final_recommendations:
        st.markdown(f"- {rec}")

    with st.expander("🔍 LangGraph Execution Trace", expanded=False):
        st.caption(
            "Every node the graph executed, in order, including any critic/revision loop "
            "iterations -- this is the actual LangGraph run, not a simulation."
        )
        for i, entry in enumerate(state["execution_trace"], start=1):
            st.markdown(f"**{i}. {entry['node']}**  \n_iteration {entry['iteration']}_")
            st.write(entry["action"])
            st.code(entry["output_summary"], language=None)


def main() -> None:
    st.title("☁️ ArchonAI")
    st.subheader("Multi-Agent Cloud Architecture Designer")
    st.caption(
        "A LangGraph-orchestrated team of agents that analyzes requirements, designs an AWS "
        "architecture, critiques it, and revises it until it holds up."
    )

    if not _api_key_configured():
        st.error(
            "**GROQ_API_KEY is not configured.** Copy `.env.example` to `.env` and set a real "
            "Groq API key from https://console.groq.com/keys before running a design."
        )

    if "user_request_input" not in st.session_state:
        st.session_state.user_request_input = ""

    st.markdown("**Try an example:**")
    example_cols = st.columns(3)
    for i, (label, prompt) in enumerate(EXAMPLE_PROMPTS.items()):
        if example_cols[i % 3].button(label, width="stretch"):
            st.session_state.user_request_input = prompt
            st.rerun()

    user_request = st.text_area(
        "Describe the system you want to build...",
        key="user_request_input",
        height=140,
        placeholder=(
            "e.g. Design an e-commerce platform that supports 500,000 concurrent users, "
            "requires high availability, low latency, secure payment processing, and must "
            "scale during traffic spikes."
        ),
    )

    run_clicked = st.button(
        "Design Architecture",
        type="primary",
        disabled=not _api_key_configured(),
    )

    if run_clicked:
        if not user_request or not user_request.strip():
            st.warning("Please describe the system you want to build before running ArchonAI.")
        else:
            accumulated_state = create_initial_state(user_request.strip())
            critic_pass = 0

            try:
                with st.status("Running ArchonAI multi-agent workflow...", expanded=True) as status:
                    for node_name, partial in stream_workflow_updates(user_request.strip()):
                        for key, value in partial.items():
                            if key == "execution_trace":
                                accumulated_state["execution_trace"] = (
                                    accumulated_state.get("execution_trace", []) + value
                                )
                            else:
                                accumulated_state[key] = value

                        label = NODE_DISPLAY_NAMES.get(node_name, node_name)

                        if node_name == "architecture_critic":
                            critic_pass += 1
                            review = partial["critic_review"]
                            suffix = "" if critic_pass == 1 else f" (re-review #{critic_pass})"
                            status.write(f"✓ {label}{suffix}")
                            if review.approved:
                                status.write(f"✅ Architecture approved (score: {review.score}/100)")
                            else:
                                status.write(f"⚠️ Architecture requires revision (score: {review.score}/100)")
                                for issue in review.issues:
                                    status.write(f"  &nbsp;&nbsp;- **[{issue.severity.value.upper()}]** {issue.issue}")
                        elif node_name == "architecture_revision":
                            status.write(
                                f"↻ Revising architecture (revision {partial['revision_count']}/{MAX_REVISIONS})..."
                            )
                        else:
                            status.write(f"✓ {label}")

                    status.update(label="ArchonAI workflow complete", state="complete", expanded=False)

                st.session_state.result_state = accumulated_state
            except WorkflowError as exc:
                st.error(f"ArchonAI workflow failed: {exc}")
            except MissingAPIKeyError as exc:
                st.error(str(exc))

    if st.session_state.get("result_state"):
        st.divider()
        _render_results(st.session_state.result_state)


if __name__ == "__main__":
    main()
