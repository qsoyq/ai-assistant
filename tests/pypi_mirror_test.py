"""Tests for pypi-mirror: HTML parsing, filename derivation, async CLI flow."""

from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from ai_assistant.commands import pypi_mirror

runner = CliRunner()


_INDEX_HTML = """<!DOCTYPE html><html><body>
<a href="/simple/foo/">foo</a>
<a href="/simple/bar-baz/">bar-baz</a>
<a href="qux/">qux</a>
</body></html>"""


_FOO_HTML = """<!DOCTYPE html><html><body>
<a href="https://files.example.com/p/foo-1.0.0-py3-none-any.whl#sha256=abc">foo-1.0.0-py3-none-any.whl</a>
<a href="../files/foo-1.0.0.tar.gz#sha256=def">foo-1.0.0.tar.gz</a>
</body></html>"""

_BAR_HTML = """<a href="https://files.example.com/p/bar-baz-2.0.tar.gz">bar-baz-2.0.tar.gz</a>"""


def _make_handler():
    """Tiny PyPI-style server: index + 3 packages, two with files, one empty."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/simple/":
            return httpx.Response(200, text=_INDEX_HTML)
        if path == "/simple/foo/":
            return httpx.Response(200, text=_FOO_HTML)
        if path == "/simple/bar-baz/":
            return httpx.Response(200, text=_BAR_HTML)
        if path == "/simple/qux/":
            return httpx.Response(200, text="")
        if path.endswith(".whl"):
            return httpx.Response(200, content=b"WHEEL_BYTES")
        if path.endswith(".tar.gz"):
            return httpx.Response(200, content=b"SDIST_BYTES")
        return httpx.Response(404)

    return handler


@pytest.fixture
def patched_async_client(monkeypatch):
    """Wrap httpx.AsyncClient so it always uses the in-memory MockTransport."""
    handler = _make_handler()
    real_cls = httpx.AsyncClient

    def factory(**kw):
        kw["transport"] = httpx.MockTransport(handler)
        return real_cls(**kw)

    monkeypatch.setattr(pypi_mirror.httpx, "AsyncClient", factory)
    return handler


def test_parse_anchors_extracts_href_and_text():
    links = pypi_mirror.parse_anchors(_INDEX_HTML)
    assert links == [("/simple/foo/", "foo"), ("/simple/bar-baz/", "bar-baz"), ("qux/", "qux")]


def test_parse_anchors_handles_empty():
    assert pypi_mirror.parse_anchors("") == []


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://files.example.com/p/foo-1.0.0-py3-none-any.whl#sha256=abc", "foo-1.0.0-py3-none-any.whl"),
        ("https://files.example.com/p/some%20name-1.0.tar.gz", "some name-1.0.tar.gz"),
        ("../files/x.whl?token=t", "x.whl"),
        ("https://example.com/", "fallback"),
    ],
)
def test_filename_from_url(url, expected):
    assert pypi_mirror.filename_from_url(url, fallback="fallback") == expected


def test_normalize_index_url_appends_slash():
    assert pypi_mirror._normalize_index_url("https://x/simple") == "https://x/simple/"
    assert pypi_mirror._normalize_index_url("https://x/simple/") == "https://x/simple/"


def test_cli_dry_run_lists_all_files(patched_async_client, tmp_path):
    result = runner.invoke(
        pypi_mirror.cmd,
        ["https://example.com/simple/", "-o", str(tmp_path), "--dry-run"],
    )
    assert result.exit_code == 0, result.output
    assert "foo-1.0.0-py3-none-any.whl" in result.output
    assert "foo-1.0.0.tar.gz" in result.output
    assert "bar-baz-2.0.tar.gz" in result.output
    # nothing actually written
    assert not list(tmp_path.rglob("*.whl"))


def test_cli_downloads_to_per_package_dirs(patched_async_client, tmp_path):
    result = runner.invoke(
        pypi_mirror.cmd,
        ["https://example.com/simple/", "-o", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "foo" / "foo-1.0.0-py3-none-any.whl").read_bytes() == b"WHEEL_BYTES"
    assert (tmp_path / "foo" / "foo-1.0.0.tar.gz").read_bytes() == b"SDIST_BYTES"
    assert (tmp_path / "bar-baz" / "bar-baz-2.0.tar.gz").read_bytes() == b"SDIST_BYTES"


def test_cli_emits_markdown_report_of_downloaded_packages(patched_async_client, tmp_path):
    result = runner.invoke(
        pypi_mirror.cmd,
        ["https://example.com/simple/", "-o", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    assert "## downloaded" in result.output
    assert "- bar-baz" in result.output
    assert "- foo" in result.output
    # individual filenames must NOT appear in the report
    assert "  - foo-1.0.0" not in result.output
    assert "  - bar-baz-2.0" not in result.output


def test_cli_no_markdown_report_when_nothing_downloaded(patched_async_client, tmp_path):
    """Skip-existing run that does no real work shouldn't print the report header."""
    for f in [
        tmp_path / "foo" / "foo-1.0.0-py3-none-any.whl",
        tmp_path / "foo" / "foo-1.0.0.tar.gz",
        tmp_path / "bar-baz" / "bar-baz-2.0.tar.gz",
    ]:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"PRE")
    result = runner.invoke(
        pypi_mirror.cmd,
        ["https://example.com/simple/", "-o", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    assert "nothing to download" in result.output
    assert "## downloaded" not in result.output


def test_format_downloaded_markdown_dedupes_and_sorts_packages():
    tasks = [
        pypi_mirror.FileTask(package="foo", filename="foo-2.tar.gz", url="u"),
        pypi_mirror.FileTask(package="bar", filename="bar-1.whl", url="u"),
        pypi_mirror.FileTask(package="foo", filename="foo-1.whl", url="u"),
    ]
    assert pypi_mirror._format_downloaded_markdown(tasks) == "## downloaded\n- bar\n- foo"


def test_cli_dedupe_skips_existing_files(patched_async_client, tmp_path):
    pre = tmp_path / "foo" / "foo-1.0.0-py3-none-any.whl"
    pre.parent.mkdir(parents=True)
    pre.write_bytes(b"OLD")
    result = runner.invoke(
        pypi_mirror.cmd,
        ["https://example.com/simple/", "-o", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    assert pre.read_bytes() == b"OLD"  # untouched
    assert "skipped as existing" in result.output


def test_cli_force_overwrites_existing(patched_async_client, tmp_path):
    pre = tmp_path / "foo" / "foo-1.0.0-py3-none-any.whl"
    pre.parent.mkdir(parents=True)
    pre.write_bytes(b"OLD")
    result = runner.invoke(
        pypi_mirror.cmd,
        ["https://example.com/simple/", "-o", str(tmp_path), "-f"],
    )
    assert result.exit_code == 0, result.output
    assert pre.read_bytes() == b"WHEEL_BYTES"


def test_cli_max_caps_download_count(patched_async_client, tmp_path):
    result = runner.invoke(
        pypi_mirror.cmd,
        ["https://example.com/simple/", "-o", str(tmp_path), "--max", "1", "--dry-run"],
    )
    assert result.exit_code == 0, result.output
    assert "limiting to first 1" in result.output


def test_cli_filters_packages_case_insensitive(patched_async_client, tmp_path):
    result = runner.invoke(
        pypi_mirror.cmd,
        ["https://example.com/simple/", "-o", str(tmp_path), "--package", "FOO", "--dry-run"],
    )
    assert result.exit_code == 0, result.output
    assert "found 1 package(s)" in result.output
    assert "bar-baz-2.0.tar.gz" not in result.output


def test_cli_requires_both_username_and_password(tmp_path):
    result = runner.invoke(
        pypi_mirror.cmd,
        ["https://example.com/simple/", "-o", str(tmp_path), "-u", "alice"],
    )
    assert result.exit_code != 0
    assert "username" in result.output.lower() or "password" in result.output.lower()


def test_cli_concurrency_option_accepted(patched_async_client, tmp_path):
    result = runner.invoke(
        pypi_mirror.cmd,
        ["https://example.com/simple/", "-o", str(tmp_path), "-c", "4", "--dry-run"],
    )
    assert result.exit_code == 0, result.output


def test_cli_concurrency_must_be_positive(tmp_path):
    result = runner.invoke(
        pypi_mirror.cmd,
        ["https://example.com/simple/", "-o", str(tmp_path), "-c", "0"],
    )
    assert result.exit_code != 0


def test_cli_reports_404_on_index(monkeypatch, tmp_path):
    real_cls = httpx.AsyncClient

    def factory(**kw):
        kw["transport"] = httpx.MockTransport(lambda r: httpx.Response(404))
        return real_cls(**kw)

    monkeypatch.setattr(pypi_mirror.httpx, "AsyncClient", factory)
    result = runner.invoke(
        pypi_mirror.cmd,
        ["https://example.com/simple/", "-o", str(tmp_path)],
    )
    assert result.exit_code != 0
    assert isinstance(result.exception, httpx.HTTPStatusError)


def test_main_module_path_exists():
    assert Path(pypi_mirror.__file__).name == "pypi_mirror.py"
