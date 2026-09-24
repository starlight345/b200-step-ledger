# -*- coding: utf-8 -*-
# AEDT IronPython -- the default FEA mesh put 21-43 um tetrahedra into 0.05 um tiers
# (aspect ratio ~800) and the solution came back with negative temperatures in the TIM,
# which a steady conduction problem with positive sources and a 40 C sink cannot have.
# Refine the thin layers with a length-based mesh operation, re-solve, and report.
# The field-calculator quantity name in IcepakFEA is "Temp" (found by probeqty.py).

oProject = oDesktop.GetActiveProject()
oDesign = oProject.GetActiveDesign()
SOL = "Setup1 : Solution"

def msg(text, level=0):
    oDesktop.AddMessage(oProject.GetName(), oDesign.GetName(), level, text)

THIN = ["tier1_array", "tier1_periX", "tier1_periY", "ILD1",
        "tier2_array", "tier2_periX", "tier2_periY", "ILD2", "BEOL", "logic"]
oMesh = oDesign.GetModule("MeshSetup")
try:
    oMesh.AssignLengthOp(["NAME:thin_layers_4um", "RefineInside:=", True, "Enabled:=", True,
                          "Objects:=", THIN, "RestrictElem:=", False, "NumMaxElem:=", "1000",
                          "RestrictLength:=", True, "MaxLength:=", "4um"])
    msg("OK   mesh operation: max length 4 um on %d thin bodies" % len(THIN))
except Exception as e:
    msg("FAIL mesh operation :: %s" % e, 2)

try:
    oDesign.Analyze("Setup1")
    msg("OK   re-solved Setup1")
except Exception as e:
    msg("FAIL analyze :: %s" % e, 2)

oF = oDesign.GetModule("FieldsReporter")
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
        msg("[4um mesh] %-14s max %.6f  min %.6f" % (label,
            max(ev(o, "Maximum") for o in objs), min(ev(o, "Minimum") for o in objs)))
    except Exception as e:
        msg("eval %s failed: %s" % (label, e), 2)
