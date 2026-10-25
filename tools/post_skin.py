#!/usr/bin/env python3
"""Turn the generated skin into the PhyXXL panel.

    python3 tools/post_skin.py "<skin dir>/Plugin Skins" [--preview build/preview]

gen_vst.py builds a working skin from layout.conf (every page a when=pg_<view>:1 panel). This script, in the built skin:
  - paints the vortex background and one panel picture per page (titles, section frames, control names, scales);
  - redraws the knob filmstrips from the knob art (static dot ring that lights up to the value, rotating body), the
    sliders, switches, option tiles, buttons, pop-up lists and lamps;
  - draws the overview: each tile's border is the art's tile frame, its inside the page in miniature, composed from the skin;
  - draws the two patch bays (hex sockets, one transparent cable picture per input / output pair, switched by the
    engine's cable parameters, IndexedEnabling), the jack rings and dimmed sockets, the matrix cells and chips,
    the response picture (VADER-style columns of strokes and dots) and the sequencer lamps.
Everything injected goes right after the background, so every control stays on top and keeps its touches.
"""
import json
import math
import os
import re
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spec  # noqa: E402

W, H = 1280, 628
FONT = os.path.join(ROOT, "art", "fonts", "TitilliumWeb-SemiBold.ttf")
SRC = os.path.join(ROOT, "art", "src")
PANEL = (18, 18, 18)
HEADER = (8, 8, 8)
LINE = (122, 122, 122)     # the mock's line grey
INK = (238, 238, 238)
DIM = (184, 184, 184)
YELLOW = (240, 240, 240)       # the lit colour (kept under the name the shared helpers use): plain white, as the overview mock
LED_OFF = (60, 60, 60)
SS = 2   # supersampling for drawn art
TAB = "PhyXXL|PhyXXL"
KNOB_SPAN = 150   # degrees each side of 12 o'clock


def font(size):
    return ImageFont.truetype(FONT, int(size))


def art(name):
    return Image.open(os.path.join(SRC, name)).convert("RGBA")


# ------------------------------------------------------------------------------------------------ the skin's data
def load_param_keys():
    keys = []
    for line in open(os.path.join(ROOT, "build", "params.h")):
        m = re.match(r'\s*\{"([^"]+)",', line)
        if m:
            keys.append(m.group(1))
    return keys


class Skin:
    def __init__(self, folder):
        self.dir = folder
        self.path = os.path.join(folder, "TUI.json")
        self.tui = json.load(open(self.path))
        self.defs_list = self.tui["pageData"]["componentDefinitions"]["localComponentDefinitions"]
        self.defs = {d["key"]: d["value"] for d in self.defs_list}
        self.page = self.defs[TAB]
        self.keys = load_param_keys()
        self.index = {k: i for i, k in enumerate(self.keys)}
        self.params = {p["key"]: p for p in json.load(open(os.path.join(ROOT, "params.json")))["params"]}

    def param_of(self, inst):
        for m in inst["handle remapping"]["map"]:
            if m["key"] == "Data" and m["value"].startswith("Parameter "):
                return self.keys[int(m["value"].split()[1])]
        return None

    def instances(self, key):
        return [c for c in self.page["componentsData"] if self.param_of(c) == key]

    def save(self):
        with open(self.path, "w") as f:
            json.dump(self.tui, f, separators=(",", ":"))


def bounds(b):
    return [int(round(float(x))) for x in b.split()]


def bstr(x, y, w, h):
    return "%d %d %d %d" % (x, y, w, h)


def image_instance(name, img, x, y, w, h, handles):
    return {"version": 2,
            "componentData": {"version": 1, "name": name, "type": "Image",
                              "data": {"version": 2, "imageType": "Regular", "colour": "0", "image": img}},
            "handle remapping": {"version": 1, "map": []},
            "bounds": {"version": 2, "acceptsHWFocus": "No", "showWhenDataModelInvalid": "Show", "whenVisible": "Always",
                       "boundsType": "Absolute", "bounds": bstr(x, y, w, h),
                       "additionalInvalidatingHandles": handles}}


# ------------------------------------------------------------------------------------------------ art primitives


def switch_image(on, w=84, h=40):
    """an MS-20-style toggle: a dark rocker, the lit side yellow"""
    S = 4
    im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w * S - 1, h * S - 1], radius=5 * S, fill=(12, 12, 12, 255), outline=(150, 150, 150, 255),
                        width=S)
    kw = int(w * S * 0.48)
    x0 = w * S - kw - 3 * S if on else 3 * S
    col = YELLOW if on else (90, 90, 90)
    d.rounded_rectangle([x0, 3 * S, x0 + kw, h * S - 3 * S], radius=3 * S, fill=col + (255,))
    return im.resize((w, h), Image.LANCZOS)


def push_button_image(on, w, h, lamp=True):
    """the sequencer's square buttons (TRIGGER / PORTAMENTO C): black cap, a lamp that lights yellow"""
    S = 4
    im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w * S - 1, h * S - 1], radius=4 * S, fill=(14, 14, 14, 255), outline=(130, 130, 130, 255),
                        width=S)
    d.rounded_rectangle([3 * S, 3 * S, w * S - 4 * S, h * S - 4 * S], radius=3 * S, fill=(34, 34, 34, 255))
    if lamp:
        r = 6 * S
        cx, cy = w * S / 2.0, h * S / 2.0
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(YELLOW if on else LED_OFF) + (255,))
        if on:
            d.ellipse([cx - r * 2, cy - r * 2, cx + r * 2, cy + r * 2], outline=YELLOW + (70,), width=3 * S)
    return im.resize((w, h), Image.LANCZOS)


def nav_image(label, on, w, h):
    """a mock button: a dark rounded cap with the grey line; pressed it lightens"""
    S = 4
    im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w * S - 1, h * S - 1], radius=8 * S, fill=((84, 84, 84) if on else (22, 22, 22)) + (255,),
                        outline=LINE + (255,), width=2 * S)
    size = 28 if label in ("<", ">") else 24
    while size > 16 and d.textlength(label, font=font(size * S)) > (w - 16) * S:
        size -= 1
    d.text((w * S / 2, h * S / 2), label, font=font(size * S), fill=INK + (255,), anchor="mm")
    return im.resize((w, h), Image.LANCZOS)


def blank(w, h):
    return Image.new("RGBA", (w, h), (0, 0, 0, 0))


def tile_highlight(w, h):
    """shown only while the tile is pressed: a soft lift inside the art's own frame"""
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle([3, 3, w - 4, h - 4], radius=16, fill=(255, 255, 255, 34))
    return im


