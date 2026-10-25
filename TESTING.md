# Testing PhyXXL

Built and checked offline only: the engine compiles and links for armv7 (Zig, glibc 2.31), the skin passes
`tools/check_skin.py`, the release zip passes `catalog_check.py --catalog` and `sh -n` on the installers.
Nothing has been run on a Force or an MPC. **No `tested.json` until a device run.**

| # | Check on the device | Result |
|---|---|---|
| 1 | Plugin loads as an effect; audio passes with the default patch (IN > MS-20 > OUT) | |
| 2 | Each filter page: knobs move the sound, the response picture follows | |
| 3 | Overview: tiles open pages; < > step; meters and CPU move | |
| 4 | Audio bay: tap output, tap input, CONNECTED page, DONE; UNPLUG; loops refused | |
| 5 | Modulation bay and matrix: patch LFO to cutoff, amount slider, UNPLUG | |
| 6 | Step, function and gate sequencers run; lamps follow | |
| 7 | Presets load with their cables | |
| 8 | Project save / reload keeps controls and cables | |
| 9 | CPU and memory with all eight filters in series | |
