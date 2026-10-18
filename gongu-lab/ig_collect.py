#!/usr/bin/env python3
"""
gongu-lab: 인스타그램 레퍼런스 계정의 캐러셀(과 일반 게시물) 수집기.
슬라이드 이미지를 전부 내려받고 좋아요·댓글·캡션·게시일을 posts.json 에 정규화해 저장한다.

수집 경로 (위에서 아래로 시도, 모자란 장수는 다음 경로가 채운다)
  1. graph : 공식 Graph API business_discovery. 환경변수 IG_USER_ID, IG_ACCESS_TOKEN 이 있을 때.
             대상이 비즈니스·크리에이터 계정이어야 한다. children(슬라이드)까지 받을 수 있는지는
             공식 문서에 명시가 없어 필드를 줄여가며 재시도하고, 어디까지 받았는지 level 로 기록한다.
  2. web   : Playwright + 로빈님 PC 의 로그인 프로필. 게시물 페이지의 JSON 에서 carousel_media 를 읽고,
             JSON 이 막히면 화면에서 '다음' 버튼을 눌러가며 슬라이드를 캡처한다.

저장 위치
  data/ig/<핸들>/posts.json            정규화된 게시물 목록
  data/ig/<핸들>/<shortcode>/slide-01.jpg …  슬라이드 이미지

사용 예
  python3 ig_collect.py --login                      # 인스타 로그인 프로필 만들기 (처음 한 번, 창이 열림)
  python3 ig_collect.py 핸들                         # 자동 선택 (graph 가능하면 graph, 부족분은 web 으로 보충)
  python3 ig_collect.py 핸들 --source web --max-posts 30 --show
  python3 ig_collect.py --all                        # references.json 의 instagram 채널 전부
  python3 ig_collect.py 핸들 --repair                # 슬라이드가 모자란 캐러셀만 다시 시도
  python3 ig_collect.py 핸들 --debug --show          # 응답 JSON 을 data/ig/_debug/ 에 저장 (막혔을 때 원인 확인용)
  python3 ig_collect.py --whoami                     # 토큰으로 IG_USER_ID(내 인스타 계정 ID) 찾기
  python3 ig_collect.py --check 핸들                 # 공식 API 로 이 계정의 캐러셀 슬라이드가 실제로 오는지 시험 (저장 안 함)

주의: 로그인 계정으로 짧은 시간에 많이 읽으면 인스타가 제한을 걸 수 있다. 게시물 사이 4~9초를 두고 기본 40개까지만 읽는다.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data" / "ig"
PROFILE_DIR = HERE / ".browser-profile"
REFS = HERE / "references.json"
KST = timezone(timedelta(hours=9))
GRAPH_VERSION = os.environ.get("IG_GRAPH_VERSION", "v25.0")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

BASE = "id,media_type,media_product_type,caption,timestamp,permalink,like_count,comments_count"
FIELD_LADDER = [  # 앞에서부터 시도, 400 오류가 나면 한 단계씩 줄인다
    ("full", BASE + ",media_url,thumbnail_url,children{media_type,media_url}"),
    ("no_children", BASE + ",media_url,thumbnail_url"),
    ("minimal", BASE),
]
LONG_SLEEP = (4.0, 9.0)


# ---------------------------------------------------------------- 공통

def now_kst() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def shortcode_from_url(url: str) -> str:
    m = re.search(r"instagram\.com/(?:[^/]+/)?(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)", url or "")
    return m.group(1) if m else ""


def clean_handle(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^https?://(www\.)?instagram\.com/", "", raw)
    return raw.lstrip("@").split("/")[0].split("?")[0]


def load_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def expected_count(post: dict) -> int | None:
    return post.get("expected_slides")


def slides_complete(post: dict, post_dir: Path) -> bool:
    """캐러셀이 아니면 True. 캐러셀이면 기대 장수만큼 파일이 내려받아졌는지."""
    if post.get("kind") != "carousel":
        return True
    slides = post.get("slides") or []
    exp = expected_count(post)
    if not slides or (exp and len(slides) < exp):
        return False
    return all(s.get("file") and (post_dir / s["file"]).exists() and (post_dir / s["file"]).stat().st_size > 0
               for s in slides)


# ---------------------------------------------------------------- 1. Graph API

def http_get_json(url: str, timeout: int = 40) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def graph_page(ig_user_id: str, token: str, target: str, fields: str, limit: int, after: str | None) -> dict:
    media = f"media.limit({limit})" + (f".after({after})" if after else "")
    q = f"business_discovery.username({target}){{username,name,followers_count,media_count,{media}{{{fields}}}}}"
    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{ig_user_id}?" + urllib.parse.urlencode(
        {"fields": q, "access_token": token})
    return http_get_json(url)


def norm_graph(m: dict) -> dict:
    permalink = m.get("permalink", "")
    mt = m.get("media_type")
    if mt == "CAROUSEL_ALBUM":
        kind = "carousel"
    elif m.get("media_product_type") == "REELS":
        kind = "reel"
    elif mt == "VIDEO":
        kind = "video"
    else:
        kind = "image"
    children = (m.get("children") or {}).get("data", [])
    if kind == "carousel":
        slides = [{"index": i, "kind": "video" if c.get("media_type") == "VIDEO" else "image", "url": c.get("media_url")}
                  for i, c in enumerate(children, 1)]
    elif kind == "image" and m.get("media_url"):
        slides = [{"index": 1, "kind": "image", "url": m["media_url"]}]
    else:
        slides = []
    return {
        "shortcode": shortcode_from_url(permalink) or m.get("id", ""),
        "url": permalink,
        "kind": kind,
        "taken_at": m.get("timestamp"),
        "caption": (m.get("caption") or "").strip(),
        "likes": m.get("like_count"),  # 계정이 좋아요 수를 숨기면 None
        "comments": m.get("comments_count"),
        "expected_slides": len(children) if children else None,
        "slides": slides,
        "thumb": m.get("thumbnail_url") or m.get("media_url"),
        "source": "graph",
    }


def collect_graph(handle: str, max_posts: int) -> tuple[dict, list[dict], str]:
    ig_user_id, token = os.environ.get("IG_USER_ID", ""), os.environ.get("IG_ACCESS_TOKEN", "")
    if not (ig_user_id and token):
        raise RuntimeError("IG_USER_ID / IG_ACCESS_TOKEN 환경변수가 없습니다")
    profile: dict = {}
    for level, fields in FIELD_LADDER:
        posts: list[dict] = []
        after = None
        try:
            while len(posts) < max_posts:
                data = graph_page(ig_user_id, token, handle, fields, min(25, max_posts - len(posts)), after)
                bd = data.get("business_discovery") or {}
                profile = {k: bd.get(k) for k in ("username", "name", "followers_count", "media_count")}
                media = bd.get("media") or {}
                posts += [norm_graph(m) for m in media.get("data", [])]
                after = ((media.get("paging") or {}).get("cursors") or {}).get("after")
                if not after or not media.get("data"):
                    break
            return profile, posts[:max_posts], level
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:300]
            if e.code == 400 and level != FIELD_LADDER[-1][0]:
                print(f"[graph] '{level}' 필드 거절됨 → 줄여서 재시도: {body}", file=sys.stderr)
                continue
            raise RuntimeError(f"Graph API 오류 {e.code}: {body}") from e
    raise RuntimeError("Graph API 필드 단계를 모두 실패")


# ---------------------------------------------------------------- 2. 웹 (Playwright)

def best_candidate(item: dict) -> dict | None:
    cands = (item.get("image_versions2") or {}).get("candidates") or []
    return max(cands, key=lambda c: (c.get("width") or 0) * (c.get("height") or 0), default=None)


def norm_web(d: dict) -> dict:
    """인스타 웹 JSON 의 미디어 객체 하나를 정규화한다. carousel_media 가 있으면 슬라이드로 펼친다."""
    cm = d.get("carousel_media") or []
    items = cm if cm else [d]
    slides = []
    for i, it in enumerate(items, 1):
        cand = best_candidate(it)
        is_video = bool(it.get("video_versions"))
        slides.append({
            "index": i,
            "kind": "video" if is_video else "image",
            "url": (cand or {}).get("url"),
            "video_url": ((it.get("video_versions") or [{}])[0]).get("url") if is_video else None,
            "width": (cand or {}).get("width"), "height": (cand or {}).get("height"),
            "alt": it.get("accessibility_caption"),
        })
    pt = d.get("product_type")
    if cm or pt == "carousel_container":
        kind = "carousel"
    elif pt == "clips":
        kind = "reel"
    else:
        kind = "video" if d.get("video_versions") else "image"
    hidden = d.get("like_and_view_counts_disabled")
    return {
        "shortcode": d.get("code", ""),
        "url": f"https://www.instagram.com/p/{d.get('code', '')}/",
        "kind": kind,
        "taken_at": datetime.fromtimestamp(d["taken_at"], timezone.utc).isoformat() if d.get("taken_at") else None,
        "caption": ((d.get("caption") or {}).get("text") or "").strip(),
        "likes": None if hidden else d.get("like_count"),
        "comments": d.get("comment_count"),
        "expected_slides": d.get("carousel_media_count") or (len(cm) or None),
        "slides": slides if kind in ("carousel", "image") else [],
        "thumb": None,
        "source": "web",
    }


def find_media(node, code: str, acc: list) -> list:
    if isinstance(node, dict):
        if node.get("code") == code and any(k in node for k in ("carousel_media", "image_versions2", "video_versions")):
            acc.append(node)
        for v in node.values():
            find_media(v, code, acc)
    elif isinstance(node, list):
        for v in node:
            find_media(v, code, acc)
    return acc


def richest(cands: list[dict]) -> dict | None:
    """같은 게시물이 여러 응답에 나오면 슬라이드·카운트 정보가 가장 많은 것을 쓴다."""
    def weight(d):
        return (len(d.get("carousel_media") or []), "like_count" in d, "caption" in d)
    return max(cands, key=weight, default=None)


def need_playwright():
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        print("playwright 가 없습니다. 먼저:\n  pip install playwright\n  python3 -m playwright install chromium", file=sys.stderr)
        sys.exit(2)


def web_login() -> None:
    need_playwright()
    from playwright.sync_api import sync_playwright
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(PROFILE_DIR), headless=False, locale="ko-KR")
        page = ctx.new_page()
        page.goto("https://www.instagram.com/accounts/login/", wait_until="domcontentloaded")
        print("열린 창에서 인스타그램에 로그인하세요. 피드가 보이면 이 터미널에서 Enter 를 누르세요.")
        try:
            input()
        except EOFError:
            time.sleep(120)
        ctx.close()
    print(f"로그인 프로필 저장됨: {PROFILE_DIR}")


def web_list_codes(page, handle: str, max_posts: int) -> list[dict]:
    """프로필 격자에서 게시물 링크와 캐러셀 아이콘 여부를 모은다."""
    page.goto(f"https://www.instagram.com/{handle}/", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(4000)
    found: dict[str, dict] = {}
    stale = 0
    while len(found) < max_posts and stale < 4:
        before = len(found)
        tiles = page.evaluate("""() => [...document.querySelectorAll('a[href*="/p/"], a[href*="/reel/"]')].map(a => ({
            href: a.getAttribute('href'),
            carousel: !!a.querySelector('svg[aria-label="캐러셀"], svg[aria-label="Carousel"]'),
            reel: a.getAttribute('href').includes('/reel/') || !!a.querySelector('svg[aria-label="릴스"], svg[aria-label="Reel"], svg[aria-label="Clip"]')
        }))""")
        for t in tiles:
            code = shortcode_from_url("https://www.instagram.com" + t["href"])
            if code and code not in found:
                found[code] = t
        stale = stale + 1 if len(found) == before else 0
        page.mouse.wheel(0, 3000)
        page.wait_for_timeout(1800)
    return list(found.items())[:max_posts]


def web_fetch_post(ctx, code: str, debug_dir: Path | None) -> tuple[dict | None, list[dict]]:
    """게시물 페이지를 열어 (정규화된 게시물, DOM 폴백 슬라이드) 를 돌려준다."""
    page = ctx.new_page()
    hits: list[dict] = []

    def on_response(resp):
        try:
            if "json" not in resp.headers.get("content-type", "") and "/graphql" not in resp.url and "/api/" not in resp.url:
                return
            txt = resp.text()
        except Exception:
            return
        if code not in txt:
            return
        if debug_dir:
            debug_dir.mkdir(parents=True, exist_ok=True)
            (debug_dir / f"{code}_{len(list(debug_dir.glob(code + '_*')))}.json").write_text(txt[:2_000_000], encoding="utf-8")
        for chunk in ([txt] if txt.lstrip().startswith(("{", "[")) else []) + txt.splitlines():
            try:
                find_media(json.loads(chunk), code, hits)
            except (json.JSONDecodeError, RecursionError):
                continue

    page.on("response", on_response)
    page.goto(f"https://www.instagram.com/p/{code}/", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(5000)
    for txt in page.eval_on_selector_all('script[type="application/json"]', "els => els.map(e => e.textContent)"):
        if txt and code in txt:
            try:
                find_media(json.loads(txt), code, hits)
            except json.JSONDecodeError:
                pass
    best = richest(hits)
    post = norm_web(best) if best else None
    dom_slides: list[dict] = []
    if post is None or (post["kind"] == "carousel" and not any(s.get("url") for s in post["slides"])):
        dom_slides = dom_capture(page)
    page.close()
    return post, dom_slides


def dom_capture(page) -> list[dict]:
    """JSON 을 못 읽었을 때: '다음' 버튼을 누르며 보이는 큰 이미지 주소와 화면 캡처를 모은다."""
    seen: list[str] = []
    for _ in range(25):
        srcs = page.evaluate("""() => [...document.querySelectorAll('article img, main img')]
            .filter(i => i.naturalWidth >= 300 && !/프로필 사진|profile picture/i.test(i.alt || ''))
            .map(i => i.currentSrc || i.src)""")
        for s in srcs:
            if s not in seen:
                seen.append(s)
        nxt = page.query_selector('button[aria-label="다음"], button[aria-label="Next"]')
        if not nxt:
            break
        nxt.click()
        page.wait_for_timeout(700)
    return [{"index": i, "kind": "image", "url": u} for i, u in enumerate(seen, 1)]


def download(url: str, dest: Path, ctx=None) -> bool:
    """이미지를 dest(확장자 제외) 로 저장. 성공하면 최종 파일명을 dest 옆에 만들고 True."""
    try:
        if ctx is not None:
            r = ctx.request.get(url)
            body, ctype = r.body(), r.headers.get("content-type", "")
            if not r.ok:
                return False
        else:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.instagram.com/"})
            with urllib.request.urlopen(req, timeout=40) as resp:
                body, ctype = resp.read(), resp.headers.get("content-type", "")
    except Exception:
        return False
    if not body:
        return False
    ext = ".png" if "png" in ctype else ".webp" if "webp" in ctype else ".jpg"
    dest.with_suffix(ext).write_bytes(body)
    return True


def save_slides(post: dict, post_dir: Path, ctx=None) -> None:
    """slides[].url 을 내려받아 slides[].file 에 파일명을 적는다. 이미 받은 파일은 건너뛴다."""
    post_dir.mkdir(parents=True, exist_ok=True)
    for s in post.get("slides", []):
        stem = post_dir / f"slide-{s['index']:02d}"
        existing = next((p for p in post_dir.glob(f"slide-{s['index']:02d}.*") if p.stat().st_size > 0), None)
        if existing:
            s["file"] = existing.name
            continue
        if not s.get("url"):
            continue
        # 그래프 경로의 CDN 주소는 로그인 없이 받아지는 경우가 많아 먼저 시도하고, 안 되면 브라우저 쿠키로 시도
        ok = download(s["url"], stem) or (ctx is not None and download(s["url"], stem, ctx))
        if ok:
            s["file"] = next(post_dir.glob(f"slide-{s['index']:02d}.*")).name


# ---------------------------------------------------------------- 병합·실행

def merge_post(old: dict | None, new: dict) -> dict:
    """새로 읽은 값으로 갱신하되, 이미 받은 슬라이드 파일명과 이전 지표 기록은 보존한다."""
    if not old:
        new["metrics_log"] = [{"at": now_kst(), "likes": new.get("likes"), "comments": new.get("comments")}]
        return new
    merged = {**old, **{k: v for k, v in new.items() if v not in (None, "", [])}}
    old_files = {s["index"]: s.get("file") for s in old.get("slides", [])}
    for s in merged.get("slides", []):
        if not s.get("file") and old_files.get(s["index"]):
            s["file"] = old_files[s["index"]]
    if (new.get("slides") and len(old.get("slides", [])) > len(new["slides"])):
        merged["slides"] = old["slides"]  # 더 많이 받아둔 쪽을 유지
    log = old.get("metrics_log", [])
    current = (new.get("likes"), new.get("comments"))
    if not log or current != (log[-1].get("likes"), log[-1].get("comments")):
        log.append({"at": now_kst(), "likes": new.get("likes"), "comments": new.get("comments")})
    merged["metrics_log"] = log[-20:]
    return merged


def run_handle(handle: str, args) -> int:
    out_dir = DATA / handle
    store = load_json(out_dir / "posts.json", {"handle": handle, "posts": []})
    by_code = {p["shortcode"]: p for p in store["posts"]}
    meta = {"source_level": None, "followers": store.get("followers")}
    new_posts: list[dict] = []

    want_graph = args.source in ("auto", "graph") and os.environ.get("IG_USER_ID") and os.environ.get("IG_ACCESS_TOKEN")
    if args.source == "graph" and not want_graph:
        print("graph 를 선택했지만 IG_USER_ID / IG_ACCESS_TOKEN 환경변수가 없습니다.", file=sys.stderr)
        return 3
    if want_graph and not args.repair:
        try:
            profile, new_posts, level = collect_graph(handle, args.max_posts)
            meta["source_level"] = f"graph:{level}"
            meta["followers"] = profile.get("followers_count") or meta["followers"]
            print(f"[graph] @{handle}: 게시물 {len(new_posts)}개, 필드 단계 '{level}'")
        except RuntimeError as e:
            print(f"[graph] 실패: {e}", file=sys.stderr)
            if args.source == "graph":
                return 3
    for p in new_posts:
        by_code[p["shortcode"]] = merge_post(by_code.get(p["shortcode"]), p)

    # 슬라이드가 모자란 캐러셀은 web 으로 채운다
    ctx_holder = {"pw": None, "ctx": None}

    def get_ctx():
        if ctx_holder["ctx"]:
            return ctx_holder["ctx"]
        need_playwright()
        from playwright.sync_api import sync_playwright
        if not PROFILE_DIR.exists():
            print("로그인 프로필이 없습니다. 먼저 --login 을 실행하세요.", file=sys.stderr)
            sys.exit(3)
        ctx_holder["pw"] = sync_playwright().start()
        ctx_holder["ctx"] = ctx_holder["pw"].chromium.launch_persistent_context(
            str(PROFILE_DIR), headless=not args.show, locale="ko-KR", user_agent=UA)
        return ctx_holder["ctx"]

    try:
        if args.source == "web" or (not want_graph and not args.repair):
            ctx = get_ctx()
            page = ctx.new_page()
            tiles = web_list_codes(page, handle, args.max_posts)
            page.close()
            meta["source_level"] = "web"
            print(f"[web] @{handle}: 격자에서 게시물 {len(tiles)}개 발견")
            for code, t in tiles:
                if code not in by_code:
                    by_code[code] = {"shortcode": code, "url": f"https://www.instagram.com/p/{code}/",
                                     "kind": "carousel" if t["carousel"] else ("reel" if t["reel"] else "image"),
                                     "slides": [], "source": "web-grid"}

        kinds = ("carousel",) if args.carousel_only else ("carousel", "image")
        todo = [c for c, p in by_code.items()
                if p.get("kind") in kinds and not slides_complete(p, out_dir / c)]
        todo = todo[: args.max_posts]
        if todo and args.no_download:
            print(f"[info] --no-download: 보충 대상 {len(todo)}개는 건너뜀")
            todo = []
        if todo:
            ctx = get_ctx()
            print(f"[web] 슬라이드 보충 대상 {len(todo)}개")
            for i, code in enumerate(todo, 1):
                if i > 1:
                    time.sleep(random.uniform(*LONG_SLEEP))
                try:
                    post, dom = web_fetch_post(ctx, code, DATA / "_debug" if args.debug else None)
                except Exception as e:  # 네트워크·렌더링 오류는 다음 게시물로
                    print(f"[warn] {code}: {e}", file=sys.stderr)
                    continue
                if post:
                    by_code[code] = merge_post(by_code.get(code), post)
                elif dom:
                    old = by_code[code]
                    old["slides"], old["kind"], old["source"] = dom, "carousel" if len(dom) > 1 else old.get("kind", "image"), "web-dom"
                    old["expected_slides"] = old.get("expected_slides") or len(dom)
                else:
                    print(f"[warn] {code}: JSON 도 화면도 못 읽음 (--debug --show 로 확인)", file=sys.stderr)
                    continue
                save_slides(by_code[code], out_dir / code, ctx_holder["ctx"])
        if not args.no_download:  # graph 로 받은 주소 중 아직 파일이 없는 것
            for code, p in by_code.items():
                if p.get("kind") in ("carousel", "image") and any(s.get("url") and not s.get("file") for s in p.get("slides", [])):
                    save_slides(p, out_dir / code, ctx_holder["ctx"])
    finally:
        if ctx_holder["ctx"]:
            ctx_holder["ctx"].close()
            ctx_holder["pw"].stop()

    posts = sorted(by_code.values(), key=lambda p: p.get("taken_at") or "", reverse=True)
    for p in posts:
        p["slides_complete"] = slides_complete(p, out_dir / p["shortcode"])
    store = {"handle": handle, "followers": meta["followers"], "collected_at": now_kst(),
             "source_level": meta["source_level"], "posts": posts}
    save_json(out_dir / "posts.json", store)

    car = [p for p in posts if p.get("kind") == "carousel"]
    bad = [p for p in car if not p["slides_complete"]]
    print(f"@{handle}: 게시물 {len(posts)}개 / 캐러셀 {len(car)}개 / 슬라이드 완전 수집 {len(car) - len(bad)}개 / 불완전 {len(bad)}개")
    for p in bad[:10]:
        print(f"  불완전: {p['shortcode']} (받은 {len([s for s in p.get('slides', []) if s.get('file')])}장, 기대 {p.get('expected_slides')})")
    if bad:
        print("  → `python3 ig_collect.py %s --repair` 로 다시 시도하거나 `--debug --show` 로 원인을 본다." % handle)
    return 0


def whoami() -> int:
    """토큰으로 연결된 페이지와 인스타 프로페셔널 계정 ID 를 보여준다."""
    token = os.environ.get("IG_ACCESS_TOKEN", "")
    if not token:
        print("IG_ACCESS_TOKEN 환경변수가 없습니다.", file=sys.stderr)
        return 3
    url = f"https://graph.facebook.com/{GRAPH_VERSION}/me/accounts?" + urllib.parse.urlencode(
        {"fields": "name,instagram_business_account{id,username}", "access_token": token})
    try:
        data = http_get_json(url)
    except urllib.error.HTTPError as e:
        print(f"오류 {e.code}: {e.read().decode('utf-8', errors='replace')[:300]}", file=sys.stderr)
        return 3
    pages = data.get("data", [])
    if not pages:
        print("연결된 페이스북 페이지가 없습니다. 인스타 계정을 페이지에 연결했는지, 토큰에 pages_show_list 권한이 있는지 확인하세요.")
        return 1
    found = False
    for pg in pages:
        ig = pg.get("instagram_business_account")
        if ig:
            found = True
            print(f"페이지 '{pg.get('name')}' → 인스타 @{ig.get('username')}  IG_USER_ID={ig.get('id')}")
        else:
            print(f"페이지 '{pg.get('name')}' → 연결된 인스타 계정 없음")
    return 0 if found else 1


def check_graph(handle: str) -> int:
    """공식 API 로 이 계정의 캐러셀 슬라이드가 실제로 오는지 시험한다. 파일은 저장하지 않는다."""
    try:
        profile, posts, level = collect_graph(handle, 12)
    except RuntimeError as e:
        print(f"실패: {e}", file=sys.stderr)
        print("→ 핸들 철자, 대상이 프로페셔널(비즈니스/크리에이터) 계정인지, 토큰 권한·만료를 확인하세요.")
        return 3
    car = [p for p in posts if p["kind"] == "carousel"]
    with_slides = [p for p in car if len(p["slides"]) > 1]
    print(f"@{handle}: 팔로워 {profile.get('followers_count')} · 최근 {len(posts)}개 중 캐러셀 {len(car)}개 · 허용된 필드 단계 '{level}'")
    hidden = sum(p["likes"] is None for p in posts)
    print(f"좋아요 수 숨김 게시물 {hidden}개 / 슬라이드 목록을 받은 캐러셀 {len(with_slides)}개")
    if car and len(with_slides) == len(car):
        print("판정: 공식 API 만으로 슬라이드 이미지까지 받을 수 있습니다. 로그인 브라우저는 필요 없습니다.")
    elif car:
        print("판정: 공식 API 로는 슬라이드 이미지가 오지 않습니다. 지표·캡션만 API 로 받고 슬라이드는 로그인 브라우저(--login)로 보충해야 합니다.")
    else:
        print("판정 보류: 최근 게시물에 캐러셀이 없습니다. 캐러셀이 있는 다른 계정으로 다시 시험하세요.")
    return 0


def handles_from_refs() -> list[str]:
    cfg = load_json(REFS, {"channels": []})
    return [clean_handle(c.get("handle") or c.get("id", "")) for c in cfg.get("channels", [])
            if c.get("platform") == "instagram" and c.get("enabled", True)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("handle", nargs="?", help="인스타그램 핸들 (@ 없이)")
    ap.add_argument("--login", action="store_true", help="인스타 로그인 프로필 만들기")
    ap.add_argument("--whoami", action="store_true", help="IG_ACCESS_TOKEN 으로 IG_USER_ID 찾기")
    ap.add_argument("--check", metavar="핸들", help="공식 API 로 캐러셀 슬라이드가 오는지 시험 (저장 안 함)")
    ap.add_argument("--all", action="store_true", help="references.json 의 instagram 채널 전부")
    ap.add_argument("--source", choices=["auto", "graph", "web"], default="auto")
    ap.add_argument("--max-posts", type=int, default=40)
    ap.add_argument("--carousel-only", action="store_true", help="보충 대상을 캐러셀로 한정")
    ap.add_argument("--no-download", action="store_true", help="지표·캡션만 갱신하고 이미지는 받지 않음")
    ap.add_argument("--repair", action="store_true", help="이미 수집한 게시물 중 슬라이드가 모자란 것만 다시 시도")
    ap.add_argument("--show", action="store_true", help="브라우저 창 보이기")
    ap.add_argument("--debug", action="store_true", help="응답 JSON 을 data/ig/_debug/ 에 저장")
    args = ap.parse_args()

    if args.login:
        web_login()
        return 0
    if args.whoami:
        return whoami()
    if args.check:
        return check_graph(clean_handle(args.check))
    handles = handles_from_refs() if args.all else ([clean_handle(args.handle)] if args.handle else [])
    if not handles:
        print("핸들을 주거나 references.json 에 platform=instagram 채널을 넣으세요.", file=sys.stderr)
        ap.print_help()
        return 1
    rc = 0
    for h in handles:
        rc = max(rc, run_handle(h, args))
    return rc


if __name__ == "__main__":
    sys.exit(main())
