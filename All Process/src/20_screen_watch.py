# ---------------- SCREEN WATCH: "is someone watching my screen?" ----------------
# Four times a second (Windows only, through Windows' own APIs: about 2 ms a look) Jarvis READS four things: the session list (qwinsta), the open connections (netstat),
# the process list (tasklist) and the titles of the visible windows. Nothing on the PC is changed.
# When a Remote Desktop / VNC / remote-help / screen-sharing session shows up, Jarvis pauses at its next output (JV_RUN),
# a red WARNING window tells you who or what it is (names come from your list of known people: 'watch know'),
# an optional e-mail goes to YOU, and if you press F the viewer sees a SIMULATED intrusion screen (text and colours only).
# Safety nets: the pause always ends (window closed, window failed to open, or the time limit), see jv_watch_alert_run.
JV_WATCH = {"daemon": False, "on": True, "thread": None, "stop": threading.Event(), "seen": set(), "alert": False,
            "interval": 0.25, "last": [], "api": None, "shield": {"hidden": set(), "sent": {}},
            "shield_lock": threading.Lock(), "wake": threading.Event(), "seen_t": 0.0, "beat_t": {}, "slow": None,
            "cfg": {}, "cfg_t": 0.0, "native": None, "native_done": False}
JV_WATCH_FAST = 0.25      # how often to look when the native (instant) look works: 4 times a second
JV_SHIELD_TICK = 0.05     # the shield re-checks the windows 20 times a second while somebody is watching
JV_SHIELD_HOLD = 1.5      # seconds the shield stays up after the viewer's last sign (no flicker if a sign blinks)
JV_WATCH_FILE = "screenwatch.json"
JV_WATCH_PORTS = {3389: "Remote Desktop (RDP)", 5900: "VNC", 5901: "VNC", 5800: "VNC (web)"}
# process name -> what it means. Only programs that run WHILE a session is going on (not the always-on background service).
JV_WATCH_TOOLS = {
    "teamviewer_desktop.exe": "TeamViewer session",
    "cpthost.exe": "Zoom screen sharing",
    "msra.exe": "Windows Remote Assistance",
    "quickassist.exe": "Quick Assist",
    "remoting_desktop.exe": "Chrome Remote Desktop session",
    "screenconnect.windowsclient.exe": "ScreenConnect session",
}
JV_WATCH_TITLES = ("is sharing your screen", "sharing your entire screen", "sharing your screen",
                   "sta condividendo lo schermo", "stai condividendo lo schermo", "condivide lo schermo",
                   "condividendo lo schermo", "sharing control bar", "stop sharing", "interrompi condivisione",
                   "smetti di condividere")


