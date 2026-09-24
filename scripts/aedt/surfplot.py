# -*- coding: utf-8 -*-
# AEDT IronPython -- contour.py showed the volume plots render as a point cloud in the
# offscreen export. Use surface plots on the bodies' faces instead (the usual fringe look),
# with the bodies transparent during the export so the faces do not hide the plot.
#   SurfAll  every face of every body            -> isometric and front views
#   SurfTop  the faces of ILD2, the topmost body  -> plan view; its top face carries the
#            tier-2 pattern (0.3 um oxide over tier 2, adiabatic top)

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

def faces(objs):
    ids = []
    for o in objs:
        ids += [str(f) for f in oEditor.GetFaceIDs(o)]    # strings: ints give "Plot definition data is not valid"
    return ids

def surf_plot(name, objs):
    ids = faces(objs)
    oF.CreateFieldPlot(
        ["NAME:" + name, "SolutionName:=", SOL, "UserSpecifyName:=", 1, "UserSpecifyFolder:=", 1,
         "QuantityName:=", "Temperature", "PlotFolder:=", "Thermal",
         "StreamlinePlot:=", False, "AdjacentSidePlot:=", False, "FullModelPlot:=", False,
         "IntrinsicVar:=", "", "PlotGeomInfo:=", [1, "Surface", "FacesList", len(ids)] + ids,
         "FilterBoxes:=", [0],
         ["NAME:PlotOnSurfaceSettings", "Filled:=", False, "IsoValType:=", "Fringe",
          "AddGrid:=", False, "MapTransparency:=", True, "Refinement:=", 0, "Transparency:=", 0,
          "SmoothingLevel:=", 0, "ShadingType:=", 0,
          ["NAME:Arrow3DSpacingSettings", "ArrowUniform:=", True, "ArrowSpacing:=", 0,
           "MinArrowSpacing:=", 0, "MaxArrowSpacing:=", 0], "GridColor:=", [255, 255, 255]],
         "EnableGaussianSmoothing:=", False], "Field")
    return len(ids)

def transparency(v):
    oEditor.ChangeProperty(["NAME:AllTabs", ["NAME:Geometry3DAttributeTab",
                            ["NAME:PropServers"] + ALL,
                            ["NAME:ChangedProps", ["NAME:Transparent", "Value:=", v]]]])

def export(fname, plot, orient):
    oEditor.ExportModelImageToFile(OUT + fname, 1600, 1000,
        ["NAME:SaveImageParams", "ShowAxis:=", "True", "ShowGrid:=", "False",
         "ShowRuler:=", "True", "ShowRegion:=", "Default", "Selections:=", "",
         "FieldPlotSelections:=", plot, "Orientation:=", orient])

for name, objs in [("SurfAll", ALL), ("SurfTop", ["ILD2"])]:
    try:
        msg("OK   %s on %d faces" % (name, surf_plot(name, objs)))
    except Exception as e:
        msg("FAIL %s :: %s" % (name, e), 2)

try:
    transparency(1)
except Exception as e:
    msg("FAIL transparency :: %s" % e, 2)
for fname, plot, orient in [("aedtsurfiso.png", "SurfAll", "isometric"),
                            ("aedtsurffront.png", "SurfAll", "front"),
                            ("aedtsurftop.png", "SurfTop", "top")]:
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
