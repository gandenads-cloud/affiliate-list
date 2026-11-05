#!/usr/bin/env bash
# Expose AFS portal lewat Cloudflare Tunnel, digerbangi Cloudflare Access (login Google).
# Pakai: ./setup-tunnel.sh afs.domainmu.com
# ponytail: tunnel jalan sebagai service systemd. Kalau nanti butuh multi-hostname
# atau staging, pindah ke config file ingress rules.
set -euo pipefail

HOSTNAME_ARG="${1:-}"
[ -n "$HOSTNAME_ARG" ] || { echo "Pakai: $0 afs.domainmu.com"; exit 1; }
TUNNEL=afs

command -v cloudflared >/dev/null || { echo "ERROR: cloudflared belum terpasang. Jalankan: sudo pacman -S cloudflared"; exit 1; }

# 1. Login (buka browser, pilih zone domainmu)
[ -f ~/.cloudflared/cert.pem ] || cloudflared tunnel login

# 2. Bikin tunnel kalau belum ada
cloudflared tunnel list 2>/dev/null | grep -qw "$TUNNEL" || cloudflared tunnel create "$TUNNEL"

# 3. Route DNS ke tunnel
cloudflared tunnel route dns "$TUNNEL" "$HOSTNAME_ARG" 2>&1 | tail -1 || true

# 4. Config: hostname -> app lokal
mkdir -p ~/.cloudflared
cat > ~/.cloudflared/config.yml <<CFG
tunnel: $TUNNEL
credentials-file: $HOME/.cloudflared/$(cloudflared tunnel list --output json | python3 -c "
import json,sys
for t in json.load(sys.stdin):
    if t['name']=='$TUNNEL': print(t['id']); break
").json

ingress:
  - hostname: $HOSTNAME_ARG
    service: http://localhost:8000
  - service: http_status:404
CFG

echo
echo "Config: ~/.cloudflared/config.yml"
echo "Test jalan di foreground:  cloudflared tunnel run $TUNNEL"
echo "Jadikan service:           sudo cloudflared service install && sudo systemctl enable --now cloudflared"
echo
echo "PENTING — belum ada login sampai kamu bikin Access policy:"
echo "  1. one.dash.cloudflare.com -> Access -> Applications -> Add -> Self-hosted"
echo "  2. Domain: $HOSTNAME_ARG"
echo "  3. Policy: Action=Allow, Include -> Emails  (isi email tim) atau Emails ending in @domainmu.com"
echo "  4. Login methods: aktifkan Google (Settings -> Authentication -> Login methods -> Add -> Google)"
echo "Tanpa langkah ini, $HOSTNAME_ARG TERBUKA ke publik."
