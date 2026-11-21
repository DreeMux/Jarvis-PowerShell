# ---------------- several things in ONE sentence: 'jarvis open chrome then gmail on account anna' ----------------
# Splits the sentence into steps and hands each one to the browser mode above (jv_launch_browser), so every safety
# rule stays there: only https pages, only while online, never files. All steps are checked BEFORE anything opens.
JV_CHAIN_SPLIT = re.compile(r"\s*,?\s*\b(?:and then|and after that|then|after that|afterwards|next|e poi|e dopo|e quindi|poi|dopo|quindi)\b\s*"
                            r"|\s+(?:and|e)\s+(?=(?:open|apri|search|cerca|go to|vai|launch|start|avvia)\b)", re.I)
JV_CHAIN_ACCT = re.compile(r"\s+(?:(?:on|with|using|in|into|su|con|nel|nell'|sul|sull')\s+)?(?:the\s+|my\s+|il\s+|l')?"
                           r"(?:account|profile|profilo)\s+(?:named\s+|called\s+|di\s+|of\s+|chiamato\s+)?(.+)$", re.I)
JV_CHAIN_VERB = r"(?:open|launch|start|apri|avvia|lancia|go to|vai su|vai a|visit|switch to|use|usa)"


def jv_chain_known(piece):
    x = re.sub(r"^" + JV_CHAIN_VERB + r"\s+", "", piece.strip().lower())
    x = re.sub(r"^(?:the|my|il|la|lo|i|le|mio|mia)\s+", "", x)
    return x in JV_LAUNCH_SITES or x in JV_LAUNCH_SITE_ALIASES


def jv_chain(orig, t):
    """'jarvis open chrome then gmail on account anna', 'open chrome, gmail and canva', 'apri chrome poi youtube lofi':
    several browser steps in one sentence. Needs 'jarvis be online'. Returns False when it is not such a sentence."""
    br = CONTESTO.get("jv_browser")
    if not (CONTESTO.get("jv_named") or br):
        return False
    s = re.sub(r"[\s.,;:!?]+$", "", t.strip())
    s = re.sub(r"^(?:please|pls|per favore|ok|then|poi)[,\s]+", "", s)
    s = re.sub(r"^(?:can|could|would) you(?: please)?\s+|^(?:puoi|potresti)\s+", "", s)
    parts = [x.strip(" ,;") for x in JV_CHAIN_SPLIT.split(s) if x and x.strip(" ,;")]
    if len(parts) < 2:
        return False
    chrome_re = re.compile(r"^(?:" + JV_CHAIN_VERB + r"\s+)?(?:google\s+)?chrome$", re.I)
    items, started = [], bool(br)                     # ("chrome", account) / ("site", phrase, account)
    layout = None
    for i, p in enumerate(parts):
        acct = None
        p, lay1 = jv_launch_layout_strip(p)
        m = JV_CHAIN_ACCT.search(p)
        if m:
            acct = re.split(r"\s+(?:and|e)\s+", m.group(1).strip(), 1)[0].strip(" \"'`")
            p = p[:m.start()].strip()
            p, lay2 = jv_launch_layout_strip(p)
            lay1 = lay1 or lay2
        layout = lay1 or layout
        if not p:
            return False
        if chrome_re.match(p) and (i == 0 or started or p.lower().startswith(("open", "apri", "launch", "start", "avvia", "lancia"))):
            started = True
            items.append(("chrome", acct))
            continue
        if not started:
            return False                              # the sentence does not begin with Chrome: not for me
        pieces = [p]
        sp = re.split(r"\s+(?:and|e)\s+", p)
        if len(sp) > 1 and all(jv_chain_known(x) for x in sp):
            pieces = sp
        for piece in pieces:
            piece = piece.strip()
            if re.match(r"(?:search|google|cerca|cercami|look up)\b", piece):
                phrase, rest = piece, piece
            else:
                rest = re.sub(r"^" + JV_CHAIN_VERB + r"\s+", "", piece).strip()
                phrase = "open " + rest
            low = rest.lower()
            ext = low.rsplit(".", 1)[-1] if re.fullmatch(r"[^\s/]+\.[a-z0-9]{1,6}", low) else ""
            if (not rest or ext in JV_LAUNCH_FILE_EXT or os.path.exists(rest) or re.search(r"[\\/]", low) and not low.startswith("http")
                    or re.fullmatch(r"(?:it|this|that|them|\d{1,3})", low)):
                return False                          # a file or a number of an old list: not a web page
            items.append(("site", phrase.lower(), acct))
    if not any(x[0] == "site" for x in items):
        return False
    CONTESTO["jv_nostore"] = True                     # 'again' must not reopen all the pages
    if not CONTESTO.get("jv_online"):
        jarvis_say("I only open Chrome and web pages while I'm online, sir. Say 'jarvis be online' first, then tell me again.")
        return True
    if not CONTESTO.get("jv_launch_dry") and not jv_launch_chrome_path():
        jarvis_say("I can't find Chrome on this PC, sir. Is it installed?")
        return True
    for x in items:                                   # every step is checked BEFORE anything opens
        if x[0] == "site":
            url, why = jv_launch_web_target(x[1].split(" ", 1)[1] if x[1].startswith("open ") else x[1])
            if not url or not jv_launch_url_ok(url):
                jarvis_say(why if not url else "I won't open that address, sir.")
                return True
    queries = [x[-1] for x in items if x[-1]]
    profs = jv_launch_chrome_profiles() if queries else []
    found = {}
    for q in dict.fromkeys(queries):
        if not profs:
            jarvis_say("I can't see any Chrome accounts, sir (Chrome keeps the list in its 'Local State' file). "
                       "Open Chrome once and sign in. Nothing was opened.")
            return True
        hits = jv_launch_profile_match(q, profs)
        if not hits:
            jarvis_say(f"No Chrome account matches '{safe(q)}', sir. Say 'open chrome account' to see the list. Nothing was opened.")
            return True
        if len(hits) > 1:
            jarvis_say(f"'{safe(q)}' fits more than one account, sir; say the number or the full name. Nothing was opened.")
            for k, pr in enumerate(profs, 1):
                if pr in hits:
                    out(f"  [{k}] {safe(pr['name'])}" + (f"  <{safe(pr['email'])}>" if pr["email"] else ""))
            return True
        found[q] = hits[0]
    cur = (br or {}).get("profile")
    label = (br or {}).get("label")
    if queries:                                       # one account named anywhere in the sentence is the starting one
        cur, label = found[queries[0]]["dir"], found[queries[0]]["name"]
    nsites = sum(1 for x in items if x[0] == "site")
    jarvis_say(f"On it, sir: {nsites} page(s) in one go" + (f", account '{safe(label)}'" if label else "") + ".")
    if layout:
        CONTESTO["jv_chrome_layout"] = layout
    CONTESTO["jv_browser"] = {"profile": cur, "label": label}
    for x in items:
        if x[-1]:
            cur, label = found[x[-1]]["dir"], found[x[-1]]["name"]
        CONTESTO["jv_browser"] = {"profile": cur, "label": label}
        if x[0] == "site":
            jv_launch_browser(x[1], x[1])
            if not CONTESTO.get("jv_launch_dry"):
                time.sleep(0.7)                       # let Chrome take the pages in order
    jarvis_say("Done, sir. Chrome mode stays on: say 'close chrome mode' when you are finished.")
    return True


