# daily-snapshot-hub

GitHub Actions 기반 일일 데이터 수집·아카이빙 허브.
여러 수집 모듈을 독립적으로 운영하며, 수집 결과를 repo에 커밋해 쌓아둡니다.

## 아키텍처

```
daily-snapshot-hub/
├── .github/workflows/
│   ├── _shared-commit.yml   # 재사용 워크플로우 (커밋·푸시 공통화)
│   ├── rss.yml              # Phase 1 — RSS 다이제스트
│   ├── weather.yml          # Phase 2 — 날씨·미세먼지 (예정)
│   ├── aws-cost.yml         # Phase 3 — AWS 비용 스냅샷 (예정)
│   └── weekly-report.yml    # Phase 4 — 주간 통합 리포트 (예정)
├── src/daily_hub/
│   ├── common/              # dates, paths, markdown 유틸
│   ├── collectors/          # 모듈별 수집기
│   └── reporters/           # 크로스 모듈 집계 (Phase 4)
├── snapshots/               # 수집 결과 (git 커밋됨)
├── reports/weekly/          # 주간 리포트
├── state/                   # 내부 상태 (last-seen 등)
└── config/                  # 피드 목록, 위치 설정 등
```

## 모듈

### Phase 1 · RSS 다이제스트

구독 피드의 새 글을 매일 `snapshots/rss/YYYY-MM-DD.md`에 저장합니다.

| 피드 | 카테고리 |
|------|---------|
| Hacker News Top | 기술 뉴스 |
| GitHub Blog | 개발 플랫폼 |
| AWS Blog | 클라우드 |
| Real Python | Python |
| Martin Fowler | 아키텍처 |
| Anthropic News | AI |
| The Pragmatic Engineer | 엔지니어링 |
| InfoQ | 기술 전반 |

피드 추가·제거: `config/rss-feeds.yml` 수정 (코드 변경 불필요).

## 로컬 실행

```bash
# 의존성 설치 (uv 필요)
uv sync

# RSS 수집 수동 실행
uv run python -m daily_hub.collectors.rss

# 테스트
uv run pytest
```

## GitHub Actions

### 수동 트리거 (첫 테스트용)
Actions 탭 → **RSS Daily Snapshot** → **Run workflow**

### 자동 스케줄 활성화
`rss.yml`의 `schedule` 블록 주석 해제:
```yaml
schedule:
  - cron: '0 23 * * *'   # 매일 KST 08:00
```

## 설계 원칙

- **실패 격리**: 하나의 피드 수집 실패가 나머지에 영향 없음
- **재사용 워크플로우**: `_shared-commit.yml`을 함수처럼 호출해 커밋 로직 중복 제거
- **상태 분리**: `snapshots/`(결과물) vs `state/`(내부 상태)
- **Public-safe**: secrets는 `secrets.` 네임스페이스만 사용, 민감 정보 커밋 금지

## 로드맵

| Phase | 내용 |
|-------|------|
| ✅ Phase 1 | RSS 다이제스트 + 허브 뼈대 |
| Phase 2 | 날씨·미세먼지 로거 |
| Phase 3 | AWS 비용 스냅샷 |
| Phase 4 | 주간 통합 리포트 (크로스 모듈 집계) |
