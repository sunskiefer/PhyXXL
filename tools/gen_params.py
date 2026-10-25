#!/usr/bin/env python3
"""Writes everything that follows from tools/spec.py:

    python3 tools/gen_params.py

  params.json        the VST parameter list for mpc-vst-plugins' gen_vst.py (index = order, append-only once shipped)
  src/param_ids.h    P_<KEY> indices and the tables for the engine
  layout.conf        the skin layout (one tab; every page is a when=pg_<view>:1 panel)
  docs/INVENTORY.md  the full control and jack list, checked against the build
  presets.json       the factory patches, cables included (tools/presets.py)
"""
import json
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spec  # noqa: E402
import presets as PRESETS  # noqa: E402

Y0 = 86   # Force Shadow y of the plugin page's top


def trigger(key, name, refresh=True):
    p = {"key": key, "name": name, "min": 0.0, "max": 1.0, "default": 0.0, "momentary": True, "type": "trigger"}
    if refresh:
        p["refresh_display"] = True
    return p


def string_param(key, name):
    return {"key": key, "name": name, "min": 0.0, "max": 0.0, "default": 0.0, "display": "string"}


def opt_param(key, name, options, default=0, **kw):
    p = {"key": key, "name": name, "options": options, "default": default}
    p.update(kw)
    return p


def param_of(c):
    if c["kind"] in ("knob", "slider"):
        p = {"key": c["key"], "name": c["name"], "min": float(c["min"]), "max": float(c["max"]),
             "default": float(c["default"]), "dynamic_display": True}
        if c.get("int"):
            p["display"] = "int"
        if c.get("unit"):
            p["unit"] = c["unit"]
        return p
    if c["kind"] in ("toggle", "enum"):
        return {"key": c["key"], "name": c["name"], "options": c["options"], "default": c["default"]}
    if c["kind"] == "button":
        return trigger(c["key"], c["name"], refresh=False)
    raise ValueError(c)


FAMILIES = []   # (name, first key, count): contiguous engine-owned groups the engine addresses by index


