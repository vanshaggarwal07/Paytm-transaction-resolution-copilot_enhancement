"""LangGraph assembly for the Paytm resolution copilot."""

from langgraph.graph import END, START, StateGraph

from src.core.graph_nodes import (
    node_clarify,
    node_error,
    node_escalate,
    node_generate,
    node_identify_issue,
    node_lookup,
    node_reconcile,
    node_retrieve,
    node_router_flags,
    node_verify,
    route_after_router,
)
from src.core.graph_state import CopilotState


def _route_after_lookup(state: CopilotState) -> str:
    """Route to error handling when lookup failed."""
    if state.get("lookup_error"):
        return "error"
    return "identify"


def _build_copilot_graph():
    """Wire the copilot graph structure with stub nodes."""
    graph = StateGraph(CopilotState)

    graph.add_node("lookup", node_lookup)
    graph.add_node("error", node_error)
    graph.add_node("identify_issue", node_identify_issue)
    graph.add_node("reconcile", node_reconcile)
    graph.add_node("router", node_router_flags)
    graph.add_node("clarify", node_clarify)
    graph.add_node("retrieve", node_retrieve)
    graph.add_node("generate", node_generate)
    graph.add_node("escalate", node_escalate)
    graph.add_node("verify", node_verify)

    graph.add_edge(START, "lookup")
    graph.add_conditional_edges(
        "lookup",
        _route_after_lookup,
        {
            "error": "error",
            "identify": "identify_issue",
        },
    )
    graph.add_edge("error", END)
    graph.add_edge("identify_issue", "reconcile")
    graph.add_edge("reconcile", "router")
    graph.add_conditional_edges(
        "router",
        route_after_router,
        {
            "clarify": "clarify",
            "resolve": "retrieve",
        },
    )
    graph.add_edge("clarify", END)
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", "escalate")
    graph.add_edge("escalate", "verify")
    graph.add_edge("verify", END)

    return graph.compile()


COPILOT_GRAPH = _build_copilot_graph()
