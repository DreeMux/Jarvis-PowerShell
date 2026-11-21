# ---------- JARVIS deep layer: specific questions + opening files (everything READ-ONLY) ----------
JV_PRON = {"it", "this", "that", "this file", "that file", "the file", "file", "selected", "selected file",
           "the selected file", "the same", "same file", "it again", "questo", "questo file", "quel file",
           "quello", "il file", "esso", "lo", "quel", "selezionato", "il file selezionato"}
JV_HERE = {"folder", "this folder", "the folder", "directory", "this directory", "here", "cartella",
           "questa cartella", "qui", "current folder", "cartella corrente"}
JV_ORD = {"first": 1, "1st": 1, "primo": 1, "prima": 1, "second": 2, "2nd": 2, "secondo": 2, "seconda": 2,
          "third": 3, "3rd": 3, "terzo": 3, "terza": 3, "fourth": 4, "4th": 4, "quarto": 4, "quarta": 4,
          "fifth": 5, "5th": 5, "quinto": 5, "quinta": 5, "last": -1, "ultimo": -1, "ultima": -1}
JV_EXTWORDS = ("png", "jpg", "jpeg", "gif", "webp", "bmp", "pdf", "txt", "csv", "json", "zip", "rar", "7z", "exe",
               "dll", "mp3", "mp4", "mkv", "avi", "mov", "wav", "docx", "xlsx", "pptx", "html", "xml", "sqlite",
               "msi", "bat")
JV_CATS = [
    (("image", "images", "picture", "pictures", "photo", "photos", "immagine", "immagini", "foto"),
     ("png", "jpg", "jpeg", "gif", "webp", "bmp", "tif", "tiff", "ico", "svg")),
    (("document", "documents", "documento", "documenti"), ("doc", "docx", "odt", "rtf", "pdf", "txt", "md")),
    (("spreadsheet", "spreadsheets", "fogli di calcolo", "foglio di calcolo"), ("xls", "xlsx", "ods", "csv", "tsv")),
    (("presentation", "presentations", "slides", "presentazioni"), ("ppt", "pptx", "odp")),
    (("video", "videos"), ("mp4", "mkv", "avi", "mov", "wmv", "webm", "flv")),
    (("music", "audio", "song", "songs", "musica", "canzoni"), ("mp3", "wav", "flac", "ogg", "m4a", "aac", "wma")),
    (("archive", "archives", "archivio", "archivi"), ("zip", "rar", "7z", "gz", "tar", "tgz", "bz2", "xz")),
    (("database", "databases"), ("db", "sqlite", "sqlite3")),
    (("program", "programs", "executable", "executables", "eseguibili", "programmi"), ("exe", "msi", "bat", "cmd")),
    (("script", "scripts", "source code", "codice"), ("py", "js", "ts", "c", "cpp", "h", "java", "cs", "sh", "ps1",
                                                      "go", "rs", "lua")),
]
GM_COUNTS = [
    (r"sprites?", "SPRT", "sprites"), (r"sounds?|sfx|sound effects?|suoni|effetti sonori", "SOND", "sounds"),
    (r"rooms?|levels?|maps?|stanz\w+|livell\w+", "ROOM", "rooms"), (r"objects?|oggett\w+", "OBJT", "objects"),
    (r"fonts?", "FONT", "fonts"), (r"paths?", "PATH", "paths"), (r"scripts?", "SCPT", "scripts"),
    (r"shaders?", "SHDR", "shaders"), (r"backgrounds?|tile ?sets?", "BGND", "backgrounds / tile sets"),
    (r"textures?|texture pages?", "TXTR", "texture pages"), (r"audio files?|embedded audio", "AUDO", "embedded audio files"),
    (r"frames?", "TPAG", "texture-page items (sprite frames and images)"),
    (r"strings?|dialog\w*|text lines?|testi|dialoghi", "STRG", "strings (text, names, dialogue...)"),
    (r"code entries|compiled code|codice", "CODE", "code entries"),
]
PE_MACHINES = {0x14C: "32-bit (x86)", 0x8664: "64-bit (x64)", 0xAA64: "64-bit (ARM64)", 0x1C0: "32-bit (ARM)",
               0x1C4: "32-bit (ARM Thumb-2)", 0x200: "64-bit (Itanium)"}