# ---------------- settings (jarvis_update/screenwatch.json) ----------------
def jv_watch_cfg():
    try:
        with open(os.path.join(jv_upd_dir(), JV_WATCH_FILE), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def jv_watch_cfg_cached(ttl=1.0):
    """The settings, re-read at most once per 'ttl' seconds (the fast loops use this instead of reading the file 4 times a second)."""
    st = JV_WATCH
    if time.time() - st["cfg_t"] > ttl:
        st["cfg"], st["cfg_t"] = jv_watch_cfg(), time.time()
    return st["cfg"]


def jv_watch_interval(cfg):
    """Seconds between two looks: 0.2 - 300, default 0.25. A value saved by an older version (no 'interval_v') is ignored,
    so that the old 5 s default does not slow the new fast look down."""
    try:
        v = float(cfg.get("interval")) if cfg.get("interval_v") == 2 else JV_WATCH_FAST
    except (TypeError, ValueError):
        v = JV_WATCH_FAST
    return min(max(v, 0.2), 300.0)


def jv_watch_save(cfg):
    """The only file this feature writes: its own tiny settings file. True when saved."""
    JV_WATCH["cfg_t"] = 0.0
    try:
        os.makedirs(jv_upd_dir(), exist_ok=True)
        with open(os.path.join(jv_upd_dir(), JV_WATCH_FILE), "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=1, ensure_ascii=False)
        return True
    except OSError:
        return False


# ---------------- reading the system (read-only) ----------------
def jv_watch_run(cmd, timeout=12):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, errors="replace",
                           creationflags=0x08000000 if os.name == "nt" else 0)   # CREATE_NO_WINDOW
        return r.stdout or ""
    except (OSError, subprocess.SubprocessError, ValueError):
        return ""


def jv_watch_parse_sessions(text):
    """qwinsta output -> [(session, user, id)] of the remote 'rdp-tcp#N' sessions.
    The state word is NOT used (it is translated on every Windows language): a session that has a
    'rdp-tcp#N' name and a user is connected; a disconnected one has no session name."""
    res = []
    for line in str(text).splitlines():
        m = re.match(r"^[\s>]*(rdp-tcp#\d+)\s+(\S+)\s+(\d+)\b", line, re.I)
        if m:
            res.append((m.group(1).lower(), m.group(2), m.group(3)))
    return res


def jv_watch_parse_netstat(text, ports=JV_WATCH_PORTS):
    """netstat -ano output -> [(port, remote ip)] of real incoming connections on the remote-control ports.
    Listening sockets (foreign address 0.0.0.0:0), the PC talking to itself and closing sockets are ignored.
    State words are not trusted either (they are translated, e.g. STABILITA)."""
    res = []
    for line in str(text).splitlines():
        p = line.split()
        if len(p) < 4 or p[0].upper() != "TCP":
            continue
        local, foreign = p[1], p[2]
        state = p[3].upper()
        lport = local.rsplit(":", 1)[-1]
        if not lport.isdigit() or int(lport) not in ports:
            continue
        fhost, _, fport = foreign.rpartition(":")
        fhost = fhost.strip("[]")
        if fport in ("0", "*", "") or fhost in ("", "0.0.0.0", "::", "*") or fhost == "::1" or fhost.startswith("127."):
            continue
        if "WAIT" in state or "CLOS" in state or "SYN" in state or "FIN" in state:
            continue
        res.append((int(lport), fhost))
    return res


def jv_watch_parse_tasks(text, tools=JV_WATCH_TOOLS):
    """tasklist /fo csv /nh output -> [(process name, meaning)] of the remote-help programs that are running."""
    import csv
    import io
    res, seen = [], set()
    try:
        for row in csv.reader(io.StringIO(str(text))):
            if row and row[0].lower() in tools and row[0].lower() not in seen:
                seen.add(row[0].lower())
                res.append((row[0].lower(), tools[row[0].lower()]))
    except csv.Error:
        pass
    return res


def jv_watch_match_titles(titles, patterns=JV_WATCH_TITLES):
    """Window titles -> the ones that say 'sharing your screen' (several languages)."""
    res = []
    for t in titles:
        low = str(t).lower()
        if any(p in low for p in patterns) and t not in res:
            res.append(t)
    return res


def jv_watch_windows():
    """Titles of the visible windows (Windows only)."""
    if os.name != "nt":
        return []
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        titles = []
        proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def each(hwnd, _):
            if user32.IsWindowVisible(hwnd):
                n = user32.GetWindowTextLengthW(hwnd)
                if n:
                    buf = ctypes.create_unicode_buffer(n + 1)
                    user32.GetWindowTextW(hwnd, buf, n + 1)
                    titles.append(buf.value)
            return True
        user32.EnumWindows(proc(each), 0)
        return titles
    except Exception:
        return []


def jv_watch_tcp_rows(buf, v6, ports=JV_WATCH_PORTS):
    """Raw Windows TCP table (GetExtendedTcpTable, owner-pid layout) -> [(port, remote host)] of the ESTABLISHED incoming
    connections on the remote-control ports. Same rules as jv_watch_parse_netstat: listening sockets, loopback and
    half-open / closing connections are ignored. Pure (no Windows needed), so it can be tested anywhere."""
    import ipaddress
    import struct
    fmt = "<16sII16sIIII" if v6 else "<6I"
    size = struct.calcsize(fmt)
    res, seen = [], set()
    count = struct.unpack_from("<I", buf, 0)[0]
    for i in range(min(count, (len(buf) - 4) // size)):
        row = struct.unpack_from(fmt, buf, 4 + i * size)
        if v6:
            _, _, lport, raddr, _, rport, state, _ = row
            host = ipaddress.IPv6Address(raddr)
            if host.ipv4_mapped is not None:
                host = host.ipv4_mapped
        else:
            state, _, lport, raddr, rport, _ = row
            host = ipaddress.IPv4Address(struct.pack("<I", raddr))
        port = ((lport & 255) << 8) | ((lport >> 8) & 255)            # the table keeps ports in network byte order
        if state != 5 or port not in ports or not (rport & 0xFFFF) or host.is_loopback or host.is_unspecified:
            continue
        if (port, str(host)) not in seen:
            seen.add((port, str(host)))
            res.append((port, str(host)))
    return res


def jv_watch_native():
    """The FAST read-only look: Windows' own APIs instead of starting qwinsta / netstat / tasklist (about 2 ms instead of
    0.5 - 2 s). Returns an object with sessions() / tcp() / procs(), or None. Each of them returns None when it fails
    (and is then not tried again): the caller falls back to the old command for that one."""
    st = JV_WATCH
    if st["native_done"]:
        return st["native"]
    st["native_done"] = True
    if os.name != "nt":
        return None
    try:
        import ctypes
        import types
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32")
        iph = ctypes.WinDLL("iphlpapi")
        wts = ctypes.WinDLL("wtsapi32")
        bad = set()

        class PE32(ctypes.Structure):
            _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                        ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                        ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                        ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                        ("szExeFile", ctypes.c_wchar * 260)]

        class WSI(ctypes.Structure):
            _fields_ = [("SessionId", wintypes.DWORD), ("pWinStationName", wintypes.LPWSTR), ("State", ctypes.c_int)]
        k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        k32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PE32)]
        k32.Process32FirstW.restype = wintypes.BOOL
        k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PE32)]
        k32.Process32NextW.restype = wintypes.BOOL
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        iph.GetExtendedTcpTable.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), wintypes.BOOL,
                                            wintypes.ULONG, ctypes.c_int, wintypes.ULONG]
        iph.GetExtendedTcpTable.restype = wintypes.DWORD
        wts.WTSEnumerateSessionsW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                                              ctypes.POINTER(ctypes.POINTER(WSI)), ctypes.POINTER(wintypes.DWORD)]
        wts.WTSEnumerateSessionsW.restype = wintypes.BOOL
        wts.WTSQuerySessionInformationW.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_int,
                                                    ctypes.POINTER(wintypes.LPWSTR), ctypes.POINTER(wintypes.DWORD)]
        wts.WTSQuerySessionInformationW.restype = wintypes.BOOL
        wts.WTSFreeMemory.argtypes = [ctypes.c_void_p]
        wts.WTSFreeMemory.restype = None

        def procs():
            h = k32.CreateToolhelp32Snapshot(2, 0)                          # TH32CS_SNAPPROCESS
            if not h or h == ctypes.c_void_p(-1).value:
                raise OSError("process snapshot failed")
            names = set()
            try:
                e = PE32()
                e.dwSize = ctypes.sizeof(PE32)
                ok = k32.Process32FirstW(h, ctypes.byref(e))
                while ok:
                    names.add(e.szExeFile.lower())
                    ok = k32.Process32NextW(h, ctypes.byref(e))
            finally:
                k32.CloseHandle(h)
            return names

        def table(family):
            size = wintypes.DWORD(0)
            iph.GetExtendedTcpTable(None, ctypes.byref(size), False, family, 5, 0)     # TCP_TABLE_OWNER_PID_ALL: asks the size
            for _ in range(5):                                                         # the table can grow between the calls
                buf = (ctypes.c_ubyte * (size.value + 512))()
                size.value = len(buf)
                r = iph.GetExtendedTcpTable(buf, ctypes.byref(size), False, family, 5, 0)
                if r == 0:
                    return buf
                if r != 122:                                                           # ERROR_INSUFFICIENT_BUFFER: try again
                    raise OSError("GetExtendedTcpTable %d" % r)
            raise OSError("GetExtendedTcpTable: table keeps growing")

        def tcp():
            return jv_watch_tcp_rows(table(2), False) + jv_watch_tcp_rows(table(23), True)    # AF_INET + AF_INET6

        def sessions():
            lst, n = ctypes.POINTER(WSI)(), wintypes.DWORD(0)
            if not wts.WTSEnumerateSessionsW(None, 0, 1, ctypes.byref(lst), ctypes.byref(n)):
                raise OSError("WTSEnumerateSessions failed")
            res = []
            try:
                for i in range(n.value):
                    name = (lst[i].pWinStationName or "").lower()
                    if not name.startswith("rdp-tcp#"):                                # only a connected remote session has this name
                        continue
                    buf, ln = wintypes.LPWSTR(), wintypes.DWORD(0)
                    user = ""
                    if wts.WTSQuerySessionInformationW(None, lst[i].SessionId, 5, ctypes.byref(buf), ctypes.byref(ln)):   # WTSUserName
                        user = buf.value or ""
                        wts.WTSFreeMemory(ctypes.cast(buf, ctypes.c_void_p))
                    if user:
                        res.append((name, user, str(lst[i].SessionId)))
            finally:
                wts.WTSFreeMemory(ctypes.cast(lst, ctypes.c_void_p))
            return res

        def safe(name, fn):
            def run():
                if name in bad:
                    return None
                try:
                    return fn()
                except Exception:
                    bad.add(name)
                    return None
            return run
        st["native"] = types.SimpleNamespace(procs=safe("procs", procs), tcp=safe("tcp", tcp),
                                             sessions=safe("sessions", sessions))
    except Exception:
        st["native"] = None
    return st["native"]


