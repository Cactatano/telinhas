#!/usr/bin/env python3
"""Telinhas Ponte: serve o Telinhas em http://localhost:8787 e deixa ele agir no seu PC (Windows).
Só usa o Python que já vem instalado.   Uso:  python ponte.py [--abrir] [--atalho]"""
import ctypes, json, os, re, subprocess, sys, threading, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORTA", 8787))
HERE = os.path.dirname(os.path.abspath(__file__))
WIN = os.name == "nt"
KEYS = {"mute": 0xAD, "voldown": 0xAE, "volup": 0xAF, "next": 0xB0, "prev": 0xB1, "stop": 0xB2, "play": 0xB3}
URI = re.compile(r"^[a-z][a-z0-9+.\-]+:", re.I)  # esquema de 2+ letras: nada de caminhos de arquivo (C:\...)
BLOQ = ("file:", "javascript:", "data:", "vbscript:", "search-ms:", "ms-msdt:", "ms-officecmd:")
STATIC = {"/manifest.webmanifest": "application/manifest+json", "/sw.js": "text/javascript", "/ponte.py": "text/plain",
          "/icon-192.png": "image/png", "/icon-512.png": "image/png", "/icon-maskable.png": "image/png", "/telinhas.ico": "image/x-icon"}

class FT(ctypes.Structure):
    _fields_ = [("l", ctypes.c_uint32), ("h", ctypes.c_uint32)]

class MS(ctypes.Structure):
    _fields_ = [("n", ctypes.c_uint32), ("load", ctypes.c_uint32)] + [(x, ctypes.c_uint64) for x in ("a", "b", "c", "d", "e", "f", "g")]

_ult = None
def cpu():
    global _ult
    if WIN:
        i, k, u = FT(), FT(), FT()
        ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(i), ctypes.byref(k), ctypes.byref(u))
        idle, tot = (i.h << 32) | i.l, ((k.h << 32) | k.l) + ((u.h << 32) | u.l)
    else:
        v = [int(x) for x in open("/proc/stat").readline().split()[1:]]
        idle, tot = v[3], sum(v)
    ant, _ult = _ult, (idle, tot)
    if not ant or tot == ant[1]:
        return 0
    return max(0, min(100, round(100 * (1 - (idle - ant[0]) / (tot - ant[1])))))

def ram():
    if WIN:
        m = MS(); m.n = ctypes.sizeof(m)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return m.load
    d = {l.split(":")[0]: int(l.split()[1]) for l in open("/proc/meminfo")}
    return round(100 * (1 - d["MemAvailable"] / d["MemTotal"]))

def gpu():
    try:
        s = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,temperature.gpu", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=2).stdout.split("\n")[0].split(",")
        return int(s[0]), int(s[1])
    except Exception:
        return None, None

def spotify():
    """Título da janela do Spotify no Windows: 'Artista - Música' quando está tocando."""
    if not WIN:
        return None
    u, k = ctypes.windll.user32, ctypes.windll.kernel32
    u.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]
    u.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    u.IsWindowVisible.argtypes = [ctypes.c_void_p]
    u.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
    k.OpenProcess.restype = ctypes.c_void_p
    k.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_uint32]
    k.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint32)]
    k.CloseHandle.argtypes = [ctypes.c_void_p]
    found = []
    EP = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(h, _):
        try:
            n = u.GetWindowTextLengthW(h)
            if n and u.IsWindowVisible(h):
                buf = ctypes.create_unicode_buffer(n + 1); u.GetWindowTextW(h, buf, n + 1)
                pid = ctypes.c_uint32(); u.GetWindowThreadProcessId(h, ctypes.byref(pid))
                ph = k.OpenProcess(0x1000, False, pid.value)
                if ph:
                    s = ctypes.create_unicode_buffer(520); sz = ctypes.c_uint32(520)
                    if k.QueryFullProcessImageNameW(ph, 0, s, ctypes.byref(sz)) and s.value.lower().endswith("spotify.exe"):
                        found.append(buf.value)
                    k.CloseHandle(ph)
        except Exception:
            pass
        return True
    u.EnumWindows(EP(cb), 0)
    for t in found:
        if t.strip() and not t.startswith("Spotify") and t not in ("GDI+ Window", "Default IME", "MSCTFIME UI"):
            return t
    return "Spotify" if found else None

def media():
    t = spotify()
    return {"app": "Spotify" if t else None, "playing": bool(t and " - " in t and not t.startswith("Spotify")), "title": t or ""}

