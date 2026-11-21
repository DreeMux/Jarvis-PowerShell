# ----------------------------- extract.port -----------------------------
@cmdlet("extract.port", group="Port tools", usage="""extract.port <file>
extract.port                 uses the file selected earlier with:  cd "<file>"
(one file only: there is no whole-PC mode for this command)""")
def extract_port(args):
    """Show all the information about one file (metadata, type, checksums)."""
    path = pick(args, "extract.port")
    if not path:
        return
    try:
        st = os.stat(path)
    except OSError as e:
        out(f"extract.port : Cannot read file ({e.strerror})", RED)
        out()
        return
    kind = detect_kind(path)
    ext = os.path.splitext(path)[1]
    fmt = lambda t: datetime.fromtimestamp(t).strftime("%d/%m/%Y %H:%M:%S")
    attrs = []
    if not os.access(path, os.W_OK):
        attrs.append("ReadOnly")
    winattr = getattr(st, "st_file_attributes", None)
    if (winattr is not None and winattr & 2) or (winattr is None and os.path.basename(path).startswith(".")):
        attrs.append("Hidden")
    if os.path.islink(path):
        attrs.append("Link")
    rows = [
        ("Name", safe(os.path.basename(path))),
        ("FullName", safe(os.path.abspath(path))),
        ("Type", kind),
        ("MimeType", "application/octet-stream" if kind == "GameMaker data file"
         else mimetypes.guess_type(path)[0] or "unknown"),
        ("Extension", ext or "(none)"),
        ("Size", human(st.st_size)),
        ("CreationTime" if os.name == "nt" else "ChangeTime",
         fmt(getattr(st, "st_birthtime", st.st_ctime))),
        ("LastWriteTime", fmt(st.st_mtime)),
        ("LastAccessTime", fmt(st.st_atime)),
        ("Attributes", ", ".join(attrs) or "Normal"),
    ]
    try:
        if st.st_size <= MAX_HASH:
            sha, md = digests(path)
            rows += [("SHA256", sha), ("MD5", md)]
        else:
            rows.append(("SHA256", "skipped (file larger than 256 MB)"))

        if kind.startswith("Text file"):
            text, enc = read_text(path)
            part = " (first 5 MB only)" if st.st_size > MAX_TEXT else ""
            rows += [("Encoding", enc), ("Lines", f"{len(text.splitlines()):,}{part}"),
                     ("Words", f"{len(text.split()):,}{part}"),
                     ("Characters", f"{len(text):,}{part}")]
        elif kind.endswith("image"):
            dim = image_size(path, kind)
            if dim:
                rows.append(("Dimensions", f"{dim[0]} x {dim[1]} pixels"))
        elif is_zip(kind):
            try:
                with zipfile.ZipFile(path) as z:
                    infos = z.infolist()
                    rows += [("Entries", f"{len(infos):,}"),
                             ("UncompressedSize", human(sum(i.file_size for i in infos)))]
            except zipfile.BadZipFile:
                rows.append(("Entries", "unreadable (archive may be corrupted)"))
        elif kind == "SQLite database":
            try:
                _, total = sqlite_tables(path)
                rows.append(("Tables", str(total)))
            except sqlite3.Error as e:
                rows.append(("Tables", f"unreadable ({safe(e)})"))
        elif kind == "GameMaker data file":
            gm = gm_read_info(path)
            rows += [("Game", gm["name"] or "unknown"), ("GameMaker", gm["gm"] or "unknown"),
                     ("Bytecode", str(gm["bytecode"])), ("Chunks", f"{len(gm['chunks'])}: " + ", ".join(gm["chunks"][:12]))]
            rows += [("Warning", n) for n in gm["notes"]]
        elif kind == "PDF document":
            with open(guard_path(path), "rb") as f:
                rows.append(("PdfVersion", safe(f.read(8).decode("latin-1").strip())))
    except OSError as e:
        rows.append(("Warning", f"Read error while analysing ({e.strerror})"))

    w = max(len(k) for k, _ in rows)
    out()
    for k, v in rows:
        out(f"{k.ljust(w)} : {v}")
    out()


