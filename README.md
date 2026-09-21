# 🏃 Box Tag

Live multiplayer platformer tag with **11 classes**, power-ups, 90-second rounds, and real-time WebSocket networking. Desktop + mobile.

## Local run

```bash
pip install -r requirements.txt
python server.py
```

Open **http://localhost:8000**

## Deploy on Render.com

| Setting | Value |
|---------|-------|
| Environment | **Python 3** |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `python server.py` |

No `package.json` needed — this is pure Python.

## What's new

- **90s rounds** with scoreboard (most tags wins)
- **Power-ups** spawn on platforms: ⚡ speed, 🚀 jump, 🛡️ shield, ✨ XP
- **Mute button** (saved)
- Round timer in HUD
- Improved mobile controls
- Single-port server (Render-ready)

## Classes (11)

Speedster · Jumper · Tank · Phantom · Glider · Clinger · Bomber · Magnet · Warper · Frost · Pounder

XP unlocks more classes (saved in browser).

## Controls

| Action | Desktop | Mobile |
|--------|---------|--------|
| Move | WASD / arrows | ◀ ▶ |
| Jump | Space / W | ▲ |
| Ability | Shift / E | ★ |
