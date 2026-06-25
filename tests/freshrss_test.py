import re

import pytest
import typer
from typer.testing import CliRunner

import ai_assistant.commands.automation.freshrss as freshrss
from ai_assistant.commands.automation.freshrss import (
    _all_videos_are_404,
    _encode_form_data,
    _entries_selected_by_video_404,
    _entries_to_mark_read,
    _extract_h5_video_urls,
    _filter_entries_by_title,
    _limit_entries,
    _normalise_keywords,
    _search_entries,
    _video_404_decision,
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


def test_filter_entries_by_title_allows_empty_title_filter():
    entries = [
        {"id": "1", "title": "OpenAI Codex", "content": "", "html": "", "url": ""},
        {"id": "2", "title": "普通新闻", "content": "", "html": "", "url": ""},
    ]

    assert _filter_entries_by_title(entries, title="") == entries
    assert _filter_entries_by_title(entries, title="openai") == [entries[0]]


def test_extract_h5_video_urls_extracts_only_videos_inside_h5_and_resolves_urls():
    html = """
    <video src="https://cdn.example.com/outside.mp4"></video>
    <h5>
      <video src="../media/a.mp4">
        <source src="/media/b.mp4">
        <source src="/media/b.mp4">
      </video>
    </h5>
    <h5><video><source src="https://cdn.example.com/c.mp4" /></video></h5>
    """

    result = _extract_h5_video_urls(html, base_url="https://example.com/articles/post.html")

    assert result == [
        "https://example.com/media/a.mp4",
        "https://example.com/media/b.mp4",
        "https://cdn.example.com/c.mp4",
    ]


def test_all_videos_are_404_requires_at_least_one_video_and_every_status_404():
    assert _all_videos_are_404([{"url": "https://example.com/a.mp4", "status_code": 404, "error": ""}])
    assert _all_videos_are_404(
        [
            {"url": "https://example.com/a.mp4", "status_code": 404, "error": ""},
            {"url": "https://example.com/b.mp4", "status_code": 404, "error": ""},
        ]
    )
    assert not _all_videos_are_404([])
    assert not _all_videos_are_404(
        [
            {"url": "https://example.com/a.mp4", "status_code": 404, "error": ""},
            {"url": "https://example.com/b.mp4", "status_code": 200, "error": ""},
        ]
    )
    assert not _all_videos_are_404([{"url": "https://example.com/a.mp4", "status_code": None, "error": "ConnectError"}])


def test_video_404_decision_marks_read_only_when_all_videos_return_404():
    entry = {"id": "1", "title": "视频文章", "content": "", "html": "", "url": ""}

    selected = _video_404_decision(
        entry,
        [
            {"url": "https://example.com/a.mp4", "status_code": 404, "error": ""},
            {"url": "https://example.com/b.mp4", "status_code": 404, "error": ""},
        ],
    )
    mixed = _video_404_decision(
        entry,
        [
            {"url": "https://example.com/a.mp4", "status_code": 404, "error": ""},
            {"url": "https://example.com/b.mp4", "status_code": 302, "error": ""},
        ],
    )

    assert selected["mark_read"] is True
    assert mixed["mark_read"] is False


def test_entries_selected_by_video_404_returns_only_mark_read_entries():
    first = {"id": "1", "title": "第一篇", "content": "", "html": "", "url": ""}
    second = {"id": "2", "title": "第二篇", "content": "", "html": "", "url": ""}
    decisions = [
        {"entry": first, "videos": [{"url": "https://example.com/a.mp4", "status_code": 404, "error": ""}], "mark_read": True, "reason": "all h5 video URLs returned 404"},
        {"entry": second, "videos": [{"url": "https://example.com/b.mp4", "status_code": 200, "error": ""}], "mark_read": False, "reason": "at least one h5 video URL did not return 404"},
    ]

    assert _entries_selected_by_video_404(decisions) == [first]


def test_freshrss_command_help_contains_cleanup_unread():
    result = CliRunner().invoke(cmd, ["--help"])

    assert result.exit_code == 0
    assert "cleanup-unread" in result.output
    assert "cleanup-video-404" in result.output
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


def test_cleanup_video_404_help_contains_dry_run_title_and_label_options():
    result = CliRunner().invoke(cmd, ["cleanup-video-404", "--help"])

    assert result.exit_code == 0
    clean_output = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
    assert "--dry-run" in clean_output
    assert "--no-dry-run" in clean_output
    assert "--title" in clean_output
    assert "--category" in clean_output
    assert "--label" in clean_output


def test_cleanup_video_404_dry_run_previews_without_marking_read(monkeypatch: pytest.MonkeyPatch):
    entry = {"id": "item-1", "title": "Daily video", "content": "", "html": "<h5><video src='https://example.com/missing.mp4'></video></h5>", "url": ""}

    monkeypatch.setattr(freshrss, "_get_account_info", lambda endpoint, user, token: {"sid": "", "lsid": "", "auth": "auth-token"})
    monkeypatch.setattr(freshrss, "_get_unread_entries_by_category", lambda client, endpoint, category: [entry])
    monkeypatch.setattr(
        freshrss,
        "_check_entry_h5_videos",
        lambda client, candidate: {
            "entry": candidate,
            "videos": [{"url": "https://example.com/missing.mp4", "status_code": 404, "error": ""}],
            "mark_read": True,
            "reason": "all h5 video URLs returned 404",
        },
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("dry-run must not mark entries as read")

    monkeypatch.setattr(freshrss, "_get_edit_token", fail_if_called)
    monkeypatch.setattr(freshrss, "_mark_entries_read", fail_if_called)

    result = CliRunner().invoke(
        cmd,
        [
            "cleanup-video-404",
            "--category",
            "videos",
            "--title",
            "daily",
            "--endpoint",
            "https://rss.example.com",
            "--user",
            "user",
            "--token",
            "token",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert "dry-run 预览，不会真实标记已读" in result.output
    assert "[MARK-READ] Daily video (item-1)" in result.output
    assert "HTTP 404 https://example.com/missing.mp4" in result.output
