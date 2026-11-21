# ---------------- extract.key: a downloadable report about the selected file ----------------
def jv_upd_export_file(text, base):
    """The ONLY place the report file is written: a brand-new text file (never overwrites anything),
    in the Downloads folder (or next to Jarvis if there is none). Returns its path."""
    folder = CONTESTO.get("jv_export_dir")
    if not folder:
        dl = os.path.join(os.path.expanduser("~"), "Downloads")
        folder = dl if os.path.isdir(dl) else os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis_exports")
    os.makedirs(folder, exist_ok=True)
    stem = re.sub(r"[^\w.\-]", "_", base)[:50] or "file"
    n = 0
    while True:
        name = f"Jarvis_report_{stem}" + (f"_{n}" if n else "") + ".txt"
        path = os.path.join(folder, name)
        try:
            with open(path, "x", encoding="utf-8", newline="\r\n") as f:
                f.write(text)
            return path
        except FileExistsError:
            n += 1
            if n > 999:
                raise


@cmdlet("extract.key", group="Port tools", usage="""extract.key <file>
extract.key                  uses the file selected earlier with:  cd "<file>"
Saves a text report about the file (what extract.port and interact.port show, plus how to verify it yourself)
as a NEW file in your Downloads folder, and tells you where. The original file is never touched.""")
def extract_key(args):
    """Save a downloadable text report about the selected file (the file itself is never changed)."""
    import io
    import contextlib
    path = pick(args, "extract.key")
    if not path:
        return
    parts = []
    for fn, title in ((extract_port, "FILE INFORMATION (extract.port)"), (interact_port, "CONTENTS AND WHAT YOU CAN DO (interact.port)")):
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                fn([path])
        except Exception as e:
            buf.write(f"(could not be produced: {type(e).__name__})\n")
        txt = re.sub(r"\x1b\[[0-9;]*m", "", buf.getvalue()).strip("\n")
        if "Cannot read file" in txt:
            out(f"extract.key : Cannot read file '{safe(path)}'", RED)
            out()
            return
        parts.append(f"{'=' * 70}\n{title}\n{'=' * 70}\n{txt}\n")
    name = os.path.basename(path)
    verify = (f"{'=' * 70}\nVERIFY IT YOURSELF\n{'=' * 70}\n"
              f"PowerShell:  Get-FileHash -Algorithm SHA256 \"{os.path.abspath(path)}\"\n"
              f"Compare the result with the SHA256 above (and with the author's, if the download page gives one).\n"
              f"Windows Security: right-click the file > Scan with Microsoft Defender.\n")
    head = (f"JARVIS FILE REPORT\nCreated : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"File    : {os.path.abspath(path)}\n"
            f"This report was made read-only: the file above was not changed.\n\n")
    try:
        saved = jv_upd_export_file(head + "\n".join(parts) + "\n" + verify, name)
    except OSError as e:
        out(f"extract.key : Cannot save the report ({safe(e.strerror or e)})", RED)
        out()
        return
    out()
    out(f"Report saved: {safe(saved)}", GREEN)
    out(f"  {human(os.path.getsize(saved))}, about {safe(name)}. The original file was not touched.", GRAY)
    out()


# ---------------- local "AI-like" brain: troubleshooting, how-to, comparisons, retrieval ----------------
JV_STOP = set("""a an the is are was were be been am do does did to of in on at for with from by and or but if then so it its this that
these those i you he she we they me my your our their can could would should will shall may might must have has had get got
what which who whom how why when where there here about into onto out up down over under again just also very really much many
some any no not yes please tell show give let know want need like using use used make makes made go goes going let s t don
isnt doesnt dont cant wont sir yo hey ok okay hi hello""".split())

