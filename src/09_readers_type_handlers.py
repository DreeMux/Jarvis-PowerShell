# ---------------- extra readers (all read-only) ----------------
def jv_gm_chunks(path):
    """[(chunk id, data start, data length)] of a GameMaker data file."""
    res = []
    size = os.path.getsize(path)
    with open(guard_path(path), "rb") as f:
        head = f.read(8)
        if len(head) < 8 or head[:4] != b"FORM":
            return res
        end = min(struct.unpack("<I", head[4:8])[0] + 8, size)
        pos = 8
        while pos + 8 <= end and len(res) < 256:
            f.seek(pos)
            hdr = f.read(8)
            if len(hdr) < 8:
                break
            cid, ln = hdr[:4], struct.unpack("<I", hdr[4:8])[0]
            if not re.fullmatch(rb"[A-Z0-9]{4}", cid):
                break
            res.append((cid.decode(), pos + 8, ln))
            pos += 8 + ln
    return res


def jv_gm_count(path, start, ln):
    if ln < 4:
        return None
    with open(guard_path(path), "rb") as f:
        f.seek(start)
        cnt = struct.unpack("<I", f.read(4))[0]
    return cnt if cnt * 4 + 4 <= ln else None


def jv_pe(path):
    with open(guard_path(path), "rb") as f:
        mz = f.read(64)
        if len(mz) < 64 or mz[:2] != b"MZ":
            return None
        f.seek(struct.unpack("<I", mz[60:64])[0])
        if f.read(4) != b"PE\x00\x00":
            return None
        machine, _, ts, _, _, optsz, chars = struct.unpack("<HHIIIHH", f.read(20))
        opt = f.read(optsz)
    if len(opt) < 70:
        return None
    magic = struct.unpack("<H", opt[:2])[0]
    sub = struct.unpack("<H", opt[68:70])[0]
    dd = 96 if magic == 0x10B else 112
    signed = dotnet = False
    if len(opt) >= dd + 120:
        signed = struct.unpack("<II", opt[dd + 32:dd + 40])[1] > 0
        dotnet = struct.unpack("<II", opt[dd + 112:dd + 120])[1] > 0
    return {"machine": PE_MACHINES.get(machine, f"unknown machine 0x{machine:04X}"), "ts": ts,
            "dll": bool(chars & 0x2000), "subsystem": {2: "graphical (GUI)", 3: "console"}.get(sub, f"type {sub}"),
            "signed": signed, "dotnet": dotnet}


def jv_hex_rows(data, base=0):
    rows = []
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        hx = " ".join(f"{b:02X}" for b in chunk).ljust(47)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        rows.append(f"  {base + i:08X}  {hx}  {asc}")
    return rows


def jv_term(orig, t, path):
    """The word/phrase the person wants searched for in a file."""
    for m in re.finditer(r'"([^"]+)"|`([^`]+)`|“([^”]+)”|(?<!\w)\'([^\']+)\'(?!\w)', orig):
        s = next(g for g in m.groups() if g)
        if not os.path.exists(os.path.expanduser(s)):
            return s
    stop = {"the", "a", "an", "it", "this", "that", "file", "files", "in", "text", "something", "anything", "any",
            "for", "inside", "whether", "if", "word", "string", "phrase", "is", "there", "il", "la", "lo", "un", "una"}
    pats = [r"(?:the\s+)?(?:word|text|string|phrase|parola|frase|stringa)\s+(\S+)",
            r"(?:search|find|look)\s+(?:for\s+)?(\S+)\s+(?:in|inside|within|on|dentro|nel|nello|nella|from)\b",
            r"(?:cerca|trova)\s+(\S+)\s+(?:in|dentro|nel|nello|nella)\b",
            r"(?:search(?:\s+for)?|look\s+for|grep|cerca(?:re)?|trova(?:re)?|find)\s+(?:the\s+(?:word|text|string|phrase)\s+|"
            r"la\s+(?:parola|frase)\s+)?(\S+)$",
            r"contains?\s+(?:the\s+)?(\S+)", r"contiene\s+(?:la parola\s+)?(\S+)",
            r"mention(?:s|ing)?\s+(\S+)",
            r"how many times (?:does |is |do )?(\S+)", r"quante volte (?:compare |appare |c'è )?(\S+)"]
    base = os.path.basename(path).lower()
    for p in pats:
        m = re.search(p, orig, re.I)
        if m:
            s = m.group(1).strip(".,;:!?()[]{}\"'`")
            if s and s.lower() not in stop and s.lower() != base:
                return s
    return None


