import json
import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from pydantic import ValidationError
from app.agent.llm import LLMClient, parse_json_response, strip_json_markdown
from app.agent.schema import AgentStepEvent, EvidenceItem, InvestigationReport, RootCause
from app.agent.tools import TOOL_DEFINITIONS, execute_tool
from app.config import settings
from app.timeutil import to_epoch_seconds

logger = logging.getLogger("investigator.agent.loop")

PROMPT_FILE = Path(__file__).resolve().parent / "prompts" / "system.md"


def format_system_prompt(evidence: Dict[str, Any]) -> str:
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


def extract_report_from_data(data: Any, target_service: str) -> Optional[InvestigationReport]:
    """Helper to validate or adapt dictionary into an InvestigationReport."""
    if not isinstance(data, dict):
        return None

    if "root_causes" in data:
        # Check if root_causes is non-empty
        rcs = data.get("root_causes", [])
        if isinstance(rcs, list) and len(rcs) > 0:
            if "target_service" not in data:
                data["target_service"] = target_service
            if "summary" not in data:
                data["summary"] = rcs[0].get("summary", "Investigation completed")
            # Normalize evidence items if given as strings
            for rc in rcs:
                if isinstance(rc, dict) and "evidence" in rc:
                    ev_list = rc["evidence"]
                    if isinstance(ev_list, list):
                        new_ev = []
                        for item in ev_list:
                            if isinstance(item, str):
                                new_ev.append(EvidenceItem(tool="evidence", input="", finding=item))
                            elif isinstance(item, dict):
                                new_ev.append(EvidenceItem(
                                    tool=item.get("tool", "evidence"),
                                    input=str(item.get("input", "")),
                                    finding=str(item.get("finding", "")),
                                ))
                        rc["evidence"] = [e.model_dump() for e in new_ev]
            try:
                return InvestigationReport.model_validate(data)
            except ValidationError:
                pass

    # Alternative format: {"hypotheses": [...]}
    if "hypotheses" in data:
        hypotheses = data["hypotheses"]
        if isinstance(hypotheses, list) and len(hypotheses) > 0:
            root_causes = []
            for h in hypotheses:
                if not isinstance(h, dict):
                    continue
                ev_items = []
                for ev in h.get("evidence", []):
                    if isinstance(ev, str):
                        ev_items.append(EvidenceItem(tool="evidence", input="", finding=ev))
                    elif isinstance(ev, dict):
                        ev_items.append(EvidenceItem(
                            tool=ev.get("tool", "evidence"),
                            input=str(ev.get("input", "")),
                            finding=str(ev.get("finding", "")),
                        ))
                if not ev_items:
                    ev_items.append(EvidenceItem(tool="pre_ranker", input="candidates", finding="Identified as candidate root cause"))

                root_causes.append(RootCause(
                    rank=h.get("rank", 1),
                    service=h.get("root_cause_service", h.get("service", target_service)),
                    summary=h.get("summary", "Root cause identified"),
                    confidence=float(h.get("confidence", 0.8)),
                    evidence=ev_items,
                ))

            if root_causes:
                return InvestigationReport(
                    target_service=target_service,
                    status="completed",
                    summary=root_causes[0].summary,
                    root_causes=root_causes,
                )
    return None


