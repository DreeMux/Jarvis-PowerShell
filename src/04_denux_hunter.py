# ----------------------------- denux.hunter -----------------------------
def check_zip(path):
    if not zipfile.is_zipfile(path):
        return "Not a valid ZIP container (bad or missing central directory)"
    with zipfile.ZipFile(path) as z:
        bad = z.testzip()
        if bad:
            return f"CRC/data error in entry '{safe(bad)}'"


def check_png(path):
    with open(guard_path(path), "rb") as f:
        if f.read(8) != b"\x89PNG\r\n\x1a\n":
            return "Invalid PNG signature"
        while True:
            hdr = f.read(8)
            if not hdr:
                return "Missing IEND chunk (file truncated)"
            if len(hdr) < 8:
                return "Truncated chunk header"
            ln, typ = struct.unpack(">I4s", hdr)
            data, crc = f.read(ln), f.read(4)
            name = safe(typ.decode("latin-1"))
            if len(data) < ln or len(crc) < 4:
                return f"Truncated chunk '{name}'"
            if zlib.crc32(typ + data) & 0xFFFFFFFF != struct.unpack(">I", crc)[0]:
                return f"Bad CRC in chunk '{name}'"
            if typ == b"IEND":
                return None


def tail_of(path, n=2048):
    size = os.path.getsize(path)
    with open(guard_path(path), "rb") as f:
        f.seek(max(0, size - n))
        return f.read()


def check_jpeg(path):
    with open(guard_path(path), "rb") as f:
        if f.read(3) != b"\xff\xd8\xff":
            return "Invalid JPEG signature"
    if not tail_of(path, 64).rstrip(b"\x00").endswith(b"\xff\xd9"):
        return "Missing end-of-image marker (file likely truncated)"


def check_gif(path):
    with open(guard_path(path), "rb") as f:
        if f.read(6) not in (b"GIF87a", b"GIF89a"):
            return "Invalid GIF signature"
    if not tail_of(path, 64).rstrip(b"\x00").endswith(b"\x3b"):
        return "Missing GIF trailer (file likely truncated)"


def check_pdf(path):
    with open(guard_path(path), "rb") as f:
        if f.read(5) != b"%PDF-":
            return "Missing %PDF- header"
    if b"%%EOF" not in tail_of(path):
        return "Missing %%EOF marker (file likely truncated)"


def check_json(path):
    with open(guard_path(path), "rb") as f:
        raw = f.read()
    try:
        json.loads(raw.decode("utf-8-sig"))
    except UnicodeDecodeError:
        return "Not valid UTF-8 text"
    except ValueError as e:
        return f"Invalid JSON: {safe(e)}"


def check_gzip(path):
    total = 0
    try:
        with gzip.open(path, "rb") as g:
            while True:
                chunk = g.read(1 << 20)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_DEEP * 2:   # decompression-bomb guard
                    break
    except (gzip.BadGzipFile, EOFError, zlib.error) as e:
        return f"Damaged GZIP stream ({safe(e)})"


def check_sqlite(path):
    with open(guard_path(path), "rb") as f:
        if f.read(16) != b"SQLite format 3\x00":
            return "Missing SQLite header"
    con = None
    try:
        con = sqlite_open_ro(path)
        res = con.execute("PRAGMA integrity_check").fetchall()
    except sqlite3.Error as e:
        return f"Database error: {safe(e)}"
    finally:
        if con:
            con.close()
    if res != [("ok",)]:
        return "Integrity check failed: " + safe(res[0][0])


CHECKS = {".png": check_png, ".jpg": check_jpeg, ".jpeg": check_jpeg,
          ".gif": check_gif, ".pdf": check_pdf, ".json": check_json,
          ".gz": check_gzip, ".db": check_sqlite, ".sqlite": check_sqlite,
          ".sqlite3": check_sqlite}
