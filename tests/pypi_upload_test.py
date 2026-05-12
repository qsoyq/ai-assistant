"""Tests for pypi-upload: file collection, name parsing, CLI flow with stubbed twine."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from ai_assistant.commands import pypi_upload
from ai_assistant.commands.pypi_upload import UploadResult

runner = CliRunner()


def _touch(p: Path, content: bytes = b"x") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p


# ---------- pure helpers ----------


@pytest.mark.parametrize(
    "name, exts, expected",
    [
        ("foo-1.0-py3-none-any.whl", ["whl", "tar.gz"], True),
        ("foo-1.0.tar.gz", ["whl", "tar.gz"], True),
        ("foo-1.0.tar.gz", ["whl"], False),
        ("FOO-1.0.WHL", ["whl"], True),  # case-insensitive
        ("foo.txt", ["whl", "tar.gz"], False),
        ("readme", ["whl"], False),
        ("foo-1.0.zip", ["zip"], True),
        ("foo-1.0.tar.gz", [".tar.gz"], True),  # leading dot tolerated
    ],
)
def test_matches_extensions(name, exts, expected):
    assert pypi_upload._matches_extensions(Path(name), exts) is expected


def test_collect_files_returns_single_file_verbatim(tmp_path):
    f = _touch(tmp_path / "anything.txt")
    # Single-file path bypasses the extension filter (user named it explicitly).
    assert pypi_upload._collect_files(f, ["whl"]) == [f]


def test_collect_files_walks_directory_with_filter(tmp_path):
    a = _touch(tmp_path / "pkg-a" / "pkg_a-1.0-py3-none-any.whl")
    b = _touch(tmp_path / "pkg-a" / "pkg_a-1.0.tar.gz")
    _touch(tmp_path / "pkg-a" / "README.md")  # filtered out
    c = _touch(tmp_path / "nested" / "pkg-b" / "pkg_b-2.0.tar.gz")
    out = pypi_upload._collect_files(tmp_path, ["whl", "tar.gz"])
    assert out == sorted([a, b, c])


def test_collect_files_returns_empty_for_missing_dir(tmp_path):
    assert pypi_upload._collect_files(tmp_path / "nope", ["whl"]) == []


@pytest.mark.parametrize(
    "filename, expected",
    [
        ("karateclub-1.3.4-py3-none-any.whl", "karateclub"),
        ("mixd_functional-0.1.0.tar.gz", "mixd-functional"),  # canonicalized by packaging
        ("mixd_functional-0.1.0-py3-none-any.whl", "mixd-functional"),
        # garbage filename → fallback heuristic
        ("weird_name_no_version.whl", "weird_name_no_version"),
    ],
)
def test_package_name_from_filename(filename, expected):
    got = pypi_upload._package_name_from_filename(Path(filename))
    # `packaging` canonicalizes underscores to dashes in distribution names; accept either form.
    assert got.replace("_", "-") == expected.replace("_", "-")


def test_format_uploaded_markdown_dedupes_and_sorts():
    results = [
        UploadResult(file=Path("a/x.whl"), package="zeta", ok=True, output=""),
        UploadResult(file=Path("b/x.whl"), package="alpha", ok=True, output=""),
        UploadResult(file=Path("c/x.whl"), package="alpha", ok=True, output=""),
        UploadResult(file=Path("d/x.whl"), package="ignored", ok=False, output="boom"),
    ]
    assert pypi_upload._format_uploaded_markdown(results) == "## uploaded\n- alpha\n- zeta"


def test_format_uploaded_markdown_empty_when_all_failed():
    results = [UploadResult(file=Path("a/x.whl"), package="z", ok=False, output="boom")]
    assert pypi_upload._format_uploaded_markdown(results) == ""


# ---------- CLI flow with stubbed _upload_one ----------


@pytest.fixture
def fake_twine(monkeypatch):
    """Replace _upload_one with a stub. Tests can configure per-file outcomes via
    `fake_twine.fail = {filename, ...}` to mark certain files as failures."""

    class _Stub:
        def __init__(self) -> None:
            self.fail: set[str] = set()
            self.calls: list[dict] = []

    stub = _Stub()

    async def fake_upload_one(file, repository_url, username, password, skip_existing, sem):
        async with sem:
            stub.calls.append(
                {
                    "file": file,
                    "repository_url": repository_url,
                    "username": username,
                    "password": password,
                    "skip_existing": skip_existing,
                }
            )
            ok = file.name not in stub.fail
            return UploadResult(
                file=file,
                package=pypi_upload._package_name_from_filename(file),
                ok=ok,
                output="200 OK" if ok else "400 Bad Request — File already exists.",
            )

    monkeypatch.setattr(pypi_upload, "_upload_one", fake_upload_one)
    return stub


def _make_dist_tree(root: Path) -> list[Path]:
    return [
        _touch(root / "foo" / "foo-1.0-py3-none-any.whl"),
        _touch(root / "foo" / "foo-1.0.tar.gz"),
        _touch(root / "bar" / "bar-2.0.tar.gz"),
    ]


def test_cli_uploads_directory_recursively(fake_twine, tmp_path):
    _make_dist_tree(tmp_path)
    result = runner.invoke(
        pypi_upload.cmd,
        [str(tmp_path), "-r", "https://target/legacy/", "-u", "alice", "-p", "secret"],
    )
    assert result.exit_code == 0, result.output
    assert len(fake_twine.calls) == 3
    assert "matched 3 file(s)" in result.output
    assert "done: 3/3 succeeded" in result.output
    assert "## uploaded" in result.output
    assert "- foo" in result.output
    assert "- bar" in result.output


def test_cli_passes_skip_existing_by_default(fake_twine, tmp_path):
    _make_dist_tree(tmp_path)
    result = runner.invoke(
        pypi_upload.cmd,
        [str(tmp_path), "-r", "https://target/legacy/", "-u", "a", "-p", "b"],
    )
    assert result.exit_code == 0, result.output
    call = fake_twine.calls[0]
    assert call["skip_existing"] is True
    assert call["repository_url"] == "https://target/legacy/"
    assert call["username"] == "a"
    assert call["password"] == "b"


def test_cli_force_drops_skip_existing(fake_twine, tmp_path):
    _make_dist_tree(tmp_path)
    result = runner.invoke(
        pypi_upload.cmd,
        [str(tmp_path), "-r", "https://target/legacy/", "-u", "a", "-p", "b", "-f"],
    )
    assert result.exit_code == 0, result.output
    assert fake_twine.calls[0]["skip_existing"] is False


def test_cli_single_file_uploads_verbatim_ignoring_ext_filter(fake_twine, tmp_path):
    f = _touch(tmp_path / "weird-name.dat")
    result = runner.invoke(
        pypi_upload.cmd,
        [str(f), "-r", "https://target/legacy/", "-u", "a", "-p", "b"],
    )
    assert result.exit_code == 0, result.output
    assert len(fake_twine.calls) == 1
    assert fake_twine.calls[0]["file"] == f


def test_cli_ext_filter_narrows_collection(fake_twine, tmp_path):
    _make_dist_tree(tmp_path)
    result = runner.invoke(
        pypi_upload.cmd,
        [str(tmp_path), "-r", "https://t/", "-u", "a", "-p", "b", "--ext", "whl"],
    )
    assert result.exit_code == 0, result.output
    assert len(fake_twine.calls) == 1
    assert fake_twine.calls[0]["file"].name == "foo-1.0-py3-none-any.whl"


def test_cli_concurrency_option_accepted(fake_twine, tmp_path):
    _make_dist_tree(tmp_path)
    result = runner.invoke(
        pypi_upload.cmd,
        [str(tmp_path), "-r", "https://t/", "-u", "a", "-p", "b", "-c", "2"],
    )
    assert result.exit_code == 0, result.output


def test_cli_max_caps_upload_count(fake_twine, tmp_path):
    _make_dist_tree(tmp_path)  # 3 files
    result = runner.invoke(
        pypi_upload.cmd,
        [str(tmp_path), "-r", "https://t/", "-u", "a", "-p", "b", "--max", "2"],
    )
    assert result.exit_code == 0, result.output
    assert "limiting to first 2 of 3" in result.output
    assert len(fake_twine.calls) == 2
    assert "done: 2/2 succeeded" in result.output


def test_cli_max_no_op_when_below_limit(fake_twine, tmp_path):
    _make_dist_tree(tmp_path)  # 3 files
    result = runner.invoke(
        pypi_upload.cmd,
        [str(tmp_path), "-r", "https://t/", "-u", "a", "-p", "b", "--max", "10"],
    )
    assert result.exit_code == 0, result.output
    assert "limiting to" not in result.output
    assert len(fake_twine.calls) == 3


def test_cli_max_must_be_positive(tmp_path):
    _touch(tmp_path / "foo-1.0.tar.gz")
    result = runner.invoke(
        pypi_upload.cmd,
        [str(tmp_path), "-r", "https://t/", "-u", "a", "-p", "b", "--max", "0"],
    )
    assert result.exit_code != 0


def test_cli_concurrency_must_be_positive(tmp_path):
    _make_dist_tree(tmp_path)
    result = runner.invoke(
        pypi_upload.cmd,
        [str(tmp_path), "-r", "https://t/", "-u", "a", "-p", "b", "-c", "0"],
    )
    assert result.exit_code != 0


def test_cli_failure_returns_nonzero_and_skips_failed_in_report(fake_twine, tmp_path):
    _make_dist_tree(tmp_path)
    fake_twine.fail = {"bar-2.0.tar.gz"}
    result = runner.invoke(
        pypi_upload.cmd,
        [str(tmp_path), "-r", "https://t/", "-u", "a", "-p", "b"],
    )
    assert result.exit_code == 1
    assert "fail bar-2.0.tar.gz" in result.output
    assert "done: 2/3 succeeded" in result.output
    # markdown report lists only successes
    assert "- foo" in result.output
    assert "- bar" not in result.output.split("## uploaded", 1)[1]


def test_cli_missing_path_errors_with_code_2(tmp_path):
    result = runner.invoke(
        pypi_upload.cmd,
        [str(tmp_path / "nope"), "-r", "https://t/", "-u", "a", "-p", "b"],
    )
    assert result.exit_code == 2
    assert "path not found" in result.output


def test_cli_empty_dir_exits_cleanly(fake_twine, tmp_path):
    result = runner.invoke(
        pypi_upload.cmd,
        [str(tmp_path), "-r", "https://t/", "-u", "a", "-p", "b"],
    )
    assert result.exit_code == 0
    assert "matched 0 file(s)" in result.output
    assert "nothing to upload" in result.output
    assert fake_twine.calls == []


def test_cli_requires_both_username_and_password(tmp_path):
    _touch(tmp_path / "foo-1.0.tar.gz")
    result = runner.invoke(
        pypi_upload.cmd,
        [str(tmp_path), "-r", "https://t/", "-u", "alice"],
    )
    assert result.exit_code != 0
    assert "username" in result.output.lower() or "password" in result.output.lower()


def test_cli_repository_url_is_required(tmp_path):
    _touch(tmp_path / "foo-1.0.tar.gz")
    result = runner.invoke(
        pypi_upload.cmd,
        [str(tmp_path), "-u", "a", "-p", "b"],
    )
    assert result.exit_code != 0
    assert "repository" in result.output.lower() or "missing" in result.output.lower()


# ---------- _do_upload_sync: twine library integration ----------


class _FakeResponse:
    def __init__(self, status_code: int, text: str = "", reason: str = ""):
        self.status_code = status_code
        self.text = text
        self.reason = reason or ("OK" if 200 <= status_code < 300 else "Error")


@pytest.fixture
def fake_repository(monkeypatch):
    """Replace twine's Repository + PackageFile + skip_upload so _do_upload_sync
    runs without touching network or actually parsing wheels.

    Configure per test via attributes:
      .pre_check_uploaded -> bool returned by package_is_uploaded
      .upload_response    -> _FakeResponse returned by repo.upload
      .upload_raises      -> Exception raised from repo.upload
      .skip_upload_returns -> bool returned by skip_upload
    """

    class _Cfg:
        pre_check_uploaded: bool = False
        upload_response: _FakeResponse | None = None
        upload_raises: BaseException | None = None
        skip_upload_returns: bool = False
        last_repo_args: tuple | None = None
        closed: bool = False

    cfg = _Cfg()

    class _FakePackageFile:
        @classmethod
        def from_filename(cls, filename, comment):
            inst = cls()
            inst.filename = filename
            return inst

    class _FakeRepository:
        def __init__(self, repository_url, username, password, disable_progress_bar=False):
            cfg.last_repo_args = (repository_url, username, password, disable_progress_bar)

        def package_is_uploaded(self, package, bypass_cache: bool = False):
            return cfg.pre_check_uploaded

        def upload(self, package, max_redirects: int = 5):
            if cfg.upload_raises is not None:
                raise cfg.upload_raises
            assert cfg.upload_response is not None, "test must set upload_response"
            return cfg.upload_response

        def close(self):
            cfg.closed = True

    def _fake_skip_upload(response, skip_existing, package):
        return cfg.skip_upload_returns

    import twine.commands.upload as twine_upload
    import twine.package as twine_package
    import twine.repository as twine_repository

    monkeypatch.setattr(twine_repository, "Repository", _FakeRepository)
    monkeypatch.setattr(twine_package, "PackageFile", _FakePackageFile)
    monkeypatch.setattr(twine_upload, "skip_upload", _fake_skip_upload)
    return cfg


def test_do_upload_sync_success_2xx(fake_repository, tmp_path):
    fake_repository.upload_response = _FakeResponse(200, "OK")
    f = _touch(tmp_path / "foo" / "foo-1.0-py3-none-any.whl")
    r = pypi_upload._do_upload_sync(f, "https://t/", "u", "p", skip_existing=True)
    assert r.ok is True
    assert "200" in r.output
    assert fake_repository.last_repo_args == ("https://t/", "u", "p", True)
    assert fake_repository.closed is True  # repo.close() always called


def test_do_upload_sync_pre_check_skip(fake_repository, tmp_path):
    fake_repository.pre_check_uploaded = True
    f = _touch(tmp_path / "foo-1.0.tar.gz")
    r = pypi_upload._do_upload_sync(f, "https://t/", "u", "p", skip_existing=True)
    assert r.ok is True
    assert "skipped" in r.output and "pre-check" in r.output


@pytest.mark.parametrize(
    "status, body",
    [
        # Nexus pypi-hosted: Disable redeploy. Status 400 + "cannot be updated" — twine misses this.
        (400, "pypi-hosted/packages/foo/1.0/foo-1.0.whl cannot be updated"),
        # Nexus alt wording.
        (400, "Repository does not allow updating assets: pypi-hosted"),
        # Nexus another phrasing seen on some versions.
        (400, "Asset cannot be modified"),
        # GitLab Package Registry.
        (400, "version already exists"),
        # JFrog Artifactory typically uses 403.
        (403, "Not enough permissions to overwrite artifact"),
    ],
)
def test_looks_like_already_exists_recognizes_extra_patterns(status, body):
    """Our extension layer covers what twine 6.x's skip_upload misses."""
    assert pypi_upload._looks_like_already_exists(_FakeResponse(status, body)) is True


