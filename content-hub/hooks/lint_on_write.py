#!/usr/bin/env python3
"""
Claude Code 훅: 콘텐츠 파일을 쓰거나 고치면 바로 지침 검사(lint_content)를 돌린다.
오류가 있으면 종료코드 2 로 Claude 에게 돌려보내 스스로 고치게 한다. 경고만 있으면 통과.
대상: gongu-lab/output/**, content-hub/out/** 의 <…>_<산출물>.md
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "gongu-lab"))


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    fp = (data.get("tool_input") or {}).get("file_path") or ""
    if not fp:
        return 0
    p = Path(fp)
    norm = str(p).replace("\\", "/")
    if p.suffix != ".md" or not ("/gongu-lab/output/" in norm or "/content-hub/out/" in norm) or not p.exists():
        return 0
    import lint_content
    if lint_content.kind_of(p, None) is None:
        return 0
    errs, warns = lint_content.lint(p)
    if errs:
        print(f"[로빈의밥상 지침 검사] {p.name} 오류 {len(errs)}건 — 고쳐서 다시 저장하세요:", file=sys.stderr)
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        return 2
    if warns:
        print(f"[지침 검사] {p.name} 경고: " + " / ".join(warns))
    return 0


if __name__ == "__main__":
    sys.exit(main())
