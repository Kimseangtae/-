# -*- coding: utf-8 -*-
"""조리 테스트 기록 → 콘텐츠 초안. 기록에 없는 수치는 만들지 않고 '확인 필요'로 남긴다.
셰프가 고친 항목은 다시 만들기를 해도 덮어쓰지 않는다. 모든 변경은 버전과 기록으로 남는다."""
from __future__ import annotations

import datetime as dt
import re

from .analysis import group_pains, topic_adj, topic_pieces
from .store import WorkbenchError, now

KINDS = ["풀링 콘텐츠", "키 콘텐츠"]
SECTIONS = ["제목 후보", "썸네일 문구", "롱폼 구성", "촬영 순서표", "도입부 대본", "본문 대본", "쇼츠·릴스",
            "유튜브 설명글", "커뮤니티 게시글", "인스타 캡션·스토리", "공구 FAQ", "근거·확인 필요"]
STATUS = "대본 초안 — 완성 영상 아님"
MEMBERSHIP = "https://www.youtube.com/channel/UCMSz_yah88yZMC6js2p149A/join"
THUMB_MAX = 18

FORBIDDEN = ["밥깡패", "매실", "체칼"]
CLAIM_WORDS = ["효능", "효과가 있", "치료", "예방", "면역", "혈당을 낮", "혈압을 낮", "살이 빠", "독소", "디톡스",
               "100%", "무조건", "절대 실패", "항암"]
NEED = "[확인 필요: {}]"


def need(v: str, label: str) -> str:
    v = (v or "").strip()
    return v if v else NEED.format(label)


def _lines(v: str) -> list[str]:
    return [ln.strip(" -•\t") for ln in (v or "").splitlines() if ln.strip(" -•\t")]


def _has_batchim(word: str) -> bool:
    ch = (word or " ")[-1]
    return "가" <= ch <= "힣" and (ord(ch) - 0xAC00) % 28 != 0


def josa(word: str, pair: str) -> str:
    a, b = pair.split("/")
    return word + (a if _has_batchim(word) else b)


def _fix(line: str) -> tuple[str, str]:
    """'실패 → 수정' 한 줄을 나눈다."""
    parts = re.split(r"\s*(?:→|->|=>)\s*", line, maxsplit=1)
    return (parts[0], parts[1]) if len(parts) == 2 else (line, "")


# ---------------------------------------------------------------- 근거 모으기
def gather(store, test_id: str) -> dict:
    test = store.get("tests", test_id)
    if not test:
        raise WorkbenchError(f"조리 테스트 {test_id} 가 없습니다.\n→ ③ 조리 테스트에서 ID를 확인하세요.")
    if test.get("셰프확인") != "예":
        raise WorkbenchError(f"{test_id}는 셰프 확인 전 기록입니다. 콘텐츠 초안은 셰프가 확인한 조리 기록만 원본으로 씁니다.\n"
                             "→ 직접 조리·확인했다면 ③ 조리 테스트에서 '셰프확인'을 '예'로 바꾼 뒤 다시 만드세요.")
    menu = next((m for m in store.rows("menus") if m.get("메뉴명", "").strip() == test.get("메뉴", "").strip()), None)
    pain_cat = (menu or {}).get("관련불편", "")
    group = None
    if pain_cat:
        groups = [g for g in group_pains(store) if g["분류"] == pain_cat]
        # 이 메뉴·이 조리 기록과 가장 가까운 묶음: 댓글에 메뉴 이름이 있거나, 실패 기록에 같은 주제 단어가 있는 것
        tokens = [w for w in re.split(r"\s+", test.get("메뉴", "")) if len(w) >= 2]
        fail_text = test.get("실패와수정", "").replace(" ", "")

        def relevance(g):
            texts = [(store.get("comments", i) or {}) for i in g["댓글ID"]]
            by_menu = sum(1 for c in texts for w in tokens if w in c.get("댓글원문", "") + c.get("출처영상", ""))
            by_fail = sum(1 for p in topic_pieces(g["주제"]) if p.replace(" ", "")[:max(1, len(p) - 1)] in fail_text)
            return (by_menu * 2 + by_fail, g["건수"])
        groups.sort(key=relevance, reverse=True)
        group = groups[0] if groups else None
    comment_ids = group["댓글ID"] if group else []
    pids = [p.strip() for p in test.get("사용상품ID", "").split(",") if p.strip()]
    product = store.get("products", pids[0]) if pids else None
    inquiries = [q for q in store.rows("inquiries") if product and q.get("상품ID") == product["상품ID"]]
    return {"test": test, "menu": menu, "pain_cat": pain_cat, "group": group, "comment_ids": comment_ids,
            "product": product, "inquiries": inquiries}


