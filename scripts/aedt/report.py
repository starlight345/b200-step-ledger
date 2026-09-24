# -*- coding: utf-8 -*-
# AEDT IronPython -- after fixloads.py. Temperature profiles along three cut lines, as AEDT
# 2D reports. The reports are drawn in the GUI (unlike the OpenGL 3D view, which Chrome
# Remote Desktop does not show here), so they are what a full-window screenshot can carry.
#   xcut  tier-2 mid-plane, y = 200 um, x 0 -> 153: array, then the 20 um periphery band
#   ycut  tier-2 mid-plane, x = 60 um,  y 0 -> 518: array, then the 92 um periphery band
#   zcut  vertical through the whole stack at (143, 472) um, inside the periphery
# The lines are non-model objects, so the solution stays valid. SolveInside must be False:
# IcepakFEA refuses "solve inside" on vacuum ("invalid thermal properties"), which killed run 1.

oProject = oDesktop.GetActiveProject()
oDesign = oProject.GetActiveDesign()
oEditor = oDesign.SetActiveEditor("3D Modeler")
oF = oDesign.GetModule("FieldsReporter")
oRep = oDesign.GetModule("ReportSetup")
SOL = "Setup1 : Solution"
Z_T2 = 559.375                      # mid-thickness of tier 2 [um]

def msg(text, level=0):
    oDesktop.AddMessage(oProject.GetName(), oDesign.GetName(), level, text)

def line(name, p0, p1):
    oEditor.CreatePolyline(
        ["NAME:PolylineParameters", "IsPolylineCovered:=", True, "IsPolylineClosed:=", False,
         ["NAME:PolylinePoints",
          ["NAME:PLPoint", "X:=", "%gum" % p0[0], "Y:=", "%gum" % p0[1], "Z:=", "%gum" % p0[2]],
          ["NAME:PLPoint", "X:=", "%gum" % p1[0], "Y:=", "%gum" % p1[1], "Z:=", "%gum" % p1[2]]],
         ["NAME:PolylineSegments",
          ["NAME:PLSegment", "SegmentType:=", "Line", "StartIndex:=", 0, "NoOfPoints:=", 2]],
         ["NAME:PolylineXSection", "XSectionType:=", "None", "XSectionOrient:=", "Auto",
          "XSectionWidth:=", "0um", "XSectionTopWidth:=", "0um", "XSectionHeight:=", "0um",
          "XSectionNumSegments:=", "0", "XSectionBendType:=", "Corner"]],
        ["NAME:Attributes", "Name:=", name, "Flags:=", "NonModel#", "Color:=", "(0 0 0)",
         "Transparency:=", 0, "PartCoordinateSystem:=", "Global", "UDMId:=", "",
         "MaterialValue:=", "\"vacuum\"", "SurfaceMaterialValue:=", "\"\"",
         "SolveInside:=", False, "ShellElement:=", False, "ShellElementThickness:=", "0um",
         "IsMaterialEditable:=", True, "UseMaterialAppearance:=", False, "IsLightweight:=", False])

LINES = [("xcut", (0, 200, Z_T2), (153, 200, Z_T2)),
         ("ycut", (60, 0, Z_T2), (60, 518, Z_T2)),
         ("zcut", (143, 472, 0), (143, 472, 559.7))]
have = []
try:
    have = [str(n) for n in oEditor.GetObjectsInGroup("Lines")]
except Exception:
    pass
for name, p0, p1 in LINES:
    if name in have:
        continue
    try:
        line(name, p0, p1)
        msg("OK   line %s" % name)
    except Exception as e:
        msg("FAIL line %s :: %s" % (name, e), 2)

try:
    oF.CalcStack("clear"); oF.EnterQty("Temp")
    try:
        oF.AddNamedExpression("TempC", "Fields")
    except Exception:
        oF.AddNamedExpression("TempC")
    msg("OK   named expression TempC")
except Exception as e:
    msg("named expression TempC: %s" % e, 1)

try:
    oRep.DeleteReports(["Tier 2 temperature across the 20 um periphery band (y = 200 um)",
                        "Tier 2 temperature across the 92 um periphery band (x = 60 um)",
                        "Temperature through the stack at (143, 472) um"])
    msg("OK   deleted the empty reports from run 1")
except Exception as e:
    msg("delete reports: %s" % e, 1)

TITLES = {"xcut": "Tier 2 temperature across the 20 um periphery band (y = 200 um)",
          "ycut": "Tier 2 temperature across the 92 um periphery band (x = 60 um)",
          "zcut": "Temperature through the stack at (143, 472) um"}
for name, _, _ in LINES:
    done = False
    for qty in ("TempC", "Temp", "Temperature"):
        try:
            oRep.CreateReport(TITLES[name], "Fields", "Rectangular Plot", SOL,
                              ["Context:=", name, "PointsOnLine:=", 1000],
                              ["Distance:=", ["All"]],
                              ["X Component:=", "Distance", "Y Component:=", [qty]])
            msg("OK   report %s with %s" % (name, qty))
            done = True
            break
        except Exception as e:
            msg("  report %s with %s: %s" % (name, qty, e), 1)
    if not done:
        msg("FAIL report %s" % name, 2)
