"""PhyXXL: the one source of truth for every control, jack, view and position.

Everything else is generated from this file:
  tools/gen_params.py  -> params.json, src/param_ids.h, layout.conf, docs/INVENTORY.md, presets.json
  tools/post_skin.py   -> panel art, knob strips, jacks, cables, overview (reads the built skin + this file)

MPC stores automation and saved values by parameter INDEX, so once a version ships the parameter list is append-only.
Coordinates are skin pixels: the plugin page is 1280 x 628 (layout.conf adds 86 to y, the Force Shadow offset).

PhyXXL is an effect: eight filter modules (in the style of the MS-20, SEM, Minimoog, Matrix-12, 2600,
Wasp, prologue and Polivoks), audio routable from any filter into any other (and the plugin input / output),
and ten modulation sources routed to six destinations of every filter through a patch bay or a matrix.
"""

# the response picture on a filter page: RC_COLS columns of RC_ROWS rows, each column one stroke (like VADER's envelope)
RC_COLS, RC_ROWS = 32, 12
RC_FRAMES = RC_ROWS * (RC_ROWS + 1) // 2
RC_CW, RC_RH = 22, 12           # column width, row height: a 704 x 144 picture inside the response box
RC_XY = (544, 268)
RESP_BOX = (527, 238, 738, 204)  # the dashed response box of the mock (x, y, w, h)

def MX(x):
    """a 1920 x 1080 mock x as a page x (the page is 1280 wide)"""
    return int(round(x * 2 / 3.0))


def MY(y):
    """a mock y as a page y (the page is 628 high: the mock's 1080 squeezed)"""
    return int(round(y * 628 / 1080.0))


OFF_ON = ["Off", "On"]
DIVS = ["1/1", "1/2", "1/4", "1/8", "1/16", "1/32", "1/4 T", "1/8 T", "1/16 T", "1/8 .", "1/16 ."]
DIV_BEATS = [4, 2, 1, 0.5, 0.25, 0.125, 2 / 3.0, 1 / 3.0, 1 / 6.0, 0.75, 0.375]

# ------------------------------------------------------------------------------------------------ filters
# (key, panel name, page title, tile title)
FILTERS = [
    ("ms20", "MS-20", "MS-20 STYLE FILTER  (HIGHPASS + LOWPASS)", "MS-20"),
    ("sem", "SEM", "SEM STYLE FILTER", "SEM"),
    ("mini", "MINI", "MINI LADDER FILTER", "MINI"),
    ("m12", "M12", "MATRIX-12 STYLE FILTER", "M12"),
    ("p26", "2600", "2600 STYLE FILTER", "2600"),
    ("wasp", "WASP", "WASP STYLE FILTER", "WASP"),
    ("prl", "PROLOGUE", "PROLOGUE STYLE FILTER", "PROLOGUE"),
    ("poli", "POLIVOKS", "POLIVOKS FILTER", "POLIVOKS"),
]
FKEYS = [f[0] for f in FILTERS]
FLABEL = {f[0]: f[1] for f in FILTERS}
FSHORT = {"ms20": "MS20", "sem": "SEM", "mini": "MINI", "m12": "M12", "p26": "2600", "wasp": "WASP", "prl": "PRL",
          "poli": "POLI"}

# modulation sources and destinations
SRCS = [("lfo", "LFO", "LFO, -1..+1"), ("env", "ENV", "Envelope (attack, hold, decay), 0..1"),
        ("foll", "FOLL", "Envelope follower of the input, 0..1"), ("step", "STEP", "Step sequencer bars"),
        ("func", "FUNC", "Function generator"), ("gate", "GATE", "Gate sequencer gate, 0 / 1"),
        ("rand", "RAND", "Random sample & hold with slew, -1..+1"), ("modw", "MODW", "MIDI mod wheel (CC 1), 0..1"),
        ("vel", "VEL", "Velocity of the last note, 0..1"), ("key", "KEY", "Pitch of the last note, 0..1 over the keyboard")]
SRC_KEYS = [s[0] for s in SRCS]
DESTS = [("cut", "CUT"), ("res", "RES"), ("drv", "DRV"), ("mode", "MODE"), ("pan", "PAN"), ("out", "OUT")]
DEST_KEYS = [d[0] for d in DESTS]
N_SRC, N_DEST, N_FLT = len(SRCS), len(DESTS), len(FILTERS)