def jv_watch_scan():
    """One look at the system -> list of {tag, what, remote, user, name} (empty = nobody watching).
    Fast path: Windows' own APIs (a few ms). A source that cannot be read that way falls back to its old command
    (qwinsta / netstat / tasklist), and then JV_WATCH['slow'] is True: the loops look less often (every 2 s at most)."""
    if os.name != "nt":
        return []
    nat = jv_watch_native()
    slow = False
    sess = nat.sessions() if nat else None
    if sess is None:
        sess, slow = jv_watch_parse_sessions(jv_watch_run(["qwinsta"])), True
    conns = nat.tcp() if nat else None
    if conns is None:
        conns, slow = jv_watch_parse_netstat(jv_watch_run(["netstat", "-ano", "-p", "tcp"])), True
    names = nat.procs() if nat else None
    if names is None:
        tasks, slow = jv_watch_parse_tasks(jv_watch_run(["tasklist", "/fo", "csv", "/nh"])), True
    else:
        tasks = [(n, JV_WATCH_TOOLS[n]) for n in sorted(names & set(JV_WATCH_TOOLS))]
    JV_WATCH["slow"] = slow
    items = []
    for sess_name, user, sid in sess:
        items.append({"tag": "sess:" + sess_name, "what": f"Remote Desktop session {sess_name} (user {user})", "remote": "", "user": user})
    for port, ip in conns:
        items.append({"tag": f"net:{ip}:{port}", "what": f"{JV_WATCH_PORTS[port]} connection on port {port}", "remote": ip, "user": ""})
    for proc, meaning in tasks:
        items.append({"tag": "proc:" + proc, "what": meaning, "remote": "", "user": ""})
    for t in jv_watch_match_titles(jv_watch_windows()):
        items.append({"tag": "win:" + t.lower()[:80], "what": f"window: {t[:80]}", "remote": "", "user": ""})
    if items:
        cfg = jv_watch_cfg_cached()
        for it in items:
            it["name"] = jv_watch_who(it, cfg)
    return items


def jv_watch_publish(items):
    """Stores what the last look found and wakes the shield at once (it does not wait for its next tick)."""
    st = JV_WATCH
    st["last"] = items
    if items:
        st["seen_t"] = time.time()
        st["wake"].set()
    return items


def jv_watch_present():
    """True while somebody is watching (plus a short hold-over, so a sign that blinks does not make the windows flicker)."""
    st = JV_WATCH
    return bool(st["on"]) and (bool(st["last"]) or time.time() - st["seen_t"] < JV_SHIELD_HOLD)


def jv_watch_warm():
    """Loads tkinter in the background, so that the first WARNING window does not pay for the import."""
    try:
        import tkinter
    except Exception:
        pass


def jv_watch_who(item, cfg):
    """Name from your list of known people ('watch know') that matches the IP or the user, or ''."""
    keys = {str(item.get("remote") or "").lower(), str(item.get("user") or "").lower()} - {""}
    known = cfg.get("known")
    if isinstance(known, dict):
        for name, ids in known.items():
            if isinstance(ids, list) and keys & {str(i).lower() for i in ids}:
                return str(name)
    return ""


# ---------------- the alert ----------------
def jv_watch_lines(items):
    lines = [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ""]
    for it in items:
        who = it.get("name") or "UNKNOWN"
        extra = f"  from {it['remote']}" if it.get("remote") else ""
        lines.append(f"- {it['what']}{extra}   [{who}]")
    return lines


def jv_watch_fake_lines(n=60):
    """Lines of the SIMULATED intrusion screen: only text, nothing real is done."""
    rnd = random
    hosts = ["10.0.%d.%d" % (rnd.randint(0, 9), rnd.randint(2, 250)) for _ in range(6)]
    pool = [
        "[!] INTRUSION DETECTED - tracing connection ...",
        "[*] locking remote input channel",
        "[*] capturing viewer fingerprint ... done",
        "[!] viewer address logged: {ip}",
        "[*] forwarding session log to security service",
        "[*] firewall rule applied: DENY {ip}",
        "[!] reverse trace in progress {pct}%",
        "[*] screenshot of viewer session saved ({kb} KB)",
        "[!] ALERT: unauthorized remote access attempt reported",
        "[*] notifying administrator ... sent",
    ]
    res = []
    for _ in range(n):
        res.append(rnd.choice(pool).format(ip=rnd.choice(hosts), pct=rnd.randint(1, 99), kb=rnd.randint(80, 900)))
    res.append("[!] CONNECTION FLAGGED - ALL ACTIVITY IS BEING RECORDED")
    return res


def jv_watch_scare(root, tk):
    """Full-screen SIMULATED attack for whoever is watching. Esc closes it. Nothing real happens."""
    top = tk.Toplevel(root)
    top.configure(bg="black")
    top.attributes("-fullscreen", True)
    top.attributes("-topmost", True)
    box = tk.Text(top, bg="black", fg="#ff3030", font=("Consolas", 15), bd=0, highlightthickness=0, cursor="none")
    box.pack(fill="both", expand=True)
    lines = jv_watch_fake_lines()
    state = {"i": 0, "alive": True}

    def step():
        if not state["alive"]:
            return
        try:
            box.insert("end", lines[state["i"] % len(lines)] + "\n")
            box.see("end")
            state["i"] += 1
            top.after(random.randint(40, 180), step)
        except tk.TclError:
            state["alive"] = False

    def close(_=None):
        state["alive"] = False
        try:
            top.destroy()
        except tk.TclError:
            pass
    top.bind("<Escape>", close)
    top.focus_force()
    step()


