# -*- coding: utf-8 -*-
# AEDT IronPython -- exportimg.py passed "VolumeFieldPlot" as the plot type and AEDT
# answered "Plot type is not valid"; the type is "Field" (and "Mesh" for a mesh plot).
# The offscreen export itself works (aedtmodel.png came out), so: make the plots again
# and render each one to a file, since the 3D view does not show over Chrome Remote Desktop.
#
# Plan-view plots include ILD2: it is the topmost body, 0.3 um of oxide over tier 2 with
# an adiabatic top, so its top face carries the tier-2 temperature pattern and would hide
# a plot drawn on tier 2 alone.

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
TOP = ["tier2_array", "tier2_periX", "tier2_periY", "ILD2"]

def head(name, qty, folder, objs):
    return ["NAME:" + name, "SolutionName:=", SOL, "UserSpecifyName:=", 1,
            "UserSpecifyFolder:=", 1, "QuantityName:=", qty, "PlotFolder:=", folder,
            "StreamlinePlot:=", False, "AdjacentSidePlot:=", False, "FullModelPlot:=", False,
            "IntrinsicVar:=", "", "PlotGeomInfo:=", [1, "Volume", "ObjList", len(objs)] + objs,
            "FilterBoxes:=", [0]]

def temp_plot(name, objs):
    oF.CreateFieldPlot(head(name, "Temp", "Temperature", objs) + [
        ["NAME:PlotOnVolumeSettings", "PlotIsoSurface:=", False, "PointSize:=", 1,
         "Refinement:=", 0, "CloudSpacing:=", 0.5, "CloudMinSpacing:=", -1,
         "CloudMaxSpacing:=", -1, "ShadingType:=", 0,
         ["NAME:Arrow3DSpacingSettings", "ArrowUniform:=", True, "ArrowSpacing:=", 0,
          "MinArrowSpacing:=", 0, "MaxArrowSpacing:=", 0], "GridColor:=", [255, 255, 255]],
        "EnableGaussianSmoothing:=", False, "SurfaceOnly:=", True], "Field")

def mesh_plot(name, objs):
    oF.CreateFieldPlot(head(name, "Mesh", "MeshPlots", objs) + [
        ["NAME:MeshSettings", "Scale factor:=", 100, "Transparency:=", 0,
         "Surface Only:=", True, "Add grid:=", True, "Refinement:=", 0,
         "Shading Type:=", 0, "Mesh line color:=", [0, 0, 0], "Mesh type:=", "Shaded"],
        "EnableGaussianSmoothing:=", False, "SurfaceOnly:=", True], "Mesh")

def export(fname, plot, orient):
    try:
        oF.UpdateAllFieldsPlots()
    except Exception:
        pass
    oEditor.ExportModelImageToFile(OUT + fname, 1600, 1000,
        ["NAME:SaveImageParams", "ShowAxis:=", "True", "ShowGrid:=", "False",
         "ShowRuler:=", "True", "ShowRegion:=", "Default", "Selections:=", "",
         "FieldPlotSelections:=", plot, "Orientation:=", orient])

def attempt(label, fn):
    try:
        fn()
        msg("OK   " + label)
        return True
    except Exception as e:
        msg("FAIL " + label + " :: " + str(e), 2)
        return False

attempt("temperature plot, whole stack", lambda: temp_plot("TempAll", ALL))
attempt("temperature plot, top of stack", lambda: temp_plot("TempTop", TOP))
attempt("mesh plot, whole stack", lambda: mesh_plot("MeshAll", ALL))
attempt("mesh plot, top of stack", lambda: mesh_plot("MeshTop", TOP))
try:
    msg("field plots now: %s" % ", ".join(list(oF.GetFieldPlotNames())))
except Exception as e:
    msg("GetFieldPlotNames: %s" % e, 1)

for fname, plot, orient in [("aedtfieldiso.png", "TempAll", "isometric"),
                            ("aedtfieldfront.png", "TempAll", "front"),
                            ("aedtfieldtop.png", "TempTop", "top"),
                            ("aedtmeshiso.png", "MeshAll", "isometric"),
                            ("aedtmeshtop.png", "MeshTop", "top")]:
    attempt("export " + fname, lambda f=fname, p=plot, o=orient: export(f, p, o))
