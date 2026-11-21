# ---------------- NEWS: 'jarvis news' (online mode) ----------------
# Reads the RSS feeds of a short list of established news desks (ANSA, RaiNews, Il Post, Geopop, BBC, Al Jazeera),
# keeps only what was published in the last 48 hours, groups the same story told by several desks, and prints it in
# parts: WAR, PROTESTS, then the regions of the world. Each story shows its photo (real colours, needs: pip install pillow)
# with the summary underneath. 'Verified' here means: published by these desks, recent, and marked when two or
# more of them carry the same story. The only network door is jv_news_get (https, read-only, online mode only).
JV_NEWS_FEEDS = (
    ("ANSA", "https://www.ansa.it/sito/notizie/topnews/topnews_rss.xml"),
    ("ANSA", "https://www.ansa.it/sito/ansait_rss.xml"),
    ("RaiNews", "https://www.rainews.it/rss/ultimora"),
    ("RaiNews", "https://www.rainews.it/rss/tutti"),
    ("Il Post", "https://www.ilpost.it/feed/"),
    ("Geopop", "https://www.geopop.it/feed/"),
    ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("The Guardian", "https://www.theguardian.com/world/rss"),
    ("NYT World", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"),
    ("DW", "https://rss.dw.com/xml/rss-en-world"),
    ("France 24", "https://www.france24.com/en/rss"),
    ("NPR World", "https://feeds.npr.org/1004/rss.xml"),
)
JV_NEWS_URLS = frozenset(u for _, u in JV_NEWS_FEEDS)
JV_NEWS_MAX_AGE_H = 48
JV_NEWS_WAR = re.compile(
    r"\b(?:war|wars|warfare|guerr\w*|conflitt\w*|bombard\w*|missil\w*|militar\w*|ucrain\w*|ukrain\w*|gaza|israel\w*|"
    r"hamas|hezbollah|russia|russo|russa|russi|russe|putin|zelensk\w*|drones?|dron[ei]|ceasefire|cessate il fuoco|tregua|"
    r"truppe|troops|soldat\w*|nato|libano|lebanon|iran\w*|sudan|sirian\w*|syria\w*|houthi|airstrikes?|offensiv\w*|"
    r"invasion\w*|invasione|esercit\w*|army|frontline|fronte)\b", re.I)
JV_NEWS_PROTEST = re.compile(
    r"\b(?:protest\w*|manifest\w*|corteo|cortei|sciopero|scioperi|general strike|walkout|rivolt\w*|dimostrant\w*|"
    r"demonstrat\w*|riot\w*|picchett\w*|presidio|sit-in|scontri|disordini|unrest)\b", re.I)
JV_NEWS_STOP = set("""the a an of in on at to for and or but is are was were be by with from as that this it its after before over
under into about new says say said più meno della delle dello degli dell nella nelle nello negli sono stato stata stati
state che per con una uno gli non dopo prima come anche tra fra sul sulla sulle sui dal dalla dalle dai cosa dove quando
ancora ultime ultima oggi ieri video foto live""".split())


def jv_news_get(url, kind="feed", limit=1500000):
    """The only network door of the news reader: a read-only https GET. Feeds must be one of my listed sources;
    pictures may come from any named https site (no IP addresses), only images, capped in size. Redirects must stay https."""
    import ssl
    import urllib.parse
    import urllib.request
    p = urllib.parse.urlparse(url)
    host = (p.hostname or "").lower()
    if p.scheme != "https" or not host or host == "localhost" or re.fullmatch(r"[\d.]+|[0-9a-f:]+", host):
        raise ValueError("only https addresses of named sites")
    if kind == "feed" and url not in JV_NEWS_URLS:
        raise ValueError("not one of my news sources")

    class Strict(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            q = urllib.parse.urlparse(newurl)
            h = (q.hostname or "").lower()
            if q.scheme != "https" or not h or h == "localhost" or re.fullmatch(r"[\d.]+|[0-9a-f:]+", h):
                raise ValueError("redirect to a non-https or numeric address refused")
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    opener = urllib.request.build_opener(Strict, urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; JARVIS-news/1.0; read-only)",
        "Accept": "application/rss+xml, application/xml, text/xml, image/*;q=0.8, */*;q=0.5"})
    with opener.open(req, timeout=7) as r:
        if kind == "image" and not (r.headers.get("Content-Type") or "").lower().startswith("image/"):
            raise ValueError("not an image")
        data = r.read(limit + 1)
    if len(data) > limit:
        raise ValueError("too big")
    return data


