# -*- coding: utf-8 -*-
"""시청자 불편 분류(규칙 기반), 주제 묶음, 영상 아이디어, 지표 비교, 공구 전환율, 회고 검색."""
from __future__ import annotations

import re
from collections import OrderedDict

from .schema import PAIN_CATEGORIES

METHOD = "규칙 기반(단어 규칙, 외부 AI 미사용)"

# (분류, 단어 조각, 주제 이름). 조각이 댓글에 들어 있으면 그 주제로 본다.
RULES: list[tuple[str, str, str]] = [
    ("요리 실패", "눌어", "바닥이 눌어붙음"), ("요리 실패", "눌러붙", "바닥이 눌어붙음"),
    ("요리 실패", "탔", "타 버림"), ("요리 실패", "타요", "타 버림"), ("요리 실패", "태웠", "타 버림"),
    ("요리 실패", "질겨", "고기가 질김"), ("요리 실패", "질기", "고기가 질김"), ("요리 실패", "딱딱", "고기가 질김"),
    ("요리 실패", "퍼져", "면·밥이 퍼짐"), ("요리 실패", "떡져", "면·밥이 퍼짐"), ("요리 실패", "질어", "면·밥이 퍼짐"),
    ("요리 실패", "비려", "비린내"), ("요리 실패", "비린", "비린내"), ("요리 실패", "누린내", "비린내"),
    ("요리 실패", "짜요", "간 맞추기"), ("요리 실패", "싱거", "간 맞추기"), ("요리 실패", "간이 안", "간 맞추기"),
    ("요리 실패", "탁해", "국물이 탁함"), ("요리 실패", "망했", "기타 실패"), ("요리 실패", "실패", "기타 실패"),
    ("요리 실패", "물러", "채소가 물러짐"), ("요리 실패", "뭉개", "채소가 물러짐"),
    ("조리 시간", "오래 걸", "시간이 오래 걸림"), ("조리 시간", "시간이", "시간이 오래 걸림"),
    ("조리 시간", "빨리", "빨리 하고 싶음"), ("조리 시간", "금방", "빨리 하고 싶음"), ("조리 시간", "바빠", "평일 저녁 시간 부족"),
    ("조리 시간", "퇴근", "평일 저녁 시간 부족"), ("조리 시간", "몇 분", "시간이 오래 걸림"),
    ("번거로움", "귀찮", "과정이 귀찮음"), ("번거로움", "번거", "과정이 귀찮음"), ("번거로움", "복잡", "과정이 귀찮음"),
    ("번거로움", "설거지", "설거지가 많음"), ("번거로움", "손이 많이", "과정이 귀찮음"), ("번거로움", "힘들", "과정이 귀찮음"),
    ("재료 비용", "비싸", "재료가 비쌈"), ("재료 비용", "물가", "재료가 비쌈"), ("재료 비용", "가격이", "재료가 비쌈"),
    ("재료 비용", "저렴", "싼 재료로 대체"), ("재료 비용", "대체", "싼 재료로 대체"), ("재료 비용", "없는 재료", "싼 재료로 대체"),
    ("건강 관심", "혈당", "혈당"), ("건강 관심", "당뇨", "혈당"), ("건강 관심", "저염", "싱겁게·저염"),
    ("건강 관심", "짜게", "싱겁게·저염"), ("건강 관심", "혈압", "싱겁게·저염"), ("건강 관심", "다이어트", "체중 관리"),
    ("건강 관심", "칼로리", "체중 관리"), ("건강 관심", "소화", "소화"), ("건강 관심", "건강", "건강 일반"),
    ("제품 구매 망설임", "살까", "살지 말지 고민"), ("제품 구매 망설임", "사야", "살지 말지 고민"),
    ("제품 구매 망설임", "고민", "살지 말지 고민"), ("제품 구매 망설임", "필요할까", "살지 말지 고민"),
    ("제품 구매 망설임", "냄비 있", "이미 가진 도구로 충분한지"), ("제품 구매 망설임", "이미 있", "이미 가진 도구로 충분한지"),
    ("제품 구매 망설임", "차이", "다른 제품과 차이"), ("제품 구매 망설임", "비교", "다른 제품과 차이"),
    ("제품 구매 망설임", "인덕션", "우리 집 화구에서 되는지"), ("제품 구매 망설임", "가스레인지", "우리 집 화구에서 되는지"),
    ("제품 구매 망설임", "무거", "무게·크기"), ("제품 구매 망설임", "크기", "무게·크기"), ("제품 구매 망설임", "용량", "무게·크기"),
]
OTHER = PAIN_CATEGORIES[-1]

