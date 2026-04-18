"""주간 통합 리포트 생성기.

직전 ISO 주차의 RSS + 날씨 데이터를 읽어
reports/weekly/YYYY-WNN.md 를 생성한다.

Usage:
    uv run python -m daily_hub.reporters.weekly
"""
from __future__ import annotations

import csv
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta, timezone, datetime
from pathlib import Path
from typing import NamedTuple

from daily_hub.common.dates import today_kst
from daily_hub.common.markdown import frontmatter
from daily_hub.common.paths import REPORTS_DIR, SNAPSHOTS_DIR


# ── 주차 계산 ──────────────────────────────────────────────────────────────

class WeekRange(NamedTuple):
    year: int
    week: int
    start: date   # 월요일
    end: date     # 일요일
    label: str    # "YYYY-WNN"


def previous_iso_week(today: date) -> WeekRange:
    """오늘 기준 직전 ISO 주차 정보 반환."""
    # 월요일 실행 기준: 오늘 -7일이면 반드시 직전 주 안에 있음
    anchor = today - timedelta(days=7)
    iso = anchor.isocalendar()
    year, week = iso.year, iso.week
    monday = anchor - timedelta(days=anchor.weekday())
    sunday = monday + timedelta(days=6)
    return WeekRange(year, week, monday, sunday, f"{year}-W{week:02d}")


def dates_in_range(start: date, end: date) -> list[date]:
    out = []
    cur = start
    while cur <= end:
        out.append(cur)
        cur += timedelta(days=1)
    return out


# ── RSS 파싱 ───────────────────────────────────────────────────────────────

@dataclass
class RssEntry:
    feed: str
    title: str
    link: str


_FEED_HEADER = re.compile(r"^## (.+?) \((\d+)건\)", re.MULTILINE)
_ENTRY_LINE  = re.compile(r"^### \[(.+?)\]\((.+?)\)", re.MULTILINE)


def _parse_rss_file(path: Path) -> dict[str, list[RssEntry]]:
    """하루치 RSS md 파일 → {feed_name: [RssEntry, ...]}"""
    text = path.read_text(encoding="utf-8")
    result: dict[str, list[RssEntry]] = {}

    # 피드 섹션 경계를 찾아 분할
    sections = _FEED_HEADER.split(text)
    # sections = [pre, feed1, count1, body1, feed2, count2, body2, ...]
    it = iter(sections[1:])  # pre 스킵
    for feed_name, _count, body in zip(it, it, it):
        entries = []
        for m in _ENTRY_LINE.finditer(body):
            entries.append(RssEntry(feed=feed_name, title=m.group(1), link=m.group(2)))
        result[feed_name] = entries

    return result


def collect_rss_week(week: WeekRange) -> dict[str, list[RssEntry]]:
    """주간 RSS 데이터 집계: {feed_name: [RssEntry, ...]}"""
    aggregated: dict[str, list[RssEntry]] = defaultdict(list)
    for d in dates_in_range(week.start, week.end):
        path = SNAPSHOTS_DIR / "rss" / f"{d.isoformat()}.md"
        if not path.exists():
            continue
        for feed, entries in _parse_rss_file(path).items():
            aggregated[feed].extend(entries)
    return dict(aggregated)


# ── 날씨 파싱 ─────────────────────────────────────────────────────────────

@dataclass
class WeatherStats:
    location: str
    avg_temp: float
    max_temp: float
    min_temp: float
    total_precip: float
    avg_pm10: float
    avg_pm25: float
    days: int


def _months_in_range(start: date, end: date) -> list[str]:
    """주 범위에 걸친 YYYY-MM 목록 (최대 2개)."""
    months = set()
    cur = start
    while cur <= end:
        months.add(cur.strftime("%Y-%m"))
        cur += timedelta(days=32)
        cur = cur.replace(day=1)
    months.add(end.strftime("%Y-%m"))
    return sorted(months)


