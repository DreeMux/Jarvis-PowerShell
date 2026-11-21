# ---------------- HELP ----------------
DESCRIPTIONS = {
    "Get-ChildItem": "List files and folders (-Force also shows hidden ones)",
    "Set-Location": "Change folder. Give it a FILE to select it for the port tools",
    "Get-Location": "Show the current folder",
    "Write-Output": "Print text",
    "Write-Host": "Print text",
    "Get-Content": "Print the text of a file (or of the selected file)",
    "Clear-Host": "Clear the screen",
    "Get-Command": "List every available command",
    "Get-Help": "Show this list; 'help <command>' shows the details",
    "Exit": "Close the shell",
}
STD_USAGE = {
    "Get-ChildItem": "dir [path] [-Force]",
    "Set-Location": 'cd <folder>\ncd "<file>"        selects that file for extract.port / interact.port / denux.hunter',
    "Get-Content": "cat <file>\ncat                 prints the selected file",
    "Get-Help": "help\nhelp <command>",
}


def describe(n):
    if n in DESCRIPTIONS:
        return DESCRIPTIONS[n]
    doc = (NOMI[n].__doc__ or "").strip()
    return doc.splitlines()[0] if doc else ""


@cmdlet("Get-Help", "help", "man")
def get_help(args):
    _, pos = parse(args)
    if pos:
        fn = CMDLETS.get(pos[0].lower())
        if fn is None:
            error("Get-Help", f"Get-Help could not find a help topic for '{pos[0]}'.",
                  "ObjectNotFound", pos[0], "HelpNotFoundException",
                  "HelpNotFound,Microsoft.PowerShell.Commands.GetHelpCommand")
            return
        n = fn.nome
        out()
        out("NAME", YELLOW)
        out(f"    {n}")
        out()
        out("SYNOPSIS", YELLOW)
        out(f"    {describe(n)}")
        out()
        out("SYNTAX", YELLOW)
        for line in (USAGE.get(n) or STD_USAGE.get(n) or f"{n} [arguments]").splitlines():
            out(f"    {line}")
        out()
        if ALIASES[n]:
            out("ALIASES", YELLOW)
            out("    " + ", ".join(ALIASES[n]))
            out()
        return
    titles = {"Assistant": "ASSISTANT", "Port tools": "PORT TOOLS", "Standard": "STANDARD COMMANDS",
              "Extensions": "EXTENSIONS (loaded from ext/)"}
    w = max(len(n) for n in NOMI) + 2
    out()
    out("Available commands   (type 'help <command>' for details)")
    out()
    for g in ("Assistant", "Port tools", "Standard", "Extensions"):
        names = sorted((n for n in NOMI if GROUPS[n] == g), key=str.lower)
        if not names:
            continue
        out(titles[g], YELLOW)
        for n in names:
            al = f"   (alias: {', '.join(ALIASES[n])})" if ALIASES[n] else ""
            out(f"  {n.ljust(w)}{describe(n)}{al}")
        out()
    out("JARVIS PHRASES (say them after 'jarvis', or just type them)", YELLOW)
    for a, b in (
        ("jarvis open <game>", "START the installed game, e.g. jarvis open deltarune  (chapter: jarvis open deltarune chapter 2)"),
        ("open <game>", "without 'jarvis' it only shows the game's data.win read-only, it never starts the game"),
        ("open data.win / open the 2nd one", "open a file or an item of the last list, read-only (also: read <file>, select <file>, go up)"),
        ("find my games", "locate the data.win of your games   (also: scan this PC for corrupt files, status, examples)"),
        ("implement jarvis", "update myself: 9 safety checks, backup, automatic rollback  (-Dry = checks only)"),
        ("implement jarvis <file.py>", "install that file;  <https://...> -Sha256 <hash>  downloads it first (hash required)"),
        ("maintenance", "maintenance mode: health check, then tests EVERY command (also: jarvis go in maintenance)"),
        ("launch <file> [args]", "start a local script or program: no shell, no administrator rights  (help launch)"),
        ("voice on / voice off", "JARVIS reads his lines aloud (needs pip install pyttsx3); silent until you ask"),
    ):
        out(f"  {a.ljust(34)}{b}")
    out()
    jarvis_say('You can also just tell me what you need, sir: "find my games", "scan this PC", "select <file>", '
               '"jarvis open <game>", "implement jarvis".')
    out()


# ======================= JARVIS (assistant layer) =======================
ACKS = ["Right away, sir.", "Certainly, sir.", "On it, sir.", "As you wish, sir."]


def jarvis_say(msg):
    out("JARVIS: " + msg, CYAN)
    jv_voice_say(msg)                  # does nothing unless you said 'voice on'


def ack(extra=""):
    jarvis_say(random.choice(ACKS) + (" " + extra if extra else ""))


def part_of_day():
    h = datetime.now().hour
    return "Good morning" if h < 12 else "Good afternoon" if h < 18 else "Good evening"


def jarvis_status(intro="Systems nominal, sir"):
    parts = []
    try:
        b = battery_info()
        parts.append(f"battery at {b['percent']}% ({'plugged in' if b['plugged'] else 'on battery'})"
                     if b else "no battery detected, running on mains")
        m = system_memory()
        if m:
            parts.append(f"memory at {m[0] * 100 // m[1]}% of {human(m[1])}")
    except Exception:
        pass
    jarvis_say(f"{intro}: " + (", ".join(parts) if parts else "all quiet") + ".")


def jarvis_greeting():
    jarvis_say(f"JARVIS online. {part_of_day()}, sir.")
    jarvis_say("Hunter, game locator, file inspector and resource monitor are standing by. "
               "Everything I do is read-only, except what you ask for: updating myself, starting a game or a program, or saving a report.")
    jarvis_status("Current status")
    sl = jv_upd_secline()
    if sl:
        out(sl[0], JV_SEC_G if sl[1] else RED)
    jarvis_say('Type "help" for commands, or just tell me what you need: '
               '"find my games", "scan this PC for corrupt files".')
    jv_upd_show_report()
    out()


