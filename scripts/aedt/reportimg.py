# -*- coding: utf-8 -*-
# AEDT IronPython -- after report.py. The report windows are drawn (the status bar tracks the
# cursor in data coordinates) but Chrome Remote Desktop does not capture AEDT's graphics
# area, 2D reports included. Render each report to a file, and keep its data as CSV.

oProject = oDesktop.GetActiveProject()
oDesign = oProject.GetActiveDesign()
oRep = oDesign.GetModule("ReportSetup")
OUT = "C:/Users/user/Desktop/"

def msg(text, level=0):
    oDesktop.AddMessage(oProject.GetName(), oDesign.GetName(), level, text)

for title, stem in [("Tier 2 temperature across the 20 um periphery band (y = 200 um)", "aedtxcut"),
                    ("Tier 2 temperature across the 92 um periphery band (x = 60 um)", "aedtycut"),
                    ("Temperature through the stack at (143, 472) um", "aedtzcut")]:
    for what, fn in [("image", lambda t=title, s=stem: oRep.ExportImageToFile(t, OUT + s + ".png", 1600, 1000)),
                     ("csv", lambda t=title, s=stem: oRep.ExportToFile(t, OUT + s + ".csv"))]:
        try:
            fn()
            msg("OK   %s %s" % (stem, what))
        except Exception as e:
            msg("FAIL %s %s :: %s" % (stem, what, e), 2)
