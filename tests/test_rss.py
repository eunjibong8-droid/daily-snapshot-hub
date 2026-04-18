"""RSS collector 단위 테스트."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from time import gmtime
from unittest.mock import MagicMock, patch

import pytest

from daily_hub.collectors.rss import (
    Entry,
    build_snapshot,
    collect_feed,
    load_state,
    save_state,
)


# ── 픽스처 ────────────────────────────────────────────────────────────────

def _make_entry(
    title: str = "Test Title",
    link: str = "https://example.com/1",
    summary: str = "Test summary",
    published: str | None = "2026-04-18T08:00:00+00:00",
) -> MagicMock:
    e = MagicMock()
    e.get.side_effect = lambda key, default="": {"title": title}.get(key, default)
    e.title = title
    e.link = link
    e.summary = summary
    e.description = ""
    e.id = link
    if published:
        dt = datetime.fromisoformat(published)
        e.published_parsed = gmtime(dt.timestamp())
    else:
        e.published_parsed = None
    return e


# ── collect_feed 테스트 ────────────────────────────────────────────────────

@patch("daily_hub.collectors.rss.feedparser.parse")
def test_collect_feed_first_run(mock_parse):
    """첫 수집(last_seen 없음)이면 모든 항목을 반환한다."""
    mock_parse.return_value = MagicMock(
        entries=[_make_entry("A"), _make_entry("B", link="https://example.com/2")]
    )
    feed_cfg = {"name": "Test", "url": "https://example.com/rss", "category": "테스트"}
    entries = collect_feed(feed_cfg, last_seen_iso=None)
    assert len(entries) == 2
    assert entries[0]["title"] == "A"


@patch("daily_hub.collectors.rss.feedparser.parse")
def test_collect_feed_filters_old_entries(mock_parse):
    """last_seen 이전 항목은 제외된다."""
    mock_parse.return_value = MagicMock(
        entries=[
            _make_entry("Old", published="2026-04-17T00:00:00+00:00"),
            _make_entry("New", link="https://example.com/2", published="2026-04-18T09:00:00+00:00"),
        ]
    )
    feed_cfg = {"name": "Test", "url": "https://example.com/rss", "category": "테스트"}
    entries = collect_feed(feed_cfg, last_seen_iso="2026-04-17T12:00:00+00:00")
    assert len(entries) == 1
    assert entries[0]["title"] == "New"


@patch("daily_hub.collectors.rss.feedparser.parse")
def test_collect_feed_skips_entry_without_link(mock_parse):
    """link와 id 둘 다 없는 항목은 스킵한다."""
    e = _make_entry()
    e.link = ""
    e.id = ""
    mock_parse.return_value = MagicMock(entries=[e])
    feed_cfg = {"name": "Test", "url": "https://example.com/rss", "category": "테스트"}
    entries = collect_feed(feed_cfg, last_seen_iso=None)
    assert entries == []


@patch("daily_hub.collectors.rss.feedparser.parse")
def test_collect_feed_truncates_summary(mock_parse):
    """summary가 200자를 초과하면 잘린다."""
    long_summary = "x" * 300
    mock_parse.return_value = MagicMock(entries=[_make_entry(summary=long_summary)])
    feed_cfg = {"name": "Test", "url": "https://example.com/rss", "category": "테스트"}
    entries = collect_feed(feed_cfg, last_seen_iso=None)
    assert len(entries[0]["summary"]) <= 201  # 200자 + 말줄임표


# ── build_snapshot 테스트 ─────────────────────────────────────────────────

def test_build_snapshot_contains_frontmatter():
    results = {"Feed A": [Entry(title="T", link="https://x.com", summary="S", published_utc="2026-04-18T00:00:00+00:00")]}
    output = build_snapshot("2026-04-18", "2026-04-18T23:00:00+00:00", results, [])
    assert output.startswith("---")
    assert "date: 2026-04-18" in output
    assert "total_entries: 1" in output


def test_build_snapshot_failed_section():
    output = build_snapshot("2026-04-18", "2026-04-18T23:00:00+00:00", {}, [("BadFeed", "timeout")])
    assert "수집 실패" in output
    assert "BadFeed" in output
    assert "timeout" in output


def test_build_snapshot_no_new_entries():
    output = build_snapshot("2026-04-18", "2026-04-18T23:00:00+00:00", {"Feed A": []}, [])
    assert "새 글 없음" in output


# ── state 테스트 ──────────────────────────────────────────────────────────

def test_save_and_load_state(tmp_path):
    with patch("daily_hub.collectors.rss.STATE_FILE", tmp_path / "state.json"):
        from daily_hub.collectors import rss
        rss.STATE_FILE = tmp_path / "state.json"

        state = {"Feed A": "2026-04-18T00:00:00+00:00"}
        save_state(state)
        loaded = load_state()
        assert loaded == state


def test_load_state_returns_empty_when_missing(tmp_path):
    with patch("daily_hub.collectors.rss.STATE_FILE", tmp_path / "nonexistent.json"):
        from daily_hub.collectors import rss
        rss.STATE_FILE = tmp_path / "nonexistent.json"
        assert load_state() == {}