JV_FAQ = [
    # (keywords, question, answer)
    ("game wont start launch open not working", "Why won't my game start?",
     "The usual causes, in order: 1) a missing runtime (Visual C++ redistributable, DirectX or .NET), 2) an outdated graphics driver, "
     "3) antivirus blocking the exe, 4) a damaged file after an interrupted download, 5) the wrong folder (start the game's own exe, not a launcher helper). "
     "Try running the game as administrator and read any error text it shows. Say 'jarvis is it corrupt' with the data file selected to check for damage."),
    ("game crashes crash random freezes freeze", "Why does my game crash or freeze?",
     "Common reasons: overheating (check temperatures), too little RAM or VRAM, bad or outdated drivers, corrupt game files, or a faulty mod. "
     "Update the graphics driver, close other programs, verify the game files in its launcher, and remove mods to test."),
    ("dll missing not found error vcruntime msvcp", "How do I fix a 'DLL not found' error?",
     "A missing DLL such as vcruntime140.dll or msvcp140.dll normally means a Microsoft runtime is missing: install the latest Visual C++ Redistributable (x86 and x64). "
     "Never download single DLLs from random sites: they are a classic malware trick. Reinstalling the game or program also restores its own DLLs."),
    ("low fps slow lag stutter performance laggy", "How can I get more FPS?",
     "Lower the resolution and shadow/effects quality, close background programs, update the graphics driver, make sure the game uses the dedicated GPU "
     "and not the integrated one, and check the PC is not overheating. Installing the game on an SSD helps loading and stutter."),
    ("free space disk full storage clean clear", "How can I free disk space?",
     "Empty the Recycle Bin, run Disk Cleanup (or Settings > Storage > Temporary files), uninstall unused programs and games, move big files to another drive, "
     "and clear your Downloads folder. Say 'jarvis biggest files' to see what takes the most space in the current folder."),
    ("backup save saves progress protect copy", "How do I back up my game saves?",
     "Copy the save folder somewhere safe. Many games keep saves in C:\\Users\\<you>\\AppData\\Local or Roaming, in Documents, or inside the game folder. "
     "Cloud saves (Steam, Epic) are an extra safety net. Back up before updating or modding a game."),
    ("mod install modding modify add", "How do I install a mod safely?",
     "Work on a copy of the game folder, read the mod's instructions, download only from the official page, and check the file with an antivirus first. "
     "Keep the original data file: if the game breaks, put it back. Never run a mod's exe you do not trust."),
    ("corrupt corrupted damaged broken file repair fix", "What should I do with a corrupt file?",
     "Re-download or re-copy it from the source, then compare the SHA-256 with the one the author publishes. For a game, use 'verify integrity of game files' in the launcher. "
     "For a zip, try 7-Zip; for a document, try the program's repair option. I can detect damage with 'jarvis is it corrupt' or 'denux.hunter', but I never change files."),
    ("safe virus trust download exe malware suspicious", "How can I tell if a file is safe?",
     "Check where it came from, its extension (a 'photo.jpg.exe' is a trap), its size, and scan it with Windows Security. "
     "Compare the SHA-256 with the official one if the site gives it. Cracked games and 'free' keygens are the main source of infections. I cannot scan for viruses myself."),
    ("hash sha256 verify compare check integrity", "How do I verify a download with a hash?",
     "Select the file and say 'jarvis sha256' (or run extract.port), then compare the result with the hash on the download page. If even one character differs, "
     "the file is damaged or has been tampered with."),
    ("extension change rename hidden show file types", "How do I show file extensions in Windows?",
     "Open File Explorer, View > Show > File name extensions. With extensions visible you can spot fake files like 'document.pdf.exe'."),
    ("open file cant open program default associate", "Why can't Windows open a file?",
     "No program is associated with that type. Right-click > Open with > Choose another app and tick 'Always use this app'. If you do not know what type it is, "
     "select it and ask me 'what type is it'."),
    ("data.win datawin gamemaker game files unpack extract", "What is a data.win file and can I open it?",
     "It is the main data file of a GameMaker game: sprites, sounds, code, rooms. I can read its header, chunks and sprite count read-only. "
     "Editing it needs tools such as UndertaleModTool, and you should always work on a copy."),
    ("temp temporary delete safe cache", "Is it safe to delete temp files?",
     "Yes for %TEMP% and the browser cache when the programs are closed; Windows recreates what it needs. Do not delete anything inside C:\\Windows."),
    ("system32 delete windows folder remove", "Can I delete System32 or Windows files?",
     "No. They are the core of Windows and deleting them can make the PC unbootable. That folder is the one place I will never open files from."),
    ("ram memory upgrade enough need how much", "How much RAM do I need?",
     "8 GB is the minimum for Windows today, 16 GB is comfortable for gaming and everyday work, 32 GB is for heavy editing, big mods or many programs at once. "
     "Say 'jarvis status' to see how much memory is in use right now."),
    ("ssd hdd upgrade faster boot load", "Should I move games to an SSD?",
     "Yes, if you can: loading screens and texture streaming are far faster, and the PC feels snappier. Keep big archives and backups on the cheaper hard disk."),
    ("overheat hot temperature fan cooling thermal", "What should I do if my PC overheats?",
     "Clean the dust from fans and vents, make sure air can flow around the case or laptop, lower the game's settings, and consider new thermal paste if it is old. "
     "Sustained temperatures above about 85 C on the CPU or GPU are too high."),
    ("slow pc computer startup boot speed", "Why is my PC slow?",
     "Check Task Manager (Ctrl+Shift+Esc) for programs using CPU, memory or disk; disable startup programs; keep at least 15% of the drive free; "
     "install updates; and scan for malware. An old hard disk replaced by an SSD is the biggest single upgrade."),
    ("update windows driver graphics nvidia amd intel gpu", "How do I update my graphics driver?",
     "Download it from the maker's site (NVIDIA, AMD or Intel) or use their app (GeForce Experience, Adrenalin). Avoid third-party 'driver updater' programs."),
    ("uninstall remove program game delete", "How do I uninstall a game properly?",
     "Use Settings > Apps, or the launcher (Steam: right-click > Manage > Uninstall). Then keep or delete the save folder as you prefer: back it up first if you want your progress."),
    ("portable install zip extract run game download", "I downloaded a game as a zip. How do I run it?",
     "Extract the whole archive to a normal folder (not from inside the zip), open the folder and run the game's exe. "
     "Do not run it from inside the archive: it will miss its files. Then say 'jarvis open <game name>' and I can start it for you."),
    ("antivirus false positive blocked quarantine", "Why does my antivirus block a game?",
     "Games and mods are often flagged by mistake (a 'false positive'), especially unsigned or cracked ones. If you trust the source, add an exclusion; "
     "if not, leave it blocked. Check the file's SHA-256 against the official one first."),
    ("zip rar 7z extract archive open unzip", "How do I open a zip, rar or 7z archive?",
     "Windows opens zip natively (right-click > Extract All). For rar and 7z install 7-Zip, which is free. Select an archive and say 'jarvis what is inside' to list its entries."),
    ("password protected zip locked archive", "What if an archive asks for a password?",
     "The password comes from whoever made it: check the download page or readme. I cannot and will not try to guess or break passwords."),
    ("path long too long error copy", "Why do I get a 'path too long' error?",
     "Windows traditionally limits paths to 260 characters. Move the folder closer to the drive root (C:\\Games\\Name) or enable long paths in Windows settings."),
    ("permission denied access administrator", "Why do I get 'access denied'?",
     "The file is protected, in use by another program, or needs administrator rights. Close the program using it, move the file out of protected folders, "
     "or run the program as administrator. Never take ownership of Windows system folders."),
    ("steam library folder move install location", "How do I move a Steam game to another drive?",
     "Steam > Settings > Storage: add a new library folder on the other drive, then in the game's Properties > Installed Files choose 'Move install folder'."),
    ("save location where saves stored appdata documents", "Where does a game keep its saves?",
     "Usually C:\\Users\\<you>\\AppData\\Local or Roaming under the game's name, or Documents\\My Games, or the game folder itself. "
     "PCGamingWiki lists the exact location for most games."),
    ("fullscreen window resolution black screen display", "My game shows a black screen. What now?",
     "Try windowed mode (Alt+Enter), lower the resolution, update the graphics driver, run the game as administrator, and disable overlays (Discord, Steam). "
     "Check that the game runs on the dedicated GPU."),
    ("sound audio no sound crackling", "Why is there no sound in my game?",
     "Check Windows' output device and the volume mixer, update the audio driver, and look at the game's own audio settings. "
     "Crackling is often a sample-rate mismatch: set the device to 48000 Hz in Sound settings."),
    ("controller gamepad joystick not working", "Why isn't my controller working?",
     "Plug it in before starting the game, try another USB port, enable Steam Input if you use Steam, and check the game's controller settings. "
     "Xbox controllers work natively; others may need a mapping tool."),
    ("language change translate english", "How do I change a game's language?",
     "Look in the game's options first; on Steam use Properties > General > Language; for others edit the settings file or use the launcher. "
     "Some games keep language inside data files, which is why you should back them up before touching anything."),
    ("shortcut desktop create icon", "How do I put a game on the desktop?",
     "Right-click the game's exe > Send to > Desktop (create shortcut). Or just say 'jarvis open <game>' and I will start it."),
    ("jarvis update upgrade implement patch install", "How do I update Jarvis?",
     "Use 'implement jarvis <file.py>': nine safety checks run first, a backup is made, and Jarvis rolls back by itself if anything fails. "
     "'implement jarvis -Dry' only runs the checks. 'security' shows the status of the guard."),
    ("jarvis safe dangerous delete files harm", "Is Jarvis safe to use?",
     "I am designed to be read-only: I read, count, search and describe files, and I only write when I update myself or when you ask me to export a report. "
     "I never change your own files, and the update guard blocks code that deletes, downloads or runs things. Say 'security' to see the guard."),
    ("jarvis wrong didnt understand fix teach learn", "What if Jarvis doesn't understand me?",
     "Try rewording it in plain words, or say 'examples'. If a phrase should work and does not, tell the developer (your assistant) the exact sentence and it can be taught."),
    ("select file selected port tools use", "How do I select a file for the port tools?",
     "Use cd \"<file>\" or say 'jarvis select <file>'. Then extract.port, interact.port, extract.key and pluton.key work on it without typing the name again."),
    ("export report save download file info", "How can I export the information of a file?",
     "Select the file and run extract.key: it saves a text report (name, type, size, dates, hashes and contents summary) in your Downloads folder. "
     "The original file is never touched."),
    ("windows activate license key product", "How do I check if Windows is activated?",
     "Settings > System > Activation. I cannot read or change license keys."),
    ("restore point system recovery reset reinstall", "How do I undo a bad change in Windows?",
     "Use System Restore (search 'Create a restore point' > System Restore) to go back to an earlier state, or Settings > Recovery > Reset this PC as a last resort. "
     "Back up your files first."),
    ("blue screen bsod stop code error restart", "What do I do after a blue screen?",
     "Note the stop code, restart, update Windows and drivers, remove any software or hardware you installed just before it started, and run 'sfc /scannow' in an administrator terminal. "
     "Repeated crashes point to RAM, disk or overheating."),
    ("sfc scannow dism check system files repair windows", "How do I check Windows system files?",
     "In an administrator terminal run 'sfc /scannow', and if it finds problems 'DISM /Online /Cleanup-Image /RestoreHealth'. These are Windows tools: I do not run them for you."),
    ("firewall port network online multiplayer connect", "Why can't I play online?",
     "Check that the firewall lets the game through, that the router is not blocking it, that the servers are up, and that your connection is stable (Ethernet beats Wi-Fi). "
     "Restarting the router fixes many cases."),
    ("ping high latency lag network online", "How can I lower my ping?",
     "Use a cable, close downloads and streaming, choose a nearer server, and restart the router. Wi-Fi interference is the usual cause of spikes."),
    ("emulator rom legal safe", "Are ROMs and emulators legal?",
     "Emulators are legal. ROMs are only legal when you own the original game and make the copy yourself; downloading them from websites generally is not."),
    ("bit 32 64 x86 x64 version which windows", "How do I know if Windows is 32 or 64 bit?",
     "Settings > System > About shows 'System type'. Most PCs today are 64-bit. For a program file, select it and ask me 'is it 64-bit'."),
    ("pdf edit convert merge", "How do I edit or convert a PDF?",
     "Word and Edge can open simple PDFs; for merging or editing use a PDF tool. I can read a PDF's version and size, but not edit it."),
    ("image resize convert png jpg compress", "How can I convert or shrink an image?",
     "Paint or Photos can resize and re-save it as another format. PNG suits screenshots and sprites; JPG suits photos. I can tell you the dimensions with 'jarvis dimensions'."),
    ("video convert compress mp4 size reduce", "How do I make a video smaller?",
     "Re-encode it with HandBrake (free) using H.264 or H.265 at a lower bitrate or resolution. mp4 is the most compatible container."),
    ("text encoding garbled characters utf strange symbols", "Why does a text file show strange characters?",
     "It is being read with the wrong encoding. Try UTF-8, UTF-16 or Windows-1252. Select it and ask 'jarvis what encoding' to see what I detect."),
    ("large file big gb slow copy transfer usb", "Why is copying a big file slow?",
     "USB 2 ports and cheap flash drives are slow; many small files are slower than one big one; antivirus scanning adds time. Use USB 3 ports and an exFAT or NTFS drive for files over 4 GB."),
    ("fat32 4gb file too large usb drive format", "Why can't I copy a file over 4 GB to my USB drive?",
     "FAT32 cannot store files larger than 4 GB. Format the drive as exFAT or NTFS (copy its contents off first, formatting erases it)."),
    ("hidden files show folder invisible", "How do I see hidden files?",
     "File Explorer > View > Show > Hidden items. In this shell, use Get-ChildItem -Force (alias dir -Force)."),
    ("default program browser change set", "How do I change the default program for a file type?",
     "Settings > Apps > Default apps, then pick the extension and choose the program."),
    ("startup programs disable boot slow", "How do I stop programs launching at startup?",
     "Task Manager > Startup apps: select the program and press Disable. Fewer startup programs means a faster boot."),
    ("screenshot capture screen record", "How do I take a screenshot?",
     "Windows+Shift+S for a selection, PrintScreen for the whole screen, Windows+G for the Xbox Game Bar recorder."),
    ("battery laptop drain life power", "How can I make my laptop battery last longer?",
     "Lower the screen brightness, use Battery Saver, close background apps, and avoid heavy games unplugged. Say 'jarvis battery' to see the level now."),
    ("compress zip smaller folder archive shrink", "How do I compress a folder?",
     "Right-click > Send to > Compressed (zipped) folder, or use 7-Zip for stronger compression (7z)."),
    ("duplicate files remove find same", "How can I find duplicate files?",
     "Say 'jarvis duplicates' and I list files with identical content (same SHA-256) in the current folder. I show them; you choose what to delete."),
    ("lost deleted recover recovery undelete", "Can I recover a deleted file?",
     "Check the Recycle Bin first. After that, stop writing to the drive and use a recovery tool such as Recuva; the sooner the better. A backup is the real answer."),
    ("ransomware encrypted files locked pay", "What if my files were encrypted by ransomware?",
     "Disconnect from the network, do not pay, do not delete anything, and scan with Windows Security Offline scan. Restore from a backup; nomoreransom.org may have a free decryptor."),
    ("password strong safe manager account", "How do I keep my accounts safe?",
     "Use a different long password per site with a password manager, turn on two-factor authentication, and never type your password after clicking a link in an email."),
    ("programming python script learn code", "Can Jarvis teach me Python?",
     "Not in depth: I am a file-and-PC assistant. I can explain basic terms such as variable, function, loop and script. pwsh.py itself is Python, so reading it is a fine start."),
    ("gamemaker sprite extract image export unpack", "Can I extract the sprites from a GameMaker game?",
     "With 'jarvis how many sprites' I can count them, but extracting images needs a dedicated tool such as UndertaleModTool. Always work on a copy of data.win."),
    ("steam family share library account refund", "How do I refund a Steam game?",
     "Steam allows a refund within 14 days of purchase and under 2 hours of play, from Help > Steam Support > Purchases."),
    ("epic launcher games library install location", "Where does the Epic launcher install games?",
     "By default in C:\\Program Files\\Epic Games. You can choose another folder when you install, and I look there for installed games too."),
]