INTEGRITY_TEST = {".zip": "every entry's CRC", ".png": "every chunk's CRC", ".jpg": "the start and end markers",
                  ".jpeg": "the start and end markers", ".gif": "the header and trailer", ".pdf": "the header and the end marker",
                  ".json": "a full parse", ".gz": "a full decompression", ".db": "SQLite's integrity check",
                  ".sqlite": "SQLite's integrity check", ".sqlite3": "SQLite's integrity check"}


def jv_ago(ts):
    d = max(0, time.time() - ts)
    for sec, nm in ((31536000, "year"), (2592000, "month"), (86400, "day"), (3600, "hour"), (60, "minute")):
        if d >= sec:
            n = int(d // sec)
            return f"{n} {nm}{'s' if n != 1 else ''} ago"
    return "just now"


def jv_rel(p, base):
    try:
        return safe(os.path.relpath(p, base))
    except ValueError:
        return safe(p)


def jv_fmt(x):
    return f"{x:,.2f}".rstrip("0").rstrip(".") if isinstance(x, float) else f"{x:,}"


def jv_listing(folder="."):
    """The visible entries of a folder in the same order as Get-ChildItem (folders first)."""
    try:
        voci = [(n, os.path.join(folder, n)) for n in os.listdir(folder)]
    except OSError:
        return []
    voci = [(n, p) for n, p in voci if not nascosto(p, n)]
    dirs = sorted([v for v in voci if os.path.isdir(v[1])], key=lambda v: v[0].lower())
    files = sorted([v for v in voci if not os.path.isdir(v[1])], key=lambda v: v[0].lower())
    return [os.path.abspath(p) for _, p in dirs + files]


def jv_games(depth=6):
    """The data.win files of the known game folders, in the same order undersopic.key lists them."""
    seen, res = set(), []
    for p in find_named(game_locations() + jv_launch_extra_dirs(), GM_FILE, depth):
        key = os.path.normcase(os.path.realpath(p))
        if key not in seen:
            seen.add(key)
            res.append(p)
    return res


def jv_color_prompt(color, text):
    return f"\x01{color}\x02{text}\x01{TEXT}\x02" if HAS_READLINE else color + text + TEXT


# ---------------- finding the file / folder a sentence is about ----------------
def jv_resolve(cand, strict=False, games=False):
    """Turn a phrase ('data.win', 'the second one', 'undertale', 'biggest file') into a path.
    Returns (status, payload): ok/path, many/[paths], range/count, pron/None, none/None."""
    c0 = re.sub(r"[\s.,;:!?]+$", "", cand.strip().strip("\"'`“”‘’").strip())
    low0 = c0.lower()
    if low0 in JV_PRON:
        return "pron", None
    if low0 in JV_HERE:
        return "ok", os.getcwd()
    if c0:
        for v in (c0, os.path.expanduser(c0)):
            if os.path.exists(v):
                return "ok", os.path.abspath(v)
    c = re.sub(r"^(?:the|il|lo|la|l'|my|that|this|quel|quello|quella)\s+", "", c0, flags=re.I)
    c = re.sub(r"^(?:file|folder|directory|cartella|document|documento|game|gioco)\s+", "", c, flags=re.I)
    c = re.sub(r"^(?:called|named|chiamato|chiamata)\s+", "", c, flags=re.I)
    c = c.strip().strip("\"'`").strip()
    low = c.lower()
    if not low or low in JV_PRON:
        return "pron", None
    if low in JV_HERE:
        return "ok", os.getcwd()
    if os.path.exists(c):
        return "ok", os.path.abspath(c)
    games_word = bool(re.search(r"\b(?:game|games|gioco|giochi)\b", low0))

    idx = None
    m = re.fullmatch(r"(?:#|n\.?\s*|no\.?\s*|number\s+|numero\s+)?(\d{1,4})(?:st|nd|rd|th)?"
                     r"(?:\s+(?:one|file|game|result|item|gioco|risultato))?", low)
    if m:
        idx = int(m.group(1))
    else:
        m = re.fullmatch(r"(first|second|third|fourth|fifth|last|primo|prima|secondo|seconda|terzo|terza|quarto|"
                         r"quarta|quinto|quinta|ultimo|ultima|1st|2nd|3rd|4th|5th)"
                         r"(?:\s+(?:one|file|game|result|item|gioco|risultato|folder|cartella))?", low)
        if m:
            idx = JV_ORD[m.group(1)]
    if idx is not None:
        pool = jv_games() if games_word else (CONTESTO.get("jlist") or jv_listing())
        pool = [p for p in pool if os.path.exists(p)]
        if not pool:
            return "none", None
        if idx == -1:
            return "ok", pool[-1]
        return ("ok", pool[idx - 1]) if 1 <= idx <= len(pool) else ("range", len(pool))

    m = re.fullmatch(r"(?:the\s+)?(biggest|largest|heaviest|smallest|lightest|newest|latest|most recent|oldest|"
                     r"più grande|piu grande|più pesante|piu pesante|più piccolo|piu piccolo|più recente|piu recente|"
                     r"più vecchio|piu vecchio)(?:\s+(?:file|one|here|in (?:this )?folder|qui))*", low)
    if m:
        files = [p for p in jv_listing() if os.path.isfile(p)]
        if not files:
            return "none", None
        w = m.group(1)
        try:
            if w in ("biggest", "largest", "heaviest", "più grande", "piu grande", "più pesante", "piu pesante"):
                return "ok", max(files, key=os.path.getsize)
            if w in ("smallest", "lightest", "più piccolo", "piu piccolo"):
                return "ok", min(files, key=os.path.getsize)
            if w in ("oldest", "più vecchio", "piu vecchio"):
                return "ok", min(files, key=os.path.getmtime)
            return "ok", max(files, key=os.path.getmtime)
        except OSError:
            return "none", None

    try:
        names = os.listdir(".")
    except OSError:
        names = []
    exact = [n for n in names if n.lower() == low]
    if exact:
        return "ok", os.path.abspath(exact[0])
    stem = [n for n in names if os.path.splitext(n)[0].lower() == low]
    if len(stem) == 1:
        return "ok", os.path.abspath(stem[0])
    if len(stem) > 1:
        return "many", [os.path.abspath(n) for n in sorted(stem, key=str.lower)]
    if not strict and len(low) >= 2:
        part = [n for n in names if low in n.lower()]
        pool = [n for n in part if n.lower().startswith(low)] or part
        if len(pool) == 1:
            return "ok", os.path.abspath(pool[0])
        if 1 < len(pool) <= 12:
            return "many", [os.path.abspath(n) for n in sorted(pool, key=str.lower)]
        close = difflib.get_close_matches(low, [n.lower() for n in names], n=1, cutoff=0.72)
        if close:
            return "ok", os.path.abspath(next(n for n in names if n.lower() == close[0]))
    seen = 0                                           # a little deeper: exact names in sub-folders
    for cur, ds, fs in os.walk(".", onerror=lambda e: None):
        depth = 0 if cur == "." else os.path.relpath(cur).count(os.sep) + 1
        ds[:] = [] if depth >= 3 else sorted(d for d in ds if not skip_dir(os.path.join(cur, d)))
        for n in ds + fs:
            seen += 1
            if n.lower() == low or os.path.splitext(n)[0].lower() == low:
                return "ok", os.path.abspath(os.path.join(cur, n))
        if seen > 20000:
            break
    if games and len(low) >= 3:
        hits = []
        for p in jv_games():
            try:
                nm = (gm_read_info(p)["name"] or "").lower()
            except OSError:
                nm = ""
            folder = os.path.basename(os.path.dirname(os.path.abspath(p))).lower()
            if re.fullmatch(JV_LAUNCH_CHAPTER, folder):
                folder = os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(p)))).lower() + " " + folder
            if low in folder or (nm and low in nm):
                hits.append(p)
        if len(hits) == 1:
            return "ok", hits[0]
        if hits:
            return "many", hits[:12]
    return "none", None