def ring_image(r=34, wdt=5):
    S = 4
    im = Image.new("RGBA", (2 * r * S, 2 * r * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([S, S, 2 * r * S - S, 2 * r * S - S], outline=YELLOW + (255,), width=wdt * S)
    return im.resize((2 * r, 2 * r), Image.LANCZOS)


def led_image(on, r=11, colour=(255, 60, 50)):
    S = 4
    im = Image.new("RGBA", (2 * r * S, 2 * r * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([0, 0, 2 * r * S - 1, 2 * r * S - 1], fill=(20, 20, 20, 255))
    col = colour + (255,) if on else tuple(int(c * 0.3) for c in colour) + (255,)
    d.ellipse([3 * S, 3 * S, 2 * r * S - 3 * S, 2 * r * S - 3 * S], fill=col)
    if on:
        d.ellipse([6 * S, 6 * S, 11 * S, 11 * S], fill=(255, 245, 220, 255))
    return im.resize((2 * r, 2 * r), Image.LANCZOS)


# the waveform glyphs on the option tiles

def seg_image(label, on, w, h):
    """an option tile of a rotary-switch group: black, white text; the chosen one yellow with black text"""
    S = 3
    im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([S, S, w * S - S - 1, h * S - S - 1], radius=5 * S, fill=(YELLOW if on else (16, 16, 16)) + (255,),
                        outline=(150, 150, 150, 255), width=S)
    ink = (17, 17, 17) if on else INK
    txt = SHORT.get(label, label).upper()
    if label in GLYPHS:
        gw = min(38 * S, int(w * S * 0.36))
        glyph(d, GLYPHS[label], 8 * S, int(h * S * 0.3), gw, int(h * S * 0.4), ink, S)
        size = 18
        while size > 15 and d.textlength(txt, font=font(size * S)) > (w - 56) * S:
            size -= 1
        d.text(((8 + gw / S + (w - 8 - gw / S) / 2.0) * S, h * S / 2.0), txt, font=font(size * S), fill=ink, anchor="mm")
    else:
        size = 19
        while size > 15 and d.textlength(txt, font=font(size * S)) > (w - 12) * S:
            size -= 1
        d.text((w * S / 2.0, h * S / 2.0), txt, font=font(size * S), fill=ink, anchor="mm")
    return im.resize((w, h), Image.LANCZOS)


def write_segments(skin, folder):
    for key, d in skin.defs.items():
        m = re.match(r"shSeg_(.+)_(\d+)$", key)
        if not m or m.group(1) not in skin.params:
            continue
        label = skin.params[m.group(1)]["options"][int(m.group(2))]
        for sub in d["componentsData"]:
            if sub["componentData"]["type"] != "Button":
                continue
            _, _, w, h = bounds(sub["bounds"]["bounds"])
            data = sub["componentData"]["data"]
            seg_image(label, True, w, h).save(os.path.join(folder, data["onImage"]))
            seg_image(label, False, w, h).save(os.path.join(folder, data["offImage"]))


# ------------------------------------------------------------------------------------------------ pop-up lists
POP_ARROW_W = 70     # the arrow box on a pop-up field's right end: tap it to open / close the list
POP_TEXT = 24


def pop_arrow_image(open_, w, h):
    S = 4
    im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w * S - 1, h * S - 1], radius=6 * S, fill=YELLOW + (255,) if open_ else (18, 18, 18, 255),
                        outline=(130, 130, 130, 255), width=2 * S)
    d.rectangle([0, 2 * S, 6 * S, h * S - 2 * S], fill=YELLOW + (255,) if open_ else (18, 18, 18, 255))
    d.line([0, 4 * S, 0, h * S - 4 * S], fill=(130, 130, 130, 255), width=2 * S)
    cx, cy, a = w * S / 2.0, h * S / 2.0, 11 * S
    ink = (17, 17, 17, 255) if open_ else YELLOW + (255,)
    if open_:
        d.polygon([(cx - a, cy + a * 0.55), (cx + a, cy + a * 0.55), (cx, cy - a * 0.65)], fill=ink)
    else:
        d.polygon([(cx - a, cy - a * 0.55), (cx + a, cy - a * 0.55), (cx, cy + a * 0.65)], fill=ink)
    return im.resize((w, h), Image.LANCZOS)


def pop_option_image(label, on, w, h):
    S = 2
    im = Image.new("RGBA", (w * S, h * S), YELLOW + (255,) if on else (16, 16, 16, 255))
    d = ImageDraw.Draw(im)
    size = POP_TEXT
    while size > 16 and d.textlength(label, font=font(size * S)) > (w - 16) * S:
        size -= 1
    d.text((w * S / 2.0, h * S / 2.0), label, font=font(size * S), fill=(17, 17, 17) if on else INK, anchor="mm")
    if not on:
        d.line([8 * S, h * S - 1, w * S - 8 * S, h * S - 1], fill=(48, 48, 48), width=S)
    return im.resize((w, h), Image.LANCZOS)


def fix_popups(skin, folder):
    """The framework's pop-up fields, rebuilt as in PS3100XXL 0.1.3: the list's open flag is the engine's pop_<key>,
    the field itself is a Q-Link focus on the value, the arrow box on its right opens and closes the list, and the
    options are redrawn in the panel's font at a readable size."""
    comps = skin.page["componentsData"]
    tog = next(v for k, v in skin.defs.items() if k.startswith("shToggle"))
    pops = [c for c in spec.CONTROLS if c["kind"] == "enum" and c["widget"] == "popup"]
    remap = {"Parameter %d" % skin.index[c["key"] + "__open"]: "Parameter %d" % skin.index["pop_" + c["key"]] for c in pops}
    remap_ie = {}
    for old, new in remap.items():
        remap_ie["IndexedEnabling/1/2/" + old] = "IndexedEnabling/1/2/" + new
    out = []
    for inst in comps:
        t = inst["componentData"]["type"]
        hs = inst["bounds"].get("additionalInvalidatingHandles", [])
        inst["bounds"]["additionalInvalidatingHandles"] = [remap_ie.get(h, h) for h in hs]
        for m in inst["handle remapping"]["map"]:
            if m["key"] == "Data" and m["value"] in remap and not t.startswith("shPopField"):
                m["value"] = remap[m["value"]]
        out.append(inst)
        if not t.startswith("shPopField"):
            continue
        mp = {m["key"]: m["value"] for m in inst["handle remapping"]["map"]}
        pop = remap[mp["Data"]]
        x, y, w, h = bounds(inst["bounds"]["bounds"])
        fkey = "msPopField_%dx%d" % (w, h)
        if fkey not in skin.defs:
            d = json.loads(json.dumps(skin.defs[t]))
            d["actions"] = [a for a in d["actions"] if a["onAction"] == "Mouse Down"]
            d["actions"][0]["handler"] = "Q-Link"
            for sub in d["componentsData"]:
                if sub["componentData"]["type"] == "Label":
                    sub["bounds"]["bounds"] = bstr(8, 0, w - POP_ARROW_W - 12, h)
            skin.defs_list.append({"key": fkey, "value": d})
            skin.defs[fkey] = d
        inst["componentData"]["type"] = fkey
        inst["handle remapping"]["map"] = [{"key": "Data", "value": mp["Text"]}, {"key": "Text", "value": mp["Text"]}]
        akey = "msPopArrow_%dx%d" % (POP_ARROW_W, h)
        if akey not in skin.defs:
            d = json.loads(json.dumps(tog))
            d["actions"] = [a for a in d["actions"] if a["onAction"] == "Mouse Down"]
            assert d["actions"] and d["actions"][0]["handler"] == "Q-Link", "switch template changed"
            for sub in d["componentsData"]:
                sub["bounds"]["bounds"] = bstr(0, 0, POP_ARROW_W, h)
                if sub["componentData"]["type"] == "Button":
                    sub["componentData"]["data"]["offImage"] = "ms_pop_arrow_%d_off.png" % h
                    sub["componentData"]["data"]["onImage"] = "ms_pop_arrow_%d_on.png" % h
            pop_arrow_image(False, POP_ARROW_W, h).save(os.path.join(folder, "ms_pop_arrow_%d_off.png" % h))
            pop_arrow_image(True, POP_ARROW_W, h).save(os.path.join(folder, "ms_pop_arrow_%d_on.png" % h))
            skin.defs_list.append({"key": akey, "value": d})
            skin.defs[akey] = d
        arrow = json.loads(json.dumps(inst))
        arrow["componentData"]["type"] = akey
        arrow["componentData"]["name"] = inst["componentData"]["name"] + " list"
        arrow["handle remapping"]["map"] = [{"key": "Data", "value": pop}]
        arrow["bounds"]["bounds"] = bstr(x + w - POP_ARROW_W, y, POP_ARROW_W, h)
        arrow["bounds"]["acceptsHWFocus"] = "No"
        out.append(arrow)
    comps[:] = out
    done = set()
    for key, d in skin.defs.items():
        m = re.match(r"shPopOpt_\d+_(.+)_(\d+)$", key)
        if not m:
            continue
        label = skin.params[m.group(1)]["options"][int(m.group(2))]
        for sub in d["componentsData"]:
            if sub["componentData"]["type"] != "Button":
                continue
            _, _, w, h = bounds(sub["bounds"]["bounds"])
            data = sub["componentData"]["data"]
            for name, on in ((data["onImage"], True), (data["offImage"], False)):
                if name not in done:
                    done.add(name)
                    pop_option_image(label, on, w, h).save(os.path.join(folder, name))
    left = [i for i in comps if any(m["value"] in remap for m in i["handle remapping"]["map"]) or
            any(h.split("/")[-1] in remap for h in i["bounds"].get("additionalInvalidatingHandles", []))]
    assert not left, "pop-up parts still on <key>__open: %r" % [i["componentData"]["name"] for i in left]


# ------------------------------------------------------------------------------------------------ panels

def cable_points(p1, p2, n=48, floor=1e9):
    (x1, y1), (x2, y2) = p1, p2
    dist = math.hypot(x2 - x1, y2 - y1)
    sag = 26 + 0.2 * dist
    bow = 0.0
    if abs(x2 - x1) < 0.35 * abs(y2 - y1):
        bow = (0.18 * abs(y2 - y1) + 20) * (1 if x1 < W / 2 else -1)
    low = min(max(y1, y2) + sag, floor)
    c1 = (x1 + (x2 - x1) * 0.2 + bow, low)
    c2 = (x2 - (x2 - x1) * 0.2 + bow, low)
    pts = []
    for i in range(n + 1):
        t = i / float(n)
        a, b, c, e = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3
        pts.append((a * x1 + b * c1[0] + c * c2[0] + e * x2, a * y1 + b * c1[1] + c * c2[1] + e * y2))
    return pts


def draw_cable(p1, p2, colour, scale=1.0, clip=(0, 0, W, H)):
    """-> (image, x, y) of the cable from p1 to p2 (page coordinates), cropped to what it covers."""
    width, outline, plug = 6.5 * scale, 10 * scale, 11 * scale
    pts = cable_points(p1, p2, floor=clip[3] + (clip[3] - max(p1[1], p2[1])) * 0.33 - 4 * outline)
    m = outline + plug + 2
    x0 = max(clip[0], int(math.floor(min(p[0] for p in pts) - m)))
    y0 = max(clip[1], int(math.floor(min(p[1] for p in pts) - m)))
    x1 = min(clip[2], int(math.ceil(max(p[0] for p in pts) + m)))
    y1 = min(clip[3], int(math.ceil(max(p[1] for p in pts) + m)))
    S = 3
    im = Image.new("RGBA", ((x1 - x0) * S, (y1 - y0) * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    sp = [((x - x0) * S, (y - y0) * S) for x, y in pts]
    dark = tuple(int(v * 0.45) for v in colour)
    d.line(sp, fill=dark + (235,), width=max(1, int(outline * S)), joint="curve")
    d.line(sp, fill=colour + (240,), width=max(1, int(width * S)), joint="curve")
    hl = tuple(min(255, int(v * 1.25) + 30) for v in colour)
    d.line([(x, y - width * S * 0.22) for x, y in sp], fill=hl + (150,), width=max(1, int(width * S * 0.25)))
    for (x, y) in (sp[0], sp[-1]):   # the plugs: black MS-20 plugs with a yellow boot
        r = plug * S
        d.ellipse([x - r, y - r, x + r, y + r], fill=(20, 20, 20, 255))
        d.ellipse([x - r * 0.72, y - r * 0.72, x + r * 0.72, y + r * 0.72], fill=colour + (255,))
        d.ellipse([x - r * 0.35, y - r * 0.55, x + r * 0.1, y - r * 0.1], fill=hl + (200,))
    im = im.resize((x1 - x0, y1 - y0), Image.LANCZOS)
    return im, x0, y0


def tile_pieces(im, x0, y0, T):
    a = im.split()[3]
    out = []
    for gy in range((y0 // T) * T, y0 + im.size[1], T):
        for gx in range((x0 // T) * T, x0 + im.size[0], T):
            bx0, by0 = max(gx, x0) - x0, max(gy, y0) - y0
            bx1, by1 = min(gx + T, x0 + im.size[0]) - x0, min(gy + T, y0 + im.size[1]) - y0
            if bx1 <= bx0 or by1 <= by0:
                continue
            bb = a.crop((bx0, by0, bx1, by1)).getbbox()
            if not bb:
                continue
            l, t, r, b = bx0 + bb[0], by0 + bb[1], bx0 + bb[2], by0 + bb[3]
            out.append((im.crop((l, t, r, b)), x0 + l, y0 + t))
    return out


# ------------------------------------------------------------------------------------------------ compositing
class Composer:
    """Draws the page as MPC would for a given state (param key -> value index or 0..1), from the skin itself."""

    def __init__(self, skin):
        self.skin = skin
        self.cache = {}

    def img(self, name):
        if name not in self.cache:
            self.cache[name] = Image.open(os.path.join(self.skin.dir, name)).convert("RGBA")
        return self.cache[name]

    def shown(self, inst, state):
        for h in inst["bounds"]["additionalInvalidatingHandles"]:
            m = re.match(r"IndexedEnabling/(\d+)/(\d+)/Parameter (\d+)", h)
            if m and state.get(self.skin.keys[int(m.group(3))], 0) != int(m.group(1)):
                return False
        return True

    def norm(self, key, state):
        p = self.skin.params.get(key)
        if p is None:
            return 0.0
        v = state[key] if key in state else p.get("default", 0)
        if "options" in p:
            n = len(p["options"])
            return v / float(n - 1) if n > 1 else 0.0
        lo, hi = p.get("min", 0), p.get("max", 1)
        return (v - lo) / (hi - lo) if hi > lo else 0.0

    def value(self, key, state):
        p = self.skin.params.get(key)
        if key in state:
            return state[key]
        return p.get("default", 0) if p else 0

    def compose(self, state, skip_images=()):
        page = Image.new("RGBA", (W, H), PANEL + (255,))
        for inst in self.skin.page["componentsData"]:
            if not self.shown(inst, state):
                continue
            x, y, w, h = bounds(inst["bounds"]["bounds"])
            t = inst["componentData"]["type"]
            if t == "Image":
                name = inst["componentData"]["data"]["image"]
                if name and not any(name.startswith(s) for s in skip_images):
                    page.alpha_composite(self.img(name).resize((w, h)) if self.img(name).size != (w, h)
                                         else self.img(name), (x, y))
                continue
            d = self.skin.defs.get(t)
            if not d:
                continue
            key = self.skin.param_of(inst)
            for sub in d["componentsData"]:
                st = sub["componentData"]["type"]
                sx, sy, sw, sh = bounds(sub["bounds"]["bounds"])
                data = sub["componentData"].get("data", {})
                if st == "Knob" and data.get("filmStrip"):
                    strip = self.img(data["filmStrip"])
                    F = strip.size[0]
                    fr = int(round(self.norm(key, state) * 127))
                    page.alpha_composite(strip.crop((0, fr * F, F, fr * F + F)).resize((sw, sh)), (x + sx, y + sy))
                elif st == "Button":
                    if sub["bounds"].get("whenVisible") == "WhenFocussed":
                        continue
                    n = data.get("numButtonsInGroup", 1)
                    v = self.value(key, state)
                    on = (int(round(v)) == data.get("buttonId", 0)) if n > 1 else bool(round(v)) and not \
                        (self.skin.params.get(key, {}).get("momentary"))
                    name = data.get("onImage") if on else data.get("offImage")
                    if name:
                        im = self.img(name)
                        page.alpha_composite(im.resize((sw, sh)) if im.size != (sw, sh) else im, (x + sx, y + sy))
                elif st == "Image" and data.get("image"):
                    page.alpha_composite(self.img(data["image"]).resize((sw, sh)), (x + sx, y + sy))
        return page



# ================================================================================================ PhyXXL's own art
GLYPHS = {}
SHORT = {}
FILTER_COLOUR = {}          # filled from the tile sheet order


def cover(im, w, h):
    s = max(w / float(im.size[0]), h / float(im.size[1]))
    im = im.resize((int(math.ceil(im.size[0] * s)), int(math.ceil(im.size[1] * s))), Image.LANCZOS)
    x, y = (im.size[0] - w) // 2, (im.size[1] - h) // 2
    return im.crop((x, y, x + w, y + h))


def background():
    """the flat panel colour with the vortex laid over it by its luminosity (neutral, no tint)"""
    lum = cover(art("bg_vortex.png"), W, H).convert("L")
    lum = lum.point(lambda v: int(18 + v * 0.40))
    return Image.merge("RGB", (lum, lum, lum))


def tile_borders():
    """the 14 tile frames of the art sheet, cut out by their grid cell and trimmed to their outline"""
    sheet = art("tiles_sheet.png")
    cw, ch = sheet.size[0] / 4.0, sheet.size[1] / 4.0
    out = []
    for i in range(14):
        c, r = i % 4, i // 4
        cell = sheet.crop((int(c * cw), int(r * ch), int((c + 1) * cw), int((r + 1) * ch)))
        bb = cell.split()[3].getbbox()
        out.append(cell.crop(bb))
    return out


def nine_slice(im, w, h, k=22):
    """a frame picture resized to w x h with its corners kept"""
    iw, ih = im.size
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    xs = [(0, k, 0, k), (k, w - k, k, iw - k), (w - k, w, iw - k, iw)]
    ys = [(0, k, 0, k), (k, h - k, k, ih - k), (h - k, h, ih - k, ih)]
    for dx0, dx1, sx0, sx1 in xs:
        for dy0, dy1, sy0, sy1 in ys:
            piece = im.crop((sx0, sy0, sx1, sy1)).resize((dx1 - dx0, dy1 - dy0), Image.LANCZOS)
            out.alpha_composite(piece, (dx0, dy0))
    return out


def knob_art():
    """the body (a round crop of the art's knob) and where its dot ring sits"""
    k = art("knob_one.png")
    cx, cy, r = 97, 143, 77
    body = k.crop((cx - r, cy - r, cx + r, cy + r))
    m = Image.new("L", body.size, 0)
    ImageDraw.Draw(m).ellipse([0, 0, body.size[0] - 1, body.size[1] - 1], fill=255)
    body.putalpha(Image.composite(body.split()[3], Image.new("L", body.size, 0), m))
    return body, 92.0, 7.0   # body, ring radius, dot radius (art pixels)


def write_knob_strips(skin):
    """128 frames per radius: the dot ring (lit up to the value) around the body, which turns -150..+150 degrees
    (the framework's rule: numFrames 127, frames <= 126 px)"""
    body, ring_r, dot_r = knob_art()
    done = []
    for name in sorted(os.listdir(skin.dir)):
        m = re.match(r"sh_knob_r(\d+)\.png$", name)
        if not m:
            continue
        R = int(m.group(1))
        F = 2 * R + 10
        S = 3
        scale = F * S / (2.0 * (ring_r + dot_r + 2))
        b = body.resize((int(body.size[0] * scale), int(body.size[1] * scale)), Image.LANCZOS)
        strip = Image.new("RGBA", (F, F * 128), (0, 0, 0, 0))
        for i in range(128):
            ang = -KNOB_SPAN + 2 * KNOB_SPAN * i / 127.0
            fr = Image.new("RGBA", (F * S, F * S), (0, 0, 0, 0))
            d = ImageDraw.Draw(fr)
            for k in range(11):
                a = -150 + 30 * k
                x = F * S / 2.0 + math.sin(math.radians(a)) * ring_r * scale
                y = F * S / 2.0 - math.cos(math.radians(a)) * ring_r * scale
                rr = dot_r * scale
                lit = a <= ang + 0.5
                if lit:
                    d.ellipse([x - rr * 2.2, y - rr * 2.2, x + rr * 2.2, y + rr * 2.2], fill=(255, 255, 255, 28))
                    d.ellipse([x - rr * 1.6, y - rr * 1.6, x + rr * 1.6, y + rr * 1.6], fill=(255, 255, 255, 55))
                d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=(236, 236, 236, 255) if lit else (88, 90, 94, 255),
                          outline=(20, 20, 20, 255), width=max(1, S // 2))
            rot = b.rotate(-ang, resample=Image.BICUBIC)
            fr.alpha_composite(rot, ((F * S - rot.size[0]) // 2, (F * S - rot.size[1]) // 2))
            strip.paste(fr.resize((F, F), Image.LANCZOS), (0, i * F))
        assert strip.size[1] <= 16128
        strip.save(os.path.join(skin.dir, name), optimize=True)
        done.append(R)
    return done


def slider_strip(w, h, frames, vertical):
    """a groove with the accent filled up to the thumb"""
    S = 3
    strip = Image.new("RGBA", (w, h * frames), (0, 0, 0, 0))
    for i in range(frames):
        t = i / float(frames - 1)
        fr = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
        d = ImageDraw.Draw(fr)
        if vertical:
            gx = w * S / 2.0
            top, bot = 12 * S, h * S - 12 * S
            d.rounded_rectangle([gx - 5 * S, top, gx + 5 * S, bot], radius=5 * S, fill=(8, 8, 8, 255), outline=(122, 122, 122, 255), width=S)
            ty = bot - (bot - top) * t
            if bot - S - ty > 1:
                d.rounded_rectangle([gx - 3 * S, ty, gx + 3 * S, bot - S], radius=min(3 * S, (bot - S - ty) / 2), fill=YELLOW + (230,))
            d.rounded_rectangle([gx - 17 * S, ty - 9 * S, gx + 17 * S, ty + 9 * S], radius=5 * S, fill=(44, 44, 44, 255), outline=(200, 200, 200, 255), width=S)
            d.line([gx - 11 * S, ty, gx + 11 * S, ty], fill=YELLOW + (255,), width=2 * S)
        else:
            gy = h * S / 2.0
            lft, rgt = 14 * S, w * S - 14 * S
            d.rounded_rectangle([lft, gy - 5 * S, rgt, gy + 5 * S], radius=5 * S, fill=(8, 8, 8, 255), outline=(122, 122, 122, 255), width=S)
            tx = lft + (rgt - lft) * t
            if tx - lft - S > 1:
                d.rounded_rectangle([lft + S, gy - 3 * S, tx, gy + 3 * S], radius=min(3 * S, (tx - lft - S) / 2), fill=YELLOW + (230,))
            d.rounded_rectangle([tx - 9 * S, gy - 13 * S, tx + 9 * S, gy + 13 * S], radius=5 * S, fill=(44, 44, 44, 255), outline=(200, 200, 200, 255), width=S)
            d.line([tx, gy - 9 * S, tx, gy + 9 * S], fill=YELLOW + (255,), width=2 * S)
        strip.paste(fr.resize((w, h), Image.LANCZOS), (0, i * h))
    return strip


def restyle_sliders(skin):
    for key, d in skin.defs.items():
        if not key.startswith("shSlider"):
            continue
        for sub in d["componentsData"]:
            if sub["componentData"]["type"] != "Knob":
                continue
            data = sub["componentData"]["data"]
            _, _, w, h = bounds(sub["bounds"]["bounds"])
            slider_strip(w, h, data["numFrames"], data["dragOrientation"] == "Vertical").save(
                os.path.join(skin.dir, data["filmStrip"]), optimize=True)


def ball_image(on, size=48):
    """a step button: the art's glass ball, tinted the accent when on"""
    b = art("step_btn.png")
    bb = b.split()[3].getbbox()
    b = b.crop(bb).resize((size, size), Image.LANCZOS)
    if on:
        tint = Image.new("RGBA", b.size, YELLOW + (255,))
        lit = Image.blend(b.convert("RGB"), tint.convert("RGB"), 0.55)
        lit = Image.eval(lit, lambda v: min(255, int(v * 1.25)))
        b2 = lit.convert("RGBA")
        b2.putalpha(b.split()[3])
        glow = Image.new("RGBA", (size + 16, size + 16), (0, 0, 0, 0))
        ImageDraw.Draw(glow).ellipse([2, 2, size + 13, size + 13], fill=YELLOW + (70,))
        glow = glow.filter(ImageFilter.GaussianBlur(4))
        glow.alpha_composite(b2, (8, 8))
        return glow.resize((size, size), Image.LANCZOS) if False else b2
    return b


def text(d, xy, s, size, fill=INK, anchor="mm"):
    d.text((xy[0] * SS, xy[1] * SS), s, font=font(size * SS), fill=fill, anchor=anchor)


def frame_box(d, x0, y0, x1, y1, label=None, fill=(8, 8, 8, 150), line=(90, 90, 90, 255), r=10, dashed=False):
    """the mock's box: near black, a grey line (dashed for the response display)"""
    d.rounded_rectangle([x0 * SS, y0 * SS, x1 * SS, y1 * SS], radius=r * SS, fill=fill)
    if dashed:
        dash_rect(d, x0, y0, x1, y1, line)
    else:
        d.rounded_rectangle([x0 * SS, y0 * SS, x1 * SS, y1 * SS], radius=r * SS, outline=line, width=2 * SS)
    if label:
        text(d, (x0 + 14, y0 + 16), label, 22, DIM, "lm")


def dash_rect(d, x0, y0, x1, y1, col, dash=9, gap=6):
    def hline(y, a, b):
        x = a
        while x < b:
            d.line([(x * SS, y * SS), (min(x + dash, b) * SS, y * SS)], fill=col, width=2 * SS)
            x += dash + gap

    def vline(x, a, b):
        y = a
        while y < b:
            d.line([(x * SS, y * SS), (x * SS, min(y + dash, b) * SS)], fill=col, width=2 * SS)
            y += dash + gap
    hline(y0, x0, x1)
    hline(y1, x0, x1)
    vline(x0, y0, y1)
    vline(x1, y0, y1)


# ------------------------------------------------------------------------------------------------ panels
def short_label(c):
    n = c["name"]
    if re.match(r"(st|fg|gt)_", c["key"]) and re.search(r"\d+$", n):
        return re.search(r"\d+$", n).group(0)
    return n.upper()


def is_ball(c):
    return c["kind"] == "toggle" and re.match(r"gt_[el]\d+$", c["key"]) is not None


def new_layer():
    im = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


TITLES = {"out": "DRIVE + OUTPUT", "moda": "MOD SOURCES A", "mstep": "MOD B1  STEP SEQUENCER", "mfunc": "MOD B2  FUNCTION GENERATOR",
          "mgate": "MOD B3  GATE SEQ + RANDOM", "matrix": "MOD MATRIX", "bayM": "PATCH BAY  MODULATION", "bayA": "PATCH BAY  AUDIO"}


def header(d, title, sub=None):
    text(d, (640, 28), title, 34, INK)
    cx, cy, w = spec.HDR_TOUCH
    d.rounded_rectangle([(cx - w // 2) * SS, (cy - 22) * SS, (cx + w // 2) * SS, (cy + 22) * SS], radius=8 * SS,
                        fill=(22, 22, 22, 255), outline=LINE + (255,), width=2 * SS)


def control_labels(d, vkey):
    for c in spec.CONTROLS:
        if c["view"] != vkey or c["key"] == "data":
            continue
        x, y = c["cx"], c["cy"]
        if c["kind"] == "knob":
            text(d, (x, y + c["r"] + 26), short_label(c), 28, INK)
        elif c["kind"] in ("toggle", "enum") and not is_ball(c):
            text(d, (x, y + 82), short_label(c), 28, INK)


def curve_frame(d):
    x, y = spec.RC_XY
    w, h = spec.RC_COLS * spec.RC_CW, spec.RC_ROWS * spec.RC_RH
    bx, by, bw, bh = spec.RESP_BOX
    frame_box(d, bx, by, bx + bw, by + bh, None, dashed=True)
    text(d, (bx + 16, by + 16), "RESPONSE", 22, DIM, "lm")
    for hz, lab in ((20, "20"), (100, "100"), (1000, "1k"), (10000, "10k"), (20000, "20k")):
        xx = x + w * math.log(hz / 20.0) / math.log(1000.0)
        text(d, (min(max(xx, x + 12), x + w - 12), y + h + 22), lab, 22, DIM)


def view_panel(i, v):
    vkey = v[0]
    im, d = new_layer()
    header(d, spec.FLABEL.get(vkey) or TITLES.get(vkey, v[1]))
    if vkey in spec.FKEYS:
        curve_frame(d)
        x, y, w, h = spec.AUD_BAR
        frame_box(d, x, y, x + w, y + h)
        text(d, (29, y + h // 2), "AUDIO", 24, DIM, "lm")
        x, y, w, h = spec.MOD_BAR
        frame_box(d, x, y, x + w, y + h)
        text(d, (29, y + 18), "MOD ON THIS FILTER", 24, DIM, "lm")
    control_labels(d, vkey)
    if vkey == "moda":
        text(d, (16, 77), "LFO", 26, DIM, "lm")
        text(d, (spec.slot(4) - 85, 77), "ENVELOPE (AHD)", 26, DIM, "lm")
        text(d, (16, 287), "ENV FOLLOWER", 26, DIM, "lm")
        text(d, (1200, 155), "ACTIVE", 24, DIM, "lm")
    if vkey == "out":
        text(d, (16, 277), "QUICK AUDIO CHAIN", 26, DIM, "lm")
    if vkey == "mstep":
        frame_box(d, 16, 67, 1264, 294, None)
    if vkey == "mfunc":
        frame_box(d, 16, 67, 883, 358, None)
    if vkey == "mgate":
        text(d, (16, 265), "GATE SEQUENCER", 26, DIM, "lm")
        text(d, (spec.slot(4) - 85, 265), "RANDOM / S&H", 26, DIM, "lm")
        text(d, (20, spec.GATE_Y1), "ENV", 22, DIM, "lm")
        text(d, (20, spec.GATE_Y2), "LFO", 22, DIM, "lm")
    return im.resize((W, H), Image.LANCZOS)


def overview_panel(sk):
    """the overview of the mock: the art's tile frames (unchanged) with each tile's name; the live status line is the engine's ts_ readout"""
    im, d = new_layer()
    header(d, "OVERVIEW")
    borders = tile_borders()
    names = {k: spec.VIEWS[spec.VIEW_NO[k]][2] for k in spec.TILE_VIEWS}
    border_of = {k: borders[min(i, 13)] for i, k in enumerate(spec.TILE_VIEWS)}
    border_of["bayM"] = borders[6]
    out = im.resize((W, H), Image.LANCZOS)
    od = ImageDraw.Draw(out)
    for k in spec.TILE_VIEWS:
        tx, ty, tw, th = spec.TILES[k]
        out.alpha_composite(nine_slice(border_of[k], tw, th), (tx, ty))
        od.text((tx + 16, ty + 34), names[k], font=font(34), fill=INK, anchor="lm")
    dx, dy = spec.DATA_POS
    od.text((dx, dy + 64), "DATA", font=font(28), fill=INK, anchor="mm")
    sy = spec.STRIP_Y + 19
    od.text((16, sy), "IN", font=font(24), fill=DIM, anchor="lm")
    od.text((262, sy), "OUT", font=font(24), fill=DIM, anchor="lm")
    od.text((520, sy), "CPU", font=font(24), fill=DIM, anchor="lm")
    return out


# ------------------------------------------------------------------------------------------------ sockets, cables, bays
def hex_socket(d, x, y, r=spec.JACK_R, dim=False, accent=False):
    pts = lambda rad: [((x + rad * math.cos(math.radians(60 * k + 30))) * SS, (y + rad * math.sin(math.radians(60 * k + 30))) * SS)
                       for k in range(6)]
    d.polygon(pts(r), fill=(96, 96, 96) if dim else (170, 170, 170))
    d.polygon(pts(r - 3), outline=(60, 60, 60), width=SS)
    rr = r - 6
    d.ellipse([(x - rr) * SS, (y - rr) * SS, (x + rr) * SS, (y + rr) * SS], fill=(70, 70, 70) if dim else (130, 130, 130))
    d.ellipse([(x - 6) * SS, (y - 6) * SS, (x + 6) * SS, (y + 6) * SS], fill=(4, 4, 4))


def cable_for(index):
    return spec.CABLE_COLOURS[index % len(spec.CABLE_COLOURS)]


def bay_panel(kind):
    """kind 'M' or 'A': the sockets and their names, in the mock's boxes"""
    im, d = new_layer()
    header(d, "PATCH BAY  MODULATION" if kind == "M" else "PATCH BAY  AUDIO")
    if kind == "M":
        frame_box(d, 16, 110, 269, 558, "MOD OUT")
        frame_box(d, 287, 110, 1264, 558, "FILTER INPUTS")
        for i, s in enumerate(spec.SRCS):
            x, y = spec.mod_out_pos(i)
            hex_socket(d, x, y, spec.JACK_R)
            text(d, (27, y), s[1], 26, INK, "lm")
        for fi, f in enumerate(spec.FILTERS):
            x, _ = spec.mod_in_pos(fi, 0)
            text(d, (x, 146), spec.FSHORT[f[0]], 24, INK)
            for di, dk in enumerate(spec.DEST_KEYS):
                xx, yy = spec.mod_in_pos(fi, di)
                hex_socket(d, xx, yy, spec.JACK_R)
        for di in range(spec.N_DEST):
            text(d, (297, spec.mod_in_pos(0, di)[1]), spec.DESTS[di][1], 26, INK, "lm")
    else:
        frame_box(d, 16, 110, 416, 578, "AUDIO OUT")
        frame_box(d, 864, 110, 1264, 578, "AUDIO IN")
        for i, a in enumerate(spec.AUDIO_OUTS):
            x, y = spec.aud_out_pos(i)
            hex_socket(d, x, y, spec.JACK_R)
            text(d, (40, y), a[1], 28, INK, "lm")
        for i, b in enumerate(spec.AUDIO_INS):
            x, y = spec.aud_in_pos(i)
            hex_socket(d, x, y, spec.JACK_R)
            text(d, (x + 33, y), b[1], 28, INK, "lm")
    frame_box(d, 16, 581, 1264, 621)
    return im.resize((W, H), Image.LANCZOS)


def connected_panel(kind):
    im, d = new_layer()
    d.rectangle([0, 56 * SS, W * SS, H * SS], fill=(8, 8, 8, 240))
    text(d, (W // 2, 130), "CONNECTED", 44, INK)
    x1, x2, y = 300, W - 300, 300
    out = im.resize((W, H), Image.LANCZOS)
    cab, cx0, cy0 = draw_cable((x1, y), (x2, y), spec.CABLE_COLOURS[3], 2.2, clip=(0, 56, W, H))
    out.alpha_composite(cab, (cx0, cy0))
    big = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    bd = ImageDraw.Draw(big)
    for x, lab in ((x1, "SOURCE" if kind == "M" else "OUTPUT"), (x2, "INPUT")):
        hex_socket(bd, x, y, 40)
        text(bd, (x, y + 84), lab, 26, DIM)
    big = big.resize((W, H), Image.LANCZOS)
    out.alpha_composite(big)
    return out


def ring_img(r=26, w=5, colour=YELLOW):
    S = 4
    im = Image.new("RGBA", (2 * r * S + 8 * S, 2 * r * S + 8 * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([4 * S, 4 * S, (2 * r + 4) * S, (2 * r + 4) * S], outline=colour + (255,), width=w * S)
    return im.resize((2 * r + 8, 2 * r + 8), Image.LANCZOS)


def dim_img(r=20):
    S = 4
    im = Image.new("RGBA", (2 * r * S, 2 * r * S), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse([0, 0, 2 * r * S - 1, 2 * r * S - 1], fill=(8, 8, 8, 190))
    return im.resize((2 * r, 2 * r), Image.LANCZOS)


def chip_image(label, state):
    """a matrix filter chip: 0 plain, 1 pressed, 2 chosen"""
    w, h = spec.MX_CHIP
    S = 3
    im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    fill = {0: (22, 22, 22, 255), 1: (110, 110, 110, 255), 2: (238, 238, 238, 255)}[state]
    d.rounded_rectangle([S, S, w * S - S, h * S - S], radius=8 * S, fill=fill, outline=LINE + (255,), width=2 * S)
    d.text((w * S / 2, h * S / 2), label, font=font(26 * S), fill=(17, 17, 17) if state == 2 else INK, anchor="mm")
    return im.resize((w, h), Image.LANCZOS)


def matrix_panel():
    im, d = new_layer()
    header(d, "MOD MATRIX")
    x, y, w, h = spec.MX_BAR
    frame_box(d, x, y, x + w, y + h)
    cw, ch = spec.MX_CELL
    for di, dd in enumerate(spec.DESTS):
        x, _ = spec.mx_cell_pos(0, di)
        text(d, (x, 126), dd[1], 26, DIM)
    for si, s in enumerate(spec.SRCS):
        x, y = spec.mx_cell_pos(si, 0)
        text(d, (20, y), s[1], 26, DIM, "lm")
        for di in range(spec.N_DEST):
            cx, cy = spec.mx_cell_pos(si, di)
            d.rounded_rectangle([(cx - cw // 2) * SS, (cy - ch // 2) * SS, (cx + cw // 2) * SS, (cy + ch // 2) * SS],
                                radius=6 * SS, fill=(28, 28, 28, 255), outline=(74, 74, 74, 255), width=2 * SS)
    out = im.resize((W, H), Image.LANCZOS)
    for fi, f in enumerate(spec.FILTERS):
        cx, cy = spec.mx_chip_pos(fi)
        out.alpha_composite(chip_image(f[3], 0), (cx - spec.MX_CHIP[0] // 2, cy - spec.MX_CHIP[1] // 2))
    return out


def cell_image(state):
    w, h = spec.MX_CELL
    S = 4
    im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if state == 1:
        d.rounded_rectangle([S, S, w * S - S, h * S - S], radius=6 * S, fill=(70, 70, 70, 255), outline=(238, 238, 238, 255), width=2 * S)
        sym = "+"
    elif state == 2:
        d.rounded_rectangle([S, S, w * S - S, h * S - S], radius=6 * S, fill=(40, 40, 40, 255), outline=(160, 160, 160, 255), width=2 * S)
        sym = "-"
    else:
        d.rounded_rectangle([S, S, w * S - S, h * S - S], radius=6 * S, fill=(255, 255, 255, 40), outline=(255, 255, 255, 255), width=3 * S)
        sym = ""
    if sym:
        d.text((w * S / 2, h * S / 2), sym, font=font(28 * S), fill=(255, 255, 255, 255), anchor="mm")
    return im.resize((w, h), Image.LANCZOS)


def led_bar(n, w=176, h=16):
    S = 3
    im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    seg = w / 8.0
    for k in range(8):
        col = YELLOW if k < n else (44, 44, 44)
        if k >= 6 and k < n:
            col = (255, 90, 80)
        d.rounded_rectangle([(k * seg + 2) * S, 0, ((k + 1) * seg - 2) * S, h * S - 1], radius=3 * S, fill=col + (255,))
    return im.resize((w, h), Image.LANCZOS)


# ------------------------------------------------------------------------------------------------ the response picture
def curve_strip():
    """RC_FRAMES frames of one column: dots stacked from row r0 to row r1 (src/engine.cc curve_calc, the pair index)"""
    CW, RH, N = spec.RC_CW, spec.RC_RH, spec.RC_ROWS
    S = 3
    strip = Image.new("RGBA", (CW, N * RH * spec.RC_FRAMES), (0, 0, 0, 0))
    k = 0
    for r0 in range(N):
        for r1 in range(r0, N):
            fr = Image.new("RGBA", (CW * S, N * RH * S), (0, 0, 0, 0))
            d = ImageDraw.Draw(fr)
            y0, y1 = r0 * RH + RH / 2.0, r1 * RH + RH / 2.0
            n = max(1, int(round((y1 - y0) / 3.5)) + 1)
            for j in range(n):
                y = y0 + (y1 - y0) * (j / float(n - 1) if n > 1 else 0)
                x = CW / 2.0
                rr = 2.4
                d.ellipse([(x - rr * 2) * S, (y - rr * 2) * S, (x + rr * 2) * S, (y + rr * 2) * S], fill=(255, 255, 255, 40))
                d.ellipse([(x - rr) * S, (y - rr) * S, (x + rr) * S, (y + rr) * S], fill=(235, 235, 235, 255))
            strip.paste(fr.resize((CW, N * RH), Image.LANCZOS), (0, k * N * RH))
            k += 1
    assert k == spec.RC_FRAMES
    return strip


def ruler_strip():
    """RC_COLS + 1 frames: the dot ruler above the picture, the cutoff's column lit"""
    w, h = spec.RC_COLS * spec.RC_CW, 12
    S = 3
    strip = Image.new("RGBA", (w, h * (spec.RC_COLS + 1)), (0, 0, 0, 0))
    for k in range(spec.RC_COLS + 1):
        fr = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
        d = ImageDraw.Draw(fr)
        for c in range(spec.RC_COLS):
            x, y = (c + 0.5) * spec.RC_CW, h / 2.0
            lit = (k == c + 1)
            rr = 4.0 if lit else 1.3
            col = (255, 255, 255, 255) if lit else (110, 110, 110, 255)
            if lit:
                d.ellipse([(x - 8) * S, (y - 8) * S, (x + 8) * S, (y + 8) * S], fill=(255, 255, 255, 60))
            d.ellipse([(x - rr) * S, (y - rr) * S, (x + rr) * S, (y + rr) * S], fill=col)
        strip.paste(fr.resize((w, h), Image.LANCZOS), (0, k * h))
    return strip


# ------------------------------------------------------------------------------------------------ read-only strips
def strip_instance(skin, fname, frames, w, h, param_key, x, y, handles, name):
    """a picture the engine moves: a filmstrip bound to a read-only parameter, with no touch"""
    dkey = "pxStrip_%s" % fname
    if dkey not in skin.defs:
        tmpl = next(v for k, v in skin.defs.items() if k.startswith("shSlider_v"))
        d = json.loads(json.dumps(tmpl))
        d["actions"] = []
        d["ignoreMousePresses"] = True
        knob = next(s for s in d["componentsData"] if s["componentData"]["type"] == "Knob")
        knob["componentData"]["data"]["filmStrip"] = fname
        knob["componentData"]["data"]["numFrames"] = frames
        knob["componentData"]["data"]["dragOrientation"] = "Vertical"
        knob["bounds"]["bounds"] = bstr(0, 0, w, h)
        d["componentsData"] = [knob]
        skin.defs_list.append({"key": dkey, "value": d})
        skin.defs[dkey] = d
    inst = json.loads(json.dumps(next(c for c in skin.page["componentsData"] if c["componentData"]["type"].startswith("shSlider_v"))))
    inst["componentData"]["type"] = dkey
    inst["componentData"]["name"] = name
    inst["handle remapping"]["map"] = [{"key": "Data", "value": "Parameter %d" % skin.index[param_key]}]
    inst["bounds"]["bounds"] = bstr(x, y, w, h)
    inst["bounds"]["additionalInvalidatingHandles"] = handles
    inst["bounds"]["acceptsHWFocus"] = "No"
    return inst


# ------------------------------------------------------------------------------------------------ buttons
def blank(w, h):
    return Image.new("RGBA", (w, h), (0, 0, 0, 0))


def push_label(key, defkey):
    m = re.match(r"shTrig_%s_(.*)$" % re.escape(key), defkey)
    lab = m.group(1) if m else ""
    return "" if lab == "x" else lab.replace("_", " ")


def rect_for(key):
    """where a framework button sits and how big it is (skin pixels), by what it does"""
    def around(x, y, w, h):
        return (int(x - w // 2), int(y - h // 2), int(w), int(h))
    if key in spec.NAV_SIZE:
        x, y = {k: (x, y) for k, _, x, y in spec.NAV}[key]
        return around(x, y, *spec.NAV_SIZE[key])
    for k, _, x, y, w in spec.CHIPS:
        if key == k:
            return around(x, y, w, 40)
    for k, _, x, y, w, h in spec.FILTER_BTNS:
        if key == k:
            return around(x, y, w, h)
    for c in spec.CONTROLS:
        if c["kind"] == "button" and c["key"] == key:
            return around(c["cx"], c["cy"], c["w"], c["h"])
    if key == "pk_cancel":
        return around(spec.PK_CANCEL[0], spec.PK_CANCEL[1], 160, 52)
    if key == "pk_done":
        return tuple(spec.PK_DONE)
    if key == "pk_unplug":
        return tuple(spec.PK_UNPLUG)
    for k, _, x, y in spec.MX_BTNS:
        if key == k:
            return around(x, y, *spec.MX_BTN)
    m = re.match(r"mxf_(\d+)$", key)
    if m:
        x, y = spec.mx_chip_pos(int(m.group(1)))
        return around(x, y, *spec.MX_CHIP)
    if key.startswith("go_") and key[3:] in spec.TILES:
        return tuple(spec.TILES[key[3:]])
    m = re.match(r"tm_(\w+)$", key)
    if m:
        x, y = spec.mod_out_pos(spec.SRC_KEYS.index(m.group(1)))
        return around(x, y, *spec.PICK_MOD_OUT)
    m = re.match(r"ti_(\w+?)_(cut|res|drv|mode|pan|out)$", key)
    if m:
        x, y = spec.mod_in_pos(spec.FKEYS.index(m.group(1)), spec.DEST_KEYS.index(m.group(2)))
        return around(x, y, *spec.PICK_MOD_IN)
    m = re.match(r"tao_(\d+)$", key)
    if m:
        return around(*(spec.aud_out_pos(int(m.group(1))) + tuple(spec.PICK_AUD)))
    m = re.match(r"tai_(\d+)$", key)
    if m:
        return around(*(spec.aud_in_pos(int(m.group(1))) + tuple(spec.PICK_AUD)))
    m = re.match(r"mx_(\w+?)_(cut|res|drv|mode|pan|out)$", key)
    if m and m.group(1) in spec.SRC_KEYS:
        x, y = spec.mx_cell_pos(spec.SRC_KEYS.index(m.group(1)), spec.DEST_KEYS.index(m.group(2)))
        return around(x, y, *spec.MX_CELL)
    return None


def restyle_triggers(skin, folder):
    """every framework button: the labelled ones as push buttons, the jacks, cells and tiles as transparent touch
    areas that show a ring or a tint while pressed"""
    done = set()
    for inst in list(skin.page["componentsData"]):
        t = inst["componentData"]["type"]
        if not t.startswith("shTrig_") or t in done:
            continue
        done.add(t)
        key = skin.param_of(inst)
        d = skin.defs[t]
        d["componentsData"] = [s for s in d["componentsData"] if s["componentData"]["type"] != "Label"]
        btn = next(s for s in d["componentsData"] if s["componentData"]["type"] == "Button")
        _, _, w, h = bounds(btn["bounds"]["bounds"])
        data = btn["componentData"]["data"]
        off_name, on_name = data["offImage"], data["onImage"]
        label = push_label(key, t)
        rect = rect_for(key)
        if rect:
            w, h = rect[2], rect[3]
            for s2 in d["componentsData"]:
                s2["bounds"]["bounds"] = bstr(0, 0, w, h)
        if key.startswith("nav_"):
            label = {k: l for k, l, _, _ in spec.NAV}[key]
        if key.startswith("nav_") or (key in ("go_bayM", "go_bayA") and label) or key.startswith("fm_") or key.startswith("chain_") \
                or key.startswith("pk_") or key in ("mx_done", "mx_unplug", "mx_cancel"):
            nav_image(label, False, w, h).save(os.path.join(folder, off_name))
            nav_image(label, True, w, h).save(os.path.join(folder, on_name))
        elif key.startswith("mxf_"):
            blank(w, h).save(os.path.join(folder, off_name))
            chip_image(spec.FILTERS[int(key.split("_")[1])][3], 1).resize((w, h), Image.LANCZOS).save(os.path.join(folder, on_name))
        elif key.startswith("go_") and not label:
            blank(w, h).save(os.path.join(folder, off_name))
            tile_highlight(w, h).save(os.path.join(folder, on_name))
        elif key.startswith("mx_"):
            blank(w, h).save(os.path.join(folder, off_name))
            tile_highlight(w, h).save(os.path.join(folder, on_name))
        else:   # tm_ ti_ tao_ tai_ jacks
            blank(w, h).save(os.path.join(folder, off_name))
            im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            r2 = ring_img(26, 4)
            im.alpha_composite(r2, ((w - r2.size[0]) // 2, (h - r2.size[1]) // 2))
            im.save(os.path.join(folder, on_name))
    for inst in skin.page["componentsData"]:
        if inst["componentData"]["type"].startswith("shTrig_"):
            rect = rect_for(skin.param_of(inst))
            if rect:
                inst["bounds"]["bounds"] = bstr(*rect)


# ------------------------------------------------------------------------------------------------ the page
class Composer:
    """Draws the page as MPC would for a given state (param key -> value), from the skin itself (previews and checks)."""

    def __init__(self, skin):
        self.skin = skin
        self.cache = {}

    def img(self, name):
        if name not in self.cache:
            self.cache[name] = Image.open(os.path.join(self.skin.dir, name)).convert("RGBA")
        return self.cache[name]

    def value(self, key, state):
        p = self.skin.params.get(key)
        if key in state:
            return state[key]
        return p.get("default", 0) if p else 0

    def shown(self, inst, state):
        for h in inst["bounds"]["additionalInvalidatingHandles"]:
            m = re.match(r"IndexedEnabling/(\d+)/(\d+)/Parameter (\d+)", h)
            if m and int(round(self.value(self.skin.keys[int(m.group(3))], state))) != int(m.group(1)):
                return False
        return True

    def norm(self, key, state):
        p = self.skin.params.get(key)
        if p is None:
            return 0.0
        v = self.value(key, state)
        if "options" in p:
            n = len(p["options"])
            return v / float(n - 1) if n > 1 else 0.0
        lo, hi = p.get("min", 0), p.get("max", 1)
        return (v - lo) / (hi - lo) if hi > lo else 0.0

    def compose(self, state):
        page = Image.new("RGBA", (W, H), PANEL + (255,))
        for inst in self.skin.page["componentsData"]:
            if not self.shown(inst, state):
                continue
            x, y, w, h = bounds(inst["bounds"]["bounds"])
            t = inst["componentData"]["type"]
            if t == "Image":
                name = inst["componentData"]["data"]["image"]
                if name:
                    im = self.img(name)
                    page.alpha_composite(im if im.size == (w, h) else im.resize((w, h)), (x, y))
                continue
            d = self.skin.defs.get(t)
            if not d:
                continue
            key = self.skin.param_of(inst)
            for sub in d["componentsData"]:
                st = sub["componentData"]["type"]
                sx, sy, sw, sh = bounds(sub["bounds"]["bounds"])
                data = sub["componentData"].get("data", {})
                if st == "Knob" and data.get("filmStrip"):
                    strip = self.img(data["filmStrip"])
                    nf = data.get("numFrames", 128)
                    fw, fh = strip.size[0], strip.size[1] // nf
                    fr = int(round(self.norm(key, state) * (nf - 1)))
                    if "pxStrip" in t:
                        fr = int(self.value(key, state))
                    page.alpha_composite(strip.crop((0, fr * fh, fw, fr * fh + fh)).resize((sw, sh)), (x + sx, y + sy))
                elif st == "Button":
                    if sub["bounds"].get("whenVisible") == "WhenFocussed":
                        continue
                    n = data.get("numButtonsInGroup", 1)
                    v = self.value(key, state)
                    on = (int(round(v)) == data.get("buttonId", 0)) if n > 1 else bool(round(v)) and not \
                        (self.skin.params.get(key, {}).get("momentary"))
                    name = data.get("onImage") if on else data.get("offImage")
                    if name:
                        im = self.img(name)
                        page.alpha_composite(im if im.size == (sw, sh) else im.resize((sw, sh)), (x + sx, y + sy))
                elif st == "Image" and data.get("image"):
                    page.alpha_composite(self.img(data["image"]).resize((sw, sh)), (x + sx, y + sy))
        return page


# ================================================================================================ main
def pg_handle(skin, vkey):
    return "IndexedEnabling/1/2/Parameter %d" % skin.index["pg_" + vkey]


def main():
    folder = sys.argv[1]
    preview = sys.argv[sys.argv.index("--preview") + 1] if "--preview" in sys.argv else None
    skin = Skin(folder)
    comps = skin.page["componentsData"]
    idx = skin.index

    # 1) the framework's mode backgrounds go; the vortex is the base
    comps[:] = [c for c in comps if not (c["componentData"]["type"] == "Image" and
                                         c["componentData"]["data"].get("image", "").startswith("sh_mode_"))]
    for name in os.listdir(folder):
        if name.startswith("sh_mode_"):
            os.remove(os.path.join(folder, name))
    background().save(os.path.join(folder, "sh_bg_0.png"))

    # 2) knobs, sliders, switches, option tiles, buttons, pop-up lists
    radii = write_knob_strips(skin)
    for key, d in skin.defs.items():   # the value under the knob
        if key.startswith("shKnob"):
            for sub in d["componentsData"]:
                x, y, w, h = bounds(sub["bounds"]["bounds"])
                if sub["componentData"]["type"] == "Label":
                    sub["bounds"]["bounds"] = bstr(x, y + 22, w, h)
                elif sub["componentData"]["type"] == "Focus":
                    sub["bounds"]["bounds"] = bstr(x, y, w, h + 22)
    for inst in comps:
        if inst["componentData"]["type"].startswith("shKnob"):
            x, y, w, h = bounds(inst["bounds"]["bounds"])
            inst["bounds"]["bounds"] = bstr(x, y, w, h + 22)
    restyle_sliders(skin)
    write_segments(skin, folder)
    switch_image(True).save(os.path.join(folder, "px_switch_on.png"))
    switch_image(False).save(os.path.join(folder, "px_switch_off.png"))
    ball_image(True).save(os.path.join(folder, "px_ball_on.png"))
    ball_image(False).save(os.path.join(folder, "px_ball_off.png"))
    for key, d in skin.defs.items():
        if key.startswith("shToggle"):
            d["componentsData"] = [s for s in d["componentsData"] if s["componentData"]["type"] != "Label"]
            narrow = "bw60" in key
            for s in d["componentsData"]:
                if s["componentData"]["type"] == "Focus":
                    s["bounds"]["bounds"] = bstr(0, 0, 60, 48) if narrow else bstr(0, 0, 130, 48)
                if s["componentData"]["type"] == "Button":
                    s["bounds"]["bounds"] = bstr(6, 0, 48, 48) if narrow else bstr(23, 4, 84, 40)
                    s["componentData"]["data"]["onImage"] = "px_ball_on.png" if narrow else "px_switch_on.png"
                    s["componentData"]["data"]["offImage"] = "px_ball_off.png" if narrow else "px_switch_off.png"
    for c in spec.CONTROLS:
        if c["kind"] == "toggle":
            for inst in skin.instances(c["key"]):
                if is_ball(c):
                    inst["bounds"]["bounds"] = bstr(c["cx"] - 30, c["cy"] - 24, 60, 48)
                elif c["key"] in ("limit_res", "bypass"):
                    inst["bounds"]["bounds"] = bstr(c["cx"] - 60, c["cy"] - 20, 120, 40)
                else:
                    inst["bounds"]["bounds"] = bstr(c["cx"] - 65, c["cy"] - 24, 130, 48)
    for key, label in (("limit_res", "Limit res."), ("bypass", "Bypass")):
        insts = skin.instances(key)
        base = insts[0]["componentData"]["type"]
        dk = "pxToggle_" + key
        d2 = json.loads(json.dumps(skin.defs[base]))
        for s2 in d2["componentsData"]:
            s2["bounds"]["bounds"] = bstr(0, 0, 120, 40)
            if s2["componentData"]["type"] == "Button":
                s2["componentData"]["data"]["onImage"] = "px_%s_on.png" % key
                s2["componentData"]["data"]["offImage"] = "px_%s_off.png" % key
        skin.defs_list.append({"key": dk, "value": d2})
        skin.defs[dk] = d2
        nav_image(label, True, 120, 40).save(os.path.join(folder, "px_%s_on.png" % key))
        nav_image(label, False, 120, 40).save(os.path.join(folder, "px_%s_off.png" % key))
        for inst in insts:
            inst["componentData"]["type"] = dk
    restyle_triggers(skin, folder)
    fix_popups(skin, folder)

    # 3) the pages: one panel picture per view, shown while its pg_<view> switch is on
    injected = []
    for i, v in enumerate(spec.VIEWS):
        if v[0] == "overview":
            im = overview_panel(skin)
        elif v[0] == "matrix":
            im = matrix_panel()
        elif v[0] == "bayM":
            im = bay_panel("M")
        elif v[0] == "bayA":
            im = bay_panel("A")
        else:
            im = view_panel(i, v)
        im.save(os.path.join(folder, "px_view_%d.png" % i), optimize=True)
        injected.append(image_instance("Panel", "px_view_%d.png" % i, 0, 0, W, H, [pg_handle(skin, v[0])]))
    # the connected page of each bay (step 4)
    for kind, vkey in (("M", "bayM"), ("A", "bayA")):
        connected_panel(kind).save(os.path.join(folder, "px_conn_%s.png" % kind), optimize=True)
        injected.append(image_instance("Panel", "px_conn_%s.png" % kind, 0, 0, W, H,
                                       [pg_handle(skin, vkey), "IndexedEnabling/4/%d/Parameter %d" % (len(spec.PK_STEPS), idx["pk"])]))

    # 4) cables
    cable_insts, pieces, total_px = [], 0, 0

    def add_cable(p1, p2, colour, handles, tag, scale):
        nonlocal pieces, total_px
        im, x0, y0 = draw_cable(p1, p2, colour, scale, clip=(0, 72, W, H))
        for k, (piece, px, py) in enumerate(tile_pieces(im, x0, y0, spec.CABLE_TILE)):
            name = "px_cab_%s_%d.png" % (tag, k)
            piece.save(os.path.join(folder, name), optimize=True)
            total_px += piece.size[0] * piece.size[1]
            pieces += 1
            cable_insts.append(image_instance("Cable", name, px, py, piece.size[0], piece.size[1], handles))

    half = spec.N_SRC // 2
    for s in range(spec.N_SRC):
        for fi, f in enumerate(spec.FKEYS):
            for di, dk in enumerate(spec.DEST_KEYS):
                ab = "a" if s < half else "b"
                key = "mv_%s_%s_%s" % (f, dk, ab)
                pos = (s % half) + 1
                add_cable(spec.mod_out_pos(s), spec.mod_in_pos(fi, di), cable_for(s),
                          ["IndexedEnabling/%d/%d/Parameter %d" % (pos, half + 1, idx[key])], "m%d_%d_%d" % (s, fi, di), 0.8)
    for a in range(spec.N_AO):
        for b in range(spec.N_AI):
            if spec.a_blocked(a, b):
                continue
            add_cable(spec.aud_out_pos(a), spec.aud_in_pos(b), cable_for(a + b),
                      ["IndexedEnabling/1/2/Parameter %d" % idx["ac_%s_%s" % (spec.AUDIO_OUTS[a][0], spec.AUDIO_INS[b][0])],
                       "IndexedEnabling/1/2/Parameter %d" % idx["pk_ta"]], "a%d_%d" % (a, b), 1.0)

    # 5) rings of the held jack, sockets that fit or are blocked
    over = []
    ring_img(26, 4).save(os.path.join(folder, "px_ring.png"))
    dim_img(20).save(os.path.join(folder, "px_dim.png"))
    R = ring_img(26, 4).size[0]

    def ring_at(x, y, handles):
        over.append(image_instance("Ring", "px_ring.png", x - R // 2, y - R // 2, R, R, handles))

    for prefix, n, pos in (("hdm", spec.N_SRC, spec.mod_out_pos),
                           ("him", spec.N_FLT * spec.N_DEST, lambda k: spec.mod_in_pos(k // spec.N_DEST, k % spec.N_DEST)),
                           ("hao", spec.N_AO, spec.aud_out_pos), ("hai", spec.N_AI, spec.aud_in_pos)):
        for k in range(n):
            g, p = divmod(k, spec.JACK_GROUP)
            gsize = min(spec.JACK_GROUP, n - g * spec.JACK_GROUP)
            x, y = pos(k)
            ring_at(x, y, ["IndexedEnabling/%d/%d/Parameter %d" % (p + 1, gsize + 1, idx["%s_%d" % (prefix, g)])])
    for kind, n, pos in (("fao", spec.N_AO, spec.aud_out_pos), ("fai", spec.N_AI, spec.aud_in_pos)):
        for k in range(n):
            x, y = pos(k)
            ring_at(x, y, ["IndexedEnabling/1/3/Parameter %d" % idx["%s_%d" % (kind, k)]])
            over.append(image_instance("Dim", "px_dim.png", x - 20, y - 20, 40, 40,
                                       ["IndexedEnabling/2/3/Parameter %d" % idx["%s_%d" % (kind, k)]]))

    # 6) the matrix: cell states, the chosen chip
    for st in (1, 2, 3):
        cell_image(st).save(os.path.join(folder, "px_cell_%d.png" % st))
    for fi in range(spec.N_FLT):
        chip_image(spec.FILTERS[fi][3], 2).save(os.path.join(folder, "px_chip_%d.png" % fi))
        cx, cy = spec.mx_chip_pos(fi)
        over.append(image_instance("Chip", "px_chip_%d.png" % fi, cx - spec.MX_CHIP[0] // 2, cy - spec.MX_CHIP[1] // 2, spec.MX_CHIP[0], spec.MX_CHIP[1],
                                   [pg_handle(skin, "matrix"), "IndexedEnabling/%d/%d/Parameter %d" % (fi, spec.N_FLT, idx["mx_f"])]))
    w, h = spec.MX_CELL
    for si, s in enumerate(spec.SRCS):
        for di, dk in enumerate(spec.DEST_KEYS):
            cx, cy = spec.mx_cell_pos(si, di)
            for st in (1, 2, 3):
                over.append(image_instance("Cell", "px_cell_%d.png" % st, cx - w // 2, cy - h // 2, w, h,
                                           ["IndexedEnabling/%d/4/Parameter %d" % (st, idx["mxs_%s_%s" % (s[0], dk)])]))

    # 7) lamps and meters
    led_image(False).save(os.path.join(folder, "px_led_off.png"))
    led_image(True).save(os.path.join(folder, "px_led_on.png"))
    led_image(True, colour=(255, 70, 60)).save(os.path.join(folder, "px_clip_on.png"))
    led_image(True, colour=YELLOW).save(os.path.join(folder, "px_led_acc.png"))
    led_image(False, colour=YELLOW).save(os.path.join(folder, "px_led_acc_off.png"))
    ox, oy = spec.OUT_LED
    over.append(image_instance("Clip", "px_led_off.png", ox - 11, oy - 11, 22, 22, [pg_handle(skin, "out")]))
    over.append(image_instance("Clip", "px_clip_on.png", ox - 11, oy - 11, 22, 22, ["IndexedEnabling/1/2/Parameter %d" % idx["drv_clip"]]))
    over.append(image_instance("Env", "px_led_acc_off.png", 1235 - 11, 123 - 11, 22, 22, [pg_handle(skin, "moda")]))
    over.append(image_instance("Env", "px_led_acc.png", 1235 - 11, 123 - 11, 22, 22, ["IndexedEnabling/1/2/Parameter %d" % idx["env_act"]]))
    for k in range(1, 9):
        led_bar(k).save(os.path.join(folder, "px_bar_%d.png" % k))
    led_bar(0).save(os.path.join(folder, "px_bar_0.png"))
    for key, x in (("m_in", 48), ("m_out", 306)):
        over.append(image_instance("Bar", "px_bar_0.png", x, spec.STRIP_Y + 11, 176, 16, [pg_handle(skin, "overview")]))
        for k in range(1, 9):
            over.append(image_instance("Bar", "px_bar_%d.png" % k, x, spec.STRIP_Y + 11, 176, 16,
                                       ["IndexedEnabling/%d/9/Parameter %d" % (k, idx[key])]))
    for key, vkey, x0, dx, y in (("st_lo", "mstep", spec.STEP_X0, spec.STEP_DX, 302), ("st_hi", "mstep", spec.STEP_X0 + 8 * spec.STEP_DX, spec.STEP_DX, 302),
                                 ("gt_lo", "mgate", spec.GATE_X0, spec.GATE_DX, 83), ("gt_hi", "mgate", spec.GATE_X0 + 8 * spec.GATE_DX, spec.GATE_DX, 83)):
        for k in range(1, 9):
            x = x0 + (k - 1) * dx
            if k == 1 or True:
                over.append(image_instance("Lamp", "px_led_acc_off.png", x - 11, y - 11, 22, 22, [pg_handle(skin, vkey)])) if key.endswith("lo") or True else None
            over.append(image_instance("Lamp", "px_led_acc.png", x - 11, y - 11, 22, 22, ["IndexedEnabling/%d/9/Parameter %d" % (k, idx[key])]))

    # 8) the response picture: columns of dots and the dot ruler, on every filter page
    curve_strip().save(os.path.join(folder, "px_curve.png"), optimize=True)
    ruler_strip().save(os.path.join(folder, "px_ruler.png"), optimize=True)
    rx, ry = spec.RC_XY
    ch = spec.RC_ROWS * spec.RC_RH
    flt = "IndexedEnabling/1/2/Parameter %d" % idx["in_flt"]
    curve_insts = []
    for i in range(spec.RC_COLS):
        curve_insts.append(strip_instance(skin, "px_curve.png", spec.RC_FRAMES, spec.RC_CW, ch, "rc%02d" % i,
                                          rx + i * spec.RC_CW, ry, [flt], "Response %d" % (i + 1)))
    curve_insts.append(strip_instance(skin, "px_ruler.png", spec.RC_COLS + 1, spec.RC_COLS * spec.RC_CW, 12, "rc_dot",
                                      rx, ry - 6, [flt], "Response Dot"))

    # everything goes right after the base picture: under every control
    comps[1:1] = injected + cable_insts + over + curve_insts
    skin.save()
    print("post_skin: %d views, knob radii %s, %d cable pieces (%.1f MB decoded), %d components" % (
        len(spec.VIEWS), radii, pieces, total_px * 4 / 1e6, len(comps)))

    if preview:
        os.makedirs(preview, exist_ok=True)
        comp = Composer(skin)
        for i, v in enumerate(spec.VIEWS):
            st = {"pg_" + v[0]: 1, "view": i, "in_sec": 1 if i else 0,
                  "in_flt": 1 if 1 <= i <= spec.N_FLT else 0, "in_bay": 1 if v[0] in ("bayM", "bayA") else 0, "hdr_ti": 1 if i else 0}
            if v[0] in spec.FKEYS:
                st.update({"rc%02d" % c: (c * 2) % spec.RC_FRAMES for c in range(spec.RC_COLS)})
                st["rc_dot"] = 14
            if v[0] == "bayA":
                st.update({"ac_in_ms20": 1, "ac_ms20_sem": 1, "ac_sem_out": 1, "pk_ta": 1, "pk": 1})
            if v[0] == "bayM":
                st.update({"mv_ms20_cut_a": 1, "mv_sem_res_b": 2, "pk_tm": 1, "pk": 1})
            comp.compose(st).convert("RGB").save(os.path.join(preview, "view_%02d_%s.png" % (i, v[0])))


if __name__ == "__main__":
    main()
