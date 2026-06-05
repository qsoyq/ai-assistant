"""Download a file or directory from a GitHub repository archive without requiring local git."""

from __future__ import annotations

import posixpath
import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Literal

import httpx
import typer

from ai_assistant.commands import version_callback

helptext = """
从 GitHub 仓库的某个分支下载单个文件或目录到本地路径。

不依赖本地 git / gh 命令, 也不内置 git 客户端; 实现方式是下载 GitHub 分支 zip archive,
再用 Python 标准库只解压 REMOTE_PATH 对应内容。

默认不加前缀。目录下载时, 若指定 --prefix 或 --prefix-from, 会把前缀加到远程目录 basename 前:
- tools-plugin/skills/jq-json-processing -> ./skills/jq-json-processing
- --prefix-from owner                  -> ./skills/tw93-jq-json-processing
- --prefix waza                        -> ./skills/waza-jq-json-processing

使用示例:
- ai-assistant git-download tw93/waza skills ./skills          # 未指定 --branch 时按 main -> master 探测
- ai-assistant git-download tw93/waza skills ./skills --branch main
- ai-assistant git-download tw93/waza skills/think ./skills --prefix-from repo
- ai-assistant git-download tw93/waza skills/think/SKILL.md ./skills/think/SKILL.md
- ai-assistant git-download https://github.com/tw93/waza.git skills ./skills --prefix waza
"""

cmd = typer.Typer(help=helptext, context_settings={"allow_interspersed_args": True})

PrefixFrom = Literal["owner", "repo"]


@dataclass(frozen=True)
class RepoInfo:
    owner: str
    repo: str

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.repo}"


@dataclass(frozen=True)
class ArchiveMember:
    name: str
    is_dir: bool


@dataclass(frozen=True)
class DownloadPlan:
    is_file: bool
    source_prefix: str
    target_root: Path
    target_file: Path | None = None


def parse_github_repo(repo: str) -> RepoInfo:
    """Parse owner/repo or common GitHub URL forms into RepoInfo."""
    value = repo.strip()
    m = re.fullmatch(r"(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?", value)
    if m:
        return RepoInfo(owner=m.group("owner"), repo=m.group("repo"))

    patterns = [
        r"https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/#?]+?)(?:\.git)?/?(?:[#?].*)?",
        r"git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/\s]+?)(?:\.git)?",
        r"ssh://git@github\.com/(?P<owner>[^/]+)/(?P<repo>[^/\s]+?)(?:\.git)?",
    ]
    for pattern in patterns:
        m = re.fullmatch(pattern, value)
        if m:
            return RepoInfo(owner=m.group("owner"), repo=m.group("repo"))
    raise typer.BadParameter("repo must be GitHub owner/repo or github.com URL, e.g. tw93/waza")


def normalize_remote_path(remote_path: str) -> str:
    normalized = posixpath.normpath(remote_path.strip().strip("/"))
    if normalized in ("", "."):
        raise typer.BadParameter("REMOTE_PATH cannot be empty or repository root")
    if normalized.startswith("../") or normalized == ".." or "/../" in normalized:
        raise typer.BadParameter("REMOTE_PATH must stay inside the repository")
    return normalized


def resolve_prefix(repo: RepoInfo, prefix: str | None, prefix_from: PrefixFrom | None) -> str | None:
    if prefix and prefix_from:
        raise typer.BadParameter("--prefix and --prefix-from cannot be used together")
    if prefix is not None:
        clean = prefix.strip().strip("/-")
        if not clean:
            raise typer.BadParameter("--prefix cannot be empty")
        return clean
    if prefix_from == "owner":
        return repo.owner
    if prefix_from == "repo":
        return repo.repo
    if prefix_from is not None:
        raise typer.BadParameter("--prefix-from must be 'owner' or 'repo'")
    return None


def target_dir_name(remote_path: str, prefix: str | None) -> str:
    base = PurePosixPath(remote_path).name
    return f"{prefix}-{base}" if prefix else base


def archive_url(repo: RepoInfo, branch: str) -> str:
    return f"https://github.com/{repo.slug}/archive/refs/heads/{branch}.zip"


def _auth_headers(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


class ArchiveNotFoundError(RuntimeError):
    pass


def download_archive(repo: RepoInfo, branch: str, dest: Path, token: str | None) -> None:
    url = archive_url(repo, branch)
    try:
        with httpx.stream("GET", url, headers=_auth_headers(token), follow_redirects=True, timeout=60) as response:
            if response.status_code == 404:
                raise ArchiveNotFoundError(f"archive not found: {repo.slug}@{branch}")
            response.raise_for_status()
            with dest.open("wb") as f:
                for chunk in response.iter_bytes():
                    f.write(chunk)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"failed to download {url}: {exc}") from exc


def _strip_archive_root(name: str) -> str | None:
    parts = PurePosixPath(name).parts
    if len(parts) <= 1:
        return None
    return "/".join(parts[1:])


def list_archive_members(zip_path: Path) -> list[ArchiveMember]:
    members: list[ArchiveMember] = []
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            rel = _strip_archive_root(info.filename)
            if not rel:
                continue
            members.append(ArchiveMember(name=rel.rstrip("/"), is_dir=info.is_dir()))
    return members


def detect_remote_kind(members: list[ArchiveMember], remote_path: str) -> Literal["file", "dir"]:
    for member in members:
        if member.name == remote_path and not member.is_dir:
            return "file"
    prefix = remote_path.rstrip("/") + "/"
    if any(member.name.startswith(prefix) for member in members):
        return "dir"
    raise FileNotFoundError(f"path not found in archive: {remote_path}")


