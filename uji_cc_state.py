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
        self.assertEqual(self.r.rakit(10.0)["state"], cs.LABEL_BAWAAN["Read"])

    def test_stop_jadi_menunggu(self):
        self.r.terapkan(ev("a", "PreToolUse", tool_name="Bash"), 10.0)
        self.r.terapkan(ev("a", "Stop"), 11.0)
        self.assertEqual(self.r.rakit(11.0)["state"], cs.LABEL_BAWAAN["idle"])

    def test_prompt_jadi_berpikir(self):
        self.r.terapkan(ev("a", "UserPromptSubmit"), 10.0)
        self.assertEqual(self.r.rakit(10.0)["state"], cs.LABEL_BAWAAN["berpikir"])

    def test_sessionend_membuang_sesi(self):
        self.r.terapkan(ev("a", "UserPromptSubmit"), 10.0)
        self.r.terapkan(ev("a", "SessionEnd"), 11.0)
        self.assertEqual(self.r.sesi, {})

    def test_peristiwa_tak_dikenal_diabaikan(self):
        self.assertFalse(self.r.terapkan(ev("a", "PostToolUse"), 10.0))
        self.assertEqual(self.r.sesi, {})

    def test_muatan_tanpa_session_id_diabaikan(self):
        self.assertFalse(self.r.terapkan({"hook_event_name": "Stop"}, 10.0))

    def test_alat_mcp_tidak_membocorkan_nama_server(self):
        self.r.terapkan(ev("a", "PreToolUse", tool_name="mcp__plugin_github_github__get_me"), 10.0)
        self.assertEqual(self.r.rakit(10.0)["state"], cs.LABEL_BAWAAN["mcp"])


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
        self.assertEqual(self.r.sesi, {})

    def test_ttl_hanya_membuang_yang_basi(self):
        self.r.terapkan(ev("a", "UserPromptSubmit"), 10.0)
        self.r.terapkan(ev("b", "UserPromptSubmit", cwd="/tmp/lain"), 1000.0)
        self.r.bersihkan(1001.0)
        self.assertEqual(list(self.r.sesi), ["b"])


class UjiLabel(unittest.TestCase):
    """Label boleh diganti tanpa menyentuh kode."""

    def _state(self, **kw):
        r = cs.Registry(**kw)
        r.terapkan(ev("a", "PreToolUse", tool_name="Bash"), 10.0)
        return r.rakit(10.0)["state"]

    def test_timpaan_alat_dipakai(self):
        self.assertEqual(self._state(label={"Bash": "Ngetik perintah"}), "Ngetik perintah")

    def test_kunci_yang_tidak_ditimpa_tetap_bawaan(self):
        r = cs.Registry(label={"Bash": "X"})
        r.terapkan(ev("a", "PreToolUse", tool_name="Read"), 10.0)
        self.assertEqual(r.rakit(10.0)["state"], cs.LABEL_BAWAAN["Read"])

    def test_timpaan_keadaan_idle_dan_berpikir(self):
        r = cs.Registry(label={"idle": "Rehat", "berpikir": "Ngelamun"})
        r.terapkan(ev("a", "UserPromptSubmit"), 10.0)
        self.assertEqual(r.rakit(10.0)["state"], "Ngelamun")
        r.terapkan(ev("a", "Stop"), 11.0)
        self.assertEqual(r.rakit(11.0)["state"], "Rehat")

    def test_timpaan_mcp_berlaku_untuk_semua_server(self):
        r = cs.Registry(label={"mcp": "Nyolek MCP"})
        r.terapkan(ev("a", "PreToolUse", tool_name="mcp__apa__pun"), 10.0)
        self.assertEqual(r.rakit(10.0)["state"], "Nyolek MCP")

    def test_cadangan_menyisipkan_nama_alat(self):
        r = cs.Registry(label={"lainnya": "Lagi {alat}"})
        r.terapkan(ev("a", "PreToolUse", tool_name="AlatAsing"), 10.0)
        self.assertEqual(r.rakit(10.0)["state"], "Lagi AlatAsing")

    def test_label_masih_digabung_dengan_jumlah_sesi(self):
        r = cs.Registry(label={"Bash": "Ngetik"})
        r.terapkan(ev("a", "PreToolUse", tool_name="Bash"), 10.0)
        r.terapkan(ev("b", "PreToolUse", cwd="/tmp/lain", tool_name="Bash"), 11.0)
        self.assertEqual(r.rakit(11.0)["state"], "Ngetik \u00b7 2 sesi aktif")

    def test_mode_detail_tetap_menempel_pada_label_timpaan(self):
        r = cs.Registry(mode="detail", label={"Edit": "Ngoret"})
        r.terapkan(ev("a", "PreToolUse", tool_name="Edit",
                      tool_input={"file_path": "/x/y/lcd_gif.py"}), 10.0)
        self.assertEqual(r.rakit(10.0)["state"], "Ngoret: lcd_gif.py")


