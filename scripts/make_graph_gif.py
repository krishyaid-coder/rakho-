#!/usr/bin/env python3
"""Looping product GIF: dekho --graph shows the cut the model got."""

from __future__ import annotations

import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FRAMES = ROOT / "docs" / "assets" / "_preview" / "graph"
GIF = ROOT / "docs" / "assets" / "dekho-graph.gif"
MP4 = ROOT / "docs" / "assets" / "dekho-graph.mp4"

W, H = 1080, 1080
FPS = 12
BG = (22, 21, 19)
INK = (244, 240, 230)
DIM = (138, 133, 128)
MUTED = (90, 86, 82)
SAFFRON = (224, 134, 60)
RED = (196, 84, 72)
GREEN = (110, 168, 108)
CARD = (36, 34, 31)
LINE = (62, 59, 54)
TERM = (16, 15, 14)

FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_B = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
MONO = "/System/Library/Fonts/Supplemental/Courier New.ttf"
MONO_B = "/System/Library/Fonts/Supplemental/Courier New Bold.ttf"

CMD = 'rakho --db memory.db dekho --actor krishy --graph "invoice"'


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def tw(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.FreeTypeFont) -> int:
    return int(draw.textbbox((0, 0), text, font=fnt)[2])


def lerp(a: float, b: float, t: float) -> float:
    t = max(0.0, min(1.0, t))
    return a + (b - a) * t


def ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def mix(c1, c2, t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return tuple(int(lerp(a, b, t)) for a, b in zip(c1, c2))


def rounded(draw: ImageDraw.ImageDraw, box, fill, outline=None, width=2, radius=18) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    im = Image.new("RGB", (W, H), BG)
    return im, ImageDraw.Draw(im)


def header(draw: ImageDraw.ImageDraw) -> None:
    mark = font(FONT_B, 44)
    draw.text((64, 48), "rakho", font=mark, fill=INK)
    dx = 64 + tw(draw, "rakho", mark) + 12
    draw.ellipse((dx, 62, dx + 16, 78), fill=SAFFRON)
    sub = font(FONT, 26)
    label = "dekho  ·  see the cut"
    draw.text((W - 64 - tw(draw, label, sub), 56), label, font=sub, fill=DIM)
    draw.line((64, 112, W - 64, 112), fill=LINE, width=2)


def footer(draw: ImageDraw.ImageDraw, caption: str) -> None:
    draw.line((64, H - 96, W - 64, H - 96), fill=LINE, width=2)
    draw.text((64, H - 70), caption, font=font(FONT, 26), fill=DIM)


def glow_box(base: Image.Image, box, color, alpha: int) -> Image.Image:
    if alpha <= 0:
        return base
    overlay = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(overlay)
    x0, y0, x1, y1 = box
    d.rounded_rectangle((x0 - 8, y0 - 8, x1 + 8, y1 + 8), radius=22, fill=color)
    blur = overlay.filter(ImageFilter.GaussianBlur(18))
    return Image.blend(base, blur, alpha / 255)


def draw_terminal_chrome(draw: ImageDraw.ImageDraw, box) -> None:
    x0, y0, x1, y1 = box
    rounded(draw, box, TERM, LINE, 2, 22)
    draw.ellipse((x0 + 26, y0 + 20, x0 + 46, y0 + 40), fill=RED)
    draw.ellipse((x0 + 58, y0 + 20, x0 + 78, y0 + 40), fill=SAFFRON)
    draw.ellipse((x0 + 90, y0 + 20, x0 + 110, y0 + 40), fill=GREEN)
    prompt = font(MONO, 22)
    draw.text((x0 + 140, y0 + 18), "krishy  ·  notebook", font=prompt, fill=MUTED)


def node(draw, xy, w, h, title, body, *, accent, alpha=1.0, tag="", meta="") -> None:
    x, y = xy
    fill = mix(BG, CARD, alpha)
    ink = mix(BG, INK, alpha)
    dim = mix(BG, DIM, alpha)
    edge = mix(BG, accent, alpha)
    rounded(draw, (x, y, x + w, y + h), fill, edge, 3, 16)
    draw.rectangle((x, y + 8, x + 7, y + h - 8), fill=edge)
    tfont = font(FONT_B, 22)
    bfont = font(MONO, 26)
    draw.text((x + 28, y + 14), title, font=tfont, fill=edge)
    if tag:
        twid = tw(draw, tag, font(FONT_B, 16))
        tx = x + w - 24 - twid - 16
        rounded(draw, (tx, y + 12, tx + twid + 16, y + 38), mix(BG, accent, 0.22 * alpha), None, 0, 10)
        draw.text((tx + 8, y + 14), tag, font=font(FONT_B, 16), fill=edge)
    draw.text((x + 28, y + 46), body, font=bfont, fill=ink if body else dim)
    if meta:
        draw.text((x + 28, y + 78), meta, font=font(MONO, 18), fill=dim)


def stem(draw, x, y0, y1, label="", *, alpha=1.0) -> None:
    color = mix(BG, SAFFRON, alpha)
    draw.line((x, y0, x, y1), fill=color, width=3)
    if label and y1 - y0 > 28:
        draw.text((x + 14, (y0 + y1) // 2 - 12), label, font=font(MONO, 18), fill=mix(BG, DIM, alpha))


def frame(t: float) -> Image.Image:
    """t is seconds in a 7.8s loop."""
    im, d = canvas()
    header(d)

    term = (64, 140, W - 64, H - 130)
    draw_terminal_chrome(d, term)

    typed = min(1.0, max(0.0, (t - 0.35) / 1.55))
    n = int(len(CMD) * ease(typed))
    shown = CMD[:n]
    cursor_on = int(t * 8) % 2 == 0 or typed < 1
    prompt = "$ " + shown + ("█" if cursor_on and typed < 1.05 else "")
    d.text((96, 210), prompt, font=font(MONO_B, 24), fill=SAFFRON if typed < 1 else INK)

    appear = (t - 2.05)
    q_a = ease((appear - 0.0) / 0.35)
    p_a = ease((appear - 0.55) / 0.35)
    u_a = ease((appear - 1.25) / 0.35)
    r_a = ease((appear - 1.95) / 0.35)

    if q_a > 0:
        im = glow_box(im, (96, 270, W - 96, 372), SAFFRON, int(40 * q_a))
        d = ImageDraw.Draw(im)
        node(
            d,
            (96, 270),
            W - 192,
            102,
            "query  ·  invoice",
            "packed 6/512   skipped 0",
            accent=SAFFRON,
            alpha=q_a,
            tag="BAG",
        )
        if p_a > 0:
            stem(d, W // 2, 372, 412, alpha=p_a)

    if p_a > 0:
        im = glow_box(im, (96, 412, W - 96, 514), GREEN, int(28 * p_a))
        d = ImageDraw.Draw(im)
        node(
            d,
            (96, 412),
            W - 192,
            102,
            "packed  ·  256d hash",
            "vendor invoice 4000 USD",
            accent=GREEN,
            alpha=p_a,
            tag="IN THE PROMPT",
            meta="vec 0.51   keyword 1.00   recency 1.00",
        )
        if u_a > 0:
            stem(d, W // 2, 514, 554, alpha=u_a)

    if u_a > 0:
        d = ImageDraw.Draw(im)
        node(
            d,
            (96, 554),
            W - 192,
            102,
            "didn't rank",
            "zebra pancakes with maple",
            accent=DIM,
            alpha=u_a,
            tag="STILL IN FILE",
        )
        if r_a > 0:
            stem(d, W // 2, 656, 696, alpha=r_a)

    if r_a > 0:
        im = glow_box(im, (96, 696, W - 96, 798), RED, int(36 * r_a))
        d = ImageDraw.Draw(im)
        node(
            d,
            (96, 696),
            W - 192,
            102,
            "refused  ·  secret_or_pii",
            "[refused:password]",
            accent=RED,
            alpha=r_a,
            tag="DOOR",
        )

    caption = "one actor. never Priya's notes."
    if r_a > 0.8:
        caption = "the bag, the miss, the door  ·  forget is a receipt"
    elif u_a > 0.8:
        caption = "exists in the notebook  ·  did not make this query"
    elif p_a > 0.8:
        caption = "this is what the model actually saw"
    elif q_a > 0.8:
        caption = "nikaalo packs a 512-token bag  ·  and says so"
    footer(d, caption)

    # scanline sheen
    sheen = Image.new("RGB", (W, H), BG)
    sd = ImageDraw.Draw(sheen)
    y = int((math.sin(t * 1.4) * 0.5 + 0.5) * (H - 200)) + 100
    sd.rectangle((0, y, W, y + 3), fill=(40, 38, 34))
    im = Image.blend(im, sheen, 0.08)
    return im


def render() -> None:
    FRAMES.mkdir(parents=True, exist_ok=True)
    duration = 7.8
    n = int(duration * FPS)
    paths = []
    for i in range(n):
        t = i / FPS
        p = FRAMES / f"frame_{i:04d}.png"
        frame(t).save(p, "PNG")
        paths.append(p)

    palette = FRAMES / "palette.png"
    subprocess.run(
        [
            "ffmpeg", "-y", "-framerate", str(FPS),
            "-i", str(FRAMES / "frame_%04d.png"),
            "-vf", "palettegen=stats_mode=diff",
            str(palette),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "ffmpeg", "-y", "-framerate", str(FPS),
            "-i", str(FRAMES / "frame_%04d.png"),
            "-i", str(palette),
            "-lavfi", "paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle",
            "-loop", "0",
            str(GIF),
        ],
        check=True,
        capture_output=True,
    )
    # LinkedIn-safe silent MP4 fallback (same pictures).
    subprocess.run(
        [
            "ffmpeg", "-y", "-framerate", str(FPS),
            "-i", str(FRAMES / "frame_%04d.png"),
            "-f", "lavfi", "-i", "sine=frequency=20:sample_rate=44100",
            "-map", "0:v:0", "-map", "1:a:0",
            "-vf", "fps=30,format=yuv420p,scale=1080:1080,setsar=1",
            "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-preset", "medium", "-crf", "18", "-r", "30", "-g", "60", "-bf", "0",
            "-fps_mode", "cfr",
            "-af", "volume=-70dB", "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
            "-t", str(duration),
            "-movflags", "+faststart",
            str(MP4),
        ],
        check=True,
        capture_output=True,
    )
    print(GIF, GIF.stat().st_size)
    print(MP4, MP4.stat().st_size)


if __name__ == "__main__":
    render()
