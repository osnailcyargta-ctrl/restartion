#!/usr/bin/env bash
# push_github.sh — push aman tanpa nyimpan token: token dibaca dari .github_token, dipakai inline, gak masuk .git/config
# usage: bash scripts/push_github.sh [branch]
set -e
cd "$(dirname "$0")/.."   # root repo (script ada di restartion/scripts/)
TOKEN=$(tr -d '\n\r ' < .github_token)
BRANCH="${1:-main}"
LOGIN=$(curl -s -H "Authorization: token ${TOKEN}" https://api.github.com/user \
        | python3 -c "import json,sys; print(json.load(sys.stdin)['login'])")
git push "https://${LOGIN}:${TOKEN}@github.com/${LOGIN}/restartion.git" "${BRANCH}"
echo "PUSH OK -> https://github.com/${LOGIN}/restartion (${BRANCH})"
