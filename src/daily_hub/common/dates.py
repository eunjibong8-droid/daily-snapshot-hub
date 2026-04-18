"""KST 기준 날짜·주차 계산 유틸."""
from datetime import datetime, timezone, timedelta
from datetime import date as DateType

KST = timezone(timedelta(hours=9))


def now_kst() -> datetime:
    return datetime.now(KST)


def today_kst() -> DateType:
    return now_kst().date()


def year_month_kst() -> str:
    """'YYYY-MM' 형식."""
    return today_kst().strftime("%Y-%m")


def iso_week_kst() -> str:
    """'YYYY-WNN' 형식. 예: '2026-W16'"""
    d = today_kst()
    return f"{d.isocalendar().year}-W{d.isocalendar().week:02d}"


def format_date(d: DateType) -> str:
    return d.isoformat()
