# -*- coding: utf-8 -*-
# AEDT IronPython -- find the field-calculator quantity name that IcepakFEA uses for
# temperature, then report max/min per body group with it.

oProject = oDesktop.GetActiveProject()
oDesign = oProject.GetActiveDesign()
oF = oDesign.GetModule("FieldsReporter")
oRep = oDesign.GetModule("ReportSetup")
SOL = "Setup1 : Solution"

def msg(text, level=0):
    oDesktop.AddMessage(oProject.GetName(), oDesign.GetName(), level, text)

for cat in ("Calculator Expressions", "Temperature", "Fields"):
    try:
        q = oRep.GetAvailableReportQuantities("Fields", "Rectangular Plot", SOL, "", cat)
        msg("report quantities [%s]: %s" % (cat, ", ".join(list(q)[:20])))
    except Exception as e:
        msg("GetAvailableReportQuantities(%s) failed: %s" % (cat, e), 1)
try:
    msg("named expressions: %s" % ", ".join(list(oF.GetNamedExpressions())))
except Exception as e:
    msg("GetNamedExpressions failed: %s" % e, 1)

WORKS = None
for name in ("Temperature", "Temp", "TEMP", "temperature", "Temperature_C", "T",
             "NodalTemperature", "Nodal Temperature", "HeatFlux", "Heat Flux"):
    try:
        oF.CalcStack("clear")
        oF.EnterQty(name)
        msg("EnterQty accepts '%s'" % name)
        if WORKS is None and "heat" not in name.lower():
            WORKS = name
    except Exception as e:
        msg("EnterQty rejects '%s'" % name, 1)

if WORKS:
    GROUPS = [("tier periphery", ["tier1_periX", "tier1_periY", "tier2_periX", "tier2_periY"]),
              ("tier array", ["tier1_array", "tier2_array"]),
              ("logic", ["logic"]), ("TIM", ["TIM"])]
    def ev(obj, op):
        oF.CalcStack("clear"); oF.EnterQty(WORKS); oF.EnterVol(obj); oF.CalcOp(op)
        try:
            oF.ClcEval(SOL, [], "Fields")
        except Exception:
            oF.ClcEval(SOL, [])
        return float(str(oF.GetTopEntryValue(SOL, [])[0]).split()[0])
    for label, objs in GROUPS:
        try:
            msg("[%s] %-14s max %.6f  min %.6f" % (WORKS, label,
                max(ev(o, "Maximum") for o in objs), min(ev(o, "Minimum") for o in objs)))
        except Exception as e:
            msg("eval %s failed: %s" % (label, e), 2)
