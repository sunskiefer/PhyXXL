// SPDX-License-Identifier: GPL-3.0-or-later
// PhyXXL -- a multi-filter effect for MPC OS (mpc-vst-plugins engine). Eight filter modules, audio routable from any
// filter into any other, ten modulation sources routed to six destinations of every filter, patched by touch.
//
//   in -> [any filters, any order, summed where cables meet] -> out -> drive / low cut / high cut / width -> dry-wet
//
// The UI side lives here too: the page ('view'), the patch bays' tap-tap patching, the matrix, the status texts and 16
// Q-Link knobs that follow the page on screen. The DSP is src/phy_dsp.h.
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <new>

extern "C" {
#include "engine.h"
}
#include "param_ids.h"
#include "denormals.h"
#include "limiter.h"
#include "phy_dsp.h"

namespace {

using namespace phy;

const int SUB = 32;   // modulation and filter coefficients are updated every 32 samples (0.7 ms)

enum { F_MS20, F_SEM, F_MINI, F_M12, F_P26, F_WASP, F_PRL, F_POLI };
static const short MIX_P[N_FLT] = {P_MS20_MIX, P_SEM_MIX, P_MINI_MIX, P_M12_MIX, P_P26_MIX, P_WASP_MIX, P_PRL_MIX, P_POLI_MIX};
static const short PAN_P[N_FLT] = {P_MS20_PAN, P_SEM_PAN, P_MINI_PAN, P_M12_PAN, P_P26_PAN, P_WASP_PAN, P_PRL_PAN, P_POLI_PAN};
static const short OUT_P[N_FLT] = {P_MS20_OUT, P_SEM_OUT, P_MINI_OUT, P_M12_OUT, P_P26_OUT, P_WASP_OUT, P_PRL_OUT, P_POLI_OUT};

struct Bank {
  Ms20 ms; Sem sem; Mini mini; M12 m12; P26 p26; Wasp wasp; Prl prl; Poli poli;
  Dc dc;
  void reset() { ms.reset(); sem.reset(); mini.reset(); m12.reset(); p26.reset(); wasp.reset(); prl.reset(); poli.reset(); dc.reset(); }
};

struct Plug {
  float pv[P_COUNT];                // parameter values (native units; options = index)
  int view = 0;
  // patch-bay UI
  int pk = 0;                       // 0 off, 1 choose, 2 an output waits, 3 an input waits, 4 connected
  int held_out = -1, held_in = -1;  // the waiting jack (mod: source / input index f*6+d; audio: out / in index)
  int sel_f = -1, sel_d = -1;       // the selected modulation input (matrix cell or the bay's connected page)
  unsigned rev = 1;
  char info[96], touch[96];
  int last_touch = -1;
  bool pop_open = false;

  // audio graph
  bool acc[N_AO][N_AI];             // accepted cables (loop-free)
  int order[N_FLT], n_order = 0;
  bool active[N_FLT], was_active[N_FLT];
  // modulation
  float srcv[N_SRC];
  Rng rng;
  Lfo lfo; Env env; Follower foll; StepSeq step; FuncGen func; GateSeq gate; RandomSh rnd;
  float modw = 0, vel = 0.8f, keyn = 60;
  bool note_trig = false;
  float last_peak_in = 0, last_peak_out = 0;
  float bpm = 120.0f;
  bool transport = false;
  // filters
  Bank bank[N_FLT][2];
  float f_hz[N_FLT], f_res[N_FLT];
  // output
  plateau::Limiter lim;
  Dc odc[2];
  float lo_s[2], hi_s[2];
  float dl[2][SUB], fo[N_FLT][2][SUB];
  float meter_in = 0, meter_out = 0;
  int lamp_in = 0, lamp_out = 0, lamp_clip = 0, lamp_env = 0, lamp_step = 0, lamp_gate = 0;
  int clip_hold = 0;
  float cpu = 0;
  int lamp_clock = 0;
  bool lamp_dirty = false;

  void init() {
    for (int i = 0; i < P_COUNT; i++) pv[i] = P_DEF[i];
    memset(acc, 0, sizeof acc);
    memset(active, 0, sizeof active);
    memset(was_active, 0, sizeof was_active);
    memset(srcv, 0, sizeof srcv);
    for (int f = 0; f < N_FLT; f++) { f_hz[f] = 1000; f_res[f] = 0; for (int c = 0; c < 2; c++) bank[f][c].reset(); }
    for (int c = 0; c < 2; c++) { bank[F_SEM][c].sem.rng = &rng; odc[c].reset(); lo_s[c] = hi_s[c] = 0; }
    lfo.rng = &rng; step.rng = &rng; rnd.rng = &rng;
    lim.Init();
    snprintf(info, sizeof info, "Tap a jack, then the other end of the cable.");
    touch[0] = 0;
    // the default patch: in -> MS-20 -> out
    pv[F_AC + 0 * N_AI + 0] = 1;
    pv[F_AC + 0 * N_AI + 8] = 0;
    rebuild();
    apply_all();
  }

  inline float P(int i) const { return pv[i]; }
  inline int Pi(int i) const { return (int)lroundf(pv[i]); }
  inline bool on(int i) const { return Pi(i) != 0; }
  void bump() { rev++; }

  void apply_all() {}

  // ---- audio graph ---------------------------------------------------------------------------------------------------
  bool reach(int from, int to) const {   // can filter `from` reach filter `to` through accepted cables
    if (from == to) return true;
    bool seen[N_FLT] = {};
    int stack[N_FLT], sp = 0;
    stack[sp++] = from; seen[from] = true;
    while (sp) {
      int x = stack[--sp];
      for (int y = 0; y < N_FLT; y++)
        if (acc[x + 1][y] && !seen[y]) { if (y == to) return true; seen[y] = true; stack[sp++] = y; }
    }
    return false;
  }
  bool would_loop(int a, int b) const { return b < N_FLT && a >= 1 && (a - 1 == b || reach(b, a - 1)); }

  void rebuild() {
    memset(acc, 0, sizeof acc);
    for (int a = 0; a < N_AO; a++)
      for (int b = 0; b < N_AI; b++)
        if (on(F_AC + a * N_AI + b) && !would_loop(a, b)) acc[a][b] = true;
    // topological order over the filters (a filter after everything that feeds it)
    bool done[N_FLT] = {};
    n_order = 0;
    for (int pass = 0; pass < N_FLT; pass++)
      for (int f = 0; f < N_FLT; f++) {
        if (done[f]) continue;
        bool ready = true;
        for (int a = 1; a < N_AO; a++) if (acc[a][f] && !done[a - 1]) ready = false;
        if (ready) { done[f] = true; order[n_order++] = f; }
      }
    bool fed[N_FLT] = {}, to_out[N_FLT] = {};
    for (int i = 0; i < n_order; i++) {
      int f = order[i];
      for (int a = 0; a < N_AO; a++) if (acc[a][f] && (a == 0 || fed[a - 1])) fed[f] = true;
    }
    for (int i = n_order - 1; i >= 0; i--) {
      int f = order[i];
      if (acc[f + 1][N_FLT]) to_out[f] = true;
      for (int b = 0; b < N_FLT; b++) if (acc[f + 1][b] && to_out[b]) to_out[f] = true;
    }
    for (int f = 0; f < N_FLT; f++) active[f] = fed[f] && to_out[f];
  }

  int n_cables_audio() const { int n = 0; for (int a = 0; a < N_AO; a++) for (int b = 0; b < N_AI; b++) n += acc[a][b]; return n; }
  int n_mod(int f) const { int n = 0; for (int d = 0; d < N_DEST; d++) n += Pi(F_MD + f * N_DEST + d) != 0; return n; }
  int n_mod_all() const { int n = 0; for (int f = 0; f < N_FLT; f++) n += n_mod(f); return n; }

