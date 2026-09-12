"""Registry sesi Claude Code dan perakitan payload Rich Presence.

Modul ini murni logika: tidak menyentuh soket, berkas, maupun jam sistem
(waktu selalu dioper dari pemanggil). Seluruh aturan privasi, penggabungan
banyak sesi, dan pemetaan nama alat ada di sini supaya bisa diuji tanpa
Discord yang menyala.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# Peristiwa hook yang dipakai. PostToolUse sengaja tidak dipasang: keadaan
# "sedang bekerja" sudah didapat dari PreToolUse dan "selesai" dari Stop,
# sementara muatannya paling besar (berisi seluruh keluaran alat).
PERISTIWA = ("SessionStart", "UserPromptSubmit", "PreToolUse", "Stop", "SessionEnd")

# Keadaan sesi.
IDLE = "idle"
BERPIKIR = "berpikir"
BEKERJA = "bekerja"

# Label bawaan. Semuanya bisa ditimpa lewat kunci "label" di konfig, jadi
# mengubah kata-katanya tidak perlu menyentuh kode. Kunci bernama alat
# dicocokkan persis; empat kunci huruf kecil di bawah ini khusus dan tidak
# akan pernah bentrok dengan nama alat (nama alat selalu CamelCase).
LABEL_BAWAAN = {
    "Bash": "Ngoprek terminal",
    "Read": "Baca kode",
    "Edit": "Ngedit kode",
    "Write": "Nulis kode",
    "NotebookEdit": "Ngedit notebook",
    "Grep": "Nyari-nyari",
    "Glob": "Nyari-nyari",
    "WebSearch": "Googling",
    "WebFetch": "Baca web",
    "Task": "Nyuruh subagen",
    "Agent": "Nyuruh subagen",
    "TodoWrite": "Nyusun rencana",
    "Skill": "Makai skill",
    # -- kunci khusus --
    "mcp": "Makai MCP",          # untuk alat apa pun berawalan mcp__
    "lainnya": "Makai {alat}",   # cadangan; {alat} diganti nama alatnya
    "berpikir": "Mikir",         # sesudah prompt, sebelum alat pertama
    "idle": "Nganggur",          # menunggu perintah berikutnya
    "dengerin": "Lagi dengerin",  # kartu musik, saat tidak ada yang dikerjakan
}

# Batas panjang field Discord.
BATAS_FIELD = 128


def label_alat(nama: str, peta: dict | None = None) -> str:
    peta = {**LABEL_BAWAAN, **(peta or {})}
    if not nama:
        return peta["lainnya"].format(alat="").strip() or peta["idle"]
    if nama in peta:
        return peta[nama]
    if nama.startswith("mcp__"):
        # Nama server MCP sengaja tidak ikut ditampilkan -- sering memuat
        # nama perusahaan atau proyek internal.
        return peta["mcp"]
    return peta["lainnya"].format(alat=nama)


def _potong(teks: str, batas: int = BATAS_FIELD) -> str:
    teks = " ".join(teks.split())
    return teks if len(teks) <= batas else teks[: batas - 1] + "…"


@dataclass
class Sesi:
    id: str
    cwd: str = ""
    keadaan: str = IDLE
    alat: str = ""
    rincian_alat: str = ""
    mulai: float = 0.0
    terakhir: float = 0.0
    # Urutan kedatangan peristiwa. Dipakai memilih sesi mana yang
    # ditampilkan saat ada beberapa sesi -- yang paling baru bergerak menang.
    urutan: int = 0

    @property
    def proyek(self) -> str:
        return os.path.basename(self.cwd.rstrip("/")) if self.cwd else ""


@dataclass
class Registry:
    """Kumpulan sesi Claude Code yang sedang hidup."""

    ttl: float = 900.0
    mode: str = "normal"
    proyek_privat: tuple = ()
    tampilkan_timer: bool = True
    label: dict = field(default_factory=dict)
    sesi: dict = field(default_factory=dict)
    _hitung: int = 0

    def __post_init__(self) -> None:
        self.proyek_privat = tuple(str(p).strip().lower() for p in self.proyek_privat if str(p).strip())

    # -- pemasukan peristiwa ------------------------------------------------

    def terapkan(self, ev: dict, sekarang: float) -> bool:
        """Masukkan satu muatan hook. Balikan True kalau registry berubah."""
        sid = ev.get("session_id")
        peristiwa = ev.get("hook_event_name")
        if not sid or peristiwa not in PERISTIWA:
            return False

        if peristiwa == "SessionEnd":
            return self.sesi.pop(sid, None) is not None

        s = self.sesi.get(sid)
        if s is None:
            s = Sesi(id=sid, mulai=sekarang)
            self.sesi[sid] = s

        self._hitung += 1
        s.urutan = self._hitung
        s.terakhir = sekarang
        if ev.get("cwd"):
            s.cwd = ev["cwd"]

        if peristiwa == "SessionStart":
            s.keadaan = IDLE
            s.alat = s.rincian_alat = ""
        elif peristiwa == "UserPromptSubmit":
            s.keadaan = BERPIKIR
            s.alat = s.rincian_alat = ""
        elif peristiwa == "PreToolUse":
            s.keadaan = BEKERJA
            s.alat = ev.get("tool_name") or ""
            s.rincian_alat = _rincian(s.alat, ev.get("tool_input"))
        elif peristiwa == "Stop":
            s.keadaan = IDLE
            s.alat = s.rincian_alat = ""
        return True

    def bersihkan(self, sekarang: float) -> bool:
        """Buang sesi yang lewat TTL. Balikan True kalau ada yang dibuang."""
        mati = [k for k, s in self.sesi.items() if sekarang - s.terakhir > self.ttl]
        for k in mati:
            del self.sesi[k]
        return bool(mati)

    # -- perakitan presence -------------------------------------------------

    def _nama_proyek(self, s: Sesi) -> str:
        nama = s.proyek
        if not nama:
            return ""
        if nama.lower() in self.proyek_privat:
            return "proyek privat"
        return nama

    def _kartu_musik(self, musik: dict, peta: dict) -> dict:
        """Presence versi 'lagi dengerin', dipakai saat tidak ada yang dikerjakan."""
        if self.mode == "minimal":
            # Judul lagu sama personalnya dengan nama proyek; mode minimal
            # menjanjikan tidak membocorkan keduanya.
            return {"details": _potong(peta["dengerin"])}
        judul = musik.get("judul", "")
        artis = musik.get("artis", "")
        teks = f"{artis} \u2014 {judul}" if artis else judul
        return {"details": _potong(f"\u266a {teks}"), "state": _potong(peta["dengerin"])}

    def rakit(self, sekarang: float, musik: dict | None = None) -> dict | None:
        """Rakit payload activity Discord. ``None`` berarti kosongkan presence.

        Lagu hanya tampil saat tidak ada sesi yang sedang bekerja atau
        berpikir -- Discord cuma punya dua baris teks, jadi menampilkan
        keduanya sekaligus membuat dua-duanya terpotong.
        """
        hidup = list(self.sesi.values())
        sibuk = any(s.keadaan in (BEKERJA, BERPIKIR) for s in hidup)
        if musik and not sibuk:
            return self._kartu_musik(musik, {**LABEL_BAWAAN, **self.label})
        if not hidup:
            return None

        utama = max(hidup, key=lambda s: s.urutan)
        jumlah = len(hidup)

        if self.mode == "minimal":
            details = "Sedang ngoding"
        else:
            nama = self._nama_proyek(utama)
            details = f"\U0001f4c1 {nama}" if nama else "Claude Code"
            if jumlah > 1:
                details += f" +{jumlah - 1} lainnya"

        peta = {**LABEL_BAWAAN, **self.label}
        if utama.keadaan == BEKERJA:
            state = label_alat(utama.alat, peta)
            if self.mode == "detail" and utama.rincian_alat:
                state += f": {utama.rincian_alat}"
        elif utama.keadaan == BERPIKIR:
            state = peta["berpikir"]
        else:
            state = peta["idle"]

        if jumlah > 1:
            state += f" · {jumlah} sesi aktif"

        activity: dict = {"details": _potong(details), "state": _potong(state)}
        if self.tampilkan_timer:
            # Timer dihitung dari sesi tertua yang masih hidup supaya angkanya
            # tidak melompat mundur saat sesi lain ikut bergabung.
            activity["timestamps"] = {"start": int(min(s.mulai for s in hidup) * 1000)}
        return activity


def _rincian(alat: str, masukan) -> str:
    """Ambil satu keping informasi untuk mode ``detail`` saja.

    Tetap dikumpulkan walau mode sedang kasar supaya pergantian mode tidak
    perlu menunggu peristiwa berikutnya; penyaringannya dilakukan di ``rakit``.
    """
    if not isinstance(masukan, dict):
        return ""
    if alat == "Bash":
        perintah = str(masukan.get("command", "")).strip()
        # Kata pertama saja -- sisanya sering memuat jalur dan argumen.
        return perintah.split()[0] if perintah else ""
    jalur = masukan.get("file_path") or masukan.get("notebook_path") or masukan.get("path")
    if jalur:
        return os.path.basename(str(jalur))
    if alat in ("Grep", "Glob"):
        return str(masukan.get("pattern", ""))[:40]
    return ""
