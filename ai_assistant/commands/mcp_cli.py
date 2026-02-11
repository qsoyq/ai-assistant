import json

import httpx
import typer

from ai_assistant.commands import default_invoke_without_command

helptext = """
MCP Client
"""

cmd = typer.Typer(help=helptext)


def add_default_invoke():
    for _cmd in (cmd,):
        _cmd.callback(invoke_without_command=True)(default_invoke_without_command)


add_default_invoke()


@cmd.command()
def tools(
    endpoint: str = typer.Argument(..., help="MCP 服务端点"),
):
    """以 HTTP Post JSON-RPC 请求方式调用查询可用工具列表

    当前仅支持 streamable MCP 服务端点.
    """

    # 构造 JSON-RPC 请求
    payload = {"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 1}

    try:
        # 发送 HTTP POST 请求
        with httpx.Client() as client:
            response = client.post(endpoint, json=payload, headers={"Content-Type": "application/json"}, timeout=30.0)
            response.raise_for_status()

            # 解析响应
            result = response.json()

            # 检查是否有错误
            if "error" in result:
                typer.echo(f"错误: {result['error']}", err=True)
                raise typer.Exit(code=1)

            # 获取工具列表
            tools_list = result.get("result", {}).get("tools", [])

            # 输出工具列表
            if tools_list:
                typer.echo(f"找到 {len(tools_list)} 个可用工具:\n")
                for idx, tool in enumerate(tools_list, 1):
                    typer.echo(f"{idx}. {tool.get('name', 'N/A')}")
                    if description := tool.get("description"):
                        typer.echo(f"   描述: {description}")
                    if input_schema := tool.get("inputSchema"):
                        typer.echo(f"   参数: {json.dumps(input_schema, ensure_ascii=False, indent=2)}")
                    typer.echo()
            else:
                typer.echo("未找到可用工具")

    except httpx.HTTPError as e:
        typer.echo(f"HTTP 请求失败: {e}", err=True)
        raise typer.Exit(code=1)
    except json.JSONDecodeError as e:
        typer.echo(f"JSON 解析失败: {e}", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"未知错误: {e}", err=True)
        raise typer.Exit(code=1)


if __name__ == "__main__":
    cmd()
