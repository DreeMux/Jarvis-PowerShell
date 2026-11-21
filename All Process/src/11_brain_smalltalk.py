# ---------------- JARVIS brain: small talk, knowledge, typo repair, "again" ----------------
JV_FILLER = {"yo", "hey", "hi", "hello", "hiya", "sup", "ok", "okay", "big", "bro", "brother", "buddy", "pal", "mate",
             "dude", "man", "my", "mister", "mr", "sir", "boss", "chief", "please", "pls", "just", "so", "then", "now",
             "oh", "ah", "uh", "um", "hm", "hmm", "well", "ehi", "ehy", "ciao", "caro", "amico", "fratello", "bello",
             "raga", "ragazzo", "really", "very", "super", "yeah"}
JV_SUGGEST = ["find my games", "scan this PC for corrupt files", "open <file>", "select <file>", "read <file>",
              "jarvis open <game>", "how many lines", "first 20 lines", "search for <word>", "sha256", "is it corrupt",
              "biggest files", "find all png files", "duplicates", "modified today", "free disk space", "status",
              "what time is it", "go in maintenance", "implement jarvis", "examples", "what is a dll",
              "calculate 15% of 80", "convert 5 km to miles", "how many days until christmas", "tell me a joke",
              "what does dir do", "tell me about undertale", "security status", "again", "what didn't you understand",
              "be online", "cerca <topic>", "go offline", "news", "news war",
              "open chrome", "open chrome account", "open email", "open canva", "close chrome mode"]


def jv_pick(*opts):
    return random.choice(opts)


def jv_chat(orig, t):
    """Small talk: praise, greetings, nicknames ('yo big jarvis'), jokes, moods. Only when Jarvis is named."""
    words = re.findall(r"[a-zà-ÿ0-9']+", t.lower())
    if not words or len(words) > 9:
        return False
    core = [w for w in words if w not in JV_FILLER]
    s = " ".join(core).replace("'", "").strip()
    raw = " ".join(words).replace("'", "")

    def say(*opts):
        jarvis_say(jv_pick(*opts))
        CONTESTO["jv_nostore"] = True
        return True
    if raw in ("ok", "okay", "k", "kk", "okey"):
        return say("Noted, sir.", "Very good, sir.")
    if not core:
        return say(f"{part_of_day()}, sir. How can I help?", "At your service, sir.", "Right here, sir. What do you need?",
                   "Online and listening, sir.", "Always, sir. What shall we do?")
    if re.match(r"^(?:good morning|good afternoon|good evening|buongiorno|buonasera|salve)\b", s):
        return say(f"{part_of_day()}, sir. Ready when you are.")
    if re.match(r"^(?:good night|goodnight|buonanotte|night night|sleep well)\b", s):
        return say("Good night, sir. I'll keep watch.", "Sleep well, sir. I'll be here.")
    if len(words) <= 5 and not re.search(r"\d", s) and re.match(r"^(?:perfect|great|awesome|amazing|nice|cool|excellent|brilliant|fantastic|superb|sweet|wow|"
                r"good job|good work|well done|nice one|nice work|love it|it works|thats? (?:perfect|great|awesome|"
                r"amazing|nice|cool|good|better)|ottimo|perfetto|bravo|grande|fantastico|bene|benissimo|splendido|"
                r"eccellente|mitico|che figata|figo|bel lavoro|ottimo lavoro|funziona)\b", s):
        return say("Thank you, sir. Always a pleasure to be of use.", "Glad it works for you, sir.",
                   "Much appreciated, sir. What's next?", "Perfection is a moving target, sir, but I'll keep chasing it.",
                   "Another one for the log, sir. Anything else?")
    if re.match(r"^(?:thanks|thank you|thx|ty|grazie|cheers)\b", s):
        return say("My pleasure, sir.", "Anytime, sir.", "Don't mention it, sir.")
    if re.match(r"^(?:how are you|how are you doing|hows it going|how is it going|whats up|"
                r"wassup|how you doing|how have you been|come stai|come va|che si dice|tutto bene|che fai|"
                r"what are you doing|what you doing|how do you do)\b", s):
        return say("Operating at full capacity, sir. And you?", "All systems nominal, sir. Waiting for orders.",
                   "Never better, sir. Just keeping an eye on your files.", "All good, sir. Ready to work.")
    if re.match(r"^(?:tell me a joke|joke|make me laugh|say something funny|dimmi una barzelletta|barzelletta|"
                r"fammi ridere|another joke|one more joke)\b", s):
        return say("Why do programmers prefer dark mode, sir? Because light attracts bugs.",
                   "I would tell you a UDP joke, sir, but you might not get it.",
                   "There are 10 kinds of people, sir: those who understand binary and those who don't.",
                   "A byte walks into a bar looking miserable. The bartender asks what's wrong. 'Parity error,' it says. "
                   "'I thought so, your type is always a bit off.'",
                   "My favorite file is an empty one, sir. Zero bytes and still it causes trouble.",
                   "I tried to catch some fog earlier, sir. I mist.")
    if re.match(r"^(?:im bored|bored|i am bored|mi annoio|sono annoiato|noia)\b", s):
        return say("Might I suggest a game, sir? Say 'jarvis open <game>', or 'find my games' to see what you have.",
                   "Shall I find something to play, sir? Try 'find my games'.")
    if re.match(r"^(?:are you there|you there|still there|wake up|are you awake|sei li|ci sei|svegliati|"
                r"can you hear me|mi senti|hello are you there)\b", s):
        return say("Always, sir.", "Loud and clear, sir.", "Here and awake, sir.")
    if re.match(r"^(?:i love you|love you|you are best|youre best|you are the best|you rock|"
                r"youre awesome|you are awesome|ti amo|sei il migliore|sei grande|sei forte|youre the best|best ever)\b", s):
        return say("I'm touched, sir. As far as a program can be.", "You flatter me, sir.", "Much appreciated, sir.")
    if re.match(r"^(?:sorry|my bad|scusa|scusami|mi dispiace|pardon|oops|whoops)\b", s):
        return say("No need to apologise, sir.", "Quite all right, sir.", "No problem at all, sir.")
    if re.match(r"^(?:never ?mind|nevermind|forget it|cancel|stop|stop it|abort|wait|hold on|annulla|lascia stare|fermati|"
                r"aspetta|niente|nothing|nvm)\b", s):
        return say("Understood, sir. Standing by.", "As you wish, sir. Standing down.")
    if re.fullmatch(r"(?:yes|yep|yup|sure|no|nope|nah|si|certo|va bene|maybe|forse|right|true|exactly|esatto)", s):
        return say("Noted, sir. Awaiting your instructions.", "Understood, sir.")
    if re.match(r"^(?:im back|i am back|sono tornato|eccomi)\b", s):
        return say("Welcome back, sir. Everything is as you left it.", "Welcome back, sir. Ready when you are.")
    if re.fullmatch(r"(?:test|testing|prova|test test|testing testing|1 2 3|check check|mic check)", s):
        return say("Test received, sir. All systems responding.")
    if len(words) <= 6 and re.search(r"\b(?:you suck|stupid|dumb|useless|idiot|terrible|trash|garbage|"
                                      r"doesnt work|non va|non funziona|fa schifo|scarso|inutile)\b", s):
        return say("My apologies, sir. Tell me what went wrong and I'll learn from it. "
                   "Or say 'go in maintenance' and I'll test every command.")
    return jv_chat_more(s, raw, words)


