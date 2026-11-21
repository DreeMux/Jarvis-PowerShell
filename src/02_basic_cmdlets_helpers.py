# ---------------- CMDLET ----------------
@cmdlet("Get-ChildItem", "dir", "ls", "gci")
def get_childitem(args):
    flags, pos = parse(args)
    force = "-force" in flags
    percorso = pos[0] if pos else "."
    if not os.path.exists(percorso):
        a = os.path.abspath(percorso)
        error("Get-ChildItem", f"Cannot find path '{a}' because it does not exist.",
              "ObjectNotFound", a, "ItemNotFoundException",
              "PathNotFound,Microsoft.PowerShell.Commands.GetChildItemCommand")
        return
    if os.path.isdir(percorso):
        cartella = os.path.abspath(percorso)
        nomi = os.listdir(percorso)
        voci = [(n, os.path.join(percorso, n)) for n in nomi]
    else:
        cartella = os.path.dirname(os.path.abspath(percorso))
        voci = [(os.path.basename(percorso), percorso)]

    if not force:
        voci = [(n, p) for n, p in voci if not nascosto(p, n)]
    dirs = sorted([v for v in voci if os.path.isdir(v[1])], key=lambda v: v[0].lower())
    files = sorted([v for v in voci if not os.path.isdir(v[1])], key=lambda v: v[0].lower())
    if not dirs and not files:
        return

    out()
    out(f"    Directory: {cartella}")
    out()
    out("Mode".ljust(21) + "LastWriteTime" + " " * 9 + "Length" + " Name", HEADER_COLOR)
    out("----".ljust(21) + "-------------" + " " * 9 + "------" + " ----", HEADER_COLOR)
    for nome, p in dirs + files:
        e_dir = os.path.isdir(p)
        try:
            st = os.stat(p)
            quando = datetime.fromtimestamp(st.st_mtime)
            lung = "" if e_dir else str(st.st_size)
        except OSError:
            quando, lung = datetime.fromtimestamp(0), ""
        data = quando.strftime("%d/%m/%Y") + "     " + quando.strftime("%H:%M")
        out(mode_string(p, nome, e_dir).ljust(14) + data + lung.rjust(15) + " " + nome)
    out()


@cmdlet("Set-Location", "cd", "sl", "chdir")
def set_location(args):
    _, pos = parse(args)
    if not pos:
        dest = os.path.expanduser("~")
    else:
        dest = os.path.expanduser(pos[0])
        joined = os.path.expanduser(" ".join(pos))
        if not os.path.exists(dest) and os.path.exists(joined):
            dest = joined
    if os.path.isfile(dest):
        # Extra feature: cd on a FILE selects it for extract.port / interact.port / denux.hunter
        full = os.path.abspath(dest)
        try:
            os.chdir(os.path.dirname(full))
        except OSError:
            pass
        CONTESTO["file"] = full
        out(f"Selected file: {safe(os.path.basename(full))}", YELLOW)
        out("Now run extract.port, interact.port or denux.hunter on it.", GRAY)
        return
    try:
        os.chdir(dest)
        CONTESTO["file"] = None
    except (OSError, ValueError):
        a = os.path.abspath(dest)
        error("Set-Location", f"Cannot find path '{a}' because it does not exist.",
              "ObjectNotFound", a, "ItemNotFoundException",
              "PathNotFound,Microsoft.PowerShell.Commands.SetLocationCommand")


@cmdlet("Get-Location", "pwd", "gl")
def get_location(args):
    out()
    out("Path")
    out("----")
    out(os.getcwd())
    out()


@cmdlet("Write-Output", "echo", "write")
def write_output(args):
    out(" ".join(args))


@cmdlet("Write-Host")
def write_host(args):
    out(" ".join(args))


@cmdlet("Get-Content", "cat", "type", "gc")
def get_content(args):
    _, pos = parse(args)
    if not pos and CONTESTO.get("file"):
        pos = [CONTESTO["file"]]
    for p in pos:
        if os.path.isdir(p):
            a = os.path.abspath(p)
            error("Get-Content", f"Access to the path '{a}' is denied.", "PermissionDenied",
                  a, "UnauthorizedAccessException",
                  "GetContentReaderUnauthorizedAccessError,Microsoft.PowerShell.Commands.GetContentCommand")
            continue
        try:
            if device_path(p):
                raise FileNotFoundError(p)          # CON/NUL/COM1... would wait for input forever
            with open(p, encoding="utf-8", errors="replace") as f:
                for riga in f:
                    out(safe(riga.rstrip("\r\n")))
        except (OSError, ValueError):
            a = os.path.abspath(p)
            error("Get-Content", f"Cannot find path '{a}' because it does not exist.",
                  "ObjectNotFound", a, "ItemNotFoundException",
                  "PathNotFound,Microsoft.PowerShell.Commands.GetContentCommand")


