#!/usr/bin/env python3
"""
content-hub: 소재 1개를 여러 플랫폼 콘텐츠로 만들어 예약 발행하고, 성과를 보고 다시 쓰는 흐름.

  Collector  collect   소재 자동 수집 (레퍼런스 인스타 상위 캐러셀 / 유튜브 검색 상위 / 유튜브 자동완성 / 스레드)
             add       직접 작성·링크·파일로 소재 넣기
  Picker     inbox     소재함 보기 (점수순)
             pick      사람이 고르기 (ID…) 또는 점수 상위 자동 선별 (--auto N)
  Creator    create    고른 소재 → 플랫폼별 작성 지시서(out/<ID>/brief.md). 글은 Claude(또는 MCP 로 연결한 AI)가 쓴다
             check     작성한 파일을 지침 검사 (gongu-lab/lint_content.py)
             cards     캐러셀 문구 → 카드뉴스 이미지
  Scheduler  queue     예약 등록·목록·승인 (승인한 뒤 파일이 바뀌면 다시 승인해야 발행)
             run       예약 시각이 된 것 발행: 스레드·인스타·페이스북은 자동, 나머지는 '올릴 시간' 알림
             done      손으로 올린 것 완료 표시 (+게시물 주소 → 성과 수집 대상)
  Reviewer   review    성과 수집 → 보고서(md)·CSV, --remix 로 반응 상위를 소재함에 되돌림
  기타       status, set-threads-token, set-webhook(휴대폰 알림)

예)
  python hub.py add --text "김장 김치 보관 실수 5가지" --tags 김장,보관
  python hub.py collect --suggest "김장" --ig --threads
  python hub.py pick --auto 3
  python hub.py create s20261109-001 --platforms threads,carousel,reels,shorts,community
  python hub.py check s20261109-001
  python hub.py queue add s20261109-001 threads --at "2026-11-10 19:30"
  python hub.py queue approve q0001
  python hub.py run            # 예약 작업이 10~30분마다 실행
  python hub.py review --remix
"""
from __future__ import annotations

import argparse
import csv
import getpass
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
GONGU = ROOT / "gongu-lab"
sys.path.insert(0, str(GONGU))
sys.path.insert(0, str(HERE))

import lint_content  # noqa: E402

DATA = HERE / "data"
OUT = HERE / "out"
INBOX = DATA / "inbox.json"
QUEUE = DATA / "queue.json"
CONFIG = HERE / "config.json"
KST = timezone(timedelta(hours=9))  # 한국은 서머타임이 없어 고정 +9 (윈도우에 tzdata 없어도 됨)

# 플랫폼 → (검사 종류, 자동 발행 방식, 이름, 작성 규격 요약)
PLATFORMS: dict[str, dict] = {
    "threads":   {"kind": "threads", "auto": "threads", "label": "스레드",
                  "spec": "스친이들 반말체, 500자 이내. 생활 밀착/발견 공유/소신발언 중 하나. 강한 훅 + 상식 뒤집기 + 참여형 마무리. 가르치는 톤 금지."},
    "carousel":  {"kind": "carousel", "auto": "instagram", "label": "인스타 캐러셀(카드뉴스)",
                  "spec": "`[N장 역할]` 블록으로 장마다 제목 1줄 + 본문 2~3줄, 맨 끝 `[캡션]`. 존댓말, 프로필 링크 CTA. 6~10장. 마지막 장에 행동 1개(저장/댓글/프로필)."},
    "reels":     {"kind": "reels", "auto": None, "label": "인스타 릴스 캡션+대본",
                  "spec": "해시태그 금지. SEO 키워드 + 공감 후킹. 존댓말. 프로필 링크 CTA. 30~60초 컷 구성 포함."},
    "shorts":    {"kind": "shorts", "auto": None, "label": "유튜브 쇼츠 설명글",
                  "spec": "첫 줄 후킹 제목 30자 이내 / 본문 약 300자 / 해시태그 3개(#로빈의밥상 필수). 외부 링크 금지, CTA 는 '본 영상'."},
    "shorts_teaser": {"kind": "shorts_teaser", "auto": None, "label": "공구 티저 쇼츠",
                  "spec": "쇼츠 규격 + 댓글 이벤트 CTA 허용. 링크 금지."},
    "script":    {"kind": "script", "auto": None, "label": "유튜브 롱폼 대본",
                  "spec": "썸네일 문구·제목 후보 먼저, 그다음 6막(0~5막). [강조] 태그, 20년 셰프 1회."},
    "thumb":     {"kind": "thumb", "auto": None, "label": "썸네일 문구·제목 후보",
                  "spec": "`- ` 로 시작하는 썸네일 문구 후보(띄어쓰기 빼고 14~18자, 정답 노출 금지) + 제목 후보 3개 이상."},
    "longdesc":  {"kind": "longdesc", "auto": None, "label": "유튜브 롱폼 설명글",
                  "spec": "해시태그 3 → 후킹 → 재료 → 조리 8줄 → 챕터 8~10개(00:00 | 인트로) → CTA(밥상 식구님들+멤버십 링크) → 저작권."},
    "pin":       {"kind": "pin", "auto": None, "label": "유튜브 고정댓글",
                  "spec": "정확히 3줄."},
    "pin_gongu": {"kind": "pin_gongu", "auto": None, "label": "공구 고정댓글",
                  "spec": "정확히 3줄(구매 링크 포함). 후킹 → 긴장 → 해소 단서 → CTA."},
    "community": {"kind": "community", "auto": None, "label": "유튜브 커뮤니티",
                  "spec": "'밥상 식구님들' 존댓말. 사진이 있으면 `(사진: 파일명)` 줄로 표시."},
    "tiktok":    {"kind": "tiktok", "auto": None, "label": "틱톡 캡션",
                  "spec": "짧은 후킹 + '프로필 링크를 눌러 확인해줘' CTA + #로빈의밥상."},
    "x":         {"kind": "x", "auto": None, "label": "X(트위터)",
                  "spec": "280 단위(한글 1자=2) 이내 → 한글 약 130자. 결론 한 줄 + 이유 한 줄 + 행동 1개."},
    "facebook":  {"kind": "facebook", "auto": "facebook", "label": "페이스북 페이지",
                  "spec": "존댓말. 3~6줄. 링크는 마지막 줄 하나(자동 발행 시 링크 미리보기로 붙음)."},
    "linkedin":  {"kind": "linkedin", "auto": None, "label": "링크드인",
                  "spec": "사업·브랜드 협업 독자. 20년 셰프의 관점 + 숫자 + 배운 점. 존댓말."},
    "dm":        {"kind": "dm", "auto": None, "label": "인스타 자동 DM 문구",
                  "spec": "댓글 키워드에 자동으로 보낼 DM. 1,000자 이내, 첫 줄 감사 + 링크 1개 + 단점 한 줄. ManyChat 같은 도구에 붙여넣는다."},
}
DEFAULT_CONFIG = {
    "keywords": ["김장", "김치", "보관", "동치미", "반찬", "냉장고", "살림", "주방", "공구"],
    "keyword_boost": 10,
    "exclude": ["김장훈"],
    "require_approval": True,
    "default_platforms": ["threads", "carousel", "reels", "shorts", "community"],
    "threads_handles": [],
    "ig_min_score": 70,
    "image_base_url": "",
    "retry_limit": 3,
}


