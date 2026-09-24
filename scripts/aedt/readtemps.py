# -*- coding: utf-8 -*-
# AEDT IronPython -- read the solved field back into the Message Manager, next to the MAPDL and
# analytic numbers it is checked against, so a screenshot of the window carries the comparison.
# Nothing is re-solved.

oProject = oDesktop.GetActiveProject()
oDesign = oProject.GetActiveDesign()
oF = oDesign.GetModule("FieldsReporter")
SOL = "Setup1 : Solution"

def msg(text, level=0):
    oDesktop.AddMessage(oProject.GetName(), oDesign.GetName(), level, text)

def ev(obj, op):
    oF.CalcStack("clear"); oF.EnterQty("Temp"); oF.EnterVol(obj); oF.CalcOp(op)
    try:
        oF.ClcEval(SOL, [], "Fields")
    except Exception:
        oF.ClcEval(SOL, [])
    return float(str(oF.GetTopEntryValue(SOL, [])[0]).split()[0])

per = max(ev(o, "Maximum") for o in ["tier1_periX", "tier1_periY", "tier2_periX", "tier2_periY"])
arr = max(ev(o, "Maximum") for o in ["tier1_array", "tier2_array"])
logic = ev("logic", "Maximum")
sink = ev("TIM", "Minimum")
tim_top = ev("TIM", "Maximum")
msg("C2 macro unit cell, steady state at duty-averaged power (logic 34.609 mW + tier 0.181 mW, 90% in periphery)")
msg("  tier peak (periphery)   AEDT %.6f C   MAPDL 100.030780 C   diff %+.2f mK" % (per, (per - 100.03078) * 1e3))
msg("  tier array max          AEDT %.6f C" % arr)
msg("  logic max               AEDT %.6f C" % logic)
msg("  sink face (TIM bottom)  AEDT %.6f C   analytic 93.614970 C   diff %+.2f mK" % (sink, (sink - 93.614970) * 1e3))
msg("  TIM drop                AEDT %.4f K    analytic 4.3897 K" % (tim_top - sink))