# the knob each modulation destination moves on each filter (None: the engine's own hidden pre-gain / nothing)
MOD_MAP = {
    "ms20": ("ms_cut", "ms_lppk", "ms_lp", "ms_hp"),
    "sem": ("sem_freq", "sem_res", "sem_ingain", "sem_mode"),
    "mini": ("mini_cut", "mini_emph", "mini_drive", "mini_vol"),
    "m12": ("m12_cut", "m12_res", None, "m12_mode"),
    "p26": ("p26_cut", "p26_res", None, "p26_fm1"),
    "wasp": ("wasp_cut", "wasp_peak", "wasp_drive", "wasp_mode"),
    "prl": ("prl_cut", "prl_res", "prl_drive", "prl_trk"),
    "poli": ("poli_cut", "poli_res", "poli_drive", "poli_env"),
}

# ---------------------------------------------------------------------------------------------------------- views
VIEWS = [("overview", "PhyXXL", "")] + [(f[0], f[2], f[3]) for f in FILTERS] + [
    ("out", "DRIVE  /  OUTPUT", "DRIVE + OUT"),
    ("moda", "MOD SOURCES A  /  LFO  ENVELOPE  FOLLOWER", "MOD A"),
    ("mstep", "MOD SOURCES B1  /  STEP SEQUENCER", "STEP SEQ"),
    ("mfunc", "MOD SOURCES B2  /  FUNCTION GENERATOR", "FUNCTION"),
    ("mgate", "MOD SOURCES B3  /  GATE SEQUENCER  /  RANDOM", "GATE + RAND"),
    ("matrix", "MOD MATRIX", "MOD MATRIX"),
    ("bayM", "PATCH BAY  /  MODULATION", "PATCH BAY"),
    ("bayA", "PATCH BAY  /  AUDIO", ""),
]
VIEW_KEYS = [v[0] for v in VIEWS]
VIEW_NO = {k: i for i, k in enumerate(VIEW_KEYS)}
N_VIEWS = len(VIEWS)

