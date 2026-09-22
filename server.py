#!/usr/bin/env python3
"""
Box Tag – single-port multiplayer server (Render / local friendly)

Serves the static game + WebSocket on the same port.
"""

import asyncio
import json
import logging
import mimetypes
import os
import random
import time
from pathlib import Path
from typing import Dict, Optional

import websockets
from websockets.asyncio.server import serve
from websockets.http11 import Request, Response
from websockets.datastructures import Headers

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("boxtag")

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", 8000))
ROOT = Path(__file__).parent.resolve()

# ---------- Game state ----------
players: Dict[str, dict] = {}
ws_by_id: Dict[str, object] = {}
it_holder: Optional[str] = None
last_tag_time: float = 0.0
TAG_COOLDOWN = 1.2


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
    log.info("Player left: %s  remaining=%d", pid, len(players))

    if it_holder == pid:
        if players:
            it_holder = random.choice(list(players.keys()))
            await broadcast({
                "type": "tagged",
                "newIt": it_holder,
                "taggerId": None,
                "tagX": None,
                "tagY": None,
            })
            log.info("IT passed to %s after disconnect", it_holder)
        else:
            it_holder = None


async def handle_join(ws, msg: dict):
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
        "id": pid, "name": name, "color": color, "cls": cls,
        "x": x, "y": y, "it": False,
        "immuneUntil": 0, "phaseUntil": 0, "glideUntil": 0,
        "hp": 100,
        "joinedAt": now(),
    }
    ws_by_id[pid] = ws

    if it_holder is None or it_holder not in players:
        it_holder = pid
        players[pid]["it"] = True
        await broadcast({
            "type": "tagged", "newIt": it_holder,
            "taggerId": None, "tagX": None, "tagY": None,
        })
    else:
        players[pid]["it"] = (pid == it_holder)

    await broadcast({
        "type": "presence", "id": pid,
        "x": round(x), "y": round(y),
        "name": name, "color": color,
        "it": players[pid]["it"], "cls": cls,
        "immuneUntil": 0, "phaseUntil": 0, "glideUntil": 0,
    })

    for other_id, p in players.items():
        if other_id == pid:
            continue
        await send_to(pid, {
            "type": "presence", "id": other_id,
            "x": round(p["x"]), "y": round(p["y"]),
            "name": p["name"], "color": p["color"],
            "it": p["it"], "cls": p["cls"],
            "immuneUntil": p.get("immuneUntil", 0),
            "phaseUntil": p.get("phaseUntil", 0),
            "glideUntil": p.get("glideUntil", 0),
        })

    log.info("Join: %s (%s) class=%s  players=%d  it=%s", name, pid, cls, len(players), it_holder)


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

    await broadcast({
        "type": "presence", "id": pid,
        "x": round(p["x"]), "y": round(p["y"]),
        "name": p["name"], "color": p["color"],
        "it": p["it"], "cls": p["cls"],
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
        return
    if now() - last_tag_time < TAG_COOLDOWN:
        return

    target = players[target_id]
    if target.get("immuneUntil", 0) > time.time() * 1000:
        log.info("Tag blocked — target %s is immune", target_id)
        return

    last_tag_time = now()
    it_holder = target_id
    for p in players.values():
        p["it"] = (p["id"] == it_holder)

    await broadcast({
        "type": "tagged",
        "newIt": it_holder,
        "taggerId": tagger_id,
        "tagX": msg.get("tagX"),
        "tagY": msg.get("tagY"),
    })
    log.info("TAG: %s → %s", players[tagger_id]["name"], players[target_id]["name"])


async def handle_vfx(msg: dict, sender_id: str):
    out = dict(msg)
    out["from"] = sender_id
    await broadcast(out, exclude=sender_id)


async def handle_damage(msg: dict, attacker_id: str):
    """Relay fighting-mode damage; track simple HP for KO flag."""
    target_id = msg.get("targetId")
    if not target_id or target_id not in players:
        return
    if target_id == attacker_id:
        return
    amount = int(msg.get("amount") or 0)
    if amount <= 0 or amount > 80:
        return

    target = players[target_id]
    hp = float(target.get("hp", 100))
    hp = max(0, hp - amount)
    target["hp"] = hp
    ko = hp <= 0
    if ko:
        target["hp"] = 100  # reset for respawn on client

    await broadcast({
        "type": "damage",
        "targetId": target_id,
        "fromId": attacker_id,
        "amount": amount,
        "source": msg.get("source") or "hit",
        "x": msg.get("x"),
        "y": msg.get("y"),
        "ko": ko,
        "hp": hp if not ko else 0,
    })
    if ko:
        log.info("KO: %s eliminated %s", players.get(attacker_id, {}).get("name"), target.get("name"))


async def ws_handler(ws):
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
            elif mtype == "damage":
                if pid:
                    await handle_damage(msg, pid)
            elif mtype == "build":
                await broadcast(msg, exclude=pid)
            elif mtype == "clearBuilds":
                await broadcast({"type": "clearBuilds"}, exclude=pid)
            elif mtype == "chat":
                if pid is None:
                    pid = msg.get("id")
                text = (msg.get("text") or "").strip()[:120]
                if not text:
                    continue
                name = None
                if pid and pid in players:
                    name = players[pid].get("name")
                if not name:
                    name = (msg.get("name") or "Player")[:16]
                await broadcast({
                    "type": "chat",
                    "id": pid or msg.get("id") or "?",
                    "name": name,
                    "text": text,
                    "t": now(),
                })
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        if pid:
            await remove_player(pid)


# ---------- HTTP static file serving (same port) ----------
def process_request(connection, request: Request):
    """Handle normal HTTP requests; upgrade only for WebSocket."""
    # Let the websockets library handle upgrade requests
    if "upgrade" in {k.lower() for k in request.headers}:
        return None

    # Serve static files
    path = request.path.split("?", 1)[0]
    if path in ("/", ""):
        path = "/index.html"

    # Security: stay inside ROOT
    file_path = (ROOT / path.lstrip("/")).resolve()
    if not str(file_path).startswith(str(ROOT)) or not file_path.is_file():
        body = b"Not Found"
        return Response(404, "Not Found", Headers([
            ("Content-Type", "text/plain"),
            ("Content-Length", str(len(body))),
        ]), body)

    data = file_path.read_bytes()
    content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    headers = Headers([
        ("Content-Type", content_type),
        ("Content-Length", str(len(data))),
        ("Cache-Control", "no-cache"),
    ])
    return Response(200, "OK", headers, data)


async def main():
    log.info("Starting Box Tag on %s:%s  (ROOT=%s)", HOST, PORT, ROOT)
    async with serve(
        ws_handler,
        HOST,
        PORT,
        process_request=process_request,
        ping_interval=20,
        ping_timeout=20,
    ):
        log.info("Ready — open http://localhost:%s", PORT)
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Shutting down")
