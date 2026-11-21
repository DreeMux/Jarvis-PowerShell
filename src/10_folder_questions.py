# ---------------- folder-level questions ----------------
def jv_filter(orig, t):
    """(predicate, description) from words like 'png files', '*.txt', 'named report', or None."""
    import fnmatch
    exts, names, globs = set(), [], []
    for m in re.finditer(r"(?<![\w.])\*?\.([a-z0-9]{1,6})\b", t):
        exts.add(m.group(1))
    for w in re.findall(r"\b(" + "|".join(JV_EXTWORDS) + r")s?\b", t):
        exts.add(w)
    for words, cat in JV_CATS:
        if any(re.search(r"\b" + re.escape(w) + r"\b", t) for w in words):
            exts.update(cat)
    globs = [g for g in re.findall(r"[\w.\-*?]*[*?][\w.\-*?]*", orig) if len(g) > 1 and not re.fullmatch(r"\*?\.[a-z0-9]{1,6}", g.lower())
             and not re.fullmatch(r"\*\.[a-z0-9]{1,6}", g.lower())]
    for m in re.finditer(r'"([^"]+)"|`([^`]+)`|“([^”]+)”', orig):
        s = next(g for g in m.groups() if g)
        if not os.path.exists(os.path.expanduser(s)):
            names.append(s)
    m = re.search(r"(?:named|called|name contains|containing|chiamat[oi]|nome)\s+([\w.\- ]+?)(?:\s+(?:in|inside|on|from|under|within|here)\b|$)", t)
    if m and not names:
        names.append(m.group(1).strip())
    if not (exts or names or globs):
        m = re.match(r"^(?:find|search(?: for)?|locate|where is|where are|trova|cerca|dov['’]?\s?[eè])\s+(?:the\s+|my\s+|il\s+|la\s+|i\s+)?"
                     r"(?:file\s+)?(?:called\s+|named\s+)?([\w.\-]+)(?:\s+(?:in|inside|under|within|nel|nella|here|qui)\b.*)?$", t)
        block = {"my", "games", "game", "files", "file", "everything", "it", "something", "anything", "stuff", "data.win",
                 "corrupt", "folders", "folder", "giochi", "gioco", "tutto", "duplicates", "duplicati", "the", "all"}
        if m and m.group(1) not in block:
            names.append(m.group(1))
    if not (exts or names or globs):
        return None

    def pred(p):
        n = os.path.basename(p).lower()
        e = os.path.splitext(n)[1].lstrip(".")
        return ((not exts or e in exts) and all(fnmatch.fnmatch(n, g.lower()) for g in globs)
                and all(s.lower() in n for s in names))
    desc = ", ".join(filter(None, [("*." + "/".join(sorted(exts)) if exts and len(exts) <= 4 else ("%d file types" % len(exts) if exts else "")),
                                   ("matching " + " ".join(globs)) if globs else "",
                                   ("with '" + "' and '".join(names) + "' in the name") if names else ""]))
    return pred, desc


def jv_walk(scope, recurse, cap=200000):
    res, capped = [], False
    if recurse:
        for cur, ds, fs in os.walk(scope, onerror=lambda e: None):
            ds[:] = [d for d in ds if not skip_dir(os.path.join(cur, d))]
            for f in fs:
                p = os.path.join(cur, f)
                try:
                    stt = os.lstat(p)
                except OSError:
                    continue
                res.append((p, stt.st_size, stt.st_mtime))
                if len(res) >= cap:
                    return res, True
    else:
        try:
            names = os.listdir(scope)
        except OSError:
            return res, False
        for f in names:
            p = os.path.join(scope, f)
            try:
                stt = os.lstat(p)
            except OSError:
                continue
            if stat.S_ISREG(stt.st_mode) and not nascosto(p, f):
                res.append((p, stt.st_size, stt.st_mtime))
    return res, capped