@pytest.mark.parametrize(
    "status, body",
    [
        (200, "ok"),  # success
        (500, "boom"),  # server error
        (404, "not found"),  # wrong endpoint
        (400, "bad metadata"),  # genuine 400 unrelated to existence
        (403, "auth failed"),  # auth, not overwrite
    ],
)
def test_looks_like_already_exists_does_not_overreach(status, body):
    assert pypi_upload._looks_like_already_exists(_FakeResponse(status, body)) is False


def test_do_upload_sync_recognizes_nexus_cannot_be_updated(fake_repository, tmp_path):
    """End-to-end check on the exact response shape the user observed in the wild."""
    nexus_html_body = "<!DOCTYPE html><html><body>pypi-hosted/packages/analyze-data-parser/0.1.0/analyze_data_parser-0.1.0-py3-none-any.whl cannot be updated</body></html>"
    fake_repository.upload_response = _FakeResponse(400, nexus_html_body, "Bad Request")
    fake_repository.skip_upload_returns = False  # twine's matcher misses this case
    f = _touch(tmp_path / "analyze_data_parser-0.1.0-py3-none-any.whl")
    r = pypi_upload._do_upload_sync(f, "http://nexus/repository/pypi-hosted/", "u", "p", skip_existing=True)
    assert r.ok is True
    assert "skipped" in r.output and "400" in r.output