class UjiKartuMusik(unittest.TestCase):
    """Lagu hanya muncul saat tidak ada yang dikerjakan."""

    LAGU = {"judul": "Too Soon", "artis": "Oliver Steele", "pemutar": "brave"}

    def setUp(self):
        self.r = cs.Registry()

    def test_tanpa_sesi_tapi_ada_lagu_presence_tetap_tampil(self):
        hasil = self.r.rakit(10.0, self.LAGU)
        self.assertIn("Too Soon", hasil["details"])
        self.assertEqual(hasil["state"], cs.LABEL_BAWAAN["dengerin"])

    def test_tanpa_sesi_tanpa_lagu_jatuh_ke_kartu_kosong(self):
        self.assertEqual(self.r.rakit(10.0, None),
                         {"type": cs.TIPE_KERJA, "details": "\U0001f4bb " + cs.LABEL_BAWAAN["idle"]})

    def test_saat_bekerja_kerjaan_menang_atas_lagu(self):
        # Discord cuma punya dua baris; menampilkan keduanya memotong keduanya.
        self.r.terapkan(ev("a", "PreToolUse", tool_name="Bash"), 10.0)
        self.assertIn("aio-lcd", self.r.rakit(10.0, self.LAGU)["details"])

    def test_saat_berpikir_kerjaan_juga_menang(self):
        self.r.terapkan(ev("a", "UserPromptSubmit"), 10.0)
        self.assertIn("aio-lcd", self.r.rakit(10.0, self.LAGU)["details"])

    def test_sesi_idle_memberi_giliran_ke_lagu(self):
        self.r.terapkan(ev("a", "Stop"), 10.0)
        self.assertIn("Too Soon", self.r.rakit(10.0, self.LAGU)["details"])

    def test_satu_sesi_sibuk_sudah_cukup_menahan_lagu(self):
        self.r.terapkan(ev("a", "Stop"), 10.0)
        self.r.terapkan(ev("b", "PreToolUse", cwd="/tmp/lain", tool_name="Bash"), 11.0)
        self.assertNotIn("Too Soon", self.r.rakit(11.0, self.LAGU)["details"])

    def test_tanpa_artis_judul_saja(self):
        hasil = self.r.rakit(10.0, {"judul": "Nada", "artis": ""})
        self.assertEqual(hasil["details"], "\u266a Nada")

    def test_mode_minimal_tidak_membocorkan_judul(self):
        r = cs.Registry(mode="minimal")
        hasil = r.rakit(10.0, self.LAGU)
        self.assertNotIn("Too Soon", hasil["details"])
        self.assertNotIn("Oliver", hasil["details"])

    def test_label_dengerin_bisa_ditimpa(self):
        r = cs.Registry(label={"dengerin": "Lagi nyetel"})
        self.assertEqual(r.rakit(10.0, self.LAGU)["state"], "Lagi nyetel")

    def test_judul_panjang_dipotong(self):
        hasil = self.r.rakit(10.0, {"judul": "L" * 300, "artis": "A" * 300})
        self.assertLessEqual(len(hasil["details"]), cs.BATAS_FIELD)