JV_COMPARE = {
    frozenset(("ssd", "hdd")): "An SSD has no moving parts: it is far faster (boot, load times), silent and shock-resistant, but costs more per GB. An HDD is cheap and big, slower and can fail from knocks. Put Windows and games on an SSD, archives on an HDD.",
    frozenset(("ram", "storage")): "RAM is the fast, temporary working memory (emptied at shutdown); storage (SSD/HDD) keeps your files permanently. RAM decides how many things you can run at once, storage how much you can keep.",
    frozenset(("ram", "vram")): "RAM serves the whole PC; VRAM lives on the graphics card and holds textures and frames for the GPU. Games with high-resolution textures need plenty of VRAM.",
    frozenset(("cpu", "gpu")): "The CPU is the general-purpose brain: few powerful cores for logic and many different tasks. The GPU has thousands of small cores built for drawing images and parallel maths. Games lean on both.",
    frozenset(("zip", "rar")): "Both pack files into one archive. Zip is built into Windows and universal; rar often compresses a little better but needs WinRAR or 7-Zip to open.",
    frozenset(("zip", "7z")): "Zip is universal and built into Windows; 7z compresses much more but needs 7-Zip (free) to open.",
    frozenset(("png", "jpg")): "PNG is lossless and supports transparency: best for screenshots, sprites and text. JPG is lossy and much smaller: best for photos, but quality drops each time it is re-saved.",
    frozenset(("mp3", "wav")): "WAV is uncompressed, perfect quality, huge files. MP3 is compressed with a small quality loss, ideal for music you carry around.",
    frozenset(("mp3", "flac")): "FLAC is compressed without losing quality (about half the size of WAV); MP3 loses a little quality to be much smaller.",
    frozenset(("mp4", "mkv")): "Both are containers for video. mp4 is the most compatible; mkv is more flexible (many audio tracks and subtitles) but less universally supported.",
    frozenset(("sha256", "md5")): "Both are fingerprints of a file. MD5 is old and can be forged deliberately, so it only detects accidental damage; SHA-256 is the modern, trustworthy one.",
    frozenset(("steam", "epic")): "Steam has the biggest library, community features and refunds; Epic gives away free games regularly and takes a smaller cut from developers. You can use both; I find games from either.",
    frozenset(("exe", "msi")): "An exe is any Windows program (often a custom installer); an msi is a standard Windows Installer package, easier for administrators to manage and uninstall.",
    frozenset(("32-bit", "64-bit")): "A 64-bit program can use far more than 4 GB of memory and needs a 64-bit Windows; 32-bit runs on both but is limited. Today almost everything is 64-bit.",
    frozenset(("wifi", "ethernet")): "Ethernet (cable) is steadier, with lower and more constant ping; Wi-Fi is convenient but suffers from interference and distance. Use a cable for online games.",
    frozenset(("txt", "docx")): "txt is plain text without formatting and opens anywhere; docx is a Word document with fonts, images and layout.",
    frozenset(("csv", "xlsx")): "csv is plain text rows split by commas (tiny, universal, no formulas or styles); xlsx is a full Excel workbook with formatting, formulas and several sheets.",
    frozenset(("json", "xml")): "Both hold structured data. JSON is shorter and easier to read; XML is wordier but supports attributes and strict schemas.",
    frozenset(("antivirus", "firewall")): "An antivirus looks for malicious files and behaviour on your PC; a firewall controls which network connections are allowed. You need both: Windows Security includes them.",
    frozenset(("virus", "malware")): "Malware is the umbrella term for any harmful software (viruses, ransomware, spyware, trojans). A virus is one kind that spreads by attaching itself to other files.",
    frozenset(("python", "powershell")): "Python is a general-purpose programming language; PowerShell is Windows' command shell and scripting language. This shell imitates PowerShell and is written in Python.",
    frozenset(("sprite", "texture")): "A sprite is a 2D picture drawn on screen as a character or object; a texture is an image wrapped around a surface (usually 3D) to give it color and detail.",
    frozenset(("mod", "dlc")): "A mod is made by the community and changes a game; DLC is extra content made and released officially by the developer.",
    frozenset(("data.win", "exe")): "In a GameMaker game the exe is the runner (the engine that starts the game) and data.win holds the game itself: sprites, sounds, code and rooms.",
}