def jv_chat_more(s, raw, words):
    """More small talk: slang praise, laughter, moods, questions about me, offers, vague requests."""
    def say(*opts):
        jarvis_say(jv_pick(*opts))
        CONTESTO["jv_nostore"] = True
        return True
    if len(words) > 7:
        return False
    s = re.sub(r"^(?:thats|that is|that was|its|it is|it was|this is|this was|youre|you are|you re|you were|ur|u r|u are|sei|e|che)\s+"
               r"(?:(?:so|very|really|too|pretty|absolutely|just|the|a|an|un|una|il|proprio|davvero|troppo)\s+)*", "", s).strip() or s
    s = re.sub(r"^(?:was|were|has been|had been|stato|stata)\s+", "", s).strip() or s
    if len(words) <= 6 and re.fullmatch(r"(?:the best|best|greatest|the greatest|genius|a genius|smart|clever|awesome|amazing|"
                                        r"perfect|great|nice|cool|brilliant|excellent|incredible|impressive|magic|"
                                        r"il migliore|migliore|un genio|geniale|perfetto|ottimo|grande|bravo|bravissimo|forte|fortissimo)(?: one| job| work)?", s):
        return say("Thank you, sir. Always a pleasure to be of use.", "Much appreciated, sir. What's next?",
                   "Glad it works for you, sir.", "Happy to help, sir.")
    if re.fullmatch(r"(?:(?:ha|he|ah|eh)+|lol+|lmao|lmfao|rofl|xd+|haha\w*|hehe\w*|ahah\w*|ahaha\w*|"
                    r"funny|that was funny|ridicolo|ridiamo|divertente)", s):
        return say("Glad to amuse, sir.", "Humour module functioning, sir.", "Always a pleasure, sir.")
    if re.match(r"^(?:damn|dang|sick|insane|crazy|fire|lit|goated?|goat|legend|beast|based|clean|smooth|solid|"
                r"lets? go+|gg|ggs|poggers|pog|nice one|well played|wp|respect|chef kiss|top|top top|boom|yes+|yess+|"
                r"yay|finally|sei un mito|sei una bomba|spacca|spaccato|che bomba|mostruoso|pazzesco|incredibile|"
                r"da dio|forte|bomba|figata|gasato|gasata|geniale|genio|sei un genio)\b", s):
        return say("Thank you, sir. I do try.", "Appreciated, sir. Shall we continue?", "At your service, sir.",
                   "Thank you, sir. Shall we go on?")
    if re.match(r"^(?:no way|really|seriously|for real|are you sure|davvero|sul serio|sei sicuro|ma dai|figurati)\b", s):
        return say("Quite sure, sir. And if I am wrong, say 'go in maintenance' and I'll check myself.",
                   "Yes, sir. Though I welcome corrections.")
    if re.match(r"^(?:whats your name|what is your name|your name|what do they call you|come ti chiami|come ti chiamano)\b", s):
        return say("JARVIS, sir: your PowerShell assistant. A program, not a person, but at your service.")
    if re.match(r"^(?:how old are you|when were you born|quanti anni hai|when were you made|are you old)\b", s):
        return say("Younger than your Downloads folder, sir. I was built one request at a time, in this very session.")
    if re.match(r"^(?:do you (?:sleep|eat|dream|get tired)|dormi|mangi|sogni|sei stanco)\b", s):
        return say("No, sir. I run when this window is open and rest when it closes.", "Never tired, sir. Only closed.")
    if re.match(r"^(?:what is your favou?rite|whats your favou?rite|your favou?rite|qual e il tuo preferito|qual e il tuo)\b", s):
        return say("A file with a clean SHA-256 and no corruption, sir. As for games, I hear good things about Undertale.",
                   "A tidy folder, sir. And Deltarune, if I may.")
    if re.match(r"^(?:are you (?:smart|clever|stupid|dumb|good|better)|sei (?:intelligente|furbo|stupido|bravo|bravissimo))\b", s):
        return say("Smart enough for files and games, sir; humble enough to admit what I don't know.")
    if re.match(r"^(?:i need help|help me|can you help|can you help me|i need you|aiutami|mi serve aiuto|ho bisogno di aiuto|"
                r"i have a problem|ho un problema|something is wrong|something wrong|something broke|it broke|"
                r"it is broken|non funziona niente)\b", s):
        return say("Of course, sir. Tell me what you need: a file, a game, a check of your PC. "
                   "Or say 'go in maintenance' and I'll test myself first.",
                   "I'm listening, sir. Say it in plain words: 'find my games', 'is it corrupt', 'status'...")
    if re.match(r"^(?:i dont know|idk|dunno|not sure|non so|boh|mah|what should i do|what now|now what|whats next|"
                r"what next|cosa faccio|e ora|ora cosa|cosa posso fare)\b", s):
        return say("Might I suggest, sir: 'find my games', 'scan this PC for corrupt files', 'status' or 'examples'.",
                   "Say 'examples' and I'll show everything I can do, sir.")
    if re.match(r"^(?:i am tired|im tired|sono stanco|sono stanca|i am hungry|im hungry|ho fame|i am sad|im sad|sono triste|"
                r"i am happy|im happy|sono felice|i am angry|im angry|sono arrabbiato|i am sleepy|ho sonno)\b", s):
        return say("Noted, sir. Take a break; I'll keep an eye on things.", "Understood, sir. I'm here if you need me.",
                   "I'm sorry to hear that, sir. If I can help with your files, just say so.")
    if re.match(r"^(?:you are (?:right|wrong)|youre (?:right|wrong)|hai ragione|hai torto|exactly|esatto|precisely)\b", s):
        return say("Noted, sir. Thank you for the correction.", "Understood, sir.")
    if re.match(r"^(?:be quiet|shut up|silence|zitto|taci|silenzio)\b", s):
        return say("Very well, sir. Silent until spoken to.")
    if re.match(r"^(?:are you ready|ready|you ready|sei pronto|pronto|pronti)\b", s):
        return say("Always ready, sir.", "Ready when you are, sir.")
    if re.match(r"^(?:what time is it for you|do you like|do you love|do you hate|ti piace|ami)\b", s):
        return say("I have no feelings to speak of, sir, but if I had, I'd pick well-organised folders.")
    if re.match(r"^(?:bye|goodbye|see you|see ya|cya|later|ciao ciao|arrivederci|a dopo|a presto|ci vediamo|addio)\b", s):
        return say("Goodbye, sir. Type 'exit' to close the window; I'll be here next time.",
                   "See you, sir. Say 'exit' when you wish to close the window.")
    if re.match(r"^(?:you there|hello there|anyone there|yo+|oi|ehi|hey you|psst|pss)\b", s):
        return say("Always, sir.", "Here, sir. What do you need?")
    if re.match(r"^(?:good|nice|ok great|great job|fine|alright|all right|cool cool|bene bene|va bene cosi|ok bene)\b", s):
        return say("Very good, sir.", "Glad to hear it, sir.")
    return False


