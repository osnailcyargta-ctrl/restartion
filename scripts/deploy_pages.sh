#!/usr/bin/env bash
# deploy_pages.sh — orphan branch gh-pages dari isi site/ + enable GitHub Pages via API
# token dibaca dari FILE .github_token (jangan pernah diketik manual)
set -e
TOKEN=$(tr -d '\n\r ' < /home/z/my-project/restartion/.github_token)
REPO=/home/z/my-project/restartion
LOGIN=$(curl -s -H "Authorization: token ${TOKEN}" https://api.github.com/user | python3 -c "import json,sys; print(json.load(sys.stdin)['login'])")
echo "login: ${LOGIN}"
cd "${REPO}"

# --- 1. snapshot isi site/ ke staging ---
rm -rf /tmp/ghpages && mkdir -p /tmp/ghpages
cp -r site/. /tmp/ghpages/

# --- 2. branch orphan gh-pages: worktree = cuma isi site/ ---
git branch -D gh-pages 2>/dev/null || true
git checkout --orphan gh-pages -q
git rm -rf --cached . > /dev/null 2>&1 || true
# hapus SEMUA file worktree kecuali file token (SAKRAL) dan staging site
find . -mindepth 1 -maxdepth 1 ! -name '.git' ! -name '.github_token' ! -name '.github_token.path' -exec rm -rf {} +
cp -r /tmp/ghpages/. .
git add -A
# GUARD 1 (insiden 2x!): orphan branch GAK PUNYA .gitignore -> git add -A nyeret .github_token.
# Keluarin dari index SEBELUM commit, lalu hard-abort kalau masih ada sisa.
git rm --cached --ignore-unmatch -q .github_token .github_token.path 2>/dev/null || true
if git diff --cached --name-only | grep -q '^\.github_token'; then
  echo "FATAL: .github_token masih di index — ABORT, push dilarang"; exit 1
fi
git commit -q -m "restartion on github.io — 57.44M param from-scratch transformer running 100% client-side (ONNX int8 63MB + ByteLevel BPE in JS + real memory via localStorage + AI-owned gallery). no server. no API. no wrapper."
# GUARD 2: commit udah jadi — cek lagi, kalau token nyangkut: abort (push protection bakal nolak, tapi jangan sampe nyoba)
if git show --stat HEAD | grep -q '\.github_token'; then
  echo "FATAL: .github_token masuk commit — ABORT"; exit 1
fi
git push -q "https://${LOGIN}:${TOKEN}@github.com/${LOGIN}/restartion.git" gh-pages --force
echo "gh-pages pushed"

# --- 3. balik ke main, bersihin sisa file gh-pages, restore folder site/ ---
git checkout main -q
git clean -fdx -e .github_token -e .github_token.path > /dev/null 2>&1 || true
git status --short | head -5 || true
mkdir -p site
cp -r /tmp/ghpages/. site/   # '/.' = copy ISI, bukan bikin site/ghpages/ nested (bug lama)
echo "main restored + site/ kept"

# --- 4. enable Pages (source: gh-pages / root) ---
CODE=$(curl -s -o /tmp/pages.json -w "%{http_code}" -X POST \
  -H "Authorization: token ${TOKEN}" -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/${LOGIN}/restartion/pages" \
  -d '{"source":{"branch":"gh-pages","path":"/"}}')
if [ "$CODE" = "409" ]; then
  echo "pages already enabled"
elif [ "$CODE" != "201" ]; then
  echo "pages enable HTTP ${CODE}:"; head -5 /tmp/pages.json
  exit 1
fi
echo "SITE -> https://${LOGIN}.github.io/restartion/"
