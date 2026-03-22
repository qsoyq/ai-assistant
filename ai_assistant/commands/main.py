import typer

import ai_assistant.commands.agent.mcd
import ai_assistant.commands.automation.cloudflare_tunnel_watcher
import ai_assistant.commands.automation.docker_hub_runner
import ai_assistant.commands.automation.file_change_runner
import ai_assistant.commands.automation.freshrss
import ai_assistant.commands.cookies
import ai_assistant.commands.cursor.usage
import ai_assistant.commands.docker
import ai_assistant.commands.mcp_cli
import ai_assistant.commands.opml
import ai_assistant.commands.similar_questions
import ai_assistant.commands.ssl
from ai_assistant.commands import default_invoke_without_command

helptext = """

"""

cmd = typer.Typer(help=helptext)

for name, subcommand in (
    ("docker", ai_assistant.commands.docker.cmd),
    ("ssl", ai_assistant.commands.ssl.cmd),
    ("similar-questions", ai_assistant.commands.similar_questions.cmd),
    ("opml", ai_assistant.commands.opml.cmd),
    ("mcp-cli", ai_assistant.commands.mcp_cli.cmd),
    ("cookies", ai_assistant.commands.cookies.cmd),
    ("freshrss", ai_assistant.commands.automation.freshrss.cmd),
    ("file-change-runner", ai_assistant.commands.automation.file_change_runner.cmd),
    ("docker-hub-runner", ai_assistant.commands.automation.docker_hub_runner.cmd),
    ("cf-tunnel-watcher", ai_assistant.commands.automation.cloudflare_tunnel_watcher.cmd),
    ("cursor-usage", ai_assistant.commands.cursor.usage.cmd),
    ("mcd", ai_assistant.commands.agent.mcd.cmd),
):
    cmd.add_typer(subcommand, name=name)


def add_default_invoke():
    for _cmd in (cmd,):
        _cmd.callback(invoke_without_command=True)(default_invoke_without_command)


add_default_invoke()

if __name__ == "__main__":
    cmd()