class UjiTipeActivity(unittest.TestCase):
    """Kata di pojok atas presence ("Playing X" / "Listening to X")."""

    LAGU = {"judul": "Too Soon", "artis": "NIKI", "pemutar": "brave"}

    def test_kartu_kerja_bawaannya_playing(self):
        r = cs.Registry()
        r.terapkan(ev("a", "PreToolUse", tool_name="Bash"), 10.0)
        self.assertEqual(r.rakit(10.0)["type"], cs.TIPE_KERJA)

    def test_kartu_musik_bawaannya_listening(self):
        self.assertEqual(cs.Registry().rakit(10.0, self.LAGU)["type"], cs.TIPE_MUSIK)

    def test_kartu_musik_mode_minimal_tetap_bertipe(self):
        r = cs.Registry(mode="minimal")
        self.assertEqual(r.rakit(10.0, self.LAGU)["type"], cs.TIPE_MUSIK)

    def test_tipe_bisa_diatur(self):
        r = cs.Registry(tipe_kerja=3, tipe_musik=5)
        r.terapkan(ev("a", "PreToolUse", tool_name="Bash"), 10.0)
        self.assertEqual(r.rakit(10.0)["type"], 3)
        r.terapkan(ev("a", "Stop"), 11.0)
        self.assertEqual(r.rakit(11.0, self.LAGU)["type"], 5)

    def test_streaming_ditolak_karena_discord_membuangnya(self):
        # Diukur langsung: type=1 diterima tapi tidak dikembalikan Discord --
        # dia menuntut URL Twitch/YouTube yang sah. Lebih baik jatuh ke bawaan
        # daripada diam-diam kehilangan tipenya.
        self.assertEqual(cs.Registry(tipe_kerja=1).tipe_kerja, cs.TIPE_KERJA)

    def test_tipe_ngawur_jatuh_ke_bawaan(self):
        self.assertEqual(cs.Registry(tipe_kerja=99).tipe_kerja, cs.TIPE_KERJA)
        self.assertEqual(cs.Registry(tipe_musik=4).tipe_musik, cs.TIPE_MUSIK)


class UjiKartuKosong(unittest.TestCase):
    """Presence saat belum ada sesi sama sekali -- mis. PC baru dinyalakan."""

    LAGU = {"judul": "Too Soon", "artis": "NIKI", "pemutar": "brave"}

    def test_tampil_walau_belum_pernah_ada_sesi(self):
        hasil = cs.Registry().rakit(10.0)
        self.assertIn(cs.LABEL_BAWAAN["idle"], hasil["details"])

    def test_tidak_punya_baris_kedua_maupun_timer(self):
        hasil = cs.Registry().rakit(10.0)
        self.assertNotIn("state", hasil)
        self.assertNotIn("timestamps", hasil)

    def test_musik_menang_atas_kartu_kosong(self):
        self.assertIn("Too Soon", cs.Registry().rakit(10.0, self.LAGU)["details"])

    def test_sesi_menang_atas_kartu_kosong(self):
        r = cs.Registry()
        r.terapkan(ev("a", "Stop"), 10.0)
        self.assertIn("aio-lcd", r.rakit(10.0)["details"])

    def test_ikut_label_idle_supaya_sekali_ganti(self):
        r = cs.Registry(label={"idle": "Rebahan"})
        self.assertIn("Rebahan", r.rakit(10.0)["details"])

    def test_ikut_tipe_kerja(self):
        self.assertEqual(cs.Registry(tipe_kerja=3).rakit(10.0)["type"], 3)

    def test_bisa_dimatikan(self):
        self.assertIsNone(cs.Registry(kartu_kosong=False).rakit(10.0))


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

    def test_registry_kosong_mengosongkan_presence_kalau_kartu_kosong_dimatikan(self):
        self.assertIsNone(cs.Registry(kartu_kosong=False).rakit(10.0))


