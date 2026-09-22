from typer.testing import CliRunner

from ai_assistant.commands import aliyun_oss


def test_sync_help_includes_verbose_option():
    result = CliRunner().invoke(aliyun_oss.cmd, ["sync", "--help"])

    assert result.exit_code == 0
    assert "--verbose" in result.output
    assert "输出扫描、列举及对象元数据比对的进度" in result.output
