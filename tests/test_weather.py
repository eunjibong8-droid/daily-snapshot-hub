"""날씨 collector 단위 테스트."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from daily_hub.collectors.weather import (
    WeatherRow,
    append_rows,
    build_row,
)

# ── 픽스처 ────────────────────────────────────────────────────────────────

SAMPLE_LOC = {
    "name": "Seoul",
    "name_ko": "서울",
    "latitude": 37.5665,
    "longitude": 126.9780,
    "timezone": "Asia/Seoul",
}

SAMPLE_WEATHER = {
    "current": {
        "temperature_2m": 15.2,
        "apparent_temperature": 13.8,
        "relative_humidity_2m": 62,
        "precipitation": 0.0,
        "precipitation_probability": 10,
        "wind_speed_10m": 8.5,
        "uv_index": 3.2,
    },
    "daily": {
        "temperature_2m_max": [19.5],
        "temperature_2m_min": [10.1],
    },
}

SAMPLE_AIR = {
    "current": {
        "pm10": 32.0,
        "pm2_5": 18.5,
    }
}


# ── build_row 테스트 ───────────────────────────────────────────────────────

def test_build_row_basic():
    row = build_row(SAMPLE_LOC, SAMPLE_WEATHER, SAMPLE_AIR, "2026-04-18T00:00:00Z", "2026-04-18")
    assert row.location == "서울"
    assert row.temp_c == 15.2
    assert row.feels_like_c == 13.8
    assert row.temp_max_c == 19.5
    assert row.temp_min_c == 10.1
    assert row.humidity_pct == 62
    assert row.pm10 == 32.0
    assert row.pm2_5 == 18.5
    assert row.date == "2026-04-18"


def test_build_row_missing_fields_defaults_to_zero():
    row = build_row(SAMPLE_LOC, {"current": {}, "daily": {}}, {"current": {}}, "ts", "2026-04-18")
    assert row.temp_c == 0.0
    assert row.pm10 == 0.0


# ── append_rows 테스트 ────────────────────────────────────────────────────

def test_append_rows_creates_csv_with_header(tmp_path):
    with patch("daily_hub.collectors.weather.SNAPSHOTS_DIR", tmp_path):
        row = WeatherRow(
            date="2026-04-18", location="서울",
            temp_c=15.2, feels_like_c=13.8,
            temp_max_c=19.5, temp_min_c=10.1,
            humidity_pct=62, precip_mm=0.0,
            precip_prob_pct=10, wind_kmh=8.5,
            uv_index=3.2, pm10=32.0, pm2_5=18.5,
            collected_at="2026-04-18T00:00:00Z",
        )
        out = append_rows([row], "2026-04")
        content = out.read_text(encoding="utf-8")
        assert "date,location" in content
        assert "서울" in content
        assert "15.2" in content


def test_append_rows_accumulates_without_duplicate_header(tmp_path):
    with patch("daily_hub.collectors.weather.SNAPSHOTS_DIR", tmp_path):
        def make_row(date_str):
            return WeatherRow(
                date=date_str, location="서울",
                temp_c=10.0, feels_like_c=9.0,
                temp_max_c=15.0, temp_min_c=5.0,
                humidity_pct=50, precip_mm=0.0,
                precip_prob_pct=0, wind_kmh=5.0,
                uv_index=1.0, pm10=20.0, pm2_5=10.0,
                collected_at="ts",
            )
        append_rows([make_row("2026-04-18")], "2026-04")
        append_rows([make_row("2026-04-19")], "2026-04")

        path = tmp_path / "weather" / "2026-04.csv"
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        # 헤더 1줄 + 데이터 2줄
        assert len(lines) == 3
        assert lines[0].startswith("date,")
