#!/usr/bin/env python3
"""N1 runner — the negative-control workloads (SmolLM2-1.7B) over the grid frozen in n1_predictions.
Same measurement as R2 (r2_run.py: ncu app-range counters, then timing); only the model id table is extended.
Usage (on the GPU host, venv active, HF_HOME set):  python n1_run.py n1_predictions_ampere.json n1_measured_ampere.jsonl
"""
import runpy, sys
import r1_run as R1

R1.HF_ID['SmolLM2-1.7B'] = 'HuggingFaceTB/SmolLM2-1.7B'
sys.argv = ['r2_run.py'] + sys.argv[1:]
runpy.run_module('r2_run', run_name='__main__')
