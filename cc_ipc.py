"""Klien Discord IPC seadanya -- tanpa dependensi luar.

Protokolnya sederhana: bingkai ``<opcode u32 LE><panjang u32 LE><JSON>``
lewat soket domain Unix. Hanya empat opcode yang dipakai di sini, jadi
memasang ``pypresence`` (yang butuh venv karena pip sistem terkunci PEP 668)
tidak sepadan.
"""

from __future__ import annotations

import glob
import json
import os
import socket
import struct
import uuid

OP_HANDSHAKE = 0
OP_FRAME = 1
OP_CLOSE = 2
OP_PING = 3
OP_PONG = 4


class DiscordTidakAda(Exception):
    """Soket Discord tidak ditemukan atau koneksinya putus."""


def cari_soket() -> list[str]:
    """Kembalikan kandidat soket IPC, yang paling mungkin di depan.

    Discord versi Flatpak menaruh soketnya di dalam ``app/<app-id>/``, bukan
    di akar ``XDG_RUNTIME_DIR`` seperti versi paket biasa. Keduanya digeledah
    supaya tidak bergantung pada symlink -- symlink ke soket Flatpak menjadi
    menggantung setiap kali Discord ditutup.
    """
    dasar = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    pola = [
        os.path.join(dasar, "discord-ipc-*"),
        os.path.join(dasar, "app", "*", "discord-ipc-*"),
        os.path.join(dasar, "snap.discord", "discord-ipc-*"),
    ]
    hasil: list[str] = []
    for p in pola:
        hasil.extend(sorted(glob.glob(p)))
    return [j for j in hasil if _adalah_soket(j)]


def _adalah_soket(jalur: str) -> bool:
    import stat
    try:
        return stat.S_ISSOCK(os.stat(jalur).st_mode)
    except OSError:
        return False


class KlienDiscord:
    """Koneksi ke klien Discord yang sedang berjalan."""

    def __init__(self, client_id: str, timeout: float = 5.0) -> None:
        self.client_id = str(client_id)
        self.timeout = timeout
        self._sock: socket.socket | None = None

    @property
    def tersambung(self) -> bool:
        return self._sock is not None

    def sambung(self) -> None:
        if self._sock is not None:
            return
        kandidat = cari_soket()
        if not kandidat:
            raise DiscordTidakAda("soket Discord tidak ditemukan (Discord belum jalan?)")

        galat_terakhir: Exception | None = None
        for jalur in kandidat:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(self.timeout)
            try:
                s.connect(jalur)
                self._sock = s
                self._kirim(OP_HANDSHAKE, {"v": 1, "client_id": self.client_id})
                op, muatan = self._terima()
                if op == OP_CLOSE:
                    pesan = muatan.get("message", "handshake ditolak")
                    self.tutup()
                    # Client ID salah bukan masalah koneksi -- mencoba soket
                    # lain tidak akan menolong, jadi langsung dilempar.
                    raise ValueError(f"Discord menolak: {pesan}")
                return
            except (OSError, ValueError) as e:
                if isinstance(e, ValueError):
                    raise
                galat_terakhir = e
                try:
                    s.close()
                except OSError:
                    pass
                self._sock = None
        raise DiscordTidakAda(f"gagal menyambung ke soket Discord: {galat_terakhir}")

    def tutup(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    # -- bingkai ------------------------------------------------------------

    def _kirim(self, op: int, muatan: dict) -> None:
        if self._sock is None:
            raise DiscordTidakAda("belum tersambung")
        b = json.dumps(muatan).encode("utf-8")
        try:
            self._sock.sendall(struct.pack("<II", op, len(b)) + b)
        except OSError as e:
            self.tutup()
            raise DiscordTidakAda(f"gagal mengirim: {e}") from e

    def _baca_tepat(self, n: int) -> bytes:
        assert self._sock is not None
        potongan = bytearray()
        while len(potongan) < n:
            bagian = self._sock.recv(n - len(potongan))
            if not bagian:
                raise DiscordTidakAda("koneksi ditutup Discord")
            potongan.extend(bagian)
        return bytes(potongan)

    def _terima(self) -> tuple[int, dict]:
        try:
            op, panjang = struct.unpack("<II", self._baca_tepat(8))
            muatan = self._baca_tepat(panjang) if panjang else b"{}"
        except OSError as e:
            self.tutup()
            raise DiscordTidakAda(f"gagal membaca: {e}") from e
        try:
            return op, json.loads(muatan)
        except ValueError:
            return op, {}

    # -- perintah -----------------------------------------------------------

    def set_activity(self, activity: dict | None) -> dict:
        """Pasang presence. ``None`` mengosongkannya."""
        self._kirim(
            OP_FRAME,
            {
                "cmd": "SET_ACTIVITY",
                "args": {"pid": os.getpid(), "activity": activity},
                "nonce": str(uuid.uuid4()),
            },
        )
        op, muatan = self._terima()
        if op == OP_CLOSE:
            self.tutup()
            raise DiscordTidakAda(muatan.get("message", "koneksi ditutup"))
        return muatan

    def __enter__(self) -> "KlienDiscord":
        self.sambung()
        return self

    def __exit__(self, *a) -> None:
        self.tutup()