CLOUD_ATTRS = 0x1000 | 0x40000 | 0x400000   # Windows: offline / cloud-only placeholders
PSEUDO_DIRS = {"/proc", "/sys", "/dev", "/run"}
SEVERITY = {"CORRUPT": 0, "WARNING": 1, "SKIPPED": 2, "EMPTY": 3, "OK": 4}
MAX_ROWS = 300


def check_file(path):
    """Return (status, reason). status: OK, WARNING, CORRUPT, SKIPPED or EMPTY."""
    ext = os.path.splitext(path)[1].lower()
    try:
        st = os.stat(path)
        if st.st_size == 0:
            return "EMPTY", "Empty file (0 bytes)"
        if getattr(st, "st_file_attributes", 0) & CLOUD_ATTRS:
            return "SKIPPED", "Cloud-only file (not downloaded), not read"
        fn = check_zip if ext in ZIP_EXT else CHECKS.get(ext)
        if fn is None and ext not in TEXT_EXT:
            return "OK", ""          # unknown type: nothing to verify, file is not even opened
        if st.st_size > MAX_DEEP:
            return "SKIPPED", "Larger than 100 MB, not deep-checked"
        if fn:
            reason = fn(path)
            if reason:
                return "CORRUPT", reason
        else:
            with open(guard_path(path), "rb") as f:
                head = f.read(65536)
            if head[:2] not in BOMS16 and b"\x00" in head:
                return "WARNING", "Contains NUL bytes (damaged, or not really a text file)"
    except (zipfile.BadZipFile, zlib.error, EOFError) as e:
        return "CORRUPT", f"Damaged data ({safe(e)})"
    except OSError as e:
        if e.errno in (errno.EACCES, errno.EPERM):
            return "WARNING", "Access denied (could not check)"
        if e.errno == errno.ENOENT:
            return "WARNING", "File disappeared during the scan"
        return "CORRUPT", f"Read error ({e.strerror or e})"
    except Exception as e:
        return "WARNING", f"Check failed unexpectedly: {safe(e)}"
    return "OK", ""


def pc_roots():
    """Every fixed drive on Windows, or / on Linux/macOS."""
    if os.name == "nt":
        try:
            import ctypes
            k = ctypes.windll.kernel32
            mask, roots = k.GetLogicalDrives(), []
            for i in range(26):
                root = f"{chr(65 + i)}:\\"
                if mask & (1 << i) and k.GetDriveTypeW(root) == 3:   # 3 = fixed disk
                    roots.append(root)
            if roots:
                return roots
        except Exception:
            pass
        return [os.environ.get("SystemDrive", "C:") + "\\"]
    return ["/"]


def skip_dir(p):
    if os.name == "nt":
        try:
            return bool(os.lstat(p).st_file_attributes & 0x400)   # junctions / cloud folders
        except OSError:
            return True
    return p in PSEUDO_DIRS or os.path.islink(p)


def walk_files(roots, recurse=True):
    for root in roots:
        for cur, dirs, names in os.walk(root, onerror=lambda e: None):
            dirs[:] = sorted(d for d in dirs if not skip_dir(os.path.join(cur, d)))
            for n in sorted(names):
                p = os.path.join(cur, n)
                if not os.path.islink(p):
                    yield p
            if not recurse:
                break