def jv_find_target(orig, t):
    """(path, True) when the sentence names an existing file/folder; (None, False) otherwise."""
    for m in re.finditer(r'"([^"]+)"|`([^`]+)`|“([^”]+)”|(?<!\w)\'([^\']+)\'(?!\w)', orig):
        s = next(g for g in m.groups() if g)
        v = os.path.expanduser(s)
        if os.path.exists(v):
            return os.path.abspath(v), True
    skip = {"file", "files", "folder", "folders", "here", "this", "that", "it", "the", "all", "game", "games",
            "data", "size", "type", "lines", "words", "text", "in", "of", "to", "on", "is", "and", "me", "my"}
    for tok in orig.split():
        s = tok.strip(".,;:!?()[]{}\"'`")
        if len(s) >= 2 and s.lower() not in skip and s not in (".", "..") and os.path.exists(os.path.expanduser(s)):
            return os.path.abspath(os.path.expanduser(s)), True
    try:
        names = sorted(os.listdir("."), key=len, reverse=True)
    except OSError:
        names = []
    for n in names:
        nl = n.lower()
        if len(nl) >= 3 and (" " in nl or "." in nl) and re.search(r"(?<![\w.-])" + re.escape(nl) + r"(?![\w-])", t):
            return os.path.abspath(n), True
    for tok in jv_filename_tokens(orig):                    # a name that lives a few folders down
        st, pay = jv_resolve(tok, strict=True)
        if st == "ok":
            return pay, True
    return None, False


