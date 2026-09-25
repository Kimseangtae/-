#!/usr/bin/env python3
"""
스레드 글 한 개의 본문 + 작성자 본인 답글 전체를 가져와 raw/<글ID>.md 로 저장한다.

로그인이 필요하다. 로빈님 PC 의 로그인된 브라우저 프로필(threads-watch/.browser-profile,
git 에 올라가지 않음)을 쓴다. 처음 한 번:

    python3 fetch_thread_full.py --login      # 창이 열리면 스레드에 로그인하고 창을 닫는다

이후:

    python3 fetch_thread_full.py https://www.threads.com/t/XXXX
    python3 fetch_thread_full.py https://www.threads.com/t/XXXX --json
    python3 fetch_thread_full.py --add https://www.threads.com/t/XXXX --report threads-watch/reports/2026-09-25.md
    python3 fetch_thread_full.py --pending    # 대기 글 전부 받기 → 답글 잡힌 글은 재분석 대상으로 출력

준비물: pip install playwright && python3 -m playwright install chromium

원리: 페이지에 심어진 데이터와 로딩 중 오가는 JSON 응답에서 thread_items 를 전부 모아
작성자 아이디가 같은 것만 시간순으로 정렬한다. 화면 구조가 바뀌어도 잘 버틴다.
전부 실패하면 화면 글자를 그대로 저장해 사람이 읽을 수 있게 한다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROFILE_DIR = HERE / ".browser-profile"
RAW_DIR = HERE / "raw"
PENDING_FILE = HERE / "state" / "pending_full.json"
KST = timezone(timedelta(hours=9))


def need_playwright():
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        print("playwright 가 없습니다. 먼저:\n  pip install playwright\n  python3 -m playwright install chromium", file=sys.stderr)
        sys.exit(2)


def find_thread_items(node, acc: list) -> list:
    if isinstance(node, dict):
        if isinstance(node.get("thread_items"), list):
            acc.extend(node["thread_items"])
        for v in node.values():
            find_thread_items(v, acc)
    elif isinstance(node, list):
        for v in node:
            find_thread_items(v, acc)
    return acc


def post_code(url: str) -> str:
    m = re.search(r"/(?:t|post)/([A-Za-z0-9_-]+)", url)
    return m.group(1) if m else re.sub(r"\W+", "_", url)[-24:]


def login():
    need_playwright()
    from playwright.sync_api import sync_playwright

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(PROFILE_DIR), headless=False, locale="ko-KR")
        page = ctx.new_page()
        page.goto("https://www.threads.com/login", wait_until="domcontentloaded")
        print("브라우저 창에서 스레드에 로그인하세요. 로그인 후 피드가 보이면 이 터미널에서 Enter 를 누르세요.")
        try:
            input()
        except EOFError:
            time.sleep(120)
        ctx.close()
    print(f"로그인 프로필 저장됨: {PROFILE_DIR}")


def fetch(url: str, headless: bool = True, wait_ms: int = 6000) -> dict:
    need_playwright()
    from playwright.sync_api import sync_playwright

    if not PROFILE_DIR.exists():
        print("로그인 프로필이 없습니다. 먼저 --login 을 실행하세요.", file=sys.stderr)
        sys.exit(3)

    collected: list = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(PROFILE_DIR), headless=headless, locale="ko-KR")
        page = ctx.new_page()

        def on_response(resp):
            ctype = resp.headers.get("content-type", "")
            if "json" in ctype or "/graphql" in resp.url or "/api/" in resp.url:
                try:
                    txt = resp.text()
                except Exception:
                    return
                if "thread_items" in txt:
                    try:
                        find_thread_items(json.loads(txt), collected)
                    except json.JSONDecodeError:
                        # 여러 JSON 이 줄바꿈으로 이어진 응답 처리
                        for line in txt.splitlines():
                            try:
                                find_thread_items(json.loads(line), collected)
                            except json.JSONDecodeError:
                                pass

        page.on("response", on_response)
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(wait_ms)
        # 답글을 더 불러오도록 몇 번 스크롤
        for _ in range(6):
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(1200)

        # 페이지에 심어진 데이터
        for txt in page.eval_on_selector_all("script[data-sjs]", "els => els.map(e => e.textContent)"):
            if txt and "thread_items" in txt:
                try:
                    find_thread_items(json.loads(txt), collected)
                except json.JSONDecodeError:
                    pass

        screen_text = page.evaluate("() => document.body.innerText")
        logged_in = "로그인" not in page.title() and "Log in" not in page.title()
        ctx.close()

    code = post_code(url)
    posts = []
    seen = set()
    for it in collected:
        p_ = it.get("post") or {}
        c = p_.get("code")
        if not c or c in seen:
            continue
        seen.add(c)
        posts.append(
            {
                "code": c,
                "user": (p_.get("user") or {}).get("username"),
                "taken_at": p_.get("taken_at"),
                "text": ((p_.get("caption") or {}).get("text") or "").strip(),
                "is_reply": bool((p_.get("text_post_app_info") or {}).get("reply_to_author")),
            }
        )
    root = next((x for x in posts if x["code"] == code), None)
    author = root["user"] if root else None
    author_posts = sorted(
        [x for x in posts if author and x["user"] == author],
        key=lambda x: x.get("taken_at") or 0,
    )
    others = [x for x in posts if x["user"] != author]
    return {
        "url": url,
        "code": code,
        "author": author,
        "logged_in_guess": logged_in,
        "root": root,
        "author_thread": author_posts,
        "other_replies": others[:30],
        "screen_text": screen_text,
        "fetched_at_kst": datetime.now(KST).isoformat(timespec="seconds"),
    }


def load_pending() -> list:
    if not PENDING_FILE.exists():
        return []
    return json.loads(PENDING_FILE.read_text(encoding="utf-8")).get("pending", [])


def save_pending(items: list) -> None:
    PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
    PENDING_FILE.write_text(
        json.dumps({"_설명": "답글을 못 읽고 분석한 글. PC 에서 --pending 으로 답글을 받으면 재분석 대상이 된다.", "pending": items},
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def add_pending(url: str, reason: str, report: str = "") -> None:
    items = load_pending()
    code = post_code(url)
    if any(x.get("code") == code for x in items):
        return
    items.append({"code": code, "url": url, "reason": reason, "report": report,
                  "added_kst": datetime.now(KST).isoformat(timespec="seconds")})
    save_pending(items)


def run_pending(headless: bool = True) -> int:
    """대기 목록의 글을 전부 받아 raw/ 에 저장한다. 답글이 실제로 잡힌 글만 목록에서 뺀다."""
    items = load_pending()
    if not items:
        print("재검토 대기 글 없음")
        return 0
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    done, kept = [], []
    for it in items:
        try:
            d = fetch(it["url"], headless=headless)
        except SystemExit:
            raise
        except Exception as e:  # 네트워크·렌더링 오류는 다음 기회로
            print(f"[warn] {it['code']}: {e}", file=sys.stderr)
            kept.append(it)
            continue
        (RAW_DIR / f"{d['code']}.md").write_text(to_markdown(d), encoding="utf-8")
        replies = [x for x in d["author_thread"] if x["code"] != d["code"]]
        if replies:
            done.append({**it, "replies": len(replies), "raw": f"threads-watch/raw/{d['code']}.md"})
        else:
            kept.append(it)
            print(f"[warn] {it['code']}: 작성자 답글이 잡히지 않음 (로그인 만료면 --login)", file=sys.stderr)
    save_pending(kept)
    print(json.dumps({"reanalyze": done, "still_pending": kept}, ensure_ascii=False, indent=2))
    return 0


def to_markdown(d: dict) -> str:
    lines = [f"# @{d['author'] or '?'} · {d['code']}", "", f"URL: {d['url']}", f"수집: {d['fetched_at_kst']}", ""]
    if d["author_thread"]:
        lines.append("## 본문 + 작성자 답글 (시간순)")
        for i, x in enumerate(d["author_thread"], 1):
            when = datetime.fromtimestamp(x["taken_at"], KST).strftime("%Y-%m-%d %H:%M") if x.get("taken_at") else ""
            tag = "답글" if x["is_reply"] or x["code"] != d["code"] else "본문"
            lines += [f"### {i}. {tag} · {when}", "", x["text"] or "(텍스트 없음, 이미지·영상)", ""]
    else:
        lines += ["## 데이터 추출 실패", "", "구조화된 데이터를 못 찾았습니다. 로그인 만료면 `--login` 을 다시 실행하세요.", ""]
    if d["other_replies"]:
        lines.append("## 다른 사람 답글 (참고, 최대 30)")
        for x in d["other_replies"]:
            t = (x["text"] or "").replace("\n", " ")
            lines.append(f"- @{x['user']}: {t[:200]}")
        lines.append("")
    lines += ["## 화면 텍스트 (원본 보존용)", "", "```", d["screen_text"][:20000], "```", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url", nargs="?", help="스레드 글 URL")
    ap.add_argument("--login", action="store_true", help="브라우저를 열어 로그인 프로필을 만든다")
    ap.add_argument("--json", action="store_true", help="마크다운 대신 JSON 출력")
    ap.add_argument("--show", action="store_true", help="브라우저 창을 보이게 실행")
    ap.add_argument("--pending", action="store_true", help="재검토 대기 글을 전부 받아온다 (답글 잡힌 글만 목록에서 제거)")
    ap.add_argument("--add", metavar="URL", help="답글 없이 분석한 글을 재검토 대기 목록에 넣는다")
    ap.add_argument("--reason", default="답글 미수집", help="--add 사유")
    ap.add_argument("--report", default="", help="--add 시 원래 보고서 경로")
    args = ap.parse_args()

    if args.add:
        add_pending(args.add, args.reason, args.report)
        print(f"대기 목록 추가: {post_code(args.add)}  (총 {len(load_pending())}건)")
        return 0
    if args.pending:
        return run_pending(headless=not args.show)

    if args.login:
        login()
        return 0
    if not args.url:
        ap.print_help()
        return 1

    d = fetch(args.url, headless=not args.show)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / f"{d['code']}.md"
    out.write_text(to_markdown(d), encoding="utf-8")
    if args.json:
        d2 = dict(d)
        d2["screen_text"] = d2["screen_text"][:2000]
        json.dump(d2, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        print(f"저장: {out}  (본문+작성자 답글 {len(d['author_thread'])}개, 로그인 추정: {d['logged_in_guess']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
