# ---------------- browser mode: 'jarvis open chrome', then 'open email', 'open canva', 'open chrome account <name>' ----------------
# Only opens web pages (https) in Chrome, on request, while Jarvis is online. It never types, clicks, reads pages or passwords.
JV_LAUNCH_SITES = {
    "gmail": ("https://mail.google.com/", None),
    "outlook": ("https://outlook.live.com/mail/", None),
    "google": ("https://www.google.com/", "https://www.google.com/search?q={}"),
    "youtube": ("https://www.youtube.com/", "https://www.youtube.com/results?search_query={}"),
    "canva": ("https://www.canva.com/", "https://www.canva.com/search?q={}"),
    "drive": ("https://drive.google.com/", "https://drive.google.com/drive/search?q={}"),
    "docs": ("https://docs.google.com/document/", None),
    "sheets": ("https://docs.google.com/spreadsheets/", None),
    "slides": ("https://docs.google.com/presentation/", None),
    "forms": ("https://docs.google.com/forms/", None),
    "calendar": ("https://calendar.google.com/", None),
    "meet": ("https://meet.google.com/", None),
    "classroom": ("https://classroom.google.com/", None),
    "photos": ("https://photos.google.com/", None),
    "keep": ("https://keep.google.com/", None),
    "maps": ("https://www.google.com/maps", "https://www.google.com/maps/search/{}"),
    "translate": ("https://translate.google.com/", None),
    "github": ("https://github.com/", "https://github.com/search?q={}"),
    "claude": ("https://claude.ai/", None),
    "chatgpt": ("https://chatgpt.com/", None),
    "whatsapp": ("https://web.whatsapp.com/", None),
    "telegram": ("https://web.telegram.org/", None),
    "instagram": ("https://www.instagram.com/", None),
    "facebook": ("https://www.facebook.com/", None),
    "x": ("https://x.com/", "https://x.com/search?q={}"),
    "reddit": ("https://www.reddit.com/", "https://www.reddit.com/search/?q={}"),
    "linkedin": ("https://www.linkedin.com/", None),
    "tiktok": ("https://www.tiktok.com/", None),
    "pinterest": ("https://www.pinterest.com/", "https://www.pinterest.com/search/pins/?q={}"),
    "amazon": ("https://www.amazon.it/", "https://www.amazon.it/s?k={}"),
    "ebay": ("https://www.ebay.it/", "https://www.ebay.it/sch/i.html?_nkw={}"),
    "netflix": ("https://www.netflix.com/", None),
    "spotify": ("https://open.spotify.com/", "https://open.spotify.com/search/{}"),
    "twitch": ("https://www.twitch.tv/", "https://www.twitch.tv/search?term={}"),
    "discord": ("https://discord.com/app", None),
    "steam": ("https://store.steampowered.com/", "https://store.steampowered.com/search/?term={}"),
    "wikipedia": ("https://en.wikipedia.org/", "https://en.wikipedia.org/w/index.php?search={}"),
    "onedrive": ("https://onedrive.live.com/", None),
    "office": ("https://www.office.com/", None),
    "word": ("https://www.office.com/launch/word", None),
    "excel": ("https://www.office.com/launch/excel", None),
    "powerpoint": ("https://www.office.com/launch/powerpoint", None),
    "teams": ("https://teams.microsoft.com/", None),
    "zoom": ("https://zoom.us/", None),
    "dropbox": ("https://www.dropbox.com/", None),
    "notion": ("https://www.notion.so/", None),
    "figma": ("https://www.figma.com/", None),
    "weather": ("https://www.google.com/search?q=weather", None),
}
JV_LAUNCH_SITE_ALIASES = {
    "email": "gmail", "e-mail": "gmail", "mail": "gmail", "my email": "gmail", "my mail": "gmail", "posta": "gmail",
    "la posta": "gmail", "la mia posta": "gmail", "google mail": "gmail", "hotmail": "outlook", "yt": "youtube",
    "you tube": "youtube", "google docs": "docs", "google doc": "docs", "document": "docs", "documents": "docs",
    "google sheets": "sheets", "spreadsheet": "sheets", "google slides": "slides", "google drive": "drive",
    "google calendar": "calendar", "calendario": "calendar", "agenda": "calendar", "google meet": "meet",
    "google classroom": "classroom", "google photos": "photos", "foto": "photos", "google maps": "maps",
    "mappe": "maps", "mappa": "maps", "traduttore": "translate", "google translate": "translate", "git hub": "github",
    "chat gpt": "chatgpt", "gpt": "chatgpt", "wa": "whatsapp", "whats app": "whatsapp", "insta": "instagram",
    "fb": "facebook", "twitter": "x", "wiki": "wikipedia", "ms teams": "teams", "microsoft teams": "teams",
    "microsoft word": "word", "microsoft excel": "excel", "powerpoint presentation": "powerpoint",
    "one drive": "onedrive", "meteo": "weather", "tempo": "weather", "the weather": "weather",
}
JV_LAUNCH_FILE_EXT = frozenset("txt py pyw png jpg jpeg gif bmp webp pdf zip rar 7z gz tar exe dll sys msi bat cmd ps1 docx doc xlsx xls pptx ppt "
                              "csv tsv json xml log ini cfg md mp3 mp4 wav ogg flac mkv avi mov win dat bin sqlite db iso lnk tmp bak".split())