def jv_filename_tokens(orig):
    """Words that look like file names (name.ext with a known extension)."""
    known = {e.lstrip(".") for e in TEXT_EXT} | {e.lstrip(".") for e in OFFICE} | set(JV_EXTWORDS) | \
        {"win", "db", "sqlite3", "gz", "dat", "bin", "iso", "tar", "7z", "ini", "log", "dll", "sys"}
    res = []
    for tok in orig.split():
        s = tok.strip(".,;:!?()[]{}\"'`")
        m = re.fullmatch(r"[\w\-.]*\w\.([A-Za-z0-9]{1,6})", s)
        if m and m.group(1).lower() in known:
            res.append(s)
    return res


def jv_target(orig, t, sel):
    p, explicit = jv_find_target(orig, t)
    if p:
        CONTESTO["jlast"] = {"path": p, "sel": sel}
        return p, True
    last = CONTESTO.get("jlast")
    if last and os.path.exists(last["path"]) and (sel is None or last["sel"] == sel):
        return last["path"], False
    if sel and os.path.exists(sel):
        return sel, False
    return None, False


def jv_hint(kind):
    if kind == "GameMaker data file":
        ex = '"what game is this", "how many sprites", "list the chunks", "search for <text>"'
    elif kind.startswith("Text file"):
        ex = '"how many lines", "first 20 lines", "search for <word>", "columns" (for csv), "which keys" (for json)'
    elif is_zip(kind):
        ex = '"what is inside", "biggest entry", "does it contain <name>"'
    elif kind == "SQLite database":
        ex = '"which tables", "how many rows in <table>", "columns of <table>"'
    elif kind.endswith("image"):
        ex = '"dimensions", "is it corrupt", "sha256"'
    elif kind == "Windows executable":
        ex = '"is it 64-bit", "when was it built", "is it signed"'
    elif kind == "PDF document":
        ex = '"how many pages", "is it corrupt", "sha256"'
    else:
        ex = '"how big is it", "when was it modified", "is it corrupt", "sha256", "show me the hex"'
    jarvis_say("It's selected, sir. You can ask me, for instance: " + ex + ".")


# ---------------- opening / selecting / reading ----------------
def jv_open_view(path, select_only=False):
    full = os.path.abspath(path)
    if os.path.isdir(full):
        try:
            os.chdir(full)
        except OSError as e:
            jarvis_say(f"I can't enter '{safe(full)}', sir ({e.strerror}).")
            return
        CONTESTO["file"] = None
        ack(f"Entering {safe(os.path.basename(full) or full)}.")
        esegui("Get-ChildItem")
        CONTESTO["jlist"] = jv_listing()
        return
    try:
        os.chdir(os.path.dirname(full))
    except OSError:
        pass
    CONTESTO["file"] = full
    CONTESTO["jlast"] = {"path": full, "sel": full}
    kind, name = detect_kind(full), safe(os.path.basename(full))
    if select_only:
        try:
            jarvis_say(f"Selected {name} ({kind}, {human(os.path.getsize(full))}).")
        except OSError:
            jarvis_say(f"Selected {name}.")
    else:
        ack(f"Opening {name}. Read-only: I only look inside, I never run or change it.")
        interact_port([full])
    jv_hint(kind)