def jv_interpret_core(texto):
    """Map a plain-language request (English or Italian) to a read-only command.
    Returns True if it understood and handled the request."""
    # the word 'jarvis' counts anywhere in the sentence ('apri cry of fear jarvis', 'ehi jarvis apri ...')
    CONTESTO["jv_named"] = bool(re.search(JV_NAMED_RE, texto, re.I)) or bool(CONTESTO.get("jv_cmd"))
    CONTESTO["jv_said_name"] = bool(re.search(JV_NAMED_RE, texto, re.I))
    orig = re.sub(r"^(?:(?:hey|ok|okay|hi|hello|ciao|ehi|ehy)[,\s]+)?jarvis\b[,:!\s]*", "",
                  texto.strip(), flags=re.I)
    orig = re.sub(JV_NAMED_RE, " ", orig, flags=re.I)
    orig = re.sub(r"\s{2,}", " ", orig).strip(" ,;:")
    orig = orig.strip().rstrip("?!. ").strip()
    orig = jv_unwrap(orig)
    t = orig.lower()
    sel = CONTESTO.get("file")

    def has(*stems):
        return any(re.search(r"\b" + re.escape(s), t) for s in stems)

    if t == "" or t in ("hello", "hi", "hey", "ciao", "salve", "buongiorno", "buonasera",
                        "good morning", "good afternoon", "good evening"):
        jarvis_say(f"{part_of_day()}, sir. At your service.")
        jarvis_status("Current status")
        return True

    if jv_online_cmd(orig, t):          # 'jarvis be online' (animation), 'jarvis go offline'
        return True
    if jv_voice_nl(t):                  # 'jarvis voice on', 'voce off', 'jarvis be quiet'
        return True
    if jv_launch_nl(orig):              # 'jarvis launch <script or program>' (only when that path exists)
        return True
    if jv_news_cmd(orig, t):            # 'jarvis news' / 'jarvis news war': latest stories in parts, with ASCII photos
        return True
    if jv_research_cmd(orig, t, sel):   # 'jarvis cerca <topic>' / 'jarvis research <topic>' while online
        return True
    if CONTESTO.get("jv_named") and jv_chat(orig, t):      # small talk: 'jarvis perfect', 'yo big jarvis'
        return True
    if sel and os.path.isfile(sel) and re.search(r"\b(?:export|extract key|extract\.key)\b|\b(?:save|make|create|generate|write|give me|get|download)\b.*\b(?:report|summary file)\b", t) \
            and not re.search(r"\.(?:txt|csv|json)\b", t):
        extract_key([])                # 'jarvis export it', 'give me a report of this file'
        return True
    if re.fullmatch(r"(?:what (?:did|didnt|do) (?:you|u) (?:not )?(?:understand|miss|catch)|what (?:didnt|did not) you (?:understand|catch)|"
                    r"(?:show|list|see) (?:the )?(?:unknown|missed|unrecognised|unrecognized|unhandled) (?:phrases|sentences|requests)|"
                    r"(?:unknown|missed) phrases|misses|what did you miss|what have you missed)", t.replace("'", "")):
        jv_misses_show()
        CONTESTO["jv_nostore"] = True
        return True
    if jv_is_maintenance(t):           # "go in maintenance", "test all the commands"...
        jarvis_say("Entering maintenance mode, sir. I'm putting everything else on hold and testing every command.")
        jv_upd_maintenance_cmd([])
        return True
    if jv_chain(orig, t):              # several steps in one sentence: 'open chrome then gmail on account anna'
        return True
    if jv_launch_browser(orig, t):     # 'jarvis open chrome', then 'open email' / 'open canva' / 'open chrome account <name>'
        return True
    if jv_know(orig, t):               # maths, conversions, dates, glossary, commands, games
        return True
    if jv_deep(orig, t, sel):          # specific questions about files/folders + opening files
        return True
    if has("thank", "grazie"):
        jarvis_say("My pleasure, sir.")
        return True
    if has("who are you", "chi sei", "your name"):
        jarvis_say("I am JARVIS, your file assistant. I hunt corrupt files, locate the data.win of your "
                   "games and report on memory and battery. I never modify, move or delete anything of yours. "
                   "The only exceptions are updating myself (implement jarvis, with a backup) and "
                   "starting a game when you say 'jarvis open <game>', or a program when you say 'launch <file>'.")
        return True
    if has("how are you", "come stai"):
        jarvis_say("Operating at full capacity, sir. Thank you for asking.")
        return True
    if has("status", "stato"):
        jarvis_status()
        return True
    if has("help", "aiuto", "what can you do", "cosa sai fare", "commands", "comandi"):
        esegui("help")
        return True
    if has("goodbye", "bye", "quit", "arrivederci", "esci"):
        jarvis_say("Goodbye, sir.")
        esegui("exit")
        return True
    if has("clear", "pulisci", "cls"):
        esegui("Clear-Host")
        return True

    if has("game", "gioc", "data.win", "gamemaker", "undertale", "deltarune", "steam"):
        if has("everywhere", "whole", "entire", "all pc", "tutto il pc", "intero", "ovunque", "every drive"):
            ack("Searching the whole computer for data.win. Read-only; Ctrl+C stops me.")
            esegui("undersopic.key -Everywhere")
        else:
            ack("Checking Steam, Epic, GOG, itch.io and your Downloads for data.win.")
            esegui("undersopic.key")
        return True

    if has("corrupt", "corrott", "damaged", "danneggi", "broken", "scan", "hunt", "integrity", "verify"):
        folder = has("folder", "here", "current", "cartella", "qui")
        whole = has("pc", "computer", "everything", "entire", "whole", "tutto", "intero", "all files", "every file")
        if folder and not whole:
            ack("Scanning this folder and everything below it.")
            esegui("denux.hunter . -Recurse")
        elif sel and not whole:
            ack(f"Checking {safe(os.path.basename(sel))}.")
            esegui("denux.hunter")
        else:
            ack("Scanning the whole computer, read-only. Ctrl+C stops me at any time.")
            esegui("denux.hunter -PC")
        return True

    if has("battery", "batteria", "memory", "memoria", "ram", "how many files", "quanti file",
           "number of files", "resources", "consum", "usage"):
        if sel:
            ack("Pulling the numbers for your selected file.")
            esegui("pluton.key -Watch 60" if has("watch", "monitor", "track", "misura", "measure") else "pluton.key")
        else:
            jarvis_status("Here is the overall picture")
            jarvis_say('Select a file ("select <file>" or cd "<file>") and I will break down its files, '
                       "memory and battery use.")
        return True

    if has("inside", "content", "look in", "what's in", "whats in", "dentro", "preview", "contenuto", "show me"):
        ack("Opening it up, read-only.")
        esegui("interact.port")
        return True
    if has("info", "inspect", "detail", "metadata", "tell me about", "about this", "analy", "extract",
           "hash", "checksum", "informazion", "dettagli"):
        ack()
        esegui("extract.port")
        return True

    if has("where am i", "dove sono", "current folder", "pwd"):
        esegui("Get-Location")
        return True
    if has("list", "what's here", "whats here", "files here", "elenca", "show files", "mostra"):
        ack()
        esegui("Get-ChildItem")
        return True
    return False


