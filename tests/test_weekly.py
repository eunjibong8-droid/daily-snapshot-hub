"""주간 리포터 단위 테스트."""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from daily_hub.reporters.weekly import (
    RssEntry,
    WeatherStats,
    WeekRange,
    _parse_rss_file,
    build_report,
    collect_rss_week,
    collect_weather_week,
    dates_in_range,
    previous_iso_week,
)


# ── 주차 계산 테스트 ──────────────────────────────────────────────────────

def test_previous_iso_week_from_monday():
    # 2026-04-20 (월) 기준 → 직전 주 W16: 2026-04-13 ~ 2026-04-19
    week = previous_iso_week(date(2026, 4, 20))
    assert week.year == 2026
    assert week.week == 16
    assert week.start == date(2026, 4, 13)
    assert week.end == date(2026, 4, 19)
    assert week.label == "2026-W16"


def test_dates_in_range():
    dates = dates_in_range(date(2026, 4, 13), date(2026, 4, 19))
    assert len(dates) == 7
    assert dates[0] == date(2026, 4, 13)
    assert dates[-1] == date(2026, 4, 19)


# ── RSS 파싱 테스트 ────────────────────────────────────────────────────────

SAMPLE_RSS_MD = """\
---
date: 2026-04-18
total_entries: 3
---

# RSS Daily Digest — 2026-04-18

## Hacker News Top (2건)

### [Ask HN: Something](https://news.ycombinator.com/item?id=1)
> 2026-04-18

Short summary here.

### [Show HN: My Project](https://news.ycombinator.com/item?id=2)
> 2026-04-18

Another summary.

---

## Real Python (1건)

### [Python Tips](https://realpython.com/tips)
> 2026-04-18

Python content.

---

## InfoQ _(새 글 없음)_
"""


def test_parse_rss_file(tmp_path):
    p = tmp_path / "2026-04-18.md"
    p.write_text(SAMPLE_RSS_MD, encoding="utf-8")
    result = _parse_rss_file(p)

    assert "Hacker News Top" in result
    assert len(result["Hacker News Top"]) == 2
    assert result["Hacker News Top"][0].title == "Ask HN: Something"
    assert result["Hacker News Top"][1].link == "https://news.ycombinator.com/item?id=2"

    assert "Real Python" in result
    assert len(result["Real Python"]) == 1


def test_collect_rss_week_aggregates_across_days(tmp_path):
    rss_dir = tmp_path / "rss"
    rss_dir.mkdir(parents=True)

    for d in ["2026-04-13", "2026-04-14"]:
        (rss_dir / f"{d}.md").write_text(SAMPLE_RSS_MD, encoding="utf-8")

    week = WeekRange(2026, 16, date(2026, 4, 13), date(2026, 4, 19), "2026-W16")
    with patch("daily_hub.reporters.weekly.SNAPSHOTS_DIR", tmp_path):
        result = collect_rss_week(week)

    assert len(result["Hacker News Top"]) == 4   # 2건 × 2일
    assert len(result["Real Python"]) == 2


def test_collect_rss_week_missing_days_skipped(tmp_path):
    (tmp_path / "rss").mkdir(parents=True)   # 빈 디렉터리
    week = WeekRange(2026, 16, date(2026, 4, 13), date(2026, 4, 19), "2026-W16")
    with patch("daily_hub.reporters.weekly.SNAPSHOTS_DIR", tmp_path):
        result = collect_rss_week(week)
    assert result == {}


# ── 날씨 집계 테스트 ──────────────────────────────────────────────────────

CSV_HEADER = "date,location,temp_c,feels_like_c,temp_max_c,temp_min_c,humidity_pct,precip_mm,precip_prob_pct,wind_kmh,uv_index,pm10,pm2_5,collected_at\n"
CSV_ROW_SEOUL = "2026-04-13,서울,15.0,14.0,20.0,10.0,60,2.0,30,8.0,3.0,30.0,15.0,ts\n"
CSV_ROW_SEOUL2 = "2026-04-14,서울,16.0,15.0,21.0,11.0,55,0.0,10,6.0,4.0,25.0,12.0,ts\n"


def test_collect_weather_week(tmp_path):
    weather_dir = tmp_path / "weather"
    weather_dir.mkdir(parents=True)
    (weather_dir / "2026-04.csv").write_text(
        CSV_HEADER + CSV_ROW_SEOUL + CSV_ROW_SEOUL2, encoding="utf-8"
    )
    week = WeekRange(2026, 16, date(2026, 4, 13), date(2026, 4, 19), "2026-W16")
    with patch("daily_hub.reporters.weekly.SNAPSHOTS_DIR", tmp_path):
        stats = collect_weather_week(week)

    assert len(stats) == 1
    s = stats[0]
    assert s.location == "서울"
    assert s.avg_temp == 15.5
    assert s.max_temp == 21.0
    assert s.min_temp == 10.0
    assert s.total_precip == 2.0


# ── 리포트 생성 테스트 ────────────────────────────────────────────────────

def test_build_report_contains_key_sections():
    week = WeekRange(2026, 16, date(2026, 4, 13), date(2026, 4, 19), "2026-W16")
    rss = {"Hacker News Top": [RssEntry("Hacker News Top", "Title", "https://x.com")]}
    weather = [WeatherStats("서울", 15.5, 21.0, 10.0, 2.0, 30.0, 15.0, 2)]

    report = build_report(week, rss, weather, "2026-04-20T23:30:00Z")

    assert "2026-W16" in report
    assert "날씨 요약" in report
    assert "서울" in report
    assert "RSS 하이라이트" in report
    assert "Hacker News Top" in report
    assert "Title" in report


def test_build_report_no_data_shows_placeholder():
    week = WeekRange(2026, 16, date(2026, 4, 13), date(2026, 4, 19), "2026-W16")
    report = build_report(week, {}, [], "2026-04-20T23:30:00Z")
    assert "날씨 데이터 없음" in report
    assert "RSS 데이터 없음" in report


def test_build_report_limits_entries_per_feed():
    week = WeekRange(2026, 16, date(2026, 4, 13), date(2026, 4, 19), "2026-W16")
    entries = [RssEntry("Feed", f"Title {i}", f"https://x.com/{i}") for i in range(10)]
    report = build_report(week, {"Feed": entries}, [], "ts")
    assert "외 5건" in report
