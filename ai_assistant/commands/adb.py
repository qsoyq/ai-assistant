"""Manage adb server: force restart in -a mode (listen on 0.0.0.0)."""

from __future__ import annotations

import os
import shutil
import subprocess
import time

import psutil
import typer

from ai_assistant.commands import make_typer

helptext = """
管理 adb server。

子命令:
  restart-all  强制重启 adb server, 监听 0.0.0.0:5037

restart-all 解决的问题:
  - adb devices 阻塞 / 超时
  - adb server 被 client 隐式拉起后只绑 127.0.0.1, 远端连不上

流程:
  1. adb devices 探活 (超时即视为卡死)
  2. 若已正确绑 0.0.0.0:5037 则跳过 (除非 --force)
  3. 强杀所有 adb 进程 (psutil, 跨平台)
  4. adb -a -P 5037 start-server
  5. psutil 校验 0.0.0.0:5037 / :: 处于 LISTEN

跨平台:
  - Windows / macOS / Linux 均可; 依赖 adb 已加入 PATH
  - 进程内执行 adb 时会清理 ANDROID_ADB_SERVER_ADDRESS, 避免 client 连到错地址
"""

cmd = make_typer(helptext)

ADB_PORT = 5037
# 监听全网卡时 socket bind 的 IP: IPv4 = 0.0.0.0, IPv6 = ::
_ALL_INTERFACE_IPS = ("0.0.0.0", "::")
_ADB_PROC_NAMES = {"adb", "adb.exe"}


def _which_adb() -> str:
    adb = shutil.which("adb")
    if not adb:
        typer.echo("未找到 adb, 请确认 adb 已加入 PATH", err=True)
        raise typer.Exit(2)
    return adb


def _clean_env() -> dict[str, str]:
    """ANDROID_ADB_SERVER_ADDRESS 是 client 用来连 server 的地址, 设错会让所有 adb 调用阻塞。
    在本命令的所有子进程里都清掉它, 强制走默认 127.0.0.1。"""
    env = os.environ.copy()
    env.pop("ANDROID_ADB_SERVER_ADDRESS", None)
    return env


def _indent(text: str, prefix: str = "    ") -> str:
    return "\n".join(prefix + line for line in text.splitlines() if line)


def _adb_devices_ok(adb: str, port: int, timeout: float) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            [adb, "-P", str(port), "devices"],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_clean_env(),
        )
    except subprocess.TimeoutExpired:
        return False, f"adb devices 超时 (>{timeout}s), server 可能卡死"
    if result.returncode != 0:
        msg = (result.stderr or result.stdout).strip() or f"rc={result.returncode}"
        return False, f"adb devices 失败: {msg}"
    return True, result.stdout.strip()


def _iter_adb_procs():
    for p in psutil.process_iter(["name"]):
        try:
            name = (p.info.get("name") or "").lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if name in _ADB_PROC_NAMES:
            yield p


def _force_kill_adb(wait_timeout: float = 2.0) -> list[str]:
    """强杀所有 adb 进程, 返回日志行。Windows 上系统进程可能 AccessDenied, 跳过即可。"""
    log: list[str] = []
    targets: list[psutil.Process] = []
    for p in _iter_adb_procs():
        try:
            p.kill()
            targets.append(p)
            log.append(f"kill pid={p.pid} name={p.info.get('name')}")
        except psutil.NoSuchProcess:
            pass
        except psutil.AccessDenied as exc:
            log.append(f"kill pid={p.pid} AccessDenied: {exc}")

    if not targets:
        log.append("no adb process found")
        return log

    # 确认真死, 而不是依赖 sleep
    gone, alive = psutil.wait_procs(targets, timeout=wait_timeout)
    for p in gone:
        log.append(f"reaped pid={p.pid}")
    for p in alive:
        log.append(f"WARN pid={p.pid} 未在 {wait_timeout}s 内退出")
    return log


def _start_server_all(adb: str, port: int, timeout: float = 15.0) -> tuple[bool, str]:
    """以 -a 模式拉起 adb server (监听全网卡)。"""
    try:
        result = subprocess.run(
            [adb, "-a", "-P", str(port), "start-server"],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_clean_env(),
        )
    except subprocess.TimeoutExpired:
        return False, f"adb -a start-server 超时 (>{timeout}s)"
    out = (result.stdout + result.stderr).strip()
    if result.returncode != 0:
        return False, out or f"rc={result.returncode}"
    return True, out or "started"


