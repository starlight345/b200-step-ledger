"""Korean narration for the walkthrough: TTS, concatenation and captions.

Everything here is macOS-native: /usr/bin/say writes the speech, the standard
library stitches the WAV files together, and afconvert makes the AAC track.
No ffmpeg is involved because this machine has no usable build of it.
"""

import os
import re
import subprocess
import wave

SAY = "/usr/bin/say"
AFCONVERT = "/usr/bin/afconvert"
SAMPLE_RATE = 22050
SCENE_HEADER = re.compile(r"^\[(\d{2}) · ([^\]]+)\]\s*$", re.MULTILINE)


def parse_scenes(path, expected=None):
    """Split the narration file into its numbered scenes."""
    source = open(path, encoding="utf-8").read().strip()
    parts = SCENE_HEADER.split(source)
    scenes = []
    for index in range(1, len(parts), 3):
        scenes.append({
            "number": parts[index],
            "title": parts[index + 1].strip(),
            "text": parts[index + 2].strip(),
        })
    if expected and len(scenes) != expected:
        raise SystemExit(
            f"{path}: expected {expected} scenes in [NN · title] form, found {len(scenes)}"
        )
    return scenes


def synthesize(scenes, work_dir, voice="Yuna", rate=178):
    """Speak each scene into its own WAV and record the measured duration."""
    os.makedirs(work_dir, exist_ok=True)
    for scene in scenes:
        text_path = os.path.join(work_dir, f"scene-{scene['number']}.txt")
        wav_path = os.path.join(work_dir, f"scene-{scene['number']}.wav")
        with open(text_path, "w", encoding="utf-8") as handle:
            handle.write(scene["text"])
        subprocess.run(
            [SAY, "-v", voice, "-r", str(rate), "-f", text_path,
             "-o", wav_path, "--data-format=LEI16@%d" % SAMPLE_RATE],
            check=True,
        )
        with wave.open(wav_path) as audio:
            scene["speech"] = audio.getnframes() / audio.getframerate()
        scene["audio"] = wav_path
    return scenes


def lay_out(scenes, lead_in=0.6, gap=0.9, tail=1.2):
    """Give every scene a start time, a duration and a slot for its actions.

    `gap` is the pause between scenes; the recorder holds the last screen of a
    scene during it, which is what makes the cuts readable.
    """
    cursor = lead_in
    for scene in scenes:
        scene["start"] = cursor
        scene["duration"] = scene["speech"] + gap
        cursor += scene["duration"]
    return cursor + tail - gap


def concat(scenes, out_wav, lead_in=0.6, total=None):
    """Join the scene WAVs with silence, matching the lay_out timeline."""
    with wave.open(scenes[0]["audio"]) as first:
        params = first.getparams()
    with wave.open(out_wav, "wb") as output:
        output.setparams(params)
        frame_size = params.sampwidth * params.nchannels
        silence = b"\x00" * frame_size

        def pad(seconds):
            output.writeframes(silence * max(0, int(round(seconds * params.framerate))))

        pad(lead_in)
        written = lead_in
        for scene in scenes:
            with wave.open(scene["audio"]) as audio:
                output.writeframes(audio.readframes(audio.getnframes()))
            written += scene["speech"]
            gap = scene["duration"] - scene["speech"]
            pad(gap)
            written += gap
        if total and total > written:
            pad(total - written)
    return out_wav


def to_aac(wav_path, m4a_path, bitrate=128000):
    """AAC in an MP4 container, so the final mux can be a passthrough export."""
    subprocess.run(
        [AFCONVERT, "-f", "m4af", "-d", "aac", "-b", str(bitrate),
         "-q", "127", "-s", "3", wav_path, m4a_path],
        check=True,
    )
    return m4a_path


def _timestamp(value):
    ms = max(0, int(round(value * 1000)))
    return "%02d:%02d:%02d.%03d" % (
        ms // 3600000, (ms % 3600000) // 60000, (ms % 60000) // 1000, ms % 1000
    )


def caption_chunks(text, limit=58):
    """Split a scene into caption-sized pieces on sentence boundaries."""
    sentences = re.findall(r"[^.!?\n]+[.!?]?", text.replace("\n", " "))
    chunks, current = [], ""
    for sentence in (item.strip() for item in sentences):
        if not sentence:
            continue
        if current and len(current) + len(sentence) + 1 > limit:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return chunks


def write_vtt(scenes, path):
    """Captions timed by character share of each scene's measured speech."""
    lines = ["WEBVTT", "", "NOTE 3D Ledger 설명 영상 v2 · 한국어 내레이션", ""]
    cue = 1
    for scene in scenes:
        chunks = caption_chunks(scene["text"])
        weight = sum(len(chunk) for chunk in chunks) or 1
        cursor = scene["start"]
        for chunk in chunks:
            end = cursor + scene["speech"] * len(chunk) / weight
            lines += [str(cue), f"{_timestamp(cursor)} --> {_timestamp(end)}", chunk, ""]
            cue += 1
            cursor = end
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return path