# ---------------------------------------------------------------- 항목별 초안
def build_sections(store, test_id: str, kind: str, audience: str = "여러분") -> tuple[dict, dict]:
    if kind not in KINDS:
        raise WorkbenchError(f"콘텐츠 종류는 {', '.join(KINDS)} 중 하나입니다.")
    g = gather(store, test_id)
    t, menu_rec, grp, prod = g["test"], g["menu"], g["group"], g["product"]
    menu = t.get("메뉴", "").strip()
    fixes = [_fix(x) for x in _lines(t.get("실패와수정"))]
    steps, scenes, ingredients = _lines(t.get("조리순서")), _lines(t.get("촬영장면")), _lines(t.get("재료와양"))
    topic = grp["주제"] if grp else ""
    pain_quote = grp["대표댓글"] if grp else ""
    if grp:  # 대표 댓글은 이 메뉴 이름이 들어간 것을 우선
        tokens = [w for w in re.split(r"\s+", menu) if len(w) >= 2]
        for cid in grp["댓글ID"]:
            c = store.get("comments", cid) or {}
            if any(w in c.get("댓글원문", "") for w in tokens):
                pain_quote, grp = c["댓글원문"], {**grp, "대표댓글ID": cid}
                break
    first_fail = fixes[0][0] if fixes else ""
    adj = topic_adj(topic) if topic else "생각대로 잘 안 되는"
    S: dict[str, str] = {}

    # 제목과 썸네일을 먼저 정한다. 해결 방법(정답)은 넣지 않는다.
    titles = [f"{menu}, {adj} 이유가 따로 있었습니다",
              f"{menu}, {adj} 분들은 이것 하나만 바꿔 보세요",
              f"{josa(audience, '이/가')} 물어본 {menu}, 제가 직접 다시 해 봤습니다"]
    S["제목 후보"] = "\n".join(f"{i}. {x}" for i, x in enumerate(titles, 1)) + \
        "\n\n※ 제목의 약속(왜 그런지·무엇을 바꿨는지)은 도입부에서 바로 이어집니다. 해결 방법은 제목에 넣지 않았습니다."
    thumbs = [f"{menu} 왜 실패할까?", "딱 하나만 바꿨습니다", f"{menu}, 뭐가 달랐을까?"]
    thumbs = [x for x in thumbs if len(x) <= THUMB_MAX] or ["이것만 바꿨습니다"]
    S["썸네일 문구"] = "\n".join(f"- {x} ({len(x)}자)" for x in thumbs) + f"\n\n※ {THUMB_MAX}자 이하, 정답 비노출."

    # 롱폼 구성
    L = [f"종류: {kind}" + (" — 상품을 집중 검증하는 영상" if kind == "키 콘텐츠" else " — 메뉴가 중심, 상품은 조연"),
         "", "0) 콜드 오픈: " + need(scenes[0] if scenes else "", "첫 장면(완성샷). 해결 방법은 아직 안 보여 줌"),
         "1) 문제 제기: " + (f"댓글 \"{pain_quote}\"({grp['대표댓글ID']})" if grp else need("", "연결된 시청자 댓글")),
         "2) 재료: " + (", ".join(ingredients) if ingredients else need("", "재료와 양")),
         "3) 조리와 셰프 포인트: 조리 순서 " + (f"{len(steps)}단계" if steps else need("", "조리 순서"))
         + (f", 실패→수정 {len(fixes)}개를 단계 사이에 배치" if fixes else ""),
         "4) 시식: " + need(t.get("맛평가"), "맛 평가"),
         "5) 정리: 바꾼 점 " + (" / ".join(f[1] for f in fixes if f[1])[:120] or need("", "수정 내용"))]
    if kind == "키 콘텐츠":
        L += ["", "[상품 검증 구간]"]
        if prod:
            L += ["- 공식 자료로 확인된 기능: " + (", ".join(_lines(prod.get("확인된기능"))) or need("", "공식 자료 확인")),
                  "- 실제 조리에서 확인한 것: " + need(prod.get("직접사용경험"), "직접 사용 경험"),
                  "- 확인 안 된 판매 문구(영상에서 말하지 않음): " + (", ".join(_lines(prod.get("확인되지않은주장"))) or "없음"),
                  "- 필요 없는 분·구매 전 비교 조건은 '공구 FAQ' 항목 참고"]
        else:
            L.append("- " + need("", "사용 상품 — ③ 조리 테스트의 사용상품ID"))
    S["롱폼 구성"] = "\n".join(L)

    # 촬영 순서표
    if scenes:
        S["촬영 순서표"] = "\n".join(f"{i}. {x}" for i, x in enumerate(scenes, 1))
    else:
        S["촬영 순서표"] = "\n".join(f"{i}. {x} (조리순서에서 옮김 — 촬영 장면은 셰프 확인 필요)"
                                  for i, x in enumerate(steps, 1)) or need("", "촬영 장면")

    # 도입부: 공감 → 문제 → 사례 → 볼 이유
    intro = [f"[공감] {audience}, {menu} 하다가 {adj} 경험 있으시죠?",
             "[문제] " + (f"댓글에도 이런 이야기가 있었습니다. \"{pain_quote}\"" if pain_quote else need("", "연결된 시청자 댓글")),
             "[사례] " + (f"저도 테스트할 때 그랬습니다. 제 기록에는 ‘{first_fail}’라고 적혀 있습니다." if first_fail else need("", "테스트 중 실패 사례")),
             f"[볼 이유] 오늘은 제가 직접 바꿔 본 한 가지를 보여 드립니다. 왜 그런지도 같이 알려 드릴게요."]
    S["도입부 대본"] = "\n".join(intro)

    # 본문
    B = [f"불 세기: {need(t.get('불세기'), '불 세기')}", f"조리 시간: {need(t.get('조리시간'), '조리 시간')}", ""]
    B += [f"재료: {x}" for x in ingredients] or [f"재료: {need('', '재료와 양')}"]
    B.append("")
    for i, st in enumerate(steps, 1):
        B.append(f"{i}. {st}")
    if not steps:
        B.append(need("", "조리 순서"))
    for before, after in fixes:
        B.append(f"[셰프 포인트] 처음엔 ‘{before}’였습니다. " + (f"그래서 ‘{after}’로 바꿨습니다." if after else need("", "수정 내용")))
    B.append(f"[시식] {need(t.get('맛평가'), '맛 평가')}")
    B.append("※ 재료량·불 세기·시간은 조리 기록에 적힌 그대로입니다. 새로 더하지 않았습니다.")
    S["본문 대본"] = "\n".join(B)

    # 쇼츠: 서로 다른 문제·장면
    shorts = []
    for i, (before, after) in enumerate(fixes[:3], 1):
        scene = scenes[i] if len(scenes) > i else (scenes[0] if scenes else "")
        shorts.append(f"쇼츠 {i}\n- 훅: ‘{before}’ — 이런 적 있으세요?\n- 장면: {need(scene, '장면')}\n- 해결: "
                      + (f"‘{after}’로 바꿨습니다." if after else need("", "수정 내용"))
                      + "\n- 끝 문장: 전체 과정은 본 영상에서 보여 드립니다.")
    if not shorts:
        shorts.append("쇼츠 1\n- " + need("", "실패와 수정 기록(쇼츠마다 다른 문제를 쓰기 위해 필요)"))
    S["쇼츠·릴스"] = "\n\n".join(shorts) + "\n\n※ 쇼츠마다 다른 문제를 다룹니다. 외부 링크 없이 본 영상으로 안내합니다."

    # 유튜브 설명글
    tag2 = "#" + re.sub(r"\s+", "", menu)
    tag3 = "#" + ((menu_rec or {}).get("요리권역") or "집밥")
    D = [f"#로빈의밥상 {tag2} {tag3}", "",
         f"{menu}, {adj} 이유가 있습니다.", f"오늘 {josa(menu, '은/는')} 제가 직접 테스트하며 바꾼 방법으로 만듭니다.",
         f"{menu} 할 때 참고해 주세요.", "", "[재료]"]
    D += ingredients or [need("", "재료와 양")]
    D += ["", "[만드는 법]"]
    D += [f"{i}. {x}" for i, x in enumerate(steps[:8], 1)] or [need("", "조리 순서")]
    if len(steps) > 8:
        D.append("(나머지 단계는 영상에서)")
    D += ["", "[타임라인]", need("", "편집 후 실제 영상 시간으로 입력"), "",
          f"{audience}, 도움이 되셨다면 구독과 좋아요 부탁드립니다.", f"멤버십: {MEMBERSHIP}", "", "© 로빈의밥상"]
    S["유튜브 설명글"] = "\n".join(D)

    S["커뮤니티 게시글"] = "\n".join([
        f"{audience}, {menu} 할 때 어디서 제일 막히세요?",
        "1) " + (topic or "맛") + "  2) 시간  3) 재료  4) 기타(댓글로)",
        f"다음 영상에서 {menu}, 제가 직접 테스트한 과정으로 보여 드립니다."])

    S["인스타 캡션·스토리"] = "\n".join([
        "[캡션]", f"{menu} 할 때 {adj} 순간, 원인은 따로 있었습니다.",
        "제가 직접 테스트하면서 한 가지를 바꿨습니다.", "전체 과정은 프로필 링크에서 확인해 주세요.", "",
        "[스토리]", f"1장: {menu}, 이런 적 있으세요?", "2장: 제가 테스트한 결과는…", "3장: 프로필 링크에서 전체 보기",
        "", "※ 인스타그램은 해시태그를 쓰지 않습니다."])

    # 공구 FAQ
    F = []
    if not prod:
        F.append("사용 상품이 없어 공구 FAQ를 만들지 않았습니다. (메뉴 중심 영상)")
    else:
        F += [f"상품: {prod.get('상품명')} / 모델: {need(prod.get('정확한모델'), '정확한 모델')}",
              f"공식 자료: {need(prod.get('공식자료출처'), '공식 자료 출처')} (확인일 {need(prod.get('확인날짜'), '확인 날짜')})", ""]
        for q in g["inquiries"]:
            F.append(f"Q. {q.get('질문원문')}  ({q['문의ID']})")
            if q.get("답변") and q.get("답변근거"):
                F.append(f"A. {q['답변']}\n   근거: {q['답변근거']}")
            elif q.get("답변"):
                F.append(f"A. {NEED.format('답변 근거 없음 — 근거 확인 전 공개 금지')} 답변 초안: {q['답변']}")
            else:
                F.append(f"A. {NEED.format('답변 없음')}")
            F.append("")
        if not g["inquiries"]:
            F += [NEED.format("이 상품의 고객 질문이 아직 없음 — ⑤-1 공동구매 문의 입력"), ""]
        F += ["[이 제품이 필요 없을 수 있는 분] — 셰프 확인 후 확정",
              "- 지금 쓰는 냄비로 같은 메뉴가 문제없이 되는 분",
              "- 우리 집 화구·수납 공간에 맞는지 확인이 안 된 분", "",
              "[구매 전 비교할 조건]", "- 우리 집 화구(가스·인덕션)에서 쓸 수 있는지: 공식 자료로 확인",
              "- 용량·무게: " + need("", "공식 사양"), "- 가격: " + need(prod.get("가격"), "가격과 기준"),
              "- 공구 조건: " + need(prod.get("공구조건"), "공구 조건"), "",
              "[확인 안 된 판매 문구 — FAQ·본문에 쓰지 않음]"]
        F += [f"- {x}" for x in _lines(prod.get("확인되지않은주장"))] or ["- 없음"]
    S["공구 FAQ"] = "\n".join(F).rstrip()

    evidence = {"테스트ID": t["테스트ID"], "메뉴ID": (menu_rec or {}).get("메뉴ID", ""),
                "댓글ID": g["comment_ids"], "상품ID": (prod or {}).get("상품ID", ""),
                "문의ID": [q["문의ID"] for q in g["inquiries"]]}
    S["근거·확인 필요"] = ""  # 아래에서 채움
    S["근거·확인 필요"] = evidence_text(evidence, S)
    return S, evidence


