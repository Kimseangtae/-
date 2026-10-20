#!/usr/bin/env python3
"""
gongu-lab: 생성한 콘텐츠 파일이 로빈님 지침(절대 금지 목록·플랫폼 규칙)을 지키는지 검사한다.

파일 이름 규칙: <날짜>_<슬롯>_<산출물>.md   예) 2026-11-17_key_script.md
산출물 종류(마지막 토큰)가 검사 규칙을 정한다: script longdesc pin pin_gongu thumb shorts shorts_teaser
shorts_verify reels reels_verify carousel threads community
파일 맨 위의 `<!-- ... -->` 주석 줄은 메모로 보고 글자 수·줄 수 계산에서 뺀다.

종료코드: 오류가 있으면 1, 경고만 있으면 0.

  python3 lint_content.py output/2026-11-example/*.md
  python3 lint_content.py 파일.md --kind shorts
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

MEMBERSHIP = "https://www.youtube.com/channel/UCMSz_yah88yZMC6js2p149A/join"
KINDS = ["script", "longdesc", "pin", "pin_gongu", "thumb", "shorts", "shorts_teaser", "shorts_verify",
         "reels", "reels_verify", "carousel", "threads", "community"]

FORBIDDEN = [  # (정규식, 설명)
    (re.compile(r"밥\s*깡\s*패"), "'밥깡패' 는 모든 형태 금지 (채널명은 로빈의밥상)"),
    (re.compile(r"매실\s?(?:액|청|엑기스|원액|즙)"), "매실액(청) 금지 → 알룰로스 또는 채향원 블루베리 와인식초"),
    (re.compile(r"체\s?칼"), "'체칼' 아님 → '채칼'"),
]
PLACEHOLDER = re.compile(r"\[[^\]\n]*(?:입력|여기에|OOO|XXX|TODO|TBD)[^\]\n]*\]|\{\{|\}\}|OOO|XXX|TODO|TBD|○○|□□")
EXAGGERATION = re.compile(r"무조건|100\s?%\s?(?:보장|확실|효과)|역대급|최저가\s?보장|단언컨대|기적")
DRAWBACK = re.compile(r"단점|아쉬|무겁|불편|한계|비싸|부담|단,|다만")
URL = re.compile(r"https?://|www\.", re.I)
HASHTAG = re.compile(r"#[^\s#]+")

GONGU_KINDS = {"pin_gongu", "shorts_teaser", "shorts_verify", "reels_verify"}
KEY_KINDS = {"script", "pin_gongu", "carousel"}


def body_lines(text: str) -> list[str]:
    lines = text.splitlines()
    while lines and (not lines[0].strip() or lines[0].lstrip().startswith("<!--")):
        lines.pop(0)
    return [ln for ln in lines if not ln.lstrip().startswith("<!--")]


def kind_of(path: Path, override: str | None) -> str | None:
    if override:
        return override
    token = path.stem.split("_")[-1]
    # shorts_teaser 처럼 밑줄이 들어간 종류 처리
    two = "_".join(path.stem.split("_")[-2:])
    return two if two in KINDS else (token if token in KINDS else None)


def lint(path: Path, kind: str | None = None) -> tuple[list[str], list[str]]:
    errs: list[str] = []
    warns: list[str] = []
    text = path.read_text(encoding="utf-8")
    kind = kind_of(path, kind)
    if kind is None:
        errs.append(f"산출물 종류를 파일명에서 알 수 없음 (끝이 {KINDS} 중 하나여야 함)")
        kind = ""
    lines = body_lines(text)
    body = "\n".join(lines)
    nonempty = [ln for ln in lines if ln.strip()]
    if not nonempty:
        return ["내용이 비었음"], warns

    for rx, why in FORBIDDEN:
        for m in rx.finditer(body):
            errs.append(f"{why} — '{m.group(0)}'")
    for m in PLACEHOLDER.finditer(body):
        errs.append(f"자리표시자가 남아 있음 — '{m.group(0)}'")
    if EXAGGERATION.search(body):
        warns.append(f"과장 표현 의심 — '{EXAGGERATION.search(body).group(0)}' (마감·수량·효과는 실제 조건만)")
    if body.count("20년") > 1:
        errs.append(f"'20년 셰프' 가 {body.count('20년')}회 — 콘텐츠 전체에서 딱 1회")

    tags = HASHTAG.findall(body)

    if kind in ("pin", "pin_gongu"):
        if len(nonempty) != 3:
            errs.append(f"고정 댓글은 정확히 3줄 (지금 {len(nonempty)}줄)")
        if kind == "pin" and URL.search(body):
            warns.append("일반 고정 댓글에 링크가 있음 — 공구용이면 pin_gongu 로")
        if kind == "pin_gongu" and not URL.search(body):
            errs.append("공구용 고정 댓글에 구매 링크가 없음 (링크 포함 3줄)")

    elif kind == "longdesc":
        if len(tags) != 3 or "#로빈의밥상" not in tags:
            errs.append(f"해시태그는 3개, #로빈의밥상 필수 (지금 {tags})")
        if "밥상 식구님들" not in body:
            errs.append("CTA 에 '밥상 식구님들' 필수")
        if MEMBERSHIP not in body:
            errs.append("멤버십 링크 누락")
        if not re.search(r"^\s*00:00\s*\|\s*인트로", body, re.M):
            errs.append("타임라인 첫 줄 '00:00 | 인트로' 없음")
        chapters = re.findall(r"^\s*\d{1,2}:\d{2}\s*\|", body, re.M)
        if not 8 <= len(chapters) <= 10:
            warns.append(f"챕터 {len(chapters)}개 (8~10개)")
        if "20년" not in body:
            warns.append("'20년 셰프' 권위 문구가 1회도 없음")

    elif kind.startswith("shorts"):
        title = re.sub(r"^\s*(?:제목\s*[:：]\s*)", "", nonempty[0]).strip()
        if len(title) > 30:
            errs.append(f"후킹 제목 {len(title)}자 (30자 이내): {title}")
        if len(tags) != 3 or "#로빈의밥상" not in tags:
            errs.append(f"해시태그는 3개, #로빈의밥상 필수 (지금 {tags})")
        if URL.search(body):
            errs.append("쇼츠 설명글에 외부 링크 금지")
        if kind == "shorts" and "본 영상" not in body:
            errs.append("일반 쇼츠는 CTA 가 '본 영상' 유도여야 함")
        if kind == "shorts" and re.search(r"댓글", body):
            warns.append("일반 쇼츠에서 댓글 유도 금지 (공구 티저만 허용)")
        main = "\n".join(nonempty[1:])
        main_len = len(re.sub(r"\s", "", HASHTAG.sub("", main)))
        if not 200 <= main_len <= 420:
            warns.append(f"본문 {main_len}자 (약 300자 권장)")

    elif kind in ("reels", "reels_verify"):
        if tags:
            errs.append("인스타 릴스는 해시태그 금지")
        if "프로필" not in body:
            warns.append("프로필 링크 CTA 가 없음")

    elif kind == "carousel":
        if "프로필" not in body and "저장" not in body and "댓글" not in body:
            warns.append("행동 지시(저장/댓글/프로필)가 없음 — 마지막 장에 행동 1개")

    elif kind == "threads":
        if "밥상 식구님" in body:
            errs.append("스레드는 '스친이들' 반말체 — '밥상 식구님' 은 유튜브용")
        if re.search(r"(?:습니다|니다|세요|해요|예요)[.!?\s]*$", body, re.M):
            warns.append("스레드는 반말체 — 존댓말 어미가 보임")
        if tags and "#로빈의밥상" not in tags:
            errs.append("해시태그를 쓰면 #로빈의밥상 포함")

    elif kind == "community":
        if "밥상 식구님들" not in body:
            errs.append("커뮤니티 글은 '밥상 식구님들' 호칭 필수")

    elif kind == "thumb":
        for ln in nonempty:
            n = len(re.sub(r"\s", "", re.sub(r"^\s*[-*\d.)]+\s*", "", ln)))
            if ln.lstrip().startswith(("-", "*")) and not 14 <= n <= 18:
                warns.append(f"썸네일 문구 {n}자 (14~18자): {ln.strip()[:30]}")

    elif kind == "script":
        for act in range(0, 6):
            if f"{act}막" not in body:
                warns.append(f"{act}막 표시 없음 (6막 구성)")
        if "20년" not in body:
            warns.append("'20년 셰프' 권위 문구가 1회도 없음")
        if "[강조]" not in body:
            warns.append("[강조] 태그가 한 번도 없음")

    if kind in KEY_KINDS and not DRAWBACK.search(body):
        warns.append("단점·한계 언급이 보이지 않음 — 장점만 나열 금지, 단점 먼저")
    if kind in GONGU_KINDS and body.count("마감") and not re.search(r"\d", body):
        warns.append("마감을 말하면서 일시·수량 숫자가 없음 — 실제 조건을 적는다")
    return errs, warns


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--kind", choices=KINDS, help="파일명 대신 종류를 직접 지정")
    args = ap.parse_args()
    bad = 0
    for f in args.files:
        errs, warns = lint(Path(f), args.kind)
        mark = "✗" if errs else ("△" if warns else "✓")
        print(f"{mark} {f}")
        for e in errs:
            print(f"    오류: {e}")
        for w in warns:
            print(f"    경고: {w}")
        bad += bool(errs)
    print(f"\n{len(args.files)}개 검사 · 오류 파일 {bad}개")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
