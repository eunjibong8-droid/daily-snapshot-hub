"""날씨·미세먼지 수집 모듈 (Open-Meteo API — 무료, API 키 불필요).

수집 항목:
  - 기온 (현재·최고·최저) / 체감온도
  - 강수량 / 강수확률
  - 풍속 / 습도 / 자외선 지수
  - 미세먼지 PM10 / 초미세먼지 PM2.5

저장 형식: snapshots/weather/YYYY-MM.csv (월별 누적)
매일 실행 시 해당 월 CSV 파일에 행 추가.

Usage:
    uv run python -m daily_hub.collectors.weather
"""
from __future__ import annotations

import csv
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import TypedDict

import httpx
import yaml

from daily_hub.common.dates import today_kst, year_month_kst
from daily_hub.common.paths import CONFIG_DIR, SNAPSHOTS_DIR

WEATHER_API = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_API = "https://air-quality-api.open-meteo.com/v1/air-quality"

CONFIG_FILE = CONFIG_DIR / "locations.yml"

CSV_FIELDS = [
    "date", "location", "temp_c", "feels_like_c",
    "temp_max_c", "temp_min_c", "humidity_pct",
    "precip_mm", "precip_prob_pct", "wind_kmh",
    "uv_index", "pm10", "pm2_5", "collected_at",
]


# ── 타입 정의 ──────────────────────────────────────────────────────────────

class LocationConfig(TypedDict):
    name: str
    name_ko: str
    latitude: float
    longitude: float
    timezone: str


@dataclass
class WeatherRow:
    date: str
    location: str
    temp_c: float
    feels_like_c: float
    temp_max_c: float
    temp_min_c: float
    humidity_pct: int
    precip_mm: float
    precip_prob_pct: int
    wind_kmh: float
    uv_index: float
    pm10: float
    pm2_5: float
    collected_at: str


# ── 설정 로드 ──────────────────────────────────────────────────────────────

def load_locations() -> list[LocationConfig]:
    raw = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8"))
    return raw["locations"]


# ── API 호출 ───────────────────────────────────────────────────────────────

def _fetch_weather(loc: LocationConfig) -> dict:
    params = {
        "latitude": loc["latitude"],
        "longitude": loc["longitude"],
        "timezone": loc["timezone"],
        "current": ",".join([
            "temperature_2m",
            "apparent_temperature",
            "relative_humidity_2m",
            "precipitation",
            "precipitation_probability",
            "wind_speed_10m",
            "uv_index",
        ]),
        "daily": "temperature_2m_max,temperature_2m_min",
        "forecast_days": 1,
    }
    resp = httpx.get(WEATHER_API, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _fetch_air_quality(loc: LocationConfig) -> dict:
    params = {
        "latitude": loc["latitude"],
        "longitude": loc["longitude"],
        "timezone": loc["timezone"],
        "current": "pm10,pm2_5",
    }
    resp = httpx.get(AIR_QUALITY_API, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


# ── 데이터 변환 ────────────────────────────────────────────────────────────

def _safe(data: dict, key: str, default=0.0):
    val = data.get(key)
    return val if val is not None else default


def build_row(
    loc: LocationConfig,
    weather_data: dict,
    air_data: dict,
    collected_at: str,
    date_str: str,
) -> WeatherRow:
    cur = weather_data.get("current", {})
    daily = weather_data.get("daily", {})
    air_cur = air_data.get("current", {})

    return WeatherRow(
        date=date_str,
        location=loc["name_ko"],
        temp_c=_safe(cur, "temperature_2m"),
        feels_like_c=_safe(cur, "apparent_temperature"),
        temp_max_c=(_safe(daily, "temperature_2m_max", [None])[0] or 0.0),
        temp_min_c=(_safe(daily, "temperature_2m_min", [None])[0] or 0.0),
        humidity_pct=int(_safe(cur, "relative_humidity_2m")),
        precip_mm=_safe(cur, "precipitation"),
        precip_prob_pct=int(_safe(cur, "precipitation_probability")),
        wind_kmh=_safe(cur, "wind_speed_10m"),
        uv_index=_safe(cur, "uv_index"),
        pm10=_safe(air_cur, "pm10"),
        pm2_5=_safe(air_cur, "pm2_5"),
        collected_at=collected_at,
    )


# ── CSV 저장 ───────────────────────────────────────────────────────────────

def _csv_path(year_month: str) -> Path:
    return SNAPSHOTS_DIR / "weather" / f"{year_month}.csv"


def append_rows(rows: list[WeatherRow], year_month: str) -> Path:
    path = _csv_path(year_month)
    path.parent.mkdir(parents=True, exist_ok=True)

    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if write_header:
            writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))
    return path


# ── 메인 ──────────────────────────────────────────────────────────────────

def main() -> None:
    today = today_kst()
    year_month = year_month_kst()
    collected_at = datetime.now(timezone.utc).isoformat()
    date_str = today.isoformat()

    locations = load_locations()
    rows: list[WeatherRow] = []
    failed: list[tuple[str, str]] = []

    for loc in locations:
        name = loc["name_ko"]
        try:
            weather_data = _fetch_weather(loc)
            air_data = _fetch_air_quality(loc)
            row = build_row(loc, weather_data, air_data, collected_at, date_str)
            rows.append(row)
            print(
                f"[OK] {name}: {row.temp_c}°C "
                f"(체감 {row.feels_like_c}°C) "
                f"PM10={row.pm10} PM2.5={row.pm2_5}"
            )
        except Exception as exc:  # noqa: BLE001
            failed.append((name, str(exc)))
            print(f"[FAIL] {name}: {exc}", file=sys.stderr)

    if rows:
        out_path = append_rows(rows, year_month)
        print(f"\n스냅샷 저장: {out_path}")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
