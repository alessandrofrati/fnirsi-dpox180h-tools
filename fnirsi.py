"""FNIRSI DPOX180H: copy the saved waveforms off the scope's USB disk and decode them.

On macOS the scope's mass-storage firmware hangs on the large reads the system normally
issues for file data (directory listings work, a plain cp stops at 0 bytes). Reading
4 kB at a time with the cache disabled (F_NOCACHE) works every time. Every access to the
scope (copy, thumbnail, delete) runs in a child process with a timeout, because a hung
read cannot be interrupted: if it happens, unplug and replug the USB cable.

Waveform file (.wav, not audio), as written by firmware V40. Every field is big-endian.
A table of 7 u32 at the start: settings offset/length, thumbnail offset/length, data
offset/length, file length. Samples are u16 starting exactly at table[4], 1600 counts per
vertical division (8 divisions on screen): all of CH1, then all of CH2.
Settings: CH1 block at 0x40, CH2 block at 0x80 (stride 0x40):
  +0x26 channel on (u8), +0x32 V/div in µV (low half of a u64), +0x3E zero position in
  pixels from the bottom (u16, 25 px per division); 0x12D samples per channel (u32);
  0x11D samples of one acquisition = one screen (u32); 0x13D sample rate in Hz (low half
  of a u64); 0x1D8 time per division in ps (low 40 bits of a u64).
Each channel holds several acquisitions of the same 12-division window, one after the
other (2 at 1 ms/div, up to 10 at 50 ns/div). The first one is what the screen showed
(it matches the thumbnail); the others are separate acquisitions, not a longer record.
Thumbnail: u16 width, u16 height, then RGB565 pixels, all big-endian, top row first.
Screenshot (.bmp): plain 320x240 RGB565 BMP, pixels at 0x2710; a 75x36 thumbnail sits at
0x46 (u16 width, u16 height, RGB565 pixels, little-endian, top row first).

Usage:
  fnirsi.py scarica [--dest DIR] [--csv] [--espelli]   copy new Waveform/*.wav (+ Screenshots)
  fnirsi.py visore [--porta N] [--dest DIR] [--csv] [--no-browser]
                                                        viewer in the browser: choose files by
                                                        thumbnail, download, delete, eject
  fnirsi.py info FILE.wav ...                           settings read from the header
  fnirsi.py csv [--acquisizione N] FILE.wav ...         write FILE.csv (time s; volts)
"""
import fcntl, glob, os, struct, subprocess, sys, time, zlib

COUNTS_PER_DIV, PX_PER_DIV = 1600, 25
F_NOCACHE, F_RDAHEAD = 48, 45
SUBDIRS = (("Waveform", ".wav"), ("Screenshots", ".bmp"))


def _u(b, o, n):
    return int.from_bytes(b[o:o + n], "big")


def parse(data, acq=1):
    """Decode acquisition number acq (1 = the one shown on screen).
    Return dict: tdiv (s), dt (s), rate, samples, acquisitions, acq,
    channels [{name, on, vdiv, zero_div, volts}]."""
    tab = [_u(data, i * 4, 4) for i in range(7)]
    if not (tab[0] == 0x32 and tab[6] == len(data) and tab[4] + tab[5] == tab[6]):
        raise ValueError("non sembra un file di forma d'onda FNIRSI")
    start = tab[4]
    n = tab[5] // 2
    tdiv = _u(data, 0x1D8, 5) / 1e12
    rate = _u(data, 0x13D, 4)
    on = [data[0x66] == 1, data[0xA6] == 1]
    if not any(on):
        on = [True, False]
    nch = sum(on)
    per = _u(data, 0x12D, 4)              # samples per channel in the file
    if not 0 < per * nch <= n:
        per = n // nch
    frame = _u(data, 0x11D, 4)            # samples of one acquisition
    if not (0 < frame <= per and per % frame == 0):
        frame = per
    nacq = per // frame
    if not 1 <= acq <= nacq:
        raise ValueError(f"acquisizione {acq} inesistente (il file ne ha {nacq})")
    dt = 1 / rate if rate else tdiv / 1000
    chans = []
    o = 0
    for k, base in ((0, 0x40), (1, 0x80)):
        vdiv = _u(data, base + 0x32, 4) / 1e6
        zero = (_u(data, base + 0x3E, 2) - 2) / PX_PER_DIV
        if not on[k]:
            chans.append({"name": f"CH{k + 1}", "on": False, "vdiv": vdiv, "zero_div": zero, "volts": []})
            continue
        a = start + 2 * (o + (acq - 1) * frame)
        seg = [int.from_bytes(data[a + 2 * i:a + 2 * i + 2], "big") for i in range(frame)]
        o += per
        lead = 0                      # each acquisition starts with a few zero samples
        while lead < min(100, len(seg)) and (seg[lead] == 0 or (lead == 0 and len(seg) > 1 and seg[1] == 0)):
            lead += 1
        volts = [None] * lead + [(c / COUNTS_PER_DIV - zero) * vdiv for c in seg[lead:]]
        chans.append({"name": f"CH{k + 1}", "on": True, "vdiv": vdiv, "zero_div": zero, "volts": volts})
    return {"tdiv": tdiv, "dt": dt, "rate": rate, "samples": frame, "acquisitions": nacq,
            "acq": acq, "channels": chans}