# 주제를 문장에 넣을 때 쓰는 꾸밈말 ("국물이 탁해지는 이유")
TOPIC_ADJ = {
    "바닥이 눌어붙음": "바닥이 눌어붙는", "타 버림": "타 버리는", "고기가 질김": "고기가 질긴",
    "면·밥이 퍼짐": "면과 밥이 퍼지는", "비린내": "비린내가 나는", "간 맞추기": "간이 잘 안 맞는",
    "국물이 탁함": "국물이 탁해지는", "기타 실패": "자꾸 실패하는", "채소가 물러짐": "채소가 물러지는",
    "시간이 오래 걸림": "시간이 오래 걸리는", "빨리 하고 싶음": "시간이 부족한", "평일 저녁 시간 부족": "저녁 시간이 부족한",
    "과정이 귀찮음": "과정이 번거로운", "설거지가 많음": "설거지가 많이 나오는", "재료가 비쌈": "재료비가 부담되는",
    "싼 재료로 대체": "재료를 바꾸고 싶은", "혈당": "혈당이 신경 쓰이는", "싱겁게·저염": "싱겁게 드셔야 하는",
    "체중 관리": "체중이 신경 쓰이는", "소화": "소화가 신경 쓰이는", "건강 일반": "건강이 신경 쓰이는",
    "살지 말지 고민": "살지 말지 고민되는", "이미 가진 도구로 충분한지": "지금 냄비로 충분할지 궁금한",
    "다른 제품과 차이": "다른 냄비와 차이가 궁금한", "우리 집 화구에서 되는지": "우리 집 화구에서 될지 궁금한",
    "무게·크기": "크기와 무게가 신경 쓰이는",
}


def topic_adj(topic: str) -> str:
    return TOPIC_ADJ.get(topic, "생각대로 잘 안 되는")


def topic_pieces(topic: str) -> list[str]:
    return [p for _, p, tp in RULES if tp == topic]

IDEAS = {
    "요리 실패": "‘{주제}’ 실패 장면을 먼저 보여 주고, 원인과 셰프의 수정 방법을 차례로 보여 주는 영상",
    "조리 시간": "‘{주제}’를 줄이는 순서 바꾸기·미리 준비 요령을 실제 시간과 함께 보여 주는 영상",
    "번거로움": "‘{주제}’를 줄이는 방법(도구 하나, 과정 줄이기)을 전후 비교로 보여 주는 영상",
    "재료 비용": "‘{주제}’ — 비싼 재료를 쉬운 재료로 바꿔도 되는지 직접 비교하는 영상",
    "건강 관심": "‘{주제}’ 관심에 맞춰 조리 방법(간·기름 양)을 바꾸는 과정 영상. 효능 주장 없이 조리법만 다룸",
    "제품 구매 망설임": "‘{주제}’ 질문에 답하는 비교 조리 영상. 필요 없는 분도 솔직히 안내",
    OTHER: "사람이 원문을 읽고 판단 필요",
}
# 댓글에 직접 쓰이지 않은 욕구 추정 (반드시 '추정'으로 표시)
GUESSES = {
    "조리 시간": "평일 저녁 30분 안쪽 메뉴를 원할 수 있음",
    "번거로움": "냄비 하나로 끝나는 구성을 원할 수 있음",
    "요리 실패": "실패하지 않는 기준(불 세기·시간)을 숫자로 알고 싶을 수 있음",
    "재료 비용": "동네 마트 재료만으로 가능한지 알고 싶을 수 있음",
    "제품 구매 망설임": "지금 가진 냄비와의 차이를 직접 보고 싶을 수 있음",
    "건강 관심": "간을 줄여도 맛있게 먹는 방법을 원할 수 있음",
}


def classify(text: str) -> dict:
    """댓글 하나를 분류한다. 여러 분류에 걸리면 모두 기록하고, 가장 많이 걸린 것을 대표로."""
    t = (text or "").replace(" ", "")
    hits: "OrderedDict[str, list[tuple[str, str]]]" = OrderedDict()
    for cat, piece, topic in RULES:
        if piece.replace(" ", "") in t:
            hits.setdefault(cat, []).append((piece, topic))
    if not hits:
        return {"대표분류": OTHER, "분류들": [OTHER], "주제": "분류 규칙에 안 걸림", "근거": "해당 단어 없음",
                "방식": METHOD}
    main = max(hits, key=lambda c: (len(hits[c]), -PAIN_CATEGORIES.index(c)))
    topics = [tp for _, tp in hits[main]]
    topic = max(set(topics), key=lambda x: (topics.count(x), -topics.index(x)))
    why = ", ".join(sorted({f"'{p}'" for c in hits for p, _ in hits[c]}))
    return {"대표분류": main, "분류들": list(hits), "주제": topic, "근거": f"들어 있는 단어: {why}", "방식": METHOD}


