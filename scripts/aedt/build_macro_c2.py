# -*- coding: utf-8 -*-
# AEDT IronPython script -- run inside Ansys Electronics Desktop via Tools > Run Script.
#
# Builds the same C2 SRAM macro unit cell as scripts/mapdl_macro.py in the ACTIVE
# IcepakFEA design: geometry, materials, and nothing else. Loads and the analysis setup
# are assigned afterwards so each step can be checked on screen.
#
# Stack (z = 0 is the heat-sink side), all dimensions in um, identical to
# thermal_stack_solver.build_stack(n_tiers=2):
#   TIM 50 | Si 500 | logic 1 | BEOL 8 | tier 0.05 | ILD 0.3 | tier 0.05 | ILD 0.3
# Macro 153 x 518 um (device team, C2). Each tier is split into the bare array
# 133 x 426 um (the C1 macro) and the L-shaped periphery around it (28.5% of the area),
# the periphery as two boxes: a 20 um band along x = 133..153 and a 92 um band along
# y = 426..518.

oProject = oDesktop.GetActiveProject()
oDesign = oProject.GetActiveDesign()
oEditor = oDesign.SetActiveEditor("3D Modeler")
oEditor.SetModelUnits(["NAME:Units Parameter", "Units:=", "um", "Rescale:=", False])

oDef = oProject.GetDefinitionManager()

# name, k [W/m/K], rho [kg/m3], cp [J/kg/K] -- the MAT table of thermal_stack_solver.py
MATS = [
    ("TIM_polymer", "5.0",  "2500", "800"),
    ("Si_90C",      "110",  "2330", "700"),
    ("BEOL_lowk",   "2.5",  "2300", "900"),
    ("aIGZO",       "1.6",  "6100", "340"),
]
for name, k, rho, cp in MATS:
    if not oDef.DoesMaterialExist(name):
        oDef.AddMaterial([
            "NAME:" + name,
            "CoordinateSystemType:=", "Cartesian",
            "BulkOrSurfaceType:=", 1,
            ["NAME:PhysicsTypes", "set:=", ["Thermal"]],
            "thermal_conductivity:=", k,
            "mass_density:=", rho,
            "specific_heat:=", cp,
        ])

MX, MY = 153.0, 518.0          # macro
AX, AY = 133.0, 426.0          # bare array (C1 macro)

def box(name, x, y, z, dx, dy, dz, mat, color):
    oEditor.CreateBox(
        ["NAME:BoxParameters",
         "XPosition:=", "%gum" % x, "YPosition:=", "%gum" % y, "ZPosition:=", "%gum" % z,
         "XSize:=", "%gum" % dx, "YSize:=", "%gum" % dy, "ZSize:=", "%gum" % dz],
        ["NAME:Attributes",
         "Name:=", name, "Flags:=", "", "Color:=", color, "Transparency:=", 0,
         "PartCoordinateSystem:=", "Global", "UDMId:=", "",
         "MaterialValue:=", "\"%s\"" % mat, "SurfaceMaterialValue:=", "\"\"",
         "SolveInside:=", True, "ShellElement:=", False, "ShellElementThickness:=", "0mm",
         "IsMaterialEditable:=", True, "UseMaterialAppearance:=", False,
         "IsLightweight:=", False])

z = 0.0
for name, t, mat, color in [("TIM", 50.0, "TIM_polymer", "(190 190 190)"),
                            ("Si", 500.0, "Si_90C", "(128 128 160)"),
                            ("logic", 1.0, "Si_90C", "(90 90 200)"),
                            ("BEOL", 8.0, "BEOL_lowk", "(200 170 110)")]:
    box(name, 0, 0, z, MX, MY, t, mat, color)
    z += t

for i in (1, 2):
    t = 0.05
    box("tier%d_array" % i, 0, 0, z, AX, AY, t, "aIGZO", "(230 90 90)")
    box("tier%d_periX" % i, AX, 0, z, MX - AX, MY, t, "aIGZO", "(250 200 60)")
    box("tier%d_periY" % i, 0, AY, z, AX, MY - AY, t, "aIGZO", "(250 200 60)")
    z += t
    box("ILD%d" % i, 0, 0, z, MX, MY, 0.3, "BEOL_lowk", "(200 170 110)")
    z += 0.3

oEditor.FitAll()
AddInfoMessage = getattr(oDesktop, "AddMessage", None)
if AddInfoMessage:
    oDesktop.AddMessage(oProject.GetName(), oDesign.GetName(), 0,
                        "C2 macro unit cell built: 14 bodies, top of stack at z = %.2f um" % z)
