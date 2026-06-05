import zipfile
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from ai_assistant.commands import git_download
from ai_assistant.commands.git_download import (
    ArchiveMember,
    ArchiveNotFoundError,
    RepoInfo,
    build_plan,
    candidate_branches,
    detect_remote_kind,
    download_path,
    extract_remote_path,
    map_directory_member,
    parse_github_repo,
    resolve_prefix,
    target_dir_name,
)

runner = CliRunner()


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("tw93/waza", RepoInfo("tw93", "waza")),
        ("tw93/waza.git", RepoInfo("tw93", "waza")),
        ("https://github.com/tw93/waza", RepoInfo("tw93", "waza")),
        ("https://github.com/tw93/waza.git", RepoInfo("tw93", "waza")),
        ("git@github.com:tw93/waza.git", RepoInfo("tw93", "waza")),
        ("ssh://git@github.com/tw93/waza.git", RepoInfo("tw93", "waza")),
    ],
)
def test_parse_github_repo(raw, expected):
    assert parse_github_repo(raw) == expected


def test_parse_github_repo_rejects_non_github_url():
    with pytest.raises(typer.BadParameter):
        parse_github_repo("https://gitlab.com/tw93/waza")


def test_resolve_prefix_default_is_none():
    repo = RepoInfo("tw93", "waza")
    assert resolve_prefix(repo, None, None) is None


@pytest.mark.parametrize(
    "prefix,prefix_from,expected",
    [
        ("custom", None, "custom"),
        (None, "owner", "tw93"),
        (None, "repo", "waza"),
    ],
)
def test_resolve_prefix(prefix, prefix_from, expected):
    assert resolve_prefix(RepoInfo("tw93", "waza"), prefix, prefix_from) == expected


def test_resolve_prefix_rejects_conflict():
    with pytest.raises(typer.BadParameter):
        resolve_prefix(RepoInfo("tw93", "waza"), "x", "owner")


def test_target_dir_name():
    assert target_dir_name("skills/think", None) == "think"
    assert target_dir_name("skills/think", "waza") == "waza-think"


def test_map_directory_member():
    assert map_directory_member("health/SKILL.md", None, True, False) == "health/SKILL.md"
    assert map_directory_member("health/SKILL.md", "waza", True, False) == "waza-health/SKILL.md"
    assert map_directory_member("RESOLVER.md", "waza", True, False) == "RESOLVER.md"
    assert map_directory_member("RESOLVER.md", "waza", False, False) is None
    assert map_directory_member("RESOLVER.md", "waza", True, True) == "waza-RESOLVER.md"


def test_candidate_branches():
    assert candidate_branches(None) == ["main", "master"]
    assert candidate_branches("dev") == ["dev"]


def test_detect_remote_kind():
    members = [
        ArchiveMember("skills/think/SKILL.md", False),
        ArchiveMember("README.md", False),
    ]
    assert detect_remote_kind(members, "README.md") == "file"
    assert detect_remote_kind(members, "skills/think") == "dir"
    with pytest.raises(FileNotFoundError):
        detect_remote_kind(members, "missing")


def test_build_plan_for_dir_keeps_local_path_as_root(tmp_path):
    plan = build_plan("tools-plugin/skills/jq-json-processing", tmp_path / "skills", "laurigates", "dir")
    assert plan.is_file is False
    assert plan.source_prefix == "tools-plugin/skills/jq-json-processing/"
    assert plan.target_root == tmp_path / "skills"
    assert plan.prefix == "laurigates"
    assert plan.include_top_files is False
    assert plan.prefix_top_files is False


def test_build_plan_for_file_to_directory(tmp_path):
    target_dir = tmp_path / "out"
    target_dir.mkdir()
    plan = build_plan("skills/think/SKILL.md", target_dir, "waza", "file")
    assert plan.is_file is True
    assert plan.target_file == target_dir / "SKILL.md"


def test_build_plan_for_file_to_explicit_file(tmp_path):
    plan = build_plan("skills/think/SKILL.md", tmp_path / "think.md", "waza", "file")
    assert plan.target_file == tmp_path / "think.md"