JV_LAUNCH_PROFILE_DIR = re.compile(r"^[A-Za-z0-9 _-]{1,40}$")


def jv_launch_url_ok(url):
    """True only for a plain https page on a real host name: no other scheme, no user:password@, no spaces,
    no local or private address."""
    import ipaddress
    from urllib.parse import urlparse
    if not isinstance(url, str) or not url or len(url) > 2000 or re.search(r'[\s\x00-\x1f\x7f"\'<>`^|\\]', url):
        return False
    try:
        p = urlparse(url)
        host = p.hostname or ""
        port = p.port
    except ValueError:
        return False
    if p.scheme != "https" or p.username or p.password or "@" in p.netloc or port not in (None, 443):
        return False
    if not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}", host):
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    return host != "localhost" and not host.endswith((".local", ".internal", ".lan"))


def jv_launch_web_target(text):
    """What to open for a phrase such as 'email', 'canva', 'youtube lofi music', 'example.com', 'search cats'.
    Returns (url, description) or (None, why). Nothing is opened here."""
    from urllib.parse import quote_plus
    raw = text.strip().strip("\"'`“”‘’")
    raw = re.sub(r"[\s.,;:!?]+$", "", raw).strip()
    raw = re.sub(r"^(?:the|my|il|la|lo|i|le|mio|mia)\s+", "", raw, flags=re.I).strip()
    low = re.sub(r"\s+", " ", raw.lower())
    if not low:
        return None, "nothing to open"
    if re.match(r"^[a-z][a-z0-9+.-]*:", low) and not low.startswith(("http://", "https://")) and not re.match(r"^[a-z0-9.-]+:\d", low):
        return None, "I only open web pages (https), sir: never files, scripts or other kinds of link."
    m = re.match(r"^(?:search(?: for)?|google|cerca(?:mi)?|look up|find)\s+(.+)$", low)
    if m and m.group(1) not in JV_LAUNCH_SITES and JV_LAUNCH_SITE_ALIASES.get(m.group(1)) is None:
        q = m.group(1)
        return "https://www.google.com/search?q=" + quote_plus(q), f"a Google search for '{q}'"
    if low in JV_LAUNCH_SITE_ALIASES:
        low = JV_LAUNCH_SITE_ALIASES[low]
    if low in JV_LAUNCH_SITES:
        return JV_LAUNCH_SITES[low][0], low
    words = low.split()
    for n in (2, 1):                                   # '<site> <what to look for>': youtube lofi music
        if len(words) > n:
            head = " ".join(words[:n])
            head = JV_LAUNCH_SITE_ALIASES.get(head, head)
            q = re.sub(r"^(?:for|per|di|about)\s+", "", " ".join(words[n:]))
            if head in JV_LAUNCH_SITES and JV_LAUNCH_SITES[head][1] and q:
                return JV_LAUNCH_SITES[head][1].format(quote_plus(q)), f"{head}, searching '{q}'"
    cand = low if low.startswith(("http://", "https://")) else "https://" + low
    cand = re.sub(r"^http://", "https://", cand)
    if " " not in low and re.fullmatch(r"https://[^/\s]+\.[a-z]{2,24}(?::443)?(?:[/?#]\S*)?", cand):
        if jv_launch_url_ok(cand):
            return cand, "that address"
        return None, "I won't open that address, sir (only normal https web pages)."
    return "https://www.google.com/search?q=" + quote_plus(raw), f"a Google search for '{raw}'"