  void set_cable(int a, int b, bool v) {
    if (v && (a == b + 1)) return;   // a filter into itself
    pv[F_AC + a * N_AI + b] = v ? 1.0f : 0.0f;
    rebuild();
    bump();
  }
  void clear_audio() {
    for (int i = 0; i < N_AO * N_AI; i++) pv[F_AC + i] = 0;
    rebuild(); bump();
  }
  void chain_set(bool series) {
    int use[N_FLT], n = 0;
    for (int f = 0; f < N_FLT; f++) if (active[f]) use[n++] = f;
    if (n == 0) for (int f = 0; f < N_FLT; f++) use[n++] = f;
    for (int i = 0; i < N_AO * N_AI; i++) pv[F_AC + i] = 0;
    if (series) {
      pv[F_AC + 0 * N_AI + use[0]] = 1;
      for (int i = 0; i + 1 < n; i++) pv[F_AC + (use[i] + 1) * N_AI + use[i + 1]] = 1;
      pv[F_AC + (use[n - 1] + 1) * N_AI + N_FLT] = 1;
    } else {
      for (int i = 0; i < n; i++) { pv[F_AC + 0 * N_AI + use[i]] = 1; pv[F_AC + (use[i] + 1) * N_AI + N_FLT] = 1; }
    }
    rebuild(); bump();
    snprintf(info, sizeof info, series ? "Series chain made." : "Parallel chain made.");
  }

  // ---- MIDI ----------------------------------------------------------------------------------------------------------
  void midi(const uint8_t *m, int len) {
    if (len < 1) return;
    int st = m[0] & 0xF0;
    int d1 = len > 1 ? m[1] & 127 : 0, d2 = len > 2 ? m[2] & 127 : 0;
    if (st == 0x90 && d2 > 0) { vel = d2 / 127.0f; keyn = (float)d1; note_trig = true; }
    else if (st == 0xB0 && d1 == 1) modw = d2 / 127.0f;
  }

  // ---- modulation ------------------------------------------------------------------------------------------------------
  float sync_hz(bool sync, float rate10, float free_hz) const {
    if (!sync) return free_hz;
    int idx = (int)clampf(roundf(rate10), 0, 10);
    return bpm / 60.0f / DIV_BEATS[idx];
  }

  void modulation(int n, float in_peak) {
    // gate sequencer: triggers the envelope, restarts the LFO
    bool ge[16], gl[16];
    for (int i = 0; i < 16; i++) { ge[i] = on(P_GT_E1 + i); gl[i] = on(P_GT_L1 + i); }
    int gsteps = (int)clampf(pv[P_GT_STEPS], 1, 16);
    float ghz = sync_hz(on(P_GT_SYNC), pv[P_GT_RATE], rate_hz(pv[P_GT_RATE]));
    bool gst = gate.run(ge, gl, gsteps, ghz, n);
    int trig = Pi(P_ENV_TRIG);
    bool fire = false;
    if (gst && gate.lfo_on) lfo.restart();
    if (trig == 0 && gst && gate.env_on) fire = true;
    if (trig == 1 && note_trig) fire = true;
    if (trig == 2 && in_peak > 0.08f && in_peak > last_peak_in * 2.0f) fire = true;
    note_trig = false;
    if (fire) env.trigger();
    last_peak_in = in_peak * 0.5f + last_peak_in * 0.5f;
    // LFO
    lfo.wave = Pi(P_LFO_WAVE);
    float lhz = sync_hz(on(P_LFO_SYNC), pv[P_LFO_RATE], 0.05f * exp2f(pv[P_LFO_RATE] * 0.8f));
    srcv[0] = lfo.run(lhz, n, pv[P_LFO_SMOOTH]);
    // envelope
    srcv[1] = env.run(pot_time(pv[P_ENV_ATT]), pot_time(pv[P_ENV_HOLD]) * 2.0f, pot_time(pv[P_ENV_DEC]), n);
    // follower
    float fp = Pi(P_FOLL_SRC) == 0 ? in_peak : last_peak_out;
    srcv[2] = foll.run(fp, pv[P_FOLL_SENS], pv[P_FOLL_DELAY], pv[P_FOLL_RISE], pv[P_FOLL_FALL], n);
    // step sequencer
    float bars[16];
    for (int i = 0; i < 16; i++) bars[i] = pv[P_ST_1 + i];
    float shz = sync_hz(on(P_ST_SYNC), pv[P_ST_RATE], rate_hz(pv[P_ST_RATE]));
    bool stepped = false;
    srcv[3] = step.run(bars, (int)clampf(pv[P_ST_STEPS], 1, 16), Pi(P_ST_DIR), shz, pv[P_ST_SWING] * 0.01f, pv[P_ST_RAND],
                       pv[P_ST_SMOOTH], n, &stepped);
    // function generator
    float pts[8];
    for (int i = 0; i < 8; i++) pts[i] = pv[P_FG_1 + i];
    float fv = func.run(pts, 0.05f * exp2f(pv[P_FG_RATE] * 0.8f), n) * pv[P_FG_SCALE] * 0.01f;
    srcv[4] = on(P_FG_BIPOLAR) ? fv * 2.0f - 1.0f : fv;
    // gate
    srcv[5] = gate.gate ? 1.0f : 0.0f;
    // random
    srcv[6] = rnd.run(sync_hz(on(P_RND_SYNC), pv[P_RND_RATE], rate_hz(pv[P_RND_RATE])), pv[P_RND_SLEW], n);
    srcv[7] = modw;
    srcv[8] = vel;
    srcv[9] = clampf((keyn - 36.0f) / 60.0f, 0, 1);
  }

  // the effective value of the knob a destination moves on filter f
  float eff(int f, int dest) const {
    int p = MOD_PARAM[f][dest];
    int s = Pi(F_MD + f * N_DEST + dest);
    if (p < 0) return 0;
    float v = pv[p];
    if (s > 0) {
      float amt = pv[F_MA + f * N_DEST + dest] * 0.01f;
      v += srcv[s - 1] * amt * (P_MAX[p] - P_MIN[p]) * 0.5f;
      v = clampf(v, P_MIN[p], P_MAX[p]);
    }
    if (dest == 1 && on(P_LIMIT_RES) && v > 9.0f) v = 9.0f;
    return v;
  }
  float pregain(int f) const {
    if (MOD_PARAM[f][2] >= 0) return 1.0f;
    int s = Pi(F_MD + f * N_DEST + 2);
    if (s == 0) return 1.0f;
    return clampf(1.0f + srcv[s - 1] * pv[F_MA + f * N_DEST + 2] * 0.01f, 0.0f, 2.5f);
  }
  float pan_of(int f) const {
    float v = pv[PAN_P[f]];
    int s = Pi(F_MD + f * N_DEST + 4);
    if (s) v += srcv[s - 1] * pv[F_MA + f * N_DEST + 4];
    return clampf(v, -100, 100) * 0.01f;
  }
  float out_db_of(int f) const {
    float v = pv[OUT_P[f]];
    int s = Pi(F_MD + f * N_DEST + 5);
    if (s) v += srcv[s - 1] * pv[F_MA + f * N_DEST + 5] * 0.24f;
    return clampf(v, -60, 12);
  }

  void set_filter(int f, int c, const float *e) {
    Bank &b = bank[f][c];
    float side = c == 0 ? -1.0f : 1.0f;   // the stereo spread of the MS-20 STEREO knob
    switch (f) {
      case F_MS20: b.ms.set(e[0], e[3], pv[P_MS_HPPK], e[2], e[1], side * pv[P_MS_STEREO] * 0.03f); break;
      case F_SEM: b.sem.set(e[0], e[1], e[3], e[2], pv[P_SEM_INNOISE], on(P_SEM_CLIP), 0); break;
      case F_MINI: b.mini.set(e[2], e[0], e[1], e[3], 0); break;
      case F_M12: b.m12.set(e[3], e[0], e[1], 0); break;
      case F_P26: {
        float oct = (e[3] * srcv[0] + pv[P_P26_FM2] * srcv[1] + pv[P_P26_FM3] * srcv[2]) * 0.1f * 3.0f;
        b.p26.set(e[0], e[1], oct, Pi(P_P26_TYPE), 0);
        break;
      }
      case F_WASP: b.wasp.set(e[0], e[1], e[3], e[2], 0); break;
      case F_PRL: {
        float trk = e[3] * 0.1f * ((keyn - 60.0f) / 12.0f);
        float eg = pv[P_PRL_EG] * 0.1f * srcv[1] * 4.0f;
        b.prl.set(e[0], e[1], e[2], trk + eg, 0);
        break;
      }
      default: b.poli.set(e[0], e[1], e[2], e[3], pv[P_POLI_DECAY], Pi(P_POLI_MODE) == 1, 0); break;
    }
  }
  inline float tick_filter(int f, int c, float x) {
    Bank &b = bank[f][c];
    switch (f) {
      case F_MS20: return b.ms.tick(x);
      case F_SEM: return b.sem.tick(x);
      case F_MINI: return b.mini.tick(x);
      case F_M12: return b.m12.tick(x);
      case F_P26: return b.p26.tick(x);
      case F_WASP: return b.wasp.tick(x);
      case F_PRL: return b.prl.tick(x);
      default: return b.poli.tick(x);
    }
  }