def evidence_text(ev: dict, sections: dict) -> str:
    needs = sorted({m for k, v in sections.items() if k != "근거·확인 필요" for m in re.findall(r"\[확인 필요: [^\]]+\]", v)})
    L = [f"상태: {STATUS}", f"원본 조리 테스트: {ev['테스트ID']} (셰프 확인됨)",
         f"메뉴 후보: {ev['메뉴ID'] or '연결 없음'}", f"시청자 댓글 근거: {', '.join(ev['댓글ID']) or '없음'}",
         f"상품: {ev['상품ID'] or '없음'}", f"공구 문의 근거: {', '.join(ev['문의ID']) or '없음'}", "",
         "확인 필요 목록:"] + ([f"- {x}" for x in needs] or ["- 없음"])
    return "\n".join(L)


def qa_check(text: str, product: dict | None = None) -> list[str]:
    warns = []
    for w in FORBIDDEN:
        if w in text:
            warns.append(f"금지어 '{w}'가 들어 있습니다.")
    for w in CLAIM_WORDS:
        if w in text:
            warns.append(f"근거 확인이 필요한 표현 '{w.strip()}'이(가) 있습니다. 효능·성능 주장은 근거 없이 쓰지 않습니다.")
    for claim in _lines((product or {}).get("확인되지않은주장", "")):
        core = claim.split("(")[0].strip()
        if len(core) >= 6 and core in text:
            warns.append(f"확인 안 된 판매 문구가 본문에 들어 있습니다: '{core}'")
    return warns