def jv_search(path, term, kind, name):
    tl = term.lower()
    if is_zip(kind):
        try:
            with zipfile.ZipFile(path) as z:
                hits = [i for i in z.infolist() if tl in i.filename.lower()]
        except zipfile.BadZipFile:
            jarvis_say(f"{name} does not open as a ZIP archive, sir: it may be damaged.")
            return
        jarvis_say(f"{len(hits)} entr{'y' if len(hits) == 1 else 'ies'} in {name} match '{safe(term)}' (names only).")
        for i in hits[:20]:
            out(f"  {human(i.file_size).rjust(12)}  {safe(i.filename)}")
        if len(hits) > 20:
            out(f"  ... and {len(hits) - 20:,} more", GRAY)
        out()
        return
    if kind.startswith("Text file"):
        text, enc = read_text(path)
        lines = text.splitlines()
        found = [(i, ln) for i, ln in enumerate(lines, 1) if tl in ln.lower()]
        total = text.lower().count(tl)
        part = " (first 5 MB only)" if os.path.getsize(path) > MAX_TEXT else ""
        if not found:
            jarvis_say(f"'{safe(term)}' does not appear in {name}, sir{part}. The search ignores upper/lower case.")
            return
        jarvis_say(f"'{safe(term)}' appears {total:,} time(s) on {len(found):,} line(s) of {name}{part}.")
        for i, ln in found[:15]:
            out(f"  {i:>6} | {safe(ln.strip())[:110]}")
        if len(found) > 15:
            out(f"  ... and {len(found) - 15:,} more line(s)", GRAY)
        out()
        return
    limit = 64 << 20
    with open(guard_path(path), "rb") as f:
        data = f.read(limit)
    hits = []
    for enc_name in ("utf-8", "utf-16-le"):
        try:
            pat = term.encode(enc_name)
        except UnicodeEncodeError:
            continue
        hits += [(m.start(), enc_name) for m in re.finditer(re.escape(pat), data, re.I)]
    hits.sort()
    part = " (first 64 MB only)" if os.path.getsize(path) > limit else ""
    if not hits:
        jarvis_say(f"I found no '{safe(term)}' inside {name}, sir{part}. Text is searched as UTF-8 and UTF-16, ignoring case.")
        return
    chunks = jv_gm_chunks(path) if kind == "GameMaker data file" else []
    jarvis_say(f"'{safe(term)}' appears {len(hits):,} time(s) in {name}{part}. First {min(len(hits), 15)}:")
    for off, enc_name in hits[:15]:
        ctx = data[max(0, off - 24):off + 48]
        ctx = "".join(chr(b) if 32 <= b < 127 else "." for b in ctx)
        where = next((f" [{cid}]" for cid, s, ln in chunks if s <= off < s + ln), "")
        out(f"  0x{off:08X}{where}  {enc_name}  ...{ctx}...")
    out()


def jv_corrupt_q(path, kind, name, ext):
    if kind == "GameMaker data file" or os.path.basename(path).lower() == GM_FILE:
        info = gm_read_info(path)
        if info["notes"]:
            jarvis_say(f"I see problems in {name}, sir:")
            for n in info["notes"]:
                out(f"  - {n}", YELLOW)
        else:
            jarvis_say(f"{name} looks intact, sir: the FORM length matches the file and all {len(info['chunks'])} chunks parse.")
        return
    status, reason = check_file(path)
    if status == "CORRUPT":
        jarvis_say(f"Yes, sir. {name} is damaged: {reason}.")
    elif status == "WARNING":
        jarvis_say(f"Possibly, sir. {name}: {reason}.")
    elif status == "EMPTY":
        jarvis_say(f"{name} is empty (0 bytes), sir. Nothing to be read from it.")
    elif status == "SKIPPED":
        jarvis_say(f"I did not deep-check {name}, sir: {reason.lower()}.")
    elif ext in INTEGRITY_TEST or ext in ZIP_EXT:
        test = INTEGRITY_TEST.get(ext, "every entry's CRC")
        jarvis_say(f"No damage found, sir. {name} passes my check of {test}.")
    elif ext in TEXT_EXT:
        jarvis_say(f"No damage found, sir. {name} is readable text with no stray NUL bytes.")
    else:
        try:
            with open(guard_path(path), "rb") as f:
                f.read(65536)
            tail_of(path, 4096)
            jarvis_say(f"I found no sign of damage in {name}, sir, but I have no integrity test for this file type: "
                       "all I can say is that it reads fine from start to end markers.")
        except OSError as e:
            jarvis_say(f"I can't read {name} properly, sir ({e.strerror}). It may be damaged.")


# ---------------- per-type question handlers (return True when they answered) ----------------
def jv_gm_q(path, t, name):
    h = lambda *pats: any(re.search(p, t) for p in pats)
    chunks = jv_gm_chunks(path)
    info = gm_read_info(path)
    size = os.path.getsize(path)
    asked = [(cid, label) for pat, cid, label in GM_COUNTS if re.search(r"\b(?:" + pat + r")\b", t)]
    if asked:
        table = {c[0]: c for c in chunks}
        for cid, label in asked:
            if cid not in table:
                jarvis_say(f"{name} has no {cid} chunk, so it lists no {label}, sir.")
                continue
            cnt = jv_gm_count(path, table[cid][1], table[cid][2])
            if cnt is None:
                jarvis_say(f"The {cid} chunk of {name} has an unusual layout, sir: I can't count the {label} safely.")
            else:
                jarvis_say(f"{name} lists {cnt:,} {label} (read from the {cid} chunk header).")
        return True
    if h(r"\bchunks?\b", r"\bbiggest\b.*\b(?:part|section|thing|chunk)\b", r"\btakes? (?:the )?most (?:space|room)\b",
         r"\bwhat takes\b", r"\bpiù pesant\w*\b", r"\bsections?\b"):
        if not chunks:
            jarvis_say(f"I can't read a chunk table from {name}, sir: it may be damaged.")
            return True
        big = h(r"biggest|largest|most|heaviest|takes|pesant|grand")
        rows = sorted(chunks, key=lambda c: -c[2])[:8] if big else chunks
        jarvis_say(f"{name} has {len(chunks)} chunk(s)" + (". The biggest:" if big else ":"))
        for cid, s, ln in rows:
            out(f"  {cid}  {human(ln).rjust(12)}  {ln * 100 / max(size, 1):5.1f}%  - {GM_LABELS.get(cid, '')}")
        out()
        return True
    if h(r"\b(?:what|which|che|quale)\b.*\b(?:game|gioco)\b", r"\bgame name\b", r"\bname of (?:the|this) game\b",
         r"\btitle\b", r"\bgame\b.*\bcalled\b", r"\bgamemaker\b|\bgame ?maker\b", r"\bengine\b", r"\bversion\b|\bversione\b",
         r"\bbytecode\b", r"\bnome del gioco\b", r"\bgioco\b"):
        game = info["name"] or "an unnamed game"
        gm = f", made with GameMaker {info['gm']}" if info["gm"] else ""
        bc = f", bytecode version {info['bytecode']}" if info["bytecode"] is not None else ""
        jarvis_say(f"{name} belongs to {safe(game)}{gm}{bc}, sir. It has {len(chunks)} chunks and weighs {human(size)}.")
        for n in info["notes"]:
            out(f"  Warning: {n}", YELLOW)
        return True
    if h(r"\bstore\b", r"\bsteam\b", r"\bepic\b", r"\bgog\b", r"\bitch\b", r"\binstall\w*\b", r"\bnegozio\b"):
        jarvis_say(f"{name} sits in: {safe(os.path.dirname(os.path.abspath(path)))}  (looks like: {store_of(path)}).")
        return True
    return False


