#!/usr/bin/env bash
# push restartion — 3 batch commit terlihat di history. pakai:
#   bash scripts/push_all.sh ghp_XXXXXXXX
set -e
TOK="${1:?pakai: bash scripts/push_all.sh ghp_...}"
cd /home/z/my-project/restartion

# 1. user EXAK dari API (jangan diketik manual — huruf I/l/O gampang ketukar)
LOGIN=$(curl -s -H "Authorization: token ${TOK}" https://api.github.com/user \
        | python3 -c "import json,sys; print(json.load(sys.stdin)['login'])")
echo "login: ${LOGIN}"

# 2. repo: pakai yang ada, atau bikin
CODE=$(curl -s -o /tmp/repo.json -w "%{http_code}" -H "Authorization: token ${TOK}" \
       "https://api.github.com/repos/${LOGIN}/restartion")
if [ "$CODE" != "200" ]; then
  curl -s -X POST -H "Authorization: token ${TOK}" -H "Accept: application/vnd.github+json" \
    https://api.github.com/user/repos \
    -d '{"name":"restartion","description":"57.44M param transformer trained FROM SCRATCH to roast you. no API. real memory. dark metal. twin / gng / stfu / sybau.","private":false}' > /dev/null
  echo "repo created"
fi

# 3. push semua commit (batch1 -> batch2 -> batch3 urut di history)
git remote remove origin 2>/dev/null || true
git remote add origin "https://${LOGIN}:${TOK}@github.com/${LOGIN}/restartion.git"
git push -u origin main --force
git tag -f batch1 HEAD~2 2>/dev/null || true
git tag -f batch2 HEAD~1 2>/dev/null || true
git tag -f batch3 HEAD 2>/dev/null || true
git push origin --tags --force
echo "PUSH DONE -> https://github.com/${LOGIN}/restartion"