# ---------------------------------------------------------------- 저장·버전
def _drafts(store) -> dict:
    return store.data.setdefault("drafts", {})


def current(sec: dict) -> str:
    return sec["chef"] if sec.get("chef") is not None else sec["auto"]


def _snapshot(d: dict, who: str, note: str) -> None:
    d["versions"].append({"버전": len(d["versions"]) + 1, "시각": now(), "주체": who, "메모": note,
                          "내용": {k: current(v) for k, v in d["sections"].items()}})


def create_draft(store, test_id: str, kind: str = "풀링 콘텐츠", audience: str = "여러분") -> str:
    sections, ev = build_sections(store, test_id, kind, audience)
    drafts = _drafts(store)
    n = len(drafts) + 1
    prefix = ("EX-" if store.mode == "예시" else "") + "D-"
    while f"{prefix}{n:04d}" in drafts:
        n += 1
    did = f"{prefix}{n:04d}"
    ts = now()
    drafts[did] = {"초안ID": did, "테스트ID": test_id, "종류": kind, "호칭": audience, "상태": STATUS,
                   "만든시각": ts, "근거": ev,
                   "sections": {k: {"auto": v, "chef": None, "auto_시각": ts, "chef_시각": None} for k, v in sections.items()},
                   "versions": []}
    _snapshot(drafts[did], "자동", "처음 만들기")
    store.log("drafts", did, "추가", "", f"{test_id} / {kind}", "콘텐츠 초안 만들기")
    store.save(f"콘텐츠 초안 {did} 만들기")
    return did


