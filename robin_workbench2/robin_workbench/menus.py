# -*- coding: utf-8 -*-
"""메뉴 후보 자동 평가(추정). 셰프 평가 칸은 절대 건드리지 않는다. 근거가 없으면 '보류'."""
from __future__ import annotations

import datetime as dt

from . import theme_menu as tm
from .analysis import category_counts
from .schema import CRITERIA

METHOD = "규칙 기반 자동 추정(외부 AI 미사용) — 셰프 평가를 대신하지 않음"

VISUAL = ["색", "노릇", "부풀", "윤기", "캐러멜", "졸아", "걸쭉", "투명", "갈색", "김이", "거품", "단면", "결대로",
          "뼈에서", "쪼그라", "부드럽게 찢", "색이 변", "맑아"]
PRINCIPLE = ["압력", "온도", "수분", "증기", "마이야르", "전분", "삼투", "콜라겐", "단백질", "산도", "유화", "잔열",
             "밀폐", "끓는점", "핏물", "숙성"]
RARE = ["사프란", "트러플", "케이퍼", "아티초크", "펜넬", "수막", "자타르", "하리사", "파로", "폴렌타", "타히니",
        "레몬그라스", "갈랑갈", "미림", "가쓰오부시", "훈제 파프리카"]


def _split_ids(v: str) -> list[str]:
    return [x.strip() for x in (v or "").split(",") if x.strip()]


def linked_tests(store, menu: dict) -> list[dict]:
    ids = _split_ids(menu.get("관련테스트ID", ""))
    tests = [store.get("tests", i) for i in ids]
    tests = [t for t in tests if t]
    if not tests:  # ID를 안 적었으면 메뉴 이름이 같은 기록
        tests = [t for t in store.rows("tests") if t.get("메뉴", "").strip() == menu.get("메뉴명", "").strip()]
    return tests


def _hits(text: str, words: list[str]) -> list[str]:
    return [w for w in words if w in text]


def _held(reason: str) -> dict:
    return {"점수": None, "보류": True, "이유": reason}


def _score(n: int, reason: str) -> dict:
    return {"점수": max(1, min(5, n)), "보류": False, "이유": reason}


def evaluate(store, menu: dict) -> dict:
    tests = linked_tests(store, menu)
    test_text = "\n".join(t.get(k, "") for t in tests for k in ("조리순서", "촬영장면", "실패와수정", "맛평가"))
    text = (menu.get("설명", "") + "\n" + test_text).strip()
    res = {}

    # 1) 불편 연결
    pain = menu.get("관련불편", "")
    if not store.rows("comments"):
        res[1] = _held("댓글 자료가 없음")
    elif not pain:
        res[1] = _held("메뉴의 '관련불편' 칸이 비어 있음")
    else:
        n = category_counts(store).get(pain, 0)
        s = 1 if n == 0 else 2 if n == 1 else 3 if n <= 3 else 4 if n <= 6 else 5
        res[1] = _score(s, f"'{pain}' 댓글 {n}건(제외 표시 제외)")

    # 2) 화면 변화
    if not text:
        res[2] = _held("설명·조리 기록이 없음")
    else:
        h = _hits(text, VISUAL)
        res[2] = _score(2 + len(h), f"화면 변화 단서: {', '.join(h)}" if h else "화면 변화 단서 단어 없음")

    # 3) 조리 원리
    if not text:
        res[3] = _held("설명·조리 기록이 없음")
    else:
        h = _hits(text, PRINCIPLE)
        res[3] = _score(2 + len(h), f"원리 단서: {', '.join(h)}" if h else "원리 단서 단어 없음")

    # 4) 재료 구하기
    ingredients = [ln.strip() for t in tests for ln in t.get("재료와양", "").splitlines() if ln.strip()]
    if not ingredients:
        res[4] = _held("조리 테스트의 재료 기록이 없음")
    else:
        rare = _hits("\n".join(ingredients), RARE)
        s = 5 - len(rare) - (1 if len(ingredients) > 12 else 0)
        why = f"재료 {len(ingredients)}가지" + (f", 구하기 어려울 수 있는 재료: {', '.join(rare)}" if rare else ", 드문 재료 없음")
        res[4] = _score(s, why)

    # 5) 상품 장점 확인
    pid = menu.get("관련상품ID", "").strip()
    prod = store.get("products", pid) if pid else None
    if not prod:
        res[5] = _held("관련 상품이 없거나 ④ 상품 정보에 없음")
    elif not (prod.get("확인된기능") and prod.get("공식자료출처") and prod.get("확인날짜")):
        res[5] = _held("상품의 확인된 기능·공식 자료 출처·확인 날짜가 모두 있어야 함 (공식 자료 확인 필요)")
    else:
        used = any(pid in _split_ids(t.get("사용상품ID", "")) for t in tests)
        s = 2 + (2 if used else 0) + (1 if prod.get("직접사용경험") else 0)
        res[5] = _score(s, ("조리 기록에서 이 상품 사용" if used else "조리 기록에 이 상품 사용 기록 없음")
                        + (", 직접 사용 경험 있음" if prod.get("직접사용경험") else ", 직접 사용 경험 미기록"))

    # 6) 상품 없이도 볼 만한가
    if res[1]["보류"] or res[3]["보류"]:
        res[6] = _held("불편 연결(1)과 조리 원리(3) 평가가 모두 있어야 판단")
    else:
        res[6] = _score(round((res[1]["점수"] + res[3]["점수"]) / 2), "불편 연결·조리 원리 점수의 평균")
    unconfirmed = [t["테스트ID"] for t in tests if t.get("셰프확인") != "예"]
    if unconfirmed:
        for k, v in res.items():
            if not v["보류"] and k in (2, 3, 4, 5):
                v["이유"] += f" (셰프 확인 전 기록 {', '.join(unconfirmed)} 포함)"
    return {"방식": METHOD, "계산시각": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "근거테스트": [t["테스트ID"] for t in tests], "평가": {str(k): v for k, v in res.items()}}


