#!/usr/bin/env python3
"""Shared model behind the ECTC figures: duty-cycled thermal envelope of a 3D SRAM tier.

The one idea. The device team's Q3 relation  BW <= P_budget / E_bit  is a STEADY-STATE
relation. An LLM decode tier is not a steady-state load: at the GB-scale design point it
is active only a few percent of wall time, in bursts short compared with plausible stack
time constants. Whether the stack integrates those bursts (average power governs) or
tracks them (peak power governs) is a property of tau = R_th * C_th, and it moves the
admissible bandwidth by more than an order of magnitude.

Phase coverage (2026-09-22, scripts/prefill_phase.py). The duty below is a DECODE number,
and prefill was checked rather than assumed: prefill duty is 0.08-0.41% against decode's
4.80%, because the tier moves the same resident weight bytes over a window >=10x longer.
Decode is the thermal design point. Prefill's exposure is on the baseline instead -- it is
compute-bound and runs nearer TDP than the measured 698.7 W decode package power.

Everything physical here is an AXIS, not a value: E/bit, R_th, C_th and the per-layer
thermal resistance increment are all unmeasured. The workload side is anchored:
D_step and f_red are trace replay, t_step and BW_HBM are regression-derived [canon].
"""
import os, sys, math
sys.path.insert(0, os.path.dirname(__file__))
from canon_3dsram import get

# ---- anchored workload side ------------------------------------------------
BW_HBM  = get('b200_baseline.hbm_effective_TBs_llama')   # 6.40 TB/s [regression-derived]
W_READ  = get('workload.llama31_8b_weight_read_per_step_GB')  # 15.010 GB [public-derived]
D_STEP  = 17.158        # GB/step, unified ledger total demand [trace replay, Gate 0]
T_STEP  = 4.515e-3      # s, t0 1.852 ms + 17.031 GB / 6.40 TB/s [Gate 3]
B_R     = 19.0          # TB/s, via-L2 fabric cap [canon design_point_axes, scenario]
P_PKG_W = 698.7         # W, measured B200 package power, decode B=8 N=2048 [measured,
                        # assets/model_evidence.json]. This is the baseline the tier's
                        # own 1-3 W rides on. Prefill runs nearer TDP and is UNMEASURED.
DUTY_PREFILL_MAX = 0.00414   # scripts/prefill_phase.py: prefill duty at an unphysical
                        # 100% MFU on BF16 peak. The tier moves the same resident bytes
                        # in both phases, so duty_prefill/duty_decode = t_decode/t_prefill,
                        # and prefill is >=10x longer. DECODE IS THE THERMAL WORST CASE.

# Gate 1 anchor: C2 2-layer 800 mm^2 (4.22 GB) replays to a 24.00% HBM byte reduction.
C_ANCHOR_GB, F_ANCHOR = 4.22, 0.2400
# Admission (Gate 6): only weight is admitted, so the tier can never serve more than
# the weight stream. f_red saturates once capacity covers the weight working set.
F_MAX = F_ANCHOR * (W_READ / C_ANCHOR_GB)

def capacity_GB(area_mm2=800.0, layers=1, dies=2, case='C2'):
    """Geometric upper bound: area / macro area, x dies x layers. No legal polygon."""
    macro = {'C2': 0.079254, 'C3': 0.120048, 'C1': 0.056658}[case]   # canon: device_3dsram.macro_area_mm2
    n = math.floor(area_mm2 / macro)
    return dies * layers * n * (1e6/8) * (1-.12)*(1-.05) / 1e9

def f_red(C_GB):
    """HBM byte reduction, linear in capacity, saturating at the weight working set."""
    return min(F_ANCHOR * C_GB / C_ANCHOR_GB, F_MAX)

def duty(C_GB, bw_TBs=B_R):
    """Fraction of wall time the tier is active: (bytes served / BW) / step time."""
    return (f_red(C_GB) * D_STEP / bw_TBs) * 1e-3 / T_STEP

def burst_s(C_GB, bw_TBs=B_R):
    return f_red(C_GB) * D_STEP / bw_TBs * 1e-3

def pss_peak(d, tau, Tp=T_STEP):
    """Periodic steady state of a first-order thermal node under a square wave,
    normalised to P_burst * R_th. -> 1 means it reaches the burst temperature,
    -> d means it perfectly averages. Exact, no small-signal approximation."""
    if tau <= 0: return 1.0
    x = Tp / tau
    a, b = math.exp(-d*x), math.exp(-(1-d)*x)
    return (1-a) / (1-a*b)

def p_burst_W(e_pJ, bw_TBs=B_R):
    """Instantaneous tier power while a burst is in flight."""
    return bw_TBs * 1e12 * 8 * e_pJ * 1e-12

def bw_cap_TBs(P_W, e_pJ, peak_frac=1.0):
    """Delivered-BW ceiling from a power budget. peak_frac = 1 is the steady-state
    relation; peak_frac < 1 is the duty-corrected one for this stack's tau."""
    return P_W / (8.0 * e_pJ) / peak_frac

# ---- stack thermal parameters (ALL ASSUMPTION AXES) ------------------------
RHO, CP = 2330.0, 700.0      # Si, for a Si-equivalent slab; the real BEOL stack differs

def C_th(layers, area_mm2=800.0, dies=2, t_um=5.0):
    return (area_mm2*1e-6*dies*layers) * (t_um*1e-6) * RHO * CP      # J/K

def R_th(layers, r_base=0.10, r_per_layer=0.03):
    """Series path: the topmost layer's heat crosses everything below it."""
    return r_base + (layers-1)*r_per_layer

def dT_peak(layers, e_pJ, area_mm2=800.0, dies=2, t_um=5.0,
            r_base=0.10, r_per_layer=0.03, bw_TBs=B_R, case='C2'):
    """Peak tier temperature rise above the local baseline, periodic steady state."""
    C   = capacity_GB(area_mm2, layers, dies, case)
    d   = duty(C, bw_TBs)
    R   = R_th(layers, r_base, r_per_layer)
    tau = R * C_th(layers, area_mm2, dies, t_um)
    return p_burst_W(e_pJ, bw_TBs) * R * pss_peak(d, tau), d, C, tau

if __name__ == '__main__':
    print(f'anchors: D_step {D_STEP} GB, t_step {T_STEP*1e3:.3f} ms, B_R {B_R} TB/s, '
          f'HBM {BW_HBM} TB/s, weight read {W_READ} GB')
    print(f'f_red saturates at {F_MAX*100:.1f}% (capacity covers the {W_READ} GB weight stream)\n')
    print(f"{'N':>2} {'C [GB]':>8} {'f_red':>7} {'duty':>7} {'burst':>9} {'tau':>9} "
          f"{'dT@0.2pJ':>9} {'dT@0.5pJ':>9}")
    for N in (1,2,4,8,16):
        C = capacity_GB(800.0, N)
        dt2,d,_,tau = dT_peak(N, 0.2); dt5,_,_,_ = dT_peak(N, 0.5)
        print(f'{N:>2} {C:>8.2f} {f_red(C)*100:>6.1f}% {d*100:>6.2f}% '
              f'{burst_s(C)*1e6:>7.0f}us {tau*1e6:>7.0f}us {dt2:>8.2f}K {dt5:>8.2f}K')
