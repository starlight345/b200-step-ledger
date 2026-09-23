#!/usr/bin/env python3
from pathlib import Path
import json,csv,numpy as np
root=Path(__file__).resolve().parent
runs=json.loads((root/'inputs/baseline_b8_l2048_first32.json').read_text())
rows=[];pooled=[];pooled_skip=[]
for r in runs:
 g=np.diff(r['decode_completion_timestamps'])*1000
 pooled.extend(g);pooled_skip.extend(g[2:])
 rows.append(dict(source=r['source_file'],n=len(g),p50_ms=np.quantile(g,.5),p95_ms=np.quantile(g,.95),p99_linear_ms=np.quantile(g,.99),max_ms=max(g),skip_first2_p99_linear_ms=np.quantile(g[2:],.99)))
for label,g in [('pooled',np.array(pooled)),('pooled_skip_first2_each',np.array(pooled_skip))]:
 rows.append(dict(source=label,n=len(g),p50_ms=np.quantile(g,.5),p95_ms=np.quantile(g,.95),p99_linear_ms=np.quantile(g,.99),max_ms=max(g),skip_first2_p99_linear_ms=''))
with (root/'outputs/baseline_p99_sensitivity.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
print(json.dumps(rows,indent=2))