  void run_filter(int f, int n, const float in[2][SUB], float out[2][SUB]) {
    float e[4];
    for (int d = 0; d < 4; d++) e[d] = eff(f, d);
    f_res[f] = e[1];
    float pg = pregain(f);
    for (int c = 0; c < 2; c++) set_filter(f, c, e);
    Bank &b0 = bank[f][0];
    switch (f) {
      case F_MS20: f_hz[f] = b0.ms.lp_hz; break;
      case F_SEM: f_hz[f] = b0.sem.hz; break;
      case F_MINI: f_hz[f] = b0.mini.hz; break;
      case F_M12: f_hz[f] = b0.m12.hz; break;
      case F_P26: f_hz[f] = b0.p26.hz; break;
      case F_WASP: f_hz[f] = b0.wasp.hz; break;
      case F_PRL: f_hz[f] = b0.prl.hz; break;
      default: f_hz[f] = b0.poli.hz; break;
    }
    float mix = pv[MIX_P[f]] * 0.01f;
    float pan = pan_of(f);
    float gl = pan > 0 ? 1.0f - pan : 1.0f, gr = pan < 0 ? 1.0f + pan : 1.0f;
    float og = powf(10.0f, out_db_of(f) * 0.05f);
    for (int c = 0; c < 2; c++) {
      float g = (c == 0 ? gl : gr) * og;
      for (int i = 0; i < n; i++) {
        float x = in[c][i];
        float y = tick_filter(f, c, x * pg);
        y = bank[f][c].dc.tick(y);
        if (bad(y)) { bank[f][c].reset(); y = 0; }
        out[c][i] = (x * (1.0f - mix) + y * mix) * g;
      }
    }
  }

  // ---- process -------------------------------------------------------------------------------------------------------------
  float bufl[128], bufr[128];

  void sub_block(const int16_t *in, int n, float *ol, float *or_) {
    float inb[2][SUB];
    float pk = 0;
    for (int i = 0; i < n; i++) {
      float l = in[i * 2] * (1.0f / 32768.0f), r = in[i * 2 + 1] * (1.0f / 32768.0f);
      inb[0][i] = l; inb[1][i] = r;
      float a = fmaxf(fabsf(l), fabsf(r));
      if (a > pk) pk = a;
    }
    if (pk > meter_in) meter_in = pk;
    modulation(n, pk);
    float fout[N_FLT][2][SUB];
    for (int k = 0; k < n_order; k++) {
      int f = order[k];
      if (!active[f]) { was_active[f] = false; continue; }
      if (!was_active[f]) { for (int c = 0; c < 2; c++) bank[f][c].reset(); was_active[f] = true; }
      float sum[2][SUB];
      memset(sum, 0, sizeof sum);
      for (int a = 0; a < N_AO; a++) {
        if (!acc[a][f]) continue;
        if (a == 0) { for (int c = 0; c < 2; c++) for (int i = 0; i < n; i++) sum[c][i] += inb[c][i]; }
        else if (active[a - 1]) { for (int c = 0; c < 2; c++) for (int i = 0; i < n; i++) sum[c][i] += fout[a - 1][c][i]; }
      }
      run_filter(f, n, sum, fout[f]);
    }
    for (int i = 0; i < n; i++) { ol[i] = 0; or_[i] = 0; }
    for (int a = 0; a < N_AO; a++) {
      if (!acc[a][N_FLT]) continue;
      if (a == 0) for (int i = 0; i < n; i++) { ol[i] += inb[0][i]; or_[i] += inb[1][i]; }
      else if (active[a - 1]) for (int i = 0; i < n; i++) { ol[i] += fout[a - 1][0][i]; or_[i] += fout[a - 1][1][i]; }
    }
    // the wet bus: drive, low cut, high cut, width, dry / wet
    float drv = pv[P_OUT_DRIVE];
    float dg = 1.0f + drv * 0.6f, mk = 1.0f / (0.5f + 0.5f * dg);
    float lo = pv[P_OUT_LO] <= 0.05f ? 0.0f : stage_alpha(20.0f * exp2f(pv[P_OUT_LO] * 0.62f));
    float hi = pv[P_OUT_HI] >= 9.95f ? 1.0f : stage_alpha(250.0f * exp2f(pv[P_OUT_HI] * 0.64f));
    float width = pv[P_OUT_MIX] * 0.01f, dw = pv[P_OUT_DW] * 0.01f;
    for (int i = 0; i < n; i++) {
      float s[2] = {ol[i], or_[i]};
      for (int c = 0; c < 2; c++) {
        float x = s[c];
        if (drv > 0.05f) x = fast_tanh(x * dg) * mk;
        if (lo > 0.0f) { float v = (x - lo_s[c]) * lo; float y = v + lo_s[c]; lo_s[c] = y + v; x = x - y; }   // one-pole high pass
        if (hi < 1.0f) { float v = (x - hi_s[c]) * hi; float y = v + hi_s[c]; hi_s[c] = y + v; x = y; }       // one-pole low pass
        s[c] = x;
      }
      float m = (s[0] + s[1]) * 0.5f, d = (s[0] - s[1]) * 0.5f * width;
      s[0] = m + d; s[1] = m - d;
      float dryl = inb[0][i], dryr = inb[1][i];
      ol[i] = dryl * (1.0f - dw) + s[0] * dw;
      or_[i] = dryr * (1.0f - dw) + s[1] * dw;
    }
  }

  void process(const int16_t *in, int16_t *out, int frames) {
    ScopedDenormalDisable dg;
    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    int done = 0;
    float pin = 0;
    while (done < frames) {
      int n = frames - done < SUB ? frames - done : SUB;
      sub_block(in + done * 2, n, bufl + done, bufr + done);
      done += n;
    }
    float gain = powf(10.0f, pv[P_OUT_LEVEL] * 0.05f);
    bool byp = on(P_BYPASS);
    float pk = 0;
    for (int i = 0; i < frames; i++) {
      float l = bufl[i] * gain, r = bufr[i] * gain;
      if (byp) { l = in[i * 2] * (1.0f / 32768.0f); r = in[i * 2 + 1] * (1.0f / 32768.0f); }
      l = odc[0].tick(l); r = odc[1].tick(r);
      if (bad(l)) l = 0;
      if (bad(r)) r = 0;
      bufl[i] = l; bufr[i] = r;
      float a = fmaxf(fabsf(l), fabsf(r));
      if (a > pk) pk = a;
    }
    pin = pk;
    lim.Process(bufl, bufr, frames, 0.0f, -0.3f, 80.0f, SR);
    float po = 0;
    for (int i = 0; i < frames; i++) {
      float a = bufl[i] * 32767.0f, b = bufr[i] * 32767.0f;
      float m = fmaxf(fabsf(bufl[i]), fabsf(bufr[i]));
      if (m > po) po = m;
      out[i * 2] = (int16_t)(a > 32767.0f ? 32767 : a < -32768.0f ? -32768 : lrintf(a));
      out[i * 2 + 1] = (int16_t)(b > 32767.0f ? 32767 : b < -32768.0f ? -32768 : lrintf(b));
    }
    last_peak_out = po;
    if (po > meter_out) meter_out = po;
    if (pin > 1.0f) clip_hold = 8;
    clock_gettime(CLOCK_MONOTONIC, &t1);
    double dt = (t1.tv_sec - t0.tv_sec) + (t1.tv_nsec - t0.tv_nsec) * 1e-9;
    float load = (float)(dt / (frames / (double)SR));
    cpu += (load - cpu) * 0.05f;
    // the lamps and meters, reported to the screen at most every 100 ms
    lamp_clock += frames;
    if (lamp_clock >= 4410) {
      lamp_clock = 0;
      auto seg = [](float p) { float db = 20.0f * log10f(fmaxf(p, 1e-5f)); return (int)clampf((db + 54.0f) / 6.0f, 0, 8.0f); };
      int mi = seg(meter_in), mo = seg(meter_out);
      meter_in *= 0.5f; meter_out *= 0.5f;
      int clip = clip_hold > 0 ? 1 : 0;
      if (clip_hold > 0) clip_hold--;
      int env_l = env.stage != 0 ? 1 : 0;
      int stp = step.lit > 8 ? 0 : step.lit;   // lamps of the step sequencer, 1..16 (two switches)
      int cpu_pct = (int)(cpu * 100.0f);
      if (view == V_OVERVIEW && (mi != lamp_in || mo != lamp_out)) { lamp_dirty = true; }
      if (view == V_OVERVIEW && cpu_pct != lamp_gate) { lamp_dirty = true; lamp_gate = cpu_pct; }
      if (view == V_OUT && clip != lamp_clip) lamp_dirty = true;
      if (view == V_MODA && env_l != lamp_env) lamp_dirty = true;
      if ((view == V_MSTEP && step.lit != lamp_step) || (view == V_MGATE && gate.pos + 1 != lamp_step)) lamp_dirty = true;
      lamp_in = mi; lamp_out = mo; lamp_clip = clip; lamp_env = env_l;
      lamp_step = view == V_MGATE ? gate.pos + 1 : step.lit;
      (void)stp;
      if ((++curve_tick & 1) == 0 && curve_calc()) lamp_dirty = true;   // the picture: at most every 200 ms, only when it moved
      if (lamp_dirty) { lamp_dirty = false; bump(); }
    }
  }

