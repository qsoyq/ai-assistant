import json
import site
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import typer


@dataclass(frozen=True)
class PythonSite:
    executable: Path
    site_packages: Path


def build_pth_content(patch_body: str) -> str:
    payload = repr(patch_body)
    return f"import os; exec({payload})\n"


def resolve_python(python: Path | None) -> Path:
    if python is None:
        return Path(sys.executable)

    expanded = python.expanduser()
    resolved = expanded if expanded.is_absolute() else Path.cwd() / expanded
    if not resolved.exists():
        raise typer.BadParameter(f"Python 解释器不存在: {resolved}")
    if not resolved.is_file():
        raise typer.BadParameter(f"Python 解释器路径不是文件: {resolved}")
    return resolved


def _current_site_packages() -> Path:
    candidates: list[str] = []
    try:
        candidates.extend(site.getsitepackages())
    except AttributeError:
        pass
    user_site = site.getusersitepackages()
    if user_site:
        candidates.append(user_site)

    if not candidates:
        raise typer.BadParameter("无法确定 site-packages 路径，请通过 --target 显式指定")

    return Path(candidates[0])


def inspect_python_site(python: Path | None) -> PythonSite:
    resolved_python = resolve_python(python)
    if python is None:
        return PythonSite(executable=resolved_python, site_packages=_current_site_packages())

    script = (
        "import json, site, sys\n"
        "candidates = []\n"
        "try:\n"
        "    candidates.extend(site.getsitepackages())\n"
        "except AttributeError:\n"
        "    pass\n"
        "user_site = site.getusersitepackages()\n"
        "if user_site:\n"
        "    candidates.append(user_site)\n"
        "print(json.dumps({'executable': sys.executable, 'candidates': candidates}))\n"
    )
    result = subprocess.run(
        [str(resolved_python), "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "目标 Python 查询 site-packages 失败"
        raise typer.BadParameter(f"{resolved_python}: {message}")

    data = json.loads(result.stdout)
    candidates = data.get("candidates") or []
    if not candidates:
        raise typer.BadParameter(f"{resolved_python}: 无法确定 site-packages 路径，请通过 --target 显式指定")

    return PythonSite(executable=Path(data["executable"]), site_packages=Path(candidates[0]))


def resolve_target_dir(target: Path | None, python: Path | None = None) -> Path:
    if target is not None:
        resolved = target.expanduser().resolve()
        if not resolved.exists():
            raise typer.BadParameter(f"目标目录不存在: {resolved}")
        if not resolved.is_dir():
            raise typer.BadParameter(f"目标路径不是目录: {resolved}")
        return resolved

    return inspect_python_site(python).site_packages


def check_python_imports(python: Path | None, modules: list[str]) -> list[str]:
    resolved_python = resolve_python(python)
    script = (
        "import importlib.util, json, sys\n"
        "modules = json.loads(sys.argv[1])\n"
        "missing = []\n"
        "for name in modules:\n"
        "    try:\n"
        "        found = importlib.util.find_spec(name) is not None\n"
        "    except (ImportError, AttributeError):\n"
        "        found = False\n"
        "    if not found:\n"
        "        missing.append(name)\n"
        "print(json.dumps(missing))\n"
    )
    result = subprocess.run(
        [str(resolved_python), "-c", script, json.dumps(modules)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "目标 Python 依赖检查失败"
        raise typer.BadParameter(f"{resolved_python}: {message}")
    return list(json.loads(result.stdout))
