# cc-presence

Discord Rich Presence untuk **Claude Code CLI** di Linux.

Menampilkan proyek yang sedang dikerjakan, apa yang sedang dilakukan, berapa
sesi yang aktif, dan sudah berapa lama — langsung di profil Discord.

```
Claude Code
📁 aio-lcd +1 lainnya
Menjalankan perintah · 2 sesi aktif
01:23 elapsed
```

Tanpa dependensi. Cuma Python 3 pustaka baku dan bash.

---

## Cara kerja

Hook Claude Code berumur sangat pendek — prosesnya mati begitu selesai, dan
Rich Presence ikut hilang saat soketnya tertutup. Jadi hook **tidak** bicara
ke Discord. Pembagiannya:

```
hook (tulis JSON, keluar)  →  spool di XDG_RUNTIME_DIR  →  daemon (pegang soket IPC)
      ~1,3 ms                     tmpfs, langsung dihapus       menerbitkan tiap ≥15 dtk
```

Hook sengaja tidak memanggil interpreter, tidak mengurai JSON, dan tidak
menyentuh jaringan — dia jalan di setiap tool call, jadi biayanya harus
mendekati nol. Kalau daemonnya mati, direktori spool tidak ada dan hook
langsung keluar tanpa menulis apa pun.

Daemon berbicara protokol Discord IPC secara langsung (bingkai
`<opcode u32 LE><panjang u32 LE><JSON>` lewat soket domain Unix). Hanya empat
opcode yang dipakai, jadi memasang `pypresence` — yang butuh venv karena pip
sistem terkunci PEP 668 — tidak sepadan.

## Privasi

Rich Presence terbaca oleh **seluruh daftar teman**. Bawaannya karena itu
sengaja kasar: jalur berkas, isi perintah, dan teks prompt tidak pernah
ditampilkan kecuali diminta.

| mode | yang tampil |
|---|---|
| `minimal` | "Sedang ngoding" — tidak ada nama proyek |
| `normal` *(bawaan)* | nama folder proyek + jenis kegiatan |
| `detail` | tambah nama berkas yang disunting / perintah yang dijalankan |

Bahkan di `detail`, perintah Bash dipotong ke **kata pertama saja** — jadi
`psql -U admin -W hunter2 -h db.internal` tampil sebagai `psql`.

Proyek yang namanya tidak boleh tampil sama sekali didaftarkan di
`proyek_privat`; namanya diganti "proyek privat".

## Pasang

```bash
./pasang.sh
```

Pemasang akan meminta **Application ID** Discord. Bikin dulu:

1. buka <https://discord.com/developers/applications>
2. **New Application**, namai persis `Claude Code` — nama aplikasi ini yang
   jadi baris paling atas di presence, dan tidak bisa diganti per pembaruan
3. salin **Application ID** di halaman *General Information*

Tidak perlu bot, token, maupun OAuth. Application ID bukan rahasia.

Pemasang menyunting `~/.claude/settings.json` (dicadangkan dulu ke
`settings.json.sebelum-cc-presence`) dan hanya menyisipkan entri miliknya —
hook alat lain seperti `rtk` atau `context-mode` tidak disentuh.

> Hook cuma aktif di sesi Claude Code yang dibuka **setelah** pemasangan.

## Pakai

```bash
./cc_daemon.py --status              # konfig, soket, keadaan spool
systemctl --user restart cc-presence # setelah mengubah konfig
journalctl --user -u cc-presence -f  # lihat apa yang diterbitkan
./copot.sh                           # cabut hook + service
```

Konfigurasi: `~/.config/cc-presence/konfig.json`

| kunci | bawaan | arti |
|---|---|---|
| `client_id` | — | Application ID Discord |
| `mode` | `normal` | tingkat privasi (lihat di atas) |
| `proyek_privat` | `[]` | nama folder yang disamarkan |
| `jeda_publish` | `15` | jarak minimum antar penerbitan, detik |
| `ttl_sesi` | `900` | sesi sediam ini dianggap mati, detik |
| `tampilkan_timer` | `true` | tampilkan lama sesi |

`jeda_publish` tidak bisa turun di bawah 15 detik — Discord membatasi laju
`SET_ACTIVITY` (~5 per 20 detik), dan tool call beruntun akan menjebolnya.

## Catatan Linux

**Discord Flatpak menaruh soketnya di tempat lain.** Bukan di akar
`$XDG_RUNTIME_DIR`, tapi di `$XDG_RUNTIME_DIR/app/com.discordapp.Discord/`.
Daemon menggeledah keduanya (plus jalur Snap) alih-alih bergantung pada
symlink — symlink ke soket Flatpak menggantung setiap kali Discord ditutup.

**Presence tidak nyangkut.** Kalau terminal ditutup paksa, `SessionEnd` tidak
sempat jalan; sesi yang diam melewati `ttl_sesi` dibuang sendiri. Discord
ditutup di tengah jalan pun aman — daemon menyambung ulang tiap 10 detik dan
menerbitkan ulang, karena presence hilang saat koneksi putus.

## Uji

```bash
python3 uji_semua.py
```

87 uji, tanpa Discord yang menyala — bagian IPC-nya diuji lewat server soket
palsu yang bicara protokol yang sama.

## Lisensi

GPL-3.0
