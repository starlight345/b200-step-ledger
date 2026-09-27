# -*- coding: utf-8 -*-
# AEDT IronPython -- run after buildvcache.py in the same IcepakFEA (Transient Thermal) design.
#
# The decode burst train on the SRAM device layer ('tier'): P_COL for 216.72 us out of every
# 4.515 ms (duty 4.80%), for N_PER periods from t = 0, as a project dataset through pwl() of
# Time. P_COL makes the burst-power steady rise exactly 100 K on this 1e-10 m2 column
# (R = 0.0259487013 K/W per 800 mm2 die, from sota_comparators.Modal -> 2.0758961e5 K/W here).
# Every body starts at the sink temperature, 20 C, so the run starts cold -- the comparison
# is against the same cold start, solved exactly (hotspot_rerun / sota_comparators Modal).
#
# File name has no capitals or underscores: the remote session drops Shift.

oProject = oDesktop.GetActiveProject()
oDesign = oProject.GetActiveDesign()
oBnd = oDesign.GetModule("BoundarySetup")

def msg(text, level=0):
    oDesktop.AddMessage(oProject.GetName(), oDesign.GetName(), level, text)

def attempt(label, fn):
    try:
        fn()
        msg("OK   " + label)
        return True
    except Exception as e:
        msg("FAIL " + label + " :: " + str(e), 2)
        return False

PERIOD, TP, N_PER, EDGE = 4.515e-3, 216.72e-6, 4, 1e-9
P_COL = "0.4817196mW"
BODIES = ["TIM", "dummySi", "bondtop", "logicSi", "logic", "logicBEOL", "bondsram", "sramSi",
          "tier", "sramBEOL"]

pts = []
for k in range(N_PER):
    t0 = k * PERIOD
    pts += [(t0, 1.0), (t0 + TP, 1.0), (t0 + TP + EDGE, 0.0), (t0 + PERIOD - EDGE, 0.0)]
pts.append((N_PER * PERIOD, 1.0))

def dataset(name, target):
    target.AddDataset(["NAME:" + name,
                       ["NAME:Coordinates"] + [["NAME:Coordinate", "X:=", x, "Y:=", y] for x, y in pts]])

ok_proj = attempt("project dataset $burst, %d points over %d periods" % (len(pts), N_PER),
                  lambda: dataset("$burst", oProject))
ok_des = attempt("design dataset burst", lambda: dataset("burst", oDesign))

done = False
for expr in (["%s*pwl($burst,Time)" % P_COL] if ok_proj else []) + (["%s*pwl(burst,Time)" % P_COL] if ok_des else []):
    if done:
        break
    done = attempt("heat generation on tier, TotalPower = %s" % expr,
                   lambda e=expr: oBnd.AssignHeatGeneration(["NAME:Qburst", "Objects:=", ["tier"],
                                                             "TotalPower:=", e]))

attempt("initial temperature 20 C on all bodies",
        lambda: oBnd.AssignInitialTemperature(["NAME:Tinit", "Objects:=", BODIES,
                                               "Temperature:=", "20cel"]))
