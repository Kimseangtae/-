#!/usr/bin/env python3
"""
content-hub: 카드뉴스·캐러셀 이미지 생성기.

캐러셀 문구 파일(아래 형식)을 넣으면 슬라이드 PNG 를 만든다. 캡션은 caption.txt 로 따로 저장한다.

    [1장 훅]
    김장김치를 버리게 만드는
    보관 실수 5가지
    (화면: ...)            ← 괄호로 시작하는 줄은 메모라 그리지 않음
    [2장 실수 1]
    제목 줄
    본문 줄 …
    [캡션]
    인스타 캡션 …

사용 예
  python3 cards.py 캐러셀.md 출력폴더
  python3 cards.py 캐러셀.md 출력폴더 --jpg          # 인스타 자동 발행용 JPEG
  python3 cards.py 캐러셀.md 출력폴더 --size 1080x1080 --image 8=사진.png --image 1=표지.jpg:0,0,600,400
  python3 cards.py spec.json 출력폴더      # JSON: {"slides":[{"badge":"","title":"","body":[""],"image":{"path":"","crop":[x0,y0,x1,y1]}}], "caption":""}
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONTS = {
    "bold": [("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 1), ("C:/Windows/Fonts/malgunbd.ttf", 0),
             ("/System/Library/Fonts/AppleSDGothicNeo.ttc", 6), ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 0)],
    "reg": [("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 1), ("C:/Windows/Fonts/malgun.ttf", 0),
            ("/System/Library/Fonts/AppleSDGothicNeo.ttc", 0), ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 0)],
}
THEME = {"bg": (251, 247, 240), "ink": (38, 34, 30), "sub": (110, 102, 94), "accent": (214, 48, 49),
         "highlight": (255, 214, 64), "card": (255, 255, 255)}
BRAND = "로빈의밥상"
SECTION = re.compile(r"^\[(\d+)\s*장\s*(.*?)\]\s*$")
PLAIN_LABELS = {"훅", "표지", "공감", "마무리", "정리"}


def font(kind: str, size: int):
    for path, idx in FONTS[kind]:
        if Path(path).exists():
            return ImageFont.truetype(path, size, index=idx)
    raise SystemExit("한글 글꼴을 찾지 못했습니다 (윈도우는 맑은 고딕이 기본으로 있음, 리눅스는 fonts-noto-cjk 설치).")


def wrap(d: ImageDraw.ImageDraw, text: str, f, width: int) -> list[str]:
    """공백 기준으로 줄을 나누고, 한 단어가 너무 길면 글자 단위로 자른다."""
    lines, cur = [], ""
    for word in text.split(" "):
        trial = (cur + " " + word).strip()
        if d.textlength(trial, font=f) <= width:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        cur = ""
        for ch in word:
            if d.textlength(cur + ch, font=f) > width:
                lines.append(cur)
                cur = ch
            else:
                cur += ch
    if cur:
        lines.append(cur)
    return lines


def parse_md(text: str) -> dict:
    slides, caption, cur, in_caption = [], [], None, False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("<!--"):
            continue
        if line == "[캡션]":
            in_caption, cur = True, None
            continue
        m = SECTION.match(line)
        if m:
            in_caption = False
            cur = {"label": m.group(2).strip(), "lines": []}
            slides.append(cur)
            continue
        if in_caption:
            caption.append(raw.rstrip())
        elif cur is not None and line and not line.startswith("("):
            cur["lines"].append(line)
    out = []
    for i, s in enumerate(slides):
        if not s["lines"]:
            continue
        if i == 0 or s["label"] in PLAIN_LABELS:
            out.append({"badge": "", "title": " ".join(s["lines"][:2]) if i == 0 else s["lines"][0],
                        "body": [] if i == 0 else s["lines"][1:], "cover": i == 0})
        else:
            out.append({"badge": s["label"], "title": s["lines"][0], "body": s["lines"][1:]})
    return {"slides": out, "caption": "\n".join(caption).strip()}


def load_image(spec: dict, max_w: int, max_h: int) -> Image.Image:
    im = Image.open(spec["path"]).convert("RGB")
    if spec.get("crop"):
        im = im.crop(tuple(spec["crop"]))
    scale = min(max_w / im.width, max_h / im.height)
    im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))), Image.LANCZOS)
    if scale > 1.2:  # 작은 사진을 키웠으면 살짝 선명하게
        im = im.filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=3))
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, im.width, im.height], 28, fill=255)
    out = Image.new("RGBA", im.size)
    out.paste(im, (0, 0), mask)
    return out


def draw_slide(s: dict, n: int, total: int, W: int, H: int, body_size: int) -> tuple[Image.Image, int]:
    M = 80
    im = Image.new("RGB", (W, H), THEME["bg"])
    d = ImageDraw.Draw(im)
    small = font("reg", 28)
    d.text((W - M - d.textlength(f"{n} / {total}", font=small), 50), f"{n} / {total}", font=small, fill=THEME["sub"])
    d.text((M, H - 80), BRAND, font=small, fill=THEME["sub"])
    y = 110
    if s.get("badge"):
        bf = font("bold", 34)
        bw = d.textlength(s["badge"], font=bf)
        d.rounded_rectangle([M, y, M + bw + 48, y + 66], 999, fill=THEME["accent"])
        d.text((M + 24, y + 9), s["badge"], font=bf, fill=(255, 255, 255))
        y += 110
    cover = s.get("cover")
    tf = font("bold", 92 if cover else 64)
    if cover:
        y = int(H * 0.30)
    for ln in wrap(d, s["title"], tf, W - 2 * M):
        d.text((M, y), ln, font=tf, fill=THEME["ink"])
        y += int(tf.size * 1.3)
    if cover:
        d.rectangle([M, y + 20, M + 120, y + 30], fill=THEME["accent"])
        y += 70
    y += 30
    if s.get("image"):
        room = H - y - 140 - int(body_size * 1.55) * len(s.get("body", []))
        pic = load_image(s["image"], W - 2 * M, max(240, min(620, room)))
        im.paste(pic, ((W - pic.width) // 2, y), pic)
        y += pic.height + 40
    bf = font("reg", body_size)
    for para in s.get("body", []):
        for ln in wrap(d, para, bf, W - 2 * M):
            d.text((M, y), ln, font=bf, fill=THEME["ink"])
            y += int(bf.size * 1.55)
        y += 14
    return im, y


def render(spec: dict, out_dir: Path, size: tuple[int, int] = (1080, 1350), ext: str = "png") -> list[Path]:
    """본문이 넘치면 글자를 40→30 까지 줄여 본다. 그래도 넘치면 경고."""
    W, H = size
    out_dir.mkdir(parents=True, exist_ok=True)
    slides = spec["slides"]
    paths = []
    for n, s in enumerate(slides, 1):
        for body_size in (40, 36, 33, 30):
            im, y = draw_slide(s, n, len(slides), W, H, body_size)
            if y <= H - 110:
                break
        else:
            print(f"[warn] {n}장 글이 길어 아래가 잘렸을 수 있습니다. 문장을 줄이세요.", file=sys.stderr)
        p = out_dir / f"slide_{n:02d}.{ext}"
        if ext == "jpg":
            im.save(p, quality=95, subsampling=0)  # 인스타 자동 발행은 JPEG 만 받는다
        else:
            im.save(p)
        paths.append(p)
    if spec.get("caption"):
        (out_dir / "caption.txt").write_text(spec["caption"] + "\n", encoding="utf-8")
    return paths


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="캐러셀 문구 .md 또는 spec .json")
    ap.add_argument("out_dir")
    ap.add_argument("--size", default="1080x1350", help="1080x1350(인스타 세로) 또는 1080x1080(정사각)")
    ap.add_argument("--jpg", action="store_true", help="JPEG 로 저장 (인스타 자동 발행용)")
    ap.add_argument("--image", action="append", default=[], help="N=사진경로[:x0,y0,x1,y1]  N장에 사진 넣기")
    args = ap.parse_args()
    src = Path(args.source)
    text = src.read_text(encoding="utf-8")
    spec = json.loads(text) if src.suffix == ".json" else parse_md(text)
    for item in args.image:
        num, _, rest = item.partition("=")
        path, _, crop = rest.partition(":")
        idx = int(num) - 1
        if not (0 <= idx < len(spec["slides"])):
            print(f"[warn] {num}장이 없습니다: {item}", file=sys.stderr)
            continue
        spec["slides"][idx]["image"] = {"path": path, "crop": [int(v) for v in crop.split(",")] if crop else None}
    w, h = (int(v) for v in args.size.lower().split("x"))
    paths = render(spec, Path(args.out_dir), (w, h), "jpg" if args.jpg else "png")
    print(f"슬라이드 {len(paths)}장 → {args.out_dir}" + (" (caption.txt 포함)" if spec.get("caption") else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