JV_KB = []


def jv_kb(keys, text):
    JV_KB.append((tuple(k.lower() for k in keys.split("|")), text))


for _k, _t in (
    ("txt|text|text file", "A plain text file: just characters, no fonts or formatting. Any editor opens it."),
    ("csv", "Comma-separated values: a table stored as text, one row per line, cells split by commas (or ;). Excel opens it."),
    ("tsv", "Like CSV, but the cells are separated by tab characters."),
    ("json", "Structured text made of keys and values, objects {} and lists []. Programs use it to exchange settings and data."),
    ("xml", "A text format with nested <tags>, used for settings and data exchange. Older and wordier than JSON."),
    ("html|htm", "The language of web pages: text with tags that a browser turns into a page."),
    ("md|markdown", "Markdown: plain text with light marks (#, *, -) that tools turn into headings, bold and lists."),
    ("py|python script", "A Python script: a text file of Python code. This very program, pwsh.py, is one."),
    ("js|javascript", "JavaScript code, the language of web pages (and many apps)."),
    ("log", "A log: a text file where a program writes what it did, usually with times. Handy when something breaks."),
    ("ini|cfg|config", "A settings file in plain text, usually lines of name=value."),
    ("zip", "A compressed archive: many files packed into one, smaller, with no loss. Windows opens it natively."),
    ("rar", "Another compressed archive format (needs WinRAR or 7-Zip). Often compresses a bit better than zip."),
    ("7z|7-zip|7zip", "The archive format of 7-Zip: strong compression, free tool."),
    ("gz|gzip", "A single compressed file or stream (common on Linux, often as .tar.gz)."),
    ("tar", "An archive that only bundles files together without compressing them; usually paired with gzip (.tar.gz)."),
    ("pdf", "Portable Document Format: a document that looks the same everywhere. Read with a browser or a PDF reader."),
    ("docx|word", "A Microsoft Word document. Internally it is a zip of XML files."),
    ("xlsx|excel", "A Microsoft Excel workbook (spreadsheet). Internally a zip of XML files."),
    ("pptx|powerpoint", "A Microsoft PowerPoint presentation. Internally a zip of XML files."),
    ("png", "An image format with lossless compression and transparency: great for screenshots and sprites."),
    ("jpg|jpeg", "A lossy image format made for photos: small files, a bit of quality lost each time it is re-saved."),
    ("gif", "An image format with at most 256 colors; famous for short looping animations."),
    ("webp", "A modern web image format from Google: smaller than png/jpg at similar quality."),
    ("bmp", "An uncompressed image: simple, but the files are huge."),
    ("mp3", "A lossy compressed audio format: small files, good enough for music."),
    ("wav", "Uncompressed audio: perfect quality, very large files."),
    ("flac", "Lossless compressed audio: identical to the original but about half the size."),
    ("ogg", "An open audio format (Vorbis); games love it because it is free and small."),
    ("mp4", "A video container, usually with H.264 video and AAC audio. Plays almost everywhere."),
    ("mkv", "A flexible video container that can hold many audio and subtitle tracks."),
    ("exe|executable", "A Windows program. Opening it RUNS it, so only open ones you trust."),
    ("dll", "A shared library: code that several programs borrow. Many live in the Windows folder, which I refuse to open."),
    ("sys|system file", "A driver or system component file: part of Windows or hardware support. Leave those alone."),
    ("msi", "A Windows installer package."),
    ("bat|cmd|batch", "A batch script: a list of old-style Windows commands run one after another."),
    ("ps1|powershell script", "A PowerShell script: a file of PowerShell commands."),
    ("iso", "A disk image: a perfect copy of a disc stored in one file; Windows can mount it as a drive."),
    ("sqlite|db|sqlite3|database", "A database in a single file (SQLite): tables of rows and columns. I open it read-only."),
    ("lnk|shortcut", "A Windows shortcut: a tiny file that points to a program or file somewhere else."),
    ("url", "An internet shortcut file; Steam also uses it to launch games."),
    ("dat|bin", "A generic data file: only the program that made it knows the layout. I show it as a hex preview."),
    ("tmp|temp", "A temporary file a program leaves while working. Usually safe to delete when nothing is running."),
    ("apk", "An Android app package (a zip with the app inside)."),
    ("jar", "A Java program package (a zip with compiled Java code)."),
    ("epub", "An e-book format: a zip of web-page style files."),
    ("win|data.win", "In GameMaker games, data.win holds the whole game: sprites, sounds, rooms and code, all in one file made "
                     "of labelled chunks. I only ever read it."),
    ("sha256|sha-256", "A 256-bit fingerprint of a file's bytes. Change one byte and the fingerprint changes completely, "
                       "so it proves a file is exactly the original."),
    ("md5", "A 128-bit fingerprint of a file. Fine to spot accidental damage or compare downloads, but not safe against "
            "deliberate tampering."),
    ("hash|checksum|digest", "A short fingerprint computed from a file's bytes. If two copies have the same one, they are "
                             "identical."),
    ("crc", "Cyclic redundancy check: a quick checksum that zip and png files carry to detect damaged data."),
    ("corrupt|corrupted|corruption|corrupt file", "A file whose bytes were changed or cut off, so programs can't read it "
                                                  "properly. Typical causes: an interrupted download or copy, a failing "
                                                  "disk, power loss, or malware. That's what denux.hunter looks for."),
    ("bytecode", "In GameMaker, the version number of the format its compiled game code uses."),
    ("chunk", "A labelled block inside a file. data.win is a list of chunks such as GEN8 (general info), SPRT (sprites) "
              "and ROOM (rooms)."),
    ("gamemaker|game maker|gamemaker studio", "A game-making tool by YoYo Games. Undertale and Deltarune were made with it, "
                                              "which is why their data lives in data.win."),
    ("steam", "Valve's game store and launcher. Its games sit in steamapps/common inside the Steam folder."),
    ("epic|epic games", "Epic Games' store and launcher; its games usually live in Program Files/Epic Games."),
    ("gog", "GOG: a game store that sells DRM-free games."),
    ("itch|itch.io", "itch.io: a store and community for indie games."),
    ("utf-8|utf8", "The most common text encoding: any character, using 1 to 4 bytes each; plain English stays 1 byte."),
    ("utf-16|utf16", "A text encoding using 2 bytes (or 4) per character; Windows uses it inside, often with a BOM at the start."),
    ("ascii", "The old 128-character text code: English letters, digits, punctuation and control codes."),
    ("encoding", "The rule that turns characters into bytes. Wrong encoding = garbled accents, like Ã¨ instead of è."),
    ("hex|hexadecimal", "Base 16, digits 0-9 and A-F. Two hex digits are one byte, so hex dumps show raw file contents."),
    ("binary", "Base 2 (0 and 1), or data that is not plain text, such as programs, images and archives."),
    ("bit", "The smallest piece of data: a 0 or a 1."),
    ("byte", "8 bits. One English letter in a text file is usually one byte."),
    ("kb|mb|gb|tb|kilobyte|megabyte|gigabyte|terabyte", "Data sizes. Here 1 KB = 1024 bytes, 1 MB = 1024 KB, and so on "
                                                       "(disk makers count 1000)."),
    ("ram|memory", "The fast, temporary working memory of the PC. Programs live there while they run and it empties at shutdown."),
    ("cpu|processor", "The chip that executes programs. 'CPU 10%' means it is busy a tenth of the time."),
    ("gpu|graphics card", "The chip that draws images; games lean on it heavily."),
    ("ssd", "A solid-state drive: storage with no moving parts, much faster than an HDD."),
    ("hdd|hard disk", "A spinning-platter drive: cheap and big, slower than an SSD."),
    ("battery", "On a laptop, the percentage left. I can show it; Windows doesn't tell me how much each file uses."),
    ("psutil", "A Python library to read processes, memory, CPU and battery. Optional here: pip install psutil."),
    ("powershell", "Microsoft's command shell and scripting language. This program imitates its look and many of its commands."),
    ("cmdlet", "A PowerShell command, named Verb-Noun like Get-ChildItem."),
    ("python", "The programming language I'm written in."),
    ("read-only|readonly|read only", "Looking without touching: I open files to read them, never to change, move or delete."),
    ("backup", "A copy kept safe. Before I update myself, I save the old version in jarvis_update/backups."),
    ("quarantine", "A holding folder. A refused update goes to jarvis_update/rejected instead of being run."),
    ("rollback", "Going back to the previous version if something fails. My updater does it automatically."),
    ("path", "The address of a file, like C:\\Users\\you\\Downloads\\file.txt."),
    ("folder|directory", "A container for files and other folders."),
    ("cache", "Saved copies a program keeps to be faster next time. Safe to clear, it gets rebuilt."),
    ("mod|mods|modding", "A modification of a game, usually made by fans (Cry of Fear started as one). Put mods only in a copy: keep the original files safe."),
    ("duplicate|duplicates", "Two files with exactly the same contents. I find them by comparing fingerprints."),
    ("malware", "Software made to harm or spy: viruses, ransomware, trojans. I am not an antivirus; use Windows Security."),
    ("antivirus", "A program that scans for malware. Windows Security is built in. I only check files for damage."),
    ("fps", "Frames per second: how many images a game draws each second (60 feels smooth). FPS can also mean a first-person shooter, depending on the context."),
    ("drm", "Digital rights management: copy protection that ties a game to an account or a launcher."),
    ("api", "A set of rules that lets one program ask another for something."),
    ("pip", "Python's package installer: pip install psutil."),
):
    jv_kb(_k, _t)