def jv_stem(w):
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > len(suf) + 2 and w.endswith(suf):
            return w[:-len(suf)]
    return w


def jv_terms(text):
    return [jv_stem(w) for w in re.findall(r"[a-z0-9.+#]+", text.lower().replace("'", "")) if w not in JV_STOP and len(w) > 1]


def jv_faq_find(t, single_ok=True):
    """Best-matching FAQ entry for a question, as (score, entry) or None: simple weighted keyword retrieval."""
    q = set(jv_terms(t))
    if not q:
        return None
    if not CONTESTO.get("jv_faq_idx") or CONTESTO["jv_faq_idx"][0] != len(JV_FAQ):
        docs = [(set(jv_terms(k + " " + qu)), set(jv_terms(k)), (k, qu, a)) for k, qu, a in JV_FAQ]
        df = {}
        for d, _, _ in docs:
            for w in d:
                df[w] = df.get(w, 0) + 1
        CONTESTO["jv_faq_idx"] = (len(JV_FAQ), docs, df)
    _, docs, df = CONTESTO["jv_faq_idx"]
    n = len(docs)
    scored = []
    for d, keys, e in docs:
        hit = q & d
        if not hit:
            continue
        sc = sum(math.log(1 + n / df[w]) * (1.6 if w in keys else 1.0) for w in hit)
        sc += 0.5 * len(hit) / max(len(q), 1)
        scored.append((sc, len(hit), e))
    if not scored:
        return None
    scored.sort(key=lambda x: -x[0])
    best = scored[0]
    if best[1] >= 2:
        return best[0], best[2]
    if single_ok and (len(scored) == 1 or best[0] >= 1.4 * scored[1][0]):     # one distinctive word and a clear winner
        return best[0], best[2]
    return None