def abrir(v):
    if WIN: os.startfile(v)
    else: subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", v])

def tecla(k):
    if not WIN: raise OSError("teclas de mídia só no Windows")
    c = KEYS[k]; u = ctypes.windll.user32
    u.keybd_event(c, 0, 0, 0); u.keybd_event(c, 0, 2, 0)

def janela(url):
    try:
        if WIN: subprocess.Popen(["cmd", "/c", "start", "", "msedge", "--app=" + url]); return
    except Exception:
        pass
    webbrowser.open(url)

def atalho():
    if not WIN: raise OSError("criar atalho só funciona no Windows")
    py = sys.executable; pw = os.path.join(os.path.dirname(py), "pythonw.exe"); alvo = pw if os.path.exists(pw) else py
    q = lambda s: s.replace("'", "''")
    ps = ("$d=[Environment]::GetFolderPath('Desktop');$s=(New-Object -ComObject WScript.Shell).CreateShortcut($d+'\\Telinhas.lnk');"
          "$s.TargetPath='" + q(alvo) + "';$s.Arguments='\"" + q(os.path.join(HERE, "ponte.py")) + "\" --abrir';"
          "$s.WorkingDirectory='" + q(HERE) + "';$s.IconLocation='" + q(os.path.join(HERE, "telinhas.ico")) + "';$s.Description='Telinhas';$s.Save()")
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], capture_output=True, text=True, timeout=25)
    if r.returncode: raise OSError(r.stderr.strip() or "o PowerShell falhou")

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def out(self, code, corpo, tipo="application/json"):
        b = corpo if isinstance(corpo, bytes) else json.dumps(corpo).encode()
        self.send_response(code); self.send_header("Content-Type", tipo + "; charset=utf-8")
        self.send_header("Content-Length", str(len(b))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(b)
    def host_ok(self):  # protege contra DNS rebinding
        return self.headers.get("Host", "").split(":")[0] in ("localhost", "127.0.0.1")
    def do_GET(self):
        if not self.host_ok(): return self.out(403, {"erro": "host"})
        p = self.path.split("?")[0]
        if p in ("/", "/index.html"):
            return self.out(200, open(os.path.join(HERE, "index.html"), "rb").read(), "text/html")
        if p in STATIC and os.path.exists(os.path.join(HERE, p[1:])):
            return self.out(200, open(os.path.join(HERE, p[1:]), "rb").read(), STATIC[p])
        if p == "/api/ping": return self.out(200, {"ok": True, "win": WIN})
        if p == "/api/stats":
            g, gt = gpu(); return self.out(200, {"cpu": cpu(), "ram": ram(), "gpu": g, "gt": gt})
        if p == "/api/media": return self.out(200, media())
        self.out(404, {"erro": "não achei"})
    def do_POST(self):
        origem = self.headers.get("Origin")
        if not self.host_ok() or self.headers.get("X-Telinhas") != "1" or (origem and origem.split("//")[-1].split(":")[0] not in ("localhost", "127.0.0.1")):
            return self.out(403, {"erro": "negado"})
        try:
            d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            if self.path == "/api/open":
                v = str(d.get("v", "")).strip()
                if not URI.match(v) or v.lower().startswith(BLOQ): return self.out(400, {"erro": "endereço não permitido"})
                abrir(v)
            elif self.path == "/api/key":
                if d.get("k") not in KEYS: return self.out(400, {"erro": "tecla desconhecida"})
                tecla(d["k"])
            elif self.path == "/api/atalho":
                atalho()
            else: return self.out(404, {"erro": "não achei"})
            self.out(200, {"ok": True})
        except Exception as e:
            self.out(500, {"erro": str(e)})

if __name__ == "__main__":
    args = sys.argv[1:]
    if "--atalho" in args:
        try: atalho(); print("Atalho criado na área de trabalho.")
        except Exception as e: print("Não consegui criar o atalho:", e)
        sys.exit()
    url = f"http://localhost:{PORT}"
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    except OSError:
        print("A ponte já está ligada em", url)
        if "--abrir" in args: janela(url)
        sys.exit()
    print(f"Telinhas Ponte ligada: abra {url}  (Ctrl+C para parar)")
    if "--abrir" in args: threading.Timer(0.8, janela, [url]).start()
    try: srv.serve_forever()
    except KeyboardInterrupt: print("\nPonte desligada.")
