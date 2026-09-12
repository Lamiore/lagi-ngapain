"""Pembacaan lagu yang sedang diputar lewat MPRIS di D-Bus sesi.

Dipakai `busctl --json=short` alih-alih pustaka D-Bus mana pun: pip sistem
terkunci PEP 668, dan busctl sudah pasti ada karena bagian dari systemd.
Keluarannya JSON, jadi tidak ada penguraian teks yang rapuh.

Hampir semua pemutar di Linux mengumumkan diri lewat MPRIS -- Spotify,
VLC, mpv, dan tab browser (Brave/Chrome/Firefox) termasuk. Jadi ini tidak
terikat ke satu aplikasi.
"""

from __future__ import annotations

import json
import subprocess

AWALAN = "org.mpris.MediaPlayer2."
_IFACE = "org.mpris.MediaPlayer2.Player"
_OBJ = "/org/mpris/MediaPlayer2"
_TIMEOUT = 2.0

# Kalau beberapa pemutar sedang jalan sekaligus, yang khusus musik menang
# atas tab browser -- browser sering ketinggalan video yang dijeda.
PRIORITAS = ("spotify", "spotifyd", "mpd", "vlc", "mpv", "rhythmbox", "audacious", "elisa")


def _busctl(*argumen: str):
    try:
        hasil = subprocess.run(
            ["busctl", "--user", "--json=short", *argumen],
            capture_output=True, text=True, timeout=_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if hasil.returncode != 0:
        return None
    try:
        return json.loads(hasil.stdout).get("data")
    except (ValueError, AttributeError):
        return None


def daftar_pemutar() -> list[str]:
    data = _busctl("call", "org.freedesktop.DBus", "/org/freedesktop/DBus",
                   "org.freedesktop.DBus", "ListNames")
    if not data:
        return []
    # ListNames membalas satu larik berisi larik nama.
    nama = data[0] if data and isinstance(data[0], list) else data
    return sorted({n for n in nama if isinstance(n, str) and n.startswith(AWALAN)})


def _urutan(bus: str) -> tuple[int, str]:
    pendek = bus[len(AWALAN):].lower()
    for i, p in enumerate(PRIORITAS):
        if pendek.startswith(p):
            return (i, bus)
    return (len(PRIORITAS), bus)


def _properti(bus: str, nama: str):
    return _busctl("get-property", bus, _OBJ, _IFACE, nama)


def _teks(nilai) -> str:
    """Ratakan nilai MPRIS jadi teks; xesam:artist berupa larik."""
    if isinstance(nilai, dict):
        nilai = nilai.get("data")
    if isinstance(nilai, list):
        return ", ".join(str(x) for x in nilai if x)
    return str(nilai).strip() if nilai is not None else ""


def _diabaikan(bus: str, abaikan) -> bool:
    pendek = bus[len(AWALAN):].lower()
    return any(pendek.startswith(str(a).lower()) for a in abaikan if str(a).strip())


def lagu_sekarang(abaikan=()) -> dict | None:
    """Lagu dari pemutar pertama yang berstatus Playing, atau None.

    ``abaikan`` berisi awalan nama pemutar yang tidak boleh dibaca sama
    sekali, mis. ``("brave", "firefox")`` untuk menutup judul video browser.
    """
    for bus in sorted(daftar_pemutar(), key=_urutan):
        if _diabaikan(bus, abaikan):
            continue
        if _properti(bus, "PlaybackStatus") != "Playing":
            continue
        meta = _properti(bus, "Metadata")
        if not isinstance(meta, dict):
            continue
        judul = _teks(meta.get("xesam:title"))
        if not judul:
            continue  # tanpa judul tidak ada yang bisa ditampilkan
        return {
            "judul": judul,
            "artis": _teks(meta.get("xesam:artist")),
            "pemutar": bus[len(AWALAN):].split(".")[0],
        }
    return None


class PembacaMusik:
    """Pembungkus ``lagu_sekarang`` dengan singgahan.

    Daemon berdenyut tiap detik, tapi lagu tidak berganti secepat itu dan
    tiap pembacaan memanggil beberapa proses ``busctl``.
    """

    def __init__(self, jeda: float = 5.0, sumber=lagu_sekarang, abaikan=()) -> None:
        self.jeda = jeda
        self._sumber = sumber
        self._abaikan = tuple(abaikan)
        self._nilai: dict | None = None
        self._kapan = float("-inf")

    def sekarang(self, waktu: float) -> dict | None:
        if waktu - self._kapan >= self.jeda:
            self._nilai = self._sumber(self._abaikan)
            self._kapan = waktu
        return self._nilai