def jv_compare(t):
    """'difference between ssd and hdd', 'zip vs rar', 'ssd or hdd, which is better' -> an explanation, or None."""
    s = t.lower().replace("'", "")
    m = re.match(r"^(?:what is the |whats the |what are the |tell me the |explain the )?(?:difference|differences|diff)s? between (.+?) and (.+)$", s) \
        or re.match(r"^(?:compare |comparison of )(.+?) (?:and|with|to|vs\.?|versus) (.+)$", s) \
        or re.match(r"^(.+?) (?:vs\.?|versus|or) (.+?)(?: which (?:is|one is) (?:better|best|faster|safer)| which should i (?:use|choose|pick|get)| which one)?$", s)
    if not m:
        return None
    a, b = (re.sub(r"^(?:an?|the)\s+", "", x.strip().strip("?!. ")) for x in m.groups())
    norm = lambda x: {"hard disk": "hdd", "hard drive": "hdd", "ssd drive": "ssd", "solid state": "ssd", "wi-fi": "wifi",
                      "wireless": "wifi", "cable": "ethernet", "7zip": "7z", "7-zip": "7z", "jpeg": "jpg", "memory": "ram",
                      "processor": "cpu", "graphics card": "gpu", "video card": "gpu", "data win": "data.win",
                      "sha-256": "sha256", "64 bit": "64-bit", "32 bit": "32-bit", "epic games": "epic",
                      "storage": "storage", "disk": "storage", "hard disk drive": "hdd"}.get(x, x)
    a, b = norm(a), norm(b)
    hit = JV_COMPARE.get(frozenset((a, b)))
    if hit:
        return hit
    ea = [e for e in JV_KB if a in e[0]]
    eb = [e for e in JV_KB if b in e[0]]
    if ea and eb and a != b:
        return f"{a.upper() if len(a) <= 5 else a.capitalize()}: {ea[0][1]}  |  {b.upper() if len(b) <= 5 else b.capitalize()}: {eb[0][1]}"
    return None


def jv_try_deep(orig, t):
    """Spoken to by name ('jarvis duplicates', 'jarvis tell me about a.txt'): a request about a file, a folder or this
    PC goes to the specific handlers first, before the glossary and the how-to answers. True when one handled it."""
    if CONTESTO.get("jv_deep_try"):
        return False
    CONTESTO["jv_deep_try"] = True
    try:
        return bool(jv_deep(orig, t, CONTESTO.get("file")))
    finally:
        CONTESTO["jv_deep_try"] = False


def jv_brain(orig, t):
    """The local 'AI-like' layer: comparisons, how-to / why / troubleshooting retrieval. Only for PC, file and game topics."""
    s = t.strip().rstrip("?!. ").replace("’", "'")
    if re.match(r"^(?:select|open|read|show|cd|go|use|choose|pick|deselect|seleziona|apri|leggi)\b", s):
        return False                   # commands on files belong to the file handlers, not to the how-to answers
    c = jv_compare(s)
    if c:
        jarvis_say(c)
        return True
    q = bool(re.match(r"^(?:how|why|what should|what do i|what can i|what to do|should i|can i|could i|is it|is there|is this|are there|"
                      r"which|where|when|do i|does|will|would|my |i have|i get|i cant|i can't|i dont|i don't|it (?:wont|won't|doesnt|doesn't|says|keeps)|"
                      r"help with|problem|issue|error|fix|solve|recommend|suggest|advice|any tips|tips)", s))
    named = CONTESTO.get("jv_named")
    if not (q or (named and len(s.split()) >= 2)):
        return False
    if named and not q and jv_try_deep(orig, t):       # 'jarvis free disk space', 'jarvis find all png files'
        return True
    one = not CONTESTO.get("file") and not re.search(r"\b(?:it|its|this|that|them|these|those)\b", s)   # 'how big is it' is about a file
    hit = jv_faq_find(s + (" jarvis" if CONTESTO.get("jv_said_name") else ""), one)
    if not hit:
        return False
    sc, (k, qu, a) = hit
    jarvis_say(a)
    others = [e for e in JV_FAQ if e[1] != qu and len(set(jv_terms(e[0])) & set(jv_terms(s))) >= 2][:2]
    if others:
        out("    Related: " + "  |  ".join(e[1] for e in others), GRAY)
    return True



