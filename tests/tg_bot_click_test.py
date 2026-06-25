import pytest
from click.testing import CliRunner as ClickCliRunner
from typer.testing import CliRunner

from ai_assistant.commands import tg_bot_click

click_runner = ClickCliRunner()
typer_runner = CliRunner()


def test_default_session_file_uses_xdg_state_home(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    assert tg_bot_click.default_session_file(platform="linux") == tmp_path / "ai-assistant" / "telegram" / "tg-bot-click.session"


def test_resolve_session_file_prefers_explicit_path(tmp_path):
    session = tmp_path / "custom.session"

    assert tg_bot_click.resolve_session_file(session) == session


def test_copy_session_file_roundtrip(tmp_path):
    source = tmp_path / "source.session"
    target = tmp_path / "nested" / "target.session"
    source.write_text("session-data", encoding="utf-8")

    copied = tg_bot_click.copy_session_file(source, target)

    assert copied == target
    assert target.read_text(encoding="utf-8") == "session-data"


def test_copy_session_file_rejects_overwrite_without_force(tmp_path):
    source = tmp_path / "source.session"
    target = tmp_path / "target.session"
    source.write_text("new", encoding="utf-8")
    target.write_text("old", encoding="utf-8")

    with pytest.raises(tg_bot_click.TgBotClickError, match="already exists"):
        tg_bot_click.copy_session_file(source, target)

    assert target.read_text(encoding="utf-8") == "old"


def test_select_button_defaults_to_first_button():
    selection = tg_bot_click.select_button([["签到", "设置"], ["取消"]])

    assert selection == tg_bot_click.ButtonSelection(row=0, column=0, text="签到")


def test_select_button_can_target_exact_button_text():
    selection = tg_bot_click.select_button([["详情", "签到"], ["取消"]], "签到")

    assert selection == tg_bot_click.ButtonSelection(row=0, column=1, text="签到")


def test_select_button_reports_missing_button_text():
    with pytest.raises(tg_bot_click.TgBotClickError, match="no button with text"):
        tg_bot_click.select_button([["详情"]], "签到")


def test_validate_bot_username_strips_at_prefix():
    assert tg_bot_click.validate_bot_username("@example_bot") == "example_bot"


def test_cli_import_session_copies_into_selected_session(tmp_path):
    source = tmp_path / "source.session"
    target = tmp_path / "target.session"
    source.write_text("session-data", encoding="utf-8")

    result = click_runner.invoke(tg_bot_click.cmd, ["--import-session", str(source), "--session", str(target)])

    assert result.exit_code == 0, result.output
    assert "Imported Telegram session" in result.output
    assert target.read_text(encoding="utf-8") == "session-data"


def test_cli_export_session_copies_from_selected_session(tmp_path):
    source = tmp_path / "source.session"
    target = tmp_path / "target.session"
    source.write_text("session-data", encoding="utf-8")

    result = click_runner.invoke(tg_bot_click.cmd, ["--session", str(source), "--export-session", str(target)])

    assert result.exit_code == 0, result.output
    assert "Exported Telegram session" in result.output
    assert target.read_text(encoding="utf-8") == "session-data"


def test_cli_rejects_missing_credentials_before_importing_telethon():
    result = click_runner.invoke(tg_bot_click.cmd, ["@example_bot", "--match", "签到"])

    assert result.exit_code == 1
    assert "missing Telegram credential" in result.output


def test_cli_help_documents_session_migration():
    result = click_runner.invoke(tg_bot_click.cmd, ["--help"])
    option_names = {option for parameter in tg_bot_click.cmd.params for option in parameter.opts}
    option_envvars = {parameter.envvar for parameter in tg_bot_click.cmd.params if parameter.envvar}

    assert result.exit_code == 0
    assert "--export-session" in option_names
    assert "--import-session" in option_names
    assert "TG_API_ID" in option_envvars


def test_root_command_registers_tg_bot_click():
    from ai_assistant.commands.main import cmd as root_cmd

    result = typer_runner.invoke(root_cmd, ["tg-bot-click", "--help"])

    assert result.exit_code == 0
    assert "Telegram bot" in result.output
