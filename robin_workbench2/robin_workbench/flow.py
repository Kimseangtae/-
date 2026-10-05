# -*- coding: utf-8 -*-
"""작업 순서 안내: 자료 입력 → 불편 분석 → 메뉴 후보 → 조리 기록 → 콘텐츠 초안 → 성과 회고."""
from __future__ import annotations

from . import menus as menus_mod


def stage_status(store) -> list[dict]:
    t = store.data["tables"]
    comments = t["comments"]
    unreviewed = sum(1 for r in comments if r.get("검토상태") in ("", "미검토"))
    auto_done = sum(1 for r in comments if r.get("_auto", {}).get("분류"))
    confirmed_tests = [x for x in t["tests"] if x.get("셰프확인") == "예"]
    chosen = [m for m in t["menus"] if m.get("셰프결정") == "선택"]
    chef_scored = [m for m in t["menus"] if any(m.get(f"셰프점수{i}") for i in range(1, 7))]
    confirmed_products = [p for p in t["products"] if p.get("확인된기능") and p.get("공식자료출처")]
    drafts = store.data.get("drafts", {})
    S = []

    def add(name, done, note, missing):
        S.append({"단계": name, "완료": done, "현황": note, "부족": missing})

    add("1. 자료 입력", bool(comments),
        f"댓글 {len(comments)} · 영상 성과 {len(t['videos'])} · 상품 {len(t['products'])} · 공구 문의 {len(t['inquiries'])} · 공구 결과 {len(t['results'])}",
        [m for m, ok in [("시청자 댓글을 넣으세요", comments), ("상품 정보(공식 자료 확인)를 넣으세요", confirmed_products)] if not ok])
    add("2. 불편 분석", bool(comments) and auto_done == len(comments),
        f"자동 분류 {auto_done}/{len(comments)} · 미검토 댓글 {unreviewed}",
        (["'분류 다시 하기'를 누르세요"] if auto_done < len(comments) else []) +
        ([f"미검토 댓글 {unreviewed}건 — 원문을 보고 분류를 확정하세요"] if unreviewed else []))
    add("3. 메뉴 후보", bool(chosen),
        f"후보 {len(t['menus'])} · 셰프 평가 {len(chef_scored)} · 선택 {len(chosen)}",
        [m for m, ok in [("메뉴 후보를 넣으세요", t["menus"]), ("셰프 점수를 매기세요", chef_scored),
                         ("찍을 메뉴를 '선택'으로 표시하세요", chosen)] if not ok])
    add("4. 조리 기록", bool(confirmed_tests),
        f"조리 테스트 {len(t['tests'])} · 셰프 확인 {len(confirmed_tests)}",
        [] if confirmed_tests else ["직접 조리한 기록을 넣고 '셰프확인=예'로 표시하세요 (콘텐츠 초안의 원본)"])
    add("5. 콘텐츠 초안", bool(drafts), f"초안 {len(drafts)}",
        [] if drafts else (["셰프 확인된 조리 테스트로 초안을 만드세요"] if confirmed_tests else ["4단계가 먼저 필요합니다"]))
    add("6. 성과 회고", bool(t["retros"]), f"회고 {len(t['retros'])} · 영상 지표 {len(t['videos'])} · 공구 결과 {len(t['results'])}",
        [] if t["retros"] else ["게시·공구 후 회고를 남기세요 (다음 메뉴 기획에서 검색됩니다)"])
    return S


def current_stage(store) -> str:
    for s in stage_status(store):
        if not s["완료"]:
            return s["단계"]
    return "모든 단계 기록 있음"


def status_text(store) -> str:
    L = [f"[{store.mode} 모드] 지금 단계: {current_stage(store)}", ""]
    for s in stage_status(store):
        L.append(f"{'✔' if s['완료'] else '…'} {s['단계']} — {s['현황']}")
        L += [f"    · {m}" for m in s["부족"]]
    return "\n".join(L)
