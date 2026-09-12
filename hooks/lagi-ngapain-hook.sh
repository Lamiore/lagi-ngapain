#!/usr/bin/env bash
# Hook lagi-ngapain: tulis muatan hook apa adanya ke spool, lalu keluar.
#
# Hook ini jalan di SETIAP tool call, jadi biayanya harus mendekati nol:
# tidak ada interpreter yang dipanggil, tidak ada soket, tidak ada jaringan,
# dan tidak ada penguraian JSON. Daemon yang mengerjakan semuanya.
#
# Kalau daemonnya mati, direktori spool tidak ada dan hook langsung keluar
# tanpa menulis apa pun -- jadi tidak menumpuk sampah saat fiturnya nonaktif.
d="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/lagi-ngapain/ev"
[ -d "$d" ] || exit 0
cat > "$d/${EPOCHREALTIME}-$$.json" 2>/dev/null
exit 0
