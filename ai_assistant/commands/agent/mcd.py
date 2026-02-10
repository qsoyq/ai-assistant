import json
from typing import Any

import typer
from openai import Client
from openai.types.responses import Response

from ai_assistant.commands import default_invoke_without_command
from ai_assistant.settings import OpenAISettings

helptext = """
基于 OpenAI Responses API 的 mcp-mcd 工具
"""

cmd = typer.Typer(help=helptext)


def add_default_invoke():
    for _cmd in (cmd,):
        _cmd.callback(invoke_without_command=True)(default_invoke_without_command)


add_default_invoke()


MCP_URL = "https://mcp.mcd.cn/mcp-servers/mcd-mcp"


class McdMcpOpenAIResponsesAgent:
    """OpenAI Responses API Agent 封装类"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        mcp_token: str,
        mcp_url: str = MCP_URL,
        auto_approve: bool = True,
        verbose: bool = True,
    ):
        """
        初始化 Agent

        Args:
            base_url: OpenAI API 基础 URL
            api_key: OpenAI API Key
            model: 使用的模型名称
            mcp_token: MCP 服务的认证 token
            mcp_url: MCP 服务的 URL
            auto_approve: 是否自动批准工具调用
            verbose: 是否打印详细信息
        """
        self.client = Client(base_url=base_url, api_key=api_key)
        self.model = model
        self.mcp_token = mcp_token
        self.mcp_url = mcp_url
        self.auto_approve = auto_approve
        self.verbose = verbose

        # 定义 MCP 工具配置
        self.tools = [
            {
                "type": "mcp",
                "server_label": "mcd",
                "server_description": "麦当劳 MCP 服务，提供优惠券查询、活动查询等功能",
                "server_url": self.mcp_url,
                "require_approval": "never" if auto_approve else "always",
                "headers": {
                    "Authorization": f"Bearer {self.mcp_token}",
                },
            }
        ]

    def _print_separator(self, title: str = "", char: str = "=", length: int = 60):
        """打印分隔线"""
        if title:
            typer.echo(f"\n{char * length}")
            typer.echo(f"{title}")
            typer.echo(f"{char * length}")
        else:
            typer.echo(f"{char * length}")

    def _print_message(self, role: str, content: str):
        """打印消息"""
        if self.verbose:
            role_emoji = {"system": "🤖", "user": "👤", "assistant": "🤖"}
            emoji = role_emoji.get(role, "💬")
            typer.echo(f"\n{emoji} [{role.upper()}]:")
            typer.echo(content)

    def _print_tool_call(self, tool_name: str, arguments: dict[str, Any]):
        """打印工具调用信息"""
        if self.verbose:
            typer.echo(f"\n🔧 [工具调用] {tool_name}")
            typer.echo(f"参数: {json.dumps(arguments, ensure_ascii=False, indent=2)}")

    def _print_response_info(self, response: Response):
        """打印响应信息"""
        if self.verbose:
            self._print_separator("响应详情", "-", 60)
            typer.echo(f"Response ID: {response.id}")
            typer.echo(f"Model: {response.model}")
            typer.echo(f"Status: {response.status}")

            if hasattr(response, "usage") and response.usage:
                typer.echo("\nToken 使用:")
                typer.echo(f"  - Input: {response.usage.input_tokens}")
                typer.echo(f"  - Output: {response.usage.output_tokens}")
                typer.echo(f"  - Total: {response.usage.total_tokens}")

    def run_conversation(self, user_query: str, system_prompt: str | None = None) -> str:
        """
        运行一次完整的对话流程

        Args:
            user_query: 用户的问题
            system_prompt: 系统提示词（可选）

        Returns:
            助手的最终回复文本
        """
        # 构建初始消息
        messages: list[dict[str, str]] = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
            self._print_message("system", system_prompt)

        messages.append({"role": "user", "content": user_query})
        self._print_message("user", user_query)

        # 调用 responses API
        self._print_separator("开始调用 OpenAI Responses API")

        response = self.client.responses.create(
            model=self.model,
            tools=self.tools,  # type: ignore
            input=messages,  # type: ignore
        )

        # 打印响应信息
        self._print_response_info(response)

        # 提取输出文本
        output_text = response.output_text or ""

        if output_text:
            self._print_message("assistant", output_text)

        # 检查是否有工具调用
        if hasattr(response, "output") and response.output:
            for item in response.output:
                if item.type == "tool_use":
                    tool_name = item.name
                    tool_input = item.input if hasattr(item, "input") else {}
                    self._print_tool_call(tool_name, tool_input)

        return output_text

    def run_multi_turn_conversation(self, queries: list[str], system_prompt: str | None = None) -> list[str]:
        """
        运行多轮对话

        Args:
            queries: 用户问题列表
            system_prompt: 系统提示词（可选）

        Returns:
            每轮对话的助手回复列表
        """
        results = []

        for i, query in enumerate(queries, 1):
            self._print_separator(f"第 {i}/{len(queries)} 轮对话", "=", 60)
            result = self.run_conversation(query, system_prompt if i == 1 else None)
            results.append(result)

        return results


@cmd.command()
def single(
    query: str = typer.Argument(..., help="用户问题，例如：看一下我有多少张优惠券"),
    mcp_token: str = typer.Option(..., help="MCD MCP 服务的 Authorization token", envvar="MCD_MCP_TOKEN"),
    base_url: str | None = typer.Option(None, help="OpenAI API 基础 URL", envvar="OPENAI_BASE_URL"),
    api_key: str | None = typer.Option(None, help="OpenAI API Key", envvar="OPENAI_API_KEY"),
    model: str | None = typer.Option(None, help="使用的模型名称", envvar="OPENAI_MODEL"),
    auto_approve: bool = typer.Option(True, help="是否自动批准工具调用"),
    verbose: bool = typer.Option(True, help="是否打印详细信息"),
):
    """运行单次对话查询"""

    # 加载配置
    settings = OpenAISettings()
    base_url = base_url or settings.base_url
    api_key = api_key or settings.api_key
    model = model or settings.model

    # 验证必需参数
    if not all([base_url, api_key, model, mcp_token]):
        typer.echo("❌ 错误: 缺少必需的配置参数", err=True)
        typer.echo("请通过命令行参数或环境变量提供以下配置:", err=True)
        typer.echo("  - base_url (OPENAI_BASE_URL)", err=True)
        typer.echo("  - api_key (OPENAI_API_KEY)", err=True)
        typer.echo("  - model (OPENAI_MODEL)", err=True)
        typer.echo("  - mcp_token (MCD_MCP_TOKEN)", err=True)
        raise typer.Exit(code=1)

    # 创建 Agent
    agent = McdMcpOpenAIResponsesAgent(
        base_url=base_url,  # type: ignore
        api_key=api_key,  # type: ignore
        model=model,  # type: ignore
        mcp_token=mcp_token,
        auto_approve=auto_approve,
        verbose=verbose,
    )

    # 系统提示词
    system_prompt = """你是一个智能助手，可以帮助用户查询麦当劳相关信息。
