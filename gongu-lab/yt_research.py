#!/usr/bin/env python3
"""
gongu-lab: vidIQ 없이 쓰는 유튜브 조사 도구. 무료 경로만 쓴다.

명령
  suggest 키워드 [--expand]
      유튜브 자동완성 검색어(사람들이 실제로 치는 말). 키 불필요.
      --expand: '방법·추천·단점·후기·비교·보관…' 을 붙여 넓게 모은다.
  search 키워드 [--days 365] [--format any|long|short] [--max 25] [--order viewCount|relevance|date]
      검색 결과 영상의 조회·좋아요·댓글과 '채널 평균 대비 배수'(아웃라이어)를 계산한다.
  comments 영상ID|URL [--max 100] [--order relevance|time] [--grep 정규식]
      댓글 수집. 좋아요 많은 순, 질문형 댓글 비율, 키워드가 들어간 댓글.
  channel @핸들|채널ID [--max 50] [--save 경로]
      채널 최근 영상 지표. --save 는 analyze_videos.py 가 바로 읽는 형식으로 저장.
  set-key
      API 키를 이 PC 에 저장(gongu-lab/.yt_key.json, 커밋 제외). 화면에 표시되지 않음.

API 키: YouTube Data API v3 키(무료). 환경변수 YOUTUBE_API_KEY 가 있으면 그것을, 없으면 set-key 로 저장한 것을 쓴다.
무료 할당량은 하루 10,000 단위. search 1회 = 100, 영상·채널·댓글 조회 1회 = 1. 이 도구는 쓴 양을 대략 세서 보여준다.

사용 예
  python3 yt_research.py suggest "김치 보관" --expand
  python3 yt_research.py search "김치 보관 용기" --days 365 --format long
  python3 yt_research.py comments https://youtu.be/XXXXXXXXXXX --grep "곰팡이|골마지|냄새"
  python3 yt_research.py channel @robynstable --save data/videos/robynstable.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_videos import parse_duration  # noqa: E402

HERE = Path(__file__).resolve().parent
KEY_FILE = HERE / ".yt_key.json"
QUOTA_FILE = HERE / "state" / "yt_quota.json"
API = "https://www.googleapis.com/youtube/v3/"
SUGGEST = "https://suggestqueries.google.com/complete/search"
UA = "Mozilla/5.0 (compatible; gongu-lab/1.0)"
KST = timezone(timedelta(hours=9))
COST = {"search": 100}  # 나머지는 1
EXPAND = ["방법", "추천", "단점", "후기", "비교", "보관", "고르는 법", "하는 법", "가격", "실패"]
QUESTION = re.compile(r"\?|나요|까요|어떻게|어디서|어디|뭐|무엇|얼마|되나|될까|궁금")
SHORT_MAX = 180


class ApiError(RuntimeError):
    pass


def http_get_json(url: str, timeout: int = 30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


# ---------------------------------------------------------------- 키·할당량

def api_key() -> str:
    if os.environ.get("YOUTUBE_API_KEY"):
        return os.environ["YOUTUBE_API_KEY"]
    if KEY_FILE.exists():
        return json.loads(KEY_FILE.read_text(encoding="utf-8")).get("key", "")
    return ""


def add_quota(units: int) -> int:
    today = datetime.now(KST).date().isoformat()
    data = json.loads(QUOTA_FILE.read_text(encoding="utf-8")) if QUOTA_FILE.exists() else {}
    data = {today: data.get(today, 0) + units}
    QUOTA_FILE.parent.mkdir(parents=True, exist_ok=True)
    QUOTA_FILE.write_text(json.dumps(data) + "\n", encoding="utf-8")
    return data[today]


def explain(status: int, body: str) -> str:
    try:
        err = json.loads(body).get("error", {})
        reason = (err.get("errors") or [{}])[0].get("reason", "") or err.get("status", "")
        msg = err.get("message", "")
    except (json.JSONDecodeError, AttributeError):
        reason, msg = "", body[:200]
    hints = {
        "quotaExceeded": "오늘 무료 할당량(10,000)을 다 썼습니다. 한국 시간 오후 4~5시쯤(미국 태평양 자정) 초기화됩니다.",
        "keyInvalid": "API 키가 올바르지 않습니다. 키를 다시 확인하세요.",
        "accessNotConfigured": "Google Cloud 프로젝트에서 'YouTube Data API v3' 를 사용 설정해야 합니다.",
        "SERVICE_DISABLED": "Google Cloud 프로젝트에서 'YouTube Data API v3' 를 사용 설정해야 합니다.",
        "forbidden": "이 요청은 허용되지 않습니다(비공개 영상이거나 댓글이 막혀 있을 수 있음).",
        "commentsDisabled": "이 영상은 댓글이 꺼져 있습니다.",
        "videoNotFound": "영상을 찾을 수 없습니다. 주소나 ID 를 확인하세요.",
    }
    return f"YouTube API 오류 {status} ({reason}): {hints.get(reason, msg)}"


def yt(endpoint: str, **params):
    key = api_key()
    if not key:
        raise ApiError("YouTube API 키가 없습니다. 환경변수 YOUTUBE_API_KEY 를 설정하거나 `set-key` 로 저장하세요.")
    url = API + endpoint + "?" + urllib.parse.urlencode({**{k: v for k, v in params.items() if v is not None}, "key": key})
    try:
        data = http_get_json(url)
    except urllib.error.HTTPError as e:
        raise ApiError(explain(e.code, e.read().decode("utf-8", errors="replace"))) from e
    add_quota(COST.get(endpoint, 1))
    return data


def chunks(xs: list, n: int = 50):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


# ---------------------------------------------------------------- suggest

def suggest(q: str, lang: str = "ko") -> list[str]:
    url = SUGGEST + "?" + urllib.parse.urlencode({"client": "firefox", "ds": "yt", "hl": lang, "gl": "kr", "q": q})
    data = http_get_json(url)
    return list(data[1]) if isinstance(data, list) and len(data) > 1 else []


def cmd_suggest(args) -> int:
    seeds = [args.keyword] + ([f"{args.keyword} {s}" for s in EXPAND] if args.expand else [])
    seen: dict[str, str] = {}
    for sd in seeds:
        try:
            for s in suggest(sd):
                seen.setdefault(s, sd)
        except (urllib.error.URLError, ValueError) as e:
            print(f"[warn] '{sd}': {e}", file=sys.stderr)
    print(f"# '{args.keyword}' 유튜브 자동완성 ({len(seen)}개)\n")
    print("자동완성은 실제로 많이 치는 검색어 순서에 가깝지만 검색량 숫자는 주지 않는다.\n")
    for s, sd in seen.items():
        print(f"- {s}" + (f"  (← {sd})" if args.expand and sd != args.keyword else ""))
    return 0


# ---------------------------------------------------------------- 영상·채널 지표

def video_rows(ids: list[str]) -> list[dict]:
    rows = []
    for part in chunks(ids):
        data = yt("videos", part="snippet,statistics,contentDetails", id=",".join(part))
        for v in data.get("items", []):
            st, sn = v.get("statistics", {}), v.get("snippet", {})
            rows.append({
                "videoId": v["id"], "title": sn.get("title", ""), "channelId": sn.get("channelId", ""),
                "channelTitle": sn.get("channelTitle", ""), "publishedAt": sn.get("publishedAt", ""),
                "viewCount": int(st.get("viewCount", 0)), "likeCount": int(st["likeCount"]) if "likeCount" in st else None,
                "commentCount": int(st["commentCount"]) if "commentCount" in st else None,
                "duration": v.get("contentDetails", {}).get("duration", ""),
            })
    return rows


def channel_avgs(channel_ids: list[str]) -> dict:
    out = {}
    for part in chunks(sorted(set(channel_ids))):
        data = yt("channels", part="statistics,snippet", id=",".join(part))
        for c in data.get("items", []):
            st = c.get("statistics", {})
            n = int(st.get("videoCount", 0)) or 1
            out[c["id"]] = {"avg": int(st.get("viewCount", 0)) / n, "subs": int(st.get("subscriberCount", 0) or 0),
                            "title": c.get("snippet", {}).get("title", "")}
    return out


def days_since(iso: str) -> float:
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return 1.0
    return max((datetime.now(timezone.utc) - t).total_seconds() / 86400, 1.0)


def enrich(rows: list[dict], avgs: dict) -> list[dict]:
    for r in rows:
        avg = (avgs.get(r["channelId"]) or {}).get("avg") or 0
        views = max(r["viewCount"], 1)
        r["seconds"] = parse_duration(r["duration"])
        r["outlier"] = round(r["viewCount"] / avg, 2) if avg else None
        r["views_per_day"] = round(r["viewCount"] / days_since(r["publishedAt"]))
        r["like_rate"] = round(r["likeCount"] / views * 100, 2) if r["likeCount"] is not None else None
        r["comment_rate"] = round(r["commentCount"] / views * 1000, 2) if r["commentCount"] is not None else None
        r["subs"] = (avgs.get(r["channelId"]) or {}).get("subs")
    return rows


def md(header: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join("-" if c is None else str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def fmt_len(sec: int) -> str:
    return f"{sec // 60}:{sec % 60:02d}"


def cmd_search(args) -> int:
    after = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = yt("search", part="snippet", q=args.keyword, type="video", maxResults=min(args.max, 50), order=args.order,
              regionCode="KR", relevanceLanguage="ko", publishedAfter=after,
              videoDuration="short" if args.format == "short" else None)
    ids = [it["id"]["videoId"] for it in data.get("items", []) if it.get("id", {}).get("videoId")]
    if not ids:
        print("검색 결과가 없습니다.")
        return 0
    rows = video_rows(ids)
    rows = enrich(rows, channel_avgs([r["channelId"] for r in rows]))
    if args.format == "long":
        rows = [r for r in rows if r["seconds"] > SHORT_MAX]
    elif args.format == "short":
        rows = [r for r in rows if 0 < r["seconds"] <= SHORT_MAX]
    rows.sort(key=lambda r: (r["outlier"] or 0), reverse=True)
    print(f"# '{args.keyword}' 검색 상위 영상 (최근 {args.days}일, {args.format}, {len(rows)}개)\n")
    print("채널 평균 대비 = 이 영상 조회수 ÷ 채널 전체 평균 조회수(채널 누적 조회 ÷ 영상 수). 2 이상이면 그 채널에서 유독 잘 된 영상.\n")
    print(md(["채널(구독)", "게시일", "제목", "조회", "채널 평균 대비", "하루 평균 조회", "좋아요율", "댓글/천회", "길이", "영상 ID"],
             [[f"{r['channelTitle'][:14]}({r['subs'] or '-'})", r["publishedAt"][:10], r["title"][:40], f"{r['viewCount']:,}",
               f"{r['outlier']}×" if r["outlier"] is not None else None, f"{r['views_per_day']:,}",
               f"{r['like_rate']}%" if r["like_rate"] is not None else None, r["comment_rate"], fmt_len(r["seconds"]), r["videoId"]]
              for r in rows]))
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n할당량: 이번 실행 약 {COST['search'] + 2}단위, 오늘 누적 약 {add_quota(0):,}/10,000")
    return 0


# ---------------------------------------------------------------- comments

def video_id(raw: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/live/)([A-Za-z0-9_-]{11})", raw)
    return m.group(1) if m else raw.strip()


def cmd_comments(args) -> int:
    vid = video_id(args.video)
    got, token = [], None
    while len(got) < args.max:
        data = yt("commentThreads", part="snippet", videoId=vid, maxResults=min(100, args.max - len(got)),
                  order=args.order, textFormat="plainText", pageToken=token)
        for it in data.get("items", []):
            top = it["snippet"]["topLevelComment"]["snippet"]
            got.append({"text": top.get("textDisplay", "").replace("\n", " "), "likes": int(top.get("likeCount", 0)),
                        "replies": int(it["snippet"].get("totalReplyCount", 0)), "at": top.get("publishedAt", "")[:10],
                        "owner": top.get("authorChannelId", {}).get("value") == it["snippet"].get("channelId")})
        token = data.get("nextPageToken")
        if not token:
            break
    viewers = [c for c in got if not c["owner"]]
    q = [c for c in viewers if QUESTION.search(c["text"])]
    print(f"# 댓글 {len(got)}개 (시청자 {len(viewers)}개) · 질문형 {len(q)}개 ({len(q) / max(len(viewers), 1):.0%})\n")
    print("## 좋아요 많은 시청자 댓글")
    for c in sorted(viewers, key=lambda c: c["likes"], reverse=True)[:15]:
        print(f"- ({c['likes']}) {c['text'][:160]}")
    print("\n## 질문형 댓글 (구매·조리 전에 막히는 지점 후보)")
    for c in sorted(q, key=lambda c: c["likes"], reverse=True)[:10]:
        print(f"- ({c['likes']}) {c['text'][:160]}")
    if args.grep:
        rx = re.compile(args.grep)
        hit = [c for c in viewers if rx.search(c["text"])]
        print(f"\n## '{args.grep}' 가 들어간 댓글 {len(hit)}개")
        for c in sorted(hit, key=lambda c: c["likes"], reverse=True)[:15]:
            print(f"- ({c['likes']}) {c['text'][:160]}")
    print("\n댓글을 콘텐츠에 쓸 때는 표현을 그대로 옮기지 말고 요약한다(작성자 노출 금지).")
    return 0


# ---------------------------------------------------------------- channel

def resolve_channel(raw: str) -> dict:
    raw = raw.strip()
    m = re.search(r"(UC[A-Za-z0-9_-]{22})", raw)
    params = {"id": m.group(1)} if m else {"forHandle": "@" + re.sub(r"^.*/@|^@", "", raw).split("/")[0]}
    data = yt("channels", part="snippet,statistics,contentDetails", **params)
    items = data.get("items", [])
    if not items:
        raise ApiError(f"채널을 찾지 못했습니다: {raw}")
    return items[0]


def cmd_channel(args) -> int:
    ch = resolve_channel(args.channel)
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, token = [], None
    while len(ids) < args.max:
        data = yt("playlistItems", part="contentDetails", playlistId=uploads, maxResults=min(50, args.max - len(ids)), pageToken=token)
        ids += [it["contentDetails"]["videoId"] for it in data.get("items", [])]
        token = data.get("nextPageToken")
        if not token:
            break
    rows = video_rows(ids)
    st = ch.get("statistics", {})
    print(f"# {ch['snippet']['title']} · 구독 {int(st.get('subscriberCount', 0)):,} · 영상 {st.get('videoCount')} · 최근 {len(rows)}개\n")
    print(md(["게시일", "제목", "조회", "좋아요", "댓글", "길이"],
             [[r["publishedAt"][:10], r["title"][:44], f"{r['viewCount']:,}", r["likeCount"], r["commentCount"],
               fmt_len(parse_duration(r["duration"]))] for r in rows]))
    if args.save:
        out = {"channelId": ch["id"], "channelTitle": ch["snippet"]["title"], "videos": [
            {k: r[k] for k in ("videoId", "title", "publishedAt", "viewCount", "likeCount", "commentCount", "duration")} for r in rows]}
        Path(args.save).parent.mkdir(parents=True, exist_ok=True)
        Path(args.save).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\n저장: {args.save}  → python3 analyze_videos.py {args.save}")
    return 0


# ---------------------------------------------------------------- set-key

def cmd_set_key(args) -> int:
    import getpass
    print("Google Cloud 콘솔에서 만든 YouTube Data API 키를 붙여넣고 Enter (화면에 안 보이는 게 정상).")
    key = getpass.getpass("API 키: ").strip().strip('"')
    if not key:
        print("입력이 비었습니다.", file=sys.stderr)
        return 1
    try:
        http_get_json(API + "videos?" + urllib.parse.urlencode({"part": "id", "id": "jNQXAC9IVRw", "key": key}))
    except urllib.error.HTTPError as e:
        print(explain(e.code, e.read().decode("utf-8", errors="replace")), file=sys.stderr)
        return 3
    KEY_FILE.write_text(json.dumps({"key": key}) + "\n", encoding="utf-8")
    try:
        os.chmod(KEY_FILE, 0o600)
    except OSError:
        pass
    print(f"확인 완료, 저장했습니다: {KEY_FILE}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("suggest"); s.add_argument("keyword"); s.add_argument("--expand", action="store_true")
    r = sub.add_parser("search"); r.add_argument("keyword")
    r.add_argument("--days", type=int, default=365); r.add_argument("--format", choices=["any", "long", "short"], default="any")
    r.add_argument("--max", type=int, default=25); r.add_argument("--order", choices=["viewCount", "relevance", "date"], default="viewCount")
    r.add_argument("--json", help="결과를 JSON 으로 저장")
    c = sub.add_parser("comments"); c.add_argument("video")
    c.add_argument("--max", type=int, default=100); c.add_argument("--order", choices=["relevance", "time"], default="relevance")
    c.add_argument("--grep", help="이 정규식이 들어간 댓글만 따로 모음")
    h = sub.add_parser("channel"); h.add_argument("channel"); h.add_argument("--max", type=int, default=50); h.add_argument("--save")
    sub.add_parser("set-key")
    args = ap.parse_args()
    try:
        return {"suggest": cmd_suggest, "search": cmd_search, "comments": cmd_comments,
                "channel": cmd_channel, "set-key": cmd_set_key}[args.cmd](args)
    except ApiError as e:
        print(str(e), file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