def build_plan(remote_path: str, local_path: Path, prefix: str | None, kind: Literal["file", "dir"]) -> DownloadPlan:
    if kind == "dir":
        return DownloadPlan(is_file=False, source_prefix=remote_path.rstrip("/") + "/", target_root=local_path / target_dir_name(remote_path, prefix))

    filename = PurePosixPath(remote_path).name
    target = local_path / filename if _looks_like_directory_target(local_path) else local_path
    return DownloadPlan(is_file=True, source_prefix=remote_path, target_root=target.parent, target_file=target)


def _looks_like_directory_target(path: Path) -> bool:
    raw = str(path)
    return path.exists() and path.is_dir() or raw.endswith(("/", "\\"))


def _safe_join(root: Path, rel: str) -> Path:
    candidate = root.joinpath(*PurePosixPath(rel).parts)
    resolved_root = root.resolve(strict=False)
    resolved_candidate = candidate.resolve(strict=False)
    if resolved_candidate != resolved_root and resolved_root not in resolved_candidate.parents:
        raise RuntimeError(f"unsafe archive path: {rel}")
    return candidate


def extract_remote_path(zip_path: Path, plan: DownloadPlan) -> tuple[int, Path]:
    count = 0
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            rel = _strip_archive_root(info.filename)
            if not rel or info.is_dir():
                continue

            if plan.is_file:
                if rel != plan.source_prefix:
                    continue
                assert plan.target_file is not None
                dest = plan.target_file
            else:
                if not rel.startswith(plan.source_prefix):
                    continue
                dest_rel = rel[len(plan.source_prefix) :]
                if not dest_rel:
                    continue
                dest = _safe_join(plan.target_root, dest_rel)

            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, dest.open("wb") as out:
                shutil.copyfileobj(src, out)
            count += 1

    if count == 0:
        raise FileNotFoundError(f"no files extracted for {plan.source_prefix}")
    return count, plan.target_file if plan.is_file and plan.target_file else plan.target_root


def candidate_branches(branch: str | None) -> list[str]:
    return [branch] if branch else ["main", "master"]


def download_path(repo_arg: str, remote_path_arg: str, local_path: Path, branch: str | None, prefix: str | None, prefix_from: PrefixFrom | None, token: str | None) -> tuple[int, Path, str]:
    repo = parse_github_repo(repo_arg)
    remote_path = normalize_remote_path(remote_path_arg)
    actual_prefix = resolve_prefix(repo, prefix, prefix_from)
    branches = candidate_branches(branch)

    with TemporaryDirectory(prefix="ai-assistant-git-download-") as tmp:
        zip_path = Path(tmp) / "repo.zip"
        last_not_found: ArchiveNotFoundError | None = None
        for candidate in branches:
            try:
                download_archive(repo, candidate, zip_path, token)
            except ArchiveNotFoundError as exc:
                last_not_found = exc
                continue
            members = list_archive_members(zip_path)
            kind = detect_remote_kind(members, remote_path)
            plan = build_plan(remote_path, local_path, actual_prefix, kind)
            count, target = extract_remote_path(zip_path, plan)
            return count, target, candidate

    tried = ", ".join(branches)
    raise ArchiveNotFoundError(f"archive not found: {repo.slug} (tried branches: {tried})") from last_not_found


@cmd.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    repo: str = typer.Argument(..., help="GitHub 仓库, 支持 owner/repo 或 https://github.com/owner/repo.git"),
    remote_path: str = typer.Argument(..., help="仓库内要下载的文件或目录路径"),
    local_path: Path = typer.Argument(..., help="本地目标路径。目录下载时作为父目录; 文件下载时可为文件路径或已存在目录"),
    _: bool = typer.Option(False, "--version", "-v", "-V", callback=version_callback),
    branch: str | None = typer.Option(None, "--branch", "-b", help="远程分支名; 不指定时按 main -> master 顺序探测"),
    prefix: str | None = typer.Option(None, "--prefix", help="目录下载时给目标目录名加此前缀, 如 --prefix waza -> waza-think"),
    prefix_from: PrefixFrom | None = typer.Option(None, "--prefix-from", help="目录下载时从 repo 信息推导前缀: owner 或 repo。默认不加前缀"),
    token: str | None = typer.Option(None, "--token", envvar="GITHUB_TOKEN", help="GitHub token, 可用于私有仓库或提高 rate limit; 默认读 GITHUB_TOKEN"),
) -> None:
    """Download REMOTE_PATH from a GitHub branch archive.

    Examples:
    - ai-assistant git-download tw93/waza skills ./skills
    - ai-assistant git-download tw93/waza skills ./skills --branch main
    - ai-assistant git-download tw93/waza skills/think ./skills --prefix-from repo
    - ai-assistant git-download tw93/waza skills/think/SKILL.md ./skills/think/SKILL.md

    This command does not require a local git installation. It downloads the GitHub
    zip archive for the chosen branch and extracts only REMOTE_PATH.
    """
    if ctx.invoked_subcommand is not None:
        return
    try:
        count, target, resolved_branch = download_path(repo, remote_path, local_path, branch, prefix, prefix_from, token)
    except (RuntimeError, FileNotFoundError, zipfile.BadZipFile, typer.BadParameter) as exc:
        typer.echo(f"git-download failed: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"downloaded {count} file(s) from {resolved_branch} to {target}")


if __name__ == "__main__":
    cmd()