def jv_watch_window(lines, hold_max):
    """The red WARNING window. Returns when it is closed, or after hold_max seconds (failsafe)."""
    import tkinter as tk
    red = "#b00020"
    root = tk.Tk()
    root.title("JARVIS - WARNING")
    root.configure(bg=red)
    root.attributes("-topmost", True)
    w, h = 760, 440
    root.geometry(f"{w}x{h}+{max(0, (root.winfo_screenwidth() - w) // 2)}+{max(0, (root.winfo_screenheight() - h) // 2)}")
    tk.Label(root, text="WARNING", font=("Segoe UI", 34, "bold"), fg="white", bg=red).pack(pady=(16, 0))
    tk.Label(root, text="Someone may be watching this screen", font=("Segoe UI", 15), fg="white", bg=red).pack()
    tk.Label(root, text="\n".join(lines[:12]), justify="left", anchor="w", font=("Consolas", 11), fg="white", bg=red,
             wraplength=w - 40).pack(pady=10, padx=20, anchor="w")
    daemon = bool(JV_WATCH.get("daemon"))
    tk.Label(root, text=("Jarvis guard (background).   ENTER = close     F = show the viewer a fake intrusion screen (Esc closes it)" if daemon else
                         "Jarvis is paused.   ENTER = resume     F = show the viewer a fake intrusion screen (Esc closes it)"),
             font=("Segoe UI", 10), fg="white", bg=red).pack(side="bottom", pady=10)
    tk.Button(root, text="OK - close" if daemon else "OK - resume Jarvis", command=root.destroy).pack(side="bottom")
    root.bind("<Return>", lambda e: root.destroy())
    root.bind("<f>", lambda e: jv_watch_scare(root, tk))
    root.bind("<F>", lambda e: jv_watch_scare(root, tk))
    root.after(int(hold_max * 1000), root.destroy)
    root.focus_force()
    root.mainloop()


def jv_watch_box_fallback(lines):
    """If the Tk window cannot open: a plain Windows message box (blocks until OK). Elsewhere: a short pause."""
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, "\n".join(lines[:12]), "JARVIS - WARNING: someone may be watching", 0x30 | 0x40000)
            return
        except Exception:
            pass
    time.sleep(5)


def jv_watch_mail(subject, body, cfg):
    """Optional alert e-mail to YOU (SMTP over TLS, only to the address you set). The password is read from an
    environment variable you name ('passenv'), never stored in the settings file. Returns '' or an error text."""
    to, host = str(cfg.get("mail_to") or ""), str(cfg.get("smtp_host") or "")
    if not to or not host:
        return "e-mail is not set up"
    try:
        import smtplib
        import ssl
        from email.message import EmailMessage
        port = int(cfg.get("smtp_port") or 465)
        user = str(cfg.get("smtp_user") or "")
        pw = os.environ.get(str(cfg.get("password_env") or ""), "")
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = subject, user or to, to
        msg.set_content(body)
        ctx = ssl.create_default_context()
        if port == 465:
            s = smtplib.SMTP_SSL(host, port, timeout=15, context=ctx)
        else:
            s = smtplib.SMTP(host, port, timeout=15)
            s.starttls(context=ctx)
        with s:
            if user and pw:
                s.login(user, pw)
            s.send_message(msg)
        return ""
    except Exception as e:
        return str(e)[:200]


def jv_watch_alert(items):
    """Pause Jarvis and open the warning. Safe to call from the watcher thread."""
    st = JV_WATCH
    if st["alert"]:
        return
    st["alert"] = True
    JV_RUN.clear()
    try:
        threading.Thread(target=jv_watch_alert_run, args=(list(items),), daemon=True).start()
    except Exception:
        st["alert"] = False
        JV_RUN.set()


def jv_watch_alert_run(items):
    try:
        cfg = jv_watch_cfg()
        lines = jv_watch_lines(items)
        jv_upd_log("screen watch: " + "; ".join(i["what"] + (" from " + i["remote"] if i.get("remote") else "") for i in items))
        if cfg.get("mail_to"):
            threading.Thread(target=jv_watch_mail, args=("JARVIS: someone is watching your screen", "\n".join(lines), cfg),
                             daemon=True).start()
        hold = min(max(int(cfg.get("hold_max") or JV_HOLD_MAX), 30), JV_HOLD_MAX)
        try:
            jv_watch_window(lines, hold)
        except Exception:
            jv_watch_box_fallback(lines)
    finally:                              # whatever happens above, Jarvis ALWAYS resumes
        JV_WATCH["alert"] = False
        JV_RUN.set()


def jv_watch_loop():
    st = JV_WATCH
    while True:
        try:
            jv_watch_beat("jarvis", st["interval"])      # tells the background guard "Jarvis is open and watching": the guard stays quiet
            if st["on"]:
                items = jv_watch_publish(jv_watch_scan())
                tags = {i["tag"] for i in items}
                new = tags - st["seen"]
                st["seen"] = tags                 # what ended is forgotten, so a later session alerts again
                if new and not st["alert"]:
                    jv_watch_alert(items)
        except Exception:
            pass                                  # the watcher never dies because of one bad reading
        if st["stop"].wait(max(st["interval"], 2.0) if st["slow"] else st["interval"]):
            break


def jv_watch_start():
    st = JV_WATCH
    cfg = jv_watch_cfg()
    st["on"] = bool(cfg.get("on", True))
    st["interval"] = jv_watch_interval(cfg)
    if os.name == "nt" and st["thread"] is None:
        threading.Thread(target=jv_watch_warm, daemon=True).start()
        st["thread"] = threading.Thread(target=jv_watch_loop, daemon=True)
        st["thread"].start()
        threading.Thread(target=jv_watch_shield_loop, args=(st["stop"],), daemon=True).start()
        if not jv_watch_guard_installed() and int(cfg.get("hint_n") or 0) < 3:
            cfg["hint_n"] = int(cfg.get("hint_n") or 0) + 1
            jv_watch_save(cfg)
            out("  Screen watch only works while Jarvis is open. For always-on (also when closed):  watch guard on", GRAY)


def jv_watch_stop():
    JV_WATCH["stop"].set()
    JV_WATCH["wake"].set()
    JV_RUN.set()
    jv_watch_shield_restore()                           # windows hidden by the shield come back when Jarvis closes
    jv_watch_beat("jarvis", 0, closed=True)             # Jarvis is closing: the background guard takes over at once


# ---------------- the shield: while somebody is watching, Firefox disappears from the screen ----------------
# As long as the watcher sees a viewer (see jv_watch_scan), every 0.05 s the windows of the shielded programs (default:
# firefox.exe) are hidden (mode 'hide'), minimised ('minimize') or asked to close ('close'). When the viewer is gone they
# come back (mode 'hide'). Nothing is killed: 'hide' only takes the window off the screen, the program keeps running.
# Speed: the viewer is noticed at the next look (every 0.25 s), the watcher wakes the shield at once, and while somebody is
# watching the shield re-checks the windows every 0.05 s, so a window that opens can be seen for ~0.05 s at most.
JV_SHIELD_MODES = ("kill", "hide", "minimize", "close", "off")


