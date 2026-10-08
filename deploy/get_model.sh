#!/bin/sh
# ============================================================
# deploy/get_model.sh — download the trained model so a fresh clone can run TriageIQ:
#     sh deploy/get_model.sh
# The model files are too large for git (266 MB each), so they live in the GitHub Release "model-v3".
# This fetches the 9 files of the serving bundle (~590 MB) into training/outputs/serving_v3/ and checks each one
# against deploy/model_bundle.sha256 — a fingerprint: change one byte and it no longer matches. The two 266 MB files
# are stored as ~45 MB parts (deploy/model_bundle.parts) so one dropped connection costs one part, not the whole file;
# they're joined here and the JOINED file is checked. Files already present and correct are skipped.
# It also creates deploy/.env with a random database password if there is none.
# Needs: curl, and sha256sum (Linux) or shasum (Mac).
# ============================================================
set -e
cd "$(dirname "$0")/.."                                 # the repo root
TAG="${TAG:-model-v3}"
URL="https://github.com/Bajaj30/TriageIQ/releases/download/$TAG"
OUT=training/outputs/serving_v3
mkdir -p "$OUT"
if command -v sha256sum >/dev/null 2>&1; then SHA="sha256sum"; else SHA="shasum -a 256"; fi
matches() { [ -f "$OUT/$2" ] && [ "$($SHA "$OUT/$2" | cut -d' ' -f1)" = "$1" ]; }

echo "== model bundle -> $OUT"
while read -r sum name; do
    [ -n "$name" ] || continue
    if matches "$sum" "$name"; then echo "   ok        $name"; continue; fi
    parts=$(awk -v f="$name" '$1 == f { print $2 }' deploy/model_bundle.parts)
    if [ -n "$parts" ]; then                           # stored in parts: download each, join in order
        : > "$OUT/$name.part"
        for i in $(seq 1 "$parts"); do
            p=$(printf '%s.part%02d' "$name" "$i")
            echo "   download  $p  ($i of $parts)"
            curl -fL --retry 5 --retry-all-errors --progress-bar -o "$OUT/$p" "$URL/$p" < /dev/null
            cat "$OUT/$p" >> "$OUT/$name.part" && rm "$OUT/$p"   # own file first: a retried part restarts cleanly
        done
    else
        echo "   download  $name"
        curl -fL --retry 5 --retry-all-errors --progress-bar -o "$OUT/$name.part" "$URL/$name" < /dev/null
    fi
    mv "$OUT/$name.part" "$OUT/$name"
    matches "$sum" "$name" || { echo "FAILED: $name doesn't match its fingerprint — delete it and run again"; exit 1; }
done < deploy/model_bundle.sha256

if [ ! -f deploy/.env ]; then                          # local database password (git-ignored, not printed)
    PW=$(head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 32)
    printf 'POSTGRES_USER=triageiq\nPOSTGRES_DB=triageiq\nPOSTGRES_PASSWORD=%s\n' "$PW" > deploy/.env
    chmod 600 deploy/.env
    echo "== created deploy/.env (random database password)"
fi

cat <<'NEXT'
== ready. Start it (Docker Desktop running):
   docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.xai.yml up -d --build
   python3 web/dev_server.py          -> http://localhost:3000   (API docs: http://localhost:8000/docs)
   (leave out the docker-compose.xai.yml part to run without the "Why this score?" explanations)
NEXT
