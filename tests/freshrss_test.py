import re

import pytest
import typer
from typer.testing import CliRunner

from ai_assistant.commands.automation.freshrss import (
    _encode_form_data,
    _entries_to_mark_read,
    _limit_entries,
    _normalise_keywords,
    _search_entries,
    cmd,
)


def test_normalise_keywords_trims_deduplicates_and_ignores_case():
    result = _normalise_keywords([" AI ", "ai", "", "LLM", "llm "], ignore_case=True)

    assert result == ["ai", "llm"]


def test_entries_to_mark_read_skips_entries_matching_any_keep_keyword():
    entries = [
        {"id": "1", "title": "OpenAI 发布新模型", "content": ""},
        {"id": "2", "title": "Anthropic 更新 Claude", "content": ""},
        {"id": "3", "title": "普通新闻", "content": ""},
    ]

    result = _entries_to_mark_read(entries, ["openai", "claude"], ignore_case=True)

    assert result == [{"id": "3", "title": "普通新闻", "content": ""}]


def test_normalised_keywords_still_match_titles_when_ignore_case_enabled():
    entries = [
        {"id": "1", "title": "OpenAI 发布新模型", "content": ""},
        {"id": "2", "title": "普通新闻", "content": ""},
    ]

    normalized_keep = _normalise_keywords(["openai"], ignore_case=True)
    result = _entries_to_mark_read(entries, normalized_keep, ignore_case=True)

    assert result == [{"id": "2", "title": "普通新闻", "content": ""}]


def test_entries_to_mark_read_requires_at_least_one_keyword():
    with pytest.raises(typer.Exit) as exc_info:
        _entries_to_mark_read([{"id": "1", "title": "anything", "content": ""}], ["", "  "], ignore_case=True)

    assert exc_info.value.exit_code == 1


def test_limit_entries_truncates_after_filtering():
    entries = [
        {"id": "1", "title": "第一篇", "content": ""},
        {"id": "2", "title": "第二篇", "content": ""},
        {"id": "3", "title": "第三篇", "content": ""},
    ]

    assert _limit_entries(entries, 2) == [
        {"id": "1", "title": "第一篇", "content": ""},
        {"id": "2", "title": "第二篇", "content": ""},
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


def test_search_entries_filters_titles_case_insensitively():
    entries = [
        {"id": "1", "title": "OpenAI 发布新模型", "content": "这是一篇关于模型发布的文章"},
        {"id": "2", "title": "普通新闻", "content": "没有关键词"},
        {"id": "3", "title": "openai API 更新", "content": "介绍最新 API 变化"},
    ]

    result = _search_entries(entries, title="openai")

    assert result == [
        {"id": "1", "title": "OpenAI 发布新模型", "content": "这是一篇关于模型发布的文章"},
        {"id": "3", "title": "openai API 更新", "content": "介绍最新 API 变化"},
    ]


def test_search_entries_filters_content_by_keyword():
    entries = [
        {"id": "1", "title": "第一篇", "content": "这是一篇关于 Codex 的文章"},
        {"id": "2", "title": "第二篇", "content": "普通内容"},
        {"id": "3", "title": "第三篇", "content": "深入分析 codex 工作流"},
    ]

    result = _search_entries(entries, keyword="codex")

    assert result == [
        {"id": "1", "title": "第一篇", "content": "这是一篇关于 Codex 的文章"},
        {"id": "3", "title": "第三篇", "content": "深入分析 codex 工作流"},
    ]


def test_search_entries_requires_both_conditions_when_both_present():
    entries = [
        {"id": "1", "title": "OpenAI Codex", "content": "Codex 工作流总结"},
        {"id": "2", "title": "OpenAI 发布", "content": "没有相关内容"},
        {"id": "3", "title": "其他标题", "content": "Codex 工作流"},
    ]

    result = _search_entries(entries, title="openai", keyword="codex")

    assert result == [{"id": "1", "title": "OpenAI Codex", "content": "Codex 工作流总结"}]


def test_freshrss_command_help_contains_cleanup_unread():
    result = CliRunner().invoke(cmd, ["--help"])

    assert result.exit_code == 0
    assert "cleanup-unread" in result.output
    assert "search" in result.output


def test_cleanup_unread_help_contains_dry_run_toggle():
    result = CliRunner().invoke(cmd, ["cleanup-unread", "--help"])

    assert result.exit_code == 0
    clean_output = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
    assert "--dry-run" in clean_output
    assert "--no-dry-run" in clean_output


def test_search_help_contains_title_keyword_category_and_read_options():
    result = CliRunner().invoke(cmd, ["search", "--help"])

    assert result.exit_code == 0
    clean_output = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
    assert "--title" in clean_output
    assert "--keyword" in clean_output
    assert "--category" in clean_output
    assert "--limit" in clean_output
    assert "--read" in clean_output
    assert "FRESHRSS_ENDPOINT" in clean_output
    assert "FRESHRSS_USER" in clean_output
    assert "FRESHRSS_API_TOKEN" in clean_output