def _adb_listen_conns(port: int) -> list[tuple[int, str, int]]:
    """返回 [(pid, laddr_ip, laddr_port)], 仅当前用户名下、name=adb 的 LISTEN socket。

    走"按进程查"而不是全局 psutil.net_connections(): macOS 上后者对所有用户都
    AccessDenied (需要 root); adb 是当前用户拉起的, 按 pid 查我们自己的进程
    永远有权限。
    """
    out: list[tuple[int, str, int]] = []
    for p in _iter_adb_procs():
        try:
            conns = p.net_connections(kind="inet")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        for c in conns:
            if c.status != psutil.CONN_LISTEN or not c.laddr or c.laddr.port != port:
                continue
            out.append((p.pid, c.laddr.ip, c.laddr.port))
    return out


def _verify_listen_all(port: int) -> tuple[bool, list[str]]:
    """检查 adb 是否在 0.0.0.0 / :: 上 LISTEN。返回 (是否绑全网卡, 人类可读行)。"""
    conns = _adb_listen_conns(port)
    lines = [f"pid={pid} {ip}:{lport} LISTEN" for pid, ip, lport in conns]
    is_all = any(ip in _ALL_INTERFACE_IPS for _, ip, _ in conns)
    return is_all, lines


@cmd.command("restart-all")
def restart_all(
    port: int = typer.Option(ADB_PORT, "--port", "-P", help="adb server 端口 (探测 + 启动均使用)"),
    timeout: float = typer.Option(5.0, "--timeout", "-t", help="adb devices 探活超时 (秒)"),
    force: bool = typer.Option(False, "--force", "-f", help="无视当前状态强制重启"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="打印 adb 详细输出"),
) -> None:
    """强制重启 adb server, 以 -a 模式监听 0.0.0.0:<port>。"""
    adb = _which_adb()
    typer.echo(f"adb: {adb}  port: {port}")

    # 1. probe
    typer.echo(f"\n[1/4] adb -P {port} devices (timeout={timeout}s)")
    devices_ok, devices_msg = _adb_devices_ok(adb, port, timeout)
    if devices_ok:
        typer.echo("  [OK] adb devices 正常响应")
        if verbose:
            typer.echo(_indent(devices_msg))
    else:
        typer.echo(f"  [!!] {devices_msg}")

    is_all, listen_lines = _verify_listen_all(port)
    if listen_lines:
        typer.echo(f"  当前 :{port} LISTEN:")
        for line in listen_lines:
            typer.echo(_indent(line))
    elif verbose:
        typer.echo(f"  当前 :{port} 无 LISTEN socket")

    if devices_ok and is_all and not force:
        typer.echo(f"\n[OK] adb server 已绑 0.0.0.0:{port}, 无需重启 (用 --force 强制)")
        raise typer.Exit(0)

    # 2. force kill
    typer.echo("\n[2/4] 强杀 adb 进程")
    for line in _force_kill_adb():
        typer.echo(_indent(line))

    # 3. start server with -a
    typer.echo(f"\n[3/4] adb -a -P {port} start-server")
    started, start_msg = _start_server_all(adb, port)
    if start_msg:
        typer.echo(_indent(start_msg))
    if not started:
        typer.echo("  [FAIL] 启动失败", err=True)
        raise typer.Exit(1)
    typer.echo("  [OK] start-server 返回成功")

    # 4. verify (poll up to 3s, server bind may lag slightly after start-server 返回)
    typer.echo(f"\n[4/4] 校验 0.0.0.0:{port} LISTEN")
    is_all = False
    listen_lines = []
    for _ in range(6):
        is_all, listen_lines = _verify_listen_all(port)
        if is_all:
            break
        time.sleep(0.5)

    for line in listen_lines:
        typer.echo(_indent(line))

    if not is_all:
        typer.echo(f"\n[FAIL] 未在 0.0.0.0:{port} 检测到 LISTEN", err=True)
        raise typer.Exit(1)

    devices_ok, devices_msg = _adb_devices_ok(adb, port, timeout)
    if not devices_ok:
        typer.echo(f"\n[WARN] 端口已绑, 但 adb devices 仍异常: {devices_msg}", err=True)
        raise typer.Exit(1)

    typer.echo(f"\n[OK] adb server 已重启, 监听 0.0.0.0:{port}")
    if verbose:
        typer.echo(_indent(devices_msg))


if __name__ == "__main__":
    cmd()
