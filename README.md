# game-trend-radar

게임 산업 보고서·전망·뉴스를 RSS로 자동 수집해 누적하고, 직접 골라 남기는 개인용 아카이브.

## 처음 세팅

1. 이 파일들을 새 GitHub 저장소(public)에 올립니다.
2. `Settings → Actions → General → Workflow permissions`에서
   **Read and write permissions**를 켭니다. (봇이 커밋해야 합니다)
3. `Actions` 탭 → `collect` → **Run workflow**로 한 번 수동 실행합니다.
4. 실행 로그를 엽니다. 여기가 중요합니다 —
   **어떤 피드가 실패했는지 그대로 찍힙니다.** 실패한 주소만 고치면 됩니다.
5. `feeds.yaml`의 KOCCA 항목에 공식 RSS 주소를 채웁니다.
   https://www.kocca.kr/kocca/subPage.do?menuNo=204917 에서 '정기간행물' 피드 주소를 복사하세요.

이후로는 한국시간 09시·21시에 알아서 돕니다.

## 쌓이는 모양

```
data/
  items/
    2026-09.json    ← 그 달에 발행된 항목들 (최신순)
    2026-10.json
  seen.json         ← 본 적 있는 id 목록. 중복 방지용
```

`state` 필드가 `new` / `keep` / `drop` 세 값을 가집니다.
수집기는 **기존 항목을 절대 건드리지 않습니다.** 한 번 keep/drop 한 건 그대로 남습니다.

## 로컬에서 돌려보기

```bash
pip install feedparser pyyaml requests
python collect.py --dry-run    # 파일 안 건드리고 결과만 확인
python collect.py              # 실제 수집
```

## 유입량이 많으면

`feeds.yaml`의 `keyword_filter`에 단어를 넣으면 제목·요약에 하나라도 걸리는 것만 담습니다.
일단 필터 없이 일주일 돌려서 실제 유입량을 본 다음에 조이는 걸 권합니다.
