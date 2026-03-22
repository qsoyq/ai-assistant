import pytest
import typer
from typer.testing import CliRunner

from ai_assistant.commands.docker import (
    ContainerLogTarget,
    _get_current_docker_context,
    _get_docker_context_host,
    can_clear_with_helper_container,
    cmd,
    select_container_targets,
    truncate_log_file,
)
from ai_assistant.commands.main import cmd as main_cmd


def build_target(name: str, container_id: str, short_id: str, log_path: str = "/var/lib/docker/containers/test/test-json.log") -> ContainerLogTarget:
    return ContainerLogTarget(
        id=container_id,
        short_id=short_id,
        name=name,
        log_path=log_path,
    )


def test_select_container_targets_matches_exact_name():
    targets = [build_target("web", "1234567890abcdef", "1234567890ab")]

    selected = select_container_targets(targets, "web")

    assert selected == targets


def test_select_container_targets_matches_full_id():
    targets = [build_target("web", "1234567890abcdef", "1234567890ab")]

    selected = select_container_targets(targets, "1234567890abcdef")

    assert selected == targets


def test_select_container_targets_matches_short_id():
    targets = [build_target("web", "1234567890abcdef", "1234567890ab")]

    selected = select_container_targets(targets, "1234567890ab")

    assert selected == targets


def test_select_container_targets_returns_all_for_wildcard():
    targets = [
        build_target("web", "1234567890abcdef", "1234567890ab"),
        build_target("db", "fedcba0987654321", "fedcba098765"),
    ]

    selected = select_container_targets(targets, "*")

    assert selected == targets


def test_select_container_targets_rejects_unknown_selector():
    targets = [build_target("web", "1234567890abcdef", "1234567890ab")]

    with pytest.raises(typer.BadParameter, match="未找到容器"):
        select_container_targets(targets, "missing")


def test_select_container_targets_rejects_ambiguous_selector():
    targets = [
        build_target("abcdef123456", "1111111111111111", "111111111111"),
        build_target("web", "2222222222222222", "abcdef123456"),
    ]

    with pytest.raises(typer.BadParameter, match="匹配到多个容器"):
        select_container_targets(targets, "abcdef123456")


def test_truncate_log_file_clears_existing_file(tmp_path):
    log_file = tmp_path / "container-json.log"
    log_file.write_bytes(b'{"log":"hello"}\n')

    truncate_log_file(str(log_file))

    assert log_file.read_bytes() == b""


def test_can_clear_with_helper_container_requires_daemon_log_root():
    assert can_clear_with_helper_container("/var/lib/docker/containers/abc/abc-json.log") is True
    assert can_clear_with_helper_container("/tmp/abc-json.log") is False
    assert can_clear_with_helper_container("relative/path.log") is False


def test_get_current_docker_context_reads_config(tmp_path):
    (tmp_path / "config.json").write_text('{"currentContext":"orbstack"}')

    assert _get_current_docker_context(tmp_path) == "orbstack"


def test_get_current_docker_context_ignores_default(tmp_path):
    (tmp_path / "config.json").write_text('{"currentContext":"default"}')

    assert _get_current_docker_context(tmp_path) is None


def test_get_docker_context_host_reads_meta(tmp_path):
    (tmp_path / "config.json").write_text('{"currentContext":"orbstack"}')
    meta_dir = tmp_path / "contexts" / "meta" / "example"
    meta_dir.mkdir(parents=True)
    (meta_dir / "meta.json").write_text('{"Name":"orbstack","Endpoints":{"docker":{"Host":"unix:///Users/test/.orbstack/run/docker.sock"}}}')

    assert _get_docker_context_host(tmp_path) == "unix:///Users/test/.orbstack/run/docker.sock"


def test_get_docker_context_host_returns_none_without_matching_meta(tmp_path):
    (tmp_path / "config.json").write_text('{"currentContext":"orbstack"}')
    meta_dir = tmp_path / "contexts" / "meta" / "example"
    meta_dir.mkdir(parents=True)
    (meta_dir / "meta.json").write_text('{"Name":"desktop-linux","Endpoints":{"docker":{"Host":"unix:///tmp/docker.sock"}}}')

    assert _get_docker_context_host(tmp_path) is None


def test_docker_command_help_contains_log_clear():
    result = CliRunner().invoke(cmd, ["--help"])

    assert result.exit_code == 0
    assert "log-clear" in result.output


def test_main_help_contains_docker_subcommand():
    result = CliRunner().invoke(main_cmd, ["--help"])

    assert result.exit_code == 0
    assert "docker" in result.output