你可以使用 MCP 工具来获取用户的优惠券信息、可领取的优惠券、营销活动等。
请根据用户的问题，选择合适的工具进行查询，并以友好、清晰的方式回答用户。"""

    # 运行对话
    try:
        result = agent.run_conversation(query, system_prompt)

        # 输出最终结果
        agent._print_separator("最终结果", "=", 60)
        typer.echo("\n✅ 查询完成")
        typer.echo(f"\n{result}")

    except Exception as e:
        typer.echo(f"\n❌ 错误: {str(e)}", err=True)
        raise typer.Exit(code=1)


@cmd.command()
def quickstart(
    mcp_token: str = typer.Option(..., help="MCD MCP 服务的 Authorization token", envvar="MCD_MCP_TOKEN"),
    base_url: str | None = typer.Option(None, help="OpenAI API 基础 URL", envvar="OPENAI_BASE_URL"),
    api_key: str | None = typer.Option(None, help="OpenAI API Key", envvar="OPENAI_API_KEY"),
    model: str | None = typer.Option(None, help="使用的模型名称", envvar="OPENAI_MODEL"),
    auto_approve: bool = typer.Option(True, help="是否自动批准工具调用"),
    verbose: bool = typer.Option(True, help="是否打印详细信息"),
):
    """运行预设的演示查询（多个场景）"""

    # 加载配置
    settings = OpenAISettings()
    base_url = base_url or settings.base_url
    api_key = api_key or settings.api_key
    model = model or settings.model

    # 验证必需参数
    if not all([base_url, api_key, model, mcp_token]):
        typer.echo("❌ 错误: 缺少必需的配置参数", err=True)
        raise typer.Exit(code=1)

    # 创建 Agent
    agent = McdMcpOpenAIResponsesAgent(
        base_url=base_url,  # type: ignore
        api_key=api_key,  # type: ignore
        model=model,  # type: ignore
        mcp_token=mcp_token,
        auto_approve=auto_approve,
        verbose=verbose,
    )

    # 系统提示词
    system_prompt = """你是一个智能助手，可以帮助用户查询麦当劳相关信息。
