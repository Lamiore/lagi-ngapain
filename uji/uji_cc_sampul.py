"""Uji untuk cc_sampul -- jalankan: python3 uji/uji_cc_sampul.py

Jaringan tidak pernah disentuh: pencarinya disuntik lewat argumen, persis
seperti ``PembacaMusik(sumber=...)`` di cc_musik. Singgahan diarahkan ke
berkas sementara supaya uji tidak mengotori ~/.cache.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cc_sampul as cs

LAGU = {"judul": "august", "artis": "Taylor Swift", "album": "folklore", "sampul_mentah": ""}


class UjiArtUrlBawaan(unittest.TestCase):
    """Sebagian pemutar sudah menyodorkan URL yang bisa dipakai apa adanya."""

    def test_url_https_dipakai_apa_adanya(self):
        self.assertEqual(cs.dari_art_url("https://i.scdn.co/image/abc"), "https://i.scdn.co/image/abc")

    def test_url_http_juga_diterima(self):
        self.assertEqual(cs.dari_art_url("http://contoh/x.png"), "http://contoh/x.png")

    def test_berkas_lokal_ditolak(self):
        # Discord tidak bisa membaca berkas di komputer ini.
        self.assertEqual(cs.dari_art_url("file:///tmp/.org.chromium.Chromium.euNiw1"), "")

    def test_kosong_ditolak(self):
        self.assertEqual(cs.dari_art_url(""), "")
        self.assertEqual(cs.dari_art_url(None), "")


class UjiPencarianITunes(unittest.TestCase):
    def test_mengambil_artwork_dan_memperbesarnya(self):
        balasan = {"resultCount": 1, "results": [
            {"artworkUrl100": "https://is1-ssl.mzstatic.com/image/thumb/x/100x100bb.jpg"}]}
        with mock.patch.object(cs, "_ambil_json", return_value=balasan):
            self.assertEqual(cs.cari_itunes("Taylor Swift", "folklore", "august"),
                             "https://is1-ssl.mzstatic.com/image/thumb/x/600x600bb.jpg")

    def test_tanpa_hasil_balikan_kosong(self):
        with mock.patch.object(cs, "_ambil_json", return_value={"resultCount": 0, "results": []}):
            self.assertEqual(cs.cari_itunes("Xyz", "", "Zzz"), "")

    def test_balasan_tanpa_artwork_balikan_kosong(self):
        with mock.patch.object(cs, "_ambil_json", return_value={"results": [{"artistName": "X"}]}):
            self.assertEqual(cs.cari_itunes("X", "", "Y"), "")

    def test_album_dipakai_kalau_ada(self):
        dicatat = []
        with mock.patch.object(cs, "_ambil_json", side_effect=lambda u: dicatat.append(u) or {"results": []}):
            cs.cari_itunes("Taylor Swift", "folklore", "august")
        self.assertIn("folklore", dicatat[0])
        self.assertIn("entity=album", dicatat[0])

    def test_tanpa_album_jatuh_ke_judul_lagu(self):
        dicatat = []
        with mock.patch.object(cs, "_ambil_json", side_effect=lambda u: dicatat.append(u) or {"results": []}):
            cs.cari_itunes("Taylor Swift", "", "august")
        self.assertIn("august", dicatat[0])
        self.assertIn("entity=song", dicatat[0])

    def test_album_nihil_jatuh_ke_pencarian_lagu(self):
        # Diukur ke API sungguhan: entity=album sering nihil walau albumnya
        # ada, mis. "LANY a beautiful blur (deluxe)". Pencarian per lagu
        # menemukannya, dan sampul yang dibalikan tetap sampul albumnya.
        dicatat = []

        def jawab(url):
            dicatat.append(url)
            if "entity=album" in url:
                return {"results": []}
            return {"results": [{"artworkUrl100": "https://x/100x100bb.jpg"}]}

        with mock.patch.object(cs, "_ambil_json", side_effect=jawab):
            hasil = cs.cari_itunes("LANY", "a beautiful blur (deluxe)", "XXL (Stripped)")
        self.assertEqual(hasil, "https://x/600x600bb.jpg")
        self.assertEqual(len(dicatat), 2)
        self.assertIn("entity=song", dicatat[1])

    def test_album_ketemu_tidak_menembak_dua_kali(self):
        dicatat = []
        with mock.patch.object(cs, "_ambil_json", side_effect=lambda u: dicatat.append(u) or {
                "results": [{"artworkUrl100": "https://x/100x100bb.jpg"}]}):
            cs.cari_itunes("Taylor Swift", "reputation", "Dress")
        self.assertEqual(len(dicatat), 1)

    def test_hasil_tanpa_artwork_juga_jatuh_ke_lagu(self):
        # Balasan berisi tapi tanpa gambar sama saja dengan nihil.
        dicatat = []

        def jawab(url):
            dicatat.append(url)
            if "entity=album" in url:
                return {"results": [{"collectionName": "x"}]}
            return {"results": [{"artworkUrl100": "https://x/100x100bb.jpg"}]}

        with mock.patch.object(cs, "_ambil_json", side_effect=jawab):
            self.assertEqual(cs.cari_itunes("A", "B", "C"), "https://x/600x600bb.jpg")
        self.assertEqual(len(dicatat), 2)

    def test_tanpa_artis_pun_masih_dicari(self):
        dicatat = []
        with mock.patch.object(cs, "_ambil_json", side_effect=lambda u: dicatat.append(u) or {"results": []}):
            cs.cari_itunes("", "", "Bohemian Rhapsody")
        self.assertEqual(len(dicatat), 1)
        self.assertIn("Bohemian", dicatat[0])

    def test_tanpa_apa_apa_tidak_menembak_jaringan(self):
        with mock.patch.object(cs, "_ambil_json", side_effect=AssertionError("jangan ditembak")):
            self.assertEqual(cs.cari_itunes("", "", ""), "")

    def test_permintaan_selalu_bertenggat(self):
        # urlopen tanpa timeout bisa menggantung selamanya dan membekukan denyut daemon.
        with mock.patch.object(cs.urllib.request, "urlopen") as buka:
            buka.return_value.__enter__.return_value.read.return_value = b'{"results": []}'
            cs._ambil_json("https://contoh/x")
        self.assertEqual(buka.call_args.kwargs.get("timeout"), cs.TENGGANG)


class UjiPencariSampul(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.jalur = Path(self.tmp.name) / "sampul.json"
        self.panggilan = []
        self.waktu = 1000.0
        self.addCleanup(self.tmp.cleanup)

    def _pencari(self, hasil="https://cover/x.jpg", **kw):
        def cari(artis, album, judul):
            self.panggilan.append((artis, album, judul))
            if isinstance(hasil, Exception):
                raise hasil
            return hasil
        kw.setdefault("jam", lambda: self.waktu)
        return cs.PencariSampul(cari=cari, jalur=self.jalur, **kw)

    def test_url_bawaan_dipakai_tanpa_menembak_jaringan(self):
        p = self._pencari()
        lagu = dict(LAGU, sampul_mentah="https://i.scdn.co/image/abc")
        self.assertEqual(p.untuk(lagu), "https://i.scdn.co/image/abc")
        self.assertEqual(self.panggilan, [])

    def test_berkas_lokal_memicu_pencarian(self):
        p = self._pencari()
        lagu = dict(LAGU, sampul_mentah="file:///tmp/x.png")
        self.assertEqual(p.untuk(lagu), "https://cover/x.jpg")
        self.assertEqual(self.panggilan, [("Taylor Swift", "folklore", "august")])

    def test_lagu_sama_dicari_sekali_saja(self):
        p = self._pencari()
        p.untuk(LAGU)
        p.untuk(LAGU)
        self.assertEqual(len(self.panggilan), 1)

    def test_lagu_yang_tidak_ketemu_tidak_ditembak_ulang(self):
        # Tanpa singgahan negatif, lagu tak dikenal memanggil API tiap denyut.
        p = self._pencari(hasil="")
        self.assertEqual(p.untuk(LAGU), "")
        self.assertEqual(p.untuk(LAGU), "")
        self.assertEqual(len(self.panggilan), 1)

    def test_galat_jaringan_tidak_disinggahi_ke_disk(self):
        # Beda dengan "tidak ketemu": begitu internet pulih, covernya harus muncul.
        p = self._pencari(hasil=OSError("jaringan mati"))
        self.assertEqual(p.untuk(LAGU), "")
        self.assertFalse(self.jalur.exists())

    def test_galat_tidak_ditembak_ulang_selama_masa_tenang(self):
        # Tanpa rem ini satu lagu yang gagal ditembak tiap denyut, dan tiap
        # tembakan menahan denyut daemon selama tenggatnya.
        p = self._pencari(hasil=OSError("jaringan mati"), masa_tenang=60.0)
        p.untuk(LAGU)
        self.waktu += 30.0
        p.untuk(LAGU)
        self.assertEqual(len(self.panggilan), 1)

    def test_galat_dicoba_lagi_setelah_masa_tenang(self):
        p = self._pencari(hasil=OSError("jaringan mati"), masa_tenang=60.0)
        p.untuk(LAGU)
        self.waktu += 61.0
        p.untuk(LAGU)
        self.assertEqual(len(self.panggilan), 2)

    def test_masa_tenang_hanya_mengunci_lagu_yang_gagal(self):
        p = self._pencari(hasil=OSError("jaringan mati"), masa_tenang=60.0)
        p.untuk(LAGU)
        p.untuk(dict(LAGU, judul="cardigan"))
        self.assertEqual(len(self.panggilan), 2)

    def test_galat_jaringan_tidak_melempar_keluar(self):
        p = self._pencari(hasil=ValueError("JSON rusak"))
        self.assertEqual(p.untuk(LAGU), "")

    def test_lagu_kosong_balikan_kosong(self):
        p = self._pencari()
        self.assertEqual(p.untuk(None), "")
        self.assertEqual(p.untuk({}), "")
        self.assertEqual(self.panggilan, [])

    def test_singgahan_bertahan_antar_proses(self):
        self._pencari().untuk(LAGU)
        lain = self._pencari()  # instance baru, berkas yang sama
        self.assertEqual(lain.untuk(LAGU), "https://cover/x.jpg")
        self.assertEqual(len(self.panggilan), 1)

    def test_singgahan_rusak_tidak_melempar(self):
        self.jalur.parent.mkdir(parents=True, exist_ok=True)
        self.jalur.write_text("{bukan json", encoding="utf-8")
        self.assertEqual(self._pencari().untuk(LAGU), "https://cover/x.jpg")

    def test_singgahan_dibatasi_supaya_tidak_tumbuh_selamanya(self):
        p = self._pencari(batas=3)
        for i in range(5):
            p.untuk(dict(LAGU, judul=f"lagu-{i}"))
        isi = json.loads(self.jalur.read_text(encoding="utf-8"))
        self.assertEqual(len(isi), 3)
        # Yang dibuang yang paling lama masuk.
        self.assertNotIn(cs.kunci(dict(LAGU, judul="lagu-0")), isi)
        self.assertIn(cs.kunci(dict(LAGU, judul="lagu-4")), isi)

    def test_judul_beda_dicari_terpisah(self):
        p = self._pencari()
        p.untuk(LAGU)
        p.untuk(dict(LAGU, judul="cardigan"))
        self.assertEqual(len(self.panggilan), 2)

    def test_kunci_tidak_peka_huruf_besar(self):
        self.assertEqual(cs.kunci(LAGU), cs.kunci({k: str(v).upper() for k, v in LAGU.items()}))


class UjiJalurSinggahan(unittest.TestCase):
    """Service-nya berjalan dalam sandbox systemd yang bikin ~/.cache
    read-only, jadi jalurnya harus ikut yang disodorkan systemd."""

    def _lingkungan(self, **isi):
        bersih = {k: v for k, v in os.environ.items()
                  if k not in ("CACHE_DIRECTORY", "XDG_CACHE_HOME")}
        bersih.update(isi)
        return mock.patch.dict(os.environ, bersih, clear=True)

    def test_cache_directory_dari_systemd_dipakai(self):
        with self._lingkungan(CACHE_DIRECTORY="/home/x/.cache/lagi-ngapain"):
            self.assertEqual(cs.jalur_singgahan(),
                             Path("/home/x/.cache/lagi-ngapain/sampul.json"))

    def test_cache_directory_majemuk_ambil_yang_pertama(self):
        # systemd memisahkan beberapa direktori dengan titik dua.
        with self._lingkungan(CACHE_DIRECTORY="/satu/lagi-ngapain:/dua/lain"):
            self.assertEqual(cs.jalur_singgahan(), Path("/satu/lagi-ngapain/sampul.json"))

    def test_cache_directory_kosong_diabaikan(self):
        with self._lingkungan(CACHE_DIRECTORY="", XDG_CACHE_HOME="/tmp/c"):
            self.assertEqual(cs.jalur_singgahan(), Path("/tmp/c/lagi-ngapain/sampul.json"))

    def test_tanpa_systemd_jatuh_ke_xdg(self):
        with self._lingkungan(XDG_CACHE_HOME="/tmp/c"):
            self.assertEqual(cs.jalur_singgahan(), Path("/tmp/c/lagi-ngapain/sampul.json"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