  // ---- UI: views --------------------------------------------------------------------------------------------------------------
  bool is_bay(int v) const { return v == V_BAYM || v == V_BAYA; }

  void set_view(int v) {
    if (v < 0 || v >= N_VIEWS || v == view) return;
    view = v;
    pop_open = false;
    touch[0] = 0;
    held_out = held_in = -1;
    pk = is_bay(v) ? 1 : 0;
    if (v != V_MATRIX && v != V_BAYM) { sel_f = sel_d = -1; }
    if (v == V_MATRIX && sel_f >= 0) sel_f = sel_d = -1;
    if (is_bay(v)) snprintf(info, sizeof info, "Tap a jack, then the other end of the cable.");
    bump();
  }

  void sync_amount() {
    if (sel_f >= 0) pv[P_MX_AMT] = pv[F_MA + sel_f * N_DEST + sel_d];
  }

  // ---- the modulation bay
  void show_mod_pair(int f, int d) {
    sel_f = f; sel_d = d; pk = 4; held_out = held_in = -1;
    sync_amount();
    int s = Pi(F_MD + f * N_DEST + d) - 1;
    snprintf(info, sizeof info, "%s  >  %s %s", s >= 0 ? SRC_LABEL[s] : "-", FLT_LABEL[f], DEST_LABEL[d]);
    bump();
  }
  void cancel_pick() {
    held_out = held_in = -1; sel_f = sel_d = -1;
    pk = is_bay(view) ? 1 : 0;
    snprintf(info, sizeof info, "Tap a jack, then the other end of the cable.");
    bump();
  }
  void unplug_pair() {
    if (pk == 4 && view == V_BAYM && sel_f >= 0) {
      pv[F_MD + sel_f * N_DEST + sel_d] = 0;
      snprintf(info, sizeof info, "%s %s unplugged", FLT_LABEL[sel_f], DEST_LABEL[sel_d]);
      sel_f = sel_d = -1; pk = 1; bump();
    } else if (pk == 4 && view == V_BAYA && held_out >= 0 && held_in >= 0) {
      set_cable(held_out, held_in, false);
      snprintf(info, sizeof info, "%s to %s unplugged", AO_LABEL[held_out], AI_LABEL[held_in]);
      held_out = held_in = -1; pk = 1; bump();
    } else cancel_pick();
  }
  void done_pick() { cancel_pick(); }

  void pick_mod(bool is_out, int idx) {
    if (view != V_BAYM || pk < 1 || pk > 3) return;
    if (is_out) {
      if (pk == 1 || pk == 2) {
        if (pk == 2 && idx == held_out) { cancel_pick(); return; }
        held_out = idx; pk = 2;
        snprintf(info, sizeof info, "%s: now tap an input  (%s)", SRC_LABEL[idx], "any filter's CUT RES DRV MODE PAN OUT");
      } else {   // an input waits for an output
        int f = held_in / N_DEST, d = held_in % N_DEST;
        pv[F_MD + held_in] = (float)(idx + 1);
        show_mod_pair(f, d);
        return;
      }
    } else {
      int f = idx / N_DEST, d = idx % N_DEST;
      if (pk == 2) {
        pv[F_MD + idx] = (float)(held_out + 1);
        show_mod_pair(f, d);
        return;
      }
      if (pk == 3) { if (idx == held_in) cancel_pick(); return; }
      if (Pi(F_MD + idx) != 0) { show_mod_pair(f, d); return; }
      held_in = idx; pk = 3;
      snprintf(info, sizeof info, "%s %s: now tap a source", FLT_LABEL[f], DEST_LABEL[d]);
    }
    bump();
  }

  // ---- the audio bay
  void pick_aud(bool is_out, int idx) {
    if (view != V_BAYA || pk < 1 || pk > 3) return;
    if (pk == 1) {
      if (is_out) { held_out = idx; pk = 2; snprintf(info, sizeof info, "%s: now tap an input", AO_LABEL[idx]); }
      else { held_in = idx; pk = 3; snprintf(info, sizeof info, "%s: now tap an output", AI_LABEL[idx]); }
      bump();
      return;
    }
    if (pk == 2) {
      if (is_out) { if (idx == held_out) cancel_pick(); else { held_out = idx; snprintf(info, sizeof info, "%s: now tap an input", AO_LABEL[idx]); bump(); } return; }
      if (aud_blocked(held_out, idx)) return;
      connect_audio(held_out, idx);
      return;
    }
    if (!is_out) { if (idx == held_in) cancel_pick(); else { held_in = idx; snprintf(info, sizeof info, "%s: now tap an output", AI_LABEL[idx]); bump(); } return; }
    if (aud_blocked(idx, held_in)) return;
    connect_audio(idx, held_in);
  }
  bool aud_blocked(int a, int b) const { return a == b + 1 || would_loop(a, b); }
  void connect_audio(int a, int b) {
    bool had = on(F_AC + a * N_AI + b);
    if (!had) set_cable(a, b, true);
    held_out = a; held_in = b; pk = 4;
    snprintf(info, sizeof info, "%s  >  %s%s", AO_LABEL[a], AI_LABEL[b], had ? "   (already patched)" : "");
    bump();
  }

  // ---- the matrix
  void matrix_cell(int s, int d) {
    int idx = mx_f_sel() * N_DEST + d;
    if (Pi(F_MD + idx) != s + 1) pv[F_MD + idx] = (float)(s + 1);
    sel_f = mx_f_sel(); sel_d = d;
    sync_amount();
    snprintf(info, sizeof info, "%s %s  <  %s", FLT_LABEL[sel_f], DEST_LABEL[d], SRC_LABEL[s]);
    bump();
  }
  int mx_f_sel() const { return Pi(P_MX_F); }

  int mx_state(int s, int d) const {
    int f = mx_f_sel();
    if (Pi(F_MD + f * N_DEST + d) != s + 1) return 0;
    if (sel_f == f && sel_d == d) return 3;
    return pv[F_MA + f * N_DEST + d] < 0 ? 2 : 1;
  }

  void open_matrix_for_view() {
    if (view >= 1 && view <= N_FLT) { pv[P_MX_F] = (float)(view - 1); set_view(V_MATRIX); sel_f = sel_d = -1; bump(); }
  }

