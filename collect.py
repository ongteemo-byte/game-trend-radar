#!/usr/bin/env python3
"""
게임 산업 트렌드 수집기.

feeds.yaml 에 적힌 RSS/Atom 피드를 읽어서 data/items/YYYY-MM.json 에 누적합니다.
이미 본 항목은 data/seen.json 으로 걸러냅니다.
큐레이션 상태(state)는 절대 덮어쓰지 않습니다 — 한 번 keep/drop 한 건 그대로 남습니다.

사용법:
    python collect.py              # 수집
    python collect.py --dry-run    # 파일 안 건드리고 결과만 출력
"""

import argparse
import hashlib
import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import feedparser
import requests
import yaml

ROOT = Path(__file__).parent
FEEDS_FILE = ROOT / "feeds.yaml"
DATA_DIR = ROOT / "data"
ITEMS_DIR = DATA_DIR / "items"
SEEN_FILE = DATA_DIR / "seen.json"

USER_AGENT = "game-trend-radar/1.0 (+personal feed aggregator)"
TIMEOUT = 20
SUMMARY_LIMIT = 400

# 링크에 붙는 추적 파라미터. 같은 글이 다른 id 로 두 번 들어오는 걸 막습니다.
TRACKING_PARAMS = re.compile(
    r"^(utm_|fbclid|gclid|ref|ref_src|source|mc_cid|mc_eid|igshid)", re.I
)


def canonical(url: str) -> str:
    """추적 파라미터를 떼고 정규화한 URL. id 계산의 기준."""
    if not url:
        return ""
    parts = urlsplit(url.strip())
    kept = [
        pair
        for pair in parts.query.split("&")
        if pair and not TRACKING_PARAMS.match(pair.split("=", 1)[0])
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, "&".join(kept), "")
    )


def make_id(url: str, title: str) -> str:
    basis = canonical(url) or title.strip()
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]


def strip_html(raw: str) -> str:
    if not raw:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:SUMMARY_LIMIT]


def parse_date(entry) -> str:
    """published 를 ISO8601(UTC)로. 없으면 빈 문자열."""
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        value = getattr(entry, key, None)
        if value:
            try:
                dt = datetime(*value[:6], tzinfo=timezone.utc)
                return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            except (TypeError, ValueError):
                continue
    return ""


def fetch(url: str):
    """requests 로 받아서 feedparser 에 넘깁니다. UA 없으면 막는 사이트가 많습니다."""
    response = requests.get(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml, */*"},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return feedparser.parse(response.content)


def passes_filter(item: dict, keywords: list) -> bool:
    if not keywords:
        return True
    haystack = (item["title"] + " " + item["summary"]).lower()
    return any(word.lower() in haystack for word in keywords)


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"  ! {path} 파싱 실패 — 기본값으로 시작합니다", file=sys.stderr)
        return default


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="파일을 쓰지 않고 결과만 출력")
    args = parser.parse_args()

    config = yaml.safe_load(FEEDS_FILE.read_text(encoding="utf-8"))
    feeds = [f for f in config.get("feeds", []) if f.get("url")]
    keywords = config.get("keyword_filter") or []

    skipped = [f["name"] for f in config.get("feeds", []) if not f.get("url")]
    for name in skipped:
        print(f"[건너뜀] {name} — url 이 비어 있습니다")

    seen = set(load_json(SEEN_FILE, []))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    new_by_month: dict[str, list] = {}
    failures: list[tuple[str, str]] = []
    total_new = 0

    for feed in feeds:
        name, url = feed["name"], feed["url"]
        try:
            parsed = fetch(url)
        except Exception as exc:  # 한 피드가 죽어도 나머지는 계속 돌아야 합니다
            failures.append((name, str(exc)[:120]))
            print(f"[실패] {name}: {str(exc)[:120]}")
            continue

        if parsed.bozo and not parsed.entries:
            failures.append((name, "RSS 로 파싱되지 않음 (주소가 피드가 아닐 수 있습니다)"))
            print(f"[실패] {name}: 피드가 아니거나 형식이 깨졌습니다")
            continue

        count = 0
        for entry in parsed.entries:
            link = entry.get("link", "")
            title = strip_html(entry.get("title", "")) or "(제목 없음)"
            item_id = make_id(link, title)
            if item_id in seen:
                continue

            published = parse_date(entry)
            item = {
                "id": item_id,
                "source": name,
                "category": feed.get("category", "news"),
                "title": title,
                "link": link,
                "published": published,
                "collected_at": now,
                "summary": strip_html(
                    entry.get("summary", "") or entry.get("description", "")
                ),
                "state": "new",
            }
            if not passes_filter(item, keywords):
                continue

            month = (published or now)[:7]
            new_by_month.setdefault(month, []).append(item)
            seen.add(item_id)
            count += 1

        total_new += count
        print(f"[성공] {name}: 신규 {count}건 / 전체 {len(parsed.entries)}건")

    if args.dry_run:
        print(f"\n[dry-run] 신규 {total_new}건, 파일은 그대로 둡니다")
        return 0

    if total_new:
        ITEMS_DIR.mkdir(parents=True, exist_ok=True)
        for month, fresh in new_by_month.items():
            path = ITEMS_DIR / f"{month}.json"
            existing = load_json(path, [])
            merged = existing + fresh
            # 최신순 정렬. published 없는 건 뒤로.
            merged.sort(key=lambda x: x.get("published") or "", reverse=True)
            path.write_text(
                json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8"
            )
            print(f"  → {path.name}: +{len(fresh)}건 (누적 {len(merged)}건)")

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        SEEN_FILE.write_text(
            json.dumps(sorted(seen), ensure_ascii=False), encoding="utf-8"
        )

    print(f"\n신규 {total_new}건, 실패한 피드 {len(failures)}개")
    for name, reason in failures:
        print(f"  - {name}: {reason}")

    # 전부 실패하면 워크플로가 초록불로 넘어가지 않게 합니다.
    if feeds and len(failures) == len(feeds):
        print("\n모든 피드가 실패했습니다.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
