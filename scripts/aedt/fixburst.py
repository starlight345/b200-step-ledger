# -*- coding: utf-8 -*-
# AEDT IronPython -- after loadburst.py. The first heat-generation boundary referred to the
# PROJECT dataset $burst, which IcepakFEA does not resolve inside a boundary expression
# ("$burst is not a defined dataset name in this context"), although the assignment itself
# returned without error. Re-point it at the DESIGN dataset 'burst' (same 17 points).
#
# File name has no capitals or underscores: the remote session drops Shift.

oProject = oDesktop.GetActiveProject()
oDesign = oProject.GetActiveDesign()
oBnd = oDesign.GetModule("BoundarySetup")

def msg(text, level=0):
    oDesktop.AddMessage(oProject.GetName(), oDesign.GetName(), level, text)

EXPR = "0.4817196mW*pwl(burst,Time)"
ARGS = ["NAME:Qburst", "Objects:=", ["tier"], "TotalPower:=", EXPR]
try:
    oBnd.EditHeatGeneration("Qburst", ARGS)
    msg("OK   edited Qburst -> TotalPower = %s" % EXPR)
except Exception as e:
    msg("edit failed (%s); deleting and re-assigning" % e, 1)
    try:
        oBnd.DeleteBoundaries(["Qburst"])
        oBnd.AssignHeatGeneration(ARGS)
        msg("OK   re-assigned Qburst -> TotalPower = %s" % EXPR)
    except Exception as e2:
        msg("FAIL re-assign Qburst :: %s" % e2, 2)
try:
    msg("boundaries now: %s" % ", ".join(str(b) for b in oBnd.GetBoundaries()))
except Exception as e:
    msg("could not list boundaries: %s" % e, 1)
