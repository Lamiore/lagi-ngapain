"""Uji untuk cc_ipc -- jalankan: python3 uji/uji_cc_ipc.py

Discord sungguhan tidak dipakai. Sebagai gantinya ada server soket palsu
yang bicara protokol yang sama, jadi bingkai, handshake, dan penanganan
putus koneksi bisa diuji tanpa aplikasi yang menyala.
"""

import json
import os
import socket
import struct
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cc_ipc


class ServerPalsu:
    """Server IPC seukur perlu: satu koneksi, balasan yang bisa diatur."""

    def __init__(self, jalur, tolak_handshake=False, putus_setelah=None):
        self.jalur = str(jalur)
        self.tolak_handshake = tolak_handshake
        self.putus_setelah = putus_setelah
        self.diterima = []
        self._srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._srv.bind(self.jalur)
        self._srv.listen(1)
        self._t = threading.Thread(target=self._layani, daemon=True)
        self._t.start()

    def _baca_bingkai(self, c):
        hdr = c.recv(8)
        if len(hdr) < 8:
            return None
        op, panjang = struct.unpack("<II", hdr)
        data = b""
        while len(data) < panjang:
            bagian = c.recv(panjang - len(data))
            if not bagian:
                break
            data += bagian
        return op, json.loads(data or b"{}")

    def _kirim(self, c, op, muatan):
        b = json.dumps(muatan).encode()
        c.sendall(struct.pack("<II", op, len(b)) + b)

    def _layani(self):
        try:
            c, _ = self._srv.accept()
        except OSError:
            return
        with c:
            n = 0
            while True:
                bingkai = self._baca_bingkai(c)
                if bingkai is None:
                    return
                op, muatan = bingkai
                self.diterima.append((op, muatan))
                n += 1
                if op == cc_ipc.OP_HANDSHAKE:
                    if self.tolak_handshake:
                        alasan = self.tolak_handshake
                        if alasan is True:
                            alasan = {"code": 4000, "message": "Invalid Client ID"}
                        self._kirim(c, cc_ipc.OP_CLOSE, alasan)
                        return
                    self._kirim(c, cc_ipc.OP_FRAME, {"cmd": "DISPATCH", "evt": "READY"})
                else:
                    self._kirim(c, cc_ipc.OP_FRAME, {"cmd": "SET_ACTIVITY", "data": muatan.get("args")})
                if self.putus_setelah is not None and n >= self.putus_setelah:
                    return

    def tutup(self):
        try:
            self._srv.close()
        except OSError:
            pass


