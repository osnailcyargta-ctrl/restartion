#!/usr/bin/env python3
"""Simulasi docker build context: jalanin aturan .dockerignore, itung total bytes + kontributor terbesar."""
import os, sys
from pathlib import Path
from fnmatch import fnmatch

ROOT = Path(__file__).resolve().parent.parent

def parse_rules(path):
    rules = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rules.append(line)
    return rules

def ignored(rel: str, rules) -> bool:
    """rel pakai '/' separator. cek pattern sederhana ala dockerignore (subset yang kepake)."""
    parts = rel.split("/")
    for i in range(len(parts)):
        sub = "/".join(parts[: i + 1])
        base = parts[i]
        for r in rules:
            pat = r.rstrip("/")
            if fnmatch(sub, pat) or fnmatch(base, pat):
                return True
    return False

def main():
    rules = parse_rules(ROOT / ".dockerignore")
    total = 0
    items = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        rel_dir = os.path.relpath(dirpath, ROOT)
        if rel_dir != "." and ignored(rel_dir, rules):
            dirnames[:] = []
            continue
        # prune direktori yang di-ignore biar gak masuk
        keep = []
        for d in dirnames:
            rd = os.path.normpath(os.path.join(rel_dir, d)) if rel_dir != "." else d
            if not ignored(rd, rules):
                keep.append(d)
        dirnames[:] = keep
        for f in filenames:
            rel = os.path.normpath(os.path.join(rel_dir, f)) if rel_dir != "." else f
            if ignored(rel, rules):
                continue
            p = Path(dirpath) / f
            try:
                sz = p.stat().st_size
            except OSError:
                continue
            total += sz
            items.append((sz, rel))
    items.sort(reverse=True)
    print(f"TOTAL CONTEXT: {total/1048576:.1f} MB ({total} bytes)")
    print("--- TOP 12 ---")
    for sz, rel in items[:12]:
        print(f"{sz/1048576:8.2f} MB  {rel}")
    print(f"--- file count: {len(items)}")

if __name__ == "__main__":
    main()