def _write_test_zip(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("waza-main/skills/health/SKILL.md", "health")
        zf.writestr("waza-main/skills/think/SKILL.md", "think")
        zf.writestr("waza-main/skills/think/assets/a.txt", "asset")
        zf.writestr("waza-main/skills/RESOLVER.md", "resolver")
        zf.writestr("waza-main/README.md", "readme")


def test_extract_remote_directory_with_prefix_and_top_files(tmp_path):
    zip_path = tmp_path / "repo.zip"
    _write_test_zip(zip_path)
    plan = build_plan("skills", tmp_path / "skills", "waza", "dir", include_top_files=True)

    count, target = extract_remote_path(zip_path, plan)

    assert count == 4
    assert target == tmp_path / "skills"
    assert (target / "RESOLVER.md").read_text() == "resolver"
    assert (target / "waza-health" / "SKILL.md").read_text() == "health"
    assert (target / "waza-think" / "SKILL.md").read_text() == "think"
    assert (target / "waza-think" / "assets" / "a.txt").read_text() == "asset"


def test_extract_remote_directory_skips_top_files_by_default(tmp_path):
    zip_path = tmp_path / "repo.zip"
    _write_test_zip(zip_path)
    plan = build_plan("skills", tmp_path / "skills", "waza", "dir")

    count, target = extract_remote_path(zip_path, plan)

    assert count == 3
    assert target == tmp_path / "skills"
    assert not (target / "RESOLVER.md").exists()
    assert (target / "waza-health" / "SKILL.md").read_text() == "health"
    assert (target / "waza-think" / "SKILL.md").read_text() == "think"


def test_extract_remote_directory_can_prefix_top_files(tmp_path):
    zip_path = tmp_path / "repo.zip"
    _write_test_zip(zip_path)
    plan = build_plan("skills", tmp_path / "skills", "waza", "dir", include_top_files=True, prefix_top_files=True)

    count, target = extract_remote_path(zip_path, plan)

    assert count == 4
    assert target == tmp_path / "skills"
    assert (target / "waza-RESOLVER.md").read_text() == "resolver"
    assert (target / "waza-health" / "SKILL.md").read_text() == "health"


def test_extract_remote_file(tmp_path):
    zip_path = tmp_path / "repo.zip"
    _write_test_zip(zip_path)
    plan = build_plan("README.md", tmp_path / "README-waza.md", None, "file")

    count, target = extract_remote_path(zip_path, plan)

    assert count == 1
    assert target == tmp_path / "README-waza.md"
    assert target.read_text() == "readme"


def test_download_path_orchestrates_archive_flow(monkeypatch, tmp_path):
    def fake_download_archive(repo, branch, dest, token):
        assert repo == RepoInfo("tw93", "waza")
        assert branch == "main"
        assert token is None
        _write_test_zip(dest)

    monkeypatch.setattr(git_download, "download_archive", fake_download_archive)

    count, target, branch = download_path("tw93/waza", "skills", tmp_path / "skills", "main", None, "repo", None)

    assert count == 3
    assert branch == "main"
    assert target == tmp_path / "skills"
    assert not (target / "RESOLVER.md").exists()
    assert (target / "waza-health" / "SKILL.md").read_text() == "health"
    assert (target / "waza-think" / "SKILL.md").read_text() == "think"


def test_download_path_falls_back_to_master(monkeypatch, tmp_path):
    tried: list[str] = []

    def fake_download_archive(repo, branch, dest, token):
        tried.append(branch)
        if branch == "main":
            raise ArchiveNotFoundError("not found")
        _write_test_zip(dest)

    monkeypatch.setattr(git_download, "download_archive", fake_download_archive)

    count, target, branch = download_path("tw93/waza", "skills", tmp_path / "skills", None, None, "repo", None)

    assert tried == ["main", "master"]
    assert count == 3
    assert branch == "master"
    assert target == tmp_path / "skills"
    assert not (target / "RESOLVER.md").exists()
    assert (target / "waza-health" / "SKILL.md").read_text() == "health"


def test_download_path_explicit_branch_does_not_fallback(monkeypatch, tmp_path):
    tried: list[str] = []

    def fake_download_archive(repo, branch, dest, token):
        tried.append(branch)
        raise ArchiveNotFoundError("not found")

    monkeypatch.setattr(git_download, "download_archive", fake_download_archive)

    with pytest.raises(ArchiveNotFoundError):
        download_path("tw93/waza", "skills/think", tmp_path / "skills", "dev", None, "repo", None)
    assert tried == ["dev"]


def test_cli_downloads_with_owner_prefix(monkeypatch, tmp_path):
    def fake_download_archive(repo, branch, dest, token):
        _write_test_zip(dest)

    monkeypatch.setattr(git_download, "download_archive", fake_download_archive)

    result = runner.invoke(git_download.cmd, ["tw93/waza", "skills", str(tmp_path / "skills"), "--prefix-from", "owner"])

    assert result.exit_code == 0, result.output
    assert "downloaded 3 file(s)" in result.output
    assert not (tmp_path / "skills" / "RESOLVER.md").exists()
    assert (tmp_path / "skills" / "tw93-health" / "SKILL.md").read_text() == "health"
    assert (tmp_path / "skills" / "tw93-think" / "SKILL.md").read_text() == "think"


def test_cli_skips_top_files_by_default(monkeypatch, tmp_path):
    def fake_download_archive(repo, branch, dest, token):
        _write_test_zip(dest)

    monkeypatch.setattr(git_download, "download_archive", fake_download_archive)

    result = runner.invoke(git_download.cmd, ["tw93/waza", "skills", str(tmp_path / "skills"), "--prefix-from", "repo"])

    assert result.exit_code == 0, result.output
    assert not (tmp_path / "skills" / "RESOLVER.md").exists()
    assert (tmp_path / "skills" / "waza-health" / "SKILL.md").read_text() == "health"


def test_cli_can_prefix_top_files(monkeypatch, tmp_path):
    def fake_download_archive(repo, branch, dest, token):
        _write_test_zip(dest)

    monkeypatch.setattr(git_download, "download_archive", fake_download_archive)

    result = runner.invoke(git_download.cmd, ["tw93/waza", "skills", str(tmp_path / "skills"), "--prefix-from", "repo", "--top-files", "--prefix-top-files"])

    assert result.exit_code == 0, result.output
    assert (tmp_path / "skills" / "waza-RESOLVER.md").read_text() == "resolver"
    assert (tmp_path / "skills" / "waza-health" / "SKILL.md").read_text() == "health"


def test_cli_rejects_prefix_conflict(tmp_path):
    result = runner.invoke(git_download.cmd, ["tw93/waza", "skills/think", str(tmp_path), "--prefix", "x", "--prefix-from", "owner"])

    assert result.exit_code == 1
    assert "--prefix and --prefix-from cannot be used together" in result.output
