# PhyXXL inventory

Every control and jack, generated from `tools/spec.py` (the build checks the skin against the same list).

## Ms-20 Style Filter  (Highpass + Lowpass)

| Control | Key | Range |
|---|---|---|
| Cutoff | `ms_cut` | -5 .. 5 |
| HP | `ms_hp` | 0 .. 10 |
| HP Peak | `ms_hppk` | 0 .. 10 |
| LP | `ms_lp` | 0 .. 10 |
| LP Peak | `ms_lppk` | 0 .. 10 |
| Stereo | `ms_stereo` | 0 .. 10 |
| Dry / Wet | `ms20_mix` | 0 .. 100 % |
| Pan | `ms20_pan` | -100 .. 100 |
| Out | `ms20_out` | -24 .. 12 dB |

## Sem Style Filter

| Control | Key | Range |
|---|---|---|
| Freq | `sem_freq` | 0 .. 10 |
| Res | `sem_res` | 0 .. 10 |
| Mode | `sem_mode` | 0 .. 10 |
| In Gain | `sem_ingain` | 0 .. 10 |
| In Noise | `sem_innoise` | 0 .. 10 |
| Soft Clip | `sem_clip` | Off / On |
| Dry / Wet | `sem_mix` | 0 .. 100 % |
| Pan | `sem_pan` | -100 .. 100 |
| Out | `sem_out` | -24 .. 12 dB |

## Mini Ladder Filter

| Control | Key | Range |
|---|---|---|
| Drive | `mini_drive` | 0 .. 10 |
| Cutoff | `mini_cut` | 0 .. 10 |
| Emphasis | `mini_emph` | 0 .. 10 |
| Out Vol | `mini_vol` | 0 .. 10 |
| Dry / Wet | `mini_mix` | 0 .. 100 % |
| Pan | `mini_pan` | -100 .. 100 |
| Out | `mini_out` | -24 .. 12 dB |

## Matrix-12 Style Filter

| Control | Key | Range |
|---|---|---|
| Mode | `m12_mode` | 0 .. 14 |
| Cutoff | `m12_cut` | 0 .. 10 |
| Reson. | `m12_res` | 0 .. 10 |
| Dry / Wet | `m12_mix` | 0 .. 100 % |
| Pan | `m12_pan` | -100 .. 100 |
| Out | `m12_out` | -24 .. 12 dB |

## 2600 Style Filter

| Control | Key | Range |
|---|---|---|
| Cutoff | `p26_cut` | 0 .. 10 |
| Res | `p26_res` | 0 .. 10 |
| FM 1 | `p26_fm1` | 0 .. 10 |
| FM 2 | `p26_fm2` | 0 .. 10 |
| FM 3 | `p26_fm3` | 0 .. 10 |
| Type | `p26_type` | 4012 / 4072 / 4075 |
| Dry / Wet | `p26_mix` | 0 .. 100 % |
| Pan | `p26_pan` | -100 .. 100 |
| Out | `p26_out` | -24 .. 12 dB |

## Wasp Style Filter

| Control | Key | Range |
|---|---|---|
| Cutoff | `wasp_cut` | 0 .. 10 |
| Peak | `wasp_peak` | 0 .. 10 |
| Mode | `wasp_mode` | 0 .. 10 |
| In Drive | `wasp_drive` | 0 .. 10 |
| Dry / Wet | `wasp_mix` | 0 .. 100 % |
| Pan | `wasp_pan` | -100 .. 100 |
| Out | `wasp_out` | -24 .. 12 dB |

## Prologue Style Filter

| Control | Key | Range |
|---|---|---|
| Cutoff | `prl_cut` | 0 .. 10 |
| Reson. | `prl_res` | 0 .. 10 |
| Drive | `prl_drive` | 0 .. 10 |
| Key Trk | `prl_trk` | 0 .. 10 |
| EG Int | `prl_eg` | -10 .. 10 |
| Dry / Wet | `prl_mix` | 0 .. 100 % |
| Pan | `prl_pan` | -100 .. 100 |
| Out | `prl_out` | -24 .. 12 dB |

## Polivoks Filter

