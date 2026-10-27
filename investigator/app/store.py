import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional
from app.agent.schema import AgentStepEvent

logger = logging.getLogger("investigator.store")


class InvestigationStore:
    def __init__(self, storage_dir: Optional[str | Path] = None):
        if storage_dir is None:
            # Check candidate directories
            candidates = [
                Path("data/investigations"),
                Path("../data/investigations"),
                Path(__file__).resolve().parent.parent / "data" / "investigations",
                Path("/data/investigations"),
            ]
            storage_path = None
            for c in candidates:
                if c.parent.exists():
                    storage_path = c
                    break
            self.storage_dir = storage_path or Path("data/investigations")
        else:
            self.storage_dir = Path(storage_dir)

        try:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"Could not create storage dir at {self.storage_dir}: {e}")

        self._records: Dict[str, Dict[str, Any]] = {}
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}
        self._load_persisted()

    def _load_persisted(self) -> None:
        if not self.storage_dir.exists():
            return
        for file in self.storage_dir.glob("*.json"):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    inv_id = data.get("id")
                    if inv_id:
                        self._records[inv_id] = data
            except Exception as e:
                logger.debug(f"Failed to load persisted investigation {file}: {e}")

    def create(self, inv_id: str, service: str, window_minutes: int) -> Dict[str, Any]:
        record: Dict[str, Any] = {
            "id": inv_id,
            "service": service,
            "window_minutes": window_minutes,
            "status": "running",
            "created_at": time.time(),
            "updated_at": time.time(),
            "evidence": None,
            "report": None,
            "events": [],
            "error": None,
        }
        self._records[inv_id] = record
        self._subscribers[inv_id] = []
        self._persist(inv_id)
        return record

    def get(self, inv_id: str) -> Optional[Dict[str, Any]]:
        return self._records.get(inv_id)

    def list_all(self) -> List[Dict[str, Any]]:
        return sorted(
            list(self._records.values()),
            key=lambda x: x.get("created_at", 0),
            reverse=True,
        )

    def add_event(self, inv_id: str, event: AgentStepEvent) -> None:
        record = self._records.get(inv_id)
        if not record:
            return

        event_dict = event.model_dump()
        record["events"].append(event_dict)
        record["updated_at"] = time.time()

        # Notify any active SSE subscribers
        subscribers = self._subscribers.get(inv_id, [])
        for q in list(subscribers):
            try:
                q.put_nowait(event_dict)
            except Exception as e:
                logger.debug(f"Failed to push event to subscriber: {e}")

    def set_evidence(self, inv_id: str, evidence: Dict[str, Any]) -> None:
        record = self._records.get(inv_id)
        if not record:
            return
        record["evidence"] = evidence
        record["updated_at"] = time.time()
        self._persist(inv_id)

    def complete(self, inv_id: str, report: Dict[str, Any]) -> None:
        record = self._records.get(inv_id)
        if not record:
            return
        record["status"] = "completed"
        record["report"] = report
        record["updated_at"] = time.time()
        self._persist(inv_id)

        # Notify subscribers of completion
        subscribers = self._subscribers.get(inv_id, [])
        for q in list(subscribers):
            try:
                q.put_nowait({"type": "done", "report": report})
            except Exception:
                pass

    def fail(self, inv_id: str, error: str) -> None:
        record = self._records.get(inv_id)
        if not record:
            return
        record["status"] = "failed"
        record["error"] = error
        record["updated_at"] = time.time()
        self._persist(inv_id)

        subscribers = self._subscribers.get(inv_id, [])
        for q in list(subscribers):
            try:
                q.put_nowait({"type": "error", "error": error})
            except Exception:
                pass

    def _persist(self, inv_id: str) -> None:
        record = self._records.get(inv_id)
        if not record:
            return
        try:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            path = self.storage_dir / f"{inv_id}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(record, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to persist investigation {inv_id}: {e}")

    async def stream_events(self, inv_id: str) -> AsyncGenerator[Dict[str, Any], None]:
        record = self.get(inv_id)
        if not record:
            yield {"data": json.dumps({"type": "error", "error": "Investigation not found"})}
            return

        # 1. Yield any historical events first
        for ev in record.get("events", []):
            yield {"data": json.dumps(ev)}

        # 2. If already finished, yield final status and finish
        if record.get("status") == "completed":
            yield {"data": json.dumps({"type": "done", "report": record.get("report")})}
            return
        elif record.get("status") == "failed":
            yield {"data": json.dumps({"type": "error", "error": record.get("error")})}
            return

        # 3. Listen for live events
        q: asyncio.Queue = asyncio.Queue()
        if inv_id not in self._subscribers:
            self._subscribers[inv_id] = []
        self._subscribers[inv_id].append(q)

        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield {"data": json.dumps(event)}
                    if event.get("type") in ("done", "error"):
                        break
                except asyncio.TimeoutError:
                    yield {"data": json.dumps({"type": "ping", "timestamp": time.time()})}
                    rec = self.get(inv_id)
                    if rec and rec.get("status") in ("completed", "failed"):
                        yield {"data": json.dumps({"type": "done", "report": rec.get("report")})}
                        break
        finally:
            if inv_id in self._subscribers and q in self._subscribers[inv_id]:
                self._subscribers[inv_id].remove(q)


store = InvestigationStore()