def jv_read_paged(path):
    text, enc = read_text(path)
    lines = text.splitlines()
    part = os.path.getsize(path) > MAX_TEXT
    jarvis_say(f"{safe(os.path.basename(path))}: {len(lines):,} line(s), {enc}"
               f"{', showing the first 5 MB only' if part else ''}.")
    width = max(40, shutil.get_terminal_size((100, 30)).columns - 9)
    page = max(10, shutil.get_terminal_size((100, 30)).lines - 3)
    interactive = sys.stdin.isatty() and sys.stdout.isatty()
    shown = 0
    for i, line in enumerate(lines, 1):
        out(f"{i:>6} | {safe(line)[:width]}")
        shown += 1
        if not interactive and shown >= 300:
            out(f"  ... {len(lines) - i:,} more line(s)", GRAY)
            break
        if interactive and shown % page == 0 and i < len(lines):
            try:
                ans = input(jv_color_prompt(GRAY, "-- Enter = next page, q = stop -- "))
            except (EOFError, KeyboardInterrupt):
                out()
                break
            if ans.strip().lower() in ("q", "quit", "stop", "exit", "n", "no"):
                break
    out()


def jv_open_request(orig, t, sel):
    pre = r"^(?:(?:please|pls|per favore|per piacere)[,\s]+)?(?:(?:can|could|would|will) you(?: please)?\s+|" \
          r"(?:puoi|potresti|mi puoi|mi potresti)\s+)?"
    m = re.match(pre + r"(open|apri(?:mi)?|view|read|leggi(?:mi)?|display|show me|show|mostrami|mostra|guarda|"
                       r"look at|check out|select|choose|pick|use|seleziona|scegli|"
                       r"launch|start|play|run|avvia(?:mi)?|lancia(?:mi)?|esegui|fai partire|fammi giocare a|"
                       r"giocare a|gioca a|gioca)\s+(.+)$", orig, re.I)
    if not m:
        return False
    verb, rest = m.group(1).lower(), m.group(2).strip()
    if verb in ("launch", "start", "play", "run", "avvia", "avviami", "lancia", "lanciami", "esegui", "fai partire",
                "fammi giocare a", "giocare a", "gioca a", "gioca"):
        # only a game of this PC, and only when spoken to Jarvis by name; anything else is not for this handler
        return bool(CONTESTO.get("jv_named") and (jv_launch_try(rest) or jv_launch_search(rest)))
    if verb in ("select", "choose", "pick", "use", "seleziona", "scegli"):
        mode = "select"
    elif verb in ("read", "leggi", "leggimi"):
        mode = "read"
    elif verb in ("open", "apri", "aprimi"):
        mode = "open"
    else:
        mode = "show"
    strict = mode in ("read", "show")
    if mode == "open" and CONTESTO.get("jv_named") and jv_launch_try(rest):
        return True                                   # 'jarvis open <game>' started (or listed) a game
    st, pay = jv_resolve(rest, strict=strict, games=not strict)
    tail = None
    if st in ("none", "range"):
        for sm in re.finditer(r"(?:\s*,\s*|\s+(?:and then|and|then|e poi|poi|e)\s+)", rest, re.I):
            st2, pay2 = jv_resolve(rest[:sm.start()], strict=strict, games=not strict)
            if st2 in ("ok", "many", "pron"):
                st, pay, tail = st2, pay2, rest[sm.end():].strip()
                break
    if st == "pron":
        last = CONTESTO.get("jlast")
        path = sel if (sel and os.path.exists(sel)) else (last["path"] if last and os.path.exists(last["path"]) else None)
        if path is None:
            if strict:
                return False
            jarvis_say("No file is selected yet, sir. Tell me which one: 'open <file>'.")
            show_file_choices()
            return True
        st, pay = "ok", path
    if st == "many":
        if strict:
            return False
        jarvis_say("Several things match, sir. Which one?")
        for i, p in enumerate(pay, 1):
            out(f"  [{i}] {safe(os.path.relpath(p) if not os.path.isabs(os.path.relpath(p)) else p)}", CYAN)
        CONTESTO["jlist"] = pay
        jarvis_say("Say 'open 1', 'open 2'... or give me the exact name.")
        return True
    if st == "range":
        if strict:
            return False
        jarvis_say(f"There are only {pay} item(s) in that list, sir.")
        return True
    if st == "none":
        if strict:
            return False
        if mode == "open" and CONTESTO.get("jv_named") and jv_launch_search(rest):
            return True
        cand = re.sub(r"\s+", " ", rest)
        jarvis_say(f"I can't find '{safe(cand)}', sir. I looked in this folder, three levels of sub-folders and your game folders.")
        close = difflib.get_close_matches(cand.lower(), [n.lower() for n in os.listdir(".")], n=3, cutoff=0.5)
        if close:
            jarvis_say("Did you mean: " + ", ".join(safe(n) for n in close) + "?")
        else:
            jarvis_say("Say 'list' to see what is here.")
        return True
    if mode == "open" and CONTESTO.get("jv_named") and os.path.isfile(pay):
        jv_launch_file(pay)                           # 'jarvis open <file>' really opens the file
    elif mode == "select":
        jv_open_view(pay, select_only=True)
    elif mode == "read" and os.path.isfile(pay) and detect_kind(pay).startswith("Text file"):
        CONTESTO["file"] = os.path.abspath(pay)
        CONTESTO["jlast"] = {"path": CONTESTO["file"], "sel": CONTESTO["file"]}
        try:
            os.chdir(os.path.dirname(CONTESTO["file"]))
        except OSError:
            pass
        ack("Reading it, read-only.")
        jv_read_paged(pay)
    else:
        jv_open_view(pay)
    if tail:
        was = CONTESTO.get("jv_cmd")
        CONTESTO["jv_cmd"] = CONTESTO.get("jv_named")
        try:
            jarvis_interpret(tail)
        finally:
            CONTESTO["jv_cmd"] = was
    return True


