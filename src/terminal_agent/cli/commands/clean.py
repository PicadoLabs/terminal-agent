"""CLI clean command to prune old sessions, checkpoints, and telemetry."""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Tuple

import typer
from rich.table import Table

from terminal_agent.checkpoints.manager import CheckpointManager
from terminal_agent.cli.theme import console
from terminal_agent.cli.ui import render_header
from terminal_agent.session.manager import SessionManager


def _dir_size_bytes(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    for root, _, files in os.walk(path):
        for name in files:
            fp = Path(root) / name
            try:
                total += fp.stat().st_size
            except OSError:
                continue
    return total


def _format_mb(num_bytes: int) -> str:
    return f"{num_bytes / (1024 * 1024):.2f} MB"


def _is_older_than(path: Path, cutoff_ts: Optional[float]) -> bool:
    if cutoff_ts is None:
        return True
    try:
        return path.stat().st_mtime < cutoff_ts
    except OSError:
        return False


def collect_clean_targets(
    working_dir: Path,
    days: Optional[int],
    purge_all: bool,
) -> List[Tuple[str, Path, int]]:
    """Return (kind, path, size_bytes) items that would be removed."""
    cutoff = None
    if not purge_all:
        age = days if days is not None else 7
        cutoff = (datetime.now(timezone.utc) - timedelta(days=age)).timestamp()

    root = working_dir / ".terminal_agent"
    targets: List[Tuple[str, Path, int]] = []

    sessions_dir = root / "sessions"
    if sessions_dir.exists():
        for json_file in sessions_dir.glob("*.json"):
            if _is_older_than(json_file, cutoff):
                targets.append(("session", json_file, _dir_size_bytes(json_file)))

    checkpoints_dir = root / "checkpoints"
    if checkpoints_dir.exists():
        for entry in checkpoints_dir.iterdir():
            if entry.is_dir() and _is_older_than(entry, cutoff):
                targets.append(("checkpoint", entry, _dir_size_bytes(entry)))

    for kind in ("telemetry", "traces"):
        tdir = root / kind
        if not tdir.exists():
            continue
        for entry in tdir.iterdir():
            if entry.is_file() and _is_older_than(entry, cutoff):
                targets.append((kind.rstrip("s"), entry, _dir_size_bytes(entry)))
            elif entry.is_dir() and _is_older_than(entry, cutoff):
                targets.append((kind.rstrip("s"), entry, _dir_size_bytes(entry)))

    return targets


def apply_deletes(working_dir: Path, days: Optional[int], purge_all: bool) -> List[Path]:
    """Delete matching artifacts. Uses manager helpers for sessions/checkpoints."""
    age = None if purge_all else (days if days is not None else 7)
    SessionManager(working_dir).delete_sessions_older_than(age)
    CheckpointManager(working_dir).prune_checkpoints(age)

    deleted: List[Path] = []
    for kind, path, _size in collect_clean_targets(working_dir, days=days, purge_all=purge_all):
        if kind in ("session", "checkpoint"):
            deleted.append(path)
            continue
        try:
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()
            deleted.append(path)
        except OSError:
            continue
    return deleted


def clean_command(
    all_data: bool = typer.Option(
        False,
        "--all",
        help="Purge all sessions, checkpoints, and telemetry logs.",
    ),
    days: int = typer.Option(
        7,
        "--days",
        help="Purge items older than N days (ignored when --all is set).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show files and disk space that would be freed without deleting.",
    ),
    working_dir: Optional[Path] = typer.Option(
        None,
        "--cwd",
        "-C",
        help="Target repository directory",
    ),
) -> None:
    """Prune old session, checkpoint, and telemetry artifacts."""
    render_header()
    target_dir = (working_dir or Path.cwd()).resolve()
    root = target_dir / ".terminal_agent"

    if not root.exists():
        console.print("[agent.muted]No .terminal_agent directory found. Nothing to clean.[/agent.muted]")
        raise typer.Exit(0)

    targets = collect_clean_targets(target_dir, days=days, purge_all=all_data)
    total_bytes = sum(size for _, _, size in targets)

    if not targets:
        console.print("[agent.muted]No session, checkpoint, or telemetry files to clean.[/agent.muted]")
        raise typer.Exit(0)

    table = Table(title="[bold agent.accent]CLEAN TARGETS[/bold agent.accent]", border_style="agent.border")
    table.add_column("Kind", style="agent.text")
    table.add_column("Path", style="agent.muted")
    table.add_column("Size", justify="right")
    for kind, path, size in targets:
        try:
            rel = path.relative_to(target_dir)
        except ValueError:
            rel = path
        table.add_row(kind, str(rel), _format_mb(size))
    console.print(table)
    console.print(
        f"[agent.accent]{len(targets)} item(s)[/agent.accent] — "
        f"[agent.success]{_format_mb(total_bytes)}[/agent.success] would be freed."
    )

    if dry_run:
        console.print("[agent.muted]Dry run: no files were deleted.[/agent.muted]")
        return

    apply_deletes(target_dir, days=days, purge_all=all_data)
    console.print("[agent.success]Cleanup complete. Directory structure preserved.[/agent.success]")