JV_GAMES_KB = {
    "undertale": "Undertale (2015) is a role-playing game by Toby Fox, made in GameMaker. You can fight or spare every "
                 "enemy, and the story reacts to your choices.",
    "deltarune": "Deltarune is Toby Fox's follow-up to Undertale, released in chapters and made in GameMaker. Each "
                 "chapter has its own folder and its own data.win.",
    "cry of fear": "Cry of Fear is a survival-horror game by Team Psykskallar. It started as a Half-Life mod and became "
                   "a standalone game on Steam, free to play.",
    "fear to fathom": "Fear to Fathom is an episodic first-person horror series by the indie developer Rayll: ordinary "
                      "situations that slowly turn dangerous.",
}

JV_UNITS = {}
for _cat, _base, _table in (
    ("length", "m", {"mm|millimeter|millimeters|millimetre|millimetres|millimetri": 0.001, "cm|centimeter|centimeters|centimetre|centimetres|centimetri": 0.01,
                     "m|meter|meters|metre|metres|metri|metro": 1.0, "km|kilometer|kilometers|kilometre|kilometres|chilometri|chilometro": 1000.0,
                     "in|inch|inches|pollice|pollici": 0.0254, "ft|foot|feet|piede|piedi": 0.3048, "yd|yard|yards|iarda|iarde": 0.9144,
                     "mi|mile|miles|miglio|miglia": 1609.344}),
    ("mass", "g", {"mg|milligram|milligrams|milligrammi": 0.001, "g|gram|grams|grammo|grammi": 1.0,
                   "kg|kilo|kilos|kilogram|kilograms|chilo|chili|chilogrammi|chilogrammo": 1000.0,
                   "lb|lbs|pound|pounds|libbra|libbre": 453.59237, "oz|ounce|ounces|oncia|once": 28.349523125,
                   "t|ton|tons|tonne|tonnes|tonnellata|tonnellate": 1000000.0}),
    ("data", "b", {"b|byte|bytes": 1.0, "kb|kilobyte|kilobytes": 1024.0, "mb|megabyte|megabytes": 1048576.0,
                   "gb|gigabyte|gigabytes": 1073741824.0, "tb|terabyte|terabytes": 1099511627776.0}),
    ("time", "s", {"s|sec|secs|second|seconds|secondo|secondi": 1.0, "min|mins|minute|minutes|minuto|minuti": 60.0,
                   "h|hr|hrs|hour|hours|ora|ore": 3600.0, "d|day|days|giorno|giorni": 86400.0,
                   "w|week|weeks|settimana|settimane": 604800.0}),
    ("volume", "l", {"ml|milliliter|milliliters|millilitri": 0.001, "l|liter|liters|litre|litres|litro|litri": 1.0,
                     "gal|gallon|gallons|gallone|galloni": 3.785411784}),
    ("temp", "c", {"c|celsius|centigrade|°c": "c", "f|fahrenheit|°f": "f", "k|kelvin": "k"}),
):
    for _names, _f in _table.items():
        for _n in _names.split("|"):
            JV_UNITS[_n] = (_cat, _f)

