#!/usr/bin/env python3
"""Draw the Projector Monitor app icon and save as icon.png (1024×1024)."""

import math
from PIL import Image, ImageDraw

SIZE  = 1024
BG    = (26,  92,  15, 255)   # #1a5c0f — dark green background
GREEN = (57, 255,  20, 255)   # #39ff14 — phosphor green
DARK  = (11,  30,   8, 255)   # very dark green for recesses

img  = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# ── Rounded background square ─────────────────────────────────────────
draw.rounded_rectangle([0, 0, SIZE, SIZE], radius=200, fill=BG)

# ── Projector body ────────────────────────────────────────────────────
draw.rounded_rectangle([75, 355, 950, 705], radius=85, fill=GREEN)

# ── Lens ─────────────────────────────────────────────────────────────
lx, ly = 290, 530   # lens centre

for r, col in [(158, DARK), (132, GREEN), (78, DARK), (34, GREEN)]:
    draw.ellipse([lx - r, ly - r, lx + r, ly + r], fill=col)

# ── Light rays (5, fanning upward) ───────────────────────────────────
def ray(angle_deg: float, r0: float, r1: float, w: int) -> None:
    a = math.radians(angle_deg)
    x1, y1 = lx + r0 * math.cos(a), ly + r0 * math.sin(a)
    x2, y2 = lx + r1 * math.cos(a), ly + r1 * math.sin(a)
    draw.line([x1, y1, x2, y2], fill=GREEN, width=w)
    hw = w // 2
    for px, py in [(x1, y1), (x2, y2)]:
        draw.ellipse([px - hw, py - hw, px + hw, py + hw], fill=GREEN)

for angle in [-148, -118, -90, -58, -32]:
    ray(angle, 178, 345, 50)

# ── Ventilation slots ─────────────────────────────────────────────────
for vy in [448, 530, 612]:
    draw.rounded_rectangle([628, vy - 20, 888, vy + 20], radius=20, fill=DARK)

# ── Indicator light ───────────────────────────────────────────────────
draw.ellipse([112, 455, 156, 499], fill=DARK)

# ── Feet ─────────────────────────────────────────────────────────────
for fx in [215, 680]:
    draw.ellipse([fx, 693, fx + 155, 768], fill=GREEN)

img.save("icon.png")
print("Saved icon.png")
