# LanPaste

A self-hosted pastebin **and** file drop service for your local network. Share text snippets, code, and files between any device on the same LAN — no cloud, no accounts, no external services.

[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0%2B-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![SQLite](https://img.shields.io/badge/SQLite-3-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![JavaScript](https://img.shields.io/badge/JavaScript-Vanilla-F7DF1E?logo=javascript&logoColor=black)](https://developer.mozilla.org/en-US/docs/Web/JavaScript)
[![HTML5](https://img.shields.io/badge/HTML5-E34F26?logo=html5&logoColor=white)](https://developer.mozilla.org/en-US/docs/Web/HTML)
[![CSS3](https://img.shields.io/badge/CSS3-1572B6?logo=css3&logoColor=white)](https://developer.mozilla.org/en-US/docs/Web/CSS)
[![macOS](https://img.shields.io/badge/macOS-launchd-000000?logo=apple&logoColor=white)](https://en.wikipedia.org/wiki/Launchd)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## Highlights

- **Drag-and-drop file sharing** — drop a file on one device, it shows up on every other device pointed at the URL within seconds.
- **Pastebin** — title, language-aware syntax highlighting, expiry presets, burn-after-read.
- **Single binary feel** — one `app.py`, one SQLite file, one optional uploads directory. No build step, no JS bundler, no external services.
- **Always-on** — runs as a `launchd` LaunchAgent on macOS with auto-restart.

## Tech stack

| Layer | Technology |
| --- | --- |
| Backend | Python 3.9+, Flask 3 |
| Storage | SQLite (metadata) + filesystem (uploaded files) |
| Frontend | Vanilla HTML / CSS / JavaScript — no framework, no bundler |
| Syntax highlighting | [highlight.js](https://highlightjs.org/) (CDN) |
| Process supervision | `launchd` (macOS) |

## Quick start

```bash
git clone https://github.com/asispan/lanpaste.git
cd lanpaste
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

The server binds to `0.0.0.0:8080`. Open `http://<your-lan-ip>:8080` from any device on the same network.

Override the port with `PORT=9000 python app.py`.

## Usage

### Web UI

Visit the root URL on any device. The home page hosts both features:

- **Drop files** anywhere in the dropzone — they upload immediately, with per-file progress bars, and appear on every other device's file list within ~2 seconds.
- **Create pastes** in the form below the file area.
- **Download** any shared file with a single click; the original filename is preserved.
- **Delete** files via the `×` button.

### Share a file from the CLI

```bash
# Upload
curl -F "file=@photo.jpg" -F "expiry=1d" http://192.168.0.143:8080/api/files

# List
curl http://192.168.0.143:8080/api/files

# Download (preserves original filename)
curl -OJ http://192.168.0.143:8080/f/<id>

# Delete
curl -X DELETE http://192.168.0.143:8080/api/files/<id>
```

### Share a paste from the CLI

```bash
# JSON
curl -s -H 'Content-Type: application/json' \
     -d "$(jq -Rs '{content: ., language: "bash", expiry: "1h"}' < script.sh)" \
     http://192.168.0.143:8080/api/paste

# Form-encoded
curl -s -F 'content=<script.sh' -F expiry=1h http://192.168.0.143:8080/api/paste
```

Response:

```json
{ "id": "abc1234", "url": "...", "raw": "...", "expires_at": "..." }
```

Handy shell function:

```bash
lanpaste() {
  curl -s -F "content=<${1:--}" "http://192.168.0.143:8080/api/paste" | jq -r .url
}
# usage: lanpaste file.txt    or    echo hi | lanpaste
```

## API reference

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | Web UI — file dropzone + paste form |
| `POST` | `/new` | Create a paste (form submit) |
| `POST` | `/api/paste` | Create a paste from JSON or form |
| `GET` | `/p/<id>` | View a paste |
| `GET` | `/raw/<id>` | Raw paste content |
| `GET` | `/dl/<id>` | Download paste as `.txt` |
| `POST` | `/api/files` | Upload one or more files (`multipart/form-data`, field `file`) |
| `GET` | `/api/files` | List shared files (JSON) |
| `GET` | `/f/<id>` | Download a shared file |
| `DELETE` | `/api/files/<id>` | Delete a shared file |

### Expiry options

`10m`, `1h`, `1d` (default), `7d`, `30d`, `never`. Expired records are lazily purged on each request.

### Limits

| Resource | Default | Where to change |
| --- | --- | --- |
| Paste size | 1 MiB | `MAX_PASTE_SIZE` in `app.py` |
| File size | 100 MiB | `MAX_FILE_SIZE` in `app.py` |
| Listening port | 8080 | `PORT` env var |

## Run as a service (macOS)

LanPaste runs 24/7 via a `launchd` LaunchAgent. Create `~/Library/LaunchAgents/com.asispanda.lanpaste.plist` pointing at this directory's `python` and `app.py`, then:

```bash
# Status
launchctl print gui/501/com.asispanda.lanpaste

# Restart
launchctl kickstart -k gui/501/com.asispanda.lanpaste

# Stop & unload
launchctl bootout gui/501/com.asispanda.lanpaste

# Load / start (after edits or after bootout)
launchctl bootstrap gui/501 ~/Library/LaunchAgents/com.asispanda.lanpaste.plist

# Tail logs
tail -f logs/out.log logs/err.log
```

The agent uses `KeepAlive=true` and `RunAtLoad=true`, with a 5-second `ThrottleInterval` to prevent tight crash loops.

> LaunchAgents run only while the user is logged in. For full 24/7 operation across logouts, convert to a `LaunchDaemon` under `/Library/LaunchDaemons/` (requires root).

## Finding your LAN IP

```bash
# macOS
ipconfig getifaddr en0   # Ethernet / Wi-Fi
ipconfig getifaddr en1   # alternative interface

# Linux
hostname -I

# Windows (PowerShell)
ipconfig | Select-String IPv4
```

For a stable URL, set a DHCP reservation on your router so the host always gets the same IP.

## Security

- **No authentication.** Anyone on the LAN can read, upload, and delete content.
- **Do not expose to the public internet.** Use a VPN or SSH tunnel if you need remote access.
- **macOS firewall:** if other devices can't reach the server, allow incoming connections to `python` in `System Settings → Network → Firewall`.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Port 8080 busy | `lsof -iTCP:8080 -sTCP:LISTEN` — see what's using it, then change `PORT` |
| Not reachable from another device | Same LAN? Some routers isolate guest Wi-Fi. macOS firewall allowing Python? |
| Service keeps respawning | `logs/err.log` — the 5 s throttle prevents a tight loop |
| Service goes away when Mac sleeps | LaunchAgents stop on logout; convert to LaunchDaemon for full uptime |
| Files don't sync between devices | Browser must allow JS; the file list refreshes every ~2 s via polling |

## Project layout

```
lanpaste/
├── app.py              # Flask app — all routes and DB logic
├── requirements.txt    # Flask>=3.0
├── templates/          # Jinja templates: base, index, view, error
├── static/             # style.css
├── pastes.db           # SQLite (gitignored, created on first run)
├── uploads/            # Stored files (gitignored, created on first run)
└── logs/               # Service logs (gitignored)
```

## License

MIT — see [LICENSE](LICENSE).