def classify_all(store) -> int:
    """모든 댓글의 자동 분류를 다시 계산한다. 로빈님이 확정한 '분류' 칸은 건드리지 않는다."""
    n = 0
    for r in store.rows("comments"):
        r.setdefault("_auto", {})["분류"] = classify(r.get("댓글원문", ""))
        n += 1
    store.save("불편 자동 분류(규칙 기반)")
    return n


def effective_category(r: dict) -> tuple[str, str]:
    """(분류, 출처). 셰프가 확정했으면 그것, 아니면 자동 추정."""
    if r.get("분류"):
        return r["분류"], "셰프 확정"
    a = r.get("_auto", {}).get("분류")
    if a:
        return a["대표분류"], "자동 추정"
    return OTHER, "미분류"


def group_pains(store, include_excluded: bool = False) -> list[dict]:
    """주제별 묶음. 각 묶음은 원문·출처로 돌아갈 수 있게 댓글ID 목록을 갖는다."""
    groups: dict[tuple[str, str], dict] = {}
    for r in store.rows("comments"):
        if r.get("검토상태") == "제외" and not include_excluded:
            continue
        cat, src = effective_category(r)
        auto = r.get("_auto", {}).get("분류") or classify(r.get("댓글원문", ""))
        topic = auto["주제"] if auto["대표분류"] == cat else f"{cat}(셰프 분류)"
        g = groups.setdefault((cat, topic), {"분류": cat, "주제": topic, "댓글ID": [], "출처": set(), "확정수": 0})
        g["댓글ID"].append(r["댓글ID"])
        g["출처"].add(r.get("플랫폼", "") or "플랫폼 미입력")
        g["확정수"] += src == "셰프 확정"
    out = []
    for g in groups.values():
        members = [store.get("comments", i) for i in g["댓글ID"]]
        members.sort(key=lambda r: (r.get("날짜") or "9999", r["댓글ID"]))
        rep = members[0]
        g["건수"] = len(members)
        g["대표댓글"] = rep.get("댓글원문", "")
        g["대표댓글ID"] = rep["댓글ID"]
        g["출처"] = sorted(g["출처"])
        g["영상아이디어"] = IDEAS[g["분류"]].format(주제=g["주제"])
        g["추정"] = GUESSES.get(g["분류"], "")
        out.append(g)
    out.sort(key=lambda g: (g["분류"] == OTHER, -g["건수"], PAIN_CATEGORIES.index(g["분류"]), g["주제"]))
    return out


def category_counts(store) -> dict[str, int]:
    counts = {c: 0 for c in PAIN_CATEGORIES}
    for r in store.rows("comments"):
        if r.get("검토상태") != "제외":
            counts[effective_category(r)[0]] += 1
    return counts


def pain_report(store) -> str:
    groups = group_pains(store)
    L = ["# 시청자 불편 분석", "", f"- 분석 방식: {METHOD}", f"- 자료: {store.mode} 모드, 댓글 {len(store.rows('comments'))}건 (제외 표시 댓글은 빼고 셈)",
         "- '셰프 확정'이 아닌 분류는 자동 추정입니다. 사실로 쓰기 전에 원문을 확인하세요.", ""]
    for g in groups:
        L += [f"## {g['분류']} — {g['주제']} ({g['건수']}건, 셰프 확정 {g['확정수']}건)", "",
              f"- 대표 댓글({g['대표댓글ID']}): \"{g['대표댓글']}\"",
              f"- 원문 추적: {', '.join(g['댓글ID'])}", f"- 플랫폼: {', '.join(g['출처'])}",
              f"- 영상 아이디어: {g['영상아이디어']}"]
        if g["추정"]:
            L.append(f"- (추정, 댓글에 직접 없음) {g['추정']}")
        L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------- 지표 비교
def _num(v: str) -> float | None:
    try:
        return float(v) if v not in ("", None) else None
    except ValueError:
        return None


