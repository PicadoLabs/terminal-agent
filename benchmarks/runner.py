"""Benchmark harness executing SWE tasks and generating AgentBench-compatible reports."""

import json
import os
import shutil
import stat
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml


def _rmtree_safely(path: Path) -> None:
    """Safely remove a directory tree handling Windows read-only git files."""
    if not path.exists():
        return
    def _handle_remove_readonly(func, p, exc_info):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except Exception:
            pass
    try:
        shutil.rmtree(path, onerror=_handle_remove_readonly)
    except Exception:
        shutil.rmtree(path, ignore_errors=True)

from terminal_agent.agent.loop import AgentLoop
from terminal_agent.checkpoints.manager import CheckpointManager
from terminal_agent.config.schema import TerminalAgentConfig
from terminal_agent.context.engine import RepositoryContextEngine
from terminal_agent.git.adapter import GitAdapter
from terminal_agent.planner.contract import TaskContractGenerator
from terminal_agent.providers.mock_provider import MockProvider
from terminal_agent.sandbox.local import LocalSandbox
from terminal_agent.security.policy import SecurityPolicyEnforcer
from terminal_agent.security.secrets import SecretGuard
from terminal_agent.session.manager import SessionManager
from terminal_agent.session.models import VerificationStatus
from terminal_agent.telemetry.events import TelemetryLogger
from terminal_agent.tools.registry import ToolRegistry
from terminal_agent.verifier.engine import IndependentVerifier