# ---------------------------------------------------------------- 저장소

def now() -> datetime:
    return datetime.now(KST)


def load(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)  # 쓰는 도중 꺼져도 원본이 깨지지 않게


def config() -> dict:
    return {**DEFAULT_CONFIG, **load(CONFIG, {})}


def inbox() -> dict:
    return load(INBOX, {"items": []})


def queue() -> dict:
    return load(QUEUE, {"posts": []})


def find_item(store: dict, item_id: str) -> dict:
    for it in store["items"]:
        if it["id"] == item_id:
            return it
    raise SystemExit(f"소재 {item_id} 가 없습니다. `hub.py inbox` 로 ID 를 확인하세요.")


def find_post(q: dict, qid: str) -> dict:
    for p in q["posts"]:
        if p["qid"] == qid:
            return p
    raise SystemExit(f"예약 {qid} 가 없습니다. `hub.py queue list` 로 확인하세요.")


def new_item_id(store: dict) -> str:
    day = now().strftime("%Y%m%d")
    n = sum(1 for it in store["items"] if it["id"].startswith(f"s{day}-")) + 1
    return f"s{day}-{n:03d}"


def keyword_score(text: str, cfg: dict) -> int:
    hits = sum(1 for k in cfg["keywords"] if k and k in text)
    return min(hits * cfg["keyword_boost"], 30)


def add_item(store: dict, *, source: str, title: str, text: str = "", url: str = "", path: str = "",
             score: float = 50, tags: list[str] | None = None, meta: dict | None = None,
             boost: bool = True) -> dict | None:
    """같은 주소·같은 제목은 다시 넣지 않는다. 자동 수집은 config 의 exclude 단어가 있으면 버린다."""
    cfg = config()
    if source != "manual" and any(w and w in title for w in cfg["exclude"]):
        return None
    key = url or title.strip()
    for it in store["items"]:
        if (it.get("url") or it["title"].strip()) == key:
            return None
    item = {"id": new_item_id(store), "created": now().isoformat(timespec="minutes"), "source": source,
            "title": title.strip()[:120], "text": text.strip(), "url": url, "path": path,
            "score": round(min(100, score + (keyword_score(title + " " + text, cfg) if boost else 0)), 1),
            "tags": tags or [], "status": "new", "meta": meta or {}}
    store["items"].append(item)
    return item


def pct_rank(values: list[float]) -> list[float]:
    order = sorted(values)
    n = len(values)
    return [100.0 if n == 1 else round(100 * order.index(v) / (n - 1), 1) for v in values]


# ---------------------------------------------------------------- Collector

def cmd_add(a) -> int:
    store = inbox()
    text, title, url, path = a.text or "", a.title or "", a.url or "", ""
    if a.file:
        p = Path(a.file)
        if not p.exists():
            raise SystemExit(f"파일이 없습니다: {p}")
        path = str(p.resolve())
        if p.suffix.lower() in (".md", ".txt"):
            text = text or p.read_text(encoding="utf-8")
    title = title or (text.strip().splitlines()[0] if text.strip() else (url or Path(path).name))
    it = add_item(store, source="manual", title=title, text=text, url=url, path=path, score=a.score,
                  tags=[t for t in (a.tags or "").split(",") if t])
    if not it:
        print("이미 소재함에 있는 소재입니다.")
        return 0
    save(INBOX, store)
    print(f"추가: {it['id']}  {it['title']}  (점수 {it['score']})")
    return 0


def collect_ig(store: dict, cfg: dict) -> int:
    """gongu-lab 이 모아 둔 레퍼런스 계정 캐러셀 중 반응 상위 (경쟁사 스파이)."""
    import ig_analyze
    n = 0
    for h in ig_analyze.all_handles():
        for p in ig_analyze.score_carousels(ig_analyze.load_store(h)):
            if p["score"] < cfg["ig_min_score"]:
                continue
            cap = p.get("caption") or ""
            first = next((ln for ln in cap.splitlines() if ln.strip()), "") or f"@{h} 캐러셀"
            if add_item(store, source="ig_ref", title=f"[@{h}] {first}", text=cap, url=p.get("url", ""),
                        score=p["score"] * 0.8, meta={"handle": h, "likes": p.get("likes"), "comments": p.get("comments"),
                                                      "note": "구조만 차용. 문장·이미지·제품 주장은 쓰지 않는다."}):
                n += 1
    return n


