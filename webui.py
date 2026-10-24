"""
RESTARTION web — dark metal chat UI. run: python webui.py  (port 7860)
BOSS SPEC v2/v3: user GAK BISA kirim gambar. restartion yang punya galeri.
+ thinking indicator ASLI (thought for Xs) + secret deepthink (Ctrl+Alt+M).
"""
import re
import uuid
from flask import Flask, request, jsonify, render_template, send_from_directory, abort

from restartion.engine import Engine, ASSETS, GALLERY, ANGER_IMG, RESPECT_GIF

app = Flask(__name__)
ENG = None
SESSIONS = {}  # sid -> {"history": [(role, text)], "turns": int}

def eng():
    global ENG
    if ENG is None:
        ENG = Engine()
    return ENG

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/img/<path:fname>")
def img(fname):
    # cuma galeri si ai yang boleh dilayani — user gak punya akses upload apa pun
    if fname not in GALLERY and fname != ANGER_IMG:  # GALLERY udah termasuk respect gif
        abort(404)
    return send_from_directory(ASSETS, fname)

@app.route("/api/send", methods=["POST"])
def send():
    sid = request.form.get("sid") or request.cookies.get("sid") or str(uuid.uuid4())[:8]
    s = SESSIONS.setdefault(sid, {"history": [], "turns": 0})
    text = (request.form.get("text") or "").strip()
    if "image" in request.files and request.files["image"].filename:
        return jsonify({"error": "nope. user gak bisa kirim gambar. galeri itu MILIK gue 😌"}), 400
    if not text:
        return jsonify({"error": "empty"}), 400
    deep = (request.form.get("deepthink") or "").lower() in ("1", "true", "yes", "on")
    s["history"].append(("user", text))
    reply = eng().reply(text, s["history"], convo_id=sid, deepthink=deep)
    s["history"].append(("bot", reply))
    s["turns"] += 1
    out_imgs = re.findall(r"<img>([^<]+)</img>", reply)
    out_gifs = re.findall(r"<gif>([^<]+)</gif>", reply)
    clean = re.sub(r"\s*<(?:img|gif)>[^<]+</(?:img|gif)>", "", reply).strip()
    resp = jsonify({"sid": sid, "reply": clean, "images": out_imgs, "gifs": out_gifs,
                    "think_secs": round(getattr(ENG, "last_think_secs", 0.0), 2),
                    "deepthink": bool(getattr(ENG, "last_deepthink", False)),
                    "facts": ENG.mem.d["facts"] if ENG else {}})
    resp.set_cookie("sid", sid)
    return resp

@app.route("/api/reset", methods=["POST"])
def reset():
    sid = str(uuid.uuid4())[:8]
    SESSIONS[sid] = {"history": [], "turns": 0}
    resp = jsonify({"ok": True, "sid": sid})
    resp.set_cookie("sid", sid)
    return resp

if __name__ == "__main__":
    print("restartion web on http://localhost:7860")
    app.run(host="0.0.0.0", port=7860, debug=False, threaded=True)
