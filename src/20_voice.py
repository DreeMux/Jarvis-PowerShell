# ---------------- VOICE (optional): JARVIS speaks only when you ask ----------------
# 'voice on' makes JARVIS read his own lines aloud, 'voice off' silences him. Every session starts SILENT.
# It uses pyttsx3 (pip install pyttsx3): free, local and offline - it only talks to the speech engine of this PC
# (SAPI5 on Windows, NSSpeechSynthesizer on macOS, espeak on Linux). Nothing is recorded, saved or sent anywhere.
JV_VOICE = {"on": False, "q": None, "thread": None, "ready": None, "engine": None, "err": None,
            "name": "", "english": True}


def jv_voice_clean(msg):
    """The text to read aloud: no colour codes, file paths said as 'a file path', and not too long."""
    s = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", str(msg))
    s = re.sub(r"(?:[A-Za-z]:)?(?:[\\/][^\s\\/]+){2,}", "a file path", s)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > 280:
        cut = s[:280]
        end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
        s = cut[:end + 1] if end > 80 else cut.rsplit(" ", 1)[0]
    return s


def jv_voice_worker(st):
    """Runs in its own thread: the speech engine lives here, so a long sentence never freezes the prompt."""
    eng = None
    try:
        if os.name == "nt":
            try:
                import comtypes                         # the speech engine of Windows needs COM in this thread
                comtypes.CoInitialize()
            except Exception:
                pass
        import pyttsx3
        eng = pyttsx3.init()
        eng.setProperty("rate", 175)
        pick = None
        for v in eng.getProperty("voices") or []:       # JARVIS talks English: prefer an English voice
            blob = (str(getattr(v, "name", "")) + " " + str(getattr(v, "id", "")) + " "
                    + str(getattr(v, "languages", ""))).lower()
            if "english" in blob or "en-" in blob or "en_" in blob:
                pick = v
                break
        if pick is not None:
            eng.setProperty("voice", pick.id)
            st["name"] = str(getattr(pick, "name", "") or "")
        st["english"] = pick is not None
        st["engine"] = eng
    except Exception as e:                              # no pyttsx3, no speech engine, no audio device...
        st["err"] = str(e) or e.__class__.__name__
    st["ready"].set()
    if st["engine"] is None:
        return
    while True:
        text = st["q"].get()
        try:
            if text is None:
                return
            if st["on"]:
                eng.say(text)
                eng.runAndWait()
        except Exception as e:
            st["err"] = str(e) or e.__class__.__name__
        finally:
            st["q"].task_done()


def jv_voice_start():
    """Starts the speech engine the first time it is needed. True when it is ready."""
    st = JV_VOICE
    if st["thread"] is not None and st["thread"].is_alive() and st["engine"] is not None:
        return True
    st.update(q=queue.Queue(), ready=threading.Event(), engine=None, err=None, name="", english=True)
    th = threading.Thread(target=jv_voice_worker, args=(st,), name="jarvis-voice", daemon=True)
    st["thread"] = th
    th.start()
    st["ready"].wait(10)
    if st["engine"] is None:
        st["err"] = st["err"] or "the speech engine did not start in time"
        st["thread"] = None
        return False
    return True


def jv_voice_say(msg):
    """Called by every JARVIS line. Silent unless the voice was switched on."""
    st = JV_VOICE
    if not st["on"] or st["q"] is None:
        return
    text = jv_voice_clean(msg)
    if text:
        st["q"].put(text)


def jv_voice_flush(seconds=5):
    """On exit: let the last sentence finish (only when the voice is on)."""
    st = JV_VOICE
    if not st["on"] or st["q"] is None:
        return
    end = time.time() + seconds
    while st["q"].unfinished_tasks and time.time() < end:
        time.sleep(0.05)


def jv_voice_set(on):
    """Switch the voice on or off, and say so."""
    st = JV_VOICE
    if on:
        if st["on"]:
            jarvis_say("The voice is already on, sir.")
            return
        if not jv_voice_start():
            err = st["err"] or "unknown error"
            jarvis_say("I can't start the speech engine, sir, so I stay silent.")
            if "No module named" in err:
                out(f"  Missing: {safe(err)[:120]}", GRAY)
                if os.name == "nt":
                    out("  Install what it needs with:  pip install pyttsx3 pywin32 comtypes     (free, local, offline)", GRAY)
                else:
                    out("  Install it with:  pip install pyttsx3     (on Linux also: sudo apt install espeak-ng)", GRAY)
            else:
                out(f"  {safe(err)[:200]}", GRAY)
            out()
            return
        st["on"] = True
        jarvis_say("Voice enabled, sir. I will read my replies aloud until you say 'voice off'.")
        if not st["english"]:
            jarvis_say("There is no English voice on this PC, so I'm using the system default. "
                       "Windows: Settings > Time & language > Speech > Add voices.")
        out()
        return
    was = st["on"]
    st["on"] = False
    q = st["q"]
    if q is not None:                                   # forget whatever was still waiting to be said
        try:
            while True:
                q.get_nowait()
                q.task_done()
        except queue.Empty:
            pass
    if was and st["engine"] is not None:
        try:
            st["engine"].stop()
        except Exception:
            pass
    jarvis_say("Voice disabled, sir. Back to silent running." if was else "The voice is already off, sir.")
    out()


