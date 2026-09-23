"""Scene-by-scene screen direction for the v2 walkthrough.

One entry per narration scene, in the same order as
assets/b200_walkthrough_narration_v2.ko.txt. Each scene's wall-clock length
comes from the measured narration, and its actions are spread evenly across it.

Actions:
    ("goto",   "page.html")          navigate and wait for load
    ("click",  "selector")           element.click()
    ("select", "selector", "value")  set a <select> and fire input+change
    ("scroll", "selector", offset)   smooth-scroll the element into view
    ("top",)                         smooth-scroll to the top of the page
    ("hold",)                        no-op, spends its slice of the scene

Keep this in step with the narration: scene 05 is the cache journey, so if the
journey UI grows a step the narration does not mention, the recording will show
something the voice never explains.
"""

LAB = "scenario-lab.html"
MEMORY = "memory.html"
REPLAY = "replay.html"

STORYBOARD = [
    {
        "scene": "01",
        "key": "lab-open",
        "expect": ["Scenario Lab"],
        "match": ['Scenario Lab'],
        "note": "Scenario Lab 첫 화면",
        "actions": [
            ("goto", LAB),
            ("top",),
            ("scroll", ".presets", -120),
            ("scroll", "#stage", -24),
        ],
    },
    {
        "scene": "02",
        "key": "whole-system",
        "expect": ["HBM · 지속 데이터", "가상 3D SRAM", "일반 L2", "구조·가정값", "사전 배치 가정", "균등 혼합 가정"],
        "match": ['전체 시스템'],
        "note": "전체 시스템 · 짧은 문맥에서 긴 문맥으로",
        # The storage bars this scene narrates live in the system map. The
        # #hbm-storage / #near-storage ids belong to the journey panel and are
        # display:none here, which is why they must not be cued from this view.
        "actions": [
            ("click", "#view-system"),
            ("click", '[data-s="short"]'),
            ("scroll", "#system-content", -90),
            ("scroll", "#system-map", -60),
            ("scroll", "#l2-view", -120),
            ("click", '[data-s="long"]'),
            ("scroll", "#system-map", -60),
            ("scroll", "#decision", -80),
        ],
    },
    {
        "scene": "03",
        "key": "model-shapes",
        "expect": ["하이브리드", "슬라이딩 창", "MoE", "MLA"],
        "match": ['MoE', '슬라이딩'],
        "note": "하이브리드 · 슬라이딩 · MoE · MLA",
        "actions": [
            ("scroll", ".presets", -110),
            ("click", '[data-s="state"]'),
            ("scroll", "#system-map", -60),
            ("scroll", ".presets", -110),
            ("click", '[data-s="sliding"]'),
            ("click", '[data-s="moe"]'),
            ("click", '[data-s="mla"]'),
            ("scroll", "#decision", -80),
        ],
    },
    {
        "scene": "04",
        "key": "sram-vs-l2",
        # The .evidence block near the page bottom is static and reads
        # "1.1099×", which is scene 06's two-device matched-object result. This
        # scene speaks 1.108× for the 64 MiB sweep cell. SCENARIO_MODEL.md:39
        # says those two must not be conflated, so keeping both in one frame
        # would ship the conflation in picture even with a clean script.
        "expect": ["추가 3D SRAM", "기존 L2 분할", "캐시 분할", "persisting 예약 영역", "1.000"],
        "forbid": ["1.1099", "1.0554", "1.0562"],
        "match": ['L2 분할', '3D SRAM'],
        "note": "추가 3D SRAM과 기존 L2 분할 · capacity cliff",
        "actions": [
            ("click", "#view-system"),
            ("scroll", ".presets", -110),
            ("select", "#mode", "added"),
            ("scroll", "#system-map", -60),
            ("select", "#mode", "partition"),
            ("scroll", "#system-map", -60),
            ("scroll", ".presets", -110),
            ("click", '[data-s="cliff"]'),
            ("scroll", "#system-map", -60),
            ("text", "근접 용량 요청", -60),
            ("scroll", "#decision", -80),
            ("scroll", "#system-map", -60),
        ],
    },
    {
        "scene": "05",
        "key": "journey",
        # The voice lists the near-tier assumptions. They only render when the
        # near tier actually has capacity: in 기존 L2 분할 the row becomes the
        # persisting reservation at 30 TB/s / 100 ns, or drops out entirely as
        # 용량 부족 · 경로 제외. Scene 04 ends on the cliff preset, which is
        # partition mode, so this scene has to put the page back first.
        "expect": ["20.0 TB/s", "50 ns", "889", "3.16", "659", "16 MiB", "최초 적재", "단계 0"],
        "match": ['한 요청'],
        "note": "한 요청 따라가기 · cold → reuse → eviction → dirty",
        "actions": [
            ("goto", LAB),
            ("select", "#mode", "added"),
            ("click", '[data-s="short"]'),
            ("click", "#view-journey"),
            ("scroll", "#near-storage", -140),
            ("scroll", "#flow", -60),
            ("select", "#journey-pattern", "cold"),
            ("click", "#reset-journey"),
            ("click", "#play"),
            ("hold",),
            ("select", "#journey-pattern", "reuse"),
            ("click", "#play"),
            ("hold",),
            ("select", "#journey-pattern", "eviction"),
            ("click", "#play"),
            ("hold",),
            ("select", "#journey-pattern", "dirty"),
            ("click", "#play"),
            ("hold",),
            ("scroll", "#flow", -60),
        ],
    },
    {
        "scene": "06",
        "key": "b200-proof",
        "expect": ["1.1099", "1.0554", "1.0562", "64 MiB", "36개"],
        "forbid": ["0.938", "1.1083", "1.163", "0.9524"],
        "match": ['배치 검증'],
        "note": "B200 배치 검증",
        "actions": [
            ("goto", MEMORY),
            ("scroll", "#placement-proof", -20),
            ("hold",),
            ("scroll", "#policy", -20),
            ("hold",),
            ("scroll", "#sources", -20),
        ],
    },
    {
        "scene": "07",
        "key": "replay",
        # The scene's claim is about what the moving beads mean, which is not a
        # string test. This is the nearest honest guard: the caption that says
        # the bead paths are computed per-object access, not a filmed trace.
        "expect": ["논리 접근"],
        "match": ['기록 재생'],
        "note": "B200 기록 재생",
        "actions": [
            ("goto", REPLAY),
            ("scroll", ".replaybar", -10),
            ("click", "#replay-toggle"),
            ("scroll", "#scene-wrap", -40),
            ("hold",),
            ("scroll", "#request-life", -40),
            ("scroll", "#chart", -40),
            ("scroll", "#pipeline-explainer", -40),
        ],
    },
    {
        "scene": "08",
        "key": "limits",
        "expect": ["측정", "유도", "제조사", "가정"],
        "match": ['근거'],
        "note": "근거와 한계",
        "actions": [
            # The voice opens by naming four evidence badges and their colours.
            # That legend is only on replay.html, so the scene has to show it
            # rather than talk over a page that does not carry it.
            ("goto", REPLAY),
            ("top",),
            ("hold",),
            ("goto", LAB),
            ("scroll", ".evidence", -40),
            ("goto", MEMORY),
            ("scroll", "#return", -20),
            ("scroll", "#sources", -20),
        ],
    },
]