def jv_watch_shield_cfg(cfg):
    """settings -> (mode, set of program names). Default: kill, firefox.exe (the program is ended at once, no questions asked)."""
    mode = str(cfg.get("shield_mode") or "kill").lower()
    if mode not in JV_SHIELD_MODES:
        mode = "kill"
    apps = cfg.get("shield_apps")
    names = {str(a).lower() for a in apps if re.fullmatch(r"[\w .+-]{1,60}\.exe", str(a), re.I)} if isinstance(apps, list) else set()
    return mode, names or {"firefox.exe"}


def jv_watch_winapi():
    """Window helper (Windows only, else None): list the windows of some programs, hide / show / minimise / close one."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        import types
        from ctypes import wintypes
        u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
        k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        k32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        u32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        u32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        u32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        u32.IsWindowVisible.argtypes = [wintypes.HWND]
        u32.IsIconic.argtypes = [wintypes.HWND]
        u32.IsWindow.argtypes = [wintypes.HWND]
        u32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        cache = {"t": 0.0, "pid": {}}
        proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        class PE32(ctypes.Structure):
            _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                        ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                        ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                        ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                        ("szExeFile", ctypes.c_wchar * 260)]
        k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        k32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PE32)]
        k32.Process32FirstW.restype = wintypes.BOOL
        k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PE32)]
        k32.Process32NextW.restype = wintypes.BOOL
        k32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        k32.TerminateProcess.restype = wintypes.BOOL

        def kill(names):
            """Ends every running process whose program name is in 'names' (TerminateProcess: instant, no 'save?' question).
            Only processes of the same user can be ended. Returns how many were ended."""
            h = k32.CreateToolhelp32Snapshot(2, 0)                         # TH32CS_SNAPPROCESS
            if not h or h == ctypes.c_void_p(-1).value:
                return 0
            pids = []
            try:
                e = PE32()
                e.dwSize = ctypes.sizeof(PE32)
                ok = k32.Process32FirstW(h, ctypes.byref(e))
                while ok:
                    if e.szExeFile.lower() in names:
                        pids.append(e.th32ProcessID)
                    ok = k32.Process32NextW(h, ctypes.byref(e))
            finally:
                k32.CloseHandle(h)
            n = 0
            for pid in pids:
                ph = k32.OpenProcess(0x0001, False, pid)                   # PROCESS_TERMINATE
                if ph:
                    if k32.TerminateProcess(ph, 1):
                        n += 1
                    k32.CloseHandle(ph)
            return n

        def exe_of(hwnd):
            pid = wintypes.DWORD(0)
            u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in cache["pid"]:
                return cache["pid"][pid.value]
            name = ""
            h = k32.OpenProcess(0x1000, False, pid.value)          # PROCESS_QUERY_LIMITED_INFORMATION
            if h:
                buf = ctypes.create_unicode_buffer(1024)
                size = wintypes.DWORD(1024)
                if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                    name = os.path.basename(buf.value).lower()
                k32.CloseHandle(h)
            cache["pid"][pid.value] = name
            return name

        def windows(names, visible=True):
            if time.time() - cache["t"] > 20:                      # process ids get reused: forget the names now and then
                cache["pid"].clear()
                cache["t"] = time.time()
            found = []

            def each(hwnd, _):
                if bool(u32.IsWindowVisible(hwnd)) == visible and (visible or u32.GetWindowTextLengthW(hwnd)):
                    if exe_of(hwnd) in names:
                        found.append(hwnd)
                return True
            u32.EnumWindows(proc(each), 0)
            return found
        return types.SimpleNamespace(
            windows=windows,
            kill=kill,
            hide=lambda h: u32.ShowWindow(h, 0),                   # SW_HIDE
            show=lambda h: u32.ShowWindow(h, 5),                   # SW_SHOW
            minimize=lambda h: u32.ShowWindow(h, 6),               # SW_MINIMIZE
            close=lambda h: u32.PostMessageW(h, 0x0010, 0, 0),     # WM_CLOSE: the polite way, the program may ask to save
            alive=lambda h: bool(u32.IsWindow(h)),
            iconic=lambda h: bool(u32.IsIconic(h)))
    except Exception:
        return None


def jv_watch_shield_step(api, mode, apps, present, state, now=None):
    """One tick of the shield. state = {'hidden': set of handles, 'sent': {handle: time}}. Returns how many processes were
    ended (mode 'kill') or windows hidden / minimised / asked to close now (or brought back, as a negative number)."""
    now = time.time() if now is None else now
    n = 0
    if state["hidden"] and (not present or mode != "hide"):       # nobody is watching (or another mode): give them back
        for h in list(state["hidden"]):
            if api.alive(h):
                api.show(h)
                n -= 1
            state["hidden"].discard(h)
    if present and mode == "kill":                                 # no hiding, no asking: the program is ended on the spot
        n += api.kill(apps)
    elif present and mode in ("hide", "minimize", "close"):
        for h in api.windows(apps):
            if mode == "hide":
                api.hide(h)
                state["hidden"].add(h)
                n += 1
            elif mode == "minimize":
                if not api.iconic(h):
                    api.minimize(h)
                    n += 1
            elif now - state["sent"].get(h, 0) > 3:                # 'close': ask again only every 3 s
                api.close(h)
                state["sent"][h] = now
                n += 1
        if len(state["sent"]) > 200:
            state["sent"].clear()
    return n


def jv_watch_shield_loop(stop):
    """Runs next to the watcher (Jarvis open) and inside the background guard. It sleeps on JV_WATCH['wake']: the watcher
    wakes it the moment it sees a viewer, then it re-checks the windows every 0.05 s for as long as somebody is watching."""
    st = JV_WATCH
    api = st["api"] = st["api"] or jv_watch_winapi()
    if api is None:
        return
    mode, apps, t_cfg, quiet = "kill", {"firefox.exe"}, 0.0, False
    while not stop.is_set():
        try:
            if time.time() - t_cfg > 1:                            # settings are re-read every second ('watch shield ...' is live)
                mode, apps = jv_watch_shield_cfg(jv_watch_cfg())
                quiet = bool(st["daemon"] and jv_watch_beat_alive("jarvis"))      # Jarvis open -> Jarvis does it, the guard stays out
                t_cfg = time.time()
            present = jv_watch_present() and not quiet
            with st["shield_lock"]:
                n = jv_watch_shield_step(api, mode, apps, present, st["shield"])
            if n > 0:
                jv_upd_log(f"screen watch shield: {mode} {n} item(s) of {', '.join(sorted(apps))}")
            busy = present or bool(st["shield"]["hidden"])
        except Exception:
            busy = False                                           # the shield never dies because of one bad tick
        st["wake"].wait(JV_SHIELD_TICK if busy else 0.25)          # idle: sleeps (and is woken at once by a sighting)
        st["wake"].clear()


def jv_watch_shield_restore(everything=False):
    """Brings back what the shield hid. everything=True also shows hidden WINDOWS WITH A TITLE of the shielded programs
    that this process did not hide (e.g. the guard died while Firefox was hidden). Returns how many were shown."""
    st = JV_WATCH
    api = st["api"] = st["api"] or jv_watch_winapi()
    if api is None:
        return 0
    with st["shield_lock"]:
        n = -jv_watch_shield_step(api, "off", set(), False, st["shield"])
        if everything:
            for h in api.windows(jv_watch_shield_cfg(jv_watch_cfg())[1], visible=False):
                api.show(h)
                n += 1
    return n


def jv_watch_shield_cmd(rest, cfg):
    word = rest[0].lower() if rest else ""
    mode, apps = jv_watch_shield_cfg(cfg)
    if not word:
        jarvis_say(f"The shield is {'OFF' if mode == 'off' else 'ON'}, sir: while someone is watching, I "
                   + ("END the programs " if mode == "kill" else f"{mode} the windows of ") + ", ".join(sorted(apps)) + ".")
        out("  watch shield kill | hide | minimize | close | off   what to do (default: kill = end the program at once)", GRAY)
        out("  watch shield add <program.exe> | del <program.exe>   which programs (default: firefox.exe)", GRAY)
        out("  watch shield show                               bring the hidden windows back right now", GRAY)
        out()
    elif word in JV_SHIELD_MODES:
        cfg["shield_mode"] = word
        if word != "hide":
            jv_watch_shield_restore()
        jarvis_say(f"Shield mode: {word}, sir." + ("" if jv_watch_save(cfg) else " (could not save the setting)"))
    elif word in ("show", "restore"):
        n = jv_watch_shield_restore(everything=True)
        jarvis_say(f"{n} window(s) brought back, sir." if n else "There was nothing hidden, sir.")
    elif word in ("add", "del", "remove") and len(rest) >= 2:
        exe = rest[1].lower() if rest[1].lower().endswith(".exe") else rest[1].lower() + ".exe"
        if not re.fullmatch(r"[\w .+-]{1,60}\.exe", exe):
            jarvis_say("That is not a program name, sir (example: firefox.exe).")
            return
        cur = set(apps)
        cur.add(exe) if word == "add" else cur.discard(exe)
        cfg["shield_apps"] = sorted(cur) or ["firefox.exe"]
        jarvis_say(f"Shielded programs: {', '.join(cfg['shield_apps'])}, sir." + ("" if jv_watch_save(cfg) else " (could not save)"))
    else:
        jarvis_say("Try:  watch shield | hide | minimize | close | off | show | add <program.exe> | del <program.exe>")


# ---------------- the background guard: watches even when Jarvis is closed ----------------
# A second, tiny copy of the same watcher runs with NO console window (pythonw), started at every Windows login
# by one file in your Startup folder. It uses the very same read-only look and the same WARNING window.
# While Jarvis is open Jarvis does the alerting (and pauses itself), so you never get two windows: the guard stays quiet.
# It is yours to control:  watch guard on | off | start | stop.  Everything lives in jarvis_update/ and the Startup folder.
JV_GUARD_NAME = "JarvisScreenWatch.vbs"


def jv_watch_beat(name, interval, closed=False):
    """Heartbeat file jarvis_update/<name>.hb : 'unix-time period'. Written at most once a second; closed=True writes an
    already-old time (and is never skipped)."""
    now = time.time()
    if not closed and now - JV_WATCH["beat_t"].get(name, 0.0) < 1.0:
        return
    JV_WATCH["beat_t"][name] = now
    try:
        with open(os.path.join(jv_upd_sub("."), name + ".hb"), "w", encoding="utf-8") as f:
            f.write(f"{0 if closed else now:.0f} {max(1, int(interval + 0.999))}")
    except OSError:
        pass


def jv_watch_beat_alive(name):
    """True when <name>.hb is fresh (written within about two of its own periods, 5 s for the fast look)."""
    try:
        with open(os.path.join(jv_upd_dir(), name + ".hb"), encoding="utf-8") as f:
            t, iv = f.read().split()[:2]
        return time.time() - float(t) < 2 * max(int(iv), 1) + 3
    except (OSError, ValueError):
        return False


def jv_watch_startup_file():
    base = os.environ.get("APPDATA") or ""
    return os.path.join(base, "Microsoft", "Windows", "Start Menu", "Programs", "Startup", JV_GUARD_NAME) if base else ""


def jv_watch_guard_installed():
    p = jv_watch_startup_file()
    return bool(p) and os.path.isfile(p)


def jv_watch_pythonw():
    exe = sys.executable or "python"
    d, b = os.path.split(exe)
    w = os.path.join(d, "pythonw.exe")
    return w if b.lower() == "python.exe" and os.path.isfile(w) else exe


def jv_watch_guard_command():
    return [jv_watch_pythonw(), os.path.abspath(__file__), "--watch-daemon"]


def jv_watch_guard_install():
    """Writes the one-line launcher into the Startup folder. Returns '' or an error text."""
    path = jv_watch_startup_file()
    if os.name != "nt" or not path:
        return "this only works on Windows"
    cmd = jv_watch_guard_command()
    vbs = 'CreateObject("WScript.Shell").Run """' + cmd[0] + '"" ""' + cmd[1] + '"" ' + cmd[2] + '", 0, False\r\n'
    try:
        with open(path, "w", encoding="utf-16") as f:
            f.write("' Jarvis screen watch guard (remove it with:  watch guard off)\r\n" + vbs)
        return ""
    except OSError as e:
        return str(e)[:200]