@cmdlet("Voice", "voce", group="Assistant", usage="""voice on      JARVIS reads his own lines aloud (needs:  pip install pyttsx3  - free, local, offline)
voice off     silent again: this is how every session starts
voice         shows whether the voice is on
(plain words work too: "jarvis voice on", "jarvis voce off", "jarvis be quiet")
Only the lines that start with JARVIS: are read; file paths are said as 'a file path'. Nothing is recorded or sent.""")
def jv_voice_cmd(args):
    """Switch JARVIS's spoken voice on or off (he is silent until you ask)."""
    flags, pos = parse(args)
    word = (pos[0] if pos else next(iter(sorted(flags)), "").lstrip("-")).lower()
    if word in ("on", "enable", "enabled", "attiva", "attivata", "start"):
        jv_voice_set(True)
    elif word in ("off", "disable", "disabled", "disattiva", "disattivata", "stop", "mute"):
        jv_voice_set(False)
    elif word in ("", "status", "stato"):
        if JV_VOICE["on"]:
            jarvis_say("Voice is ON, sir" + (f" ({safe(JV_VOICE['name'])})" if JV_VOICE["name"] else "")
                       + ". Say 'voice off' to silence me.")
        else:
            jarvis_say("Voice is OFF, sir: I stay silent until you say 'voice on'.")
        out()
    else:
        jarvis_say("Say 'voice on' or 'voice off', sir.")
        out()


def jv_voice_nl(t):
    """'jarvis voice on', 'voce off', 'be quiet', 'parla con me'... Only whole sentences, so nothing else is caught."""
    s = re.sub(r"[^a-z\u00e0-\u00ff0-9' ]+", " ", t.lower())
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"^(?:(?:please|pls|per favore|can you|could you|puoi|potresti)\s+)+", "", s)
    s = re.sub(r"\s+(?:now|ora|adesso|please|pls|per favore|sir|signore)$", "", s)
    if re.fullmatch(r"(?:voice|voce) (?:on|enabled?|attiva(?:ta)?)|(?:turn|switch|put) (?:the |my )?voice on|"
                    r"(?:enable|activate|attiva|accendi) (?:the |la )?voce|speak to me|talk to me|parlami|"
                    r"parla(?: con me)?|start (?:talking|speaking)", s):
        on = True
    elif re.fullmatch(r"(?:voice|voce) (?:off|disabled?|disattiva(?:ta)?)|(?:turn|switch|put) (?:the |my )?voice off|"
                      r"(?:disable|deactivate|disattiva|spegni) (?:the |la )?voce|stop (?:talking|speaking)|"
                      r"be (?:quiet|silent)|stai zitto|zitto|silenzio|smetti di parlare", s):
        on = False
    elif re.fullmatch(r"(?:voice|voce)(?: status| stato)?|is (?:the )?voice on|la voce [e\u00e8] attiva", s):
        CONTESTO["jv_nostore"] = True
        jv_voice_cmd([])
        return True
    else:
        return False
    CONTESTO["jv_nostore"] = True                       # 'again' must not flip the voice back and forth
    jv_voice_set(on)
    return True


# ======================= LAUNCHER (launch <script or program>) =======================
# Starts a LOCAL script or program with the standard library only: no shell, no administrator rights (a program
# that asks for them gets Windows' own prompt - I never elevate), nothing is installed, changed or downloaded.
# Named jv_launch_* so the update gate protects it exactly like the game launcher; it reuses jv_launch_blocked,
# so Windows system files are refused here too.
JV_LAUNCH_BAT_BAD = re.compile(r'[&|<>^%"!]')      # characters cmd.exe would read as commands, not as text


def jv_launch_plan(path, args, wait=None):
    """How 'launch' would start this path, WITHOUT starting anything. Returns a dict: full (absolute path),
    argv (None when it is a document or folder: those just open with their usual program), wait (True: I stay
    until it ends and its output appears here), why (the reason for a refusal, or None)."""
    full = os.path.abspath(os.path.expanduser(path))
    plan = {"full": full, "argv": None, "wait": False, "why": None}
    if not os.path.exists(full):
        plan["why"] = "that file or folder does not exist"
        return plan
    plan["why"] = jv_launch_blocked(full)
    if plan["why"]:
        return plan
    ext = os.path.splitext(full)[1].lower()
    argv, default_wait = None, False
    if os.path.isdir(full):
        pass
    elif ext == ".py":
        argv, default_wait = [sys.executable, "-u", full], True
    elif ext == ".ps1":
        exe = shutil.which("pwsh") or shutil.which("powershell")
        if not exe:
            plan["why"] = "PowerShell is not installed here"
            return plan
        argv, default_wait = [exe, "-NoProfile", "-File", full], True          # obeys YOUR execution policy
    elif ext in (".bat", ".cmd"):
        if os.name != "nt":
            plan["why"] = "batch files only run on Windows"
            return plan
        if any(JV_LAUNCH_BAT_BAD.search(a) for a in args):
            plan["why"] = "an argument has a character that cmd.exe would read as a command"
            return plan
        argv, default_wait = [full], True
    elif ext == ".sh" and os.name != "nt":
        argv, default_wait = ["sh", full], True
    elif (os.name == "nt" and ext in (".exe", ".com")) or (os.name != "nt" and os.path.isfile(full) and os.access(full, os.X_OK)):
        argv = [full]                                                         # a program: starts on its own
    if argv is None:
        if args:
            plan["why"] = "I can only pass arguments to scripts and programs"
        return plan
    plan["argv"] = argv + list(args)
    plan["wait"] = default_wait if wait is None else wait
    return plan


