import json
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from ai_assistant.commands import httpx_rfc_cache
from ai_assistant.commands._pth_patch import inspect_python_site

runner = CliRunner()


def test_status_reports_uninstalled_on_empty_dir(tmp_path: Path):
    result = runner.invoke(httpx_rfc_cache.cmd, ["status", "--target", str(tmp_path)])

    assert result.exit_code == 0
    assert "状态: 未安装" in result.output
    assert "目标解释器:" in result.output


def test_install_writes_pth_and_status_reports_installed(tmp_path: Path):
    install_result = runner.invoke(httpx_rfc_cache.cmd, ["install", "--target", str(tmp_path), "--yes"])

    assert install_result.exit_code == 0, install_result.output
    pth = tmp_path / httpx_rfc_cache.PTH_FILENAME
    assert pth.exists()
    content = pth.read_text(encoding="utf-8")
    assert content.startswith("import os; exec(")
    assert "AI_ASSISTANT_HTTPX_RFC_CACHE_DISABLE" in content
    assert "SyncCacheTransport" in content
    assert "AsyncCacheTransport" in content

    status_result = runner.invoke(httpx_rfc_cache.cmd, ["status", "--target", str(tmp_path)])
    assert status_result.exit_code == 0
    assert "状态: 已安装" in status_result.output


def test_install_aborts_when_user_declines_confirmation(tmp_path: Path):
    result = runner.invoke(httpx_rfc_cache.cmd, ["install", "--target", str(tmp_path)], input="n\n")

    assert result.exit_code == 0
    assert "已取消" in result.output
    assert not (tmp_path / httpx_rfc_cache.PTH_FILENAME).exists()


def test_install_overwrites_existing_pth_without_error(tmp_path: Path):
    pth = tmp_path / httpx_rfc_cache.PTH_FILENAME
    pth.write_text("stale content", encoding="utf-8")

    result = runner.invoke(httpx_rfc_cache.cmd, ["install", "--target", str(tmp_path), "--yes"])

    assert result.exit_code == 0
    assert "已覆盖" in result.output
    assert "stale content" not in pth.read_text(encoding="utf-8")


def test_uninstall_removes_pth(tmp_path: Path):
    pth = tmp_path / httpx_rfc_cache.PTH_FILENAME
    pth.write_text("placeholder", encoding="utf-8")

    result = runner.invoke(httpx_rfc_cache.cmd, ["uninstall", "--target", str(tmp_path)])

    assert result.exit_code == 0
    assert "已卸载" in result.output
    assert not pth.exists()


def test_uninstall_missing_pth_errors_without_quiet(tmp_path: Path):
    result = runner.invoke(httpx_rfc_cache.cmd, ["uninstall", "--target", str(tmp_path)])

    assert result.exit_code == 1
    assert "pth 不存在" in result.output


def test_uninstall_quiet_swallows_missing_pth(tmp_path: Path):
    result = runner.invoke(httpx_rfc_cache.cmd, ["uninstall", "--target", str(tmp_path), "--quiet"])

    assert result.exit_code == 0


def test_install_checks_target_python_dependencies(tmp_path: Path):
    venv_dir = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
    python = venv_dir / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")

    result = runner.invoke(
        httpx_rfc_cache.cmd,
        ["install", "--python", str(python), "--target", str(tmp_path), "--yes"],
    )

    assert result.exit_code == 1
    assert "目标解释器缺少依赖" in result.output
    assert "pip install 'hishel[httpx]>=1.3.0'" in result.output
    assert not (tmp_path / httpx_rfc_cache.PTH_FILENAME).exists()


def test_python_site_inspection_preserves_venv_python_path(tmp_path: Path):
    venv_dir = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
    python = venv_dir / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")

    site_info = inspect_python_site(python)

    assert Path(site_info.executable).samefile(python)
    assert venv_dir in site_info.site_packages.parents


def test_runtime_patch_wraps_default_transports_and_preserves_custom_transport(tmp_path: Path):
    script = """
import asyncio
import json
import os

os.environ["AI_ASSISTANT_HTTPX_RFC_CACHE_DIR"] = r"{cache_dir}"

from ai_assistant.commands.httpx_rfc_cache import _PATCH_BODY

exec(_PATCH_BODY)

import httpx
from hishel.httpx import AsyncCacheTransport, SyncCacheTransport

client = httpx.Client()
custom_transport = httpx.HTTPTransport()
custom_client = httpx.Client(transport=custom_transport)
async_client = httpx.AsyncClient()

result = {{
    "sync_wrapped": isinstance(client._transport, SyncCacheTransport),
    "custom_preserved": custom_client._transport is custom_transport,
    "async_wrapped": isinstance(async_client._transport, AsyncCacheTransport),
}}

client.close()
custom_client.close()
asyncio.run(async_client.aclose())

print(json.dumps(result))
""".format(cache_dir=tmp_path)

    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=True)

    assert json.loads(result.stdout) == {
        "sync_wrapped": True,
        "custom_preserved": True,
        "async_wrapped": True,
    }


def test_runtime_disable_env_leaves_default_transport_unwrapped(tmp_path: Path):
    script = """
import json
import os

os.environ["AI_ASSISTANT_HTTPX_RFC_CACHE_DIR"] = r"{cache_dir}"
os.environ["AI_ASSISTANT_HTTPX_RFC_CACHE_DISABLE"] = "1"

from ai_assistant.commands.httpx_rfc_cache import _PATCH_BODY

exec(_PATCH_BODY)

import httpx
from hishel.httpx import SyncCacheTransport

client = httpx.Client()
result = {{"sync_wrapped": isinstance(client._transport, SyncCacheTransport)}}
client.close()

print(json.dumps(result))
""".format(cache_dir=tmp_path)

    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=True)

    assert json.loads(result.stdout) == {"sync_wrapped": False}
    assert list(tmp_path.iterdir()) == []
