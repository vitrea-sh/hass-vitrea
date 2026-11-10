"""Ghost-hunt analyzer: classify every Vitrea actuation in an HA log.

Not collected by pytest — run manually:

    python tests/ghost_hunt.py <home-assistant.log> [more logs...]

Requires vitrea debug logging (custom_components.vitrea: debug). For each
actuation it answers "who asked?":

  HUMAN       entity_debug context has a user_id (dashboard/app/voice)
  AUTOMATION  entity_debug context has a parent_id (automation/script)
  INTERNAL    entity_debug context has neither -> initiated by an
              integration (HomeKit, scheduler, ...) inside HA
  MULTIWAY    a Multiway link action (INFO-logged by the link itself)
  UNATTRIBUTED an actuation TX with no known requester logged nearby —
              investigate (old build without entity_debug, or a gap)

It also reports wall/external events (RX status changes with no TX),
connection incidents, and Multiway breaker trips.
"""

import re
import sys
from collections import Counter

TS = r"(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)"
RE_TX = re.compile(TS + r".*vbox_connection\] TX b'(?P<frame>[^']*)'")
RE_RX = re.compile(TS + r".*vbox_connection\] RX b'(?P<frame>[^']*)'")
RE_CTX = re.compile(
    TS
    + r".*entity_debug\] (?P<action>\S+) requested for (?P<entity>\S+) "
    + r"\(context=(?P<ctx>\S+) user=(?P<user>\S+) parent=(?P<parent>\S+)\)"
)
RE_MULTIWAY = re.compile(TS + r".*\.multiway\] (?P<msg>Multiway .*)")
RE_CONN = re.compile(
    TS + r".*(?P<msg>Connection to Vitrea lost due to: .*|The connection is "
    r"back online|Successfully reconnected to VBox.*)"
)

# Actuation frames: H:Nxxx:K:<action>... where action is not G (query).
RE_ACTUATION = re.compile(r"H:(N\d+|A\d+|O\d+|R\d+)(:(\d+))?:(?P<act>[OFDTBMdr])")
QUERY_MARKERS = (":G", "NALL", "P:VITREA", "G:V", "VTH>")


def classify_frame(frame: str):
    if any(marker in frame for marker in QUERY_MARKERS):
        return None
    match = RE_ACTUATION.search(frame)
    if match:
        return match.group(0)
    if frame.startswith("L:"):
        return frame.rstrip("\\r\\n") + " (LED)"
    return None


def _key_of(frame: str) -> str | None:
    """Node:key identity of a frame, e.g. H:N005:2:... / S:N005:2:... -> N005:2."""
    match = re.match(r"[HS]:(N\d+):(\d+)", frame)
    return f"{match.group(1)}:{match.group(2)}" if match else None


def main(paths: list[str]) -> int:
    events = []
    recent_ctx = []  # entity_debug context lines awaiting their TX
    pending_multiway = 0  # multiway set-key lines awaiting their TX
    recent_tx_keys: dict[str, str] = {}  # node:key -> ts of our own TX
    counts: Counter = Counter()

    for path in paths:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if match := RE_CTX.search(line):
                    recent_ctx.append(match.groupdict())
                    recent_ctx[:] = recent_ctx[-8:]
                    continue
                if match := RE_MULTIWAY.search(line):
                    events.append((match["ts"], "MULTIWAY", match["msg"]))
                    counts["MULTIWAY"] += 1
                    if "setting key" in match["msg"]:
                        pending_multiway += 1
                    continue
                if match := RE_CONN.search(line):
                    events.append((match["ts"], "CONNECTION", match["msg"]))
                    counts["CONNECTION"] += 1
                    continue
                if match := RE_TX.search(line):
                    actuation = classify_frame(match["frame"])
                    if not actuation:
                        continue
                    if key := _key_of(match["frame"]):
                        recent_tx_keys[key] = match["ts"]
                    # Attribute to the most recent context line (they are
                    # logged immediately before the model sends).
                    origin = "UNATTRIBUTED"
                    detail = match["frame"]
                    if recent_ctx:
                        ctx = recent_ctx.pop()
                        if ctx["user"] != "None":
                            origin = "HUMAN"
                        elif ctx["parent"] != "None":
                            origin = "AUTOMATION"
                        else:
                            origin = "INTERNAL(HomeKit/scheduler/...)"
                        detail = (
                            f"{match['frame']}  <- {ctx['action']} on "
                            f"{ctx['entity']} user={ctx['user']} "
                            f"parent={ctx['parent']}"
                        )
                    elif pending_multiway > 0:
                        pending_multiway -= 1
                        origin = "MULTIWAY(link TX)"
                    events.append((match["ts"], origin, detail))
                    counts[origin] += 1
                    continue
                if match := RE_RX.search(line):
                    frame = match["frame"]
                    if frame.startswith("S:N") and frame.count(":") >= 3:
                        key = _key_of(frame)
                        if key and key in recent_tx_keys:
                            # Confirmation of our own command, not external.
                            del recent_tx_keys[key]
                            continue
                        events.append((match["ts"], "WALL/EXTERNAL", frame))
                        counts["WALL/EXTERNAL"] += 1

    print(f"{'timestamp':<28} {'origin':<28} detail")
    print("-" * 100)
    for ts, origin, detail in events:
        print(f"{ts:<28} {origin:<28} {detail}")
    print("-" * 100)
    for origin, count in counts.most_common():
        print(f"{origin:<28} {count}")
    unattributed = counts.get("UNATTRIBUTED", 0)
    if unattributed:
        print(
            f"\n!! {unattributed} actuation(s) without attribution — deploy the "
            "latest build (entity_debug) or investigate these lines."
        )
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    sys.exit(main(sys.argv[1:]))