# ----------------------------- interact.port -----------------------------
def preview(path, kind, size):
    if size == 0:
        out("  The file is empty.")
        return
    if kind.startswith("Text file"):
        text, enc = read_text(path)
        lines = text.splitlines()
        part = " (first 5 MB only)" if size > MAX_TEXT else ""
        out(f"  Encoding: {enc}  |  Lines: {len(lines):,}{part}")
        ext = os.path.splitext(path)[1].lower()
        if ext in (".csv", ".tsv") and lines:
            delim = max(",;\t|", key=lines[0].count)
            cols = [safe(c.strip()) for c in lines[0].split(delim)]
            out(f"  Table-like data: {len(cols)} column(s): {', '.join(cols[:12])}"
                f"{' ...' if len(cols) > 12 else ''}  |  {max(len(lines) - 1, 0):,} data row(s)")
        if ext == ".json" and size <= 20 * 1024 * 1024:
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    keys = list(data)
                    out(f"  JSON object with {len(keys)} key(s): "
                        f"{', '.join(safe(k) for k in keys[:15])}{' ...' if len(keys) > 15 else ''}")
                elif isinstance(data, list):
                    out(f"  JSON array with {len(data):,} item(s)")
                else:
                    out(f"  JSON value of type {type(data).__name__}")
            except ValueError as e:
                out(f"  Invalid JSON: {safe(e)}", RED)
        out("  First 15 lines:", GRAY)
        for i, line in enumerate(lines[:15], 1):
            out(f"  {i:>3} | {safe(line)[:110]}")
    elif is_zip(kind):
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
            out(f"  {len(infos):,} entr{'y' if len(infos) == 1 else 'ies'} inside (listed only, nothing is extracted):")
            for i in infos[:30]:
                out(f"  {human(i.file_size).rjust(12)}  {safe(i.filename)}")
            if len(infos) > 30:
                out(f"  ... and {len(infos) - 30:,} more", GRAY)
    elif kind == "GameMaker data file":
        gm = gm_read_info(path)
        out(f"  GameMaker game data: {gm['name'] or 'unknown name'}, GameMaker {gm['gm'] or '?'}, bytecode {gm['bytecode']}")
        out(f"  {len(gm['chunks'])} chunks: {', '.join(gm['chunks'][:20])}")
        for n in gm["notes"]:
            out(f"  Warning: {n}", YELLOW)
        out("  Viewing only: the game data is never opened for writing.", GRAY)
    elif kind == "GZIP archive":
        out("  Compressed stream. Contents are not unpacked here; use denux.hunter to verify integrity.")
    elif kind.endswith("image"):
        dim = image_size(path, kind)
        out(f"  Image, {dim[0]} x {dim[1]} pixels." if dim else "  Image (dimensions could not be read).")
    elif kind == "PDF document":
        with open(guard_path(path), "rb") as f:
            raw = f.read(20 * 1024 * 1024)
        pages = len(re.findall(rb"/Type\s*/Page[^s]", raw))
        out(f"  PDF version: {safe(raw[:8].decode('latin-1').strip())}  |  approx. pages: {pages or 'unknown'}")
        out(f"  End-of-file marker present: {'yes' if b'%%EOF' in raw[-2048:] else 'NO (file may be truncated)'}")
    elif kind == "SQLite database":
        tables, total = sqlite_tables(path)
        out(f"  {total} table(s) (opened read-only):")
        for n, c in tables:
            out(f"  {safe(n).ljust(30)} {c:,} row(s)")
        if total > len(tables):
            out(f"  ... and {total - len(tables)} more", GRAY)
    else:
        with open(guard_path(path), "rb") as f:
            data = f.read(128)
        out("  Binary content, hex preview of the first 128 bytes (never executed):")
        for row in hexdump(data):
            out(row)


@cmdlet("interact.port", group="Port tools", usage="""interact.port <file>
interact.port                uses the file selected earlier with:  cd "<file>"
(one file only: there is no whole-PC mode for this command)""")
def interact_port(args):
    """Show what you can see inside a file and what you can do with it."""
    path = pick(args, "interact.port")
    if not path:
        return
    try:
        size = os.path.getsize(path)
    except OSError as e:
        out(f"interact.port : Cannot read file ({e.strerror})", RED)
        out()
        return
    kind = detect_kind(path)
    name = safe(os.path.basename(path))
    q = f'"{name}"' if " " in name else name
    out()
    out(f"Interactive view: {name}  [{kind}, {human(size)}]", CYAN)
    out()
    out("What you can SEE inside this file:", YELLOW)
    try:
        preview(path, kind, size)
    except Exception as e:
        out(f"  Could not read the contents ({safe(e)}).", RED)
        out(f"  The file may be damaged: try  denux.hunter {q}", RED)
    out()
    out("What you can DO with it (all read-only):", YELLOW)
    if kind.startswith("Text file"):
        out(f"  Get-Content {q}   - print the whole text")
    out(f"  extract.port {q}   - full metadata, dates and checksums")
    out(f"  denux.hunter {q}   - check whether this file is corrupted")
    out("interact.port never runs, edits, moves or deletes files.", GRAY)
    out()


