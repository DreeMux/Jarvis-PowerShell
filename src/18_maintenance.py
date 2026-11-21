# ---------------- maintenance (read-only health check) ----------------
def jv_upd_secline():
    """One compact line about the security state of this file, or None when it cannot be read."""
    import ast
    me = os.path.abspath(__file__)
    try:
        with open(me, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        viol = len(jv_upd_scan(tree))
        prot = len(jv_upd_protected(tree))
        try:
            nb = sum(1 for n in os.listdir(os.path.join(jv_upd_dir(), "backups")) if n.lower().endswith(".py"))
        except OSError:
            nb = 0
        return (f"[{'+' if not viol else '!'}] SECURITY  scan {viol} violation(s)  |  {prot} protected  |  "
                f"{len(JV_UPD_PHASES)} patch gates armed  |  {nb} backup(s)", not viol)
    except (OSError, SyntaxError, UnicodeDecodeError):
        return None


def jv_upd_health(args):
    """Read-only security status of Jarvis (integrity, security scan, backups, log)."""
    import ast
    me = os.path.abspath(__file__)
    out()
    jv_upd_box("SECURITY STATUS // INTEGRITY REPORT  (read-only)")

    def row(ok, key, text, color=None):
        out(f"  {'[+]' if ok else '[!]'} {key.ljust(13, '.')} {text}", color or (JV_SEC_G if ok else RED))
    try:
        with open(me, encoding="utf-8") as f:
            src = f.read()
        tree = ast.parse(src)
        row(True, "PROGRAM", f"{safe(me)}")
        row(True, "FINGERPRINT", f"sha256 {jv_upd_sha_of(me)[:32]}  ({human(len(src.encode('utf-8')))})")
    except (OSError, SyntaxError, UnicodeDecodeError) as e:
        row(False, "PROGRAM", f"cannot be checked ({e})")
        out()
        return
    err, data = jv_upd_data_block(src)
    if err:
        row(False, "DATA BLOCK", err)
    else:
        alive = sum(1 for d in data["game_dirs"] if os.path.isdir(d))
        row(True, "DATA BLOCK", f"version {data['version']}, last update '{data['updated'] or 'never'}', "
                                f"{alive}/{len(data['game_dirs'])} learned game folder(s) still there")
    found = jv_upd_scan(tree)
    row(not found, "CODE SCAN", "0 violations" if not found else f"{len(found)} violation(s), first: {found[0]}")
    prot = jv_upd_protected(tree)
    row(True, "PROTECTED", f"{len(prot)} updater/launcher item(s) locked: an update that changes them is refused")
    rules = (len(JV_UPD_NET) + len(JV_UPD_DYNAMIC) + len(JV_UPD_BAD_BUILTINS) + len(JV_UPD_BAD_CALLS)
             + len(JV_UPD_BAD_METHODS) + len(JV_UPD_BAD_SYS) + len(JV_UPD_BAD_DUNDERS))
    row(True, "GUARD", f"v{JV_UPD_GUARD}: {rules} scan rules, alias tracking, hidden-character and link/pipe refusal, pinned install")
    row(True, "ISOLATION", "start test: python -I, cleaned environment, 10 s limit; downloads: https only, TLS 1.2+")
    row(True, "PATCH GATES", " > ".join(JV_UPD_PHASES))
    base = jv_upd_dir()

    def count(sub, ext=".py"):
        try:
            return sorted(n for n in os.listdir(os.path.join(base, sub)) if n.lower().endswith(ext))
        except OSError:
            return []
    backups = count("backups")
    row(bool(backups), "BACKUPS", f"{len(backups)}" + (f", newest {safe(backups[-1])}" if backups else " (made before every install)"),
        JV_SEC_G if backups else JV_SEC_A)
    row(True, "QUARANTINE", f"{len(count('rejected'))} rejected update(s)", JV_SEC_D)
    row(True, "INCOMING", f"{len(count('incoming'))} update(s) waiting", JV_SEC_D)
    try:
        with open(os.path.join(base, "update.log"), encoding="utf-8", errors="replace") as f:
            last = f.read().splitlines()[-5:]
    except OSError:
        last = []
    row(True, "LOG", "(no events yet)" if not last else "last events:", JV_SEC_D)
    for ln in last:
        out("      " + safe(ln)[:150], JV_SEC_D)
    out()


@cmdlet("Get-SecurityStatus", "security", "secstat", group="Assistant", usage="""Get-SecurityStatus     security panel: file fingerprint, code scan, protected items, patch gates, backups, quarantine, log
(read-only; alias: security)""")
def jv_upd_security_cmd(args):
    """Security panel of Jarvis (fingerprint, code scan, patch gates, backups, log)."""
    jv_upd_health([])


def jv_upd_png(truncate=False):
    """A tiny valid PNG (2 x 3 pixels), optionally cut short to make a damaged one."""
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\x10\x20\x30" * 2 for _ in range(3))
    data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 3, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    return data[:-9] if truncate else data


def jv_upd_samples(tmp):
    """Throw-away sample files used by the self-test (they live in a temporary folder that is deleted after)."""
    def w(name, text):
        with open(os.path.join(tmp, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    text = "alpha beta\ngamma delta\nalpha again\nlast line\n"
    w("a.txt", text)
    w("dup.txt", text)
    w("e.txt", "")
    w("data.csv", "name,score\nx,1\ny,3\n")
    w("data.json", json.dumps({"alpha": 1, "beta": [1, 2, 3]}))
    with zipfile.ZipFile(os.path.join(tmp, "z.zip"), "w") as z:
        z.writestr("inside.txt", "hello")
    with open(os.path.join(tmp, "p.png"), "wb") as f:
        f.write(jv_upd_png())
    with open(os.path.join(tmp, "bad.png"), "wb") as f:
        f.write(jv_upd_png(True))
    con = sqlite3.connect(os.path.join(tmp, "db.sqlite"))
    con.execute("CREATE TABLE items (id INTEGER, name TEXT)")
    con.execute("INSERT INTO items VALUES (1, 'one')")
    con.commit()
    con.close()
    os.makedirs(os.path.join(tmp, "sub"))
    body = b"GEN8" + struct.pack("<I", 60) + bytes(60) + b"SPRT" + struct.pack("<I", 4) + struct.pack("<I", 0)
    with open(os.path.join(tmp, "sub", "data.win"), "wb") as f:
        f.write(b"FORM" + struct.pack("<I", len(body)) + body)


def jv_is_maintenance(t):
    """True for 'go in maintenance', 'maintenance mode', 'manutenzione', 'test all the commands'..."""
    toks = [x.strip(",.!?;:") for x in t.split()]
    names = ["maintenance", "manutenzione"]
    has_m = any("." not in x and "/" not in x and "\\" not in x and difflib.get_close_matches(x, names, n=1, cutoff=0.78)
                for x in toks)
    starters = ("go", "enter", "switch", "put", "start", "run", "begin", "vai", "entra", "passa", "metti", "mettiti",
                "avvia", "fai", "please", "now", "ora", "can", "could", "puoi")
    if has_m and (len(toks) <= 3 or (toks and toks[0] in starters)):
        return True
    return bool(re.search(r"\b(?:test|check|verify|testa|controlla|verifica|prova)\b.*\b(?:commands?|comandi)\b", t)
                and not re.search(r"\.\w{1,5}\b", t))


def jv_upd_selftest():
    """Run every command of Jarvis once on throw-away sample files and report what works.
    Nothing outside the temporary folder is touched; no game or file is opened. Returns (passed, total)."""
    import io
    import tempfile
    snap, old_cwd = dict(CONTESTO), os.getcwd()
    CONTESTO["jv_nolog"] = True          # the test sentences must not end up in the list of misunderstood phrases
    tmp = tempfile.mkdtemp(prefix="jarvis_selftest_")
    results = []
    tag = {"n": 0}

    def run(label, fn, need=(), expect="ok", bad=(), red=False, empty=False):
        buf, old = io.StringIO(), sys.stdout
        sys.stdout = buf
        problem, exited = None, False
        try:
            fn()
        except SystemExit:
            exited = True
        except KeyboardInterrupt:
            sys.stdout = old
            raise
        except Exception as e:
            problem = f"{type(e).__name__}: {e}"
        finally:
            sys.stdout = old
        text = buf.getvalue()
        plain = re.sub(r"\x1b\[[0-9;]*m", "", text)
        if problem is None:
            if expect == "exit":
                if not exited:
                    problem = "it did not close the shell"
            elif exited:
                problem = "it closed the shell by itself"
        if problem is None and expect != "exit":
            if "Traceback" in plain or "I ran into trouble" in plain:
                problem = "internal error: " + next((l.strip() for l in plain.splitlines()
                                                     if "Traceback" in l or "I ran into trouble" in l), "")[:90]
            elif expect == "err" and RED not in text:
                problem = "no error message was shown"
            elif expect == "ok" and RED in text and not red:
                problem = "it printed an error: " + next((re.sub(r"\x1b\[[0-9;]*m", "", l).strip()
                                                          for l in text.splitlines() if RED in l), "")[:90]
            elif not plain.strip() and not empty:
                problem = "no output"
            else:
                for s in need:
                    if s not in plain:
                        problem = f"output lacks '{s}'"
                        break
                for s in bad:
                    if s in plain and problem is None:
                        problem = f"output contains '{s}'"
        if problem and problem.startswith("output "):
            seen = " / ".join(l.strip() for l in plain.splitlines() if l.strip())      # what it really answered
            problem += f"  [it said: {safe(seen)[:200] or '(nothing)'}]  [folder: {safe(os.getcwd())}]"
        tag["n"] += 1
        results.append((label, problem))
        out(f"  {'[ OK ]' if problem is None else '[FAIL]'} {label}" + (f"  -> {problem}" if problem else ""),
            GREEN if problem is None else RED)

    def cmd(name, *a):
        def f():
            CONTESTO["riga"] = name + " " + " ".join(a)
            CMDLETS[name.lower()](list(a))
        return f

    def say(text):
        def f():
            if not jarvis_interpret(text):
                raise RuntimeError("Jarvis did not understand it")
        return f

    def section(title):
        out()
        out(title, YELLOW)

    try:
        jv_upd_samples(tmp)
        os.chdir(tmp)
        CONTESTO["file"] = None
        CONTESTO["jlast"] = None
        CONTESTO.pop("jlist", None)
        sub = os.path.join(tmp, "sub")

        section("Registry")
        def registry():
            for n, fn in NOMI.items():
                if CMDLETS.get(n.lower()) is not fn:
                    raise RuntimeError(f"{n} is not registered")
                for a in ALIASES[n]:
                    if CMDLETS.get(a.lower()) is not fn:
                        raise RuntimeError(f"alias {a} of {n} is broken")
            print(f"{len(NOMI)} commands, {len(CMDLETS)} names")
        run("every command and alias is registered", registry)

        section("Integrity of the program and of what I know")
        def dupes():
            import ast
            with open(os.path.abspath(__file__), encoding="utf-8") as f:
                tree = ast.parse(f.read())
            seen, dup = {}, []
            for top in tree.body:
                if isinstance(top, (ast.FunctionDef, ast.ClassDef)):
                    if top.name in seen:
                        dup.append(top.name)
                    seen[top.name] = True
            if dup:
                raise RuntimeError("defined twice (the second hides the first): " + ", ".join(sorted(set(dup))))
            print(f"{len(seen)} top-level names, no duplicates")
        run("no function is defined twice", dupes)
        def faqself():
            bad = []
            for k, qu, a in JV_FAQ:
                hit = jv_faq_find(qu)
                if not hit or hit[1][1] != qu:
                    bad.append(qu)
                if not a.strip() or len(a) < 40:
                    bad.append("short answer: " + qu)
            if bad:
                raise RuntimeError(f"{len(bad)} entries not found by their own question: {bad[:2]}")
            print(f"{len(JV_FAQ)} how-to answers, each found by its own question")
        run("every how-to answer is found by its own question", faqself)
        def kbsane():
            keys, dup = {}, []
            for ks, txt in JV_KB:
                if len(txt) < 15:
                    raise RuntimeError(f"too short: {ks}")
                for k in ks:
                    if k in keys and keys[k] != txt:
                        dup.append(k)
                    keys[k] = txt
            for pair in JV_COMPARE:
                if len(pair) != 2:
                    raise RuntimeError(f"bad comparison {set(pair)}")
            if dup:
                raise RuntimeError("same glossary word with two meanings: " + ", ".join(sorted(set(dup))[:8]))
            print(f"{len(JV_KB)} glossary entries, {len(JV_GAMES_KB)} games, {len(JV_COMPARE)} comparisons")
        run("glossary, games and comparisons are consistent", kbsane)
        run("the list of misunderstood phrases can be shown", say("jarvis what didnt you understand"), need=["JARVIS"])
        def misslog():
            jv_didnt_catch("this sentence is a test and must not be remembered")
        run("a misunderstood sentence gets a polite reply and is not logged during tests", misslog, need=["sir"])

        section("Standard commands")
        run("Get-Location", cmd("Get-Location"), need=[tmp])
        run("Get-ChildItem", cmd("Get-ChildItem"), need=["a.txt", "data.csv", "sub"])
        run("Get-ChildItem on a missing path (must show an error)", cmd("Get-ChildItem", "nope_missing"), expect="err")
        run("Set-Location into a folder", cmd("Set-Location", "sub"), empty=True)
        run("  ...and back", cmd("Set-Location", ".."), empty=True)
        run("Set-Location on a file selects it", cmd("Set-Location", "a.txt"), need=["Selected file"])
        run("Set-Location on a missing folder (must show an error)", cmd("Set-Location", "nope_missing"), expect="err")
        CONTESTO["file"] = None
        run("Write-Output", cmd("Write-Output", "hello", "world"), need=["hello world"])
        run("Write-Host", cmd("Write-Host", "hello"), need=["hello"])
        run("Get-Content", cmd("Get-Content", "a.txt"), need=["alpha beta", "last line"])
        run("Get-Content on a missing file (must show an error)", cmd("Get-Content", "nope_missing.txt"), expect="err")
        run("Clear-Host", cmd("Clear-Host"), empty=True)
        run("Get-Command lists everything", cmd("Get-Command"), need=list(NOMI))
        run("Get-Help (full list)", cmd("Get-Help"), need=["Available commands"])
        def helps():
            for n in list(NOMI):
                CMDLETS["get-help"]([n])
        run("Get-Help <command> for every command", helps, need=["SYNTAX"])
        run("Exit closes the shell", cmd("Exit"), expect="exit", empty=True)

        section("Port tools (on sample files)")
        samples = ["a.txt", "data.csv", "data.json", "z.zip", "p.png", "db.sqlite", "e.txt", "bad.png",
                   os.path.join("sub", "data.win")]
        for s in samples:
            run(f"extract.port {s}", cmd("extract.port", s), need=["Name", "Size"], bad=["Read error"])
        for s in samples:
            run(f"interact.port {s}", cmd("interact.port", s), need=["What you can DO"], bad=["Could not read"],
                red=(s == "bad.png"))
        CONTESTO["jv_export_dir"] = os.path.join(tmp, "exports")
        run("extract.key saves a report (in the temporary folder)", cmd("extract.key", "a.txt"), need=["Report saved"])
        def keyfile():
            d = os.path.join(tmp, "exports")
            got = [n for n in os.listdir(d)] if os.path.isdir(d) else []
            if len(got) != 1:
                raise RuntimeError(f"expected one report, found {got}")
            with open(os.path.join(d, got[0]), encoding="utf-8") as f:
                body = f.read()
            for need in ("JARVIS FILE REPORT", "SHA256", "VERIFY IT YOURSELF", "alpha beta"):
                if need not in body:
                    raise RuntimeError(f"the report lacks '{need}'")
            print("ok")
        run("the report file has everything in it", keyfile)
        run("extract.key on a missing file (must show an error)", cmd("extract.key", "nope_missing"), expect="err")
        CONTESTO.pop("jv_export_dir", None)
        run("extract.port on a missing file (must show an error)", cmd("extract.port", "nope_missing"), expect="err")
        run("denux.hunter finds the damaged PNG", cmd("denux.hunter", ".", "-Recurse"), need=["bad.png", "CORRUPT"], red=True)
        run("denux.hunter on one good file", cmd("denux.hunter", "a.txt"), need=["0 corrupt"])
        run("denux.hunter on one damaged file", cmd("denux.hunter", "bad.png"), need=["CORRUPT"], red=True)
        run("undersopic.key finds the sample data.win", cmd("undersopic.key", tmp), need=["Found 1 data.win"])
        run("pluton.key", cmd("pluton.key", "a.txt"), need=["Pluton report", "FILES", "MEMORY", "BATTERY"])
        run("pluton.key -Watch 1", cmd("pluton.key", "a.txt", "-Watch", "1"), need=["Pluton report"])

        section("Jarvis, plain language (read-only questions)")
        phrases = [
            ("status", []), ("what time is it", [":"]), ("free disk space", ["free"]), ("who are you", ["JARVIS"]),
            ("thank you", []), ("examples", ["ANY FILE"]), ("what os is this", []), ("uptime", []),
            ("how many files here", ["file(s)"]), ("biggest files", ["Biggest"]), ("find all png files", ["2 file(s)"]),
            ("duplicates", ["identical"]), ("modified today", ["file(s)"]), ("by extension", [".txt"]),
            ("empty files", ["empty"]), ("files bigger than 1 byte", ["file(s)"]),
            ("select a.txt", ["Selected"]), ("how many lines", ["4 line"]), ("first 2 lines", ["alpha beta"]),
            ("last 1 lines", ["last line"]), ("search for alpha", ["2 time"]), ("sha256", ["SHA256"]),
            ("is it corrupt", ["No damage"]), ("how big is it", ["weighs"]), ("when was it modified", ["modified"]),
            ("what type is it", ["Text file"]), ("hex dump", ["61 6C"]),
            ("select data.csv", ["Selected"]), ("which columns", ["name, score"]), ("average of score", ["2"]),
            ("select data.json", ["Selected"]), ("which keys", ["alpha"]),
            ("select z.zip", ["Selected"]), ("what is inside", ["inside.txt"]),
            ("select db.sqlite", ["Selected"]), ("which tables", ["items"]), ("how many rows in items", ["1 row"]),
            ("select p.png", ["Selected"]), ("dimensions", ["2 x 3"]),
            ("select bad.png", ["Selected"]), ("is it corrupt", ["damaged"]),
            ("select e.txt", ["Selected"]), ("is it corrupt", ["empty"]),
            ("select sub/data.win", ["Selected"]), ("what game is this", ["2 chunks"]), ("how many sprites", ["0 sprites"]),
            ("list the chunks", ["GEN8", "SPRT"]), ("go up", ["Now in"]), ("read a.txt", ["alpha beta"]),
            ("what is selected", []), ("deselect", []),
            ("jarvis thats sick", ["sir"]), ("jarvis help me", ["sir"]),
            ("jarvis why does my game crash", ["overheating"]), ("jarvis how do i fix a dll not found error", ["Redistributable"]),
            ("jarvis difference between ssd and hdd", ["moving parts"]), ("jarvis zip vs rar", ["WinRAR"]),
            ("jarvis how can i free disk space", ["Disk Cleanup"]), ("jarvis is it safe to delete temp files", ["Windows recreates"]), ("jarvis ur the best", ["sir"]), ("jarvis whats your name", ["JARVIS"]), ("jarvis lol", ["sir"]),
            ("what is a vpn", ["tunnel"]), ("i want to know what a dll is", ["library"]), ("cosa significa ssd", ["solid-state"]),
            ("tell me about cry of fear", ["horror"]), ("can you calculate 12*12", ["144"]), ("jarvis ssd", ["solid-state"]),
            ("tell me about a.txt", ["SHA256"]), ("what's inside a.txt", ["First 15 lines"]),
            ("jarvis tell me about a.txt", ["SHA256"]), ("jarvis what's inside a.txt", ["First 15 lines"]),
            ("jarvis free disk space", ["free"]), ("jarvis duplicates", ["identical"]), ("jarvis by extension", [".txt"]),
        ]
        for text, need in phrases:
            run(f"jarvis: {text}", say(text), need=need)

        section("Jarvis brain (small talk, knowledge, maths, dates, typos)")
        brain = [
            ("jarvis perfect", ["JARVIS"]), ("yo big jarvis", ["JARVIS"]), ("hey jarvis how are you", ["JARVIS"]),
            ("jarvis tell me a joke", ["JARVIS"]), ("jarvis thats awesome", ["JARVIS"]), ("good night jarvis", ["sir"]),
            ("jarvis what is 15% of 80", ["= 12"]), ("jarvis calculate 2+2*3", ["= 8"]), ("jarvis what is 7 times 8", ["= 56"]),
            ("what is 5 divided by 0", ["Division by zero"]), ("jarvis square root of 144", ["= 12"]),
            ("jarvis convert 5 km to miles", ["3.10"]), ("jarvis 100 f to c", ["37.7"]), ("jarvis 2 gb in mb", ["2,048"]),
            ("jarvis how many days until christmas", ["day(s) until"]), ("jarvis what day is 25/12/2026", ["Friday"]),
            ("jarvis days between 1/1/2026 and 1/3/2026", ["59 day"]),
            ("jarvis what is a dll", ["shared library"]), ("jarvis explain sha256", ["fingerprint"]),
            ("jarvis what is a .win file", ["GameMaker"]), ("jarvis what does dir do", ["Get-ChildItem"]),
            ("jarvis tell me about undertale", ["Toby Fox"]), ("jarvis tell me about cry of fear", ["Psykskallar"]),
            ("jarvis who made you", ["Python"]), ("jarvis are you an ai", ["rule-based"]),
            ("jarvis whats the weather", ["offline"]), ("jarvis blorp zzz qqq", None),
        ]
        for text, need in brain:
            if need is None:
                run("jarvis: an unknown request gets a helpful answer", lambda: jv_didnt_catch("jarvis blorp zzz qqq"),
                    need=["didn't catch"])
            else:
                run(f"jarvis: {text}", say(text), need=need)
        def typo():
            if jv_typofix("show the biggset files") != "show the biggest files":
                raise RuntimeError("typo not repaired")
            if jv_typofix("open undertale") != "open undertale":
                raise RuntimeError("a good sentence was changed")
            print("ok")
        run("typos of my own keywords are repaired", typo)
        run("jarvis: what time is it, then 'again'", lambda: (say("jarvis what time is it")(), say("jarvis again")()),
            need=["Repeating", ":"])

        section("Maintenance wording")
        def wording():
            for yes in ("go in maintenance", "go in maintance", "maintenance mode", "jarvis maintenance".replace("jarvis ", ""),
                        "vai in manutenzione", "test all the commands", "testa tutti i comandi", "enter maintenance mode"):
                if not jv_is_maintenance(yes):
                    raise RuntimeError(f"'{yes}' is not recognised")
            for no in ("open maintenance.txt", "find my games", "how many lines", "what is the status"):
                if jv_is_maintenance(no):
                    raise RuntimeError(f"'{no}' was taken for maintenance")
            print("ok")
        run("the phrases that start maintenance mode", wording)

        section("Online mode and research")
        def online_wording():
            for yes in ("be online", "go online", "online", "vai online", "sii online", "connettiti", "boot up"):
                if jv_online_kind(yes) != "on":
                    raise RuntimeError(f"'{yes}' does not bring me online")
            for yes in ("go offline", "be offline", "offline", "disconnettiti"):
                if jv_online_kind(yes) != "off":
                    raise RuntimeError(f"'{yes}' does not take me offline")
            for no in ("open online.txt", "find my games", "how many lines", "what is online banking"):
                if jv_online_kind(no):
                    raise RuntimeError(f"'{no}' was taken for the online switch")
            print("ok")
        run("the phrases that switch online and offline", online_wording)
        def online_flow():
            CONTESTO["jv_online"] = False
            if not jarvis_interpret("jarvis research ram"):
                raise RuntimeError("Jarvis did not understand it")
            if not jarvis_interpret("jarvis be online"):
                raise RuntimeError("Jarvis did not understand it")
            if not CONTESTO.get("jv_online"):
                raise RuntimeError("I did not come online")
        run("jarvis be online (research refused while offline, then the animation)", online_flow, need=["not online", "ONLINE"])
        run("jarvis cerca ram (research summary)", say("jarvis cerca ram"), need=["Research on", "In short"])
        run("jarvis research sha256 (works with a file selected too)", say("jarvis research sha256"), need=["Research on", "In short"])
        run("jarvis cerca a topic nobody taught me", say("jarvis cerca zzzqqqxx"), need=["found nothing"])
        def search_stays_a_file_question():
            CONTESTO["jv_online"] = True
            n = 0
            for phrase in ('jarvis search for "alpha"', "jarvis cerca alpha in notes.txt"):
                if jv_rs_parse(phrase.replace("jarvis ", "", 1), None) is not None:
                    raise RuntimeError(f"'{phrase}' was taken for a research")
                n += 1
            print("ok")
        run("quoted words and file names are not researched", search_stays_a_file_question)
        run("jarvis go offline", say("jarvis go offline"), need=["offline"])
        def news_wording():
            for yes, topic in (("news", ""), ("jarvis news".replace("jarvis ", ""), ""), ("ultime notizie", ""), ("le ultime news", ""),
                               ("news war", "war"), ("notizie sulla guerra", "guerra"), ("what's the news", ""),
                               ("show me the latest news about protests", "protests"), ("cosa succede nel mondo", "")):
                if jv_news_parse(yes) != topic:
                    raise RuntimeError(f"'{yes}' is not read as news about '{topic}'")
            for no in ("open news.txt", "search for news in it", "how many lines", 'search for "news"', "what is a dll"):
                if jv_news_parse(no) is not None:
                    raise RuntimeError(f"'{no}' was taken for a news request")
            print("ok")
        run("the phrases that ask for the news", news_wording)
        def news_pipeline():
            from datetime import timezone, timedelta
            now = datetime.now(timezone.utc)
            mk = lambda title, src, h, desc="Summary of the story. More detail follows here.": {
                "title": title, "link": "https://example.org/x", "desc": desc, "ts": now - timedelta(hours=h), "src": src, "img": None}
            items = [mk("Missile attack on city leaves dozens wounded", "BBC World", 2),
                     mk("Missile attack on city leaves dozens wounded overnight", "ANSA", 3),
                     mk("Thousands protest in the capital against the new law", "RaiNews", 5),
                     mk("Scientists find new exoplanet candidate", "Geopop", 7),
                     mk("Old story from last week", "ANSA", 300)]
            jv_news_show(items, "", {"BBC World", "ANSA", "RaiNews", "Geopop"}, {"BBC World", "ANSA", "RaiNews", "Geopop", "Il Post"},
                         with_images=False, now=now)
            jv_news_show(items, "war", {"ANSA"}, {"ANSA"}, with_images=False, now=now)
            jv_news_show([], "", set(), {"ANSA"}, with_images=False, now=now)
        run("news sorted into war / protests / everything else", news_pipeline, need=["WAR AND CONFLICTS", "PROTESTS", "SCIENCE AND TECH", "confirmed by 2 desks", "couldn't reach"], bad=["last week"])
        def news_refusals():
            for url, kind in (("http://www.ansa.it/sito/ansait_rss.xml", "feed"), ("https://example.com/feed", "feed"),
                              ("https://127.0.0.1/a.jpg", "image"), ("https://localhost/a.jpg", "image")):
                try:
                    jv_news_get(url, kind)
                except ValueError:
                    continue
                raise RuntimeError(f"{url} was not refused")
            try:
                jv_news_parse_feed(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><rss><channel/></rss>', "T")
            except ValueError:
                print("ok")
                return
            raise RuntimeError("a feed with XML entities was accepted")
        run("only my news sources, https, no numeric hosts, no XML entities", news_refusals)

        section("Game launcher (nothing is started)")
        def match():
            games = [{"name": "Cry of Fear", "alt": ""}, {"name": "Fear to Fathom", "alt": ""},
                     {"name": "DELTARUNE", "alt": "DELTARUNE"}]
            for phrase, want in (("cry of fear", "Cry of Fear"), ("the game cry of fear please", "Cry of Fear"),
                                 ("fear to fhatom", "Fear to Fathom"), ("deltarune", "DELTARUNE")):
                got, _ = jv_launch_match(phrase, games)
                if [g["name"] for g in got] != [want]:
                    raise RuntimeError(f"'{phrase}' gave {[g['name'] for g in got]}, expected {want}")
            if jv_launch_match("zzzzqq", games)[0]:
                raise RuntimeError("an unknown name matched a game")
            print("ok")
        run("matching a spoken name to a game (also with typos)", match)
        def listing():
            games = jv_launch_games(force=True)
            print(f"{len(games)} game(s) found on this PC: " + ", ".join(safe(g["name"]) for g in games[:12]))
        run("finding the games installed on this PC", listing)
        def blocked():
            win = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32", "notepad.exe") \
                if os.name == "nt" else "/etc/hosts"
            if jv_launch_blocked(win) is None:
                raise RuntimeError("a Windows/system file is not blocked")
            if jv_launch_blocked(os.path.join(tmp, "a.txt")) is not None:
                raise RuntimeError("a normal file is blocked")
            jv_launch_file(win)
        run("system files are refused, normal files allowed", blocked, need=["I won't open"])
        run("a program outside its game folder is refused", lambda: jv_launch_run(
            {"name": "test", "root": sub, "wins": [], "generic": True},
            ("launcher", os.path.join(tmp, "a.txt"), None)), need=["I won't start"])

        section("Voice and launcher (nothing is started, nothing is spoken)")
        def voice_quiet():
            if JV_VOICE["on"]:
                raise RuntimeError("the voice is on before anyone asked for it")
            jv_voice_say("this must stay silent")
            if JV_VOICE["q"] is not None and JV_VOICE["q"].unfinished_tasks:
                raise RuntimeError("a sentence was queued while the voice was off")
            got = jv_voice_clean("\x1b[36mOpen C:\\Games\\x\\y.exe now\x1b[0m")
            if got != "Open a file path now":
                raise RuntimeError(f"text for speech was not cleaned: {got!r}")
            print("ok")
        run("the voice starts silent; text is cleaned before it would be read aloud", voice_quiet)
        run("voice (shows its state)", cmd("Voice"), need=["OFF"])
        run("voice off while already silent", cmd("Voice", "off"), need=["already off"])
        run("'jarvis voice off' in plain words", say("jarvis voice off"), need=["already off"])
        def launch_plans():
            py = os.path.join(tmp, "t.py")
            with open(py, "w", encoding="utf-8") as f:
                f.write("print('hi')\n")
            p = jv_launch_plan(py, ["x"])
            if p["why"] or p["argv"][0] != sys.executable or p["argv"][-1] != "x" or not p["wait"]:
                raise RuntimeError(f"a .py script was planned wrongly: {p}")
            if jv_launch_plan(py, [], wait=False)["wait"]:
                raise RuntimeError("-Detach was ignored")
            doc = jv_launch_plan(os.path.join(tmp, "a.txt"), [])
            if doc["argv"] is not None or doc["why"]:
                raise RuntimeError("a text file should simply open with its usual program")
            if not jv_launch_plan(os.path.join(tmp, "a.txt"), ["x"])["why"]:
                raise RuntimeError("arguments for a document were accepted")
            if not jv_launch_plan(os.path.join(tmp, "nothing.py"), [])["why"]:
                raise RuntimeError("a missing file was accepted")
            print("ok")
        run("launch plans: .py gets this Python, documents open normally, bad requests are refused", launch_plans)
        def launch_blocked():
            win = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32", "notepad.exe") \
                if os.name == "nt" else "/etc/hosts"
            jv_launch_script(win, [])
        run("launch refuses system files", launch_blocked, need=["I won't launch"])
        run("launch without a file asks which one", cmd("Launch"), need=["Which file"])

        section("Browser mode (nothing is started: only checked)")
        def urlsafety():
            good = ["https://mail.google.com/", "https://www.canva.com/design?x=1"]
            bad = ["http://a.com", "https://localhost/", "https://127.0.0.1/", "https://10.0.0.5/", "https://a.com:8080/",
                   "https://user:pw@evil.com/", "javascript:alert(1)", "file:///C:/Windows/win.ini", "https://a.com/ x",
                   "https://x.local/", "chrome://settings", "data:text/html,hi", "https://a.com/\"onload=1"]
            for u in good:
                if not jv_launch_url_ok(u):
                    raise RuntimeError(f"a normal address was refused: {u}")
            for u in bad:
                if jv_launch_url_ok(u):
                    raise RuntimeError(f"an unsafe address was accepted: {u}")
            for phrase in ("javascript:alert(1)", "file:///C:/x", "chrome://settings", "data:text/html,hi", "https://u:p@evil.com"):
                if jv_launch_web_target(phrase)[0]:
                    raise RuntimeError(f"'{phrase}' would have been opened")
            print(f"{len(good)} normal and {len(bad)} unsafe addresses checked")
        run("only plain https pages are ever opened", urlsafety)
        def targets():
            want = {"email": "https://mail.google.com/", "my email": "https://mail.google.com/", "canva": "https://www.canva.com/",
                    "youtube lofi music": "https://www.youtube.com/results?search_query=lofi+music",
                    "search best pizza": "https://www.google.com/search?q=best+pizza", "example.com": "https://example.com",
                    "http://example.com": "https://example.com", "maps colosseo": "https://www.google.com/maps/search/colosseo"}
            for phrase, url in want.items():
                got = jv_launch_web_target(phrase)[0]
                if got != url:
                    raise RuntimeError(f"'{phrase}' gave {got}, expected {url}")
            print(f"{len(want)} phrases map to the right page")
        run("'email', 'canva', 'youtube <words>', 'search <words>' find the right page", targets)
        def profiles():
            d = os.path.join(tmp, "chrome")
            os.makedirs(d)
            sp = os.path.join(d, "Local State")
            with open(sp, "w", encoding="utf-8") as f:
                json.dump({"profile": {"info_cache": {"Default": {"name": "Anna", "user_name": "anna@example.com"},
                                                      "Profile 1": {"name": "Work", "user_name": "w@example.org"},
                                                      "../evil": {"name": "x"}}}}, f)
            ps = jv_launch_chrome_profiles(sp)
            if [p["dir"] for p in ps] != ["Default", "Profile 1"]:
                raise RuntimeError(f"profiles read wrongly: {ps}")
            for q, dirn in (("anna", "Default"), ("work", "Profile 1"), ("w@example.org", "Profile 1"), ("2", "Profile 1"), ("annna", "Default")):
                got = jv_launch_profile_match(q, ps)
                if [p["dir"] for p in got] != [dirn]:
                    raise RuntimeError(f"'{q}' matched {[p['dir'] for p in got]}, expected {dirn}")
            if jv_launch_profile_match("zzzz", ps):
                raise RuntimeError("an unknown name matched an account")
            print("2 accounts read, an unsafe folder name ignored, names/emails/numbers/typos matched")
        run("Chrome accounts are read and matched (from a sample file)", profiles)
        def convo():
            CONTESTO["jv_launch_dry"] = True
            try:
                CONTESTO["jv_online"] = False
                CONTESTO["jv_browser"] = None
                CONTESTO["jv_named"] = True
                if not jv_launch_browser("open chrome", "open chrome") or CONTESTO.get("jv_browser"):
                    raise RuntimeError("Chrome mode started while offline")
                CONTESTO["jv_online"] = True
                jv_launch_browser("open chrome", "open chrome")
                if not CONTESTO.get("jv_browser"):
                    raise RuntimeError("Chrome mode did not start")
                CONTESTO["jv_named"] = False
                for text in ("open email", "open canva", "search cats", "open chrome account"):
                    if not jv_launch_browser(text, text):
                        raise RuntimeError(f"'{text}' was not handled in Chrome mode")
                if jv_launch_browser("open a.txt", "open a.txt"):
                    raise RuntimeError("a file name was taken for a web page")
                jv_launch_browser("close chrome mode", "close chrome mode")
                if CONTESTO.get("jv_browser"):
                    raise RuntimeError("Chrome mode did not end")
                if jv_launch_browser("open email", "open email"):
                    raise RuntimeError("'open email' was taken without Chrome mode")
            finally:
                CONTESTO["jv_launch_dry"] = False
                CONTESTO["jv_browser"] = None
                CONTESTO["jv_online"] = False
                CONTESTO["jv_named"] = False
            print("ok")
        run("Chrome mode: needs online, then 'open email' / 'open canva', never takes file names, ends cleanly", convo)
        def chain_test():
            CONTESTO["jv_launch_dry"] = True
            try:
                CONTESTO.update(jv_online=True, jv_named=True, jv_browser=None)
                if jv_chain("open a.txt then read it", "open a.txt then read it"):
                    raise RuntimeError("a file sentence was taken for a browser chain")
                if jv_chain("open chrome", "open chrome"):
                    raise RuntimeError("a single step was taken for a chain")
                for text in ("open chrome then gmail and canva", "apri chrome poi youtube lofi", "open chrome, then search cats",
                             "open chrome then gmail on account zzzqqq"):
                    if not jv_chain(text, text):
                        raise RuntimeError(f"'{text}' was not handled")
                CONTESTO["jv_online"] = False
                if not jv_chain("open chrome then gmail", "open chrome then gmail"):
                    raise RuntimeError("the offline case was not answered")
            finally:
                CONTESTO.update(jv_launch_dry=False, jv_browser=None, jv_online=False, jv_named=False)
        run("several steps in one sentence: 'open chrome then gmail on account ...' (nothing is opened)", chain_test, need=["page(s) in one go", "online"])
        def layout_test():
            for text, want in (("open chrome full screen", ("open chrome", "full")), ("open chrome accanto", ("open chrome", "side")),
                               ("open chrome side by side", ("open chrome", "side")), ("gmail on account x a schermo intero", ("gmail on account x", "full")),
                               ("open chrome", ("open chrome", None))):
                got = jv_launch_layout_strip(text)
                if want[1] is None and got[1] is None:
                    continue
                if got != want:
                    raise RuntimeError(f"'{text}' gave {got}, expected {want}")
            CONTESTO["jv_launch_dry"] = True
            try:
                CONTESTO.update(jv_online=True, jv_named=True, jv_browser=None, jv_chrome_layout=None)
                if not jv_launch_browser("chrome full screen", "chrome full screen") or CONTESTO.get("jv_chrome_layout") != "full":
                    raise RuntimeError("'chrome full screen' did not set the layout")
                if not jv_launch_browser("chrome side by side", "chrome side by side") or CONTESTO.get("jv_chrome_layout") != "side":
                    raise RuntimeError("'chrome side by side' did not set the layout")
                jv_launch_browser("open chrome full screen", "open chrome full screen")
                if CONTESTO.get("jv_chrome_layout") != "full":
                    raise RuntimeError("'open chrome full screen' did not set the layout")
                jv_chain("open chrome side by side then gmail", "open chrome side by side then gmail")
                if CONTESTO.get("jv_chrome_layout") != "side":
                    raise RuntimeError("the chain did not take the layout")
                kind, rect = jv_launch_plan_rect("full")
                if kind != "full":
                    raise RuntimeError("full screen plan is wrong")
                print("ok")
            finally:
                CONTESTO.update(jv_launch_dry=False, jv_browser=None, jv_online=False, jv_named=False, jv_chrome_layout=None)
                CONTESTO.pop("jv_chrome_win", None)
        run("Chrome layout words: full screen / beside Jarvis (nothing is opened)", layout_test)
        def intro_test():
            for R in (4, 5, 11):
                ls = jv_logo_lines(R, 120, 0.7, 2)
                if len(ls) != 2 * R + 1 + 2:
                    raise RuntimeError(f"logo of radius {R} has {len(ls)} lines")
            if jv_launch_maximize_self() not in (True, False):
                raise RuntimeError("maximise returned something odd")
            jv_logo_show()                                    # not a terminal here: it must do nothing at all
            print("ok")
        run("start-up logo: sizes are right, nothing happens without a real terminal", intro_test, need=["ok"])

        section("Update system (checks only, nothing is installed)")
        run("Get-SecurityStatus panel", cmd("Get-SecurityStatus"), need=["SECURITY STATUS", "FINGERPRINT", "CODE SCAN", "GUARD", "ISOLATION"])
        cand = os.path.join(tmp, "jarvis_candidate.py")
        shutil.copyfile(os.path.abspath(__file__), cand)      # the running Jarvis as a candidate: all 9 checks must pass
        run("implement jarvis <copy of myself> -Dry (all 9 safety checks)", cmd("Implement", "jarvis", cand, "-Dry"),
            need=["SECURITY GATE", "9/9 gates passed"], bad=["would be REFUSED", "BLOCKED"], red=False)

        section("Security guard (the scanner must catch the classic tricks; nothing is executed or installed)")
        import ast as _ast

        def scan_blocks(code, want):
            def f():
                got = jv_upd_scan(_ast.parse(code))
                if not got:
                    raise RuntimeError("the scanner let it through")
                if want not in " ".join(got):
                    raise RuntimeError(f"flagged, but not as expected: {got[0]}")
                print(got[0])
            return f
        tricks = (
            ("import os as o ... o.remove()", "import os as o\ndef f(p):\n    o.remove(p)\n", "os.remove"),
            ("rm = shutil.rmtree ... rm()", "import shutil\nrm = shutil.rmtree\ndef f(p):\n    rm(p)\n", "shutil.rmtree"),
            ("map(os.remove, files)", "import os\ndef f(l):\n    list(map(os.remove, l))\n", "os.remove"),
            ("getattr(os, 'rem' + 'ove')", "import os\ndef f():\n    getattr(os, 'rem' + 'ove')('x')\n", "computed attribute"),
            ("getattr(x, 'system')", "def f(x):\n    getattr(x, 'system')('y')\n", "system"),
            ("__subclasses__ escape", "def f():\n    return ().__class__.__bases__[0].__subclasses__()\n", "__"),
            ("Path('a').open('w')", "import pathlib\ndef f():\n    pathlib.Path('a').open('w')\n", "opened for writing"),
            ("os.environ['A'] = ...", "import os\ndef f():\n    os.environ['A'] = '1'\n", "os.environ"),
            ("sys.modules['os']", "import sys\ndef f():\n    return sys.modules['os']\n", "sys.modules"),
            ("zip.extractall()", "def f(z):\n    z.extractall('.')\n", "extractall"),
            ("import subprocess as sp", "import subprocess as sp\ndef f():\n    sp.run(['x'])\n", "subprocess.run"),
            ("import socket as s ... s.socket()", "import socket as s\ndef f():\n    return s.socket()\n", "socket"),
            ("winreg write", "import winreg\ndef f():\n    winreg.SetValueEx(1, 'a', 0, 1, 'b')\n", "winreg"),
        )
        for label, code, want in tricks:
            run(f"scanner blocks: {label}", scan_blocks(code, want))

        def harmless():
            code = ("import os\nimport re\n"
                    "def f(p):\n    with open(p, 'rb') as h:\n"
                    "        return re.sub('a', 'b', h.read().decode()) + str(os.path.getsize(p)) + os.environ.get('X', '')\n"
                    "def g(o):\n    return getattr(o, 'st_birthtime', None)\n")
            got = jv_upd_scan(_ast.parse(code))
            if got:
                raise RuntimeError("false alarm: " + got[0])
            print("read-only code passes")
        run("scanner lets normal read-only code through", harmless)

        def candidate_with(text, name, **kw):
            path = os.path.join(tmp, name)
            with open(os.path.abspath(__file__), "rb") as s_, open(path, "wb") as d_:
                d_.write(s_.read() + text)
            return path
        hidden = candidate_with("\n# access \u202eevil\u202c\n".encode("utf-8"), "cand_hidden.py")
        run("a hidden direction-change character is refused (check 1)", lambda: jv_upd_check(hidden, None),
            need=["BLOCKED", "U+202E"], red=True)
        run("a file that changed after staging is refused (check 2)", lambda: jv_upd_check(cand, None, "0" * 64),
            need=["BLOCKED", "changed after"], red=True)
        link = os.path.join(tmp, "cand_link.py")

        def linked():
            try:
                os.symlink(cand, link)
            except (OSError, NotImplementedError, AttributeError):
                print("(this system does not allow links here: skipped)")
                return
            ok_, phase_, _why = jv_upd_check(link, None)
            if ok_ or phase_ != "valid source":
                raise RuntimeError("a link was accepted as an update")
        run("a link instead of a plain file is refused (check 1)", linked, need=[], red=True)
        run("log lines cannot be forged or carry escape codes", lambda: print(
            "clean" if jv_upd_clean("a\nb\x1b[31m c\u202e") == "a b [31m c" else (_ for _ in ()).throw(
                RuntimeError(repr(jv_upd_clean("a\nb\x1b[31m c\u202e"))))))

        exts = [n for n in NOMI if GROUPS.get(n) == "Extensions"]
        if exts:
            section("Extensions (from ext/): registered and documented; not executed, I do not know their arguments")
            for n in exts:
                run(f"help {n}", cmd("Get-Help", n), need=["SYNTAX"])
    except KeyboardInterrupt:
        out()
        out("Stopped by user: the results are partial.", YELLOW)
    finally:
        try:
            os.chdir(old_cwd)
        except OSError:
            pass
        CONTESTO.clear()
        CONTESTO.update(snap)
        shutil.rmtree(tmp, ignore_errors=True)
    failed = [r for r in results if r[1]]
    return len(results) - len(failed), len(results), failed


@cmdlet("Maintenance", group="Assistant", usage="""maintenance     maintenance mode: health check of Jarvis, then a test of EVERY command
(say it in plain words too: "jarvis go in maintenance", "jarvis test all the commands")
The tests run on sample files in a temporary folder that is deleted afterwards: nothing of yours is changed,
no game or file is opened, nothing is installed. To update, use  implement jarvis)""")
def jv_upd_maintenance_cmd(args):
    """Maintenance mode: health check of Jarvis and a test of every command."""
    out()
    out("=== MAINTENANCE MODE ===  (everything else is on hold; Ctrl+C stops it)", CYAN)
    jv_upd_health([])
    out("Testing every command on sample files in a temporary folder (deleted afterwards)...", GRAY)
    t0 = time.monotonic()
    ok, total, failed = jv_upd_selftest()
    out()
    secs = time.monotonic() - t0
    if failed:
        out(f"{ok}/{total} tests passed in {secs:.1f} s. {len(failed)} FAILED:", RED)
        for label, why in failed:
            out(f"  - {label}: {why}", RED)
    else:
        out(f"All {total} tests passed in {secs:.1f} s. Every command works, sir.", GREEN)
    out("Maintenance finished: nothing of yours was changed. Back to normal operation.", GRAY)
    out()


# ======================= GAME LAUNCHER (jarvis open <game>) =======================
# Only 'jarvis open <game>' starts anything: the game's own program, found inside the game's own folder.
# A plain 'open <game>' keeps showing the data.win read-only and never starts it.
def jv_launch_extra_dirs():
    """Game folders learned during updates (JV_DATA)."""
    try:
        return [d for d in JV_DATA.get("game_dirs", []) if isinstance(d, str) and os.path.isdir(d)]
    except Exception:
        return []


def jv_launch_norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def jv_launch_exes(folder):
    """The programs that can start a game in this folder (installers, crash reporters... skipped)."""
    res = []
    try:
        names = sorted(os.listdir(folder), key=str.lower)
    except OSError:
        return res
    for n in names:
        low, p = n.lower(), os.path.join(folder, n)
        if any(s in low for s in JV_LAUNCH_SKIP):
            continue
        if os.name == "nt":
            ok = low.endswith(".exe") and os.path.isfile(p)
        elif sys.platform == "darwin":
            ok = low.endswith(".app") and os.path.isdir(p)
        else:
            ok = os.path.isfile(p) and (low.endswith((".x86_64", ".x86", ".sh", ".appimage"))
                                        or ("." not in n and os.access(p, os.X_OK)))
        if ok:
            res.append(p)
    return res


def jv_launch_best(exes, names):
    """Of several programs, the one named like the game; otherwise the biggest."""
    if not exes:
        return None
    want = {jv_launch_norm(n) for n in names if n}
    for p in exes:
        if jv_launch_norm(os.path.splitext(os.path.basename(p))[0]) in want:
            return p
    try:
        return max(exes, key=os.path.getsize)
    except OSError:
        return exes[0]


JV_LAUNCH_NOTGAME = ("steamworks shared", "steam controller configs", "steam linux runtime", "proton", "steamvr",
                     "common redist", "directx", "vcredist")


def jv_launch_generic():
    """Games that are not GameMaker: every sub-folder of the game libraries that holds a program
    (searched in the folder itself, then one and two levels below). {key: game}."""
    res = {}
    for lib in game_locations() + jv_launch_extra_dirs():
        try:
            subs = sorted(os.listdir(lib), key=str.lower)
        except OSError:
            continue
        alts = {}                                         # Steam: install folder -> real game title
        if os.path.basename(lib.rstrip("\\/")).lower() == "common":
            sa = os.path.dirname(lib.rstrip("\\/"))
            try:
                for f in os.listdir(sa):
                    if f.startswith("appmanifest_") and f.endswith(".acf"):
                        with open(os.path.join(sa, f), encoding="utf-8", errors="replace") as fh:
                            txt = fh.read(20000)
                        d1 = re.search(r'"installdir"\s+"([^"]+)"', txt)
                        n1 = re.search(r'"name"\s+"([^"]+)"', txt)
                        if d1 and n1:
                            alts[d1.group(1).lower()] = n1.group(1)
            except OSError:
                pass
        for n in subs:
            root = os.path.join(lib, n)
            if not os.path.isdir(root) or skip_dir(root) or n.lower().startswith(JV_LAUNCH_NOTGAME):
                continue
            key = os.path.normcase(os.path.realpath(root))
            if key in res:
                continue
            exes, winexe = [], False
            alt = alts.get(n.lower(), "")
            base = root.rstrip(os.sep).count(os.sep)
            for cur, ds, _fs in os.walk(root, onerror=lambda e: None):
                depth = cur.rstrip(os.sep).count(os.sep) - base
                ds[:] = [] if depth >= 3 else sorted(d for d in ds if not skip_dir(os.path.join(cur, d)))
                exes = jv_launch_exes(cur)
                if exes:
                    break
            if exes:
                best = jv_launch_best(exes, [n, alt])
                res[key] = {"name": n, "alt": alt, "root": root, "wins": [], "dirs": [],
                            "parts": [("launcher", best, None)], "winexe": False, "generic": True}
            elif os.name != "nt":
                try:
                    winexe = any(f.lower().endswith(".exe") for f in os.listdir(root))
                except OSError:
                    pass
                if winexe:
                    res[key] = {"name": n, "alt": alt, "root": root, "wins": [], "dirs": [],
                                "parts": [], "winexe": True, "generic": True}
    return res


def jv_launch_games(force=False):
    """Installed games, one per game folder (chapter folders are grouped under their parent):
    {name, alt, root, wins, parts:[(label, exe, chapter)], winexe}."""
    cached = CONTESTO.get("jv_launch_cache")
    if cached and not force and time.time() - cached[0] < 30:
        return cached[1]
    roots = {}
    for w in jv_games():
        d = os.path.dirname(os.path.abspath(w))
        m = re.fullmatch(JV_LAUNCH_CHAPTER, os.path.basename(d))
        root = os.path.dirname(d) if m else d
        g = roots.setdefault(os.path.normcase(os.path.realpath(root)),
                             {"name": os.path.basename(root) or root, "alt": "", "root": root,
                              "wins": [], "dirs": [], "parts": [], "winexe": False})
        g["wins"].append(w)
        g["dirs"].append((d, int(m.group(1)) if m else None))
    for g in roots.values():
        try:
            g["alt"] = gm_read_info(g["wins"][0])["name"] or ""
        except Exception:
            g["alt"] = ""
        names = [g["name"], g["alt"]]
        launcher = jv_launch_best(jv_launch_exes(g["root"]), names)
        if launcher:
            g["parts"] = [("launcher", launcher, None)]
        else:
            for d, ch in sorted(g["dirs"], key=lambda x: (x[1] or 0, x[0].lower())):
                exe = jv_launch_best(jv_launch_exes(d), names)
                if exe:
                    g["parts"].append((os.path.basename(d), exe, ch))
        if not g["parts"] and os.name != "nt":
            try:
                g["winexe"] = any(n.lower().endswith(".exe") for n in os.listdir(g["root"]))
            except OSError:
                pass
    for key, g in jv_launch_generic().items():           # every other game (Cry of Fear, ...)
        if key not in roots:
            roots[key] = g
    games = sorted(roots.values(), key=lambda g: g["name"].lower())
    CONTESTO["jv_launch_cache"] = (time.time(), games)
    return games


def jv_launch_match(phrase, games):
    """(matching games, chapter number or None) for what the person said."""
    p = re.sub(r"\s+(?:please|pls|now|subito|ora|per favore)$", "", phrase.strip(), flags=re.I)
    p = re.sub(r"^(?:(?:the|il|lo|la|my|mio|il mio|game|gioco|il gioco|the game)\s+)+", "", p, flags=re.I).strip()
    tries = [(p, None)]
    m = re.match(r"(?i)^(.*?)[\s,]*(?:chapter|capitolo|cap\.?|ch\.?|#)?\s*(\d{1,2})$", p)
    if m and m.group(1).strip():
        tries.append((m.group(1).strip(), int(m.group(2))))
    for text, ch in tries:
        n = jv_launch_norm(text)
        if len(n) < 2:
            continue
        exact = [g for g in games if n in (jv_launch_norm(g["name"]), jv_launch_norm(g["alt"]))]
        if exact:
            return exact, ch
        part = [g for g in games if len(n) >= 3 and (n in jv_launch_norm(g["name"]) or n in jv_launch_norm(g["alt"]))]
        if part:
            return part, ch
        if len(n) >= 5:
            close = [g for g in games if difflib.get_close_matches(n, [jv_launch_norm(g["name"]),
                                                                        jv_launch_norm(g["alt"])], n=1, cutoff=0.85)]
            if close:
                return close, ch
    return [], None


def jv_launch_run(game, part):
    """Start ONE program of a known game folder. Everything is checked first."""
    label, exe, chapter = part
    name = safe(game["name"])
    real_root = os.path.normcase(os.path.realpath(game["root"]))
    real_exe = os.path.normcase(os.path.realpath(exe))
    if not (real_exe.startswith(real_root + os.sep) and os.path.exists(exe)
            and (game.get("generic") or any(os.path.isfile(w) for w in game["wins"]))):
        jarvis_say(f"I won't start that, sir: it is not inside the folder of a game I know ({name}).")
        return
    if os.name != "nt" and exe.lower().endswith(".exe"):
        jarvis_say(f"{name} is a Windows program, sir: this system cannot start it.")
        return
    import subprocess
    jarvis_say(f"Launching {name}{'' if label == 'launcher' else ' (' + safe(label) + ')'}, sir. "
               "I only start the game's own program; I don't touch its files.")
    out(f"  {safe(exe)}", GRAY)
    try:
        if sys.platform == "darwin" and exe.lower().endswith(".app"):
            proc = subprocess.Popen(["open", exe], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
        elif os.name == "nt":
            flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            proc = subprocess.Popen([exe], cwd=os.path.dirname(exe), stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    close_fds=True, creationflags=flags)
        else:
            proc = subprocess.Popen([exe], cwd=os.path.dirname(exe), stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    close_fds=True, start_new_session=True)
    except OSError as e:
        jarvis_say(f"It would not start, sir ({safe(e.strerror or e)}).")
        return
    time.sleep(1.2)
    rc = proc.poll()
    if rc not in (None, 0):
        jarvis_say(f"It closed right away with exit code {rc}, sir. Try starting it once from its own folder.")
    else:
        jarvis_say(f"{name} is starting, sir.")
    out()


def jv_launch_start(game, chapter):
    parts = game["parts"]
    if not parts:
        if game["winexe"]:
            jarvis_say(f"{safe(game['name'])} has only a Windows program, sir: this system cannot start it.")
        else:
            jarvis_say(f"I found the folder of {safe(game['name'])} but no program to start in it, sir.")
        out(f"  {safe(game['root'])}", GRAY)
        jarvis_say(f"'open {safe(game['name'])}' (without 'jarvis') still shows its data.win.")
        return
    if len(parts) > 1:
        if chapter is not None:
            hit = [p for p in parts if p[2] == chapter]
            if not hit:
                jarvis_say(f"{safe(game['name'])} has no chapter {chapter} here, sir.")
                return
            jv_launch_run(game, hit[0])
            return
        jarvis_say(f"{safe(game['name'])} has several chapters, sir. Which one?")
        for i, p in enumerate(parts, 1):
            out(f"  [{i}] {safe(p[0])}", CYAN)
        CONTESTO["jv_launch_pending"] = [(game, p) for p in parts]
        jarvis_say("Say 'jarvis open 1', 'jarvis open 2'... or 'jarvis open <game> chapter 2'.")
        return
    jv_launch_run(game, parts[0])


def jv_launch_blocked(path):
    """Why this file must not be opened (Windows internal / system files), or None when it is fine."""
    full = os.path.normcase(os.path.realpath(path))
    if os.name == "nt":
        roots = [os.environ.get("SystemRoot"), os.environ.get("windir")]
        for r in roots:
            if r:
                rr = os.path.normcase(os.path.realpath(r))
                if full == rr or full.startswith(rr + os.sep):
                    return "it is inside the Windows system folder"
        try:
            if os.stat(path).st_file_attributes & 0x4:        # FILE_ATTRIBUTE_SYSTEM
                return "it is marked as a Windows system file"
        except OSError:
            pass
        if os.path.splitext(full)[1] in (".sys", ".dll", ".drv", ".mui", ".cat", ".cpl", ".ocx"):
            return "it is an internal Windows component file"
    else:
        for d in PSEUDO_DIRS | {"/boot", "/etc"}:
            if full == d or full.startswith(d + os.sep):
                return "it is a system file"
    return None


def jv_launch_file(path):
    """'jarvis open <file>': open any file with its normal program, except Windows internal ones."""
    full = os.path.abspath(path)
    name = safe(os.path.basename(full))
    why = jv_launch_blocked(full)
    if why:
        jarvis_say(f"I won't open {name}, sir: {why}.")
        return
    import subprocess
    ack(f"Opening {name} with its usual program.")
    out(f"  {safe(full)}", GRAY)
    try:
        if os.name == "nt":
            os.startfile(full)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", full], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(["xdg-open", full], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError as e:
        jarvis_say(f"It would not open, sir ({safe(e.strerror or e)}). There may be no program set for this file type.")
        return
    CONTESTO["file"] = full
    CONTESTO["jlast"] = {"path": full, "sel": full}
    out()


JV_LAUNCH_NOSEARCH = r"(?:the\s+)?(?:scan|status|check|battery|memory|ram|search|find|update|test|everything|all|games?|corrupt)\b"


def jv_launch_search(phrase, limit=60):
    """Last resort for 'jarvis open <name>': look for a shortcut, a program or a game folder with that name
    on the whole PC (Windows folder excluded) and open it. True when it handled the request."""
    p = re.sub(r"\s+(?:please|pls|now|subito|ora|per favore)$", "", phrase.strip().strip("\"'`"), flags=re.I)
    p = re.sub(r"^(?:(?:the|il|lo|la|my|mio|il mio|game|gioco|il gioco|the game)\s+)+", "", p, flags=re.I).strip()
    n = jv_launch_norm(p)
    if len(n) < 3 or len(p.split()) > 6 or re.match(JV_LAUNCH_NOSEARCH, p, re.I) or re.search(r"[\\/:]", p):
        return False

    def close(stem):
        s = jv_launch_norm(stem)
        if not s:
            return False
        if s == n or (len(n) >= 6 and n in s):
            return True
        if len(n) >= 5 and abs(len(s) - len(n)) <= 4:
            sm = difflib.SequenceMatcher(None, s, n)
            return sm.real_quick_ratio() >= 0.85 and sm.ratio() >= 0.85
        return False

    home = os.path.expanduser("~")
    quick = []
    if os.name == "nt":
        for v in ("ProgramData", "APPDATA"):
            if os.environ.get(v):
                quick.append(os.path.join(os.environ[v], "Microsoft", "Windows", "Start Menu"))
        quick += [os.path.join(home, "Desktop"), os.path.join(home, "OneDrive", "Desktop"),
                  os.path.join(os.environ.get("PUBLIC", "C:\\Users\\Public"), "Desktop")]
    win = os.path.normcase(os.environ.get("SystemRoot") or os.environ.get("windir") or "\x00")
    jarvis_say(f"I don't know '{safe(p)}' yet, sir. Searching this PC for it (Ctrl+C stops me)...")
    t0, found, stopped = time.time(), [], False

    def scan(roots):
        nonlocal stopped
        for root in roots:
            if not os.path.isdir(root):
                continue
            for cur, ds, fs in os.walk(root, onerror=lambda e: None):
                if time.time() - t0 > limit:
                    stopped = True
                    return
                ds[:] = [d for d in ds if not skip_dir(os.path.join(cur, d))
                         and os.path.normcase(os.path.join(cur, d)) != win
                         and d.lower() not in ("$recycle.bin", "system volume information", "windowsapps")]
                for d in ds:
                    if close(d):
                        found.append((2, os.path.join(cur, d)))
                for f in fs:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in (".lnk", ".url", ".exe") and close(os.path.splitext(f)[0]) \
                            and not any(x in f.lower() for x in JV_LAUNCH_SKIP):
                        found.append((0 if ext != ".exe" else 1, os.path.join(cur, f)))
                if len(found) >= 12:
                    return

    try:
        scan(quick)
        if not found:
            scan(pc_roots())
    except KeyboardInterrupt:
        out()
        jarvis_say("Stopped, sir.")
        return True
    found = [x for x in found if jv_launch_blocked(x[1]) is None]
    found.sort(key=lambda x: (x[0], len(x[1])))
    for rank, path in found:
        if rank in (0, 1) and os.path.isfile(path):
            if rank == 1:
                jv_launch_run({"name": os.path.splitext(os.path.basename(path))[0], "root": os.path.dirname(path),
                               "wins": [], "generic": True}, ("launcher", path, None))
            else:
                jv_launch_file(path)
            return True
        if rank == 2 and os.path.isdir(path):
            exes, base = [], path.rstrip(os.sep).count(os.sep)
            for cur, ds, _fs in os.walk(path, onerror=lambda e: None):
                ds[:] = [] if cur.rstrip(os.sep).count(os.sep) - base >= 3 else sorted(
                    d for d in ds if not skip_dir(os.path.join(cur, d)))
                exes = jv_launch_exes(cur)
                if exes:
                    break
            best = jv_launch_best(exes, [os.path.basename(path), p])
            if best:
                jv_launch_run({"name": os.path.basename(path), "root": path, "wins": [], "generic": True},
                              ("launcher", best, None))
                return True
    jarvis_say(f"I searched the whole PC and found nothing called '{safe(p)}'{' (time limit reached)' if stopped else ''}, sir.")
    return True


