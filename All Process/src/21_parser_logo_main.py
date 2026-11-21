# ---------------- PARSER E LOOP ----------------
def tokenize(riga):
    token, cur, q, ha = [], "", None, False
    for ch in riga:
        if q:
            if ch == q:
                q = None
            else:
                cur += ch
        elif ch in "'\"":
            q, ha = ch, True
        elif ch.isspace():
            if cur or ha:
                token.append(cur)
            cur, ha = "", False
        else:
            cur += ch
    if cur or ha:
        token.append(cur)
    return token


def esegui(riga):
    CONTESTO["riga"] = riga
    token = tokenize(riga)
    if not token:
        return
    nome = token[0]
    fn = CMDLETS.get(nome.lower())
    if nome.lower() in ("help", "get-help", "man") and re.search(JV_NAMED_RE, riga, re.I):
        rest = [a for a in token[1:] if not re.fullmatch(JV_NAMED_RE, a, re.I)]
        if rest and not all(a.startswith("-") or a.lower() in CMDLETS for a in rest) and jarvis_interpret(riga):
            return                          # 'help me jarvis': a request, not a help topic
    if fn is not None and nome.lower() not in JV_NOT_NAMED_CMDS and re.search(JV_NAMED_RE, riga, re.I):
        if jarvis_interpret(riga):          # 'jarvis' somewhere in the line: Jarvis answers first
            return
    if fn is None:
        if jarvis_interpret(riga):
            return
        out(f"{nome} : The term '{nome}' is not recognized as the name of a cmdlet, "
            "function, script file, or operable program. Check the spelling of the "
            "name, or if a path was included, verify that the path is correct and "
            "try again.", RED)
        out("At line:1 char:1", RED)
        out(f"+ {riga.strip()}", RED)
        out(f"+ {'~' * len(riga.strip())}", RED)
        out(f"    + CategoryInfo          : ObjectNotFound: ({nome}:String) [], "
            "CommandNotFoundException", RED)
        out("    + FullyQualifiedErrorId : CommandNotFoundException", RED)
        out()
        close = difflib.get_close_matches(nome.lower(), list(CMDLETS), n=1, cutoff=0.6)
        if close:
            jarvis_say(f"Did you mean '{close[0]}', sir?")
            out()
        return
    try:
        fn(token[1:])
    except SystemExit:
        raise
    except KeyboardInterrupt:
        out()
    except Exception as e:  # un'estensione che si rompe non deve uccidere la shell
        out(f"{nome} : {e}", RED)
        out()


def carica_estensioni():
    cartella = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ext")
    if not os.path.isdir(cartella):
        return
    CONTESTO["ext"] = True   # commands registered from here on are listed as Extensions
    api = dict(cmdlet=cmdlet, out=out, error=error, parse=parse, CMDLETS=CMDLETS, CONTESTO=CONTESTO,
               TEXT=TEXT, YELLOW=YELLOW, RED=RED, GREEN=GREEN, CYAN=CYAN, GRAY=GRAY)
    for f in sorted(os.listdir(cartella)):
        if f.endswith(".py") and not f.startswith("_"):
            try:
                runpy.run_path(os.path.join(cartella, f), init_globals=api)
            except Exception as e:
                out(f"Errore caricando ext/{f}: {e}", RED)


def jv_hl(buf):
    """Colors of the line while you type: the command yellow, the word jarvis cyan, quoted text blue, the rest normal."""
    def words(t, back):
        return re.sub(r"(?i)\bjarvis\b", lambda x: CYAN + x.group(0) + back, t)
    m = re.match(r"(\s*)(\S+)", buf)
    res, i, q, run = "", 0, None, ""
    if m:
        res, i = m.group(1) + YELLOW + words(m.group(2), YELLOW) + TEXT, m.end()
    while i < len(buf):
        c = buf[i]
        if q:
            res += c
            if c == q:
                res, q = res + TEXT, None
        elif c in "\"'":
            res, run, q = res + words(run, TEXT) + BLUE + c, "", c
        else:
            run += c
        i += 1
    return res + words(run, TEXT) + TEXT


JV_HIST = []