def get_draft(store, did: str) -> dict:
    d = _drafts(store).get(did)
    if not d:
        raise WorkbenchError(f"초안 {did} 가 없습니다.")
    return d


def save_edit(store, did: str, section: str, text: str) -> bool:
    """셰프 수정 저장. 바뀐 게 없으면 저장하지 않는다."""
    d = get_draft(store, did)
    if section not in d["sections"]:
        raise WorkbenchError(f"'{section}' 항목이 없습니다.")
    sec = d["sections"][section]
    before = current(sec)
    text = (text or "").rstrip()
    if text == before.rstrip():
        return False
    sec["chef"], sec["chef_시각"] = text, now()
    store.log("drafts", did, section, before, text, "셰프 수정")
    _snapshot(d, "셰프", f"'{section}' 수정")
    store.save(f"초안 {did} '{section}' 셰프 수정")
    return True


def undo_edit(store, did: str, section: str) -> None:
    """셰프 수정을 빼고 자동 초안으로 되돌린다(수정본은 버전 기록에 남아 있음)."""
    d = get_draft(store, did)
    sec = d["sections"][section]
    if sec.get("chef") is None:
        return
    store.log("drafts", did, section, sec["chef"], sec["auto"], "셰프 수정 취소 → 자동 초안")
    sec["chef"], sec["chef_시각"] = None, None
    _snapshot(d, "셰프", f"'{section}' 수정 취소")
    store.save(f"초안 {did} '{section}' 수정 취소")


