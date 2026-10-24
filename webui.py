"""
RESTARTION web — dark metal chat UI. run: python webui.py  (port 7860)
"""
import os
import re
import uuid
import time
from flask import Flask, request, jsonify, render_template, send_from_directory

from restartion.engine import Engine, ASSETS

app = Flask(__name__)
ENG = None
SESSIONS = {}  # sid -> {"history": [(role, text)], "images": {fname: path}, "turns": int}

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
    return send_from_directory(ASSETS, fname)

def _save_upload(sid, f):
    updir = os.path.join(ASSETS, "uploads")
    os.makedirs(updir, exist_ok=True)
    fname = f"{sid[:8]}_{f.filename}"
    fname = re.sub(r"[^A-Za-z0-9_.-]", "_", fname)
    f.save(os.path.join(updir, fname))
    return fname

@app.route("/api/send", methods=["POST"])
def send():
    sid = request.form.get("sid") or request.cookies.get("sid") or str(uuid.uuid4())[:8]
    s = SESSIONS.setdefault(sid, {"history": [], "images": {}, "turns": 0})
    text = (request.form.get("text") or "").strip()
    if not text and "image" not in request.files:
        return jsonify({"error": "empty"}), 400
    imgs = []
    if "image" in request.files and request.files["image"].filename:
        fname = _save_upload(sid, request.files["image"])
        s["images"][fname] = os.path.join(ASSETS, "uploads", fname)
        imgs.append(fname)
        text = (text + f" <img>{fname}</img>").strip()
    s["history"].append(("user", text))
    reply = eng().reply(text, s["history"], convo_id=sid, images=s["images"])
    s["history"].append(("bot", reply))
    s["turns"] += 1
    out_imgs = re.findall(r"<img>([^<]+)</img>", reply)
    clean = re.sub(r"\s*<img>[^<]+</img>", "", reply).strip()
    resp = jsonify({"sid": sid, "reply": clean, "images": out_imgs,
                    "facts": ENG.mem.d["facts"] if ENG else {}})
    resp.set_cookie("sid", sid)
    return resp

@app.route("/api/reset", methods=["POST"])
def reset():
    sid = str(uuid.uuid4())[:8]
    SESSIONS[sid] = {"history": [], "images": {}, "turns": 0}
    resp = jsonify({"ok": True, "sid": sid})
    resp.set_cookie("sid", sid)
    return resp

if __name__ == "__main__":
    print("restartion web on http://localhost:7860")
    app.run(host="0.0.0.0", port=7860, debug=False, threaded=True)
