import shutil


def test_cmd():
    assert shutil.which("ai-assistant") is not None