| Control | Key | Range |
|---|---|---|
| Cutoff | `poli_cut` | 0 .. 10 |
| Res | `poli_res` | 0 .. 10 |
| Drive | `poli_drive` | 0 .. 10 |
| Env Amt | `poli_env` | 0 .. 10 |
| Decay | `poli_decay` | 0 .. 10 |
| Mode | `poli_mode` | LP / BP |
| Dry / Wet | `poli_mix` | 0 .. 100 % |
| Pan | `poli_pan` | -100 .. 100 |
| Out | `poli_out` | -24 .. 12 dB |

## Drive  /  Output

| Control | Key | Range |
|---|---|---|
| Output | `out_level` | -24 .. 12 dB |
| Series | `chain_series` | push |
| Parallel | `chain_par` | push |
| Clear | `chain_clear` | push |
| Drive | `out_drive` | 0 .. 10 |
| Low Cut | `out_lo` | 0 .. 10 |
| High Cut | `out_hi` | 0 .. 10 |
| Dry / Wet | `out_dw` | 0 .. 100 % |
| Mix | `out_mix` | 0 .. 200 % |

## Mod Sources A  /  Lfo  Envelope  Follower

| Control | Key | Range |
|---|---|---|
| Wave | `lfo_wave` | 0 .. 4 |
| Rate | `lfo_rate` | 0 .. 10 |
| Smooth | `lfo_smooth` | 0 .. 10 |
| Sync | `lfo_sync` | Off / On |
| Attack | `env_att` | 0 .. 10 |
| Hold | `env_hold` | 0 .. 10 |
| Decay | `env_dec` | 0 .. 10 |
| Trigger | `env_trig` | Gate Seq / Note / Input |
| Sens. | `foll_sens` | 0 .. 10 |
| Delay | `foll_delay` | 0 .. 10 |
| Rise | `foll_rise` | 0 .. 10 |
| Fall | `foll_fall` | 0 .. 10 |
| Source | `foll_src` | Audio In / After Drive |

## Mod Sources B1  /  Step Sequencer

| Control | Key | Range |
|---|---|---|
| Step 1 | `st_1` | 0 .. 100 |
| Step 2 | `st_2` | 0 .. 100 |
| Step 3 | `st_3` | 0 .. 100 |
| Step 4 | `st_4` | 0 .. 100 |
| Step 5 | `st_5` | 0 .. 100 |
| Step 6 | `st_6` | 0 .. 100 |
| Step 7 | `st_7` | 0 .. 100 |
| Step 8 | `st_8` | 0 .. 100 |
| Step 9 | `st_9` | 0 .. 100 |
| Step 10 | `st_10` | 0 .. 100 |
| Step 11 | `st_11` | 0 .. 100 |
| Step 12 | `st_12` | 0 .. 100 |
| Step 13 | `st_13` | 0 .. 100 |
| Step 14 | `st_14` | 0 .. 100 |
| Step 15 | `st_15` | 0 .. 100 |
| Step 16 | `st_16` | 0 .. 100 |
| Steps | `st_steps` | 1 .. 16 |
| Rate | `st_rate` | 0 .. 10 |
| Swing | `st_swing` | 50 .. 75 % |
| Random | `st_rand` | 0 .. 10 |
| Smooth | `st_smooth` | 0 .. 10 |
| Sync | `st_sync` | Off / On |
| Direction | `st_dir` | Forward / Back / Ping-Pong / Random |

## Mod Sources B2  /  Function Generator

| Control | Key | Range |
|---|---|---|
| Point 1 | `fg_1` | 0 .. 100 |
| Point 2 | `fg_2` | 0 .. 100 |
| Point 3 | `fg_3` | 0 .. 100 |
| Point 4 | `fg_4` | 0 .. 100 |
| Point 5 | `fg_5` | 0 .. 100 |
| Point 6 | `fg_6` | 0 .. 100 |
| Point 7 | `fg_7` | 0 .. 100 |
| Point 8 | `fg_8` | 0 .. 100 |
| Rate | `fg_rate` | 0 .. 10 |
| Scale | `fg_scale` | 0 .. 100 % |
| Bipolar | `fg_bipolar` | Off / On |
| Presets | `fg_preset` | Ramp Up / Ramp Down / Triangle / Hump / S-Curve / Stairs / Pulse / Wobble |

## Mod Sources B3  /  Gate Sequencer  /  Random