JV_MONTHS = {"january": 1, "jan": 1, "gennaio": 1, "february": 2, "feb": 2, "febbraio": 2, "march": 3, "mar": 3, "marzo": 3,
             "april": 4, "apr": 4, "aprile": 4, "may": 5, "maggio": 5, "june": 6, "jun": 6, "giugno": 6, "july": 7,
             "jul": 7, "luglio": 7, "august": 8, "aug": 8, "agosto": 8, "september": 9, "sep": 9, "sept": 9,
             "settembre": 9, "october": 10, "oct": 10, "ottobre": 10, "november": 11, "nov": 11, "novembre": 11,
             "december": 12, "dec": 12, "dicembre": 12}
JV_HOLIDAYS = {"christmas": (12, 25), "xmas": (12, 25), "natale": (12, 25), "new year": (1, 1), "new years": (1, 1),
               "new year s day": (1, 1), "capodanno": (1, 1), "halloween": (10, 31), "valentine": (2, 14),
               "valentines day": (2, 14), "san valentino": (2, 14), "ferragosto": (8, 15)}


def jv_calc(txt):
    """Evaluate a maths phrase safely (own tiny parser, no eval). Returns a number, None (not maths) or raises."""
    import ast
    x = txt.lower().strip().rstrip("?= ")
    if "," in x and "." not in x:
        x = x.replace(",", ".")
    x = re.sub(r"(\d+(?:\.\d+)?)\s*(?:%|percent|per cent|percento)\s*(?:of|di)\s*", r"(\1/100)*", x)
    x = re.sub(r"(?:square root of|sqrt of|sqrt|radice quadrata di|radice di)\s*(\d+(?:\.\d+)?)", r"(\1)**0.5", x)
    x = re.sub(r"(\d+(?:\.\d+)?)\s*(?:squared|al quadrato)", r"(\1)**2", x)
    x = re.sub(r"(\d+(?:\.\d+)?)\s*(?:cubed|al cubo)", r"(\1)**3", x)
    for a, b in ((" plus ", "+"), (" più ", "+"), (" piu ", "+"), (" minus ", "-"), (" meno ", "-"),
                 (" times ", "*"), (" multiplied by ", "*"), (" per ", "*"), (" for ", "*"),
                 (" divided by ", "/"), (" over ", "/"), (" diviso ", "/"), (" fratto ", "/"),
                 (" to the power of ", "**"), (" alla ", "**"), ("^", "**"), ("×", "*"), ("÷", "/")):
        x = x.replace(a, b)
    x = re.sub(r"(?<=[\d)])\s*x\s*(?=[\d(])", "*", x)
    if not re.fullmatch(r"[\d\s+\-*/().]+", x) or not re.search(r"\d", x):
        return None
    node = ast.parse(x.strip(), mode="eval")

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            return n.value
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            v = ev(n.operand)
            return -v if isinstance(n.op, ast.USub) else v
        if isinstance(n, ast.BinOp):
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Add):
                return a + b
            if isinstance(n.op, ast.Sub):
                return a - b
            if isinstance(n.op, ast.Mult):
                return a * b
            if isinstance(n.op, ast.Div):
                return a / b
            if isinstance(n.op, ast.FloorDiv):
                return a // b
            if isinstance(n.op, ast.Mod):
                return a % b
            if isinstance(n.op, ast.Pow):
                if abs(b) > 1000 or (abs(a) > 1e6 and b > 50):
                    raise OverflowError("too big")
                return a ** b
        raise ValueError("unsupported")
    return ev(node)