def jv_watch_guard_uninstall():
    path = jv_watch_startup_file()
    try:
        if path and os.path.isfile(path):
            os.remove(path)
        return ""
    except OSError as e:
        return str(e)[:200]


def jv_watch_guard_start():
    """Starts the guard now (hidden, detached from this console). Returns '' or an error text."""
    if os.name != "nt":
        return "this only works on Windows"
    if jv_watch_beat_alive("guard"):
        return ""
    try:
        stop = os.path.join(jv_upd_dir(), "guard.stop")
        if os.path.isfile(stop):
            os.remove(stop)
        subprocess.Popen(jv_watch_guard_command(), cwd=os.path.dirname(os.path.abspath(__file__)), close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=0x00000008 | 0x00000200 | 0x08000000)   # DETACHED | NEW_PROCESS_GROUP | NO_WINDOW
        return ""
    except OSError as e:
        return str(e)[:200]


def jv_watch_guard_stop():
    """Asks a running guard to quit (it looks for the flag every cycle). True when one was running."""
    if not jv_watch_beat_alive("guard"):
        return False
    try:
        with open(os.path.join(jv_upd_sub("."), "guard.stop"), "w", encoding="utf-8") as f:
            f.write("stop")
        return True
    except OSError:
        return False


def jv_watch_daemon(max_loops=None):
    """The background guard itself:  pythonw pwsh.py --watch-daemon   (no console, no Jarvis)."""
    import io
    if sys.stdout is None:                               # pythonw has no console streams
        sys.stdout = io.StringIO()
    if sys.stderr is None:
        sys.stderr = io.StringIO()
    st = JV_WATCH
    st["daemon"] = True
    if jv_watch_beat_alive("guard"):
        return                                           # another guard is already running
    stop = os.path.join(jv_upd_dir(), "guard.stop")
    try:
        if os.path.isfile(stop):
            os.remove(stop)
    except OSError:
        pass
    jv_upd_log("screen watch guard started (background)")
    threading.Thread(target=jv_watch_warm, daemon=True).start()
    threading.Thread(target=jv_watch_shield_loop, args=(st["stop"],), daemon=True).start()
    n = 0
    while max_loops is None or n < max_loops:
        n += 1
        try:
            cfg = jv_watch_cfg_cached()
            st["interval"] = jv_watch_interval(cfg)
            st["on"] = bool(cfg.get("on", True))
            jv_watch_beat("guard", st["interval"])
            if os.path.isfile(stop):
                try:
                    os.remove(stop)
                except OSError:
                    pass
                break
            if st["on"]:
                items = jv_watch_publish(jv_watch_scan())
                tags = {i["tag"] for i in items}
                new = tags - st["seen"]
                st["seen"] = tags
                if new and not st["alert"] and not jv_watch_beat_alive("jarvis"):     # Jarvis open -> Jarvis alerts
                    jv_watch_alert(items)
            else:
                st["last"] = []
        except Exception:
            pass                                         # the guard never dies because of one bad reading
        if max_loops is None:
            st["stop"].wait(max(st["interval"], 2.0) if st["slow"] else st["interval"])
    st["stop"].set()
    st["wake"].set()
    jv_watch_shield_restore()                            # the guard is closing: nothing stays hidden
    jv_watch_beat("guard", 0, closed=True)
    jv_upd_log("screen watch guard stopped")


