"""Uji untuk cc_state -- jalankan: python3 uji_cc_state.py

Fokusnya tiga hal yang paling gampang salah dan paling mahal kalau salah:
peralihan keadaan sesi, penggabungan banyak sesi, dan penyaringan privasi.
"""

import unittest

import cc_state as cs

CWD = "/home/ram/workspace/projects/aio-lcd"


def ev(sid, peristiwa, cwd=CWD, **tambahan):
    d = {"session_id": sid, "hook_event_name": peristiwa, "cwd": cwd}
    d.update(tambahan)
    return d


class UjiPeralihan(unittest.TestCase):
    def setUp(self):
        self.r = cs.Registry()

    def test_sesi_baru_terdaftar_dari_peristiwa_apa_pun(self):
        # Daemon bisa mulai di tengah sesi yang sudah jalan, jadi SessionStart
        # tidak boleh jadi syarat.
        self.r.terapkan(ev("a", "PreToolUse", tool_name="Bash"), 10.0)
        self.assertIn("a", self.r.sesi)

    def test_pretooluse_jadi_bekerja(self):
        self.r.terapkan(ev("a", "PreToolUse", tool_name="Read"), 10.0)
        self.assertEqual(self.r.rakit(10.0)["state"], "Membaca berkas")

    def test_stop_jadi_menunggu(self):
        self.r.terapkan(ev("a", "PreToolUse", tool_name="Bash"), 10.0)
        self.r.terapkan(ev("a", "Stop"), 11.0)
        self.assertEqual(self.r.rakit(11.0)["state"], "Menunggu perintah")

    def test_prompt_jadi_berpikir(self):
        self.r.terapkan(ev("a", "UserPromptSubmit"), 10.0)
        self.assertEqual(self.r.rakit(10.0)["state"], "Berpikir")

    def test_sessionend_membuang_sesi(self):
        self.r.terapkan(ev("a", "UserPromptSubmit"), 10.0)
        self.r.terapkan(ev("a", "SessionEnd"), 11.0)
        self.assertIsNone(self.r.rakit(11.0), "presence harus dikosongkan")

    def test_peristiwa_tak_dikenal_diabaikan(self):
        self.assertFalse(self.r.terapkan(ev("a", "PostToolUse"), 10.0))
        self.assertEqual(self.r.sesi, {})

    def test_muatan_tanpa_session_id_diabaikan(self):
        self.assertFalse(self.r.terapkan({"hook_event_name": "Stop"}, 10.0))

    def test_alat_mcp_tidak_membocorkan_nama_server(self):
        self.r.terapkan(ev("a", "PreToolUse", tool_name="mcp__plugin_github_github__get_me"), 10.0)
        self.assertEqual(self.r.rakit(10.0)["state"], "Memakai MCP")


class UjiBanyakSesi(unittest.TestCase):
    def setUp(self):
        self.r = cs.Registry()

    def test_jumlah_sesi_ditampilkan(self):
        self.r.terapkan(ev("a", "UserPromptSubmit"), 10.0)
        self.r.terapkan(ev("b", "UserPromptSubmit", cwd="/home/ram/workspace/dokumen"), 11.0)
        hasil = self.r.rakit(11.0)
        self.assertIn("2 sesi aktif", hasil["state"])
        self.assertIn("+1 lainnya", hasil["details"])

    def test_satu_sesi_tidak_menyebut_jumlah(self):
        self.r.terapkan(ev("a", "UserPromptSubmit"), 10.0)
        hasil = self.r.rakit(10.0)
        self.assertNotIn("sesi aktif", hasil["state"])
        self.assertNotIn("lainnya", hasil["details"])

    def test_sesi_paling_baru_bergerak_yang_ditampilkan(self):
        self.r.terapkan(ev("a", "PreToolUse", tool_name="Bash"), 10.0)
        self.r.terapkan(ev("b", "PreToolUse", cwd="/home/ram/workspace/dokumen", tool_name="Read"), 11.0)
        self.assertIn("dokumen", self.r.rakit(11.0)["details"])
        # sesi a bergerak lagi -> giliran a yang tampil
        self.r.terapkan(ev("a", "PreToolUse", tool_name="Grep"), 12.0)
        self.assertIn("aio-lcd", self.r.rakit(12.0)["details"])

    def test_timer_dari_sesi_tertua_supaya_tidak_melompat_mundur(self):
        self.r.terapkan(ev("a", "UserPromptSubmit"), 100.0)
        awal = self.r.rakit(100.0)["timestamps"]["start"]
        self.r.terapkan(ev("b", "UserPromptSubmit", cwd="/tmp/lain"), 200.0)
        self.assertEqual(self.r.rakit(200.0)["timestamps"]["start"], awal)

    def test_ttl_membuang_sesi_yang_terminalnya_ditutup_paksa(self):
        # SessionEnd tidak sempat jalan saat terminal dibunuh; tanpa TTL
        # presence akan nyangkut selamanya.
        self.r.terapkan(ev("a", "UserPromptSubmit"), 10.0)
        self.assertFalse(self.r.bersihkan(500.0))
        self.assertTrue(self.r.bersihkan(10.0 + self.r.ttl + 1))
        self.assertIsNone(self.r.rakit(10.0 + self.r.ttl + 1))

    def test_ttl_hanya_membuang_yang_basi(self):
        self.r.terapkan(ev("a", "UserPromptSubmit"), 10.0)
        self.r.terapkan(ev("b", "UserPromptSubmit", cwd="/tmp/lain"), 1000.0)
        self.r.bersihkan(1001.0)
        self.assertEqual(list(self.r.sesi), ["b"])


