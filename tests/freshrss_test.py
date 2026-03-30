import re

import pytest
import typer
from typer.testing import CliRunner

from ai_assistant.commands.automation.freshrss import (
    _encode_form_data,
    _entries_to_mark_read,
    _limit_entries,
    _normalise_keywords,
    cmd,
)


def test_normalise_keywords_trims_deduplicates_and_ignores_case():
    result = _normalise_keywords([" AI ", "ai", "", "LLM", "llm "], ignore_case=True)

    assert result == ["ai", "llm"]


def test_entries_to_mark_read_skips_entries_matching_any_keep_keyword():
    entries = [
        {"id": "1", "title": "OpenAI 发布新模型"},
        {"id": "2", "title": "Anthropic 更新 Claude"},
        {"id": "3", "title": "普通新闻"},
    ]

    result = _entries_to_mark_read(entries, ["openai", "claude"], ignore_case=True)

    assert result == [{"id": "3", "title": "普通新闻"}]


def test_normalised_keywords_still_match_titles_when_ignore_case_enabled():
    entries = [
        {"id": "1", "title": "OpenAI 发布新模型"},
        {"id": "2", "title": "普通新闻"},
    ]

    normalized_keep = _normalise_keywords(["openai"], ignore_case=True)
    result = _entries_to_mark_read(entries, normalized_keep, ignore_case=True)

    assert result == [{"id": "2", "title": "普通新闻"}]


def test_entries_to_mark_read_requires_at_least_one_keyword():
    with pytest.raises(typer.Exit) as exc_info:
        _entries_to_mark_read([{"id": "1", "title": "anything"}], ["", "  "], ignore_case=True)

    assert exc_info.value.exit_code == 1


def test_limit_entries_truncates_after_filtering():
    entries = [
        {"id": "1", "title": "第一篇"},
        {"id": "2", "title": "第二篇"},
        {"id": "3", "title": "第三篇"},
    ]

    assert _limit_entries(entries, 2) == [
        {"id": "1", "title": "第一篇"},
        {"id": "2", "title": "第二篇"},
    ]


def test_encode_form_data_preserves_repeated_item_ids():
    encoded = _encode_form_data(
        [
            ("a", "user/-/state/com.google/read"),
            ("T", "token123"),
            ("i", "item-1"),
            ("i", "item-2"),
        ]
    )

    assert encoded.decode() == "a=user%2F-%2Fstate%2Fcom.google%2Fread&T=token123&i=item-1&i=item-2"


def test_freshrss_command_help_contains_cleanup_unread():
    result = CliRunner().invoke(cmd, ["--help"])

    assert result.exit_code == 0
    assert "cleanup-unread" in result.output


def test_cleanup_unread_help_contains_dry_run_toggle():
    result = CliRunner().invoke(cmd, ["cleanup-unread", "--help"])

    assert result.exit_code == 0
    clean_output = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
    assert "--dry-run" in clean_output
    assert "--no-dry-run" in clean_output
