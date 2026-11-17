#!/usr/bin/env python3
"""skin_fix.py - structural edits to a generated TUI.json, shared by make_skin.py of Vulcan Rotary and F4 Phantom.

TUI.json holds duplicate "version" keys inside the overlay widgets, so it is read into an ordered-pairs list (Obj) and written
back with a copy of the SDK's own dump_json (tools/gen_ui.py): the result is byte-compatible with what gen_ui writes.

What it fixes, from the device notes in open-mpc/mpc-vst-plugins docs/SDK-PORTING.md section 4 (measured on a Live III and a
Key 37, MPC OS 3.10.1):
  1. "Choice pick-lists: the native MenuOverlay opens EMPTY for an external VST2." The generator's `slider` + menu control
     is replaced by a `choiceValue` component: the parameter's name over a Knob of type ValueSlider, which shows the choice
     text and steps through the choices when dragged vertically or turned with a Q-Link / the data wheel. No pop-up list.
  2. "Labels on top of Buttons swallow taps." The captions of segmented switches are moved BELOW their buttons in paint
     order, and the buttons use translucent images (segtN_*.png, a faint tint with a border, lit = accent) so the caption
     shows through. A fully transparent picture has no touch area; these have a visible fill, so they do.
Also helpers to set the tab background image and to clone the unipolar knob around a different film strip.
"""
import copy
import json
import os
import re

from PIL import Image, ImageDraw


class Obj(list):
    """A JSON object as an ordered list of (key, value) pairs. Keys may repeat."""


def dump_json(value, indent=0):
    pad, inner = " " * indent, " " * (indent + 4)
    if isinstance(value, Obj):
        if not value: return "{}"
        return "{\n" + ",\n".join(inner + json.dumps(str(k)) + ": " + dump_json(v, indent + 4) for k, v in value) + "\n" + pad + "}"
    if isinstance(value, dict): return dump_json(Obj(value.items()), indent)
    if isinstance(value, (list, tuple)):
        if not value: return "[]"
        return "[\n" + ",\n".join(inner + dump_json(v, indent + 4) for v in value) + "\n" + pad + "]"
    if isinstance(value, bool): return "true" if value else "false"
    if value is None: return "null"
    if isinstance(value, int): return str(value)
    if isinstance(value, float): return repr(value)
    return json.dumps(value, ensure_ascii=False)


def load(path):
    return json.loads(open(path, encoding="utf-8").read(), object_pairs_hook=Obj)


def save(root, path):
    open(path, "w", encoding="utf-8", newline="\n").write(dump_json(root) + "\n")


def get(o, key, default=None):
    for k, v in o:
        if k == key: return v
    return default


def put(o, key, val):
    for i, (k, _) in enumerate(o):
        if k == key:
            o[i] = (key, val); return
    o.append((key, val))


def defs(root):
    return get(get(get(root, "pageData"), "componentDefinitions"), "localComponentDefinitions")


def find_def(root, key):
    for e in defs(root):
        if get(e, "key") == key: return get(e, "value")
    return None


def tabs(root):
    return get(get(root, "pageData"), "tabs")


def tab_children(tab):
    return get(get(tab, "componentDefinition"), "componentsData")


def comp_name(c): return get(get(c, "componentData"), "name")
def comp_type(c): return get(get(c, "componentData"), "type")


def set_type(c, t): put(get(c, "componentData"), "type", t)


# ------------------------------------------------------------------ background image on every tab
def add_background(root, image):
    n = 0
    for tab in tabs(root):
        bg = get(get(tab, "componentDefinition"), "backgroundData")
        for side in ("focussed", "unfocussed"):
            put(get(bg, side), "image", image); n += 1
    return n // 2


# ------------------------------------------------------------------ a hero dial: knobUni with another film strip
def clone_knob_def(root, new_key, new_strip, control_name):
    src = find_def(root, "knobUni")
    new = copy.deepcopy(src)
    for c in get(new, "componentsData"):
        d = get(get(c, "componentData"), "data")
        if get(d, "knobType") == "FilmStrip": put(d, "filmStrip", new_strip)
    defs(root).append(Obj([("key", new_key), ("value", new)]))
    n = 0
    for tab in tabs(root):
        for c in tab_children(tab):
            if comp_name(c) == control_name and comp_type(c) == "knobUni":
                set_type(c, new_key); n += 1
    return n


