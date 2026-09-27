# -*- coding: utf-8 -*-
# AEDT IronPython -- after a transient run of the V-Cache column (buildvcache.py ... monitor.py).
# The remote session does not draw AEDT's graphics area, so plots cannot be read off the screen.
# This exports every monitor history to Desktop\vcmon<design>.csv and prints, per 4.515 ms period,
# the largest tier and logic temperature (and when it happened) to the Message Manager, where
# they can be compared with assets/aedt/vcache_reference.json (scripts/aedt_vcache_reference.py).
#
# File name has no capitals or underscores: the remote session drops Shift.
import os

oProject = oDesktop.GetActiveProject()
oDesign = oProject.GetActiveDesign()
oRep = oDesign.GetModule("ReportSetup")
PERIOD_MS = 4.515
QUANTS = ["monptier.Temperature", "monplogic.Temperature"]

def msg(text, level=0):
    oDesktop.AddMessage(oProject.GetName(), oDesign.GetName(), level, text)

desk = os.path.join(os.environ.get("USERPROFILE", "C:\\Users\\user"), "Desktop")
tag = oDesign.GetName().lower().replace(" ", "").replace("_", "")
setup = "Setup1 : Solution"
try:
    names = oDesign.GetModule("AnalysisSetup").GetSetups()
    if names:
        setup = "%s : Solution" % names[0]
except Exception as e:
    msg("setup list failed: %s" % e, 1)

def series(q):
    """(times in ms, values) for one monitor quantity, trying the context forms Icepak accepts."""
    last = None
    for ctx in (["Domain:=", "Sweep"], []):
        try:
            d = oRep.GetSolutionDataPerVariation("Monitor", setup, ctx, ["Time:=", ["All"]], [q])
            s = d[0]
            t = [float(x) for x in s.GetSweepValues("Time")]
            v = [float(x) for x in s.GetRealDataValues(q)]
            try:
                unit = s.GetSweepUnits("Time")
            except Exception:
                unit = "?"
            # the values come back in seconds whatever unit the sweep reports ("ns" on
            # 2026 R1): a run of a few periods ends at ~1e-2
            scale = 1e3 if max(t) < 1.0 else 1.0
            return [x*scale for x in t], v, str(unit)
        except Exception as e:
            last = e
    raise Exception(last)

rows = {}
for q in QUANTS:
    try:
        t, v, unit = series(q)
        rows[q] = (t, v)
        msg("PEAKS %s: %d samples, t %.6g..%.6g ms (sweep unit %s), T %.6f..%.6f" %
            (q, len(t), min(t), max(t), unit, min(v), max(v)))
        n = int(max(t)/PERIOD_MS + 0.5)
        for k in range(n):
            w = [(vv, tt) for tt, vv in zip(t, v) if k*PERIOD_MS <= tt < (k + 1)*PERIOD_MS + 1e-9]
            if w:
                vm, tm = max(w)
                msg("PEAKS %s period %d: max %.6f at %.6f ms" % (q, k + 1, vm, tm))
    except Exception as e:
        msg("PEAKS %s failed: %s" % (q, e), 2)

if rows:
    path = os.path.join(desk, "vcmon%s.csv" % tag)
    try:
        f = open(path, "w")
        f.write("time_ms," + ",".join(q for q in QUANTS if q in rows) + "\n")
        t0 = rows[list(rows)[0]][0]
        for i in range(len(t0)):
            f.write("%.9g," % t0[i] + ",".join("%.9g" % rows[q][1][i] for q in QUANTS if q in rows) + "\n")
        f.close()
        msg("PEAKS wrote %s" % path)
    except Exception as e:
        msg("PEAKS csv failed: %s" % e, 1)