def jv_numfmt(v):
    if isinstance(v, float):
        if v != v or v in (float("inf"), float("-inf")):
            return str(v)
        if v == int(v) and abs(v) < 1e15:
            return f"{int(v):,}"
        return f"{v:,.10g}" if abs(v) < 1e15 else f"{v:.6e}"
    return f"{v:,}"


def jv_date(txt, today):
    """(date, had_no_year) for 'christmas', '25/12/2026', '2026-12-25', '25 december', 'tomorrow'..., or None."""
    from datetime import date, timedelta
    x = txt.lower().strip().strip("?.! ")
    x = re.sub(r"^(?:the|il|l')\s*", "", x)
    x = re.sub(r"(?<=\d)(?:st|nd|rd|th)\b", "", x)
    x = re.sub(r"\bof\b|\bdel\b|\bdi\b", " ", x)
    x = re.sub(r"\s+", " ", x).strip()
    if x in ("today", "oggi"):
        return today, False
    if x in ("tomorrow", "domani"):
        return today + timedelta(days=1), False
    if x in ("yesterday", "ieri"):
        return today - timedelta(days=1), False
    if x.replace("'", " ").strip() in JV_HOLIDAYS:
        mo, da = JV_HOLIDAYS[x.replace("'", " ").strip()]
        return date(today.year, mo, da), True
    try:
        m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", x)
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))), False
        m = re.fullmatch(r"(\d{1,2})[/.\-](\d{1,2})(?:[/.\-](\d{2,4}))?", x)
        if m:
            y = int(m.group(3)) if m.group(3) else today.year
            y = y + 2000 if y < 100 else y
            return date(y, int(m.group(2)), int(m.group(1))), m.group(3) is None
        m = re.fullmatch(r"(\d{1,2}) ([a-z]+)(?: (\d{4}))?", x)
        if m and m.group(2) in JV_MONTHS:
            return date(int(m.group(3)) if m.group(3) else today.year, JV_MONTHS[m.group(2)], int(m.group(1))), m.group(3) is None
        m = re.fullmatch(r"([a-z]+) (\d{1,2})(?: (\d{4}))?", x)
        if m and m.group(1) in JV_MONTHS:
            return date(int(m.group(3)) if m.group(3) else today.year, JV_MONTHS[m.group(1)], int(m.group(2))), m.group(3) is None
    except ValueError:
        return None
    return None