class UjiPencarianSoket(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.lama = os.environ.get("XDG_RUNTIME_DIR")
        os.environ["XDG_RUNTIME_DIR"] = self.dir.name

    def tearDown(self):
        if self.lama is None:
            os.environ.pop("XDG_RUNTIME_DIR", None)
        else:
            os.environ["XDG_RUNTIME_DIR"] = self.lama
        self.dir.cleanup()

    def _soket(self, relatif):
        jalur = Path(self.dir.name) / relatif
        jalur.parent.mkdir(parents=True, exist_ok=True)
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.bind(str(jalur))
        self.addCleanup(s.close)
        return str(jalur)

    def test_menemukan_soket_flatpak_yang_bersarang(self):
        # Ini bentuk nyata di mesin ini: Discord Flatpak tidak menaruh
        # soketnya di akar XDG_RUNTIME_DIR.
        jalur = self._soket("app/com.discordapp.Discord/discord-ipc-0")
        self.assertIn(jalur, cc_ipc.cari_soket())

    def test_menemukan_soket_di_akar(self):
        jalur = self._soket("discord-ipc-0")
        self.assertIn(jalur, cc_ipc.cari_soket())

    def test_berkas_biasa_bukan_soket_diabaikan(self):
        (Path(self.dir.name) / "discord-ipc-0").write_text("bukan soket")
        self.assertEqual(cc_ipc.cari_soket(), [])

    def test_tidak_ada_soket_balikan_kosong(self):
        self.assertEqual(cc_ipc.cari_soket(), [])


class UjiKlien(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.jalur = Path(self.dir.name) / "discord-ipc-0"
        self.lama = os.environ.get("XDG_RUNTIME_DIR")
        os.environ["XDG_RUNTIME_DIR"] = self.dir.name

    def tearDown(self):
        if self.lama is None:
            os.environ.pop("XDG_RUNTIME_DIR", None)
        else:
            os.environ["XDG_RUNTIME_DIR"] = self.lama
        self.dir.cleanup()

    def test_handshake_lalu_set_activity(self):
        srv = ServerPalsu(self.jalur)
        self.addCleanup(srv.tutup)
        with cc_ipc.KlienDiscord("123456") as k:
            k.set_activity({"details": "halo", "state": "dunia"})
        op, muatan = srv.diterima[0]
        self.assertEqual(op, cc_ipc.OP_HANDSHAKE)
        self.assertEqual(muatan["client_id"], "123456")
        op, muatan = srv.diterima[1]
        self.assertEqual(op, cc_ipc.OP_FRAME)
        self.assertEqual(muatan["cmd"], "SET_ACTIVITY")
        self.assertEqual(muatan["args"]["activity"]["details"], "halo")
        self.assertEqual(muatan["args"]["pid"], os.getpid())

    def test_mengosongkan_presence_pakai_activity_none(self):
        srv = ServerPalsu(self.jalur)
        self.addCleanup(srv.tutup)
        with cc_ipc.KlienDiscord("123456") as k:
            k.set_activity(None)
        self.assertIsNone(srv.diterima[1][1]["args"]["activity"])

    def test_client_id_ditolak_melempar_valueerror(self):
        # Dibedakan dari DiscordTidakAda: mengulang tidak akan menolong,
        # jadi daemon harus berhenti, bukan mencoba lagi.
        srv = ServerPalsu(self.jalur, tolak_handshake=True)
        self.addCleanup(srv.tutup)
        with self.assertRaises(ValueError) as ctx:
            cc_ipc.KlienDiscord("000").sambung()
        self.assertIn("Invalid Client ID", str(ctx.exception))

    def test_penolakan_lain_bisa_diulang(self):
        # Kejadian nyata 13 Sept: daemon nyambung 7 detik sesudah Discord
        # dinyalakan, sebelum login selesai. Discord menutup handshake dengan
        # "User logged out" -- kodenya tidak tertangkap, jadi yang dianggap
        # permanen hanya bentuk yang sudah diukur (4000 + Invalid Client ID).
        for alasan in (
            {"code": 4000, "message": "User logged out"},
            {"code": 1000, "message": "User logged out"},
            {"message": "User logged out"},
        ):
            with self.subTest(alasan=alasan):
                if self.jalur.exists():
                    self.jalur.unlink()
                srv = ServerPalsu(self.jalur, tolak_handshake=alasan)
                self.addCleanup(srv.tutup)
                k = cc_ipc.KlienDiscord("123456")
                with self.assertRaises(cc_ipc.DiscordTidakAda) as ctx:
                    k.sambung()
                self.assertIn("User logged out", str(ctx.exception))
                self.assertFalse(k.tersambung)

    def test_tanpa_soket_melempar_discordtidakada(self):
        with self.assertRaises(cc_ipc.DiscordTidakAda):
            cc_ipc.KlienDiscord("123").sambung()

    def test_koneksi_putus_saat_kirim_terdeteksi(self):
        srv = ServerPalsu(self.jalur, putus_setelah=1)  # tutup tepat setelah handshake
        self.addCleanup(srv.tutup)
        k = cc_ipc.KlienDiscord("123456")
        k.sambung()
        with self.assertRaises(cc_ipc.DiscordTidakAda):
            for _ in range(3):  # kiriman pertama bisa lolos ke buffer kernel
                k.set_activity({"details": "x"})
        self.assertFalse(k.tersambung, "soket harus ditandai putus")

    def test_muatan_besar_terbaca_utuh(self):
        # recv() bisa mengembalikan potongan; pembacaannya harus mengulang.
        srv = ServerPalsu(self.jalur)
        self.addCleanup(srv.tutup)
        besar = {"details": "d" * 4000, "state": "s" * 4000}
        with cc_ipc.KlienDiscord("123456") as k:
            balasan = k.set_activity(besar)
        self.assertEqual(balasan["data"]["activity"]["details"], besar["details"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