@cmdlet("denux.hunter", group="Port tools", usage="""denux.hunter                scan EVERY file on this computer (read-only, Ctrl+C stops it)
denux.hunter <path>         scan one folder (add -Recurse for sub-folders) or one file
denux.hunter . -Recurse     scan the current folder and everything below it
denux.hunter                after  cd "<file>"  it scans only that selected file
-PC                         scan the whole computer even if a file is selected
-All                        also list OK, empty and skipped files""")
def denux_hunter(args):
    """Hunt for corrupted files: whole PC, a folder, or one selected file."""
    flags, pos = target_args(args)
    recurse, show_all = "-recurse" in flags, "-all" in flags
    whole_pc, target = False, None
    if pos:
        target = resolve_existing(pos, "denux.hunter")
        if target is None:
            return
    elif CONTESTO.get("file") and os.path.isfile(CONTESTO["file"]) and "-pc" not in flags:
        target = CONTESTO["file"]
    else:
        whole_pc = True

    single = target is not None and os.path.isfile(target)
    if whole_pc:
        roots = pc_roots()
        files = walk_files(roots, True)
        base = None
    elif single:
        files = iter([target])
        base = os.path.dirname(os.path.abspath(target))
    else:
        files = walk_files([target], recurse)
        base = target

    out()
    if whole_pc:
        out("Hunting on the WHOLE COMPUTER: " + ", ".join(roots), YELLOW)
        out("Read-only scan. Press Ctrl+C to stop at any time.", GRAY)
    elif single:
        out(f"Hunting in the selected file: {safe(os.path.abspath(target))}")
    else:
        out(f"Hunting in: {safe(os.path.abspath(target))}{'  (recursive)' if recurse else ''}")

    counts = {k: 0 for k in SEVERITY}
    rows, n, interrupted = [], 0, False
    tty = sys.stdout.isatty()
    width = shutil.get_terminal_size((100, 20)).columns
    last, t0 = 0.0, time.monotonic()
    try:
        for p in files:
            n += 1
            status, reason = check_file(p)
            counts[status] += 1
            if status != "OK" or (show_all and not whole_pc):
                name = os.path.abspath(p) if whole_pc else os.path.relpath(p, base)
                rows.append((status, safe(name), reason))
            if tty and time.monotonic() - last > 0.15:
                last = time.monotonic()
                line = (f"  Scanned {n:,} | corrupt {counts['CORRUPT']} | "
                        f"warnings {counts['WARNING']} | {safe(p)}")
                sys.stdout.write("\r" + GRAY + line[:width - 1].ljust(width - 1) + TEXT)
                sys.stdout.flush()
    except KeyboardInterrupt:
        interrupted = True
    if tty:
        sys.stdout.write("\r" + " " * (width - 1) + "\r")

    hidden = {"EMPTY", "SKIPPED"} if whole_pc and not show_all else set()
    shown = sorted((r for r in rows if r[0] not in hidden), key=lambda r: SEVERITY[r[0]])
    extra = max(0, len(shown) - MAX_ROWS)
    shown = shown[:MAX_ROWS]
    if shown:
        w = min(max(len(r[1]) for r in shown), 70)
        colors = {"CORRUPT": RED, "WARNING": YELLOW, "SKIPPED": GRAY, "EMPTY": GRAY, "OK": GREEN}
        out()
        out("Status   " + "File".ljust(w) + "  Reason")
        out("------   " + "----".ljust(w) + "  ------")
        for s, name, reason in shown:
            out(f"{s.ljust(8)} {name.ljust(w)}  {reason}", colors[s])
    out()
    secs = int(time.monotonic() - t0)
    summary = (f"Scanned {n:,} file(s) in {secs // 60}:{secs % 60:02d}: {counts['CORRUPT']} corrupt, "
               f"{counts['WARNING']} warning(s), {counts['EMPTY']} empty, "
               f"{counts['SKIPPED']} skipped, {counts['OK']} OK.")
    out(summary, RED if counts["CORRUPT"] else YELLOW if counts["WARNING"] else GREEN)
    if interrupted:
        out("Stopped by user: results are partial.", YELLOW)
    if not counts["CORRUPT"]:
        out("No corrupted files found" + (" so far." if interrupted else "."), GREEN)
    if extra:
        out(f"{extra:,} more row(s) not shown (first {MAX_ROWS} displayed). "
            "Run denux.hunter on a folder to see the rest.", YELLOW)
    if hidden and (counts["EMPTY"] or counts["SKIPPED"]):
        out(f"{counts['EMPTY']:,} empty and {counts['SKIPPED']:,} skipped file(s) not listed; use -All to list them.", GRAY)
    out("denux.hunter is read-only: no file was modified, moved or deleted.", GRAY)
    out()