class UjiSampulDiKartuMusik(unittest.TestCase):
    """Sampul album menempel di kartu musik lewat assets.large_image."""

    LAGU = {"judul": "august", "artis": "Taylor Swift", "album": "folklore",
            "pemutar": "brave", "sampul": "https://cover/x.jpg"}

    def test_sampul_jadi_large_image(self):
        hasil = cs.Registry().rakit(10.0, self.LAGU)
        self.assertEqual(hasil["assets"]["large_image"], "https://cover/x.jpg")

    def test_tanpa_sampul_tidak_ada_assets_sama_sekali(self):
        # Kunci kosong bikin activity ditolak diam-diam; lebih baik tidak dikirim.
        hasil = cs.Registry().rakit(10.0, dict(self.LAGU, sampul=""))
        self.assertNotIn("assets", hasil)

    def test_mode_minimal_tidak_dapat_sampul(self):
        # Sampul album sama membocorkannya dengan judul lagu.
        hasil = cs.Registry(mode="minimal").rakit(10.0, self.LAGU)
        self.assertNotIn("assets", hasil)

    def test_large_text_menyebut_album(self):
        self.assertEqual(cs.Registry().rakit(10.0, self.LAGU)["assets"]["large_text"], "folklore")

    def test_tanpa_album_large_text_jatuh_ke_judul(self):
        hasil = cs.Registry().rakit(10.0, dict(self.LAGU, album=""))
        self.assertEqual(hasil["assets"]["large_text"], "august")

    def test_large_text_dipotong_sesuai_batas_discord(self):
        hasil = cs.Registry().rakit(10.0, dict(self.LAGU, album="x" * 400))
        self.assertLessEqual(len(hasil["assets"]["large_text"]), cs.BATAS_FIELD)


class UjiSampulDiKartuKerja(unittest.TestCase):
    """Sampul juga menempel di kartu kerja, bukan cuma di kartu musik.

    Slot gambar itu yang biasanya diisi ikon aplikasi, jadi selama ada lagu
    yang diputar ikon Claude Code memang tergantikan sampul album. Namanya
    tetap tampil di baris teratas presence, jadi kartunya tidak jadi anonim.
    """

    LAGU = {"judul": "august", "artis": "Taylor Swift", "album": "folklore",
            "pemutar": "brave", "sampul": "https://cover/x.jpg"}

    def _sibuk(self, peristiwa="PreToolUse", **kw):
        r = cs.Registry(**kw)
        r.terapkan(ev("a", peristiwa, tool_name="Bash"), 10.0)
        return r

    def test_sampul_nempel_walau_lagi_ngoding(self):
        hasil = self._sibuk().rakit(10.0, self.LAGU)
        self.assertEqual(hasil["type"], cs.TIPE_KERJA, "tetap kartu kerja, bukan kartu musik")
        self.assertEqual(hasil["state"], "Ngoprek terminal")
        self.assertEqual(hasil["assets"]["large_image"], "https://cover/x.jpg")

    def test_hover_menyebut_lagunya_bukan_albumnya(self):
        # Di kartu kerja judul lagunya tidak tampil di mana pun, jadi teks
        # gantungnya harus menyebut lagu -- beda dengan kartu musik yang
        # sudah memuatnya di baris atas.
        hasil = self._sibuk().rakit(10.0, self.LAGU)
        self.assertEqual(hasil["assets"]["large_text"], "\u266a Taylor Swift \u2014 august")

    def test_kartu_berpikir_juga_kebagian(self):
        hasil = self._sibuk("UserPromptSubmit").rakit(10.0, self.LAGU)
        self.assertIn("assets", hasil)

    def test_bisa_dimatikan_tanpa_mematikan_kartu_musik(self):
        # Yang mau ikon Claude Code tetap terlihat saat ngoding.
        r = self._sibuk(sampul_saat_kerja=False)
        self.assertNotIn("assets", r.rakit(10.0, self.LAGU))
        polos = cs.Registry(sampul_saat_kerja=False)
        self.assertIn("assets", polos.rakit(10.0, self.LAGU), "kartu musik tidak ikut mati")

    def test_mode_minimal_tidak_bocor_lewat_gambar(self):
        self.assertNotIn("assets", self._sibuk(mode="minimal").rakit(10.0, self.LAGU))

    def test_tanpa_lagu_tidak_ada_assets(self):
        self.assertNotIn("assets", self._sibuk().rakit(10.0))

    def test_lagu_tanpa_sampul_tidak_ada_assets(self):
        # Kunci kosong bikin activity ditolak diam-diam.
        self.assertNotIn("assets", self._sibuk().rakit(10.0, dict(self.LAGU, sampul="")))

    def test_timer_tidak_hilang_gara_gara_sampul(self):
        hasil = self._sibuk().rakit(10.0, self.LAGU)
        self.assertIn("timestamps", hasil)


if __name__ == "__main__":
    unittest.main(verbosity=2)
