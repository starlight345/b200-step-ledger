# -*- coding: utf-8 -*-
# AEDT IronPython -- correct the tier loads, re-solve, re-read, re-render.
#
# loadssteady.py gave one heat-generation boundary to the four periphery bodies and one to
# the two array bodies. IcepakFEA applies "TotalPower" to EACH object of a boundary, not
# split among them, so the tier received 4x (periphery) and 2x (array) the intended power:
# 35.2959 mW in the cell instead of 34.7899. The first solve shows it to the millikelvin --
# the sink face came out 94.3938 C against 94.3947 predicted for 35.2959 mW (93.6150 for the
# intended 34.7899) -- so the 0.10 K tier-over-logic rise it reported was the load, not the
# tetrahedral mesh as first assumed.
#
# Fix: one boundary per body, the periphery split by body volume (uniform density across
# the L), the array split equally between the two tiers.

oProject = oDesktop.GetActiveProject()
oDesign = oProject.GetActiveDesign()
oEditor = oDesign.SetActiveEditor("3D Modeler")
oBnd = oDesign.GetModule("BoundarySetup")
oF = oDesign.GetModule("FieldsReporter")
SOL = "Setup1 : Solution"
OUT = "C:/Users/user/Desktop/"

def msg(text, level=0):
    oDesktop.AddMessage(oProject.GetName(), oDesign.GetName(), level, text)

PERI_MW, ARR_MW = 0.162629, 0.0180699          # per C2 cell, both tiers together
AX_, AY_ = 20.0 * 518.0, 133.0 * 92.0          # footprint of periX and periY [um2]
per_x = PERI_MW / 2.0 * AX_ / (AX_ + AY_)
per_y = PERI_MW / 2.0 * AY_ / (AX_ + AY_)
LOADS = [("tier1_periX", per_x), ("tier2_periX", per_x),
         ("tier1_periY", per_y), ("tier2_periY", per_y),
         ("tier1_array", ARR_MW / 2.0), ("tier2_array", ARR_MW / 2.0)]

try:
    msg("boundaries before: %s" % ", ".join(list(oBnd.GetBoundaries())))
except Exception as e:
    msg("GetBoundaries: %s" % e, 1)
try:
    oBnd.DeleteBoundaries(["Q_tier_periphery", "Q_tier_array"])
    msg("OK   deleted the two multi-body tier boundaries")
except Exception as e:
    msg("FAIL delete :: %s" % e, 2)

total = 34.6092
for obj, mw in LOADS:
    try:
        oBnd.AssignHeatGeneration(["NAME:Q_" + obj, "Objects:=", [obj],
                                   "TotalPower:=", "%.7gmW" % mw])
        total += mw
        msg("OK   Q_%s = %.7g mW" % (obj, mw))
    except Exception as e:
        msg("FAIL Q_%s :: %s" % (obj, e), 2)
msg("cell power now %.6f mW (intended 34.789899); sink face should read %.4f C"
    % (total, 40.0 + total * 1e-3 / (153e-6 * 518e-6) / 8187.4))

try:
    oDesign.Analyze("Setup1")
    msg("OK   re-solved Setup1 with per-body loads")
except Exception as e:
    msg("FAIL analyze :: %s" % e, 2)

def ev(obj, op):
    oF.CalcStack("clear"); oF.EnterQty("Temp"); oF.EnterVol(obj); oF.CalcOp(op)
    try:
        oF.ClcEval(SOL, [], "Fields")
    except Exception:
        oF.ClcEval(SOL, [])
    return float(str(oF.GetTopEntryValue(SOL, [])[0]).split()[0])

GROUPS = [("tier periphery", ["tier1_periX", "tier1_periY", "tier2_periX", "tier2_periY"]),
          ("tier array", ["tier1_array", "tier2_array"]),
          ("logic", ["logic"]), ("Si", ["Si"]), ("TIM", ["TIM"])]
for label, objs in GROUPS:
    try:
        msg("[per-body loads] %-14s max %.6f  min %.6f" % (label,
            max(ev(o, "Maximum") for o in objs), min(ev(o, "Minimum") for o in objs)))
    except Exception as e:
        msg("eval %s failed: %s" % (label, e), 2)

def export(fname, plot, orient):
    oEditor.ExportModelImageToFile(OUT + fname, 1600, 1000,
        ["NAME:SaveImageParams", "ShowAxis:=", "True", "ShowGrid:=", "False",
         "ShowRuler:=", "True", "ShowRegion:=", "Default", "Selections:=", "",
         "FieldPlotSelections:=", plot, "Orientation:=", orient])

try:
    oF.UpdateAllFieldsPlots()
except Exception:
    pass
for fname, plot, orient in [("aedtfieldiso.png", "TempAll", "isometric"),
                            ("aedtfieldfront.png", "TempAll", "front"),
                            ("aedtfieldtop.png", "TempTop", "top"),
                            ("aedtmeshiso.png", "MeshAll", "isometric"),
                            ("aedtmeshtop.png", "MeshTop", "top")]:
    try:
        export(fname, plot, orient)
        msg("OK   export " + fname)
    except Exception as e:
        msg("FAIL export %s :: %s" % (fname, e), 2)

try:
    oProject.Save()
    msg("OK   project saved")
except Exception as e:
    msg("FAIL save :: %s" % e, 2)
