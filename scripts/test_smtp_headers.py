#!/usr/bin/env python3
"""Test from_header() + send_recovery_email PAKAI FAKE SMTP (gak ngirim beneran).
Verifikasi: header From = 'restartion <email>', envelope MAIL FROM = alamat telanjang."""
import os, sys

os.environ.update({
    "SMTP_HOST": "smtp.gmail.com", "SMTP_PORT": "587",
    "SMTP_USER": "osnailcyargta@gmail.com", "SMTP_PASS": "dummykeydummykey",
    "SMTP_FROM": "osnailcyargta@gmail.com", "SMTP_TLS": "none",
})
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import accounts
import smtplib

CAP = {}

class FakeSMTP:
    def __init__(self, host, port, timeout=None): self.host, self.port = host, port
    def starttls(self): return self
    def login(self, u, p): CAP["login"] = u
    def sendmail(self, frm, to, raw): CAP["envelope_from"], CAP["to"], CAP["raw"] = frm, to, raw
    def quit(self): pass

smtplib.SMTP = FakeSMTP
smtplib.SMTP_SSL = FakeSMTP

ok = True
# 1) header + envelope terpisah
hdr, env = accounts.from_header()
print("header From :", hdr)
print("envelope    :", env)
if hdr != "restartion <osnailcyargta@gmail.com>": ok = False; print("❌ header salah")
if env != "osnailcyargta@gmail.com": ok = False; print("❌ envelope harus telanjang")

# 2) user isi SMTP_FROM kotor ("Nama <email>") -> envelope tetep telanjang
accounts.SMTP_ENV["SMTP_FROM"] = "Nama Apa Aja <osnailcyargta@gmail.com>"
hdr2, env2 = accounts.from_header()
print("header kotor:", hdr2, "| envelope:", env2)
if env2 != "osnailcyargta@gmail.com": ok = False; print("❌ parseaddr gagal")

# 3) full send path
accounts.SMTP_ENV["SMTP_FROM"] = "osnailcyargta@gmail.com"
r = accounts.send_recovery_email("boss@gmail.com", "bos", "12345678")
raw = CAP["raw"]
from_line = [l for l in raw.split("\n") if l.startswith("From:")][0]
print("send ok:", r, "| login sbg:", CAP["login"])
print("raw From:", from_line)
if not r: ok = False; print("❌ send gagal")
if CAP["envelope_from"] != "osnailcyargta@gmail.com": ok = False; print("❌ envelope send salah")
if "restartion" not in from_line or "osnailcyargta@gmail.com" not in from_line: ok = False; print("❌ From header salah")

print("\n" + ("✅ SEMUA PASS" if ok else "❌ ADA YANG GAGAL"))
sys.exit(0 if ok else 1)
