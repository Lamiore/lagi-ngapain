#!/usr/bin/env python3
"""Daemon cc-presence: menyalakan Discord Rich Presence untuk Claude Code.

Hook Claude Code berumur sangat pendek -- prosesnya mati begitu selesai,
dan Rich Presence ikut hilang saat soketnya tertutup. Jadi hook hanya
menumpahkan muatannya ke spool, dan proses inilah yang memegang koneksi
IPC serta menerbitkan pembaruan dengan laju yang aman.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cc_konfig
from cc_ipc import DiscordTidakAda, KlienDiscord
from cc_musik import PembacaMusik
import cc_sampul
from cc_sampul import PencariSampul
from cc_state import Registry

# Jeda antar denyut. Jauh lebih rapat dari jeda penerbitan supaya peristiwa
# cepat terserap; penerbitannya sendiri yang direm.
DENYUT = 1.0
# Jeda coba-sambung ulang saat Discord tidak ada.
JEDA_SAMBUNG = 10.0
# Berkas spool yang JSON-nya belum utuh dibiarkan selama ini sebelum
# dianggap rusak -- menutup lomba baca/tulis tanpa membebani hook.
TENGGANG_RUSAK = 3.0

# Penanda "belum pernah menerbitkan apa pun". Tidak bisa memakai None karena
# None adalah muatan yang sah (artinya: kosongkan presence).
BELUM_PERNAH = object()


def dir_spool() -> Path:
    dasar = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    return Path(dasar) / "cc-presence" / "ev"


def _log(*a) -> None:
    print(time.strftime("[%H:%M:%S]"), *a, flush=True)


class Daemon:
    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg
        self.spool = dir_spool()
        self.registry = Registry(
            ttl=cfg["ttl_sesi"],
            mode=cfg["mode"],
            proyek_privat=cfg["proyek_privat"],
            tampilkan_timer=cfg["tampilkan_timer"],
            label=cfg["label"],
            tipe_kerja=cfg["tipe_kerja"],
            tipe_musik=cfg["tipe_musik"],
            kartu_kosong=cfg["kartu_kosong"],
            sampul_saat_kerja=cfg["sampul_saat_kerja"],
        )
        self.klien = KlienDiscord(cfg["client_id"])
        # Dibaca berkala, bukan tiap denyut: satu pembacaan memanggil
        # beberapa proses busctl, sementara lagu tidak berganti tiap detik.
        self.musik = PembacaMusik(abaikan=cfg["abaikan_pemutar"]) if cfg["musik"] else None
        # Mode minimal menjanjikan judul lagu tidak ke mana-mana -- termasuk
        # tidak ke API pencarian sampul.
        self.sampul = (PencariSampul() if self.musik and cfg.get("sampul", True)
                       and cfg["mode"] != "minimal" else None)
        self.terakhir_terbit = 0.0
        self.terakhir_muatan = BELUM_PERNAH
        self.coba_sambung_lagi = 0.0
        self.jalan = True

    # -- spool --------------------------------------------------------------

    def siapkan_spool(self) -> None:
        """Membuat direktori spool -- inilah yang 'menyalakan' hook."""
        self.spool.mkdir(parents=True, exist_ok=True)
        for f in self.spool.iterdir():  # buang sisa jalan sebelumnya
            f.unlink(missing_ok=True)

    def bereskan_spool(self) -> None:
        """Menghapus direktori spool supaya hook kembali jadi no-op."""
        try:
            for f in self.spool.iterdir():
                f.unlink(missing_ok=True)
            self.spool.rmdir()
        except OSError:
            pass

    def serap_peristiwa(self, sekarang: float) -> bool:
        """Baca seluruh berkas spool sesuai urutan waktu. True kalau berubah."""
        try:
            berkas = sorted(self.spool.iterdir(), key=lambda p: p.name)
        except OSError:
            return False

        berubah = False
        for f in berkas:
            try:
                ev = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                # Kemungkinan besar hook masih menulisnya. Biarkan dulu;
                # kalau tetap tidak terbaca sampai tenggang, baru dibuang.
                try:
                    if sekarang - f.stat().st_mtime > TENGGANG_RUSAK:
                        f.unlink(missing_ok=True)
                except OSError:
                    pass
                continue
            f.unlink(missing_ok=True)
            if isinstance(ev, dict) and self.registry.terapkan(ev, sekarang):
                berubah = True
        return berubah

    def lagu_kini(self, sekarang: float):
        """Lagu yang sedang diputar, dilengkapi URL sampulnya kalau ketemu.

        Pencariannya di sini, bukan di Registry: Registry sengaja tidak
        menyentuh jaringan supaya perakitan presence tetap murni logika.
        """
        lagu = self.musik.sekarang(sekarang) if self.musik else None
        if lagu and self.sampul:
            lagu = dict(lagu, sampul=self.sampul.untuk(lagu))
        return lagu

    # -- penerbitan ---------------------------------------------------------

    def pastikan_tersambung(self, sekarang: float) -> bool:
        if self.klien.tersambung:
            return True
        if sekarang < self.coba_sambung_lagi:
            return False
        try:
            self.klien.sambung()
            _log("tersambung ke Discord")
            # Paksa terbit ulang: presence hilang saat koneksi putus.
            self.terakhir_muatan = BELUM_PERNAH
            self.terakhir_terbit = 0.0
            return True
        except ValueError as e:  # client_id ditolak -- tidak ada gunanya mengulang
            _log("FATAL:", e)
            _log("Perbaiki client_id di", cc_konfig.jalur_konfig())
            self.jalan = False
            return False
        except DiscordTidakAda:
            self.coba_sambung_lagi = sekarang + JEDA_SAMBUNG
            return False

    def terbitkan(self, activity, sekarang: float) -> None:
        if activity == self.terakhir_muatan:
            return
        if sekarang - self.terakhir_terbit < self.cfg["jeda_publish"]:
            return  # direm: Discord membatasi laju SET_ACTIVITY
        try:
            self.klien.set_activity(activity)
        except DiscordTidakAda as e:
            _log("koneksi putus:", e)
            self.coba_sambung_lagi = sekarang + JEDA_SAMBUNG
            return
        self.terakhir_muatan = activity
        self.terakhir_terbit = sekarang
        if activity is None:
            _log("presence dikosongkan")
        else:
            from cc_state import TIPE_VALID
            ruas = [TIPE_VALID.get(activity.get("type"), "?"), activity.get("details")]
            if activity.get("state"):  # kartu kosong tidak punya baris kedua
                ruas.append(activity["state"])
            # Gambar yang ditolak Discord tidak menimbulkan galat apa pun,
            # jadi journal ini satu-satunya tanda sampulnya ikut terkirim.
            if activity.get("assets", {}).get("large_image"):
                ruas.append("+sampul")
            _log("presence:", " | ".join(ruas))

    # -- daur hidup ---------------------------------------------------------

    def berhenti(self, *a) -> None:
        self.jalan = False

    def jalankan(self) -> int:
        if not self.cfg["client_id"]:
            _log("client_id belum diisi di", cc_konfig.jalur_konfig())
            _log("Buat aplikasi di https://discord.com/developers/applications,")
            _log('namai "Claude Code", lalu salin Application ID-nya ke situ.')
            return 2

        signal.signal(signal.SIGTERM, self.berhenti)
        signal.signal(signal.SIGINT, self.berhenti)
        self.siapkan_spool()
        _log("daemon jalan, spool:", self.spool, "| mode:", self.cfg["mode"])

        try:
            while self.jalan:
                sekarang = time.time()
                self.serap_peristiwa(sekarang)
                self.registry.bersihkan(sekarang)
                if self.pastikan_tersambung(sekarang):
                    self.terbitkan(self.registry.rakit(sekarang, self.lagu_kini(sekarang)), sekarang)
                time.sleep(DENYUT)
        finally:
            if self.klien.tersambung:
                try:
                    self.klien.set_activity(None)
                except DiscordTidakAda:
                    pass
                self.klien.tutup()
            self.bereskan_spool()
            _log("daemon berhenti")
        return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Discord Rich Presence untuk Claude Code CLI")
    p.add_argument("--mode", choices=cc_konfig.MODE_VALID, help="timpa tingkat privasi sekali jalan")
    p.add_argument("--client-id", help="timpa Application ID sekali jalan")
    p.add_argument("--status", action="store_true", help="tampilkan keadaan lalu keluar")
    p.add_argument("--musik", choices=("on", "off"),
                   help="nyalakan/matikan tampilan lagu, lalu muat ulang service")
    args = p.parse_args(argv)

    cfg = cc_konfig.muat()
    if args.mode:
        cfg["mode"] = args.mode
    if args.client_id:
        cfg["client_id"] = args.client_id.strip()

    if args.musik:
        cfg["musik"] = args.musik == "on"
        cc_konfig.simpan(cfg)
        print("musik:", "nyala" if cfg["musik"] else "MATI")
        # Daemon membaca konfig sekali saat start, jadi perubahannya baru
        # berlaku setelah dimuat ulang. Dilakukan di sini supaya "tombol
        # panik" benar-benar satu perintah.
        import subprocess
        hasil = subprocess.run(["systemctl", "--user", "restart", "cc-presence.service"],
                               capture_output=True, text=True)
        print("service:", "dimuat ulang" if hasil.returncode == 0 else "belum jalan, tidak dimuat ulang")
        return 0

    if args.status:
        from cc_ipc import cari_soket
        print("konfig       :", cc_konfig.jalur_konfig())
        print("client_id    :", cfg["client_id"] or "(belum diisi)")
        print("mode privasi :", cfg["mode"])
        print("musik        :", "nyala" if cfg["musik"] else "mati",
              ("(abaikan: " + ", ".join(cfg["abaikan_pemutar"]) + ")") if cfg["abaikan_pemutar"] else "")
        singgahan = cc_sampul.jalur_singgahan()
        print("sampul       :", "nyala" if cfg["sampul"] else "mati",
              "(kartu kerja ikut)" if cfg["sampul_saat_kerja"] else "(kartu musik saja)",
              "|", singgahan if singgahan.exists() else f"{singgahan} (belum ada)")
        print("soket Discord:", ", ".join(cari_soket()) or "(tidak ketemu -- Discord belum jalan?)")
        spool = dir_spool()
        print("spool        :", spool, "(aktif)" if spool.is_dir() else "(daemon mati)")
        return 0

    return Daemon(cfg).jalankan()


if __name__ == "__main__":
    raise SystemExit(main())