def jv_rows(rows, base, limit=25):
    for p, sz, mt in rows[:limit]:
        out(f"  {human(sz).rjust(11)}  {datetime.fromtimestamp(mt).strftime('%d/%m/%Y %H:%M')}  {jv_rel(p, base)}")
    if len(rows) > limit:
        out(f"  ... and {len(rows) - limit:,} more", GRAY)
    out()


def jv_size_of(txt):
    m = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*(bytes?|kb|mb|gb|tb|b)", txt.strip().lower())
    n = float(m.group(1).replace(",", "."))
    mult = {"b": 1, "byte": 1, "bytes": 1, "kb": 1 << 10, "mb": 1 << 20, "gb": 1 << 30, "tb": 1 << 40}[m.group(2)]
    return int(n * mult)


def jv_folder_q(orig, t, scope, explicit_dir):
    h = lambda *pats: any(re.search(p, t) for p in pats)
    base = os.path.abspath(scope)
    where = "this folder" if not explicit_dir else safe(os.path.basename(base) or base)
    explicit_flat = h(r"\b(?:only|just|top.?level|directly|non.?recurs\w*|solo|soltanto)\b")
    wants_deep = h(r"recurs", r"sub-?folders?", r"sottocartell", r"\bbelow\b", r"\beverything\b", r"\btutt[oi]\b", r"\bdeep\b")
    recurse = wants_deep or not (explicit_flat or h(r"\b(?:here|qui)\b"))
    scope_txt = "this folder and everything below it" if recurse else "this folder only"
    if explicit_dir:
        scope_txt = scope_txt.replace("this folder", where)

    # find / count by type, name or pattern
    trigger = h(r"\b(?:find|search|locate|look for|where (?:is|are)|show (?:me )?(?:all|every)|list (?:all|every|the)|display all|"
                r"trova\w*|cerca\w*|dov['’]?\s?[eè]|mostra\w* (?:tutt\w+|ogni)|elenca\w*)\b", r"\bhow many\b", r"\bquant[ie]\b")
    if trigger:
        flt = jv_filter(orig, t)
        if flt:
            pred, desc = flt
            everywhere = h(r"\beverywhere\b", r"\bwhole (?:pc|computer)\b", r"\bentire (?:pc|computer)\b", r"\ball (?:drives|disks)\b",
                           r"\bany drive\b", r"\btutto il (?:pc|computer)\b", r"\bovunque\b")
            roots = pc_roots() if everywhere else [base]
            if everywhere:
                jarvis_say("Searching the whole computer, sir. Read-only; Ctrl+C stops me.")
            found, scanned, stopped = [], 0, False
            try:
                for root in roots:
                    for cur, ds, fs in os.walk(root, onerror=lambda e: None):
                        ds[:] = sorted(d for d in ds if not skip_dir(os.path.join(cur, d)))
                        for f in sorted(fs):
                            scanned += 1
                            p = os.path.join(cur, f)
                            if pred(p):
                                found.append(p)
                        if not recurse and not everywhere:
                            break
                        if scanned > 1500000:
                            stopped = True
                            break
            except KeyboardInterrupt:
                stopped = True
            where_txt = "the whole computer" if everywhere else scope_txt
            if not found:
                jarvis_say(f"I found no files {desc} in {where_txt}, sir ({scanned:,} files looked at).")
                return True
            jarvis_say(f"{len(found):,} file(s) {desc} in {where_txt}, sir ({scanned:,} files looked at"
                       f"{'; stopped early, the list may be incomplete' if stopped else ''}).")
            rows = []
            for p in found[:40]:
                try:
                    stt = os.stat(p)
                    rows.append((p, stt.st_size, stt.st_mtime))
                except OSError:
                    pass
            for i, (p, sz, mt) in enumerate(rows, 1):
                out(f"  [{i:>2}] {human(sz).rjust(11)}  {jv_rel(p, None if everywhere else base)}")
            if len(found) > 40:
                out(f"  ... and {len(found) - 40:,} more", GRAY)
            CONTESTO["jlist"] = found[:200]
            out()
            jarvis_say("Say 'open 1' (or the number you like) to look inside one of them.")
            return True

    # duplicates
    if h(r"\bduplicat\w*\b", r"\bduplicati\b", r"\bidentical files\b", r"\bsame files?\b", r"\bcopies\b", r"\bcopie\b"):
        files, capped = jv_walk(base, recurse)
        by_size = {}
        for p, sz, _ in files:
            if sz > 0:
                by_size.setdefault(sz, []).append(p)
        groups, hashed, skipped = [], 0, 0
        try:
            for sz, ps in by_size.items():
                if len(ps) < 2:
                    continue
                if sz > 200 * 1024 * 1024 or hashed >= 3000:
                    skipped += len(ps)
                    continue
                by_hash = {}
                for p in ps:
                    try:
                        by_hash.setdefault(digests(p)[0], []).append(p)
                        hashed += 1
                    except OSError:
                        pass
                groups += [(sz, g) for g in by_hash.values() if len(g) > 1]
        except KeyboardInterrupt:
            jarvis_say("Stopped, sir. The list is partial.")
        if not groups:
            jarvis_say(f"No duplicate files in {scope_txt}, sir ({len(files):,} files compared).")
            return True
        waste = sum((len(g) - 1) * sz for sz, g in groups)
        jarvis_say(f"{len(groups)} group(s) of identical files in {scope_txt}, sir. Deleting copies would free {human(waste)} "
                   "(I never delete anything myself).")
        for sz, g in sorted(groups, key=lambda x: -x[0] * (len(x[1]) - 1))[:10]:
            out(f"  {human(sz)} x {len(g)}", YELLOW)
            for p in g[:6]:
                out(f"      {jv_rel(p, base)}")
        if skipped:
            out(f"  ({skipped} file(s) over 200 MB or beyond the hashing cap were not compared)", GRAY)
        out()
        return True

    # bigger / smaller than
    m = re.search(r"\b(bigger|larger|greater|over|above|more than|heavier than|piu di|più di|oltre|sopra|maggiore di|"
                  r"smaller|less than|under|below|lighter than|meno di|sotto|minore di)\s+(?:than\s+)?(\d+(?:[.,]\d+)?\s*(?:bytes?|kb|mb|gb|tb|b))\b", t)
    if m:
        limit = jv_size_of(m.group(2))
        bigger = m.group(1) in ("bigger", "larger", "greater", "over", "above", "more than", "heavier than", "piu di", "più di",
                                "oltre", "sopra", "maggiore di")
        files, capped = jv_walk(base, recurse)
        rows = sorted([r for r in files if (r[1] > limit if bigger else r[1] < limit)], key=lambda r: -r[1])
        jarvis_say(f"{len(rows):,} file(s) {'over' if bigger else 'under'} {human(limit)} in {scope_txt}, sir.")
        jv_rows(rows, base)
        CONTESTO["jlist"] = [r[0] for r in rows[:200]]
        return True

    # recently modified
    mt, vague = None, False
    if h(r"\bmodified\b", r"\bchanged\b", r"\bupdated\b", r"\bcreated\b", r"\bmodificat\w*\b", r"\bnew files\b", r"\brecent\w*\b"):
        now = time.time()
        lt = time.localtime()
        midnight = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
        mm = re.search(r"\b(?:last|past|ultim[ie])\s+(\d+)\s+(hours?|ore|days?|giorni|weeks?|settimane|months?|mesi|minutes?|minuti)\b", t)
        if mm:
            unit = mm.group(2)
            secs = 3600 if unit.startswith(("hour", "ore")) else 60 if unit.startswith("minut") else \
                604800 if unit.startswith(("week", "settim")) else 2592000 if unit.startswith(("month", "mes")) else 86400
            mt, label = now - int(mm.group(1)) * secs, f"in the last {mm.group(1)} {unit}"
        elif h(r"\btoday\b", r"\boggi\b"):
            mt, label = midnight, "today"
        elif h(r"\byesterday\b", r"\bieri\b"):
            mt, label = midnight - 86400, "since yesterday"
        elif h(r"\bthis week\b", r"\bquesta settimana\b"):
            mt, label = now - 7 * 86400, "in the last 7 days"
        elif h(r"\brecent\w*\b", r"\bnew files\b"):
            mt, label, vague = now - 7 * 86400, "in the last 7 days", True
    if mt is not None and (not vague or h(r"\bfiles?\b", r"\bwhat\b", r"\bwhich\b", r"\bshow\b", r"\blist\b", r"\bquali\b", r"\bcosa\b")):
        files, capped = jv_walk(base, recurse)
        rows = sorted([r for r in files if r[2] >= mt], key=lambda r: -r[2])
        jarvis_say(f"{len(rows):,} file(s) touched {label} in {scope_txt}, sir.")
        jv_rows(rows, base)
        CONTESTO["jlist"] = [r[0] for r in rows[:200]]
        return True

    # empty files / folders
    if h(r"\bempty\b", r"\bzero.?byte\b", r"\b0.?byte\b", r"\bvuot[ioe]\b"):
        if h(r"\bfolders?\b", r"\bdirector\w+\b", r"\bcartell\w+\b"):
            res = []
            for cur, ds, fs in os.walk(base, onerror=lambda e: None):
                ds[:] = [d for d in ds if not skip_dir(os.path.join(cur, d))]
                for d in ds:
                    try:
                        if not os.listdir(os.path.join(cur, d)):
                            res.append(os.path.join(cur, d))
                    except OSError:
                        pass
                if not recurse:
                    break
            jarvis_say(f"{len(res):,} empty folder(s) in {scope_txt}, sir.")
            for p in res[:25]:
                out(f"  {jv_rel(p, base)}")
            out()
        else:
            files, capped = jv_walk(base, recurse)
            rows = [r for r in files if r[1] == 0]
            jarvis_say(f"{len(rows):,} empty (0-byte) file(s) in {scope_txt}, sir.")
            jv_rows(rows, base)
            CONTESTO["jlist"] = [r[0] for r in rows[:200]]
        return True

    # breakdown by extension
    if h(r"\bby (?:extension|type)\b", r"\bfile types?\b", r"\bwhat kinds? of files\b", r"\bwhich extensions\b", r"\btipi di file\b",
         r"\bper estensione\b", r"\bbreakdown\b", r"\bextensions?\b"):
        files, capped = jv_walk(base, recurse)
        agg = {}
        for p, sz, _ in files:
            e = os.path.splitext(p)[1].lower() or "(none)"
            c, s = agg.get(e, (0, 0))
            agg[e] = (c + 1, s + sz)
        jarvis_say(f"{len(files):,} file(s) in {scope_txt}, sir, by type:")
        for e, (c, s) in sorted(agg.items(), key=lambda kv: -kv[1][0])[:15]:
            out(f"  {e.ljust(10)} {str(c).rjust(7)} file(s)  {human(s).rjust(12)}")
        if len(agg) > 15:
            out(f"  ... and {len(agg) - 15} more type(s)", GRAY)
        out()
        return True

    # rankings
    rk = re.search(r"\b(biggest|largest|heaviest|smallest|lightest|newest|latest|most recent|oldest|più grand\w*|piu grand\w*|"
                   r"più pesant\w*|più piccol\w*|più recent\w*|piu recent\w*|più vecchi\w*|piu vecchi\w*)\b", t) or \
        re.search(r"\b(last modified|recently modified|ultim\w+ modific\w+)\b", t)
    if rk and h(r"\bfiles?\b", r"\bfolders?\b", r"\bcartell\w+\b", r"\bdirector\w+\b", r"\bitems?\b"):
        w = rk.group(1)
        mn = re.search(r"\b(?:top\s+)?(\d{1,2})\b", t)
        n = int(mn.group(1)) if mn else 5
        if h(r"\bfolders?\b", r"\bcartell\w+\b", r"\bdirector\w+\b") and not h(r"\bfiles?\b"):
            try:
                subs = [os.path.join(base, d) for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))
                        and not skip_dir(os.path.join(base, d))]
            except OSError:
                subs = []
            sized = []
            try:
                for d in subs:
                    sized.append((d,) + count_folder(d)[:3])
            except KeyboardInterrupt:
                jarvis_say("Stopped, sir. The list is partial.")
            small = w in ("smallest", "lightest", "più piccol", "più piccolo")
            sized.sort(key=lambda r: r[3], reverse=small)
            if not sized:
                jarvis_say("There are no sub-folders here, sir.")
                return True
            jarvis_say(f"{'Smallest' if small else 'Biggest'} sub-folders of {where}, sir:")
            for d, nf, nd, sz in (sized if small else sized[:n])[:n]:
                out(f"  {human(sz).rjust(11)}  {nf:,} file(s)  {jv_rel(d, base)}")
            out()
            CONTESTO["jlist"] = [r[0] for r in sized[:n]]
            return True
        files, capped = jv_walk(base, recurse)
        if not files:
            jarvis_say(f"There are no files in {scope_txt}, sir.")
            return True
        if re.match(r"(biggest|largest|heaviest|più grand|piu grand|più pesant)", w):
            rows, what = sorted(files, key=lambda r: -r[1]), "Biggest"
        elif re.match(r"(smallest|lightest|più piccol)", w):
            rows, what = sorted(files, key=lambda r: r[1]), "Smallest"
        elif re.match(r"(oldest|più vecchi|piu vecchi)", w):
            rows, what = sorted(files, key=lambda r: r[2]), "Oldest"
        else:
            rows, what = sorted(files, key=lambda r: -r[2]), "Newest"
        top = rows[0]
        jarvis_say(f"{what}: {jv_rel(top[0], base)}, {human(top[1])}, {datetime.fromtimestamp(top[2]).strftime('%d/%m/%Y %H:%M')}"
                   f" (out of {len(files):,} file(s) in {scope_txt}).")
        if n > 1:
            jv_rows(rows[:n], base, n)
        CONTESTO["jlist"] = [r[0] for r in rows[:max(n, 5)]]
        return True

    # counts
    if h(r"\bhow many\b.*\b(?:files?|folders?|director\w+|dirs?|items?|elements?|subfolders?)\b", r"\bnumber of (?:files?|folders?|items?)\b",
         r"\bquant[ie]\s+(?:file|cartell\w+|element\w+|oggett\w+)\b"):
        if CONTESTO.get("file") and not explicit_dir and not h(r"\b(?:here|qui|folder|director\w+|cartell\w+|dir)\b"):
            return False                      # keep the old behaviour: a selected file gets its pluton report
        try:
            names = os.listdir(base)
        except OSError as e:
            jarvis_say(f"I can't read {where}, sir ({e.strerror}).")
            return True
        nf = sum(1 for n in names if os.path.isfile(os.path.join(base, n)))
        nd = sum(1 for n in names if os.path.isdir(os.path.join(base, n)))
        files, dirs, size, capped = count_folder(base)
        jarvis_say(f"{where.capitalize()} holds {nf:,} file(s) and {nd:,} folder(s) directly. Counting everything below: "
                   f"{files:,}{'+' if capped else ''} file(s) in {dirs:,} folder(s), {human(size)} in total.")
        return True

    # total size of a folder
    if h(r"\b(?:how big|how large|how much (?:space|disk)|total size|size of|weigh|weighs|quanto pesa|quanto spazio|dimensione|peso)\b") \
            and (explicit_dir or h(r"\b(?:folder|director\w+|cartella|here|qui)\b")):
        files, dirs, size, capped = count_folder(base)
        jarvis_say(f"{where.capitalize()} weighs {human(size)}{'+' if capped else ''}: {files:,} file(s) in {dirs:,} folder(s), sir.")
        return True

    if h(r"\bhidden\b", r"\bnascost\w+\b") and h(r"\bfiles?\b", r"\bfolders?\b", r"\bwhat\b", r"\bshow\b"):
        try:
            hid = [n for n in os.listdir(base) if nascosto(os.path.join(base, n), n)]
        except OSError:
            hid = []
        jarvis_say(f"{len(hid)} hidden item(s) in {where}, sir." + (":" if hid else ""))
        for n in sorted(hid, key=str.lower)[:30]:
            out(f"  {safe(n)}")
        out()
        return True
    return False


