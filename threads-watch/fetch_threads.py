#!/usr/bin/env python3
"""
threads-watch: 스레드(Threads) 공개 채널의 새 글을 가져와 아직 보지 않은 글만 골라낸다.

동작 순서
  1. channels.json 에 적힌 핸들마다 RSSHub 미러에서 RSS 를 받는다.
  2. state/seen.json 에 기록된 글 ID 와 비교해 새 글만 남긴다.
  3. 새 글을 JSON 으로 stdout 에 출력한다. (--mark 를 주면 seen.json 도 갱신)
  4. 모든 미러가 실패한 핸들은 "fallback" 목록에 넣어 WebFetch 로 직접 읽으라고 알린다.

사용 예
  python3 fetch_threads.py                 # channels.json 전체, 새 글 출력만
  python3 fetch_threads.py --mark          # 출력 후 seen.json 갱신
  python3 fetch_threads.py --handle zuck   # 한 핸들만 시험 (seen.json 건드리지 않음)
  python3 fetch_threads.py --limit 15      # 핸들당 최대 글 수 (기본 20)
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHANNELS_FILE = HERE / "channels.json"
SEEN_FILE = HERE / "state" / "seen.json"

# 공개 RSSHub 미러. 앞에서부터 시도하고 처음 성공한 것을 쓴다.
# 미러가 죽으면 여기 목록만 고치면 된다. 경로 형식: /threads/<handle>
MIRRORS = [
    "https://rsshub.rssforever.com",
    "https://rsshub.pseudoyu.com",
    "https://rsshub.app",
]
UA = "Mozilla/5.0 (compatible; threads-watch/1.0; +https://github.com/Kimseangtae/-)"
TAG_RE = re.compile(r"<[^>]+>")


def load_json(path: Path, default):
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def clean_handle(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^https?://(www\.)?threads\.(net|com)/", "", raw)
    return raw.lstrip("@").split("/")[0].split("?")[0]


def fetch_rss(handle: str, timeout: int = 40) -> tuple[str | None, str | None]:
    """미러를 차례로 시도. (본문 XML, 사용한 미러) 를 돌려준다."""
    last_err = None
    for base in MIRRORS:
        url = f"{base}/threads/{handle}"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                if "<rss" in body or "<feed" in body:
                    return body, base
                last_err = f"{base}: RSS 형식 아님"
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            last_err = f"{base}: {e}"
    print(f"[warn] @{handle}: 모든 미러 실패 ({last_err})", file=sys.stderr)
    return None, None


def html_to_text(fragment: str) -> str:
    text = re.sub(r"</p>\s*<p>", "\n", fragment)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = TAG_RE.sub("", text)
    return html.unescape(text).strip()


def parse_items(xml_text: str, handle: str, limit: int) -> list[dict]:
    root = ET.fromstring(xml_text)
    channel = root.find("channel")
    if channel is None:
        return []
    items = []
    for it in channel.findall("item")[:limit]:
        link = (it.findtext("link") or it.findtext("guid") or "").strip()
        post_id = link.rstrip("/").split("/")[-1] if link else ""
        desc = it.findtext("description") or ""
        # description 첫 단락은 "@handle:" 이라 제거
        desc = re.sub(r"^<p><strong>@[^<]*</strong>:</p>", "", desc.strip())
        text = html_to_text(desc)
        has_media = bool(re.search(r"<(img|video)\b", desc))
        pub_raw = it.findtext("pubDate") or ""
        try:
            pub = parsedate_to_datetime(pub_raw).astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError):
            pub = pub_raw
        items.append(
            {
                "handle": handle,
                "id": post_id,
                "url": link,
                "published_utc": pub,
                "text": text,
                "has_media": has_media,
                "chars": len(text),
            }
        )
    return items


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--handle", help="channels.json 대신 이 핸들 하나만 (시험용, 상태 저장 안 함)")
    ap.add_argument("--mark", action="store_true", help="출력한 새 글을 seen.json 에 기록")
    ap.add_argument("--limit", type=int, default=20, help="핸들당 최대 글 수")
    ap.add_argument("--all", action="store_true", help="seen 여부 무시하고 전부 출력")
    args = ap.parse_args()

    if args.handle:
        handles = [clean_handle(args.handle)]
        args.mark = False
    else:
        cfg = load_json(CHANNELS_FILE, {"channels": []})
        handles = [clean_handle(c["handle"]) for c in cfg.get("channels", []) if c.get("enabled", True)]
        if not handles:
            print("[info] channels.json 에 감시할 채널이 없습니다.", file=sys.stderr)

    seen: dict[str, list[str]] = load_json(SEEN_FILE, {})
    out = {"fetched_at_utc": datetime.now(timezone.utc).isoformat(), "new_posts": [], "fallback": [], "sources": {}}

    for h in handles:
        xml_text, mirror = fetch_rss(h)
        if not xml_text:
            out["fallback"].append({"handle": h, "profile_url": f"https://www.threads.com/@{h}"})
            continue
        out["sources"][h] = mirror
        items = parse_items(xml_text, h, args.limit)
        already = set(seen.get(h, []))
        fresh = [i for i in items if args.all or (i["id"] and i["id"] not in already)]
        out["new_posts"].extend(fresh)
        if args.mark:
            merged = list(dict.fromkeys(list(already) + [i["id"] for i in items if i["id"]]))
            seen[h] = merged[-500:]  # 핸들당 최근 500개만 보관

    if args.mark and handles:
        save_json(SEEN_FILE, seen)

    out["new_posts"].sort(key=lambda p: p["published_utc"], reverse=True)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