def jv_know(orig, t):
    """Knowledge: maths, conversions, dates, a glossary of file types and tech terms, commands, games, about me."""
    from datetime import date
    s = t.strip().rstrip("?!. ").replace("’", "'")
    s = s.replace("what's", "what is").replace("whats", "what is").replace("who's", "who is")
    say = jarvis_say

    c = jv_compare(s)                  # 'difference between ssd and hdd', 'zip vs rar'
    if c:
        say(c)
        return True

    # --- maths
    m = re.match(r"^(?:what is|what s|whats|calculate|calc|compute|solve|how much is|quanto fa|quanto è|quanto e|calcola|"
                 r"fammi il conto di|result of)\s+(.+)$", s)
    expr = m.group(1) if m else (s if re.match(r"^(?:square root of|sqrt|radice)", s) else s if re.fullmatch(r"[\d\s+\-*/().,%^x×÷]+", s) and re.search(r"\d\s*[+\-*/^x×÷%]\s*\(?\d", s) else None)
    if expr:
        try:
            v = jv_calc(expr)
        except ZeroDivisionError:
            say("Division by zero, sir: that is undefined.")
            return True
        except (OverflowError, ValueError, SyntaxError, RecursionError, MemoryError):
            v = None
        if v is not None:
            say(f"{expr.strip()} = {jv_numfmt(v)}, sir.")
            return True

    # --- unit conversion
    m = re.match(r"^(?:convert\s+|how (?:many|much) is\s+|converti\s+|quanti\s+\w+\s+sono\s+)?(-?\d+(?:[.,]\d+)?)\s*"
                 r"(°?[a-z]+)\s+(?:to|in|into|a|in)\s+(°?[a-z]+)$", s)
    if m:
        val = float(m.group(1).replace(",", "."))
        ua, ub = JV_UNITS.get(m.group(2)), JV_UNITS.get(m.group(3))
        if ua and ub and ua[0] == ub[0]:
            if ua[0] == "temp":
                c = val if ua[1] == "c" else (val - 32) * 5 / 9 if ua[1] == "f" else val - 273.15
                res = c if ub[1] == "c" else c * 9 / 5 + 32 if ub[1] == "f" else c + 273.15
            else:
                res = val * ua[1] / ub[1]
            say(f"{jv_numfmt(val)} {m.group(2)} = {jv_numfmt(round(res, 6))} {m.group(3)}, sir."
                + (" (1 KB = 1024 bytes here.)" if ua[0] == "data" else ""))
            return True
        if ua and ub:
            say(f"I can't convert {m.group(2)} to {m.group(3)}, sir: they measure different things.")
            return True

    # --- dates
    today = datetime.now().date()

    def nice(d):
        return d.strftime("%A %d %B %Y")

    def fix(d, noyear):
        if noyear and d < today:
            try:
                return d.replace(year=d.year + 1)
            except ValueError:
                return d
        return d
    m = re.match(r"^(?:how many days|how long|quanti giorni|days)\s+(?:are there |ci sono |mancano |is it |left )?"
                 r"(?:until|till|to|left until|left till|before|a|al|alla|fino a|fino al)\s+(.+)$", s)
    if m:
        r = jv_date(m.group(1), today)
        if r:
            d = fix(*r)
            n = (d - today).days
            say("That is today, sir." if n == 0 else f"{n:,} day(s) until {nice(d)}, sir." if n > 0
                else f"{nice(d)} was {-n:,} day(s) ago, sir.")
            return True
    m = re.match(r"^(?:how many days|how long|quanti giorni|days)\s+(?:has it been |sono passati )?(?:since|from|ago|da)\s+(.+)$", s)
    if m:
        r = jv_date(m.group(1), today)
        if r:
            d = r[0] if not r[1] or r[0] <= today else r[0].replace(year=r[0].year - 1)
            say(f"{(today - d).days:,} day(s) since {nice(d)}, sir.")
            return True
    m = re.match(r"^(?:days|how many days|quanti giorni) between\s+(.+?)\s+and\s+(.+)$", s)
    if m:
        a, b = jv_date(m.group(1), today), jv_date(m.group(2), today)
        if a and b:
            say(f"{abs((fix(*b) - fix(*a)).days):,} day(s) between {nice(a[0])} and {nice(b[0])}, sir.")
            return True
    m = re.match(r"^(?:what day|which day|che giorno)\s+(?:of the week |della settimana )?(?:is|was|will be|è|sarà|era)\s+(?:it on |on |il )?(.+)$", s)
    if m:
        r = jv_date(m.group(1), today)
        if r:
            d = fix(*r)
            say(f"{nice(d)}, sir.")
            return True

    # --- who/what am I
    if re.search(r"\b(?:who (?:made|created|built|programmed|wrote) you|your (?:creator|maker|author)|chi ti ha (?:creato|fatto|programmato))\b", s):
        say("I was created by DreeMux, sir: a Python program living in pwsh.py, built one request at a time from his instructions. "
            "No cloud, no neural network inside me: I understand the phrases and patterns I was taught, which is why "
            "you can keep teaching me more.")
        return True
    if re.search(r"\b(?:are you (?:an? )?(?:ai|bot|robot|real|human|smart|intelligent|chatgpt|claude|alive)|sei (?:un'?)?(?:ai|robot|intelligente|vivo|umano))\b", s):
        say("I'm a rule-based assistant, sir, not a language model: quick and careful with files, games and your PC, "
            "but I only know what I was taught. Say 'examples' to see how much that is.")
        return True
    if re.search(r"\b(?:do you (?:speak|understand|know) (?:italian|english)|parli italiano|capisci l'?italiano|speak italian)\b", s):
        say("Yes, sir. I understand English and Italian, but I always answer in English.")
        return True
    if re.search(r"\b(?:weather|meteo|news|notizie|google|youtube|stock price|bitcoin|search the web|cerca su internet)\b", s) \
            and not re.search(r"\.\w{2,4}\b", s):
        say("I run offline, sir: no internet, so no weather, news or web searches. Files, games, your PC, maths, "
            "units, dates and a glossary of tech terms are my territory. Say 'jarvis be online' and then "
            "'jarvis cerca <topic>' for a summary from my own knowledge and your files.")
        return True

    # --- definitions: "what is a dll", "explain sha256", "tell me about undertale", "what does dir do"
    m = re.match(r"^(?:what is|what s|whats|what are|what does|what do|who is|who s|explain|define|tell me about|describe|"
                 r"meaning of|what is the meaning of|cos è|cos'è|che cos è|che cos'è|cosa è|cosa sono|spiegami|spiega|"
                 r"cosa significa|che significa|parlami di|dimmi di)\s+(?:an? |the |un |una |uno |il |lo |la |i |gli |le |l'|l )?"
                 r"(.+?)(?:\s+(?:mean|means|do|does|do for|stands for|file|files|format|extension|estensione|significa))*$", s)
    if m:
        term = m.group(1).strip().strip("'\"` ").lstrip(".")
        term = re.sub(r"^(?:\.|file |un |una |the )", "", term)
        key = re.sub(r"\s+", " ", term.lower())
        if CONTESTO.get("file") and key in ("sha256", "sha-256", "md5", "hash", "checksum", "digest"):
            return False                  # a file is selected: that is a question about the file, not the word
        if key in JV_GAMES_KB:
            say(JV_GAMES_KB[key] + f" Say 'jarvis open {key}' to start it.")
            return True
        for g, txt in JV_GAMES_KB.items():
            if len(key) >= 4 and difflib.get_close_matches(key, [g], n=1, cutoff=0.82):
                say(txt + f" Say 'jarvis open {g}' to start it.")
                return True
        fn = CMDLETS.get(key.replace(" ", "-")) or CMDLETS.get(key)
        hits = sorted((e for e in JV_KB if key in e[0]), key=lambda e: e[0][0] != key)
        if fn is not None and not hits:
            n = fn.nome
            say(f"{n}: {describe(n)}.")
            for line in (USAGE.get(n) or STD_USAGE.get(n) or "").splitlines()[:6]:
                out("    " + line, GRAY)
            if ALIASES.get(n):
                out("    aliases: " + ", ".join(ALIASES[n]), GRAY)
            return True
        if not hits and len(key) >= 4:
            allk = [k for keys, _ in JV_KB for k in keys]
            close = difflib.get_close_matches(key, allk, n=1, cutoff=0.88)
            hits = [e for e in JV_KB if close and close[0] in e[0]]
        if hits:
            name = key if len(key) <= 12 else key[:12]
            say(f"{hits[0][0][0].upper() if len(hits[0][0][0]) <= 5 else hits[0][0][0].capitalize()}: {hits[0][1]}")
            return True
        if jv_brain(orig, t):
            return True
        if CONTESTO.get("jv_named") and re.match(r"^(?:what is|what are|who is|what does|explain|define|tell me about|"
                                                 r"cos|che cos|spiega|parlami)", s) and len(key) >= 3:
            if jv_try_deep(orig, t):                       # not a word: a file here ('tell me about a.txt'), what is inside...
                return True
            say(f"I don't have '{safe(key)}' in my glossary yet, sir. I know file types, PC and Windows terms, security, "
                f"games and programming words. Ask me about a file, or say 'jarvis examples'.")
            return True
    # a bare word or two: "jarvis dll", "jarvis ssd", "jarvis cry of fear"
    if CONTESTO.get("jv_named") and 1 <= len(s.split()) <= 3 and not CONTESTO.get("file"):
        key = s.strip("'\"` ").lstrip(".")
        if key in JV_GAMES_KB:
            say(JV_GAMES_KB[key] + f" Say 'jarvis open {key}' to start it.")
            return True
        hits = sorted((e for e in JV_KB if key in e[0]), key=lambda e: e[0][0] != key)
        if hits and len(key) >= 2 and not (jv_needs_file(t) and not CONTESTO.get("file")) and jv_try_deep(orig, t):
            return True                                              # 'jarvis duplicates' lists them, it does not define them
        if hits and len(key) >= 2:
            say(f"{hits[0][0][0].upper() if len(hits[0][0][0]) <= 5 else hits[0][0][0].capitalize()}: {hits[0][1]}")
            return True
    return jv_brain(orig, t)


