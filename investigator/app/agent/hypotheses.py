import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from app.agent.llm import LLMClient, parse_json_response

PROMPT_FILE = Path(__file__).resolve().parent / "prompts" / "hypotheses.md"


def format_investigation_prompt(evidence: Dict[str, Any]) -> str:
    with open(PROMPT_FILE, "r", encoding="utf-8") as f:
        template = f.read()

    service = evidence.get("service", "unknown")
    window = evidence.get("window", {})
    start = window.get("start", "")
    end = window.get("end", "")
    minutes = window.get("minutes", "")

    candidates = evidence.get("candidates", [])
    candidates_str = json.dumps(candidates, indent=2) if candidates else "None identified"

    graph = evidence.get("graph", {})
    nodes = [f"{n.get('id')} ({n.get('health')})" for n in graph.get("nodes", [])]
    edges = [f"{e.get('from')} -> {e.get('to')}" for e in graph.get("edges", [])]
    nodes_str = ", ".join(nodes) if nodes else "None"
    edges_str = ", ".join(edges) if edges else "None"

    timeline = evidence.get("timeline", [])
    timeline_lines = [
        f"[{e.get('timestamp')}] ({e.get('type')}) {e.get('service')}: {e.get('description')}"
        for e in timeline
    ]
    timeline_str = "\n".join(timeline_lines) if timeline_lines else "No timeline events recorded"

    metrics = evidence.get("metrics", {})
    metrics_str = json.dumps(metrics, indent=2)

    logs = evidence.get("logs", {})
    logs_str = json.dumps(logs.get("patterns", []), indent=2)

    return template.format(
        service=service,
        start=start,
        end=end,
        minutes=minutes,
        candidates=candidates_str,
        graph_nodes=nodes_str,
        graph_edges=edges_str,
        timeline=timeline_str,
        metrics=metrics_str,
        logs=logs_str,
    )


def generate_hypotheses(
    evidence: Dict[str, Any],
    client: Optional[LLMClient] = None,
) -> Dict[str, Any]:
    """Sub-step 10(a): one LLM call, context in, JSON hypotheses out, no tools."""
    if client is None:
        client = LLMClient()

    prompt_content = format_investigation_prompt(evidence)
    messages = [
        {"role": "user", "content": prompt_content}
    ]

    message = client.complete(
        messages=messages,
        temperature=0.1,
    )
    raw_content = message.get("content", "")
    return parse_json_response(raw_content)
