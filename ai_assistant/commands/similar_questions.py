import json
import typer
from openai import OpenAI
from openai.types.responses.response_output_message import ResponseOutputMessage
from openai.types.responses.response_output_text import ResponseOutputText
from ai_assistant.commands import default_invoke_without_command
from ai_assistant.settings import OpenAISettings

helptext = """
Generate N similar questions by input query.
"""

cmd = typer.Typer(help=helptext)


def add_default_invoke():
    for _cmd in (cmd,):
        _cmd.callback(invoke_without_command=True)(default_invoke_without_command)


add_default_invoke()


def get_similar_questions_by_query(query: str, topn: int, base_url: str, api_key: str, model: str) -> list[str] | None:
    client = OpenAI(base_url=base_url, api_key=api_key)
    prompt = f"""
    现在开始, 你是一位经验丰富的 AI 训练师, 负责帮我从一个问题泛化成至多{topn}条相似问.

    生成的相似问必须按照 JSON 格式, 并将值作为数组写入 list 字段内, 请严格按照这种格式返回.
    """
    messages = [
        {"role": "system", "content": f"{prompt}"},
        {"role": "user", "content": f"{query}"},
    ]

    response = client.responses.create(model=model, input=messages)  # type: ignore

    for item in response.output:
        if isinstance(item, ResponseOutputMessage):
            for content in item.content:
                if isinstance(content, ResponseOutputText):
                    try:
                        data = json.loads(content.text)["list"]
                        return data[:topn]
                    except json.decoder.JSONDecodeError:
                        continue


@cmd.command()
def generate(
    query: str = typer.Argument(..., help="用户输入问题"),
    topn: int = typer.Option(5, help="生成的相似问条数"),
    base_url: str | None = typer.Option(None),
    api_key: str | None = typer.Option(None),
    model: str | None = typer.Option(None),
):
    """输入问题并输出 N 条相似问题"""
    settings = OpenAISettings()
    if base_url is None:
        base_url = settings.base_url

    if api_key is None:
        api_key = settings.api_key

    if model is None:
        model = settings.model

    assert base_url and api_key and model
    result = get_similar_questions_by_query(query, topn, base_url, api_key, model)
    typer.echo("\n".join(result or []))


if __name__ == "__main__":
    cmd()
