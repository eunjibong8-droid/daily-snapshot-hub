"""스냅샷·상태 파일 경로 규칙."""
from pathlib import Path
from datetime import date as DateType

# repo 루트 = 이 파일 기준 3단계 위 (common → daily_hub → src → repo root)
REPO_ROOT = Path(__file__).resolve().parents[3]

SNAPSHOTS_DIR = REPO_ROOT / "snapshots"
REPORTS_DIR = REPO_ROOT / "reports"
STATE_DIR = REPO_ROOT / "state"
CONFIG_DIR = REPO_ROOT / "config"


def snapshot_path(module: str, date: DateType) -> Path:
    """snapshots/{module}/YYYY-MM-DD.md"""
    return SNAPSHOTS_DIR / module / f"{date.isoformat()}.md"


def monthly_snapshot_path(module: str, year_month: str) -> Path:
    """snapshots/{module}/YYYY-MM.csv (날씨 등 월별 누적용)"""
    return SNAPSHOTS_DIR / module / f"{year_month}.csv"


def state_path(name: str) -> Path:
    """state/{name}"""
    return STATE_DIR / name


def weekly_report_path(week: str) -> Path:
    """reports/weekly/YYYY-WNN.md"""
    return REPORTS_DIR / "weekly" / f"{week}.md"