def jv_selection(orig, t, sel):
    if re.search(r"\b(?:deselect|unselect|clear (?:the |my )?selection|forget (?:the |this |that )?file|deseleziona|"
                 r"annulla (?:la )?selezione|rimuovi (?:la )?selezione|drop (?:the )?file)\b", t):
        if sel:
            CONTESTO["file"] = None
            CONTESTO.pop("jlast", None)
            jarvis_say(f"Selection cleared, sir. {safe(os.path.basename(sel))} is no longer selected.")
        else:
            jarvis_say("Nothing is selected, sir.")
        return True
    if re.search(r"^(?:what|which|quale|cosa|che)\b.*\b(?:selected|selezionat\w*|chosen|scelto|am i using|are we using|"
                 r"working (?:on|with)|current file|file corrente)\b", t):
        if sel and os.path.exists(sel):
            try:
                jarvis_say(f"{safe(os.path.basename(sel))}, sir: {detect_kind(sel)}, {human(os.path.getsize(sel))}.")
            except OSError:
                jarvis_say(f"{safe(os.path.basename(sel))}, sir.")
            out(f"  {safe(sel)}", GRAY)
        else:
            jarvis_say("No file is selected, sir. Say 'open <file>' or 'select <file>'.")
        return True
    return False


def jv_navigate(orig, t):
    m = re.match(r"^(?:please\s+|per favore\s+)?(?:go|move|navigate|vai|andiamo|torna|tornare)\b\s*(.*)$", t)
    if not m and not re.fullmatch(r"(?:up|back|indietro)", t):
        return False
    rest = m.group(1).strip() if m else t
    home = os.path.expanduser("~")
    if re.fullmatch(r"(?:up|back|up one(?: level| folder)?|back one(?: level| folder)?|up a (?:level|folder)|"
                    r"to the parent(?: folder)?|indietro|su|su di (?:una|1) cartella|alla cartella superiore|"
                    r"back to the parent(?: folder)?|(?:up|back)(?: a| one)? level)", rest):
        dest = ".."
    elif re.fullmatch(r"(?:(?:to |in |a |alla |nella )?(?:the )?(?:home|casa)(?: folder| directory| cartella)?)", rest):
        dest = home
    else:
        rest = re.sub(r"^(?:to|into|in|a|alla|nella|nel|al)\s+(?:the\s+|la\s+|il\s+)?(?:folder\s+|cartella\s+)?", "", rest).strip()
        if not rest:
            return False
        aliases = {"downloads": "Downloads", "download": "Downloads", "desktop": "Desktop", "scrivania": "Desktop",
                   "documents": "Documents", "documenti": "Documents", "pictures": "Pictures", "immagini": "Pictures",
                   "music": "Music", "musica": "Music", "videos": "Videos", "video": "Videos"}
        dest = None
        if rest.lower() in aliases:
            cand = os.path.join(home, aliases[rest.lower()])
            dest = cand if os.path.isdir(cand) else None
        if dest is None:
            st, pay = jv_resolve(rest, strict=False)
            if st == "ok" and os.path.isdir(pay):
                dest = pay
        if dest is None:
            if rest.lower() in aliases or re.fullmatch(r"[\w .\-]{1,60}", rest):
                jarvis_say(f"I can't find a folder called '{safe(rest)}', sir.")
                return True
            return False
    try:
        os.chdir(dest)
        CONTESTO["file"] = None
        CONTESTO["jlist"] = jv_listing()
        jarvis_say(f"Now in {safe(os.getcwd())}.")
    except OSError as e:
        jarvis_say(f"I can't go there, sir ({e.strerror}).")
    return True


