"""RSS 피드 수집 모듈.

Usage:
    uv run python -m daily_hub.collectors.rss
"""
from __future__ import annotations

import json
import sys
from calendar import timegm
from datetime import datetime, timezone
from pathlib import Path
from time import struct_time
from typing import TypedDict

import feedparser
import yaml

from daily_hub.common.dates import today_kst
from daily_hub.common.markdown import frontmatter, horizontal_rule, truncate
from daily_hub.common.paths import CONFIG_DIR, snapshot_path, state_path

STATE_FILE = state_path("rss-last-seen.json")
CONFIG_FILE = CONFIG_DIR / "rss-feeds.yml"
SUMMARY_MAX_LEN = 200


# ── 타입 정의 ──────────────────────────────────────────────────────────────

class FeedConfig(TypedDict):
    name: str
    url: str
    category: str


class Entry(TypedDict):
    title: str
    link: str
    summary: str
    published_utc: str  # ISO 8601


# ── 상태 관리 ──────────────────────────────────────────────────────────────

def load_state() -> dict[str, str]:
    """피드별 마지막 수집 시각 (ISO 8601 UTC) 반환. 없으면 빈 dict."""
    if STATE_FILE.exists() and STATE_FILE.stat().st_size > 2:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict[str, str]) -> None:
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── 피드 설정 로드 ─────────────────────────────────────────────────────────

def load_feed_configs() -> list[FeedConfig]:
    raw = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8"))
    return raw["feeds"]


# ── 수집 ──────────────────────────────────────────────────────────────────

def _struct_to_dt(t: struct_time | None) -> datetime | None:
    """feedparser의 time.struct_time → timezone-aware datetime (UTC)."""
    if t is None:
        return None
    return datetime.fromtimestamp(timegm(t), tz=timezone.utc)


def collect_feed(
    feed_cfg: FeedConfig,
    last_seen_iso: str | None,
) -> list[Entry]:
    """피드에서 last_seen 이후의 새 항목만 반환."""
    parsed = feedparser.parse(feed_cfg["url"])

    last_seen_dt: datetime | None = None
    if last_seen_iso:
        last_seen_dt = datetime.fromisoformat(last_seen_iso)

    entries: list[Entry] = []
    for e in parsed.entries:
        pub_dt = _struct_to_dt(getattr(e, "published_parsed", None))

        # 발행일 없으면 첫 수집 시 포함, 이후엔 스킵 (중복 방지)
        if pub_dt is None:
            if last_seen_dt is not None:
                continue
            pub_iso = datetime.now(timezone.utc).isoformat()
        else:
            pub_iso = pub_dt.isoformat()
            if last_seen_dt and pub_dt <= last_seen_dt:
                continue

        link = getattr(e, "link", None) or getattr(e, "id", "")
        if not link:
            continue

        summary_raw = getattr(e, "summary", "") or getattr(e, "description", "")
        entries.append(
            Entry(
                title=e.get("title", "(제목 없음)").strip(),
                link=link,
                summary=truncate(summary_raw, SUMMARY_MAX_LEN),
                published_utc=pub_iso,
            )
        )

    return entries


# ── Markdown 생성 ──────────────────────────────────────────────────────────

def _format_entry(entry: Entry) -> str:
    lines = [
        f"### [{entry['title']}]({entry['link']})",
        f"> {entry['published_utc'][:10]}",
        "",
    ]
    if entry["summary"]:
        lines.append(entry["summary"])
        lines.append("")
    return "\n".join(lines)


def build_snapshot(
    date_str: str,
    collected_at: str,
    results: dict[str, list[Entry]],
    failed: list[tuple[str, str]],
) -> str:
    total = sum(len(v) for v in results.values())
    meta = {
        "date": date_str,
        "collected_at": collected_at,
        "total_entries": total,
        "feeds_ok": len(results),
        "feeds_failed": len(failed),
    }
    parts = [frontmatter(meta), "", f"# RSS Daily Digest — {date_str}", ""]

    for feed_name, entries in results.items():
        if not entries:
            parts.append(f"## {feed_name} _(새 글 없음)_\n")
            continue
        parts.append(f"## {feed_name} ({len(entries)}건)\n")
        for entry in entries:
            parts.append(_format_entry(entry))
        parts.append(horizontal_rule())

    if failed:
        parts.append("## ⚠️ 수집 실패\n")
        for name, reason in failed:
            parts.append(f"- **{name}**: {reason}")
        parts.append("")

    return "\n".join(parts)


# ── 메인 ──────────────────────────────────────────────────────────────────

def main() -> None:
    today = today_kst()
    collected_at = datetime.now(timezone.utc).isoformat()

    feeds = load_feed_configs()
    state = load_state()

    results: dict[str, list[Entry]] = {}
    failed: list[tuple[str, str]] = []
    new_state: dict[str, str] = dict(state)

    for feed_cfg in feeds:
        name = feed_cfg["name"]
        try:
            entries = collect_feed(feed_cfg, state.get(name))
            results[name] = entries
            new_state[name] = collected_at
            print(f"[OK] {name}: {len(entries)}건")
        except Exception as exc:  # noqa: BLE001
            failed.append((name, str(exc)))
            print(f"[FAIL] {name}: {exc}", file=sys.stderr)

    out_path = snapshot_path("rss", today)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        build_snapshot(today.isoformat(), collected_at, results, failed),
        encoding="utf-8",
    )
    print(f"\n스냅샷 저장: {out_path}")

    save_state(new_state)

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
