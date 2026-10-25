// SPDX-License-Identifier: GPL-3.0-or-later
// PhyXXL -- the sound engine's building blocks, host-free. Plain numbers in, plain numbers out, 44100 Hz.
//
// Eight filter modules (each its own circuit idea, written from public descriptions of the originals, no manufacturer
// code): MS-20 style (two Sallen-Key stages with a diode-clipped resonance), SEM style (state variable with a
// LP / notch / HP / BP morph), Mini style (four-stage transistor ladder), Matrix-12 style (four cascaded poles with 15
// mode mixes), 2600 style (ladder variants after the 4012, 4072 and 4075), Wasp style (state variable with CMOS-like
// clipping), prologue style (2-pole low pass with drive) and Polivoks style (2-pole LP / BP, op-amp saturation, an
// envelope tied to the input). Plus the modulation sources: LFO, AHD envelope, envelope follower, step / function /
// gate sequencers and a random sample & hold.
//
// Every filter takes audio at nominal +-1.0 and returns the same scale. Nothing here allocates.
#pragma once
#include <math.h>
#include <stdint.h>
#include <string.h>

namespace phy {

const float SR = 44100.0f;
const float INV_SR = 1.0f / 44100.0f;
const float PI = 3.14159265358979f;

inline float clampf(float x, float a, float b) { return x < a ? a : x > b ? b : x; }
inline float fast_tanh(float x) {   // Pade, exact enough for a clipper, cheap on armv7
  if (x < -3.0f) return -1.0f;
  if (x > 3.0f) return 1.0f;
  float x2 = x * x;
  return x * (27.0f + x2) / (27.0f + 9.0f * x2);
}
inline bool bad(float x) { return !(x == x) || x > 1e5f || x < -1e5f; }

struct Rng {
  uint32_t s = 0x9E3779B9u;
  inline float white() {   // -1..1
    s ^= s << 13; s ^= s >> 17; s ^= s << 5;
    return (int32_t)s * (1.0f / 2147483648.0f);
  }
  inline float unit() { return white() * 0.5f + 0.5f; }
};

// one-pole TPT stage (Zavalishin)
struct OnePole {
  float s = 0;
  inline void reset() { s = 0; }
  inline float lp(float x, float alpha) {   // alpha = g / (1 + g)
    float v = (x - s) * alpha;
    float y = v + s;
    s = y + v;
    return y;
  }
};
inline float stage_alpha(float hz) {
  float g = tanf(PI * clampf(hz, 5.0f, 19000.0f) * INV_SR);
  return g / (1.0f + g);
}
inline float oct_hz(float fmin, float oct_span, float pos10, float extra_oct) {
  float hz = fmin * exp2f(pos10 * 0.1f * oct_span + extra_oct);
  return clampf(hz, 8.0f, 19000.0f);
}

// DC blocker (5 Hz)
struct Dc {
  float x1 = 0, y1 = 0;
  inline float tick(float x) { float y = x - x1 + 0.9993f * y1; x1 = x; y1 = y; return y; }
  void reset() { x1 = y1 = 0; }
};

// ---- the common face of a filter module ---------------------------------------------------------------------------
// set() gets the already-modulated knob values (0..10 unless said otherwise) once per sub-block; tick() runs one sample.
// info() describes the response for the page's readout.

// ---- MS-20 style: HPF then LPF, each a 12 dB Sallen-Key with a resonance feedback ------------------------------------
struct Ms20Lpf {
  OnePole lp1, lp2, hp;
  float alpha = 0.1f, beta = 0.9f, K = 0;
  void reset() { lp1.reset(); lp2.reset(); hp.reset(); }
  void set(float hz, float peak) {
    alpha = stage_alpha(hz);
    beta = 1.0f - alpha;
    K = 2.2f * powf(clampf(peak, 0, 1), 0.9f);
  }
  static inline float clip_fb(float v) { return fast_tanh(v * 0.5f) * 2.0f; }
  inline float tick(float x) {
    float a = alpha;
    float x1 = lp1.lp(x, a);
    float S2 = (1.0f - a) * lp2.s;
    float lin = beta * (S2 - hp.s);
    float u = (x1 + K * lin) / (1.0f - K * beta * a);
    float fb = beta * (a * u + S2 - hp.s);
    float fbc = clip_fb(fb);
    if (fbc != fb) u = x1 + K * fbc;
    float y = lp2.lp(u, a);
    hp.lp(y, a);
    return -y;
  }
};
struct Ms20Hpf {
  OnePole hp1, hp2, lp;
  float alpha = 0.1f, K = 0;
  void reset() { hp1.reset(); hp2.reset(); lp.reset(); }
  void set(float hz, float peak) {
    alpha = stage_alpha(hz);
    K = 2.2f * powf(clampf(peak, 0, 1), 0.9f);
  }
  inline float tick(float x) {
    float a = alpha;
    float x1 = x - hp1.lp(x, a);
    float b = 1.0f - a;
    float lin = a * (b * (-hp2.s) - lp.s) + lp.s;
    float u = (x1 + K * lin) / (1.0f - K * a * b);
    float y_lin = b * (u - hp2.s);
    float fb = a * (y_lin - lp.s) + lp.s;
    float fbc = Ms20Lpf::clip_fb(fb);
    if (fbc != fb) u = x1 + K * fbc;
    float y = u - hp2.lp(u, a);
    lp.lp(y, a);
    return y + 0.45f * (x1 - y);
  }
};

struct Ms20 {
  Ms20Hpf hpf;
  Ms20Lpf lpf;
  bool hp_on = false;
  float lp_hz = 1000, hp_hz = 50, lp_q = 0, hp_q = 0;
  void reset() { hpf.reset(); lpf.reset(); }
  // cut: master offset -5..5 (octaves*0.8), hp / lp 0..10, peaks 0..10; side -1 / +1: the stereo spread
  void set(float cut, float hp, float hppk, float lp, float lppk, float side_oct) {
    float off = cut * 0.8f + side_oct;
    hp_on = hp > 0.05f;
    hp_hz = oct_hz(50.0f, 8.23f, hp, off);
    lp_hz = oct_hz(50.0f, 8.23f, lp, off);
    hp_q = hppk * 0.1f; lp_q = lppk * 0.1f;
    hpf.set(hp_hz, hp_q);
    lpf.set(lp_hz, lp_q);
  }
  inline float tick(float x) {
    float v = x * 2.5f;          // the MS-20's 5 Vpp
    if (hp_on) v = hpf.tick(v);
    v = lpf.tick(v);
    return v * 0.4f;
  }
};

// ---- SEM style: state variable, LP -> notch -> HP -> BP --------------------------------------------------------------
struct Sem {
  float ic1 = 0, ic2 = 0;
  float g = 0.1f, k = 1, a1 = 0, a2 = 0, a3 = 0;
  float w_lp = 1, w_nt = 0, w_hp = 0, w_bp = 0, gain = 1, noise = 0;
  bool clip = true;
  float hz = 1000, q = 0.7f;
  Rng *rng = nullptr;
  void reset() { ic1 = ic2 = 0; }
  void set(float freq, float res, float mode, float ingain, float innoise, bool softclip, float side_oct) {
    hz = oct_hz(40.0f, 8.2f, freq, side_oct);
    g = tanf(PI * clampf(hz, 8.0f, 18000.0f) * INV_SR);
    k = 2.0f - 1.96f * clampf(res * 0.1f, 0, 1);
    q = 1.0f / k;
    a1 = 1.0f / (1.0f + g * (g + k));
    a2 = g * a1;
    a3 = g * a2;
    float m = clampf(mode * 0.3f, 0, 3.0f);   // 0 LP, 1 notch, 2 HP, 3 BP
    w_lp = clampf(1.0f - m, 0, 1);
    w_nt = m <= 1 ? clampf(m, 0, 1) : clampf(2.0f - m, 0, 1);
    w_hp = m <= 1 ? 0.0f : m <= 2 ? clampf(m - 1.0f, 0, 1) : clampf(3.0f - m, 0, 1);
    w_bp = clampf(m - 2.0f, 0, 1);
    gain = 0.4f + ingain * 0.16f;
    noise = innoise * 0.1f;
    clip = softclip;
  }
  inline float tick(float x) {
    float v0 = x * gain + (rng ? rng->white() * noise * 0.03f : 0.0f);
    if (clip) v0 = fast_tanh(v0);
    float v3 = v0 - ic2;
    float v1 = a1 * ic1 + a2 * v3;
    float v2 = ic2 + a2 * ic1 + a3 * v3;
    ic1 = 2.0f * v1 - ic1;
    ic2 = 2.0f * v2 - ic2;
    if (clip) { ic1 = fast_tanh(ic1 * 0.7f) * 1.43f; }
    float lp = v2, bp = v1 * k, hp = v0 - k * v1 - v2, nt = v0 - k * v1;
    return (lp * w_lp + nt * w_nt + hp * w_hp + bp * w_bp * 0.9f) * 0.85f;
  }
};

// ---- Mini style: four transistor-ladder stages ------------------------------------------------------------------------
struct Ladder {
  float y[4] = {0, 0, 0, 0}, t[4] = {0, 0, 0, 0}, last = 0;
  float g = 0.1f, k = 0, drive = 1, vol = 1, comp = 0.0f, sat = 1.0f;
  float hz = 1000;
  void reset() { for (int i = 0; i < 4; i++) y[i] = t[i] = 0; last = 0; }
  // hz, resonance 0..10, drive gain, compensation of the bass loss (0 = none: the Moog way), saturation
  void setup(float freq_hz, float res10, float drv, float comp_, float sat_, float maxk) {
    hz = clampf(freq_hz, 10.0f, 16000.0f);
    g = clampf(1.0f - expf(-2.0f * PI * hz * INV_SR), 0.0005f, 0.95f);
    k = maxk * clampf(res10 * 0.1f, 0, 1);
    drive = drv; comp = comp_; sat = sat_;
  }
  inline float tick(float x) {
    float in = x * drive * (1.0f + comp * k * 0.25f) - k * last;
    float u = fast_tanh(in * sat) / sat;
    float prev = u;
    for (int i = 0; i < 4; i++) {
      y[i] += g * (prev - t[i]);
      t[i] = fast_tanh(y[i] * sat) / sat;
      prev = y[i];
    }
    last = (y[3] + y[2]) * 0.5f;
    return y[3];
  }
};
struct Mini {
  Ladder lad;
  float vol = 1;
  float hz = 1000, k = 0;
  void reset() { lad.reset(); }
  void set(float drive, float cut, float emph, float outvol, float side_oct) {
    hz = oct_hz(30.0f, 9.0f, cut, side_oct);
    lad.setup(hz, emph, 0.6f + drive * 0.22f, 0.0f, 1.0f, 4.1f);
    k = lad.k;
    vol = outvol * 0.2f;
  }
  inline float tick(float x) { return lad.tick(x) * vol * (1.0f + 0.5f * k * 0.25f); }
};

// ---- Matrix-12 style: four poles, 15 mode mixes ---------------------------------------------------------------------------
struct M12 {
  OnePole st[4];
  float fbs = 0, alpha = 0.1f, k = 0, hz = 1000;
  float mix[5] = {0, 0, 0, 0, 1};
  void reset() { for (int i = 0; i < 4; i++) st[i].reset(); fbs = 0; }
  static void mode_row(int m, float *c) {
    static const float T[15][5] = {
        {0, 1, 0, 0, 0}, {0, 0, 1, 0, 0}, {0, 0, 0, 1, 0}, {0, 0, 0, 0, 1},                    // LP 1..4
        {1, -1, 0, 0, 0}, {1, -2, 1, 0, 0}, {1, -3, 3, -1, 0}, {1, -4, 6, -4, 1},               // HP 1..4
        {0, 1, -1, 0, 0}, {0, 0, 1, -2, 1},                                                       // BP 2, BP 4
        {1, -2, 2, 0, 0}, {1, -2, 0, 4, -2},                                                      // notch 2, 4 (approximate)
        {1, -2, 2, 0, 0},                                                                         // phase 2
        {0, 0, 1, -1, 1}, {0, 1, -1, 1, 0}};                                                      // LP2 + HP, BP + LP
    for (int i = 0; i < 5; i++) c[i] = T[m][i];
  }
  void set(float mode, float cut, float res, float side_oct) {
    hz = oct_hz(30.0f, 9.0f, cut, side_oct);
    alpha = stage_alpha(hz * 1.3f);
    k = 3.9f * clampf(res * 0.1f, 0, 1);
    float m = clampf(mode, 0, 14.0f);
    int i0 = (int)m;
    int i1 = i0 < 14 ? i0 + 1 : 14;
    float f = m - i0, a[5], b[5];
    mode_row(i0, a); mode_row(i1, b);
    for (int i = 0; i < 5; i++) mix[i] = a[i] * (1 - f) + b[i] * f;
  }
  inline float tick(float x) {
    float in = x - fast_tanh(k * fbs * 0.8f) * 1.25f;
    float s1 = st[0].lp(in, alpha), s2 = st[1].lp(s1, alpha), s3 = st[2].lp(s2, alpha), s4 = st[3].lp(s3, alpha);
    fbs = s4;
    float y = in * mix[0] + s1 * mix[1] + s2 * mix[2] + s3 * mix[3] + s4 * mix[4];
    return y * (1.0f / (1.0f + k * 0.12f));
  }
};

// ---- 2600 style: ladder variants -----------------------------------------------------------------------------------------------
struct P26 {
  Ladder lad;
  float vol = 1, hz = 1000;
  int type = 1;
  void reset() { lad.reset(); }
  // fm_oct: the three FM depths already summed in octaves
  void set(float cut, float res, float fm_oct, int t, float side_oct) {
    type = t;
    hz = oct_hz(25.0f, 9.5f, cut, fm_oct + side_oct);
    if (t == 0) lad.setup(hz, res, 1.0f, 0.0f, 1.0f, 4.0f);          // 4012: the Moog-ladder imitation, bass thins as it resonates
    else if (t == 1) lad.setup(hz, res, 1.0f, 0.7f, 0.8f, 4.0f);     // 4072: ARP's own design, keeps its bass, a gentler clip
    else lad.setup(hz, res, 1.3f, 0.9f, 1.3f, 4.4f);                 // 4075: later revision, taken as a hotter 4072 (unverified)
    vol = 0.8f;
  }
  inline float tick(float x) { return lad.tick(x) * vol; }
};

// ---- Wasp style: a state variable with CMOS-ish clipping ---------------------------------------------------------------
struct Wasp {
  float ic1 = 0, ic2 = 0, g = 0.1f, k = 1, a1 = 0, a2 = 0, a3 = 0, drive = 1, hz = 1000;
  float w[4] = {1, 0, 0, 0};
  void reset() { ic1 = ic2 = 0; }
  void set(float cut, float peak, float mode, float indrive, float side_oct) {
    hz = oct_hz(40.0f, 8.0f, cut, side_oct);
    g = tanf(PI * clampf(hz, 8.0f, 16000.0f) * INV_SR);
    k = 2.0f - 1.9f * clampf(peak * 0.1f, 0, 1);
    a1 = 1.0f / (1.0f + g * (g + k));
    a2 = g * a1;
    a3 = g * a2;
    drive = 1.0f + indrive * 0.9f;
    float m = clampf(mode * 0.3f, 0, 3.0f);   // LP, BP, HP, notch
    for (int i = 0; i < 4; i++) { float d = fabsf(m - i); w[i] = d < 1.0f ? 1.0f - d : 0.0f; }
  }
  static inline float cmos(float x) { return fast_tanh(x + 0.25f * x * x) - 0.06f; }   // lopsided, as the inverter stages
  inline float tick(float x) {
    float v0 = cmos(x * drive) * 0.9f;
    float v3 = v0 - ic2;
    float v1 = a1 * ic1 + a2 * v3;
    float v2 = ic2 + a2 * ic1 + a3 * v3;
    ic1 = fast_tanh(2.0f * v1 - ic1);
    ic2 = fast_tanh(2.0f * v2 - ic2);
    float lp = v2, bp = v1 * k, hp = v0 - k * v1 - v2, nt = v0 - k * v1;
    return (lp * w[0] + bp * w[1] + hp * w[2] + nt * w[3]) * (0.8f / (0.6f + 0.1f * drive));
  }
};

// ---- prologue style: 2-pole low pass, drive, key tracking, EG ------------------------------------------------------------
struct Prl {
  float ic1 = 0, ic2 = 0, g = 0.1f, k = 1, a1 = 0, a2 = 0, a3 = 0, drive = 1, hz = 1000;
  void reset() { ic1 = ic2 = 0; }
  // cut 0..10; oct_extra: key tracking and EG in octaves
  void set(float cut, float res, float drv, float oct_extra, float side_oct) {
    hz = oct_hz(30.0f, 9.0f, cut, oct_extra + side_oct);
    g = tanf(PI * clampf(hz, 8.0f, 17000.0f) * INV_SR);
    k = 2.0f - 1.98f * clampf(res * 0.1f, 0, 1);
    a1 = 1.0f / (1.0f + g * (g + k));
    a2 = g * a1;
    a3 = g * a2;
    drive = 1.0f + drv * 0.35f;
  }
  inline float tick(float x) {
    float v0 = fast_tanh(x * drive) / (0.6f + 0.4f * drive * 0.5f);
    float v3 = v0 - ic2;
    float v1 = a1 * ic1 + a2 * v3;
    float v2 = ic2 + a2 * ic1 + a3 * v3;
    ic1 = 2.0f * v1 - ic1;
    ic2 = 2.0f * v2 - ic2;
    if (k < 0.25f) ic1 = fast_tanh(ic1);       // near self-oscillation the loop is limited
    return v2;
  }
};

// ---- Polivoks style: 2-pole LP / BP, op-amp saturation, an envelope fired by the input -------------------------------
struct Poli {
  float ic1 = 0, ic2 = 0, g = 0.1f, k = 1, a1 = 0, a2 = 0, a3 = 0, drive = 1, hz = 1000;
  bool bp = false;
  float env = 0, env_rate = 0.001f, det = 0, amt = 0;
  void reset() { ic1 = ic2 = 0; env = det = 0; }
  void set(float cut, float res, float drv, float envamt, float decay, bool bandpass, float side_oct) {
    amt = envamt;
    float e_oct = env * amt * 0.7f;
    hz = oct_hz(30.0f, 9.0f, cut, e_oct + side_oct);
    g = tanf(PI * clampf(hz, 8.0f, 17000.0f) * INV_SR);
    k = 2.0f - 1.97f * clampf(res * 0.1f, 0, 1);
    a1 = 1.0f / (1.0f + g * (g + k));
    a2 = g * a1;
    a3 = g * a2;
    drive = 1.0f + drv * 0.5f;
    bp = bandpass;
    float t = 0.01f * powf(10.0f, clampf(decay, 0, 10) * 0.3f);   // 10 ms .. 20 s
    env_rate = expf(-1.0f / (t * SR));
  }
  inline float tick(float x) {
    float a = fabsf(x);
    if (a > det) det = a; else det *= 0.9995f;
    if (det > 0.2f && env < 1.0f && det > env * 0.5f && a > 0.15f) env = fmaxf(env, fminf(1.0f, det * 2.0f));   // an input transient fires it
    env *= env_rate;
    float v0 = x * drive;
    v0 = v0 / (1.0f + fabsf(v0) * 0.5f) * 1.2f;   // op-amp style soft knee, odd harmonics
    float v3 = v0 - ic2;
    float v1 = a1 * ic1 + a2 * v3;
    float v2 = ic2 + a2 * ic1 + a3 * v3;
    ic1 = 2.0f * v1 - ic1;
    ic2 = 2.0f * v2 - ic2;
    ic1 = fast_tanh(ic1 * 0.8f) * 1.25f;
    return bp ? v1 * k * 0.9f : v2;
  }
};

// ============================================================================================================================
// modulation sources
// ============================================================================================================================
inline float pot_time(float v10) { return 0.001f * powf(10.0f, clampf(v10, 0, 10) * 0.45f); }   // 1 ms .. 31 s

struct Lfo {
  float phase = 0, smooth_state = 0, rnd = 0, out = 0;
  Rng *rng = nullptr;
  int wave = 0;
  void restart() { phase = 0; }
  // advance by n samples at hz; returns -1..1
  float run(float hz, int n, float smooth10) {
    float prev = phase;
    phase += hz * n * INV_SR;
    bool wrapped = phase >= 1.0f;
    if (wrapped) { phase -= floorf(phase); if (rng) rnd = rng->white(); }
    (void)prev;
    float v;
    switch (wave) {
      case 0: v = sinf(2.0f * PI * phase); break;
      case 1: v = phase < 0.5f ? 4.0f * phase - 1.0f : 3.0f - 4.0f * phase; break;
      case 2: v = 2.0f * phase - 1.0f; break;
      case 3: v = phase < 0.5f ? 1.0f : -1.0f; break;
      default: v = rnd; break;
    }
    float sm = clampf(smooth10 * 0.1f, 0, 1);
    float a = 1.0f - powf(sm, 0.3f) * 0.995f * 1.0f;
    a = clampf(a, 0.002f, 1.0f);
    float ka = 1.0f - powf(1.0f - a, (float)n);   // per sub-block of n samples
    smooth_state += (v - smooth_state) * ka;
    out = smooth_state;
    return out;
  }
};

struct Env {   // attack - hold - decay, fired by a trigger
  int stage = 0;   // 0 idle, 1 attack, 2 hold, 3 decay
  float v = 0, hold_left = 0;
  void trigger() { stage = 1; }
  float run(float att_s, float hold_s, float dec_s, int n) {
    float dt = n * INV_SR;
    switch (stage) {
      case 1: v += dt / fmaxf(att_s, 0.0005f); if (v >= 1.0f) { v = 1.0f; stage = 2; hold_left = hold_s; } break;
      case 2: hold_left -= dt; if (hold_left <= 0) stage = 3; break;
      case 3: v -= dt / fmaxf(dec_s, 0.0005f); if (v <= 0.0005f) { v = 0; stage = 0; } break;
      default: break;
    }
    return v;
  }
};

struct Follower {
  float level = 0, det = 0;
  static const int DLEN = 64;   // delay in sub-blocks (32 samples ~ 0.73 ms): up to ~47 ms steps of 0.73 ms
  float dl[DLEN];
  int dpos = 0;
  Follower() { memset(dl, 0, sizeof dl); }
  // peak of the block in, sensitivity 0..10, delay 0..10 (0..46 ms), rise / fall 0..10
  float run(float peak, float sens10, float delay10, float rise10, float fall10, int n) {
    float in = clampf(peak * (0.5f + sens10 * 0.6f), 0, 1.5f);
    float rise = 1.0f - expf(-(float)n / (pot_time(rise10) * 0.25f * SR + 1.0f));
    float fall = 1.0f - expf(-(float)n / (pot_time(fall10) * 2.0f * SR + 1.0f));
    det += (in - det) * (in > det ? rise : fall);
    int dn = (int)(clampf(delay10, 0, 10) * 0.1f * (DLEN - 1));
    dl[dpos] = det;
    float v = dl[(dpos - dn + DLEN) % DLEN];
    dpos = (dpos + 1) % DLEN;
    level = clampf(v, 0, 1);
    return level;
  }
};

// a clock that steps at a rate (Hz) or a sync division; swing delays every odd step
struct Clock {
  float phase = 0;
  int step = 0;
  void reset() { phase = 0; step = 0; }
  // advance by n samples; returns the number of steps that fell in it (0 or 1 normally)
  int run(float step_hz, float swing, int n) {
    float len = 1.0f;
    float ph = phase + step_hz * n * INV_SR;
    float need = (step & 1) ? len * (2.0f * swing) : len * (2.0f * (1.0f - swing));
    if (ph >= need) { phase = ph - need; step++; return 1; }
    phase = ph;
    return 0;
  }
};

inline float rate_hz(float rate10) { return 0.25f * exp2f(clampf(rate10, 0, 10) * 0.6f); }

struct StepSeq {
  Clock clk;
  int pos = 0, dir = 1, last_rand = 0;
  float val = 0, out = 0;
  Rng *rng = nullptr;
  int lit = 0;
  void reset() { clk.reset(); pos = 0; dir = 1; }
  // bars[16] 0..100; returns 0..1
  float run(const float *bars, int steps, int mode, float step_hz, float swing, float rand10, float smooth10, int n, bool *stepped) {
    *stepped = false;
    if (clk.run(step_hz, swing, n)) {
      *stepped = true;
      switch (mode) {
        case 0: pos = (pos + 1) % steps; break;
        case 1: pos = (pos + steps - 1) % steps; break;
        case 2:
          if (steps > 1) { pos += dir; if (pos >= steps - 1) { pos = steps - 1; dir = -1; } if (pos <= 0) { pos = 0; dir = 1; } }
          break;
        default: pos = rng ? (int)(rng->unit() * steps) % steps : 0; break;
      }
      if (pos >= steps) pos = steps - 1;
      float b = bars[pos] * 0.01f;
      float r = rand10 * 0.1f;
      val = clampf(b + (rng ? rng->white() * 0.5f * r : 0.0f), 0, 1);
    }
    lit = pos + 1;
    float sm = clampf(smooth10 * 0.1f, 0, 1);
    float a = clampf(1.0f - sm * 0.995f, 0.003f, 1.0f);
    out += (val - out) * (1.0f - powf(1.0f - a, (float)n));
    return out;
  }
};

struct FuncGen {
  float phase = 0;
  void reset() { phase = 0; }
  // 8 breakpoints, looping once per cycle at rate Hz; linear between them
  float run(const float *pts, float hz, int n) {
    phase += hz * n * INV_SR;
    phase -= floorf(phase);
    float p = phase * 8.0f;
    int i = (int)p;
    float f = p - i;
    float a = pts[i & 7] * 0.01f, b = pts[(i + 1) & 7] * 0.01f;
    return a + (b - a) * f;
  }
};

struct GateSeq {
  Clock clk;
  int pos = 0;
  bool env_on = false, lfo_on = false, gate = false;
  float gate_left = 0;
  void reset() { clk.reset(); pos = 0; gate = false; }
  // returns the number of new steps (0/1); sets env_on / lfo_on for the new step
  bool run(const bool *e, const bool *l, int steps, float step_hz, int n) {
    bool st = clk.run(step_hz, 0.5f, n) != 0;
    env_on = lfo_on = false;
    if (st) {
      pos = (pos + 1) % steps;
      env_on = e[pos]; lfo_on = l[pos];
      gate = env_on || lfo_on;
      gate_left = 0.5f / fmaxf(step_hz, 0.01f);
    } else if (gate) {
      gate_left -= n * INV_SR;
      if (gate_left <= 0) gate = false;
    }
    return st;
  }
};

struct RandomSh {
  float phase = 0, target = 0, out = 0;
  Rng *rng = nullptr;
  float run(float hz, float slew10, int n) {
    phase += hz * n * INV_SR;
    if (phase >= 1.0f) { phase -= floorf(phase); if (rng) target = rng->white(); }
    float a = clampf(1.0f - clampf(slew10 * 0.1f, 0, 1) * 0.995f, 0.003f, 1.0f);
    out += (target - out) * (1.0f - powf(1.0f - a, (float)n));
    return out;
  }
};

}  // namespace phy
