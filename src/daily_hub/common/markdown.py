"""Markdown 생성 헬퍼."""
from datetime import date as DateType
from typing import Any


def frontmatter(meta: dict[str, Any]) -> str:
    """YAML frontmatter 블록 생성."""
    lines = ["---"]
    for key, value in meta.items():
        lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def truncate(text: str, max_len: int = 200) -> str:
    """텍스트를 max_len 자로 자르고 말줄임표 추가."""
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + "…"


def section_header(title: str, level: int = 2) -> str:
    return f"{'#' * level} {title}"


def horizontal_rule() -> str:
    return "\n---\n"
