import os
import sqlite3
import secrets
import string
import re
import unicodedata
from datetime import datetime, timedelta
from contextlib import contextmanager
from flask import Flask, request, render_template, redirect, url_for, abort, jsonify, Response, send_file

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "pastes.db")
UPLOAD_DIR = os.path.join(APP_DIR, "uploads")
MAX_PASTE_SIZE = 1 * 1024 * 1024  # 1 MiB per paste
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MiB per file

EXPIRY_OPTIONS = {
    "10m": timedelta(minutes=10),
    "1h": timedelta(hours=1),
    "1d": timedelta(days=1),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "never": None,
}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE + 16 * 1024


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pastes (
                id TEXT PRIMARY KEY,
                title TEXT,
                content TEXT NOT NULL,
                language TEXT DEFAULT 'plaintext',
                created_at TEXT NOT NULL,
                expires_at TEXT,
                burn_after_read INTEGER DEFAULT 0,
                views INTEGER DEFAULT 0
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_expires ON pastes(expires_at)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                size INTEGER NOT NULL,
                mime TEXT,
                created_at TEXT NOT NULL,
                expires_at TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_files_expires ON files(expires_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_files_created ON files(created_at)")


def generate_id(length=7, table="pastes"):
    alphabet = string.ascii_lowercase + string.digits
    while True:
        pid = "".join(secrets.choice(alphabet) for _ in range(length))
        with get_db() as conn:
            row = conn.execute(f"SELECT 1 FROM {table} WHERE id = ?", (pid,)).fetchone()
            if not row:
                return pid


def purge_expired():
    now = datetime.utcnow().isoformat()
    with get_db() as conn:
        conn.execute(
            "DELETE FROM pastes WHERE expires_at IS NOT NULL AND expires_at < ?",
            (now,),
        )
        expired = conn.execute(
            "SELECT id FROM files WHERE expires_at IS NOT NULL AND expires_at < ?",
            (now,),
        ).fetchall()
        for row in expired:
            try:
                os.remove(os.path.join(UPLOAD_DIR, row["id"]))
            except FileNotFoundError:
                pass
        conn.execute(
            "DELETE FROM files WHERE expires_at IS NOT NULL AND expires_at < ?",
            (now,),
        )


def sanitize_filename(name):
    if not name:
        return "file"
    name = unicodedata.normalize("NFKC", name)
    name = name.replace("\\", "/").split("/")[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    return name[:255] or "file"


def human_size(n):
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024 or unit == "GiB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} {unit}"
        n /= 1024
    return f"{n:.1f} GiB"


@app.route("/", methods=["GET"])
def index():
    purge_expired()
    with get_db() as conn:
        recent = conn.execute(
            """
            SELECT id, title, language, created_at, expires_at
            FROM pastes
            WHERE burn_after_read = 0
            ORDER BY created_at DESC
            LIMIT 20
            """
        ).fetchall()
    return render_template(
        "index.html",
        recent=recent,
        expiry_options=list(EXPIRY_OPTIONS.keys()),
    )


@app.route("/new", methods=["POST"])
def new_paste():
    content = request.form.get("content", "")
    if not content.strip():
        return redirect(url_for("index"))
    if len(content.encode("utf-8")) > MAX_PASTE_SIZE:
        abort(413)

    title = (request.form.get("title") or "").strip()[:200] or None
    language = (request.form.get("language") or "plaintext").strip()[:40]
    expiry_key = request.form.get("expiry", "1d")
    burn = 1 if request.form.get("burn") == "on" else 0

    delta = EXPIRY_OPTIONS.get(expiry_key, timedelta(days=1))
    now = datetime.utcnow()
    expires_at = (now + delta).isoformat() if delta else None

    pid = generate_id()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO pastes (id, title, content, language, created_at, expires_at, burn_after_read)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (pid, title, content, language, now.isoformat(), expires_at, burn),
        )
    return redirect(url_for("view_paste", paste_id=pid))


def fetch_paste(paste_id):
    purge_expired()
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM pastes WHERE id = ?", (paste_id,)
        ).fetchone()
        if not row:
            return None
        if row["burn_after_read"]:
            conn.execute("DELETE FROM pastes WHERE id = ?", (paste_id,))
        else:
            conn.execute(
                "UPDATE pastes SET views = views + 1 WHERE id = ?", (paste_id,)
            )
    return row


@app.route("/p/<paste_id>", methods=["GET"])
def view_paste(paste_id):
    row = fetch_paste(paste_id)
    if not row:
        abort(404)
    return render_template("view.html", paste=row)


@app.route("/raw/<paste_id>", methods=["GET"])
def raw_paste(paste_id):
    row = fetch_paste(paste_id)
    if not row:
        abort(404)
    return Response(row["content"], mimetype="text/plain; charset=utf-8")


@app.route("/dl/<paste_id>", methods=["GET"])
def download_paste(paste_id):
    row = fetch_paste(paste_id)
    if not row:
        abort(404)
    filename = f"{paste_id}.txt"
    return Response(
        row["content"],
        mimetype="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.route("/api/paste", methods=["POST"])
def api_paste():
    data = request.get_json(silent=True) or request.form
    content = data.get("content", "")
    if not content.strip():
        return jsonify({"error": "content required"}), 400
    if len(content.encode("utf-8")) > MAX_PASTE_SIZE:
        return jsonify({"error": "too large"}), 413

    title = (data.get("title") or "").strip()[:200] or None
    language = (data.get("language") or "plaintext").strip()[:40]
    expiry_key = data.get("expiry", "1d")
    burn = 1 if data.get("burn") in (True, "true", "on", 1, "1") else 0

    delta = EXPIRY_OPTIONS.get(expiry_key, timedelta(days=1))
    now = datetime.utcnow()
    expires_at = (now + delta).isoformat() if delta else None

    pid = generate_id()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO pastes (id, title, content, language, created_at, expires_at, burn_after_read)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (pid, title, content, language, now.isoformat(), expires_at, burn),
        )
    return jsonify(
        {
            "id": pid,
            "url": url_for("view_paste", paste_id=pid, _external=True),
            "raw": url_for("raw_paste", paste_id=pid, _external=True),
            "expires_at": expires_at,
        }
    )


@app.route("/api/files", methods=["GET"])
def api_files_list():
    purge_expired()
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, name, size, mime, created_at, expires_at
            FROM files
            ORDER BY created_at DESC
            LIMIT 200
            """
        ).fetchall()
    items = [
        {
            "id": r["id"],
            "name": r["name"],
            "size": r["size"],
            "size_human": human_size(r["size"]),
            "mime": r["mime"],
            "created_at": r["created_at"],
            "expires_at": r["expires_at"],
            "url": url_for("download_file", file_id=r["id"], _external=False),
        }
        for r in rows
    ]
    resp = jsonify({"files": items})
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/api/files", methods=["POST"])
def api_files_upload():
    expiry_key = request.form.get("expiry", "1d")
    delta = EXPIRY_OPTIONS.get(expiry_key, timedelta(days=1))

    uploads = request.files.getlist("file")
    if not uploads:
        return jsonify({"error": "no file"}), 400

    saved = []
    for upload in uploads:
        if not upload or not upload.filename:
            continue
        name = sanitize_filename(upload.filename)
        fid = generate_id(table="files")
        dest = os.path.join(UPLOAD_DIR, fid)
        upload.save(dest)
        size = os.path.getsize(dest)
        if size > MAX_FILE_SIZE:
            os.remove(dest)
            return jsonify({"error": "too large", "name": name}), 413

        now = datetime.utcnow()
        expires_at = (now + delta).isoformat() if delta else None
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO files (id, name, size, mime, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (fid, name, size, upload.mimetype or None, now.isoformat(), expires_at),
            )
        saved.append(
            {
                "id": fid,
                "name": name,
                "size": size,
                "size_human": human_size(size),
                "url": url_for("download_file", file_id=fid, _external=False),
                "expires_at": expires_at,
            }
        )

    if not saved:
        return jsonify({"error": "no file"}), 400
    return jsonify({"files": saved})


@app.route("/f/<file_id>", methods=["GET"])
def download_file(file_id):
    purge_expired()
    with get_db() as conn:
        row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    if not row:
        abort(404)
    path = os.path.join(UPLOAD_DIR, row["id"])
    if not os.path.exists(path):
        abort(404)
    return send_file(
        path,
        mimetype=row["mime"] or "application/octet-stream",
        as_attachment=True,
        download_name=row["name"],
    )


@app.route("/api/files/<file_id>", methods=["DELETE", "POST"])
def delete_file(file_id):
    if request.method == "POST" and request.form.get("_method", "").upper() != "DELETE":
        abort(405)
    with get_db() as conn:
        row = conn.execute("SELECT id FROM files WHERE id = ?", (file_id,)).fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404
        conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
    try:
        os.remove(os.path.join(UPLOAD_DIR, file_id))
    except FileNotFoundError:
        pass
    return jsonify({"ok": True})


@app.errorhandler(404)
def not_found(_):
    return render_template("error.html", code=404, message="Not found or expired."), 404


@app.errorhandler(413)
def too_large(_):
    return render_template("error.html", code=413, message="Upload too large."), 413


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=False)
