"""Uji untuk cc_musik -- jalankan: python3 uji_cc_musik.py

D-Bus sungguhan tidak dipanggil; ``_busctl`` diganti dengan jawaban palsu
supaya bentuk balasan yang aneh (pemutar dijeda, artis berupa larik,
busctl gagal) bisa diuji tanpa memutar musik betulan.
"""

import unittest
from unittest import mock

import cc_musik as cm

BRAVE = "org.mpris.MediaPlayer2.brave.instance123"
SPOTIFY = "org.mpris.MediaPlayer2.spotify"


def balasan(peta):
    """Bikin pengganti _busctl dari peta sederhana {bus: (status, metadata)}."""
    def palsu(*arg):
        if arg[0] == "call":
            return [list(peta)]
        _, bus, _, _, prop = arg
        status, meta = peta[bus]
        return status if prop == "PlaybackStatus" else meta
    return palsu


class UjiPerataanNilai(unittest.TestCase):
    def test_artis_berupa_larik_digabung(self):
        self.assertEqual(cm._teks(["A", "B"]), "A, B")

    def test_nilai_terbungkus_dict_dibuka(self):
        self.assertEqual(cm._teks({"type": "s", "data": "Halo"}), "Halo")

    def test_none_jadi_teks_kosong(self):
        self.assertEqual(cm._teks(None), "")

    def test_larik_kosong_jadi_teks_kosong(self):
        self.assertEqual(cm._teks([]), "")


class UjiPrioritas(unittest.TestCase):
    def test_pemutar_musik_menang_atas_tab_browser(self):
        # Tab browser sering ketinggalan video yang dijeda; pemutar khusus
        # musik lebih bisa dipercaya.
        urut = sorted([BRAVE, SPOTIFY], key=cm._urutan)
        self.assertEqual(urut[0], SPOTIFY)

    def test_pemutar_tak_dikenal_tetap_urut_stabil(self):
        a, b = "org.mpris.MediaPlayer2.zed", "org.mpris.MediaPlayer2.apa"
        self.assertEqual(sorted([a, b], key=cm._urutan), [b, a])


class UjiLaguSekarang(unittest.TestCase):
    def _jalankan(self, peta):
        with mock.patch.object(cm, "_busctl", balasan(peta)):
            return cm.lagu_sekarang()

    def test_mengambil_pemutar_yang_playing(self):
        lagu = self._jalankan({BRAVE: ("Playing", {
            "xesam:title": "Too Soon", "xesam:artist": ["Oliver Steele"]})})
        self.assertEqual(lagu["judul"], "Too Soon")
        self.assertEqual(lagu["artis"], "Oliver Steele")
        self.assertEqual(lagu["pemutar"], "brave")

    def test_pemutar_dijeda_dilewati(self):
        self.assertIsNone(self._jalankan({BRAVE: ("Paused", {"xesam:title": "X"})}))

    def test_yang_playing_dipilih_walau_ada_yang_dijeda(self):
        lagu = self._jalankan({
            SPOTIFY: ("Paused", {"xesam:title": "Basi"}),
            BRAVE: ("Playing", {"xesam:title": "Segar"}),
        })
        self.assertEqual(lagu["judul"], "Segar")

    def test_tanpa_judul_dilewati(self):
        # Sebagian tab browser mengumumkan diri tanpa metadata apa pun.
        self.assertIsNone(self._jalankan({BRAVE: ("Playing", {"xesam:album": "X"})}))

    def test_tanpa_artis_tetap_dipakai(self):
        lagu = self._jalankan({BRAVE: ("Playing", {"xesam:title": "Nada"})})
        self.assertEqual(lagu["artis"], "")

    def test_tidak_ada_pemutar_balikan_none(self):
        self.assertIsNone(self._jalankan({}))

    def test_busctl_gagal_tidak_melempar(self):
        # Daemon tidak boleh mati cuma karena D-Bus lagi rewel.
        with mock.patch.object(cm, "_busctl", lambda *a: None):
            self.assertIsNone(cm.lagu_sekarang())
            self.assertEqual(cm.daftar_pemutar(), [])

    def test_busctl_hilang_dari_sistem_tidak_melempar(self):
        with mock.patch.object(cm.subprocess, "run", side_effect=OSError("tidak ada")):
            self.assertIsNone(cm._busctl("call"))


