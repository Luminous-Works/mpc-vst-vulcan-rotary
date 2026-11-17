#!/usr/bin/env python3
"""make_skin.py - give Vulcan Rotary its hand-tuned MPC skin (pizzazz).

The generated screen (tools/gen_ui.py from ui.json) is plain. This script copies it to skins/ and adds two things:
  * bg.png      the decal as a faint background on every page (1280 x 628, the tab size).
  * rotor_dial  the RATE control becomes the rotor itself: a 90 x 90 film strip (127 frames) where six barrels turn
                three full turns across the 120 .. 7,200 rpm range, an amber arc fills to the value, and the glow rises
                with rpm. One barrel carries a bright marker so the spin reads at a glance.
It is a TOUCHSCREEN skin: nothing here is animated by the plugin (the MPC UI format has no meter / animation channel and
a plugin pushing parameter values from the audio thread would flood project automation); the barrel turns because YOU turn
the dial. Real-time animation is a deliberate non-goal until it can be tested on a device.

TUI.json is patched as TEXT because the file contains duplicate "version" keys (docs/ui-reference.md 1.8) that
Python's json module would destroy.

Pipeline (run from the SDK root; <P> = this project folder):
    1. delete <P>/skins                       (so build.py runs the generator)
    2. python tools/build.py "<P>"
    3. python "<P>/tools/make_skin.py" "<P>"  (writes <P>/skins)
    4. python tools/build.py "<P>"            (now copies skins/ verbatim)
If ui.json changes, repeat from step 1.
"""
import math
import os
import re
import shutil
import sys

from PIL import Image, ImageDraw, ImageFilter

FRAMES, FS = 127, 90          # film-strip frames, frame size
AMBER = (255, 176, 32)
SS = 4                        # supersampling


def rotor_frame(norm):
    w = FS * SS
    c = w / 2
    img = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    # glow behind the rotor, brighter as rpm rises
    glow = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((c - 34 * SS, c - 34 * SS, c + 34 * SS, c + 34 * SS), fill=AMBER + (int(30 + 150 * norm),))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(7 * SS)))
    d = ImageDraw.Draw(img)
    bb = (c - 42 * SS, c - 42 * SS, c + 42 * SS, c + 42 * SS)
    d.arc(bb, 135, 405, fill=(60, 60, 64, 255), width=int(5 * SS))                  # value track
    if norm > 0.003:
        d.arc(bb, 135, 135 + 270 * norm, fill=AMBER + (255,), width=int(5 * SS))     # value arc
    d.ellipse((c - 33 * SS, c - 33 * SS, c + 33 * SS, c + 33 * SS), fill=(14, 14, 14, 255), outline=AMBER + (255,), width=int(2 * SS))
    a = norm * 1080.0                                                                # three turns across the range
    for k in range(6):
        ang = math.radians(a + 60 * k - 90)
        bx, by = c + 20 * SS * math.cos(ang), c + 20 * SS * math.sin(ang)
        d.ellipse((bx - 8 * SS, by - 8 * SS, bx + 8 * SS, by + 8 * SS), fill=(18, 18, 18, 255), outline=AMBER + (255,), width=int(1.6 * SS))
        d.ellipse((bx - 4.6 * SS, by - 4.6 * SS, bx + 4.6 * SS, by + 4.6 * SS), fill=(0, 0, 0, 255))
        if k == 0:                                                                   # marker barrel
            d.ellipse((bx - 2.4 * SS, by - 2.4 * SS, bx + 2.4 * SS, by + 2.4 * SS), fill=(255, 235, 170, 255))
    hub = [(c + 7 * SS * math.cos(math.radians(a + 60 * k)), c + 7 * SS * math.sin(math.radians(a + 60 * k))) for k in range(6)]
    d.polygon(hub, fill=(22, 22, 22, 255), outline=AMBER + (255,))
    d.ellipse((c - 2.2 * SS, c - 2.2 * SS, c + 2.2 * SS, c + 2.2 * SS), fill=AMBER + (255,))
    return img.resize((FS, FS), Image.LANCZOS)


def make_background(project):
    bg = Image.new("RGBA", (1280, 628), (10, 10, 10, 255))
    decal = Image.open(os.path.join(project, "tools", "decal.png")).convert("RGBA")
    size = 560
    decal = decal.resize((size, size), Image.LANCZOS)
    a = decal.split()[3].point(lambda v: int(v * 0.07))          # 7 % so the controls stay legible
    decal.putalpha(a)
    bg.alpha_composite(decal, (640 - size // 2, 314 - size // 2))
    return bg


def match_brace(t, start):
    """Index just past the '}' matching the '{' at t[start]."""
    depth = 0
    for i in range(start, len(t)):
        ch = t[i]
        if ch == '{': depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0: return i + 1
    raise ValueError("unbalanced braces")


def main():
    project = os.path.abspath(sys.argv[1])
    build = os.path.join(project, "build")
    src = None
    for d in os.listdir(build):
        cand = os.path.join(build, d, "Plugin Skins")
        if os.path.isdir(cand): src = cand
    if not src: sys.exit("no generated Plugin Skins under build/ - run tools/build.py first (with skins/ removed)")
    out = os.path.join(project, "skins")
    if os.path.isdir(out): shutil.rmtree(out)
    shutil.copytree(src, out)
    # drop the decal SVG that build.py copied in from assets/ (the skin folder only needs images the TUI uses)
    for f in os.listdir(out):
        if f.lower().endswith(".svg"): os.remove(os.path.join(out, f))

    strip = Image.new("RGBA", (FS, FS * FRAMES), (0, 0, 0, 0))
    for f in range(FRAMES):
        strip.paste(rotor_frame(f / (FRAMES - 1)), (0, f * FS))
    strip.save(os.path.join(out, "rotor_dial.png"), optimize=True)
    make_background(project).convert("RGB").save(os.path.join(out, "bg.png"), optimize=True)

    p = os.path.join(out, "TUI.json")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import skin_fix as sf
    root = sf.load(p)
    n_bg = sf.add_background(root, "bg.png")
    n_dial = sf.clone_knob_def(root, "knobRotor", "rotor_dial.png", "Rate")
    n_menu = sf.fix_menus(root)                                   # empty native pick-lists -> ValueSlider value fields
    made = sf.make_translucent_segments(out, (255, 176, 32))            # captions must not sit on top of buttons
    n_img, n_move = sf.fix_segments(root)
    sf.save(root, p)
    print("skin written to", out, "| backgrounds:", n_bg, "| Rate dial:", n_dial, "| menus -> value fields:", n_menu,
          "| segment images:", len(made), "| captions moved under buttons:", n_move)


if __name__ == "__main__":
    main()
