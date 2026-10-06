"""Bashkit evaluation and Windows import behavior, without real configuration data."""

from __future__ import annotations

import builtins
import importlib.util
import os
import sys
import uuid
from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from ai_assistant.commands import shell_env_to_win, win_env
from ai_assistant.lib import shell_env

runner = CliRunner()
requires_bashkit = pytest.mark.skipif(importlib.util.find_spec("bashkit") is None, reason="optional bashkit dependency unavailable")


def write_script(tmp_path: Path, text: str, *, name: str = "settings.zshrc", encoding: str = "utf-8") -> Path:
    file = tmp_path / name
    file.write_text(text, encoding=encoding, newline="")
    return file


@requires_bashkit
def test_paseo_style_exports_keep_complete_prompt(tmp_path):
    prompt = "# 中文标题\n\n$HOME `command` %USERPROFILE%\n  保留缩进与尾部空格  "
    script = "export PROVIDER=sample\nexport MODEL='test model'\nexport MODE=local\n"
    script += f"PROMPT=\"$(cat <<'PROMPT_EOF'\n{prompt}\n\nPROMPT_EOF\n)\"\nexport PROMPT\n"
    script += "alias reload='source ~/.zshrc && osascript -e example'\n"
    assert shell_env.evaluate_exports(write_script(tmp_path, script)) == {"PROVIDER": "sample", "MODEL": "test model", "MODE": "local", "PROMPT": prompt}


@requires_bashkit
def test_assignments_exports_and_multiline_quoting(tmp_path):
    file = write_script(tmp_path, "LOCAL=hidden\nexport VALUE=first\nVALUE=second\nexport EMPTY=''\nMULTI='first\n\nlast\n'\nexport MULTI\n")
    assert shell_env.evaluate_exports(file) == {"VALUE": "second", "EMPTY": "", "MULTI": "first\n\nlast\n"}


@requires_bashkit
def test_expansion_control_flow_functions_and_relative_source(tmp_path):
    write_script(tmp_path, "export CHILD=child\n", name="child file.sh")
    file = write_script(tmp_path, 'source \'./child file.sh\'\nmake_value() { export RESULT="${SEED}-${CHILD}"; }\nif [ "$SEED" = explicit ]; then make_value; fi\n')
    assert shell_env.evaluate_exports(file, {"SEED": "explicit"}) == {"CHILD": "child", "RESULT": "explicit-child"}


@requires_bashkit
def test_does_not_inherit_host_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_ASSISTANT_HOST_SENTINEL", "host-secret")
    file = write_script(tmp_path, 'export RESULT="${AI_ASSISTANT_HOST_SENTINEL-unset}"\n')
    assert shell_env.evaluate_exports(file) == {"RESULT": "unset"}


@requires_bashkit
def test_initial_exports_only_return_changes(tmp_path):
    file = write_script(tmp_path, "export SAME=unchanged\nexport CHANGED=new\n")
    assert shell_env.evaluate_exports(file, {"SAME": "unchanged", "CHANGED": "old"}) == {"CHANGED": "new"}


@requires_bashkit
def test_reassigning_initial_and_exported_variables_uses_final_value(tmp_path):
    file = write_script(tmp_path, "INITIAL=updated\nexport VALUE=first\nVALUE=second\nexport VALUE=third\n")
    assert shell_env.evaluate_exports(file, {"INITIAL": "old"}) == {"INITIAL": "updated", "VALUE": "third"}


@requires_bashkit
def test_utf8_bom_and_literal_line_endings(tmp_path):
    file = write_script(tmp_path, "export TEXT=$'中文\\r\\nnext'\n", encoding="utf-8-sig")
    assert shell_env.evaluate_exports(file) == {"TEXT": "中文\r\nnext"}


@requires_bashkit
def test_windows_crlf_source_line_endings(tmp_path):
    file = write_script(tmp_path, "export FIRST=one\r\n\r\nexport SECOND=two\r\n")
    assert shell_env.evaluate_exports(file) == {"FIRST": "one", "SECOND": "two"}


@requires_bashkit
@pytest.mark.parametrize("script", ["export BEFORE=ok\nfalse\nexport AFTER=wrong", 'export TOKEN="unterminated-secret', "missing_command private-secret\nexport AFTER=wrong"])
def test_shell_failures_never_return_partial_exports_or_leak_output(tmp_path, script):
    file = write_script(tmp_path, script)
    with pytest.raises(shell_env.ShellEnvError) as error:
        shell_env.evaluate_exports(file)
    assert "no variables imported" in str(error.value)
    assert "secret" not in str(error.value)


@requires_bashkit
def test_stderr_is_hidden_and_stops_import(tmp_path):
    file = write_script(tmp_path, "echo private-secret >&2\nexport RESULT=ok")
    with pytest.raises(shell_env.ShellEnvError, match="Shell output is hidden") as error:
        shell_env.evaluate_exports(file)
    assert "private-secret" not in str(error.value)