def evaluate_all(store) -> None:
    for m in store.rows("menus"):
        m.setdefault("_auto", {})["평가"] = evaluate(store, m)
    store.save("메뉴 자동 평가(추정) 다시 계산")


def summary(menu: dict) -> dict:
    """자동 합계와 셰프 합계를 따로. 셰프 점수를 자동 점수로 채우지 않는다."""
    ev = menu.get("_auto", {}).get("평가", {}).get("평가", {})
    auto_scores = [v["점수"] for v in ev.values() if not v["보류"]]
    chef = [menu.get(f"셰프점수{i}", "") for i in range(1, 7)]
    chef_scores = [int(c) for c in chef if c]
    return {"자동합계": sum(auto_scores) if auto_scores else None, "자동보류": sum(1 for v in ev.values() if v["보류"]),
            "셰프합계": sum(chef_scores) if chef_scores else None, "셰프미평가": 6 - len(chef_scores),
            "셰프결정": menu.get("셰프결정") or "미정"}


def menu_report(store) -> str:
    L = ["# 메뉴 선정표", "", f"- 자동 평가: {METHOD}", "- 최종 메뉴는 셰프가 정합니다. 자동 점수는 참고용입니다.", ""]
    for m in store.rows("menus"):
        ev = m.get("_auto", {}).get("평가") or evaluate(store, m)
        s = summary({**m, "_auto": {"평가": ev}})
        L += [f"## {m['메뉴명']} ({m['메뉴ID']}, {m.get('요리권역') or '권역 미입력'}) — 셰프 결정: {s['셰프결정']}", "",
              "| 기준 | 자동(추정) | 자동 이유 | 셰프 | 셰프 이유 |", "|---|---|---|---|---|"]
        for i in range(1, 7):
            a = ev["평가"][str(i)]
            L.append(f"| {i}) {CRITERIA[i-1]} | {'보류' if a['보류'] else a['점수']} | {a['이유']} | "
                     f"{m.get(f'셰프점수{i}') or '미평가'} | {(m.get(f'셰프이유{i}') or '').replace(chr(10), ' ')} |")
        L += ["", f"- 자동 합계 {s['자동합계'] if s['자동합계'] is not None else '없음'} (보류 {s['자동보류']}개) / "
              f"셰프 합계 {s['셰프합계'] if s['셰프합계'] is not None else '없음'} (미평가 {s['셰프미평가']}개)",
              f"- 근거 조리 테스트: {', '.join(ev['근거테스트']) or '없음'}", ""]
    return "\n".join(L)


# ---------------------------------------------------------------- 테마 추천 연결
def theme_menus(store) -> list[tm.Menu]:
    return [tm.Menu(m["메뉴ID"], m["메뉴명"], store.mode, m.get("요리권역", ""), tm._split(m.get("색", "")),
                    tm._split(m.get("맛", "")), tm._split(m.get("스타일태그", "")),
                    "예" if m.get("셰프결정") == "선택" else "") for m in store.rows("menus")]


def theme_report(store, birth: dt.date | None, mbti: str | None, day: dt.date, audience: str = "여러분") -> str:
    menus = theme_menus(store)
    if not menus:
        from .store import WorkbenchError
        raise WorkbenchError("메뉴 후보가 없습니다.\n→ ⑥ 메뉴 후보를 먼저 입력하세요.")
    return tm.build_report(menus, birth, tm.parse_mbti(mbti) if mbti else None, day, audience)
