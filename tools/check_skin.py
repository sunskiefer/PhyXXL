#!/usr/bin/env python3
"""Checks the built skin against tools/spec.py, the inventory: nothing in the list may be missing from the panel.

    python3 tools/check_skin.py "<skin dir>/Plugin Skins"

- every control is on its page (a component bound to its parameter, shown only while its pg_<view> switch is on);
- every jack (modulation and audio), matrix cell and chip, overview tile has one touch area, at its place, not overlapping;
- every page has its picture; navigation is one instance shown on every section page;
- pop-up lists are wired; every switch has at most 11 positions (nothing larger seen working on a Force);
- the response picture has all its columns; every image the skin names exists.
Exit status 1 with a list of what is missing.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import post_skin as P  # noqa: E402
import spec  # noqa: E402


def main():
    folder = sys.argv[1]
    skin = P.Skin(folder)
    problems = []
    by_param = {}
    images = set()
    boxes = {}
    for inst in skin.page["componentsData"]:
        hs = inst["bounds"]["additionalInvalidatingHandles"]
        for m in inst["handle remapping"]["map"]:
            if m["value"].startswith("Parameter "):
                by_param.setdefault(skin.keys[int(m["value"].split()[1])], []).append((inst, hs))
        if inst["componentData"]["type"] == "Image":
            images.add(inst["componentData"]["data"]["image"])
    for d in skin.defs.values():
        for sub in d.get("componentsData", []):
            data = sub["componentData"].get("data", {})
            for key in ("image", "onImage", "offImage", "filmStrip"):
                if data.get(key):
                    images.add(data[key])

    def on_view(key, view):
        want = "IndexedEnabling/1/2/Parameter %d" % skin.index["pg_" + view]
        return any(want in hs for _, hs in by_param.get(key, []))

    for c in spec.CONTROLS:
        if c["key"] == "mx_amt":   # shared by the matrix and the bay's connected page: shown by amt_on
            if not any("IndexedEnabling/1/2/Parameter %d" % skin.index["amt_on"] in hs for _, hs in by_param.get("mx_amt", [])):
                problems.append("mx_amt is not shown by amt_on")
            continue
        if not on_view(c["key"], c["view"]):
            problems.append("control %s (%s) is not on the %s page" % (c["key"], c["name"], c["view"]))
    for k in spec.TILE_VIEWS:
        if not on_view("go_" + k, "overview"):
            problems.append("no overview tile for %s" % k)

    def touch(key, want=None):
        insts = by_param.get(key, [])
        if len(insts) != 1:
            problems.append("%s: %d touch area(s), want one" % (key, len(insts)))
            return
        b = tuple(P.bounds(insts[0][0]["bounds"]["bounds"]))
        if want and b != tuple(want):
            problems.append("%s: its touch area %s is not where it belongs %s" % (key, b, tuple(want)))
        x, y, w, h = b
        if y < 0 or y + h > P.H or x < 0 or x + w > P.W:
            problems.append("%s is off the page" % key)
        boxes[key] = b

    for k in spec.TILE_VIEWS:
        if k == "bayM":   # the tile and the bay's chip share go_bayM: two areas, one on each page
            if len(by_param.get("go_bayM", [])) != 2:
                problems.append("go_bayM: want the overview tile and the bay chip")
            continue
        touch("go_" + k, spec.TILES[k])
    for i, s in enumerate(spec.SRCS):
        touch("tm_" + s[0], P.rect_for("tm_" + s[0]))
    for f in spec.FKEYS:
        for d in spec.DEST_KEYS:
            touch("ti_%s_%s" % (f, d), P.rect_for("ti_%s_%s" % (f, d)))
    for i in range(spec.N_AO):
        touch("tao_%d" % i, P.rect_for("tao_%d" % i))
    for i in range(spec.N_AI):
        touch("tai_%d" % i, P.rect_for("tai_%d" % i))
    for s in spec.SRCS:
        for d in spec.DEST_KEYS:
            touch("mx_%s_%s" % (s[0], d), P.rect_for("mx_%s_%s" % (s[0], d)))
    for i in range(spec.N_FLT):
        touch("mxf_%d" % i, P.rect_for("mxf_%d" % i))
    # no two touch areas that can be on screen together overlap (the jacks of one bay, the cells and chips, the tiles)
    groups = {
        "mod bay": [k for k in boxes if k.startswith("tm_") or k.startswith("ti_")],
        "audio bay": [k for k in boxes if k.startswith("tao_") or k.startswith("tai_")],
        "matrix": [k for k in boxes if k.startswith("mx_") or k.startswith("mxf_")],
        "overview": [k for k in boxes if k.startswith("go_")],
    }
    for name, ks in groups.items():
        for a in range(len(ks)):
            ax, ay, aw, ah = boxes[ks[a]]
            for b in range(a + 1, len(ks)):
                bx, by, bw, bh = boxes[ks[b]]
                if ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah:
                    problems.append("%s: %s and %s overlap" % (name, ks[a], ks[b]))
    for key, shown in (("pk_cancel", "IndexedEnabling/1/2/Parameter %d" % skin.index["pk_c"]),
                       ("pk_unplug", "IndexedEnabling/4/%d/Parameter %d" % (len(spec.PK_STEPS), skin.index["pk"])),
                       ("pk_done", "IndexedEnabling/4/%d/Parameter %d" % (len(spec.PK_STEPS), skin.index["pk"]))):
        insts = by_param.get(key, [])
        if len(insts) != 1 or shown not in insts[0][1]:
            problems.append("%s: want one button shown by %s" % (key, shown))
    sec = "IndexedEnabling/1/2/Parameter %d" % skin.index["in_sec"]
    for k, _, _, _ in spec.NAV:
        insts = by_param.get(k, [])
        if len(insts) != 1:
            problems.append("%s: %d instance(s), want one shown on every page" % (k, len(insts)))
    for c in spec.CONTROLS:
        if c["kind"] != "enum" or c["widget"] != "popup":
            continue
        pidx = skin.index["pop_" + c["key"]]
        if by_param.get(c["key"] + "__open"):
            problems.append("pop-up %s still bound to the wrapper's %s__open" % (c["key"], c["key"]))
        if not by_param.get("pop_" + c["key"]):
            problems.append("pop-up %s has no arrow on pop_%s" % (c["key"], c["key"]))
        opened = "IndexedEnabling/1/2/Parameter %d" % pidx
        parts = [hs for (_, hs) in by_param.get(c["key"], []) if opened in hs]
        if len(parts) != len(c["options"]):
            problems.append("pop-up %s: %d options shown, want %d" % (c["key"], len(parts), len(c["options"])))
    for i in range(len(spec.VIEWS)):
        if "px_view_%d.png" % i not in images:
            problems.append("no panel picture for view %d" % i)
    for i in range(spec.RC_COLS):
        if len(by_param.get("rc%02d" % i, [])) != 1:
            problems.append("response column %d missing" % i)
    if len(by_param.get("rc_dot", [])) != 1:
        problems.append("response dot ruler missing")
    for inst in skin.page["componentsData"]:
        for h in inst["bounds"]["additionalInvalidatingHandles"]:
            m = re.match(r"IndexedEnabling/(\d+)/(\d+)/Parameter (\d+)$", h)
            if m and int(m.group(2)) > 11:
                problems.append("%s: %s positions (more than the 11 seen working)" % (h, m.group(2)))
    for name in sorted(images):
        if not os.path.exists(os.path.join(folder, name)):
            problems.append("image %s is missing" % name)
    if problems:
        print("check_skin: %d problems" % len(problems))
        for p in sorted(set(problems))[:60]:
            print("  " + p)
        sys.exit(1)
    print("check_skin: OK -- %d controls, %d touch areas, %d pages, %d images" % (
        len(spec.CONTROLS), len(boxes), len(spec.VIEWS), len(images)))


if __name__ == "__main__":
    main()