def build_params():
    S = spec
    P = [param_of(c) for c in S.CONTROLS]
    fam = {}

    def family(name, items):
        fam[name] = (len(P), len(items))
        P.extend(items)

    P.append(opt_param("view", "View", [v[2] or v[1] for v in S.VIEWS], 0))
    P += [trigger(k, lbl) for k, lbl, _, _ in S.NAV]
    P += [trigger("go_" + v[0], "Go " + (v[2] or v[0])) for v in S.VIEWS[1:]]
    P += [trigger("fm_audio", "Edit In Bay"), trigger("fm_open", "Open Matrix")]
    # page switches: one two-way picture switch per page (the Force: nothing above 11 positions seen working)
    family("pg", [opt_param("pg_" + v[0], "Page " + v[0], S.OFF_ON, 0) for v in S.VIEWS])
    P.append(opt_param("in_sec", "In Section", ["Overview", "Section"], 0))
    P.append(opt_param("in_flt", "In Filter", S.OFF_ON, 0))
    P.append(opt_param("in_bay", "In Bay", S.OFF_ON, 0))
    P.append(opt_param("hdr_ti", "Header Value", S.OFF_ON, 0))
    P.append(opt_param("amt_on", "Amount Shown", S.OFF_ON, 0))
    # modulation cables as parameters (settable: a preset carries its cables): md = the source feeding the input
    srcn = ["-"] + [s[1] for s in S.SRCS]
    family("md", [opt_param("md_%s_%s" % (f, d), "Mod %s %s" % (S.FSHORT[f], d.upper()), srcn, 0, poll=False)
                  for f in S.FKEYS for d in S.DEST_KEYS])
    family("ma", [{"key": "ma_%s_%s" % (f, d), "name": "Amt %s %s" % (S.FSHORT[f], d.upper()), "min": -100.0, "max": 100.0,
                   "default": 50.0, "display": "int", "poll": False} for f in S.FKEYS for d in S.DEST_KEYS])
    # audio cables: ac_<out>_<in> 1 = patched (a filter into itself is a loop and is refused)
    # the default patch is IN > MS-20 > OUT, so a freshly loaded plugin passes sound
    family("ac", [opt_param("ac_%s_%s" % (a[0], b[0]), "Audio %s to %s" % (a[1], b[1]), S.OFF_ON,
                            1 if (a[0], b[0]) in (("in", "ms20"), ("ms20", "out")) else 0, poll=False)
                  for a in S.AUDIO_OUTS for b in S.AUDIO_INS])
    # cable pictures of the modulation bay: per input, sources 0-4 in a, 5-9 in b (6 positions each)
    half = S.N_SRC // 2
    family("mv", [opt_param("mv_%s_%s_%s" % (f, d, ab), "Cable %s %s %s" % (S.FSHORT[f], d.upper(), ab),
                            ["-"] + [s[1] for s in (S.SRCS[:half] if ab == "a" else S.SRCS[half:])], 0, poll=False)
                  for f in S.FKEYS for d in S.DEST_KEYS for ab in ("a", "b")])
    # sockets of the audio bay: 0 plain, 1 fits (ring), 2 blocked (dim)
    family("fao", [opt_param("fao_%d" % i, "Out Jack %d" % i, ["-", "Fits", "Blocked"], 0) for i in range(S.N_AO)])
    family("fai", [opt_param("fai_%d" % i, "In Jack %d" % i, ["-", "Fits", "Blocked"], 0) for i in range(S.N_AI)])
    # rings of the jack waiting for its other end
    def ring(prefix, labels):
        n = len(labels)
        out = []
        for g in range(0, n, S.JACK_GROUP):
            out.append(opt_param("%s_%d" % (prefix, g // S.JACK_GROUP), "Held %s %d" % (prefix, g // S.JACK_GROUP + 1),
                                 ["-"] + labels[g:g + S.JACK_GROUP], 0))
        return out
    family("hdm", ring("hdm", [s[1] for s in S.SRCS]))
    family("him", ring("him", ["%s %s" % (S.FSHORT[f], d.upper()) for f in S.FKEYS for d in S.DEST_KEYS]))
    family("hao", ring("hao", [a[1] for a in S.AUDIO_OUTS]))
    family("hai", ring("hai", [b[1] for b in S.AUDIO_INS]))
    # patching by pages
    P.append(opt_param("pk", "Patch Step", S.PK_STEPS, 0))
    P.append(opt_param("pk_tm", "Mod Taps", S.OFF_ON, 0))
    P.append(opt_param("pk_ta", "Audio Taps", S.OFF_ON, 0))
    P.append(opt_param("pk_c", "Patch Cancel Shown", S.OFF_ON, 0))
    P += [trigger(k, n) for k, n in (("pk_cancel", "Patch Cancel"), ("pk_done", "Patch Done"), ("pk_unplug", "Patch Unplug"))]
    family("tm", [trigger("tm_" + s[0], "Jack " + s[1]) for s in S.SRCS])
    family("ti", [trigger("ti_%s_%s" % (f, d), "Jack %s %s" % (S.FSHORT[f], d.upper())) for f in S.FKEYS for d in S.DEST_KEYS])
    family("tao", [trigger("tao_%d" % i, "Jack Out %s" % a[1]) for i, a in enumerate(S.AUDIO_OUTS)])
    family("tai", [trigger("tai_%d" % i, "Jack In %s" % b[1]) for i, b in enumerate(S.AUDIO_INS)])
    # the matrix
    P.append(opt_param("mx_f", "Matrix Filter", [f[1] for f in S.FILTERS], 0))
    family("mxf", [trigger("mxf_%d" % i, "Matrix %s" % f[1]) for i, f in enumerate(S.FILTERS)])
    family("mxc", [trigger("mx_%s_%s" % (s[0], d), "Cell %s %s" % (s[1], d.upper())) for s in S.SRCS for d in S.DEST_KEYS])
    family("mxs", [opt_param("mxs_%s_%s" % (s[0], d), "State %s %s" % (s[1], d.upper()), ["-", "+", "-", "Sel"], 0)
                   for s in S.SRCS for d in S.DEST_KEYS])
    P.append(opt_param("mx_on", "Cell Selected", S.OFF_ON, 0))
    P += [trigger(k, k.upper()) for k, _, _, _ in S.MX_BTNS]
    # text readouts
    for k, n in (("patch_info", "Patch Info"), ("touch_info", "Touch Info"), ("aud_info", "Audio Info"),
                 ("mod_info", "Mod Info"), ("resp_info", "Response"), ("mx_info", "Matrix Info"), ("cpu_info", "CPU")):
        P.append(string_param(k, n))
    family("ts", [string_param("ts_" + k, "Tile " + k) for k in S.TILE_VIEWS])
    # lamps and meters (engine-owned, polled)
    P.append(opt_param("env_act", "Envelope Active", S.OFF_ON, 0))
    P.append(opt_param("drv_clip", "Drive Clip", S.OFF_ON, 0))
    P.append(opt_param("m_in", "In Meter", [str(i) for i in range(9)], 0))
    P.append(opt_param("m_out", "Out Meter", [str(i) for i in range(9)], 0))
    family("rc", [{"key": "rc%02d" % i, "name": "Response %d" % (i + 1), "min": 0.0, "max": float(S.RC_FRAMES - 1),
                   "default": 0.0, "display": "int"} for i in range(S.RC_COLS)])
    P.append({"key": "rc_dot", "name": "Response Dot", "min": 0.0, "max": float(S.RC_COLS), "default": 0.0, "display": "int"})
    for n, lo in (("st_lo", 1), ("st_hi", 9), ("gt_lo", 1), ("gt_hi", 9)):
        P.append(opt_param(n, "Step Lamp %d-%d" % (lo, lo + 7), ["-"] + [str(lo + i) for i in range(8)], 0))
    P += [{"key": "ql%d" % (i + 1), "name": "Q-Link %d" % (i + 1), "min": 0.0, "max": 1.0, "default": 0.0,
           "dynamic_name": True, "dynamic_display": True} for i in range(16)]
    P.append(opt_param("pop_fg_preset", "Presets List", ["Closed", "Open"], 0))
    keys = [p["key"] for p in P]
    assert len(keys) == len(set(keys)), "duplicate keys: %s" % [k for k in keys if keys.count(k) > 1][:5]
    for name, (first, n) in fam.items():
        assert all(len(p.get("options", [])) <= 11 for p in P[first:first + n]), name
    return P, fam


def write_params(P):
    secs = []
    for v in spec.VIEWS[1:]:
        ks = [c["key"] for c in spec.CONTROLS if c["view"] == v[0]]
        if ks:
            secs.append({"label": (v[2] or v[0]).title()[:20], "keys": ks})
    with open(os.path.join(ROOT, "params.json"), "w") as f:
        json.dump({"name": "PhyXXL", "params": P, "sections": secs}, f, indent=1)
        f.write("\n")


def cid(k):
    return "P_" + k.upper()


def view_qlinks(v):
    S = spec
    k = v[0]
    if k == "overview":
        keys = S.OVERVIEW_QLINKS
    elif k == "mstep":
        keys = S.STEP_QLINKS
    elif k == "mfunc":
        keys = S.FUNC_QLINKS
    elif k == "mgate":
        keys = S.GATE_QLINKS
    elif k == "matrix":
        keys = S.MATRIX_QLINKS
    elif k in ("bayM", "bayA"):
        keys = []
    else:
        cs = [c for c in S.CONTROLS if c["view"] == k and c["kind"] != "button"]
        cs.sort(key=lambda c: (round(c["cy"] / 60), c["cx"]))
        keys = [c["key"] for c in cs][:16]
    return keys + ["-"] * (16 - len(keys))


def write_header(P, fam):
    S = spec
    L = ["// Generated by tools/gen_params.py from tools/spec.py -- do not edit.", "#pragma once", ""]
    for i, p in enumerate(P):
        L.append("#define %s %d" % (cid(p["key"]), i))
    L.append("#define P_COUNT %d" % len(P))

    def num(p, k, d):
        t = "%.6g" % float(p.get(k, d))
        return t + (".0f" if "." not in t and "e" not in t else "f")
    L.append("static const char *const P_KEY[P_COUNT] = {%s};" % ", ".join('"%s"' % p["key"] for p in P))
    L.append("static const char *const P_NAME[P_COUNT] = {%s};" % ", ".join('"%s"' % p["name"] for p in P))
    L.append("static const char *const P_UNIT[P_COUNT] = {%s};" % ", ".join('"%s"' % p.get("unit", "") for p in P))
    L.append("static const float P_MIN[P_COUNT] = {%s};" % ", ".join(num(p, "min", 0) for p in P))
    L.append("static const float P_MAX[P_COUNT] = {%s};" % ", ".join(
        ("%d.0f" % (len(p["options"]) - 1)) if "options" in p else num(p, "max", 1) for p in P))
    L.append("static const float P_DEF[P_COUNT] = {%s};" % ", ".join(num(p, "default", 0) for p in P))
    L.append("static const unsigned char P_NOPTS[P_COUNT] = {%s};" % ", ".join(str(len(p.get("options", []))) for p in P))
    for i, p in enumerate(P):
        if "options" in p and not re.match(r"(pg|mv|fao|fai|hdm|him|hao|hai|mxs|md|ac)_|m_(in|out)$", p["key"]):
            L.append("static const char *const OPTS_%d[] = {%s};" % (i, ", ".join('"%s"' % o for o in p["options"])))
    # the option text of the engine-owned families is never asked for: generic ones
    L.append('static const char *const OPTS_YESNO[] = {"Off", "On"};')
    L.append("static const char *const *const P_OPT[P_COUNT] = {%s};" % ", ".join(
        ("OPTS_%d" % i) if ("options" in p and not re.match(r"(pg|mv|fao|fai|hdm|him|hao|hai|mxs|md|ac)_|m_(in|out)$", p["key"]))
        else ("OPTS_YESNO" if "options" in p else "0") for i, p in enumerate(P)))
    L.append("static const unsigned char P_INT[P_COUNT] = {%s};" % ", ".join(
        "1" if p.get("display") == "int" else "0" for p in P))
    L.append("#define N_CONTROLS %d   // the sound parameters come first: indices 0..N_CONTROLS-1" % len(S.CONTROLS))
    L.append("")
    for name, (first, n) in fam.items():
        L.append("#define F_%s %d   // first index of the %d '%s' parameters" % (name.upper(), first, n, name))
        L.append("#define N_%s %d" % (name.upper(), n))
    L.append("")
    L.append("// views")
    for i, v in enumerate(S.VIEWS):
        L.append("#define V_%s %d" % (v[0].upper(), i))
    L.append("#define N_VIEWS %d" % len(S.VIEWS))
    L.append("#define RC_COLS %d\n#define RC_ROWS %d\n#define RC_FRAMES %d" % (S.RC_COLS, S.RC_ROWS, S.RC_FRAMES))
    L.append("#define N_FLT %d" % S.N_FLT)
    L.append("#define N_SRC %d" % S.N_SRC)
    L.append("#define N_DEST %d" % S.N_DEST)
    L.append("#define N_AO %d" % S.N_AO)
    L.append("#define N_AI %d" % S.N_AI)
    L.append("#define JACK_GROUP %d" % S.JACK_GROUP)
    L.append("#define N_TILES %d" % len(S.TILE_VIEWS))
    L.append("static const char *const SRC_LABEL[N_SRC] = {%s};" % ", ".join('"%s"' % s[1] for s in S.SRCS))
    L.append("static const char *const DEST_LABEL[N_DEST] = {%s};" % ", ".join('"%s"' % d[1] for d in S.DESTS))
    L.append("static const char *const FLT_LABEL[N_FLT] = {%s};" % ", ".join('"%s"' % f[1] for f in S.FILTERS))
    L.append("static const char *const AO_LABEL[N_AO] = {%s};" % ", ".join('"%s"' % a[1] for a in S.AUDIO_OUTS))
    L.append("static const char *const AI_LABEL[N_AI] = {%s};" % ", ".join('"%s"' % b[1] for b in S.AUDIO_INS))
    L.append("static const char *const M12_MODE_NAME[15] = {%s};" % ", ".join('"%s"' % m for m in S.M12_MODES))
    L.append("static const char *const LFO_WAVE_NAME[5] = {%s};" % ", ".join('"%s"' % m for m in S.LFO_WAVES))
    L.append("static const float DIV_BEATS[%d] = {%s};" % (len(S.DIV_BEATS), ", ".join("%.6ff" % b for b in S.DIV_BEATS)))
    L.append("static const char *const DIV_NAME[%d] = {%s};" % (len(S.DIVS), ", ".join('"%s"' % d for d in S.DIVS)))
    # the knob each destination of each filter moves (-1: none / the engine's hidden pre-gain)
    rows = []
    for f in S.FKEYS:
        rows.append("    {%s}," % ", ".join(cid(k) if k else "-1" for k in S.MOD_MAP[f]))
    L.append("static const short MOD_PARAM[N_FLT][4] = {")
    L += rows
    L.append("};")
    # the page each filter's controls sit on, and the view index of each tile
    L.append("static const short TILE_VIEW[N_TILES] = {%s};" % ", ".join("V_" + k.upper() for k in S.TILE_VIEWS))
    L.append("")
    L.append("// the views' controls in Q-Link order (top row left to right, then the next): up to 16 per view, -1 = none")
    rows = []
    for v in S.VIEWS:
        ids = [cid(k) if k != "-" else "-1" for k in view_qlinks(v)]
        rows.append("    {%s}," % ", ".join(ids))
    L.append("static const short VIEW_QLINKS[N_VIEWS][16] = {")
    L += rows
    L.append("};")
    L.append("")
    with open(os.path.join(ROOT, "src", "param_ids.h"), "w") as f:
        f.write("\n".join(L))


# ------------------------------------------------------------------------------------------------ layout.conf
THEME = """scale_names=1
label_scale=1.25
theme_bg=121212
theme_panel=121212
theme_line=7a7a7a
theme_ink=eeeeee
theme_ink_dim=b8b8b8
theme_ink_faint=777777
theme_accent=e6c84a
theme_accent_hi=ffffff
theme_knob_face=141414
theme_knob_ring=3a3a3a
theme_knob_dot=eeeeee
theme_bar=141414
theme_seg_active=e6c84a
theme_seg_inactive=111111
theme_seg_active_tx=111111
theme_btn_text=eeeeee
theme_tab_on=e6c84a
theme_tab_on_tx=111111
theme_lcd=0d0d0d
theme_box=111111"""
HIDDEN = "121212"   # the panel colour: the framework's value label under a knob stays invisible, the value shows in the header


def layout_line(c):
    v = "when=pg_%s:1" % c["view"]
    x, y = c["cx"], c["cy"] + Y0
    if c["kind"] == "knob":
        bw = 130 if c["r"] >= 46 else 110
        return 'knob cx=%d cy=%d r=%d label="%s" key=%s ns=0 vs=1 ink_dim=%s bw=%d %s' % (
            x, y, c["r"], c["name"].upper(), c["key"], HIDDEN, bw, v)
    if c["kind"] == "slider":
        if c["vertical"]:
            return 'slider_v cx=%d cy=%d w=%d h=%d label="%s" key=%s ns=0 vs=1 bw=%d %s' % (
                x, y, c["sw"], c["sh"], c["name"].upper(), c["key"], max(c["sw"], 44), v)
        return 'slider_h cx=%d cy=%d w=%d h=%d label="%s" key=%s ns=0 vs=24 bw=%d when=amt_on:1' % (
            x, y, c["sw"], c["sh"], c["name"].upper(), c["key"], c["sw"])
    if c["kind"] == "toggle":
        return 'toggle cx=%d cy=%d label="%s" key=%s bw=%d ns=0 %s' % (x, y, c["name"].upper(), c["key"], c["bw"], v)
    if c["kind"] == "button":
        return 'button cx=%d cy=%d label="%s" key=%s %s' % (x, y, c["name"].upper(), c["key"], v)
    if c["widget"] == "popup":
        return 'popup cx=%d cy=%d w=%d h=%d label="%s" key=%s %s' % (x, y, c["w"], c["h"], c["name"].upper(), c["key"], v)
    return 'enum_h cx=%d cy=%d sw=%d sh=%d rows=%d label="%s" key=%s %s' % (
        x, y, c["sw"], c["sh"], c["rows"], c["name"].upper(), c["key"], v)


def box_centre(b):
    return b[0] + b[2] // 2, b[1] + b[3] // 2


def write_layout():
    S = spec
    L = ["# PhyXXL page layout. GENERATED by tools/gen_params.py from tools/spec.py -- edit spec.py, not this.",
         "# One tab; each page is a panel shown while its pg_<view> switch is on. The overview tiles, jacks, cables, meters",
         "# and the panel art are placed and drawn by tools/post_skin.py.",
         THEME,
         "qlinks_track = " + ",".join("ql%d" % (i + 1) for i in range(16)),
         "", "[tab PhyXXL]"]
    for k, lbl, x, y in S.NAV:   # one instance each, shown on every page but the overview
        L.append('button cx=%d cy=%d label="%s" key=%s' % (x, y + Y0, lbl, k))
    for k, lbl, x, y, w in S.CHIPS:   # the bay's mode chips
        L.append('button cx=%d cy=%d label="%s" key=%s when=in_bay:1' % (x, y + Y0, lbl, k))
    for k, lbl, x, y, w, h in S.FILTER_BTNS:
        L.append('button cx=%d cy=%d label="%s" key=%s when=in_flt:1' % (x, y + Y0, lbl, k))
    for k in S.TILE_VIEWS:
        x, y, w, h = S.TILES[k]
        L.append('button cx=%d cy=%d label="" key=go_%s when=pg_overview:1' % (x + w // 2, y + h // 2 + Y0, k))
    for k in S.TILE_VIEWS:
        x, y, w, h = S.TILES[k]
        L.append('readout cx=%d cy=%d w=%d h=34 label="" key=ts_%s box=0 tsize=26 talign=left when=pg_overview:1' % (
            x + 12 + (w - 24) // 2, y + 76 + Y0, w - 24, k))
    L.append('readout cx=660 cy=%d w=200 h=34 label="" key=cpu_info box=0 tsize=26 talign=left when=pg_overview:1' % (S.STRIP_Y + 19 + Y0))
    # patch bay jacks
    for i, s in enumerate(S.SRCS):
        x, y = S.mod_out_pos(i)
        w, h = S.PICK_MOD_OUT
        L.append('button cx=%d cy=%d label="" key=tm_%s when=pk_tm:1' % (x, y + Y0, s[0]))
    for fi, f in enumerate(S.FKEYS):
        for d in S.DEST_KEYS:
            x, y = S.mod_in_pos(fi, S.DEST_KEYS.index(d))
            L.append('button cx=%d cy=%d label="" key=ti_%s_%s when=pk_tm:1' % (x, y + Y0, f, d))
    for i in range(S.N_AO):
        x, y = S.aud_out_pos(i)
        L.append('button cx=%d cy=%d label="" key=tao_%d when=pk_ta:1' % (x, y + Y0, i))
    for i in range(S.N_AI):
        x, y = S.aud_in_pos(i)
        L.append('button cx=%d cy=%d label="" key=tai_%d when=pk_ta:1' % (x, y + Y0, i))
    L.append('button cx=%d cy=%d label="CANCEL" key=pk_cancel when=pk_c:1' % (S.PK_CANCEL[0], S.PK_CANCEL[1] + Y0))
    cx, cy = box_centre(S.PK_UNPLUG)
    L.append('button cx=%d cy=%d label="UNPLUG" key=pk_unplug when=pk:4' % (cx, cy + Y0))
    cx, cy = box_centre(S.PK_DONE)
    L.append('button cx=%d cy=%d label="DONE" key=pk_done when=pk:4' % (cx, cy + Y0))
    L.append('readout cx=479 cy=%d w=900 h=44 label="" key=patch_info box=0 tsize=26 talign=left when=in_bay:1' % (590 + Y0))
    L.append('readout cx=%d cy=%d w=%d h=44 label="" key=touch_info tsize=28 when=hdr_ti:1' % (
        S.HDR_TOUCH[0], S.HDR_TOUCH[1] + Y0, S.HDR_TOUCH[2]))
    # filter pages' bars
    L.append('readout cx=1000 cy=%d w=480 h=36 label="" key=resp_info box=0 tsize=24 talign=right when=in_flt:1' % (254 + Y0))
    L.append('readout cx=499 cy=%d w=800 h=40 label="" key=aud_info box=0 tsize=26 talign=left when=in_flt:1' % (489 + Y0))
    L.append('readout cx=429 cy=%d w=800 h=40 label="" key=mod_info box=0 tsize=26 talign=left when=in_flt:1' % (577 + Y0))
    # the matrix
    for i in range(S.N_FLT):
        x, y = S.mx_chip_pos(i)
        L.append('button cx=%d cy=%d label="" key=mxf_%d when=pg_matrix:1' % (x, y + Y0, i))
    for si in range(S.N_SRC):
        for di, d in enumerate(S.DEST_KEYS):
            x, y = S.mx_cell_pos(si, di)
            L.append('button cx=%d cy=%d label="" key=mx_%s_%s when=pg_matrix:1' % (x, y + Y0, S.SRC_KEYS[si], d))
    for k, lbl, x, y in S.MX_BTNS:
        L.append('button cx=%d cy=%d label="%s" key=%s when=mx_on:1' % (x, y + Y0, lbl, k))
    L.append('readout cx=349 cy=%d w=640 h=40 label="" key=mx_info box=0 tsize=26 talign=left when=pg_matrix:1' % (521 + Y0))
    for c in S.CONTROLS:
        if c["key"] == "data":
            continue   # the DATA knob keeps its parameter (indexes never move) but has no place on the page
        L.append(layout_line(c))
    L.append('qlinks "PhyXXL" = ' + ",".join("ql%d" % (i + 1) for i in range(16)))
    L = [l for l in L if l is not None]
    with open(os.path.join(ROOT, "layout.conf"), "w") as f:
        f.write("\n".join(L) + "\n")


# ------------------------------------------------------------------------------------------------ inventory
def write_inventory():
    S = spec
    L = ["# PhyXXL inventory", "",
         "Every control and jack, generated from `tools/spec.py` (the build checks the skin against the same list).", ""]
    for v in S.VIEWS[1:]:
        cs = [c for c in S.CONTROLS if c["view"] == v[0]]
        if not cs:
            continue
        L += ["## " + v[1].title(), "", "| Control | Key | Range |", "|---|---|---|"]
        for c in cs:
            if c["kind"] in ("knob", "slider"):
                rng = "%g .. %g %s" % (c["min"], c["max"], c.get("unit", ""))
            elif c["kind"] == "button":
                rng = "push"
            else:
                rng = " / ".join(c["options"]) if len(c["options"]) <= 8 else "%d options" % len(c["options"])
            L.append("| %s | `%s` | %s |" % (c["name"], c["key"], rng.strip()))
        L.append("")
    L += ["## Modulation: sources and destinations", "", "| Source | Signal |", "|---|---|"]
    for s in S.SRCS:
        L.append("| %s | %s |" % (s[1], s[2]))
    L += ["", "Each of the 8 filters has 6 destinations, each fed by one source (`md_<filter>_<dest>`) at an amount "
          "(`ma_<filter>_<dest>`, -100..+100):", "",
          "| Filter | CUT | RES | DRV | MODE | PAN | OUT |", "|---|---|---|---|---|---|---|"]
    for f in S.FILTERS:
        m = S.MOD_MAP[f[0]]
        names = [(S.CTRL[k]["name"] if k else "(pre-gain)") for k in m]
        L.append("| %s | %s | Pan | Out |" % (f[1], " | ".join(names)))
    L += ["", "## Audio bay", "", "Outputs: " + ", ".join(a[1] for a in S.AUDIO_OUTS) + ". Inputs: " +
          ", ".join(b[1] for b in S.AUDIO_INS) + ". Any output into any input; an input sums its cables; a filter "
          "into itself, or a loop through other filters, is refused.", "",
          "%d controls, %d modulation inputs, %d audio cables possible." % (
              len(S.CONTROLS), S.N_FLT * S.N_DEST, S.N_AO * S.N_AI - S.N_FLT), ""]
    with open(os.path.join(ROOT, "docs", "INVENTORY.md"), "w") as f:
        f.write("\n".join(L))


# ------------------------------------------------------------------------------------------------ factory presets
def write_presets():
    S = spec
    out = []
    for name, over, audio, mods in PRESETS.PRESETS:
        vals = {}
        for k in over:
            assert k in S.CTRL, "preset %s: unknown control %s" % (name, k)
        for c in S.CONTROLS:
            if c["kind"] == "button" or c["key"] in ("data",):
                continue
            v = over.get(c["key"], c["default"])
            if c["kind"] in ("toggle", "enum"):
                v = c["options"][int(v)]
            vals[c["key"]] = v
        aud = set(audio)
        for a in S.AUDIO_OUTS:
            for b in S.AUDIO_INS:
                vals["ac_%s_%s" % (a[0], b[0])] = "On" if (a[0], b[0]) in aud else "Off"
        for (a, b) in aud:
            assert a in [x[0] for x in S.AUDIO_OUTS] and b in [x[0] for x in S.AUDIO_INS], (name, a, b)
            assert not (a == b), "preset %s: loop %s" % (name, a)
        mm = {(f, d): (s, amt) for f, d, s, amt in mods}
        for f in S.FKEYS:
            for d in S.DEST_KEYS:
                if (f, d) in mm:
                    s, amt = mm[(f, d)]
                    assert s in S.SRC_KEYS, (name, s)
                    vals["md_%s_%s" % (f, d)] = S.SRCS[S.SRC_KEYS.index(s)][1]
                    vals["ma_%s_%s" % (f, d)] = amt
                else:
                    vals["md_%s_%s" % (f, d)] = "-"
                    vals["ma_%s_%s" % (f, d)] = 50
        out.append({"name": name, "values": vals})
    with open(os.path.join(ROOT, "presets.json"), "w") as f:
        json.dump({"presets": out}, f, indent=1)
        f.write("\n")
    return len(out)


def main():
    P, fam = build_params()
    write_params(P)
    write_header(P, fam)
    write_layout()
    write_inventory()
    n = write_presets()
    print("gen_params: %d parameters (%d controls), %d presets" % (len(P), len(spec.CONTROLS), n))


if __name__ == "__main__":
    main()