@requires_bashkit
def test_timeout_stops_evaluation(tmp_path):
    file = write_script(tmp_path, "sleep 1\nexport AFTER=wrong")
    with pytest.raises(shell_env.ShellEnvError):
        shell_env.evaluate_exports(file, timeout_seconds=0.01)


@requires_bashkit
def test_host_source_directory_is_read_only(tmp_path):
    original = write_script(tmp_path, "original", name="keep.txt")
    file = write_script(tmp_path, "echo overwritten > ./keep.txt\nexport RESULT=wrong")
    with pytest.raises(shell_env.ShellEnvError):
        shell_env.evaluate_exports(file)
    assert original.read_text(encoding="utf-8") == "original"


@requires_bashkit
def test_temporary_files_stay_in_virtual_filesystem(tmp_path):
    file = write_script(tmp_path, "echo value > /tmp/shell-env-test\nexport RESULT=$(cat /tmp/shell-env-test)")
    assert shell_env.evaluate_exports(file) == {"RESULT": "value"}
    assert not (tmp_path / "shell-env-test").exists()


def test_explicit_environment_parsing_preserves_equals_and_empty_values():
    assert shell_env.parse_initial_env(["FIRST=a=b", "EMPTY=", "FIRST=last"]) == {"FIRST": "last", "EMPTY": ""}


@pytest.mark.parametrize("entry", ["secret-without-equals", "bad-name=secret", "=secret"])
def test_invalid_initial_environment_does_not_leak_values(entry):
    with pytest.raises(shell_env.ShellEnvError) as error:
        shell_env.parse_initial_env([entry])
    assert "secret" not in str(error.value)


@pytest.mark.parametrize(
    "exports",
    [{"FOO": "a", "foo": "b"}, {"BAD-NAME": "secret"}, {"VALUE": "secret\0"}, {"VALUE": "\ud800"}, {"VALUE": "x" * 32767}, {"VALUE": "😀" * 16384}],
)
def test_export_preflight_rejects_invalid_windows_values(exports):
    with pytest.raises(shell_env.ShellEnvError):
        shell_env.validate_exports(exports)


def test_missing_or_non_utf8_source_has_safe_error(tmp_path):
    for file in [tmp_path / "missing", write_script(tmp_path, "é", encoding="latin-1")]:
        # This preflight runs only after loading the optional interpreter.
        if importlib.util.find_spec("bashkit") is None:
            pytest.skip("optional bashkit dependency unavailable")
        with pytest.raises(shell_env.ShellEnvError, match="Cannot read"):
            shell_env.evaluate_exports(file)


@pytest.fixture
def cli_backend(tmp_path, monkeypatch):
    file = write_script(tmp_path, "# synthetic input\n")
    monkeypatch.setattr(shell_env_to_win.sys, "platform", "win32")
    evaluate = Mock(return_value={"AI_ASSISTANT_IMPORT_A": "private-secret"})
    read = Mock(return_value=None)
    write = Mock()
    broadcast = Mock()
    monkeypatch.setattr(shell_env_to_win, "evaluate_exports", evaluate)
    monkeypatch.setattr(win_env, "read_var", read)
    monkeypatch.setattr(win_env, "write_var", write)
    monkeypatch.setattr(win_env, "broadcast_setting_change", broadcast)
    monkeypatch.delenv("AI_ASSISTANT_IMPORT_A", raising=False)
    monkeypatch.delenv("AI_ASSISTANT_IMPORT_B", raising=False)
    return file, evaluate, read, write, broadcast


def test_dry_run_has_no_windows_side_effects(cli_backend):
    file, evaluate, _, write, broadcast = cli_backend
    result = runner.invoke(shell_env_to_win.app, [str(file), "--dry-run", "--env", "SEED=a=b"])
    assert result.exit_code == 0, result.output
    evaluate.assert_called_once_with(file, {"SEED": "a=b"})
    write.assert_not_called()
    broadcast.assert_not_called()
    assert "AI_ASSISTANT_IMPORT_A" not in os.environ
    assert "private-secret" not in result.output


def test_import_uses_reg_sz_and_broadcasts_once(cli_backend):
    file, evaluate, read, write, broadcast = cli_backend
    evaluate.return_value = {"AI_ASSISTANT_IMPORT_A": "first\nsecond %USERPROFILE%", "AI_ASSISTANT_IMPORT_B": ""}
    read.return_value = ("old", win_env.REG_EXPAND_SZ)
    result = runner.invoke(shell_env_to_win.app, [str(file)])
    assert result.exit_code == 0, result.output
    assert write.call_count == 2
    write.assert_any_call(win_env.WriteScope.user, "AI_ASSISTANT_IMPORT_A", "first\nsecond %USERPROFILE%", win_env.REG_SZ)
    assert os.environ["AI_ASSISTANT_IMPORT_B"] == ""
    broadcast.assert_called_once_with()
    assert "update AI_ASSISTANT_IMPORT_A" in result.output
    assert "%USERPROFILE%" not in result.output


