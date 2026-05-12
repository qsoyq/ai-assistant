"""Upload local wheel/sdist files to a PyPI-compatible repository via twine's library API."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import typer
from tqdm.asyncio import tqdm

from ai_assistant.commands import version_callback

helptext = """
把本地的 whl / tar.gz 上传到指定仓库 (asyncio 并发, 直接调用 twine 库内 API)。

PATH 是文件或目录: 文件直接上传; 目录会按 --ext 递归筛选后批量上传。
默认带 --skip-existing, 服务器回 "已存在" 错误时算成功跳过; -f / --force 取消该行为。
鉴权与 twine 一致: -u/-p 走 HTTP Basic。

示例:
- ai-assistant pypi-upload ./dist/pypi -r https://target.example.com/legacy/ -u alice -p s3cret
- ai-assistant pypi-upload ./dist/pypi/foo -r https://target.example.com/legacy/ -c 8
- ai-assistant pypi-upload ./mypkg-1.0.whl -r https://target.example.com/legacy/ -f
- ai-assistant pypi-upload ./dist -r https://target.example.com/legacy/ --ext whl
"""

cmd = typer.Typer(help=helptext, context_settings={"allow_interspersed_args": True})


@dataclass(frozen=True)
class UploadResult:
    file: Path
    package: str
    ok: bool
    output: str  # twine stdout/stderr (combined), kept for failure diagnostics


def _matches_extensions(path: Path, exts: list[str]) -> bool:
    """Suffix match. Handles compound extensions like `tar.gz` correctly because we
    compare against the full lowercased filename, not just `path.suffix`."""
    name = path.name.lower()
    return any(name.endswith("." + e.lower().lstrip(".")) for e in exts)


def _collect_files(root: Path, exts: list[str]) -> list[Path]:
    """A file path is taken verbatim (extension filter does not apply — user named it).
    A directory is walked recursively and filtered by `exts`."""
    if root.is_file():
        return [root]
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob("*") if p.is_file() and _matches_extensions(p, exts))


def _package_name_from_filename(path: Path) -> str:
    """Best-effort package name. Use `packaging` parsers (provided transitively by twine)
    for canonical correctness; fall back to a heuristic on parse failure."""
    name = path.name
    try:
        if name.lower().endswith(".whl"):
            from packaging.utils import parse_wheel_filename

            return str(parse_wheel_filename(name)[0])
        if name.lower().endswith(".tar.gz") or name.lower().endswith(".zip"):
            from packaging.utils import parse_sdist_filename

            return str(parse_sdist_filename(name)[0])
    except Exception:
        pass
    # Fallback: take everything before the first `-<digit>` (version usually starts with a digit).
    import re

    stem = re.sub(r"\.(whl|tar\.gz|zip)$", "", name, flags=re.IGNORECASE)
    m = re.match(r"^(.*?)-\d", stem)
    return m.group(1) if m else stem


# Server-specific "file already exists" patterns that twine 6.x's `skip_upload`
# does NOT recognize. Each entry is a lowercase substring searched in the
# response body + reason. Extend this list when a new private-index server is
# discovered to use a different wording.
_EXTRA_ALREADY_EXISTS_PATTERNS = (
    "cannot be updated",  # Nexus pypi-hosted, Deployment Policy = Disable redeploy
    "cannot be modified",  # Nexus, alt wording on some versions
    "does not allow updating",  # Nexus, "Repository does not allow updating assets: ..."
    "version already exists",  # GitLab Package Registry
    "overwrite artifact",  # JFrog Artifactory (typically 403)
)


def _looks_like_already_exists(response) -> bool:
    """Best-effort fallback for servers whose 'file already exists' wording
    twine doesn't yet recognize. Conservative: only fires on the status codes
    these servers actually use for duplicates (400 / 403 / 409)."""
    if response.status_code not in (400, 403, 409):
        return False
    haystack = ((getattr(response, "text", "") or "") + " " + (getattr(response, "reason", "") or "")).lower()
    return any(p in haystack for p in _EXTRA_ALREADY_EXISTS_PATTERNS)


def _do_upload_sync(
    file: Path,
    repository_url: str,
    username: str | None,
    password: str | None,
    skip_existing: bool,
) -> UploadResult:
    """Synchronous single-file upload using twine's library API. Designed to be
    handed off to `asyncio.to_thread` — twine/requests are blocking, so each call
    occupies one worker thread for the duration of the HTTP transfer.

    A fresh Repository per call avoids any concern about session/connection-pool
    sharing across worker threads."""
    from twine.commands.upload import skip_upload
    from twine.exceptions import TwineException
    from twine.package import PackageFile
    from twine.repository import Repository

    package_label = _package_name_from_filename(file)
    try:
        package = PackageFile.from_filename(str(file), comment=None)
    except (TwineException, OSError, ValueError) as exc:
        return UploadResult(file=file, package=package_label, ok=False, output=f"package error: {exc}")

    repository = Repository(repository_url, username, password, disable_progress_bar=True)
    try:
        if skip_existing and repository.package_is_uploaded(package):
            return UploadResult(file=file, package=package_label, ok=True, output="skipped: already on server (pre-check)")
        try:
            response = repository.upload(package)
        except Exception as exc:
            return UploadResult(file=file, package=package_label, ok=False, output=f"network error: {type(exc).__name__}: {exc}")

        status = f"{response.status_code} {response.reason}"
        if 200 <= response.status_code < 300:
            return UploadResult(file=file, package=package_label, ok=True, output=status)
        if skip_existing and (skip_upload(response, True, package) or _looks_like_already_exists(response)):
            return UploadResult(file=file, package=package_label, ok=True, output=f"skipped: {status}")
        body = (response.text or "").strip().replace("\n", " ")[:300]
        return UploadResult(file=file, package=package_label, ok=False, output=f"{status} — {body}")
    finally:
        repository.close()


async def _upload_one(
    file: Path,
    repository_url: str,
    username: str | None,
    password: str | None,
    skip_existing: bool,
    sem: asyncio.Semaphore,
) -> UploadResult:
    """asyncio façade: gate on the semaphore, then push the blocking twine call to
    a worker thread. The semaphore bound = max concurrent threads in flight."""
    async with sem:
        return await asyncio.to_thread(_do_upload_sync, file, repository_url, username, password, skip_existing)


def _format_uploaded_markdown(results: list[UploadResult]) -> str:
    packages = sorted({r.package for r in results if r.ok})
    if not packages:
        return ""
    return "\n".join(["## uploaded", *(f"- {p}" for p in packages)])


async def _run(
    *,
    files: list[Path],
    repository_url: str,
    username: str | None,
    password: str | None,
    concurrency: int,
    force: bool,
) -> int:
    """Returns the suggested process exit code (0 if every upload succeeded, 1 otherwise)."""
    skip_existing = not force
    sem = asyncio.Semaphore(concurrency)
    coros = [_upload_one(f, repository_url, username, password, skip_existing, sem) for f in files]
    results: list[UploadResult] = []
    for coro in tqdm.as_completed(coros, desc="upload", unit="file", total=len(coros)):
        r: UploadResult = await coro
        results.append(r)
        if not r.ok:
            tqdm.write(f"  ! fail {r.file.name}: {r.output}")

    ok_count = sum(1 for r in results if r.ok)
    tqdm.write(f"done: {ok_count}/{len(results)} succeeded")
    md = _format_uploaded_markdown(results)
    if md:
        tqdm.write("")
        tqdm.write(md)
    return 0 if ok_count == len(results) else 1


@cmd.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="文件或目录 (目录会按 --ext 递归筛选)"),
    _: bool = typer.Option(False, "--version", "-v", "-V", callback=version_callback),
    repository_url: str = typer.Option(
        ...,
        "--repository-url",
        "-r",
        help="目标仓库 URL, 例如 https://target.example.com/legacy/ (必填, 避免误传 PyPI)",
    ),
    username: str | None = typer.Option(None, "--username", "-u", help="HTTP Basic 用户名"),
    password: str | None = typer.Option(None, "--password", "-p", help="HTTP Basic 密码"),
    concurrency: int = typer.Option(4, "--concurrency", "-c", min=1, help="并发上限, 默认 4"),
    max_files: int | None = typer.Option(None, "--max", min=1, help="本次最多上传 N 个文件; 默认不限"),
    force: bool = typer.Option(False, "--force", "-f", help="去掉 --skip-existing, 服务器对重复文件会报错"),
    ext: list[str] = typer.Option(
        ["whl", "tar.gz"],
        "--ext",
        help="目录模式下的文件后缀白名单, 可多次传; 默认 whl 和 tar.gz",
    ),
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    if (username is None) != (password is None):
        raise typer.BadParameter("--username 与 --password 必须同时提供")

    if not path.exists():
        typer.echo(f"path not found: {path}", err=True)
        raise typer.Exit(2)

    files = _collect_files(path, ext)
    typer.echo(f"input: {path.resolve()}")
    typer.echo(f"target: {repository_url}")
    typer.echo(f"matched {len(files)} file(s) (ext={ext})")
    if max_files is not None and len(files) > max_files:
        typer.echo(f"limiting to first {max_files} of {len(files)} file(s) (--max)")
        files = files[:max_files]
    if not files:
        typer.echo("nothing to upload.")
        return

    rc = asyncio.run(
        _run(
            files=files,
            repository_url=repository_url,
            username=username,
            password=password,
            concurrency=concurrency,
            force=force,
        )
    )
    if rc != 0:
        raise typer.Exit(rc)


if __name__ == "__main__":
    cmd()
