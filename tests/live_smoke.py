"""Read-only smoke test against a real vBox controller.

Not collected by pytest (no test_ prefix) — run manually:

    python tests/live_smoke.py <ip> [port] [--listen SECONDS]

Occupies the vBox's single host socket for the duration of the run, so
disconnect any other host (HA, app, bridge) first. Sends NO actuation
commands: auth, version query, parameter-API database read, and a full
status request (H:NALL:G) only.
"""

import argparse
import asyncio
import logging
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "vitrea"))

from vitrea_integration.vbox_controller import VBoxController  # noqa: E402

_LOGGER = logging.getLogger("live_smoke")


def stage(name: str, ok: bool, detail: str = "") -> bool:
    marker = "PASS" if ok else "FAIL"
    print(f"[{marker}] {name}" + (f" — {detail}" if detail else ""))
    return ok


async def run(ip: str, port: int, listen_seconds: float) -> int:
    results: list[bool] = []
    print(f"vBox live smoke test → {ip}:{port} at {datetime.now():%H:%M:%S}")
    print("-" * 60)

    # Stage 1: short-lived validation socket (auth + version)
    validation = await VBoxController.validate_controller_availability(ip, port)
    results.append(
        stage(
            "validate: auth + version query",
            validation.get("supported", False),
            f"version={validation.get('version') or '?'} "
            f"led_commands={validation.get('supports_led_commands')} "
            f"reason={validation.get('reason') or '-'}",
        )
    )
    if not validation.get("supported", False):
        print("Controller not reachable/supported — stopping here.")
        return 1

    # Stage 2: full controller lifecycle (connect, DB read, status sync)
    statuses: Counter = Counter()

    async def on_update(item: dict) -> None:
        statuses[item.get("type", "?")] += 1

    controller = VBoxController(ip=ip, port=port, status_update_callback=on_update)
    try:
        connected = await controller.connect()
        results.append(stage("connect + authenticate", bool(connected)))

        db = controller.database
        db_ok = db is not None and db.is_loaded()
        detail = ""
        if db is not None:
            data = db.serialize()
            keys = data.get("keys", [])
            sample = ", ".join(
                repr(k.get("name", "")) for k in keys[:3]
            )
            detail = (
                f"floors={len(data.get('floors', []))} "
                f"rooms={len(data.get('rooms', []))} "
                f"keys={len(keys)} "
                f"acs={len(data.get('air_conditioners', []))} "
                f"scenarios={len(data.get('scenarios', []))}"
                + (f" — sample key names: {sample}" if sample else "")
            )
        results.append(stage("parameter-API database read", db_ok, detail))

        # Stage 3: observe pushed status frames after the NALL:G resync
        # (controller.connect() already requested a full status update).
        print(f"... listening for status frames for {listen_seconds:.0f}s")
        await asyncio.sleep(listen_seconds)
        detail = ", ".join(f"{k}={v}" for k, v in sorted(statuses.items())) or "none"
        results.append(stage("status frames received", sum(statuses.values()) > 0, detail))

        # Stage 4: keep-alive health after the listen window
        conn = controller.connection
        healthy = conn.is_healthy()
        last_rx_age = (
            (datetime.now() - conn.last_rx).total_seconds()
            if conn.last_rx
            else None
        )
        results.append(
            stage(
                "connection healthy (keep-alive flowing)",
                healthy,
                f"last_rx_age={last_rx_age:.1f}s" if last_rx_age is not None else "no rx",
            )
        )
    finally:
        await controller.close()
        print("... connection closed (vBox slot released)")

    print("-" * 60)
    passed = sum(results)
    print(f"{passed}/{len(results)} stages passed")
    return 0 if all(results) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ip")
    parser.add_argument("port", nargs="?", type=int, default=11502)
    parser.add_argument("--listen", type=float, default=25.0,
                        help="seconds to observe pushed status frames (default 25, "
                        "covers at least one keep-alive cycle)")
    parser.add_argument("--debug", action="store_true", help="raw frame logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if not args.debug:
        logging.getLogger("vitrea_integration").setLevel(logging.INFO)

    return asyncio.run(run(args.ip, args.port, args.listen))


if __name__ == "__main__":
    sys.exit(main())