  // ---- value text -----------------------------------------------------------------------------------------------------------------
  void display(int p, char *buf, int n) const {
    float v = pv[p];
    if (p == P_DATA) {
      if (last_touch >= 0) { display(last_touch, buf, n); return; }
      snprintf(buf, n, "-"); return;
    }
    if (p == P_M12_MODE) { snprintf(buf, n, "%s", M12_MODE_NAME[(int)clampf(v, 0, 14)]); return; }
    if (p == P_LFO_WAVE) { snprintf(buf, n, "%s", LFO_WAVE_NAME[(int)clampf(v, 0, 4)]); return; }
    if (p == P_LFO_RATE && on(P_LFO_SYNC)) { snprintf(buf, n, "%s", DIV_NAME[(int)clampf(roundf(v), 0, 10)]); return; }
    if (p == P_ST_RATE && on(P_ST_SYNC)) { snprintf(buf, n, "%s", DIV_NAME[(int)clampf(roundf(v), 0, 10)]); return; }
    if (p == P_GT_RATE && on(P_GT_SYNC)) { snprintf(buf, n, "%s", DIV_NAME[(int)clampf(roundf(v), 0, 10)]); return; }
    if (p == P_RND_RATE && on(P_RND_SYNC)) { snprintf(buf, n, "%s", DIV_NAME[(int)clampf(roundf(v), 0, 10)]); return; }
    if (p == P_MX_AMT) { snprintf(buf, n, "%+d", (int)lroundf(v)); return; }
    if (p >= P_ST_1 && p < P_ST_1 + 16) { snprintf(buf, n, "%d %%", (int)lroundf(v)); return; }
    if (p >= P_FG_1 && p < P_FG_1 + 8) { snprintf(buf, n, "%d %%", (int)lroundf(v)); return; }
    if (P_NOPTS[p]) { snprintf(buf, n, "%s", P_OPT[p] ? P_OPT[p][(int)clampf(v, 0, P_NOPTS[p] - 1)] : "-"); return; }
    const char *u = P_UNIT[p];
    if (P_INT[p]) snprintf(buf, n, "%d%s%s", (int)lroundf(v), *u ? " " : "", u);
    else if (!strcmp(u, "dB")) snprintf(buf, n, "%+.1f dB", v);
    else if (p == P_MS_CUT) snprintf(buf, n, "%+.1f", v);
    else if (p == P_PRL_EG) snprintf(buf, n, "%+.1f", v);
    else snprintf(buf, n, "%.1f%s%s", v, *u ? " " : "", u);
  }

  void note_touch(int p) {
    char val[48];
    display(p, val, sizeof val);
    last_touch = p;
    if (is_bay(view) || view == V_MATRIX) snprintf(info, sizeof info, "%s  %s", P_NAME[p], val);
    else snprintf(touch, sizeof touch, "%s  %s", P_NAME[p], val);
    bump();
  }

  static void hz_text(float hz, char *b, int n) {
    if (hz >= 1000.0f) snprintf(b, n, "%.2f kHz", hz / 1000.0f); else snprintf(b, n, "%d Hz", (int)lroundf(hz));
  }
  void describe(int f, char *buf, int n) const {
    char h[24];
    hz_text(f_hz[f], h, sizeof h);
    int res = (int)lroundf(f_res[f] * 10.0f);
    char kind[40];
    switch (f) {
      case F_MS20: snprintf(kind, sizeof kind, "%s12 dB LP", pv[P_MS_HP] > 0.05f ? "12 dB HP + " : ""); break;
      case F_SEM: { static const char *m[4] = {"LP", "NOTCH", "HP", "BP"}; snprintf(kind, sizeof kind, "12 dB %s", m[(int)clampf(roundf(pv[P_SEM_MODE] * 0.3f), 0, 3)]); break; }
      case F_MINI: snprintf(kind, sizeof kind, "24 dB LP"); break;
      case F_M12: snprintf(kind, sizeof kind, "%s", M12_MODE_NAME[(int)clampf(roundf(pv[P_M12_MODE]), 0, 14)]); break;
      case F_P26: snprintf(kind, sizeof kind, "24 dB LP  %s", P_OPT[P_P26_TYPE][Pi(P_P26_TYPE)]); break;
      case F_WASP: { static const char *m[4] = {"LP", "BP", "HP", "NOTCH"}; snprintf(kind, sizeof kind, "12 dB %s", m[(int)clampf(roundf(pv[P_WASP_MODE] * 0.3f), 0, 3)]); break; }
      case F_PRL: snprintf(kind, sizeof kind, "12 dB LP"); break;
      default: snprintf(kind, sizeof kind, "12 dB %s", Pi(P_POLI_MODE) == 1 ? "BP" : "LP"); break;
    }
    snprintf(buf, n, "%s   %s   RES %d%%", kind, h, res);
  }


  // ---- the response picture: RC_COLS columns, each a stroke between two of RC_ROWS rows (see tools/spec.py) ----------------------
  unsigned curve_tick = 0;
  unsigned char rc[RC_COLS] = {0}; int rc_dot = 0;
  static float lp2(float x, float q) { float a = 1 - x * x; return 1.0f / (a * a + x * x / (q * q)); }
  static float hp2(float x, float q) { return x * x * x * x * lp2(x, q); }
  static float bp2(float x, float q) { return x * x / (q * q) * lp2(x, q); }
  static float nt2(float x, float q) { float a = 1 - x * x; return a * a * lp2(x, q); }
  float resp_db(int f, float hz) const {
    float fc = fmaxf(f_hz[f], 20.0f), x = hz / fc, r = f_res[f];
    float q = fminf(0.55f + r * r * 0.22f, 30.0f), m = 1.0f;
    switch (f) {
      case F_MS20: {
        m = lp2(x, q);
        if (pv[P_MS_HP] > 0.05f) m *= hp2(hz / fmaxf(bank[f][0].ms.hp_hz, 20.0f), fminf(0.55f + pv[P_MS_HPPK] * pv[P_MS_HPPK] * 0.22f, 30.0f));
        break;
      }
      case F_SEM: { int k = (int)clampf(roundf(pv[P_SEM_MODE] * 0.3f), 0, 3); m = k == 0 ? lp2(x, q) : k == 1 ? nt2(x, q) : k == 2 ? hp2(x, q) : bp2(x, q); break; }
      case F_MINI: case F_P26: m = lp2(x, q) * lp2(x, 0.62f); break;
      case F_WASP: { int k = (int)clampf(roundf(pv[P_WASP_MODE] * 0.3f), 0, 3); m = k == 0 ? lp2(x, q) : k == 1 ? bp2(x, q) : k == 2 ? hp2(x, q) : nt2(x, q); break; }
      case F_M12: {
        int k = (int)clampf(roundf(pv[P_M12_MODE]), 0, 14);
        float l = lp2(x, q), l4 = l * lp2(x, 0.62f), h = hp2(x, q), h4 = h * hp2(x, 0.62f);
        switch (k) {
          case 0: m = lp2(x, 0.55f); break;  case 1: m = l; break;  case 2: m = l * lp2(x, 0.55f); break;  case 3: m = l4; break;
          case 4: m = hp2(x, 0.55f); break;  case 5: m = h; break;  case 6: m = h * hp2(x, 0.55f); break;  case 7: m = h4; break;
          case 8: m = bp2(x, q); break;  case 9: { float b = bp2(x, q); m = b * b; break; }
          case 10: m = nt2(x, q); break;  case 11: { float b = nt2(x, q); m = b * b; break; }
          case 12: m = 1.0f; break;  case 13: m = l * hp2(hz / 60.0f, 0.7f); break;
          default: m = bp2(x, q) * lp2(x, 0.7f) * 2.0f; break;
        }
        break;
      }
      case F_PRL: m = lp2(x, q); break;
      default: m = Pi(P_POLI_MODE) == 1 ? bp2(x, q) : lp2(x, q); break;
    }
    return 10.0f * log10f(fmaxf(m, 1e-9f));
  }
  // returns true when the picture changed
  bool curve_calc() {
    if (view < 1 || view > N_FLT) { bool ch = rc_dot != 0; for (int i = 0; i < RC_COLS; i++) { if (rc[i]) ch = true; rc[i] = 0; } rc_dot = 0; return ch; }
    int f = view - 1;
    auto row_of = [](float db) { return (int)clampf(floorf((18.0f - db) / 4.3f), 0, RC_ROWS - 1); };
    bool ch = false;
    float prev = resp_db(f, 20.0f * powf(1000.0f, -0.5f / RC_COLS + 0.0f) );
    for (int i = 0; i < RC_COLS; i++) {
      float hzr = 20.0f * powf(1000.0f, (i + 1.0f) / RC_COLS);
      float cur = resp_db(f, hzr);
      float mid = resp_db(f, 20.0f * powf(1000.0f, (i + 0.5f) / RC_COLS));
      int r0 = row_of(prev), r1 = row_of(cur), rm = row_of(mid);
      int lo = r0 < r1 ? r0 : r1, hi = r0 < r1 ? r1 : r0;
      if (rm < lo) lo = rm;
      if (rm > hi) hi = rm;
      unsigned char v = (unsigned char)(lo * RC_ROWS - lo * (lo - 1) / 2 + (hi - lo));
      if (v != rc[i]) { rc[i] = v; ch = true; }
      prev = cur;
    }
    float cf = clampf(logf(fmaxf(f_hz[f], 20.0f) / 20.0f) / logf(1000.0f), 0, 0.9999f);
    int d = 1 + (int)(cf * RC_COLS);
    if (d != rc_dot) { rc_dot = d; ch = true; }
    return ch;
  }

