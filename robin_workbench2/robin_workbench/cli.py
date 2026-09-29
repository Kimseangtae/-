# -*- coding: utf-8 -*-
"""예시 자료로 전체 흐름을 한 번에 돌리고 결과 파일을 다운로드 폴더에 저장한다.
  python -m robin_workbench.cli example   (예시)
  python -m robin_workbench.cli status --mode 실제"""
from __future__ import annotations

import argparse
import datetime as dt
import sys

from . import analysis, content, flow, menus
from .store import Store, WorkbenchError


def run_example(home=None) -> list:
    s = Store(home, "예시")
    analysis.classify_all(s)
    menus.evaluate_all(s)
    out = s.output_dir()
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    files = []
    for name, text in [("불편분석", analysis.pain_report(s)), ("메뉴선정표", menus.menu_report(s)),
                       ("테마밥상", menus.theme_report(s, dt.date(1966, 9, 10), "ISFJ", dt.date.today())),
                       ("성과회고", analysis.retro_report(s)), ("진행현황", flow.status_text(s))]:
        f = out / f"{name}_{stamp}.md"
        f.write_text(text + "\n", encoding="utf-8")
        files.append(f)
    confirmed = [t["테스트ID"] for t in s.rows("tests") if t.get("셰프확인") == "예"]
    for tid in confirmed[:1]:
        did = content.create_draft(s, tid, "키 콘텐츠")
        files.append(content.export_draft(s, did))
    return files


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="로빈 요리·공구 작업실 2.0")
    p.add_argument("command", choices=["example", "status"])
    p.add_argument("--mode", default="예시", choices=["예시", "실제"])
    a = p.parse_args(argv)
    try:
        if a.command == "example":
            files = run_example()
            print("예시 자료로 전체 흐름을 실행했습니다. 결과 파일:")
            for f in files:
                print(" -", f)
        else:
            print(flow.status_text(Store(None, a.mode)))
    except WorkbenchError as e:
        print(f"[멈춤] {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
