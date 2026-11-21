# ---------------- ONLINE mode: the sci-fi boot animation and the research command ----------------
# 'jarvis be online' plays a spinning globe over five big square nodes that light up forward and back,
# then Jarvis says he is online. While online, 'jarvis cerca <topic>' / 'jarvis research <topic>' brings back
# a summary. Everything stays OFFLINE and READ-ONLY: the research uses my own glossary, FAQ, games and
# commands, plus a look at the small text files and file names of the current folder.
JV_NODE_NAMES = ("FILES", "GAMES", "PC", "BRAIN", "SECURE")


def jv_can_utf8():
    """True when the console can draw box and block characters; otherwise the animation uses plain ASCII."""
    try:
        "\u2588\u2592\u250c\u2500\u2510\u2502\u2514\u2518\u252c\u2534\u253c".encode(getattr(sys.stdout, "encoding", None) or "utf-8")
        return True
    except (UnicodeError, LookupError):
        return False


def jv_shade(level, hue="cyan"):
    """Brightness 0..1 -> colour escape. Cyan while booting, green once online; the brightest cells run white-hot."""
    level = max(0.0, min(1.0, level))
    r, g, b = (97, 214, 214) if hue == "cyan" else (22, 220, 60)
    k = 0.16 + 0.84 * level
    w = 0.6 * level ** 4
    return fg(int(r * k + (255 - r) * w), int(g * k + (255 - g) * w), int(b * k + (255 - b) * w))


def jv_paint(cells, hue):
    """[(char, brightness)] -> one coloured line."""
    parts, last = [], None
    for c, lv in cells:
        if c == " ":
            parts.append(" ")
            continue
        col = jv_shade(lv, hue)
        parts.append(c if col == last else col + c)
        last = col
    return "".join(parts) + TEXT


def jv_globe_rows(R, angle, scan=-1):
    """The rotating globe as rows of (char, brightness): continents from a smooth pattern, a lat/long grid, a rim."""
    rows = []
    for ry in range(2 * R + 1):
        y = (R - ry) / R
        lat = math.asin(max(-1.0, min(1.0, y)))
        cells = []
        for c in range(4 * R + 1):
            x = (c - 2 * R) / (2.0 * R)             # characters are about twice as tall as wide
            d = x * x + y * y
            if d > 1.0:
                cells.append((" ", 0.0))
                continue
            z = math.sqrt(1.0 - d)
            lon = math.atan2(x, z) + angle
            f = (math.sin(2.1 * lon + 0.8) * math.cos(1.7 * lat) + 0.6 * math.sin(3.3 * lat - 1.1 * lon)
                 + 0.4 * math.sin(5.2 * lon + lat))
            if f > 0.3:
                ch, lv = "+*#@"[min(3, int(z * 4))], 0.35 + 0.65 * z
            else:
                la, lo = math.degrees(lat), math.degrees(lon) % 360
                if abs((la + 15) % 30 - 15) < 4.0 or abs((lo + 15) % 30 - 15) < 3.2 / max(math.cos(lat), 0.35):
                    ch, lv = ".", 0.25 + 0.45 * z
                elif z < 0.3:
                    ch, lv = ":", 0.5                      # the rim of the globe
                else:
                    ch, lv = " ", 0.0
            if ry == scan and ch != " ":
                lv = min(1.0, lv + 0.4)
            cells.append((ch, lv))
        rows.append(cells)
    return rows


