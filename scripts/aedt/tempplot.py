# -*- coding: utf-8 -*-
# AEDT IronPython -- second pass at the field images (fieldimg.py, run 1):
#   * a plot on "Temp" was created and at once "removed due to deletion of quantity
#     expression": "Temp" is the calculator's name, not a plot quantity. Try the plot
#     names in turn and keep the first whose plot survives; if none does, wrap the
#     calculator quantity in a named expression and plot that.
#   * a mesh plot with plot type "Mesh" is "not valid"; the type is "Field" with the
#     quantity "Mesh".

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

def plots():
    try:
        return [str(p) for p in oF.GetFieldPlotNames()]
    except Exception:
        return []

def head(name, qty, folder, objs):
    return ["NAME:" + name, "SolutionName:=", SOL, "UserSpecifyName:=", 1,
            "UserSpecifyFolder:=", 1, "QuantityName:=", qty, "PlotFolder:=", folder,
            "StreamlinePlot:=", False, "AdjacentSidePlot:=", False, "FullModelPlot:=", False,
            "IntrinsicVar:=", "", "PlotGeomInfo:=", [1, "Volume", "ObjList", len(objs)] + objs,
            "FilterBoxes:=", [0]]

def temp_plot(name, objs, qty):
    oF.CreateFieldPlot(head(name, qty, "Thermal", objs) + [
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
        "EnableGaussianSmoothing:=", False], "Field")

def survives(name, make):
    try:
        make()
    except Exception as e:
        msg("  %s: create raised %s" % (name, e), 1)
        return False
    ok = name in plots()
    msg("  %s: %s" % (name, "kept" if ok else "not kept"), 0 if ok else 1)
    return ok

QTY = None
for i, q in enumerate(["Temperature", "Temp", "Temperature_C", "Nodal Temperature"]):
    probe = "probe%d" % i
    if survives(probe + " (" + q + ")", lambda p=probe, q=q: temp_plot(p, ["ILD2"], q)) or probe in plots():
        QTY = q
        break
if QTY is None:
    try:
        oF.CalcStack("clear")
        oF.EnterQty("Temp")
        try:
            oF.AddNamedExpression("TempC", "Fields")
        except Exception:
            oF.AddNamedExpression("TempC")
        msg("named expression TempC = Temp added")
        if survives("probe9 (TempC)", lambda: temp_plot("probe9", ["ILD2"], "TempC")) \
                or "probe9" in plots():
            QTY = "TempC"
    except Exception as e:
        msg("named-expression route failed: %s" % e, 2)
msg("temperature plot quantity = %s ; plots now: %s" % (QTY, ", ".join(plots())))

made = {}
if QTY:
    made["TempAll"] = survives("TempAll", lambda: temp_plot("TempAll", ALL, QTY))
    made["TempTop"] = survives("TempTop", lambda: temp_plot("TempTop", TOP, QTY))
made["MeshAll"] = survives("MeshAll", lambda: mesh_plot("MeshAll", ALL))
made["MeshTop"] = survives("MeshTop", lambda: mesh_plot("MeshTop", TOP))

def export(fname, plot, orient):
    oEditor.ExportModelImageToFile(OUT + fname, 1600, 1000,
        ["NAME:SaveImageParams", "ShowAxis:=", "True", "ShowGrid:=", "False",
         "ShowRuler:=", "True", "ShowRegion:=", "Default", "Selections:=", "",
         "FieldPlotSelections:=", plot, "Orientation:=", orient])

for fname, plot, orient in [("aedtfieldiso.png", "TempAll", "isometric"),
                            ("aedtfieldfront.png", "TempAll", "front"),
                            ("aedtfieldtop.png", "TempTop", "top"),
                            ("aedtmeshiso.png", "MeshAll", "isometric"),
                            ("aedtmeshtop.png", "MeshTop", "top")]:
    if not made.get(plot):
        msg("skip %s (no %s plot)" % (fname, plot), 1)
        continue
    try:
        export(fname, plot, orient)
        msg("OK   export " + fname)
    except Exception as e:
        msg("FAIL export %s :: %s" % (fname, e), 2)