def jv_news_parse_feed(raw, src):
    """RSS 2.0 bytes -> [{'title','link','desc','ts','src','img'}]; refuses XML that declares entities."""
    import html
    import xml.etree.ElementTree as ET
    from datetime import timezone
    from email.utils import parsedate_to_datetime
    if re.search(rb"<!ENTITY", raw[:50000], re.I):
        raise ValueError("feed declares XML entities")
    root = ET.fromstring(raw)

    def clean(x):
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(x or ""))).strip()
    items = []
    for it in list(root.iter("item"))[:30]:
        fields, img = {}, None
        for el in it.iter():
            tag = el.tag.rsplit("}", 1)[-1] if isinstance(el.tag, str) else ""
            if tag in ("title", "link", "description", "encoded", "pubDate", "date") and tag not in fields:
                fields[tag] = el.text or ""
            if tag in ("content", "thumbnail", "enclosure") and img is None:
                u, ty = el.get("url") or "", (el.get("type") or el.get("medium") or "image").lower()
                if u.startswith("https://") and ("image" in ty or tag == "thumbnail"):
                    img = u
        title = clean(fields.get("title"))
        if not title:
            continue
        if img is None:
            m = re.search(r"""<img[^>]+src=["'](https://[^"']+)""", html.unescape(fields.get("description", "") + fields.get("encoded", "")))
            img = m.group(1) if m else None
        desc = max(clean(fields.get("description")), clean(fields.get("encoded")), key=len)
        if desc.lower().startswith(title.lower()):
            desc = desc[len(title):].strip(" -:.")
        ts = None
        stamp = (fields.get("pubDate") or fields.get("date") or "").strip()
        try:
            ts = parsedate_to_datetime(stamp)
        except (TypeError, ValueError):
            try:
                ts = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            except ValueError:
                ts = None
        if ts is not None and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        items.append({"title": safe(title), "link": safe((fields.get("link") or "").strip()), "desc": safe(desc),
                      "ts": ts, "src": src, "img": img})
    return items


def jv_news_collect():
    """Read every source in parallel. Returns (items, names reached, names tried)."""
    from concurrent.futures import ThreadPoolExecutor

    def one(feed):
        name, url = feed
        try:
            return name, jv_news_parse_feed(jv_news_get(url, "feed"), name)
        except Exception:
            return name, None
    items, reached = [], set()
    with ThreadPoolExecutor(max_workers=len(JV_NEWS_FEEDS)) as ex:
        for name, got in ex.map(one, JV_NEWS_FEEDS):
            if got is not None:
                reached.add(name)
                items.extend(got)
    return items, reached, {n for n, _ in JV_NEWS_FEEDS}


def jv_news_tokens(title):
    return {w for w in re.findall(r"[a-z\u00e0-\u00ff0-9]{4,}", title.lower()) if w not in JV_NEWS_STOP}


def jv_news_group(items, now):
    """Keep recent items, merge the same story told by several desks: [{'best','srcs','ts'}], newest first."""
    from datetime import timezone
    fresh = [i for i in items if i["ts"] is not None and 0 <= (now - i["ts"]).total_seconds() <= JV_NEWS_MAX_AGE_H * 3600]
    fresh.sort(key=lambda i: i["ts"], reverse=True)
    groups = []
    for i in fresh:
        tk = jv_news_tokens(i["title"])
        for g in groups:
            common = len(tk & g["tk"])
            if common >= 3 and common >= 0.5 * min(len(tk), len(g["tk"])):
                g["items"].append(i)
                g["tk"] |= tk
                break
        else:
            groups.append({"items": [i], "tk": set(tk)})
    out_ = []
    for g in groups:
        best = sorted(g["items"], key=lambda i: (bool(i["img"]), len(i["desc"]), i["ts"]), reverse=True)[0]
        out_.append({"best": best, "srcs": sorted({i["src"] for i in g["items"]}), "ts": max(i["ts"] for i in g["items"]),
                     "items": g["items"]})
    return out_


