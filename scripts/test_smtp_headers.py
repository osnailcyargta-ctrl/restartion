#!/usr/bin/env python3
"""Test from_header() + send_recovery_email PAKAI FAKE SMTP (gak ngirim beneran).
Verifikasi: header From = 'restartion <email>', envelope MAIL FROM = alamat telanjang."""
import os, sys

os.environ.update({
    "SMTP_HOST": "smtp.gmail.com", "SMTP_PORT": "587",
    "SMTP_USER": "boss@example.com", "SMTP_PASS": "xxxx xxxx xxxx xxxx",
    "SMTP_FROM": "boss@example.com", "SMTP_TLS": "none",
})
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import accounts
import smtplib

CAP = {}

class FakeSMTP:
    def __init__(self, host, port, timeout=None): self.host, self.port = host, port
    def starttls(self): return self
    def login(self, u, p): CAP["login"], CAP["pass"] = u, p
    def sendmail(self, frm, to, raw): CAP["envelope_from"], CAP["to"], CAP["raw"] = frm, to, raw
    def quit(self): pass

smtplib.SMTP = FakeSMTP
smtplib.SMTP_SSL = FakeSMTP

ok = True
# 0) strip spasi app password terjadi pas IMPORT (env di atas udah ada spasi)
assert CAP.get("pass") is None  # belum login, cuma sanity
# 1) header + envelope terpisah
hdr, env = accounts.from_header()
print("header From :", hdr)
print("envelope    :", env)
if hdr != "restartion <boss@example.com>": ok = False; print("❌ header salah")
if env != "boss@example.com": ok = False; print("❌ envelope harus telanjang")

# 2) user isi SMTP_FROM kotor ("Nama <email>") -> envelope tetep telanjang
accounts.SMTP_ENV["SMTP_FROM"] = "Nama Apa Aja <boss@example.com>"
hdr2, env2 = accounts.from_header()
print("header kotor:", hdr2, "| envelope:", env2)
if env2 != "boss@example.com": ok = False; print("❌ parseaddr gagal")

# 3) full send path
accounts.SMTP_ENV["SMTP_FROM"] = "boss@example.com"
r = accounts.send_recovery_email("boss@gmail.com", "bos", "12345678")
raw = CAP["raw"]
from_line = [l for l in raw.split("\n") if l.startswith("From:")][0]
print("send ok:", r, "| login sbg:", CAP["login"], "| pass stripped:", CAP["pass"] == "xxxxxxxxxxxxxxxx")
print("raw From:", from_line)
if not r: ok = False; print("❌ send gagal")
if CAP["envelope_from"] != "boss@example.com": ok = False; print("❌ envelope send salah")
if "restartion" not in from_line or "boss@example.com" not in from_line: ok = False; print("❌ From header salah")

print("\n" + ("✅ SEMUA PASS" if ok else "❌ ADA YANG GAGAL"))
sys.exit(0 if ok else 1)
