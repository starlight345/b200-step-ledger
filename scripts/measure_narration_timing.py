#!/usr/bin/env python3
"""Measure how long the Korean walkthrough narration actually takes to speak.

The scene table in VIDEO_REFRESH_PLAN.md holds planned lengths. This renders the
real narration with the same voice the build uses and reports measured seconds per
scene and per sentence, so screen clips and subtitle cues can be cut to the audio
instead of to an estimate.

    python3 scripts/measure_narration_timing.py            # rewrite the JSON in assets/
    python3 scripts/measure_narration_timing.py --check    # verify it is current, write nothing

Requires macOS `say` with the ko_KR voice and `afinfo`. Voice and rate default to
the values scripts/build_walkthrough_v2.cjs uses.
"""
import argparse, json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NARRATION = os.path.join(ROOT, 'assets', 'b200_walkthrough_narration_v2.ko.txt')
OUT = os.path.join(ROOT, 'assets', 'b200_walkthrough_narration_v2.timing.json')
SCENE_RE = re.compile(r'^\[(\d{2}) · ([^\]]+)\]\s*$', re.M)
DURATION_RE = re.compile(r'estimated duration: ([0-9.]+)')


def scenes(text):
    parts = SCENE_RE.split(text.strip())
    if len(parts) < 4:
        raise SystemExit('narration has no [NN · title] scene headers')
    return [{'scene': parts[i], 'title': parts[i + 1], 'body': parts[i + 2].strip()}
            for i in range(1, len(parts), 3)]


def sentences(body):
    out = []
    for para in (p.strip() for p in body.split('\n')):
        if not para:
            continue
        out.extend(s.strip() for s in re.split(r'(?<=[.!?])\s+', para) if s.strip())
    return out


def speak(text, voice, rate, workdir, stem):
    src = os.path.join(workdir, stem + '.txt')
    dst = os.path.join(workdir, stem + '.aiff')
    with open(src, 'w', encoding='utf-8') as fh:
        fh.write(text)
    subprocess.run(['say', '-v', voice, '-r', str(rate), '-f', src, '-o', dst], check=True)
    info = subprocess.run(['afinfo', dst], capture_output=True, text=True).stdout
    found = DURATION_RE.search(info)
    if not found:
        raise SystemExit(f'afinfo reported no duration for {stem}')
    return round(float(found.group(1)), 3)


def measure(voice, rate, gap):
    with open(NARRATION, encoding='utf-8') as fh:
        text = fh.read()
    report = []
    with tempfile.TemporaryDirectory() as workdir:
        for sc in scenes(text):
            rows = [{'i': i, 'sec': speak(s, voice, rate, workdir, f"{sc['scene']}-{i:02d}"),
                     'chars': len(s), 'text': s}
                    for i, s in enumerate(sentences(sc['body']), 1)]
            report.append({'scene': sc['scene'], 'title': sc['title'],
                           'sec': speak(sc['body'], voice, rate, workdir, sc['scene']),
                           'sentences': rows})
    spoken = sum(s['sec'] for s in report)
    return {'voice': voice, 'rate': rate, 'gap_seconds': gap,
            'spoken_seconds': round(spoken, 3),
            'total_seconds': round(spoken + gap * (len(report) - 1), 3),
            'scenes': report}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--voice', default=os.environ.get('WALKTHROUGH_VOICE', 'Yuna'))
    ap.add_argument('--rate', type=int, default=int(os.environ.get('WALKTHROUGH_RATE', '178')))
    ap.add_argument('--gap', type=float, default=0.35, help='silence the build inserts between scenes')
    ap.add_argument('--check', action='store_true', help='compare against the committed JSON instead of rewriting it')
    args = ap.parse_args()

    result = measure(args.voice, args.rate, args.gap)
    rendered = json.dumps(result, ensure_ascii=False, indent=1) + '\n'
    if args.check:
        current = open(OUT, encoding='utf-8').read() if os.path.exists(OUT) else ''
        if current != rendered:
            print('narration timing is stale — rerun without --check', file=sys.stderr)
            return 1
        print('narration timing is current')
        return 0
    with open(OUT, 'w', encoding='utf-8') as fh:
        fh.write(rendered)
    for sc in result['scenes']:
        print(f"{sc['scene']} {sc['title']}: {len(sc['sentences'])} sentences, {sc['sec']:.1f}s")
    print(f"total {result['total_seconds']:.1f}s including {args.gap}s scene gaps")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
