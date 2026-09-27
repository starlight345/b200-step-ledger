# -*- coding: utf-8 -*-
# AEDT IronPython -- after fixburst.py. Point monitors for the transient time history:
#   ptier   mid-plane of the SRAM device layer (the tier), z = 823.6 um  -- the quantity
#   plogic  mid-plane of the logic device layer, z = 808.1 um
# The column is laterally uniform, so the x-y position (5, 5) um is immaterial.
#
# File name has no capitals or underscores: the remote session drops Shift.

oProject = oDesktop.GetActiveProject()
oDesign = oProject.GetActiveDesign()
oEditor = oDesign.SetActiveEditor("3D Modeler")

def msg(text, level=0):
    oDesktop.AddMessage(oProject.GetName(), oDesign.GetName(), level, text)

PTS = [("ptier", 823.6), ("plogic", 808.1)]
for name, z in PTS:
    try:
        oEditor.CreatePoint(["NAME:PointParameters", "PointX:=", "5um", "PointY:=", "5um",
                             "PointZ:=", "%gum" % z],
                            ["NAME:Attributes", "Name:=", name, "Color:=", "(143 175 143)"])
        msg("OK   point %s at z = %g um" % (name, z))
    except Exception as e:
        msg("FAIL point %s :: %s" % (name, e), 2)

for modname in ("Monitor", "MonitorSetup"):
    try:
        oMon = oDesign.GetModule(modname)
    except Exception as e:
        msg("no module %s: %s" % (modname, e), 1)
        continue
    for name, _ in PTS:
        for args in (["NAME:mon" + name, "Quantities:=", ["Temperature"], "Points:=", [name]],
                     ["NAME:mon" + name, "Quantities:=", ["Temperature"], "Objects:=", [name]]):
            try:
                oMon.AssignPointMonitor(args)
                msg("OK   %s.AssignPointMonitor(%s)" % (modname, args[3]))
                break
            except Exception as e:
                msg("try %s.AssignPointMonitor %s :: %s" % (modname, args[3], e), 1)
    break