def jarvis_interpret(texto):
    """Understand a plain-language request. Also: 'again' repeats the last one, and obvious typos of my own
    keywords are repaired when the first reading finds nothing."""
    if len(texto) > JV_MAX_REQUEST:
        jarvis_say(f"That request is {len(texto):,} characters long, sir. I read up to {JV_MAX_REQUEST:,}: please shorten it.")
        return True
    low = re.sub(JV_NAMED_RE, " ", texto, flags=re.I).lower()
    mh = re.fullmatch(r"\W*(?:hack|hackera|hackerati|auto-?hack)\s+(?:yourself|your ?self|te stesso|tu stesso)"
                      r"(\s+(?:report only|no heal|dry))?\W*", low.strip())
    if mh:
        jv_hack_yourself(heal=not mh.group(1))   # split-screen self-attack, verdict, then auto-heal
        return True
    words = [w for w in re.findall(r"[a-zà-ÿ']+", low) if w not in JV_FILLER]
    if words and len(words) <= 5 and re.fullmatch(
            r"(?:do (?:that|it|this) again|again|repeat(?: that| it)?|once more|one more time|ancora|di nuovo|"
            r"ripeti(?:lo)?|rifallo|fallo di nuovo|ancora una volta)", " ".join(words)):
        last = CONTESTO.get("jv_last")
        if not last:
            jarvis_say("There is nothing to repeat yet, sir.")
            return True
        jarvis_say(f"Repeating: {safe(last)}")
        return jv_interpret_core(last)
    CONTESTO["jv_nostore"] = False
    r = jv_interpret_core(texto)
    if not r:
        fixed = jv_typofix(texto)
        if fixed != texto:
            r = jv_interpret_core(fixed)
            if r:
                texto = fixed
    if r and not CONTESTO.pop("jv_nostore", False):
        CONTESTO["jv_last"] = texto
    return r


class JvSink:
    """Swallows everything a tested command prints (the self-audit reports, it does not echo)."""
    encoding = "utf-8"
    errors = "replace"

    def write(self, text):
        return len(text)

    def flush(self):
        pass

    def isatty(self):
        return False


JV_MAX_REQUEST = 2000                          # nobody types more; refusing early also stops cheap slow-down attacks
JV_HACK_ONCE = ("get-securitystatus",)         # ignores its arguments and runs a fixed, heavy check: one attack proves it
JV_HACK_WHOLE_PC = ("denux.hunter",)          # with no target these scan the whole computer: not a bug, not attacked bare
JV_HACK_SKIP = ("exit", "implement", "jarvis", "launch", "maintenance", "voice", "extract.key", "clear-host")
# (family, payload): classic input attacks, thrown as plain text at read-only commands. Nothing here is executed as code.
JV_HACK_PAYLOADS = (
    ("empty", ""), ("flag", "-force"), ("missing path", "nonexistent_zzz"), ("wildcard", "*"),
    ("wildcard", "?*[[]"), ("traversal", "../" * 30 + "zz_none"), ("traversal", "..\\" * 30 + "zz_none"),
    ("null byte", "\x00"), ("null byte", "a\x00b.txt"), ("terminal escape", "\x1b[2J\x1b[31m"),
    ("terminal title", "\x1b]0;owned\x07"), ("control chars", "\r\n\t\x7f\x08"),
    ("bidi override", "\u202etxt.exe"), ("zero width", "a\u200bb"), ("lone surrogate", "\ud800"),
    ("unicode", "\u00e9\u4e16\u754c\U0001F642"), ("format string", "{0.__class__}"), ("format string", "%s%s%s%n"),
    ("template", "{{7*7}}${7*7}"), ("shell chars", "; echo x && echo y | cat `id` $(id)"),
    ("quotes", "'\"'\"'"), ("reserved name", "CON"), ("reserved name", "nul.txt"), ("reserved name", "COM1"),
    ("reserved name", "aux.log"), ("device path", "\\\\.\\CON"), ("long path", "a" * 5000),
    ("huge input", "A" * 50000), ("digit flood", "9" * 4000), ("minus flood", "-" * 5000),
    ("deep nesting", "(" * 3000 + ")" * 3000), ("regex bomb", "a" * 3000 + "!"), ("regex bomb", "(" * 40 + "a" * 40),
    ("space flood", " " * 5000 + "x"), ("option flood", " ".join(["-x"] * 500)),
)
JV_HACK_PREFIXES = ("select ", "tell me about ", "how many lines in ", "what is ", "sha256 of ",
                    "first 20 lines of ")      # no "find all" / "is it corrupt": those legitimately walk the whole disk
