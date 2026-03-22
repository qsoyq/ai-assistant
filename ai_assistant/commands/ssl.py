import ipaddress
import os
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import typer

from ai_assistant.commands import default_invoke_without_command

_DOMAIN_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")

helptext = """
生成和管理 SSL 证书

依赖说明：

- `ssl generate` / `ssl info` 依赖 `openssl`
  - macOS: `brew install openssl@3`
  - Windows: `winget install ShiningLight.OpenSSL.Light` 或 `choco install openssl`
  - Debian / Ubuntu: `sudo apt install openssl`
  - Fedora / RHEL / CentOS: `sudo dnf install openssl`

- `ssl trust` 会按系统使用不同命令
  - macOS: 使用系统自带 `security`，通常无需额外安装
  - Windows: 使用系统自带 `certutil`，通常位于 `C:\\Windows\\System32`
  - Debian / Ubuntu: 依赖 `update-ca-certificates`，可安装 `ca-certificates`
  - Fedora / RHEL / CentOS: 依赖 `update-ca-trust`，可安装 `ca-certificates`

命令执行前会自动检查依赖；如果缺失，会提示安装方法并退出。
"""

cmd = typer.Typer(help=helptext)


def add_default_invoke():
    for _cmd in (cmd,):
        _cmd.callback(invoke_without_command=True)(default_invoke_without_command)


add_default_invoke()


def _split_multi_value_input(raw: str) -> list[str]:
    return [item.strip() for item in re.split(r"[,，]", raw) if item.strip()]


def _prompt_multiple_values(title: str) -> list[str]:
    typer.echo(f"{title}，支持单行输入多个值（用逗号分隔），直接回车结束。")
    values: list[str] = []
    seen: set[str] = set()

    while True:
        raw = input("> ").strip()
        if not raw:
            return values

        for item in _split_multi_value_input(raw):
            if item in seen:
                continue
            seen.add(item)
            values.append(item)


def _is_valid_domain(value: str) -> bool:
    if not value or len(value) > 253:
        return False

    if "*" in value and not value.startswith("*."):
        return False

    normalized_value = value[2:] if value.startswith("*.") else value
    labels = normalized_value.split(".")
    if any(not label for label in labels):
        return False

    if value.startswith("*.") and len(labels) < 2:
        return False

    return all(_DOMAIN_LABEL_PATTERN.fullmatch(label) for label in labels)


def _split_domains_and_ips(values: list[str]) -> tuple[list[str], list[str]]:
    domains: list[str] = []
    ips: list[str] = []
    invalid_values: list[str] = []

    for value in values:
        if _looks_like_ip(value):
            ips.append(value)
        elif _is_valid_domain(value):
            domains.append(value)
        else:
            invalid_values.append(value)

    if invalid_values:
        invalid_values_text = ", ".join(invalid_values)
        raise typer.BadParameter(f"以下输入不是合法的域名或 IP: {invalid_values_text}")

    return domains, ips