def jv_uptime():
    try:
        import psutil
        return time.time() - psutil.boot_time()
    except Exception:
        pass
    try:
        if os.name == "nt":
            import ctypes
            return ctypes.windll.kernel32.GetTickCount64() / 1000.0
        with open("/proc/uptime", encoding="utf-8", errors="replace") as f:
            return float(f.read().split()[0])
    except Exception:
        return None


def jv_global(t):
    now = datetime.now()
    if re.search(r"\bwhat time\b|\bcurrent time\b|\btime is it\b|\bche ore\b|\bche ora\b|\bwhat'?s the time\b", t):
        jarvis_say(f"It is {now.strftime('%H:%M')}, sir.")
        return True
    if re.search(r"today'?s date|\bwhat(?:'s| is) (?:the )?(?:date|day)\b|\bwhat day\b|\bche giorno\b|\bche data\b|"
                 r"\bcurrent date\b|\bdata di oggi\b", t):
        jarvis_say(f"Today is {now.strftime('%A, %d %B %Y')}, sir.")
        return True
    folderish = re.search(r"folder|director|cartella|\bfiles?\b|\bfile\b", t)
    if not folderish and (re.search(r"\b(?:free|left|available|remaining|libero|liber[ae]|disponibile|rimast\w+)\b.*"
                                    r"\b(?:space|disk|storage|drive|spazio|disco)\b", t)
                          or re.search(r"\b(?:disk|drive|storage|disco)\s+(?:space|usage|capacity)\b|\bspazio\b.*\b(?:libero|disco)\b|"
                                       r"\bhow much (?:disk |storage )?space\b", t)):
        try:
            tot, used, free = shutil.disk_usage(os.getcwd())
            jarvis_say(f"The drive of this folder has {human(free)} free of {human(tot)} ({used * 100 // tot}% used), sir.")
        except OSError as e:
            jarvis_say(f"I can't read the disk figures, sir ({e.strerror}).")
        return True
    if re.search(r"\bpython version\b|\bwhich python\b|\bversione di python\b", t):
        jarvis_say(f"Python {sys.version.split()[0]} on {sys.platform}, sir.")
        return True
    if re.search(r"\bwhat os\b|\bwhich os\b|operating system|sistema operativo|windows version|versione di windows", t):
        import platform
        jarvis_say(f"{platform.platform()}, sir.")
        return True
    if re.search(r"how many (?:cpu|cores?|processors?)|\bcpu cores?\b|quanti (?:core|processori)|number of cores", t):
        jarvis_say(f"{os.cpu_count()} logical processor(s), sir.")
        return True
    if re.search(r"\buptime\b|how long (?:has|have) (?:this|the) (?:pc|computer) been (?:on|running)|\bacceso da\b", t):
        up = jv_uptime()
        if up is None:
            jarvis_say("I can't read the uptime on this system, sir.")
        else:
            d, rem = divmod(int(up), 86400)
            jarvis_say(f"Up for {d} day(s), {rem // 3600} hour(s) and {rem % 3600 // 60} minute(s), sir.")
        return True
    if re.search(r"\bwho am i\b|\bmy user ?name\b|\bhostname\b|\bcomputer name\b|\bnome (?:utente|del computer)\b", t):
        import getpass
        import socket
        try:
            who = getpass.getuser()
        except Exception:
            who = "unknown"
        jarvis_say(f"You are {safe(who)} on {safe(socket.gethostname())}, sir.")
        return True
    return False