class UjiSaringanPemutar(unittest.TestCase):
    """Pemutar tertentu bisa ditutup seluruhnya -- ini rem privasinya."""

    def _jalankan(self, peta, abaikan):
        with mock.patch.object(cm, "_busctl", balasan(peta)):
            return cm.lagu_sekarang(abaikan)

    def test_pemutar_yang_diabaikan_tidak_dibaca(self):
        hasil = self._jalankan({BRAVE: ("Playing", {"xesam:title": "Video Rahasia"})}, ["brave"])
        self.assertIsNone(hasil)

    def test_pemutar_lain_tetap_kebaca(self):
        hasil = self._jalankan({
            BRAVE: ("Playing", {"xesam:title": "Video Rahasia"}),
            SPOTIFY: ("Playing", {"xesam:title": "Lagu"}),
        }, ["brave"])
        self.assertEqual(hasil["judul"], "Lagu")

    def test_pencocokan_tidak_peka_huruf_besar(self):
        self.assertIsNone(self._jalankan({BRAVE: ("Playing", {"xesam:title": "X"})}, ["BRAVE"]))

    def test_daftar_kosong_tidak_menyaring_apa_pun(self):
        self.assertIsNotNone(self._jalankan({BRAVE: ("Playing", {"xesam:title": "X"})}, []))

    def test_entri_kosong_tidak_menyaring_semuanya(self):
        # "" adalah awalan dari segalanya -- kalau lolos, semua pemutar mati.
        self.assertIsNotNone(self._jalankan({BRAVE: ("Playing", {"xesam:title": "X"})}, ["", "  "]))

    def test_saringan_diteruskan_lewat_singgahan(self):
        dipanggil = []
        p = cm.PembacaMusik(sumber=lambda ab: dipanggil.append(ab), abaikan=["brave"])
        p.sekarang(0.0)
        self.assertEqual(dipanggil, [("brave",)])


class UjiSinggahan(unittest.TestCase):
    def setUp(self):
        self.panggilan = 0

    def _sumber(self, abaikan=()):
        self.panggilan += 1
        return {"judul": f"lagu-{self.panggilan}", "artis": "", "pemutar": "x"}

    def test_dibaca_sekali_dalam_satu_jendela(self):
        p = cm.PembacaMusik(jeda=5.0, sumber=self._sumber)
        p.sekarang(100.0)
        p.sekarang(102.0)
        p.sekarang(104.9)
        self.assertEqual(self.panggilan, 1)

    def test_dibaca_lagi_setelah_jendela_lewat(self):
        p = cm.PembacaMusik(jeda=5.0, sumber=self._sumber)
        self.assertEqual(p.sekarang(100.0)["judul"], "lagu-1")
        self.assertEqual(p.sekarang(105.0)["judul"], "lagu-2")

    def test_pembacaan_pertama_tidak_menunggu(self):
        p = cm.PembacaMusik(jeda=5.0, sumber=self._sumber)
        self.assertIsNotNone(p.sekarang(0.0))


class UjiMetadataSampul(unittest.TestCase):
    """Data yang dibutuhkan pencarian sampul ikut dibaca dari MPRIS."""

    def _jalankan(self, meta):
        with mock.patch.object(cm, "_busctl", balasan({BRAVE: ("Playing", meta)})):
            return cm.lagu_sekarang()

    def test_album_dan_art_url_ikut_terbaca(self):
        lagu = self._jalankan({
            "xesam:title": "august", "xesam:artist": ["Taylor Swift"],
            "xesam:album": "folklore", "mpris:artUrl": "file:///tmp/x.png"})
        self.assertEqual(lagu["album"], "folklore")
        self.assertEqual(lagu["sampul_mentah"], "file:///tmp/x.png")

    def test_metadata_tanpa_album_tetap_punya_kuncinya(self):
        # Pencari sampul membaca kunci ini langsung; kalau hilang, meledak.
        lagu = self._jalankan({"xesam:title": "Nada"})
        self.assertEqual(lagu["album"], "")
        self.assertEqual(lagu["sampul_mentah"], "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