# ------------------------------------------------------------------ 1. menus -> ValueSlider value fields
def fix_menus(root, accent_argb="ffffb020"):
    src = find_def(root, "sliderWithFocusMenu")
    if src is None: return 0
    new = copy.deepcopy(src)
    # drop the "Show Overlay" (empty pick-list) actions; keep the Q-Link on touch
    acts = get(new, "actions")
    keep = [a for a in acts if get(a, "handler") != "Show Overlay"]
    put(new, "actions", keep)
    comps = get(new, "componentsData")
    focus = [c for c in comps if comp_type(c) == "Focus"][0]
    # name label: cloned from the unipolar knob's name label
    knob = find_def(root, "knobUni")
    name_lbl = copy.deepcopy([c for c in get(knob, "componentsData") if comp_name(c) == "name"][0])
    put(get(name_lbl, "bounds"), "bounds", "15 12 248 34")
    ts = get(get(get(name_lbl, "componentData"), "data"), "textStyle")
    put(ts, "justification", "left")
    value = Obj([
        ("version", 2),
        ("componentData", Obj([("version", 1), ("name", "value"), ("type", "Knob"), ("data", Obj([
            ("version", 4), ("knobType", "ValueSlider"),
            ("textStyle", Obj([("version", 1), ("font", Obj([("version", 1), ("name", "Titillium Web"), ("style", "Regular"), ("height", 30.0)])),
                               ("colour", "ffc8c8c8"), ("justification", "left verticallyCentred"), ("case", "Original")])),
            ("dragOrientation", "Vertical"), ("handleName", "Data")]))])),
        ("handle remapping", Obj([("version", 1), ("map", [])])),
        ("bounds", Obj([("version", 1), ("acceptsHWFocus", "No"), ("showWhenDataModelInvalid", "Show"), ("whenVisible", "Always"),
                        ("boundsType", "Absolute"), ("bounds", "15 48 248 46")])),
    ])
    put(new, "componentsData", [focus, name_lbl, value])
    defs(root).append(Obj([("key", "choiceValue"), ("value", new)]))
    n = 0
    for tab in tabs(root):
        for c in tab_children(tab):
            if comp_type(c) == "sliderWithFocusMenu":
                set_type(c, "choiceValue"); n += 1
    return n


# ------------------------------------------------------------------ 2. captions under translucent segment buttons
def make_translucent_segments(skins_dir, accent_rgb):
    made = []
    for f in sorted(os.listdir(skins_dir)):
        m = re.fullmatch(r"seg(\d)_(on|off)\.png", f)
        if not m: continue
        w, h = Image.open(os.path.join(skins_dir, f)).size
        S = 4
        im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        if m.group(2) == "on":
            d.rounded_rectangle((S, S, w * S - S, h * S - S), radius=7 * S, fill=accent_rgb + (95,), outline=accent_rgb + (255,), width=2 * S)
        else:
            d.rounded_rectangle((S, S, w * S - S, h * S - S), radius=7 * S, fill=(255, 255, 255, 16), outline=(110, 110, 118, 255), width=2 * S)
        out = "segt%s_%s.png" % (m.group(1), m.group(2))
        im.resize((w, h), Image.LANCZOS).save(os.path.join(skins_dir, out))
        made.append(out)
    return made


def fix_segments(root):
    """Use the translucent images and paint every 'seg k' caption before (below) the controls."""
    n_img = 0
    for e in defs(root):
        value = get(e, "value")
        for c in get(value, "componentsData"):
            d = get(get(c, "componentData"), "data")
            if get(d, "onImage") and re.fullmatch(r"seg\d_on\.png", get(d, "onImage")):
                put(d, "onImage", get(d, "onImage").replace("seg", "segt", 1))
                put(d, "offImage", get(d, "offImage").replace("seg", "segt", 1)); n_img += 1
    n_move = 0
    for tab in tabs(root):
        ch = tab_children(tab)
        caps = [c for c in ch if comp_type(c) == "Label" and re.search(r" seg \d+$", comp_name(c) or "")]
        rest = [c for c in ch if c not in caps]
        put(get(tab, "componentDefinition"), "componentsData", caps + rest)
        n_move += len(caps)
    return n_img, n_move
