#!/usr/bin/env python3
"""
gongu-lab: 레퍼런스 채널 영상 지표 분석기.

입력은 vidIQ `vidiq_channel_videos` 응답 JSON(그대로 저장한 것) 또는 같은 필드의 리스트 파일이다.
필드: videoId, title, publishedAt, viewCount, likeCount, commentCount, duration(ISO8601), vph, breakoutScore
(선택) description, pinnedComment — 있으면 공구 후보 판정에 같이 쓴다.

하는 일
  1. 채널·형식(롱폼/쇼츠)별 기준선(조회수 중앙값)을 만든다.
  2. 영상마다 기준선 대비 배수, 좋아요율, 댓글률(조회 1천당)을 계산하고
     채널 안 백분위 평균으로 "종합 반응 점수"를 매긴다.
  3. 종합 상위·댓글 상위 영상을 뽑는다.
  4. 상위 25% 영상 제목에 어떤 요소가 더 자주 나오는지(리프트) 센다.
  5. 공구 후보(제목·설명 키워드) 또는 tags.json 으로 사람이 표시한 공구 영상을 나머지와 비교한다.

공구 영상은 "정보 다큐 위장"이라 제목에 '공구'가 안 나오는 경우가 많다. 키워드 판정은 후보일 뿐이고,
설명·고정댓글·대본을 읽고 확정한 것은 data/tags.json 에 적어 넣는다:
  { "영상ID": { "role": "key|teaser|education|other", "campaign": "캠페인명", "appeal": "난이도 해소|속도 향상|선택 대행" } }

사용 예
  python3 analyze_videos.py data/videos/*.json
  python3 analyze_videos.py data/videos/*.json --tags data/tags.json --top 8 --json data/analysis.json
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

GONGU_WORDS = re.compile(
    r"공구|공동\s?구매|특가|한정\s?수량|오픈\s?(?:일|시간)|마감|구매\s?링크|최저가|런칭|사전\s?예약|증정|"
    r"파격|선착순|재입고|프로필\s?링크|고정\s?댓글|유료\s?광고|협찬|제품\s?지원",
)
SHORT_MAX_SEC = 180
MIN_N = 8  # 채널·형식별 통계를 믿으려면 최소 영상 수
MIN_RATIO = 0.5  # 상위 표에 올리려면 채널 중앙값의 절반 이상 조회가 나와야 한다 (비율 지표는 조회가 작을수록 부풀기 때문)
W_VIEW, W_LIKE, W_COM = 0.5, 0.25, 0.25

TITLE_FEATURES = {
    "숫자 포함": re.compile(r"\d"),
    "퍼센트·'90%가 모르는'류": re.compile(r"\d+\s?%"),
    "금지·부정 명령(~마세요/그만)": re.compile(r"마세요|말고|그만|절대|하지\s?마"),
    "의문·반문(?, 왜, 몰랐)": re.compile(r"\?|왜|몰랐|모르"),
    "느낌표": re.compile(r"!"),
    "정답 숨김(이것/이방법/이렇게)": re.compile(r"이것|이\s?방법|이렇게|'이"),
    "금액·절약": re.compile(r"\d+\s?(?:만\s?)?원|아끼|절약|사먹지|사 먹지|사드세요"),
    "권위(셰프·경력·사장님)": re.compile(r"셰프|세프|경력|사장님|대박집|전문점"),
    "손해 회피(손해·버립니다·속지)": re.compile(r"손해|버립니다|버려|속지|속으|낭비"),
    "건강 효능(혈당·뱃살·노화·보약)": re.compile(r"혈당|뱃살|노화|보약|항염|노안|다이어트|건강"),
}


def parse_duration(iso: str | None) -> int:
    if not iso:
        return 0
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
    if not m:
        return 0
    h, mi, s = (int(x or 0) for x in m.groups())
    return h * 3600 + mi * 60 + s


def load_videos(paths: list[str]) -> list[dict]:
    out = []
    for p in paths:
        path = Path(p)
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            channel = data.get("channelTitle") or path.stem
            videos = data.get("videos", [])
            fmt_hint = data.get("videoFormat")
        else:
            channel, videos, fmt_hint = path.stem, data, None
        for v in videos:
            sec = parse_duration(v.get("duration"))
            fmt = fmt_hint if fmt_hint in ("long", "short") else ("short" if 0 < sec <= SHORT_MAX_SEC else "long")
            out.append(
                {
                    "channel": channel,
                    "id": v.get("videoId", ""),
                    "title": v.get("title", ""),
                    "published": (v.get("publishedAt") or "")[:10],
                    "views": int(v.get("viewCount") or 0),
                    "likes": int(v.get("likeCount") or 0),
                    "comments": int(v.get("commentCount") or 0),
                    "seconds": sec,
                    "format": fmt,
                    "vph": v.get("vph"),
                    "breakout": v.get("breakoutScore"),
                    "text": " ".join(str(v.get(k) or "") for k in ("title", "description", "pinnedComment")),
                }
            )
    return out


def pct_ranks(values: list[float]) -> list[float]:
    """0~100 백분위. 동점은 평균 순위."""
    n = len(values)
    if n == 1:
        return [50.0]
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2
        for k in range(i, j + 1):
            ranks[order[k]] = avg / (n - 1) * 100
        i = j + 1
    return ranks


def score(videos: list[dict]) -> dict:
    groups: dict[tuple, list[dict]] = {}
    for v in videos:
        groups.setdefault((v["channel"], v["format"]), []).append(v)
    baselines = {}
    for (ch, fmt), vs in groups.items():
        med = statistics.median(x["views"] for x in vs) or 1
        baselines[f"{ch}|{fmt}"] = {
            "channel": ch, "format": fmt, "n": len(vs), "median_views": med,
            "reliable": len(vs) >= MIN_N,
        }
        for v in vs:
            views = max(v["views"], 1)
            v["ratio"] = v["views"] / med
            v["like_rate"] = v["likes"] / views * 100
            v["comment_rate"] = v["comments"] / views * 1000
        r_view = pct_ranks([v["ratio"] for v in vs])
        r_like = pct_ranks([v["like_rate"] for v in vs])
        r_com = pct_ranks([v["comment_rate"] for v in vs])
        for v, a, b, c in zip(vs, r_view, r_like, r_com):
            v["score"] = round(W_VIEW * a + W_LIKE * b + W_COM * c, 1)
    return baselines


def title_lift(videos: list[dict]) -> list[dict]:
    """채널·형식별 상위 25% 안에서 각 제목 요소의 출현율이 전체보다 얼마나 높은지."""
    top, allv = [], []
    groups: dict[tuple, list[dict]] = {}
    for v in videos:
        groups.setdefault((v["channel"], v["format"]), []).append(v)
    for vs in groups.values():
        if len(vs) < MIN_N:
            continue
        vs_sorted = sorted(vs, key=lambda x: x["score"], reverse=True)
        cut = max(2, len(vs) // 4)
        top += vs_sorted[:cut]
        allv += vs
    if not top:
        return []
    rows = []
    for name, rx in TITLE_FEATURES.items():
        p_top = sum(bool(rx.search(v["title"])) for v in top) / len(top)
        p_all = sum(bool(rx.search(v["title"])) for v in allv) / len(allv)
        lift = p_top / p_all if p_all else None
        rows.append({"feature": name, "top_share": round(p_top * 100), "all_share": round(p_all * 100),
                     "lift": round(lift, 2) if lift else None, "n_top": len(top), "n_all": len(allv)})
    rows.sort(key=lambda r: (r["lift"] or 0), reverse=True)
    return rows


def fmt_n(n: float) -> str:
    return f"{n:,.0f}"


def table(rows: list[list], header: list[str]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def video_row(v: dict, tag: str = "") -> list:
    return [v["channel"], v["published"], f"{v['title'][:46]}{'…' if len(v['title']) > 46 else ''}",
            fmt_n(v["views"]), f"{v['ratio']:.1f}×", f"{v['like_rate']:.1f}%", f"{v['comment_rate']:.1f}",
            v["score"], tag]


VIDEO_HEADER = ["채널", "게시일", "제목", "조회수", "기준선 대비", "좋아요율", "댓글/천회", "종합", "공구"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", help="vidIQ channel_videos 응답 JSON 파일들")
    ap.add_argument("--tags", help="사람이 확정한 공구 영상 태그 JSON")
    ap.add_argument("--top", type=int, default=8, help="표마다 보여줄 영상 수")
    ap.add_argument("--format", choices=["long", "short", "all"], default="all")
    ap.add_argument("--json", help="계산 결과 전체를 이 경로에 JSON 으로 저장")
    args = ap.parse_args()

    videos = load_videos(args.files)
    if not videos:
        print("영상이 없습니다.", file=sys.stderr)
        return 1
    tags = json.loads(Path(args.tags).read_text(encoding="utf-8")) if args.tags and Path(args.tags).exists() else {}
    if args.format != "all":
        videos = [v for v in videos if v["format"] == args.format]

    baselines = score(videos)
    for v in videos:
        t = tags.get(v["id"])
        v["gongu"] = f"확정:{t.get('role', '?')}" if t else ("후보" if GONGU_WORDS.search(v["text"]) else "")

    lines = ["# 레퍼런스 영상 반응 분석", ""]
    lines += ["## 1. 채널 기준선 (조회수 중앙값)", "",
              table([[b["channel"], "롱폼" if b["format"] == "long" else "쇼츠", b["n"], fmt_n(b["median_views"]),
                      "" if b["reliable"] else f"⚠ {MIN_N}개 미만, 참고용"] for b in baselines.values()],
                    ["채널", "형식", "영상 수", "중앙값 조회수", "신뢰"]), ""]

    solid = [v for v in videos if v["ratio"] >= MIN_RATIO]
    top = sorted(solid, key=lambda v: v["score"], reverse=True)[: args.top]
    lines += [f"## 2. 종합 반응 상위 {len(top)}",
              "", f"종합 = 조회 배수 {W_VIEW:.0%} + 좋아요율 {W_LIKE:.0%} + 댓글률 {W_COM:.0%} (각각 채널 안 백분위). "
              f"기준선의 {MIN_RATIO:.0%} 미만 조회 영상은 비율이 부풀어 제외.", "",
              table([video_row(v, v["gongu"]) for v in top], VIDEO_HEADER), ""]

    by_com = sorted(solid, key=lambda v: v["comment_rate"], reverse=True)[: args.top]
    lines += [f"## 3. 댓글률 상위 {len(by_com)} (조회 1천당 댓글, 기준선 {MIN_RATIO:.0%} 이상 조회만)", "",
              table([video_row(v, v["gongu"]) for v in by_com], VIDEO_HEADER), ""]

    lift = title_lift(videos)
    if lift:
        lines += ["## 4. 상위 25% 영상 제목에 더 자주 나오는 요소",
                  "", f"기준: 영상 {MIN_N}개 이상인 채널·형식만. 리프트 1.0 = 전체와 같음, 1.3 이상이면 의미 있는 신호로 본다.", "",
                  table([[r["feature"], f"{r['top_share']}%", f"{r['all_share']}%", r["lift"] if r["lift"] else "-"]
                         for r in lift], ["제목 요소", "상위 25%", "전체", "리프트"]), ""]

    gongu = [v for v in videos if v["gongu"]]
    rest = [v for v in videos if not v["gongu"]]
    lines += ["## 5. 공구 영상 vs 일반 영상"]
    if gongu and rest:
        med = lambda xs: statistics.median(xs)  # noqa: E731
        lines += ["", table(
            [["공구(후보·확정)", len(gongu), f"{med([v['ratio'] for v in gongu]):.2f}×",
              f"{med([v['like_rate'] for v in gongu]):.2f}%", f"{med([v['comment_rate'] for v in gongu]):.2f}"],
             ["일반", len(rest), f"{med([v['ratio'] for v in rest]):.2f}×",
              f"{med([v['like_rate'] for v in rest]):.2f}%", f"{med([v['comment_rate'] for v in rest]):.2f}"]],
            ["구분", "영상 수", "기준선 대비(중앙값)", "좋아요율(중앙값)", "댓글/천회(중앙값)"]), ""]
        n_conf = sum(v["gongu"].startswith("확정") for v in videos)
        if n_conf == 0:
            lines += ["⚠ 확정 태그가 없어 키워드 후보만으로 비교했다. 후보는 오탐·누락이 많다(정보 다큐 위장 영상은 제목에 안 드러남). "
                      "설명·고정댓글·대본을 읽고 `data/tags.json` 에 확정 태그를 적은 뒤 다시 돌린다.", ""]
        lines += ["### 공구 영상 목록", "", table([video_row(v, v["gongu"]) for v in sorted(gongu, key=lambda x: x["score"], reverse=True)[:20]], VIDEO_HEADER), ""]
    else:
        lines += ["", "공구 후보가 없다(또는 전부 공구). 설명·고정댓글을 가져와 `pinnedComment` 필드로 넣거나 tags.json 으로 직접 표시한다.", ""]

    print("\n".join(lines))
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(
            json.dumps({"baselines": baselines, "videos": videos, "title_lift": lift}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
