from typing import Any, Dict, List, Optional, Tuple
import networkx as nx
from app.config import load_services_config


class ServiceGraph:
    def __init__(self, services_cfg: Optional[Dict[str, Any]] = None):
        self.services_cfg = services_cfg if services_cfg is not None else load_services_config()
        self.g = nx.DiGraph()
        self._build_graph()

    def _build_graph(self) -> None:
        for svc, info in self.services_cfg.items():
            container = info.get("container", svc) if isinstance(info, dict) else svc
            self.g.add_node(
                svc,
                container=container,
                health="healthy",
                health_details={},
            )

        for svc, info in self.services_cfg.items():
            if isinstance(info, dict):
                deps = info.get("depends_on", [])
                for dep in deps:
                    # Edge from service to its dependency (svc -> dep)
                    # Downstream of svc = dependencies it calls
                    # Upstream of dep = services that call it
                    self.g.add_edge(svc, dep)

    def get_downstream(self, service: str) -> List[str]:
        """Returns direct dependencies called by service."""
        if service not in self.g:
            return []
        return list(self.g.successors(service))

    def get_upstream(self, service: str) -> List[str]:
        """Returns direct callers that depend on service."""
        if service not in self.g:
            return []
        return list(self.g.predecessors(service))

    def mark_health(self, service: str, is_healthy: bool, details: Optional[Dict[str, Any]] = None) -> None:
        if service not in self.g:
            return
        self.g.nodes[service]["health"] = "healthy" if is_healthy else "unhealthy"
        self.g.nodes[service]["health_details"] = details or {}

    def is_healthy(self, service: str) -> bool:
        if service not in self.g:
            return True
        return self.g.nodes[service].get("health") == "healthy"

    def to_dict(self) -> Dict[str, Any]:
        nodes = []
        for node, data in self.g.nodes(data=True):
            nodes.append({
                "id": node,
                "container": data.get("container", node),
                "health": data.get("health", "healthy"),
                "details": data.get("health_details", {}),
            })

        edges = []
        for u, v in self.g.edges():
            edges.append({"from": u, "to": v})

        return {
            "nodes": nodes,
            "edges": edges,
        }


def evaluate_service_health(
    metrics: Dict[str, Any],
    container_status: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, List[str]]:
    """
    Health from Stage 7 metrics:
    - unhealthy if error_ratio > 0.05
    - or p95 > 3x baseline and > 0.3 s
    - plus services whose container is down / OOMKilled
    """
    reasons: List[str] = []

    # Container state
    if container_status:
        if not container_status.get("running", True) or container_status.get("status") in ("exited", "dead", "stopped"):
            reasons.append(f"Container down (status: {container_status.get('status')})")
        if container_status.get("oom_killed"):
            reasons.append("Container was OOMKilled")

    # Metrics health
    if metrics:
        err_ratio = metrics.get("error_ratio")
        if isinstance(err_ratio, dict):
            max_err = err_ratio.get("max", 0.0)
            last_err = err_ratio.get("last", 0.0)
            if max_err > 0.05 or last_err > 0.05:
                reasons.append(f"error_ratio ({max(max_err, last_err):.4f}) > 0.05")

        lat_p95 = metrics.get("latency_p95_seconds")
        if isinstance(lat_p95, dict):
            max_p95 = lat_p95.get("max", 0.0)
            baseline = lat_p95.get("baseline", 0.0)
            if max_p95 > 0.3:
                if baseline > 0 and max_p95 > (3.0 * baseline):
                    reasons.append(
                        f"latency_p95 ({max_p95:.4f}s) > 3x baseline ({baseline:.4f}s) and > 0.3s"
                    )
                elif baseline == 0.0:
                    reasons.append(f"latency_p95 ({max_p95:.4f}s) > 0.3s")

    is_healthy = len(reasons) == 0
    return is_healthy, reasons


def find_candidates(
    graph: ServiceGraph,
    container_statuses: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Pre-rank: candidates are unhealthy services none of whose dependencies
    are unhealthy (plus services whose container is down).
    """
    candidates: List[Dict[str, Any]] = []

    for svc in graph.g.nodes():
        is_down = False
        if container_statuses and svc in container_statuses:
            cs = container_statuses[svc]
            if not cs.get("running", True) or cs.get("status") in ("exited", "dead", "stopped") or cs.get("oom_killed"):
                is_down = True

        is_unhealthy = not graph.is_healthy(svc) or is_down
        if not is_unhealthy:
            continue

        if is_down:
            candidates.append({
                "service": svc,
                "reason": f"Container down ({container_statuses[svc].get('status', 'down')})",
                "is_down": True,
            })
            continue

        # Check dependencies
        deps = graph.get_downstream(svc)
        unhealthy_deps = [dep for dep in deps if not graph.is_healthy(dep)]
        if not unhealthy_deps:
            reasons = graph.g.nodes[svc].get("health_details", {}).get("reasons", [])
            reason_str = ", ".join(reasons) if reasons else "unhealthy"
            candidates.append({
                "service": svc,
                "reason": f"{reason_str} (no unhealthy dependencies)",
                "is_down": False,
            })

    return candidates
