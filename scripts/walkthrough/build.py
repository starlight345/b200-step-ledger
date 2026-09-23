#!/usr/bin/env python3
"""Build the v2 Korean walkthrough: narration, screen recording, MP4, captions.

Replaces scripts/build_walkthrough_v2.cjs, which cannot run on this machine:
it needs the playwright npm package and an ffmpeg with libx264/AAC, and the
only ffmpeg here is playwright's bundled build (PNG and VP8 only). Playwright's
recorder is hard-wired to VP8/WebM, which nothing on this Mac can decode, so
the recording is taken straight from CDP and muxed with AVFoundation.

    ./build.py                      full render into assets/
    ./build.py --scenes 01,07       re-record two chapters only
    ./build.py --check              validate selectors, record nothing
    ./build.py --out-dir /tmp/x     render somewhere else first

Everything it needs is already on the box: Chrome, /usr/bin/say (Yuna),
/usr/bin/afconvert and the AVFoundation encoder in this directory.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import narration  # noqa: E402
from record import Recorder  # noqa: E402
from storyboard import resolve  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
ASSETS = os.path.join(ROOT, "assets")
DEFAULT_NARRATION = os.path.join(ASSETS, "b200_walkthrough_narration_v2.ko.txt")
ENCODER = os.path.join(HERE, "encode")
ENCODER_SOURCE = os.path.join(HERE, "Encode.m")


def tree_state():
    """Identify the exact checkout being recorded.

    Three sessions share this working tree, so it can move under a six-minute
    recording. The report keeps the commit and a digest of uncommitted changes,
    and the build warns if either moves mid-render.
    """
    def git(*args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                              text=True).stdout.strip()

    dirty = git("status", "--porcelain")
    return {
        "commit": git("rev-parse", "HEAD"),
        "dirtyFiles": len([line for line in dirty.splitlines() if line]),
        "dirtyDigest": hashlib.sha256(dirty.encode()).hexdigest()[:12],
    }


def ensure_encoder():
    """Compile the AVFoundation muxer if it is missing or out of date."""
    if os.path.exists(ENCODER) and os.path.getmtime(ENCODER) > os.path.getmtime(ENCODER_SOURCE):
        return ENCODER
    subprocess.run(
        ["clang", "-fobjc-arc", "-O2", "-o", ENCODER, ENCODER_SOURCE,
         "-framework", "Foundation", "-framework", "AVFoundation",
         "-framework", "CoreMedia", "-framework", "CoreVideo",
         "-framework", "CoreGraphics", "-framework", "ImageIO"],
        check=True, cwd=HERE,
    )
    return ENCODER


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--narration", default=DEFAULT_NARRATION)
    parser.add_argument("--out-dir", default=ASSETS)
    parser.add_argument("--prefix", default="b200_walkthrough_v2")
    parser.add_argument("--scenes", default="", help="comma-separated scene numbers, e.g. 01,07")
    parser.add_argument("--voice", default=os.environ.get("WALKTHROUGH_VOICE", "Yuna"))
    parser.add_argument("--rate", type=int, default=int(os.environ.get("WALKTHROUGH_RATE", 178)))
    parser.add_argument("--quality", type=int, default=88, help="screencast JPEG quality")
    # 700 kbps keeps 720p screen text crisp (checked at 500 kbps over the
    # animated replay scene) and lands a six-minute render near 33 MB. The v1
    # video was 13 MB, so raise this only if a reviewer asks for it.
    parser.add_argument("--bitrate", type=int, default=700_000)
    parser.add_argument("--keep-frames", action="store_true")
    parser.add_argument("--check", action="store_true", help="validate selectors and exit")
    parser.add_argument("--rehearse", action="store_true",
                        help="perform every cue without recording and report where it lands")
    parser.add_argument("--require-commit", default=None,
                        help="refuse to record unless HEAD is this commit "
                             "(the plan's 녹화 기준 커밋)")
    args = parser.parse_args()

    if args.check:
        with Recorder() as recorder:
            report = recorder.check()
        missing = [f"{page} {sel}" for page in report for sel, ok in report[page].items() if not ok]
        for line in missing:
            print(f"MISSING {line}")
        print(f"{len(missing)} missing selector(s)")
        raise SystemExit(1 if missing else 0)

    if args.require_commit:
        head = tree_state()["commit"]
        if not head.startswith(args.require_commit):
            raise SystemExit(
                f"working tree is at {head[:9]}, not {args.require_commit}; "
                "pin the recording commit before rendering"
            )

    if args.rehearse:
        everything = resolve(narration.parse_scenes(args.narration))
        scenes = everything
        if args.scenes:
            wanted = {i.strip() for i in args.scenes.split(",")}
            scenes = [s for s in everything if s["number"] in wanted]
        with Recorder() as recorder:
            report = recorder.rehearse(scenes, context=everything)
        bad = 0
        for row in report:
            kind = row["action"][0]
            target = str(row["action"][1]) if len(row["action"]) > 1 else ""
            state = row["state"]
            box = row["box"]
            flag = ""
            if row["error"]:
                flag = f"  FAILED {row['error']}"
            elif box is None and kind in ("click", "select", "scroll"):
                flag = "  <-- target did not resolve"
            elif box and (box["h"] == 0 or box["w"] == 0):
                flag = (f"  <-- NO BOX at cue time"
                        + (f", hidden by {box['hiddenBy']}" if box.get("hiddenBy") else ""))
            elif row.get("missing"):
                flag = f"  <-- never on screen: {', '.join(row['missing'])}"
            elif row.get("forbidden"):
                flag = f"  <-- MUST NOT be in frame: {', '.join(row['forbidden'])}"
            elif kind == "scroll" and state.get("y") == 0:
                flag = "  <-- landed at the top of the page"
            if flag:
                bad += 1
            print(f"  {row['scene']} {kind:<7}{target:<26} "
                  f"{state.get('page','?'):<20} y={state.get('y','?'):<6}{flag}")
        print(f"\n{bad} cue(s) need attention")
        raise SystemExit(1 if bad else 0)

    encoder = ensure_encoder()
    os.makedirs(args.out_dir, exist_ok=True)
    scenes = resolve(narration.parse_scenes(args.narration))
    if args.scenes:
        wanted = {item.strip() for item in args.scenes.split(",")}
        scenes = [scene for scene in scenes if scene["number"] in wanted]
        if not scenes:
            raise SystemExit(f"no scenes matched {args.scenes}")

    work = tempfile.mkdtemp(prefix="ledger3d-walkthrough-")
    print(f"work dir: {work}")

    print(f"narrating {len(scenes)} scene(s) with {args.voice} at {args.rate} wpm")
    narration.synthesize(scenes, os.path.join(work, "audio"), voice=args.voice, rate=args.rate)
    total = narration.lay_out(scenes)
    for scene in scenes:
        print(f"  {scene['number']}  {scene['speech']:6.2f}s  starts {scene['start']:7.2f}s  {scene['title']}")
    print(f"  timeline {total:.2f}s = {int(total // 60)}:{int(total % 60):02d}")

    video_path = os.path.join(args.out_dir, f"{args.prefix}.mp4")
    vtt_path = os.path.join(args.out_dir, f"{args.prefix}.ko.vtt")
    poster_path = os.path.join(args.out_dir, f"{args.prefix}_poster.png")
    report_path = os.path.join(args.out_dir, f"{args.prefix}.build.json")

    print("recording screens")
    before = tree_state()
    print(f"  tree {before['commit'][:9]} (+{before['dirtyFiles']} uncommitted)")
    started = time.time()
    with Recorder(log_dir=work) as recorder:
        frames = recorder.record(
            scenes,
            frame_dir=os.path.join(work, "frames"),
            poster_path=poster_path,
            quality=args.quality,
        )
        page_errors = list(recorder.page_errors)
    elapsed = time.time() - started
    after = tree_state()
    print(f"  {len(frames)} frames over {elapsed:.1f}s "
          f"({len(frames) / max(elapsed, 1):.1f} fps average)")

    if after != before:
        print(f"\nWARNING: the working tree changed while recording "
              f"({before['commit'][:9]}+{before['dirtyDigest']} -> "
              f"{after['commit'][:9]}+{after['dirtyDigest']}). "
              "Scenes recorded before and after the change show different builds; "
              "re-record against a pinned commit before publishing.")

    real_errors = [error for error in page_errors if "favicon.ico" not in error]
    if real_errors:
        raise SystemExit("page errors during recording:\n  " + "\n  ".join(real_errors))

    print("muxing narration")
    wav_path = narration.concat(scenes, os.path.join(work, "narration.wav"), total=total)
    aac_path = narration.to_aac(wav_path, os.path.join(work, "narration.m4a"))
    narration.write_vtt(scenes, vtt_path)

    manifest_path = os.path.join(work, "manifest.json")
    with open(manifest_path, "w") as handle:
        json.dump({
            "width": recorder.viewport[0], "height": recorder.viewport[1],
            "frames": frames, "audio": aac_path, "output": video_path,
            "endTime": total, "bitrate": args.bitrate,
        }, handle)
    result = json.loads(subprocess.run([encoder, manifest_path], check=True,
                                       capture_output=True, text=True).stdout)

    drift = result["durationSeconds"] - total
    report = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "pipeline": "cdp-screencast + avfoundation (no ffmpeg, no playwright)",
        "narration": os.path.relpath(args.narration, ROOT),
        "treeBefore": before,
        "treeAfter": after,
        "treeStable": before == after,
        "voice": args.voice,
        "voiceRate": args.rate,
        "viewport": list(recorder.viewport),
        "frames": len(frames),
        "durationSeconds": round(result["durationSeconds"], 3),
        "narrationTimelineSeconds": round(total, 3),
        "audioVideoDriftSeconds": round(drift, 3),
        "hasAudio": result["hasAudio"],
        "bytes": result["bytes"],
        "scenes": [{
            "number": scene["number"], "title": scene["title"],
            "startSeconds": round(scene["start"], 2),
            "speechSeconds": round(scene["speech"], 2),
            "durationSeconds": round(scene["duration"], 2),
        } for scene in scenes],
    }
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    if not args.keep_frames:
        shutil.rmtree(work, ignore_errors=True)
    else:
        print(f"frames kept in {work}")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if abs(drift) > 1.0:
        print(f"\nWARNING: video runs {drift:+.2f}s against the narration timeline")


if __name__ == "__main__":
    main()
