"""Probe pemulihan koneksi -- jalankan: python3 probe/pulih_koneksi.py

Bukan bagian dari uji_semua.py: makan ~40 detik karena harus menunggu jeda
sambung-ulang yang sesungguhnya. Yang dibuktikan di sini tidak bisa dibuktikan
uji satuan -- daemon SUNGGUHAN menghadapi soket yang benar-benar hilang lalu
kembali, lengkap dengan broken pipe dan penerbitan ulangnya.

Discord sungguhan tidak disentuh; yang dimatikan server palsu di direktori
sementara. Versi pertama probe ini keliru: server palsunya thread, dan
thread yang nyangkut di recv() tidak pernah mati -- jadi "Discord ditutup"
tidak pernah terjadi dan vonisnya salah semua. Karena itu sekarang server
palsunya proses terpisah yang bisa di-kill sungguhan.
"""
import json, os, signal, subprocess, sys, tempfile, threading, time
from pathlib import Path
DIR = "/home/ram/workspace/projects/cc-presence"
SP = os.path.dirname(os.path.abspath(__file__))

tmp = tempfile.mkdtemp()
runtime = Path(tmp, "run"); runtime.mkdir()
conf = Path(tmp, "conf", "cc-presence"); conf.mkdir(parents=True)
(conf / "konfig.json").write_text(json.dumps({"client_id": "123456789", "musik": False}))
soket = str(runtime / "discord-ipc-0")

def hidupkan_server():
    return subprocess.Popen([sys.executable, f"{SP}/discord_palsu.py", soket],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

srv = hidupkan_server(); time.sleep(0.8)
env = {**os.environ, "XDG_RUNTIME_DIR": str(runtime), "XDG_CONFIG_HOME": str(Path(tmp, "conf"))}
d = subprocess.Popen([sys.executable, f"{DIR}/cc_daemon.py"], env=env,
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
baris = []
threading.Thread(target=lambda: [baris.append(l.rstrip()) or print("   ", l.rstrip(), flush=True)
                                 for l in d.stdout], daemon=True).start()
time.sleep(2)
(runtime / "cc-presence" / "ev" / "1.json").write_text(json.dumps({
    "session_id": "a", "hook_event_name": "PreToolUse",
    "cwd": "/home/ram/workspace/projects/uji", "tool_name": "Bash"}))
time.sleep(4)

print("\n>>> DISCORD DITUTUP (proses dibunuh + soket dihapus)\n", flush=True)
srv.kill(); srv.wait()
try: os.unlink(soket)
except OSError: pass
batas = len(baris)
time.sleep(14)

print("\n>>> DISCORD DIBUKA LAGI\n", flush=True)
srv = hidupkan_server()
time.sleep(18)
d.terminate(); d.wait(timeout=10); srv.kill()

sesudah = "\n".join(baris[batas:])
semua = "\n".join(baris)
print("\n=== VONIS ===")
print("putus terdeteksi      :", "YA" if "koneksi putus" in semua else "TIDAK")
print("nyambung ulang sendiri:", "YA" if "tersambung ke Discord" in sesudah else "TIDAK")
print("presence terbit lagi  :", "YA" if "\U0001f4c1 uji" in sesudah else "TIDAK")
print("daemon tetap hidup    :", "YA" if "daemon berhenti" not in "\n".join(baris[batas:batas+3]) else "TIDAK")
