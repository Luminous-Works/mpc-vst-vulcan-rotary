#!/usr/bin/env python3
"""make_es_fader.py - render the Lumina ELECTRON TUBE SLIDER as MPC film strips.

Writes fader_h_uni.png and fader_h_bi.png (248 x 36 per frame, 127 frames stacked vertically) into ../assets/.
build.py copies assets/ over the stock kit after gen_ui runs, so these replace the plain faders on the MPC screen.

Look follows components/ElectronSlider/ElectronTubeSlider.tsx: dark glass tube, filament fill that brightens toward
the leading edge, soft glow at the head, electron specks, cathode / anode end caps. MPC changes (it is a TOUCHSCREEN):
the tube fills the whole 36 px frame and a bright plasma bead rides the head as a large grab handle; the component's
whole 248 x 36 area takes the horizontal drag.

Usage: python tools/make_es_fader.py [--accent 00F2FF]
"""
import argparse
import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter

W, H, FRAMES, S = 248, 36, 127, 4          # frame size, frames, supersampling
PAD = 17                                   # bead travel margin (bead radius + tube end)


def hex_rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def render_frame(norm, bipolar, acc):
    cr, cg, cb = acc
    w, h = W * S, H * S
    tx, ty, tw, th = 2 * S, 3 * S, w - 4 * S, h - 6 * S          # tube
    rad = th // 2
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # tube body + rim
    d.rounded_rectangle((tx, ty, tx + tw, ty + th), radius=rad, fill=(10, 12, 16, 235), outline=(cr, cg, cb, 60), width=S)
    # glass: vertical sheen
    glass = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glass)
    for y in range(ty, ty + th):
        t = (y - ty) / th
        a = int(255 * (0.10 * (1 - abs(t - 0.5) * 2) + 0.04))
        gd.line((tx + rad // 2, y, tx + tw - rad // 2, y), fill=(255, 255, 255, a // 4) if 0.35 < t < 0.65 else (cr, cg, cb, a // 3))
    img.alpha_composite(glass)

    head = (PAD + norm * (W - 2 * PAD)) * S
    c0 = (W / 2) * S if bipolar else (PAD) * S
    x0, x1 = (min(c0, head), max(c0, head))
    filled = (x1 - x0) > 1.5 * S

    if filled:
        # filament: gradient that brightens toward the leading (head) end
        fill = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        fd = ImageDraw.Draw(fill)
        inset = 2 * S
        span = max(1, int(x1 - x0))
        for i in range(span):
            u = i / span
            u = u if head >= c0 else 1 - u            # 1.0 at the head end
            a = 0.04 + 0.30 * (u ** 1.6) + 0.20 * (u ** 6)
            fd.line((x0 + i, ty + inset, x0 + i, ty + th - inset), fill=(cr, cg, cb, int(255 * min(0.9, a))))
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle((x0, ty + inset, x1, ty + th - inset), radius=max(2, rad - inset), fill=255)
        fill.putalpha(Image.composite(fill.split()[3], Image.new("L", (w, h), 0), mask))
        img.alpha_composite(fill)
        d.rounded_rectangle((x0, ty + inset, x1, ty + th - inset), radius=max(2, rad - inset), outline=(cr, cg, cb, 110), width=max(1, S // 2))

        # electron specks: fixed layout (seeded) so frames do not shimmer as the value moves
        rnd = random.Random(7)
        sp = Image.new("RGBA", (w, h), (0, 0, 0, 0)); sd = ImageDraw.Draw(sp)
        for k in range(0, int(W / 12) + 1):
            px = PAD * S + rnd.random() * (w - 2 * PAD * S)
            if x0 < px < x1:
                py = ty + th * (0.30 + 0.4 * rnd.random())
                r = (0.7 + rnd.random() * 0.9) * S
                sd.ellipse((px - 2.5 * r, py - 2.5 * r, px + 2.5 * r, py + 2.5 * r), fill=(cr, cg, cb, 40))
                sd.ellipse((px - r, py - r, px + r, py + r), fill=(min(255, cr + 90), min(255, cg + 90), min(255, cb + 90), 230))
        img.alpha_composite(sp)

    # cathode / anode end caps
    cp = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d0 = d; d = ImageDraw.Draw(cp)
    for i in range(8 * S):
        a = int(255 * 0.14 * (1 - i / (8 * S)))
        d.line((tx + rad // 2 + i, ty + 2 * S, tx + rad // 2 + i, ty + th - 2 * S), fill=(cr, cg, cb, a))
        d.line((tx + tw - rad // 2 - i, ty + 2 * S, tx + tw - rad // 2 - i, ty + th - 2 * S), fill=(cr, cg, cb, a // 2))
    if bipolar:                                           # centre detent tick
        d.line((w // 2, ty + 3 * S, w // 2, ty + th - 3 * S), fill=(200, 200, 200, 90), width=S // 2 + 1)
    img.alpha_composite(cp); d = d0

    # head glow + the bead (touch handle)
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gdr = ImageDraw.Draw(glow)
    cy = h / 2
    gdr.ellipse((head - 22 * S, cy - 17 * S, head + 22 * S, cy + 17 * S), fill=(cr, cg, cb, 150))
    glow = glow.filter(ImageFilter.GaussianBlur(7 * S))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((tx, ty, tx + tw, ty + th), radius=rad, fill=255)
    glow.putalpha(Image.composite(glow.split()[3], Image.new("L", (w, h), 0), mask))
    img.alpha_composite(glow)

    br = 11 * S                                            # bead radius: 22 px across in a 36 px tube
    halo = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse((head - br - 2 * S, cy - br - 2 * S, head + br + 2 * S, cy + br + 2 * S), fill=(cr, cg, cb, 70))
    img.alpha_composite(halo)
    d = ImageDraw.Draw(img)
    d.ellipse((head - br, cy - br, head + br, cy + br), fill=(14, 18, 24, 255), outline=(cr, cg, cb, 255), width=int(1.6 * S))
    core = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(core).ellipse((head - 6 * S, cy - 6 * S, head + 6 * S, cy + 6 * S), fill=(min(255, cr + 120), min(255, cg + 120), min(255, cb + 120), 255))
    core = core.filter(ImageFilter.GaussianBlur(2.2 * S))
    img.alpha_composite(core)
    d = ImageDraw.Draw(img)
    hl = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(hl).arc((head - br + 2 * S, cy - br + 2 * S, head + br - 2 * S, cy + br - 2 * S), 200, 290, fill=(255, 255, 255, 130), width=S)   # glass highlight
    img.alpha_composite(hl)

    return img.resize((W, H), Image.LANCZOS)


def build(bipolar, acc, path):
    strip = Image.new("RGBA", (W, H * FRAMES), (0, 0, 0, 0))
    for f in range(FRAMES):
        strip.paste(render_frame(f / (FRAMES - 1), bipolar, acc), (0, f * H))
    strip.save(path, optimize=True)
    print("wrote", path, strip.size)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--accent", default="00F2FF")
    a = ap.parse_args()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
    acc = hex_rgb(a.accent)
    build(False, acc, os.path.join(out, "fader_h_uni.png"))
    build(True, acc, os.path.join(out, "fader_h_bi.png"))
