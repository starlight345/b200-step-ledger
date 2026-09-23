"""Find sentences that point at the screen and show what covers them.

A scene's cues and its script are one object. Changing the screen to satisfy a
declaration can invalidate a sentence, and changing a sentence can invalidate a
shot; that happened in both directions while this video was being made. Neither
side can be checked alone, so this lists every sentence whose wording depends on
what is in frame, next to the declarations that pin it down.

It does not decide anything. It makes an assumption that was in someone's head
into a line someone has to look at.
"""

import re
import sys

# Wording that only means something if the viewer can see the thing.
DEICTIC = [
    "화면", "여기", "이 색", "색 비율", "왼쪽", "오른쪽", "위쪽", "아래쪽",
    "표시된", "표시됩니다", "뜬", "뜹니다", "보이는", "보입니다",
    "막대", "배지", "딱지", "단추", "버튼", "사다리", "그림", "구슬",
    "초록", "파랑", "노랑", "회색", "빨강",
]


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.replace("\n", " ")) if s.strip()]


def lint(scenes):
    findings = []
    for scene in scenes:
        entry_expect = scene.get("expect", [])
        entry_forbid = scene.get("forbid", [])
        for sentence in sentences(scene["text"]):
            hits = [word for word in DEICTIC if word in sentence]
            if not hits:
                continue
            covered = [n for n in entry_expect if n in sentence]
            findings.append({
                "scene": scene["number"], "sentence": sentence,
                "deictic": hits, "covered": covered,
                "expect": entry_expect, "forbid": entry_forbid,
            })
    return findings


def main():
    sys.path.insert(0, __file__.rsplit("/", 1)[0])
    import narration
    from storyboard import STORYBOARD, resolve

    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path:
        raise SystemExit("usage: lint_script.py <narration.ko.txt>")
    scenes = resolve(narration.parse_scenes(path))
    for scene in scenes:
        entry = next((e for e in STORYBOARD if e["key"] == scene["storyboard"]), {})
        scene["expect"] = entry.get("expect", [])
        scene["forbid"] = entry.get("forbid", [])

    # Literal containment cannot tell whether a sentence is covered: a pointing
    # sentence rarely quotes the string it points at. So report what is here and
    # flag only the case that is unambiguously a gap — a scene that points at
    # the screen and declares nothing at all.
    by_scene = {}
    for item in lint(scenes):
        by_scene.setdefault(item["scene"], []).append(item)

    gaps = 0
    for scene in scenes:
        items = by_scene.get(scene["number"], [])
        if not items:
            continue
        declared = scene["expect"] + scene["forbid"]
        status = "DECLARES NOTHING" if not declared else f"{len(declared)} declaration(s)"
        flag = ""
        if not declared:
            gaps += 1
            flag = "   <-- points at the screen with nothing pinned down"
        print(f"\n{scene['number']} {scene['title']}  ·  {len(items)} pointing sentence(s)  ·  {status}{flag}")
        if declared:
            print(f"     expect {scene['expect']}")
            if scene["forbid"]:
                print(f"     forbid {scene['forbid']}")
        for item in items:
            print(f"     [{', '.join(item['deictic'])}] {item['sentence'][:96]}")
    print(f"\n{gaps} scene(s) point at the screen with no declaration at all")
    raise SystemExit(1 if gaps else 0)


if __name__ == "__main__":
    main()
