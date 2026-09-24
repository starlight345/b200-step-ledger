# -*- coding: utf-8 -*-
# AEDT IronPython -- surfplot.py put SurfTop in the same plot folder as SurfAll, and a folder
# shares one colour scale: the plan view came out one flat red on the 93.6-100.1 C stack
# scale, which hides a 0.03 K pattern. Give the plan view its own folder, so the automatic
# scale spans only the top of the stack, then re-render it.

oProject = oDesktop.GetActiveProject()
oDesign = oProject.GetActiveDesign()
oEditor = oDesign.SetActiveEditor("3D Modeler")
oF = oDesign.GetModule("FieldsReporter")
SOL = "Setup1 : Solution"
OUT = "C:/Users/user/Desktop/"

def msg(text, level=0):
    oDesktop.AddMessage(oProject.GetName(), oDesign.GetName(), level, text)

ALL = ["TIM", "Si", "logic", "BEOL", "tier1_array", "tier1_periX", "tier1_periY", "ILD1",
       "tier2_array", "tier2_periX", "tier2_periY", "ILD2"]

try:
    oF.DeleteFieldPlot(["SurfTop"])
    msg("OK   deleted SurfTop (shared scale)")
except Exception as e:
    msg("delete SurfTop: %s" % e, 1)

ids = [str(f) for f in oEditor.GetFaceIDs("ILD2")]
try:
    oF.CreateFieldPlot(
        ["NAME:TierTop", "SolutionName:=", SOL, "UserSpecifyName:=", 1, "UserSpecifyFolder:=", 1,
         "QuantityName:=", "Temperature", "PlotFolder:=", "TierTop",
         "StreamlinePlot:=", False, "AdjacentSidePlot:=", False, "FullModelPlot:=", False,
         "IntrinsicVar:=", "", "PlotGeomInfo:=", [1, "Surface", "FacesList", len(ids)] + ids,
         "FilterBoxes:=", [0],
         ["NAME:PlotOnSurfaceSettings", "Filled:=", False, "IsoValType:=", "Fringe",
          "AddGrid:=", False, "MapTransparency:=", True, "Refinement:=", 0, "Transparency:=", 0,
          "SmoothingLevel:=", 0, "ShadingType:=", 0,
          ["NAME:Arrow3DSpacingSettings", "ArrowUniform:=", True, "ArrowSpacing:=", 0,
           "MinArrowSpacing:=", 0, "MaxArrowSpacing:=", 0], "GridColor:=", [255, 255, 255]],
         "EnableGaussianSmoothing:=", False], "Field")
    msg("OK   TierTop on %d faces, own folder" % len(ids))
except Exception as e:
    msg("FAIL TierTop :: %s" % e, 2)

def transparency(v):
    oEditor.ChangeProperty(["NAME:AllTabs", ["NAME:Geometry3DAttributeTab",
                            ["NAME:PropServers"] + ALL,
                            ["NAME:ChangedProps", ["NAME:Transparent", "Value:=", v]]]])

try:
    transparency(1)
    for fname, orient in [("aedttiertop.png", "top"), ("aedttieriso.png", "isometric")]:
        oEditor.ExportModelImageToFile(OUT + fname, 1600, 1000,
            ["NAME:SaveImageParams", "ShowAxis:=", "True", "ShowGrid:=", "False",
             "ShowRuler:=", "True", "ShowRegion:=", "Default", "Selections:=", "",
             "FieldPlotSelections:=", "TierTop", "Orientation:=", orient])
        msg("OK   export " + fname)
except Exception as e:
    msg("FAIL export :: %s" % e, 2)
finally:
    try:
        transparency(0)
        msg("OK   transparency restored")
    except Exception as e:
        msg("FAIL restore :: %s" % e, 2)
