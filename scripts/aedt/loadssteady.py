# -*- coding: utf-8 -*-
# AEDT IronPython -- run after build_macro_c2.py in the same IcepakFEA (Steady-State
# Thermal) design. Assigns the loads of the MAPDL representative case, per one C2 macro:
#   logic plane      349.35 W/die  ->  34.6092 mW in this macro
#   tier, averaged   38 W/die burst x 4.80% duty  ->  0.180699 mW in this macro,
#                    phi = 0.9 of it in the L-shaped periphery, 0.1 in the array
#   sink             convection on the TIM outer face, h = 8187.4 W/m2K, 40 C
# All four lateral faces stay at the default (adiabatic): a mirrored array of macros.
# Reference (MAPDL, same model, load step 1 of prod_k1_phi90): tier max 100.03078 C.
#
# The file name has no capitals or underscores on purpose: the remote session drops
# Shift, so it has to be typeable if it ever needs to be typed.

oProject = oDesktop.GetActiveProject()
oDesign = oProject.GetActiveDesign()
oEditor = oDesign.SetActiveEditor("3D Modeler")
oBnd = oDesign.GetModule("BoundarySetup")

def msg(text, level=0):
    oDesktop.AddMessage(oProject.GetName(), oDesign.GetName(), level, text)

def attempt(label, fn):
    try:
        fn()
        msg("OK   " + label)
    except Exception as e:
        msg("FAIL " + label + " :: " + str(e), 2)

def sink():
    fid = oEditor.GetFaceByPosition(["NAME:FaceParameters", "BodyName:=", "TIM",
                                     "XPosition:=", "76.5um", "YPosition:=", "259um",
                                     "ZPosition:=", "0um"])
    msg("sink face id = %s" % fid)
    oBnd.AssignConvection(["NAME:Sink_h8187", "Faces:=", [fid],
                           "Temperature:=", "40cel", "Uniform:=", True,
                           "FilmCoeff:=", "8187.4w_per_m2kel"])

attempt("convection on TIM outer face", sink)
attempt("heat generation, logic 34.6092 mW", lambda: oBnd.AssignHeatGeneration(
    ["NAME:Q_logic", "Objects:=", ["logic"], "TotalPower:=", "34.6092mW"]))
# CORRECTION (2026-09-24): IcepakFEA applies "TotalPower" to EACH object of a heat-generation
# boundary, not split among them. The first version put the four periphery bodies under one
# boundary and the two array bodies under another, so the tier got 4x / 2x its power (the
# sink face read 94.39 C instead of 93.62). One boundary per body, the periphery split by
# body volume, the array equally between tiers. fixloads.py migrated the existing project.
PERI_MW, ARR_MW = 0.162629, 0.0180699
AX_, AY_ = 20.0 * 518.0, 133.0 * 92.0
for obj, mw in [("tier1_periX", PERI_MW / 2 * AX_ / (AX_ + AY_)), ("tier2_periX", PERI_MW / 2 * AX_ / (AX_ + AY_)),
                ("tier1_periY", PERI_MW / 2 * AY_ / (AX_ + AY_)), ("tier2_periY", PERI_MW / 2 * AY_ / (AX_ + AY_)),
                ("tier1_array", ARR_MW / 2), ("tier2_array", ARR_MW / 2)]:
    attempt("heat generation, %s %.7g mW" % (obj, mw),
            lambda o=obj, w=mw: oBnd.AssignHeatGeneration(
                ["NAME:Q_" + o, "Objects:=", [o], "TotalPower:=", "%.7gmW" % w]))