class UjiPrivasi(unittest.TestCase):
    def test_normal_hanya_nama_folder_bukan_jalur(self):
        r = cs.Registry(mode="normal")
        r.terapkan(ev("a", "PreToolUse", tool_name="Edit",
                      tool_input={"file_path": f"{CWD}/rahasia.py"}), 10.0)
        hasil = r.rakit(10.0)
        self.assertNotIn("/home/ram", hasil["details"])
        self.assertNotIn("rahasia.py", hasil["state"])
        self.assertIn("aio-lcd", hasil["details"])

    def test_minimal_tidak_menyebut_proyek(self):
        r = cs.Registry(mode="minimal")
        r.terapkan(ev("a", "PreToolUse", tool_name="Bash"), 10.0)
        self.assertNotIn("aio-lcd", r.rakit(10.0)["details"])

    def test_detail_menambah_nama_berkas(self):
        r = cs.Registry(mode="detail")
        r.terapkan(ev("a", "PreToolUse", tool_name="Edit",
                      tool_input={"file_path": f"{CWD}/lcd_gif.py"}), 10.0)
        self.assertIn("lcd_gif.py", r.rakit(10.0)["state"])

    def test_detail_bash_hanya_kata_pertama(self):
        r = cs.Registry(mode="detail")
        r.terapkan(ev("a", "PreToolUse", tool_name="Bash",
                      tool_input={"command": "psql -U admin -W hunter2 -h db.internal"}), 10.0)
        state = r.rakit(10.0)["state"]
        self.assertIn("psql", state)
        self.assertNotIn("hunter2", state)
        self.assertNotIn("db.internal", state)

    def test_proyek_privat_disamarkan(self):
        r = cs.Registry(proyek_privat=["Skripsi"])
        r.terapkan(ev("a", "UserPromptSubmit", cwd="/home/ram/Documents/Skripsi"), 10.0)
        hasil = r.rakit(10.0)
        self.assertNotIn("Skripsi", hasil["details"])
        self.assertIn("proyek privat", hasil["details"])

    def test_proyek_privat_tidak_peka_huruf_besar(self):
        r = cs.Registry(proyek_privat=["SKRIPSI"])
        r.terapkan(ev("a", "UserPromptSubmit", cwd="/home/ram/skripsi"), 10.0)
        self.assertIn("proyek privat", r.rakit(10.0)["details"])

    def test_cwd_berakhiran_garis_miring_tetap_kebaca(self):
        r = cs.Registry()
        r.terapkan(ev("a", "UserPromptSubmit", cwd="/home/ram/workspace/aio-lcd/"), 10.0)
        self.assertIn("aio-lcd", r.rakit(10.0)["details"])

    def test_field_dipotong_ke_batas_discord(self):
        r = cs.Registry()
        r.terapkan(ev("a", "UserPromptSubmit", cwd="/home/ram/" + "x" * 300), 10.0)
        self.assertLessEqual(len(r.rakit(10.0)["details"]), cs.BATAS_FIELD)

    def test_timer_bisa_dimatikan(self):
        r = cs.Registry(tampilkan_timer=False)
        r.terapkan(ev("a", "UserPromptSubmit"), 10.0)
        self.assertNotIn("timestamps", r.rakit(10.0))

    def test_registry_kosong_mengosongkan_presence(self):
        self.assertIsNone(cs.Registry().rakit(10.0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
