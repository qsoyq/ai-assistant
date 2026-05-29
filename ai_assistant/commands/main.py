from ai_assistant.commands import make_typer
from ai_assistant.commands._lazy import LazyRootGroup

helptext = """

"""


class _Root(LazyRootGroup):
    lazy_subcommands = {
        "docker": ("ai_assistant.commands.docker:cmd", "docker"),
        "greader": ("ai_assistant.commands.greader:cmd", None),
        "ssl": ("ai_assistant.commands.ssl:cmd", None),
        "similar-questions": ("ai_assistant.commands.similar_questions:cmd", "mcd"),
        "opml": ("ai_assistant.commands.opml:cmd", None),
        "mcp-cli": ("ai_assistant.commands.mcp_cli:cmd", None),
        "cookies": ("ai_assistant.commands.cookies:cmd", "cookies"),
        "freshrss": ("ai_assistant.commands.automation.freshrss:cmd", "freshrss"),
        "file-change-runner": ("ai_assistant.commands.automation.file_change_runner:cmd", None),
        "docker-hub-runner": ("ai_assistant.commands.automation.docker_hub_runner:cmd", None),
        "cf-tunnel-watcher": ("ai_assistant.commands.automation.cloudflare_tunnel_watcher:cmd", None),
        "cursor-usage": ("ai_assistant.commands.cursor.usage:cmd", "cursor"),
        "mcd": ("ai_assistant.commands.agent.mcd:cmd", "mcd"),
        "stash-log": ("ai_assistant.commands.stash_log:cmd", None),
        "handoff": ("ai_assistant.commands.handoff:cmd", None),
        "httpx-disable-verify": ("ai_assistant.commands.httpx_disable_verify:cmd", None),
        "requests-disable-verify": ("ai_assistant.commands.requests_disable_verify:cmd", None),
        "udp": ("ai_assistant.commands.udp:cmd", None),
        "aliyun-oss": ("ai_assistant.commands.aliyun_oss:cmd", "oss"),
        "reality": ("ai_assistant.commands.reality:cmd", None),
        "realm": ("ai_assistant.commands.realm:cmd", None),
        "disable-ssl-verify": ("ai_assistant.commands.disable_ssl_verify:cmd", None),
        "bump-version": ("ai_assistant.commands.bump_version:cmd", None),
        "pypi-mirror": ("ai_assistant.commands.pypi_mirror:cmd", None),
        "pypi-upload": ("ai_assistant.commands.pypi_upload:cmd", None),
        "win-env": ("ai_assistant.commands.win_env:cmd", None),
        "adb": ("ai_assistant.commands.adb:cmd", None),
        "lan-ddns": ("ai_assistant.commands.lan_ddns:cmd", None),
        "ghi": ("ai_assistant.commands.ghi.main:cmd", None),
        "uv-tool": ("ai_assistant.commands.uv_tool:cmd", None),
    }


cmd = make_typer(helptext, cls=_Root)
if __name__ == "__main__":
    cmd()
