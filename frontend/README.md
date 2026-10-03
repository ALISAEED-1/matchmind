# MatchMind web app (Flutter)

Broadcast-style viewer for MatchMind: pitch view, timed overlay cards, momentum graph, Fan /
Analyst / Player focus modes, English / Urdu / Arabic, and a debug drawer showing every agent
handoff.

- **Demo mode** replays bundles in `assets/data/` (exported from the backend with
  `uv run python scripts/export_web_data.py`). No backend needed; this is what GitHub Pages serves.
- **Live agents** connects to the backend WebSocket (`uv run uvicorn matchmind.api.app:app`) and
  runs the agent team while you watch, personalised for your profile, with a simulated-outage
  switch in the debug drawer.

```bash
flutter pub get
flutter run -d chrome
flutter build web --release --pwa-strategy=none
```

Deep links (handy for demos): `?match=mm-0004-comeback&seek=59&audience=analyst&lang=ur&club=IRN`,
plus `drawer=1` (open the handoff drawer) or `recap=1` (jump to the full-time recap).
