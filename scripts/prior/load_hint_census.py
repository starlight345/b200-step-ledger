#!/usr/bin/env python3
"""Static census of L2 load hints in shipped GPU kernel libraries (SASS; CPU only, no GPU).

D3 showed three load classes behave differently under the persistence controls: normal loads, evict-first loads
(`ld.global.cs` -> SASS opcode modifier .EF) and loads carrying a kernel-built cache-policy descriptor (createpolicy
-> the desc[URx] operand holds a policy the kernel made with UMOV/ULOP3 instead of the driver's default, which is read
from the constant bank: (U)LDC(U).64 URx, c[0x0][0x358]). This asks how common the last two are in what an LLM
serving stack actually runs, per library and architecture:
  * per kernel (function): its global load variants (LDG / LD / LDGSTS / TMA UTMALDG / bulk UBLKCP, with modifiers) and
    whether any global memory instruction uses a descriptor register the kernel built itself rather than the driver's
    default read from constant bank 0 (slot per architecture: sm_80 0x118, sm_90 0x208, sm_100/sm_120 0x358),
    followed through UMOV/UMOV.64 copies;
  * modifiers other than .EF are reported as found (e.g. .EL, .LU, .NA), not assumed.
The descriptor rule is a heuristic; it is checked on our own D3 binary (l2policy_bench_hint: createpolicy kernels
must be flagged, the plain and `.cs` kernels must not).

Usage (on a host with cuobjdump and c++filt):
  python3 load_hint_census.py OUT.jsonl ARCH[,ARCH...] LIB.so [LIB.so ...]    e.g. sm_90,sm_100,sm_120
  -> one JSON line per (library, arch, kernel); a summary per (library, arch) on stdout
"""
import json, os, re, subprocess, sys
from collections import Counter, defaultdict

FUNC = re.compile(r'^\s*Function : (\S+)')
ARCH = re.compile(r'^\s*arch = (sm_\d+a?)')
INS = re.compile(r'/\*[0-9a-f]{4,}\*/\s+(?:@!?U?P\w+\s+)?([A-Z][A-Z0-9_.]*)\s*([^;]*);')
CB = re.compile(r'c\[0x0\]\[(0x[0-9a-f]+)\]')
# the driver's default memory descriptor (constant bank 0), read from the SASS of plain kernels of each architecture
SLOT = {'sm_80': '0x118', 'sm_86': '0x118', 'sm_89': '0x118', 'sm_90': '0x208', 'sm_100': '0x358', 'sm_120': '0x358'}
GMEM = ('LDG', 'STG', 'LD', 'ST', 'LDGSTS', 'ATOMG', 'ATOM', 'RED', 'REDG', 'UTMALDG', 'UTMASTG', 'UTMAPF', 'UTMAREDG',
        'UBLKCP', 'UBLKPF', 'UBLKRED')
LOADS = ('LDG', 'LD', 'LDGSTS', 'UTMALDG', 'UBLKCP')      # UTMALDG = TMA tensor load, UBLKCP = bulk copy

def census(lib, arch):
    """Yield one dict per kernel of LIB for ARCH (streamed; libcublasLt's SASS is several GB of text).
    Descriptor sources by a linear scan in address order: a uniform register written by (U)LDC(U) from constant bank
    c[0x0][X] is labelled cb:X, a UMOV copy takes its source's label, anything else (UMOV immediate, ULOP3, ...) is
    'built'. The driver's default descriptor sits at an architecture-specific slot (SLOT); cb labels at other slots
    are kernel parameters (reported, not counted as kernel-built)."""
    p = subprocess.Popen(['cuobjdump', '-sass', '-arch', arch, lib], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         text=True, errors='replace', bufsize=1 << 20)
    cur, slot = None, 'cb:' + SLOT.get(arch.rstrip('a'), '?')
    def done(k):
        k.pop('kind'); k['ef'] = any('.EF' in v for v in k['variants'])
        k['custom_desc'] = k['desc'].get('built', 0) > 0
        k['param_desc'] = any(l.startswith('cb:') and l != slot for l in k['desc'])
        k['desc'] = dict(k['desc'])
        return k
    for line in p.stdout:
        m = FUNC.match(line)
        if m:
            if cur: yield done(cur)
            cur = dict(lib=os.path.basename(lib), arch=arch, name=m.group(1), variants=Counter(), desc=Counter(), kind={})
            continue
        if cur is None: continue
        m = INS.search(line)
        if not m: continue
        op, args = m.group(1), m.group(2)
        base = op.split('.')[0]
        if base in GMEM:
            d = re.search(r'desc\[(UR\d+)\]', args)
            if d: cur['desc'][cur['kind'].get(d.group(1), 'undefined')] += 1
            if base in LOADS: cur['variants'][op] += 1
            continue
        first = args.split(',')[0].strip()
        if re.fullmatch(r'UR\d+', first):                      # a write to a uniform register
            rest = args[len(args.split(',')[0]):]
            src, cb = re.findall(r'UR\d+', rest), CB.search(rest)
            if base in ('LDC', 'ULDC', 'LDCU') and cb: k = 'cb:' + cb.group(1)
            elif base == 'UMOV' and src: k = cur['kind'].get(src[0], 'built')
            else: k = 'built'
            cur['kind'][first] = k
    if cur: yield done(cur)
    p.wait()