# The frame the page is linked with. Taken once scene 01 has settled.
POSTER = {"page": LAB, "settle": 2.5, "scroll": ("#stage", -24)}


def resolve(scenes):
    """Attach a storyboard entry to every narration scene, by title not number.

    The narration numbers its scenes, but those numbers move: splitting one
    scene renumbers every scene after it. Matching on distinctive title words
    instead means a renumber costs nothing, and when a scene is split in two
    both halves match the same entry and share its choreography in order.
    """
    matched = []
    for scene in scenes:
        hits = [entry for entry in STORYBOARD
                if any(word in scene["title"] for word in entry["match"])]
        if not hits:
            raise SystemExit(
                f"scene {scene['number']} \"{scene['title']}\" matches no storyboard entry.\n"
                f"Add one to STORYBOARD with a 'match' keyword from that title."
            )
        if len(hits) > 1:
            raise SystemExit(
                f"scene {scene['number']} \"{scene['title']}\" matches "
                f"{[h['key'] for h in hits]}; make the 'match' keywords distinctive."
            )
        matched.append((scene, hits[0]))

    shared = {}
    for scene, entry in matched:
        shared.setdefault(entry["key"], []).append(scene)
    for scene, entry in matched:
        siblings = shared[entry["key"]]
        actions = entry["actions"]
        if len(siblings) == 1:
            scene["actions"] = actions
        else:
            # A split scene: hand each half a contiguous slice of the same
            # choreography so the screen still follows the voice in order.
            index = siblings.index(scene)
            size = len(actions) / len(siblings)
            start, end = round(index * size), round((index + 1) * size)
            scene["actions"] = actions[start:end] or [actions[min(start, len(actions) - 1)]]
        scene["storyboard"] = entry["key"]
    return scenes


def pages_used():
    pages, current = {}, None
    for scene in STORYBOARD:
        for action in scene["actions"]:
            if action[0] == "goto":
                current = action[1]
            elif action[0] in ("click", "select", "scroll") and current:
                pages.setdefault(current, set()).add(action[1])
    return pages
