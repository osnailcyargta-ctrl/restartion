"""
RESTARTION SERVER — docker edition (boss spec v4, port 4006)

1. web + API satu proses: static site/ dilayani langsung, gak ada CORS drama
2. AKUN ASLI: register email+username+password, login, lupa password
   (recovery code 10 menit ke email), session cookie HttpOnly
3. CHAT GATED: belum login akun restartion = GAK BISA chat. titik.
4. memori AI PER-AKUN: tiap akun punya memory.json sendiri di DATA_DIR/memories/
5. thinking trace ASLI -> UI expandable kayak z.ai (klik "thought for Xs")
6. inferensi SERVER-SIDE (torch int8) -> browser gak download 63MB, GAK ADA LAG wasm
7. /api/auth/verify: fondasi SSO — akun restartion buat login ke web web selanjutnya

run lokal : python server.py                      (default port 4006)
run docker: docker compose up --build -d          (port 4006, data di ./docker-data)
"""
import os
import re
import time
import threading

from flask import Flask, request, jsonify, send_from_directory, send_file, abort

import accounts
from accounts import AuthError
from restartion.engine import Engine, ASSETS, GALLERY, ANGER_IMG, Memory

ROOT = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(ROOT, "site")
PORT = int(os.environ.get("PORT", "4006"))
MEM_DIR = os.path.join(accounts.DATA_DIR, "memories")

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024  # 1MB cukup buat chat json

ENG = None
ENG_LOCK = threading.Lock()   # model gak thread-safe; sekali satu orang generate
HIST = {}                     # user_id -> [(role, text)] (dipotong 30 turn terakhir)
RT = {}                       # rate limit sederhana: key -> [window_start, count]


def eng():
    global ENG
    if ENG is None:
        ENG = Engine(threads=int(os.environ.get("TORCH_THREADS", "2")))
    return ENG


def user_memory(user_id):
    os.makedirs(MEM_DIR, exist_ok=True)
    return Memory(path=os.path.join(MEM_DIR, f"user_{user_id}.json"))


def rate_ok(key, limit, window=60.0):
    now = time.time()
    st = RT.setdefault(key, [now, 0])
    if now - st[0] > window:
        st[0], st[1] = now, 0
    st[1] += 1
    return st[1] <= limit


def current_user():
    return accounts.user_for_session(request.cookies.get("rst_session", ""))


@app.after_request
def _mark(resp):
    if request.path.startswith("/api/"):
        resp.headers["X-Restartion-Server"] = "1"   # penanda buat mode-detect frontend
    return resp


# ---------------- static site ----------------
@app.route("/")
def index():
    return send_file(os.path.join(SITE, "index.html"))


@app.route("/<path:fname>")
def static_files(fname):
    full = os.path.normpath(os.path.join(SITE, fname))
    if not full.startswith(SITE) or not os.path.isfile(full):
        abort(404)
    return send_file(full)


@app.route("/img/<path:fname>")
def img(fname):
    # cuma galeri si ai yang boleh dilayani — user gak punya akses upload apa pun
    if fname not in GALLERY and fname != ANGER_IMG:
        abort(404)
    return send_from_directory(ASSETS, fname)


@app.route("/api/health")
def health():
    return jsonify({"ok": True, "model_loaded": bool(ENG), "ts": time.time()})


# ---------------- auth ----------------
def _auth_resp(u):
    resp = jsonify({"ok": True,
                    "user": {"id": u["id"], "username": u["username"], "email": u["email"]}})
    resp.set_cookie("rst_session", accounts.create_session(u["id"]),
                    max_age=60 * 60 * 24 * 30, httponly=True, samesite="Lax")
    return resp


def _body():
    return request.get_json(silent=True) or {}


@app.route("/api/auth/register", methods=["POST"])
def register():
    if not rate_ok("reg:" + (request.remote_addr or "?"), 10):
        return jsonify({"error": "slow down lil bro."}), 429
    d = _body()
    try:
        u = accounts.create_user(d.get("email"), d.get("username"), d.get("password"))
    except AuthError as e:
        return jsonify({"error": e.msg}), e.code
    return _auth_resp(u)


@app.route("/api/auth/login", methods=["POST"])
def login():
    if not rate_ok("log:" + (request.remote_addr or "?"), 15):
        return jsonify({"error": "kelamaan mikir password lu. napas dulu."}), 429
    d = _body()
    try:
        u = accounts.authenticate(d.get("username"), d.get("password"))
    except AuthError as e:
        return jsonify({"error": e.msg}), e.code
    return _auth_resp(u)


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    accounts.revoke_session(request.cookies.get("rst_session", ""))
    resp = jsonify({"ok": True})
    resp.delete_cookie("rst_session")
    return resp


@app.route("/api/auth/me", methods=["GET"])
def me():
    u = current_user()
    if not u:
        return jsonify({"user": None}), 200   # frontend cek header server, bukan 401
    mem = user_memory(u["id"])
    return jsonify({"user": u, "facts": mem.d.get("facts", {})})


