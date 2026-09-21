#!/usr/bin/env python3
"""
Box Tag - WebSocket multiplayer server
Run: python3 server.py
Then open http://localhost:8000 in multiple tabs/browsers.
"""

import asyncio
import json
import logging
import random
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Dict, Optional, Set

import websockets
from websockets.asyncio.server import ServerConnection as WebSocketServerProtocol

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("boxtag")

HOST = "0.0.0.0"
HTTP_PORT = 8000
WS_PORT = 8001

# Game state
players: Dict[str, dict] = {}          # id -> player data
ws_by_id: Dict[str, WebSocketServerProtocol] = {}
it_holder: Optional[str] = None
last_tag_time: float = 0.0
TAG_COOLDOWN = 1.2  # seconds


def now() -> float:
    return time.time()


async def broadcast(msg: dict, exclude: Optional[str] = None):
    data = json.dumps(msg)
    dead = []
    for pid, ws in list(ws_by_id.items()):
        if pid == exclude:
            continue
        try:
            await ws.send(data)
        except Exception:
            dead.append(pid)
    for pid in dead:
        await remove_player(pid)


async def send_to(pid: str, msg: dict):
    ws = ws_by_id.get(pid)
    if ws:
        try:
            await ws.send(json.dumps(msg))
        except Exception:
            await remove_player(pid)


async def remove_player(pid: str):
    global it_holder
    if pid in players:
        del players[pid]
    if pid in ws_by_id:
        del ws_by_id[pid]
    await broadcast({"type": "leave", "id": pid})
    log.info(f"Player left: {pid}  remaining={len(players)}")

    if it_holder == pid:
        # Pass "it" to a random remaining player
        if players:
            it_holder = random.choice(list(players.keys()))
            await broadcast({
                "type": "tagged",
                "newIt": it_holder,
                "taggerId": None,
                "tagX": None,
                "tagY": None,
            })
            log.info(f"IT passed to {it_holder} after disconnect")
        else:
            it_holder = None


async def handle_join(ws: WebSocketServerProtocol, msg: dict):
    global it_holder
    pid = msg.get("id")
    if not pid or not isinstance(pid, str):
        return
    name = (msg.get("name") or "Player")[:16]
    color = msg.get("color") or "#5eb1ff"
    cls = msg.get("cls") or "speedster"
    x = float(msg.get("x", 100))
    y = float(msg.get("y", 100))

    players[pid] = {
        "id": pid,
        "name": name,
        "color": color,
        "cls": cls,
        "x": x,
        "y": y,
        "it": False,
        "immuneUntil": 0,
        "phaseUntil": 0,
        "glideUntil": 0,
        "joinedAt": now(),
    }
    ws_by_id[pid] = ws

    # First player becomes IT
    if it_holder is None or it_holder not in players:
        it_holder = pid
        players[pid]["it"] = True
        await broadcast({
            "type": "tagged",
            "newIt": it_holder,
            "taggerId": None,
            "tagX": None,
            "tagY": None,
        })
    else:
        players[pid]["it"] = (pid == it_holder)

    # Tell everyone about this player
    await broadcast({
        "type": "presence",
        "id": pid,
        "x": round(x),
        "y": round(y),
        "name": name,
        "color": color,
        "it": players[pid]["it"],
        "cls": cls,
        "immuneUntil": 0,
        "phaseUntil": 0,
        "glideUntil": 0,
    })

    # Send existing players to the new joiner
    for other_id, p in players.items():
        if other_id == pid:
            continue
        await send_to(pid, {
            "type": "presence",
            "id": other_id,
            "x": round(p["x"]),
            "y": round(p["y"]),
            "name": p["name"],
            "color": p["color"],
            "it": p["it"],
            "cls": p["cls"],
            "immuneUntil": p.get("immuneUntil", 0),
            "phaseUntil": p.get("phaseUntil", 0),
            "glideUntil": p.get("glideUntil", 0),
        })

    log.info(f"Join: {name} ({pid}) class={cls}  players={len(players)}  it={it_holder}")


async def handle_presence(msg: dict):
    pid = msg.get("id")
    if pid not in players:
        return
    p = players[pid]
    p["x"] = float(msg.get("x", p["x"]))
    p["y"] = float(msg.get("y", p["y"]))
    p["name"] = (msg.get("name") or p["name"])[:16]
    p["color"] = msg.get("color") or p["color"]
    p["cls"] = msg.get("cls") or p["cls"]
    p["it"] = bool(msg.get("it", False))
    p["immuneUntil"] = float(msg.get("immuneUntil") or 0)
    p["phaseUntil"] = float(msg.get("phaseUntil") or 0)
    p["glideUntil"] = float(msg.get("glideUntil") or 0)

    # Relay to everyone else
    await broadcast({
        "type": "presence",
        "id": pid,
        "x": round(p["x"]),
        "y": round(p["y"]),
        "name": p["name"],
        "color": p["color"],
        "it": p["it"],
        "cls": p["cls"],
        "immuneUntil": p["immuneUntil"],
        "phaseUntil": p["phaseUntil"],
        "glideUntil": p["glideUntil"],
    }, exclude=pid)


async def handle_tag(msg: dict, tagger_id: str):
    global it_holder, last_tag_time
    target_id = msg.get("targetId")
    if not target_id or target_id not in players:
        return
    if tagger_id != it_holder:
        return  # only the current IT can tag
    if now() - last_tag_time < TAG_COOLDOWN:
        return

    target = players[target_id]
    # Client sends immuneUntil as Date.now() milliseconds
    if target.get("immuneUntil", 0) > time.time() * 1000:
        log.info(f"Tag blocked — target {target_id} is immune")
        return

    last_tag_time = now()
    it_holder = target_id

    for p in players.values():
        p["it"] = (p["id"] == it_holder)

    tag_x = msg.get("tagX")
    tag_y = msg.get("tagY")

    await broadcast({
        "type": "tagged",
        "newIt": it_holder,
        "taggerId": tagger_id,
        "tagX": tag_x,
        "tagY": tag_y,
    })
    log.info(f"TAG: {players[tagger_id]['name']} → {players[target_id]['name']}")


async def handle_vfx(msg: dict, sender_id: str):
    # Just relay VFX to everyone else
    out = dict(msg)
    out["from"] = sender_id
    await broadcast(out, exclude=sender_id)


async def handler(ws: WebSocketServerProtocol):
    pid = None
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            mtype = msg.get("type")

            if mtype == "join":
                pid = msg.get("id")
                await handle_join(ws, msg)
            elif mtype == "presence":
                if pid is None:
                    pid = msg.get("id")
                await handle_presence(msg)
            elif mtype == "tag":
                if pid:
                    await handle_tag(msg, pid)
            elif mtype == "vfx":
                if pid:
                    await handle_vfx(msg, pid)
            else:
                pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        if pid:
            await remove_player(pid)


def start_http_server():
    """Serve the static files (index.html etc.) on HTTP_PORT"""
    root = Path(__file__).parent.resolve()

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def log_message(self, format, *args):
            # quieter
            if "GET / " in (args[0] if args else ""):
                log.info("HTTP %s", args[0])

    server = ThreadingHTTPServer((HOST, HTTP_PORT), Handler)
    log.info(f"HTTP server serving {root} on http://{HOST}:{HTTP_PORT}")
    server.serve_forever()


async def main():
    # Start HTTP in background thread
    t = Thread(target=start_http_server, daemon=True)
    t.start()

    log.info(f"WebSocket server on ws://{HOST}:{WS_PORT}")
    async with websockets.serve(handler, HOST, WS_PORT, ping_interval=20, ping_timeout=20):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Shutting down")