def jv_online_cfg(big, utf):
    """Sizes and characters of the animation: a big layout for roomy terminals, a compact one otherwise."""
    R, NW, NH, GAP = (6, 9, 4, 5) if big else (4, 5, 2, 3)
    cs = [i * (NW + GAP) + NW // 2 for i in range(5)]
    if utf:
        ch = {"v": "\u2502", "h": "\u2500", "tl": "\u250c", "tr": "\u2510", "bl": "\u2514", "br": "\u2518",
              "td": "\u252c", "x": "\u253c", "full": "\u2588", "mid": "\u2592"}
    else:
        ch = {"v": "|", "h": "-", "tl": "+", "tr": "+", "bl": "+", "br": "+", "td": "+", "x": "+", "full": "#", "mid": "%"}
    return {"R": R, "NW": NW, "NH": NH, "GAP": GAP, "CW": 5 * NW + 4 * GAP, "cs": cs, "ch": ch}


def jv_online_frame(cfg, angle, p, phase, linked, hue, tick, scan=-1, flash=1.0):
    """One picture: title, globe, link to the bus, the bus with its pulse at column p, five nodes, their names, status."""
    R, NW, NH, GAP, CW, cs, ch = (cfg[k] for k in ("R", "NW", "NH", "GAP", "CW", "cs", "ch"))
    blank = (" ", 0.0)
    lines = []
    title = "J . A . R . V . I . S"
    lines.append(jv_paint([(c, 0.95 * flash) for c in " " * ((CW - len(title)) // 2) + title], hue))
    left = [blank] * ((CW - (4 * R + 1)) // 2)
    for row in jv_globe_rows(R, angle, scan):
        lines.append(jv_paint(left + row, hue))
    if phase == "lock":
        lv = [flash] * 5
    elif p is None:
        lv = [0.0] * 5
    else:
        lv = [max(0.0, 1.0 - abs(c - p) / (NW + GAP * 0.5)) for c in cs]
    hub = 0.2 if phase == "boot" else flash if phase == "lock" else 0.45 + 0.45 * abs(math.sin(tick * 0.35))
    row = [blank] * CW
    row[cs[2]] = (ch["v"], hub)
    lines.append(jv_paint(row, hue))
    bus = [blank] * CW
    for x in range(cs[0], cs[4] + 1):
        near = 0.18 if p is None else 0.18 + 0.82 * max(0.0, 1.0 - abs(x - p) / (NW * 1.1))
        bus[x] = (ch["h"], flash if phase == "lock" else near)
    for i, key in ((0, "tl"), (1, "td"), (2, "x"), (3, "td"), (4, "tr")):
        bus[cs[i]] = (ch[key], bus[cs[i]][1])
    lines.append(jv_paint(bus, hue))
    row = [blank] * CW
    for i in range(5):
        row[cs[i]] = (ch["v"], max(lv[i], 0.18))
    lines.append(jv_paint(row, hue))
    for r in range(NH):
        cells = []
        for i in range(5):
            if i:
                cells += [blank] * GAP
            if lv[i] >= 0.7:
                cells += [(ch["full"], 0.55 + 0.45 * lv[i])] * NW
            elif lv[i] >= 0.3:
                cells += [(ch["mid"], 0.35 + 0.5 * lv[i])] * NW
            else:
                if r == 0:
                    s = ch["tl"] + ch["h"] * (NW - 2) + ch["tr"]
                elif r == NH - 1:
                    s = ch["bl"] + ch["h"] * (NW - 2) + ch["br"]
                else:
                    s = ch["v"] + " " * (NW - 2) + ch["v"]
                cells += [(c, 0.14) for c in s]
        lines.append(jv_paint(cells, hue))
    cells = []
    for i in range(5):
        if i:
            cells += [blank] * GAP
        cells += [(c, max(lv[i], 0.3)) for c in JV_NODE_NAMES[i].center(NW)[:NW]]
    lines.append(jv_paint(cells, hue))
    if phase == "boot":
        st = "INITIALIZING CORE" + "." * (tick // 3 % 4)
    elif phase == "sweep":
        st = f"LINKING NODES  {len(linked)}/5"
    else:
        st = "ALL NODES LINKED  -  ONLINE"
    st = st.ljust(28)
    lines.append(jv_paint([(c, 0.75) for c in " " * ((CW - len(st)) // 2) + st], hue))
    return lines


def jv_online_animation():
    """Globe turning, five nodes lighting up forward and back, then everything locks green. Needs a real terminal;
    when the output is redirected only the final picture is printed."""
    utf = jv_can_utf8()
    try:
        cols, rows = shutil.get_terminal_size((100, 30))
    except (OSError, ValueError):
        cols, rows = 100, 30
    cfg = jv_online_cfg(cols >= 72 and rows >= 26, utf)
    cs, R, NW = cfg["cs"], cfg["R"], cfg["NW"]
    linked = set()
    if not sys.stdout.isatty():
        sys.stdout.write("\n".join(jv_online_frame(cfg, 0.6, None, "lock", linked, "green", 0)) + "\n")
        return
    state = {"first": True, "tick": 0, "angle": 0.0}

    def draw(phase, p, hue, spin, flash=1.0, scan=True):
        lines = jv_online_frame(cfg, state["angle"], p, phase, linked, hue, state["tick"],
                                scan=(state["tick"] % (2 * R + 1)) if scan else -1, flash=flash)
        if not state["first"]:
            sys.stdout.write("\x1b[%dA" % len(lines))
        state["first"] = False
        sys.stdout.write("".join(l + "\x1b[K\n" for l in lines))
        sys.stdout.flush()
        state["angle"] += spin
        state["tick"] += 1
        time.sleep(0.05)

    sys.stdout.write("\x1b[?25l")
    try:
        try:
            for _ in range(14):                                   # 1) core boots, globe starts turning
                draw("boot", None, "cyan", 0.18)
            steps = 12
            for k in range(4):                                    # 2) the pulse runs forward, back, forward, back
                a, b = (cs[0], cs[4]) if k % 2 == 0 else (cs[4], cs[0])
                for i in range(steps + 1):
                    p = a + (b - a) * i / steps
                    for j, c in enumerate(cs):
                        if abs(c - p) <= NW / 2:
                            linked.add(j)
                    draw("sweep", p, "cyan", 0.22)
            for i in range(10):                                   # 3) everything locks on, the globe turns green
                draw("lock", None, "green", 0.12, flash=1.0 if i % 4 < 2 else 0.78)
        except KeyboardInterrupt:
            pass
        draw("lock", None, "green", 0.0, scan=False)
    finally:
        sys.stdout.write("\x1b[?25h" + TEXT)
        sys.stdout.flush()


def jv_online_kind(t):
    """'on' for 'be online', 'go online', 'vai online', 'connettiti'...; 'off' for 'go offline'...; 'ask' for 'are you
    online'; None otherwise (so 'open online.txt' or 'what is online banking' are left to the other readers)."""
    s = re.sub(r"[^a-z\u00e0-\u00ff0-9' ]+", " ", t.lower())
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"^(?:(?:please|pls|per favore|ora|now|adesso|can you|could you|puoi|potresti)\s+)+", "", s)
    s = re.sub(r"\s+(?:now|ora|adesso|please|pls|per favore|sir|signore)$", "", s)
    pre = r"(?:(?:be|go|get|come|sii|vai|vieni|mettiti|torna|stay|resta|rimani)\s+)?"
    if re.fullmatch(pre + r"on ?line", s) or re.fullmatch(
            r"(?:connect|connettiti|collegati|attivati|boot up|boot|power up|initiali[sz]e|inizializzati|accenditi|go live|vai live)", s):
        return "on"
    if re.fullmatch(pre + r"off ?line", s) or re.fullmatch(
            r"(?:disconnect|disconnettiti|scollegati|spegniti|power down|go dark|stand ?by)", s):
        return "off"
    if re.fullmatch(r"(?:are you|r u|sei|sei ancora|are you still)\s+(?:on ?line|connected|connesso|in linea)", s):
        return "ask"
    return None


def jv_online_cmd(orig, t):
    """Handles 'jarvis be online', 'jarvis go offline', 'jarvis are you online'. Only when Jarvis is named."""
    if not CONTESTO.get("jv_named"):
        return False
    kind = jv_online_kind(t)
    if kind is None:
        return False
    CONTESTO["jv_nostore"] = True                   # 'again' must not replay the whole animation
    if kind == "ask":
        if CONTESTO.get("jv_online"):
            jarvis_say("Online, sir. All five nodes are linked. Say 'jarvis cerca <topic>' for a research summary.")
        else:
            jarvis_say("Not online yet, sir. Say 'jarvis be online' and I'll bring the nodes up.")
        return True
    if kind == "off":
        if CONTESTO.get("jv_online"):
            CONTESTO["jv_online"] = False
            jarvis_say("Going offline, sir. Nodes released. Say 'jarvis be online' whenever you need me linked again.")
        else:
            jarvis_say("I'm already offline, sir.")
        return True
    if CONTESTO.get("jv_online"):
        jarvis_say("Already online, sir. Let me show you the link once more.")
    else:
        jarvis_say("Initialising, sir. Bringing the nodes up...")
    out()
    jv_online_animation()
    CONTESTO["jv_online"] = True
    out()
    out("  [ JARVIS ONLINE ]", GREEN)
    jarvis_say("I'm online, sir. All five nodes are linked: files, games, PC, brain and security.")
    jarvis_say("Ask me anything with 'jarvis search <topic>' and I'll look it up on the web, or say 'jarvis news' for the latest stories. "
               "Still read-only: I never change your files.")
    return True


# ---- research ----
JV_RS_EXTS = "txt|csv|tsv|json|py|md|log|ini|cfg|xml|png|jpg|jpeg|gif|bmp|zip|rar|7z|pdf|exe|dll|win|db|sqlite|bat|mp3|wav|ogg"
JV_RS_FILE_WORDS = re.compile(r"\b(?:files?|folders?|directory|directories|cartella|cartelle|lines?|righe?|riga|rows?|chunks?|"
                              r"sprites?|rooms?|sounds?|hash|duplicat\w+|corrupt\w*|corrott\w*|selected|selezionat\w+|here|qui)\b")
JV_RS_CONN = r"(?:\s+(?:about|on|for|su|sul|sulla|sullo|sui|sugli|di|riguardo a|riguardo|a proposito di|per))*"
JV_RS_STRONG = (r"(?:ricercami|ricerca|research|look ?up|find out|find (?:some )?info(?:rmation)?|informati|approfondisci|"
                r"dimmi tutto|tell me everything|cerca(?:mi)? (?:info|informazioni|notizie)|search (?:online|the web|the internet)|"
                r"cerca (?:online|su internet|sul web|in rete))")
JV_RS_WEAK = r"(?:cercami|cerca|cercare|search for|search|look for)"
JV_IT_EN = {"memoria": "memory", "giochi": "games", "gioco": "game", "cartella": "folder", "disco": "disk",
            "processore": "cpu", "sicurezza": "security", "rete": "network", "scheda": "card", "video": "video",
            "salvataggio": "save", "salvataggi": "saves", "aggiornamento": "update", "virus": "virus",
            "estensione": "extension", "programma": "program", "archivio": "archive", "immagine": "image"}


def jv_rs_parse(t, sel, online=False):
    """'cerca ram' / 'research sha256' -> (topic, strong) or None when it is really a file question
    (quotes, a file name or extension, 'in it', a selected file with a plain 'search for')."""
    s = re.sub(r"\s+", " ", t.lower().replace("\u2019", "'")).strip(" ,;:!?.")
    s = re.sub(r"^(?:(?:please|pls|per favore|ora|now|adesso|puoi|potresti|can you|could you|will you|mi)\s+)+", "", s)
    m = re.match(r"^" + JV_RS_STRONG + JV_RS_CONN + r"\s+(.+)$", s)
    strong = bool(m)
    if not m:
        m = re.match(r"^" + JV_RS_WEAK + JV_RS_CONN + r"\s+(.+)$", s)
    if not m or re.search(r"[\"\u201c\u201d`]", t):
        return None
    prefix = s[:m.start(1)]
    with_on = bool(re.search(r"\b(?:su|sul|sulla|sullo|sui|sugli|about|on|riguardo|proposito)\b", prefix))
    q = re.sub(r"\s+(?:please|pls|per favore|grazie|thanks|for me|per me)$", "", m.group(1)).strip(" ,;:!?.'\"")
    if not q:
        return None
    if JV_RS_FILE_WORDS.search(q) or re.search(r"\.(?:" + JV_RS_EXTS + r")\b", q):
        return None
    if re.match(r"^(?:the (?:word|text|string|phrase)|la parola|il testo|la stringa|la frase)\b", q):
        return None
    if re.search(r"\b(?:in|inside|dentro|nel|nello|nella|within)\s+(?:it|this|that|questo|questa|quello|quella|lo|la|il|the|my|mio|mia)\b", q):
        return None
    if re.fullmatch(r"(?:it|this|that|lo|la|questo|questa|quello|quella)", q):
        return None
    if sel and not strong and not with_on and not online:
        return None                                  # a file is selected: a plain 'search for x' means search INSIDE it
    return q, strong


def jv_web_get(lang, path, params=None):
    """The ONLY place that touches the internet: a read-only https GET to Wikipedia (en or it), only while Jarvis
    is online, sending nothing but the search words. Returns the decoded JSON; raises OSError/ValueError on trouble."""
    import ssl
    import urllib.parse
    import urllib.request
    if lang not in ("en", "it"):
        raise ValueError("unsupported language")
    url = f"https://{lang}.wikipedia.org{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "JARVIS-research/1.0 (read-only lookup)",
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=6, context=ssl.create_default_context()) as r:
        return json.loads(r.read(300000).decode("utf-8", "replace"))


def jv_web_summary(q, prefer_it=False):
    """Wikipedia summary of a topic: ({'title','text','url'}, None) or (None, reason)."""
    problem = None
    for lang in (("it", "en") if prefer_it else ("en", "it")):
        try:
            hit = jv_web_get(lang, "/w/api.php", {"action": "opensearch", "search": q, "limit": 1,
                                                  "format": "json", "redirects": "resolve"})
            if not hit[1]:
                continue
            title = hit[1][0]
            d = jv_web_get(lang, "/api/rest_v1/page/summary/" + title.replace(" ", "_").replace("/", "%2F"))
            text = re.sub(r"\s+", " ", d.get("extract") or "").strip()
            if text:
                url = ((d.get("content_urls") or {}).get("desktop") or {}).get("page") or hit[3][0]
                return {"title": safe(d.get("title") or title), "text": safe(text), "url": safe(url)}, None
        except (OSError, ValueError, KeyError, IndexError, TypeError) as e:
            problem = type(e).__name__
    return None, problem


def jv_rs_first_sentence(text, limit=170):
    m = re.match(r"(.+?[.!?])(?:\s|$)", text.strip())
    s = m.group(1) if m else text.strip()
    return s if len(s) <= limit else s[:limit - 3].rstrip() + "..."


def jv_rs_wrap(text, width, indent):
    lines, cur = [], ""
    for w in str(text).split():
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return [" " * indent + l for l in lines] or [""]


def jv_rs_files(words, root, seconds=2.0):
    """A read-only look around a folder (two levels deep, a few thousand entries at most): file and folder names that
    contain a search word, and the best lines of small text files. Returns (name hits, content hits)."""
    end = time.time() + seconds
    me = os.path.abspath(__file__)
    names, content, seen = [], [], 0
    stack = [(root, 0)]
    while stack and time.time() < end and seen < 3000:
        d, depth = stack.pop()
        try:
            entries = sorted(os.scandir(d), key=lambda e: e.name.lower())
        except OSError:
            continue
        for e in entries:
            seen += 1
            low = e.name.lower()
            try:
                if e.is_dir(follow_symlinks=False):
                    if any(w in low for w in words) and len(names) < 6:
                        names.append((os.path.relpath(e.path, root), "folder"))
                    if depth < 2 and not low.startswith(".") and low != "jarvis_update" and not skip_dir(e.path):
                        stack.append((e.path, depth + 1))
                elif e.is_file(follow_symlinks=False):
                    if os.path.abspath(e.path) == me:
                        continue
                    if any(w in low for w in words) and len(names) < 6:
                        names.append((os.path.relpath(e.path, root), human(e.stat().st_size)))
                    if len(content) < 6 and os.path.splitext(low)[1] in TEXT_EXT and e.stat().st_size <= 262144:
                        with open(e.path, "rb") as f:
                            body = f.read(262144).decode("utf-8", "replace")
                        best = []
                        for n, line in enumerate(body.splitlines()[:4000], 1):
                            ll = line.lower()
                            hit = sum(1 for w in words if w in ll)
                            if hit:
                                best.append((hit, -n, n, line.strip()))
                        best.sort(reverse=True)
                        if best and (len(words) < 2 or best[0][0] >= 2 or len(best) >= 2):
                            content.append((os.path.relpath(e.path, root), [(n, safe(x[:150])) for _, _, n, x in best[:2]]))
            except OSError:
                continue
    return names, content


def jv_research_run(query, prefer_it=False):
    """Look the topic up in everything I know and in the current folder, then print a summary."""
    q = re.sub(r"\s+", " ", query).strip(" ,.;:!?\"'")
    qkey = q.lower().replace("'", "")
    qkey = " ".join(JV_IT_EN.get(w, w) for w in qkey.split())
    words = [w for w in re.findall(r"[a-z0-9.+#]+", qkey) if w not in JV_STOP and len(w) > 1]
    terms = set(jv_terms(qkey))
    found = []                                     # (label, text)

    for g, txt in JV_GAMES_KB.items():             # games
        if re.search(r"(?<![\w])" + re.escape(g) + r"(?![\w])", qkey):
            found.append((g.title(), txt + f" Say 'jarvis open {g}' to start it."))
    scored = []                                    # glossary
    for keys, txt in JV_KB:
        sc = 0.0
        for k in keys:
            if re.search(r"(?<![\w.])" + re.escape(k) + r"(?![\w])", qkey):
                sc = max(sc, 3 + len(k) / 10)
        ov = len(terms & set(jv_terms(txt)))
        if sc == 0 and ov < 2:
            continue
        scored.append((sc + 0.6 * ov, keys[0], txt))
    scored.sort(key=lambda x: -x[0])
    for sc, k, txt in scored[:3]:
        found.append((k.upper() if len(k) <= 5 else k.capitalize(), txt))
    for w in words:                                # commands
        fn = CMDLETS.get(w) if len(w) >= 3 else None
        if fn is not None:
            found.append(("Command " + fn.nome, f"{describe(fn.nome)}."))
            break
    try:
        c = jv_compare(qkey)                       # 'ssd vs hdd'
    except Exception:
        c = None
    if c:
        found.append(("Comparison", c))
    try:
        hit = jv_faq_find(qkey, False)
    except Exception:
        hit = None
    if hit:
        found.append(("Q: " + hit[1][1], hit[1][2]))
    seen_txt, uniq = set(), []
    for lab, txt in found:                         # no entry twice
        if txt not in seen_txt:
            seen_txt.add(txt)
            uniq.append((lab, txt))
    found = uniq[:5]

    web, web_problem = None, None
    if not CONTESTO.get("jv_nolog"):               # (the maintenance test never goes to the internet)
        web, web_problem = jv_web_summary(q, prefer_it)
    root = os.getcwd()
    fwords = [w for w in words if len(w) >= 3] or words
    names, content = jv_rs_files(fwords, root) if fwords else ([], [])
    try:
        width = max(50, min(100, shutil.get_terminal_size((100, 30)).columns - 8))
    except (OSError, ValueError):
        width = 90

    if not found and not names and not content and not web:
        jarvis_say(f"I searched my glossary, FAQ, games, commands and the files in this folder for '{safe(q)}', sir, "
                   "and found nothing. I only know what I was taught: try a more specific word, or say 'jarvis examples'.")
        if not CONTESTO.get("jv_nolog"):
            jv_upd_log_miss("research: " + q)
        return
    jarvis_say(f"Research on '{safe(q)}' done, sir. Here is the summary:")
    if web:
        out(f"  [{web['title']} - Wikipedia]", GREEN)
        for l in jv_rs_wrap(" ".join(re.findall(r"[^.!?]+[.!?]+(?:\s|$)", web["text"])[:3]) or web["text"][:500], width, 4):
            out(l, CYAN)
        out("    " + web["url"], GRAY)
    elif web_problem:
        out("  (I could not reach the web just now, so this is only what I know offline.)", GRAY)
    for lab, txt in found:
        out(f"  [{safe(lab)}]", GREEN)
        for l in jv_rs_wrap(txt, width, 4):
            out(l, CYAN)
    if names or content:
        out(f"  [In {safe(os.path.basename(root) or root)}]", GREEN)
        for rel, info in names:
            out(f"    name match: {safe(rel)}  ({info})", CYAN)
        for rel, hits in content:
            for n, line in hits:
                out(f"    {safe(rel)}:{n}  {line}", CYAN)
    parts = []
    if web:
        parts.append(jv_rs_first_sentence(web["text"]))
    if found:
        parts.append(jv_rs_first_sentence(found[0][1]) if not web else "Related: " + ", ".join(safe(l) for l, _ in found[:3]) + ".")
        if len(found) > 1 and not web:
            parts.append("Related: " + ", ".join(safe(l) for l, _ in found[1:4]) + ".")
    nf = len({r for r, _ in names} | {r for r, _ in content})
    if nf:
        parts.append(f"{nf} file(s) here mention it.")
    out()
    jarvis_say("In short, sir: " + " ".join(parts))
    out("  (sources: " + ("Wikipedia, " if web else "") + "my glossary, FAQ, games and commands, plus names and small text "
        "files of the current folder; nothing was changed)", GRAY)


def jv_research_cmd(orig, t, sel):
    """'jarvis cerca ...' / 'jarvis research ...': a research summary, available while online."""
    if not CONTESTO.get("jv_named"):
        return False
    if re.fullmatch(r"(?:please |per favore )?(?:cerca|search|research|ricerca|look up)", t.strip().lower()):
        jarvis_say("Search for what, sir? Say 'jarvis cerca <topic>', for example 'jarvis cerca sha256'.")
        return True
    p = jv_rs_parse(t, sel, bool(CONTESTO.get("jv_online")))
    if p is None:
        return False
    if not CONTESTO.get("jv_online"):
        jarvis_say("I'm not online yet, sir. Say 'jarvis be online' first, then ask me again and I'll research it.")
        CONTESTO["jv_nostore"] = True
        return True
    try:
        jv_research_run(p[0], bool(re.match(r"^(?:\w+\s+){0,2}(?:cerca\w*|ricerc\w*|informati|dimmi)\b", t.strip().lower())))
    except KeyboardInterrupt:
        out()
        jarvis_say("Stopped, sir.")
    return True