def demangle(names):
    out = subprocess.run(['c++filt', '-n'], input='\n'.join(names), capture_output=True, text=True).stdout.split('\n')
    return dict(zip(names, out))

def family(dn):
    """Short kernel family from a demangled name: the qualified function name, template arguments and parameter list
    removed at any nesting depth (a bracket-depth scan; 'operator<' does not occur in kernel names)."""
    out, depth = [], 0
    for ch in dn:
        if ch == '<': depth += 1
        elif ch == '>': depth = max(0, depth - 1)
        elif depth == 0: out.append(ch)
    s = ''.join(out)
    s = s.split('(')[0].strip()
    s = re.sub(r'^(void|auto)\s+', '', s)
    if s.split('::')[-1] in ('device_kernel', 'Kernel', 'Kernel2', 'kernel') and '<' in dn:
        # a generic launcher (cutlass::device_kernel<Op>, cutlass::Kernel<Op>): name the operator it launches
        arg, depth = [], 0
        for ch in dn[dn.index('<') + 1:]:
            if ch == '<': depth += 1
            elif ch == '>' and depth == 0: break
            elif ch == '>': depth -= 1
            elif ch == ',' and depth == 0: break
            elif depth == 0: arg.append(ch)
        a = ''.join(arg).strip()
        if re.fullmatch(r'[A-Za-z0-9_]+', a) and a.count('_') >= 3: a = '_'.join(a.split('_')[:3])
        if a and not a[0].isdigit() and a not in ('int', 'long', 'float', 'bool', 'true', 'false'): s = f'{s}<{a}>'
    if re.fullmatch(r'[A-Za-z0-9_]+', s) and s.count('_') >= 3:
        # C-style library kernel names carry tile shapes and dtypes (sm90_xmma_gemm_bf16bf16_..._tilesize128x128x64_...,
        # cutlass_80_wmma_tensorop_bf16_...): keep the first three tokens as the family
        s = '_'.join(s.split('_')[:3])
    return s[:140]

if __name__ == '__main__':
    outp, archs, libs = sys.argv[1], sys.argv[2].split(','), sys.argv[3:]
    rows = []
    with open(outp, 'w') as f:
        for lib in libs:
            for arch in archs:
                ks = list(census(lib, arch))
                if not ks: continue
                dm = demangle([k['name'] for k in ks])
                for k in ks:
                    k['family'] = family(dm.get(k['name'], k['name'])); k['variants'] = dict(k['variants'])
                    f.write(json.dumps(k) + '\n'); rows.append(k)
    S = defaultdict(lambda: dict(kernels=0, with_loads=0, ef=0, custom_desc=0, param_desc=0, fam_ef=Counter(),
                                 fam_cd=Counter(), mods=Counter(), labels=Counter()))
    for k in rows:
        s = S[(k['lib'], k['arch'])]; s['kernels'] += 1
        if k['variants']: s['with_loads'] += 1
        s['ef'] += k['ef']; s['custom_desc'] += k['custom_desc']; s['param_desc'] += k['param_desc']
        if k['ef']: s['fam_ef'][k['family']] += 1
        if k['custom_desc']: s['fam_cd'][k['family']] += 1
        for l in k['desc']: s['labels'][l] += 1
        mods = {t for v in k['variants'] for t in v.split('.')[1:] if t in ('EF', 'EL', 'LU', 'NA', 'EN', 'EU', 'NT')}
        for t in mods: s['mods'][t] += 1
    for (lib, arch), s in S.items():
        print(f"{lib} {arch}: {s['kernels']} kernels ({s['with_loads']} with global loads); evict-first (.EF) {s['ef']}; "
              f"kernel-built descriptor {s['custom_desc']}; parameter descriptor {s['param_desc']}; "
              f"kernels per load modifier {dict(s['mods'])}; kernels per descriptor source {s['labels'].most_common(4)}")
        print('   .EF families:', s['fam_ef'].most_common(8))
        print('   kernel-built-descriptor families:', s['fam_cd'].most_common(8))