def jv_getkey():
    """One key: a character, or 'left' 'right' 'up' 'down' 'home' 'end' 'del' 'enter' 'bs' 'eof'."""
    if os.name == "nt":
        import msvcrt
        c = msvcrt.getwch()
        if c in ("\x00", "\xe0"):
            return {"K": "left", "M": "right", "H": "up", "P": "down", "G": "home", "O": "end", "S": "del"}.get(msvcrt.getwch(), "")
        if c == "\x03":
            raise KeyboardInterrupt
        return {"\r": "enter", "\n": "enter", "\x08": "bs", "\x1a": "eof", "\x01": "home", "\x05": "end"}.get(c, c)
    import select
    fd = sys.stdin.fileno()
    dec = codecs.getincrementaldecoder("utf-8")("replace")
    while True:
        b = os.read(fd, 1)
        if not b:
            return "eof"
        if b == b"\x1b":
            if not select.select([fd], [], [], 0.04)[0]:
                return ""
            if os.read(fd, 1) not in (b"[", b"O"):
                return ""
            seq = b""
            while True:
                x = os.read(fd, 1)
                seq += x
                if not x or 0x40 <= x[0] <= 0x7e:
                    break
            return {b"A": "up", b"B": "down", b"C": "right", b"D": "left", b"H": "home", b"F": "end",
                    b"3~": "del", b"1~": "home", b"7~": "home", b"4~": "end", b"8~": "end"}.get(seq, "")
        if b in (b"\r", b"\n"):
            return "enter"
        if b in (b"\x7f", b"\x08"):
            return "bs"
        if b == b"\x04":
            return "eof"
        if b == b"\x01":
            return "home"
        if b == b"\x05":
            return "end"
        c = dec.decode(b)
        if c:
            return c