def jv_watch_guard_cli(remove=False):
    """pwsh.py --guard-install / --guard-remove: turns the guard on or off WITHOUT opening Jarvis (used by the start.bat menu: Install Guard / Delete Guard).
    Returns the exit code."""
    if os.name != "nt":
        print("The guard works only on Windows.")
        return 1
    if remove:
        stopped = jv_watch_guard_stop()
        err = jv_watch_guard_uninstall()
        print(("Guard removed: it will not start with Windows any more." + (" It was stopped." if stopped else "")) if not err
              else "Could not remove the guard: " + err)
    else:
        err = jv_watch_guard_install() or jv_watch_guard_start()
        print("Guard installed and running. From now on it starts with Windows, even if Jarvis is never opened." if not err
              else "Could not install the guard: " + err)
    return 1 if err else 0


def jv_watch_guard_cmd(rest, cfg):
    word = rest[0].lower() if rest else ""
    if os.name != "nt":
        jarvis_say("The background guard works only on Windows, sir.")
    elif word in ("on", "install"):
        err = jv_watch_guard_install() or jv_watch_guard_start()
        jarvis_say("The guard is on, sir: it starts with Windows and watches even when I am closed." if not err
                   else f"I could not turn the guard on: {err}")
    elif word in ("off", "remove", "uninstall"):
        stopped = jv_watch_guard_stop()
        err = jv_watch_guard_uninstall()
        jarvis_say("The guard is off, sir: it will not start with Windows any more." + (" It was stopped." if stopped else "")
                   if not err else f"I could not remove the guard: {err}")
    elif word == "start":
        err = jv_watch_guard_start()
        jarvis_say("The guard is running, sir." if not err else f"I could not start the guard: {err}")
    elif word == "stop":
        jarvis_say("Stopping the guard for now, sir (it will start again with Windows)." if jv_watch_guard_stop()
                   else "The guard was not running, sir.")
    else:
        out(f"  guard (always on, even when Jarvis is closed): {'RUNNING' if jv_watch_beat_alive('guard') else 'not running'}", YELLOW)
        out(f"  starts with Windows : {'yes' if jv_watch_guard_installed() else 'no'}", GRAY)
        out("  watch guard on | off | start | stop", GRAY)
        out()


# ---------------- the command ----------------
@cmdlet("Screen-Watch", "watch", "screenwatch", group="Assistant", usage="""watch                          status (on by default, Windows only)
watch on | off                 switch the watch on or off (remembered)
watch now                      look right now and say what was found
watch test                     show the WARNING window as if someone were watching (nothing is really connected)
watch interval <seconds>       how often to look (0.2-300, default 0.25; decimals ok)
watch know                     list the people you know
watch know add <name> <ip-or-user>     e.g. watch know add Mario 192.168.1.20
watch know del <name>
watch mail to=<you@x.com> host=<smtp.x.com> [port=465] [user=<login>] [passenv=<ENV_VAR_WITH_PASSWORD>]
watch mail off | test
watch guard                    always-on guard: status (it watches even when Jarvis is closed)
watch guard on | off           start it with Windows (and now) / remove it
watch guard start | stop       run it now / stop it until the next Windows login
watch shield                   Firefox shield: while someone watches, Firefox is ended at once (on by default)
watch shield kill | hide | minimize | close | off    what to do with it (default kill = ended at once)      watch shield show: bring hidden windows back
watch shield add <program.exe> | del <program.exe>    other programs to shield too
Read-only: it only reads the session list, open connections, process list and window titles.
On a sighting Jarvis pauses at its next output and a red WARNING window opens; ENTER resumes, F shows the
viewer a SIMULATED intrusion screen (text only). The pause always ends by itself after at most 15 minutes.
The shield is the one thing that acts on other programs: by default it ENDS Firefox at once (unsaved tabs are not saved by
Jarvis; Firefox's own session restore usually brings them back). Choose 'hide' to only take the windows off the screen
(they come back when the viewer leaves) or 'minimize' / 'close' / 'off'.""")
def jv_watch_cmd(args):
    """Notice who is watching the shared / remote screen: pauses Jarvis and opens a WARNING window."""
    CONTESTO["watchcmd"] = True
    try:
        jv_watch_cmd_run(args)
    finally:
        CONTESTO["watchcmd"] = False


