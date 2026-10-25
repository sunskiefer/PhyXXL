"""Factory patches. Each: (name, {control: value}, [(audio out, audio in)], [(filter, dest, source, amount)]).

Audio outs are "in" and the filter keys; audio ins are the filter keys and "out". Controls not named take their defaults,
modulation inputs not named are unpatched, so a patch always sounds the same whatever was loaded before.
"""
F = ["ms20", "sem", "mini", "m12", "p26", "wasp", "prl", "poli"]


def chain(*names):
    names = list(names)
    return [(a, b) for a, b in zip(["in"] + names, names + ["out"])]


def par(*names):
    return [("in", n) for n in names] + [(n, "out") for n in names]


PRESETS = [
    ("Init: MS-20 Only", {}, chain("ms20"), []),
    ("Init: SEM Only", {}, chain("sem"), []),
    ("Init: Mini Only", {}, chain("mini"), []),
    ("Init: M12 Only", {}, chain("m12"), []),
    ("Init: 2600 Only", {}, chain("p26"), []),
    ("Init: Wasp Only", {}, chain("wasp"), []),
    ("Init: Prologue Only", {}, chain("prl"), []),
    ("Init: Polivoks Only", {}, chain("poli"), []),
    ("Slow Sweep (MS-20)", {"ms_lp": 5, "ms_lppk": 6, "lfo_rate": 2}, chain("ms20"), [("ms20", "cut", "lfo", 60)]),
    ("Ladder Wah (Mini)", {"mini_cut": 4, "mini_emph": 6, "env_trig": 2, "env_dec": 3},
     chain("mini"), [("mini", "cut", "foll", 70)]),
    ("Pulse Gate (SEM)", {"sem_freq": 5, "sem_res": 4, "gt_rate": 6}, chain("sem"),
     [("sem", "out", "gate", 100), ("sem", "cut", "env", 40)]),
    ("Step Filter (Wasp)", {"wasp_cut": 4, "wasp_peak": 6, "st_rate": 6}, chain("wasp"), [("wasp", "cut", "step", 80)]),
    ("Random Walk (M12)", {"m12_mode": 9, "m12_res": 5, "rnd_rate": 3}, chain("m12"),
     [("m12", "cut", "rand", 60), ("m12", "pan", "rand", 40)]),
    ("Function Swell (Poli)", {"poli_cut": 3, "poli_res": 5, "fg_rate": 2}, chain("poli"), [("poli", "cut", "func", 80)]),
    ("Series: Mini > MS-20", {"mini_cut": 6, "ms_lp": 7}, chain("mini", "ms20"), []),
    ("Series: Wasp > Mini > SEM", {}, chain("wasp", "mini", "sem"), []),
    ("Series: Prologue > Poli", {"prl_res": 4, "poli_res": 4}, chain("prl", "poli"), []),
    ("Parallel: SEM + Mini", {"sem_mix": 100, "mini_mix": 100, "sem_pan": -50, "mini_pan": 50}, par("sem", "mini"), []),
    ("Parallel: MS-20 + Wasp", {"ms_stereo": 5, "wasp_mode": 3}, par("ms20", "wasp"), []),
    ("Wide Four", {"sem_pan": -80, "mini_pan": -30, "m12_pan": 30, "p26_pan": 80}, par("sem", "mini", "m12", "p26"), []),
    ("Split And Merge", {}, [("in", "sem"), ("in", "mini"), ("sem", "ms20"), ("mini", "ms20"), ("ms20", "out")], []),
    ("Notch Phase (SEM > M12)", {"sem_mode": 3, "m12_mode": 12}, chain("sem", "m12"),
     [("sem", "cut", "lfo", 50), ("m12", "cut", "lfo", -50)]),
    ("Bass Tightener", {"ms_lp": 4, "ms_hp": 2, "mini_cut": 3}, chain("ms20", "mini"), []),
    ("Screaming 2600", {"p26_res": 8, "p26_fm1": 4, "p26_type": 0}, chain("p26"), [("p26", "cut", "lfo", 40)]),
    ("Dirty Polivoks", {"poli_drive": 8, "poli_res": 7, "poli_env": 6}, chain("poli"), [("poli", "drv", "env", 40)]),
    ("Drum Bus Squash", {"out_drive": 4, "mini_drive": 6, "mini_cut": 7}, chain("mini"), [("mini", "cut", "env", 50)]),
    ("Vowel Morph", {"m12_mode": 8, "m12_res": 7, "sem_res": 7}, par("m12", "sem"),
     [("m12", "cut", "lfo", 70), ("sem", "cut", "lfo", -70)]),
    ("Velocity Opens (Prologue)", {"prl_cut": 3, "prl_eg": 6}, chain("prl"), [("prl", "cut", "vel", 70)]),
]
assert len({p[0] for p in PRESETS}) == len(PRESETS)
