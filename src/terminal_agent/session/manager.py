"""Session manager for state persistence, recovery, and retrieval."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
import uuid

from terminal_agent.session.models import (
    CheckpointSnapshot,
    FailureCategory,
    FailureRecord,
    PlanItem,
    SessionMetrics,
    SessionState,
    StepAction,
    TaskContract,
    VerificationResult,
    VerificationStatus,
)


def get_sessions_dir(working_dir: Optional[Path] = None) -> Path:
    """Return path to .terminal_agent/sessions directory in working_dir."""
    base = working_dir or Path.cwd()
    s_dir = base / ".terminal_agent" / "sessions"
    s_dir.mkdir(parents=True, exist_ok=True)
    return s_dir


class SessionManager:
    """Manages creation, serialization, and restoration of agent sessions."""

    def __init__(self, working_dir: Optional[Path] = None):
        self.working_dir = working_dir or Path.cwd()
        self.sessions_dir = get_sessions_dir(self.working_dir)

    def create_session(
        self,
        task_description: str,
        contract: Optional[TaskContract] = None,
        session_id: Optional[str] = None
    ) -> SessionState:
        """Create and initialize a new SessionState."""
        now = datetime.now(timezone.utc)
        s_id = session_id or f"session_{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        state = SessionState(
            session_id=s_id,
            working_dir=str(self.working_dir.resolve()),
            task_description=task_description,
            contract=contract,
            current_status=VerificationStatus.PENDING,
            metrics=SessionMetrics(start_time=now.isoformat())
        )
        self.save_session(state)
        return state

    def save_session(self, state: SessionState) -> Path:
        """Persist SessionState to JSON file."""
        state.updated_at = datetime.now(timezone.utc).isoformat()
        filepath = self.sessions_dir / f"{state.session_id}.json"
        try:
            start_dt = datetime.fromisoformat(state.metrics.start_time)
            curr_dt = datetime.fromisoformat(state.updated_at)
            state.metrics.execution_time_seconds = round((curr_dt - start_dt).total_seconds(), 2)
        except Exception:
            pass
        data = state.model_dump(mode="json")
        filepath.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return filepath

    def load_session(self, session_id: str) -> Optional[SessionState]:
        """Load SessionState by session_id."""
        filepath = self.sessions_dir / f"{session_id}.json"
        if not filepath.exists():
            candidates = list(self.sessions_dir.glob(f"*{session_id}*.json"))
            if candidates:
                filepath = candidates[0]
            else:
                return None
        try:
            content = filepath.read_text(encoding="utf-8")
            data = json.loads(content)
            return SessionState.model_validate(data)
        except Exception:
            return None

    def list_sessions(self) -> List[SessionState]:
        """List all saved sessions sorted by most recent first."""
        sessions = []
        if not self.sessions_dir.exists():
            return sessions
        for json_file in sorted(self.sessions_dir.glob("*.json"), key=os.path.getmtime, reverse=True):
            try:
                content = json_file.read_text(encoding="utf-8")
                data = json.loads(content)
                sessions.append(SessionState.model_validate(data))
            except Exception:
                continue
        return sessions

    def get_latest_session(self) -> Optional[SessionState]:
        """Retrieve the most recent session if available."""
        sessions = self.list_sessions()
        return sessions[0] if sessions else None

    def delete_sessions_older_than(self, days: Optional[int] = None) -> List[Path]:
        """Delete session JSON files older than ``days``.

        If ``days`` is None, delete every session file. Returns the list of
        deleted file paths. The sessions directory itself is kept.
        """
        deleted: List[Path] = []
        if not self.sessions_dir.exists():
            return deleted
        cutoff = None
        if days is not None:
            cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
        for json_file in list(self.sessions_dir.glob("*.json")):
            if cutoff is not None and json_file.stat().st_mtime >= cutoff:
                continue
            try:
                json_file.unlink()
                deleted.append(json_file)
            except OSError:
                continue
        return deleted

    def record_step(
        self,
        state: SessionState,
        action_type: str,
        reason: str,
        tool_name: Optional[str] = None,
        tool_args: Optional[dict] = None,
        output: Optional[str] = None,
        status: str = "success",
        duration_ms: Optional[int] = None
    ) -> StepAction:
        """Record an executed step in the session state."""
        step_number = len(state.completed_steps) + 1
        step = StepAction(
            step_number=step_number,
            action_type=action_type,
            tool_name=tool_name,
            tool_args=tool_args,
            reason=reason,
            output=output,
            status=status,
            duration_ms=duration_ms
        )
        state.completed_steps.append(step)
        if tool_name:
            state.metrics.tool_calls += 1
            if tool_name in ("run_command", "run_tests"):
                state.metrics.commands_run += 1
        self.save_session(state)
        return step

    def record_verification(
        self,
        state: SessionState,
        verification_result: VerificationResult
    ) -> None:
        """Update session state with verification engine results."""
        state.last_verification = verification_result
        state.current_status = verification_result.status
        state.metrics.verification_status = verification_result.status.value
        state.metrics.tests_run += verification_result.tests_run
        state.metrics.tests_passed = verification_result.tests_passed
        state.metrics.tests_failed = verification_result.tests_failed
        state.metrics.files_changed = verification_result.files_changed_count
        self.save_session(state)

    def record_failure(
        self,
        state: SessionState,
        category: FailureCategory,
        raw_output: str,
        root_cause_hypothesis: str,
        recovery_action: str
    ) -> FailureRecord:
        """Record classified failure and proposed recovery."""
        record = FailureRecord(
            step_number=len(state.completed_steps),
            failure_category=category,
            raw_output=raw_output,
            root_cause_hypothesis=root_cause_hypothesis,
            recovery_action=recovery_action
        )
        state.failures.append(record)
        state.metrics.retries_attempted += 1
        self.save_session(state)
        return record
