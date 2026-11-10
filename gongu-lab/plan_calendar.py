#!/usr/bin/env python3
"""
gongu-lab: 공구 일정(schedule.json) + 타임라인(playbook.json) → 일자별 제작 캘린더.

명령
  plan   [캠페인ID]          캘린더 생성 → calendar/<ID>.md, calendar/<ID>.json (빠진 정보가 있으면 무엇인지 알려주고 멈춤)
  today  [--date YYYY-MM-DD] 오늘(KST) 올릴 것 + 밀린 것. 파일이 있으면 검사 결과까지
  brief  캠페인ID 날짜       그 날 만들 산출물의 제작 지시서(JSON). 클로드가 이걸 보고 파일을 쓴다
  status [캠페인ID]          전체 진행 현황 (미작성 / 작성·검사통과 / 검사오류 / 업로드완료)
  done   항목ID              업로드 완료 표시 (state/posted.json)

산출물 파일 위치: output/<캠페인ID>/<날짜>_<슬롯>_<산출물>.md   (lint_content.py 가 이 이름으로 종류를 판단)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lint_content import lint  # noqa: E402

HERE = Path(__file__).resolve().parent
SCHEDULE = HERE / "schedule.json"
PLAYBOOK = HERE / "playbook.json"
OUTPUT = HERE / "output"
CAL = HERE / "calendar"
POSTED = HERE / "state" / "posted.json"
KST = timezone(timedelta(hours=9))
REQUIRED = {"id": "캠페인 ID", "product": "제품명", "category": "카테고리", "appeal": "소구점 (난이도 해소 / 속도 향상 / 선택 대행)",
            "open_date": "오픈일 YYYY-MM-DD", "drawbacks": "제품 단점 1개 이상 (단점 먼저 짚는 원칙)"}
APPEALS = ("난이도 해소", "속도 향상", "선택 대행")
WEEKDAY = "월화수목금토일"


def load(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def today_kst() -> date:
    return datetime.now(KST).date()


PLAN_KEYS = ("id", "product", "open_date")  # 날짜 캘린더를 만들 때 필요한 것
CONTENT_KEYS = ("category", "appeal", "drawbacks")  # 글을 쓸 때 추가로 필요한 것. 지어내지 않고 채운 뒤에만 작성


def missing_fields(c: dict, keys: tuple = PLAN_KEYS + CONTENT_KEYS) -> list[str]:
    out = [f"{k}: {REQUIRED[k]}" for k in keys if not c.get(k)]
    if "appeal" in keys and c.get("appeal") and c["appeal"] not in APPEALS:
        out.append(f"appeal '{c['appeal']}' 은 {APPEALS} 중 하나")
    if "open_date" in keys:
        for k in ("open_date", "close_date"):
            if c.get(k):
                try:
                    date.fromisoformat(c[k])
                except ValueError:
                    out.append(f"{k} '{c[k]}' 형식 오류 (YYYY-MM-DD)")
    return out


def sale_windows(campaigns: list[dict]) -> dict:
    """캠페인 ID → (오픈일, 마감일). 날짜가 올바른 것만."""
    out = {}
    for c in campaigns:
        try:
            out[c["id"]] = (date.fromisoformat(c["open_date"]), date.fromisoformat(c.get("close_date") or c["open_date"]))
        except (KeyError, ValueError):
            continue
    return out


def build_items(c: dict, playbook: dict) -> list[dict]:
    anchors = {"open": date.fromisoformat(c["open_date"])}
    if c.get("close_date"):
        anchors["close"] = date.fromisoformat(c["close_date"])
    items = []
    for slot in playbook["slots"]:
        base = anchors.get(slot["anchor"])
        if base is None:
            continue  # 마감일이 없으면 마감 기준 슬롯은 건너뜀
        d = base + timedelta(days=(c.get("offsets") or {}).get(slot["id"], slot["offset"]))
        for deliv in slot["deliverables"]:
            fname = f"{d.isoformat()}_{slot['id']}_{deliv}.md"
            items.append({
                "item_id": f"{c['id']}:{slot['id']}:{deliv}",
                "campaign": c["id"], "date": d.isoformat(), "weekday": WEEKDAY[d.weekday()],
                "slot": slot["id"], "slot_label": slot["label"], "deliverable": deliv,
                "deliverable_desc": playbook["deliverables"].get(deliv, deliv),
                "rule": slot["rule"], "file": f"output/{c['id']}/{fname}",
            })
    items.sort(key=lambda i: (i["date"], i["slot"], i["deliverable"]))
    return items


def item_status(item: dict, posted: dict) -> tuple[str, list[str], list[str]]:
    if item["item_id"] in posted:
        return "posted", [], []
    path = HERE / item["file"]
    if not path.exists():
        return "missing", [], []
    errs, warns = lint(path)
    return ("lint_error" if errs else "ready"), errs, warns


STATUS_LABEL = {"missing": "미작성", "ready": "작성·검사통과", "lint_error": "검사오류", "posted": "업로드완료"}


def get_campaigns(only: str | None) -> list[dict]:
    cs = load(SCHEDULE, {"campaigns": []}).get("campaigns", [])
    if only:
        cs = [c for c in cs if c.get("id") == only]
        if not cs:
            sys.exit(f"schedule.json 에 캠페인 '{only}' 가 없습니다.")
    if not cs:
        sys.exit("schedule.json 에 캠페인이 없습니다. schedule.example.json 을 참고해 등록하세요.")
    return cs


def cmd_plan(args) -> int:
    pb_path = Path(args.playbook) if args.playbook else PLAYBOOK
    if not pb_path.is_absolute() and not pb_path.exists():
        pb_path = HERE / pb_path
    playbook = load(pb_path, None) or sys.exit(f"{pb_path} 가 없습니다.")
    windows = sale_windows(load(SCHEDULE, {"campaigns": []}).get("campaigns", []))
    names = {c["id"]: c.get("product", c["id"]) for c in load(SCHEDULE, {"campaigns": []}).get("campaigns", []) if c.get("id")}
    rc = 0
    for c in get_campaigns(args.campaign):
        miss = missing_fields(c, PLAN_KEYS)
        if miss:
            print(f"[{c.get('id', '?')}] 날짜 캘린더를 만들려면 아래 정보가 필요합니다:")
            for m in miss:
                print(f"  - {m}")
            rc = 2
            continue
        content_miss = missing_fields(c, CONTENT_KEYS)
        items = build_items(c, playbook)
        CAL.mkdir(parents=True, exist_ok=True)
        (CAL / f"{c['id']}.json").write_text(json.dumps({"campaign": c, "playbook": pb_path.name, "items": items}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        posted = load(POSTED, {})
        today = today_kst()

        def clash(it: dict) -> str:
            d = date.fromisoformat(it["date"])
            return ", ".join(names.get(k, k) for k, (a, z) in windows.items() if k != c["id"] and a <= d <= z)

        lines = [f"# {c['product']} 공구 캘린더 ({c['id']})", "",
                 f"오픈 {c['open_date']} {c.get('open_time', '')}".strip() + (f" · 마감 {c['close_date']}" if c.get("close_date") else " · 마감일 미정(마감 임박 슬롯 제외)"),
                 f"소구점: {c.get('appeal') or '미정'} · 타임라인: {pb_path.name} ({playbook.get('source', '')})", "",
                 "| 날짜 | 요일 | D- | 슬롯 | 산출물 | 상태 | 비고 | 파일 |", "|---|---|---|---|---|---|---|---|"]
        open_d = date.fromisoformat(c["open_date"])
        clashes = 0
        for it in items:
            st, _, _ = item_status(it, posted)
            d = date.fromisoformat(it["date"])
            past = " (지남)" if d < today and st == "missing" else ""
            other = clash(it)
            clashes += bool(other)
            lines.append(f"| {it['date']} | {it['weekday']} | D{(d - open_d).days:+d} | {it['slot_label']} | {it['deliverable']} | {STATUS_LABEL[st]}{past} | {('타 공구 판매 중: ' + other) if other else ''} | `{it['file']}` |")
        longs = [it["date"] for it in items if it["deliverable"] == "script"]
        lines += ["", f"항목 {len(items)}개 · 롱폼 대본 {len(longs)}개({', '.join(longs) or '없음'}) · 다른 공구 판매 기간과 겹치는 항목 {clashes}개"]
        if clashes:
            lines.append("겹치는 항목은 날짜를 옮기거나(`offsets` 로 슬롯별 조정) 합친다. 판매 중인 공구의 시청자에게 새 공구를 홍보하면 피로가 쌓인다.")
        late = [it for it in items if date.fromisoformat(it["date"]) < today and item_status(it, posted)[0] == "missing"]
        if late:
            lines += ["", f"⚠ 이미 날짜가 지난 미작성 항목 {len(late)}개. 지난 슬롯은 건너뛰고 남은 슬롯에 핵심을 합치는 것을 권한다."]
        if content_miss:
            lines += ["", "글 작성 전에 채워야 할 정보(지어내지 않는다): " + " / ".join(content_miss)]
        (CAL / f"{c['id']}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"[{c['id']}] 항목 {len(items)}개 · 롱폼 {len(longs)}개 · 겹침 {clashes}개 → calendar/{c['id']}.md" + (f" · 글 작성 전 필요한 정보 {len(content_miss)}건" if content_miss else ""))
    return rc


def cmd_today(args) -> int:
    day = date.fromisoformat(args.date) if args.date else today_kst()
    posted = load(POSTED, {})
    found = 0
    print(f"# {day.isoformat()} ({WEEKDAY[day.weekday()]}) 오늘 할 일\n")
    for f in sorted(CAL.glob("*.json")) if CAL.exists() else []:
        cal = load(f, {})
        due = [it for it in cal.get("items", []) if it["date"] == day.isoformat()]
        overdue = [it for it in cal.get("items", []) if it["date"] < day.isoformat() and item_status(it, posted)[0] in ("ready", "lint_error")]
        for tag, group in (("오늘", due), ("밀림(작성됐지만 미업로드)", overdue)):
            for it in group:
                st, errs, warns = item_status(it, posted)
                found += 1
                print(f"- [{tag}] {cal['campaign']['product']} · {it['slot_label']} · {it['deliverable']} · {STATUS_LABEL[st]}")
                print(f"    {it['file']}")
                for e in errs:
                    print(f"    ✗ {e}")
                for w in warns:
                    print(f"    △ {w}")
    if not found:
        print("오늘 올릴 항목이 없습니다. (캘린더가 없으면 `plan` 먼저)")
    return 0


def cmd_brief(args) -> int:
    cal = load(CAL / f"{args.campaign}.json", None) or sys.exit(f"calendar/{args.campaign}.json 이 없습니다. `plan` 먼저.")
    items = [it for it in cal["items"] if it["date"] == args.date]
    if not items:
        sys.exit(f"{args.date} 에 항목이 없습니다.")
    c = cal["campaign"]
    need = missing_fields(c, CONTENT_KEYS)
    if need:
        sys.exit("글을 쓰기 전에 아래 정보가 필요합니다. 지어내지 말고 로빈님께 묻습니다:\n  - " + "\n  - ".join(need))
    brief = {
        "campaign": {k: c.get(k) for k in ("id", "product", "category", "appeal", "open_date", "open_time", "close_date",
                                           "limited_qty", "price_note", "drawbacks", "link", "notes")},
        "items": items,
        "analysis_to_apply": "analysis/ 폴더의 최신 레퍼런스 분석(공구 구조, 소구점, 캐러셀 패턴)을 먼저 읽고 이 슬롯에 맞는 구조를 따른다.",
        "hard_rules": ["'밥깡패' 금지", "매실액 금지(알룰로스/채향원 블루베리 와인식초)", "채칼 표기", "정답 노출 금지(썸네일·제목)",
                       "단점을 먼저 짚고 CTA", "20년 셰프 경력은 콘텐츠당 딱 1회", "실제 조건만(과장·허위 마감 금지)",
                       "자리표시자 금지: 정보가 없으면 작성하지 말고 질문"],
        "after_writing": "python3 gongu-lab/lint_content.py <파일> 로 검사하고 오류를 고친 뒤 끝낸다.",
    }
    print(json.dumps(brief, ensure_ascii=False, indent=2))
    return 0


def cmd_status(args) -> int:
    posted = load(POSTED, {})
    for f in sorted(CAL.glob("*.json")) if CAL.exists() else []:
        cal = load(f, {})
        if args.campaign and cal["campaign"]["id"] != args.campaign:
            continue
        counts: dict[str, int] = {}
        for it in cal["items"]:
            st = item_status(it, posted)[0]
            counts[st] = counts.get(st, 0) + 1
        print(f"{cal['campaign']['id']} ({cal['campaign']['product']}): " + " · ".join(f"{STATUS_LABEL[k]} {v}" for k, v in counts.items()))
    return 0


def cmd_done(args) -> int:
    posted = load(POSTED, {})
    posted[args.item_id] = datetime.now(KST).isoformat(timespec="seconds")
    POSTED.parent.mkdir(parents=True, exist_ok=True)
    POSTED.write_text(json.dumps(posted, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"업로드 완료 표시: {args.item_id}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan"); p.add_argument("campaign", nargs="?"); p.add_argument("--playbook", help="타임라인 파일 (기본 playbook.json)")
    t = sub.add_parser("today"); t.add_argument("--date")
    b = sub.add_parser("brief"); b.add_argument("campaign"); b.add_argument("date")
    s = sub.add_parser("status"); s.add_argument("campaign", nargs="?")
    d = sub.add_parser("done"); d.add_argument("item_id")
    args = ap.parse_args()
    return {"plan": cmd_plan, "today": cmd_today, "brief": cmd_brief, "status": cmd_status, "done": cmd_done}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