def jv_needs_file(t):
    """Questions that only make sense about one file, asked when no file is known."""
    return bool(re.search(r"\bhow many (?:lines?|words?|characters?|chars?|righe|parole|caratteri)\b|\b(?:first|last|top|head|tail|primi|ultim[ei])"
                          r"\s+\d*\s*(?:lines?|righe)\b|\bencoding\b|\bdimensions?\b|\bhow many pages\b|\bhex(?:dump)?\b|\bcolumns? of\b"
                          r"|\bwhich (?:keys|tables)\b|\bwhat game is\b", t))


def _jv_deep(orig, t, sel):
    if jv_selection(orig, t, sel) or jv_open_request(orig, t, sel) or jv_navigate(orig, t):
        return True
    if jv_examples(t) or jv_global(t):
        return True
    path, explicit = jv_target(orig, t, sel)
    if not explicit:
        missing = [k for k in jv_filename_tokens(orig) if not os.path.exists(os.path.expanduser(k))
                   and not (k.lower() == GM_FILE and re.match(r"(?:find|search|locate|where|trova|cerca|dov)", t))]
        if missing:
            jarvis_say(f"I can't find '{safe(missing[0])}', sir: not in this folder nor in the three levels below it.")
            close = difflib.get_close_matches(missing[0].lower(), [n.lower() for n in os.listdir(".")], n=3, cutoff=0.5)
            if close:
                jarvis_say("Did you mean: " + ", ".join(safe(n) for n in close) + "?")
            return True
    if path is None:
        if jv_needs_file(t):
            jarvis_say("Which file, sir? Say 'open <file>' first, or name it in the question.")
            show_file_choices()
            return True
        return jv_folder_q(orig, t, ".", False)
    if os.path.isfile(path):
        if jv_file_q(orig, t, path, explicit):
            return True
        if jv_folder_q(orig, t, ".", False):
            return True
        if explicit:                                        # a named file with a generic request
            if re.search(r"\b(?:describe|summar\w*|overview|riassum\w*|panoramica|everything about|tutto su)\b", t):
                extract_port([path])
                interact_port([path])
                return True
            if re.search(r"\b(?:battery|batteria|memory|memoria|ram|resources|consum\w*|usage)\b", t):
                pluton_key([path] + (["-Watch", "60"] if re.search(r"\b(?:watch|monitor|track|measure|misura)\b", t) else []))
                return True
            if re.search(r"\b(?:inside|content|contents|preview|look in|what'?s in|dentro|contenuto|show)\b", t):
                interact_port([path])
                return True
            if re.search(r"\b(?:info|inspect|detail|details|metadata|tell me about|about|analy\w*|extract|informazion\w*|dettagli)\b", t):
                extract_port([path])
                return True
        return False
    return jv_folder_q(orig, t, path, True)                 # an explicit folder


def jv_deep(orig, t, sel):
    """Entry point of the deep layer; never lets an unexpected error kill the shell."""
    try:
        return _jv_deep(orig, t, sel)
    except KeyboardInterrupt:
        out()
        jarvis_say("Stopped, sir.")
        return True
    except Exception as e:
        jarvis_say(f"I ran into trouble with that, sir: {safe(e)}")
        return True


# the word 'jarvis' on its own (not inside jarvis.py, jarvis_update, a path...)
JV_NAMED_RE = r"(?<![\w./\\-])jarvis(?![\w/\\-]|\.\w)"
JV_NOT_NAMED_CMDS = ("jarvis", "implement", "implement-jarvis", "maintenance", "help", "get-help", "man", "exit", "quit")