@cmdlet("Clear-Host", "cls", "clear")
def clear_host(args):
    sys.stdout.write(BG + TEXT + "\x1b[2J\x1b[H")


@cmdlet("Get-Command", "gcm")
def get_command(args):
    out()
    out("CommandType     Name")
    out("-----------     ----")
    for nome in sorted(NOMI, key=str.lower):
        out(f"Cmdlet          {nome}")
    out()


@cmdlet("Exit", "quit")
def esci(args):
    raise SystemExit(0)


# ======================= PORT TOOLS (built in) =======================
# extract.port, interact.port, denux.hunter - all READ-ONLY.

MAX_HASH = 256 * 1024 * 1024    # checksums skipped above this size
MAX_DEEP = 100 * 1024 * 1024    # denux.hunter does not deep-check above this
MAX_TEXT = 5 * 1024 * 1024      # text read limit for previews/statistics
MAX_FILES = 5000                # denux.hunter stops after this many files

BOMS16 = (codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)
OFFICE = {
    ".docx": "Word document", ".xlsx": "Excel workbook",
    ".pptx": "PowerPoint presentation", ".odt": "OpenDocument text",
    ".ods": "OpenDocument spreadsheet", ".odp": "OpenDocument presentation",
    ".epub": "EPUB book", ".jar": "Java archive", ".apk": "Android package",
}
ZIP_EXT = set(OFFICE) | {".zip"}
TEXT_EXT = {".txt", ".md", ".csv", ".tsv", ".log", ".py", ".ini", ".cfg", ".xml",
            ".html", ".htm", ".yml", ".yaml", ".js", ".css"}
MAGIC = [
    (b"\x89PNG\r\n\x1a\n", "PNG image"), (b"\xff\xd8\xff", "JPEG image"),
    (b"GIF87a", "GIF image"), (b"GIF89a", "GIF image"),
    (b"%PDF-", "PDF document"), (b"PK\x03\x04", "ZIP archive"),
    (b"\x1f\x8b", "GZIP archive"), (b"7z\xbc\xaf\x27\x1c", "7-Zip archive"),
    (b"Rar!", "RAR archive"), (b"SQLite format 3\x00", "SQLite database"),
    (b"\x7fELF", "ELF executable"),
]


# ----------------------------- helpers -----------------------------
def safe(s):
    """Strip control characters so a hostile file name/content cannot mess up the terminal."""
    return "".join(c if c.isprintable() else "." for c in str(s).replace("\t", "    "))


def human(n):
    if n < 1024:
        return f"{n:,} bytes"
    for unit in ("KB", "MB", "GB", "TB"):
        n /= 1024
        if n < 1024 or unit == "TB":
            return f"{n:,.1f} {unit}"


def is_zip(kind):
    return kind == "ZIP archive" or kind.endswith("(ZIP container)")


def detect_kind(path):
    ext = os.path.splitext(path)[1].lower()
    try:
        with open(guard_path(path), "rb") as f:
            head = f.read(4096)
    except OSError:
        return "Unreadable"
    if not head:
        return "Empty file"
    if head[:2] in BOMS16:
        return "Text file (UTF-16)"
    for sig, name in MAGIC:
        if head.startswith(sig):
            if name == "ZIP archive" and ext in OFFICE:
                return OFFICE[ext] + " (ZIP container)"
            return name
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "WebP image"
    if ext == ".win" and head[:4] == b"FORM" and head[8:12] == b"GEN8":
        return "GameMaker data file"
    if head[:2] == b"MZ" and ext in (".exe", ".dll", ".sys"):
        return "Windows executable"
    if b"\x00" in head:
        return "Binary data"
    try:
        head.decode("utf-8")
        return "Text file"
    except UnicodeDecodeError as e:
        return "Text file" if e.start >= len(head) - 3 else "Text file (legacy encoding)"


def read_text(path, limit=MAX_TEXT):
    with open(guard_path(path), "rb") as f:
        raw = f.read(limit)
    if raw[:2] in BOMS16:
        return raw.decode("utf-16", errors="replace"), "UTF-16"
    if raw.startswith(codecs.BOM_UTF8):
        return raw[3:].decode("utf-8", errors="replace"), "UTF-8 with BOM"
    try:
        return raw.decode("utf-8"), "UTF-8"
    except UnicodeDecodeError as e:
        if e.start >= len(raw) - 3 and len(raw) == limit:
            return raw[:e.start].decode("utf-8"), "UTF-8"
        return raw.decode("latin-1"), "Legacy 8-bit (shown as Latin-1)"