def collect_yt(store: dict, path: str) -> int:
    """yt_research.py search ... --json 결과. 채널 평균 대비 배수를 백분위로 바꿔 점수로 쓴다."""
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    ranks = pct_rank([r.get("outlier") or 0 for r in rows])
    n = 0
    for r, rk in zip(rows, ranks):
        if add_item(store, source="yt", title=r["title"], url=f"https://www.youtube.com/watch?v={r['videoId']}",
                    score=rk * 0.8, meta={"channel": r.get("channelTitle"), "views": r.get("viewCount"),
                                          "outlier": r.get("outlier")}):
            n += 1
    return n


def collect_suggest(store: dict, keyword: str) -> int:
    """유튜브 자동완성 = 사람들이 실제로 치는 검색어 (키 불필요). 앞 순위일수록 점수가 높다."""
    import yt_research
    sugg = yt_research.suggest(keyword)
    n = 0
    for i, s in enumerate(sugg):
        if s.strip() == keyword.strip():
            continue
        # 검색어 자체가 키워드라 가산점을 주면 전부 똑같이 오른다 → 자동완성 순위만으로 점수
        if add_item(store, source="suggest", title=s, score=70 - i * 3, tags=[keyword], boost=False):
            n += 1
    return n


def collect_threads(store: dict, handles: list[str]) -> int:
    sys.path.insert(0, str(ROOT / "threads-watch"))
    import fetch_threads
    n = 0
    for h in handles:
        xml, err = fetch_threads.fetch_rss(h)
        if not xml:
            print(f"  [스레드 @{h}] 가져오지 못함: {err}", file=sys.stderr)
            continue
        for p in fetch_threads.parse_items(xml, h, 20):
            first = next((ln for ln in p["text"].splitlines() if ln.strip()), "")
            if first and add_item(store, source="threads", title=f"[@{h}] {first}", text=p["text"], url=p["url"],
                                  score=40, meta={"handle": h}):
                n += 1
    return n


def cmd_collect(a) -> int:
    cfg, store = config(), inbox()
    got = {}
    if a.ig:
        got["인스타 레퍼런스"] = collect_ig(store, cfg)
    for f in a.yt or []:
        got[f"유튜브 {Path(f).name}"] = collect_yt(store, f)
    for k in a.suggest or []:
        got[f"자동완성 '{k}'"] = collect_suggest(store, k)
    if a.threads:
        handles = cfg["threads_handles"] or [c["handle"] for c in load(ROOT / "threads-watch" / "channels.json", {}).get("channels", [])
                                              if c.get("enabled")]
        got["스레드"] = collect_threads(store, handles)
    if not got:
        raise SystemExit("수집할 곳을 하나 이상 고르세요: --ig / --yt 파일 / --suggest 검색어 / --threads")
    save(INBOX, store)
    for k, v in got.items():
        print(f"  {k}: 새 소재 {v}개")
    print("`hub.py inbox` 로 확인하세요.")
    return 0


# ---------------------------------------------------------------- Picker

def cmd_inbox(a) -> int:
    items = [it for it in inbox()["items"] if a.all or it["status"] in ("new", "picked")]
    items.sort(key=lambda it: (it["status"] != "picked", -it["score"]))
    if a.json:
        print(json.dumps(items[: a.limit], ensure_ascii=False, indent=2))
        return 0
    if not items:
        print("소재함이 비었습니다. `hub.py add` 또는 `hub.py collect` 로 채우세요.")
        return 0
    print(f"| ID | 상태 | 점수 | 출처 | 소재 |\n|---|---|---|---|---|")
    for it in items[: a.limit]:
        print(f"| {it['id']} | {it['status']} | {it['score']} | {it['source']} | {it['title'][:50]} |")
    return 0


def cmd_pick(a) -> int:
    store = inbox()
    if a.auto:
        cands = sorted((it for it in store["items"] if it["status"] == "new"), key=lambda it: -it["score"])[: a.auto]
    else:
        cands = [find_item(store, i) for i in a.ids]
    for it in cands:
        it["status"] = "skipped" if a.skip else "picked"
        print(f"{'제외' if a.skip else '선택'}: {it['id']}  {it['title'][:50]}")
    save(INBOX, store)
    return 0


# ---------------------------------------------------------------- Creator

def out_file(item_id: str, platform: str) -> Path:
    return OUT / item_id / f"{item_id}_{PLATFORMS[platform]['kind']}.md"


def parse_platforms(raw: str | None) -> list[str]:
    plats = [p.strip() for p in (raw or ",".join(config()["default_platforms"])).split(",") if p.strip()]
    bad = [p for p in plats if p not in PLATFORMS]
    if bad:
        raise SystemExit(f"모르는 플랫폼: {bad}. 가능: {', '.join(PLATFORMS)}")
    return plats


def latest_analysis() -> str:
    reps = sorted((GONGU / "analysis").glob("20*.md"))
    return str(reps[-1].relative_to(ROOT)) if reps else ""


