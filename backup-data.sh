#!/usr/bin/env bash
# Backup data AFS (db + csv + xlsx) ke repo PRIVATE gandenads-cloud/afs-data.
# ponytail: snapshot penuh tiap commit; kalau repo mulai gendut (>500M),
# pindah ke git-lfs atau backup non-git (restic/rclone).
set -euo pipefail

SRC=/home/gan/Projects/AFS
DST=/home/gan/Projects/afs-data

[ -d "$DST/.git" ] || { echo "ERROR: $DST bukan git repo"; exit 1; }

sqlite3 "$SRC/database/afs.db" "PRAGMA wal_checkpoint(TRUNCATE);" >/dev/null
cp "$SRC/database/afs.db" "$DST/"
cp "$SRC"/*.csv "$DST/"
cp "$SRC"/files/*.xlsx "$DST/" 2>/dev/null || true

cd "$DST"
git add -A
git diff --cached --quiet && { echo "Tidak ada perubahan data."; exit 0; }
git commit -qm "Backup data $(date +%Y-%m-%d\ %H:%M)"
git push -q origin main
echo "Pushed: $(git log -1 --oneline)"