def _sanitize_filename(name: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")
    return sanitized or "server"


def _looks_like_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def _validate_domain_or_ip(value: str, field_name: str) -> str:
    if _looks_like_ip(value) or _is_valid_domain(value):
        return value

    raise typer.BadParameter(f"{field_name} 不是合法的域名或 IP: {value}")


def _ensure_subject_alt_names(domains: list[str], ips: list[str], common_name: str) -> tuple[list[str], list[str]]:
    san_domains = list(domains)
    san_ips = list(ips)

    if san_domains or san_ips:
        return san_domains, san_ips

    if _looks_like_ip(common_name):
        san_ips.append(common_name)
    else:
        san_domains.append(common_name)

    return san_domains, san_ips


def _build_openssl_config(common_name: str, san_domains: list[str], san_ips: list[str]) -> str:
    lines = [
        "[req]",
        "default_bits = 2048",
        "prompt = no",
        "default_md = sha256",
        "distinguished_name = req_distinguished_name",
        "x509_extensions = v3_req",
        "",
        "[req_distinguished_name]",
        f"CN = {common_name}",
        "",
        "[v3_req]",
        "basicConstraints = CA:FALSE",
        "keyUsage = digitalSignature, keyEncipherment",
        "extendedKeyUsage = serverAuth",
    ]

    if san_domains or san_ips:
        lines.extend(["subjectAltName = @alt_names", "", "[alt_names]"])
        lines.extend([f"DNS.{index} = {domain}" for index, domain in enumerate(san_domains, start=1)])
        lines.extend([f"IP.{index} = {ip}" for index, ip in enumerate(san_ips, start=1)])

    return "\n".join(lines) + "\n"


def _resolve_output_dir(output_dir: Path | None) -> Path:
    base_dir = output_dir or Path.cwd() / "ssl"
    return base_dir.expanduser().resolve()


def _resolve_cert_path(cert_path: Path) -> Path:
    resolved_cert_path = cert_path.expanduser().resolve()
    if not resolved_cert_path.exists():
        raise typer.BadParameter(f"证书文件不存在: {resolved_cert_path}")

    if not resolved_cert_path.is_file():
        raise typer.BadParameter(f"证书路径不是文件: {resolved_cert_path}")

    if not os.access(resolved_cert_path, os.R_OK):
        raise typer.BadParameter(f"证书文件不可读: {resolved_cert_path}")

    return resolved_cert_path


def _build_missing_command_message(command_name: str) -> str:
    install_guides = {
        "openssl": (
            "未找到命令 `openssl`。\n"
            "可参考以下安装方式：\n"
            "- macOS: `brew install openssl@3`\n"
            "- Windows: `winget install ShiningLight.OpenSSL.Light` 或 `choco install openssl`\n"
            "- Debian / Ubuntu: `sudo apt install openssl`\n"
            "- Fedora / RHEL / CentOS: `sudo dnf install openssl`"
        ),
        "security": ("未找到命令 `security`。\n该命令为 macOS 系统自带工具，通常无需安装。\n如果缺失，请确认当前环境是完整的 macOS，并检查 `/usr/bin/security` 是否存在。"),
        "certutil": ("未找到命令 `certutil`。\n该命令通常为 Windows 系统自带工具，无需单独安装。\n请确认 `C:\\Windows\\System32` 已加入 PATH，或在管理员终端中重试。"),
        "update-ca-certificates": ("未找到命令 `update-ca-certificates`。\n常见安装方式：\n- Debian / Ubuntu: `sudo apt install ca-certificates`\n- Alpine: `apk add ca-certificates`"),
        "update-ca-trust": ("未找到命令 `update-ca-trust`。\n常见安装方式：\n- Fedora / RHEL / CentOS: `sudo dnf install ca-certificates`\n- 较老系统也可能使用: `sudo yum install ca-certificates`"),
    }

    return install_guides.get(command_name, f"未找到命令 `{command_name}`，请先安装后再重试。")


def _require_command(command_name: str) -> None:
    if shutil.which(command_name):
        return

    typer.echo(f"警告：缺少依赖命令 `{command_name}`。", err=True)
    typer.echo(_build_missing_command_message(command_name), err=True)
    raise typer.Exit(code=1)


def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    executable = command[0]
    _require_command(executable)
    return subprocess.run(command, check=False, capture_output=True, text=True)


def _print_command_failure(prefix: str, result: subprocess.CompletedProcess[str]) -> None:
    typer.echo(prefix, err=True)
    if result.stdout.strip():
        typer.echo(result.stdout, err=True)
    if result.stderr.strip():
        typer.echo(result.stderr, err=True)


def _resolve_linux_trust_store() -> tuple[Path, list[str]] | None:
    candidates = (
        (Path("/usr/local/share/ca-certificates"), ["update-ca-certificates"]),
        (Path("/etc/pki/ca-trust/source/anchors"), ["update-ca-trust", "extract"]),
    )

    for directory, refresh_command in candidates:
        if shutil.which(refresh_command[0]):
            return directory, refresh_command

    return None


def _trust_certificate_on_macos(cert_path: Path, scope: str) -> None:
    if scope == "system":
        keychain_path = "/Library/Keychains/System.keychain"
    else:
        keychain_path = str(Path("~/Library/Keychains/login.keychain-db").expanduser())

    command = [
        "security",
        "add-trusted-cert",
        "-d",
        "-r",
        "trustRoot",
        "-k",
        keychain_path,
        str(cert_path),
    ]
    result = _run_command(command)

    if result.returncode != 0:
        _print_command_failure("将证书加入 macOS 信任存储失败。", result)
        if scope == "system":
            typer.echo("提示：写入系统钥匙串通常需要管理员权限，请尝试使用管理员身份运行。", err=True)
        raise typer.Exit(code=result.returncode)


def _trust_certificate_on_windows(cert_path: Path, scope: str) -> None:
    command = ["certutil"]
    if scope == "user":
        command.append("-user")
    command.extend(["-addstore", "Root", str(cert_path)])

    result = _run_command(command)

    if result.returncode != 0:
        _print_command_failure("将证书加入 Windows 信任存储失败。", result)
        if scope == "system":
            typer.echo("提示：写入本机 Root 证书存储通常需要管理员权限，请尝试使用管理员身份运行。", err=True)
        raise typer.Exit(code=result.returncode)


def _trust_certificate_on_linux(cert_path: Path, trust_store: tuple[Path, list[str]] | None = None) -> None:
    trust_store = trust_store or _resolve_linux_trust_store()
    if trust_store is None:
        typer.echo(
            "当前 Linux 发行版暂未识别到受支持的系统证书信任命令。目前支持 `update-ca-certificates` 和 `update-ca-trust extract`。",
            err=True,
        )
        typer.echo(_build_missing_command_message("update-ca-certificates"), err=True)
        typer.echo("", err=True)
        typer.echo(_build_missing_command_message("update-ca-trust"), err=True)
        raise typer.Exit(code=1)

    target_directory, refresh_command = trust_store
    target_path = target_directory / f"{_sanitize_filename(cert_path.stem)}.crt"

    try:
        target_directory.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cert_path, target_path)
    except PermissionError:
        typer.echo("写入 Linux 系统证书目录失败，通常需要 root 权限。", err=True)
        raise typer.Exit(code=1) from None
    except OSError as exc:
        typer.echo(f"复制证书到 Linux 系统证书目录失败: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    result = _run_command(refresh_command)
    if result.returncode != 0:
        _print_command_failure("刷新 Linux 系统证书存储失败。", result)
        raise typer.Exit(code=result.returncode)


@cmd.command()
def info(
    cert_path: Path = typer.Argument(
        ...,
        file_okay=True,
        dir_okay=False,
        resolve_path=False,
        help="证书文件路径",
    ),
):
    """查看证书信息并打印。

    Usage examples::

        # 打印证书详细信息
        ai-assistant ssl info ./ssl/server.crt
    """
    resolved_cert_path = _resolve_cert_path(cert_path)
    command = ["openssl", "x509", "-in", str(resolved_cert_path), "-text", "-noout"]
    result = _run_command(command)

    if result.returncode != 0:
        _print_command_failure(f"读取证书信息失败: {resolved_cert_path}", result)
        raise typer.Exit(code=result.returncode)

    typer.echo(f"证书文件: {resolved_cert_path}")
    typer.echo("")
    typer.echo(result.stdout.rstrip())


@cmd.command()
def generate(
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        "-o",
        help="证书输出目录，默认使用当前目录下的 ssl 子目录",
        file_okay=False,
        dir_okay=True,
        resolve_path=False,
    ),
):
    """通过交互方式生成自签名 SSL 证书。

    Usage examples::

        # 使用默认输出目录（当前目录下的 ssl/）
        ai-assistant ssl generate

        # 指定证书输出目录
        ai-assistant ssl generate --output-dir ./certs
    """
    resolved_output_dir = _resolve_output_dir(output_dir)

    typer.echo("开始生成 SSL 证书，请根据提示输入信息。")
    typer.echo("")

    certificate_name = typer.prompt("证书名称", default="server").strip() or "server"

    typer.echo("")
    subject_alt_names = _prompt_multiple_values("请输入域名或 IP")
    domains, ips = _split_domains_and_ips(subject_alt_names)

    default_common_name = domains[0] if domains else ips[0] if ips else "localhost"
    common_name = typer.prompt("Common Name (CN)", default=default_common_name).strip() or default_common_name
    common_name = _validate_domain_or_ip(common_name, "Common Name (CN)")
    valid_days = typer.prompt("证书有效期（天）", default=3650, type=int)

    if valid_days <= 0:
        raise typer.BadParameter("证书有效期必须大于 0")

    san_domains, san_ips = _ensure_subject_alt_names(domains=domains, ips=ips, common_name=common_name)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    filename = _sanitize_filename(certificate_name)
    key_path = resolved_output_dir / f"{filename}.key"
    cert_path = resolved_output_dir / f"{filename}.crt"

    if key_path.exists() or cert_path.exists():
        should_overwrite = typer.confirm(f"目标文件已存在，是否覆盖？\n- {key_path}\n- {cert_path}", default=False)
        if not should_overwrite:
            raise typer.Exit(code=1)

    openssl_config = _build_openssl_config(common_name=common_name, san_domains=san_domains, san_ips=san_ips)

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".cnf", delete=False) as temp_config_file:
        temp_config_file.write(openssl_config)
        config_path = Path(temp_config_file.name)

    command = [
        "openssl",
        "req",
        "-x509",
        "-nodes",
        "-newkey",
        "rsa:2048",
        "-sha256",
        "-days",
        str(valid_days),
        "-keyout",
        str(key_path),
        "-out",
        str(cert_path),
        "-config",
        str(config_path),
        "-extensions",
        "v3_req",
    ]

    try:
        result = _run_command(command)
    finally:
        config_path.unlink(missing_ok=True)

    if result.returncode != 0:
        if key_path.exists():
            key_path.unlink(missing_ok=True)
        if cert_path.exists():
            cert_path.unlink(missing_ok=True)

        typer.echo("SSL 证书生成失败。", err=True)
        if result.stdout.strip():
            typer.echo(result.stdout, err=True)
        if result.stderr.strip():
            typer.echo(result.stderr, err=True)
        raise typer.Exit(code=result.returncode)

    key_path.chmod(0o600)

    typer.echo("")
    typer.echo("SSL 证书生成成功：")
    typer.echo(f"- 私钥: {key_path}")
    typer.echo(f"- 证书: {cert_path}")
    typer.echo(f"- CN: {common_name}")
    typer.echo(f"- 域名 SAN: {', '.join(san_domains) if san_domains else '无'}")
    typer.echo(f"- IP SAN: {', '.join(san_ips) if san_ips else '无'}")