  void aud_text(int f, char *buf, int n) const {
    char src[48] = "", dst[48] = "";
    int ns = 0, nd = 0;
    for (int a = 0; a < N_AO; a++) if (acc[a][f]) { ns += snprintf(src + ns, sizeof src - ns, "%s%s", ns ? "+" : "", AO_LABEL[a]); if (ns > 40) break; }
    for (int b = 0; b < N_AI; b++) if (b != f && acc[f + 1][b]) { nd += snprintf(dst + nd, sizeof dst - nd, "%s%s", nd ? "+" : "", AI_LABEL[b]); if (nd > 40) break; }
    snprintf(buf, n, "%s > %s > %s", ns ? src : "-", FLT_LABEL[f], nd ? dst : "-");
  }
  void mod_text(int f, char *buf, int n) const {
    int len = 0;
    buf[0] = 0;
    for (int d = 0; d < N_DEST; d++) {
      int s = Pi(F_MD + f * N_DEST + d);
      if (!s) continue;
      len += snprintf(buf + len, n - len, "%s%s<%s", len ? "  " : "", DEST_LABEL[d], SRC_LABEL[s - 1]);
      if (len > n - 14) break;
    }
    if (!len) snprintf(buf, n, "none patched");
  }

  void tile_text(int tile, char *buf, int n) const {
    int v = TILE_VIEW[tile];
    if (v >= 1 && v <= N_FLT) { snprintf(buf, n, "FILTER / %d mod", n_mod(v - 1)); return; }
    switch (v) {
      case V_OUT: snprintf(buf, n, "DRIVE %.0f  MIX %d%%", pv[P_OUT_DRIVE], (int)lroundf(pv[P_OUT_DW])); break;
      case V_MODA: snprintf(buf, n, "LFO / ENV / FOLLOWER"); break;
      case V_MSTEP: snprintf(buf, n, "%d steps", (int)lroundf(pv[P_ST_STEPS])); break;
      case V_MFUNC: snprintf(buf, n, "8 points  %s", on(P_FG_BIPOLAR) ? "bipolar" : "unipolar"); break;
      case V_MGATE: snprintf(buf, n, "%d steps + random", (int)lroundf(pv[P_GT_STEPS])); break;
      case V_MATRIX: snprintf(buf, n, "%d routes", n_mod_all()); break;
      default: snprintf(buf, n, "%d cables", n_cables_audio() + n_mod_all()); break;
    }
  }

  // ---- the engine-owned parameters, by index ---------------------------------------------------------------------------------------
  int get_owned(int p, char *buf, int n) const {
    auto num = [&](int v) { return snprintf(buf, n, "%d", v); };
    if (p == P_VIEW) return num(view);
    if (p >= F_PG && p < F_PG + N_PG) return num(view == p - F_PG);
    if (p == P_IN_SEC) return num(view > 0);
    if (p == P_IN_FLT) return num(view >= 1 && view <= N_FLT);
    if (p == P_IN_BAY) return num(is_bay(view));
    if (p == P_HDR_TI) return num(view > 0 && !is_bay(view));
    if (p == P_AMT_ON) return num((view == V_MATRIX && sel_f >= 0) || (view == V_BAYM && pk == 4));
    if (p >= F_MV && p < F_MV + N_MV) {   // modulation cable pictures
      int k = p - F_MV, ab = k & 1, input = k >> 1;
      if (view != V_BAYM || pk == 4) return num(0);
      int s = Pi(F_MD + input) - 1;
      if (s < 0) return num(0);
      int half = N_SRC / 2;
      if (ab == 0) return num(s < half ? s + 1 : 0);
      return num(s >= half ? s - half + 1 : 0);
    }
    if (p >= F_FAO && p < F_FAO + N_FAO) { int a = p - F_FAO; return num(jack_state(true, a)); }
    if (p >= F_FAI && p < F_FAI + N_FAI) { int b = p - F_FAI; return num(jack_state(false, b)); }
    if (p >= F_HDM && p < F_HDM + N_HDM) {   // rings of the held modulation source (groups of JACK_GROUP)
      int g = p - F_HDM;
      if (view != V_BAYM || pk != 2 || held_out < 0 || held_out / JACK_GROUP != g) return num(0);
      return num(1 + held_out % JACK_GROUP);
    }
    if (p >= F_HIM && p < F_HIM + N_HIM) {
      int g = p - F_HIM;
      if (view != V_BAYM || pk != 3 || held_in < 0 || held_in / JACK_GROUP != g) return num(0);
      return num(1 + held_in % JACK_GROUP);
    }
    if (p == F_HAO) return num(view == V_BAYA && (pk == 2 || pk == 3 || pk == 4) && held_out >= 0 && pk != 3 ? 1 + held_out : 0);
    if (p == F_HAI) return num(view == V_BAYA && (pk == 2 || pk == 3 || pk == 4) && held_in >= 0 && pk != 2 ? 1 + held_in : 0);
    if (p == P_PK) return num(is_bay(view) ? pk : 0);
    if (p == P_PK_TM) return num(view == V_BAYM && pk >= 1 && pk <= 3);
    if (p == P_PK_TA) return num(view == V_BAYA && pk >= 1 && pk <= 3);
    if (p == P_PK_C) return num(is_bay(view) && (pk == 2 || pk == 3));
    if (p == P_MX_ON) return num(view == V_MATRIX && sel_f >= 0);
    if (p >= F_MXS && p < F_MXS + N_MXS) { int k = p - F_MXS; return num(view == V_MATRIX ? mx_state(k / N_DEST, k % N_DEST) : 0); }
    if (p >= F_RC && p < F_RC + N_RC) return num(rc[p - F_RC]);
    if (p == P_RC_DOT) return num(rc_dot);
    if (p == P_ENV_ACT) return num(view == V_MODA && lamp_env);
    if (p == P_DRV_CLIP) return num(view == V_OUT && lamp_clip);
    if (p == P_M_IN) return num(view == V_OVERVIEW ? lamp_in : 0);
    if (p == P_M_OUT) return num(view == V_OVERVIEW ? lamp_out : 0);
    if (p == P_ST_LO) return num(view == V_MSTEP && lamp_step >= 1 && lamp_step <= 8 ? lamp_step : 0);
    if (p == P_ST_HI) return num(view == V_MSTEP && lamp_step >= 9 ? lamp_step - 8 : 0);
    if (p == P_GT_LO) return num(view == V_MGATE && lamp_step >= 1 && lamp_step <= 8 ? lamp_step : 0);
    if (p == P_GT_HI) return num(view == V_MGATE && lamp_step >= 9 ? lamp_step - 8 : 0);
    if (p == P_POP_FG_PRESET) return num(pop_open ? 1 : 0);
    if (p == P_MX_F) return num(Pi(P_MX_F));
    if (p == P_PATCH_INFO) return snprintf(buf, n, "%s", info);
    if (p == P_TOUCH_INFO) return snprintf(buf, n, "%s", touch);
    if (p == P_RESP_INFO) { if (view >= 1 && view <= N_FLT) describe(view - 1, buf, n); else buf[0] = 0; return (int)strlen(buf) ? (int)strlen(buf) : snprintf(buf, n, " "); }
    if (p == P_AUD_INFO) { if (view >= 1 && view <= N_FLT) aud_text(view - 1, buf, n); else snprintf(buf, n, " "); return (int)strlen(buf); }
    if (p == P_MOD_INFO) { if (view >= 1 && view <= N_FLT) mod_text(view - 1, buf, n); else snprintf(buf, n, " "); return (int)strlen(buf); }
    if (p == P_MX_INFO) {
      if (view == V_MATRIX && sel_f >= 0) { int s = Pi(F_MD + sel_f * N_DEST + sel_d) - 1; snprintf(buf, n, "%s %s  <  %s", FLT_LABEL[sel_f], DEST_LABEL[sel_d], s >= 0 ? SRC_LABEL[s] : "-"); }
      else snprintf(buf, n, "Tap a cell: source (row) to destination (column)");
      return (int)strlen(buf);
    }
    if (p == P_CPU_INFO) return snprintf(buf, n, "CPU %d%%", (int)lroundf(cpu * 100.0f));
    if (p >= F_TS && p < F_TS + N_TS) { tile_text(p - F_TS, buf, n); return (int)strlen(buf); }
    return -1;
  }