def jv_typofix(texto):
    """Repair obvious typos of Jarvis' own keywords ('serach', 'biggset'). Names of files are never touched."""
    vocab = ["open", "launch", "select", "search", "find", "scan", "status", "battery", "memory", "corrupt", "damaged",
             "duplicates", "biggest", "largest", "smallest", "newest", "oldest", "modified", "folder", "files", "lines",
             "words", "columns", "tables", "dimensions", "checksum", "maintenance", "examples", "calculate", "convert",
             "explain", "describe", "inside", "contents", "games", "security", "weather", "joke", "again", "repeat"]
    out_t, changed = [], False
    for tok in texto.split():
        bare = tok.strip(".,;:!?()[]{}\"'`")
        low = bare.lower()
        if (len(bare) >= 5 and bare.isalpha() and low not in vocab and not os.path.exists(os.path.expanduser(bare))
                and low != "jarvis"):
            c = difflib.get_close_matches(low, vocab, n=1, cutoff=0.8)
            if c:
                tok = tok.replace(bare, c[0])
                changed = True
        out_t.append(tok)
    return " ".join(out_t) if changed else texto


def jv_upd_log_miss(text):
    """Remember a sentence Jarvis did not understand (one line, in jarvis_update/unknown_phrases.log), so it can be taught."""
    text = jv_upd_clean(text, 200)
    if not text or CONTESTO.get("jv_nolog"):
        return
    try:
        path = os.path.join(jv_upd_sub("."), "unknown_phrases.log")
        if os.path.isfile(path) and os.path.getsize(path) > 200_000:
            return
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {text}\n")
    except OSError:
        pass