@pytest.mark.parametrize("include_path", [False, True])
def test_path_policy(cli_backend, include_path):
    file, evaluate, _, write, _ = cli_backend
    evaluate.return_value = {"PATH": "/bin:/custom"}
    arguments = [str(file), "--dry-run"] + (["--include-path"] if include_path else [])
    result = runner.invoke(shell_env_to_win.app, arguments)
    assert result.exit_code == 0, result.output
    assert ("Skipped PATH" in result.output) is not include_path
    assert ("add PATH" in result.output) is include_path
    write.assert_not_called()


def test_evaluation_failure_prevents_all_registry_access(cli_backend):
    file, evaluate, read, write, broadcast = cli_backend
    evaluate.side_effect = shell_env.ShellEnvError("Shell evaluation failed; no variables imported.")
    result = runner.invoke(shell_env_to_win.app, [str(file)])
    assert result.exit_code == 1
    read.assert_not_called()
    write.assert_not_called()
    broadcast.assert_not_called()


def test_read_failure_prevents_writes_and_hides_details(cli_backend):
    file, _, read, write, broadcast = cli_backend
    read.side_effect = OSError("private-secret")
    result = runner.invoke(shell_env_to_win.app, [str(file)])
    assert result.exit_code == 1
    assert "private-secret" not in result.output
    write.assert_not_called()
    broadcast.assert_not_called()


def test_partial_failure_reports_written_variables_and_broadcasts(cli_backend):
    file, evaluate, _, write, broadcast = cli_backend
    evaluate.return_value = {"AI_ASSISTANT_IMPORT_A": "one", "AI_ASSISTANT_IMPORT_B": "two"}
    write.side_effect = [None, OSError("private-secret")]
    result = runner.invoke(shell_env_to_win.app, [str(file)])
    assert result.exit_code == 1
    assert "1 registry writes completed" in result.output
    assert "Written variables: AI_ASSISTANT_IMPORT_A" in result.output
    assert "private-secret" not in result.output
    assert "AI_ASSISTANT_IMPORT_B" not in os.environ
    broadcast.assert_called_once_with()


def test_system_permission_failure_does_not_broadcast(cli_backend):
    file, _, _, write, broadcast = cli_backend
    write.side_effect = PermissionError("private-secret")
    result = runner.invoke(shell_env_to_win.app, [str(file), "--scope", "system"])
    assert result.exit_code == 1
    write.assert_called_once_with(win_env.WriteScope.system, "AI_ASSISTANT_IMPORT_A", "private-secret", win_env.REG_SZ)
    assert "private-secret" not in result.output
    broadcast.assert_not_called()


def test_broadcast_failure_reports_saved_variables(cli_backend):
    file, _, _, _, broadcast = cli_backend
    broadcast.side_effect = RuntimeError("private-secret")
    result = runner.invoke(shell_env_to_win.app, [str(file)])
    assert result.exit_code == 1
    assert "Variables were written" in result.output
    assert "private-secret" not in result.output


def test_root_and_command_help_work_without_bashkit(monkeypatch):
    from ai_assistant.commands.main import cmd as root_cmd

    original_import = builtins.__import__

    def reject_bashkit(name, *args, **kwargs):
        if name == "bashkit":
            raise AssertionError("help must not import bashkit")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_bashkit)
    for arguments in [["--help"], ["shell-env-to-win", "--help"]]:
        result = runner.invoke(root_cmd, arguments, terminal_width=160)
        assert result.exit_code == 0, result.output
        assert "shell-env-to-win" in result.output


@pytest.mark.parametrize("error", [ModuleNotFoundError("No module named 'bashkit'"), ImportError("Cannot load the native extension")])
def test_missing_optional_dependency_has_install_hint(cli_backend, error):
    file, evaluate, _, _, _ = cli_backend
    evaluate.side_effect = error
    result = runner.invoke(shell_env_to_win.app, [str(file)])
    assert result.exit_code == 1
    assert "ai-assistant[shell-env]" in result.output


def test_non_windows_guard(tmp_path, monkeypatch):
    file = write_script(tmp_path, "export VALUE=ok")
    monkeypatch.setattr(shell_env_to_win.sys, "platform", "linux")
    result = runner.invoke(shell_env_to_win.app, [str(file)])
    assert result.exit_code == 1
    assert "shell-env-to-win 仅支持 Windows" in result.output


@requires_bashkit
@pytest.mark.skipif(sys.platform != "win32", reason="Windows registry roundtrip")
def test_windows_multiline_registry_roundtrip(tmp_path, monkeypatch):
    name = "AI_ASSISTANT_TEST_" + uuid.uuid4().hex
    value = "中文\n\n$HOME `literal` %USERPROFILE%\n"
    file = write_script(tmp_path, f"export {name}='{value}'\n")
    monkeypatch.setenv(name, "previous-process-value")
    broadcast = Mock()
    monkeypatch.setattr(win_env, "broadcast_setting_change", broadcast)
    try:
        result = runner.invoke(shell_env_to_win.app, [str(file)])
        assert result.exit_code == 0, result.output
        assert win_env.read_var(win_env.WriteScope.user, name) == (value, win_env.REG_SZ)
        assert os.environ[name] == value
        broadcast.assert_called_once_with()
    finally:
        win_env.delete_var(win_env.WriteScope.user, name)