def test_do_upload_sync_post_error_recognized_as_skip(fake_repository, tmp_path):
    fake_repository.upload_response = _FakeResponse(400, "File already exists.", "Bad Request")
    fake_repository.skip_upload_returns = True
    f = _touch(tmp_path / "foo-1.0.tar.gz")
    r = pypi_upload._do_upload_sync(f, "https://t/", "u", "p", skip_existing=True)
    assert r.ok is True
    assert "skipped" in r.output and "400" in r.output


def test_do_upload_sync_post_error_unknown_is_failure(fake_repository, tmp_path):
    fake_repository.upload_response = _FakeResponse(500, "boom", "Server Error")
    fake_repository.skip_upload_returns = False
    f = _touch(tmp_path / "foo-1.0.tar.gz")
    r = pypi_upload._do_upload_sync(f, "https://t/", "u", "p", skip_existing=True)
    assert r.ok is False
    assert "500" in r.output and "boom" in r.output


def test_do_upload_sync_force_ignores_skip_logic(fake_repository, tmp_path):
    """With force=True (skip_existing=False) the pre-check is bypassed AND a 4xx
    duplicate-file response counts as a real failure."""
    fake_repository.pre_check_uploaded = True  # would skip if not for force
    fake_repository.upload_response = _FakeResponse(400, "File already exists.", "Bad Request")
    fake_repository.skip_upload_returns = True  # would skip if not for force
    f = _touch(tmp_path / "foo-1.0.tar.gz")
    r = pypi_upload._do_upload_sync(f, "https://t/", "u", "p", skip_existing=False)
    assert r.ok is False
    assert "400" in r.output


def test_do_upload_sync_network_error_is_failure(fake_repository, tmp_path):
    fake_repository.upload_raises = ConnectionError("dns is down")
    f = _touch(tmp_path / "foo-1.0.tar.gz")
    r = pypi_upload._do_upload_sync(f, "https://t/", "u", "p", skip_existing=True)
    assert r.ok is False
    assert "network error" in r.output and "dns is down" in r.output
    assert fake_repository.closed is True
