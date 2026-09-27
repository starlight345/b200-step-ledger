# -*- coding: utf-8 -*-
# AEDT IronPython -- print the first monitor samples of the active design (time in ms, tier and
# logic temperature) and where the NaNs begin, so they can be compared point by point with the
# exact cold-start solution (scripts/aedt_vcache_reference.py). Same as scripts/aedt/vcsamples.py.
oProject = oDesktop.GetActiveProject()
oDesign = oProject.GetActiveDesign()
oRep = oDesign.GetModule("ReportSetup")

def msg(text, level=0):
    oDesktop.AddMessage(oProject.GetName(), oDesign.GetName(), level, text)

setup = "%s : Solution" % oDesign.GetModule("AnalysisSetup").GetSetups()[0]
vals = {}
for q in ("monptier.Temperature", "monplogic.Temperature"):
    d = oRep.GetSolutionDataPerVariation("Monitor", setup, ["Domain:=", "Sweep"], ["Time:=", ["All"]], [q])[0]
    vals[q] = ([float(x)*1e3 for x in d.GetSweepValues("Time")], [float(x) for x in d.GetRealDataValues(q)])
t, tier = vals["monptier.Temperature"]
logic = vals["monplogic.Temperature"][1]
first_nan = next((i for i, v in enumerate(tier) if v != v), None)
msg("SAMPLES %d, first NaN at index %s (t = %s ms)" % (len(t), first_nan, t[first_nan] if first_nan is not None else "-"))
for i in range(min(len(t), 140)):
    if i < 16 or i % 10 == 0 or (first_nan is not None and abs(i - first_nan) < 3):
        msg("SAMPLE %3d t %.6f ms tier %.6f logic %.6f" % (i, t[i], tier[i], logic[i]))