def jv_launch_script(path, args, wait=None):
    """'launch <file> [arguments]': scripts run here and I wait; programs start on their own; documents and
    folders open with their usual program (like 'jarvis open'). Returns True when something was started."""
    plan = jv_launch_plan(path, args, wait)
    full = plan["full"]
    name = safe(os.path.basename(full) or full)
    if plan["why"]:
        jarvis_say(f"I won't launch {name}, sir: {plan['why']}.")
        out()
        return False
    if plan["argv"] is None:
        jv_launch_file(full)                                                  # same safe path as 'jarvis open'
        return True
    import subprocess
    ack(f"Launching {name}" + (" and waiting for it to finish." if plan["wait"] else "."))
    out("  " + safe(" ".join([full] + list(args))), GRAY)
    kw = {"cwd": os.path.dirname(full)}
    if not plan["wait"]:
        if os.name == "nt":
            kw["creationflags"] = getattr(subprocess, "CREATE_NEW_CONSOLE", 0x10)      # its own window
        else:
            kw.update(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                      start_new_session=True)
    try:
        proc = subprocess.Popen(plan["argv"], **kw)                           # list of arguments: never a shell
    except OSError as e:
        if getattr(e, "winerror", None) == 740:
            jarvis_say(f"{name} needs administrator rights, sir. I never elevate: start it yourself with "
                       "'Run as administrator' if you really want it.")
        else:
            jarvis_say(f"It would not start, sir ({safe(e.strerror or e)}).")
        out()
        return False
    if not plan["wait"]:
        jarvis_say(f"{name} is running on its own now, sir (process {proc.pid}).")
        out()
        return True
    try:
        rc = proc.wait()
    except KeyboardInterrupt:                                                 # Ctrl+C: give it a moment, then stop it
        try:
            rc = proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                rc = proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                rc = proc.wait()
        sys.stdout.write(TEXT + "\n")
        jarvis_say(f"Stopped {name}, sir.")
        out()
        return True
    sys.stdout.write(TEXT)
    jarvis_say(f"{name} finished, sir." if rc == 0 else f"{name} ended with exit code {rc}, sir.")
    out()
    return True


@cmdlet("Launch", "Start-Script", group="Assistant", usage="""launch <file> [arguments]       start a local script or program
  launch "C:\\tools\\backup.py" --fast      .py runs with this Python: its output appears here and I wait for it
  launch .\\update.bat | .ps1 | .sh         other scripts run here too (PowerShell obeys your execution policy)
  launch "D:\\Apps\\tool.exe"               a program starts on its own (-Wait: stay until it ends)
  launch -Detach <script>                   a script runs in its own window and I don't wait
  launch <document or folder>               opens it with its usual program, like 'jarvis open'
No shell and no administrator rights: a program that asks for them gets Windows' own prompt, I never elevate.
Windows system files and folders are refused. Also: jarvis launch <file>""")
def jv_launch_cmd(args):
    """Start a local script or program (no shell, no administrator rights)."""
    rest, wait = list(args), None
    while rest and rest[0].lower() in ("-wait", "-detach"):
        wait = rest.pop(0).lower() == "-wait"
    if not rest:
        jarvis_say('Which file, sir? For example:  launch "C:\\tools\\backup.py"')
        out()
        return
    jv_launch_script(rest[0], rest[1:], wait)


def jv_launch_nl(orig):
    """'jarvis launch <path> [args]' / 'jarvis lancia <path>': only when Jarvis is named and the path really
    exists, so every other sentence ('start deltarune', 'launch a scan') is left to the other readers."""
    if not CONTESTO.get("jv_named"):
        return False
    m = re.match(r"(?:launch|lancia|avvia script|run script)\s+(.+)$", orig, re.I)
    if not m:
        return False
    tok = tokenize(m.group(1))
    if not tok or not os.path.exists(os.path.expanduser(tok[0])):
        return False
    CONTESTO["jv_nostore"] = True                       # 'again' must never start a program a second time
    jv_launch_script(tok[0], tok[1:])
    return True


