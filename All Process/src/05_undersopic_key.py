# ----------------------------- undersopic.key -----------------------------
GM_FILE = "data.win"


def gm_read_info(path):
    """Read-only peek at a GameMaker data.win (a FORM container). Never modifies it."""
    info = {"ok": False, "notes": [], "chunks": [], "name": None, "gm": None, "bytecode": None}
    size = os.path.getsize(path)
    with open(guard_path(path), "rb") as f:
        head = f.read(8)
        if len(head) < 8 or head[:4] != b"FORM":
            info["notes"].append("Missing FORM header (not a GameMaker data file, or damaged)")
            return info
        end = struct.unpack("<I", head[4:8])[0] + 8
        if end != size:
            info["notes"].append(f"FORM length expects {end:,} bytes but the file has {size:,} "
                                 "(truncated or modified?)")
        pos, gen8, broken = 8, None, False
        while pos + 8 <= min(end, size) and len(info["chunks"]) < 64:
            f.seek(pos)
            hdr = f.read(8)
            cid, clen = hdr[:4], struct.unpack("<I", hdr[4:8])[0]
            if not re.fullmatch(rb"[A-Z0-9]{4}", cid):
                info["notes"].append("Chunk list is damaged")
                broken = True
                break
            info["chunks"].append(cid.decode())
            if cid == b"GEN8":
                gen8 = (pos + 8, clen)
            pos += 8 + clen
        if not broken and pos > size:
            info["notes"].append("The last chunk runs past the end of the file (truncated)")
        info["ok"] = bool(info["chunks"]) and info["chunks"][0] == "GEN8"
        if not info["ok"]:
            info["notes"].append("First chunk is not GEN8 (unusual for a GameMaker game)")
        if gen8 and gen8[1] >= 60:   # best-effort: game name and GameMaker version
            f.seek(gen8[0])
            g = f.read(60)
            info["bytecode"] = g[1]
            ptr = struct.unpack("<I", g[40:44])[0]
            if 4 < ptr < size:
                f.seek(ptr - 4)
                ln = struct.unpack("<I", f.read(4))[0]
                if 0 < ln <= 64:
                    s = f.read(ln)
                    if s.isascii() and s.decode("ascii").isprintable():
                        info["name"] = s.decode("ascii")
            major, minor, rel, build = struct.unpack("<4I", g[44:60])
            if 1 <= major <= 3 and minor < 100 and rel < 100000 and build < 100000:
                info["gm"] = f"{major}.{minor}.{rel}.{build}"
    return info


def store_of(path):
    low = path.lower().replace("\\", "/")
    if "/steamapps/" in low:
        return "Steam"
    if "epic games" in low:
        return "Epic Games"
    if "/gog" in low:
        return "GOG"
    if "/itch" in low:
        return "itch.io"
    if "/downloads/" in low:
        return "Downloads folder"
    return "Other folder"


def steam_libraries():
    home = os.path.expanduser("~")
    cands = []
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
                cands.append(winreg.QueryValueEx(k, "SteamPath")[0])
        except Exception:
            pass
        for pf in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
            if pf:
                cands.append(os.path.join(pf, "Steam"))
    elif sys.platform == "darwin":
        cands.append(home + "/Library/Application Support/Steam")
    else:
        cands += [home + "/.steam/steam", home + "/.local/share/Steam",
                  home + "/.var/app/com.valvesoftware.Steam/.local/share/Steam"]
    libs = []
    for c in cands:
        if os.path.isdir(os.path.join(c, "steamapps")):
            libs.append(c)
        try:
            with open(os.path.join(c, "steamapps", "libraryfolders.vdf"),
                      encoding="utf-8", errors="replace") as f:
                for m in re.findall(r'"path"\s+"([^"]+)"', f.read()):
                    libs.append(m.replace("\\\\", "\\"))
        except OSError:
            pass
    return [os.path.join(lib, "steamapps", "common") for lib in libs]


def game_locations():
    """Folders where downloaded games usually live (only those that exist)."""
    home = os.path.expanduser("~")
    locs = steam_libraries()
    locs += [home + "/Downloads", home + "/Desktop", home + "/Games", home + "/Documents/Games"]
    if os.name == "nt":
        for pf in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
            if pf:
                locs += [os.path.join(pf, "Epic Games"), os.path.join(pf, "GOG Galaxy", "Games")]
        for var in ("APPDATA", "LOCALAPPDATA"):
            if os.environ.get(var):
                locs.append(os.path.join(os.environ[var], "itch", "apps"))
        locs += ["C:\\GOG Games", "C:\\Games"]
    else:
        locs.append(home + "/.config/itch/apps")
    seen, res = set(), []
    for p in locs:
        if os.path.isdir(p):
            key = os.path.normcase(os.path.realpath(p))
            if key not in seen:
                seen.add(key)
                res.append(p)
    return res


