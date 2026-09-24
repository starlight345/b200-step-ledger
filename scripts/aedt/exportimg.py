# -*- coding: utf-8 -*-
# AEDT IronPython -- Chrome Remote Desktop does not capture AEDT's OpenGL 3D view in this
# session, so render the temperature field to a file instead and look at the file.

oProject = oDesktop.GetActiveProject()
oDesign = oProject.GetActiveDesign()
oEditor = oDesign.SetActiveEditor("3D Modeler")
oF = oDesign.GetModule("FieldsReporter")

def msg(text, level=0):
    oDesktop.AddMessage(oProject.GetName(), oDesign.GetName(), level, text)

OBJS = ["TIM", "Si", "logic", "BEOL", "tier1_array", "tier1_periX", "tier1_periY", "ILD1",
        "tier2_array", "tier2_periX", "tier2_periY", "ILD2"]
TIER = ["tier2_array", "tier2_periX", "tier2_periY"]

def field_plot(name, objs):
    oF.CreateFieldPlot(
        ["NAME:" + name, "SolutionName:=", "Setup1 : Solution", "UserSpecifyName:=", 0,
         "UserSpecifyFolder:=", 0, "QuantityName:=", "Temp", "PlotFolder:=", "Temp",
         "StreamlinePlot:=", False, "AdjacentSidePlot:=", False, "FullModelPlot:=", False,
         "IntrinsicVar:=", "", "PlotGeomInfo:=", [1, "Volume", "ObjList", len(objs)] + objs,
         "FilterBoxes:=", [0],
         ["NAME:PlotOnVolumeSettings", "PlotIsoSurface:=", False, "PointSize:=", 1,
          "Refinement:=", 0, "CloudSpacing:=", 0.5, "CloudMinSpacing:=", -1,
          "CloudMaxSpacing:=", -1, "ShadingType:=", 0,
          ["NAME:Arrow3DSpacingSettings", "ArrowUniform:=", True, "ArrowSpacing:=", 0,
           "MinArrowSpacing:=", 0, "MaxArrowSpacing:=", 0], "GridColor:=", [255, 255, 255]],
         "EnableGaussianSmoothing:=", False, "SurfaceOnly:=", True],
        "VolumeFieldPlot")

def export(path, plot, orient):
    oEditor.ExportModelImageToFile(path, 1600, 1000,
        ["NAME:SaveImageParams", "ShowAxis:=", "True", "ShowGrid:=", "False",
         "ShowRuler:=", "True", "ShowRegion:=", "Default", "Selections:=", "",
         "FieldPlotSelections:=", plot, "Orientation:=", orient])

for label, fn in [
        ("field plot, whole stack", lambda: field_plot("TempStack", OBJS)),
        ("field plot, upper tier", lambda: field_plot("TempTier", TIER)),
        ("export stack image", lambda: export("C:/Users/user/Desktop/aedtstack.png", "TempStack", "isometric")),
        ("export tier image", lambda: export("C:/Users/user/Desktop/aedttier.png", "TempTier", "top")),
        ("export model image", lambda: export("C:/Users/user/Desktop/aedtmodel.png", "", "isometric"))]:
    try:
        fn()
        msg("OK   " + label)
    except Exception as e:
        msg("FAIL " + label + " :: " + str(e), 2)
