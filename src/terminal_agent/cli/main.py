"""Main Typer CLI entrypoint for Terminal Agent."""

import importlib.metadata
import sys
from pathlib import Path
from typing import Optional
import typer

from terminal_agent.cli.commands.checkpoint import checkpoint_app, rollback_command
from terminal_agent.cli.commands.config_cmd import config_command
from terminal_agent.cli.commands.diff import diff_command
from terminal_agent.cli.commands.doctor import doctor_command
from terminal_agent.cli.commands.resume import resume_command
from terminal_agent.cli.commands.run import run_command
from terminal_agent.cli.commands.setup import setup_command
from terminal_agent.cli.commands.status import status_command
from terminal_agent.cli.commands.test import test_command
from terminal_agent.cli.commands.clean import clean_command
from terminal_agent.cli.commands.trace import trace_command


def version_callback(value: bool):
    if value:
        try:
            ver = importlib.metadata.version("terminal-agent-cli")
        except Exception:
            try:
                ver = importlib.metadata.version("terminal-agent")
            except Exception:
                from terminal_agent import __version__ as ver

        typer.echo(f"terminal-agent v{ver}")
        raise typer.Exit()
    

app = typer.Typer(
    name="terminal-agent",
    help="Terminal Agent: Build. Verify. Ship. Autonomous terminal-based coding agent.",
    no_args_is_help=False
)


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        callback=version_callback,
        is_eager=True,
        help="Show the version and exit.",
    )
):
    pass


# Register Subcommands
app.command(name="run", help="Run an autonomous coding task.")(run_command)
app.command(name="setup", help="Interactively configure model providers (Ollama, OpenAI, Claude, Gemini).")(setup_command)
app.command(name="resume", help="Resume an interrupted agent session.")(resume_command)
app.command(name="status", help="Inspect workspace git status and active session.")(status_command)
app.command(name="diff", help="View working tree git diff and stats.")(diff_command)
app.command(name="test", help="Execute independent verification test suite.")(test_command)
app.add_typer(checkpoint_app, name="checkpoint")
app.command(name="rollback", help="Restore repository state to a previous checkpoint.")(rollback_command)
app.command(name="doctor", help="Check system health, sandboxing, and provider status.")(doctor_command)
app.command(name="trace", help="View structured telemetry trace for a session.")(trace_command)
app.command(name="config", help="View or initialize configuration file.")(config_command)
app.command(name="clean", help="Prune old sessions, checkpoints, and telemetry files.")(clean_command)

KNOWN_COMMANDS = {
    "run", "setup", "resume", "status", "diff", "test", "checkpoint",
    "rollback", "doctor", "trace", "config", "clean", "--help", "-h",
    "--version", "-v"
}


def cli():
    """Main CLI entrypoint handling automatic default 'run' routing."""
    args = sys.argv[1:]
    if args:
        first_arg = args[0]
        if first_arg not in KNOWN_COMMANDS and not first_arg.startswith("-"):
            # Route bare string task to 'run' subcommand
            sys.argv.insert(1, "run")
    elif len(sys.argv) == 1:
        # Bare terminal-agent invocation -> prompt in run command
        sys.argv.append("run")

    app()


if __name__ == "__main__":
    cli()
