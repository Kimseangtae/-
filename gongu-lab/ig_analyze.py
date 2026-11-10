#!/usr/bin/env python3
"""
gongu-lab: 인스타그램 캐러셀 분석 도구. ig_collect.py 가 모은 data/ig/<핸들>/ 위에서 동작한다.

분업
  이 스크립트  : 반응 순위 매기기, 분석 대상 고르기, 슬라이드 모아보기, 결과 검증, 패턴 통계 (숫자 계산 전부)
  클로드(비전) : 슬라이드 이미지를 직접 보고 글자를 옮겨 적고 역할·구조를 판독해 <shortcode>/analysis.json 으로 저장
                 (판독 기준은 .claude/skills/gongu-lab/carousel-analysis.md)

명령
  rank     핸들...        캐러셀 반응 점수 계산 → 상위·하위 K개를 분석 대기열(queue.json)에 올린다
  sheet    핸들 shortcode  슬라이드를 한 장으로 모은 sheet.jpg 생성 (Pillow 필요, 흐름 파악용)
  validate [핸들...]      수집 장수·이미지 파일·analysis.json 형식 점검. 문제가 있으면 종료코드 1
  stats    [핸들...]      analysis.json 이 있는 캐러셀로 어떤 구조·훅·CTA 가 반응이 좋은지 집계

사용 예
  python3 ig_analyze.py rank 핸들 --k 8
  python3 ig_analyze.py validate 핸들
  python3 ig_analyze.py stats --out analysis/carousel-patterns.md
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_videos import pct_ranks  # noqa: E402

HERE = Path(__file__).resolve().parent
DATA = HERE / "data" / "ig"

HOOK_TYPES = ["상식뒤집기", "숫자리스트", "질문", "손해경고", "비포애프터", "권위·경력", "공감·장면", "기타"]
ROLES = ["hook", "problem", "cause", "evidence", "steps", "comparison", "reveal", "summary", "cta", "other"]
CTA_TYPES = ["저장", "댓글", "팔로우", "프로필링크", "DM", "공유", "없음"]
APPEALS = ["난이도 해소", "속도 향상", "선택 대행", "해당 없음"]
MIN_CAROUSELS = 6   # 이보다 적으면 순위가 의미 없다
W_LIKE, W_COM = 0.6, 0.4


def load_store(handle: str) -> dict:
    p = DATA / handle / "posts.json"
    if not p.exists():
        sys.exit(f"{p} 가 없습니다. 먼저 ig_collect.py 로 수집하세요.")
    return json.loads(p.read_text(encoding="utf-8"))


def all_handles() -> list[str]:
    return sorted(d.name for d in DATA.iterdir() if d.is_dir() and (d / "posts.json").exists()) if DATA.exists() else []


def score_carousels(store: dict) -> list[dict]:
    """계정 안 캐러셀끼리만 비교한다. 좋아요를 숨긴 게시물은 댓글만으로 점수를 낸다."""
    car = [p for p in store["posts"] if p.get("kind") == "carousel"]
    if not car:
        return []
    likes = [p["likes"] for p in car if p.get("likes") is not None]
    med_likes = statistics.median(likes) if likes else None
    comments = [p.get("comments") or 0 for p in car]
    r_com = pct_ranks(comments)
    like_vals = [p["likes"] if p.get("likes") is not None else None for p in car]
    r_like_known = pct_ranks([v for v in like_vals if v is not None]) if likes else []
    it = iter(r_like_known)
    followers = store.get("followers")
    for p, rc, lv in zip(car, r_com, like_vals):
        rl = next(it) if lv is not None else None
        p["score"] = round(W_LIKE * rl + W_COM * rc, 1) if rl is not None else round(rc, 1)
        p["like_ratio"] = round(p["likes"] / med_likes, 2) if (med_likes and p.get("likes") is not None) else None
        p["er_followers"] = round(((p.get("likes") or 0) + (p.get("comments") or 0)) / followers * 100, 2) if followers else None
        p["likes_hidden"] = p.get("likes") is None
    return sorted(car, key=lambda p: p["score"], reverse=True)


def analysis_path(handle: str, code: str) -> Path:
    return DATA / handle / code / "analysis.json"


def md_table(header: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


# ---------------------------------------------------------------- rank

def cmd_rank(args) -> int:
    for handle in args.handles:
        store = load_store(handle)
        car = score_carousels(store)
        print(f"## @{handle} 캐러셀 반응 순위 (캐러셀 {len(car)}개)\n")
        if len(car) < MIN_CAROUSELS:
            print(f"⚠ 캐러셀이 {MIN_CAROUSELS}개 미만이라 순위는 참고용이다. 더 수집한 뒤 다시 돌린다.\n")
        if not car:
            continue
        k = len(car) if args.all else min(args.k, max(1, len(car) // 2))
        top, bottom = car[:k], ([] if args.all else [p for p in car[-k:] if p not in car[:k]])
        queue = []
        rows = []
        for bucket, group in (("top", top), ("bottom", bottom)):
            for p in group:
                if not p.get("slides_complete"):
                    status = "slides_incomplete"
                elif analysis_path(handle, p["shortcode"]).exists():
                    status = "analyzed"
                else:
                    status = "needs_analysis"
                queue.append({"shortcode": p["shortcode"], "bucket": bucket, "score": p["score"], "status": status})
                rows.append([bucket, p["shortcode"], (p.get("taken_at") or "")[:10], len(p.get("slides", [])),
                             "숨김" if p["likes_hidden"] else p.get("likes"), p.get("comments"),
                             p["like_ratio"] if p["like_ratio"] is not None else "-", p["score"], status,
                             (p.get("caption") or "").replace("\n", " ")[:28]])
        print(md_table(["구분", "코드", "게시일", "장수", "좋아요", "댓글", "중앙값 대비", "점수", "상태", "캡션"], rows))
        (DATA / handle / "queue.json").write_text(json.dumps(
            {"handle": handle, "note": "top=반응 좋은 쪽, bottom=나쁜 쪽. 둘을 대조해야 패턴이 보인다.", "queue": queue},
            ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        counts = Counter(q["status"] for q in queue)
        print(f"\n대기열 저장: data/ig/{handle}/queue.json · " + ", ".join(f"{k} {v}" for k, v in counts.items()) + "\n")
    return 0


# ---------------------------------------------------------------- sheet

def cmd_sheet(args) -> int:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("Pillow 가 없습니다: pip install pillow", file=sys.stderr)
        return 2
    d = DATA / args.handle / args.code
    files = sorted(p for p in d.glob("slide-*.*") if p.suffix.lower() in (".jpg", ".png", ".webp"))
    if not files:
        print(f"{d} 에 슬라이드 이미지가 없습니다.", file=sys.stderr)
        return 1
    cols = min(5, len(files))
    cell_w = 360
    thumbs = []
    for f in files:
        im = Image.open(f).convert("RGB")
        im.thumbnail((cell_w, int(cell_w * 1.4)))
        thumbs.append(im)
    cell_h = max(t.height for t in thumbs)
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (cell_w + 8) + 8, rows * (cell_h + 8) + 8), (245, 245, 245))
    draw = ImageDraw.Draw(sheet)
    for i, t in enumerate(thumbs):
        x, y = 8 + (i % cols) * (cell_w + 8), 8 + (i // cols) * (cell_h + 8)
        sheet.paste(t, (x, y))
        draw.rectangle([x, y, x + 34, y + 24], fill=(220, 40, 40))
        draw.text((x + 8, y + 6), str(i + 1), fill=(255, 255, 255))
    out = d / "sheet.jpg"
    sheet.save(out, quality=88)
    print(f"저장: {out} ({len(files)}장). 글자 판독은 sheet 가 아니라 slide-NN 원본으로 한다.")
    return 0


# ---------------------------------------------------------------- validate

def validate_analysis(a: dict, n_files: int) -> tuple[list[str], list[str]]:
    errs, warns = [], []
    for key in ("hook_type", "hook_text", "slides", "cta", "appeal"):
        if key not in a:
            errs.append(f"'{key}' 없음")
    if errs:
        return errs, warns
    if a["hook_type"] not in HOOK_TYPES:
        errs.append(f"hook_type '{a['hook_type']}' 는 {HOOK_TYPES} 중 하나여야 함")
    if a["appeal"] not in APPEALS:
        errs.append(f"appeal '{a['appeal']}' 는 {APPEALS} 중 하나여야 함")
    cta = a["cta"]
    if cta.get("type") not in CTA_TYPES:
        errs.append(f"cta.type '{cta.get('type')}' 는 {CTA_TYPES} 중 하나여야 함")
    slides = a["slides"]
    if len(slides) != n_files:
        errs.append(f"분석한 슬라이드 {len(slides)}장 ≠ 수집한 이미지 {n_files}장 (빠뜨린 장이 있음)")
    for i, s in enumerate(slides, 1):
        if s.get("n") != i:
            errs.append(f"슬라이드 번호 {i}번 자리에 n={s.get('n')}")
        if s.get("role") not in ROLES:
            errs.append(f"{i}장 role '{s.get('role')}' 는 {ROLES} 중 하나여야 함")
        if not (s.get("text") or "").strip() and not s.get("no_text"):
            errs.append(f"{i}장 text 가 비었음 (글자가 정말 없으면 no_text: true)")
        if not (s.get("visual") or "").strip():
            warns.append(f"{i}장 visual(디자인 묘사) 없음")
    if slides and a["hook_text"].strip() and a["hook_text"].strip() not in (slides[0].get("text") or ""):
        warns.append("hook_text 가 1장 text 에 그대로 들어있지 않음 (원문 그대로 옮겼는지 확인)")
    if cta.get("type") != "없음" and not (1 <= int(cta.get("slide") or 0) <= max(len(slides), 1)):
        errs.append("cta.slide 가 1~장수 범위를 벗어남")
    if not (a.get("transferable") or "").strip():
        warns.append("transferable(로빈님 콘텐츠에 가져올 것) 비었음")
    return errs, warns


def cmd_validate(args) -> int:
    handles = args.handles or all_handles()
    problems = 0
    for handle in handles:
        store = load_store(handle)
        by_code = {p["shortcode"]: p for p in store["posts"]}
        qf = DATA / handle / "queue.json"
        codes = [q["shortcode"] for q in json.loads(qf.read_text(encoding="utf-8"))["queue"]] if qf.exists() else \
            [c for c, p in by_code.items() if p.get("kind") == "carousel"]
        print(f"## @{handle} (점검 대상 {len(codes)}개)")
        todo = 0
        for code in codes:
            post = by_code.get(code)
            d = DATA / handle / code
            files = sorted(p for p in d.glob("slide-*.*") if p.suffix.lower() in (".jpg", ".png", ".webp") and p.stat().st_size > 0)
            exp = (post or {}).get("expected_slides")
            msgs = []
            if post is None:
                msgs.append("posts.json 에 없음")
            elif exp and len(files) < exp:
                msgs.append(f"이미지 {len(files)}장 < 기대 {exp}장")
            elif not files:
                msgs.append("이미지 없음")
            try:
                from PIL import Image
                for f in files:
                    try:
                        with Image.open(f) as im:
                            im.verify()
                    except Exception:
                        msgs.append(f"{f.name} 손상")
            except ImportError:
                pass
            ap = analysis_path(handle, code)
            warns: list[str] = []
            if not ap.exists():
                todo += 1
            else:
                try:
                    a = json.loads(ap.read_text(encoding="utf-8"))
                    e, warns = validate_analysis(a, len(files))
                    msgs += [f"analysis.json: {x}" for x in e]
                except json.JSONDecodeError as ex:
                    msgs.append(f"analysis.json JSON 오류: {ex}")
            for m in msgs:
                print(f"  ✗ {code}: {m}")
            for w in warns:
                print(f"  △ {code}: {w}")
            problems += len(msgs)
        print(f"  분석 미작성 {todo}개 · 오류 {problems}건\n")
    return 1 if problems else 0


# ---------------------------------------------------------------- stats

def density_bucket(a: dict) -> str:
    chars = [len("".join((s.get("text") or "").split())) for s in a["slides"]]
    avg = sum(chars) / len(chars) if chars else 0
    return "짧음(≤30자/장)" if avg <= 30 else "중간(31~80자/장)" if avg <= 80 else "길음(80자+/장)"


def count_bucket(n: int) -> str:
    return "≤5장" if n <= 5 else "6~7장" if n <= 7 else "8~10장" if n <= 10 else "11장+"


def signature(a: dict) -> str:
    seq = []
    for s in a["slides"]:
        if not seq or seq[-1] != s["role"]:
            seq.append(s["role"])
    return ">".join(seq)


def features(a: dict) -> dict[str, str]:
    first = (a["slides"][0].get("text") or "") if a["slides"] else ""
    return {
        "장수": count_bucket(len(a["slides"])),
        "훅 유형": a["hook_type"],
        "1장에 숫자": "있음" if any(ch.isdigit() for ch in first) else "없음",
        "글자 밀도": density_bucket(a),
        "CTA 유형": a["cta"].get("type", "없음"),
        "소구점": a["appeal"],
        "단점 먼저": "예" if a.get("drawback_first") else "아니오",
        "공구 관련": "예" if a.get("gongu") else "아니오",
        "구조(역할 순서)": signature(a),
    }


def cmd_stats(args) -> int:
    rows = []  # (handle, post, analysis)
    for handle in args.handles or all_handles():
        store = load_store(handle)
        scored = {p["shortcode"]: p for p in score_carousels(store)}
        n = len(scored)
        for rank, (code, p) in enumerate(scored.items()):
            ap = analysis_path(handle, code)
            if ap.exists():
                p["_rank_share"] = rank / max(n - 1, 1)  # 0=최상위, 1=최하위
                rows.append((handle, p, json.loads(ap.read_text(encoding="utf-8"))))
    lines = ["# 인스타 캐러셀 패턴 통계", ""]
    if len(rows) < 4:
        lines += [f"분석 완료 캐러셀이 {len(rows)}개뿐이라 통계를 내지 않는다. 최소 4개(상위·하위 각 2개 이상), 권장 12개 이상.", ""]
        print("\n".join(lines))
        return 0
    lines += [f"분석 완료 {len(rows)}개 · 계정 {len({h for h, _, _ in rows})}개. 점수는 계정 안 캐러셀끼리의 순위(좋아요 {W_LIKE:.0%} + 댓글 {W_COM:.0%}).",
              "표본 3개 미만 항목은 ⚠ 로 표시했고 결론에 쓰지 않는다. 표본이 작은 동안 이 표는 가설이다.",
              "읽을 때 주의 두 가지: (1) 항목을 하나씩 따로 본 표라 장수·훅·CTA 가 한꺼번에 움직이면 어느 것이 원인인지 가를 수 없다. "
              "표마다 같은 게시물이 반복해서 위에 오르면 그 게시물의 '조합'을 하나의 패턴으로 읽는다. "
              "(2) 분석 대상을 상위·하위 위주로 골랐으면 '상위 3분의 1 비율'이 실제보다 극단적으로 나온다. 방향만 본다.", ""]
    groups: dict[str, dict[str, list]] = {}
    for _h, p, a in rows:
        for feat, val in features(a).items():
            groups.setdefault(feat, {}).setdefault(val, []).append(p)
    for feat, vals in groups.items():
        if feat == "구조(역할 순서)":
            vals = {k: v for k, v in vals.items() if len(v) >= 2}
            if not vals:
                continue
        table = []
        for val, ps in sorted(vals.items(), key=lambda kv: statistics.median(x["score"] for x in kv[1]), reverse=True):
            top_share = sum(x["_rank_share"] <= 0.33 for x in ps) / len(ps)
            lr = [x["like_ratio"] for x in ps if x["like_ratio"] is not None]
            table.append([val, len(ps) if len(ps) >= 3 else f"{len(ps)} ⚠", f"{statistics.median(x['score'] for x in ps):.0f}",
                          f"{statistics.median(lr):.2f}×" if lr else "-", f"{top_share:.0%}"])
        lines += [f"## {feat}", "", md_table(["값", "개수", "점수 중앙값", "좋아요 중앙값 대비", "상위 3분의 1 비율"], table), ""]
    out = "\n".join(lines)
    print(out)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(out + "\n", encoding="utf-8")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("rank")
    r.add_argument("handles", nargs="+")
    r.add_argument("--k", type=int, default=8, help="상위·하위 각각 몇 개")
    r.add_argument("--all", action="store_true", help="캐러셀 전부를 대기열에")
    s = sub.add_parser("sheet")
    s.add_argument("handle")
    s.add_argument("code")
    v = sub.add_parser("validate")
    v.add_argument("handles", nargs="*")
    st = sub.add_parser("stats")
    st.add_argument("handles", nargs="*")
    st.add_argument("--out", help="결과를 마크다운 파일로도 저장")
    args = ap.parse_args()
    return {"rank": cmd_rank, "sheet": cmd_sheet, "validate": cmd_validate, "stats": cmd_stats}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