def jv_examples(t):
    if not re.search(r"\bexamples?\b|\besempi\b|what can i ask|cosa posso chiedere|what (?:else )?can you answer|"
                     r"what do you know|capabilit", t):
        return False
    jarvis_say("Here is what I can answer, sir. All read-only, except the START A GAME, LAUNCH and UPDATE rows:")
    rows = [
        ("OPEN", 'open data.win   |   open the 2nd one   |   open undertale   |   read notes.txt   |   go up'),
        ("START A GAME", 'jarvis open deltarune   |   jarvis open undertale   |   jarvis open deltarune chapter 2   (plain "open deltarune" never starts it)'),
        ("LAUNCH", 'launch backup.py   |   launch "D:\\Tools\\app.exe"   |   jarvis launch notes.txt   (never asks for administrator rights)'),
        ("VOICE", 'voice on   |   voice off   |   jarvis be quiet   (JARVIS speaks only when you ask)'),
        ("ANY FILE", 'how big is it   |   when was it modified   |   what type is it   |   is it corrupt   |   sha256   |   does the md5 match <hash>'),
        ("TEXT", 'how many lines/words   |   first 20 lines   |   last 5 lines   |   lines 10 to 20   |   search for "word"   |   hex dump'),
        ("CSV / JSON", 'which columns   |   average of <column>   |   first 5 rows   |   which keys   |   value of <key>'),
        ("ZIP / DB", 'what is inside   |   biggest entry   |   which tables   |   how many rows in <table>   |   columns of <table>'),
        ("IMAGE / PDF / EXE", 'dimensions   |   how many pages   |   is it 64-bit   |   when was it built   |   is it signed'),
        ("GAMES (data.win)", 'what game is this   |   how many sprites/rooms/sounds   |   list the chunks   |   biggest chunk   |   search for "text"'),
        ("FOLDER", 'how many files here   |   biggest files   |   newest / oldest   |   find all png files   |   duplicates   |   bigger than 100 MB   |   modified today   |   by extension'),
        ("PC", 'free disk space   |   what time is it   |   uptime   |   status   |   find my games   |   scan this PC for corrupt files'),
        ("KNOWLEDGE", 'what is a dll / sha256 / data.win   |   what does dir do   |   tell me about undertale   |   who made you'),
        ("MATHS / UNITS", 'calculate 15% of 80   |   2+2*3   |   square root of 144   |   convert 5 km to miles   |   100 f to c   |   2 gb in mb'),
        ("DATES", 'how many days until christmas   |   what day is 25/12/2026   |   days between 1/1/2026 and 1/3/2026'),
        ("CHAT", 'jarvis perfect   |   yo big jarvis   |   tell me a joke   |   how are you   |   again (repeats my last request)'),
        ("ONLINE / RESEARCH", 'jarvis be online   |   jarvis search <topic>   |   jarvis cerca <topic>   |   jarvis go offline'),
        ("CHROME (online)", 'jarvis open chrome then gmail on account anna   |   open chrome, youtube lofi and canva   |   apri chrome poi gmail con account paolo'),
        ("CHROME LAYOUT", 'chrome full screen   |   chrome side by side   |   open chrome full screen then gmail   |   apri chrome accanto poi canva'),
        ("NEWS (online)", 'jarvis news   |   jarvis news war   |   jarvis notizie sulle proteste   (world stories in parts, photo + long summary)'),
        ("SECURITY / UPDATE", 'security   |   implement jarvis   |   implement jarvis -Dry   |   implement jarvis <file.py>   |   go in maintenance'),
    ]
    w = max(len(a) for a, _ in rows)
    for a, b in rows:
        out(f"  {a.ljust(w)}  {b}", CYAN)
    out()
    return True