def jv_launch_chrome_path():
    """The Chrome program of this PC, or None."""
    cands = []
    if os.name == "nt":
        for env in ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData"):
            base = os.environ.get(env)
            if base:
                cands.append(os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"))
    elif sys.platform == "darwin":
        cands.append("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    else:
        for n in ("google-chrome", "google-chrome-stable", "chrome", "chromium", "chromium-browser"):
            w = shutil.which(n)
            if w:
                cands.append(w)
    for c in cands:
        if os.path.isfile(c):
            return c
    return None


def jv_launch_chrome_profiles(state_path=None):
    """Chrome profiles (accounts) read from Chrome's own 'Local State' file, read-only:
    [{'dir', 'name', 'email'}]. Never reads passwords, cookies or history."""
    if state_path is None:
        home = os.path.expanduser("~")
        if os.name == "nt":
            state_path = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local"),
                                      "Google", "Chrome", "User Data", "Local State")
        elif sys.platform == "darwin":
            state_path = os.path.join(home, "Library", "Application Support", "Google", "Chrome", "Local State")
        else:
            state_path = os.path.join(home, ".config", "google-chrome", "Local State")
    try:
        with open(state_path, encoding="utf-8") as f:
            cache = json.load(f).get("profile", {}).get("info_cache", {})
    except (OSError, ValueError, AttributeError):
        return []
    res = []
    for d, info in cache.items():
        if isinstance(info, dict) and isinstance(d, str) and JV_LAUNCH_PROFILE_DIR.match(d):
            res.append({"dir": d, "name": str(info.get("name") or d)[:60],
                        "email": str(info.get("user_name") or info.get("gaia_name") or "")[:80]})
    res.sort(key=lambda p: (p["dir"] != "Default", p["dir"]))
    return res


def jv_launch_profile_match(query, profs):
    """Profiles that fit 'paolo', 'work', 'name@gmail.com' or a number (1 = first in the list)."""
    q = re.sub(r"^(?:the|my|il|mio|account|profile|profilo|di|of|for|named|chiamato)\s+", "", query.strip().lower().strip("\"'`")).strip()
    q = re.sub(r"^(?:the|my|il|mio)\s+", "", q).strip()
    if not q:
        return []
    if q.isdigit() and 1 <= int(q) <= len(profs):
        return [profs[int(q) - 1]]
    exact = [p for p in profs if q in (p["name"].lower(), p["email"].lower(), p["dir"].lower())]
    if exact:
        return exact
    part = [p for p in profs if q in p["name"].lower() or q in p["email"].lower() or q in p["dir"].lower()]
    if part:
        return part
    names = {p["name"].lower(): p for p in profs}
    names.update({p["email"].lower(): p for p in profs if p["email"]})
    close = difflib.get_close_matches(q, list(names), n=2, cutoff=0.7)
    return [names[c] for c in close]


# ---- where Chrome goes on the screen: full screen, or next to the Jarvis window (never on top of it) ----
JV_LAUNCH_LAYOUT_RE = re.compile(
    r"\s*(?:,\s*)?(?:(?:in|on|to|su|a)\s+)?(?:(full\s*-?\s*screen|maximi[sz]ed?|schermo intero|tutto schermo)"
    r"|(side\s*-?\s*by\s*-?\s*side|next to jarvis|beside jarvis|accanto(?:\s+a|\s+al)?(?:\s+jarvis|\s+alla finestra di jarvis)?|"
    r"di fianco(?:\s+a jarvis)?|affiancat[oa]))\s*$", re.I)


def jv_launch_layout_strip(text):
    """'open chrome full screen' -> ('open chrome', 'full'); '... accanto' -> (..., 'side'); no layout words -> (text, None)."""
    m = JV_LAUNCH_LAYOUT_RE.search(text)
    if not m or m.start() == 0:
        return text, None
    return text[:m.start()].strip(" ,;"), "full" if m.group(1) else "side"


def jv_launch_layout():
    return CONTESTO.get("jv_chrome_layout") or "side"


def jv_launch_win_api():
    """The few Windows calls used to place windows (Windows only; None elsewhere or when they are not available)."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        u, k = ctypes.windll.user32, ctypes.windll.kernel32
        H, I, U = wintypes.HWND, ctypes.c_int, wintypes.UINT

        class MI(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                        ("dwFlags", wintypes.DWORD)]
        k.GetConsoleWindow.restype = H
        u.GetAncestor.restype, u.GetAncestor.argtypes = H, [H, U]
        u.GetWindowRect.argtypes = [H, ctypes.POINTER(wintypes.RECT)]
        u.MonitorFromWindow.restype, u.MonitorFromWindow.argtypes = wintypes.HANDLE, [H, wintypes.DWORD]
        u.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MI)]
        u.SetWindowPos.argtypes = [H, H, I, I, I, I, U]
        u.ShowWindow.argtypes = [H, I]
        u.IsWindow.argtypes = [H]
        u.IsWindowVisible.argtypes = [H]
        u.IsZoomed.argtypes = [H]
        u.GetClassNameW.argtypes = [H, wintypes.LPWSTR, I]
        u.GetWindowTextLengthW.argtypes = [H]
        return {"c": ctypes, "w": wintypes, "u": u, "k": k, "MI": MI}
    except Exception:
        return None


def jv_launch_screen_rects(api):
    """(work area, Jarvis window rectangle, Jarvis window handle) as (l, t, r, b) tuples, or None."""
    u, k, c, w, MI = api["u"], api["k"], api["c"], api["w"], api["MI"]
    hwnd = k.GetConsoleWindow()
    if not hwnd:
        return None
    root = u.GetAncestor(hwnd, 3) or hwnd                      # GA_ROOTOWNER: the real window, also inside Windows Terminal
    r = w.RECT()
    if not u.GetWindowRect(root, c.byref(r)):
        return None
    mi = MI()
    mi.cbSize = c.sizeof(MI)
    mon = u.MonitorFromWindow(root, 2)                         # the screen where the Jarvis window is
    if not mon or not u.GetMonitorInfoW(mon, c.byref(mi)):
        return None
    wa = mi.rcWork
    return (wa.left, wa.top, wa.right, wa.bottom), (r.left, r.top, r.right, r.bottom), root


def jv_launch_plan_rect(layout):
    """Where Chrome should go: ('full', None) or ('rect', (x, y, w, h)). 'side' picks the free space beside the
    Jarvis window; when there is not enough room, Jarvis is moved to one half of the screen and Chrome gets the other,
    so the two windows never overlap."""
    api = jv_launch_win_api()
    if layout == "full" or api is None:
        return ("full", None) if layout == "full" else (None, None)
    got = jv_launch_screen_rects(api)
    if not got:
        return None, None
    (wl, wt, wr, wb), (jl, jt, jr, jb), root = got
    need = max(640, int((wr - wl) * 0.35))
    zoomed = bool(api["u"].IsZoomed(root))
    if not zoomed and jr <= wr and wr - jr >= need:
        return "rect", (jr, wt, wr - jr, wb - wt)
    if not zoomed and jl >= wl and jl - wl >= need:
        return "rect", (wl, wt, jl - wl, wb - wt)
    half = (wr - wl) // 2                                      # no room: tile the screen, Jarvis left, Chrome right
    api["u"].ShowWindow(root, 9)                               # SW_RESTORE
    api["u"].SetWindowPos(root, None, wl, wt, half, wb - wt, 0x0010 | 0x0040)
    return "rect", (wl + half, wt, (wr - wl) - half, wb - wt)


def jv_launch_chrome_windows(api):
    """Handles of the visible Chrome windows right now."""
    found = []
    c, u = api["c"], api["u"]
    proc_t = c.WINFUNCTYPE(c.c_int, api["w"].HWND, api["w"].LPARAM)

    def cb(hwnd, _lp):
        try:
            if u.IsWindowVisible(hwnd) and u.GetWindowTextLengthW(hwnd) > 0:
                buf = c.create_unicode_buffer(64)
                u.GetClassNameW(hwnd, buf, 64)
                if buf.value == "Chrome_WidgetWin_1":
                    found.append(hwnd)
        except Exception:
            pass
        return 1
    u.EnumWindows.argtypes = [proc_t, api["w"].LPARAM]
    u.EnumWindows(proc_t(cb), 0)
    return set(found)


def jv_launch_apply(hwnd, kind, rect, api):
    """Move one Chrome window: maximised, or into the rectangle beside Jarvis."""
    u = api["u"]
    u.ShowWindow(hwnd, 9)                                      # restore first (a maximised window ignores moves)
    if kind == "full":
        u.ShowWindow(hwnd, 3)                                  # SW_MAXIMIZE
    elif kind == "rect" and rect:
        x, y, w, h = rect
        u.SetWindowPos(hwnd, None, x, y, w, h, 0x0010 | 0x0040)   # no activate, show


def jv_launch_relayout():
    """'chrome full screen' / 'chrome side by side' while Chrome windows of this session are open."""
    wins = CONTESTO.get("jv_chrome_win") or {}
    api = jv_launch_win_api()
    if not wins or api is None:
        return 0
    kind, rect = jv_launch_plan_rect(jv_launch_layout())
    n = 0
    for key, hwnd in list(wins.items()):
        try:
            if api["u"].IsWindow(hwnd):
                jv_launch_apply(hwnd, kind, rect, api)
                n += 1
        except Exception:
            pass
    return n


def jv_launch_maximize_self():
    """Windows: make the Jarvis window full screen (also inside Windows Terminal). True when it was done."""
    api = jv_launch_win_api()
    if api is None:
        return False
    try:
        got = jv_launch_screen_rects(api)
        if not got:
            return False
        root = got[2]
        if not api["u"].IsZoomed(root):
            api["u"].ShowWindow(root, 3)                       # SW_MAXIMIZE
        return True
    except Exception:
        return False


def jv_launch_chrome_open(urls, profile_dir=None):
    """Start Chrome (read-only for me: I only hand it addresses). The command is a list, never a shell string.
    The first window of each account in this session is placed (full screen, or beside the Jarvis window);
    later pages open as tabs in that window."""
    import subprocess
    if CONTESTO.get("jv_launch_dry"):
        return True
    exe = jv_launch_chrome_path()
    if not exe:
        return False
    for u in urls:
        if not jv_launch_url_ok(u):
            return False
    cmd = [exe]
    if profile_dir:
        if not JV_LAUNCH_PROFILE_DIR.match(profile_dir):
            return False
        cmd.append("--profile-directory=" + profile_dir)
    api = jv_launch_win_api()
    wins = CONTESTO.setdefault("jv_chrome_win", {})
    key = profile_dir or ""
    old = wins.get(key)
    first = True
    try:
        first = not (api is not None and old and api["u"].IsWindow(old))
    except Exception:
        first = True
    kind, rect, before = None, None, set()
    if first:
        layout = jv_launch_layout()
        try:
            kind, rect = jv_launch_plan_rect(layout)
        except Exception:
            kind, rect = None, None
        cmd.append("--new-window")
        if kind == "full":
            cmd.append("--start-maximized")
        elif kind == "rect" and rect:
            cmd += [f"--window-position={rect[0]},{rect[1]}", f"--window-size={rect[2]},{rect[3]}"]
        if api is not None:
            try:
                before = jv_launch_chrome_windows(api)
            except Exception:
                before = set()
    cmd += list(urls)
    kw = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    if os.name == "nt":
        kw["creationflags"] = 0x00000008 | 0x00000200
    else:
        kw["start_new_session"] = True
    subprocess.Popen(cmd, **kw)
    if first and api is not None and kind:
        end = time.time() + 6                                   # wait for the new window, then put it exactly in place
        while time.time() < end:
            time.sleep(0.2)
            try:
                new = jv_launch_chrome_windows(api) - before
            except Exception:
                break
            if new:
                hwnd = sorted(new)[0]
                wins[key] = hwnd
                time.sleep(0.4)
                jv_launch_apply(hwnd, kind, rect, api)
                break
    return True


def jv_launch_browser(orig, t):
    """Browser mode. 'jarvis open chrome' starts it; then 'open email', 'open canva', 'open youtube lofi',
    'search ...', 'open chrome account <name>' open pages in Chrome, in the chosen account, until 'close chrome mode'.
    Needs 'jarvis be online'. True when the sentence was for the browser."""
    br = CONTESTO.get("jv_browser")
    named = bool(CONTESTO.get("jv_named"))
    s = re.sub(r"[\s.,;:!?]+$", "", t.strip())
    s = re.sub(r"^(?:please|pls|per favore|ok|then|poi|now|ora)[,\s]+", "", s)
    s = re.sub(r"^(?:can|could|would) you(?: please)?\s+|^(?:puoi|potresti)\s+", "", s)
    s_lay, lay = jv_launch_layout_strip(s)
    if lay and (named or br) and re.fullmatch(r"(?:(?:make|put|set|metti|imposta|use|usa)\s+)?(?:the\s+)?(?:chrome|browser|layout)"
                                              r"(?:\s+(?:mode|window|windows|finestra))?", s_lay):
        CONTESTO["jv_chrome_layout"] = lay
        moved = jv_launch_relayout()
        jarvis_say(("Chrome will open full screen, sir" if lay == "full" else
                    "Chrome will open next to my window, sir, never on top of it")
                   + (f" ({moved} open window(s) moved)." if moved else "."))
        return True
    if lay and re.fullmatch(r"(?:open|launch|start|apri|avvia|lancia|switch to|passa a|use|usa)\s+(?:google\s+)?chrome.*", s_lay):
        CONTESTO["jv_chrome_layout"] = lay
        s = s_lay
    if br and re.fullmatch(r"(?:close|exit|stop|end|leave|quit|chiudi|termina|esci da|finish)\s+(?:the\s+)?(?:chrome|browser|browsing)(?:\s+mode)?|"
                           r"(?:done|finished) (?:with )?(?:chrome|the browser)|(?:chrome|browser) mode off", s):
        CONTESTO["jv_browser"] = None
        CONTESTO.pop("jv_chrome_win", None)
        jarvis_say("Chrome mode ended, sir. I only stop sending pages; the browser window stays as it is.")
        return True
    m = re.fullmatch(r"(?:open|launch|start|apri|avvia|lancia|switch to|passa a|use|usa)\s+(?:google\s+)?chrome"
                     r"(?:\s+(?:and\s+)?(?:with|using|on|in|con|su)?\s*(?:the\s+|my\s+)?(?:account|profile|profilo|user)\b\s*(.*))?", s)
    if m and (named or br):
        acct = (m.group(1) or "").strip()
        if not CONTESTO.get("jv_online"):
            jarvis_say("I only open Chrome and web pages while I'm online, sir. Say 'jarvis be online' first.")
            return True
        profs = jv_launch_chrome_profiles()
        profile = None
        if re.search(r"\b(?:account|profile|profilo|user)\b", s) and not acct:
            if not profs:
                jarvis_say("I can't see any Chrome accounts, sir (Chrome keeps the list in its 'Local State' file). Open Chrome once and sign in.")
                return True
            jarvis_say("Chrome accounts I can see, sir: say  open chrome account <name or number>")
            for i, p in enumerate(profs, 1):
                out(f"  [{i}] {safe(p['name'])}" + (f"  <{safe(p['email'])}>" if p["email"] else "") + f"   ({safe(p['dir'])})")
            return True
        if acct:
            hits = jv_launch_profile_match(acct, profs)
            if not profs:
                jarvis_say("I can't see any Chrome accounts, sir. Open Chrome once and sign in, then try again.")
                return True
            if not hits:
                jarvis_say(f"No Chrome account matches '{safe(acct)}', sir. Say 'open chrome account' to see the list.")
                return True
            if len(hits) > 1:
                jarvis_say(f"'{safe(acct)}' fits more than one account, sir; say the number:")
                for i, p in enumerate(profs, 1):
                    if p in hits:
                        out(f"  [{i}] {safe(p['name'])}" + (f"  <{safe(p['email'])}>" if p["email"] else ""))
                return True
            profile = hits[0]
        if not CONTESTO.get("jv_launch_dry") and not jv_launch_chrome_path():
            jarvis_say("I can't find Chrome on this PC, sir. Is it installed?")
            return True
        ok = jv_launch_chrome_open([], profile["dir"] if profile else (br or {}).get("profile"))
        if not ok:
            jarvis_say("Chrome would not start, sir.")
            return True
        CONTESTO["jv_browser"] = {"profile": profile["dir"] if profile else (br or {}).get("profile"),
                                  "label": (profile["name"] if profile else (br or {}).get("label"))}
        who = f" with the account '{safe(profile['name'])}'" if profile else ""
        jarvis_say(f"Chrome{who} is starting, sir. Chrome mode is on: say  open email / open canva / open <site> / search <words>,  "
                   f"and 'close chrome mode' when you are done.")
        return True
    m = re.fullmatch(r"(?:open|go to|goto|visit|apri|vai su|vai a|search(?: for)?|google|cerca(?:mi)?|look up)\s+(.+)", s)
    if not m:
        return False
    rest = m.group(1).strip()
    explicit = re.search(r"\s+(?:in|on|with|su|con|using)\s+(?:google\s+)?chrome$", rest)
    if explicit:
        rest = rest[:explicit.start()].strip()
    if not (br or (named and explicit)):
        return False
    verb = s.split()[0]
    if verb in ("search", "google", "cerca", "cercami", "look") and not re.match(r"^(?:search|google|cerca|look up)", rest):
        rest = "search " + rest
    low = rest.lower()
    if re.fullmatch(r"(?:it|this|that|them|these|those|here|0|\d{1,3}|(?:the )?(?:first|second|third|1st|2nd|3rd)(?: one)?)", low) \
            or re.search(r"[\\/]", low) and not low.startswith("http") or os.path.isfile(rest) or os.path.isdir(rest):
        return False                                    # a file, folder or number of an earlier list: not a web page
    ext = low.rsplit(".", 1)[-1] if re.fullmatch(r"[^\s/]+\.[a-z0-9]{1,6}", low) else ""
    if ext in JV_LAUNCH_FILE_EXT:
        return False                                    # 'open notes.txt' is a file, never a web address
    if not CONTESTO.get("jv_online"):
        jarvis_say("I only open web pages while I'm online, sir. Say 'jarvis be online' first.")
        return True
    url, desc = jv_launch_web_target(rest)
    if not url:
        jarvis_say(desc)
        return True
    if not jv_launch_url_ok(url):
        jarvis_say("I won't open that address, sir.")
        return True
    if not CONTESTO.get("jv_launch_dry") and not jv_launch_chrome_path():
        jarvis_say("I can't find Chrome on this PC, sir. Is it installed?")
        return True
    prof = (br or {}).get("profile")
    if not jv_launch_chrome_open([url], prof):
        jarvis_say("Chrome would not open it, sir.")
        return True
    if not br:
        CONTESTO["jv_browser"] = {"profile": None, "label": None}
    acct = f" (account '{safe(br['label'])}')" if br and br.get("label") else ""
    jarvis_say(f"Opening {safe(desc)} in Chrome{acct}, sir.")
    out("  " + safe(url), GRAY)
    return True


def jv_launch_try(rest):
    """'jarvis open <rest>': True when it was a game request (started, listed, or explained); False to let the
    normal read-only open handle it (files, folders, data.win, numbers of an earlier list...)."""
    phrase = re.sub(r"[\s.,;:!?]+$", "", rest.strip().strip("\"'`“”‘’")).strip()
    if not phrase or re.search(r"[\\/:]", phrase) or phrase.lower() in JV_PRON or phrase.lower() in JV_HERE:
        return False
    num = re.fullmatch(r"(?:#|n\.?\s*|number\s+|numero\s+)?(\d{1,3})(?:st|nd|rd|th)?", phrase, re.I) \
        or re.fullmatch(r"(first|second|third|fourth|fifth|primo|secondo|terzo|quarto|quinto)", phrase, re.I)
    pend = CONTESTO.get("jv_launch_pending")
    if num:
        if not pend:
            return False
        idx = int(num.group(1)) if num.group(1).isdigit() else JV_ORD[num.group(1).lower()]
        if 1 <= idx <= len(pend):
            game, part = pend[idx - 1]
            CONTESTO.pop("jv_launch_pending", None)
            if part is None:
                jv_launch_start(game, None)
            else:
                jv_launch_run(game, part)
        else:
            jarvis_say(f"There are only {len(pend)} choice(s), sir.")
        return True
    if jv_filename_tokens(phrase) and not re.search(r"\s", phrase):
        return False                                           # looks like a file name: normal open
    if os.path.isfile(phrase):
        return False
    matches, chapter = jv_launch_match(phrase, jv_launch_games())
    if not matches:
        return False
    CONTESTO.pop("jv_launch_pending", None)
    if len(matches) > 1:
        jarvis_say("Several games match, sir. Which one?")
        for i, g in enumerate(matches, 1):
            out(f"  [{i}] {safe(g['name'])}   {safe(g['root'])}", CYAN)
        CONTESTO["jv_launch_pending"] = [(g, None) for g in matches]
        jarvis_say("Say 'jarvis open 1', 'jarvis open 2'... or give me the exact name.")
        return True
    jv_launch_start(matches[0], chapter)
    return True