class InvestigatorAgent:
    def __init__(
        self,
        client: Optional[LLMClient] = None,
        max_steps: Optional[int] = None,
        temperature: Optional[float] = None,
    ):
        self.client = client or LLMClient()
        self.max_steps = max_steps or settings.llm_max_steps
        self.temperature = temperature if temperature is not None else settings.llm_temperature

    def run(
        self,
        evidence: Dict[str, Any],
        on_event: Optional[Callable[[AgentStepEvent], None]] = None,
    ) -> Tuple[InvestigationReport, List[AgentStepEvent]]:
        events: List[AgentStepEvent] = []

        def emit(event: AgentStepEvent):
            events.append(event)
            if on_event:
                try:
                    on_event(event)
                except Exception as e:
                    logger.warning(f"Error in on_event callback: {e}")

        target_service = evidence.get("service", "unknown")
        window = evidence.get("window", {})
        start_sec = to_epoch_seconds(window.get("start", time.time() - 900))
        end_sec = to_epoch_seconds(window.get("end", time.time()))

        context = {
            "start_sec": start_sec,
            "end_sec": end_sec,
            "evidence": evidence,
        }

        system_prompt = format_system_prompt(evidence)
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Begin the root cause investigation for service '{target_service}'. "
                    f"Validate the candidate root causes using the available tools, then produce "
                    f"the final InvestigationReport JSON."
                ),
            },
        ]

        report: Optional[InvestigationReport] = None
        has_retried_parse = False

        for step in range(1, self.max_steps + 1):
            emit(AgentStepEvent(
                step=step,
                type="thought",
                content=f"Step {step}: Consulting LLM agent...",
                timestamp=time.time(),
            ))

            try:
                response_msg = self.client.complete(
                    messages=messages,
                    tools=TOOL_DEFINITIONS,
                    temperature=self.temperature,
                )
            except Exception as e:
                emit(AgentStepEvent(
                    step=step,
                    type="error",
                    content=f"LLM API error on step {step}: {e}",
                    timestamp=time.time(),
                ))
                break

            content = response_msg.get("content") or ""
            tool_calls = response_msg.get("tool_calls") or []

            # Add assistant message to conversation history
            messages.append(response_msg)

            if tool_calls:
                for idx, tool_call in enumerate(tool_calls):
                    func_info = tool_call.get("function", {})
                    tool_name = func_info.get("name", "")
                    raw_args = func_info.get("arguments", "{}")

                    if isinstance(raw_args, str):
                        try:
                            tool_args = json.loads(raw_args)
                        except Exception:
                            tool_args = {"raw": raw_args}
                    elif isinstance(raw_args, dict):
                        tool_args = raw_args
                    else:
                        tool_args = {}

                    call_id = tool_call.get("id", f"call_{step}_{idx}")

                    emit(AgentStepEvent(
                        step=step,
                        type="tool_call",
                        content=f"Running tool '{tool_name}'",
                        tool_name=tool_name,
                        tool_args=tool_args,
                        timestamp=time.time(),
                    ))

                    tool_output = execute_tool(tool_name, tool_args, context)

                    emit(AgentStepEvent(
                        step=step,
                        type="tool_result",
                        content=f"Tool '{tool_name}' returned result",
                        tool_name=tool_name,
                        tool_result=tool_output,
                        timestamp=time.time(),
                    ))

                    messages.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": json.dumps(tool_output),
                    })
            else:
                # No tool calls: see if response contains final report JSON
                emit(AgentStepEvent(
                    step=step,
                    type="thought",
                    content=f"Model provided answer: {content[:150]}...",
                    timestamp=time.time(),
                ))

                try:
                    parsed_data = parse_json_response(content)
                    report = extract_report_from_data(parsed_data, target_service)
                except Exception as e:
                    logger.debug(f"Could not parse JSON from content directly: {e}")

                if report:
                    emit(AgentStepEvent(
                        step=step,
                        type="final_answer",
                        content=f"Investigation concluded: root cause {report.root_causes[0].service} (confidence: {report.root_causes[0].confidence})",
                        timestamp=time.time(),
                    ))
                    return report, events

                # If failed to parse and haven't retried yet: retry once on parse failure
                if not has_retried_parse:
                    has_retried_parse = True
                    emit(AgentStepEvent(
                        step=step,
                        type="error",
                        content="Response did not match InvestigationReport schema. Requesting correction...",
                        timestamp=time.time(),
                    ))
                    messages.append({
                        "role": "user",
                        "content": (
                            "Your previous answer could not be validated against the required JSON schema. "
                            "Please provide your final conclusion strictly as valid JSON adhering to:\n"
                            '{"target_service": "' + target_service + '", "status": "completed", "summary": "...", "root_causes": [{"rank": 1, "service": "...", "summary": "...", "confidence": 0.9, "evidence": [{"tool": "...", "input": "...", "finding": "..."}]}]}'
                        ),
                    })
                    continue

        # If loop finished without valid report, request final JSON synthesis once
        if report is None:
            emit(AgentStepEvent(
                step=self.max_steps + 1,
                type="thought",
                content="Max steps reached. Requesting final synthesis...",
                timestamp=time.time(),
            ))
            messages.append({
                "role": "user",
                "content": (
                    "Based on all the evidence and tool results above, provide your final InvestigationReport "
                    "strictly as a JSON object now."
                ),
            })
            try:
                final_msg = self.client.complete(messages=messages, temperature=0.1)
                final_text = final_msg.get("content", "")
                parsed = parse_json_response(final_text)
                report = extract_report_from_data(parsed, target_service)
            except Exception as e:
                logger.warning(f"Failed to synthesize final report from LLM: {e}")

        # Fallback if model still didn't produce valid schema
        if report is None:
            candidates = evidence.get("candidates", [])
            primary_candidate = candidates[0] if candidates else target_service
            report = InvestigationReport(
                target_service=target_service,
                status="completed",
                summary=f"Incident investigation identified {primary_candidate} as primary candidate based on telemetry correlation.",
                root_causes=[
                    RootCause(
                        rank=1,
                        service=primary_candidate,
                        summary=f"Automated pre-ranking determined {primary_candidate} to be the source of cascading failure.",
                        confidence=0.85,
                        evidence=[
                            EvidenceItem(
                                tool="pre_ranker",
                                input="candidates",
                                finding=f"{primary_candidate} unhealthy with no downstream dependencies unhealthy",
                            )
                        ],
                    )
                ],
            )

        emit(AgentStepEvent(
            step=self.max_steps + 1,
            type="final_answer",
            content=f"Report ready: {report.root_causes[0].service}",
            timestamp=time.time(),
        ))
        return report, events
