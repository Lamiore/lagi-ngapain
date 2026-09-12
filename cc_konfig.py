"""Konfigurasi cc-presence.

Menyimpan Application ID Discord dan tingkat privasi. Berkasnya di
``$XDG_CONFIG_HOME/cc-presence/konfig.json`` (bawaan ``~/.config``).

Tingkat privasi (``mode``) sengaja bawaannya kasar: Rich Presence terbaca
oleh seluruh daftar teman, jadi jalur berkas dan isi perintah tidak pernah
ditampilkan kecuali diminta eksplisit.

* ``minimal`` -- tidak ada nama proyek sama sekali.
* ``normal``  -- nama folder proyek saja (bawaan).
* ``detail``  -- tambah nama berkas yang disunting / perintah yang dijalankan.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

MODE_VALID = ("minimal", "normal", "detail")

BAWAAN: dict = {
    # Application ID dari https://discord.com/developers/applications
    # Nama aplikasinya jadi baris paling atas di presence, jadi namai
    # aplikasinya "Claude Code".
    "client_id": "",
    "mode": "normal",
    # Proyek yang namanya tidak boleh tampil walau mode >= normal.
    # Dicocokkan ke nama folder, tidak peka huruf besar-kecil.
    "proyek_privat": [],
    # Discord membatasi laju SET_ACTIVITY (~5 per 20 detik). Nilai ini
    # jarak minimum antar penerbitan, bukan jarak polling.
    "jeda_publish": 15,
    # Sesi yang tidak mengirim kabar selama ini dianggap mati. Menjaga
    # presence tidak nyangkut kalau terminal ditutup paksa (SessionEnd
    # tidak sempat jalan).
    "ttl_sesi": 900,
    "tampilkan_timer": True,
    # Tampilkan lagu yang sedang diputar saat tidak ada yang dikerjakan.
    "musik": True,
    # Awalan nama pemutar yang tidak boleh dibaca sama sekali, mis.
    # ["brave", "firefox"] untuk menutup judul video dari browser.
    "abaikan_pemutar": [],
    # Timpaan label kegiatan, mis. {"Bash": "Ngetik perintah", "idle": "Rehat"}.
    # Kunci yang tidak disebut memakai bawaan di cc_state.LABEL_BAWAAN.
    "label": {},
}


def jalur_konfig() -> Path:
    dasar = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(dasar) / "cc-presence" / "konfig.json"


def muat(jalur: Path | None = None) -> dict:
    """Baca konfigurasi, lengkapi kunci yang hilang dengan bawaan."""
    jalur = jalur or jalur_konfig()
    cfg = dict(BAWAAN)
    try:
        isi = json.loads(jalur.read_text(encoding="utf-8"))
        if isinstance(isi, dict):
            cfg.update({k: v for k, v in isi.items() if k in BAWAAN})
    except (OSError, ValueError):
        pass

    if cfg["mode"] not in MODE_VALID:
        cfg["mode"] = BAWAAN["mode"]
    if not isinstance(cfg["proyek_privat"], list):
        cfg["proyek_privat"] = []
    if not isinstance(cfg["abaikan_pemutar"], list):
        cfg["abaikan_pemutar"] = []
    if not isinstance(cfg["label"], dict):
        cfg["label"] = {}
    else:
        # Nilai non-teks akan meledak saat dirakit; buang di sini selagi murah.
        cfg["label"] = {str(k): str(v) for k, v in cfg["label"].items() if isinstance(v, str)}
    # Jeda di bawah 15 detik menabrak batas laju Discord.
    cfg["jeda_publish"] = max(15, int(cfg["jeda_publish"] or 15))
    cfg["ttl_sesi"] = max(60, int(cfg["ttl_sesi"] or 900))
    cfg["client_id"] = str(cfg["client_id"] or "").strip()
    return cfg


def simpan(cfg: dict, jalur: Path | None = None) -> Path:
    jalur = jalur or jalur_konfig()
    jalur.parent.mkdir(parents=True, exist_ok=True)
    sementara = jalur.with_suffix(".tmp")
    sementara.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    sementara.replace(jalur)
    return jalur