def cmd_create(a) -> int:
    store = inbox()
    it = find_item(store, a.id)
    plats = parse_platforms(a.platforms)
    d = OUT / it["id"]
    d.mkdir(parents=True, exist_ok=True)
    brief = {
        "item": it, "platforms": [{"platform": p, "label": PLATFORMS[p]["label"], "file": str(out_file(it["id"], p).relative_to(ROOT)),
                                   "lint_kind": PLATFORMS[p]["kind"], "spec": PLATFORMS[p]["spec"]} for p in plats],
        "read_first": ["gongu-lab/guidelines.md"] + ([latest_analysis()] if latest_analysis() else []),
        "rules": ["소재의 사실만 쓴다. 가격·수량·마감·효능이 소재에 없으면 지어내지 말고 로빈님께 묻는다.",
                  "레퍼런스(ig_ref·threads·yt)는 구조만 빌린다. 문장·이미지·제품 주장은 베끼지 않는다.",
                  "플랫폼마다 호칭·어미를 다시 쓴다 (유튜브 '밥상 식구님들' 존댓말 / 스레드 '스친이들' 반말 / 인스타 존댓말).",
                  "20년 셰프는 콘텐츠 하나에 딱 1회. 단점 먼저. 마지막은 행동 1개. 자리표시자 금지.",
                  "파일 맨 위 <!-- --> 주석에 근거(소재 ID, 따른 구조)를 남긴다. 검사에서 빠진다."],
        "after": f"python content-hub/hub.py check {it['id']}",
    }
    save(d / "brief.json", brief)
    lines = [f"# 작성 지시서 · {it['id']}", "", f"**소재**: {it['title']}", f"- 출처: {it['source']} {it.get('url') or ''}".rstrip()]
    if it.get("text"):
        lines += ["", "```", it["text"][:2000], "```"]
    if it.get("meta", {}).get("note"):
        lines += ["", f"> {it['meta']['note']}"]
    lines += ["", "## 먼저 읽기"] + [f"- {r}" for r in brief["read_first"]]
    lines += ["", "## 규칙"] + [f"- {r}" for r in brief["rules"]]
    lines += ["", "## 쓸 파일"] + [f"- [ ] `{p['file']}` — {p['label']}: {p['spec']}" for p in brief["platforms"]]
    lines += ["", f"다 쓰면: `{brief['after']}` → 오류 0건까지 고친다."]
    (d / "brief.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    it["status"] = "created"
    it["platforms"] = sorted(set(it.get("platforms", [])) | set(plats))
    save(INBOX, store)
    print(f"지시서: {(d / 'brief.md').relative_to(ROOT)}")
    for p in brief["platforms"]:
        print(f"  - {p['file']}  ({p['label']})")
    return 0


def lint_files(files: list[Path]) -> tuple[int, list[str]]:
    bad, report = 0, []
    for f in files:
        errs, warns = lint_content.lint(f)
        report.append(f"{'✗' if errs else ('△' if warns else '✓')} {f.relative_to(ROOT) if f.is_absolute() else f}")
        report += [f"    오류: {e}" for e in errs] + [f"    경고: {w}" for w in warns]
        bad += bool(errs)
    return bad, report


def cmd_check(a) -> int:
    d = OUT / a.id
    files = sorted(p for p in d.glob(f"{a.id}_*.md")) if d.exists() else []
    if not files:
        raise SystemExit(f"{d} 에 작성된 파일이 없습니다. 먼저 `hub.py create {a.id}` 후 글을 쓰세요.")
    bad, report = lint_files(files)
    print("\n".join(report))
    missing = [p["file"] for p in load(d / "brief.json", {}).get("platforms", []) if not (ROOT / p["file"]).exists()]
    if missing:
        print("\n아직 안 쓴 파일: " + ", ".join(missing))
    print(f"\n{len(files)}개 검사 · 오류 파일 {bad}개")
    return 1 if bad else 0


def cmd_cards(a) -> int:
    import cards
    src = out_file(a.id, "carousel")
    if not src.exists():
        raise SystemExit(f"{src.relative_to(ROOT)} 이 없습니다. 캐러셀 문구를 먼저 쓰세요.")
    spec = cards.parse_md(src.read_text(encoding="utf-8"))
    for item in a.image or []:
        num, _, rest = item.partition("=")
        path, _, crop = rest.partition(":")
        spec["slides"][int(num) - 1]["image"] = {"path": path, "crop": [int(v) for v in crop.split(",")] if crop else None}
    w, h = (int(v) for v in a.size.lower().split("x"))
    paths = cards.render(spec, OUT / a.id / "cards", (w, h), "jpg")
    print(f"카드 {len(paths)}장 → {(OUT / a.id / 'cards').relative_to(ROOT)}")
    print("인스타 자동 발행: 이 JPEG 들을 인터넷에서 열리는 곳에 올리고 `queue add ... --image-urls` 또는 config 의 image_base_url 을 쓰세요.")
    return 0


# ---------------------------------------------------------------- Scheduler

def file_text(path: Path) -> str:
    return "\n".join(lint_content.body_lines(path.read_text(encoding="utf-8"))).strip()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def split_caption(text: str) -> str:
    """캐러셀 파일에서 [캡션] 아래만. 없으면 전체."""
    if "[캡션]" in text:
        return text.split("[캡션]", 1)[1].strip()
    return text


def parse_at(raw: str) -> datetime:
    raw = raw.strip()
    if raw in ("now", "지금"):
        return now()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%m-%d %H:%M"):
        try:
            t = datetime.strptime(raw, fmt)
            if fmt == "%m-%d %H:%M":
                t = t.replace(year=now().year)
            return t.replace(tzinfo=KST)
        except ValueError:
            continue
    raise SystemExit(f"시각 형식: \"2026-11-10 19:30\" (한국 시간). 받은 값: {raw}")


def image_urls_for(item_id: str, explicit: str | None) -> list[str]:
    if explicit:
        return [u.strip() for u in explicit.split(",") if u.strip()]
    base = config()["image_base_url"].rstrip("/")
    cards_dir = OUT / item_id / "cards"
    if base and cards_dir.exists():
        return [f"{base}/{item_id}/{p.name}" for p in sorted(cards_dir.glob("slide_*.jpg"))]
    return []


def auto_mode(plat: str, image_urls: list[str]) -> str | None:
    """자동 발행 가능하면 방식, 연결이 안 돼 있으면 None(= 시간이 되면 알림만)."""
    import publishers
    mode = PLATFORMS[plat]["auto"]
    if mode == "threads" and not publishers.threads_creds()["token"]:
        return None
    if mode in ("instagram", "facebook"):
        c = publishers.ig_creds_quiet()
        if not (c.get("token") and c.get("ig_user_id")):
            return None
    if plat == "carousel" and not image_urls:
        return None
    return mode


def cmd_queue(a) -> int:
    q = queue()
    if a.qcmd == "add":
        plat = a.platform
        if plat not in PLATFORMS:
            raise SystemExit(f"모르는 플랫폼: {plat}. 가능: {', '.join(PLATFORMS)}")
        f = Path(a.file).resolve() if a.file else out_file(a.id, plat)
        if not f.exists():
            raise SystemExit(f"파일이 없습니다: {f}")
        bad, report = lint_files([f])
        if bad:
            print("\n".join(report))
            raise SystemExit("검사 오류가 있어 예약하지 않았습니다. 고친 뒤 다시 등록하세요.")
        at = parse_at(a.at)
        urls = image_urls_for(a.id, a.image_urls) if plat == "carousel" else ([a.image_urls] if a.image_urls else [])
        post = {"qid": f"q{len(q['posts']) + 1:04d}", "item_id": a.id, "platform": plat, "file": str(f.relative_to(ROOT)),
                "at": at.isoformat(timespec="minutes"), "status": "draft", "image_urls": urls, "link": a.link or "",
                "approved_sha": "", "attempts": 0, "result": {}, "error": "", "metrics": {}}
        q["posts"].append(post)
        save(QUEUE, q)
        mode = auto_mode(plat, urls)
        print(f"예약 {post['qid']}: {PLATFORMS[plat]['label']} · {post['at']} · {'자동 발행' if mode else '알림만(손으로 올림)'}")
        if config()["require_approval"]:
            print(f"승인해야 발행됩니다: hub.py queue approve {post['qid']}")
        return 0
    if a.qcmd == "approve":
        targets = [p for p in q["posts"] if p["status"] == "draft"] if a.all else [find_post(q, i) for i in a.qids]
        for p in targets:
            f = ROOT / p["file"]
            bad, report = lint_files([f])
            if bad:
                print("\n".join(report))
                print(f"{p['qid']} 검사 오류 — 승인하지 않음")
                continue
            p["status"], p["approved_sha"], p["approved_at"] = "approved", sha(f), now().isoformat(timespec="minutes")
            p["attempts"], p["error"] = 0, ""
            print(f"승인: {p['qid']} {PLATFORMS[p['platform']]['label']} {p['at']}")
        save(QUEUE, q)
        return 0
    if a.qcmd == "cancel":
        for i in a.qids:
            find_post(q, i)["status"] = "cancelled"
        save(QUEUE, q)
        print("취소했습니다.")
        return 0
    rows = [p for p in q["posts"] if a.all or p["status"] not in ("published", "done", "cancelled")]
    rows.sort(key=lambda p: p["at"])
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    print("| 예약 | 시각 | 플랫폼 | 상태 | 소재 | 파일 |\n|---|---|---|---|---|---|")
    for p in rows:
        print(f"| {p['qid']} | {p['at'].replace('T', ' ')[:16]} | {PLATFORMS[p['platform']]['label']} | {p['status']} | {p['item_id']} | {p['file']} |")
    return 0


def publish_one(p: dict) -> dict:
    import publishers
    text = file_text(ROOT / p["file"])
    mode = PLATFORMS[p["platform"]]["auto"]
    if mode == "threads":
        return publishers.threads_publish(text)
    if mode == "instagram":
        return publishers.ig_publish(p["image_urls"], split_caption(text))
    if mode == "facebook":
        return publishers.fb_publish(text, link=p.get("link", ""), image_url=(p["image_urls"] or [""])[0])
    raise RuntimeError("자동 발행 대상 아님")


def cmd_run(a) -> int:
    cfg, q = config(), queue()
    t = now()
    due = [p for p in q["posts"] if datetime.fromisoformat(p["at"]) <= t
           and p["status"] in (("approved",) if cfg["require_approval"] else ("approved", "draft"))]
    notes, changed = [], False
    if not a.dry:
        try:
            import publishers
            msg = publishers.threads_refresh_if_old()
            if "고쳤" in msg:
                print(msg)
        except Exception as e:  # 토큰 갱신 실패는 발행을 막지 않는다
            print(f"[스레드 토큰 갱신 실패] {e}", file=sys.stderr)
    for p in sorted(due, key=lambda p: p["at"]):
        f = ROOT / p["file"]
        label = PLATFORMS[p["platform"]]["label"]
        if not f.exists():
            p["status"], p["error"] = "failed", "파일이 사라짐"
            changed = True
            continue
        if cfg["require_approval"] and p.get("approved_sha") and sha(f) != p["approved_sha"]:
            p["status"], p["held"] = "draft", True
            notes.append(f"- {p['qid']} {label}: 승인 뒤 파일이 바뀌어 보류 → 확인 후 `hub.py queue approve {p['qid']}`")
            changed = True
            continue
        mode = auto_mode(p["platform"], p["image_urls"])
        if not mode:
            p["status"] = "manual_due"
            notes.append(f"- {p['qid']} 지금 올릴 시간: {label} → `{p['file']}` (올린 뒤 `hub.py done {p['qid']} --url 주소`)")
            changed = True
            continue
        if a.dry:
            print(f"[시험] {p['qid']} {label} 자동 발행 예정 · {p['file']}")
            continue
        p["status"] = "publishing"   # 발행 중 꺼져도 다음 실행이 같은 글을 두 번 올리지 않게
        p["attempts"] += 1
        save(QUEUE, q)
        try:
            p["result"] = publish_one(p)
            p["status"], p["published_at"], p["error"] = "published", now().isoformat(timespec="minutes"), ""
            print(f"발행: {p['qid']} {label} {p['result'].get('url', '')}")
            notes.append(f"- {p['qid']} 자동 발행 완료: {label} {p['result'].get('url', '')}")
        except Exception as e:
            p["error"] = str(e)[:300]
            p["status"] = "failed" if p["attempts"] >= cfg["retry_limit"] else "approved"
            print(f"실패({p['attempts']}/{cfg['retry_limit']}): {p['qid']} {label} — {p['error']}", file=sys.stderr)
            if p["status"] == "failed":
                notes.append(f"- {p['qid']} 발행 실패({cfg['retry_limit']}회): {label} — {p['error'][:120]}")
        changed = True
    waiting = [p for p in q["posts"] if p["status"] == "draft" and cfg["require_approval"]
               and datetime.fromisoformat(p["at"]) <= t and not p.pop("held", False)]
    for p in waiting:
        notes.append(f"- {p['qid']} 시간이 됐지만 승인 전: {PLATFORMS[p['platform']]['label']} → `hub.py queue approve {p['qid']}`")
    stuck = [p for p in q["posts"] if p["status"] == "publishing"]
    for p in stuck:
        notes.append(f"- {p['qid']} 발행 중에 멈췄던 기록 — 실제로 올라갔는지 확인 후 `hub.py done {p['qid']}` 또는 `queue approve`")
    if changed and not a.dry:
        save(QUEUE, q)
    if notes:
        msg = f"# 올릴 것 ({t:%m/%d %H:%M})\n" + "\n".join(notes)
        print(msg)
        DATA.mkdir(parents=True, exist_ok=True)
        with (DATA / "notify.md").open("a", encoding="utf-8") as fh:
            fh.write(msg + "\n\n")
        if not a.dry:
            notify(msg)
    if not due and not stuck and not waiting:
        print("지금 올릴 예약이 없습니다.")
    return 0


WEBHOOK_FILE = HERE / ".webhook.json"


def notify(msg: str) -> None:
    """디스코드·슬랙 웹후크로 휴대폰 알림. 주소는 `hub.py set-webhook` 으로 저장(저장소에 안 올라감) 또는 환경변수."""
    import os
    url = load(WEBHOOK_FILE, {}).get("url") or os.environ.get("CONTENT_HUB_WEBHOOK", "")
    if not url:
        return
    body = json.dumps({"content": msg[:1900], "text": msg[:1900]}).encode()  # content=디스코드, text=슬랙
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "content-hub/1.0"})
    try:
        urllib.request.urlopen(req, timeout=20).read()
    except Exception as e:
        print(f"[알림 실패] {e}", file=sys.stderr)


