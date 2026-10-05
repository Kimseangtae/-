# -*- coding: utf-8 -*-
"""
테마 밥상 추천 (로빈 요리·공구 작업실 추가 부품)

바디프랜드 안마의자의 '사주운세·성격유형·별자리 테마 마사지' 구조를 요리에 옮긴 것.
  기질 정보 입력 → 테마 풀이(계산 가능한 부분만) → 메뉴 후보의 태그와 맞춰 추천 → 콘텐츠 아이디어

원칙
- 파이썬 표준 라이브러리만 쓴다. 외부 AI·인터넷 연결 없음. 전부 '규칙 기반'.
- 운세 문장을 지어내지 않는다. 역법으로 계산되는 값(띠, 연간 오행, 일진, 별자리)만 쓴다.
- 오행의 색·맛 연결은 전통 배속(재미·기획용)이며 건강 효능 주장이 아니다.
- 메뉴 태그가 비어 있으면 0점이 아니라 '평가 보류'.
- 예시 데이터와 실제 데이터를 한 파일에 섞으면 멈춘다.
- 최종 메뉴는 셰프가 고른다. 이 도구는 후보를 좁혀 줄 뿐이다.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

RULE_LABEL = "규칙 기반(외부 AI 미사용)"
DISCLAIMER = ("재미·기획용 추천입니다. 사주·별자리·성격유형은 과학적 근거가 아니며, "
              "맛·조리 안전성·건강 판단을 대신하지 않습니다. 최종 메뉴는 셰프가 정합니다.")

# ---------------------------------------------------------------- 역법 계산
STEMS = "갑을병정무기경신임계"
STEMS_HANJA = "甲乙丙丁戊己庚辛壬癸"
BRANCHES = "자축인묘진사오미신유술해"
BRANCHES_HANJA = "子丑寅卯辰巳午未申酉戌亥"
ANIMALS = ["쥐", "소", "호랑이", "토끼", "용", "뱀", "말", "양", "원숭이", "닭", "개", "돼지"]
STEM_ELEMENT = ["목", "목", "화", "화", "토", "토", "금", "금", "수", "수"]

# 전통 오행 배속 (색·맛). 재미·기획용.
ELEMENT_INFO = {
    "목": {"색": "청", "맛": "신맛", "색말": "초록·푸른 채소"},
    "화": {"색": "적", "맛": "쓴맛", "색말": "빨간 재료"},
    "토": {"색": "황", "맛": "단맛", "색말": "노란 재료·뿌리채소"},
    "금": {"색": "백", "맛": "매운맛", "색말": "하얀 재료"},
    "수": {"색": "흑", "맛": "짠맛", "색말": "검은 재료·해조류"},
}
# 상생: 목→화→토→금→수→목 (앞이 뒤를 돕는다)
GENERATES = {"목": "화", "화": "토", "토": "금", "금": "수", "수": "목"}
GENERATED_BY = {v: k for k, v in GENERATES.items()}

# 기준일: 2000-01-01 = 무오(戊午)일. 60갑자 번호 54.
_ANCHOR = dt.date(2000, 1, 1)
_ANCHOR_INDEX = 54


def sexagenary_name(index: int) -> str:
    return f"{STEMS[index % 10]}{BRANCHES[index % 12]}({STEMS_HANJA[index % 10]}{BRANCHES_HANJA[index % 12]})"


def day_pillar(day: dt.date) -> tuple[int, str, str]:
    """선택일의 일진. (60갑자 번호, 이름, 일간 오행)"""
    idx = (_ANCHOR_INDEX + (day - _ANCHOR).days) % 60
    return idx, sexagenary_name(idx), STEM_ELEMENT[idx % 10]


@dataclass
class YearInfo:
    saju_year: int
    pillar: str
    animal: str
    element: str
    boundary_note: str = ""


def year_info(birth: dt.date) -> YearInfo:
    """띠와 연간 오행. 사주의 해는 입춘(대개 2월 4일 전후)에 바뀐다.
    입춘 날짜는 해마다 2월 3~5일로 달라서, 그 사흘에 태어났으면 '확인 필요'로 남긴다."""
    y = birth.year
    note = ""
    if birth.month == 1 or (birth.month == 2 and birth.day < 3):
        y -= 1
    elif birth.month == 2 and 3 <= birth.day <= 5:
        note = "입춘 경계일(2월 3~5일) — 태어난 시각에 따라 전년도 띠일 수 있어 확인 필요"
    idx = (y - 4) % 60
    return YearInfo(y, sexagenary_name(idx), ANIMALS[(y - 4) % 12], STEM_ELEMENT[idx % 10], note)


ZODIAC = [  # (시작 월, 시작 일, 이름, 원소)
    (1, 20, "물병자리", "공기"), (2, 19, "물고기자리", "물"), (3, 21, "양자리", "불"),
    (4, 20, "황소자리", "흙"), (5, 21, "쌍둥이자리", "공기"), (6, 22, "게자리", "물"),
    (7, 23, "사자자리", "불"), (8, 23, "처녀자리", "흙"), (9, 23, "천칭자리", "공기"),
    (10, 23, "전갈자리", "물"), (11, 22, "사수자리", "불"), (12, 22, "염소자리", "흙"),
]


def zodiac_sign(birth: dt.date) -> tuple[str, str]:
    md = (birth.month, birth.day)
    sign = ("염소자리", "흙")  # 1/1~1/19
    for m, d, name, elem in ZODIAC:
        if md >= (m, d):
            sign = (name, elem)
    return sign


# 별자리 원소 → 요리 성향 태그 (재미·기획용)
ZODIAC_STYLE = {
    "불": ["센불", "빠른조리", "매운맛"],
    "흙": ["오래끓이기", "뿌리채소", "한그릇"],
    "공기": ["퓨전", "가벼운", "샐러드"],
    "물": ["국물", "찜", "추억음식"],
}

# 성격유형(MBTI) 글자 → 요리 성향 태그 (재미·기획용)
MBTI_STYLE = {
    "E": ("여럿나눔", "여럿이 나눠 먹는 큰 냄비 요리"),
    "I": ("1인분", "혼자 차려도 부담 없는 양"),
    "S": ("단계적", "순서가 분명한 레시피"),
    "N": ("퓨전", "새로운 조합"),
    "T": ("원리설명", "왜 그렇게 하는지 원리가 있는 요리"),
    "F": ("추억음식", "이야기가 담긴 음식"),
    "J": ("계량정확", "계량이 딱 떨어지는 레시피"),
    "P": ("냉장고파먹기", "있는 재료로 응용하는 요리"),
}


def parse_mbti(text: str) -> str:
    t = (text or "").strip().upper()
    ok = (len(t) == 4 and t[0] in "EI" and t[1] in "SN" and t[2] in "TF" and t[3] in "JP")
    if not ok:
        raise ValueError(f"성격유형 '{text}' 을(를) 읽을 수 없습니다. 예: ISFJ, ENTP (네 글자)")
    return t


# ---------------------------------------------------------------- 메뉴 후보
REQUIRED_COLUMNS = ["메뉴ID", "메뉴명", "데이터구분"]
OPTIONAL_COLUMNS = ["요리권역", "색", "맛", "스타일태그", "셰프확인"]


@dataclass
class Menu:
    menu_id: str
    name: str
    data_kind: str
    region: str = ""
    colors: set[str] = field(default_factory=set)
    tastes: set[str] = field(default_factory=set)
    styles: set[str] = field(default_factory=set)
    chef_checked: str = ""

    @property
    def has_tags(self) -> bool:
        return bool(self.colors or self.tastes or self.styles)


def _split(v: str) -> set[str]:
    return {x.strip() for x in (v or "").replace("/", ",").replace("·", ",").split(",") if x.strip()}


class InputError(Exception):
    """사용자가 고칠 수 있는 입력 오류. 메시지에 원인과 해결 방법을 담는다."""


def load_menus(path: Path) -> list[Menu]:
    if not path.exists():
        raise InputError(f"메뉴 후보 파일이 없습니다: {path}\n→ 파일 이름과 위치를 확인하세요.")
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise InputError(f"메뉴 후보 파일을 열 수 없습니다: {e}\n→ 엑셀에서 열려 있으면 닫고 다시 실행하세요.")
    for enc in ("utf-8-sig", "cp949"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise InputError("글자 인코딩을 읽을 수 없습니다.\n→ 엑셀에서 'CSV UTF-8'로 다시 저장하세요.")
    reader = csv.DictReader(text.splitlines())
    headers = [h.strip() for h in (reader.fieldnames or [])]
    missing = [c for c in REQUIRED_COLUMNS if c not in headers]
    if missing:
        raise InputError(f"필수 열이 없습니다: {', '.join(missing)}\n→ 첫 줄 제목을 예시 파일과 같게 맞추세요.")
    menus, seen, kinds = [], set(), set()
    for n, row in enumerate(reader, start=2):
        row = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
        if not any(row.values()):
            continue
        mid, name, kind = row.get("메뉴ID", ""), row.get("메뉴명", ""), row.get("데이터구분", "")
        if not mid or not name:
            raise InputError(f"{n}번째 줄: 메뉴ID와 메뉴명은 비울 수 없습니다.")
        if kind not in ("예시", "실제"):
            raise InputError(f"{n}번째 줄: 데이터구분은 '예시' 또는 '실제'여야 합니다. (지금: '{kind}')")
        if mid in seen:
            raise InputError(f"{n}번째 줄: 메뉴ID '{mid}'가 중복입니다. 하나만 남기세요.")
        seen.add(mid)
        kinds.add(kind)
        menus.append(Menu(mid, name, kind, row.get("요리권역", ""), _split(row.get("색", "")),
                          _split(row.get("맛", "")), _split(row.get("스타일태그", "")), row.get("셰프확인", "")))
    if len(kinds) > 1:
        raise InputError("한 파일에 '예시'와 '실제' 메뉴가 섞여 있습니다.\n→ 예시 줄을 지우거나 파일을 나누세요.")
    if not menus:
        raise InputError("메뉴 후보가 한 줄도 없습니다.")
    return menus


# ---------------------------------------------------------------- 추천
@dataclass
class Pick:
    menu: Menu
    score: int
    reasons: list[str]
    on_hold: bool = False


def _rank(menus: list[Menu], want_colors: dict[str, str], want_tastes: dict[str, str],
          want_styles: dict[str, str]) -> list[Pick]:
    picks = []
    for m in menus:
        if not m.has_tags:
            picks.append(Pick(m, 0, ["색·맛·스타일 태그가 비어 있어 평가 보류"], on_hold=True))
            continue
        reasons = []
        for c, why in want_colors.items():
            if c in m.colors:
                reasons.append(f"색 '{c}' — {why}")
        for t, why in want_tastes.items():
            if t in m.tastes:
                reasons.append(f"맛 '{t}' — {why}")
        for s, why in want_styles.items():
            if s in m.styles:
                reasons.append(f"스타일 '{s}' — {why}")
        picks.append(Pick(m, len(reasons), reasons))
    picks.sort(key=lambda p: (p.on_hold, -p.score, p.menu.menu_id))
    return picks


def by_element(menus, element: str, label: str):
    info, helper = ELEMENT_INFO[element], GENERATED_BY[element]
    colors = {info["색"]: f"{label} 오행 '{element}'의 전통 색", ELEMENT_INFO[helper]["색"]: f"'{element}'를 돕는(상생) '{helper}'의 색"}
    tastes = {info["맛"]: f"{label} 오행 '{element}'의 전통 맛"}
    return _rank(menus, colors, tastes, {})


def by_zodiac(menus, elem: str, sign: str):
    return _rank(menus, {}, {"매운맛": f"{sign}({elem}) 성향"} if elem == "불" else {},
                 {s: f"{sign}({elem} 원소) 성향" for s in ZODIAC_STYLE[elem]})


def by_mbti(menus, mbti: str):
    return _rank(menus, {}, {}, {MBTI_STYLE[ch][0]: f"{ch} — {MBTI_STYLE[ch][1]}" for ch in mbti})


# ---------------------------------------------------------------- 보고서
def _pick_lines(picks: list[Pick], top: int = 3) -> list[str]:
    out, shown = [], 0
    for p in picks:
        if p.on_hold or p.score == 0:
            continue
        chef = " · 셰프 확인됨" if p.menu.chef_checked in ("예", "Y", "y", "확인") else " · 셰프 확인 전"
        out.append(f"- **{p.menu.name}** ({p.menu.menu_id}, 일치 {p.score}개{chef})")
        out += [f"  - {r}" for r in p.reasons]
        shown += 1
        if shown >= top:
            break
    if not shown:
        out.append("- 태그가 맞는 메뉴 후보가 없습니다. 메뉴 후보에 색·맛·스타일 태그를 채우면 추천이 나옵니다.")
    held = [p.menu.menu_id for p in picks if p.on_hold]
    if held:
        out.append(f"- 평가 보류(태그 없음): {', '.join(held)}")
    return out


def build_report(menus: list[Menu], birth: dt.date | None, mbti: str | None, day: dt.date,
                 audience: str = "여러분") -> str:
    kind = menus[0].data_kind
    L = [f"# 테마 밥상 추천 ({kind} 데이터)", "",
         f"- 분석 방식: {RULE_LABEL}", f"- 만든 시각: {dt.datetime.now():%Y-%m-%d %H:%M}",
         f"- 메뉴 후보: {len(menus)}개", f"- 주의: {DISCLAIMER}", ""]

    idx, pname, elem = day_pillar(day)
    L += [f"## 1. 선택일 밥상 — {day:%Y-%m-%d} 일진 {pname}", "",
          f"- 일간 오행: **{elem}** (전통 배속: {ELEMENT_INFO[elem]['색말']}, {ELEMENT_INFO[elem]['맛']})",
          "- 운세 문장은 만들지 않습니다. 역법으로 계산되는 일진만 씁니다.", ""]
    L += _pick_lines(by_element(menus, elem, "선택일")) + [""]

    if birth:
        yi = year_info(birth)
        sign, zelem = zodiac_sign(birth)
        L += [f"## 2. 띠·오행 밥상 — {birth:%Y-%m-%d}생", "",
              f"- 사주 연주: {yi.pillar} ({yi.saju_year}년 기준) · **{yi.animal}띠** · 연간 오행 **{yi.element}**"]
        if yi.boundary_note:
            L.append(f"- 확인 필요: {yi.boundary_note}")
        L += ["- 연간 오행만 쓴 간이 풀이입니다. 월·일·시 전체 사주풀이가 아닙니다.", ""]
        L += _pick_lines(by_element(menus, yi.element, "태어난 해")) + [""]
        L += [f"## 3. 별자리 밥상 — {sign} ({zelem} 원소)", "",
              f"- 성향 태그: {', '.join(ZODIAC_STYLE[zelem])}", ""]
        L += _pick_lines(by_zodiac(menus, zelem, sign)) + [""]
    else:
        L += ["## 2~3. 띠·별자리 밥상", "", "- 생년월일을 넣지 않아 건너뜀.", ""]

    if mbti:
        L += [f"## 4. 성격유형 밥상 — {mbti}", "",
              f"- 성향 태그: {', '.join(MBTI_STYLE[c][0] for c in mbti)}", ""]
        L += _pick_lines(by_mbti(menus, mbti)) + [""]
    else:
        L += ["## 4. 성격유형 밥상", "", "- 성격유형을 넣지 않아 건너뜀.", ""]

    L += ["## 5. 콘텐츠 아이디어 초안 (확정 아님)", "",
          "시청자가 '내 이야기'로 받아들이게 만드는 연결고리용입니다. 정답(메뉴 이름)은 썸네일에 넣지 않습니다.", "",
          "- 시리즈: 12띠 밥상 / 별자리 밥상 / 오늘의 일진 밥상",
          f"- 제목 후보: {audience} 띠에 맞는 냄비 요리, 따로 있습니다",
          f"- 제목 후보: 생일만 알면 오늘 저녁 메뉴가 정해집니다",
          "- 썸네일 후보: 내 띠 밥상은 뭘까?",
          "- 썸네일 후보: 별자리마다 다른 한 그릇",
          f"- 댓글 참여: \"{audience} 띠를 댓글로 남겨 주세요. 다음 영상 메뉴에 반영합니다.\"",
          "- 공동구매 연결 시: 같은 냄비로 띠별 메뉴를 돌려 보는 구성이 가능. 제품 성능 문구는 공식 자료·직접 사용 확인 후에만.",
          "", "## 셰프 확인 칸", "", "- [ ] 추천 메뉴 중 실제로 찍을 메뉴:",
          "- [ ] 조리 테스트 ID:", "- [ ] 제외한 메뉴와 이유:", ""]
    return "\n".join(L)


# ---------------------------------------------------------------- 실행
def default_output_dir() -> Path:
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    return home / "Downloads" / "로빈_테마밥상추천"


def _date(s: str) -> dt.date:
    try:
        return dt.date.fromisoformat(s.strip())
    except ValueError:
        raise InputError(f"날짜 '{s}' 형식이 맞지 않습니다. 예: 1968-03-15")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="테마 밥상 추천 (규칙 기반)")
    p.add_argument("--menus", required=True, help="메뉴 후보 CSV")
    p.add_argument("--birth", help="생년월일 YYYY-MM-DD (선택)")
    p.add_argument("--mbti", help="성격유형 네 글자 (선택)")
    p.add_argument("--day", help="선택일 YYYY-MM-DD (기본: 오늘)")
    p.add_argument("--out", help="저장 폴더 (기본: 다운로드\\로빈_테마밥상추천)")
    a = p.parse_args(argv)
    try:
        menus = load_menus(Path(a.menus))
        birth = _date(a.birth) if a.birth else None
        mbti = parse_mbti(a.mbti) if a.mbti else None
        day = _date(a.day) if a.day else dt.date.today()
        report = build_report(menus, birth, mbti, day)
        out_dir = Path(a.out) if a.out else default_output_dir()
        out_dir.mkdir(parents=True, exist_ok=True)
        f = out_dir / f"테마밥상_{menus[0].data_kind}_{dt.datetime.now():%Y%m%d_%H%M%S}.md"
        f.write_text(report, encoding="utf-8")
    except (InputError, ValueError) as e:
        print(f"[멈춤] {e}", file=sys.stderr)
        return 2
    print(f"저장했습니다: {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