GM_LABELS = {"GEN8": "general info", "OPTN": "options", "LANG": "languages", "EXTN": "extensions", "SOND": "sounds",
             "AGRP": "audio groups", "SPRT": "sprites", "BGND": "backgrounds / tile sets", "PATH": "paths",
             "SCPT": "scripts", "GLOB": "global scripts", "SHDR": "shaders", "FONT": "fonts", "TMLN": "timelines",
             "OBJT": "objects", "ROOM": "rooms", "DAFL": "data files", "TPAG": "texture-page items", "CODE": "code",
             "VARI": "variables", "FUNC": "functions", "STRG": "strings", "TXTR": "textures", "AUDO": "audio",
             "SEQN": "sequences", "ACRV": "animation curves", "TGIN": "texture group info", "DBGI": "debug info",
             "EMBI": "embedded images", "FEDS": "feature flags", "FEAT": "feature flags", "PSEM": "particle systems",
             "PSYS": "particle systems", "UILR": "UI layout"}


def jv_pe_q(path, t, name):
    if not re.search(r"64.?bit|32.?bit|\bx64\b|\bx86\b|\barm\b|architect|architettur|\bcompil\w*|\bbuilt\b|build date|"
                     r"timestamp|\bsigned\b|signature|firma\w*|\bdll\b|\bconsole\b|\bgui\b|\.net|dotnet|subsystem|\bbit\b", t):
        return False
    pe = jv_pe(path)
    if pe is None:
        jarvis_say(f"{name} has a Windows-style header but I can't read its PE structure, sir: it may be damaged.")
        return True
    jarvis_say(f"{name}, sir:")
    from datetime import timezone
    built = ("not recorded" if pe["ts"] in (0, 0xFFFFFFFF) else
             datetime.fromtimestamp(pe["ts"], tz=timezone.utc).strftime("%d/%m/%Y %H:%M UTC") +
             "  (the builder can fake this date)")
    for k, v in (("Architecture", pe["machine"]), ("Kind", "library (DLL)" if pe["dll"] else "program (EXE)"),
                 ("Interface", pe["subsystem"]), ("Built", built),
                 ("Digitally signed", "yes (a signature block is present; I don't validate it)" if pe["signed"] else "no signature block found"),
                 (".NET", "yes, managed code" if pe["dotnet"] else "no (native code)")):
        out(f"  {k.ljust(17)}: {v}")
    out()
    return True


def jv_zip_q(path, t, orig, name):
    h = lambda *pats: any(re.search(p, t) for p in pats)
    if not h(r"entr(?:y|ies)", r"\binside\b", r"\bcontain", r"\blist\b", r"how many (?:files|items|things|documents)",
             r"biggest|largest", r"unpack|extract|decompress|unzip", r"\bcompress", r"\bcontenut", r"\bdentro\b",
             r"quanti file", r"più grand|piu grand", r"\bwhat'?s in\b", r"\bencrypt|password"):
        return False
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        jarvis_say(f"{name} does not open as a ZIP archive, sir: it may be damaged. Ask me 'is it corrupt'.")
        return True
    with z:
        infos = z.infolist()
    files = [i for i in infos if not i.is_dir()]
    total, comp = sum(i.file_size for i in files), sum(i.compress_size for i in files)
    enc = sum(1 for i in infos if i.flag_bits & 1)
    if h(r"unpack|extract|decompress|unzip"):
        jarvis_say("I never unpack archives, sir: I only list them. Here is what is inside.")
    if h(r"biggest|largest|più grand|piu grand"):
        top = sorted(files, key=lambda i: -i.file_size)[:5]
        jarvis_say(f"The biggest entries of {name}:")
        for i in top:
            out(f"  {human(i.file_size).rjust(12)}  {safe(i.filename)}")
        out()
        return True
    if h(r"\bencrypt|password"):
        jarvis_say(f"{enc} of the {len(infos)} entries in {name} are password-protected, sir." if enc else
                   f"No entry in {name} is password-protected, sir.")
        return True
    ratio = f", compressed to {human(comp)} ({comp * 100 // max(total, 1)}%)" if total else ""
    jarvis_say(f"{name} holds {len(files):,} file(s) and {len(infos) - len(files):,} folder(s): {human(total)} unpacked{ratio}."
               + (f" {enc} entr{'y is' if enc == 1 else 'ies are'} password-protected." if enc else ""))
    if not h(r"how many", r"quanti"):
        for i in infos[:30]:
            out(f"  {human(i.file_size).rjust(12)}  {safe(i.filename)}")
        if len(infos) > 30:
            out(f"  ... and {len(infos) - 30:,} more", GRAY)
    out()
    return True