def write_csv(path, w):
    on = [c for c in w["channels"] if c["on"]]
    with open(path, "w") as fh:
        fh.write("tempo_s;" + ";".join(c["name"] + "_V" for c in on) + "\n")
        for i in range(w["samples"]):
            vals = ["" if c["volts"][i] is None else f"{c['volts'][i]:.6f}" for c in on]
            fh.write(f"{i * w['dt']:.9g};" + ";".join(vals) + "\n")


def _fmt(x, unit):
    for f, p in ((1, ""), (1e-3, "m"), (1e-6, "µ"), (1e-9, "n")):
        if abs(x) >= f:
            return f"{x / f:g} {p}{unit}"
    return f"{x:g} {unit}"


def info(path):
    w = parse(open(path, "rb").read())
    chs = ", ".join(f"{c['name']} {_fmt(c['vdiv'], 'V')}/div" for c in w["channels"] if c["on"])
    acq = f", {w['acquisitions']} acquisizioni" if w["acquisitions"] > 1 else ""
    return (f"{os.path.basename(path)}: {_fmt(w['tdiv'], 's')}/div, {chs}, "
            f"{w['samples']} campioni a {_fmt(w['dt'], 's')} ({_fmt(w['samples'] * w['dt'], 's')}){acq}")


# ---------- thumbnails ----------