def digests(path):
    sha = hashlib.sha256()
    try:
        md = hashlib.md5(usedforsecurity=False)
    except TypeError:
        md = hashlib.md5()
    with open(guard_path(path), "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            sha.update(chunk)
            md.update(chunk)
    return sha.hexdigest().upper(), md.hexdigest().upper()


def image_size(path, kind):
    try:
        with open(guard_path(path), "rb") as f:
            head = f.read(32)
            if kind == "PNG image" and len(head) >= 24:
                return struct.unpack(">II", head[16:24])
            if kind == "GIF image" and len(head) >= 10:
                return struct.unpack("<HH", head[6:10])
            if kind == "JPEG image":
                f.seek(2)
                while True:
                    b = f.read(1)
                    if not b:
                        return None
                    if b != b"\xff":
                        continue
                    m = f.read(1)
                    while m == b"\xff":
                        m = f.read(1)
                    if not m:
                        return None
                    c = m[0]
                    if c in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                        f.read(3)
                        h, w = struct.unpack(">HH", f.read(4))
                        return (w, h)
                    if c in (0xD8, 0x01) or 0xD0 <= c <= 0xD7:
                        continue
                    ln = struct.unpack(">H", f.read(2))[0]
                    f.seek(ln - 2, 1)
    except (OSError, struct.error):
        return None
    return None


def sqlite_open_ro(path):
    return sqlite3.connect(pathlib.Path(path).resolve().as_uri() + "?mode=ro", uri=True)


def sqlite_tables(path, limit=30):
    con = sqlite_open_ro(path)
    try:
        names = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        res = []
        for n in names[:limit]:
            cnt = con.execute('SELECT COUNT(*) FROM "%s"' % n.replace('"', '""')).fetchone()[0]
            res.append((n, cnt))
        return res, len(names)
    finally:
        con.close()


def hexdump(data):
    rows = []
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        hx = " ".join(f"{b:02X}" for b in chunk).ljust(47)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        rows.append(f"  {i:08X}  {hx}  {asc}")
    return rows


def target_args(args):
    """Split flags/targets. Also accepts the word 'cd':  denux.hunter cd "file"."""
    flags, pos = parse(args)
    if pos and pos[0].lower() in ("cd", "sl", "set-location"):
        pos = pos[1:]
    return flags, pos


DEVICE_NAMES = frozenset({"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
                         | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)})


def device_path(p, win=None):
    """True for Windows device names (CON, NUL, COM1, \\\\.\\...). They 'exist' but opening them waits for
    input forever, so no command may ever open them as files."""
    if win is None:
        win = os.name == "nt"
    if not win:
        return False
    t = str(p).replace("/", "\\")
    if t.startswith("\\\\.\\"):
        return True
    for part in t.split("\\"):
        stem = part.split(":")[-1].rstrip(" .").split(".")[0].rstrip(" ").upper()
        if stem in DEVICE_NAMES:
            return True
    return False


def guard_path(p):
    """The path itself, or FileNotFoundError for a Windows device name (CON, NUL...): it then follows the same
    road as a missing file, because opening a device would wait for input forever."""
    if device_path(p):
        raise FileNotFoundError(p)
    return p


def resolve_existing(pos, cmd):
    p = pos[0]
    joined = " ".join(pos)
    if not os.path.exists(p) and os.path.exists(joined):
        p = joined
    if device_path(p) or not os.path.exists(p):
        a = os.path.abspath(p)
        error(cmd, f"Cannot find path '{a}' because it does not exist.",
              "ObjectNotFound", a, "ItemNotFoundException", f"PathNotFound,{cmd}")
        return None
    return p


def show_file_choices():
    out("Files in the current folder:")
    try:
        files = sorted(n for n in os.listdir(".") if os.path.isfile(n))
    except OSError:
        files = []
    if not files:
        out("  (no files in this folder)", GRAY)
    for n in files[:25]:
        out(f"  {safe(n).ljust(40)} {detect_kind(n)}")
    if len(files) > 25:
        out(f"  ... and {len(files) - 25} more", GRAY)
    out()


def pick(args, cmd):
    """The file to work on: the one given, or the one selected earlier with cd."""
    flags, pos = target_args(args)
    if pos:
        p = resolve_existing(pos, cmd)
        if p is None:
            return None
        if os.path.isdir(p):
            out(f"'{safe(p)}' is a folder. Use cd to enter it, then pick a file inside.", YELLOW)
            out()
            return None
        return p
    sel = CONTESTO.get("file")
    if sel and os.path.isfile(sel):
        out(f"Using selected file: {safe(sel)}", GRAY)
        return sel
    out(f"Usage: {cmd} <file>", YELLOW)
    out(f'Or select a file first with:  cd "<file>"   and then run  {cmd}', YELLOW)
    show_file_choices()
    return None


