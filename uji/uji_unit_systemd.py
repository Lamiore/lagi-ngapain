"""Uji berkas unit systemd -- jalankan: python3 uji/uji_unit_systemd.py

Bukan uji perilaku: service sungguhan butuh Discord yang menyala. Yang
dijaga di sini cuma hal-hal yang kalau salah baru ketahuan berhari-hari
kemudian lewat journal yang membanjir.
"""

import configparser
import unittest
from pathlib import Path

UNIT = Path(__file__).resolve().parent.parent / "systemd" / "lagi-ngapain.service"


class UjiUnit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = configparser.ConfigParser(strict=False, interpolation=None)
        cls.cfg.optionxform = str
        cls.cfg.read(UNIT)

    def test_unit_ada_dan_terbaca(self):
        self.assertTrue(UNIT.exists())
        self.assertEqual(set(self.cfg.sections()), {"Unit", "Service", "Install"})

    def test_service_pengguna_bukan_sistem(self):
        self.assertEqual(self.cfg["Install"]["WantedBy"], "default.target")

    def test_exec_pakai_specifier_home_bukan_jalur_keras(self):
        exec_start = self.cfg["Service"]["ExecStart"]
        self.assertTrue(exec_start.startswith("%h/"), exec_start)
        self.assertNotIn("/home/ram", exec_start)

    def test_keluar_karena_belum_dikonfigurasi_tidak_diulang(self):
        # cc_daemon keluar dengan kode 2 saat client_id kosong. Tanpa baris
        # ini Restart=on-failure akan mengulangnya tiap 10 detik selamanya.
        self.assertEqual(self.cfg["Service"]["SuccessExitStatus"], "2")

    def test_singgahan_sampul_punya_tempat_yang_bisa_ditulis(self):
        # ProtectHome=read-only bikin ~/.cache read-only buat service ini,
        # dan cc_sampul menelan galat tulisnya (singgahan itu kenyamanan,
        # bukan syarat). Tanpa baris ini singgahannya gagal ditulis diam-diam
        # tiap lagu baru, dan iTunes ditanya ulang tiap daemon dinyalakan.
        self.assertEqual(self.cfg["Service"]["CacheDirectory"], "lagi-ngapain")

    def test_ada_jeda_restart_supaya_tidak_kebut(self):
        self.assertGreaterEqual(int(self.cfg["Service"]["RestartSec"]), 5)

    def test_tidak_memakai_conflicts_atau_onfailure(self):
        # Gabungan Restart= + OnFailure= + Conflicts= pernah bikin dua unit
        # saling membunuh tanpa henti di proyek aio-lcd. Di sini tidak ada
        # unit lawan, jadi jangan sampai ketiganya masuk diam-diam.
        self.assertNotIn("Conflicts", self.cfg["Unit"])
        self.assertNotIn("OnFailure", self.cfg["Unit"])

    def test_home_hanya_baca(self):
        # Daemon tidak pernah perlu menulis ke $HOME; konfigurasinya ditulis
        # pemasang, bukan daemon.
        self.assertEqual(self.cfg["Service"]["ProtectHome"], "read-only")

    def test_runtime_dir_bisa_ditulis(self):
        # Spool dan soket Discord dua-duanya ada di %t (XDG_RUNTIME_DIR).
        self.assertIn("%t", self.cfg["Service"]["ReadWritePaths"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
