"""LangGraph wiring."""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from orchestrator.nodes import (
    build_queries,
    collect,
    cv_score,
    docs_apply,
    drive_export,
    email,
    ingest,
    jd_analyze,
    merge_jd,
    mvp_projects,
    recalc,
    wait_approval,
    yt_branch,
)
from orchestrator.state import GraphState, NodeDeps


def build_graph(deps: NodeDeps):
    """Return a compiled LangGraph graph for the workflow."""

    graph = StateGraph(GraphState)
    graph.add_node("ingest", ingest.build_node(deps))
    graph.add_node("drive_export", drive_export.build_node(deps))
    graph.add_node("merge_jd", merge_jd.build_node(deps))
    graph.add_node("jd_analyze", jd_analyze.build_node(deps))
    graph.add_node("cv_score", cv_score.build_node(deps))
    graph.add_node("build_queries", build_queries.build_node(deps))
    graph.add_node("yt_branch", yt_branch.build_node(deps))
    graph.add_node("mvp_projects", mvp_projects.build_node(deps))
    graph.add_node("collect", collect.build_node(deps))
    graph.add_node("email", email.build_node(deps))
    graph.add_node("wait_approval", wait_approval.build_node(deps))
    graph.add_node("docs_apply", docs_apply.build_node(deps))
    graph.add_node("recalc", recalc.build_node(deps))

    graph.set_entry_point("ingest")

    graph.add_edge("ingest", "drive_export")
    graph.add_edge("drive_export", "merge_jd")
    graph.add_edge("merge_jd", "jd_analyze")
    graph.add_edge("jd_analyze", "cv_score")
    graph.add_edge("cv_score", "build_queries")
    graph.add_edge("build_queries", "yt_branch")
    graph.add_edge("yt_branch", "mvp_projects")
    graph.add_edge("mvp_projects", "collect")
    graph.add_edge("collect", "email")
    graph.add_edge("email", "wait_approval")
    graph.add_edge("wait_approval", "docs_apply")
    graph.add_edge("docs_apply", "recalc")
    graph.add_edge("recalc", END)

    return graph.compile()
