# -*- coding: utf-8 -*-
# AEDT IronPython -- the offscreen export draws the field-plot surface and the body face at the
# same depth, and the opaque body wins (legend present, contour missing, z-fighting speckle).
# Make the bodies fully transparent for the export, render, then put the transparency back.

oProject = oDesktop.GetActiveProject()
oDesign = oProject.GetActiveDesign()
oEditor = oDesign.SetActiveEditor("3D Modeler")
oF = oDesign.GetModule("FieldsReporter")
OUT = "C:/Users/user/Desktop/"

def msg(text, level=0):
    oDesktop.AddMessage(oProject.GetName(), oDesign.GetName(), level, text)

ALL = ["TIM", "Si", "logic", "BEOL", "tier1_array", "tier1_periX", "tier1_periY", "ILD1",
       "tier2_array", "tier2_periX", "tier2_periY", "ILD2"]

def transparency(v):
    oEditor.ChangeProperty(["NAME:AllTabs", ["NAME:Geometry3DAttributeTab",
                            ["NAME:PropServers"] + ALL,
                            ["NAME:ChangedProps", ["NAME:Transparent", "Value:=", v]]]])

def export(fname, plot, orient):
    oEditor.ExportModelImageToFile(OUT + fname, 1600, 1000,
        ["NAME:SaveImageParams", "ShowAxis:=", "True", "ShowGrid:=", "False",
         "ShowRuler:=", "True", "ShowRegion:=", "Default", "Selections:=", "",
         "FieldPlotSelections:=", plot, "Orientation:=", orient])

try:
    transparency(1)
    msg("OK   bodies transparent for export")
except Exception as e:
    msg("FAIL transparency :: %s" % e, 2)
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
    transparency(0)
    msg("OK   transparency restored")
except Exception as e:
    msg("FAIL restore :: %s" % e, 2)
