# -*- coding: utf-8 -*-
# AEDT IronPython -- after the solve. Prints max/min temperature per body group to the
# Message Manager so the result can be read without the 3D view (which Chrome Remote
# Desktop does not capture). Compare with MAPDL prod_k1_phi90 load step 1: tier max
# 100.03078 C, logic max ~100.00 C.

oProject = oDesktop.GetActiveProject()
oDesign = oProject.GetActiveDesign()

def msg(text, level=0):
    oDesktop.AddMessage(oProject.GetName(), oDesign.GetName(), level, text)

oRep = oDesign.GetModule("ReportSetup")
oF = oDesign.GetModule("FieldsReporter")

sols = []
for cat in ("Fields", "Temperature", ""):
    try:
        s = oRep.GetAvailableSolutions(cat)
        if s:
            sols = list(s)
            msg("solutions (%s): %s" % (cat or "any", ", ".join(sols)))
            break
    except Exception as e:
        msg("GetAvailableSolutions(%s) failed: %s" % (cat, e), 1)
if not sols:
    sols = ["Setup1 : Solution", "Setup1 : Steady", "Setup1 : LastAdaptive"]
    msg("falling back to guessed solution names", 1)

GROUPS = [
    ("tier periphery", ["tier1_periX", "tier1_periY", "tier2_periX", "tier2_periY"]),
    ("tier array",     ["tier1_array", "tier2_array"]),
    ("logic",          ["logic"]),
    ("TIM",            ["TIM"]),
]

def evaluate(sol, obj, op):
    oF.CalcStack("clear")
    oF.EnterQty("Temperature")
    oF.EnterVol(obj)
    oF.CalcOp(op)
    try:
        oF.ClcEval(sol, [], "Fields")
    except Exception:
        oF.ClcEval(sol, [])
    v = oF.GetTopEntryValue(sol, [])
    return float(str(v[0]).split()[0])

for sol in sols:
    try:
        for label, objs in GROUPS:
            mx = max(evaluate(sol, o, "Maximum") for o in objs)
            mn = min(evaluate(sol, o, "Minimum") for o in objs)
            msg("[%s] %-14s max %.6f  min %.6f" % (sol, label, mx, mn))
        break
    except Exception as e:
        msg("evaluation with '%s' failed: %s" % (sol, e), 2)