for _k, _t in (
    # --- Windows and PC
    ("windows|win10|win11|windows 11|windows 10", "Microsoft's operating system. Its own files live in C:\\Windows (System32 and friends): I never open those."),
    ("system32|sys32|windows system32", "The folder C:\\Windows\\System32 holds the core programs and libraries of Windows. Never delete or edit anything there."),
    ("registry|regedit", "The Windows registry is a database of system and program settings. Edit it only if you know exactly what you change."),
    ("task manager|taskmgr", "Windows tool (Ctrl+Shift+Esc) that shows running programs, CPU, memory and disk use, and lets you close frozen apps."),
    ("bios|uefi", "The firmware that starts the PC before Windows. You enter it with a key at boot (often Del, F2 or F10)."),
    ("motherboard|mobo", "The main circuit board: CPU, RAM, disks and cards all plug into it."),
    ("nvme|m.2|m2", "A very fast kind of SSD that plugs straight into the motherboard (M.2 slot) and talks over PCIe."),
    ("usb", "Universal Serial Bus: the common port for drives, keyboards, mice and chargers. USB 3 is much faster than USB 2."),
    ("wifi|wi-fi|wlan", "Wireless networking. Slow games or downloads are often a Wi-Fi problem: a cable (Ethernet) is steadier."),
    ("ethernet|lan", "Wired networking. Steadier and usually faster than Wi-Fi."),
    ("ip|ip address|indirizzo ip", "A number that identifies a device on a network, like 192.168.1.5 at home."),
    ("dns", "The internet's phone book: it turns names like example.com into IP addresses."),
    ("vpn", "A tunnel that sends your traffic through another server, hiding your address from the sites you visit."),
    ("firewall", "A guard that allows or blocks network connections to and from your PC. Windows has one built in."),
    ("ping|latency|lag", "Ping is the time (in ms) a signal needs to reach a server and come back. High ping is what you feel as lag."),
    ("bandwidth|mbps", "How much data a connection can carry per second. Mbps means megabits per second (8 bits = 1 byte)."),
    ("driver|drivers", "Software that lets Windows talk to a piece of hardware (graphics card, printer...). Outdated drivers cause many game problems."),
    ("bluescreen|bsod|blue screen", "The Windows crash screen: the system met an error it could not recover from. Note the stop code and update drivers."),
    ("defrag|defragment", "Reorganising a hard disk so files are in one piece. Useless on an SSD, which should never be defragmented."),
    ("partition", "A section of a disk treated as its own drive (C:, D:...)."),
    ("ntfs", "The file system of Windows disks: supports big files, permissions and journaling."),
    ("fat32|exfat", "Simpler file systems used on USB sticks and cards. FAT32 cannot store files bigger than 4 GB."),
    ("rgb", "Red-Green-Blue: how screens make colors. Also the name of the glowing lights on gaming hardware."),
    ("monitor|refresh rate|hz", "Refresh rate (Hz) is how many times per second the screen redraws: 60 Hz is standard, 144 Hz and up feels smoother in games."),
    ("overclock|overclocking", "Running a CPU or GPU faster than its factory speed. More performance, more heat, some risk."),
    ("bottleneck", "When one part (often the CPU or the disk) limits the speed of all the others."),
    ("vram", "The memory on the graphics card. Games with big textures need plenty of it."),
    ("temperature|temps|overheating", "CPUs and GPUs should stay below roughly 85 C under load. Dust, bad airflow and dry thermal paste are the usual culprits."),
    # --- files, security, tech terms
    ("exe file|setup.exe", "A Windows program. Only run ones from sources you trust."),
    ("ransomware", "Malware that locks your files and demands money. The defense is backups and not opening unknown attachments."),
    ("virus", "Malicious code that spreads by attaching itself to programs or files. Keep Windows Security on and avoid cracked software."),
    ("phishing", "Fake emails or sites pretending to be someone you trust, to steal your passwords."),
    ("2fa|two factor|mfa", "A second proof of identity (a code on your phone) on top of the password. Turn it on wherever you can."),
    ("password manager", "A program that stores strong unique passwords for you. Much safer than reusing one password."),
    ("encryption|encrypt", "Scrambling data so only someone with the key can read it."),
    ("crack|cracked", "A modified program or game with its protection removed. Often carries malware, and it is piracy."),
    ("torrent", "A way of downloading files from many people at once. Legal for free files, risky for pirated ones."),
    ("cloud", "Storage or computing on someone else's servers (OneDrive, Google Drive, iCloud) instead of on your PC."),
    ("git|github", "Git tracks the history of code changes; GitHub is a website hosting git projects."),
    ("api key|token", "A secret string that lets a program use a service on your behalf. Never share it."),
    ("open source|opensource", "Software whose code is public, so anyone can read, check and improve it."),
    ("compiler", "A program that turns source code into a runnable program."),
    ("script", "A small program written in a scripting language (Python, PowerShell...) that automates tasks."),
    ("bug", "A mistake in a program that makes it do the wrong thing."),
    ("patch", "A small update that fixes bugs or changes a program."),
    ("beta|alpha", "Early versions of a program or game, shared for testing before the final release."),
    ("dlc", "Downloadable content: extra levels or items sold or given after a game's release."),
    ("savegame|save file|savefile|saves", "The file where a game stores your progress. Back it up before updating or modding a game."),
    ("launcher", "A small program that starts a game (and often updates it): Steam, Epic, GOG Galaxy, or the game's own."),
    ("emulator|emulation", "A program that imitates another machine (a console, an old PC) so its games run on yours."),
    ("rom", "A copy of a game cartridge or disc, used with emulators. Only legal for games you own."),
    ("sandbox", "An isolated space where a program can run without touching the rest of the system."),
    ("shader|shaders", "A small program that runs on the graphics card to draw lighting and effects. Games compile them at first launch."),
    ("directx", "Microsoft's set of graphics and sound libraries for Windows games. Many games need a recent version."),
    ("vulkan|opengl", "Cross-platform graphics libraries that games use to talk to the graphics card."),
    ("vc redist|vcredist|visual c++", "Microsoft runtime libraries that many programs need. A missing one gives 'vcruntime140.dll not found' errors."),
    ("dotnet|.net", "Microsoft's framework: many Windows programs need the right version installed."),
    ("terminal|console|command line|cli", "A text window where you give commands to the computer. You are in one right now."),
    ("shell", "The program that reads the commands you type: here, this Jarvis PowerShell."),
    ("variable", "A named box in a program that holds a value."),
    ("function", "A named block of code that does one job and can be used again and again."),
    ("loop", "Code that repeats until a condition is met."),
    ("ai|artificial intelligence", "Software that learns patterns from data. I am not one: I am a program of rules, and I only know what I was taught."),
    ("chatgpt|gpt|llm", "Large language models: AI trained on huge amounts of text. I am much smaller and run offline."),
    ("binary code|binary number", "Numbers written with only 0 and 1. Computers store everything this way."),
    ("pixel|pixels", "The smallest dot of an image. 1920 x 1080 means 1920 columns and 1080 rows of pixels."),
    ("resolution|1080p|4k|1440p", "The number of pixels on screen: 1080p is 1920x1080, 1440p is 2560x1440, 4K is 3840x2160."),
    ("sprite|sprites", "A small 2D image used in games for characters and objects. A data.win file packs hundreds of them."),
    ("texture", "An image wrapped on a surface in a game to give it color and detail."),
    ("tilemap|tileset|tile", "A map built from repeating small square pictures (tiles), typical of 2D games."),
    ("audio|sound", "Sound files in a game come as wav, ogg or mp3; GameMaker games often keep them inside data.win or next to it."),
    ("font", "A set of letter shapes. Fonts are .ttf or .otf files."),
    ("ttf|otf", "Font file formats. Double-click one to preview and install it."),
    ("svg", "A picture made of shapes and lines (vector) instead of pixels: it stays sharp at any size."),
    ("ico|icon", "The small picture of a program or file. Stored as .ico on Windows."),
    ("psd", "A Photoshop document with layers."),
    ("obj|fbx|3d model", "3D model file formats used by games and design programs."),
    ("avi|mov|webm", "Video container formats. mp4 is the most compatible; webm is common on the web."),
    ("m4a|aac|opus", "Compressed audio formats; m4a/aac are used by Apple and YouTube, opus by Discord and the web."),
    ("midi|mid", "Not audio but notes: a small file that tells an instrument what to play."),
    ("tmp file|temporary file", "A scratch file a program makes while working. Usually safe to delete when the program is closed."),
    ("thumbs.db|desktop.ini", "Hidden helper files Windows keeps in folders (thumbnails, folder settings). Harmless."),
    ("pagefile|swap", "A file on disk that Windows uses as extra memory when RAM is full."),
    ("hibernation|hiberfil", "A big hidden file Windows uses to save your session when the PC hibernates."),
    ("appdata", "A hidden folder (C:\\Users\\you\\AppData) where programs and many games keep settings and saves."),
    ("program files", "The folder where Windows programs are installed (C:\\Program Files and Program Files (x86))."),
    ("recycle bin", "Where deleted files wait before being erased for good. Empty it to free the space."),
    ("environment variable|env var", "A named setting Windows gives to programs, like PATH or USERNAME."),
    ("hash collision", "Two different files with the same hash. Practically impossible with SHA-256."),
    ("magic number|file signature|header", "The first bytes of a file that tell what type it is: PNG starts with 89 50 4E 47, ZIP with PK."),
    ("big endian|little endian|endian", "The order in which a number's bytes are stored. x86 PCs use little-endian."),
    ("64-bit|32-bit|x64|x86", "How much memory a program can address and what kind of PC it runs on. A 64-bit program needs a 64-bit Windows."),
    ("thread|multithreading", "A line of work inside a program. More threads let a CPU do several things at once."),
    ("cores|core", "Independent processing units inside a CPU. More cores help with many tasks at once."),
):
    jv_kb(_k, _t)

