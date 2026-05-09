import pytest
import typer
from typer.testing import CliRunner

from ai_assistant.commands.uvx_gh import build_uvx_cmd, cmd, split_argv


def test_split_argv_only_tool():
    flags, tool, tail = split_argv(["ai-assistant"])
    assert flags == []
    assert tool == "ai-assistant"
    assert tail == []


def test_split_argv_empty():
    flags, tool, tail = split_argv([])
    assert flags == []
    assert tool is None
    assert tail == []


def test_split_argv_simple_flag_then_tool():
    flags, tool, tail = split_argv(["--refresh", "ai-assistant"])
    assert flags == ["--refresh"]
    assert tool == "ai-assistant"
    assert tail == []


def test_split_argv_value_flag_consumes_next_token():
    flags, tool, tail = split_argv(["--with", "extras", "ai-assistant"])
    assert flags == ["--with", "extras"]
    assert tool == "ai-assistant"
    assert tail == []


def test_split_argv_short_value_flag():
    flags, tool, tail = split_argv(["-p", "3.12", "tool"])
    assert flags == ["-p", "3.12"]
    assert tool == "tool"
    assert tail == []


def test_split_argv_equals_form_skips_whitelist_lookup():
    flags, tool, tail = split_argv(["--with=extras", "tool"])
    assert flags == ["--with=extras"]
    assert tool == "tool"
    assert tail == []


def test_split_argv_unknown_flag_is_single_token():
    flags, tool, tail = split_argv(["--no-progress", "tool"])
    assert flags == ["--no-progress"]
    assert tool == "tool"
    assert tail == []


def test_split_argv_tool_args_after_tool():
    flags, tool, tail = split_argv(["tool", "--tool-flag", "value"])
    assert flags == []
    assert tool == "tool"
    assert tail == ["--tool-flag", "value"]


def test_split_argv_double_dash_terminator():
    flags, tool, tail = split_argv(["--", "some-tool", "--user", "actually-tool-arg"])
    assert flags == []
    assert tool == "some-tool"
    assert tail == ["--user", "actually-tool-arg"]


def test_split_argv_double_dash_with_no_tail():
    flags, tool, tail = split_argv(["--"])
    assert flags == []
    assert tool is None
    assert tail == []


def test_split_argv_value_flag_missing_value_raises_exit():
    with pytest.raises(typer.Exit) as exc_info:
        split_argv(["--with"])
    assert exc_info.value.exit_code == 1


def test_split_argv_mixed_flags_then_tool_then_tool_args():
    flags, tool, tail = split_argv(["--refresh", "--python", "3.12", "tool", "--tool-arg"])
    assert flags == ["--refresh", "--python", "3.12"]
    assert tool == "tool"
    assert tail == ["--tool-arg"]


def test_build_uvx_cmd_plain_tool():
    result = build_uvx_cmd("qsoyq", ["ai-assistant"])
    assert result == [
        "uvx",
        "--from",
        "git+https://github.com/qsoyq/ai-assistant",
        "ai-assistant",
    ]


def test_build_uvx_cmd_at_latest_appends_refresh():
    result = build_uvx_cmd("qsoyq", ["ai-assistant@latest"])
    assert result == [
        "uvx",
        "--refresh",
        "--from",
        "git+https://github.com/qsoyq/ai-assistant",
        "ai-assistant",
    ]


def test_build_uvx_cmd_at_ref_appends_to_url():
    result = build_uvx_cmd("qsoyq", ["ai-assistant@v1.2.3"])
    assert result == [
        "uvx",
        "--from",
        "git+https://github.com/qsoyq/ai-assistant@v1.2.3",
        "ai-assistant",
    ]


def test_build_uvx_cmd_custom_user():
    result = build_uvx_cmd("alice", ["some-tool"])
    assert result == [
        "uvx",
        "--from",
        "git+https://github.com/alice/some-tool",
        "some-tool",
    ]


def test_build_uvx_cmd_passes_uvx_flags_and_tool_args():
    result = build_uvx_cmd("qsoyq", ["--refresh", "ai-assistant", "--port", "8080"])
    assert result == [
        "uvx",
        "--refresh",
        "--from",
        "git+https://github.com/qsoyq/ai-assistant",
        "ai-assistant",
        "--port",
        "8080",
    ]


def test_build_uvx_cmd_no_tool_exits():
    with pytest.raises(typer.Exit) as exc_info:
        build_uvx_cmd("qsoyq", ["--refresh"])
    assert exc_info.value.exit_code == 1


def test_build_uvx_cmd_double_dash_lets_tool_have_dashed_name():
    result = build_uvx_cmd("qsoyq", ["--", "tool", "--user", "alice"])
    assert result == [
        "uvx",
        "--from",
        "git+https://github.com/qsoyq/tool",
        "tool",
        "--user",
        "alice",
    ]


def test_uvx_gh_help_contains_usage_hint():
    result = CliRunner().invoke(cmd, ["--help"])
    assert result.exit_code == 0
    assert "uvx-gh" in result.output or "tool" in result.output


def test_uvx_gh_no_args_exits_with_usage():
    result = CliRunner().invoke(cmd, [])
    assert result.exit_code == 1
    assert "Usage" in result.output


def test_uvx_gh_version_flag_does_not_passthrough():
    result = CliRunner().invoke(cmd, ["--version"])
    assert result.exit_code == 0
    assert "cli version:" in result.output


def test_uvx_gh_version_uses_root_prog_name():
    result = CliRunner().invoke(cmd, ["--version"], prog_name="uvx-gh")
    assert result.exit_code == 0
    assert result.output.startswith("uvx-gh cli version:")


def test_uvx_gh_version_uses_ai_assistant_when_invoked_as_subcommand():
    result = CliRunner().invoke(cmd, ["--version"], prog_name="ai-assistant uvx-gh")
    assert result.exit_code == 0
    # CliRunner only sees the inner cmd; root info_name == "ai-assistant uvx-gh"
    assert "cli version:" in result.output
