# LanPaste

> A self-hosted **pastebin + file drop** for your local network. Share text, code, and files between any device on the same Wi-Fi — no cloud, no accounts, no third parties.

[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![SQLite](https://img.shields.io/badge/SQLite-3-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![macOS](https://img.shields.io/badge/macOS-launchd-000000?logo=apple&logoColor=white)](https://en.wikipedia.org/wiki/Launchd)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

LanPaste runs as an always-on background service on your Mac and serves a single web page that every device on your LAN can open. Drop a file on your laptop, grab it on your phone. Paste a log on your phone, open it on your laptop. One `app.py`, one SQLite file — no build step, no framework, no external services.

---

## Install

**One command.** Installs LanPaste and starts it as a background service that launches at login and restarts itself if it ever crashes:

```bash
curl -fsSL https://raw.githubusercontent.com/asispan/lanpaste/main/install.sh | bash
```

When it finishes it prints the URL to open — for example `http://192.168.1.20:8080`. Open that on any device on the same network and you're done. LanPaste is now running and will come back automatically after a reboot.

<details>
<summary><b>Prefer not to pipe to <code>bash</code>?</b> Clone and run it yourself.</summary>

```bash
git clone https://github.com/asispan/lanpaste.git
cd lanpaste
./install.sh
```

The script is short and dependency-free — read [`install.sh`](install.sh) before running it.
</details>

**Requirements:** macOS with `python3` (already present on modern macOS; otherwise `xcode-select --install`). Nothing else — the installer creates an isolated virtual environment.

### Install options

Override any of these by setting the variable on the install command:

```bash
curl -fsSL https://raw.githubusercontent.com/asispan/lanpaste/main/install.sh | PORT=9000 bash
```

| Variable | Default | Purpose |
| --- | --- | --- |
| `PORT` | `8080` | Port the service listens on |
| `LANPASTE_HOME` | `~/.lanpaste` | Where the app and its data live |
| `LANPASTE_LABEL` | `com.asispan.lanpaste` | launchd service label |

---

## Usage

### Web UI

Open the URL (e.g. `http://<your-mac-ip>:8080`) on any device on the LAN. The home page hosts both features:

- **Drop files** anywhere in the dropzone — they upload immediately with per-file progress, and appear on every other device's list within ~2 seconds.
- **Create pastes** in the form below: optional title, language for syntax highlighting, expiry preset, and burn-after-read.
- **Download** any shared file in one click — the original filename is preserved.
- **Delete** a file with the `×` button.

### From the command line

Set your server once, then use the snippets below:

```bash
export LANPASTE=http://192.168.1.20:8080   # your Mac's LAN address
```

**Share files**

```bash
curl -F "file=@photo.jpg" -F "expiry=1d" "$LANPASTE/api/files"   # upload
curl "$LANPASTE/api/files"                                       # list (JSON)
curl -OJ "$LANPASTE/f/<id>"                                      # download (keeps filename)
curl -X DELETE "$LANPASTE/api/files/<id>"                        # delete
```

**Share pastes**

```bash
# from a file (form-encoded)
curl -s -F 'content=<script.sh' -F expiry=1h "$LANPASTE/api/paste"

# from a pipe (JSON, with language for highlighting)
echo "hello" | curl -s -H 'Content-Type: application/json' \
  -d "$(jq -Rs '{content: ., language: "bash", expiry: "1h"}')" "$LANPASTE/api/paste"
```

Response: `{ "id": "...", "url": "...", "raw": "...", "expires_at": "..." }`

**Handy shell helper** — add to your `~/.zshrc`:

```bash
lanpaste() { curl -s -F "content=<${1:--}" "$LANPASTE/api/paste" | jq -r .url; }
# usage:  lanpaste file.txt    |    echo hi | lanpaste
```

---

## Managing the service

LanPaste runs as a launchd LaunchAgent (`com.asispan.lanpaste`). Logs live in `~/.lanpaste/logs/`.

```bash
# Restart
launchctl kickstart -k gui/$(id -u)/com.asispan.lanpaste

# Stop (until next login)
launchctl bootout gui/$(id -u)/com.asispan.lanpaste

# Start again
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.asispan.lanpaste.plist

# Follow the logs
tail -f ~/.lanpaste/logs/out.log ~/.lanpaste/logs/err.log
```

> LaunchAgents run while you're logged in. For uptime across logouts, convert it to a `LaunchDaemon` under `/Library/LaunchDaemons/` (requires root).

### Uninstall

```bash
# Stop the service and remove the LaunchAgent (keeps your data)
curl -fsSL https://raw.githubusercontent.com/asispan/lanpaste/main/uninstall.sh | bash

# Also delete the installed copy, pastes, and uploads
curl -fsSL https://raw.githubusercontent.com/asispan/lanpaste/main/uninstall.sh | bash -s -- --purge
```

---

## Configuration

| Setting | Default | Where |
| --- | --- | --- |
| Listening port | `8080` | `PORT` (installer) or re-run with a new value |
| Paste size limit | 1 MiB | `MAX_PASTE_SIZE` in [`app.py`](app.py) |
| File size limit | 100 MiB | `MAX_FILE_SIZE` in [`app.py`](app.py) |
| Expiry presets | `10m` `1h` `1d`* `7d` `30d` `never` | `EXPIRY_OPTIONS` in [`app.py`](app.py) |

<sub>*default. Expired pastes and files are purged lazily on each request.</sub>

## API reference

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | Web UI — dropzone + paste form |
| `POST` | `/api/paste` | Create a paste (JSON or form) |
| `GET` | `/p/<id>` | View a paste |
| `GET` | `/raw/<id>` | Raw paste content |
| `GET` | `/dl/<id>` | Download paste as `.txt` |
| `POST` | `/api/files` | Upload file(s) (`multipart/form-data`, field `file`) |
| `GET` | `/api/files` | List shared files (JSON) |
| `GET` | `/f/<id>` | Download a shared file |
| `DELETE` | `/api/files/<id>` | Delete a shared file |

## Security

LanPaste is built for a **trusted local network**, not the public internet.

- **No authentication** — anyone who can reach the URL can read, upload, and delete.
- **Do not port-forward or expose it publicly.** For remote access, use a VPN or SSH tunnel (e.g. Tailscale).
- **Firewall:** if other devices can't connect, allow incoming connections for `python` under *System Settings → Network → Firewall*. macOS may prompt for this the first time the service starts.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Not reachable from another device | Same network? Some routers isolate guest Wi-Fi. Is the macOS firewall allowing `python`? |
| `Port 8080 busy` | `lsof -iTCP:8080 -sTCP:LISTEN` to see what's using it, then reinstall with `PORT=9000`. |
| Service didn't start | `tail -f ~/.lanpaste/logs/err.log` — a 5 s throttle prevents a tight crash loop. |
| Files don't sync between devices | The list refreshes every ~2 s via polling; the browser must allow JavaScript. |
| Service stops when the Mac sleeps/logs out | LaunchAgents stop on logout — convert to a LaunchDaemon for full uptime. |

## Development / manual run

To hack on LanPaste without installing the service:

```bash
git clone https://github.com/asispan/lanpaste.git
cd lanpaste
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py            # http://localhost:8080  (PORT=9000 to change)
```

## How it works

| Layer | Technology |
| --- | --- |
| Backend | Python 3.9+, Flask 3 — a single [`app.py`](app.py) |
| Storage | SQLite for metadata + the filesystem for uploaded files |
| Frontend | Vanilla HTML / CSS / JS — no framework, no bundler |
| Highlighting | [highlight.js](https://highlightjs.org/) via CDN |
| Service | `launchd` LaunchAgent (`RunAtLoad` + `KeepAlive`) |

```
lanpaste/
├── app.py            # Flask app — all routes and DB logic
├── install.sh        # One-command macOS installer + service setup
├── uninstall.sh      # Stop service and remove (optionally --purge data)
├── requirements.txt  # Flask>=3.0
├── templates/        # Jinja templates: base, index, view, error
├── static/           # style.css
├── pastes.db         # SQLite — created on first run (gitignored)
├── uploads/          # Stored files — created on first run (gitignored)
└── logs/             # Service logs (gitignored)
```

## License

[MIT](LICENSE)