class BenchmarkRunner:
    """Orchestrates multi-task benchmarks and outputs AgentBench-compatible evaluation summaries."""

    def __init__(self, tasks_dir: Optional[Path] = None, output_dir: Optional[Path] = None):
        base_dir = Path(__file__).parent
        self.tasks_dir = tasks_dir or (base_dir / "tasks")
        self.output_dir = output_dir or (base_dir / "results")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def list_tasks(self) -> List[Path]:
        """Discover all task directories."""
        if not self.tasks_dir.exists():
            return []
        return sorted([d for d in self.tasks_dir.iterdir() if d.is_dir() and (d / "task.yaml").exists()])

    def run_task(self, task_dir: Path, target_workspace: Path) -> Dict[str, Any]:
        """Execute a single benchmark task in a clean sandbox workspace."""
        task_meta_file = task_dir / "task.yaml"
        meta: Dict[str, Any] = yaml.safe_load(task_meta_file.read_text(encoding="utf-8"))

        task_id = meta.get("id", task_dir.name)
        task_prompt = meta.get("prompt", "")
        category = meta.get("category", "General")
        verification_cfg = meta.get("verification", {})

        # 1. Populate workspace from repo/
        repo_src = task_dir / "repo"
        if repo_src.exists():
            shutil.copytree(repo_src, target_workspace, dirs_exist_ok=True)

        # Initialize git inside target_workspace
        subprocess.run(["git", "init"], cwd=str(target_workspace), check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["git", "config", "user.name", "BenchmarkRunner"], cwd=str(target_workspace), check=True)
        subprocess.run(["git", "config", "user.email", "benchmark@agent.local"], cwd=str(target_workspace), check=True)
        subprocess.run(["git", "add", "."], cwd=str(target_workspace), check=True)
        subprocess.run(["git", "commit", "-m", "initial benchmark commit"], cwd=str(target_workspace), check=True)

        # 2. Setup Agent & Provider
        solution_patch = task_dir / "solution"
        provider = MockProvider(model_name="benchmark-eval-model")

        # Program mock provider with solution if available
        if solution_patch.exists():
            for f in solution_patch.glob("*"):
                if f.is_file():
                    content = f.read_text(encoding="utf-8")
                    provider.queue_tool_call(
                        tool_name="write_file",
                        arguments={
                            "path": f.name,
                            "content": content,
                            "reason": f"Apply benchmark solution for {f.name}"
                        }
                    )
            provider.queue_text_response("Benchmark solution applied. Triggering verification.")

        # 3. Configure Runtime
        config = TerminalAgentConfig()
        test_cmds = verification_cfg.get("tests", ["pytest"])
        config.verification.tests = test_cmds
        if "assertions" in verification_cfg:
            config.verification.assertions = verification_cfg["assertions"]
        if "max_files_changed" in verification_cfg:
            config.verification.diff.max_files_changed = verification_cfg["max_files_changed"]

        secret_guard = SecretGuard(working_dir=target_workspace)
        security_enforcer = SecurityPolicyEnforcer(security_config=config.security, secret_guard=secret_guard)
        sandbox = LocalSandbox(working_dir=target_workspace, default_timeout=30, secret_guard=secret_guard)
        git_adapter = GitAdapter(target_workspace)
        checkpoint_mgr = CheckpointManager(target_workspace)
        session_mgr = SessionManager(target_workspace)
        context_engine = RepositoryContextEngine(target_workspace, secret_guard=secret_guard)

        tool_registry = ToolRegistry(
            working_dir=target_workspace,
            sandbox=sandbox,
            security_enforcer=security_enforcer,
            git_adapter=git_adapter,
            checkpoint_manager=checkpoint_mgr,
            secret_guard=secret_guard
        )

        verifier = IndependentVerifier(
            sandbox=sandbox,
            git_adapter=git_adapter,
            config=config.verification,
            working_dir=target_workspace
        )

        session_state = session_mgr.create_session(task_description=task_prompt)
        telemetry_logger = TelemetryLogger(session_state.session_id, working_dir=target_workspace)

        agent_loop = AgentLoop(
            session_state=session_state,
            config=config,
            provider=provider,
            tool_registry=tool_registry,
            verifier=verifier,
            context_engine=context_engine,
            checkpoint_manager=checkpoint_mgr,
            session_manager=session_mgr,
            telemetry_logger=telemetry_logger
        )

        start_time = time.perf_counter()
        final_state = agent_loop.run()
        duration_ms = int((time.perf_counter() - start_time) * 1000)

        # Build AgentBench compatible run record
        run_record = {
            "session_id": final_state.session_id,
            "task_id": task_id,
            "task": task_prompt,
            "category": category,
            "status": final_state.current_status.value,
            "tests_passed": final_state.last_verification.tests_passed if final_state.last_verification else 0,
            "tests_failed": final_state.last_verification.tests_failed if final_state.last_verification else 0,
            "retries": len(final_state.failures),
            "tool_calls": len([s for s in final_state.completed_steps if s.tool_name]),
            "files_changed": len(final_state.modified_files),
            "duration_ms": duration_ms
        }

        return run_record

    def run_all(self, temp_base: Optional[Path] = None) -> Dict[str, Any]:
        """Execute all benchmark tasks and output full evaluation report."""
        task_dirs = self.list_tasks()
        runs: List[Dict[str, Any]] = []

        for idx, t_dir in enumerate(task_dirs, start=1):
            ws = (temp_base or self.output_dir) / f"ws_{t_dir.name}"
            if ws.exists():
                _rmtree_safely(ws)
            ws.mkdir(parents=True, exist_ok=True)

            try:
                record = self.run_task(t_dir, ws)
                runs.append(record)
            finally:
                if ws.exists():
                    _rmtree_safely(ws)

        passed_count = sum(1 for r in runs if r["status"] == "VERIFIED")
        report = {
            "benchmark_suite": "Terminal Agent SWE-10 Benchmark",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_tasks": len(runs),
            "passed_tasks": passed_count,
            "failed_tasks": len(runs) - passed_count,
            "pass_rate_percent": round((passed_count / len(runs) * 100) if runs else 0.0, 1),
            "runs": runs
        }

        report_file = self.output_dir / "benchmark_report.json"
        report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report


if __name__ == "__main__":
    runner = BenchmarkRunner()
    result = runner.run_all()
    print(json.dumps(result, indent=2))

