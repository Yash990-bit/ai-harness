"""Standalone persistent error ledger for Odin.

Follows the core engineering tenet:
"Every error compounds... Nothing gets diagnosed twice."

Records execution errors, verification crashes, and agent failures into a
structured, persistent ledger (.odin/errors.jsonl) with signature grouping
and disposition lifecycle (open, fixed, non-issue).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("odin.error_ledger")


def compute_symptom_signature(source: str, message: str) -> str:
    """Normalize and hash message into a stable symptom signature."""
    # Strip line numbers, memory addresses, timestamps, and UUIDs for grouping
    cleaned = re.sub(r"0x[0-9a-fA-F]+", "0x...", message)
    cleaned = re.sub(r"\b\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}\b", "<TIMESTAMP>", cleaned)
    cleaned = re.sub(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", "<UUID>", cleaned)
    cleaned = re.sub(r"line \d+", "line <N>", cleaned)
    cleaned = " ".join(cleaned.split())[:200]
    
    prefix = f"{source}:{cleaned}"
    digest = hashlib.sha256(prefix.encode("utf-8")).hexdigest()[:12]
    return f"{source}_{digest}"


@dataclass
class ErrorEvent:
    """A recorded error occurrence with triage lifecycle."""
    event_id: str
    source: str  # "execution_failure" | "verification_failure" | "agent_crash" | ...
    source_id: str  # task_id or spec_id
    message: str
    symptom_signature: str
    traceback: str = ""
    disposition: str = "open"  # "open" | "fixed" | "non-issue"
    disposition_note: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ErrorEvent:
        return cls(**data)


class LocalErrorLedger:
    """Manages appending and querying error events in local file storage."""

    def __init__(self, ledger_file: Optional[Path] = None):
        if ledger_file is None:
            odin_dir = Path(os.getcwd()) / ".odin"
            odin_dir.mkdir(parents=True, exist_ok=True)
            self.ledger_file = odin_dir / "errors.jsonl"
        else:
            self.ledger_file = Path(ledger_file)
            self.ledger_file.parent.mkdir(parents=True, exist_ok=True)

    def _load_all(self) -> List[ErrorEvent]:
        if not self.ledger_file.exists():
            return []
        events = []
        try:
            with open(self.ledger_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        events.append(ErrorEvent.from_dict(json.loads(line)))
        except Exception as exc:
            logger.warning("Error reading error ledger: %s", exc)
        return events

    def _save_all(self, events: List[ErrorEvent]) -> None:
        temp_file = self.ledger_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            for ev in events:
                f.write(json.dumps(ev.to_dict()) + "\n")
        temp_file.replace(self.ledger_file)

    def record(
        self,
        source: str,
        source_id: str,
        message: str,
        traceback: str = "",
        symptom_signature: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ErrorEvent:
        """Record an error event. Deduplicates if exact source and source_id match."""
        events = self._load_all()
        signature = symptom_signature or compute_symptom_signature(source, message)
        
        # Check if already present for identical source and source_id
        if source_id:
            for ev in events:
                if ev.source == source and ev.source_id == source_id:
                    ev.message = message
                    ev.traceback = traceback
                    ev.updated_at = datetime.now(timezone.utc).isoformat()
                    if metadata:
                        ev.metadata.update(metadata)
                    self._save_all(events)
                    return ev

        event_id = f"err_{int(time.time())}_{len(events) + 1}"
        new_event = ErrorEvent(
            event_id=event_id,
            source=source,
            source_id=source_id,
            message=message,
            symptom_signature=signature,
            traceback=traceback,
            disposition="open",
            disposition_note="",
            metadata=metadata or {},
        )
        events.append(new_event)
        self._save_all(events)
        return new_event

    def set_disposition(
        self,
        event_id: str,
        disposition: str,
        note: str = "",
    ) -> Optional[ErrorEvent]:
        """Update disposition ('open', 'fixed', 'non-issue') of an error event."""
        valid_dispositions = {"open", "fixed", "non-issue"}
        if disposition not in valid_dispositions:
            raise ValueError(f"Invalid disposition '{disposition}'. Must be one of {valid_dispositions}")

        events = self._load_all()
        target = None
        for ev in events:
            if ev.event_id == event_id or ev.event_id.startswith(event_id):
                ev.disposition = disposition
                if note:
                    ev.disposition_note = note
                ev.updated_at = datetime.now(timezone.utc).isoformat()
                target = ev
                break

        if target:
            self._save_all(events)
        return target

    def list_events(
        self,
        disposition: Optional[str] = None,
        source: Optional[str] = None,
    ) -> List[ErrorEvent]:
        """List recorded events with optional filters."""
        events = self._load_all()
        if disposition:
            events = [e for e in events if e.disposition == disposition]
        if source:
            events = [e for e in events if e.source == source]
        return events

    def summary(self) -> Dict[str, Any]:
        """Generate structured breakdown of open, fixed, and non-issue errors."""
        events = self._load_all()
        total = len(events)
        open_count = sum(1 for e in events if e.disposition == "open")
        fixed_count = sum(1 for e in events if e.disposition == "fixed")
        non_issue_count = sum(1 for e in events if e.disposition == "non-issue")

        signatures: Dict[str, int] = {}
        for e in events:
            signatures[e.symptom_signature] = signatures.get(e.symptom_signature, 0) + 1

        return {
            "total_errors": total,
            "open": open_count,
            "fixed": fixed_count,
            "non_issue": non_issue_count,
            "unique_signatures": len(signatures),
            "signatures": signatures,
        }
