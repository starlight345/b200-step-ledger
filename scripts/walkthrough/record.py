"""Drive the static pages in headless Chrome and capture the walkthrough.

Frames come from CDP's screencast, which only fires on repaint, so a still
screen costs nothing and a scroll arrives at ~30 fps. Each frame keeps the
timestamp Chrome reports, and the encoder lays them on that same timeline, so
the picture stays locked to the narration even if a page stalls.
"""

import base64
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cdp import Chrome, ProtocolError  # noqa: E402
from storyboard import POSTER, STORYBOARD, pages_used  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VIEWPORT = (1280, 720)


class Recorder:
    def __init__(self, port=None, debug_port=None, viewport=VIEWPORT, log_dir="/tmp"):
        # Several sessions share this machine and one of them already holds
        # 4174, the port the old builder hard-coded. Serving from a port
        # somebody else owns silently records a different checkout, so take a
        # free port and prove the server is this working tree before recording.
        self.port = port or free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.viewport = viewport
        self.server = None
        self.chrome = None
        self.debug_port = debug_port or free_port()
        self.log_dir = log_dir
        self.page_errors = []

    def __enter__(self):
        self.server = subprocess.Popen(
            ["/usr/bin/python3", "-m", "http.server", str(self.port), "--bind", "127.0.0.1"],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(1.0)
        self._verify_server()
        self.chrome = Chrome(
            port=self.debug_port,
            window=self.viewport,
            profile_dir=os.path.join(self.log_dir, "chrome-profile"),
            log_path=os.path.join(self.log_dir, "chrome.log"),
        ).start()
        self.chrome.call("Page.enable")
        self.chrome.call("Runtime.enable")
        self.chrome.call("Log.enable")
        self.chrome.handlers["Runtime.exceptionThrown"] = self._on_exception
        self.chrome.handlers["Log.entryAdded"] = self._on_log
        self.chrome.call("Emulation.setDeviceMetricsOverride", {
            "width": self.viewport[0], "height": self.viewport[1],
            "deviceScaleFactor": 1, "mobile": False,
        })
        return self

    def _verify_server(self):
        """Confirm the port is serving THIS tree, not another session's copy."""
        if self.server.poll() is not None:
            raise ProtocolError(
                f"static server exited immediately on port {self.port}; "
                "the port is probably already in use"
            )
        local = open(os.path.join(ROOT, "index.html"), "rb").read()
        try:
            with urllib.request.urlopen(f"{self.base}/index.html", timeout=5) as response:
                served = response.read()
        except Exception as error:
            raise ProtocolError(f"static server not answering on {self.base}: {error}")
        if served != local:
            raise ProtocolError(
                f"{self.base} is serving a different copy of the repo than {ROOT}; "
                "another process owns that port"
            )

    def __exit__(self, *_):
        if self.chrome:
            self.chrome.stop()
        if self.server:
            self.server.terminate()

    def _on_exception(self, params):
        details = params.get("exceptionDetails", {})
        text = details.get("exception", {}).get("description") or details.get("text")
        self.page_errors.append(f"{details.get('url', '?')}: {text}")

    def _on_log(self, params):
        entry = params.get("entry", {})
        if entry.get("level") == "error":
            self.page_errors.append(f"{entry.get('url', '?')}: {entry.get('text')}")

    # ------------------------------------------------------------- browsing

    def evaluate(self, expression, quiet=False):
        result = self.chrome.call("Runtime.evaluate", {
            "expression": expression, "returnByValue": True, "awaitPromise": False,
        })
        if "exceptionDetails" in result and not quiet:
            raise ProtocolError(f"page threw on {expression[:70]}: "
                                f"{json.dumps(result['exceptionDetails'])[:200]}")
        return result.get("result", {}).get("value")

    def wait_for(self, selector, timeout=8.0):
        """Poll for a selector. The panels mount after their JSON loads, so a
        bare readyState check is not enough to know the screen is ready."""
        deadline = time.time() + timeout
        expression = ("!!document.querySelector(%s)" % json.dumps(selector))
        while True:
            if self.evaluate(expression, quiet=True):
                return True
            if time.time() >= deadline:
                return False
            self.chrome.pump(0.2)

    def goto(self, page, settle=2.2):
        self.chrome.call("Page.navigate", {"url": f"{self.base}/{page}"})
        deadline = time.time() + 12
        while time.time() < deadline:
            self.chrome.pump(0.3)
            if self.evaluate("document.readyState", quiet=True) == "complete":
                break
        self.chrome.pump(settle)

    def act(self, action):
        kind = action[0]
        if kind == "goto":
            self.goto(action[1], settle=1.4)
        elif kind == "top":
            self.evaluate("window.scrollTo({top:0,behavior:'smooth'})")
        elif kind == "click":
            self._require(action[1])
            self.evaluate(
                f"(()=>{{const el=document.querySelector({json.dumps(action[1])});"
                "if(!el)throw new Error('missing '+" + json.dumps(action[1]) + ");"
                "el.scrollIntoView({block:'center',behavior:'smooth'});el.click();})()"
            )
        elif kind == "select":
            selector, value = action[1], action[2]
            self._require(selector)
            self.evaluate(
                f"(()=>{{const el=document.querySelector({json.dumps(selector)});"
                "if(!el)throw new Error('missing '+" + json.dumps(selector) + ");"
                f"el.value={json.dumps(value)};"
                "el.dispatchEvent(new Event('input',{bubbles:true}));"
                "el.dispatchEvent(new Event('change',{bubbles:true}));})()"
            )
        elif kind == "scroll":
            selector, offset = action[1], action[2]
            self._require(selector)
            # Some targets carry no layout box in the current view (a panel that
            # is switched off, a bar whose contents were just re-rendered). Their
            # rect reads as 0, which used to scroll the page to the very top and
            # quietly film the wrong screen, so climb to the nearest ancestor
            # that actually occupies space and refuse if there is none.
            self.evaluate(
                f"(()=>{{const sel={json.dumps(selector)};"
                "let el=document.querySelector(sel);"
                "if(!el)throw new Error('missing '+sel);"
                "let node=el;"
                "while(node&&node!==document.body){const b=node.getBoundingClientRect();"
                "if(b.height>0&&b.width>0)break;node=node.parentElement;}"
                "if(!node||node===document.body)"
                "throw new Error('no laid-out box for '+sel+' in the current view');"
                "const b=node.getBoundingClientRect();"
                f"window.scrollTo({{top:Math.max(0,b.top+window.scrollY+({offset})),"
                "behavior:'smooth'});})()"
            )
        elif kind == "text":
            # Some figures the voice names sit in blocks with no id of their
            # own. Cueing them by the text itself says what the shot is for and
            # survives markup changes that a positional selector would not.
            needle, offset = action[1], action[2]
            self.evaluate(
                f"(()=>{{const needle={json.dumps(needle)};"
                "let hit=null;"
                "for(const e of document.querySelectorAll('body *')){"
                "if(e.children.length)continue;"
                "if(!(e.textContent||'').includes(needle))continue;"
                "const b=e.getBoundingClientRect();"
                "if(b.height>0&&b.width>0){hit=e;break}}"
                "if(!hit)throw new Error('no visible element contains '+needle);"
                "const b=hit.getBoundingClientRect();"
                f"window.scrollTo({{top:Math.max(0,b.top+window.scrollY+({offset})),"
                "behavior:'smooth'});})()"
            )
        elif kind == "hold":
            pass
        else:
            raise ValueError(f"unknown action {kind}")

    # -------------------------------------------------------------- checking

    def _require(self, selector):
        if not self.wait_for(selector):
            raise ProtocolError(f"selector never appeared: {selector}")

    def check(self):
        """Verify every storyboard selector resolves on its page."""
        report = {}
        for page, selectors in pages_used().items():
            self.goto(page, settle=2.5)
            report[page] = {
                selector: self.wait_for(selector, timeout=6.0)
                for selector in sorted(selectors)
            }
        return report

    VISIBLE_TEXT = """(()=>{const needles=%s,out={};
        // Case-insensitive: the page headers this video points at are set in
        // capitals, and CSS text-transform can differ from the DOM either way,
        // so a viewer matching "SCENARIO LAB" to the spoken "Scenario Lab" is
        // right and a literal comparison is not.
        const low=needles.map(n=>n.toLowerCase());
        for(const n of needles) out[n]=false;
        for(const s of document.querySelectorAll('select')){
          const b=s.getBoundingClientRect();
          if(!(b.height>0&&b.bottom>0&&b.top<innerHeight)) continue;
          const t=((s.options[s.selectedIndex]||{}).text||'').toLowerCase();
          needles.forEach((n,i)=>{if(t.includes(low[i])) out[n]=true});
        }
        for(const e of document.querySelectorAll('body *')){
          if(e.children.length) continue;
          if(e.tagName==='SCRIPT'||e.tagName==='STYLE'||e.tagName==='NOSCRIPT') continue;
          const raw=e.textContent; if(!raw) continue;
          const t=raw.toLowerCase();
          let hit=false; low.forEach((n,i)=>{if(!out[needles[i]]&&t.includes(n)) hit=true});
          if(!hit) continue;
          const b=e.getBoundingClientRect();
          if(b.height>0&&b.width>0&&b.bottom>0&&b.top<innerHeight&&b.right>0&&b.left<innerWidth)
            low.forEach((n,i)=>{if(t.includes(n)) out[needles[i]]=true});
        }
        return JSON.stringify(out);})()"""

    def visible_text(self, needles):
        """Which of these strings are on screen right now, inside the viewport."""
        if not needles:
            return {}
        raw = self.evaluate(self.VISIBLE_TEXT % json.dumps(list(needles)), quiet=True)
        return json.loads(raw) if raw else {}

    def rehearse(self, scenes, dwell=0.7, context=None):
        """Walk the whole storyboard fast, checking every cue actually lands.

        --check only proves a selector exists. The failure that matters is a
        selector that exists but carries no layout box in the view the scene is
        in, because that used to scroll to the top and film the wrong screen.
        This performs the real actions and reports where each one left the page.
        """
        report, expected = [], {}
        # A subset still has to be reached the way the film reaches it: scene 04
        # begins on the lab page only because scene 03 left it there. Replay the
        # earlier scenes' cues silently so the subset starts in the real state.
        lead = []
        if context:
            for scene in context:
                if scene is scenes[0]:
                    break
                lead.append(scene)
        first_actions = (lead[0]["actions"] if lead else scenes[0]["actions"])
        self.goto(next(a[1] for a in first_actions if a[0] == "goto"), settle=2.5)
        for scene in lead:
            for action in scene["actions"]:
                try:
                    self.act(action)
                except Exception:  # noqa: BLE001 - only reported for the subset
                    pass
                self.chrome.pump(0.25)
        for scene in scenes:
            for action in scene["actions"]:
                error = None
                # Existence is not visibility. Both of the faults that reached a
                # finished take were elements that resolved fine but carried no
                # box in the view the scene is filmed in, so measure the target
                # at the moment the cue fires, before acting on it.
                box = None
                if action[0] in ("click", "select", "scroll"):  # selector cues only
                    box = self.evaluate(
                        "(()=>{const e=document.querySelector(%s);if(!e)return null;"
                        "const b=e.getBoundingClientRect();const cs=getComputedStyle(e);"
                        "let hidden=null,n=e;"
                        "while(n&&n!==document.body){if(getComputedStyle(n).display==='none')"
                        "{hidden=n.id||n.className||'anon';break}n=n.parentElement}"
                        "return JSON.stringify({w:Math.round(b.width),h:Math.round(b.height),"
                        "vis:cs.visibility,hiddenBy:hidden});})()" % json.dumps(action[1]),
                        quiet=True)
                try:
                    self.act(action)
                except Exception as problem:  # noqa: BLE001 - reported, not raised
                    error = str(problem)[:120]
                self.chrome.pump(dwell)
                state = self.evaluate(
                    "JSON.stringify({y:Math.round(scrollY),"
                    "centre:(document.elementFromPoint(640,360)||{}).id||"
                    "((document.elementFromPoint(640,360)||{}).closest?"
                    "((document.elementFromPoint(640,360).closest('[id]')||{}).id||''):''),"
                    "page:location.pathname.split('/').pop()})", quiet=True)
                entry = next((e for e in STORYBOARD
                               if e["key"] == scene.get("storyboard")), {})
                seen = self.visible_text(entry.get("expect", []) + entry.get("forbid", []))
                for needle in entry.get("expect", []):
                    if seen.get(needle):
                        expected.setdefault(scene["number"], set()).add(needle)
                onscreen = [n for n in entry.get("forbid", []) if seen.get(n)]
                report.append({
                    "scene": scene["number"], "action": action,
                    "box": json.loads(box) if box else None,
                    "forbidden": onscreen,
                    "state": json.loads(state) if state else {}, "error": error,
                })
        for scene in scenes:
            entry = next((e for e in STORYBOARD
                          if e["key"] == scene.get("storyboard")), {})
            missing = [n for n in entry.get("expect", [])
                       if n not in expected.get(scene["number"], set())]
            if missing:
                report.append({"scene": scene["number"], "action": ("expect",),
                               "box": None, "forbidden": [], "missing": missing,
                               "state": {}, "error": None})
        return report

    # ------------------------------------------------------------- recording

    def record(self, scenes, frame_dir, poster_path=None, quality=88, every_nth=1):
        os.makedirs(frame_dir, exist_ok=True)
        frames = []
        state = {"count": 0, "t0": None}

        def on_frame(params):
            self.chrome.ws.send(json.dumps({
                "id": 10_000_000 + state["count"],
                "method": "Page.screencastFrameAck",
                "params": {"sessionId": params["sessionId"]},
            }))
            stamp = params.get("metadata", {}).get("timestamp") or time.time()
            if state["t0"] is None:
                state["t0"] = stamp
            path = os.path.join(frame_dir, "f%06d.jpg" % state["count"])
            with open(path, "wb") as handle:
                handle.write(base64.b64decode(params["data"]))
            frames.append({"path": path, "t": round(stamp - state["t0"], 4)})
            state["count"] += 1

        self.chrome.handlers["Page.screencastFrame"] = on_frame

        first_page = next(a[1] for a in STORYBOARD[0]["actions"] if a[0] == "goto")
        self.goto(first_page, settle=POSTER["settle"])
        if poster_path:
            self.act(("scroll",) + POSTER["scroll"])
            self.chrome.pump(1.2)
            shot = self.chrome.call("Page.captureScreenshot", {"format": "png"})
            with open(poster_path, "wb") as handle:
                handle.write(base64.b64decode(shot["data"]))
            self.evaluate("window.scrollTo({top:0,behavior:'instant'})", quiet=True)
            self.chrome.pump(0.8)

        self.chrome.call("Page.startScreencast", {
            "format": "jpeg", "quality": quality, "everyNthFrame": every_nth,
            "maxWidth": self.viewport[0], "maxHeight": self.viewport[1],
        })
        clock = time.time()

        def hold_until(video_time):
            remaining = (clock + video_time) - time.time()
            if remaining > 0:
                self.chrome.pump(remaining)

        for scene in scenes:
            actions = [a for a in scene["actions"] if a]
            slot = scene["duration"] / max(1, len(actions))
            for index, action in enumerate(actions):
                self.act(action)
                hold_until(scene["start"] + slot * (index + 1))
            scene["recordedEnd"] = round(time.time() - clock, 3)

        hold_until(scenes[-1]["start"] + scenes[-1]["duration"] + 0.8)
        self.chrome.call("Page.stopScreencast")
        self.chrome.pump(0.4)
        return frames


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def main():
    import argparse

    parser = argparse.ArgumentParser(description="check or record the walkthrough screens")
    parser.add_argument("--check", action="store_true", help="validate selectors and exit")
    parser.add_argument("--port", type=int, default=None,
                        help="static server port (default: a free one)")
    args = parser.parse_args()

    if args.check:
        with Recorder(port=args.port) as recorder:
            report = recorder.check()
        missing = 0
        for page in sorted(report):
            print(f"\n{page}")
            for selector in sorted(report[page]):
                ok = report[page][selector]
                missing += 0 if ok else 1
                print(f"  {'ok  ' if ok else 'MISS'}  {selector}")
        print(f"\n{missing} missing selector(s)")
        raise SystemExit(1 if missing else 0)
    parser.error("nothing to do: pass --check, or call record() from build.py")


if __name__ == "__main__":
    main()
