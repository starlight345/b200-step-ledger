# -*- coding: utf-8 -*-
# AEDT IronPython -- run inside Ansys Electronics Desktop via Tools > Run Script, in an
# IcepakFEA design whose Solution Type is Transient Thermal.
#
# Builds the shipping V-Cache stack (hb_stack_check.vcache_stack('F2B')) as a 10 x 10 um
# column. The four side faces stay at the default (adiabatic), so the column IS the 1D
# problem that thermal_stack_solver / sota_comparators / HotSpot solve -- the point is an
# independent transient FEA of the same burst train, not a new geometry.
#
# Stack, z = 0 at the heat-sink side, um:
#   TIM 50 | dummy Si 750 | bond 0.425 | logic-die Si 7.2 | logic 1 | BEOL 8 | bond 0.425 |
#   SRAM Si 6 | SRAM device ('tier', heat source) 1 | SRAM BEOL 8        (face-to-back)
#
# Loads, per this 1e-10 m2 column: the tier gets P_COL during each burst, zero otherwise;
# P_COL is chosen so the burst-power steady rise is 100 K (R = 0.0259487 K/W per 800 mm2
# die -> 2.07590e5 K/W per column). Sink face held at 20 C.
#
# File name has no capitals or underscores: the remote session drops Shift.

oProject = oDesktop.GetActiveProject()
oDesign = oProject.GetActiveDesign()
oEditor = oDesign.SetActiveEditor("3D Modeler")
oEditor.SetModelUnits(["NAME:Units Parameter", "Units:=", "um", "Rescale:=", False])
oDef = oProject.GetDefinitionManager()
oBnd = oDesign.GetModule("BoundarySetup")

def msg(text, level=0):
    oDesktop.AddMessage(oProject.GetName(), oDesign.GetName(), level, text)

def attempt(label, fn):
    try:
        fn()
        msg("OK   " + label)
        return True
    except Exception as e:
        msg("FAIL " + label + " :: " + str(e), 2)
        return False

# name, k [W/m/K], rho [kg/m3], cp [J/kg/K] -- thermal_stack_solver.MAT + hb_stack_check 'bond'
MATS = [
    ("TIM_polymer", "5.0",  "2500", "800"),
    ("Si_90C",      "110",  "2330", "700"),
    ("BEOL_lowk",   "2.5",  "2300", "900"),
    ("bond_oxide",  "1.4",  "2200", "730"),
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

W = 10.0     # column side, um

def box(name, z, dz, mat, color):
    oEditor.CreateBox(
        ["NAME:BoxParameters",
         "XPosition:=", "0um", "YPosition:=", "0um", "ZPosition:=", "%.6gum" % z,
         "XSize:=", "%gum" % W, "YSize:=", "%gum" % W, "ZSize:=", "%.6gum" % dz],
        ["NAME:Attributes",
         "Name:=", name, "Flags:=", "", "Color:=", color, "Transparency:=", 0,
         "PartCoordinateSystem:=", "Global", "UDMId:=", "",
         "MaterialValue:=", "\"%s\"" % mat, "SurfaceMaterialValue:=", "\"\"",
         "SolveInside:=", True, "ShellElement:=", False, "ShellElementThickness:=", "0mm",
         "IsMaterialEditable:=", True, "UseMaterialAppearance:=", False,
         "IsLightweight:=", False])

LAYERS = [("TIM", 50.0, "TIM_polymer", "(190 190 190)"),
          ("dummySi", 750.0, "Si_90C", "(128 128 160)"),
          ("bondtop", 0.425, "bond_oxide", "(120 200 120)"),
          ("logicSi", 7.2, "Si_90C", "(128 128 160)"),
          ("logic", 1.0, "Si_90C", "(90 90 200)"),
          ("logicBEOL", 8.0, "BEOL_lowk", "(200 170 110)"),
          ("bondsram", 0.425, "bond_oxide", "(120 200 120)"),
          ("sramSi", 6.0, "Si_90C", "(128 128 160)"),
          ("tier", 1.0, "Si_90C", "(230 90 90)"),
          ("sramBEOL", 8.0, "BEOL_lowk", "(200 170 110)")]
z = 0.0
for name, t, mat, color in LAYERS:
    attempt("box %s %.3g um at z = %.4g um" % (name, t, z), lambda n=name, zz=z, tt=t, m=mat, c=color: box(n, zz, tt, m, c))
    z += t
oEditor.FitAll()
msg("V-Cache F2B column built: %d bodies, top at z = %.3f um" % (len(LAYERS), z))

# sink: the TIM's outer face (z = 0) at a fixed 20 C
def sink():
    fid = oEditor.GetFaceByPosition(["NAME:FaceParameters", "BodyName:=", "TIM",
                                     "XPosition:=", "5um", "YPosition:=", "5um", "ZPosition:=", "0um"])
    msg("sink face id = %s" % fid)
    oBnd.AssignTemperature(["NAME:Tsink", "Faces:=", [fid], "Temperature:=", "20cel"])
attempt("fixed temperature 20 C on the TIM outer face", sink)