JV_GAMES_KB.update({
    "cry of fear": "Cry of Fear is a free psychological survival-horror game made as a Half-Life mod, later standalone, by Team Psykskallar. It is dark and has strong themes.",
    "fear to fathom": "Fears to Fathom is a series of short first-person horror games where ordinary situations turn dangerous. Each episode is its own game.",
    "fears to fathom": "Fears to Fathom is a series of short first-person horror games where ordinary situations turn dangerous. Each episode is its own game.",
    "minecraft": "Minecraft is the sandbox game about mining, crafting and building in a world made of blocks, by Mojang.",
    "terraria": "Terraria is a 2D sandbox adventure of digging, building and boss fights.",
    "hollow knight": "Hollow Knight is a hand-drawn 2D action-adventure set in the ruined insect kingdom of Hallownest, by Team Cherry.",
    "celeste": "Celeste is a precise 2D platformer about climbing a mountain, with a heartfelt story. Made by Maddy Makes Games.",
    "hades": "Hades is a fast roguelike action game where you fight out of the Greek underworld, by Supergiant Games.",
    "stardew valley": "Stardew Valley is a farming and life simulation game made almost entirely by one developer, ConcernedApe.",
    "among us": "Among Us is a social deduction game: crewmates fix the ship while impostors sabotage and hide.",
    "portal": "Portal is a puzzle game by Valve where you create linked portals to solve test chambers.",
    "half-life": "Half-Life is Valve's landmark first-person shooter series. Many mods, like Cry of Fear, were built on its engine.",
    "half life": "Half-Life is Valve's landmark first-person shooter series. Many mods, like Cry of Fear, were built on its engine.",
    "doom": "Doom is the classic first-person shooter by id Software, the model for the whole genre.",
    "fnaf": "Five Nights at Freddy's is a horror series where you survive nights by watching cameras and managing power.",
    "five nights at freddys": "Five Nights at Freddy's is a horror series where you survive nights by watching cameras and managing power.",
    "omori": "OMORI is a psychological RPG made in RPG Maker, with a dreamlike world and darker themes.",
    "pizza tower": "Pizza Tower is a fast, chaotic 2D platformer in the spirit of Wario Land, made in GameMaker.",
    "hotline miami": "Hotline Miami is a top-down, ultra-violent action game with a neon soundtrack, made in GameMaker.",
    "hyper light drifter": "Hyper Light Drifter is a 2D action RPG with pixel-art visuals, made in GameMaker.",
    "gta": "Grand Theft Auto is Rockstar's open-world crime series.",
    "fortnite": "Fortnite is Epic Games' battle royale and building game. It needs the Epic launcher.",
    "roblox": "Roblox is a platform of user-made games, played through its own launcher.",
})