def leggi_riga():
    """The prompt with live colors (needs a real terminal; otherwise plain input())."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return input(prompt())
    base = f"PS {os.getcwd()}> "
    buf, pos, hist, draft = "", 0, len(JV_HIST), ""
    old = None
    if os.name != "nt":
        import termios
        import tty
        old = termios.tcgetattr(sys.stdin.fileno())
        tty.setcbreak(sys.stdin.fileno())

    def draw():
        col = len(base) + pos
        sys.stdout.write("\r" + TEXT + base + jv_hl(buf) + "\x1b[K\r" + (f"\x1b[{col}C" if col else ""))
        sys.stdout.flush()
    try:
        draw()
        while True:
            k = jv_getkey()
            if k == "enter":
                break
            if k == "eof":
                if not buf:
                    sys.stdout.write("\n")
                    raise EOFError
            elif k == "bs":
                if pos:
                    buf, pos = buf[:pos - 1] + buf[pos:], pos - 1
            elif k == "del":
                buf = buf[:pos] + buf[pos + 1:]
            elif k == "left":
                pos = max(0, pos - 1)
            elif k == "right":
                pos = min(len(buf), pos + 1)
            elif k == "home":
                pos = 0
            elif k == "end":
                pos = len(buf)
            elif k in ("up", "down"):
                if hist == len(JV_HIST):
                    draft = buf
                hist = max(0, hist - 1) if k == "up" else min(len(JV_HIST), hist + 1)
                buf = JV_HIST[hist] if hist < len(JV_HIST) else draft
                pos = len(buf)
            elif len(k) == 1 and k >= " ":
                buf, pos = buf[:pos] + k + buf[pos:], pos + 1
            draw()
    except KeyboardInterrupt:
        sys.stdout.write(TEXT + "\n")
        raise
    finally:
        if old is not None:
            import termios
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old)
    sys.stdout.write(TEXT + "\n")
    if buf.strip() and (not JV_HIST or JV_HIST[-1] != buf):
        JV_HIST.append(buf)
    return buf


def prompt():
    base = f"PS {os.getcwd()}> "
    giallo = f"\x01{YELLOW}\x02" if HAS_READLINE else YELLOW
    testo = f"\x01{TEXT}\x02" if HAS_READLINE else TEXT
    return testo + base + giallo


# ---------------- START-UP LOGO: the spinning globe with J.A.R.V.I.S. fixed underneath ----------------
# Same globe as 'jarvis be online' (jv_globe_rows). It only plays on a real terminal, so the start test of an
# update (which reads the output through a pipe) sees nothing new and the start speed is not affected.
def jv_logo_bar(progress, cols, width=24):
    """The small loading bar under the title:  [██████░░░░░░░░░░░░░░░░░░]  42%   (progress 0..1)"""
    p = max(0.0, min(1.0, progress))
    full = int(round(width * p))
    cells = [("[", 0.5)] + [("\u2588", 0.95)] * full + [("\u2591", 0.3)] * (width - full) + [("]", 0.5)]
    cells += [(c, 0.75) for c in f" {int(round(p * 100)):3d}%"]
    pad = [(" ", 0.0)] * max(0, (cols - len(cells)) // 2)
    return jv_paint(pad + cells, "cyan")


def jv_logo_lines(R, cols, angle, scan=-1, progress=None):
    pad = [(" ", 0.0)] * max(0, (cols - (4 * R + 1)) // 2)
    lines = [jv_paint(pad + row, "cyan") for row in jv_globe_rows(R, angle, scan)]
    title = "J.A.R.V.I.S."
    lines.append("")
    lines.append(jv_paint([(c, 0.95) for c in " " * max(0, (cols - len(title)) // 2) + title], "cyan"))
    if progress is not None:                                    # start-up only: a loading bar under the title
        lines.append("")
        lines.append(jv_logo_bar(progress, cols))
    return lines


def jv_logo_show():
    """Start-up: the window goes full screen, the globe spins in the middle of it, then shrinks and rises to the top
    while the window settles. Needs a real terminal (a pipe, e.g. the update start test, sees nothing of this)."""
    if not sys.stdout.isatty():
        return
    try:
        before = shutil.get_terminal_size((100, 30))
    except (OSError, ValueError):
        before = os.terminal_size((100, 30))
    if jv_launch_maximize_self():
        end = time.time() + 1.2                                 # wait until the console really has the new size
        while time.time() < end and shutil.get_terminal_size((100, 30)) == before:
            time.sleep(0.05)
    try:
        cols, rows = shutil.get_terminal_size((100, 30))
    except (OSError, ValueError):
        cols, rows = 100, 30
    Rs = 5 if rows >= 28 else 4 if rows >= 22 else 0
    if Rs == 0 or cols < 4 * Rs + 6:                            # a very small window: just the name
        out("J.A.R.V.I.S.", CYAN)
        out()
        return
    Rb = max(Rs, min((rows - 8) // 2, (cols - 6) // 4, 11))
    total = 2 * Rb + 1 + 2 + 2                                  # globe rows + blank + title + blank + loading bar
    pad0 = max(0, (rows - 1 - total) // 2)
    screen = pad0 + total
    state = {"first": True}

    def draw(R, pad, angle, scan=-1, progress=None):
        lines = [""] * pad + jv_logo_lines(R, cols, angle, scan, progress)
        lines += [""] * (screen - len(lines))
        if not state["first"]:
            sys.stdout.write("\x1b[%dA" % screen)
        state["first"] = False
        sys.stdout.write("".join(l + "\x1b[K\n" for l in lines[:screen]))
        sys.stdout.flush()

    sys.stdout.write("\x1b[?25l\x1b[2J\x1b[H")
    angle = 0.0
    try:
        try:
            spin = 34
            for i in range(spin):                               # 1) full screen, the globe spins in the middle
                draw(Rb, pad0, angle, scan=i % (2 * Rb + 1), progress=0.7 * (i + 1) / spin)
                angle += 0.07 + 0.2 * (1 - i / spin)
                time.sleep(0.05)
            steps = 22
            for i in range(1, steps + 1):                       # 2) it shrinks and rises to the top
                t = i / steps
                t = t * t * (3 - 2 * t)
                draw(round(Rb + (Rs - Rb) * t), round(pad0 * (1 - t)), angle, progress=0.7 + 0.3 * i / steps)
                angle += 0.06
                time.sleep(0.04)
        except KeyboardInterrupt:
            pass
    finally:
        sys.stdout.write("\x1b[?25h" + TEXT)
        sys.stdout.flush()
    sys.stdout.write("\x1b[2J\x1b[H")                           # 3) the same picture, now as the top of the window
    for l in jv_logo_lines(Rs, cols, angle):
        sys.stdout.write(l + "\x1b[K\n")
    sys.stdout.write(TEXT)
    sys.stdout.flush()
    out()


def main():
    if "--watch-daemon" in sys.argv[1:]:          # the background guard: no console, no Jarvis (see watch guard)
        jv_watch_daemon()
        return
    if "--guard-install" in sys.argv[1:] or "--guard-remove" in sys.argv[1:]:     # one double click, Jarvis stays closed
        sys.exit(jv_watch_guard_cli("--guard-remove" in sys.argv[1:]))
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    os.system("")  # abilita i codici ANSI sul terminale di Windows
    sys.stdout.write("\x1b]0;Jarvis PowerShell\x07" + BG + TEXT + "\x1b[2J\x1b[H")
    jv_logo_show()
    out("Jarvis PowerShell")
    out("Copyright (C) DreeMux. Licensed under the GNU GPL v3 or later.")
    out()
    carica_estensioni()
    jv_watch_start()
    jarvis_greeting()
    try:
        while True:
            try:
                riga = leggi_riga()
            except EOFError:
                break
            except KeyboardInterrupt:
                out()
                continue
            sys.stdout.write(TEXT)
            esegui(riga)
    except SystemExit:
        pass
    jv_watch_stop()
    jv_voice_flush()
    sys.stdout.write("\x1b[0m\x1b[2J\x1b[H")


if __name__ == "__main__":
    main()