你可以使用 MCP 工具来获取用户的优惠券信息、可领取的优惠券、营销活动等。
请根据用户的问题，选择合适的工具进行查询，并以友好、清晰的方式回答用户。"""

    # 预设的演示查询
    demo_queries = [
        "看一下我有多少张优惠券",
        "现在有什么优惠券可以领取？",
        "最近有什么营销活动？",
        "帮我领取目前可领取的优惠券",
    ]

    # 统计信息
    success_count = 0
    fail_count = 0
    results = []

    # 运行演示
    typer.echo("\n" + "=" * 60)
    typer.echo("🚀 开始运行 OpenAI Responses API Agent Demo")
    typer.echo("=" * 60)

    for i, query in enumerate(demo_queries, 1):
        try:
            agent._print_separator(f"演示 {i}/{len(demo_queries)}: {query}", "=", 60)
            result = agent.run_conversation(query, system_prompt if i == 1 else None)
            results.append({"query": query, "result": result, "success": True})
            success_count += 1
            typer.echo(f"\n✅ 演示 {i} 完成")
        except Exception as e:
            typer.echo(f"\n❌ 演示 {i} 失败: {str(e)}", err=True)
            results.append({"query": query, "result": str(e), "success": False})
            fail_count += 1

    # 输出统计信息
    typer.echo("\n" + "=" * 60)
    typer.echo("📊 演示统计")
    typer.echo("=" * 60)
    typer.echo(f"总计: {len(demo_queries)} 个查询")
    typer.echo(f"成功: {success_count} 个")
    typer.echo(f"失败: {fail_count} 个")
    typer.echo(f"成功率: {success_count / len(demo_queries) * 100:.1f}%")

    # 输出详细结果
    typer.echo("\n" + "=" * 60)
    typer.echo("📝 详细结果")
    typer.echo("=" * 60)

    for i, item in enumerate(results, 1):
        status = "✅" if item["success"] else "❌"
        typer.echo(f"\n{status} 查询 {i}: {item['query']}")
        result = str(getattr(item, "result", ""))
        typer.echo(f"结果: {result[:200]}...")  # 只显示前200个字符


@cmd.command()
def interactive(
    mcp_token: str = typer.Option(..., help="MCD MCP 服务的 Authorization token", envvar="MCD_MCP_TOKEN"),
    base_url: str | None = typer.Option(None, help="OpenAI API 基础 URL", envvar="OPENAI_BASE_URL"),
    api_key: str | None = typer.Option(None, help="OpenAI API Key", envvar="OPENAI_API_KEY"),
    model: str | None = typer.Option(None, help="使用的模型名称", envvar="OPENAI_MODEL"),
    auto_approve: bool = typer.Option(True, help="是否自动批准工具调用"),
):
    """交互式对话模式"""

    # 加载配置
    settings = OpenAISettings()
    base_url = base_url or settings.base_url
    api_key = api_key or settings.api_key
    model = model or settings.model

    # 验证必需参数
    if not all([base_url, api_key, model, mcp_token]):
        typer.echo("❌ 错误: 缺少必需的配置参数", err=True)
        raise typer.Exit(code=1)

    # 创建 Agent
    agent = McdMcpOpenAIResponsesAgent(
        base_url=base_url,  # type: ignore
        api_key=api_key,  # type: ignore
        model=model,  # type: ignore
        mcp_token=mcp_token,
        auto_approve=auto_approve,
        verbose=True,
    )

    # 系统提示词
    system_prompt = """
    你是一个智能助手，可以帮助用户查询麦当劳相关信息。
    你可以使用 MCP 工具来获取用户的优惠券信息、可领取的优惠券、营销活动等。
    请根据用户的问题，选择合适的工具进行查询，并以友好、清晰的方式回答用户。
    """

    # 欢迎信息
    typer.echo("\n" + "=" * 60)
    typer.echo("🤖 OpenAI Responses API Agent - 交互式模式")
    typer.echo("=" * 60)
    typer.echo("\n你可以问我关于麦当劳的问题，例如：")
    typer.echo("  - 看一下我有多少张优惠券")
    typer.echo("  - 现在有什么优惠券可以领取？")
    typer.echo("  - 最近有什么营销活动？")
    typer.echo("\n输入 'exit' 或 'quit' 退出")
    typer.echo("=" * 60)

    # 交互循环
    is_first_query = True
    while True:
        try:
            # 获取用户输入
            query = typer.prompt("\n👤 你").strip()

            # 检查退出命令
            if query.lower() in ["exit", "quit", "退出", "q"]:
                typer.echo("\n👋 再见！")
                break

            if not query:
                continue

            # 运行对话
            agent.run_conversation(query, system_prompt if is_first_query else None)
            is_first_query = False

        except KeyboardInterrupt:
            typer.echo("\n\n👋 再见！")
            break
        except Exception as e:
            typer.echo(f"\n❌ 错误: {str(e)}", err=True)


if __name__ == "__main__":
    cmd()
