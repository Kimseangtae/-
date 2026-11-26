#!/usr/bin/env python3
"""
content-hub MCP 서버: Claude 데스크톱·ChatGPT·Gemini 같은 AI 가 소재함·작성·예약을 쓰게 한다.

일부러 빠진 것: 승인(queue approve)과 발행(run). AI 가 스스로 승인·발행하지 못하게 사람 손에만 둔다.

실행:  pip install mcp   →   python content-hub/mcp_server.py      (stdio)
Claude 데스크톱 설정(claude_desktop_config.json) 예시는 README 참고.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import hub  # noqa: E402
try:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as Server  # noqa: E402
except ImportError:  # mcp 2.x 에서 이름이 바뀜
    from mcp.server.mcpserver import MCPServer as Server  # noqa: E402

mcp = Server("robyn-content-hub")


def _run(fn, **kw) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            code = fn(argparse.Namespace(**kw))
        except SystemExit as e:
            code = e.code
            if isinstance(e.code, str):
                print(e.code)
    out = buf.getvalue().strip()
    return out + ("" if code in (0, None) else f"\n(종료 코드 {code})")


@mcp.tool()
def read_guidelines() -> str:
    """로빈의밥상 제작 지침(금지 목록·플랫폼 규격·공구 규칙). 글을 쓰기 전에 반드시 먼저 읽는다."""
    return (hub.GONGU / "guidelines.md").read_text(encoding="utf-8")


@mcp.tool()
def list_inbox(limit: int = 30) -> str:
    """소재함(점수순). 상태 new=새 소재, picked=선택됨, created=지시서 만듦."""
    return _run(hub.cmd_inbox, all=False, json=True, limit=limit)


@mcp.tool()
def add_source(text: str = "", url: str = "", title: str = "", tags: str = "") -> str:
    """소재 넣기. 직접 쓴 아이디어(text), 참고 링크(url) 중 하나 이상."""
    return _run(hub.cmd_add, text=text, url=url, title=title, file=None, tags=tags, score=70)


@mcp.tool()
def collect_suggest(keyword: str) -> str:
    """유튜브 자동완성(사람들이 실제로 치는 검색어)으로 소재 수집. 키 불필요."""
    return _run(hub.cmd_collect, ig=False, yt=None, suggest=[keyword], threads=False)


@mcp.tool()
def pick(ids: list[str]) -> str:
    """소재 선택. 고른 이유를 사용자에게 한 줄씩 설명한다."""
    return _run(hub.cmd_pick, ids=ids, auto=None, skip=False)


@mcp.tool()
def create_brief(item_id: str, platforms: str = "") -> str:
    """선택한 소재로 플랫폼별 작성 지시서를 만들고 내용을 돌려준다. platforms 예: threads,carousel,reels,shorts,community"""
    out = _run(hub.cmd_create, id=item_id, platforms=platforms or None)
    brief = hub.OUT / item_id / "brief.md"
    return out + ("\n\n" + brief.read_text(encoding="utf-8") if brief.exists() else "")


@mcp.tool()
def write_content(item_id: str, platform: str, text: str) -> str:
    """플랫폼 글을 파일로 저장하고 바로 지침 검사 결과를 돌려준다. 오류가 있으면 고쳐서 다시 저장한다."""
    if platform not in hub.PLATFORMS:
        return f"모르는 플랫폼: {platform}. 가능: {', '.join(hub.PLATFORMS)}"
    f = hub.out_file(item_id, platform)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text.strip() + "\n", encoding="utf-8")
    bad, report = hub.lint_files([f])
    return "\n".join(report) + ("\n오류를 고쳐 다시 저장하세요." if bad else "\n통과")


@mcp.tool()
def check_item(item_id: str) -> str:
    """소재의 작성 파일 전체 검사 + 아직 안 쓴 파일 목록."""
    return _run(hub.cmd_check, id=item_id)


@mcp.tool()
def schedule_post(item_id: str, platform: str, at: str, image_urls: str = "") -> str:
    """예약 등록(한국 시간 "2026-11-10 19:30"). 등록만 하고 승인·발행은 로빈님이 직접 한다."""
    return _run(hub.cmd_queue, qcmd="add", id=item_id, platform=platform, at=at, file=None,
                image_urls=image_urls or None, link=None)


@mcp.tool()
def list_queue() -> str:
    """예약 목록(승인 전 draft / 승인됨 approved / 손으로 올릴 것 manual_due …)."""
    return _run(hub.cmd_queue, qcmd="list", all=False, json=False)


@mcp.tool()
def performance_report(days: int = 14) -> str:
    """최근 성과 보고서(자동 발행분 + 주소를 남긴 게시물)."""
    return _run(hub.cmd_review, days=days, remix=False)


if __name__ == "__main__":
    mcp.run()
