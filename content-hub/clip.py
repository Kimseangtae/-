#!/usr/bin/env python3
"""
content-hub: 롱폼 영상 → 세로 쇼츠·릴스 클립(1080x1920) 자르기. ffmpeg 필요.

구간은 사람이(또는 Claude 가 자막·대본을 읽고) 고른다. 이 도구는 자르고, 세로로 바꾸고, 제목·자막을 얹는다.

  python clip.py 원본.mp4 --cuts "03:10-03:52,12:05-12:50" --out clips
  python clip.py 원본.mp4 --cuts "03:10-03:52" --title "김장 김치가 위에서부터 시는 이유" --srt 원본.srt
  python clip.py 원본.mp4 --cuts "03:10-03:52" --mode crop     # 가운데를 꽉 채워 자르기 (기본은 흐린 배경 + 원본 전체)

  --mode blur : 가로 화면 전체를 가운데에 두고 위아래는 같은 화면을 흐리게 깔아 채운다 (요리 손동작이 잘리지 않음)
  --mode crop : 세로로 꽉 차게 가운데만 자른다 (얼굴·냄비가 가운데 있을 때)
  쇼츠는 3분까지 올라가지만 짧을수록 끝까지 보는 비율이 높다. 60초 넘으면 경고만 한다.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FONT_CANDIDATES = ["/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "C:/Windows/Fonts/malgunbd.ttf",
                   "/System/Library/Fonts/AppleSDGothicNeo.ttc"]


def ts(raw: str) -> float:
    parts = [float(p) for p in raw.strip().split(":")]
    sec = 0.0
    for p in parts:
        sec = sec * 60 + p
    return sec


def parse_cuts(raw: str) -> list[tuple[float, float]]:
    cuts = []
    for seg in raw.split(","):
        a, _, b = seg.partition("-")
        s, e = ts(a), ts(b)
        if e <= s:
            raise SystemExit(f"구간이 잘못됐습니다: {seg}")
        cuts.append((s, e))
    return cuts


def srt_time(t: float) -> str:
    t = max(t, 0)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s - int(s)) * 1000)):03d}"


def shift_srt(text: str, start: float, end: float) -> str:
    """원본 자막에서 [start, end] 구간만 남기고 0초 기준으로 당긴다."""
    out, n = [], 0
    for block in re.split(r"\n\s*\n", text.strip()):
        m = re.search(r"(\d+:\d+:\d+[,.]\d+)\s*-->\s*(\d+:\d+:\d+[,.]\d+)", block)
        if not m:
            continue
        a, b = (ts(x.replace(",", ".")) for x in m.groups())
        if b <= start or a >= end:
            continue
        n += 1
        body = block[m.end():].strip()
        out.append(f"{n}\n{srt_time(max(a, start) - start)} --> {srt_time(min(b, end) - start)}\n{body}")
    return "\n\n".join(out) + "\n"


def ff_escape(path: str) -> str:
    """ffmpeg 필터 안의 경로 (윈도우 C:/ 의 콜론 포함)."""
    return path.replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def build_filter(mode: str, title_file: str | None, srt_file: str | None, font: str | None) -> str:
    if mode == "crop":
        chain = "[0:v]scale=-2:1920,crop=1080:1920,setsar=1[v0]"
    else:
        chain = ("[0:v]split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:2[bg];"
                 "[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v0]")
    last = "v0"
    if title_file and font:
        chain += (f";[{last}]drawtext=fontfile='{ff_escape(font)}':textfile='{ff_escape(title_file)}':fontsize=72:"
                  f"fontcolor=white:borderw=6:bordercolor=black:line_spacing=18:x=(w-text_w)/2:y=220[v1]")
        last = "v1"
    if srt_file:
        name = "Malgun Gothic" if font and "malgun" in font.lower() else (
            "Apple SD Gothic Neo" if font and "Apple" in font else "Noto Sans CJK KR")
        style = f"FontName={name},FontSize=16,Outline=2,MarginV=90,Alignment=2"
        chain += f";[{last}]subtitles='{ff_escape(srt_file)}':force_style='{style}'[v2]"
        last = "v2"
    return chain + f";[{last}]fps=30,format=yuv420p[vout]"


def wrap_title(title: str, width: int = 12) -> str:
    """한 줄 12자 안팎으로 끊는다 (세로 화면 72pt 기준)."""
    lines, cur = [], ""
    for w in title.split():
        if len((cur + " " + w).strip()) > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return "\n".join(lines[:3])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--cuts", required=True, help='"mm:ss-mm:ss,mm:ss-mm:ss"')
    ap.add_argument("--out", default="clips")
    ap.add_argument("--mode", choices=["blur", "crop"], default="blur")
    ap.add_argument("--title", help="화면 위쪽 고정 제목 (모든 클립 같은 제목)")
    ap.add_argument("--srt", help="원본 자막 파일 → 구간에 맞춰 잘라 입힘")
    ap.add_argument("--dry", action="store_true", help="ffmpeg 명령만 출력")
    a = ap.parse_args()

    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg 이 없습니다. 윈도우: winget install Gyan.FFmpeg 후 창을 다시 여세요.")
    src = Path(a.video)
    if not src.exists():
        raise SystemExit(f"영상이 없습니다: {src}")
    font = next((f for f in FONT_CANDIDATES if Path(f).exists()), None)
    if a.title and not font:
        print("[warn] 한글 글꼴을 못 찾아 제목을 빼고 만듭니다.", file=sys.stderr)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="clip_"))
    title_file = None
    if a.title:
        title_file = str(tmp / "title.txt")
        Path(title_file).write_text(wrap_title(a.title), encoding="utf-8")
    srt_text = Path(a.srt).read_text(encoding="utf-8-sig") if a.srt else None
    made = []
    for i, (s, e) in enumerate(parse_cuts(a.cuts), 1):
        if e - s > 60:
            print(f"[warn] {i}번 클립 {e - s:.0f}초 — 60초 안쪽이 끝까지 보는 비율이 높습니다.", file=sys.stderr)
        srt_file = None
        if srt_text:
            srt_file = str(tmp / f"c{i}.srt")
            Path(srt_file).write_text(shift_srt(srt_text, s, e), encoding="utf-8")
        dst = out / f"{src.stem}_clip{i:02d}.mp4"
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{s:.2f}", "-t", f"{e - s:.2f}", "-i", str(src),
               "-filter_complex", build_filter(a.mode, title_file if font else None, srt_file, font),
               "-map", "[vout]", "-map", "0:a?", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
               "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(dst)]
        if a.dry:
            print(" ".join(f'"{c}"' if " " in c or ";" in c else c for c in cmd))
            continue
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            print(f"[실패] {i}번 클립: {r.stderr.strip()[-400:]}", file=sys.stderr)
            continue
        made.append(dst)
        print(f"{i}번 클립 {e - s:.0f}초 → {dst}")
    shutil.rmtree(tmp, ignore_errors=True)
    if not a.dry:
        print(f"클립 {len(made)}개 완료. 쇼츠 설명글은 hub.py create <소재ID> --platforms shorts 로.")
    return 0 if (made or a.dry) else 1


if __name__ == "__main__":
    sys.exit(main())
