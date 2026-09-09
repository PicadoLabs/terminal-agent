"""Unit tests for the clean command and prune helpers."""

import os
import time
from pathlib import Path

from typer.testing import CliRunner

from terminal_agent.checkpoints.manager import CheckpointManager
from terminal_agent.cli.commands.clean import collect_clean_targets
from terminal_agent.cli.main import app
from terminal_agent.session.manager import SessionManager


runner = CliRunner()


def _write_file(path: Path, content: str = "x" * 100) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _age_file(path: Path, days: int) -> None:
    ts = time.time() - (days * 86400)
    os.utime(path, (ts, ts))


def test_delete_sessions_older_than(tmp_path: Path):
    mgr = SessionManager(tmp_path)
    old = mgr.sessions_dir / "old.json"
    new = mgr.sessions_dir / "new.json"
    _write_file(old)
    _write_file(new)
    _age_file(old, 10)

    deleted = mgr.delete_sessions_older_than(7)
    assert old in deleted
    assert not old.exists()
    assert new.exists()
    assert mgr.sessions_dir.exists()


def test_prune_checkpoints(tmp_path: Path):
    mgr = CheckpointManager(tmp_path)
    old_dir = mgr.checkpoints_dir / "chk_old"
    new_dir = mgr.checkpoints_dir / "chk_new"
    _write_file(old_dir / "metadata.json", "{}")
    _write_file(new_dir / "metadata.json", "{}")
    _age_file(old_dir, 10)

    deleted = mgr.prune_checkpoints(7)
    assert old_dir in deleted
    assert not old_dir.exists()
    assert new_dir.exists()
    assert mgr.checkpoints_dir.exists()


def test_collect_dry_run_counts(tmp_path: Path):
    root = tmp_path / ".terminal_agent"
    sess = root / "sessions" / "s.json"
    chk = root / "checkpoints" / "c1" / "metadata.json"
    tel = root / "telemetry" / "t.json"
    _write_file(sess)
    _write_file(chk)
    _write_file(tel)
    _age_file(sess, 10)
    _age_file(chk.parent, 10)
    _age_file(tel, 10)

    targets = collect_clean_targets(tmp_path, days=7, purge_all=False)
    kinds = {k for k, _, _ in targets}
    assert "session" in kinds
    assert "checkpoint" in kinds
    assert sum(s for _, _, s in targets) > 0


def test_clean_dry_run_cli(tmp_path: Path):
    sess = tmp_path / ".terminal_agent" / "sessions" / "s.json"
    _write_file(sess, "hello world")
    _age_file(sess, 10)

    result = runner.invoke(app, ["clean", "--dry-run", "--days", "7", "-C", str(tmp_path)])
    assert result.exit_code == 0
    assert sess.exists()
    assert "item" in result.stdout.lower() or "MB" in result.stdout


def test_clean_all_removes_files_keeps_dirs(tmp_path: Path):
    sess = tmp_path / ".terminal_agent" / "sessions" / "s.json"
    chk = tmp_path / ".terminal_agent" / "checkpoints" / "c1" / "metadata.json"
    tel = tmp_path / ".terminal_agent" / "telemetry" / "t.json"
    _write_file(sess)
    _write_file(chk)
    _write_file(tel)

    result = runner.invoke(app, ["clean", "--all", "-C", str(tmp_path)])
    assert result.exit_code == 0
    assert not sess.exists()
    assert not chk.parent.exists()
    assert not tel.exists()
    assert (tmp_path / ".terminal_agent" / "sessions").exists()
    assert (tmp_path / ".terminal_agent" / "checkpoints").exists()


def test_clean_empty_directory(tmp_path: Path):
    (tmp_path / ".terminal_agent").mkdir()
    result = runner.invoke(app, ["clean", "--all", "-C", str(tmp_path)])
    assert result.exit_code == 0
    assert "nothing" in result.stdout.lower() or "no session" in result.stdout.lower()


def test_clean_missing_root(tmp_path: Path):
    result = runner.invoke(app, ["clean", "-C", str(tmp_path)])
    assert result.exit_code == 0
    assert "nothing to clean" in result.stdout.lower()