def jv_sqlite_q(path, t, orig, name):
    h = lambda *pats: any(re.search(p, t) for p in pats)
    if not h(r"\btables?\b", r"\brows?\b", r"\bcolumns?\b", r"\bschema\b", r"\brecords?\b", r"\bdatabase\b",
             r"\bfields?\b", r"\btabell\w+", r"\bcolonn\w+", r"\briga\b|\brighe\b", r"\bstruttura\b"):
        return False
    q = lambda n: '"' + n.replace('"', '""') + '"'
    try:
        con = sqlite_open_ro(path)
    except sqlite3.Error as e:
        jarvis_say(f"I can't open {name} as a database, sir ({safe(e)}).")
        return True
    try:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        named = [n for n in tables if re.search(r"(?<![\w])" + re.escape(n.lower()) + r"(?![\w])", t)]
        tab = max(named, key=len) if named else None
        mnum = re.search(r"\b(\d{1,2})\b", t)
        n = min(int(mnum.group(1)), 20) if mnum else 5
        if tab and h(r"\bcolumns?\b", r"\bschema\b", r"\bfields?\b", r"\bcolonn\w+", r"\bstruttura\b"):
            cols = con.execute(f"PRAGMA table_info({q(tab)})").fetchall()
            jarvis_say(f"Table '{safe(tab)}' has {len(cols)} column(s):")
            for c in cols:
                out(f"  {safe(c[1]).ljust(28)} {safe(c[2] or 'no declared type')}{'  (primary key)' if c[5] else ''}")
            out()
        elif tab and h(r"\bfirst\b", r"\btop\b", r"\bsample\b", r"\bshow\b", r"\bprimi\b", r"\bpreview\b", r"\bcontents?\b",
                       r"\bmostra\b", r"\bsome\b"):
            cur = con.execute(f"SELECT * FROM {q(tab)} LIMIT {n}")
            cols = [d[0] for d in cur.description]
            jarvis_say(f"First {n} row(s) of '{safe(tab)}':")
            out("  " + " | ".join(safe(c) for c in cols), YELLOW)
            for row in cur.fetchall():
                out("  " + " | ".join(f"<blob {len(v)} bytes>" if isinstance(v, bytes) else safe(v)[:40] for v in row))
            out()
        elif tab:
            cnt = con.execute(f"SELECT COUNT(*) FROM {q(tab)}").fetchone()[0]
            jarvis_say(f"Table '{safe(tab)}' has {cnt:,} row(s), sir.")
        else:
            res, total = sqlite_tables(path)
            jarvis_say(f"{name} has {total} table(s), sir:")
            for tn, c in res:
                out(f"  {safe(tn).ljust(30)} {c:,} row(s)")
            out()
    except sqlite3.Error as e:
        jarvis_say(f"The database refused that, sir ({safe(e)}).")
    finally:
        con.close()
    return True


def jv_jtype(v):
    return {"dict": "an object", "list": "an array", "str": "a string", "int": "an integer", "float": "a number",
            "bool": "a boolean", "NoneType": "null"}.get(type(v).__name__, type(v).__name__)


def jv_json_q(path, t, orig, name):
    h = lambda *pats: any(re.search(p, t) for p in pats)
    try:
        text, _ = read_text(path, 20 * 1024 * 1024)
        data = json.loads(text.lstrip("\ufeff"))
    except (ValueError, OSError) as e:
        if h(r"\bkeys?\b", r"\bstructure\b", r"\bvalid\b", r"\bschema\b", r"\bvalue\b"):
            jarvis_say(f"{name} is not valid JSON, sir: {safe(e)}.")
            return True
        return False
    key = None
    if isinstance(data, dict):
        for k in data:
            if len(str(k)) >= 3 and re.search(r"(?<![\w])" + re.escape(str(k).lower()) + r"(?![\w])", t):
                if key is None or len(str(k)) > len(str(key)):
                    key = k
    for tok in re.findall(r"[\w\-]+(?:\.[\w\-]+)+", orig):          # dotted path: a.b.c
        node, ok = data, True
        for part in tok.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
                node = node[int(part)]
            else:
                ok = False
                break
        if ok and "." in tok and tok.lower() != name.lower():
            jarvis_say(f"{safe(tok)} = {safe(json.dumps(node, ensure_ascii=False))[:300]}")
            return True
    asks = h(r"\bvalue\b", r"\bwhat(?:'s| is)\b", r"\bshow\b", r"\bget\b", r"\bqual\w*\b", r"\bmostra\b", r"\bdammi\b", r"\bvalore\b")
    if key is not None and asks:
        v = json.dumps(data[key], ensure_ascii=False)
        jarvis_say(f"{safe(key)} is {jv_jtype(data[key])}: {safe(v)[:300]}{' ...' if len(v) > 300 else ''}")
        return True
    if not h(r"\bkeys?\b", r"\bstructure\b", r"\bschema\b", r"how many (?:items|elements|entries|objects|records)",
             r"\bvalid\b", r"\bchiavi?\b", r"\bstruttura\b", r"\bitems?\b"):
        return False
    if isinstance(data, dict):
        jarvis_say(f"{name} is valid JSON: an object with {len(data)} key(s):")
        for k, v in list(data.items())[:25]:
            extra = f" ({len(v)} item(s))" if isinstance(v, (list, dict)) else ""
            out(f"  {safe(k)[:40].ljust(40)} {jv_jtype(v).split(' ', 1)[1]}{extra}")
        if len(data) > 25:
            out(f"  ... and {len(data) - 25} more", GRAY)
    elif isinstance(data, list):
        jarvis_say(f"{name} is valid JSON: an array with {len(data):,} item(s).")
        if data and isinstance(data[0], dict):
            out("  Keys of the first item: " + ", ".join(safe(k) for k in list(data[0])[:15]))
    else:
        jarvis_say(f"{name} is valid JSON holding {jv_jtype(data)}.")
    out()
    return True