def jv_watch_cmd_run(args):
    st = JV_WATCH
    cfg = jv_watch_cfg()
    word = args[0].lower() if args else ""
    rest = args[1:]
    if not word:
        jarvis_say(f"Screen watch is {'ON' if st['on'] else 'OFF'}, sir. I look every {st['interval']:g} s"
                   + ("." if os.name == "nt" else " (but only on Windows)."))
        out(f"  known people : {len(cfg.get('known') or {})}", GRAY)
        out(f"  e-mail alert : {'to ' + cfg['mail_to'] if cfg.get('mail_to') else 'not set up'}", GRAY)
        out(f"  seen now     : {len(st['last'])} item(s)", GRAY)
        if st["slow"] is not None:
            out(f"  look method  : {'commands (slow: qwinsta / netstat / tasklist)' if st['slow'] else 'Windows API (instant)'}", GRAY)
        out()
    elif word in ("on", "off"):
        st["on"] = word == "on"
        cfg["on"] = st["on"]
        st["seen"] = set()
        jarvis_say(f"Screen watch {'on' if st['on'] else 'off'}, sir." + ("" if jv_watch_save(cfg) else " (could not save the setting)"))
    elif word == "now":
        t0 = time.perf_counter()
        items = jv_watch_publish(jv_watch_scan())
        out(f"  (looked in {(time.perf_counter() - t0) * 1000:.0f} ms)", GRAY)
        if not items:
            jarvis_say("Nobody is watching the screen that I can see, sir." + ("" if os.name == "nt" else " (Windows only.)"))
        for line in jv_watch_lines(items)[2:]:
            out(line, YELLOW)
        out()
    elif word == "test":
        jarvis_say("Showing the warning window as a test, sir.")
        jv_watch_alert([{"tag": "test", "what": "TEST - nothing is really connected", "remote": "", "user": "", "name": ""}])
        time.sleep(0.3)                       # the pause starts at the next output: wait here until the window is closed
        while not JV_RUN.wait(0.2):
            pass
    elif word == "interval" and rest and re.fullmatch(r"\d+(?:[.,]\d+)?", rest[0]):
        cfg["interval"], cfg["interval_v"] = float(rest[0].replace(",", ".")), 2
        st["interval"] = jv_watch_interval(cfg)
        jv_watch_save(cfg)
        jarvis_say(f"I will look every {st['interval']:g} seconds, sir." + (" (Not faster than every 2 s while the instant look is "
                   "unavailable on this PC.)" if st["slow"] else ""))
    elif word == "know":
        known = cfg.get("known") if isinstance(cfg.get("known"), dict) else {}
        if rest and rest[0].lower() == "add" and len(rest) >= 3:
            known.setdefault(rest[1], [])
            for ident in rest[2:]:
                if ident not in known[rest[1]]:
                    known[rest[1]].append(ident)
            cfg["known"] = known
            jarvis_say(f"{rest[1]} is now one of the people I know, sir." + ("" if jv_watch_save(cfg) else " (could not save)"))
        elif rest and rest[0].lower() in ("del", "remove") and len(rest) >= 2:
            if known.pop(rest[1], None) is None:
                jarvis_say(f"I do not know anybody called {rest[1]}, sir.")
            else:
                cfg["known"] = known
                jv_watch_save(cfg)
                jarvis_say(f"{rest[1]} removed, sir.")
        else:
            if not known:
                jarvis_say("Nobody yet, sir. Add one with:  watch know add <name> <ip-or-user>")
            for name, ids in known.items():
                out(f"  {name}: {', '.join(map(str, ids))}", YELLOW)
            out()
    elif word == "mail":
        jv_watch_mail_cmd(rest, cfg)
    elif word == "guard":
        jv_watch_guard_cmd(rest, cfg)
    elif word in ("shield", "firefox"):
        jv_watch_shield_cmd(rest, cfg)
    else:
        jarvis_say("Try:  watch | watch on | watch off | watch now | watch test | watch know | watch guard | watch mail ...  (help watch)")


def jv_watch_mail_cmd(rest, cfg):
    if rest and rest[0].lower() == "off":
        for k in ("mail_to", "smtp_host", "smtp_port", "smtp_user", "password_env"):
            cfg.pop(k, None)
        jv_watch_save(cfg)
        jarvis_say("E-mail alerts off, sir.")
    elif rest and rest[0].lower() == "test":
        err = jv_watch_mail("JARVIS: test", "Screen watch e-mail test.", cfg)
        jarvis_say("The test e-mail was sent, sir." if not err else f"The e-mail failed: {err}")
    elif rest:
        new = {}
        for a in rest:
            k, _, v = a.partition("=")
            k = k.lower()
            if k == "to" and re.fullmatch(r"[^@\s<>,;]+@[^@\s<>,;]+\.[^@\s<>,;]+", v):
                new["mail_to"] = v
            elif k == "host" and re.fullmatch(r"[A-Za-z0-9.-]+", v):
                new["smtp_host"] = v
            elif k == "port" and v.isdigit():
                new["smtp_port"] = int(v)
            elif k == "user" and re.fullmatch(r"[^\s<>,;]+", v):
                new["smtp_user"] = v
            elif k == "passenv" and re.fullmatch(r"\w+", v):
                new["password_env"] = v
            else:
                jarvis_say(f"I did not understand '{a}', sir.")
                return
        cfg.update(new)
        jv_watch_save(cfg)
        need = [k for k in ("mail_to", "smtp_host") if not cfg.get(k)]
        jarvis_say("E-mail settings saved, sir." + (f" Still missing: {', '.join(need)}." if need else
                   " The password is read from the environment variable you gave as passenv; try  watch mail test."))
    else:
        jarvis_say("watch mail to=<you@x.com> host=<smtp.x.com> [port=465] [user=<login>] [passenv=<ENV_VAR>]  |  off  |  test")