def collect_weather_week(week: WeekRange) -> list[WeatherStats]:
    """주간 날씨 CSV 집계 → 위치별 WeatherStats."""
    date_strs = {d.isoformat() for d in dates_in_range(week.start, week.end)}
    rows_by_loc: dict[str, list[dict]] = defaultdict(list)

    for ym in _months_in_range(week.start, week.end):
        path = SNAPSHOTS_DIR / "weather" / f"{ym}.csv"
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row["date"] in date_strs:
                    rows_by_loc[row["location"]].append(row)

    stats = []
    for loc, rows in rows_by_loc.items():
        def avg(key: str) -> float:
            vals = [float(r[key]) for r in rows if r.get(key) not in (None, "")]
            return round(sum(vals) / len(vals), 1) if vals else 0.0

        def mx(key: str) -> float:
            vals = [float(r[key]) for r in rows if r.get(key) not in (None, "")]
            return round(max(vals), 1) if vals else 0.0

        def mn(key: str) -> float:
            vals = [float(r[key]) for r in rows if r.get(key) not in (None, "")]
            return round(min(vals), 1) if vals else 0.0

        def total(key: str) -> float:
            vals = [float(r[key]) for r in rows if r.get(key) not in (None, "")]
            return round(sum(vals), 1)

        stats.append(WeatherStats(
            location=loc,
            avg_temp=avg("temp_c"),
            max_temp=mx("temp_max_c"),
            min_temp=mn("temp_min_c"),
            total_precip=total("precip_mm"),
            avg_pm10=avg("pm10"),
            avg_pm25=avg("pm2_5"),
            days=len(rows),
        ))
    return stats


# ── 리포트 생성 ────────────────────────────────────────────────────────────

def _pm_grade(pm10: float, pm25: float) -> str:
    if pm25 >= 76 or pm10 >= 151:
        return "🔴 매우나쁨"
    if pm25 >= 36 or pm10 >= 81:
        return "🟠 나쁨"
    if pm25 >= 16 or pm10 >= 31:
        return "🟡 보통"
    return "🟢 좋음"


def build_report(
    week: WeekRange,
    rss: dict[str, list[RssEntry]],
    weather: list[WeatherStats],
    generated_at: str,
) -> str:
    total_rss = sum(len(v) for v in rss.values())
    meta = {
        "week": week.label,
        "period": f"{week.start} ~ {week.end}",
        "generated_at": generated_at,
        "rss_total": total_rss,
        "weather_locations": len(weather),
    }
    lines = [frontmatter(meta), ""]
    lines += [
        f"# 주간 리포트 — {week.label}",
        f"> {week.start.strftime('%Y-%m-%d (%a)')} ~ {week.end.strftime('%Y-%m-%d (%a)')}",
        "",
    ]

    # ── 날씨 섹션 ─────────────────────────────────────────────────────────
    if weather:
        lines += ["## 🌤️ 날씨 요약", ""]
        lines += ["| 도시 | 평균기온 | 최고 | 최저 | 총강수량 | PM10 | PM2.5 | 미세먼지 |"]
        lines += ["|------|---------|------|------|---------|------|-------|---------|"]
        for w in weather:
            grade = _pm_grade(w.avg_pm10, w.avg_pm25)
            lines.append(
                f"| {w.location} "
                f"| {w.avg_temp}°C "
                f"| {w.max_temp}°C "
                f"| {w.min_temp}°C "
                f"| {w.total_precip}mm "
                f"| {w.avg_pm10} "
                f"| {w.avg_pm25} "
                f"| {grade} |"
            )
        lines.append("")
    else:
        lines += ["## 🌤️ 날씨 요약", "", "_이번 주 날씨 데이터 없음_", ""]

    # ── RSS 섹션 ──────────────────────────────────────────────────────────
    lines += ["## 📰 RSS 하이라이트", ""]
    if rss:
        lines += [f"이번 주 총 **{total_rss}건** 수집", ""]
        lines += ["| 피드 | 수집 건수 |"]
        lines += ["|------|---------|"]
        for feed, entries in sorted(rss.items(), key=lambda x: -len(x[1])):
            lines.append(f"| {feed} | {len(entries)}건 |")
        lines.append("")

        for feed, entries in sorted(rss.items(), key=lambda x: -len(x[1])):
            if not entries:
                continue
            lines += [f"### {feed}", ""]
            for e in entries[:5]:   # 피드별 상위 5개
                lines.append(f"- [{e.title}]({e.link})")
            if len(entries) > 5:
                lines.append(f"- _...외 {len(entries) - 5}건_")
            lines.append("")
    else:
        lines += ["_이번 주 RSS 데이터 없음_", ""]

    return "\n".join(lines)


# ── 메인 ──────────────────────────────────────────────────────────────────

def main() -> None:
    today = today_kst()
    week = previous_iso_week(today)
    generated_at = datetime.now(timezone.utc).isoformat()

    print(f"리포트 대상 주차: {week.label} ({week.start} ~ {week.end})")

    rss_data = collect_rss_week(week)
    weather_data = collect_weather_week(week)

    rss_total = sum(len(v) for v in rss_data.values())
    print(f"RSS: {rss_total}건 / 날씨: {len(weather_data)}개 도시")

    out_path = REPORTS_DIR / "weekly" / f"{week.label}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        build_report(week, rss_data, weather_data, generated_at),
        encoding="utf-8",
    )
    print(f"리포트 저장: {out_path}")


if __name__ == "__main__":
    main()