def jv_csv_q(path, t, orig, name):
    import csv
    h = lambda *pats: any(re.search(p, t) for p in pats)
    try:
        text, _ = read_text(path)
    except OSError:
        return False
    lines = text.splitlines()
    if not lines:
        return False
    delim = max(",;\t|", key=lines[0].count)
    rows = list(csv.reader(lines, delimiter=delim))
    header, data = rows[0], rows[1:]
    lowh = [c.strip().lower() for c in header]
    col = None
    for i, c in enumerate(lowh):
        if c and re.search(r"(?<![\w])" + re.escape(c) + r"(?![\w])", t) and (col is None or len(c) > len(lowh[col])):
            col = i
    trig = h(r"\bcolumns?\b", r"\bheaders?\b", r"\bfields?\b", r"\bcolonn\w+", r"\bintestazion\w+", r"\brows?\b", r"\brighe\b",
             r"\brecords?\b", r"\baverage\b", r"\bmean\b", r"\bmedia\b", r"\bsum\b", r"\btotal\b", r"\bsomma\b", r"\btotale\b",
             r"\bminimum\b|\bmin\b|\blowest\b|\bsmallest\b", r"\bmaximum\b|\bmax\b|\bhighest\b|\blargest\b|\bbiggest\b",
             r"\bunique\b|\bdistinct\b|\bunici\b", r"\bmost common\b|\bfrequent\b", r"\bsample\b|\bpreview\b")
    if not trig and col is None:
        return False

    def num(v):
        v = v.strip().replace(" ", "")
        try:
            return float(v)
        except ValueError:
            if "," in v and delim != ",":
                try:
                    return float(v.replace(",", "."))
                except ValueError:
                    return None
        return None

    if col is not None and not h(r"\bcolumns?\b", r"\bheaders?\b"):
        vals = [r[col].strip() for r in data if col < len(r) and r[col].strip() != ""]
        nums = [x for x in (num(v) for v in vals) if x is not None]
        cname = safe(header[col].strip())
        if len(nums) >= max(1, len(vals) * 0.8) and not h(r"\bunique\b|\bdistinct\b|\bunici\b|\bmost common\b|\bfrequent\b"):
            if h(r"\bsum\b|\btotal\b|\bsomma\b|\btotale\b") :
                jarvis_say(f"The sum of '{cname}' is {jv_fmt(sum(nums))}, sir ({len(nums):,} values).")
            elif h(r"\baverage\b|\bmean\b|\bmedia\b"):
                jarvis_say(f"The average of '{cname}' is {jv_fmt(sum(nums) / len(nums))}, sir ({len(nums):,} values).")
            elif h(r"\bminimum\b|\bmin\b|\blowest\b|\bsmallest\b"):
                jarvis_say(f"The lowest '{cname}' is {jv_fmt(min(nums))}, sir.")
            elif h(r"\bmaximum\b|\bmax\b|\bhighest\b|\blargest\b|\bbiggest\b"):
                jarvis_say(f"The highest '{cname}' is {jv_fmt(max(nums))}, sir.")
            else:
                jarvis_say(f"'{cname}' is numeric, sir: {len(nums):,} values, sum {jv_fmt(sum(nums))}, "
                           f"average {jv_fmt(sum(nums) / len(nums))}, min {jv_fmt(min(nums))}, max {jv_fmt(max(nums))}.")
        else:
            from collections import Counter
            cnt = Counter(vals)
            jarvis_say(f"'{cname}' has {len(vals):,} filled value(s), {len(cnt):,} distinct. Most common:")
            for v, c in cnt.most_common(8):
                out(f"  {str(c).rjust(7)} x  {safe(v)[:60]}")
            out()
        return True
    if h(r"\bsample\b", r"\bpreview\b", r"\bfirst\b", r"\btop\b", r"\bshow\b") and h(r"\brows?\b", r"\brighe\b", r"\brecords?\b"):
        mnum = re.search(r"\b(\d{1,3})\b", t)
        n = min(int(mnum.group(1)), 50) if mnum else 5
        jarvis_say(f"First {n} data row(s) of {name}:")
        out("  " + " | ".join(safe(c) for c in header), YELLOW)
        for r in data[:n]:
            out("  " + " | ".join(safe(c)[:30] for c in r))
        out()
        return True
    if h(r"\bcolumns?\b", r"\bheaders?\b", r"\bfields?\b", r"\bcolonn\w+", r"\bintestazion\w+"):
        jarvis_say(f"{name} has {len(header)} column(s): " + ", ".join(safe(c.strip()) for c in header[:40]) + ".")
        return True
    jarvis_say(f"{name} has {len(data):,} data row(s) and {len(header)} column(s), sir.")
    return True