def regenerate(store, did: str) -> dict:
    """자동 초안만 새로 만든다. 셰프가 고친 항목은 그대로 둔다."""
    d = get_draft(store, did)
    sections, ev = build_sections(store, d["테스트ID"], d["종류"], d.get("호칭", "여러분"))
    kept, changed = [], []
    ts = now()
    for k, v in sections.items():
        sec = d["sections"].setdefault(k, {"auto": "", "chef": None, "auto_시각": ts, "chef_시각": None})
        if sec["auto"] != v:
            changed.append(k)
            store.log("drafts", did, k + "(자동안)", sec["auto"], v, "자동 초안 다시 만들기")
            sec["auto"], sec["auto_시각"] = v, ts
        if sec.get("chef") is not None:
            kept.append(k)
    d["근거"] = ev
    _snapshot(d, "자동", f"다시 만들기 — 바뀐 자동안 {len(changed)}개, 셰프 수정 {len(kept)}개 유지")
    store.save(f"초안 {did} 다시 만들기")
    return {"바뀐자동안": changed, "유지된셰프수정": kept}


def export_draft(store, did: str) -> "Path":
    from pathlib import Path  # noqa
    d = get_draft(store, did)
    prod = store.get("products", d["근거"].get("상품ID", "")) if d["근거"].get("상품ID") else None
    L = [f"# 콘텐츠 초안 {did} — {d['종류']}", "", f"- 상태: **{d['상태']}**", f"- 원본 조리 테스트: {d['테스트ID']}",
         f"- 만든 시각: {d['만든시각']} / 버전 {len(d['versions'])}", ""]
    allw = []
    for k in SECTIONS:
        sec = d["sections"].get(k)
        if not sec:
            continue
        tag = "셰프 수정" if sec.get("chef") is not None else "자동 초안"
        txt = current(sec)
        allw += [f"{k}: {w}" for w in qa_check(txt, prod)]
        L += [f"## {k}  _({tag})_", "", txt, ""]
    L += ["## 점검 결과", ""] + ([f"- {w}" for w in allw] or ["- 금지어·근거 없는 주장 표현 없음 (규칙 기반 점검)"])
    out = store.output_dir() / f"콘텐츠초안_{did}_{dt.datetime.now():%Y%m%d_%H%M%S}.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    return out
