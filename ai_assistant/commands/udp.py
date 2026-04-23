import socket
from datetime import datetime

import rich
import typer

from ai_assistant.commands import default_invoke_without_command

helptext = """
UDP 端口可达性验证工具
"""

cmd = typer.Typer(help=helptext)


def add_default_invoke():
    for _cmd in (cmd,):
        _cmd.callback(invoke_without_command=True)(default_invoke_without_command)


add_default_invoke()


def _now() -> str:
    return datetime.now().strftime(r"%Y-%m-%d %H:%M:%S")


def _echo(msg: str):
    rich.print(f"[{_now()}] {msg}")


@cmd.command()
def client(
    message: str = typer.Argument("hello world", help="发送的消息"),
    host: str = typer.Option("127.0.0.1", "-h", "--host", help="服务端地址"),
    port: int = typer.Option(8000, "-p", "--port", help="服务端端口"),
    timeout: float = typer.Option(60, "-t", "--timeout", help="接收超时, 秒"),
):
    """创建 UDP 客户端, 发送消息并监听回复

    使用示例:
    - `ai-assistant udp client "ping" -h 1.2.3.4 -p 8000`
    """
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    if timeout:
        client_socket.settimeout(timeout)
    try:
        _echo(f"发送到 {host}:{port}: {message}")
        client_socket.sendto(message.encode(), (host, port))
        data, addr = client_socket.recvfrom(1024)
        _echo(f"接收到来自 {addr} 的回显: {data.decode()}")
    except socket.timeout:
        _echo("接收响应超时")
        raise typer.Exit(1)
    finally:
        client_socket.close()


@cmd.command("echo-server")
def echo_server(
    host: str = typer.Option("0.0.0.0", "-h", "--host", help="监听地址"),
    port: int = typer.Option(8000, "-p", "--port", help="监听端口"),
):
    """启动 UDP Echo 服务器, 收到的内容原样回发

    使用示例:
    - `ai-assistant udp echo-server -p 8000`
    """
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.bind((host, port))
    _echo(f"UDP Echo Server 启动, 监听 {host}:{port}")

    try:
        while True:
            data, addr = server_socket.recvfrom(1024)
            _echo(f"接收到来自 {addr} 的数据: {data.decode()}")
            server_socket.sendto(data, addr)
    except KeyboardInterrupt:
        _echo("服务器已停止")
    finally:
        server_socket.close()


if __name__ == "__main__":
    cmd()