# overview tiles (x, y, w, h): 5 x 3 tiles, the strip below for the meters and the two switches
_TW, _TH, _GX, _GY, _TX, _TY = 309, 113, 9, 6, 13, 67
TILE_VIEWS = FKEYS + ["out", "moda", "mstep", "mfunc", "mgate", "matrix", "bayM"]
TILES = {}
for _i, _k in enumerate(TILE_VIEWS):
    TILES[_k] = (_TX + (_i % 4) * (_TW + _GX), _TY + (_i // 4) * (_TH + _GY), _TW, _TH)
STRIP_Y = 548   # the strip under the tiles: meters, CPU and the two buttons
DATA_POS = (_TX + 3 * (_TW + _GX) + _TW // 2, 464)   # the 16th tile slot, empty on purpose

# ---------------------------------------------------------------------------------------------- the controls
BIG, MED, SMALL = 58, 46, 58


def K(key, name, lo, hi, de, view, cx, cy, r=BIG, unit="", intd=False, vals=None):
    return dict(key=key, name=name, kind="knob", min=lo, max=hi, default=de, view=view, cx=cx, cy=cy, r=r, unit=unit,
                int=intd, vals=vals)


def T(key, name, de, view, cx, cy, options=OFF_ON, bw=130):
    return dict(key=key, name=name, kind="toggle", options=options, default=de, view=view, cx=cx, cy=cy, bw=bw)


def E(key, name, options, de, view, cx, cy, sw=110, sh=52, rows=1, widget="enum_h", w=220, h=52):
    return dict(key=key, name=name, kind="enum", options=options, default=de, view=view, cx=cx, cy=cy, widget=widget,
                sw=sw, sh=sh, rows=rows, w=w, h=h)


def B(key, name, view, cx, cy, w=120, h=44):
    return dict(key=key, name=name, kind="button", view=view, cx=cx, cy=cy, w=w, h=h)


def SL(key, name, lo, hi, de, view, cx, cy, w=40, h=200, vertical=True):
    return dict(key=key, name=name, kind="slider", min=lo, max=hi, default=de, view=view, cx=cx, cy=cy, sw=w, sh=h,
                vertical=vertical)


def slot(i):
    return 99 + 171 * i


ROW1 = 135                  # the knob row of every filter page
ROW2 = 312                  # the second row: DRY / WET, PAN, OUT
M12_MODES = ["LP 1", "LP 2", "LP 3", "LP 4", "HP 1", "HP 2", "HP 3", "HP 4", "BP 2", "BP 4", "NOTCH 2", "NOTCH 4",
             "PHASE 2", "LP2 + HP", "BP + LP"]
P26_TYPES = ["4012", "4072", "4075"]
POLI_MODES = ["LP", "BP"]

CONTROLS = [
    # parameter 0 first: MPC's host toggles parameter 0 on insert and stop, so it is the plain OUTPUT level
    K("out_level", "Output", -24, 12, 0, "out", slot(5), 131, unit="dB"),
    # ---- MS-20: CUTOFF, HP, HP PEAK, LP, LP PEAK, STEREO
    K("ms_cut", "Cutoff", -5, 5, 0, "ms20", slot(0), ROW1),
    K("ms_hp", "HP", 0, 10, 0, "ms20", slot(1), ROW1),
    K("ms_hppk", "HP Peak", 0, 10, 0, "ms20", slot(2), ROW1),
    K("ms_lp", "LP", 0, 10, 8, "ms20", slot(3), ROW1),
    K("ms_lppk", "LP Peak", 0, 10, 2, "ms20", slot(4), ROW1),
    K("ms_stereo", "Stereo", 0, 10, 0, "ms20", slot(5), ROW1),
    # ---- SEM
    K("sem_freq", "Freq", 0, 10, 6, "sem", slot(0), ROW1),
    K("sem_res", "Res", 0, 10, 2, "sem", slot(1), ROW1),
    K("sem_mode", "Mode", 0, 10, 0, "sem", slot(2), ROW1),
    K("sem_ingain", "In Gain", 0, 10, 5, "sem", slot(3), ROW1),
    K("sem_innoise", "In Noise", 0, 10, 0, "sem", slot(4), ROW1),
    T("sem_clip", "Soft Clip", 1, "sem", slot(5), ROW1),
    # ---- MINI
    K("mini_drive", "Drive", 0, 10, 3, "mini", slot(0), ROW1),
    K("mini_cut", "Cutoff", 0, 10, 6, "mini", slot(1), ROW1),
    K("mini_emph", "Emphasis", 0, 10, 2, "mini", slot(2), ROW1),
    K("mini_vol", "Out Vol", 0, 10, 7, "mini", slot(3), ROW1),
    # ---- M12
    K("m12_mode", "Mode", 0, 14, 3, "m12", slot(0), ROW1, intd=True),
    K("m12_cut", "Cutoff", 0, 10, 6, "m12", slot(1), ROW1),
    K("m12_res", "Reson.", 0, 10, 2, "m12", slot(2), ROW1),
    # ---- 2600
    K("p26_cut", "Cutoff", 0, 10, 6, "p26", slot(0), ROW1),
    K("p26_res", "Res", 0, 10, 2, "p26", slot(1), ROW1),
    K("p26_fm1", "FM 1", 0, 10, 0, "p26", slot(2), ROW1),
    K("p26_fm2", "FM 2", 0, 10, 0, "p26", slot(3), ROW1),
    K("p26_fm3", "FM 3", 0, 10, 0, "p26", slot(4), ROW1),
    E("p26_type", "Type", P26_TYPES, 1, "p26", slot(5), ROW1, sw=76),
    # ---- WASP
    K("wasp_cut", "Cutoff", 0, 10, 6, "wasp", slot(0), ROW1),
    K("wasp_peak", "Peak", 0, 10, 3, "wasp", slot(1), ROW1),
    K("wasp_mode", "Mode", 0, 10, 0, "wasp", slot(2), ROW1),
    K("wasp_drive", "In Drive", 0, 10, 3, "wasp", slot(3), ROW1),
    # ---- PROLOGUE
    K("prl_cut", "Cutoff", 0, 10, 6, "prl", slot(0), ROW1),
    K("prl_res", "Reson.", 0, 10, 2, "prl", slot(1), ROW1),
    K("prl_drive", "Drive", 0, 10, 2, "prl", slot(2), ROW1),
    K("prl_trk", "Key Trk", 0, 10, 0, "prl", slot(3), ROW1),
    K("prl_eg", "EG Int", -10, 10, 0, "prl", slot(4), ROW1),
    # ---- POLIVOKS
    K("poli_cut", "Cutoff", 0, 10, 6, "poli", slot(0), ROW1),
    K("poli_res", "Res", 0, 10, 2, "poli", slot(1), ROW1),
    K("poli_drive", "Drive", 0, 10, 3, "poli", slot(2), ROW1),
    K("poli_env", "Env Amt", 0, 10, 0, "poli", slot(3), ROW1),
    K("poli_decay", "Decay", 0, 10, 4, "poli", slot(4), ROW1),
    E("poli_mode", "Mode", POLI_MODES, 0, "poli", slot(5), ROW1, sw=76),
]
# the three controls every filter has (the "Every filter" column): DRY / WET, PAN, OUT
for _f in FILTERS:
    CONTROLS += [K(_f[0] + "_mix", "Dry / Wet", 0, 100, 100, _f[0], slot(0), ROW2, unit="%", intd=True),
                 K(_f[0] + "_pan", "Pan", -100, 100, 0, _f[0], slot(1), ROW2, intd=True),
                 K(_f[0] + "_out", "Out", -24, 12, 0, _f[0], slot(2), ROW2, unit="dB")]
# ---- DRIVE / OUTPUT (out_level was placed first, above)
CONTROLS += [
    B("chain_series", "Series", "out", 103, 315, w=173, h=44),
    B("chain_par", "Parallel", "out", 287, 315, w=173, h=44),
    B("chain_clear", "Clear", "out", 471, 315, w=173, h=44),
    K("out_drive", "Drive", 0, 10, 0, "out", slot(0), 131),
    K("out_lo", "Low Cut", 0, 10, 0, "out", slot(1), 131),
    K("out_hi", "High Cut", 0, 10, 10, "out", slot(2), 131),
    K("out_dw", "Dry / Wet", 0, 100, 100, "out", slot(3), 131, unit="%", intd=True),
    K("out_mix", "Mix", 0, 200, 100, "out", slot(4), 131, unit="%", intd=True),
]

# ---- MOD SOURCES A: LFO, ENVELOPE (AHD), ENVELOPE FOLLOWER
LFO_WAVES = ["Sine", "Triangle", "Saw", "Square", "Random"]
CONTROLS += [
    K("lfo_wave", "Wave", 0, 4, 0, "moda", slot(0), 157, intd=True),
    K("lfo_rate", "Rate", 0, 10, 4, "moda", slot(1), 157),
    K("lfo_smooth", "Smooth", 0, 10, 0, "moda", slot(2), 157),
    T("lfo_sync", "Sync", 0, "moda", slot(3), 157),
    K("env_att", "Attack", 0, 10, 1, "moda", slot(4), 157),
    K("env_hold", "Hold", 0, 10, 0, "moda", slot(5), 157),
    K("env_dec", "Decay", 0, 10, 4, "moda", slot(6), 157),
    E("env_trig", "Trigger", ["Gate Seq", "Note", "Input"], 0, "moda", slot(6), 362, sw=88),
    K("foll_sens", "Sens.", 0, 10, 5, "moda", slot(0), 362),
    K("foll_delay", "Delay", 0, 10, 0, "moda", slot(1), 362),
    K("foll_rise", "Rise", 0, 10, 2, "moda", slot(2), 362),
    K("foll_fall", "Fall", 0, 10, 4, "moda", slot(3), 362),
    E("foll_src", "Source", ["Audio In", "After Drive"], 0, "moda", slot(4) + 30, 362, sw=96),
]
# ---- MOD SOURCES B1: STEP SEQUENCER (16 bars)
STEP_X0, STEP_DX, STEP_Y, STEP_H = 67, 75, 181, 215
CONTROLS += [SL("st_%d" % (i + 1), "Step %d" % (i + 1), 0, 100, 50 if i % 2 else 20, "mstep", STEP_X0 + i * STEP_DX,
                STEP_Y, w=40, h=STEP_H) for i in range(16)]
CONTROLS += [
    K("st_steps", "Steps", 1, 16, 16, "mstep", slot(0), 387, intd=True),
    K("st_rate", "Rate", 0, 10, 5, "mstep", slot(1), 387),
    K("st_swing", "Swing", 50, 75, 50, "mstep", slot(2), 387, unit="%", intd=True),
    K("st_rand", "Random", 0, 10, 0, "mstep", slot(3), 387),
    K("st_smooth", "Smooth", 0, 10, 0, "mstep", slot(4), 387),
    T("st_sync", "Sync", 0, "mstep", slot(5), 387),
    E("st_dir", "Direction", ["Forward", "Back", "Ping-Pong", "Random"], 0, "mstep", slot(6), 380, sw=86, sh=44, rows=2),
]
# ---- MOD SOURCES B2: FUNCTION GENERATOR (8 breakpoints)
FUNC_PRESETS = ["Ramp Up", "Ramp Down", "Triangle", "Hump", "S-Curve", "Stairs", "Pulse", "Wobble"]
CONTROLS += [SL("fg_%d" % (i + 1), "Point %d" % (i + 1), 0, 100, 50, "mfunc", 70 + i * 108, 213, w=44, h=265)
             for i in range(8)]
CONTROLS += [
    K("fg_rate", "Rate", 0, 10, 4, "mfunc", slot(0), 445),
    K("fg_scale", "Scale", 0, 100, 100, "mfunc", slot(1), 445, unit="%", intd=True),
    T("fg_bipolar", "Bipolar", 0, "mfunc", slot(2), 445),
    E("fg_preset", "Presets", FUNC_PRESETS, 2, "mfunc", slot(3) + 20, 445, widget="popup", w=240, h=52),
]
# ---- MOD SOURCES B3: GATE SEQUENCER (16 x 2), RANDOM / S&H
GATE_X0, GATE_DX, GATE_Y1, GATE_Y2 = 120, 72, 128, 202
CONTROLS += [T("gt_e%d" % (i + 1), "Env %d" % (i + 1), 1 if i % 4 == 0 else 0, "mgate", GATE_X0 + i * GATE_DX, GATE_Y1,
               bw=60) for i in range(16)]
CONTROLS += [T("gt_l%d" % (i + 1), "Lfo %d" % (i + 1), 1 if i % 8 == 0 else 0, "mgate", GATE_X0 + i * GATE_DX, GATE_Y2,
               bw=60) for i in range(16)]
CONTROLS += [
    K("gt_steps", "Steps", 1, 16, 16, "mgate", slot(0), 352, intd=True),
    K("gt_rate", "Rate", 0, 10, 5, "mgate", slot(1), 352),
    T("gt_sync", "Sync", 0, "mgate", slot(2), 352),
    K("rnd_rate", "Rate", 0, 10, 4, "mgate", slot(4), 352),
    K("rnd_slew", "Slew", 0, 10, 3, "mgate", slot(5), 352),
    T("rnd_sync", "Sync", 0, "mgate", slot(6), 352),
]
# ---- OVERVIEW: the bottom strip's switches and the DATA knob
CONTROLS += [
    T("limit_res", "Limit Res.", 1, "overview", 1060, STRIP_Y + 19, bw=150),
    T("bypass", "Bypass", 0, "overview", 1193, STRIP_Y + 19, bw=150),
    K("data", "Data", 0, 1, 0.5, "overview", DATA_POS[0], DATA_POS[1], r=MED),
]
# ---- MOD MATRIX: the amount of the selected cell
CONTROLS.append(SL("mx_amt", "Amount", -100, 100, 50, "matrix", 363, 558, w=640, h=30, vertical=False))
CTRL = {c["key"]: c for c in CONTROLS}
assert CONTROLS[0]["key"] == "out_level", "parameter 0 is the OUTPUT level"
for _f, _m in MOD_MAP.items():
    for _k in _m:
        assert _k is None or _k in CTRL, _k

# ------------------------------------------------------------------------------------------------ navigation
NAV = [("nav_zoom", "OVERVIEW", 96, 28), ("nav_prev", "<", 208, 28), ("nav_next", ">", 264, 28)]
NAV_SIZE = {"nav_zoom": (160, 44), "nav_prev": (48, 44), "nav_next": (48, 44)}
CHIPS = [("go_bayM", "MODULATION", 116, 79, 200), ("go_bayA", "AUDIO", 327, 79, 200)]   # the patch bay's two modes (bay views)
FILTER_BTNS = [("fm_audio", "EDIT IN BAY", 1170, 489, 170, 40), ("fm_open", "OPEN MATRIX", 1170, 577, 170, 40)]
HDR_TOUCH = (1144, 28, 240)   # the readout box at the top right: the touched control and its value
AUD_BAR = (16, 465, 1248, 47)
MOD_BAR = (16, 523, 1248, 87)
OUT_LED = (1208, 88)

# --------------------------------------------------------------------------------------------- patch bay jacks
JACK_GROUP = 9   # picture switches have at most JACK_GROUP + 1 positions (the Force: nothing above 11 seen working)
JACK_R = 17

# modulation bay: 10 outputs at the left, a 6 x 8 grid of inputs (the 6 destinations of 8 filters)
MO_X, MO_Y0, MO_DY = 227, 152, 40
MI_X0, MI_DX, MI_Y0, MI_DY = 400, 113, 185, 70
AO_X, AO_Y0, AO_DY = 373, 152, 48
AI_X = 907
AUDIO_OUTS = [("in", "IN")] + [(k, FSHORT[k]) for k in FKEYS]
AUDIO_INS = [(k, FSHORT[k]) for k in FKEYS] + [("out", "OUT")]
N_AO, N_AI = len(AUDIO_OUTS), len(AUDIO_INS)


def mod_out_pos(s):
    return (MO_X, MO_Y0 + s * MO_DY)


def mod_in_pos(f, d):
    return (MI_X0 + f * MI_DX, MI_Y0 + d * MI_DY)


def aud_out_pos(a):
    return (AO_X, AO_Y0 + a * AO_DY)


def aud_in_pos(b):
    return (AI_X, AO_Y0 + b * AO_DY)


def a_blocked(a, b):
    """audio out a (0 = IN, 1..8 filters) to audio in b (0..7 filters, 8 = OUT): a filter into itself is a loop"""
    return a == b + 1


PICK_MOD_IN = (62, 56)
PICK_MOD_OUT = (96, 38)
PICK_AUD = (110, 46)
PK_STEPS = ["Off", "Choose", "Pick input", "Pick output", "Connected"]
PK_CANCEL = (1170, 28)
PK_DONE = (330, 440, 250, 66)
PK_UNPLUG = (700, 440, 250, 66)
CABLE_TILE = 128
# the cables' colours: grey, black, white, light blue, light green, light dark green, dark blue (and no others)
CABLE_COLOURS = [(150, 150, 150), (24, 24, 24), (240, 240, 240), (140, 200, 240), (150, 224, 150), (70, 165, 95),
                 (28, 58, 140)]

# ------------------------------------------------------------------------------------------------ matrix
MX_CHIP_X0, MX_CHIP_DX, MX_CHIP_Y = 90, 155, 86
MX_CHIP = (149, 40)
MX_COL_X0, MX_COL_DX = 247, 180
MX_ROW_Y0, MX_ROW_DY = 154, 35
MX_CELL = (172, 32)
MX_BAR = (16, 500, 1248, 98)
MX_BTNS = [("mx_done", "DONE", 943, 558), ("mx_unplug", "UNPLUG", 1070, 558), ("mx_cancel", "CANCEL", 1197, 558)]
MX_BTN = (113, 40)


def mx_cell_pos(s, d):
    return (MX_COL_X0 + d * MX_COL_DX, MX_ROW_Y0 + s * MX_ROW_DY)


def mx_chip_pos(f):
    return (MX_CHIP_X0 + f * MX_CHIP_DX, MX_CHIP_Y)


# ------------------------------------------------------------------------------------------------ Q-Links
OVERVIEW_QLINKS = [f + "_mix" for f in FKEYS] + ["out_level", "out_drive", "out_lo", "out_hi", "out_dw", "lfo_rate",
                                                  "env_dec", "-"]
STEP_QLINKS = ["st_steps", "st_rate", "st_swing", "st_rand", "st_smooth", "st_dir", "st_sync", "-"] + \
              ["st_%d" % (i + 1) for i in range(8)]
FUNC_QLINKS = ["fg_rate", "fg_scale", "fg_bipolar", "fg_preset", "-", "-", "-", "-"] + ["fg_%d" % (i + 1) for i in range(8)]
GATE_QLINKS = ["gt_steps", "gt_rate", "gt_sync", "rnd_rate", "rnd_slew", "rnd_sync", "-", "-"] + \
              ["gt_e%d" % (i + 1) for i in range(4)] + ["gt_l%d" % (i + 1) for i in range(4)]
MATRIX_QLINKS = ["mx_amt"]
assert all(k == "-" or k in CTRL for k in OVERVIEW_QLINKS + STEP_QLINKS + FUNC_QLINKS + GATE_QLINKS + MATRIX_QLINKS)

# the overview status line of each tile is live text (ts_<view>)
TILE_TEXT_Y = 38   # offset from the tile's bottom