def cmd_set_webhook(a) -> int:
    url = getpass.getpass("디스코드(또는 슬랙) 웹후크 주소 붙여넣기(화면에 안 보임): ").strip()
    if not url.startswith("https://"):
        raise SystemExit("https:// 로 시작하는 웹후크 주소가 필요합니다.")
    save(WEBHOOK_FILE, {"url": url})
    notify("로빈의밥상 content-hub 알림 연결 완료")
    print("저장했고 시험 알림을 보냈습니다. 휴대폰에 왔는지 확인하세요.")
    return 0


def cmd_done(a) -> int:
    q = queue()
    p = find_post(q, a.qid)
    p["status"], p["published_at"] = "done", now().isoformat(timespec="minutes")
    if a.url:
        p["result"] = {**p.get("result", {}), "url": a.url}
    save(QUEUE, q)
    print(f"완료 표시: {p['qid']} {PLATFORMS[p['platform']]['label']}")
    return 0


# ---------------------------------------------------------------- Reviewer

MAIN_METRIC = {"threads": "views", "carousel": "reach", "facebook": "reactions"}


def yt_video_id(url: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/|shorts/)([\w-]{11})", url or "")
    return m.group(1) if m else ""


def cmd_review(a) -> int:
    import publishers
    q = queue()
    since = now() - timedelta(days=a.days)
    posts = [p for p in q["posts"] if p["status"] in ("published", "done") and p.get("published_at")
             and datetime.fromisoformat(p["published_at"]) >= since]
    errors = []
    yt_ids = {}
    for p in posts:
        mid = (p.get("result") or {}).get("media_id")
        try:
            if p["status"] == "published" and p["platform"] == "threads" and mid:
                p["metrics"] = publishers.threads_insights(mid)
            elif p["status"] == "published" and p["platform"] == "carousel" and mid:
                p["metrics"] = publishers.ig_insights(mid)
            elif p["status"] == "published" and p["platform"] == "facebook" and mid:
                p["metrics"] = publishers.fb_insights(mid)
            elif yt_video_id((p.get("result") or {}).get("url", "")):
                yt_ids[yt_video_id(p["result"]["url"])] = p
        except Exception as e:
            errors.append(f"{p['qid']}: {e}")
    if yt_ids:
        try:
            import yt_research
            for r in yt_research.video_rows(list(yt_ids)):
                yt_ids[r["videoId"]]["metrics"] = {"views": r["viewCount"], "likes": r["likeCount"], "comments": r["commentCount"]}
        except BaseException as e:  # 키가 없으면 yt_research 가 SystemExit
            errors.append(f"유튜브 성과: {e}")
    for p in posts:
        if p.get("metrics"):
            p["metrics"]["_at"] = now().isoformat(timespec="minutes")
    save(QUEUE, q)

    by_plat: dict[str, list[dict]] = {}
    for p in posts:
        if p.get("metrics"):
            by_plat.setdefault(p["platform"], []).append(p)
    items = {it["id"]: it for it in inbox()["items"]}
    lines = [f"# 성과 보고서 {now():%Y-%m-%d} (최근 {a.days}일)", "",
             "플랫폼 안에서만 비교한다(백분위). 플랫폼끼리 숫자를 직접 비교하지 않는다.", ""]
    top_items = []
    rows_csv = []
    for plat, ps in sorted(by_plat.items()):
        key = MAIN_METRIC.get(plat, "views")
        vals = [p["metrics"].get(key) or 0 for p in ps]
        ranks = pct_rank(vals)
        lines += [f"## {PLATFORMS[plat]['label']} (기준: {key}, {len(ps)}개)", "",
                  "| 백분위 | " + key + " | 소재 | 게시일 | 주소 |", "|---|---|---|---|---|"]
        for p, v, rk in sorted(zip(ps, vals, ranks), key=lambda x: -x[2]):
            title = items.get(p["item_id"], {}).get("title", p["item_id"])[:40]
            lines.append(f"| {rk} | {v:,} | {title} | {p['published_at'][:10]} | {(p.get('result') or {}).get('url', '')} |")
            rows_csv.append({"platform": plat, "qid": p["qid"], "item_id": p["item_id"], "title": title,
                             "published_at": p["published_at"], "metric": key, "value": v, "percentile": rk,
                             **{k: v2 for k, v2 in p["metrics"].items() if not k.startswith("_")},
                             "url": (p.get("result") or {}).get("url", "")})
            if rk >= 80 and len(ps) >= 3:
                top_items.append((p["item_id"], plat, rk))
        lines.append("")
    no_metric = [p for p in posts if not p.get("metrics")]
    if no_metric:
        lines += ["## 숫자를 못 가져온 게시물 (플랫폼 앱에서 직접 확인)"]
        lines += [f"- {PLATFORMS[p['platform']]['label']} · {items.get(p['item_id'], {}).get('title', p['item_id'])[:40]} · "
                  f"{(p.get('result') or {}).get('url') or '주소 없음'}" for p in no_metric]
        lines.append("")
    if len(posts) < 5:
        lines.append(f"> 표본 {len(posts)}개 — 결론이 아니라 가설로 본다.")
    if errors:
        lines += ["", "## 가져오지 못한 것"] + [f"- {e}" for e in errors]
    if not by_plat:
        lines.append("성과를 가져온 게시물이 없습니다. 자동 발행 게시물이나 `done --url` 로 주소를 남긴 게시물만 수집됩니다.")
    rep_dir = DATA / "reports"
    rep_dir.mkdir(parents=True, exist_ok=True)
    rep = rep_dir / f"review_{now():%Y-%m-%d}.md"
    rep.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if rows_csv:
        cols = sorted({k for r in rows_csv for k in r}, key=lambda k: list(rows_csv[0]).index(k) if k in rows_csv[0] else 99)
        with (rep_dir / f"review_{now():%Y-%m-%d}.csv").open("w", encoding="utf-8-sig", newline="") as fh:  # 엑셀 한글 깨짐 방지
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(rows_csv)
    print("\n".join(lines))
    print(f"\n보고서: {rep.relative_to(ROOT)}" + (" (+CSV)" if rows_csv else ""))
    if a.remix and top_items:
        store = inbox()
        for item_id, plat, rk in top_items:
            src = store_item = next((it for it in store["items"] if it["id"] == item_id), None)
            if not src:
                continue
            done_plats = set(store_item.get("platforms", []))
            rest = [p for p in config()["default_platforms"] if p not in done_plats]
            it = add_item(store, source="remix", title=f"[재활용] {src['title']}", text=src.get("text", ""),
                          url=f"remix:{item_id}:{plat}", score=min(100, rk), tags=src.get("tags", []),
                          meta={"from": item_id, "proven_on": plat, "suggest_platforms": rest,
                                "note": f"{PLATFORMS[plat]['label']}에서 상위 {100 - rk:.0f}% — 같은 소재를 다른 플랫폼·다른 각도로."})
            if it:
                print(f"재활용 소재: {it['id']} ← {item_id} ({PLATFORMS[plat]['label']} 백분위 {rk})")
        save(INBOX, store)
    return 0


