#!/usr/bin/env bash
# Pencabut cc-presence. Hook alat lain di settings.json tidak disentuh.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT="cc-presence.service"

systemctl --user disable --now "$UNIT" 2>/dev/null || true
rm -f ~/.config/systemd/user/"$UNIT"
systemctl --user daemon-reload

python3 - "$DIR" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
import cc_pasang
print("  " + cc_pasang.copot()[1])
PY
echo "Dicopot. Konfig di ~/.config/cc-presence/ sengaja dibiarkan."