@app.route("/api/auth/forgot", methods=["POST"])
def forgot():
    """langkah 1: masukin email/username -> recovery code 10 menit ke email."""
    if not rate_ok("fgt:" + (request.remote_addr or "?"), 5):
        return jsonify({"error": "kakean minta code. tunggu sebentar."}), 429
    d = _body()
    try:
        u, code = accounts.create_recovery_code(d.get("identifier"))
    except AuthError as e:
        return jsonify({"error": e.msg}), e.code
    sent = False
    try:
        sent = accounts.send_recovery_email(u["email"], u["username"], code)
    except Exception as e:  # SMTP down/gagal -> jangan bikin endpoint 500
        print(f"[recovery] SMTP gagal: {e!r}")
        sent = False
    out = {"ok": True, "sent_email": sent, "ttl_minutes": 10,
           "username": u["username"]}
    if not sent:
        # SMTP belum diset (dev/docker tanpa .env): code ditampilin di popup + log server
        out["dev_code"] = code
        out["note"] = ("SMTP belum dikonfigurasi (SMTP_HOST kosong) — recovery code "
                       "muncul di sini sementara. set SMTP_HOST/SMTP_USER/SMTP_PASS/SMTP_FROM "
                       "di .env biar code dikirim ke email beneran.")
        print(f"[recovery] user={u['username']} code={code} (SMTP off)")
    return jsonify(out)


@app.route("/api/auth/reset", methods=["POST"])
def reset():
    """langkah 2: code + password baru."""
    d = _body()
    try:
        u = accounts.verify_recovery_and_reset(
            d.get("identifier"), d.get("code"), d.get("new_password"))
    except AuthError as e:
        return jsonify({"error": e.msg}), e.code
    return _auth_resp(u)   # langsung loginkan biar gak ngetik lagi


@app.route("/api/auth/token", methods=["POST"])
def make_token():
    """buat api token (SSO) dari sesi yang lagi login."""
    u = current_user()
    if not u:
        return jsonify({"error": "login dulu."}), 401
    tok = accounts.create_api_token(u["id"], (_body().get("name") or "sso"))
    return jsonify({"ok": True, "api_token": tok,
                    "note": "simpen baik-baik. ini buat login ke web lain pake akun restartion."})


@app.route("/api/auth/verify", methods=["POST"])
def verify_token():
    """ENDPOINT SSO: web pihak ketiga POST {api_token} -> identitas akun restartion.
    ini fondasi 'dari akun restartion bisa login ke web web selanjutnya'."""
    u = accounts.user_for_api_token(_body().get("api_token"))
    if not u:
        return jsonify({"ok": False, "error": "api_token gak valid."}), 401
    return jsonify({"ok": True, "user": u})


# ---------------- chat (GATED: wajib login) ----------------
@app.route("/api/chat", methods=["POST"])
def chat():
    u = current_user()
    if not u:
        return jsonify({"error": "belum login. akun restartion itu gerbangnya — "
                                 "daftar dulu, gratis, 20 detik."}), 401
    if not rate_ok(f"chat:{u['id']}", 30):
        return jsonify({"error": "spambot detected. tarik napas dulu gng."}), 429
    d = _body()
    text = (d.get("text") or "").strip()[:2000]
    if not text:
        return jsonify({"error": "empty"}), 400
    deep = bool(d.get("deepthink"))
    sid = (d.get("convo_id") or "default")[:40]
    hist = HIST.setdefault(u["id"], [])
    hist.append(("user", text))
    mem = user_memory(u["id"])
    with ENG_LOCK:   # model satu, dipake rame-rame -> antre rapi
        reply = eng().reply(text, hist, convo_id=f"{u['id']}_{sid}",
                            deepthink=deep, mem=mem)
        think_secs = round(getattr(ENG, "last_think_secs", 0.0), 2)
        thinking = list(getattr(ENG, "last_thinking", []))
    hist.append(("bot", reply))
    HIST[u["id"]] = hist[-30:]
    imgs = re.findall(r"<img>([^<]+)</img>", reply)
    gifs = re.findall(r"<gif>([^<]+)</gif>", reply)
    clean = re.sub(r"\s*<(?:img|gif)>[^<]+</(?:img|gif)>", "", reply).strip()
    return jsonify({"reply": clean, "images": imgs, "gifs": gifs,
                    "think_secs": think_secs, "deepthink": deep,
                    "thinking": thinking, "facts": mem.d["facts"]})


@app.route("/api/reset", methods=["POST"])
def reset_convo():
    u = current_user()
    if not u:
        return jsonify({"error": "login dulu."}), 401
    HIST[u["id"]] = []
    return jsonify({"ok": True})


if __name__ == "__main__":
    accounts.init_db()
    print(f"restartion server -> http://0.0.0.0:{PORT}  (data: {accounts.DATA_DIR})")
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