# ---------------------------------------------------------------- 기타

def cmd_set_threads_token(a) -> int:
    import publishers
    tok = getpass.getpass("스레드 액세스 토큰 붙여넣기(화면에 안 보이는 게 정상): ").strip()
    if not tok:
        raise SystemExit("토큰이 비었습니다.")
    secret = getpass.getpass("60일 토큰으로 바꾸려면 Threads 앱 시크릿 코드(그냥 Enter 면 건너뜀): ").strip()
    expires = None
    if secret:
        tok, expires = publishers.threads_long_lived(tok, secret)
    me = publishers.threads_me(tok)
    publishers.threads_save(tok, me["id"], me.get("username", ""), expires)
    print(f"저장했습니다: @{me.get('username')} (content-hub/.threads_token.json, 저장소에 올라가지 않음)")
    return 0


def cmd_ig_check(a) -> int:
    """인스타 자동 발행에 필요한 것을 차례로 확인하고 다음에 할 일 1개를 알려준다. 글을 올리지는 않는다."""
    import publishers
    todo = []
    c = publishers.ig_creds_quiet()
    if not c.get("token"):
        print("✗ 토큰 없음")
        print("\n다음에 할 일: python gongu-lab\\ig_collect.py --set-token")
        return 1
    print("✓ 토큰 저장됨")
    try:
        perms = {x["permission"] for x in publishers._request("GET", publishers._ig("me/permissions"),
                                                                {"access_token": c["token"]}).get("data", []) if x.get("status") == "granted"}
    except publishers.PublishError as e:
        print(f"✗ 토큰 조회 실패(만료됐거나 잘못된 토큰): {e}")
        print("\n다음에 할 일: python gongu-lab\\ig_collect.py --set-token 으로 새 토큰 저장")
        return 1
    for need, why in (("instagram_content_publish", "인스타에 글·사진·캐러셀 올리기"),
                      ("pages_manage_posts", "연결된 페이스북 페이지에 글 올리기(선택)"),
                      ("instagram_manage_insights", "인스타 성과 숫자 가져오기"),
                      ("pages_show_list", "계정 찾기")):
        ok = need in perms
        print(f"{'✓' if ok else '✗'} 권한 {need} — {why}")
        if not ok and need in ("instagram_content_publish", "instagram_manage_insights", "pages_show_list"):
            todo.append(f"토큰에 `{need}` 권한 추가")
    print(f"{'✓' if c.get('ig_user_id') else '✗'} 인스타 계정 ID {c.get('ig_user_id') or '(못 찾음)'}")
    base = config()["image_base_url"].strip()
    print(f"{'✓' if base else '△'} 이미지 주소(image_base_url) {base or '비어 있음 → 카드 이미지는 손으로 올리고 알림만 받음'}")
    if base:
        try:
            req = urllib.request.Request(base, method="HEAD", headers={"User-Agent": publishers.UA})
            urllib.request.urlopen(req, timeout=15)
            print("✓ 이미지 주소가 인터넷에서 열림")
        except Exception as e:
            print(f"△ 이미지 주소 접속 확인 못 함: {e}")
    if todo:
        print("\n다음에 할 일 1개: " + todo[0] + "  (Graph API Explorer 에서 권한 추가 후 `ig_collect.py --set-token` 으로 다시 저장)")
        return 1
    print("\n준비 끝. 시험은 카드 1장짜리 캐러셀이 아니라 사진 1장으로 먼저: hub.py queue add … carousel --image-urls 주소1개")
    return 0