def jv_misses_show():
    """'jarvis what didn't you understand': the last phrases I could not handle."""
    path = os.path.join(jv_upd_dir(), "unknown_phrases.log")
    try:
        with open(guard_path(path), encoding="utf-8", errors="replace") as f:
            lines = [l.rstrip() for l in f if l.strip()]
    except OSError:
        lines = []
    if not lines:
        jarvis_say("Nothing yet, sir: every sentence so far was understood.")
        return
    jarvis_say(f"{len(lines)} sentence(s) I could not handle so far; the last {min(20, len(lines))}:")
    for l in lines[-20:]:
        out("    " + safe(l), GRAY)
    out(f"  (kept in {safe(path)}: send them over and they get taught)", GRAY)


def jv_didnt_catch(text):
    jv_upd_log_miss(re.sub(JV_NAMED_RE, " ", text, flags=re.I))
    if jv_claude_fallback(text):       # 3.2.0: unknown requests are answered by Claude Code, pasted as JARVIS
        return
    t = re.sub(JV_NAMED_RE, " ", text, flags=re.I).strip().lower().rstrip("?!. ")
    if re.match(r"^(?:what|who|why|when|where|how|which|is|are|can|does|do|did|will|would|should|cosa|che|chi|perch|quando|dove|come|quale)\b", t):
        jarvis_say("I can't answer that one offline, sir. I know files, games, your PC, maths, units, dates and a glossary of "
                   "file types and tech terms.")
    else:
        jarvis_say("I'm afraid I didn't catch that, sir.")
    pool = [x.lower() for x in JV_SUGGEST] + [qu.lower().rstrip("?") for _, qu, _ in JV_FAQ]
    close = difflib.get_close_matches(t, pool, n=3, cutoff=0.4) if t else []
    if close:
        jarvis_say("Did you mean: " + "  |  ".join(f"'{c}'" for c in close) + "?")
    else:
        jarvis_say("Try 'examples' to see everything I understand, or 'help'.")


JV_ACTION_VERBS = ("open", "launch", "start", "play", "run", "read", "select", "show", "find", "scan", "search", "list",
                   "check", "tell", "explain", "calculate", "convert", "count", "give", "get", "see", "view", "look",
                   "apri", "avvia", "lancia", "gioca", "leggi", "seleziona", "mostra", "trova", "cerca", "controlla",
                   "dimmi", "spiega", "calcola", "converti", "conta", "fammi", "dammi", "vedere", "guarda")


def jv_unwrap(orig):
    """'can you open X' / 'i want to play X' / 'let's open X' / 'puoi aprire X' -> 'open X';
    'i want to know what a dll is' / 'puoi dirmi cosa e una gpu' -> 'what is a dll' / 'cosa e una gpu'."""
    low = orig.lower().replace("'", " ").strip()
    m = re.match(r"^(?:(?:please|pls|per favore|ok|so|hey|ehi)[,\s]+)*(?:i want to know|i wanna know|i d like to know|"
                 r"i would like to know|can you tell me|could you tell me|do you know|you know|tell me|let me know|"
                 r"explain to me|explain|describe|define|spiegami|spiega|descrivimi|"
                 r"puoi dirmi|puoi dire|mi puoi dire|mi sai dire|sai dirmi|sai dire|dimmi|vorrei sapere|voglio sapere|"
                 r"mi dici|mi spieghi|puoi spiegarmi|puoi spiegare|mi spiegheresti)\s+"
                 r"((?:what|who|how|which|where|why|when|cosa|che|chi|come|quale|quanto|dove|perche|quando)\b.*)$", low)
    if m:
        orig = low = m.group(1).strip()
        mm = re.match(r"^(what|who|cosa|chi)\s+(?:an?\s+|the\s+)?(.+?)\s+(is|are|means|mean)$", low)
        if mm and mm.group(1) in ("what", "who"):
            orig = low = f"what is {mm.group(2)}"
        return jv_unwrap(orig) if orig != low else orig
    s = orig.strip()
    low = s.lower()
    m = re.match(r"^(?:(?:please|pls|per favore|per piacere|ok|so|then|and|ehi|hey)[,\s]+)*"
                 r"(?:can you|could you|would you|will you|can u|could u|would u|can you please|could you please|"
                 r"i want you to|i need you to|i would like you to|i d like you to|i want to|i wanna|i need to|i d like to|"
                 r"i would like to|lets|let us|let s|go ahead and|try to|you should|you can|"
                 r"puoi|potresti|mi puoi|mi potresti|riesci a|vorrei|voglio|devo|dovresti|fammi|facciamo|andiamo a|"
                 r"mi fai il favore di|ho bisogno di|ho voglia di|mi va di)\s+(.+)$", low.replace("'", " "))
    if not m:
        return orig
    rest = m.group(1).strip()
    first = rest.split()[0] if rest.split() else ""
    stem = {"aprirmi": "apri", "avviarmi": "avvia", "lanciarmi": "lancia", "mostrarmi": "mostra", "leggermi": "leggi",
            "trovarmi": "trova", "cercarmi": "cerca", "aprirmelo": "apri", "farmi": "fammi", "darmi": "dammi",
            "aprire": "apri", "avviare": "avvia", "lanciare": "lancia", "giocare": "gioca", "leggere": "leggi",
            "selezionare": "seleziona", "mostrare": "mostra", "trovare": "trova", "cercare": "cerca",
            "controllare": "controlla", "calcolare": "calcola", "convertire": "converti", "vedere": "guarda",
            "spiegare": "spiega", "contare": "conta"}.get(first)
    if stem:
        rest = stem + rest[len(first):]
        first = stem
    if first in JV_ACTION_VERBS:
        return jv_unwrap(rest) if rest.split()[0] in ("explain", "tell", "describe", "spiega", "dimmi") else rest
    return orig