def jv_pdf_q(path, t, name):
    if not re.search(r"\bpages?\b|\bpagine\b|\bencrypt\w*\b|\bpassword\b|\bcifrat\w+\b", t):
        return False
    with open(guard_path(path), "rb") as f:
        raw = f.read(20 * 1024 * 1024)
    pages = len(re.findall(rb"/Type\s*/Page[^s]", raw))
    enc = b"/Encrypt" in raw
    if re.search(r"\bencrypt\w*\b|\bpassword\b|\bcifrat\w+\b", t):
        jarvis_say(f"{name} {'is encrypted (it has an /Encrypt entry)' if enc else 'shows no encryption'}, sir.")
    else:
        jarvis_say(f"{name} has about {pages or 'an unknown number of'} page(s), sir"
                   f"{' (the count may be off: some PDFs hide page objects in compressed streams)' if not pages else ''}.")
    return True


def jv_file_q(orig, t, path, explicit):
    name = safe(os.path.basename(path))
    try:
        st = os.stat(path)
    except OSError as e:
        jarvis_say(f"I can't read {name}, sir ({e.strerror}).")
        return True
    size = st.st_size
    kind = detect_kind(path)
    ext = os.path.splitext(path)[1].lower()
    is_text = kind.startswith("Text file")
    is_gm = kind == "GameMaker data file" or os.path.basename(path).lower() == GM_FILE
    h = lambda *pats: any(re.search(p, t) for p in pats)
    fw = (not explicit) and h(r"\b(?:folders?|director(?:y|ies)|cartell\w+|here|qui)\b")
    nonum = lambda: jarvis_say(f"{name} is not a text file ({kind}), sir, so it has no lines to speak of. "
                               f"Ask me for 'the hex' instead.")

    # 1. checksums (and comparing against a hash the person pastes)
    if h(r"\bsha.?256\b", r"\bmd5\b", r"\bchecksums?\b", r"\bhash(?:es)?\b", r"\bdigest\b", r"\bimpronta\b"):
        if size > MAX_HASH:
            jarvis_say(f"{name} is larger than 256 MB, sir: I skip the checksums for files that big.")
            return True
        sha, md = digests(path)
        want_sha, want_md = h(r"\bsha.?256\b") or not h(r"\bmd5\b"), h(r"\bmd5\b") or not h(r"\bsha.?256\b")
        given = re.findall(r"\b[0-9a-fA-F]{64}\b|\b[0-9a-fA-F]{32}\b", orig)
        if given:
            for g in given:
                real, label = (sha, "SHA256") if len(g) == 64 else (md, "MD5")
                if g.upper() == real:
                    jarvis_say(f"The {label} MATCHES, sir: {name} is exactly the file that hash describes.")
                else:
                    jarvis_say(f"The {label} does NOT match, sir. The file gives {real}; you gave {g.upper()}.")
            return True
        jarvis_say(f"Checksums of {name}, sir:")
        if want_sha:
            out(f"  SHA256 : {sha}")
        if want_md:
            out(f"  MD5    : {md}")
        out()
        return True

    # 2. searching inside the file
    searching = h(r"\b(?:search|find|look for|grep|cerca\w*|trova\w*|contain\w*|contiene|mention\w*|appears?|occurrences?|"
                  r"occorrenz\w*)\b", r"how many times", r"quante volte")
    if searching:
        pron = h(r"\b(?:in|inside|within|dentro|nel|nello|from)\s+(?:it|this file|that file|the (?:selected )?file|questo file|quel file|il file|esso)\b",
                 r"\b(?:does|do|did)\s+(?:it|this file|the file|that file)\b", r"\b(?:it|this file|the file)\s+(?:contain|mention|include)",
                 r"\bcontiene\b", r"quante volte", r"how many times")
        folderish_s = h(r"\b(?:folders?|director\w+|cartell\w+|pcs?|computer|everywhere|drives?|disk|here|qui|downloads|desktop)\b")
        content_verb = h(r"\b(?:search|grep|look for|cerca\w*)\b") or bool(re.search(r"[\"“`]", orig))
        term = jv_term(orig, t, path) if (explicit or pron or (content_verb and not folderish_s)) else None
        if term:
            jv_search(path, term, kind, name)
            return True

    # 3. showing lines / hex
    m = (re.search(r"\b(?:first|top|head|primi|prime|prima)\s+(\d+)\s+(?:lines?|righe)\b", t)
         or re.search(r"\b(?:first|top|head|primi|prime)\s+(?:lines?|righe)\b", t))
    if m:
        if not is_text:
            nonum()
            return True
        n = min(int(m.group(1)) if m.groups() else 10, 200)
        lines = read_text(path)[0].splitlines()
        jarvis_say(f"First {min(n, len(lines))} line(s) of {name}:")
        for i, ln in enumerate(lines[:n], 1):
            out(f"  {i:>6} | {safe(ln)[:120]}")
        out()
        return True
    m = (re.search(r"\b(?:last|bottom|tail|ultim[ei])\s+(\d+)\s+(?:lines?|righe)\b", t)
         or re.search(r"\b(?:last|bottom|tail|ultim[ei])\s+(?:lines?|righe)\b", t))
    if m:
        if not is_text:
            nonum()
            return True
        n = min(int(m.group(1)) if m.groups() else 10, 200)
        lines = read_text(path)[0].splitlines()
        start = max(0, len(lines) - n)
        jarvis_say(f"Last {len(lines) - start} line(s) of {name}:")
        for i, ln in enumerate(lines[start:], start + 1):
            out(f"  {i:>6} | {safe(ln)[:120]}")
        out()
        return True
    m = re.search(r"\blines?\s+(\d+)\s*(?:to|-|through|and|a|e)\s*(\d+)\b", t) or \
        re.search(r"\brighe\s+(?:da\s+)?(\d+)\s*(?:a|-|to)\s*(\d+)\b", t)
    if m:
        if not is_text:
            nonum()
            return True
        a, b = int(m.group(1)), min(int(m.group(2)), int(m.group(1)) + 199)
        lines = read_text(path)[0].splitlines()
        jarvis_say(f"Lines {a} to {min(b, len(lines))} of {name} ({len(lines):,} in total):")
        for i in range(max(a, 1), min(b, len(lines)) + 1):
            out(f"  {i:>6} | {safe(lines[i - 1])[:120]}")
        out()
        return True
    m = re.search(r"\b(?:line|riga)\s+(?:number\s+|numero\s+)?(\d+)\b", t)
    if m:
        if not is_text:
            nonum()
            return True
        lines = read_text(path)[0].splitlines()
        i = int(m.group(1))
        if 1 <= i <= len(lines):
            jarvis_say(f"Line {i} of {name}:")
            out(f"  {i:>6} | {safe(lines[i - 1])[:200]}")
        else:
            jarvis_say(f"{name} has only {len(lines):,} line(s), sir.")
        out()
        return True
    if h(r"\bhex(?:dump)?\b", r"\besadecimal\w*\b", r"\b(?:first|primi)\s+\d+\s+bytes?\b", r"\bbytes? at offset\b", r"\boffset\b"):
        mn = re.search(r"\b(\d+)\s+bytes?\b", t)
        mo = re.search(r"\boffset\s+(0x[0-9a-f]+|\d+)\b", t)
        n = min(int(mn.group(1)), 512) if mn else 128
        off = int(mo.group(1), 16 if mo.group(1).startswith("0x") else 10) if mo else 0
        with open(guard_path(path), "rb") as f:
            f.seek(min(off, size))
            data = f.read(n)
        jarvis_say(f"{len(data)} byte(s) of {name} from offset 0x{off:X} (viewing only, nothing is executed):")
        for r in jv_hex_rows(data, off):
            out(r)
        out()
        return True

    # 4. counts and encoding
    if h(r"\bhow many (?:lines?|words?|characters?|chars?|letters?|righe|parole|caratteri)\b", r"\bnumber of (?:lines|words|characters)\b",
         r"\bquant[ie] (?:righe|parole|caratteri)\b", r"\bword count\b", r"\bline count\b", r"\bconta (?:le )?(?:righe|parole)\b",
         r"\bcount (?:the )?(?:lines|words|characters)\b"):
        if not is_text:
            nonum()
            return True
        text, enc = read_text(path)
        part = " (first 5 MB only)" if size > MAX_TEXT else ""
        if ext in (".csv", ".tsv") and h(r"\brows?\b|\brecords?\b|\brighe\b"):
            jarvis_say(f"{name} has {max(len(text.splitlines()) - 1, 0):,} data row(s) plus the header, sir{part}.")
        else:
            jarvis_say(f"{name}: {len(text.splitlines()):,} line(s), {len(text.split()):,} word(s), {len(text):,} character(s){part}.")
        return True
    if h(r"\bencoding\b", r"\bcodifica\b", r"\bcharset\b", r"\butf.?8\b", r"\butf.?16\b") and is_text:
        enc = read_text(path)[1]
        jarvis_say(f"{name} is encoded as {enc}, sir.")
        return True

    # 5. is it damaged?
    if h(r"\bcorrupt\w*\b", r"\bcorrott\w*\b", r"\bdamaged?\b", r"\bdanneggiat\w*\b", r"\bbroken\b", r"\brott[oi]\b", r"\bintact\b",
         r"\bintegr\w*\b", r"\btruncat\w*\b", r"\btroncat\w*\b", r"\btamper\w*\b", r"\bvalid\b(?!\s+json)", r"\bhealthy\b", r"\bsano\b",
         r"\bis it (?:ok|fine)\b", r"\bsafe to open\b"):
        lead = h(r"^(?:is|are|does|do|did|can|could|has|have|will|would|should|è|e'|sono|sembra|looks?|seems?|check|verify|"
                 r"test|controlla|verifica|testa|scan)\b")
        wide = h(r"\b(?:pc|computer|whole|entire|everything|folder|cartella|tutto|intero|all files|every file|games?)\b")
        if (explicit or lead) and not wide:
            jv_corrupt_q(path, kind, name, ext)
            return True

    # 6. image size
    if h(r"\bdimensions?\b", r"\bresolution\b", r"\bpixels?\b", r"\brisoluzione\b", r"how (?:wide|tall)\b", r"\bwidth\b",
         r"\bheight\b", r"\blarghezza\b", r"\baltezza\b", r"\baspect ratio\b"):
        dim = image_size(path, kind) if kind.endswith("image") else None
        if dim:
            from math import gcd
            g = gcd(dim[0], dim[1]) or 1
            jarvis_say(f"{name} is {dim[0]} x {dim[1]} pixels (aspect ratio {dim[0] // g}:{dim[1] // g}), sir.")
        elif kind.endswith("image"):
            jarvis_say(f"{name} is an image but I couldn't read its dimensions, sir. It may be damaged.")
        else:
            jarvis_say(f"{name} is not an image I can measure ({kind}), sir.")
        return True

    # 7. where is it
    if h(r"\bwhere (?:is|are)\s+(?:it|this|that|the file)\b", r"\bpath\b", r"\blocation\b", r"\bpercorso\b", r"\bdove si trova\b",
         r"\bfull ?name\b") and not h(r"\bwhere is the\b.*\b(?:text|word)\b"):
        jarvis_say(f"{name} lives at: {safe(os.path.abspath(path))}" + (f"  (looks like: {store_of(path)})" if is_gm else ""))
        return True

    # 8. type-specific questions
    if is_gm and jv_gm_q(path, t, name):
        return True
    if kind == "Windows executable" and jv_pe_q(path, t, name):
        return True
    if is_zip(kind) and jv_zip_q(path, t, orig, name):
        return True
    if kind == "SQLite database" and jv_sqlite_q(path, t, orig, name):
        return True
    if ext == ".json" and jv_json_q(path, t, orig, name):
        return True
    if ext in (".csv", ".tsv") and is_text and jv_csv_q(path, t, orig, name):
        return True
    if kind == "PDF document" and jv_pdf_q(path, t, name):
        return True

    # 9. dates, size, type
    if not fw and h(r"\b(?:when|quando)\b.*\b(?:modif\w*|creat\w*|chang\w*|updat\w*|edit\w*|sav\w*|made|born|download\w*|open\w*|access\w*|aperto)\b",
                    r"\blast (?:modified|write|changed|updated|edited|opened|accessed)\b", r"\bultima modifica\b", r"\bmodificat[oa]\b",
                    r"\bcreat[oa]\b", r"\bhow old\b", r"\bquanto (?:è )?vecchio\b", r"\bdata di (?:modifica|creazione)\b", r"\bdate\b"):
        fmt = lambda ts: datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M:%S") + f"  ({jv_ago(ts)})"
        born = getattr(st, "st_birthtime", st.st_ctime)
        label = "Created" if os.name == "nt" or hasattr(st, "st_birthtime") else "Status changed"
        if h(r"\bcreat\w*\b", r"\bborn\b", r"\bmade\b", r"\bhow old\b", r"\bvecchio\b", r"\bcreazione\b"):
            jarvis_say(f"{name} was {label.lower()} on {fmt(born)}, sir.")
        elif h(r"\bmodif\w*\b", r"\bchang\w*\b", r"\bupdat\w*\b", r"\bedit\w*\b", r"\bsav\w*\b", r"\bwrite\b"):
            jarvis_say(f"{name} was last modified on {fmt(st.st_mtime)}, sir.")
        elif h(r"\bopen\w*\b", r"\baccess\w*\b", r"\baperto\b"):
            jarvis_say(f"{name} was last accessed on {fmt(st.st_atime)}, sir (some systems don't update this).")
        else:
            jarvis_say(f"Dates of {name}, sir:")
            out(f"  {label.ljust(14)}: {fmt(born)}")
            out(f"  Modified      : {fmt(st.st_mtime)}")
            out(f"  Accessed      : {fmt(st.st_atime)}")
            out()
        return True
    if not fw and h(r"\bhow (?:big|large|heavy)\b", r"\bsize\b", r"\bquanto pesa\b", r"\bpeso\b", r"\bdimension[ei]\b",
                    r"\bhow much (?:space|room)\b", r"\bquanto (?:spazio|è grande)\b", r"\bweigh\b"):
        extra = ""
        try:
            if is_zip(kind):
                with zipfile.ZipFile(path) as z:
                    extra = f" Unpacked it would be about {human(sum(i.file_size for i in z.infolist()))}."
            elif kind == "GZIP archive" and size >= 4:
                with open(guard_path(path), "rb") as f:
                    f.seek(-4, 2)
                    extra = f" Unpacked it would be about {human(struct.unpack('<I', f.read(4))[0])} (from the gzip trailer)."
        except (OSError, zipfile.BadZipFile):
            pass
        jarvis_say(f"{name} weighs {human(size)}" + (f" ({size:,} bytes)" if size >= 1024 else "") + f", sir.{extra}")
        return True
    if not fw and h(r"\bwhat (?:type|kind|sort) of file\b", r"\bwhat (?:format|type|kind)\b", r"\bche (?:tipo|formato)\b", r"\bwhat is (?:it|this|that)\b",
                    r"\bwhat file is (?:it|this)\b", r"\bfile type\b", r"\bextension\b", r"\bestensione\b", r"\bmime\b", r"\bcos'?è\b",
                    r"\bwhat'?s this\b", r"\bwhat is the file\b"):
        mime = "application/octet-stream" if is_gm else (mimetypes.guess_type(path)[0] or "unknown")
        jarvis_say(f"{name} is a {kind}, sir: extension {ext or '(none)'}, MIME type {mime}, {human(size)}.")
        return True
    return False