def thumbnail(head, kind):
    """Return (width, height, RGB bytes) of the thumbnail in the first bytes of a file."""
    if kind == "wav":
        off = _u(head, 8, 4)
        order = "big"
    else:
        if head[:2] != b"BM":
            raise ValueError("non è un BMP")
        off = 0x46
        order = "little"
    w = int.from_bytes(head[off:off + 2], order)
    h = int.from_bytes(head[off + 2:off + 4], order)
    if not (0 < w <= 320 and 0 < h <= 240) or len(head) < off + 4 + w * h * 2:
        raise ValueError("miniatura assente")
    px = head[off + 4:off + 4 + w * h * 2]
    rgb = bytearray()
    for i in range(0, len(px), 2):
        v = int.from_bytes(px[i:i + 2], order)
        rgb += bytes(((v >> 11 & 31) * 255 // 31, (v >> 5 & 63) * 255 // 63, (v & 31) * 255 // 31))
    return w, h, bytes(rgb)


def thumb_bytes_needed(kind):
    # wav: table + settings (~0x3D0) + 4 + 102*54*2; bmp: 0x46 + 4 + 75*36*2
    return 16384 if kind == "wav" else 8192


def png(w, h, rgb):
    raw = b"".join(b"\0" + rgb[y * w * 3:(y + 1) * w * 3] for y in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


# ---------- access to the scope (always in a child process) ----------

def _open_nocache(src):
    fd = os.open(src, os.O_RDONLY)
    fcntl.fcntl(fd, F_NOCACHE, 1)
    fcntl.fcntl(fd, F_RDAHEAD, 0)
    return fd


def copy_small(src, dst):
    """Copy 4 kB at a time without cache (the scope hangs on large reads)."""
    fd = _open_nocache(src)
    try:
        with open(dst + ".part", "wb") as out:
            while True:
                b = os.read(fd, 4096)
                if not b:
                    break
                out.write(b)
    finally:
        os.close(fd)
    os.replace(dst + ".part", dst)


def read_head_small(src, n):
    fd = _open_nocache(src)
    try:
        out = bytearray()
        while len(out) < n:
            b = os.read(fd, min(4096, n - len(out)))
            if not b:
                break
            out += b
        return bytes(out)
    finally:
        os.close(fd)


def _child(args, timeout):
    """Run this script with args in a child process; return (ok, stdout bytes)."""
    p = subprocess.Popen([sys.executable, os.path.abspath(__file__)] + args,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        out, _ = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        p.communicate()
        raise TimeoutError("lettura bloccata")
    return p.returncode == 0, out


def scope_head(src, n):
    ok, out = _child(["_testa", src, str(n)], 20)
    if not ok:
        raise OSError("lettura non riuscita")
    return out


def scope_delete(src):
    ok, _ = _child(["_cancella", src], 20)
    if not ok or os.path.exists(src):
        raise OSError("cancellazione non riuscita")


def find_scope():
    """Mounted FAT volumes that contain a Waveform folder (the scope shows up as NO NAME)."""
    out = subprocess.run(["mount"], capture_output=True, text=True).stdout
    vols = [l.split(" on ", 1)[1].rsplit(" (", 1)[0] for l in out.splitlines() if "(msdos" in l]
    return [v for v in vols if os.path.isdir(os.path.join(v, "Waveform"))]


def scope_listing(vol):
    """Files on the scope as [(relative path 'Waveform/1.wav', full path, size)], in order."""
    res = []
    for sub, ext in SUBDIRS:
        d = os.path.join(vol, sub)
        if os.path.isdir(d):
            names = [x for x in os.listdir(d) if x.lower().endswith(ext) and not x.startswith(".")]
            names.sort(key=lambda x: (len(x), x))
            for x in names:
                full = os.path.join(d, x)
                try:
                    res.append((f"{sub}/{x}", full, os.path.getsize(full)))
                except OSError:
                    pass
    return res


def scarica(dest, csv=False, eject=False, log=print, copied_paths=None, only=None, present_paths=None):
    """Copy new files; return 0 ok, 3 scope not found, 4 read hung.
    Paths of the copied files are appended to copied_paths if given, those already in
    dest (identical) to present_paths; only, if given, is a set of relative paths
    ('Waveform/1.wav') to consider."""
    print = log
    vols = find_scope()
    if not vols:
        print("Oscilloscopio non trovato: collegalo e attendi che compaia come disco (NO NAME).")
        return 3
    vol = vols[0]
    os.makedirs(dest, exist_ok=True)
    todo = [(full, rel.split("/", 1)[1], size) for rel, full, size in scope_listing(vol)
            if only is None or rel in only]
    print(f"{vol}: {len(todo)} file")
    copied = 0
    for src, name, size in todo:
        dst = os.path.join(dest, name)
        # The scope restarts its numbering after a deletion: never overwrite a
        # different file with the same name, add a suffix instead.
        if os.path.exists(dst):
            try:
                same = os.path.getsize(dst) == size and _same_head(src, dst)
            except TimeoutError:
                print(f"  {name}: lettura bloccata. Stacca e riattacca l'USB, poi rilancia.")
                return 4
            if same:
                if present_paths is not None:
                    present_paths.append(dst)
                continue
            stem, ext = os.path.splitext(name)
            k = 2
            while os.path.exists(os.path.join(dest, f"{stem}_{k}{ext}")):
                k += 1
            dst = os.path.join(dest, f"{stem}_{k}{ext}")
        try:
            ok, _ = _child(["_copia", src, dst], 30)
        except TimeoutError:
            print(f"  {name}: lettura bloccata. Stacca e riattacca l'USB, poi rilancia.")
            return 4
        if not ok or not os.path.exists(dst) or os.path.getsize(dst) != size:
            print(f"  {name}: copia non riuscita")
            continue
        copied += 1
        if copied_paths is not None:
            copied_paths.append(dst)
        line = f"  {name} -> {os.path.basename(dst)}"
        if dst.endswith(".wav"):
            try:
                line += "   " + info(dst).split(": ", 1)[1]
                if csv:
                    write_csv(dst[:-4] + ".csv", parse(open(dst, "rb").read()))
            except ValueError as e:
                line += f"   ({e})"
        print(line)
    print(f"copiati {copied} file nuovi in {dest}")
    if eject:
        r = subprocess.run(["diskutil", "eject", vol], capture_output=True, text=True)
        print(r.stdout.strip() or r.stderr.strip())
    return 0


def _same_head(a, b):
    """Compare the first 4 kB (small no-cache read on the scope side)."""
    ha = scope_head(a, 4096)
    with open(b, "rb") as fh:
        return fh.read(len(ha)) == ha


# ---------- viewer with download, thumbnails and delete ----------

HERE = os.path.dirname(os.path.abspath(__file__))
VIEWER = os.path.join(HERE, "visore_fnirsi_dpox180h.html")
# downloads go to misure/ next to the project folder (change with --dest)
MISURE = os.path.join(os.path.dirname(HERE), "misure")


def default_dest():
    return os.path.join(MISURE, "oscilloscopio_" + time.strftime("%Y%m%d"))


def visore(port=8765, dest=None, csv=False, open_browser=True):
    """Serve the viewer on 127.0.0.1 with an API for its buttons.

    GET  /                        the viewer
    GET  /api/stato               is the scope mounted, how many files it holds
    GET  /api/elenco              files on the scope (path, type, size)
    GET  /api/miniatura?f=REL     thumbnail as PNG; header X-Copiato names a local copy
    POST /api/scarica             body {"file": [REL, ...]} or empty for all new files
    POST /api/cancella            body {"file": [REL, ...]}: delete on the scope
    POST /api/espelli             eject the scope's disk
    GET  /api/file/NAME           a file copied into the destination folder
    POSTs must carry the header X-Fnirsi: 1, which a foreign web page cannot send
    without a CORS preflight (never answered), and the Host must be local.
    """
    import http.server, json, threading, urllib.parse, webbrowser
    scope_lock = threading.Lock()           # one access to the scope at a time
    state = {"dest": dest}
    heads = {}                               # (full path, size, mtime) -> head bytes
    local_heads = {}                         # local path -> (size, mtime, head)

    def cur_dest():
        return state["dest"] or default_dest()

    def local_copy(kind, size, head):
        """A file already on the Mac with the same size and the same head, or None."""
        n = len(head)
        for p in glob.glob(os.path.join(MISURE, "**", "*." + kind), recursive=True) + \
                glob.glob(os.path.join(cur_dest(), "*." + kind)):
            try:
                st = os.stat(p)
            except OSError:
                continue
            if st.st_size != size:
                continue
            c = local_heads.get(p)
            if not c or c[0] != st.st_size or c[1] != st.st_mtime or len(c[2]) < n:
                with open(p, "rb") as fh:
                    c = (st.st_size, st.st_mtime, fh.read(n))
                local_heads[p] = c
            if c[2][:n] == head:
                return os.path.relpath(p, MISURE)
        return None

    def resolve(vol, rel):
        """Full path of a relative scope path, only inside Waveform/ or Screenshots/."""
        sub, _, name = rel.partition("/")
        exts = dict(SUBDIRS)
        if sub not in exts or not name or "/" in name or name.startswith(".") \
                or not name.lower().endswith(exts[sub]):
            raise ValueError("percorso non valido")
        return os.path.join(vol, sub, name)

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _local(self):
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
            return host in ("127.0.0.1", "localhost")

        def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
            if isinstance(body, (dict, list)):
                body = json.dumps(body).encode()
            elif isinstance(body, str):
                body = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if not n:
                return {}
            try:
                return json.loads(self.rfile.read(n))
            except ValueError:
                return {}

        def do_GET(self):
            if not self._local():
                return self._send(403, {"errore": "host non locale"})
            u = urllib.parse.urlparse(self.path)
            path, q = u.path, urllib.parse.parse_qs(u.query)
            if path in ("/", "/index.html"):
                with open(VIEWER, "rb") as fh:
                    return self._send(200, fh.read(), "text/html; charset=utf-8")
            if path == "/api/stato":
                vols = find_scope()
                try:
                    n = len(scope_listing(vols[0])) if vols else 0
                except OSError:
                    n = None
                return self._send(200, {"collegato": bool(vols), "volume": vols[0] if vols else None,
                                        "file_sullo_strumento": n, "cartella": cur_dest(),
                                        "occupato": scope_lock.locked()})
            if path == "/api/elenco":
                vols = find_scope()
                if not vols:
                    return self._send(200, {"collegato": False, "file": []})
                files = [{"f": rel, "nome": rel.split("/", 1)[1], "tipo": rel.rsplit(".", 1)[1].lower(),
                          "dimensione": size} for rel, _, size in scope_listing(vols[0])]
                return self._send(200, {"collegato": True, "file": files})
            if path == "/api/miniatura":
                vols = find_scope()
                if not vols:
                    return self._send(404, {"errore": "oscilloscopio non collegato"})
                try:
                    full = resolve(vols[0], (q.get("f") or [""])[0])
                    st = os.stat(full)
                except (ValueError, OSError):
                    return self._send(404, {"errore": "file non trovato"})
                kind = full.rsplit(".", 1)[1].lower()
                key = (full, st.st_size, st.st_mtime)
                head = heads.get(key)
                if head is None:
                    if not scope_lock.acquire(timeout=120):
                        return self._send(409, {"errore": "oscilloscopio occupato"})
                    try:
                        head = scope_head(full, min(st.st_size, thumb_bytes_needed(kind)))
                    except TimeoutError:
                        return self._send(504, {"errore": "lettura bloccata: stacca e riattacca l'USB"})
                    except OSError as e:
                        return self._send(500, {"errore": str(e)})
                    finally:
                        scope_lock.release()
                    heads[key] = head
                copia = local_copy(kind, st.st_size, head) or ""
                extra = {"X-Copiato": urllib.parse.quote(copia)}
                try:
                    return self._send(200, png(*thumbnail(head, kind)), "image/png", extra)
                except ValueError:
                    return self._send(204, b"", "image/png", extra)
            if path.startswith("/api/file/"):
                name = os.path.basename(urllib.parse.unquote(path[len("/api/file/"):]))
                full = os.path.join(cur_dest(), name)
                if not name.lower().endswith((".wav", ".bmp", ".csv")) or not os.path.isfile(full):
                    return self._send(404, {"errore": "file non trovato"})
                ctype = {"wav": "application/octet-stream", "bmp": "image/bmp",
                         "csv": "text/csv; charset=utf-8"}[name.rsplit(".", 1)[1].lower()]
                with open(full, "rb") as fh:
                    return self._send(200, fh.read(), ctype)
            self._send(404, {"errore": "non trovato"})

        def do_POST(self):
            if not self._local() or self.headers.get("X-Fnirsi") != "1":
                return self._send(403, {"errore": "richiesta non ammessa"})
            path = urllib.parse.urlparse(self.path).path
            body = self._body()
            if not scope_lock.acquire(timeout=60):   # waits for a thumbnail being read
                return self._send(409, {"errore": "un'altra operazione è in corso"})
            try:
                if path == "/api/scarica":
                    lines, paths, present = [], [], []
                    dest = cur_dest()
                    only = set(body["file"]) if isinstance(body.get("file"), list) else None
                    rc = scarica(dest, csv=csv, log=lines.append, copied_paths=paths, only=only,
                                 present_paths=present)
                    for l in lines:
                        print(l)
                    files = [{"nome": os.path.basename(p), "tipo": p.rsplit(".", 1)[1].lower(), "nuovo": True}
                             for p in paths] + \
                            [{"nome": os.path.basename(p), "tipo": p.rsplit(".", 1)[1].lower(), "nuovo": False}
                             for p in present]
                    msg = {0: f"Copiati {len(paths)} file nuovi in {dest}"
                              + (f"; {len(present)} erano già lì" if present else ""),
                           3: "Oscilloscopio non trovato: collegalo e attiva USB sharing.",
                           4: "Lettura bloccata: stacca e riattacca l'USB, poi riprova."}[rc]
                    return self._send(200, {"ok": rc == 0, "codice": rc, "messaggio": msg,
                                            "file": files, "dettagli": lines, "cartella": dest})
                if path == "/api/cancella":
                    vols = find_scope()
                    if not vols:
                        return self._send(200, {"ok": False, "messaggio": "Oscilloscopio non collegato."})
                    rels = body.get("file") if isinstance(body.get("file"), list) else []
                    done, errors = [], []
                    for rel in rels:
                        try:
                            full = resolve(vols[0], rel)
                            if not os.path.isfile(full):
                                raise OSError("non c'è più")
                            scope_delete(full)
                            side = os.path.join(os.path.dirname(full), "._" + os.path.basename(full))
                            if os.path.exists(side):
                                try:
                                    scope_delete(side)
                                except OSError:
                                    pass
                            done.append(rel)
                            print(f"  cancellato sullo strumento: {rel}")
                        except TimeoutError:
                            errors.append(f"{rel}: bloccato, stacca e riattacca l'USB")
                            break
                        except (ValueError, OSError) as e:
                            errors.append(f"{rel}: {e}")
                    msg = f"Cancellati {len(done)} file dallo strumento."
                    if errors:
                        msg += " Problemi: " + "; ".join(errors)
                    return self._send(200, {"ok": not errors, "messaggio": msg, "cancellati": done})
                if path == "/api/espelli":
                    vols = find_scope()
                    if not vols:
                        return self._send(200, {"ok": False, "messaggio": "Nessun oscilloscopio da espellere."})
                    r = subprocess.run(["diskutil", "eject", vols[0]], capture_output=True, text=True)
                    ok = r.returncode == 0
                    return self._send(200, {"ok": ok, "messaggio": "Disco espulso: puoi staccare il cavo." if ok
                                            else (r.stderr.strip() or r.stdout.strip() or "Espulsione non riuscita.")})
                self._send(404, {"errore": "non trovato"})
            finally:
                scope_lock.release()

    try:
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), H)
    except OSError as e:
        if e.errno != 48:                    # EADDRINUSE
            raise
        if not _replace_old_viewer(port):
            return 5
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), H)
    url = f"http://127.0.0.1:{port}/"
    print(f"Visore su {url}  (file copiati in {cur_dest()}; Ctrl-C per chiudere)")
    if open_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        srv.server_close()
    return 0


