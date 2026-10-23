from typing import Any, Dict, Optional
import docker


def get_container_status(container_name: str, client: Optional[Any] = None) -> Dict[str, Any]:
    try:
        if client is None:
            client = docker.from_env()
        container = client.containers.get(container_name)
        state = container.attrs.get("State", {})
        restart_count = container.attrs.get("RestartCount", 0)
        
        status = state.get("Status", "unknown")
        oom_killed = state.get("OOMKilled", False)
        exit_code = state.get("ExitCode", 0)
        started_at = state.get("StartedAt")
        finished_at = state.get("FinishedAt")
        running = state.get("Running", status == "running")

        return {
            "status": status,
            "running": running,
            "restart_count": restart_count,
            "oom_killed": oom_killed,
            "exit_code": exit_code,
            "started_at": started_at,
            "finished_at": finished_at,
        }
    except Exception as e:
        return {
            "status": "unknown",
            "running": True,
            "restart_count": 0,
            "oom_killed": False,
            "exit_code": 0,
            "started_at": None,
            "finished_at": None,
            "error": str(e),
        }