def jv_news_age(ts, now):
    m = int((now - ts).total_seconds() // 60)
    return "just now" if m < 2 else f"{m} min ago" if m < 90 else f"{m // 60} h ago"


def jv_news_photo(raw, width=64, maxrows=20):
    """A real photo in the terminal: every character is two pixels (upper half block, foreground over background,
    24-bit colour). Needs Pillow and a UTF-8 console; returns None otherwise."""
    if not jv_can_utf8():
        return None
    try:
        from PIL import Image
    except ImportError:
        return None
    import io
    try:
        Image.MAX_IMAGE_PIXELS = 40000000
        im = Image.open(io.BytesIO(raw))
        im.draft("RGB", (width * 4, width * 4))
        im = im.convert("RGB")
        w, h = im.size
        rows = max(4, min(maxrows, int(width * h / max(w, 1) / 2)))
        im = im.resize((width, rows * 2))
        lines = []
        for y in range(rows):
            parts = []
            for x in range(width):
                t, u = im.getpixel((x, 2 * y)), im.getpixel((x, 2 * y + 1))
                parts.append(fg(*t) + bg(*u) + "\u2580")
            lines.append("".join(parts) + TEXT + BG)
        return lines
    except Exception:
        return None


JV_NEWS_REGIONS = (
    ("MIDDLE EAST", re.compile(r"\b(?:israel\w*|gaza|palestin\w*|iran\w*|iraq\w*|syria\w*|sirian\w*|lebanon|libano|yemen|saudi|turkey|turchia|"
                              r"egypt|egitto|qatar|emirat\w*|hamas|hezbollah|medio oriente|middle east|jordan)\b", re.I)),
    ("EUROPE", re.compile(r"\b(?:europe\w*|europa|brussels|bruxelles|german\w*|germania|france|francia|french|britain|british|london|londra|"
                         r"italy|italia|italian\w*|spain|spagna|poland|polonia|paris|parigi|berlin\w*|meloni|macron|scholz|merz|greece|grecia|"
                         r"vatican\w*|papa|pope|ukrain\w*|ucrain\w*)\b", re.I)),
    ("AMERICAS", re.compile(r"\b(?:trump|biden|harris|washington|white house|casa bianca|united states|stati uniti|american\w*|canada|canadian\w*|"
                           r"mexic\w*|messico|brazil\w*|brasile|argentin\w*|venezuela\w*|colombia\w*|chile\w*|cile|cuba\w*|peru|congress\w*)\b", re.I)),
    ("ASIA AND PACIFIC", re.compile(r"\b(?:china|cina|chinese|cinese|japan\w*|giappone|india\w*|korea\w*|taiwan\w*|pakistan\w*|afghan\w*|"
                                   r"indonesia\w*|vietnam\w*|thailand\w*|philippin\w*|filippine|australia\w*|beijing|pechino|myanmar|bangladesh|nepal)\b", re.I)),
    ("AFRICA", re.compile(r"\b(?:africa\w*|nigeria\w*|kenya\w*|ethiopia\w*|congo|somalia|mali|niger|ghana|morocco|marocco|algeria|libya|libia|"
                         r"tunisia|uganda|zimbabwe|mozambique|sahel)\b", re.I)),
    ("ECONOMY", re.compile(r"\b(?:econom\w*|market\w*|borsa|inflation|inflazione|bank\w*|banca|stocks?|trade|dazi|tariff\w*|oil|petrolio|gdp|pil|"
                          r"euro|dollar\w*|interest rates?|tassi|recession\w*|business|aziend\w*|company|companies)\b", re.I)),
    ("SCIENCE AND TECH", re.compile(r"\b(?:scien\w*|space|spazio|nasa|astronom\w*|planet\w*|exoplan\w*|esopian\w*|climate|clima|artificial intelligence|"
                                   r"intelligenza artificiale|tech\w*|robot\w*|vaccin\w*|medic\w*|health|salute|ricerc\w*|study|studio|researchers?|"
                                   r"archaeolog\w*|fossil\w*|volcan\w*|eruption|earthquake|terremoto)\b", re.I)),
)


def jv_news_region(text):
    for label, rx in JV_NEWS_REGIONS:
        if rx.search(text):
            return label
    return "ELSEWHERE IN THE WORLD"


def jv_news_topic_filter(topic):
    """'war', 'guerra', 'protests'... -> a regex; any other topic -> its words."""
    tl = topic.lower()
    if re.search(r"\b(?:war|guerra|guerre|conflict\w*|conflitt\w*)\b", tl):
        return JV_NEWS_WAR
    if re.search(r"\b(?:protest\w*|manifest\w*|strike|sciopero|scioperi)\b", tl):
        return JV_NEWS_PROTEST
    words = [w for w in re.findall(r"[a-z\u00e0-\u00ff0-9]{3,}", tl) if w not in JV_NEWS_STOP]
    return re.compile(r"\b(?:" + "|".join(re.escape(w) for w in words) + r")", re.I) if words else None


def jv_news_show(items, topic, reached, tried, with_images=True, now=None):
    """Sort the groups into WAR / PROTESTS / OTHER (or one block for a topic) and print each story in turn."""
    from datetime import timezone
    now = now or datetime.now(timezone.utc)
    if not reached:
        jarvis_say("I couldn't reach any news desk, sir: no internet, or the sites are blocking me. Try again in a moment.")
        return
    groups = jv_news_group(items, now)
    hit = jv_news_topic_filter(topic) if topic else None
    if topic and hit is None:
        jarvis_say("Which topic, sir? Say 'jarvis news', 'jarvis news war' or 'jarvis news protests'.")
        return
    if hit is not None:
        groups = [g for g in groups if hit.search(g["best"]["title"] + " " + g["best"]["desc"])]
    key = lambda g: (-len(g["srcs"]), -g["ts"].timestamp())
    if topic:
        parts = [(topic.upper()[:24], sorted(groups, key=key)[:10])]
    else:
        txt = lambda g: g["best"]["title"] + " " + g["best"]["desc"]
        prot = [g for g in groups if JV_NEWS_PROTEST.search(txt(g))]
        rest = [g for g in groups if g not in prot]
        war = [g for g in rest if JV_NEWS_WAR.search(txt(g))]
        rest = [g for g in rest if g not in war]
        parts = [("WAR AND CONFLICTS", sorted(war, key=key)[:4]), ("PROTESTS", sorted(prot, key=key)[:3])]
        by = {}
        for g in rest:
            by.setdefault(jv_news_region(txt(g)), []).append(g)
        for label in [r for r, _ in JV_NEWS_REGIONS] + ["ELSEWHERE IN THE WORLD"]:
            if by.get(label):
                parts.append((label, sorted(by[label], key=key)[:3]))
    chosen = [g for _, gs in parts for g in gs]
    if not chosen:
        jarvis_say("Nothing new from the desks I follow" + (f" about '{safe(topic)}'" if topic else "") +
                   f" in the last {JV_NEWS_MAX_AGE_H} hours, sir.")
        return
    pics = {}
    if with_images:
        from concurrent.futures import ThreadPoolExecutor

        def grab(g):
            u = g["best"]["img"]
            if not u:
                return None
            try:
                return jv_news_photo(jv_news_get(u, "image", 2000000), pics_width)
            except Exception:
                return None
        try:
            pics_width = max(30, min(72, shutil.get_terminal_size((100, 30)).columns - 8))
        except (OSError, ValueError):
            pics_width = 56
        with ThreadPoolExecutor(max_workers=6) as ex:
            for g, art in zip(chosen, ex.map(grab, chosen)):
                pics[id(g)] = art
    try:
        width = max(50, min(100, shutil.get_terminal_size((100, 30)).columns - 8))
    except (OSError, ValueError):
        width = 90
    tick = "\u2714" if jv_can_utf8() else "OK"
    jarvis_say(f"Here is the latest, sir: {len(chosen)} stories from {len(reached)} of {len(tried)} desks "
               f"({', '.join(sorted(reached))}), all from the last {JV_NEWS_MAX_AGE_H} hours.")
    pillow_note = False
    for label, gs in parts:
        if not gs:
            continue
        out()
        out(f"  ===== {label} =====", GREEN)
        for n, g in enumerate(gs, 1):
            b = g["best"]
            out()
            for l in jv_rs_wrap(f"{n}/{len(gs)}  {b['title']}", width, 2):
                out(l, YELLOW)
            conf = f"{tick} confirmed by {len(g['srcs'])} desks: " if len(g["srcs"]) > 1 else "single desk: "
            out(f"  {conf}{', '.join(g['srcs'])}  -  {jv_news_age(g['ts'], now)}", GRAY)
            art = pics.get(id(g))
            if art:
                out()
                for l in art:
                    out("  " + l, None)
            elif b["img"] and with_images:
                pillow_note = True
            out()
            sents = re.findall(r"[^.!?]+[.!?]+(?:\s|$)", b["desc"])
            summary = " ".join(sents[:7]) if sents else b["desc"]
            if len(summary) > 1100:
                summary = summary[:1097].rstrip() + "..."
            for l in jv_rs_wrap(summary or "(the feed carries no summary: open the link)", width, 4):
                out(l, CYAN)
            for o in [i for i in g["items"] if i["src"] != b["src"] and i["desc"]][:2]:
                more = " ".join(re.findall(r"[^.!?]+[.!?]+(?:\s|$)", o["desc"])[:3]) or o["desc"][:300]
                out()
                for l in jv_rs_wrap(f"[{o['src']}] {more}", width, 4):
                    out(l, CYAN)
            if b["link"]:
                out()
                out("    " + b["link"], GRAY)
            out()
            out("  " + "-" * min(width, 70), GRAY)
    out()
    if pillow_note:
        out("  (some stories have a photo: install Pillow with 'pip install pillow' (and use a UTF-8 terminal) and I will show it)", GRAY)
    out("  ('verified' here means: published by the desks above in the last 48 hours; a tick marks a story that two or "
        "more desks carry. I cannot fact-check beyond that.)", GRAY)


def jv_news_parse(t):
    """'news', 'ultime notizie', 'jarvis news war', 'notizie sulla guerra', 'cosa succede nel mondo' -> topic ('' for
    everything) or None (so 'open news.txt' stays a file question)."""
    s = re.sub(r"\s+", " ", t.lower().replace("\u2019", "'")).strip(" ,;:!?.")
    s = re.sub(r"^(?:(?:please|pls|per favore|ora|now|adesso|puoi|potresti|can you|could you|dammi|dimmi|mostrami|"
               r"show me|give me|tell me|fammi vedere|leggimi|read me|fammi|voglio)\s+)+", "", s)
    if re.search(r"\.(?:" + JV_RS_EXTS + r")\b", s) or re.search(r"[\"\u201c\u201d`]", s) or JV_RS_FILE_WORDS.search(s):
        return None
    lead = r"(?:(?:the|all the|tutte le|le|i|gli)\s+)?(?:(?:latest|last|new|newest|breaking|today's|ultime|ultimi|nuove|nuovi|ultim')\s+)*"
    m = re.fullmatch(lead + r"(?:news|notizie|notiziario|headlines|titoli|telegiornale)(?:\s+(?:of today|today|di oggi|oggi|now|ora|"
                     r"adesso|della giornata|del giorno))?(?:\s+(?:about|on|su|sul|sulla|sullo|sui|sugli|di|riguardo a|riguardo|"
                     r"regarding|from|dalla|dal|della|del|delle)\s+(.+))?", s)
    if m:
        return (m.group(1) or "").strip()
    if re.fullmatch(r"(?:what's|what is|whats)\s+(?:the\s+)?(?:news|happening(?: in the world)?|going on(?: in the world)?)"
                    r"(?:\s+(?:today|now))?|any (?:news|updates)|cosa succede(?: nel mondo)?|che succede(?: nel mondo)?|"
                    r"cosa sta succedendo(?: nel mondo)?|novit[a\u00e0]|aggiornamenti", s):
        return ""
    m = re.fullmatch(r"(?:latest |ultime )?(?:news|notizie)\s+(.+)", s)
    if m:
        return m.group(1).strip()
    return None


def jv_news_cmd(orig, t):
    """'jarvis news' (everything) / 'jarvis news war' / 'jarvis notizie sulle proteste', while online."""
    if not CONTESTO.get("jv_named"):
        return False
    topic = jv_news_parse(t)
    if topic is None:
        return False
    if not CONTESTO.get("jv_online"):
        jarvis_say("I'm not online yet, sir. Say 'jarvis be online' first, then ask for the news again.")
        CONTESTO["jv_nostore"] = True
        return True
    if CONTESTO.get("jv_nolog"):                      # the maintenance test never goes to the internet
        jarvis_say("Test mode, sir: I don't touch the network here.")
        return True
    try:
        jarvis_say("Reading the news desks, sir: " + ", ".join(dict.fromkeys(n for n, _ in JV_NEWS_FEEDS)) + "...")
        items, reached, tried = jv_news_collect()
        jv_news_show(items, topic, reached, tried)
    except KeyboardInterrupt:
        out()
        jarvis_say("Stopped, sir.")
    return True