def _replace_old_viewer(port):
    """The port is taken. If it is another 'fnirsi.py visore' with nothing in progress,
    stop it and return True; otherwise explain and return False."""
    import json, signal, urllib.request
    pids = subprocess.run(["lsof", "-t", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
                          capture_output=True, text=True).stdout.split()
    cmd = subprocess.run(["ps", "-o", "command=", "-p", pids[0]], capture_output=True,
                         text=True).stdout.strip() if pids else ""
    if not ("fnirsi.py" in cmd and "visore" in cmd):
        print(f"La porta {port} è usata da un altro programma ({cmd or 'sconosciuto'}).\n"
              f"Scegline un'altra, per esempio: fnirsi.py visore --porta {port + 1}")
        return False
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/stato", timeout=5) as r:
            busy = json.load(r).get("occupato")
    except (OSError, ValueError):
        busy = False
    if busy:
        print(f"C'è già un visore aperto (processo {pids[0]}) che sta copiando o cancellando file.\n"
              f"Aspetta che finisca, chiudilo con Ctrl-C nel suo terminale e rilancia.")
        return False
    print(f"Chiudo il visore già aperto (processo {pids[0]}) e lo sostituisco con questo.")
    os.kill(int(pids[0]), signal.SIGTERM)
    for _ in range(50):
        time.sleep(0.1)
        if not subprocess.run(["lsof", "-t", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
                              capture_output=True, text=True).stdout.strip():
            return True
    print("Il visore precedente non si è chiuso: chiudilo con Ctrl-C nel suo terminale e rilancia.")
    return False


def main(argv):
    if len(argv) >= 3 and argv[0] == "_copia":
        copy_small(argv[1], argv[2])
        return 0
    if len(argv) >= 3 and argv[0] == "_testa":
        sys.stdout.buffer.write(read_head_small(argv[1], int(argv[2])))
        return 0
    if len(argv) >= 2 and argv[0] == "_cancella":
        os.remove(argv[1])
        return 0
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "scarica":
        dest = rest[rest.index("--dest") + 1] if "--dest" in rest else default_dest()
        return scarica(dest, "--csv" in rest, "--espelli" in rest)
    if cmd == "visore":
        port = int(rest[rest.index("--porta") + 1]) if "--porta" in rest else 8765
        dest = rest[rest.index("--dest") + 1] if "--dest" in rest else None
        return visore(port, dest, "--csv" in rest, "--no-browser" not in rest)
    acq = 1
    if "--acquisizione" in rest:
        i = rest.index("--acquisizione")
        acq = int(rest[i + 1])
        rest = rest[:i] + rest[i + 2:]
    files = [f for a in rest for f in (glob.glob(a) or [a])]
    for f in files:
        try:
            if cmd == "info":
                print(info(f))
            elif cmd == "csv":
                out = os.path.splitext(f)[0] + (f"_acq{acq}" if acq > 1 else "") + ".csv"
                write_csv(out, parse(open(f, "rb").read(), acq))
                print(f"{f} -> {out}")
            else:
                print("comando sconosciuto:", cmd)
                return 2
        except (OSError, ValueError) as e:
            print(f"{f}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
