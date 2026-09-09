"""CLI commands package for Terminal Agent."""

from terminal_agent.cli.commands.run import run_command
from terminal_agent.cli.commands.resume import resume_command
from terminal_agent.cli.commands.status import status_command
from terminal_agent.cli.commands.diff import diff_command
from terminal_agent.cli.commands.test import test_command
from terminal_agent.cli.commands.checkpoint import checkpoint_app, rollback_command
from terminal_agent.cli.commands.doctor import doctor_command
from terminal_agent.cli.commands.trace import trace_command
from terminal_agent.cli.commands.config_cmd import config_command
from terminal_agent.cli.commands.clean import clean_command

__all__ = [
    "run_command",
    "resume_command",
    "status_command",
    "diff_command",
    "test_command",
    "checkpoint_app",
    "rollback_command",
    "doctor_command",
    "trace_command",
    "config_command",
    "clean_command",
]
