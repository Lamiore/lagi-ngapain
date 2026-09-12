"""Uji untuk cc_konfig -- jalankan: python3 uji_cc_konfig.py"""

import json
import tempfile
import unittest
from pathlib import Path

import cc_konfig as ck


class UjiKonfig(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.jalur = Path(self.dir.name) / "konfig.json"

    def tearDown(self):
        self.dir.cleanup()

    def tulis(self, isi):
        self.jalur.write_text(json.dumps(isi), encoding="utf-8")

    def test_berkas_tidak_ada_pakai_bawaan(self):
        cfg = ck.muat(self.jalur)
        self.assertEqual(cfg["mode"], "normal")
        self.assertEqual(cfg["client_id"], "")

    def test_berkas_rusak_tidak_melempar(self):
        self.jalur.write_text("{bukan json", encoding="utf-8")
        self.assertEqual(ck.muat(self.jalur)["mode"], "normal")

    def test_kunci_hilang_dilengkapi(self):
        self.tulis({"client_id": "123"})
        cfg = ck.muat(self.jalur)
        self.assertEqual(cfg["client_id"], "123")
        self.assertEqual(cfg["ttl_sesi"], ck.BAWAAN["ttl_sesi"])

    def test_kunci_asing_diabaikan(self):
        self.tulis({"client_id": "123", "rahasia": "jangan-kepakai"})
        self.assertNotIn("rahasia", ck.muat(self.jalur))

    def test_mode_ngawur_jatuh_ke_bawaan(self):
        self.tulis({"mode": "bocorin-semua"})
        self.assertEqual(ck.muat(self.jalur)["mode"], "normal")

    def test_jeda_publish_tidak_boleh_di_bawah_batas_laju(self):
        # Discord membatasi SET_ACTIVITY; nilai kecil harus dinaikkan paksa.
        self.tulis({"jeda_publish": 1})
        self.assertEqual(ck.muat(self.jalur)["jeda_publish"], 15)

    def test_ttl_terlalu_kecil_dinaikkan(self):
        self.tulis({"ttl_sesi": 5})
        self.assertEqual(ck.muat(self.jalur)["ttl_sesi"], 60)

    def test_client_id_dirapikan(self):
        self.tulis({"client_id": "  123456  "})
        self.assertEqual(ck.muat(self.jalur)["client_id"], "123456")

    def test_proyek_privat_bukan_larik_diabaikan(self):
        self.tulis({"proyek_privat": "skripsi"})
        self.assertEqual(ck.muat(self.jalur)["proyek_privat"], [])

    def test_simpan_lalu_muat_pulang_pergi(self):
        cfg = ck.muat(self.jalur)
        cfg["client_id"] = "987"
        cfg["proyek_privat"] = ["Skripsi"]
        ck.simpan(cfg, self.jalur)
        lagi = ck.muat(self.jalur)
        self.assertEqual(lagi["client_id"], "987")
        self.assertEqual(lagi["proyek_privat"], ["Skripsi"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