  // a socket of the audio bay: 0 plain, 1 fits (ring), 2 blocked (dim)
  int jack_state(bool is_out, int idx) const {
    if (view != V_BAYA) return 0;
    if (pk == 2) {
      if (is_out) return idx == held_out ? 0 : 2;
      return aud_blocked(held_out, idx) ? 2 : 1;
    }
    if (pk == 3) {
      if (!is_out) return idx == held_in ? 0 : 2;
      return aud_blocked(idx, held_in) ? 2 : 1;
    }
    return 0;
  }

  // ---- state --------------------------------------------------------------------------------------------------------------------------
  int save(char *buf, int n) const {
    int len = snprintf(buf, n, "phyxxl 1;");
    for (int i = 0; i < N_CONTROLS && len < n - 40; i++) {
      if (i == P_DATA) continue;
      if (pv[i] == P_DEF[i]) continue;
      len += snprintf(buf + len, n - len, "%s=%g;", P_KEY[i], pv[i]);
    }
    for (int i = 0; i < N_MD && len < n - 40; i++)
      if (pv[F_MD + i] != 0) len += snprintf(buf + len, n - len, "%s=%g;", P_KEY[F_MD + i], pv[F_MD + i]);
    for (int i = 0; i < N_MA && len < n - 40; i++)
      if (pv[F_MA + i] != 50.0f) len += snprintf(buf + len, n - len, "%s=%g;", P_KEY[F_MA + i], pv[F_MA + i]);
    for (int i = 0; i < N_AC && len < n - 40; i++)
      if (pv[F_AC + i] != 0) len += snprintf(buf + len, n - len, "%s=1;", P_KEY[F_AC + i]);
    if (len < n - 20) len += snprintf(buf + len, n - len, "view=%d;end=1;", view);
    return len < n ? len : -1;
  }
};

int find_key(const char *k) {
  static int table[4096];
  static bool built = false;
  auto h = [](const char *s) { uint32_t x = 2166136261u; while (*s) x = (x ^ (unsigned char)*s++) * 16777619u; return x; };
  if (!built) {
    for (int i = 0; i < 4096; i++) table[i] = -1;
    for (int i = 0; i < P_COUNT; i++) {
      uint32_t s = h(P_KEY[i]) & 4095;
      while (table[s] >= 0) s = (s + 1) & 4095;
      table[s] = i;
    }
    built = true;
  }
  uint32_t s = h(k) & 4095;
  while (table[s] >= 0) {
    if (!strcmp(P_KEY[table[s]], k)) return table[s];
    s = (s + 1) & 4095;
  }
  return -1;
}

void set_value(Plug *s, int p, float v) {
  v = clampf(v, P_MIN[p], P_MAX[p]);
  if (P_NOPTS[p] || P_INT[p]) v = roundf(v);
  s->pv[p] = v;
}

// writes a sound parameter, with the side effects of the ones that mean more than their value
void set_control(Plug *s, int p, float v) {
  float before = s->pv[p];
  set_value(s, p, v);
  bool moved = s->pv[p] != before;
  if (p == P_MX_AMT) {   // the amount slider writes the selected cell's amount
    if (s->sel_f >= 0) s->pv[F_MA + s->sel_f * N_DEST + s->sel_d] = s->pv[p];
    return;
  }
  if (p == P_FG_PRESET && moved) {
    int k = s->Pi(P_FG_PRESET);
    for (int i = 0; i < 8; i++) {
      float x = i / 7.0f, y = 0;
      switch (k) {
        case 0: y = x; break;
        case 1: y = 1.0f - x; break;
        case 2: y = x < 0.5f ? x * 2.0f : 2.0f - x * 2.0f; break;
        case 3: y = sinf(x * 3.14159f); break;
        case 4: y = x * x * (3.0f - 2.0f * x); break;
        case 5: y = ((i / 2) % 4) / 3.0f; break;
        case 6: y = (i % 4) < 2 ? 1.0f : 0.0f; break;
        default: y = 0.5f + 0.5f * sinf(x * 12.0f) * (1.0f - x * 0.5f); break;
      }
      s->pv[P_FG_1 + i] = clampf(y * 100.0f, 0, 100);
    }
    s->pop_open = false;
  }
  if (p == P_FG_PRESET) s->pop_open = false;
}

void load_state(Plug *s, const char *st) {
  if (strncmp(st, "phyxxl", 6)) return;
  for (int i = 0; i < N_CONTROLS; i++) if (i != P_DATA) s->pv[i] = P_DEF[i];
  for (int i = 0; i < N_MD; i++) s->pv[F_MD + i] = 0;
  for (int i = 0; i < N_MA; i++) s->pv[F_MA + i] = 50.0f;
  for (int i = 0; i < N_AC; i++) s->pv[F_AC + i] = 0;
  const char *q = strchr(st, ';');
  int view = 0;
  while (q && *++q) {
    const char *e = strchr(q, ';');
    if (!e) break;
    char item[64];
    int len = (int)(e - q) < 63 ? (int)(e - q) : 63;
    memcpy(item, q, len);
    item[len] = 0;
    char *eq = strchr(item, '=');
    if (eq) {
      *eq = 0;
      if (!strcmp(item, "view")) view = (int)clampf((float)atoi(eq + 1), 0, N_VIEWS - 1);
      else {
        int p = find_key(item);
        if (p >= 0 && (p < N_CONTROLS || (p >= F_MD && p < F_AC + N_AC))) set_value(s, p, (float)atof(eq + 1));
      }
    }
    q = e;
  }
  s->held_out = s->held_in = -1; s->sel_f = s->sel_d = -1;
  s->rebuild();
  s->view = -1;
  s->set_view(view);
  s->bump();
}

// ---- mpc_engine glue ------------------------------------------------------------------------------------------------
void *create(const char *) {
  void *mem = calloc(1, sizeof(Plug));
  if (!mem) return nullptr;
  Plug *s = new (mem) Plug();
  s->init();
  return s;
}

void destroy(void *inst) {
  Plug *s = (Plug *)inst;
  s->~Plug();
  free(s);
}

void midi(void *inst, const uint8_t *m, int len) { ((Plug *)inst)->midi(m, len); }

static bool in_family(int p, int first, int n) { return p >= first && p < first + n; }

void set_param(void *inst, const char *key, const char *val) {
  Plug *s = (Plug *)inst;
  float v = (float)atof(val);
  if (!strcmp(key, "state")) { load_state(s, val); return; }
  if (!strcmp(key, "lfo_bpm")) { if (v > 1) s->bpm = v; return; }
  if (!strcmp(key, "transport")) {
    bool play = v > 0.5f;
    if (play && !s->transport) { s->step.reset(); s->gate.reset(); s->func.reset(); }
    s->transport = play;
    return;
  }
  int p = find_key(key);
  if (p < 0) return;
  if (p < N_CONTROLS) {
    if (p == P_DATA) {   // the DATA knob edits the control touched last
      int t = s->last_touch;
      if (t >= 0 && t != P_DATA && t < N_CONTROLS) {
        float x = clampf(v, 0, 1), before = s->pv[t];
        set_control(s, t, P_MIN[t] + x * (P_MAX[t] - P_MIN[t]));
        s->pv[P_DATA] = x;
        if (s->pv[t] != before) s->note_touch(t);
        s->last_touch = t;
      }
      s->bump();
      return;
    }
    float before = s->pv[p];
    set_control(s, p, v);
    if (s->pv[p] != before) s->note_touch(p);
    if (p == P_CHAIN_SERIES) { if (v > 0.5f) s->chain_set(true); return; }
    s->bump();
    return;
  }
  if (p == P_VIEW) { s->set_view((int)lroundf(v)); return; }
  // settable families
  if (in_family(p, F_MD, N_MD)) { s->pv[p] = clampf(roundf(v), 0, N_SRC); s->bump(); return; }
  if (in_family(p, F_MA, N_MA)) {
    s->pv[p] = clampf(roundf(v), -100, 100);
    if (s->sel_f >= 0 && p == F_MA + s->sel_f * N_DEST + s->sel_d) s->pv[P_MX_AMT] = s->pv[p];
    s->bump();
    return;
  }
  if (in_family(p, F_AC, N_AC)) {
    int k = p - F_AC;
    s->pv[p] = v > 0.5f ? 1.0f : 0.0f;
    s->rebuild();
    s->bump();
    (void)k;
    return;
  }
  if (p == P_MX_F) { s->pv[p] = clampf(roundf(v), 0, N_FLT - 1); s->sel_f = s->sel_d = -1; s->bump(); return; }
  if (p == P_POP_FG_PRESET) { s->pop_open = v > 0.5f; s->bump(); return; }
  // everything else engine-owned is read-only, or a trigger firing on 1
  if (p >= P_QL1 && p <= P_QL16) {
    int t = VIEW_QLINKS[s->view][p - P_QL1];
    if (t < 0) return;
    float x = clampf(v, 0, 1), before = s->pv[t];
    if (t == P_DATA) { set_param(inst, "data", val); return; }
    set_control(s, t, P_MIN[t] + x * (P_MAX[t] - P_MIN[t]));
    if (s->pv[t] != before) s->note_touch(t);
    s->bump();
    return;
  }
  if (v < 0.5f) return;   // triggers fire on 1
  if (p == P_NAV_ZOOM) { s->set_view(V_OVERVIEW); return; }
  if (p == P_NAV_PREV || p == P_NAV_NEXT) {
    int v2 = s->view <= 0 ? 1 : s->view + (p == P_NAV_NEXT ? 1 : -1);
    if (v2 < 1) v2 = N_VIEWS - 1;
    if (v2 >= N_VIEWS) v2 = 1;
    s->set_view(v2);
    return;
  }
  if (p >= P_GO_MS20 && p < P_GO_MS20 + (N_VIEWS - 1)) { s->set_view(1 + p - P_GO_MS20); return; }
  if (p == P_FM_AUDIO) { s->set_view(V_BAYA); return; }
  if (p == P_FM_OPEN) { s->open_matrix_for_view(); return; }
  if (in_family(p, F_TM, N_TM)) { s->pick_mod(true, p - F_TM); return; }
  if (in_family(p, F_TI, N_TI)) { s->pick_mod(false, p - F_TI); return; }
  if (in_family(p, F_TAO, N_TAO)) { s->pick_aud(true, p - F_TAO); return; }
  if (in_family(p, F_TAI, N_TAI)) { s->pick_aud(false, p - F_TAI); return; }
  if (p == P_PK_CANCEL) { s->cancel_pick(); return; }
  if (p == P_PK_UNPLUG) { s->unplug_pair(); return; }
  if (p == P_PK_DONE) { s->done_pick(); return; }
  if (in_family(p, F_MXF, N_MXF)) { s->pv[P_MX_F] = (float)(p - F_MXF); s->sel_f = s->sel_d = -1; s->bump(); return; }
  if (in_family(p, F_MXC, N_MXC)) { if (s->view == V_MATRIX) s->matrix_cell((p - F_MXC) / N_DEST, (p - F_MXC) % N_DEST); return; }
  if (p == P_MX_DONE || p == P_MX_CANCEL) { s->sel_f = s->sel_d = -1; s->bump(); return; }
  if (p == P_MX_UNPLUG) {
    if (s->sel_f >= 0) { s->pv[F_MD + s->sel_f * N_DEST + s->sel_d] = 0; s->sel_f = s->sel_d = -1; s->bump(); }
    return;
  }
  if (p == P_CHAIN_PAR) { s->chain_set(false); return; }
  if (p == P_CHAIN_CLEAR) { s->clear_audio(); snprintf(s->info, sizeof s->info, "All audio cables removed."); return; }
}

int get_param(void *inst, const char *key, char *buf, int n) {
  Plug *s = (Plug *)inst;
  if (!strcmp(key, "display_rev")) return snprintf(buf, n, "%u", s->rev);
  if (!strcmp(key, "state")) return s->save(buf, n);
  size_t kl = strlen(key);
  char base[64];
  int suffix = 0;   // 1 = _display, 2 = _name
  if (kl > 8 && !strcmp(key + kl - 8, "_display")) { suffix = 1; kl -= 8; }
  else if (kl > 5 && !strcmp(key + kl - 5, "_name")) { suffix = 2; kl -= 5; }
  if (kl >= sizeof base) return 0;
  memcpy(base, key, kl);
  base[kl] = 0;
  int p = find_key(base);
  if (p < 0) return 0;
  if (p >= P_QL1 && p <= P_QL16) {
    int t = VIEW_QLINKS[s->view][p - P_QL1];
    if (suffix == 2) return snprintf(buf, n, "%s", t >= 0 ? (t == P_DATA ? "Data" : P_NAME[t]) : "-");
    if (suffix == 1) { if (t < 0) return snprintf(buf, n, " "); s->display(t, buf, n); return (int)strlen(buf); }
    if (t < 0) return snprintf(buf, n, "0");
    float span = P_MAX[t] - P_MIN[t];
    return snprintf(buf, n, "%g", span > 0 ? (s->pv[t] - P_MIN[t]) / span : 0.0f);
  }
  if (suffix == 2) return 0;
  if (suffix == 1) {
    if (p >= N_CONTROLS) return 0;
    s->display(p, buf, n);
    return (int)strlen(buf);
  }
  if (p == P_DATA) return snprintf(buf, n, "%g", s->last_touch >= 0 ? (s->pv[s->last_touch] - P_MIN[s->last_touch]) /
                                                   fmaxf(P_MAX[s->last_touch] - P_MIN[s->last_touch], 1e-6f) : 0.5f);
  if (p < N_CONTROLS) {
    if (P_NOPTS[p]) return snprintf(buf, n, "%d", (int)s->pv[p]);
    return snprintf(buf, n, "%g", s->pv[p]);
  }
  if (in_family(p, F_MD, N_MD) || in_family(p, F_MA, N_MA) || in_family(p, F_AC, N_AC)) return snprintf(buf, n, "%g", s->pv[p]);
  int r = s->get_owned(p, buf, n);
  if (r >= 0) return r;
  return snprintf(buf, n, "0");   // triggers and navigation read back as 0
}

void process_fn(void *inst, const int16_t *in, int16_t *out, int frames) { ((Plug *)inst)->process(in, out, frames); }
void render_fn(void *inst, int16_t *out, int frames) { memset(out, 0, (size_t)frames * 4); (void)inst; }

const mpc_engine_t API = {create, destroy, midi, set_param, get_param, render_fn, process_fn, nullptr};

}  // namespace

extern "C" const mpc_engine_t *mpc_engine(void) { return &API; }