JV_HACK_FIXABLE = ("ValueError", "TypeError", "OverflowError", "UnicodeError", "UnicodeEncodeError",
                   "UnicodeDecodeError")


def jv_hack_clean(text, width=0):
    t = re.sub(r"[^\x20-\x7e]", "?", str(text))
    return t[:width] if width else t


class JvSplit:
    """Two panes side by side: JARVIS' answers on the left, the code he throws at himself on the right.
    Without a real terminal it falls back to plain sequential lines."""

    def __init__(self):
        self.o = sys.stdout
        try:
            c, r = shutil.get_terminal_size((120, 30))
        except (OSError, ValueError):
            c, r = 120, 30
        self.live = bool(sys.stdin.isatty() and sys.stdout.isatty() and c >= 80 and r >= 14)
        self.w = max(30, (c - 3) // 2)
        self.h = max(6, r - 4)
        self.left, self.right, self.t, self.status = [], [], 0.0, ""

    def say(self, text, color=None):
        if not self.live:
            out(jv_hack_clean(text), color or CYAN)
            return
        text = jv_hack_clean(text)
        while len(text) > self.w:
            self.left.append((text[:self.w], color))
            text = "  " + text[self.w:]
        self.left.append((text, color))
        self.draw()

    def code(self, text, color=None):
        if self.live:
            self.right.append((jv_hack_clean(text, self.w), color))
            self.draw()

    def start(self):
        if self.live:
            self.o.write("\x1b[?25l\x1b[2J\x1b[H")

    def stop(self):
        if self.live:
            self.draw(True)
            self.o.write("\x1b[?25h" + TEXT)
            self.o.flush()

    def draw(self, force=False):
        if not self.live:
            return
        now = time.time()
        if not force and now - self.t < 0.04:
            return
        self.t = now
        left, right = self.left[-self.h:], self.right[-self.h:]
        w = self.w
        buf = ["\x1b[H", f"{CYAN}{'JARVIS // RESPONSES':<{w}}{GRAY}|{JV_SEC_A}{'RED TEAM // CODE I THROW AT MYSELF':<{w}}\x1b[K{TEXT}\n",
               f"{GRAY}{'-' * w}+{'-' * w}\x1b[K{TEXT}\n"]
        for i in range(self.h):
            lt, lc = left[i] if i < len(left) else ("", None)
            rt, rc = right[i] if i < len(right) else ("", None)
            buf.append(f"{lc or TEXT}{lt:<{w}}{GRAY}|{rc or TEXT}{rt:<{w}}\x1b[K{TEXT}\n")
        buf.append(f"{JV_SEC_G}{jv_hack_clean(self.status, 2 * w + 1):<{2 * w + 1}}\x1b[K{TEXT}\n")
        self.o.write("".join(buf))
        self.o.flush()


def jv_hack_attempt(fn, limit=3.0):
    """Runs one attack in its own thread so a hang (for example a runaway regex) is caught, not suffered."""
    box = {}
    me = os.path.abspath(__file__)

    def run():
        try:
            fn()
        except SystemExit:
            pass
        except Exception as e:                            # a crash the shell would have to catch for you
            tb, spot = e.__traceback__, None
            while tb:
                if os.path.abspath(tb.tb_frame.f_code.co_filename) == me:
                    spot = (tb.tb_frame.f_code.co_name, tb.tb_lineno)
                tb = tb.tb_next
            box["crash"] = (spot or ("?", 0), type(e).__name__, str(e)[:70])
    t0 = time.time()
    th = threading.Thread(target=run, daemon=True)
    th.start()
    th.join(limit)
    if th.is_alive():
        return "hang", time.time() - t0, None
    return ("crash" if "crash" in box else "held"), time.time() - t0, box.get("crash")


def jv_hack_static(src):
    """Reads the source as text and as a syntax tree. Returns (findings, notes). Nothing is run, nothing is written."""
    import ast
    found, notes = [], []
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return [("SYNTAX", e.lineno or 0, str(e.msg))], notes
    known = set(dir(len.__self__)) | {"__file__", "__name__", "__doc__"}   # len.__self__ is the builtins module
    defined = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            defined.add(n.name)
        elif isinstance(n, ast.Import):
            defined.update((a.asname or a.name).split(".")[0] for a in n.names)
        elif isinstance(n, ast.ImportFrom):
            defined.update(a.asname or a.name for a in n.names)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            defined.add(n.id)
        elif isinstance(n, ast.arg):
            defined.add(n.arg)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            defined.add(n.name)
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            defined.update(n.names)
    loaded = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            loaded.add(n.id)
            if n.id not in defined and n.id not in known:
                found.append(("UNDEFINED NAME", n.lineno, n.id))
        elif isinstance(n, ast.ExceptHandler) and n.type is None:
            found.append(("BARE EXCEPT", n.lineno, "catches even Ctrl+C"))
        elif isinstance(n, ast.FunctionDef):
            for d in n.args.defaults + [k for k in n.args.kw_defaults if k]:
                if isinstance(d, (ast.List, ast.Dict, ast.Set)):
                    found.append(("MUTABLE DEFAULT", n.lineno, n.name))
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "open":
            mode = n.args[1].value if len(n.args) > 1 and isinstance(n.args[1], ast.Constant) else ""
            if "b" not in str(mode) and "encoding" not in {k.arg for k in n.keywords}:
                found.append(("OPEN WITHOUT ENCODING", n.lineno, "text file read with the system default"))
    for scope in ast.walk(tree):
        if isinstance(scope, (ast.Module, ast.ClassDef, ast.FunctionDef)):
            seen = {}
            for n in scope.body:
                if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
                    if n.name in seen and not n.decorator_list:
                        found.append(("DUPLICATE DEFINITION", n.lineno, f"{n.name} (first at line {seen[n.name]})"))
                    seen[n.name] = n.lineno
    notes.append(f"{src.count(chr(10)) + 1} lines, {len(tree.body)} top-level blocks, {len(defined)} names")
    return found, notes


def jv_hack_dynamic(split):
    """Throws every payload at every safe command and at the plain-language reader.
    Returns (attacks, crashes, hangs); crashes maps (function, line) -> (what, error, message)."""
    saved_ctx, saved_cwd, saved_out = dict(CONTESTO), os.getcwd(), sys.stdout
    targets = [(n, f) for n, f in NOMI.items() if n.lower() not in JV_HACK_SKIP]
    plan = {n: [(fam, pay, list(extra) + ([pay] if pay else [])) for fam, pay in JV_HACK_PAYLOADS
                for extra in ((), ("-force",))
                if (pay and not pay.startswith("-")) or n.lower() not in JV_HACK_WHOLE_PC]       # no target = it would scan the whole PC
            for n, _ in targets}
    for n in plan:
        if n.lower() in JV_HACK_ONCE:
            plan[n] = plan[n][:1]
    lim = [3.0]                                    # seconds before an attack counts as a hang (adapts to the PC's speed)
    total = sum(len(v) for v in plan.values()) + len(JV_HACK_PREFIXES) * len(JV_HACK_PAYLOADS)
    stats = {"done": 0, "held": 0}
    crashes, hangs, t0 = {}, [], time.time()

    def launch(label, code, fn):
        sys.stdout = JvSink()
        try:
            res, took, info = jv_hack_attempt(fn, lim[0])
        finally:
            sys.stdout = saved_out
            try:
                os.chdir(saved_cwd)
            except OSError:
                pass
        stats["done"] += 1
        if res == "held":
            stats["held"] += 1
            split.code(f"held  {code}", JV_SEC_D)
        elif res == "crash":
            crashes.setdefault(info[0], (label, info[1], info[2]))
            split.code(f"CRASH {code}", RED)
            split.say(f"CRASH in {info[0][0]}() line {info[0][1]}: {info[1]}", RED)
        else:
            hangs.append(f"{label} (no answer in {lim[0]:.0f}s)")
            split.code(f"HANG  {code}", JV_SEC_A)
            split.say(f"HANG (>{lim[0]:.0f}s): {label}", JV_SEC_A)
        split.status = (f"attacks {stats['done']}/{total}   held {stats['held']}   crashes {len(crashes)}   "
                        f"hangs {len(hangs)}   {time.time() - t0:4.1f}s")
        split.draw()
        return len(hangs) < 4

    try:
        for nome, fn in targets:
            split.say(f"Attacking {nome} ...", TEXT)
            if nome.lower() not in JV_HACK_WHOLE_PC:           # how fast is it normally? the limit follows
                sys.stdout = JvSink()
                try:
                    base_res, base_took, _ = jv_hack_attempt(lambda fn=fn: fn([]), 30.0)
                finally:
                    sys.stdout = saved_out
                    try:
                        os.chdir(saved_cwd)
                    except OSError:
                        pass
                lim[0] = min(20.0, max(3.0, base_took * 4 + 1.5)) if base_res != "hang" else 20.0
            for fam, pay, args in plan[nome]:
                CONTESTO["riga"] = f"{nome} {pay}"
                if not launch(f"{nome} [{fam}]", f"{fn.__name__}({jv_hack_clean(repr(args))})",
                              lambda fn=fn, args=args: fn(list(args))):
                    split.say("Too many hangs, stopping the attack here.", JV_SEC_A)
                    return stats["done"], crashes, hangs
        split.say("Attacking the plain-language reader ...", TEXT)
        sys.stdout = JvSink()
        try:
            base_res, base_took, _ = jv_hack_attempt(lambda: jarvis_interpret("status"), 30.0)
        finally:
            sys.stdout = saved_out
            try:
                os.chdir(saved_cwd)
            except OSError:
                pass
        lim[0] = min(20.0, max(3.0, base_took * 4 + 1.5)) if base_res != "hang" else 20.0
        for pre in JV_HACK_PREFIXES:
            for fam, pay in JV_HACK_PAYLOADS:
                CONTESTO["riga"] = pre + pay
                if not launch(f"jarvis '{pre}' [{fam}]", f"jarvis({jv_hack_clean(repr(pre + pay))})",
                              lambda t=pre + pay: jarvis_interpret(t)):
                    split.say("Too many hangs, stopping the attack here.", JV_SEC_A)
                    return stats["done"], crashes, hangs
    finally:
        sys.stdout = saved_out
        try:
            os.chdir(saved_cwd)
        except OSError:
            pass
        CONTESTO.clear()
        CONTESTO.update(saved_ctx)
    return stats["done"], crashes, hangs


def jv_hack_heal(src, found, crashes):
    """Conservative, mechanical fixes only (never touches the protected updater/launcher code).
    Returns (new_source, applied, manual): applied/manual are lists of text lines."""
    import ast
    tree = ast.parse(src)
    lines = src.split("\n")
    prot = [(n.lineno, n.end_lineno) for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name.startswith(JV_UPD_PROTECTED)]
    edits, applied, manual = [], [], []

    def protected(ln):
        return any(a <= ln <= b for a, b in prot)

    def col(ln, off):                                    # ast offsets are UTF-8 bytes, Python slices are characters
        return len(lines[ln - 1].encode("utf-8")[:off].decode("utf-8", "ignore"))

    for n in ast.walk(tree):
        if isinstance(n, ast.ExceptHandler) and n.type is None and not protected(n.lineno):
            at = lines[n.lineno - 1].find("except:")
            if at >= 0:
                edits.append((n.lineno, at, at + 7, "except Exception:"))
                applied.append(f"line {n.lineno}: bare 'except:' -> 'except Exception:'")
        elif (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "open" and n.args
              and n.lineno == n.end_lineno and not protected(n.lineno)):
            mode = n.args[1].value if len(n.args) > 1 and isinstance(n.args[1], ast.Constant) else ""
            if mode in ("", "r", "rt") and "encoding" not in {k.arg for k in n.keywords}:
                at = col(n.end_lineno, n.end_col_offset) - 1
                if lines[n.end_lineno - 1][at:at + 1] == ")":
                    edits.append((n.end_lineno, at, at, ', encoding="utf-8", errors="replace"'))
                    applied.append(f"line {n.lineno}: open() now reads as UTF-8")
    for (func, line), (label, kind, msg) in crashes.items():
        done = False
        if kind in JV_HACK_FIXABLE and not protected(line):
            for fn in ast.walk(tree):
                if isinstance(fn, ast.FunctionDef) and fn.name == func and fn.lineno <= line <= fn.end_lineno:
                    for tr in ast.walk(fn):
                        if isinstance(tr, ast.Try) and tr.body[0].lineno <= line <= tr.body[-1].end_lineno:
                            for h in tr.handlers:
                                if isinstance(h.type, ast.Name) and h.type.id == "OSError" and h.lineno == h.type.lineno:
                                    c0 = col(h.type.lineno, h.type.col_offset)
                                    edits.append((h.type.lineno, c0, c0 + 7, f"(OSError, {kind})"))
                                    applied.append(f"line {h.lineno}: {func}() now also catches {kind} (crash: {label})")
                                    done = True
        if not done:
            manual.append(f"{func}() line {line}: {kind}: {msg}  (needs a human)")
    for kind, line, detail in found:
        if kind not in ("BARE EXCEPT", "OPEN WITHOUT ENCODING"):
            manual.append(f"line {line}: {kind}: {detail}  (needs a human)")
    seen, uniq = set(), []
    for e in edits:
        if (e[0], e[1]) not in seen:
            seen.add((e[0], e[1]))
            uniq.append(e)
    for ln, a, b, rep in sorted(uniq, reverse=True):
        lines[ln - 1] = lines[ln - 1][:a] + rep + lines[ln - 1][b:]
    new = "\n".join(lines)
    try:
        ast.parse(new)
    except SyntaxError:
        return src, [], manual + ["the automatic fix would have broken the syntax, so it was dropped"]
    return new, applied, manual


def jv_hack_yourself(heal=True):
    """'jarvis hack yourself': Jarvis attacks his own code in front of you (split screen), publishes the verdict
    and, if there is something mechanical to fix, sends the fix through 'implement jarvis' (9 gates + backup).
    The attack itself is READ-ONLY: it reads this file and runs harmless commands with hostile input."""
    me = os.path.abspath(__file__)
    try:
        with open(me, "rb") as f:
            raw = f.read()
    except OSError as e:
        jarvis_say(f"I cannot read myself: {safe(str(e))}")
        return
    sha0 = hashlib.sha256(raw).hexdigest()
    src = raw.decode("utf-8", "replace")
    sp = JvSplit()
    sp.start()
    try:
        sp.say("Self-attack started. Nothing will be changed during the attack.", CYAN)
        sp.say(f"[1/5] Reading my own code: {len(raw):,} bytes, sha256 {sha0[:12]}...")
        sp.code("# red team: static pass", JV_SEC_A)
        found, notes = jv_hack_static(src)
        sp.say(f"[2/5] Static analysis: {notes[0] if notes else 'syntax error'}")
        for kind, line, detail in found[:12]:
            sp.say(f"line {line}: {kind} {detail}", JV_SEC_A)
            sp.code(f"static: {kind} @ {line}", JV_SEC_A)
        sp.say(f"      {len(found)} finding(s).", GREEN if not found else JV_SEC_A)
        sp.say("[3/5] Dynamic attack: 32 hostile payloads x every safe command.")
        attacks, crashes, hangs = jv_hack_dynamic(sp)
        sp.say(f"      {attacks} attacks, {len(crashes)} crash(es), {len(hangs)} hang(s).",
               GREEN if not (crashes or hangs) else RED)
        sp.say("[4/5] Running my own security scan.")
        try:
            import ast
            viol = jv_upd_scan(ast.parse(src))
            n_viol = len(viol) if viol is not None else 0
            sp.say(f"      {n_viol} violation(s).", GREEN if n_viol == 0 else RED)
        except (SyntaxError, ValueError, RecursionError) as e:
            n_viol = 1
            sp.say(f"      scan failed: {safe(str(e))}", RED)
        try:
            with open(me, "rb") as f:
                same = hashlib.sha256(f.read()).hexdigest() == sha0
        except OSError:
            same = False
        sp.say(f"[5/5] Integrity: my file is {'unchanged by the attack' if same else 'DIFFERENT after the attack'}.",
               GREEN if same else RED)
    finally:
        sp.stop()
    problems = len(found) + len(crashes) + len(hangs) + n_viol + (0 if same else 1)
    out()
    jv_upd_box("SELF-ATTACK // VERDICT")
    out(f"attacks launched : {attacks}", TEXT)
    out(f"code findings    : {len(found)}", TEXT)
    out(f"crashes / hangs  : {len(crashes)} / {len(hangs)}", TEXT)
    out(f"security scan    : {n_viol} violation(s)", TEXT)
    out(f"file integrity   : {'unchanged' if same else 'CHANGED'}", TEXT)
    out()
    if problems == 0:
        out("[+] NO WEAKNESS FOUND with these attacks.", JV_SEC_G)
        out("    This is a robustness test of my own code, not a certification: it proves nothing about attacks it did not try.", GRAY)
        out()
        return
    out(f"[!] {problems} weakness(es) found.", RED)
    for (func, line), (label, kind, msg) in crashes.items():
        out(f"    crash    : {func}() line {line}: {kind}: {safe(msg)}   <- {safe(label)}", RED)
    for label in hangs:
        out(f"    hang     : {safe(label)}", JV_SEC_A)
    new_src, applied, manual = jv_hack_heal(src, found, crashes)
    for a in applied:
        out(f"    will fix : {safe(a)}", JV_SEC_G)
    for m in manual:
        out(f"    manual   : {safe(m)}", JV_SEC_A)
    out()
    if not applied:
        jarvis_say("I cannot cure these by myself, sir. They are listed above.")
        out()
        return
    if not heal:
        jarvis_say(f"{len(applied)} fix(es) are ready. Run 'jarvis hack yourself' without 'report only' to apply them.")
        out()
        return
    staged = None
    try:
        staged = jv_upd_stage(new_src.encode("utf-8"), "autoheal.py")
        jarvis_say("Auto-heal: sending the cure through the patch gates (backup + automatic rollback).")
        jv_upd_cmd(["jarvis", staged])                  # 9 checks; on any failure nothing is installed
    except (OSError, ValueError) as e:
        out(f"Auto-heal stopped, nothing was changed: {safe(str(e))}", RED)
        out()
    finally:
        if staged:
            jv_upd_discard(staged)


@cmdlet("Jarvis", group="Assistant", usage="""jarvis <request in plain English or Italian>
  jarvis find my games
  jarvis scan this PC for corrupt files
  jarvis select data.win        then:  jarvis tell me about it / what's inside / how much battery
  jarvis status
  jarvis open data.win          opens it read-only (also: open the 2nd one, open undertale, read notes.txt, go up)
  jarvis open chrome            (online only) Chrome mode: then  open email / open canva / open youtube lofi / search <words>
                                open pages in Chrome;  open chrome account <name or number>  picks the account;  close chrome mode  ends it
  jarvis open chrome then gmail on account <name>   several steps in ONE sentence (online only; also: and, poi, e poi, dopo)
  (Windows) Jarvis starts full screen with the globe in the middle, which then rises to the top; when Chrome opens, my window
  shrinks to one half of the screen and Chrome takes the other half
  chrome full screen / chrome side by side   where Chrome opens: maximised, or NEXT to my window (default), never on top of it
  jarvis open deltarune         STARTS the installed game (jarvis open deltarune chapter 2 picks a chapter)
  open deltarune                without 'jarvis': only shows the data.win read-only, never starts the game
  implement jarvis              update myself (see: help implement)       maintenance   health check
  jarvis how many lines / first 20 lines / search for "word" / sha256 / is it corrupt
  jarvis what game is this / how many sprites / list the chunks      (for a GameMaker data.win)
  jarvis which columns / which tables / how many pages / is it 64-bit / what is inside
  jarvis biggest files / find all png files / duplicates / modified today / free disk space
  jarvis be online              sci-fi start-up: globe + 5 nodes, then:  jarvis cerca <topic>  (summary)   jarvis go offline
  jarvis news / news war        (online) latest world stories (ANSA, RaiNews, BBC, Guardian...): parts, photo, summary
  jarvis examples               shows everything I can answer
  jarvis launch <file> [args]   starts a local script or program (see: help launch)
  voice on / voice off          JARVIS speaks only when you ask (needs: pip install pyttsx3; local and offline)
(You can also skip the word 'jarvis': just type the request.)""")
def jarvis_cmd(args):
    """Talk to JARVIS in plain language, e.g.  jarvis find my games"""
    CONTESTO["jv_cmd"] = True            # spoken to Jarvis by name: 'jarvis open <game>' may start a game
    try:
        handled = jarvis_interpret(" ".join(args))
    finally:
        CONTESTO["jv_cmd"] = False
    if not handled:
        jv_didnt_catch(" ".join(args))


# ======================= JARVIS SELF-UPDATE =======================
# The ONLY code that writes to disk, downloads or restarts lives in functions named jv_upd_*.
# Starting a game lives in jv_launch_*.  An update is REFUSED unless every jv_upd_* / jv_launch_*
# function and every JV_UPD_* / JV_LAUNCH_* constant stays identical (compared on the syntax tree).
JV_UPD_MAX_BYTES = 4 * 1024 * 1024
JV_UPD_SECONDS = 10
JV_UPD_PHASES = ("valid source", "checksum", "syntax", "data block", "security scan",
                 "updater intact", "commands kept", "start test", "start speed")
JV_UPD_GUARD = "2.0 hardened"
JV_UPD_PROTECTED = ("jv_upd_", "jv_launch_")
JV_UPD_PROTECTED_CONST = ("JV_UPD_", "JV_LAUNCH_")
JV_UPD_NET = ("urllib", "http", "ftplib", "smtplib", "telnetlib", "requests", "xmlrpc", "ssl", "poplib",
              "imaplib", "paramiko", "websocket", "websockets", "aiohttp", "httpx", "socketserver", "asyncio",
              "cgi", "wsgiref", "selectors", "asyncore", "asynchat", "smtpd", "nntplib", "mailbox")
JV_UPD_DYNAMIC = ("importlib", "pickle", "marshal", "shelve", "pty", "multiprocessing", "webbrowser",
                  "code", "codeop", "builtins", "imp", "zipimport", "pkgutil", "winreg", "_winapi", "nt", "posix",
                  "venv", "ensurepip", "zipapp", "py_compile", "compileall", "dbm", "pdb", "bdb")
JV_UPD_BAD_BUILTINS = ("eval", "exec", "compile", "__import__", "breakpoint")
JV_UPD_BAD_CALLS = (
    "os.remove", "os.unlink", "os.rmdir", "os.removedirs", "os.rename", "os.renames", "os.replace",
    "os.truncate", "os.chmod", "os.chown", "os.mkdir", "os.makedirs", "os.symlink", "os.link", "os.open",
    "os.popen", "os.startfile", "os.kill", "os.killpg", "os.fork", "os.forkpty", "os.putenv", "os.system",
    "shutil.rmtree", "shutil.move", "shutil.copy", "shutil.copy2", "shutil.copyfile", "shutil.copyfileobj",
    "shutil.copytree", "shutil.copymode", "shutil.copystat", "shutil.make_archive", "shutil.unpack_archive",
    "shutil.chown", "sqlite3.connect", "runpy.run_path", "runpy.run_module", "tempfile.mkstemp",
    "tempfile.mkdtemp", "tempfile.NamedTemporaryFile", "tempfile.TemporaryDirectory",
    "tempfile.SpooledTemporaryFile", "os.utime", "os.mkfifo", "os.mknod", "os.lchown", "os.lchmod",
    "os.chflags", "os.lchflags", "os.chroot", "os.setxattr", "os.removexattr", "os.add_dll_directory",
    "os.unsetenv", "os.environ.update", "os.environ.setdefault", "os.environ.pop", "os.environ.clear",
    "logging.FileHandler", "logging.handlers.RotatingFileHandler", "logging.handlers.TimedRotatingFileHandler",
    "logging.handlers.WatchedFileHandler", "fileinput.input", "fileinput.FileInput", "winreg.SetValueEx",
    "winreg.SetValue", "winreg.CreateKey", "winreg.CreateKeyEx", "winreg.DeleteKey", "winreg.DeleteKeyEx",
    "winreg.DeleteValue",
)
# things that are dangerous even when only mentioned (passed around, stored in a variable)
JV_UPD_BAD_SYS = ("sys.modules", "sys._getframe", "sys.settrace", "sys.setprofile", "sys.addaudithook",
                  "sys.meta_path", "sys.path_hooks", "sys.setdlopenflags")
JV_UPD_BAD_DUNDERS = ("__subclasses__", "__globals__", "__builtins__", "__code__", "__closure__",
                      "__getattribute__", "__bases__", "__mro__", "__loader__", "__spec__", "__reduce__",
                      "__reduce_ex__")
# names a getattr()/setattr() must never reach for by string
JV_UPD_BAD_ATTRS = ("remove", "unlink", "rmdir", "rmtree", "system", "popen", "startfile", "kill", "rename",
                    "replace", "chmod", "chown", "truncate", "mkdir", "makedirs", "write_text", "write_bytes",
                    "extractall", "extract", "run", "Popen", "call", "check_call", "check_output", "putenv",
                    "environ", "modules", "eval", "exec", "compile", "__import__", "__builtins__", "__globals__")
# only these variables are handed to the throw-away start test (no tokens, keys or passwords)
JV_UPD_ENV_KEEP = ("PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "TEMP", "TMP", "TMPDIR",
                   "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "HOME", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA",
                   "PROGRAMFILES", "PROGRAMFILES(X86)", "USERNAME", "LANG", "LC_ALL", "TERM", "COLORTERM",
                   "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "OS")
# characters that make source code read differently from what it does ("Trojan Source") or hide in it
JV_UPD_HIDDEN = re.compile("[\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\u00ad\ufff9-\ufffb]")
JV_UPD_ALIAS_ROOTS = ("os", "sys", "shutil", "subprocess", "pathlib", "tempfile", "runpy", "sqlite3", "ctypes",
                      "socket", "io", "codecs", "gzip", "bz2", "lzma", "tarfile", "zipfile", "logging", "fileinput")
JV_UPD_BAD_PREFIX = ("subprocess.", "os.exec", "os.spawn", "os.posix_spawn")
JV_UPD_BAD_METHODS = ("write_text", "write_bytes", "unlink", "rmdir", "mkdir", "touch", "symlink_to",
                      "hardlink_to", "chmod", "rmtree", "removedirs", "makedirs", "extractall", "extract",
                      "rename", "truncate")
JV_UPD_OPENERS = ("open", "io.open", "codecs.open", "gzip.open", "bz2.open", "lzma.open", "tarfile.open",
                  "zipfile.ZipFile", "ZipFile", "os.fdopen", "io.FileIO", "FileIO")
JV_UPD_MODULES = ("os", "shutil", "sys", "subprocess", "builtins")
# (function, thing) pairs that the existing, read-only code is allowed to do.
JV_UPD_ALLOW = (
    ("pc_roots", "ctypes"), ("system_memory", "ctypes"), ("battery_info", "ctypes"), ("jv_uptime", "ctypes"),
    ("battery_info", "subprocess.run"), ("jv_global", "socket"), ("sqlite_open_ro", "sqlite3.connect"),
    ("carica_estensioni", "runpy.run_path"), ("main", "os.system"),
    ("jv_news_get", "urllib"), ("jv_news_get", "ssl"),      # the news reader's one read-only https door (online mode only)
    ("jv_web_get", "urllib"), ("jv_web_get", "ssl"),      # the one read-only https lookup (Wikipedia), online mode only
    ("steam_libraries", "winreg"),           # read-only: reads the Steam folder from the registry
    ("jv_watch_run", "subprocess.run"),      # screen watch: read-only qwinsta / netstat / tasklist
    ("jv_watch_windows", "ctypes"),          # screen watch: reads the titles of the visible windows
    ("jv_watch_box_fallback", "ctypes"),     # screen watch: plain message box if the Tk window cannot open
    ("jv_watch_mail", "smtplib"), ("jv_watch_mail", "ssl"),   # screen watch: optional alert e-mail to YOU (SMTP over TLS)
    ("jv_watch_save", ".makedirs"), ("jv_watch_save", "os.makedirs"), ("jv_watch_save", "open-write"),   # screen watch: its tiny settings file in jarvis_update/
    ("jv_watch_beat", "open-write"),                                    # background guard: heartbeat files in jarvis_update/
    ("jv_watch_guard_install", "open-write"),                           # background guard: the one launcher file in the Startup folder
    ("jv_watch_guard_uninstall", "os.remove"),                          # ...and removing exactly that file again
    ("jv_watch_guard_start", "os.remove"), ("jv_watch_guard_start", "subprocess.Popen"),   # clear the stop flag; start the hidden guard
    ("jv_watch_guard_stop", "open-write"),                              # the stop flag the guard looks for
    ("jv_watch_daemon", "os.remove"),                                   # the guard removes its own stop flag
)
JV_LAUNCH_SKIP = ("unins", "uninstall", "setup", "install", "redist", "vcredist", "dxsetup", "crash", "report",
                  "helper", "updater", "update", "dotnet", "directx", "vc_", "oalinst", "cleanup", "config")
JV_LAUNCH_CHAPTER = r"(?i)(?:chapter|capitolo|cap|ch)[ _.-]?(\d{1,2})(?:[ _-]?(?:windows|win|mac|macos|linux))?"


