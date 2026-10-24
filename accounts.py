"""
RESTARTION ACCOUNTS — akun asli (boss spec v4):
  - register  : email + username + password
  - login     : username ATAU email + password
  - lupa pass : recovery code 8 digit, valid 10 MENIT, single-use, dikirim ke email
  - api token : fondasi SSO — akun restartion bisa dipakai login ke web web selanjutnya

Storage: SQLite di DATA_DIR/restartion.db (volume docker /data).
Password: pbkdf2:sha256 via werkzeug. Code/token disimpan sebagai SHA-256 hash
bukan plaintext — database bocor pun code/password gak ikut bocor.
"""
import os
import re
import time
import hashlib
import sqlite3
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr, parseaddr

from werkzeug.security import generate_password_hash, check_password_hash

DATA_DIR = os.environ.get(
    "DATA_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data_runtime"))
DB_PATH = os.path.join(DATA_DIR, "restartion.db")

SESSION_TTL = 60 * 60 * 24 * 30   # 30 hari
RECOVERY_TTL = 60 * 10            # 10 MENIT (boss spec, persis)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE NOT NULL,
  username TEXT UNIQUE NOT NULL,
  pw_hash TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions(
  token_hash TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  expires_at REAL NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS recovery_codes(
  code_hash TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  expires_at REAL NOT NULL,
  used INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS api_tokens(
  token_hash TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  name TEXT DEFAULT 'sso',
  created_at REAL NOT NULL,
  last_used REAL
);
"""

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
USER_RE = re.compile(r"^[a-zA-Z0-9_.]{3,20}$")


class AuthError(Exception):
    def __init__(self, msg, code=400):
        super().__init__(msg)
        self.msg = msg
        self.code = code


def _con():
    os.makedirs(DATA_DIR, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=15)
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init_db():
    with _con() as c:
        c.executescript(SCHEMA)


def _h(t):
    return hashlib.sha256((t or "").strip().encode()).hexdigest()


# ---------------- users ----------------
def create_user(email, username, password):
    email = (email or "").strip().lower()
    username = (username or "").strip()
    if not EMAIL_RE.match(email):
        raise AuthError("email gak valid banh. format: nama@domain.tld")
    if not USER_RE.match(username):
        raise AuthError("username 3-20 char: huruf, angka, underscore, titik aja.")
    if len(password or "") < 6:
        raise AuthError("password minimal 6 char. serius deh.")
    with _con() as c:
        try:
            c.execute("INSERT INTO users(email, username, pw_hash, created_at) VALUES(?,?,?,?)",
                      (email, username, generate_password_hash(password), time.time()))
        except sqlite3.IntegrityError:
            raise AuthError("email atau username udah dipake akun lain. ganti banh.", 409)
    return get_user_by_login(username)


def get_user_by_login(login):
    """login bisa username ATAU email."""
    q = (login or "").strip().lower()
    if not q:
        return None
    with _con() as c:
        row = c.execute("SELECT id, email, username, pw_hash FROM users "
                        "WHERE username=? OR email=?", (q, q)).fetchone()
    return {"id": row[0], "email": row[1], "username": row[2], "pw_hash": row[3]} if row else None


def authenticate(login, password):
    u = get_user_by_login(login)
    if not u or not check_password_hash(u["pw_hash"], password or ""):
        raise AuthError("username/password salah. dasar lil bro.", 401)
    return u


# ---------------- session cookie ----------------
def create_session(user_id):
    tok = secrets.token_urlsafe(32)
    with _con() as c:
        c.execute("INSERT INTO sessions(token_hash, user_id, expires_at, created_at) VALUES(?,?,?,?)",
                  (_h(tok), user_id, time.time() + SESSION_TTL, time.time()))
    return tok


def user_for_session(tok):
    if not tok:
        return None
    with _con() as c:
        row = c.execute(
            "SELECT u.id, u.email, u.username FROM sessions s "
            "JOIN users u ON u.id = s.user_id "
            "WHERE s.token_hash=? AND s.expires_at > ?", (_h(tok), time.time())).fetchone()
    return {"id": row[0], "email": row[1], "username": row[2]} if row else None


def revoke_session(tok):
    if tok:
        with _con() as c:
            c.execute("DELETE FROM sessions WHERE token_hash=?", (_h(tok),))


# ---------------- recovery code (10 menit, single-use) ----------------
def create_recovery_code(identifier):
    u = get_user_by_login(identifier)
    if not u:
        raise AuthError("akun gak ketemu. cek email/username lu banh.", 404)
    code = f"{secrets.randbelow(10 ** 8):08d}"
    with _con() as c:
        c.execute("UPDATE recovery_codes SET used=1 WHERE user_id=? AND used=0", (u["id"],))
        c.execute("INSERT INTO recovery_codes(code_hash, user_id, expires_at) VALUES(?,?,?)",
                  (_h(code), u["id"], time.time() + RECOVERY_TTL))
    return u, code


def verify_recovery_and_reset(identifier, code, new_password):
    u = get_user_by_login(identifier)
    if not u:
        raise AuthError("akun gak ketemu.", 404)
    if len(new_password or "") < 6:
        raise AuthError("password baru minimal 6 char.")
    with _con() as c:
        rows = c.execute("SELECT code_hash FROM recovery_codes "
                         "WHERE user_id=? AND used=0 AND expires_at > ?",
                         (u["id"], time.time())).fetchall()
    if not any(_h(code) == r[0] for r in rows):
        raise AuthError("code salah / kedaluwarsa (umurnya 10 menit doang). minta code baru.", 400)
    with _con() as c:
        c.execute("UPDATE recovery_codes SET used=1 WHERE user_id=? AND used=0", (u["id"],))
        c.execute("UPDATE users SET pw_hash=? WHERE id=?",
                  (generate_password_hash(new_password), u["id"]))
    return u


# ---------------- api tokens: fondasi SSO antar-web ----------------
def create_api_token(user_id, name="sso"):
    """token format rst_... — web pihak ketiga POST ke /api/auth/verify buat
    ngecek identitas. ini gerbang 'login ke web web selanjutnya' (boss spec)."""
    tok = "rst_" + secrets.token_urlsafe(24)
    with _con() as c:
        c.execute("INSERT INTO api_tokens(token_hash, user_id, name, created_at) VALUES(?,?,?,?)",
                  (_h(tok), user_id, (name or "sso")[:40], time.time()))
    return tok


def user_for_api_token(tok):
    if not tok:
        return None
    with _con() as c:
        row = c.execute(
            "SELECT u.id, u.email, u.username FROM api_tokens t "
            "JOIN users u ON u.id = t.user_id WHERE t.token_hash=?", (_h(tok),)).fetchone()
        if row:
            c.execute("UPDATE api_tokens SET last_used=? WHERE token_hash=?",
                      (time.time(), _h(tok)))
    return {"id": row[0], "email": row[1], "username": row[2]} if row else None


# ---------------- email (SMTP) ----------------
SMTP_ENV = {k: os.environ.get(k, "") for k in
            ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "SMTP_FROM", "SMTP_TLS")}
# gmail app password sering ke-paste masih ada spasinya ("xxxx xxxx xxxx xxxx")
# -> server nolak 535. strip spasi otomatis biar gak ada drama.
SMTP_ENV["SMTP_PASS"] = SMTP_ENV["SMTP_PASS"].replace(" ", "").replace("\t", "")
# nama pengirim yang tampil di inbox penerima (default: restartion).
# alamat asli tetep SMTP_FROM — yang berubah cuma display name "From:".
SMTP_FROM_NAME = (os.environ.get("SMTP_FROM_NAME") or "restartion").strip("\" ")


def smtp_configured():
    return bool(SMTP_ENV["SMTP_HOST"] and SMTP_ENV["SMTP_FROM"])


def from_header():
    """return (header_from, envelope_from).
    header  -> 'restartion <boss@example.com>' (nama tampil di inbox)
    envelope-> 'boss@example.com' (HARUS alamat telanjang buat MAIL FROM;
               kalo kena display name gmail langsung nolak 555)."""
    bare = parseaddr(SMTP_ENV["SMTP_FROM"])[1] or SMTP_ENV["SMTP_FROM"].strip()
    return formataddr((SMTP_FROM_NAME, bare)), bare


def send_recovery_email(to_email, username, code):
    """kirim recovery code ke email beneran. return True kalau sukses.
    SMTP gak diset -> return False (server fallback: code muncul di response dev + log)."""
    if not smtp_configured():
        return False
    host = SMTP_ENV["SMTP_HOST"]
    port = int(SMTP_ENV["SMTP_PORT"] or 587)
    frm, envelope_from = from_header()
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"restartion recovery code: {code}"
    msg["From"] = frm
    msg["To"] = to_email
    plain = (f"yo {username},\n\nrecovery code lu:\n\n{code}\n\n"
             f"valid 10 MENIT, sekali pakai. jangan dikasih ke siapa pun —\n"
             f"termasuk yang ngaku-ngaku restartion. gue gak pernah minta code.\n\n"
             f"— restartion (58.75M params, gak punya perasaan, tetep ngeemail)")
    html = f"""\
<div style="font-family:'JetBrains Mono',Consolas,monospace;background:#0a0b0d;color:#cfd6e1;
     padding:28px;border:1px solid #232a35;border-radius:10px;max-width:520px">
  <h2 style="letter-spacing:2px;margin:0 0 12px;color:#e8edf4">RESTART<span style="color:#ff4655">ION</span></h2>
  <p style="font-size:13px">yo <b>{username}</b>, ini recovery code lu:</p>
  <div style="font-size:32px;letter-spacing:8px;color:#ff4655;border:1px dashed #232a35;
       padding:14px;text-align:center;border-radius:8px;margin:14px 0">{code}</div>
  <p style="font-size:12px;color:#78828f">valid <b>10 menit</b>, sekali pakai.
     jangan kasih ke siapa pun — termasuk akun yang ngaku-ngaku restartion.</p>
</div>"""
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))
    if SMTP_ENV["SMTP_TLS"] == "ssl":
        s = smtplib.SMTP_SSL(host, port, timeout=20)
    else:
        s = smtplib.SMTP(host, port, timeout=20)
        if (SMTP_ENV["SMTP_TLS"] or "starttls") == "starttls":
            s.starttls()
    try:
        if SMTP_ENV["SMTP_USER"]:
            s.login(SMTP_ENV["SMTP_USER"], SMTP_ENV["SMTP_PASS"] or "")
        s.sendmail(envelope_from, [to_email], msg.as_string())
    finally:
        s.quit()
    return True