def find_named(roots, name=GM_FILE, maxdepth=None):
    for root in roots:
        base = root.rstrip(os.sep).count(os.sep)
        for cur, dirs, files in os.walk(root, onerror=lambda e: None):
            if maxdepth is not None and cur.rstrip(os.sep).count(os.sep) - base >= maxdepth:
                dirs[:] = []
            else:
                dirs[:] = sorted(d for d in dirs if not skip_dir(os.path.join(cur, d)))
            for fn in files:
                if fn.lower() == name:
                    yield os.path.join(cur, fn)


def show_gm(i, path):
    try:
        info = gm_read_info(path)
        size = os.path.getsize(path)
        mtime = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%d/%m/%Y %H:%M")
    except OSError as e:
        out(f"[{i}] {safe(path)}", CYAN)
        out(f"    Cannot read it ({e.strerror})", RED)
        out()
        return
    game = info["name"] or os.path.basename(os.path.dirname(os.path.abspath(path)))
    out(f"[{i}] {safe(game)}", CYAN)
    out(f"    Path    : {safe(os.path.abspath(path))}")
    out(f"    Store   : {store_of(path)}")
    out(f"    Size    : {human(size)}   (modified {mtime})")
    if info["ok"]:
        extra = f", GameMaker {info['gm']}" if info["gm"] else ""
        bc = f"bytecode {info['bytecode']}" if info["bytecode"] is not None else "bytecode ?"
        out(f"    Format  : GameMaker data file, {bc}{extra}, {len(info['chunks'])} chunks")
    for note in info["notes"]:
        out(f"    Warning : {note}", YELLOW)
    out()


@cmdlet("undersopic.key", group="Port tools", usage="""undersopic.key               find the data.win of your downloaded games (Steam, Epic, GOG, itch.io, Downloads...)
undersopic.key <folder>      search that folder and everything below it
undersopic.key -Everywhere   search the whole computer (can take a while, Ctrl+C stops it)
undersopic.key               after  cd "<data.win>"  it shows that file only
(read-only: it only finds and describes the file, it never changes it)""")
def undersopic_key(args):
    """Find the direct data.win file of downloaded games (GameMaker)."""
    flags, pos = target_args(args)
    sel = CONTESTO.get("file")
    paths, interrupted, searched = [], False, []
    if pos:
        target = resolve_existing(pos, "undersopic.key")
        if target is None:
            return
        if os.path.isfile(target):
            if os.path.basename(target).lower() != GM_FILE:
                out(f"'{safe(os.path.basename(target))}' is not a {GM_FILE} file.", YELLOW)
                out()
                return
            paths = [target]
        else:
            searched = [target]
    elif sel and os.path.basename(sel).lower() == GM_FILE and os.path.isfile(sel):
        paths = [sel]
    elif "-everywhere" in flags:
        searched = pc_roots()
        out()
        out("Searching the WHOLE COMPUTER for data.win... Press Ctrl+C to stop.", YELLOW)
    else:
        searched = game_locations()
        if not searched:
            out()
            out("No known game folders were found on this PC.", YELLOW)
            out('Try:  undersopic.key <folder>    or    undersopic.key -Everywhere', YELLOW)
            out()
            return
    if searched:
        if not (pos is None and "-everywhere" in flags):
            out()
            out("Searching in:", GRAY)
            for s in searched:
                out(f"  {safe(s)}", GRAY)
        depth = None if ("-everywhere" in flags or pos) else 6
        seen = set()
        try:
            for p in find_named(searched, GM_FILE, depth):
                key = os.path.normcase(os.path.realpath(p))
                if key not in seen:
                    seen.add(key)
                    paths.append(p)
        except KeyboardInterrupt:
            interrupted = True
    out()
    if not paths:
        out("No data.win found.", YELLOW)
        out("Tip: undersopic.key <folder> searches a specific folder; -Everywhere searches the whole PC.", GRAY)
        out()
        return
    out(f"Found {len(paths)} data.win file(s):", GREEN)
    out()
    for i, p in enumerate(paths, 1):
        show_gm(i, p)
    if interrupted:
        out("Stopped by user: the list may be incomplete.", YELLOW)
    q = safe(os.path.abspath(paths[0]))
    out(f'Tip: select one with  cd "{q}"  then use extract.port, interact.port, denux.hunter or pluton.key.', GRAY)
    out()


