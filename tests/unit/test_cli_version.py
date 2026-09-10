from typer.testing import CliRunner

from terminal_agent.cli.main import app


runner = CliRunner()


def test_version_long_flag():
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert "terminal-agent v0.1.0" in result.stdout


def test_version_short_flag():
    result = runner.invoke(app, ["-v"])

    assert result.exit_code == 0
    assert "terminal-agent v0.1.0" in result.stdout
    