| Control | Key | Range |
|---|---|---|
| Env 1 | `gt_e1` | Off / On |
| Env 2 | `gt_e2` | Off / On |
| Env 3 | `gt_e3` | Off / On |
| Env 4 | `gt_e4` | Off / On |
| Env 5 | `gt_e5` | Off / On |
| Env 6 | `gt_e6` | Off / On |
| Env 7 | `gt_e7` | Off / On |
| Env 8 | `gt_e8` | Off / On |
| Env 9 | `gt_e9` | Off / On |
| Env 10 | `gt_e10` | Off / On |
| Env 11 | `gt_e11` | Off / On |
| Env 12 | `gt_e12` | Off / On |
| Env 13 | `gt_e13` | Off / On |
| Env 14 | `gt_e14` | Off / On |
| Env 15 | `gt_e15` | Off / On |
| Env 16 | `gt_e16` | Off / On |
| Lfo 1 | `gt_l1` | Off / On |
| Lfo 2 | `gt_l2` | Off / On |
| Lfo 3 | `gt_l3` | Off / On |
| Lfo 4 | `gt_l4` | Off / On |
| Lfo 5 | `gt_l5` | Off / On |
| Lfo 6 | `gt_l6` | Off / On |
| Lfo 7 | `gt_l7` | Off / On |
| Lfo 8 | `gt_l8` | Off / On |
| Lfo 9 | `gt_l9` | Off / On |
| Lfo 10 | `gt_l10` | Off / On |
| Lfo 11 | `gt_l11` | Off / On |
| Lfo 12 | `gt_l12` | Off / On |
| Lfo 13 | `gt_l13` | Off / On |
| Lfo 14 | `gt_l14` | Off / On |
| Lfo 15 | `gt_l15` | Off / On |
| Lfo 16 | `gt_l16` | Off / On |
| Steps | `gt_steps` | 1 .. 16 |
| Rate | `gt_rate` | 0 .. 10 |
| Sync | `gt_sync` | Off / On |
| Rate | `rnd_rate` | 0 .. 10 |
| Slew | `rnd_slew` | 0 .. 10 |
| Sync | `rnd_sync` | Off / On |

## Mod Matrix

| Control | Key | Range |
|---|---|---|
| Amount | `mx_amt` | -100 .. 100 |

## Modulation: sources and destinations

| Source | Signal |
|---|---|
| LFO | LFO, -1..+1 |
| ENV | Envelope (attack, hold, decay), 0..1 |
| FOLL | Envelope follower of the input, 0..1 |
| STEP | Step sequencer bars |
| FUNC | Function generator |
| GATE | Gate sequencer gate, 0 / 1 |
| RAND | Random sample & hold with slew, -1..+1 |
| MODW | MIDI mod wheel (CC 1), 0..1 |
| VEL | Velocity of the last note, 0..1 |
| KEY | Pitch of the last note, 0..1 over the keyboard |

Each of the 8 filters has 6 destinations, each fed by one source (`md_<filter>_<dest>`) at an amount (`ma_<filter>_<dest>`, -100..+100):

| Filter | CUT | RES | DRV | MODE | PAN | OUT |
|---|---|---|---|---|---|---|
| MS-20 | Cutoff | LP Peak | LP | HP | Pan | Out |
| SEM | Freq | Res | In Gain | Mode | Pan | Out |
| MINI | Cutoff | Emphasis | Drive | Out Vol | Pan | Out |
| M12 | Cutoff | Reson. | (pre-gain) | Mode | Pan | Out |
| 2600 | Cutoff | Res | (pre-gain) | FM 1 | Pan | Out |
| WASP | Cutoff | Peak | In Drive | Mode | Pan | Out |
| PROLOGUE | Cutoff | Reson. | Drive | Key Trk | Pan | Out |
| POLIVOKS | Cutoff | Res | Drive | Env Amt | Pan | Out |

## Audio bay

Outputs: IN, MS20, SEM, MINI, M12, 2600, WASP, PRL, POLI. Inputs: MS20, SEM, MINI, M12, 2600, WASP, PRL, POLI, OUT. Any output into any input; an input sums its cables; a filter into itself, or a loop through other filters, is refused.

163 controls, 48 modulation inputs, 73 audio cables possible.