def cmd_status(a) -> int:
    items, posts = inbox()["items"], queue()["posts"]
    count = lambda xs, k: {s: sum(1 for x in xs if x[k] == s) for s in sorted({x[k] for x in xs})}
    print("소재함:", count(items, "status") or "비었음")
    print("예약:", count(posts, "status") or "없음")
    upcoming = sorted((p for p in posts if p["status"] in ("draft", "approved")), key=lambda p: p["at"])[:5]
    for p in upcoming:
        print(f"  {p['at'].replace('T', ' ')[:16]} {PLATFORMS[p['platform']]['label']} [{p['status']}] {p['qid']}")
    manual = [p for p in posts if p["status"] == "manual_due"]
    if manual:
        print("손으로 올릴 것:")
        for p in manual:
            print(f"  {p['qid']} {PLATFORMS[p['platform']]['label']} → {p['file']}")
    import publishers
    print("연결:", "스레드 " + ("O" if publishers.threads_creds()["token"] else "X"),
          "/ 인스타·페북 " + ("O" if (GONGU / ".ig_token.json").exists() else "X"))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("add", help="소재 직접 넣기")
    s.add_argument("--text"); s.add_argument("--title"); s.add_argument("--url"); s.add_argument("--file")
    s.add_argument("--tags", help="쉼표로 구분"); s.add_argument("--score", type=float, default=70)
    s.set_defaults(fn=cmd_add)

    s = sub.add_parser("collect", help="소재 자동 수집")
    s.add_argument("--ig", action="store_true", help="gongu-lab 레퍼런스 인스타 반응 상위 캐러셀")
    s.add_argument("--yt", action="append", help="yt_research.py search --json 결과 파일")
    s.add_argument("--suggest", action="append", help="유튜브 자동완성 검색어 (키 불필요)")
    s.add_argument("--threads", action="store_true", help="스레드 채널 새 글 (config 의 threads_handles 또는 threads-watch 채널)")
    s.set_defaults(fn=cmd_collect)

    s = sub.add_parser("inbox", help="소재함")
    s.add_argument("--all", action="store_true"); s.add_argument("--json", action="store_true")
    s.add_argument("--limit", type=int, default=30)
    s.set_defaults(fn=cmd_inbox)

    s = sub.add_parser("pick", help="소재 고르기")
    s.add_argument("ids", nargs="*"); s.add_argument("--auto", type=int, help="점수 상위 N개 자동 선별")
    s.add_argument("--skip", action="store_true", help="고르는 대신 제외")
    s.set_defaults(fn=cmd_pick)

    s = sub.add_parser("create", help="플랫폼별 작성 지시서")
    s.add_argument("id"); s.add_argument("--platforms", help=f"쉼표로: {','.join(PLATFORMS)}")
    s.set_defaults(fn=cmd_create)

    s = sub.add_parser("check", help="작성 파일 검사"); s.add_argument("id"); s.set_defaults(fn=cmd_check)

    s = sub.add_parser("cards", help="캐러셀 문구 → 카드 이미지(JPEG)")
    s.add_argument("id"); s.add_argument("--size", default="1080x1350")
    s.add_argument("--image", action="append", help="N=사진경로[:x0,y0,x1,y1]")
    s.set_defaults(fn=cmd_cards)

    s = sub.add_parser("queue", help="예약"); qs = s.add_subparsers(dest="qcmd", required=True)
    x = qs.add_parser("add"); x.add_argument("id"); x.add_argument("platform"); x.add_argument("--at", required=True)
    x.add_argument("--file", help="기본은 out/<ID>/<ID>_<종류>.md"); x.add_argument("--image-urls", help="인스타·페북용 이미지 주소(쉼표)")
    x.add_argument("--link", help="페이스북 글에 붙일 링크")
    x = qs.add_parser("approve"); x.add_argument("qids", nargs="*"); x.add_argument("--all", action="store_true")
    x = qs.add_parser("cancel"); x.add_argument("qids", nargs="+")
    x = qs.add_parser("list"); x.add_argument("--all", action="store_true"); x.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_queue)

    s = sub.add_parser("run", help="예약 시각이 된 것 발행/알림"); s.add_argument("--dry", action="store_true"); s.set_defaults(fn=cmd_run)
    s = sub.add_parser("done", help="손으로 올린 것 완료"); s.add_argument("qid"); s.add_argument("--url"); s.set_defaults(fn=cmd_done)
    s = sub.add_parser("review", help="성과 보고서"); s.add_argument("--days", type=int, default=14)
    s.add_argument("--remix", action="store_true", help="반응 상위를 소재함에 되돌림"); s.set_defaults(fn=cmd_review)
    s = sub.add_parser("set-threads-token", help="스레드 토큰 저장"); s.set_defaults(fn=cmd_set_threads_token)
    s = sub.add_parser("set-webhook", help="휴대폰 알림(디스코드/슬랙 웹후크) 저장"); s.set_defaults(fn=cmd_set_webhook)
    s = sub.add_parser("ig-check", help="인스타 자동 발행 준비 점검"); s.set_defaults(fn=cmd_ig_check)
    s = sub.add_parser("status", help="현황"); s.set_defaults(fn=cmd_status)

    for stream in (sys.stdout, sys.stderr):  # 윈도우 로그 파일로 보낼 때 ✓ 같은 글자에서 멈추지 않게
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