@cmd.command()
def trust(
    cert_path: Path = typer.Argument(
        ...,
        file_okay=True,
        dir_okay=False,
        resolve_path=False,
        help="需要加入系统信任存储的证书文件路径",
    ),
    scope: str = typer.Option(
        "system",
        "--scope",
        help="证书信任范围：system 表示系统级，user 表示当前用户（Linux 仅支持 system）",
        case_sensitive=False,
    ),
):
    """将证书加入系统信任存储。

    Usage examples::

        # 将证书加入系统信任存储
        ai-assistant ssl trust ./ssl/server.crt

        # 在 macOS / Windows 中仅信任当前用户
        ai-assistant ssl trust ./ssl/server.crt --scope user
    """
    normalized_scope = scope.strip().lower()
    if normalized_scope not in {"system", "user"}:
        raise typer.BadParameter(f"不支持的 scope: {scope}，仅支持 system 或 user")

    resolved_cert_path = _resolve_cert_path(cert_path)
    system_name = platform.system()

    typer.echo(f"检测到系统: {system_name}")
    typer.echo(f"证书文件: {resolved_cert_path}")
    typer.echo(f"信任范围: {normalized_scope}")

    if system_name == "Darwin":
        _trust_certificate_on_macos(resolved_cert_path, normalized_scope)
    elif system_name == "Windows":
        _trust_certificate_on_windows(resolved_cert_path, normalized_scope)
    elif system_name == "Linux":
        if normalized_scope != "system":
            raise typer.BadParameter("Linux 目前仅支持 system 级别的证书信任")
        _trust_certificate_on_linux(resolved_cert_path)
    else:
        typer.echo(f"暂不支持当前操作系统: {system_name}", err=True)
        raise typer.Exit(code=1)

    typer.echo("")
    typer.echo("证书已成功加入系统信任存储。")


if __name__ == "__main__":
    cmd()
