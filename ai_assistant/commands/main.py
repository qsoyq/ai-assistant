import typer

import ai_assistant.commands.similar_questions
from ai_assistant.commands import default_invoke_without_command


helptext = """

"""

cmd = typer.Typer(help=helptext)
cmd.add_typer(ai_assistant.commands.similar_questions.cmd, name="similar-questions")


def add_default_invoke():
    for _cmd in (cmd,):
        _cmd.callback(invoke_without_command=True)(default_invoke_without_command)


add_default_invoke()

if __name__ == "__main__":
    cmd()
