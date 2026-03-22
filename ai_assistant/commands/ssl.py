import ipaddress
import re
import subprocess
import tempfile
from pathlib import Path

import typer

from ai_assistant.commands import default_invoke_without_command

_DOMAIN_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")

helptext = """
生成自签名 SSL 证书
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
        result = subprocess.run(command, check=False, capture_output=True, text=True)
    except FileNotFoundError:
        typer.echo("未找到 openssl 命令，请先安装 OpenSSL 后再重试。", err=True)
        raise typer.Exit(code=1) from None
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


if __name__ == "__main__":
    cmd()
