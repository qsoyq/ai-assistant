from typer.testing import CliRunner

from ai_assistant.commands.cindy import cmd
from ai_assistant.commands.main import cmd as root_cmd

runner = CliRunner()


def test_cindy_command_help():
    result = runner.invoke(cmd, ["--help"])
    assert result.exit_code == 0
    assert "Cindy" in result.output


def test_root_registers_cindy_command():
    result = runner.invoke(root_cmd, ["cindy", "--help"])
    assert result.exit_code == 0
    assert "Cindy" in result.output
