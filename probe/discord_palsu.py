"""Discord palsu sbg proses terpisah, supaya bisa dibunuh sungguhan."""
import json, os, socket, struct, sys
jalur = sys.argv[1]
try: os.unlink(jalur)
except OSError: pass
srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
srv.bind(jalur); srv.listen(1)
print("server siap", flush=True)
while True:
    c, _ = srv.accept()
    with c:
        while True:
            hdr = c.recv(8)
            if len(hdr) < 8: break
            op, n = struct.unpack("<II", hdr)
            muatan = json.loads(c.recv(n) or b"{}") if n else {}
            if op == 0:
                balas = {"cmd": "DISPATCH", "evt": "READY"}
            else:
                act = (muatan.get("args") or {}).get("activity")
                print("TERIMA:", act and act.get("details"), flush=True)
                balas = {"cmd": "SET_ACTIVITY"}
            b = json.dumps(balas).encode()
            c.sendall(struct.pack("<II", 1, len(b)) + b)
