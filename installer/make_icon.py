"""
Generate installer/icon.ico for PC Checker Extreme.
Run once: .venv\Scripts\python.exe installer\make_icon.py
Requires Pillow (already in requirements.txt).
"""
import math
import os
from PIL import Image, ImageDraw, ImageFont

SIZES = [256, 128, 64, 48, 32, 16]
OUT = os.path.join(os.path.dirname(__file__), "icon.ico")

BG      = (15,  30,  60)   # deep navy
ACCENT  = (0,  180, 160)   # teal
WHITE   = (255, 255, 255)
TICK    = (60,  220, 140)   # green-teal tick


def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    pad = max(1, size // 16)
    r   = size // 6  # corner radius

    # Rounded-rect background
    d.rounded_rectangle([pad, pad, size - pad - 1, size - pad - 1],
                        radius=r, fill=BG)

    # Monitor outline (upper 60% of the icon)
    mw = int(size * 0.62)
    mh = int(size * 0.44)
    mx = (size - mw) // 2
    my = int(size * 0.10)
    border = max(1, size // 32)
    screen_inset = border * 2
    screen_r = max(1, r // 2)

    d.rounded_rectangle([mx, my, mx + mw, my + mh],
                        radius=screen_r, fill=ACCENT)
    d.rounded_rectangle([mx + screen_inset, my + screen_inset,
                         mx + mw - screen_inset, my + mh - screen_inset],
                        radius=max(1, screen_r - 1), fill=BG)

    # Stand neck + base
    neck_w = max(2, size // 12)
    neck_h = max(2, size // 10)
    nx = (size - neck_w) // 2
    ny = my + mh
    d.rectangle([nx, ny, nx + neck_w, ny + neck_h], fill=ACCENT)

    base_w = int(size * 0.40)
    base_h = max(2, size // 20)
    bx = (size - base_w) // 2
    by = ny + neck_h
    d.rounded_rectangle([bx, by, bx + base_w, by + base_h],
                        radius=max(1, base_h // 2), fill=ACCENT)

    # Tick mark drawn inside the screen area
    if size >= 24:
        sx0 = mx + screen_inset + 1
        sy0 = my + screen_inset + 1
        sx1 = mx + mw - screen_inset - 1
        sy1 = my + mh - screen_inset - 1
        sw  = sx1 - sx0
        sh  = sy1 - sy0

        # Three points of the tick: start, mid, end
        tx0 = int(sx0 + sw * 0.15)
        ty0 = int(sy0 + sh * 0.52)
        tx1 = int(sx0 + sw * 0.42)
        ty1 = int(sy0 + sh * 0.78)
        tx2 = int(sx0 + sw * 0.85)
        ty2 = int(sy0 + sh * 0.22)

        lw = max(1, size // 20)
        d.line([(tx0, ty0), (tx1, ty1), (tx2, ty2)],
               fill=TICK, width=lw, joint="curve")

    return img


def main():
    images = [draw_icon(s) for s in SIZES]
    images[0].save(OUT, format="ICO", sizes=[(s, s) for s in SIZES],
                   append_images=images[1:])
    print(f"Written: {OUT}  ({os.path.getsize(OUT):,} bytes)")


if __name__ == "__main__":
    main()
