# 🏃 Box Tag

Live multiplayer platformer tag with 11 classes, abilities, particles, and real-time WebSocket networking. Works great on desktop **and mobile**.

## Quick start

```bash
cd box-tag
python3 server.py
```

Open **http://localhost:8000** on multiple devices / tabs / phones.

| Port | Service              |
|------|----------------------|
| 8000 | Game (HTTP)          |
| 8001 | Multiplayer (WebSocket) |

On phones use your computer’s local IP (e.g. `http://192.168.x.x:8000`).

## Controls

**Desktop**
- Move: A/D or ←/→
- Jump: Space / W / ↑
- Ability: Shift / E

**Mobile**
- Large on-screen buttons (move + jump + ability)
- Optimized for touch, safe-area aware, no accidental zoom

## Classes (11 total)

| Class      | Unlock | Ability              | Notes                     |
|------------|--------|----------------------|---------------------------|
| Speedster  | 0 XP   | Dash                 | Fast run                  |
| Jumper     | 0 XP   | Double Jump          | High jumps                |
| Tank       | 40 XP  | Shield               | Longer immunity           |
| Phantom    | 100 XP | Phase                | Invisible + immune        |
| Glider     | 160 XP | Glide                | Slow floaty fall          |
| Clinger    | 180 XP | Wall Cling           | Stick to walls + wall jump|
| Bomber     | 240 XP | Blast                | Knockback burst           |
| Magnet     | 280 XP | Attract              | Pull nearby players       |
| Warper     | 320 XP | Blink                | Teleport forward          |
| Frost      | 360 XP | Freeze               | Slow nearby players       |
| Pounder    | 450 XP | Ground Slam          | Dive + shockwave (air)    |

XP is saved in the browser (`localStorage`). Survive and tag others to unlock more classes.

## Features

- Real-time multiplayer (presence + authoritative tagging)
- 11 unique classes with cooldowns & VFX
- Particle system, screen shake, wind, ambient leaves
- Mobile-first touch controls + desktop keyboard
- Light / dark theme (system preference)
- Offline practice mode if the server is down
- Auto-reconnect
- Sound effects (Web Audio)

## Requirements

- Python 3.8+
- `websockets` package (`pip install websockets`)

```bash
pip install websockets
python3 server.py
```

That’s it — no build step, no frameworks.