def compare_videos(store) -> list[dict]:
    """같은 플랫폼·같은 게시 후 경과시간끼리만 묶어서 비교한다."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in store.rows("videos"):
        groups.setdefault((r.get("플랫폼", ""), r.get("게시후경과시간", "")), []).append(r)
    out = []
    for (plat, hours), rows in sorted(groups.items()):
        rows = sorted(rows, key=lambda r: -(_num(r.get("조회수")) or -1))
        out.append({"플랫폼": plat, "경과시간": hours, "영상": [
            {"영상ID": r.get("영상ID"), "메뉴": r.get("메뉴"), "제목": r.get("제목"),
             "조회수": r.get("조회수") or "미확보", "클릭률": r.get("클릭률") or "미확보",
             "평균시청시간": r.get("평균시청시간") or "미확보", "기록ID": r.get("기록ID")} for r in rows],
            "비교가능": len(rows) > 1})
    return out


def gb_summary(store) -> list[dict]:
    """공구 결과 요약. 선예약은 주문·매출과 따로 두고, 전환율은 분모·분자가 모두 있을 때만 계산."""
    by: dict[tuple[str, str, str], dict] = {}
    for r in store.rows("results"):
        key = (r.get("상품ID", ""), r.get("기간", ""), r.get("집계기준", ""))
        by.setdefault(key, {})[r.get("지표종류", "")] = _num(r.get("값"))
    out = []
    for (pid, period, basis), m in sorted(by.items()):
        visits, orders, pre, returns = m.get("방문"), m.get("주문"), m.get("선예약"), m.get("반품")
        conv = (f"{orders / visits * 100:.1f}% (주문 {orders:g} ÷ 방문 {visits:g})"
                if visits and orders is not None else "계산 안 함 — 같은 기간·같은 집계기준의 방문과 주문이 모두 있어야 함")
        ret = (f"{returns / orders * 100:.1f}% (반품 {returns:g} ÷ 주문 {orders:g})"
               if orders and returns is not None else "계산 안 함 — 주문과 반품 수치가 모두 있어야 함")
        out.append({"상품ID": pid, "기간": period, "집계기준": basis,
                    "선예약": "미확보" if pre is None else f"{pre:g} (주문·매출에 넣지 않음)",
                    "주문": "미확보" if orders is None else f"{orders:g}",
                    "매출": "미확보" if m.get("매출") is None else f"{m['매출']:,.0f}",
                    "전환율": conv, "반품률": ret})
    return out


# ---------------------------------------------------------------- 회고 검색
def search_retros(store, query: str) -> list[dict]:
    words = [w for w in re.split(r"\s+", (query or "").strip()) if w]
    if not words:
        return []
    out = []
    for r in store.rows("retros"):
        blob = " ".join(str(v) for k, v in r.items() if not k.startswith("_"))
        if all(w in blob for w in words):
            snippet = next((f"{k}: {r[k]}" for k in ("다음에바꿀한가지", "다음개선점", "시청자반응", "실제성과")
                            if r.get(k)), "")
            out.append({"회고ID": r["회고ID"], "종류": r.get("종류"), "대상": r.get("대상"),
                        "메뉴": r.get("메뉴"), "요점": snippet})
    return out


def retro_report(store) -> str:
    L = ["# 성과 회고", "", f"- 자료: {store.mode} 모드", "", "## 영상 지표 비교 (같은 플랫폼·같은 경과시간끼리만)", ""]
    for g in compare_videos(store):
        L.append(f"### {g['플랫폼']} / 게시 후 {g['경과시간']}시간" + ("" if g["비교가능"] else " — 비교 대상 1개뿐"))
        for v in g["영상"]:
            L.append(f"- {v['영상ID']} {v['메뉴'] or ''}: 조회수 {v['조회수']}, 클릭률 {v['클릭률']}, 평균시청 {v['평균시청시간']}초")
        L.append("")
    L += ["## 공동구매 결과", ""]
    for s in gb_summary(store):
        L += [f"### {s['상품ID']} {s['기간']} ({s['집계기준']})",
              f"- 선예약: {s['선예약']}", f"- 주문: {s['주문']} / 매출: {s['매출']}",
              f"- 전환율: {s['전환율']}", f"- 반품률: {s['반품률']}", ""]
    L += ["## 회고 기록", ""]
    for r in store.rows("retros"):
        L += [f"### {r['회고ID']} {r.get('종류')} {r.get('대상')} {r.get('메뉴') or ''}"]
        for k in ("해결하려던문제", "실제성과", "시청자반응", "다음에바꿀한가지", "구매를이끈질문", "구매를막은질문",
                  "불만반품사유", "다음개선점"):
            if r.get(k):
                L.append(f"- {k}: {r[k]}")
        L.append("")
    return "\n".join(L)
