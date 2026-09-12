#!/usr/bin/env bash
# Pemasang cc-presence: hook Claude Code + service systemd pengguna.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="$DIR/hooks/cc-presence-hook.sh"
UNIT="cc-presence.service"

say() { printf '  %s\n' "$*"; }

command -v python3 >/dev/null || { echo "python3 tidak ada"; exit 1; }
chmod +x "$HOOK" "$DIR/cc_daemon.py"

echo "==> Konfigurasi"
CID="${1:-}"
if [ -z "$CID" ]; then
  CID="$(python3 -c "import sys; sys.path.insert(0,'$DIR'); import cc_konfig; print(cc_konfig.muat()['client_id'])")"
fi
if [ -z "$CID" ]; then
  echo
  say "Application ID Discord belum ada. Bikin dulu:"
  say "  1. buka https://discord.com/developers/applications"
  say "  2. New Application, namai persis: Claude Code"
  say "     (nama aplikasi ini jadi baris paling atas di presence)"
  say "  3. salin Application ID di halaman General Information"
  echo
  read -rp "  Tempel Application ID di sini: " CID
fi
[ -n "$CID" ] || { echo "Application ID wajib diisi."; exit 1; }

python3 - "$DIR" "$CID" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
import cc_konfig
cfg = cc_konfig.muat()
cfg["client_id"] = sys.argv[2].strip()
print("  konfig:", cc_konfig.simpan(cfg))
print("  mode privasi:", cfg["mode"])
PY

echo "==> Hook Claude Code"
python3 - "$DIR" "$HOOK" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
import cc_pasang
ok, pesan = cc_pasang.pasang(sys.argv[2])
print("  " + pesan)
print("  settings:", cc_pasang.jalur_settings())
sys.exit(0 if ok else 1)
PY

echo "==> Service systemd"
mkdir -p ~/.config/systemd/user
cp "$DIR/systemd/$UNIT" ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now "$UNIT"
say "$(systemctl --user is-active "$UNIT") -- log: journalctl --user -u $UNIT -f"

echo
echo "Selesai. Presence muncul dalam ~15 detik."
say "Sesi Claude Code yang sedang jalan ikut terpantau -- settings.json"
say "dibaca ulang saat itu juga, jadi tidak perlu dibuka ulang."
say "Ubah privasi: $DIR/cc_daemon.py --status, sunting konfignya, lalu"
say "  systemctl --user restart $UNIT"
