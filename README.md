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

## Lagu yang sedang diputar

Saat tidak ada sesi yang sedang bekerja — atau tidak ada sesi sama sekali —
presence berpindah menampilkan lagu yang sedang diputar:

```
Terminal                          Terminal
📁 cc-presence          →         ♪ NIKI — Did You Like Her In The Morning?
Ngoprek terminal                  Lagi dengerin
   (lagi ngoding)                    (nganggur)
```

Keduanya sengaja tidak pernah tampil bersamaan: Discord cuma punya dua baris
teks, jadi menggabungkannya membuat dua-duanya terpotong.

Sumbernya **MPRIS** di D-Bus sesi lewat `busctl` — bukan pustaka D-Bus, karena
pip sistem terkunci PEP 668 dan `busctl` sudah pasti ada (bagian dari systemd).
Hampir semua pemutar di Linux mengumumkan diri lewat MPRIS: Spotify, VLC, mpv,
dan tab browser termasuk.

**Yang perlu disadari soal browser.** Tab browser mengumumkan judul apa pun
yang sedang diputar, bukan cuma musik — judul video YouTube ikut tampil. Yang
**tidak** terbaca: judul tab biasa (GNOME Wayland menutup itu, dan MPRIS memang
hanya mengumumkan media), halaman tanpa media, dan video yang dijeda.

Kalau itu tidak diinginkan:

```bash
./cc_daemon.py --musik off      # matikan seketika, service dimuat ulang
./cc_daemon.py --musik on
```

Atau tutup pemutar tertentu saja lewat `abaikan_pemutar` di konfig, mis.
`["brave", "firefox"]` — Spotify tetap terbaca, browser tidak.

### Kata di pojok atas

Baris teratas presence adalah `<jenis> <nama aplikasi>`, dan dua-duanya bisa
diatur. Nama aplikasi diganti di Developer Portal (Application ID tidak
berubah); jenisnya lewat konfig:

| nilai | tampil |
|---|---|
| `0` | Playing *(bawaan saat ngoding)* |
| `2` | Listening to *(bawaan saat dengerin)* |
| `3` | Watching |
| `5` | Competing in |

`1` (Streaming) sengaja ditolak: diuji langsung ke Discord, nilainya diterima
tapi tidak dikembalikan — dia menuntut URL Twitch/YouTube yang sah. Jatuh ke
bawaan lebih baik daripada diam-diam kehilangan jenisnya.

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

Mode `minimal` juga menutup judul lagu, bukan cuma nama proyek — judul lagu
sama personalnya.

**Dua sumber data, tidak ada yang lain:** muatan hook Claude Code (`cwd`,
nama alat, id sesi) dan MPRIS di D-Bus sesi. Judul jendela, isi berkas,
ketikan, dan papan klip tidak pernah disentuh.

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

> Claude Code membaca ulang `settings.json` saat itu juga, jadi sesi yang
> **sedang berjalan** pun langsung ikut terpantau — tidak perlu dibuka ulang.
> (Diuji langsung: presence terbit ~15 detik setelah `pasang.sh` selesai,
> dari sesi yang sudah jalan sebelum pemasangan.)

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
| `musik` | `true` | tampilkan lagu saat tidak ada yang dikerjakan |
| `abaikan_pemutar` | `[]` | awalan nama pemutar yang tidak boleh dibaca |
| `label` | `{}` | timpaan teks kegiatan, mis. `{"Bash": "Ngetik perintah"}` |
| `tipe_kerja` | `0` | kata pojok atas saat ngoding (lihat di bawah) |
| `tipe_musik` | `2` | kata pojok atas saat dengerin |

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

139 uji, tanpa Discord yang menyala — bagian IPC-nya diuji lewat server soket
palsu yang bicara protokol yang sama, dan bagian MPRIS-nya lewat jawaban
`busctl` palsu.

### Mengubah kata-katanya

Semua teks kegiatan bisa ditimpa dari konfig tanpa menyentuh kode:

```json
{ "label": { "Bash": "Ngetik perintah", "idle": "Rehat dulu" } }
```

Kunci yang tidak disebut memakai bawaan di `cc_state.LABEL_BAWAAN`. Selain
nama alat, ada empat kunci khusus: `mcp`, `lainnya` (cadangan, `{alat}`
diganti nama alatnya), `berpikir`, `idle`, dan `dengerin`.

## Lisensi

GPL-3.0
