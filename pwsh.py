#!/usr/bin/env python3
# Copyright (C) 2026 DreeMux
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""pwsh.py - Jarvis PowerShell: a Windows-PowerShell-style shell with a read-only file assistant.

Author: DreeMux

Run:  python pwsh.py      (Windows: double-click START.bat)
Type  help  or just talk to it:  "find my games", "scan this PC for corrupt files".

Everything here is READ-ONLY: nothing of yours is ever written, moved or deleted. Only four things you
ask for explicitly go further: "implement jarvis" (updates this very file, after 9 safety checks and
with a backup), "jarvis open <game>" (starts the game's own program), "launch <file>" (starts a local
script or program) and "extract.key" (saves a NEW report file in Downloads). I also keep a list of sentences I did not understand (jarvis_update/).
Online only: 'jarvis open chrome' starts Chrome mode ('open email', 'open canva', 'open chrome account <name>'): it only opens https pages.
While online (jarvis be online): 'jarvis search <topic>' also asks Wikipedia (https, only the search words are sent), and
'jarvis news' reads the RSS feeds of Italian and international desks (https, read-only; photos need Pillow).
Optional: pip install psutil  (live memory/CPU of a running game in pluton.key).
Optional voice: pip install pyttsx3, then 'voice on' / 'voice off' (local, offline, free; silent until you ask).
Launch a local script or program: 'launch <file> [arguments]' (no shell, never asks for administrator rights).
Screen watch: 'watch' (on by default, Windows) notices who is watching the shared / remote screen, pauses Jarvis and opens a WARNING window.
Optional extensions: put .py files in a folder named ext/ next to this file.
"""

import codecs
import difflib
import errno
import gzip
import hashlib
import json
import math
import mimetypes
import os
import pathlib
import queue
import random
import re
import runpy
import shutil
import sqlite3
import stat
import struct
import subprocess
import sys
import threading
import time
import zipfile
import zlib
from datetime import datetime

# ---------------- JARVIS DATA (only rewritten by 'implement jarvis' maintenance updates) ----------------
# JV_DATA_BEGIN
JV_DATA = {'version': 2, 'game_dirs': ['c:\\program files (x86)\\steam\\steamapps\\common\\DELTARUNEdemo'], 'updated': '2026-10-17 20:52'}
# JV_DATA_END

# ---------------- COLORI ORIGINALI (console Windows PowerShell) ----------------
def fg(r, g, b): return f"\x1b[38;2;{r};{g};{b}m"
def bg(r, g, b): return f"\x1b[48;2;{r};{g};{b}m"

# palette of the Windows 11 terminal (Campbell scheme), as PowerShell 7 shows it there
BG      = bg(12, 12, 12)         # #0C0C0C sfondo
TEXT    = fg(204, 204, 204)      # #CCCCCC testo normale
YELLOW  = fg(249, 241, 165)      # #F9F1A5 comando digitato (PSReadLine)
BLUE    = fg(59, 120, 255)       # #3B78FF testo tra virgolette
RED     = fg(231, 72, 86)        # #E74856 errori
GREEN   = fg(22, 198, 12)        # #16C60C
CYAN    = fg(97, 214, 214)       # #61D6D6
GRAY    = fg(118, 118, 118)      # #767676
JV_SEC_G = fg(22, 198, 12)      # security panels: green
JV_SEC_D = fg(19, 161, 14)      # dim green
JV_SEC_A = fg(193, 156, 0)      # amber warnings
HEADER_COLOR = TEXT              # intestazioni tabelle: classico = testo normale

try:
    import readline  # noqa: F401  (cronologia con le frecce)
    HAS_READLINE = True
except ImportError:
    HAS_READLINE = False

# ---------------- REGISTRO CMDLET ----------------
CMDLETS = {}      # nome minuscolo -> funzione
NOMI = {}         # nome canonico -> funzione (per Get-Command)
CONTESTO = {"riga": ""}
JV_RUN = threading.Event()   # set = Jarvis runs; cleared by the screen watch: the main thread stops at its next output
JV_RUN.set()
JV_HOLD_MAX = 900            # seconds: the longest the screen watch can ever hold Jarvis (failsafe)


ALIASES, GROUPS, USAGE = {}, {}, {}


def cmdlet(nome, *alias, group=None, usage=None):
    """Decoratore: registra un cmdlet con i suoi alias (case-insensitive)."""
    def reg(fn):
        fn.nome = nome
        NOMI[nome] = fn
        ALIASES[nome] = list(alias)
        GROUPS[nome] = group or ("Extensions" if CONTESTO.get("ext") else "Standard")
        if usage:
            USAGE[nome] = usage
        for n in (nome, *alias):
            CMDLETS[n.lower()] = fn
        return fn
    return reg


def out(testo="", colore=None, fine="\n"):
    if not JV_RUN.is_set() and not CONTESTO.get("watchcmd") and threading.current_thread() is threading.main_thread():
        t0 = time.time()                 # "someone is watching": every action stops here until the warning is closed
        while not JV_RUN.wait(0.2):
            if time.time() - t0 > JV_HOLD_MAX + 30:
                JV_RUN.set()             # failsafe: never hold forever, whatever went wrong with the watcher
                break
    sys.stdout.write((colore or TEXT) + str(testo) + TEXT + fine)
    sys.stdout.flush()


def parse(args):
    """Separa i parametri (-Force) dagli argomenti posizionali."""
    flags, pos = set(), []
    for a in args:
        if a.startswith("-") and len(a) > 1 and not a[1].isdigit():
            flags.add(a.lower())
        else:
            pos.append(a)
    return flags, pos


def error(cmd, messaggio, categoria="NotSpecified", oggetto="", exc="Exception",
          fqid=None):
    """Stampa un errore nel formato originale PowerShell, in rosso."""
    riga = CONTESTO["riga"].strip()
    lunghezza = max(len(riga), 1)
    righe = [
        f"{cmd} : {messaggio}",
        "At line:1 char:1",
        f"+ {riga}",
        f"+ {'~' * lunghezza}",
        f"    + CategoryInfo          : {categoria}: ({oggetto}:String) [{cmd if fqid else ''}], {exc}",
        f"    + FullyQualifiedErrorId : {fqid or exc}",
    ]
    out("\n".join(righe), RED)
    out()


# ---------------- UTILITA' ----------------
def nascosto(path, nome):
    try:
        attr = getattr(os.stat(path), "st_file_attributes", None)
        if attr is not None:
            return bool(attr & stat.FILE_ATTRIBUTE_HIDDEN)
    except OSError:
        pass
    return nome.startswith(".")


def mode_string(path, nome, e_dir):
    m = ["d" if e_dir else "-", "-" if e_dir else "a", "-", "-", "-", "-"]
    if not os.access(path, os.W_OK):
        m[2] = "r"
    if nascosto(path, nome):
        m[3] = "h"
    if os.path.islink(path):
        m[5] = "l"
    return "".join(m)


# >>>>> JARVIS-PART 02_basic_cmdlets_helpers.py >>>>>
# ---------------- CMDLET ----------------
@cmdlet("Get-ChildItem", "dir", "ls", "gci")
def get_childitem(args):
    flags, pos = parse(args)
    force = "-force" in flags
    percorso = pos[0] if pos else "."
    if not os.path.exists(percorso):
        a = os.path.abspath(percorso)
        error("Get-ChildItem", f"Cannot find path '{a}' because it does not exist.",
              "ObjectNotFound", a, "ItemNotFoundException",
              "PathNotFound,Microsoft.PowerShell.Commands.GetChildItemCommand")
        return
    if os.path.isdir(percorso):
        cartella = os.path.abspath(percorso)
        nomi = os.listdir(percorso)
        voci = [(n, os.path.join(percorso, n)) for n in nomi]
    else:
        cartella = os.path.dirname(os.path.abspath(percorso))
        voci = [(os.path.basename(percorso), percorso)]

    if not force:
        voci = [(n, p) for n, p in voci if not nascosto(p, n)]
    dirs = sorted([v for v in voci if os.path.isdir(v[1])], key=lambda v: v[0].lower())
    files = sorted([v for v in voci if not os.path.isdir(v[1])], key=lambda v: v[0].lower())
    if not dirs and not files:
        return

    out()
    out(f"    Directory: {cartella}")
    out()
    out("Mode".ljust(21) + "LastWriteTime" + " " * 9 + "Length" + " Name", HEADER_COLOR)
    out("----".ljust(21) + "-------------" + " " * 9 + "------" + " ----", HEADER_COLOR)
    for nome, p in dirs + files:
        e_dir = os.path.isdir(p)
        try:
            st = os.stat(p)
            quando = datetime.fromtimestamp(st.st_mtime)
            lung = "" if e_dir else str(st.st_size)
        except OSError:
            quando, lung = datetime.fromtimestamp(0), ""
        data = quando.strftime("%d/%m/%Y") + "     " + quando.strftime("%H:%M")
        out(mode_string(p, nome, e_dir).ljust(14) + data + lung.rjust(15) + " " + nome)
    out()


@cmdlet("Set-Location", "cd", "sl", "chdir")
def set_location(args):
    _, pos = parse(args)
    if not pos:
        dest = os.path.expanduser("~")
    else:
        dest = os.path.expanduser(pos[0])
        joined = os.path.expanduser(" ".join(pos))
        if not os.path.exists(dest) and os.path.exists(joined):
            dest = joined
    if os.path.isfile(dest):
        # Extra feature: cd on a FILE selects it for extract.port / interact.port / denux.hunter
        full = os.path.abspath(dest)
        try:
            os.chdir(os.path.dirname(full))
        except OSError:
            pass
        CONTESTO["file"] = full
        out(f"Selected file: {safe(os.path.basename(full))}", YELLOW)
        out("Now run extract.port, interact.port or denux.hunter on it.", GRAY)
        return
    try:
        os.chdir(dest)
        CONTESTO["file"] = None
    except (OSError, ValueError):
        a = os.path.abspath(dest)
        error("Set-Location", f"Cannot find path '{a}' because it does not exist.",
              "ObjectNotFound", a, "ItemNotFoundException",
              "PathNotFound,Microsoft.PowerShell.Commands.SetLocationCommand")


@cmdlet("Get-Location", "pwd", "gl")
def get_location(args):
    out()
    out("Path")
    out("----")
    out(os.getcwd())
    out()


@cmdlet("Write-Output", "echo", "write")
def write_output(args):
    out(" ".join(args))


@cmdlet("Write-Host")
def write_host(args):
    out(" ".join(args))


@cmdlet("Get-Content", "cat", "type", "gc")
def get_content(args):
    _, pos = parse(args)
    if not pos and CONTESTO.get("file"):
        pos = [CONTESTO["file"]]
    for p in pos:
        if os.path.isdir(p):
            a = os.path.abspath(p)
            error("Get-Content", f"Access to the path '{a}' is denied.", "PermissionDenied",
                  a, "UnauthorizedAccessException",
                  "GetContentReaderUnauthorizedAccessError,Microsoft.PowerShell.Commands.GetContentCommand")
            continue
        try:
            if device_path(p):
                raise FileNotFoundError(p)          # CON/NUL/COM1... would wait for input forever
            with open(p, encoding="utf-8", errors="replace") as f:
                for riga in f:
                    out(safe(riga.rstrip("\r\n")))
        except (OSError, ValueError):
            a = os.path.abspath(p)
            error("Get-Content", f"Cannot find path '{a}' because it does not exist.",
                  "ObjectNotFound", a, "ItemNotFoundException",
                  "PathNotFound,Microsoft.PowerShell.Commands.GetContentCommand")


@cmdlet("Clear-Host", "cls", "clear")
def clear_host(args):
    sys.stdout.write(BG + TEXT + "\x1b[2J\x1b[H")


@cmdlet("Get-Command", "gcm")
def get_command(args):
    out()
    out("CommandType     Name")
    out("-----------     ----")
    for nome in sorted(NOMI, key=str.lower):
        out(f"Cmdlet          {nome}")
    out()


@cmdlet("Exit", "quit")
def esci(args):
    raise SystemExit(0)


# ======================= PORT TOOLS (built in) =======================
# extract.port, interact.port, denux.hunter - all READ-ONLY.

MAX_HASH = 256 * 1024 * 1024    # checksums skipped above this size
MAX_DEEP = 100 * 1024 * 1024    # denux.hunter does not deep-check above this
MAX_TEXT = 5 * 1024 * 1024      # text read limit for previews/statistics
MAX_FILES = 5000                # denux.hunter stops after this many files

BOMS16 = (codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)
OFFICE = {
    ".docx": "Word document", ".xlsx": "Excel workbook",
    ".pptx": "PowerPoint presentation", ".odt": "OpenDocument text",
    ".ods": "OpenDocument spreadsheet", ".odp": "OpenDocument presentation",
    ".epub": "EPUB book", ".jar": "Java archive", ".apk": "Android package",
}
ZIP_EXT = set(OFFICE) | {".zip"}
TEXT_EXT = {".txt", ".md", ".csv", ".tsv", ".log", ".py", ".ini", ".cfg", ".xml",
            ".html", ".htm", ".yml", ".yaml", ".js", ".css"}
MAGIC = [
    (b"\x89PNG\r\n\x1a\n", "PNG image"), (b"\xff\xd8\xff", "JPEG image"),
    (b"GIF87a", "GIF image"), (b"GIF89a", "GIF image"),
    (b"%PDF-", "PDF document"), (b"PK\x03\x04", "ZIP archive"),
    (b"\x1f\x8b", "GZIP archive"), (b"7z\xbc\xaf\x27\x1c", "7-Zip archive"),
    (b"Rar!", "RAR archive"), (b"SQLite format 3\x00", "SQLite database"),
    (b"\x7fELF", "ELF executable"),
]


# ----------------------------- helpers -----------------------------
def safe(s):
    """Strip control characters so a hostile file name/content cannot mess up the terminal."""
    return "".join(c if c.isprintable() else "." for c in str(s).replace("\t", "    "))


def human(n):
    if n < 1024:
        return f"{n:,} bytes"
    for unit in ("KB", "MB", "GB", "TB"):
        n /= 1024
        if n < 1024 or unit == "TB":
            return f"{n:,.1f} {unit}"


def is_zip(kind):
    return kind == "ZIP archive" or kind.endswith("(ZIP container)")


def detect_kind(path):
    ext = os.path.splitext(path)[1].lower()
    try:
        with open(guard_path(path), "rb") as f:
            head = f.read(4096)
    except OSError:
        return "Unreadable"
    if not head:
        return "Empty file"
    if head[:2] in BOMS16:
        return "Text file (UTF-16)"
    for sig, name in MAGIC:
        if head.startswith(sig):
            if name == "ZIP archive" and ext in OFFICE:
                return OFFICE[ext] + " (ZIP container)"
            return name
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "WebP image"
    if ext == ".win" and head[:4] == b"FORM" and head[8:12] == b"GEN8":
        return "GameMaker data file"
    if head[:2] == b"MZ" and ext in (".exe", ".dll", ".sys"):
        return "Windows executable"
    if b"\x00" in head:
        return "Binary data"
    try:
        head.decode("utf-8")
        return "Text file"
    except UnicodeDecodeError as e:
        return "Text file" if e.start >= len(head) - 3 else "Text file (legacy encoding)"


def read_text(path, limit=MAX_TEXT):
    with open(guard_path(path), "rb") as f:
        raw = f.read(limit)
    if raw[:2] in BOMS16:
        return raw.decode("utf-16", errors="replace"), "UTF-16"
    if raw.startswith(codecs.BOM_UTF8):
        return raw[3:].decode("utf-8", errors="replace"), "UTF-8 with BOM"
    try:
        return raw.decode("utf-8"), "UTF-8"
    except UnicodeDecodeError as e:
        if e.start >= len(raw) - 3 and len(raw) == limit:
            return raw[:e.start].decode("utf-8"), "UTF-8"
        return raw.decode("latin-1"), "Legacy 8-bit (shown as Latin-1)"


def digests(path):
    sha = hashlib.sha256()
    try:
        md = hashlib.md5(usedforsecurity=False)
    except TypeError:
        md = hashlib.md5()
    with open(guard_path(path), "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            sha.update(chunk)
            md.update(chunk)
    return sha.hexdigest().upper(), md.hexdigest().upper()


def image_size(path, kind):
    try:
        with open(guard_path(path), "rb") as f:
            head = f.read(32)
            if kind == "PNG image" and len(head) >= 24:
                return struct.unpack(">II", head[16:24])
            if kind == "GIF image" and len(head) >= 10:
                return struct.unpack("<HH", head[6:10])
            if kind == "JPEG image":
                f.seek(2)
                while True:
                    b = f.read(1)
                    if not b:
                        return None
                    if b != b"\xff":
                        continue
                    m = f.read(1)
                    while m == b"\xff":
                        m = f.read(1)
                    if not m:
                        return None
                    c = m[0]
                    if c in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                        f.read(3)
                        h, w = struct.unpack(">HH", f.read(4))
                        return (w, h)
                    if c in (0xD8, 0x01) or 0xD0 <= c <= 0xD7:
                        continue
                    ln = struct.unpack(">H", f.read(2))[0]
                    f.seek(ln - 2, 1)
    except (OSError, struct.error):
        return None
    return None


def sqlite_open_ro(path):
    return sqlite3.connect(pathlib.Path(path).resolve().as_uri() + "?mode=ro", uri=True)


def sqlite_tables(path, limit=30):
    con = sqlite_open_ro(path)
    try:
        names = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        res = []
        for n in names[:limit]:
            cnt = con.execute('SELECT COUNT(*) FROM "%s"' % n.replace('"', '""')).fetchone()[0]
            res.append((n, cnt))
        return res, len(names)
    finally:
        con.close()


def hexdump(data):
    rows = []
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        hx = " ".join(f"{b:02X}" for b in chunk).ljust(47)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        rows.append(f"  {i:08X}  {hx}  {asc}")
    return rows


def target_args(args):
    """Split flags/targets. Also accepts the word 'cd':  denux.hunter cd "file"."""
    flags, pos = parse(args)
    if pos and pos[0].lower() in ("cd", "sl", "set-location"):
        pos = pos[1:]
    return flags, pos


DEVICE_NAMES = frozenset({"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
                         | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)})


def device_path(p, win=None):
    """True for Windows device names (CON, NUL, COM1, \\\\.\\...). They 'exist' but opening them waits for
    input forever, so no command may ever open them as files."""
    if win is None:
        win = os.name == "nt"
    if not win:
        return False
    t = str(p).replace("/", "\\")
    if t.startswith("\\\\.\\"):
        return True
    for part in t.split("\\"):
        stem = part.split(":")[-1].rstrip(" .").split(".")[0].rstrip(" ").upper()
        if stem in DEVICE_NAMES:
            return True
    return False


def guard_path(p):
    """The path itself, or FileNotFoundError for a Windows device name (CON, NUL...): it then follows the same
    road as a missing file, because opening a device would wait for input forever."""
    if device_path(p):
        raise FileNotFoundError(p)
    return p


def resolve_existing(pos, cmd):
    p = pos[0]
    joined = " ".join(pos)
    if not os.path.exists(p) and os.path.exists(joined):
        p = joined
    if device_path(p) or not os.path.exists(p):
        a = os.path.abspath(p)
        error(cmd, f"Cannot find path '{a}' because it does not exist.",
              "ObjectNotFound", a, "ItemNotFoundException", f"PathNotFound,{cmd}")
        return None
    return p


def show_file_choices():
    out("Files in the current folder:")
    try:
        files = sorted(n for n in os.listdir(".") if os.path.isfile(n))
    except OSError:
        files = []
    if not files:
        out("  (no files in this folder)", GRAY)
    for n in files[:25]:
        out(f"  {safe(n).ljust(40)} {detect_kind(n)}")
    if len(files) > 25:
        out(f"  ... and {len(files) - 25} more", GRAY)
    out()


def pick(args, cmd):
    """The file to work on: the one given, or the one selected earlier with cd."""
    flags, pos = target_args(args)
    if pos:
        p = resolve_existing(pos, cmd)
        if p is None:
            return None
        if os.path.isdir(p):
            out(f"'{safe(p)}' is a folder. Use cd to enter it, then pick a file inside.", YELLOW)
            out()
            return None
        return p
    sel = CONTESTO.get("file")
    if sel and os.path.isfile(sel):
        out(f"Using selected file: {safe(sel)}", GRAY)
        return sel
    out(f"Usage: {cmd} <file>", YELLOW)
    out(f'Or select a file first with:  cd "<file>"   and then run  {cmd}', YELLOW)
    show_file_choices()
    return None


# >>>>> JARVIS-PART 03_extract_interact.py >>>>>
# ----------------------------- extract.port -----------------------------
@cmdlet("extract.port", group="Port tools", usage="""extract.port <file>
extract.port                 uses the file selected earlier with:  cd "<file>"
(one file only: there is no whole-PC mode for this command)""")
def extract_port(args):
    """Show all the information about one file (metadata, type, checksums)."""
    path = pick(args, "extract.port")
    if not path:
        return
    try:
        st = os.stat(path)
    except OSError as e:
        out(f"extract.port : Cannot read file ({e.strerror})", RED)
        out()
        return
    kind = detect_kind(path)
    ext = os.path.splitext(path)[1]
    fmt = lambda t: datetime.fromtimestamp(t).strftime("%d/%m/%Y %H:%M:%S")
    attrs = []
    if not os.access(path, os.W_OK):
        attrs.append("ReadOnly")
    winattr = getattr(st, "st_file_attributes", None)
    if (winattr is not None and winattr & 2) or (winattr is None and os.path.basename(path).startswith(".")):
        attrs.append("Hidden")
    if os.path.islink(path):
        attrs.append("Link")
    rows = [
        ("Name", safe(os.path.basename(path))),
        ("FullName", safe(os.path.abspath(path))),
        ("Type", kind),
        ("MimeType", "application/octet-stream" if kind == "GameMaker data file"
         else mimetypes.guess_type(path)[0] or "unknown"),
        ("Extension", ext or "(none)"),
        ("Size", human(st.st_size)),
        ("CreationTime" if os.name == "nt" else "ChangeTime",
         fmt(getattr(st, "st_birthtime", st.st_ctime))),
        ("LastWriteTime", fmt(st.st_mtime)),
        ("LastAccessTime", fmt(st.st_atime)),
        ("Attributes", ", ".join(attrs) or "Normal"),
    ]
    try:
        if st.st_size <= MAX_HASH:
            sha, md = digests(path)
            rows += [("SHA256", sha), ("MD5", md)]
        else:
            rows.append(("SHA256", "skipped (file larger than 256 MB)"))

        if kind.startswith("Text file"):
            text, enc = read_text(path)
            part = " (first 5 MB only)" if st.st_size > MAX_TEXT else ""
            rows += [("Encoding", enc), ("Lines", f"{len(text.splitlines()):,}{part}"),
                     ("Words", f"{len(text.split()):,}{part}"),
                     ("Characters", f"{len(text):,}{part}")]
        elif kind.endswith("image"):
            dim = image_size(path, kind)
            if dim:
                rows.append(("Dimensions", f"{dim[0]} x {dim[1]} pixels"))
        elif is_zip(kind):
            try:
                with zipfile.ZipFile(path) as z:
                    infos = z.infolist()
                    rows += [("Entries", f"{len(infos):,}"),
                             ("UncompressedSize", human(sum(i.file_size for i in infos)))]
            except zipfile.BadZipFile:
                rows.append(("Entries", "unreadable (archive may be corrupted)"))
        elif kind == "SQLite database":
            try:
                _, total = sqlite_tables(path)
                rows.append(("Tables", str(total)))
            except sqlite3.Error as e:
                rows.append(("Tables", f"unreadable ({safe(e)})"))
        elif kind == "GameMaker data file":
            gm = gm_read_info(path)
            rows += [("Game", gm["name"] or "unknown"), ("GameMaker", gm["gm"] or "unknown"),
                     ("Bytecode", str(gm["bytecode"])), ("Chunks", f"{len(gm['chunks'])}: " + ", ".join(gm["chunks"][:12]))]
            rows += [("Warning", n) for n in gm["notes"]]
        elif kind == "PDF document":
            with open(guard_path(path), "rb") as f:
                rows.append(("PdfVersion", safe(f.read(8).decode("latin-1").strip())))
    except OSError as e:
        rows.append(("Warning", f"Read error while analysing ({e.strerror})"))

    w = max(len(k) for k, _ in rows)
    out()
    for k, v in rows:
        out(f"{k.ljust(w)} : {v}")
    out()


# ----------------------------- interact.port -----------------------------
def preview(path, kind, size):
    if size == 0:
        out("  The file is empty.")
        return
    if kind.startswith("Text file"):
        text, enc = read_text(path)
        lines = text.splitlines()
        part = " (first 5 MB only)" if size > MAX_TEXT else ""
        out(f"  Encoding: {enc}  |  Lines: {len(lines):,}{part}")
        ext = os.path.splitext(path)[1].lower()
        if ext in (".csv", ".tsv") and lines:
            delim = max(",;\t|", key=lines[0].count)
            cols = [safe(c.strip()) for c in lines[0].split(delim)]
            out(f"  Table-like data: {len(cols)} column(s): {', '.join(cols[:12])}"
                f"{' ...' if len(cols) > 12 else ''}  |  {max(len(lines) - 1, 0):,} data row(s)")
        if ext == ".json" and size <= 20 * 1024 * 1024:
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    keys = list(data)
                    out(f"  JSON object with {len(keys)} key(s): "
                        f"{', '.join(safe(k) for k in keys[:15])}{' ...' if len(keys) > 15 else ''}")
                elif isinstance(data, list):
                    out(f"  JSON array with {len(data):,} item(s)")
                else:
                    out(f"  JSON value of type {type(data).__name__}")
            except ValueError as e:
                out(f"  Invalid JSON: {safe(e)}", RED)
        out("  First 15 lines:", GRAY)
        for i, line in enumerate(lines[:15], 1):
            out(f"  {i:>3} | {safe(line)[:110]}")
    elif is_zip(kind):
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
            out(f"  {len(infos):,} entr{'y' if len(infos) == 1 else 'ies'} inside (listed only, nothing is extracted):")
            for i in infos[:30]:
                out(f"  {human(i.file_size).rjust(12)}  {safe(i.filename)}")
            if len(infos) > 30:
                out(f"  ... and {len(infos) - 30:,} more", GRAY)
    elif kind == "GameMaker data file":
        gm = gm_read_info(path)
        out(f"  GameMaker game data: {gm['name'] or 'unknown name'}, GameMaker {gm['gm'] or '?'}, bytecode {gm['bytecode']}")
        out(f"  {len(gm['chunks'])} chunks: {', '.join(gm['chunks'][:20])}")
        for n in gm["notes"]:
            out(f"  Warning: {n}", YELLOW)
        out("  Viewing only: the game data is never opened for writing.", GRAY)
    elif kind == "GZIP archive":
        out("  Compressed stream. Contents are not unpacked here; use denux.hunter to verify integrity.")
    elif kind.endswith("image"):
        dim = image_size(path, kind)
        out(f"  Image, {dim[0]} x {dim[1]} pixels." if dim else "  Image (dimensions could not be read).")
    elif kind == "PDF document":
        with open(guard_path(path), "rb") as f:
            raw = f.read(20 * 1024 * 1024)
        pages = len(re.findall(rb"/Type\s*/Page[^s]", raw))
        out(f"  PDF version: {safe(raw[:8].decode('latin-1').strip())}  |  approx. pages: {pages or 'unknown'}")
        out(f"  End-of-file marker present: {'yes' if b'%%EOF' in raw[-2048:] else 'NO (file may be truncated)'}")
    elif kind == "SQLite database":
        tables, total = sqlite_tables(path)
        out(f"  {total} table(s) (opened read-only):")
        for n, c in tables:
            out(f"  {safe(n).ljust(30)} {c:,} row(s)")
        if total > len(tables):
            out(f"  ... and {total - len(tables)} more", GRAY)
    else:
        with open(guard_path(path), "rb") as f:
            data = f.read(128)
        out("  Binary content, hex preview of the first 128 bytes (never executed):")
        for row in hexdump(data):
            out(row)


@cmdlet("interact.port", group="Port tools", usage="""interact.port <file>
interact.port                uses the file selected earlier with:  cd "<file>"
(one file only: there is no whole-PC mode for this command)""")
def interact_port(args):
    """Show what you can see inside a file and what you can do with it."""
    path = pick(args, "interact.port")
    if not path:
        return
    try:
        size = os.path.getsize(path)
    except OSError as e:
        out(f"interact.port : Cannot read file ({e.strerror})", RED)
        out()
        return
    kind = detect_kind(path)
    name = safe(os.path.basename(path))
    q = f'"{name}"' if " " in name else name
    out()
    out(f"Interactive view: {name}  [{kind}, {human(size)}]", CYAN)
    out()
    out("What you can SEE inside this file:", YELLOW)
    try:
        preview(path, kind, size)
    except Exception as e:
        out(f"  Could not read the contents ({safe(e)}).", RED)
        out(f"  The file may be damaged: try  denux.hunter {q}", RED)
    out()
    out("What you can DO with it (all read-only):", YELLOW)
    if kind.startswith("Text file"):
        out(f"  Get-Content {q}   - print the whole text")
    out(f"  extract.port {q}   - full metadata, dates and checksums")
    out(f"  denux.hunter {q}   - check whether this file is corrupted")
    out("interact.port never runs, edits, moves or deletes files.", GRAY)
    out()


# >>>>> JARVIS-PART 04_denux_hunter.py >>>>>
# ----------------------------- denux.hunter -----------------------------
def check_zip(path):
    if not zipfile.is_zipfile(path):
        return "Not a valid ZIP container (bad or missing central directory)"
    with zipfile.ZipFile(path) as z:
        bad = z.testzip()
        if bad:
            return f"CRC/data error in entry '{safe(bad)}'"


def check_png(path):
    with open(guard_path(path), "rb") as f:
        if f.read(8) != b"\x89PNG\r\n\x1a\n":
            return "Invalid PNG signature"
        while True:
            hdr = f.read(8)
            if not hdr:
                return "Missing IEND chunk (file truncated)"
            if len(hdr) < 8:
                return "Truncated chunk header"
            ln, typ = struct.unpack(">I4s", hdr)
            data, crc = f.read(ln), f.read(4)
            name = safe(typ.decode("latin-1"))
            if len(data) < ln or len(crc) < 4:
                return f"Truncated chunk '{name}'"
            if zlib.crc32(typ + data) & 0xFFFFFFFF != struct.unpack(">I", crc)[0]:
                return f"Bad CRC in chunk '{name}'"
            if typ == b"IEND":
                return None


def tail_of(path, n=2048):
    size = os.path.getsize(path)
    with open(guard_path(path), "rb") as f:
        f.seek(max(0, size - n))
        return f.read()


def check_jpeg(path):
    with open(guard_path(path), "rb") as f:
        if f.read(3) != b"\xff\xd8\xff":
            return "Invalid JPEG signature"
    if not tail_of(path, 64).rstrip(b"\x00").endswith(b"\xff\xd9"):
        return "Missing end-of-image marker (file likely truncated)"


def check_gif(path):
    with open(guard_path(path), "rb") as f:
        if f.read(6) not in (b"GIF87a", b"GIF89a"):
            return "Invalid GIF signature"
    if not tail_of(path, 64).rstrip(b"\x00").endswith(b"\x3b"):
        return "Missing GIF trailer (file likely truncated)"


def check_pdf(path):
    with open(guard_path(path), "rb") as f:
        if f.read(5) != b"%PDF-":
            return "Missing %PDF- header"
    if b"%%EOF" not in tail_of(path):
        return "Missing %%EOF marker (file likely truncated)"


def check_json(path):
    with open(guard_path(path), "rb") as f:
        raw = f.read()
    try:
        json.loads(raw.decode("utf-8-sig"))
    except UnicodeDecodeError:
        return "Not valid UTF-8 text"
    except ValueError as e:
        return f"Invalid JSON: {safe(e)}"


def check_gzip(path):
    total = 0
    try:
        with gzip.open(path, "rb") as g:
            while True:
                chunk = g.read(1 << 20)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_DEEP * 2:   # decompression-bomb guard
                    break
    except (gzip.BadGzipFile, EOFError, zlib.error) as e:
        return f"Damaged GZIP stream ({safe(e)})"


def check_sqlite(path):
    with open(guard_path(path), "rb") as f:
        if f.read(16) != b"SQLite format 3\x00":
            return "Missing SQLite header"
    con = None
    try:
        con = sqlite_open_ro(path)
        res = con.execute("PRAGMA integrity_check").fetchall()
    except sqlite3.Error as e:
        return f"Database error: {safe(e)}"
    finally:
        if con:
            con.close()
    if res != [("ok",)]:
        return "Integrity check failed: " + safe(res[0][0])


CHECKS = {".png": check_png, ".jpg": check_jpeg, ".jpeg": check_jpeg,
          ".gif": check_gif, ".pdf": check_pdf, ".json": check_json,
          ".gz": check_gzip, ".db": check_sqlite, ".sqlite": check_sqlite,
          ".sqlite3": check_sqlite}
CLOUD_ATTRS = 0x1000 | 0x40000 | 0x400000   # Windows: offline / cloud-only placeholders
PSEUDO_DIRS = {"/proc", "/sys", "/dev", "/run"}
SEVERITY = {"CORRUPT": 0, "WARNING": 1, "SKIPPED": 2, "EMPTY": 3, "OK": 4}
MAX_ROWS = 300


def check_file(path):
    """Return (status, reason). status: OK, WARNING, CORRUPT, SKIPPED or EMPTY."""
    ext = os.path.splitext(path)[1].lower()
    try:
        st = os.stat(path)
        if st.st_size == 0:
            return "EMPTY", "Empty file (0 bytes)"
        if getattr(st, "st_file_attributes", 0) & CLOUD_ATTRS:
            return "SKIPPED", "Cloud-only file (not downloaded), not read"
        fn = check_zip if ext in ZIP_EXT else CHECKS.get(ext)
        if fn is None and ext not in TEXT_EXT:
            return "OK", ""          # unknown type: nothing to verify, file is not even opened
        if st.st_size > MAX_DEEP:
            return "SKIPPED", "Larger than 100 MB, not deep-checked"
        if fn:
            reason = fn(path)
            if reason:
                return "CORRUPT", reason
        else:
            with open(guard_path(path), "rb") as f:
                head = f.read(65536)
            if head[:2] not in BOMS16 and b"\x00" in head:
                return "WARNING", "Contains NUL bytes (damaged, or not really a text file)"
    except (zipfile.BadZipFile, zlib.error, EOFError) as e:
        return "CORRUPT", f"Damaged data ({safe(e)})"
    except OSError as e:
        if e.errno in (errno.EACCES, errno.EPERM):
            return "WARNING", "Access denied (could not check)"
        if e.errno == errno.ENOENT:
            return "WARNING", "File disappeared during the scan"
        return "CORRUPT", f"Read error ({e.strerror or e})"
    except Exception as e:
        return "WARNING", f"Check failed unexpectedly: {safe(e)}"
    return "OK", ""


def pc_roots():
    """Every fixed drive on Windows, or / on Linux/macOS."""
    if os.name == "nt":
        try:
            import ctypes
            k = ctypes.windll.kernel32
            mask, roots = k.GetLogicalDrives(), []
            for i in range(26):
                root = f"{chr(65 + i)}:\\"
                if mask & (1 << i) and k.GetDriveTypeW(root) == 3:   # 3 = fixed disk
                    roots.append(root)
            if roots:
                return roots
        except Exception:
            pass
        return [os.environ.get("SystemDrive", "C:") + "\\"]
    return ["/"]


def skip_dir(p):
    if os.name == "nt":
        try:
            return bool(os.lstat(p).st_file_attributes & 0x400)   # junctions / cloud folders
        except OSError:
            return True
    return p in PSEUDO_DIRS or os.path.islink(p)


def walk_files(roots, recurse=True):
    for root in roots:
        for cur, dirs, names in os.walk(root, onerror=lambda e: None):
            dirs[:] = sorted(d for d in dirs if not skip_dir(os.path.join(cur, d)))
            for n in sorted(names):
                p = os.path.join(cur, n)
                if not os.path.islink(p):
                    yield p
            if not recurse:
                break


@cmdlet("denux.hunter", group="Port tools", usage="""denux.hunter                scan EVERY file on this computer (read-only, Ctrl+C stops it)
denux.hunter <path>         scan one folder (add -Recurse for sub-folders) or one file
denux.hunter . -Recurse     scan the current folder and everything below it
denux.hunter                after  cd "<file>"  it scans only that selected file
-PC                         scan the whole computer even if a file is selected
-All                        also list OK, empty and skipped files""")
def denux_hunter(args):
    """Hunt for corrupted files: whole PC, a folder, or one selected file."""
    flags, pos = target_args(args)
    recurse, show_all = "-recurse" in flags, "-all" in flags
    whole_pc, target = False, None
    if pos:
        target = resolve_existing(pos, "denux.hunter")
        if target is None:
            return
    elif CONTESTO.get("file") and os.path.isfile(CONTESTO["file"]) and "-pc" not in flags:
        target = CONTESTO["file"]
    else:
        whole_pc = True

    single = target is not None and os.path.isfile(target)
    if whole_pc:
        roots = pc_roots()
        files = walk_files(roots, True)
        base = None
    elif single:
        files = iter([target])
        base = os.path.dirname(os.path.abspath(target))
    else:
        files = walk_files([target], recurse)
        base = target

    out()
    if whole_pc:
        out("Hunting on the WHOLE COMPUTER: " + ", ".join(roots), YELLOW)
        out("Read-only scan. Press Ctrl+C to stop at any time.", GRAY)
    elif single:
        out(f"Hunting in the selected file: {safe(os.path.abspath(target))}")
    else:
        out(f"Hunting in: {safe(os.path.abspath(target))}{'  (recursive)' if recurse else ''}")

    counts = {k: 0 for k in SEVERITY}
    rows, n, interrupted = [], 0, False
    tty = sys.stdout.isatty()
    width = shutil.get_terminal_size((100, 20)).columns
    last, t0 = 0.0, time.monotonic()
    try:
        for p in files:
            n += 1
            status, reason = check_file(p)
            counts[status] += 1
            if status != "OK" or (show_all and not whole_pc):
                name = os.path.abspath(p) if whole_pc else os.path.relpath(p, base)
                rows.append((status, safe(name), reason))
            if tty and time.monotonic() - last > 0.15:
                last = time.monotonic()
                line = (f"  Scanned {n:,} | corrupt {counts['CORRUPT']} | "
                        f"warnings {counts['WARNING']} | {safe(p)}")
                sys.stdout.write("\r" + GRAY + line[:width - 1].ljust(width - 1) + TEXT)
                sys.stdout.flush()
    except KeyboardInterrupt:
        interrupted = True
    if tty:
        sys.stdout.write("\r" + " " * (width - 1) + "\r")

    hidden = {"EMPTY", "SKIPPED"} if whole_pc and not show_all else set()
    shown = sorted((r for r in rows if r[0] not in hidden), key=lambda r: SEVERITY[r[0]])
    extra = max(0, len(shown) - MAX_ROWS)
    shown = shown[:MAX_ROWS]
    if shown:
        w = min(max(len(r[1]) for r in shown), 70)
        colors = {"CORRUPT": RED, "WARNING": YELLOW, "SKIPPED": GRAY, "EMPTY": GRAY, "OK": GREEN}
        out()
        out("Status   " + "File".ljust(w) + "  Reason")
        out("------   " + "----".ljust(w) + "  ------")
        for s, name, reason in shown:
            out(f"{s.ljust(8)} {name.ljust(w)}  {reason}", colors[s])
    out()
    secs = int(time.monotonic() - t0)
    summary = (f"Scanned {n:,} file(s) in {secs // 60}:{secs % 60:02d}: {counts['CORRUPT']} corrupt, "
               f"{counts['WARNING']} warning(s), {counts['EMPTY']} empty, "
               f"{counts['SKIPPED']} skipped, {counts['OK']} OK.")
    out(summary, RED if counts["CORRUPT"] else YELLOW if counts["WARNING"] else GREEN)
    if interrupted:
        out("Stopped by user: results are partial.", YELLOW)
    if not counts["CORRUPT"]:
        out("No corrupted files found" + (" so far." if interrupted else "."), GREEN)
    if extra:
        out(f"{extra:,} more row(s) not shown (first {MAX_ROWS} displayed). "
            "Run denux.hunter on a folder to see the rest.", YELLOW)
    if hidden and (counts["EMPTY"] or counts["SKIPPED"]):
        out(f"{counts['EMPTY']:,} empty and {counts['SKIPPED']:,} skipped file(s) not listed; use -All to list them.", GRAY)
    out("denux.hunter is read-only: no file was modified, moved or deleted.", GRAY)
    out()


# >>>>> JARVIS-PART 05_undersopic_key.py >>>>>
# ----------------------------- undersopic.key -----------------------------
GM_FILE = "data.win"


def gm_read_info(path):
    """Read-only peek at a GameMaker data.win (a FORM container). Never modifies it."""
    info = {"ok": False, "notes": [], "chunks": [], "name": None, "gm": None, "bytecode": None}
    size = os.path.getsize(path)
    with open(guard_path(path), "rb") as f:
        head = f.read(8)
        if len(head) < 8 or head[:4] != b"FORM":
            info["notes"].append("Missing FORM header (not a GameMaker data file, or damaged)")
            return info
        end = struct.unpack("<I", head[4:8])[0] + 8
        if end != size:
            info["notes"].append(f"FORM length expects {end:,} bytes but the file has {size:,} "
                                 "(truncated or modified?)")
        pos, gen8, broken = 8, None, False
        while pos + 8 <= min(end, size) and len(info["chunks"]) < 64:
            f.seek(pos)
            hdr = f.read(8)
            cid, clen = hdr[:4], struct.unpack("<I", hdr[4:8])[0]
            if not re.fullmatch(rb"[A-Z0-9]{4}", cid):
                info["notes"].append("Chunk list is damaged")
                broken = True
                break
            info["chunks"].append(cid.decode())
            if cid == b"GEN8":
                gen8 = (pos + 8, clen)
            pos += 8 + clen
        if not broken and pos > size:
            info["notes"].append("The last chunk runs past the end of the file (truncated)")
        info["ok"] = bool(info["chunks"]) and info["chunks"][0] == "GEN8"
        if not info["ok"]:
            info["notes"].append("First chunk is not GEN8 (unusual for a GameMaker game)")
        if gen8 and gen8[1] >= 60:   # best-effort: game name and GameMaker version
            f.seek(gen8[0])
            g = f.read(60)
            info["bytecode"] = g[1]
            ptr = struct.unpack("<I", g[40:44])[0]
            if 4 < ptr < size:
                f.seek(ptr - 4)
                ln = struct.unpack("<I", f.read(4))[0]
                if 0 < ln <= 64:
                    s = f.read(ln)
                    if s.isascii() and s.decode("ascii").isprintable():
                        info["name"] = s.decode("ascii")
            major, minor, rel, build = struct.unpack("<4I", g[44:60])
            if 1 <= major <= 3 and minor < 100 and rel < 100000 and build < 100000:
                info["gm"] = f"{major}.{minor}.{rel}.{build}"
    return info


def store_of(path):
    low = path.lower().replace("\\", "/")
    if "/steamapps/" in low:
        return "Steam"
    if "epic games" in low:
        return "Epic Games"
    if "/gog" in low:
        return "GOG"
    if "/itch" in low:
        return "itch.io"
    if "/downloads/" in low:
        return "Downloads folder"
    return "Other folder"


def steam_libraries():
    home = os.path.expanduser("~")
    cands = []
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
                cands.append(winreg.QueryValueEx(k, "SteamPath")[0])
        except Exception:
            pass
        for pf in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
            if pf:
                cands.append(os.path.join(pf, "Steam"))
    elif sys.platform == "darwin":
        cands.append(home + "/Library/Application Support/Steam")
    else:
        cands += [home + "/.steam/steam", home + "/.local/share/Steam",
                  home + "/.var/app/com.valvesoftware.Steam/.local/share/Steam"]
    libs = []
    for c in cands:
        if os.path.isdir(os.path.join(c, "steamapps")):
            libs.append(c)
        try:
            with open(os.path.join(c, "steamapps", "libraryfolders.vdf"),
                      encoding="utf-8", errors="replace") as f:
                for m in re.findall(r'"path"\s+"([^"]+)"', f.read()):
                    libs.append(m.replace("\\\\", "\\"))
        except OSError:
            pass
    return [os.path.join(lib, "steamapps", "common") for lib in libs]


def game_locations():
    """Folders where downloaded games usually live (only those that exist)."""
    home = os.path.expanduser("~")
    locs = steam_libraries()
    locs += [home + "/Downloads", home + "/Desktop", home + "/Games", home + "/Documents/Games"]
    if os.name == "nt":
        for pf in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
            if pf:
                locs += [os.path.join(pf, "Epic Games"), os.path.join(pf, "GOG Galaxy", "Games")]
        for var in ("APPDATA", "LOCALAPPDATA"):
            if os.environ.get(var):
                locs.append(os.path.join(os.environ[var], "itch", "apps"))
        locs += ["C:\\GOG Games", "C:\\Games"]
    else:
        locs.append(home + "/.config/itch/apps")
    seen, res = set(), []
    for p in locs:
        if os.path.isdir(p):
            key = os.path.normcase(os.path.realpath(p))
            if key not in seen:
                seen.add(key)
                res.append(p)
    return res


def find_named(roots, name=GM_FILE, maxdepth=None):
    for root in roots:
        base = root.rstrip(os.sep).count(os.sep)
        for cur, dirs, files in os.walk(root, onerror=lambda e: None):
            if maxdepth is not None and cur.rstrip(os.sep).count(os.sep) - base >= maxdepth:
                dirs[:] = []
            else:
                dirs[:] = sorted(d for d in dirs if not skip_dir(os.path.join(cur, d)))
            for fn in files:
                if fn.lower() == name:
                    yield os.path.join(cur, fn)


def show_gm(i, path):
    try:
        info = gm_read_info(path)
        size = os.path.getsize(path)
        mtime = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%d/%m/%Y %H:%M")
    except OSError as e:
        out(f"[{i}] {safe(path)}", CYAN)
        out(f"    Cannot read it ({e.strerror})", RED)
        out()
        return
    game = info["name"] or os.path.basename(os.path.dirname(os.path.abspath(path)))
    out(f"[{i}] {safe(game)}", CYAN)
    out(f"    Path    : {safe(os.path.abspath(path))}")
    out(f"    Store   : {store_of(path)}")
    out(f"    Size    : {human(size)}   (modified {mtime})")
    if info["ok"]:
        extra = f", GameMaker {info['gm']}" if info["gm"] else ""
        bc = f"bytecode {info['bytecode']}" if info["bytecode"] is not None else "bytecode ?"
        out(f"    Format  : GameMaker data file, {bc}{extra}, {len(info['chunks'])} chunks")
    for note in info["notes"]:
        out(f"    Warning : {note}", YELLOW)
    out()


@cmdlet("undersopic.key", group="Port tools", usage="""undersopic.key               find the data.win of your downloaded games (Steam, Epic, GOG, itch.io, Downloads...)
undersopic.key <folder>      search that folder and everything below it
undersopic.key -Everywhere   search the whole computer (can take a while, Ctrl+C stops it)
undersopic.key               after  cd "<data.win>"  it shows that file only
(read-only: it only finds and describes the file, it never changes it)""")
def undersopic_key(args):
    """Find the direct data.win file of downloaded games (GameMaker)."""
    flags, pos = target_args(args)
    sel = CONTESTO.get("file")
    paths, interrupted, searched = [], False, []
    if pos:
        target = resolve_existing(pos, "undersopic.key")
        if target is None:
            return
        if os.path.isfile(target):
            if os.path.basename(target).lower() != GM_FILE:
                out(f"'{safe(os.path.basename(target))}' is not a {GM_FILE} file.", YELLOW)
                out()
                return
            paths = [target]
        else:
            searched = [target]
    elif sel and os.path.basename(sel).lower() == GM_FILE and os.path.isfile(sel):
        paths = [sel]
    elif "-everywhere" in flags:
        searched = pc_roots()
        out()
        out("Searching the WHOLE COMPUTER for data.win... Press Ctrl+C to stop.", YELLOW)
    else:
        searched = game_locations()
        if not searched:
            out()
            out("No known game folders were found on this PC.", YELLOW)
            out('Try:  undersopic.key <folder>    or    undersopic.key -Everywhere', YELLOW)
            out()
            return
    if searched:
        if not (pos is None and "-everywhere" in flags):
            out()
            out("Searching in:", GRAY)
            for s in searched:
                out(f"  {safe(s)}", GRAY)
        depth = None if ("-everywhere" in flags or pos) else 6
        seen = set()
        try:
            for p in find_named(searched, GM_FILE, depth):
                key = os.path.normcase(os.path.realpath(p))
                if key not in seen:
                    seen.add(key)
                    paths.append(p)
        except KeyboardInterrupt:
            interrupted = True
    out()
    if not paths:
        out("No data.win found.", YELLOW)
        out("Tip: undersopic.key <folder> searches a specific folder; -Everywhere searches the whole PC.", GRAY)
        out()
        return
    out(f"Found {len(paths)} data.win file(s):", GREEN)
    out()
    for i, p in enumerate(paths, 1):
        show_gm(i, p)
    if interrupted:
        out("Stopped by user: the list may be incomplete.", YELLOW)
    q = safe(os.path.abspath(paths[0]))
    out(f'Tip: select one with  cd "{q}"  then use extract.port, interact.port, denux.hunter or pluton.key.', GRAY)
    out()


# >>>>> JARVIS-PART 06_pluton_key.py >>>>>
# ----------------------------- pluton.key -----------------------------
def count_folder(folder, cap=200000):
    files = dirs = size = 0
    for cur, ds, fs in os.walk(folder, onerror=lambda e: None):
        ds[:] = [d for d in ds if not skip_dir(os.path.join(cur, d))]
        dirs += len(ds)
        for n in fs:
            files += 1
            try:
                size += os.lstat(os.path.join(cur, n)).st_size
            except OSError:
                pass
            if files >= cap:
                return files, dirs, size, True
    return files, dirs, size, False


def system_memory():
    """(used, total) bytes of RAM, or None."""
    try:
        import psutil
        vm = psutil.virtual_memory()
        return vm.total - vm.available, vm.total
    except Exception:
        pass
    try:
        if os.name == "nt":
            import ctypes

            class MEMSTATUS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            s = MEMSTATUS()
            s.dwLength = ctypes.sizeof(MEMSTATUS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s))
            return s.ullTotalPhys - s.ullAvailPhys, s.ullTotalPhys
        if os.path.exists("/proc/meminfo"):
            vals = {}
            with open("/proc/meminfo", encoding="utf-8", errors="replace") as f:
                for line in f:
                    k, _, v = line.partition(":")
                    vals[k] = int(v.split()[0]) * 1024
            return vals["MemTotal"] - vals["MemAvailable"], vals["MemTotal"]
    except Exception:
        pass
    return None


def battery_info():
    """dict(percent, plugged, secs) or None when there is no battery (desktop PC) or it is unreadable."""
    try:
        import psutil
        b = psutil.sensors_battery()
        if b:
            secs = b.secsleft if b.secsleft not in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN) else None
            return {"percent": round(b.percent), "plugged": bool(b.power_plugged), "secs": secs}
    except Exception:
        pass
    try:
        if os.name == "nt":
            import ctypes

            class POWER(ctypes.Structure):
                _fields_ = [("ac", ctypes.c_ubyte), ("flag", ctypes.c_ubyte), ("pct", ctypes.c_ubyte),
                            ("sys", ctypes.c_ubyte), ("life", ctypes.c_ulong), ("full", ctypes.c_ulong)]
            s = POWER()
            if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(s)) and s.flag != 128 and s.pct != 255:
                return {"percent": s.pct, "plugged": s.ac == 1,
                        "secs": None if s.life == 0xFFFFFFFF else s.life}
        elif sys.platform == "darwin":
            txt = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=3).stdout
            m = re.search(r"(\d+)%", txt)
            if m:
                return {"percent": int(m.group(1)), "plugged": "AC Power" in txt.splitlines()[0], "secs": None}
        else:
            base = "/sys/class/power_supply"
            for n in sorted(os.listdir(base)):
                if n.startswith("BAT"):
                    with open(f"{base}/{n}/capacity", encoding="utf-8", errors="replace") as f:
                        pct = int(f.read().strip())
                    with open(f"{base}/{n}/status", encoding="utf-8", errors="replace") as f:
                        st = f.read().strip()
                    return {"percent": pct, "plugged": st != "Discharging", "secs": None}
    except Exception:
        pass
    return None


def battery_text(b):
    if b is None:
        return "No battery detected (desktop PC, or the system does not report it)"
    state = "plugged in / charging" if b["plugged"] else "on battery"
    left = ""
    if b["secs"] and not b["plugged"]:
        left = f", about {b['secs'] // 3600}h {b['secs'] % 3600 // 60:02d}m left"
    return f"{b['percent']}%  ({state}{left})"


def running_from(folder, exe_file):
    """Processes whose executable is this file or lives in its folder. None = psutil missing."""
    try:
        import psutil
    except ImportError:
        return None
    base = os.path.normcase(os.path.abspath(folder))
    target = os.path.normcase(os.path.abspath(exe_file))
    folder_ok = os.path.dirname(base) != base          # never match "everything on the drive"
    res = []
    for p in psutil.process_iter(["exe"]):
        try:
            exe = p.info.get("exe")
            if not exe:
                continue
            e = os.path.normcase(os.path.abspath(exe))
            if e == target or (folder_ok and e.startswith(base + os.sep)):
                res.append(p)
        except Exception:
            continue
    return res


def sample_procs(procs, seconds=1.0):
    """(cpu share of the whole PC in %, total RSS bytes) of the given processes."""
    import psutil
    live = []
    for p in procs:
        try:
            p.cpu_percent(None)
            live.append(p)
        except psutil.Error:
            pass
    time.sleep(seconds)
    cpu = rss = 0.0
    for p in live:
        try:
            cpu += p.cpu_percent(None)
            rss += p.memory_info().rss
        except psutil.Error:
            pass
    return cpu / (psutil.cpu_count() or 1), int(rss)


@cmdlet("pluton.key", group="Port tools", usage="""pluton.key <file>
pluton.key                   uses the file selected earlier with:  cd "<file>"
pluton.key -Watch <seconds>  also measures the real battery change while its program runs
(read-only. Needs no install; 'pip install psutil' adds live memory/CPU of the running program)""")
def pluton_key(args):
    """Number of files, memory and battery used around the selected file."""
    watch, rest, i, low = 0, [], 0, [a.lower() for a in args]
    while i < len(args):
        if low[i] == "-watch":
            if i + 1 < len(args) and args[i + 1].isdigit():
                watch, i = int(args[i + 1]), i + 2
            else:
                watch, i = 30, i + 1
            continue
        rest.append(args[i])
        i += 1
    watch = min(watch, 3600)
    path = pick(rest, "pluton.key")
    if not path:
        return
    full = os.path.abspath(path)
    folder = os.path.dirname(full)
    try:
        fsize = os.path.getsize(full)
        siblings = sum(1 for n in os.listdir(folder) if os.path.isfile(os.path.join(folder, n)))
    except OSError as e:
        out(f"pluton.key : Cannot read file ({e.strerror})", RED)
        out()
        return
    files, dirs, fsz, capped = count_folder(folder)
    plus = "+" if capped else ""
    w = 24

    def row(k, v, color=None):
        out(f"  {k.ljust(w)}: {v}", color)

    out()
    out(f"Pluton report: {safe(os.path.basename(full))}", CYAN)
    out(f"  {safe(full)}", GRAY)
    out()
    out("FILES", YELLOW)
    row("This file", f"{safe(os.path.basename(full))}  ({human(fsize)})")
    row("Files next to it", f"{siblings:,}")
    row("Files in its folder", f"{files:,}{plus} file(s) and {dirs:,} folder(s), counting sub-folders")
    out()

    procs = running_from(folder, full)
    cpu = rss = None
    if procs:
        cpu, rss = sample_procs(procs)
    mem = system_memory()
    out("MEMORY", YELLOW)
    row("Disk space, this file", human(fsize))
    row("Disk space, its folder", f"{human(fsz)}{plus}")
    row("RAM in this PC", f"{human(mem[0])} used of {human(mem[1])} ({mem[0] * 100 // mem[1]}%)" if mem else "unavailable")
    if procs is None:
        row("RAM used by program", "unknown (install psutil to see running programs)", GRAY)
    elif not procs:
        row("RAM used by program", "0 (no program from this file/folder is running)")
    else:
        row("RAM used by program", f"{human(rss)} in {len(procs)} process(es)")
    out()

    bat = battery_info()
    out("BATTERY", YELLOW)
    row("Battery now", battery_text(bat))
    if procs is None:
        row("Power impact", "unknown (install psutil to measure the running program)", GRAY)
    elif not procs:
        row("Power impact", "None right now (the program is not running)")
    else:
        level = "Low" if cpu < 3 else "Medium" if cpu < 15 else "High"
        row("Power impact (estimate)", f"{level}  (CPU {cpu:.1f}% of this PC, sampled over 1 second)",
            RED if level == "High" else YELLOW if level == "Medium" else GREEN)
    out("  The OS does not report battery use per file. Battery state and the program's CPU/RAM", GRAY)
    out("  load (what drains it) are shown; use -Watch <seconds> for a real battery change.", GRAY)
    out()

    if watch:
        if procs is None:
            out("-Watch needs psutil to follow the program (pip install psutil).", YELLOW)
            out()
            return
        out(f"Watching for {watch} s... (Ctrl+C to stop early)", GRAY)
        start, cpus, peak, t0 = battery_info(), [], 0, time.monotonic()
        try:
            while time.monotonic() - t0 < watch:
                if procs:
                    c, r = sample_procs(procs)
                    cpus.append(c)
                    peak = max(peak, r)
                else:
                    time.sleep(1)
        except KeyboardInterrupt:
            pass
        end, secs = battery_info(), int(time.monotonic() - t0)
        out(f"Watched {secs} s:", YELLOW)
        if start and end:
            row("Battery change", f"{start['percent']}% -> {end['percent']}%  ({end['percent'] - start['percent']:+d}%)")
            if secs < 300:
                out("  Battery % moves slowly: watch for 5+ minutes for a meaningful number.", GRAY)
        else:
            row("Battery change", "no battery to measure")
        if cpus:
            row("Average CPU", f"{sum(cpus) / len(cpus):.1f}% of this PC")
            row("Peak RAM", human(peak))
        else:
            row("Program", "was not running during the watch")
        out()


# >>>>> JARVIS-PART 07_help.py >>>>>
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


# >>>>> JARVIS-PART 08_deep_layer_finder_opener.py >>>>>
# ---------- JARVIS deep layer: specific questions + opening files (everything READ-ONLY) ----------
JV_PRON = {"it", "this", "that", "this file", "that file", "the file", "file", "selected", "selected file",
           "the selected file", "the same", "same file", "it again", "questo", "questo file", "quel file",
           "quello", "il file", "esso", "lo", "quel", "selezionato", "il file selezionato"}
JV_HERE = {"folder", "this folder", "the folder", "directory", "this directory", "here", "cartella",
           "questa cartella", "qui", "current folder", "cartella corrente"}
JV_ORD = {"first": 1, "1st": 1, "primo": 1, "prima": 1, "second": 2, "2nd": 2, "secondo": 2, "seconda": 2,
          "third": 3, "3rd": 3, "terzo": 3, "terza": 3, "fourth": 4, "4th": 4, "quarto": 4, "quarta": 4,
          "fifth": 5, "5th": 5, "quinto": 5, "quinta": 5, "last": -1, "ultimo": -1, "ultima": -1}
JV_EXTWORDS = ("png", "jpg", "jpeg", "gif", "webp", "bmp", "pdf", "txt", "csv", "json", "zip", "rar", "7z", "exe",
               "dll", "mp3", "mp4", "mkv", "avi", "mov", "wav", "docx", "xlsx", "pptx", "html", "xml", "sqlite",
               "msi", "bat")
JV_CATS = [
    (("image", "images", "picture", "pictures", "photo", "photos", "immagine", "immagini", "foto"),
     ("png", "jpg", "jpeg", "gif", "webp", "bmp", "tif", "tiff", "ico", "svg")),
    (("document", "documents", "documento", "documenti"), ("doc", "docx", "odt", "rtf", "pdf", "txt", "md")),
    (("spreadsheet", "spreadsheets", "fogli di calcolo", "foglio di calcolo"), ("xls", "xlsx", "ods", "csv", "tsv")),
    (("presentation", "presentations", "slides", "presentazioni"), ("ppt", "pptx", "odp")),
    (("video", "videos"), ("mp4", "mkv", "avi", "mov", "wmv", "webm", "flv")),
    (("music", "audio", "song", "songs", "musica", "canzoni"), ("mp3", "wav", "flac", "ogg", "m4a", "aac", "wma")),
    (("archive", "archives", "archivio", "archivi"), ("zip", "rar", "7z", "gz", "tar", "tgz", "bz2", "xz")),
    (("database", "databases"), ("db", "sqlite", "sqlite3")),
    (("program", "programs", "executable", "executables", "eseguibili", "programmi"), ("exe", "msi", "bat", "cmd")),
    (("script", "scripts", "source code", "codice"), ("py", "js", "ts", "c", "cpp", "h", "java", "cs", "sh", "ps1",
                                                      "go", "rs", "lua")),
]
GM_COUNTS = [
    (r"sprites?", "SPRT", "sprites"), (r"sounds?|sfx|sound effects?|suoni|effetti sonori", "SOND", "sounds"),
    (r"rooms?|levels?|maps?|stanz\w+|livell\w+", "ROOM", "rooms"), (r"objects?|oggett\w+", "OBJT", "objects"),
    (r"fonts?", "FONT", "fonts"), (r"paths?", "PATH", "paths"), (r"scripts?", "SCPT", "scripts"),
    (r"shaders?", "SHDR", "shaders"), (r"backgrounds?|tile ?sets?", "BGND", "backgrounds / tile sets"),
    (r"textures?|texture pages?", "TXTR", "texture pages"), (r"audio files?|embedded audio", "AUDO", "embedded audio files"),
    (r"frames?", "TPAG", "texture-page items (sprite frames and images)"),
    (r"strings?|dialog\w*|text lines?|testi|dialoghi", "STRG", "strings (text, names, dialogue...)"),
    (r"code entries|compiled code|codice", "CODE", "code entries"),
]
PE_MACHINES = {0x14C: "32-bit (x86)", 0x8664: "64-bit (x64)", 0xAA64: "64-bit (ARM64)", 0x1C0: "32-bit (ARM)",
               0x1C4: "32-bit (ARM Thumb-2)", 0x200: "64-bit (Itanium)"}
INTEGRITY_TEST = {".zip": "every entry's CRC", ".png": "every chunk's CRC", ".jpg": "the start and end markers",
                  ".jpeg": "the start and end markers", ".gif": "the header and trailer", ".pdf": "the header and the end marker",
                  ".json": "a full parse", ".gz": "a full decompression", ".db": "SQLite's integrity check",
                  ".sqlite": "SQLite's integrity check", ".sqlite3": "SQLite's integrity check"}


def jv_ago(ts):
    d = max(0, time.time() - ts)
    for sec, nm in ((31536000, "year"), (2592000, "month"), (86400, "day"), (3600, "hour"), (60, "minute")):
        if d >= sec:
            n = int(d // sec)
            return f"{n} {nm}{'s' if n != 1 else ''} ago"
    return "just now"


def jv_rel(p, base):
    try:
        return safe(os.path.relpath(p, base))
    except ValueError:
        return safe(p)


def jv_fmt(x):
    return f"{x:,.2f}".rstrip("0").rstrip(".") if isinstance(x, float) else f"{x:,}"


def jv_listing(folder="."):
    """The visible entries of a folder in the same order as Get-ChildItem (folders first)."""
    try:
        voci = [(n, os.path.join(folder, n)) for n in os.listdir(folder)]
    except OSError:
        return []
    voci = [(n, p) for n, p in voci if not nascosto(p, n)]
    dirs = sorted([v for v in voci if os.path.isdir(v[1])], key=lambda v: v[0].lower())
    files = sorted([v for v in voci if not os.path.isdir(v[1])], key=lambda v: v[0].lower())
    return [os.path.abspath(p) for _, p in dirs + files]


def jv_games(depth=6):
    """The data.win files of the known game folders, in the same order undersopic.key lists them."""
    seen, res = set(), []
    for p in find_named(game_locations() + jv_launch_extra_dirs(), GM_FILE, depth):
        key = os.path.normcase(os.path.realpath(p))
        if key not in seen:
            seen.add(key)
            res.append(p)
    return res


def jv_color_prompt(color, text):
    return f"\x01{color}\x02{text}\x01{TEXT}\x02" if HAS_READLINE else color + text + TEXT


# ---------------- finding the file / folder a sentence is about ----------------
def jv_resolve(cand, strict=False, games=False):
    """Turn a phrase ('data.win', 'the second one', 'undertale', 'biggest file') into a path.
    Returns (status, payload): ok/path, many/[paths], range/count, pron/None, none/None."""
    c0 = re.sub(r"[\s.,;:!?]+$", "", cand.strip().strip("\"'`“”‘’").strip())
    low0 = c0.lower()
    if low0 in JV_PRON:
        return "pron", None
    if low0 in JV_HERE:
        return "ok", os.getcwd()
    if c0:
        for v in (c0, os.path.expanduser(c0)):
            if os.path.exists(v):
                return "ok", os.path.abspath(v)
    c = re.sub(r"^(?:the|il|lo|la|l'|my|that|this|quel|quello|quella)\s+", "", c0, flags=re.I)
    c = re.sub(r"^(?:file|folder|directory|cartella|document|documento|game|gioco)\s+", "", c, flags=re.I)
    c = re.sub(r"^(?:called|named|chiamato|chiamata)\s+", "", c, flags=re.I)
    c = c.strip().strip("\"'`").strip()
    low = c.lower()
    if not low or low in JV_PRON:
        return "pron", None
    if low in JV_HERE:
        return "ok", os.getcwd()
    if os.path.exists(c):
        return "ok", os.path.abspath(c)
    games_word = bool(re.search(r"\b(?:game|games|gioco|giochi)\b", low0))

    idx = None
    m = re.fullmatch(r"(?:#|n\.?\s*|no\.?\s*|number\s+|numero\s+)?(\d{1,4})(?:st|nd|rd|th)?"
                     r"(?:\s+(?:one|file|game|result|item|gioco|risultato))?", low)
    if m:
        idx = int(m.group(1))
    else:
        m = re.fullmatch(r"(first|second|third|fourth|fifth|last|primo|prima|secondo|seconda|terzo|terza|quarto|"
                         r"quarta|quinto|quinta|ultimo|ultima|1st|2nd|3rd|4th|5th)"
                         r"(?:\s+(?:one|file|game|result|item|gioco|risultato|folder|cartella))?", low)
        if m:
            idx = JV_ORD[m.group(1)]
    if idx is not None:
        pool = jv_games() if games_word else (CONTESTO.get("jlist") or jv_listing())
        pool = [p for p in pool if os.path.exists(p)]
        if not pool:
            return "none", None
        if idx == -1:
            return "ok", pool[-1]
        return ("ok", pool[idx - 1]) if 1 <= idx <= len(pool) else ("range", len(pool))

    m = re.fullmatch(r"(?:the\s+)?(biggest|largest|heaviest|smallest|lightest|newest|latest|most recent|oldest|"
                     r"più grande|piu grande|più pesante|piu pesante|più piccolo|piu piccolo|più recente|piu recente|"
                     r"più vecchio|piu vecchio)(?:\s+(?:file|one|here|in (?:this )?folder|qui))*", low)
    if m:
        files = [p for p in jv_listing() if os.path.isfile(p)]
        if not files:
            return "none", None
        w = m.group(1)
        try:
            if w in ("biggest", "largest", "heaviest", "più grande", "piu grande", "più pesante", "piu pesante"):
                return "ok", max(files, key=os.path.getsize)
            if w in ("smallest", "lightest", "più piccolo", "piu piccolo"):
                return "ok", min(files, key=os.path.getsize)
            if w in ("oldest", "più vecchio", "piu vecchio"):
                return "ok", min(files, key=os.path.getmtime)
            return "ok", max(files, key=os.path.getmtime)
        except OSError:
            return "none", None

    try:
        names = os.listdir(".")
    except OSError:
        names = []
    exact = [n for n in names if n.lower() == low]
    if exact:
        return "ok", os.path.abspath(exact[0])
    stem = [n for n in names if os.path.splitext(n)[0].lower() == low]
    if len(stem) == 1:
        return "ok", os.path.abspath(stem[0])
    if len(stem) > 1:
        return "many", [os.path.abspath(n) for n in sorted(stem, key=str.lower)]
    if not strict and len(low) >= 2:
        part = [n for n in names if low in n.lower()]
        pool = [n for n in part if n.lower().startswith(low)] or part
        if len(pool) == 1:
            return "ok", os.path.abspath(pool[0])
        if 1 < len(pool) <= 12:
            return "many", [os.path.abspath(n) for n in sorted(pool, key=str.lower)]
        close = difflib.get_close_matches(low, [n.lower() for n in names], n=1, cutoff=0.72)
        if close:
            return "ok", os.path.abspath(next(n for n in names if n.lower() == close[0]))
    seen = 0                                           # a little deeper: exact names in sub-folders
    for cur, ds, fs in os.walk(".", onerror=lambda e: None):
        depth = 0 if cur == "." else os.path.relpath(cur).count(os.sep) + 1
        ds[:] = [] if depth >= 3 else sorted(d for d in ds if not skip_dir(os.path.join(cur, d)))
        for n in ds + fs:
            seen += 1
            if n.lower() == low or os.path.splitext(n)[0].lower() == low:
                return "ok", os.path.abspath(os.path.join(cur, n))
        if seen > 20000:
            break
    if games and len(low) >= 3:
        hits = []
        for p in jv_games():
            try:
                nm = (gm_read_info(p)["name"] or "").lower()
            except OSError:
                nm = ""
            folder = os.path.basename(os.path.dirname(os.path.abspath(p))).lower()
            if re.fullmatch(JV_LAUNCH_CHAPTER, folder):
                folder = os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(p)))).lower() + " " + folder
            if low in folder or (nm and low in nm):
                hits.append(p)
        if len(hits) == 1:
            return "ok", hits[0]
        if hits:
            return "many", hits[:12]
    return "none", None


def jv_find_target(orig, t):
    """(path, True) when the sentence names an existing file/folder; (None, False) otherwise."""
    for m in re.finditer(r'"([^"]+)"|`([^`]+)`|“([^”]+)”|(?<!\w)\'([^\']+)\'(?!\w)', orig):
        s = next(g for g in m.groups() if g)
        v = os.path.expanduser(s)
        if os.path.exists(v):
            return os.path.abspath(v), True
    skip = {"file", "files", "folder", "folders", "here", "this", "that", "it", "the", "all", "game", "games",
            "data", "size", "type", "lines", "words", "text", "in", "of", "to", "on", "is", "and", "me", "my"}
    for tok in orig.split():
        s = tok.strip(".,;:!?()[]{}\"'`")
        if len(s) >= 2 and s.lower() not in skip and s not in (".", "..") and os.path.exists(os.path.expanduser(s)):
            return os.path.abspath(os.path.expanduser(s)), True
    try:
        names = sorted(os.listdir("."), key=len, reverse=True)
    except OSError:
        names = []
    for n in names:
        nl = n.lower()
        if len(nl) >= 3 and (" " in nl or "." in nl) and re.search(r"(?<![\w.-])" + re.escape(nl) + r"(?![\w-])", t):
            return os.path.abspath(n), True
    for tok in jv_filename_tokens(orig):                    # a name that lives a few folders down
        st, pay = jv_resolve(tok, strict=True)
        if st == "ok":
            return pay, True
    return None, False


def jv_filename_tokens(orig):
    """Words that look like file names (name.ext with a known extension)."""
    known = {e.lstrip(".") for e in TEXT_EXT} | {e.lstrip(".") for e in OFFICE} | set(JV_EXTWORDS) | \
        {"win", "db", "sqlite3", "gz", "dat", "bin", "iso", "tar", "7z", "ini", "log", "dll", "sys"}
    res = []
    for tok in orig.split():
        s = tok.strip(".,;:!?()[]{}\"'`")
        m = re.fullmatch(r"[\w\-.]*\w\.([A-Za-z0-9]{1,6})", s)
        if m and m.group(1).lower() in known:
            res.append(s)
    return res


def jv_target(orig, t, sel):
    p, explicit = jv_find_target(orig, t)
    if p:
        CONTESTO["jlast"] = {"path": p, "sel": sel}
        return p, True
    last = CONTESTO.get("jlast")
    if last and os.path.exists(last["path"]) and (sel is None or last["sel"] == sel):
        return last["path"], False
    if sel and os.path.exists(sel):
        return sel, False
    return None, False


def jv_hint(kind):
    if kind == "GameMaker data file":
        ex = '"what game is this", "how many sprites", "list the chunks", "search for <text>"'
    elif kind.startswith("Text file"):
        ex = '"how many lines", "first 20 lines", "search for <word>", "columns" (for csv), "which keys" (for json)'
    elif is_zip(kind):
        ex = '"what is inside", "biggest entry", "does it contain <name>"'
    elif kind == "SQLite database":
        ex = '"which tables", "how many rows in <table>", "columns of <table>"'
    elif kind.endswith("image"):
        ex = '"dimensions", "is it corrupt", "sha256"'
    elif kind == "Windows executable":
        ex = '"is it 64-bit", "when was it built", "is it signed"'
    elif kind == "PDF document":
        ex = '"how many pages", "is it corrupt", "sha256"'
    else:
        ex = '"how big is it", "when was it modified", "is it corrupt", "sha256", "show me the hex"'
    jarvis_say("It's selected, sir. You can ask me, for instance: " + ex + ".")


# ---------------- opening / selecting / reading ----------------
def jv_open_view(path, select_only=False):
    full = os.path.abspath(path)
    if os.path.isdir(full):
        try:
            os.chdir(full)
        except OSError as e:
            jarvis_say(f"I can't enter '{safe(full)}', sir ({e.strerror}).")
            return
        CONTESTO["file"] = None
        ack(f"Entering {safe(os.path.basename(full) or full)}.")
        esegui("Get-ChildItem")
        CONTESTO["jlist"] = jv_listing()
        return
    try:
        os.chdir(os.path.dirname(full))
    except OSError:
        pass
    CONTESTO["file"] = full
    CONTESTO["jlast"] = {"path": full, "sel": full}
    kind, name = detect_kind(full), safe(os.path.basename(full))
    if select_only:
        try:
            jarvis_say(f"Selected {name} ({kind}, {human(os.path.getsize(full))}).")
        except OSError:
            jarvis_say(f"Selected {name}.")
    else:
        ack(f"Opening {name}. Read-only: I only look inside, I never run or change it.")
        interact_port([full])
    jv_hint(kind)


def jv_read_paged(path):
    text, enc = read_text(path)
    lines = text.splitlines()
    part = os.path.getsize(path) > MAX_TEXT
    jarvis_say(f"{safe(os.path.basename(path))}: {len(lines):,} line(s), {enc}"
               f"{', showing the first 5 MB only' if part else ''}.")
    width = max(40, shutil.get_terminal_size((100, 30)).columns - 9)
    page = max(10, shutil.get_terminal_size((100, 30)).lines - 3)
    interactive = sys.stdin.isatty() and sys.stdout.isatty()
    shown = 0
    for i, line in enumerate(lines, 1):
        out(f"{i:>6} | {safe(line)[:width]}")
        shown += 1
        if not interactive and shown >= 300:
            out(f"  ... {len(lines) - i:,} more line(s)", GRAY)
            break
        if interactive and shown % page == 0 and i < len(lines):
            try:
                ans = input(jv_color_prompt(GRAY, "-- Enter = next page, q = stop -- "))
            except (EOFError, KeyboardInterrupt):
                out()
                break
            if ans.strip().lower() in ("q", "quit", "stop", "exit", "n", "no"):
                break
    out()


def jv_open_request(orig, t, sel):
    pre = r"^(?:(?:please|pls|per favore|per piacere)[,\s]+)?(?:(?:can|could|would|will) you(?: please)?\s+|" \
          r"(?:puoi|potresti|mi puoi|mi potresti)\s+)?"
    m = re.match(pre + r"(open|apri(?:mi)?|view|read|leggi(?:mi)?|display|show me|show|mostrami|mostra|guarda|"
                       r"look at|check out|select|choose|pick|use|seleziona|scegli|"
                       r"launch|start|play|run|avvia(?:mi)?|lancia(?:mi)?|esegui|fai partire|fammi giocare a|"
                       r"giocare a|gioca a|gioca)\s+(.+)$", orig, re.I)
    if not m:
        return False
    verb, rest = m.group(1).lower(), m.group(2).strip()
    if verb in ("launch", "start", "play", "run", "avvia", "avviami", "lancia", "lanciami", "esegui", "fai partire",
                "fammi giocare a", "giocare a", "gioca a", "gioca"):
        # only a game of this PC, and only when spoken to Jarvis by name; anything else is not for this handler
        return bool(CONTESTO.get("jv_named") and (jv_launch_try(rest) or jv_launch_search(rest)))
    if verb in ("select", "choose", "pick", "use", "seleziona", "scegli"):
        mode = "select"
    elif verb in ("read", "leggi", "leggimi"):
        mode = "read"
    elif verb in ("open", "apri", "aprimi"):
        mode = "open"
    else:
        mode = "show"
    strict = mode in ("read", "show")
    if mode == "open" and CONTESTO.get("jv_named") and jv_launch_try(rest):
        return True                                   # 'jarvis open <game>' started (or listed) a game
    st, pay = jv_resolve(rest, strict=strict, games=not strict)
    tail = None
    if st in ("none", "range"):
        for sm in re.finditer(r"(?:\s*,\s*|\s+(?:and then|and|then|e poi|poi|e)\s+)", rest, re.I):
            st2, pay2 = jv_resolve(rest[:sm.start()], strict=strict, games=not strict)
            if st2 in ("ok", "many", "pron"):
                st, pay, tail = st2, pay2, rest[sm.end():].strip()
                break
    if st == "pron":
        last = CONTESTO.get("jlast")
        path = sel if (sel and os.path.exists(sel)) else (last["path"] if last and os.path.exists(last["path"]) else None)
        if path is None:
            if strict:
                return False
            jarvis_say("No file is selected yet, sir. Tell me which one: 'open <file>'.")
            show_file_choices()
            return True
        st, pay = "ok", path
    if st == "many":
        if strict:
            return False
        jarvis_say("Several things match, sir. Which one?")
        for i, p in enumerate(pay, 1):
            out(f"  [{i}] {safe(os.path.relpath(p) if not os.path.isabs(os.path.relpath(p)) else p)}", CYAN)
        CONTESTO["jlist"] = pay
        jarvis_say("Say 'open 1', 'open 2'... or give me the exact name.")
        return True
    if st == "range":
        if strict:
            return False
        jarvis_say(f"There are only {pay} item(s) in that list, sir.")
        return True
    if st == "none":
        if strict:
            return False
        if mode == "open" and CONTESTO.get("jv_named") and jv_launch_search(rest):
            return True
        cand = re.sub(r"\s+", " ", rest)
        jarvis_say(f"I can't find '{safe(cand)}', sir. I looked in this folder, three levels of sub-folders and your game folders.")
        close = difflib.get_close_matches(cand.lower(), [n.lower() for n in os.listdir(".")], n=3, cutoff=0.5)
        if close:
            jarvis_say("Did you mean: " + ", ".join(safe(n) for n in close) + "?")
        else:
            jarvis_say("Say 'list' to see what is here.")
        return True
    if mode == "open" and CONTESTO.get("jv_named") and os.path.isfile(pay):
        jv_launch_file(pay)                           # 'jarvis open <file>' really opens the file
    elif mode == "select":
        jv_open_view(pay, select_only=True)
    elif mode == "read" and os.path.isfile(pay) and detect_kind(pay).startswith("Text file"):
        CONTESTO["file"] = os.path.abspath(pay)
        CONTESTO["jlast"] = {"path": CONTESTO["file"], "sel": CONTESTO["file"]}
        try:
            os.chdir(os.path.dirname(CONTESTO["file"]))
        except OSError:
            pass
        ack("Reading it, read-only.")
        jv_read_paged(pay)
    else:
        jv_open_view(pay)
    if tail:
        was = CONTESTO.get("jv_cmd")
        CONTESTO["jv_cmd"] = CONTESTO.get("jv_named")
        try:
            jarvis_interpret(tail)
        finally:
            CONTESTO["jv_cmd"] = was
    return True


def jv_selection(orig, t, sel):
    if re.search(r"\b(?:deselect|unselect|clear (?:the |my )?selection|forget (?:the |this |that )?file|deseleziona|"
                 r"annulla (?:la )?selezione|rimuovi (?:la )?selezione|drop (?:the )?file)\b", t):
        if sel:
            CONTESTO["file"] = None
            CONTESTO.pop("jlast", None)
            jarvis_say(f"Selection cleared, sir. {safe(os.path.basename(sel))} is no longer selected.")
        else:
            jarvis_say("Nothing is selected, sir.")
        return True
    if re.search(r"^(?:what|which|quale|cosa|che)\b.*\b(?:selected|selezionat\w*|chosen|scelto|am i using|are we using|"
                 r"working (?:on|with)|current file|file corrente)\b", t):
        if sel and os.path.exists(sel):
            try:
                jarvis_say(f"{safe(os.path.basename(sel))}, sir: {detect_kind(sel)}, {human(os.path.getsize(sel))}.")
            except OSError:
                jarvis_say(f"{safe(os.path.basename(sel))}, sir.")
            out(f"  {safe(sel)}", GRAY)
        else:
            jarvis_say("No file is selected, sir. Say 'open <file>' or 'select <file>'.")
        return True
    return False


def jv_navigate(orig, t):
    m = re.match(r"^(?:please\s+|per favore\s+)?(?:go|move|navigate|vai|andiamo|torna|tornare)\b\s*(.*)$", t)
    if not m and not re.fullmatch(r"(?:up|back|indietro)", t):
        return False
    rest = m.group(1).strip() if m else t
    home = os.path.expanduser("~")
    if re.fullmatch(r"(?:up|back|up one(?: level| folder)?|back one(?: level| folder)?|up a (?:level|folder)|"
                    r"to the parent(?: folder)?|indietro|su|su di (?:una|1) cartella|alla cartella superiore|"
                    r"back to the parent(?: folder)?|(?:up|back)(?: a| one)? level)", rest):
        dest = ".."
    elif re.fullmatch(r"(?:(?:to |in |a |alla |nella )?(?:the )?(?:home|casa)(?: folder| directory| cartella)?)", rest):
        dest = home
    else:
        rest = re.sub(r"^(?:to|into|in|a|alla|nella|nel|al)\s+(?:the\s+|la\s+|il\s+)?(?:folder\s+|cartella\s+)?", "", rest).strip()
        if not rest:
            return False
        aliases = {"downloads": "Downloads", "download": "Downloads", "desktop": "Desktop", "scrivania": "Desktop",
                   "documents": "Documents", "documenti": "Documents", "pictures": "Pictures", "immagini": "Pictures",
                   "music": "Music", "musica": "Music", "videos": "Videos", "video": "Videos"}
        dest = None
        if rest.lower() in aliases:
            cand = os.path.join(home, aliases[rest.lower()])
            dest = cand if os.path.isdir(cand) else None
        if dest is None:
            st, pay = jv_resolve(rest, strict=False)
            if st == "ok" and os.path.isdir(pay):
                dest = pay
        if dest is None:
            if rest.lower() in aliases or re.fullmatch(r"[\w .\-]{1,60}", rest):
                jarvis_say(f"I can't find a folder called '{safe(rest)}', sir.")
                return True
            return False
    try:
        os.chdir(dest)
        CONTESTO["file"] = None
        CONTESTO["jlist"] = jv_listing()
        jarvis_say(f"Now in {safe(os.getcwd())}.")
    except OSError as e:
        jarvis_say(f"I can't go there, sir ({e.strerror}).")
    return True


def jv_uptime():
    try:
        import psutil
        return time.time() - psutil.boot_time()
    except Exception:
        pass
    try:
        if os.name == "nt":
            import ctypes
            return ctypes.windll.kernel32.GetTickCount64() / 1000.0
        with open("/proc/uptime", encoding="utf-8", errors="replace") as f:
            return float(f.read().split()[0])
    except Exception:
        return None


def jv_global(t):
    now = datetime.now()
    if re.search(r"\bwhat time\b|\bcurrent time\b|\btime is it\b|\bche ore\b|\bche ora\b|\bwhat'?s the time\b", t):
        jarvis_say(f"It is {now.strftime('%H:%M')}, sir.")
        return True
    if re.search(r"today'?s date|\bwhat(?:'s| is) (?:the )?(?:date|day)\b|\bwhat day\b|\bche giorno\b|\bche data\b|"
                 r"\bcurrent date\b|\bdata di oggi\b", t):
        jarvis_say(f"Today is {now.strftime('%A, %d %B %Y')}, sir.")
        return True
    folderish = re.search(r"folder|director|cartella|\bfiles?\b|\bfile\b", t)
    if not folderish and (re.search(r"\b(?:free|left|available|remaining|libero|liber[ae]|disponibile|rimast\w+)\b.*"
                                    r"\b(?:space|disk|storage|drive|spazio|disco)\b", t)
                          or re.search(r"\b(?:disk|drive|storage|disco)\s+(?:space|usage|capacity)\b|\bspazio\b.*\b(?:libero|disco)\b|"
                                       r"\bhow much (?:disk |storage )?space\b", t)):
        try:
            tot, used, free = shutil.disk_usage(os.getcwd())
            jarvis_say(f"The drive of this folder has {human(free)} free of {human(tot)} ({used * 100 // tot}% used), sir.")
        except OSError as e:
            jarvis_say(f"I can't read the disk figures, sir ({e.strerror}).")
        return True
    if re.search(r"\bpython version\b|\bwhich python\b|\bversione di python\b", t):
        jarvis_say(f"Python {sys.version.split()[0]} on {sys.platform}, sir.")
        return True
    if re.search(r"\bwhat os\b|\bwhich os\b|operating system|sistema operativo|windows version|versione di windows", t):
        import platform
        jarvis_say(f"{platform.platform()}, sir.")
        return True
    if re.search(r"how many (?:cpu|cores?|processors?)|\bcpu cores?\b|quanti (?:core|processori)|number of cores", t):
        jarvis_say(f"{os.cpu_count()} logical processor(s), sir.")
        return True
    if re.search(r"\buptime\b|how long (?:has|have) (?:this|the) (?:pc|computer) been (?:on|running)|\bacceso da\b", t):
        up = jv_uptime()
        if up is None:
            jarvis_say("I can't read the uptime on this system, sir.")
        else:
            d, rem = divmod(int(up), 86400)
            jarvis_say(f"Up for {d} day(s), {rem // 3600} hour(s) and {rem % 3600 // 60} minute(s), sir.")
        return True
    if re.search(r"\bwho am i\b|\bmy user ?name\b|\bhostname\b|\bcomputer name\b|\bnome (?:utente|del computer)\b", t):
        import getpass
        import socket
        try:
            who = getpass.getuser()
        except Exception:
            who = "unknown"
        jarvis_say(f"You are {safe(who)} on {safe(socket.gethostname())}, sir.")
        return True
    return False


def jv_examples(t):
    if not re.search(r"\bexamples?\b|\besempi\b|what can i ask|cosa posso chiedere|what (?:else )?can you answer|"
                     r"what do you know|capabilit", t):
        return False
    jarvis_say("Here is what I can answer, sir. All read-only, except the START A GAME, LAUNCH and UPDATE rows:")
    rows = [
        ("OPEN", 'open data.win   |   open the 2nd one   |   open undertale   |   read notes.txt   |   go up'),
        ("START A GAME", 'jarvis open deltarune   |   jarvis open undertale   |   jarvis open deltarune chapter 2   (plain "open deltarune" never starts it)'),
        ("LAUNCH", 'launch backup.py   |   launch "D:\\Tools\\app.exe"   |   jarvis launch notes.txt   (never asks for administrator rights)'),
        ("VOICE", 'voice on   |   voice off   |   jarvis be quiet   (JARVIS speaks only when you ask)'),
        ("ANY FILE", 'how big is it   |   when was it modified   |   what type is it   |   is it corrupt   |   sha256   |   does the md5 match <hash>'),
        ("TEXT", 'how many lines/words   |   first 20 lines   |   last 5 lines   |   lines 10 to 20   |   search for "word"   |   hex dump'),
        ("CSV / JSON", 'which columns   |   average of <column>   |   first 5 rows   |   which keys   |   value of <key>'),
        ("ZIP / DB", 'what is inside   |   biggest entry   |   which tables   |   how many rows in <table>   |   columns of <table>'),
        ("IMAGE / PDF / EXE", 'dimensions   |   how many pages   |   is it 64-bit   |   when was it built   |   is it signed'),
        ("GAMES (data.win)", 'what game is this   |   how many sprites/rooms/sounds   |   list the chunks   |   biggest chunk   |   search for "text"'),
        ("FOLDER", 'how many files here   |   biggest files   |   newest / oldest   |   find all png files   |   duplicates   |   bigger than 100 MB   |   modified today   |   by extension'),
        ("PC", 'free disk space   |   what time is it   |   uptime   |   status   |   find my games   |   scan this PC for corrupt files'),
        ("KNOWLEDGE", 'what is a dll / sha256 / data.win   |   what does dir do   |   tell me about undertale   |   who made you'),
        ("MATHS / UNITS", 'calculate 15% of 80   |   2+2*3   |   square root of 144   |   convert 5 km to miles   |   100 f to c   |   2 gb in mb'),
        ("DATES", 'how many days until christmas   |   what day is 25/12/2026   |   days between 1/1/2026 and 1/3/2026'),
        ("CHAT", 'jarvis perfect   |   yo big jarvis   |   tell me a joke   |   how are you   |   again (repeats my last request)'),
        ("ONLINE / RESEARCH", 'jarvis be online   |   jarvis search <topic>   |   jarvis cerca <topic>   |   jarvis go offline'),
        ("CHROME (online)", 'jarvis open chrome then gmail on account anna   |   open chrome, youtube lofi and canva   |   apri chrome poi gmail con account paolo'),
        ("CHROME LAYOUT", 'chrome full screen   |   chrome side by side   |   open chrome full screen then gmail   |   apri chrome accanto poi canva'),
        ("NEWS (online)", 'jarvis news   |   jarvis news war   |   jarvis notizie sulle proteste   (world stories in parts, photo + long summary)'),
        ("SECURITY / UPDATE", 'security   |   implement jarvis   |   implement jarvis -Dry   |   implement jarvis <file.py>   |   go in maintenance'),
    ]
    w = max(len(a) for a, _ in rows)
    for a, b in rows:
        out(f"  {a.ljust(w)}  {b}", CYAN)
    out()
    return True


# >>>>> JARVIS-PART 09_readers_type_handlers.py >>>>>
# ---------------- extra readers (all read-only) ----------------
def jv_gm_chunks(path):
    """[(chunk id, data start, data length)] of a GameMaker data file."""
    res = []
    size = os.path.getsize(path)
    with open(guard_path(path), "rb") as f:
        head = f.read(8)
        if len(head) < 8 or head[:4] != b"FORM":
            return res
        end = min(struct.unpack("<I", head[4:8])[0] + 8, size)
        pos = 8
        while pos + 8 <= end and len(res) < 256:
            f.seek(pos)
            hdr = f.read(8)
            if len(hdr) < 8:
                break
            cid, ln = hdr[:4], struct.unpack("<I", hdr[4:8])[0]
            if not re.fullmatch(rb"[A-Z0-9]{4}", cid):
                break
            res.append((cid.decode(), pos + 8, ln))
            pos += 8 + ln
    return res


def jv_gm_count(path, start, ln):
    if ln < 4:
        return None
    with open(guard_path(path), "rb") as f:
        f.seek(start)
        cnt = struct.unpack("<I", f.read(4))[0]
    return cnt if cnt * 4 + 4 <= ln else None


def jv_pe(path):
    with open(guard_path(path), "rb") as f:
        mz = f.read(64)
        if len(mz) < 64 or mz[:2] != b"MZ":
            return None
        f.seek(struct.unpack("<I", mz[60:64])[0])
        if f.read(4) != b"PE\x00\x00":
            return None
        machine, _, ts, _, _, optsz, chars = struct.unpack("<HHIIIHH", f.read(20))
        opt = f.read(optsz)
    if len(opt) < 70:
        return None
    magic = struct.unpack("<H", opt[:2])[0]
    sub = struct.unpack("<H", opt[68:70])[0]
    dd = 96 if magic == 0x10B else 112
    signed = dotnet = False
    if len(opt) >= dd + 120:
        signed = struct.unpack("<II", opt[dd + 32:dd + 40])[1] > 0
        dotnet = struct.unpack("<II", opt[dd + 112:dd + 120])[1] > 0
    return {"machine": PE_MACHINES.get(machine, f"unknown machine 0x{machine:04X}"), "ts": ts,
            "dll": bool(chars & 0x2000), "subsystem": {2: "graphical (GUI)", 3: "console"}.get(sub, f"type {sub}"),
            "signed": signed, "dotnet": dotnet}


def jv_hex_rows(data, base=0):
    rows = []
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        hx = " ".join(f"{b:02X}" for b in chunk).ljust(47)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        rows.append(f"  {base + i:08X}  {hx}  {asc}")
    return rows


def jv_term(orig, t, path):
    """The word/phrase the person wants searched for in a file."""
    for m in re.finditer(r'"([^"]+)"|`([^`]+)`|“([^”]+)”|(?<!\w)\'([^\']+)\'(?!\w)', orig):
        s = next(g for g in m.groups() if g)
        if not os.path.exists(os.path.expanduser(s)):
            return s
    stop = {"the", "a", "an", "it", "this", "that", "file", "files", "in", "text", "something", "anything", "any",
            "for", "inside", "whether", "if", "word", "string", "phrase", "is", "there", "il", "la", "lo", "un", "una"}
    pats = [r"(?:the\s+)?(?:word|text|string|phrase|parola|frase|stringa)\s+(\S+)",
            r"(?:search|find|look)\s+(?:for\s+)?(\S+)\s+(?:in|inside|within|on|dentro|nel|nello|nella|from)\b",
            r"(?:cerca|trova)\s+(\S+)\s+(?:in|dentro|nel|nello|nella)\b",
            r"(?:search(?:\s+for)?|look\s+for|grep|cerca(?:re)?|trova(?:re)?|find)\s+(?:the\s+(?:word|text|string|phrase)\s+|"
            r"la\s+(?:parola|frase)\s+)?(\S+)$",
            r"contains?\s+(?:the\s+)?(\S+)", r"contiene\s+(?:la parola\s+)?(\S+)",
            r"mention(?:s|ing)?\s+(\S+)",
            r"how many times (?:does |is |do )?(\S+)", r"quante volte (?:compare |appare |c'è )?(\S+)"]
    base = os.path.basename(path).lower()
    for p in pats:
        m = re.search(p, orig, re.I)
        if m:
            s = m.group(1).strip(".,;:!?()[]{}\"'`")
            if s and s.lower() not in stop and s.lower() != base:
                return s
    return None


def jv_search(path, term, kind, name):
    tl = term.lower()
    if is_zip(kind):
        try:
            with zipfile.ZipFile(path) as z:
                hits = [i for i in z.infolist() if tl in i.filename.lower()]
        except zipfile.BadZipFile:
            jarvis_say(f"{name} does not open as a ZIP archive, sir: it may be damaged.")
            return
        jarvis_say(f"{len(hits)} entr{'y' if len(hits) == 1 else 'ies'} in {name} match '{safe(term)}' (names only).")
        for i in hits[:20]:
            out(f"  {human(i.file_size).rjust(12)}  {safe(i.filename)}")
        if len(hits) > 20:
            out(f"  ... and {len(hits) - 20:,} more", GRAY)
        out()
        return
    if kind.startswith("Text file"):
        text, enc = read_text(path)
        lines = text.splitlines()
        found = [(i, ln) for i, ln in enumerate(lines, 1) if tl in ln.lower()]
        total = text.lower().count(tl)
        part = " (first 5 MB only)" if os.path.getsize(path) > MAX_TEXT else ""
        if not found:
            jarvis_say(f"'{safe(term)}' does not appear in {name}, sir{part}. The search ignores upper/lower case.")
            return
        jarvis_say(f"'{safe(term)}' appears {total:,} time(s) on {len(found):,} line(s) of {name}{part}.")
        for i, ln in found[:15]:
            out(f"  {i:>6} | {safe(ln.strip())[:110]}")
        if len(found) > 15:
            out(f"  ... and {len(found) - 15:,} more line(s)", GRAY)
        out()
        return
    limit = 64 << 20
    with open(guard_path(path), "rb") as f:
        data = f.read(limit)
    hits = []
    for enc_name in ("utf-8", "utf-16-le"):
        try:
            pat = term.encode(enc_name)
        except UnicodeEncodeError:
            continue
        hits += [(m.start(), enc_name) for m in re.finditer(re.escape(pat), data, re.I)]
    hits.sort()
    part = " (first 64 MB only)" if os.path.getsize(path) > limit else ""
    if not hits:
        jarvis_say(f"I found no '{safe(term)}' inside {name}, sir{part}. Text is searched as UTF-8 and UTF-16, ignoring case.")
        return
    chunks = jv_gm_chunks(path) if kind == "GameMaker data file" else []
    jarvis_say(f"'{safe(term)}' appears {len(hits):,} time(s) in {name}{part}. First {min(len(hits), 15)}:")
    for off, enc_name in hits[:15]:
        ctx = data[max(0, off - 24):off + 48]
        ctx = "".join(chr(b) if 32 <= b < 127 else "." for b in ctx)
        where = next((f" [{cid}]" for cid, s, ln in chunks if s <= off < s + ln), "")
        out(f"  0x{off:08X}{where}  {enc_name}  ...{ctx}...")
    out()


def jv_corrupt_q(path, kind, name, ext):
    if kind == "GameMaker data file" or os.path.basename(path).lower() == GM_FILE:
        info = gm_read_info(path)
        if info["notes"]:
            jarvis_say(f"I see problems in {name}, sir:")
            for n in info["notes"]:
                out(f"  - {n}", YELLOW)
        else:
            jarvis_say(f"{name} looks intact, sir: the FORM length matches the file and all {len(info['chunks'])} chunks parse.")
        return
    status, reason = check_file(path)
    if status == "CORRUPT":
        jarvis_say(f"Yes, sir. {name} is damaged: {reason}.")
    elif status == "WARNING":
        jarvis_say(f"Possibly, sir. {name}: {reason}.")
    elif status == "EMPTY":
        jarvis_say(f"{name} is empty (0 bytes), sir. Nothing to be read from it.")
    elif status == "SKIPPED":
        jarvis_say(f"I did not deep-check {name}, sir: {reason.lower()}.")
    elif ext in INTEGRITY_TEST or ext in ZIP_EXT:
        test = INTEGRITY_TEST.get(ext, "every entry's CRC")
        jarvis_say(f"No damage found, sir. {name} passes my check of {test}.")
    elif ext in TEXT_EXT:
        jarvis_say(f"No damage found, sir. {name} is readable text with no stray NUL bytes.")
    else:
        try:
            with open(guard_path(path), "rb") as f:
                f.read(65536)
            tail_of(path, 4096)
            jarvis_say(f"I found no sign of damage in {name}, sir, but I have no integrity test for this file type: "
                       "all I can say is that it reads fine from start to end markers.")
        except OSError as e:
            jarvis_say(f"I can't read {name} properly, sir ({e.strerror}). It may be damaged.")


# ---------------- per-type question handlers (return True when they answered) ----------------
def jv_gm_q(path, t, name):
    h = lambda *pats: any(re.search(p, t) for p in pats)
    chunks = jv_gm_chunks(path)
    info = gm_read_info(path)
    size = os.path.getsize(path)
    asked = [(cid, label) for pat, cid, label in GM_COUNTS if re.search(r"\b(?:" + pat + r")\b", t)]
    if asked:
        table = {c[0]: c for c in chunks}
        for cid, label in asked:
            if cid not in table:
                jarvis_say(f"{name} has no {cid} chunk, so it lists no {label}, sir.")
                continue
            cnt = jv_gm_count(path, table[cid][1], table[cid][2])
            if cnt is None:
                jarvis_say(f"The {cid} chunk of {name} has an unusual layout, sir: I can't count the {label} safely.")
            else:
                jarvis_say(f"{name} lists {cnt:,} {label} (read from the {cid} chunk header).")
        return True
    if h(r"\bchunks?\b", r"\bbiggest\b.*\b(?:part|section|thing|chunk)\b", r"\btakes? (?:the )?most (?:space|room)\b",
         r"\bwhat takes\b", r"\bpiù pesant\w*\b", r"\bsections?\b"):
        if not chunks:
            jarvis_say(f"I can't read a chunk table from {name}, sir: it may be damaged.")
            return True
        big = h(r"biggest|largest|most|heaviest|takes|pesant|grand")
        rows = sorted(chunks, key=lambda c: -c[2])[:8] if big else chunks
        jarvis_say(f"{name} has {len(chunks)} chunk(s)" + (". The biggest:" if big else ":"))
        for cid, s, ln in rows:
            out(f"  {cid}  {human(ln).rjust(12)}  {ln * 100 / max(size, 1):5.1f}%  - {GM_LABELS.get(cid, '')}")
        out()
        return True
    if h(r"\b(?:what|which|che|quale)\b.*\b(?:game|gioco)\b", r"\bgame name\b", r"\bname of (?:the|this) game\b",
         r"\btitle\b", r"\bgame\b.*\bcalled\b", r"\bgamemaker\b|\bgame ?maker\b", r"\bengine\b", r"\bversion\b|\bversione\b",
         r"\bbytecode\b", r"\bnome del gioco\b", r"\bgioco\b"):
        game = info["name"] or "an unnamed game"
        gm = f", made with GameMaker {info['gm']}" if info["gm"] else ""
        bc = f", bytecode version {info['bytecode']}" if info["bytecode"] is not None else ""
        jarvis_say(f"{name} belongs to {safe(game)}{gm}{bc}, sir. It has {len(chunks)} chunks and weighs {human(size)}.")
        for n in info["notes"]:
            out(f"  Warning: {n}", YELLOW)
        return True
    if h(r"\bstore\b", r"\bsteam\b", r"\bepic\b", r"\bgog\b", r"\bitch\b", r"\binstall\w*\b", r"\bnegozio\b"):
        jarvis_say(f"{name} sits in: {safe(os.path.dirname(os.path.abspath(path)))}  (looks like: {store_of(path)}).")
        return True
    return False


GM_LABELS = {"GEN8": "general info", "OPTN": "options", "LANG": "languages", "EXTN": "extensions", "SOND": "sounds",
             "AGRP": "audio groups", "SPRT": "sprites", "BGND": "backgrounds / tile sets", "PATH": "paths",
             "SCPT": "scripts", "GLOB": "global scripts", "SHDR": "shaders", "FONT": "fonts", "TMLN": "timelines",
             "OBJT": "objects", "ROOM": "rooms", "DAFL": "data files", "TPAG": "texture-page items", "CODE": "code",
             "VARI": "variables", "FUNC": "functions", "STRG": "strings", "TXTR": "textures", "AUDO": "audio",
             "SEQN": "sequences", "ACRV": "animation curves", "TGIN": "texture group info", "DBGI": "debug info",
             "EMBI": "embedded images", "FEDS": "feature flags", "FEAT": "feature flags", "PSEM": "particle systems",
             "PSYS": "particle systems", "UILR": "UI layout"}


def jv_pe_q(path, t, name):
    if not re.search(r"64.?bit|32.?bit|\bx64\b|\bx86\b|\barm\b|architect|architettur|\bcompil\w*|\bbuilt\b|build date|"
                     r"timestamp|\bsigned\b|signature|firma\w*|\bdll\b|\bconsole\b|\bgui\b|\.net|dotnet|subsystem|\bbit\b", t):
        return False
    pe = jv_pe(path)
    if pe is None:
        jarvis_say(f"{name} has a Windows-style header but I can't read its PE structure, sir: it may be damaged.")
        return True
    jarvis_say(f"{name}, sir:")
    from datetime import timezone
    built = ("not recorded" if pe["ts"] in (0, 0xFFFFFFFF) else
             datetime.fromtimestamp(pe["ts"], tz=timezone.utc).strftime("%d/%m/%Y %H:%M UTC") +
             "  (the builder can fake this date)")
    for k, v in (("Architecture", pe["machine"]), ("Kind", "library (DLL)" if pe["dll"] else "program (EXE)"),
                 ("Interface", pe["subsystem"]), ("Built", built),
                 ("Digitally signed", "yes (a signature block is present; I don't validate it)" if pe["signed"] else "no signature block found"),
                 (".NET", "yes, managed code" if pe["dotnet"] else "no (native code)")):
        out(f"  {k.ljust(17)}: {v}")
    out()
    return True


def jv_zip_q(path, t, orig, name):
    h = lambda *pats: any(re.search(p, t) for p in pats)
    if not h(r"entr(?:y|ies)", r"\binside\b", r"\bcontain", r"\blist\b", r"how many (?:files|items|things|documents)",
             r"biggest|largest", r"unpack|extract|decompress|unzip", r"\bcompress", r"\bcontenut", r"\bdentro\b",
             r"quanti file", r"più grand|piu grand", r"\bwhat'?s in\b", r"\bencrypt|password"):
        return False
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        jarvis_say(f"{name} does not open as a ZIP archive, sir: it may be damaged. Ask me 'is it corrupt'.")
        return True
    with z:
        infos = z.infolist()
    files = [i for i in infos if not i.is_dir()]
    total, comp = sum(i.file_size for i in files), sum(i.compress_size for i in files)
    enc = sum(1 for i in infos if i.flag_bits & 1)
    if h(r"unpack|extract|decompress|unzip"):
        jarvis_say("I never unpack archives, sir: I only list them. Here is what is inside.")
    if h(r"biggest|largest|più grand|piu grand"):
        top = sorted(files, key=lambda i: -i.file_size)[:5]
        jarvis_say(f"The biggest entries of {name}:")
        for i in top:
            out(f"  {human(i.file_size).rjust(12)}  {safe(i.filename)}")
        out()
        return True
    if h(r"\bencrypt|password"):
        jarvis_say(f"{enc} of the {len(infos)} entries in {name} are password-protected, sir." if enc else
                   f"No entry in {name} is password-protected, sir.")
        return True
    ratio = f", compressed to {human(comp)} ({comp * 100 // max(total, 1)}%)" if total else ""
    jarvis_say(f"{name} holds {len(files):,} file(s) and {len(infos) - len(files):,} folder(s): {human(total)} unpacked{ratio}."
               + (f" {enc} entr{'y is' if enc == 1 else 'ies are'} password-protected." if enc else ""))
    if not h(r"how many", r"quanti"):
        for i in infos[:30]:
            out(f"  {human(i.file_size).rjust(12)}  {safe(i.filename)}")
        if len(infos) > 30:
            out(f"  ... and {len(infos) - 30:,} more", GRAY)
    out()
    return True


def jv_sqlite_q(path, t, orig, name):
    h = lambda *pats: any(re.search(p, t) for p in pats)
    if not h(r"\btables?\b", r"\brows?\b", r"\bcolumns?\b", r"\bschema\b", r"\brecords?\b", r"\bdatabase\b",
             r"\bfields?\b", r"\btabell\w+", r"\bcolonn\w+", r"\briga\b|\brighe\b", r"\bstruttura\b"):
        return False
    q = lambda n: '"' + n.replace('"', '""') + '"'
    try:
        con = sqlite_open_ro(path)
    except sqlite3.Error as e:
        jarvis_say(f"I can't open {name} as a database, sir ({safe(e)}).")
        return True
    try:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        named = [n for n in tables if re.search(r"(?<![\w])" + re.escape(n.lower()) + r"(?![\w])", t)]
        tab = max(named, key=len) if named else None
        mnum = re.search(r"\b(\d{1,2})\b", t)
        n = min(int(mnum.group(1)), 20) if mnum else 5
        if tab and h(r"\bcolumns?\b", r"\bschema\b", r"\bfields?\b", r"\bcolonn\w+", r"\bstruttura\b"):
            cols = con.execute(f"PRAGMA table_info({q(tab)})").fetchall()
            jarvis_say(f"Table '{safe(tab)}' has {len(cols)} column(s):")
            for c in cols:
                out(f"  {safe(c[1]).ljust(28)} {safe(c[2] or 'no declared type')}{'  (primary key)' if c[5] else ''}")
            out()
        elif tab and h(r"\bfirst\b", r"\btop\b", r"\bsample\b", r"\bshow\b", r"\bprimi\b", r"\bpreview\b", r"\bcontents?\b",
                       r"\bmostra\b", r"\bsome\b"):
            cur = con.execute(f"SELECT * FROM {q(tab)} LIMIT {n}")
            cols = [d[0] for d in cur.description]
            jarvis_say(f"First {n} row(s) of '{safe(tab)}':")
            out("  " + " | ".join(safe(c) for c in cols), YELLOW)
            for row in cur.fetchall():
                out("  " + " | ".join(f"<blob {len(v)} bytes>" if isinstance(v, bytes) else safe(v)[:40] for v in row))
            out()
        elif tab:
            cnt = con.execute(f"SELECT COUNT(*) FROM {q(tab)}").fetchone()[0]
            jarvis_say(f"Table '{safe(tab)}' has {cnt:,} row(s), sir.")
        else:
            res, total = sqlite_tables(path)
            jarvis_say(f"{name} has {total} table(s), sir:")
            for tn, c in res:
                out(f"  {safe(tn).ljust(30)} {c:,} row(s)")
            out()
    except sqlite3.Error as e:
        jarvis_say(f"The database refused that, sir ({safe(e)}).")
    finally:
        con.close()
    return True


def jv_jtype(v):
    return {"dict": "an object", "list": "an array", "str": "a string", "int": "an integer", "float": "a number",
            "bool": "a boolean", "NoneType": "null"}.get(type(v).__name__, type(v).__name__)


def jv_json_q(path, t, orig, name):
    h = lambda *pats: any(re.search(p, t) for p in pats)
    try:
        text, _ = read_text(path, 20 * 1024 * 1024)
        data = json.loads(text.lstrip("\ufeff"))
    except (ValueError, OSError) as e:
        if h(r"\bkeys?\b", r"\bstructure\b", r"\bvalid\b", r"\bschema\b", r"\bvalue\b"):
            jarvis_say(f"{name} is not valid JSON, sir: {safe(e)}.")
            return True
        return False
    key = None
    if isinstance(data, dict):
        for k in data:
            if len(str(k)) >= 3 and re.search(r"(?<![\w])" + re.escape(str(k).lower()) + r"(?![\w])", t):
                if key is None or len(str(k)) > len(str(key)):
                    key = k
    for tok in re.findall(r"[\w\-]+(?:\.[\w\-]+)+", orig):          # dotted path: a.b.c
        node, ok = data, True
        for part in tok.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
                node = node[int(part)]
            else:
                ok = False
                break
        if ok and "." in tok and tok.lower() != name.lower():
            jarvis_say(f"{safe(tok)} = {safe(json.dumps(node, ensure_ascii=False))[:300]}")
            return True
    asks = h(r"\bvalue\b", r"\bwhat(?:'s| is)\b", r"\bshow\b", r"\bget\b", r"\bqual\w*\b", r"\bmostra\b", r"\bdammi\b", r"\bvalore\b")
    if key is not None and asks:
        v = json.dumps(data[key], ensure_ascii=False)
        jarvis_say(f"{safe(key)} is {jv_jtype(data[key])}: {safe(v)[:300]}{' ...' if len(v) > 300 else ''}")
        return True
    if not h(r"\bkeys?\b", r"\bstructure\b", r"\bschema\b", r"how many (?:items|elements|entries|objects|records)",
             r"\bvalid\b", r"\bchiavi?\b", r"\bstruttura\b", r"\bitems?\b"):
        return False
    if isinstance(data, dict):
        jarvis_say(f"{name} is valid JSON: an object with {len(data)} key(s):")
        for k, v in list(data.items())[:25]:
            extra = f" ({len(v)} item(s))" if isinstance(v, (list, dict)) else ""
            out(f"  {safe(k)[:40].ljust(40)} {jv_jtype(v).split(' ', 1)[1]}{extra}")
        if len(data) > 25:
            out(f"  ... and {len(data) - 25} more", GRAY)
    elif isinstance(data, list):
        jarvis_say(f"{name} is valid JSON: an array with {len(data):,} item(s).")
        if data and isinstance(data[0], dict):
            out("  Keys of the first item: " + ", ".join(safe(k) for k in list(data[0])[:15]))
    else:
        jarvis_say(f"{name} is valid JSON holding {jv_jtype(data)}.")
    out()
    return True


def jv_csv_q(path, t, orig, name):
    import csv
    h = lambda *pats: any(re.search(p, t) for p in pats)
    try:
        text, _ = read_text(path)
    except OSError:
        return False
    lines = text.splitlines()
    if not lines:
        return False
    delim = max(",;\t|", key=lines[0].count)
    rows = list(csv.reader(lines, delimiter=delim))
    header, data = rows[0], rows[1:]
    lowh = [c.strip().lower() for c in header]
    col = None
    for i, c in enumerate(lowh):
        if c and re.search(r"(?<![\w])" + re.escape(c) + r"(?![\w])", t) and (col is None or len(c) > len(lowh[col])):
            col = i
    trig = h(r"\bcolumns?\b", r"\bheaders?\b", r"\bfields?\b", r"\bcolonn\w+", r"\bintestazion\w+", r"\brows?\b", r"\brighe\b",
             r"\brecords?\b", r"\baverage\b", r"\bmean\b", r"\bmedia\b", r"\bsum\b", r"\btotal\b", r"\bsomma\b", r"\btotale\b",
             r"\bminimum\b|\bmin\b|\blowest\b|\bsmallest\b", r"\bmaximum\b|\bmax\b|\bhighest\b|\blargest\b|\bbiggest\b",
             r"\bunique\b|\bdistinct\b|\bunici\b", r"\bmost common\b|\bfrequent\b", r"\bsample\b|\bpreview\b")
    if not trig and col is None:
        return False

    def num(v):
        v = v.strip().replace(" ", "")
        try:
            return float(v)
        except ValueError:
            if "," in v and delim != ",":
                try:
                    return float(v.replace(",", "."))
                except ValueError:
                    return None
        return None

    if col is not None and not h(r"\bcolumns?\b", r"\bheaders?\b"):
        vals = [r[col].strip() for r in data if col < len(r) and r[col].strip() != ""]
        nums = [x for x in (num(v) for v in vals) if x is not None]
        cname = safe(header[col].strip())
        if len(nums) >= max(1, len(vals) * 0.8) and not h(r"\bunique\b|\bdistinct\b|\bunici\b|\bmost common\b|\bfrequent\b"):
            if h(r"\bsum\b|\btotal\b|\bsomma\b|\btotale\b") :
                jarvis_say(f"The sum of '{cname}' is {jv_fmt(sum(nums))}, sir ({len(nums):,} values).")
            elif h(r"\baverage\b|\bmean\b|\bmedia\b"):
                jarvis_say(f"The average of '{cname}' is {jv_fmt(sum(nums) / len(nums))}, sir ({len(nums):,} values).")
            elif h(r"\bminimum\b|\bmin\b|\blowest\b|\bsmallest\b"):
                jarvis_say(f"The lowest '{cname}' is {jv_fmt(min(nums))}, sir.")
            elif h(r"\bmaximum\b|\bmax\b|\bhighest\b|\blargest\b|\bbiggest\b"):
                jarvis_say(f"The highest '{cname}' is {jv_fmt(max(nums))}, sir.")
            else:
                jarvis_say(f"'{cname}' is numeric, sir: {len(nums):,} values, sum {jv_fmt(sum(nums))}, "
                           f"average {jv_fmt(sum(nums) / len(nums))}, min {jv_fmt(min(nums))}, max {jv_fmt(max(nums))}.")
        else:
            from collections import Counter
            cnt = Counter(vals)
            jarvis_say(f"'{cname}' has {len(vals):,} filled value(s), {len(cnt):,} distinct. Most common:")
            for v, c in cnt.most_common(8):
                out(f"  {str(c).rjust(7)} x  {safe(v)[:60]}")
            out()
        return True
    if h(r"\bsample\b", r"\bpreview\b", r"\bfirst\b", r"\btop\b", r"\bshow\b") and h(r"\brows?\b", r"\brighe\b", r"\brecords?\b"):
        mnum = re.search(r"\b(\d{1,3})\b", t)
        n = min(int(mnum.group(1)), 50) if mnum else 5
        jarvis_say(f"First {n} data row(s) of {name}:")
        out("  " + " | ".join(safe(c) for c in header), YELLOW)
        for r in data[:n]:
            out("  " + " | ".join(safe(c)[:30] for c in r))
        out()
        return True
    if h(r"\bcolumns?\b", r"\bheaders?\b", r"\bfields?\b", r"\bcolonn\w+", r"\bintestazion\w+"):
        jarvis_say(f"{name} has {len(header)} column(s): " + ", ".join(safe(c.strip()) for c in header[:40]) + ".")
        return True
    jarvis_say(f"{name} has {len(data):,} data row(s) and {len(header)} column(s), sir.")
    return True


def jv_pdf_q(path, t, name):
    if not re.search(r"\bpages?\b|\bpagine\b|\bencrypt\w*\b|\bpassword\b|\bcifrat\w+\b", t):
        return False
    with open(guard_path(path), "rb") as f:
        raw = f.read(20 * 1024 * 1024)
    pages = len(re.findall(rb"/Type\s*/Page[^s]", raw))
    enc = b"/Encrypt" in raw
    if re.search(r"\bencrypt\w*\b|\bpassword\b|\bcifrat\w+\b", t):
        jarvis_say(f"{name} {'is encrypted (it has an /Encrypt entry)' if enc else 'shows no encryption'}, sir.")
    else:
        jarvis_say(f"{name} has about {pages or 'an unknown number of'} page(s), sir"
                   f"{' (the count may be off: some PDFs hide page objects in compressed streams)' if not pages else ''}.")
    return True


def jv_file_q(orig, t, path, explicit):
    name = safe(os.path.basename(path))
    try:
        st = os.stat(path)
    except OSError as e:
        jarvis_say(f"I can't read {name}, sir ({e.strerror}).")
        return True
    size = st.st_size
    kind = detect_kind(path)
    ext = os.path.splitext(path)[1].lower()
    is_text = kind.startswith("Text file")
    is_gm = kind == "GameMaker data file" or os.path.basename(path).lower() == GM_FILE
    h = lambda *pats: any(re.search(p, t) for p in pats)
    fw = (not explicit) and h(r"\b(?:folders?|director(?:y|ies)|cartell\w+|here|qui)\b")
    nonum = lambda: jarvis_say(f"{name} is not a text file ({kind}), sir, so it has no lines to speak of. "
                               f"Ask me for 'the hex' instead.")

    # 1. checksums (and comparing against a hash the person pastes)
    if h(r"\bsha.?256\b", r"\bmd5\b", r"\bchecksums?\b", r"\bhash(?:es)?\b", r"\bdigest\b", r"\bimpronta\b"):
        if size > MAX_HASH:
            jarvis_say(f"{name} is larger than 256 MB, sir: I skip the checksums for files that big.")
            return True
        sha, md = digests(path)
        want_sha, want_md = h(r"\bsha.?256\b") or not h(r"\bmd5\b"), h(r"\bmd5\b") or not h(r"\bsha.?256\b")
        given = re.findall(r"\b[0-9a-fA-F]{64}\b|\b[0-9a-fA-F]{32}\b", orig)
        if given:
            for g in given:
                real, label = (sha, "SHA256") if len(g) == 64 else (md, "MD5")
                if g.upper() == real:
                    jarvis_say(f"The {label} MATCHES, sir: {name} is exactly the file that hash describes.")
                else:
                    jarvis_say(f"The {label} does NOT match, sir. The file gives {real}; you gave {g.upper()}.")
            return True
        jarvis_say(f"Checksums of {name}, sir:")
        if want_sha:
            out(f"  SHA256 : {sha}")
        if want_md:
            out(f"  MD5    : {md}")
        out()
        return True

    # 2. searching inside the file
    searching = h(r"\b(?:search|find|look for|grep|cerca\w*|trova\w*|contain\w*|contiene|mention\w*|appears?|occurrences?|"
                  r"occorrenz\w*)\b", r"how many times", r"quante volte")
    if searching:
        pron = h(r"\b(?:in|inside|within|dentro|nel|nello|from)\s+(?:it|this file|that file|the (?:selected )?file|questo file|quel file|il file|esso)\b",
                 r"\b(?:does|do|did)\s+(?:it|this file|the file|that file)\b", r"\b(?:it|this file|the file)\s+(?:contain|mention|include)",
                 r"\bcontiene\b", r"quante volte", r"how many times")
        folderish_s = h(r"\b(?:folders?|director\w+|cartell\w+|pcs?|computer|everywhere|drives?|disk|here|qui|downloads|desktop)\b")
        content_verb = h(r"\b(?:search|grep|look for|cerca\w*)\b") or bool(re.search(r"[\"“`]", orig))
        term = jv_term(orig, t, path) if (explicit or pron or (content_verb and not folderish_s)) else None
        if term:
            jv_search(path, term, kind, name)
            return True

    # 3. showing lines / hex
    m = (re.search(r"\b(?:first|top|head|primi|prime|prima)\s+(\d+)\s+(?:lines?|righe)\b", t)
         or re.search(r"\b(?:first|top|head|primi|prime)\s+(?:lines?|righe)\b", t))
    if m:
        if not is_text:
            nonum()
            return True
        n = min(int(m.group(1)) if m.groups() else 10, 200)
        lines = read_text(path)[0].splitlines()
        jarvis_say(f"First {min(n, len(lines))} line(s) of {name}:")
        for i, ln in enumerate(lines[:n], 1):
            out(f"  {i:>6} | {safe(ln)[:120]}")
        out()
        return True
    m = (re.search(r"\b(?:last|bottom|tail|ultim[ei])\s+(\d+)\s+(?:lines?|righe)\b", t)
         or re.search(r"\b(?:last|bottom|tail|ultim[ei])\s+(?:lines?|righe)\b", t))
    if m:
        if not is_text:
            nonum()
            return True
        n = min(int(m.group(1)) if m.groups() else 10, 200)
        lines = read_text(path)[0].splitlines()
        start = max(0, len(lines) - n)
        jarvis_say(f"Last {len(lines) - start} line(s) of {name}:")
        for i, ln in enumerate(lines[start:], start + 1):
            out(f"  {i:>6} | {safe(ln)[:120]}")
        out()
        return True
    m = re.search(r"\blines?\s+(\d+)\s*(?:to|-|through|and|a|e)\s*(\d+)\b", t) or \
        re.search(r"\brighe\s+(?:da\s+)?(\d+)\s*(?:a|-|to)\s*(\d+)\b", t)
    if m:
        if not is_text:
            nonum()
            return True
        a, b = int(m.group(1)), min(int(m.group(2)), int(m.group(1)) + 199)
        lines = read_text(path)[0].splitlines()
        jarvis_say(f"Lines {a} to {min(b, len(lines))} of {name} ({len(lines):,} in total):")
        for i in range(max(a, 1), min(b, len(lines)) + 1):
            out(f"  {i:>6} | {safe(lines[i - 1])[:120]}")
        out()
        return True
    m = re.search(r"\b(?:line|riga)\s+(?:number\s+|numero\s+)?(\d+)\b", t)
    if m:
        if not is_text:
            nonum()
            return True
        lines = read_text(path)[0].splitlines()
        i = int(m.group(1))
        if 1 <= i <= len(lines):
            jarvis_say(f"Line {i} of {name}:")
            out(f"  {i:>6} | {safe(lines[i - 1])[:200]}")
        else:
            jarvis_say(f"{name} has only {len(lines):,} line(s), sir.")
        out()
        return True
    if h(r"\bhex(?:dump)?\b", r"\besadecimal\w*\b", r"\b(?:first|primi)\s+\d+\s+bytes?\b", r"\bbytes? at offset\b", r"\boffset\b"):
        mn = re.search(r"\b(\d+)\s+bytes?\b", t)
        mo = re.search(r"\boffset\s+(0x[0-9a-f]+|\d+)\b", t)
        n = min(int(mn.group(1)), 512) if mn else 128
        off = int(mo.group(1), 16 if mo.group(1).startswith("0x") else 10) if mo else 0
        with open(guard_path(path), "rb") as f:
            f.seek(min(off, size))
            data = f.read(n)
        jarvis_say(f"{len(data)} byte(s) of {name} from offset 0x{off:X} (viewing only, nothing is executed):")
        for r in jv_hex_rows(data, off):
            out(r)
        out()
        return True

    # 4. counts and encoding
    if h(r"\bhow many (?:lines?|words?|characters?|chars?|letters?|righe|parole|caratteri)\b", r"\bnumber of (?:lines|words|characters)\b",
         r"\bquant[ie] (?:righe|parole|caratteri)\b", r"\bword count\b", r"\bline count\b", r"\bconta (?:le )?(?:righe|parole)\b",
         r"\bcount (?:the )?(?:lines|words|characters)\b"):
        if not is_text:
            nonum()
            return True
        text, enc = read_text(path)
        part = " (first 5 MB only)" if size > MAX_TEXT else ""
        if ext in (".csv", ".tsv") and h(r"\brows?\b|\brecords?\b|\brighe\b"):
            jarvis_say(f"{name} has {max(len(text.splitlines()) - 1, 0):,} data row(s) plus the header, sir{part}.")
        else:
            jarvis_say(f"{name}: {len(text.splitlines()):,} line(s), {len(text.split()):,} word(s), {len(text):,} character(s){part}.")
        return True
    if h(r"\bencoding\b", r"\bcodifica\b", r"\bcharset\b", r"\butf.?8\b", r"\butf.?16\b") and is_text:
        enc = read_text(path)[1]
        jarvis_say(f"{name} is encoded as {enc}, sir.")
        return True

    # 5. is it damaged?
    if h(r"\bcorrupt\w*\b", r"\bcorrott\w*\b", r"\bdamaged?\b", r"\bdanneggiat\w*\b", r"\bbroken\b", r"\brott[oi]\b", r"\bintact\b",
         r"\bintegr\w*\b", r"\btruncat\w*\b", r"\btroncat\w*\b", r"\btamper\w*\b", r"\bvalid\b(?!\s+json)", r"\bhealthy\b", r"\bsano\b",
         r"\bis it (?:ok|fine)\b", r"\bsafe to open\b"):
        lead = h(r"^(?:is|are|does|do|did|can|could|has|have|will|would|should|è|e'|sono|sembra|looks?|seems?|check|verify|"
                 r"test|controlla|verifica|testa|scan)\b")
        wide = h(r"\b(?:pc|computer|whole|entire|everything|folder|cartella|tutto|intero|all files|every file|games?)\b")
        if (explicit or lead) and not wide:
            jv_corrupt_q(path, kind, name, ext)
            return True

    # 6. image size
    if h(r"\bdimensions?\b", r"\bresolution\b", r"\bpixels?\b", r"\brisoluzione\b", r"how (?:wide|tall)\b", r"\bwidth\b",
         r"\bheight\b", r"\blarghezza\b", r"\baltezza\b", r"\baspect ratio\b"):
        dim = image_size(path, kind) if kind.endswith("image") else None
        if dim:
            from math import gcd
            g = gcd(dim[0], dim[1]) or 1
            jarvis_say(f"{name} is {dim[0]} x {dim[1]} pixels (aspect ratio {dim[0] // g}:{dim[1] // g}), sir.")
        elif kind.endswith("image"):
            jarvis_say(f"{name} is an image but I couldn't read its dimensions, sir. It may be damaged.")
        else:
            jarvis_say(f"{name} is not an image I can measure ({kind}), sir.")
        return True

    # 7. where is it
    if h(r"\bwhere (?:is|are)\s+(?:it|this|that|the file)\b", r"\bpath\b", r"\blocation\b", r"\bpercorso\b", r"\bdove si trova\b",
         r"\bfull ?name\b") and not h(r"\bwhere is the\b.*\b(?:text|word)\b"):
        jarvis_say(f"{name} lives at: {safe(os.path.abspath(path))}" + (f"  (looks like: {store_of(path)})" if is_gm else ""))
        return True

    # 8. type-specific questions
    if is_gm and jv_gm_q(path, t, name):
        return True
    if kind == "Windows executable" and jv_pe_q(path, t, name):
        return True
    if is_zip(kind) and jv_zip_q(path, t, orig, name):
        return True
    if kind == "SQLite database" and jv_sqlite_q(path, t, orig, name):
        return True
    if ext == ".json" and jv_json_q(path, t, orig, name):
        return True
    if ext in (".csv", ".tsv") and is_text and jv_csv_q(path, t, orig, name):
        return True
    if kind == "PDF document" and jv_pdf_q(path, t, name):
        return True

    # 9. dates, size, type
    if not fw and h(r"\b(?:when|quando)\b.*\b(?:modif\w*|creat\w*|chang\w*|updat\w*|edit\w*|sav\w*|made|born|download\w*|open\w*|access\w*|aperto)\b",
                    r"\blast (?:modified|write|changed|updated|edited|opened|accessed)\b", r"\bultima modifica\b", r"\bmodificat[oa]\b",
                    r"\bcreat[oa]\b", r"\bhow old\b", r"\bquanto (?:è )?vecchio\b", r"\bdata di (?:modifica|creazione)\b", r"\bdate\b"):
        fmt = lambda ts: datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M:%S") + f"  ({jv_ago(ts)})"
        born = getattr(st, "st_birthtime", st.st_ctime)
        label = "Created" if os.name == "nt" or hasattr(st, "st_birthtime") else "Status changed"
        if h(r"\bcreat\w*\b", r"\bborn\b", r"\bmade\b", r"\bhow old\b", r"\bvecchio\b", r"\bcreazione\b"):
            jarvis_say(f"{name} was {label.lower()} on {fmt(born)}, sir.")
        elif h(r"\bmodif\w*\b", r"\bchang\w*\b", r"\bupdat\w*\b", r"\bedit\w*\b", r"\bsav\w*\b", r"\bwrite\b"):
            jarvis_say(f"{name} was last modified on {fmt(st.st_mtime)}, sir.")
        elif h(r"\bopen\w*\b", r"\baccess\w*\b", r"\baperto\b"):
            jarvis_say(f"{name} was last accessed on {fmt(st.st_atime)}, sir (some systems don't update this).")
        else:
            jarvis_say(f"Dates of {name}, sir:")
            out(f"  {label.ljust(14)}: {fmt(born)}")
            out(f"  Modified      : {fmt(st.st_mtime)}")
            out(f"  Accessed      : {fmt(st.st_atime)}")
            out()
        return True
    if not fw and h(r"\bhow (?:big|large|heavy)\b", r"\bsize\b", r"\bquanto pesa\b", r"\bpeso\b", r"\bdimension[ei]\b",
                    r"\bhow much (?:space|room)\b", r"\bquanto (?:spazio|è grande)\b", r"\bweigh\b"):
        extra = ""
        try:
            if is_zip(kind):
                with zipfile.ZipFile(path) as z:
                    extra = f" Unpacked it would be about {human(sum(i.file_size for i in z.infolist()))}."
            elif kind == "GZIP archive" and size >= 4:
                with open(guard_path(path), "rb") as f:
                    f.seek(-4, 2)
                    extra = f" Unpacked it would be about {human(struct.unpack('<I', f.read(4))[0])} (from the gzip trailer)."
        except (OSError, zipfile.BadZipFile):
            pass
        jarvis_say(f"{name} weighs {human(size)}" + (f" ({size:,} bytes)" if size >= 1024 else "") + f", sir.{extra}")
        return True
    if not fw and h(r"\bwhat (?:type|kind|sort) of file\b", r"\bwhat (?:format|type|kind)\b", r"\bche (?:tipo|formato)\b", r"\bwhat is (?:it|this|that)\b",
                    r"\bwhat file is (?:it|this)\b", r"\bfile type\b", r"\bextension\b", r"\bestensione\b", r"\bmime\b", r"\bcos'?è\b",
                    r"\bwhat'?s this\b", r"\bwhat is the file\b"):
        mime = "application/octet-stream" if is_gm else (mimetypes.guess_type(path)[0] or "unknown")
        jarvis_say(f"{name} is a {kind}, sir: extension {ext or '(none)'}, MIME type {mime}, {human(size)}.")
        return True
    return False


# >>>>> JARVIS-PART 10_folder_questions.py >>>>>
# ---------------- folder-level questions ----------------
def jv_filter(orig, t):
    """(predicate, description) from words like 'png files', '*.txt', 'named report', or None."""
    import fnmatch
    exts, names, globs = set(), [], []
    for m in re.finditer(r"(?<![\w.])\*?\.([a-z0-9]{1,6})\b", t):
        exts.add(m.group(1))
    for w in re.findall(r"\b(" + "|".join(JV_EXTWORDS) + r")s?\b", t):
        exts.add(w)
    for words, cat in JV_CATS:
        if any(re.search(r"\b" + re.escape(w) + r"\b", t) for w in words):
            exts.update(cat)
    globs = [g for g in re.findall(r"[\w.\-*?]*[*?][\w.\-*?]*", orig) if len(g) > 1 and not re.fullmatch(r"\*?\.[a-z0-9]{1,6}", g.lower())
             and not re.fullmatch(r"\*\.[a-z0-9]{1,6}", g.lower())]
    for m in re.finditer(r'"([^"]+)"|`([^`]+)`|“([^”]+)”', orig):
        s = next(g for g in m.groups() if g)
        if not os.path.exists(os.path.expanduser(s)):
            names.append(s)
    m = re.search(r"(?:named|called|name contains|containing|chiamat[oi]|nome)\s+([\w.\- ]+?)(?:\s+(?:in|inside|on|from|under|within|here)\b|$)", t)
    if m and not names:
        names.append(m.group(1).strip())
    if not (exts or names or globs):
        m = re.match(r"^(?:find|search(?: for)?|locate|where is|where are|trova|cerca|dov['’]?\s?[eè])\s+(?:the\s+|my\s+|il\s+|la\s+|i\s+)?"
                     r"(?:file\s+)?(?:called\s+|named\s+)?([\w.\-]+)(?:\s+(?:in|inside|under|within|nel|nella|here|qui)\b.*)?$", t)
        block = {"my", "games", "game", "files", "file", "everything", "it", "something", "anything", "stuff", "data.win",
                 "corrupt", "folders", "folder", "giochi", "gioco", "tutto", "duplicates", "duplicati", "the", "all"}
        if m and m.group(1) not in block:
            names.append(m.group(1))
    if not (exts or names or globs):
        return None

    def pred(p):
        n = os.path.basename(p).lower()
        e = os.path.splitext(n)[1].lstrip(".")
        return ((not exts or e in exts) and all(fnmatch.fnmatch(n, g.lower()) for g in globs)
                and all(s.lower() in n for s in names))
    desc = ", ".join(filter(None, [("*." + "/".join(sorted(exts)) if exts and len(exts) <= 4 else ("%d file types" % len(exts) if exts else "")),
                                   ("matching " + " ".join(globs)) if globs else "",
                                   ("with '" + "' and '".join(names) + "' in the name") if names else ""]))
    return pred, desc


def jv_walk(scope, recurse, cap=200000):
    res, capped = [], False
    if recurse:
        for cur, ds, fs in os.walk(scope, onerror=lambda e: None):
            ds[:] = [d for d in ds if not skip_dir(os.path.join(cur, d))]
            for f in fs:
                p = os.path.join(cur, f)
                try:
                    stt = os.lstat(p)
                except OSError:
                    continue
                res.append((p, stt.st_size, stt.st_mtime))
                if len(res) >= cap:
                    return res, True
    else:
        try:
            names = os.listdir(scope)
        except OSError:
            return res, False
        for f in names:
            p = os.path.join(scope, f)
            try:
                stt = os.lstat(p)
            except OSError:
                continue
            if stat.S_ISREG(stt.st_mode) and not nascosto(p, f):
                res.append((p, stt.st_size, stt.st_mtime))
    return res, capped


def jv_rows(rows, base, limit=25):
    for p, sz, mt in rows[:limit]:
        out(f"  {human(sz).rjust(11)}  {datetime.fromtimestamp(mt).strftime('%d/%m/%Y %H:%M')}  {jv_rel(p, base)}")
    if len(rows) > limit:
        out(f"  ... and {len(rows) - limit:,} more", GRAY)
    out()


def jv_size_of(txt):
    m = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*(bytes?|kb|mb|gb|tb|b)", txt.strip().lower())
    n = float(m.group(1).replace(",", "."))
    mult = {"b": 1, "byte": 1, "bytes": 1, "kb": 1 << 10, "mb": 1 << 20, "gb": 1 << 30, "tb": 1 << 40}[m.group(2)]
    return int(n * mult)


def jv_folder_q(orig, t, scope, explicit_dir):
    h = lambda *pats: any(re.search(p, t) for p in pats)
    base = os.path.abspath(scope)
    where = "this folder" if not explicit_dir else safe(os.path.basename(base) or base)
    explicit_flat = h(r"\b(?:only|just|top.?level|directly|non.?recurs\w*|solo|soltanto)\b")
    wants_deep = h(r"recurs", r"sub-?folders?", r"sottocartell", r"\bbelow\b", r"\beverything\b", r"\btutt[oi]\b", r"\bdeep\b")
    recurse = wants_deep or not (explicit_flat or h(r"\b(?:here|qui)\b"))
    scope_txt = "this folder and everything below it" if recurse else "this folder only"
    if explicit_dir:
        scope_txt = scope_txt.replace("this folder", where)

    # find / count by type, name or pattern
    trigger = h(r"\b(?:find|search|locate|look for|where (?:is|are)|show (?:me )?(?:all|every)|list (?:all|every|the)|display all|"
                r"trova\w*|cerca\w*|dov['’]?\s?[eè]|mostra\w* (?:tutt\w+|ogni)|elenca\w*)\b", r"\bhow many\b", r"\bquant[ie]\b")
    if trigger:
        flt = jv_filter(orig, t)
        if flt:
            pred, desc = flt
            everywhere = h(r"\beverywhere\b", r"\bwhole (?:pc|computer)\b", r"\bentire (?:pc|computer)\b", r"\ball (?:drives|disks)\b",
                           r"\bany drive\b", r"\btutto il (?:pc|computer)\b", r"\bovunque\b")
            roots = pc_roots() if everywhere else [base]
            if everywhere:
                jarvis_say("Searching the whole computer, sir. Read-only; Ctrl+C stops me.")
            found, scanned, stopped = [], 0, False
            try:
                for root in roots:
                    for cur, ds, fs in os.walk(root, onerror=lambda e: None):
                        ds[:] = sorted(d for d in ds if not skip_dir(os.path.join(cur, d)))
                        for f in sorted(fs):
                            scanned += 1
                            p = os.path.join(cur, f)
                            if pred(p):
                                found.append(p)
                        if not recurse and not everywhere:
                            break
                        if scanned > 1500000:
                            stopped = True
                            break
            except KeyboardInterrupt:
                stopped = True
            where_txt = "the whole computer" if everywhere else scope_txt
            if not found:
                jarvis_say(f"I found no files {desc} in {where_txt}, sir ({scanned:,} files looked at).")
                return True
            jarvis_say(f"{len(found):,} file(s) {desc} in {where_txt}, sir ({scanned:,} files looked at"
                       f"{'; stopped early, the list may be incomplete' if stopped else ''}).")
            rows = []
            for p in found[:40]:
                try:
                    stt = os.stat(p)
                    rows.append((p, stt.st_size, stt.st_mtime))
                except OSError:
                    pass
            for i, (p, sz, mt) in enumerate(rows, 1):
                out(f"  [{i:>2}] {human(sz).rjust(11)}  {jv_rel(p, None if everywhere else base)}")
            if len(found) > 40:
                out(f"  ... and {len(found) - 40:,} more", GRAY)
            CONTESTO["jlist"] = found[:200]
            out()
            jarvis_say("Say 'open 1' (or the number you like) to look inside one of them.")
            return True

    # duplicates
    if h(r"\bduplicat\w*\b", r"\bduplicati\b", r"\bidentical files\b", r"\bsame files?\b", r"\bcopies\b", r"\bcopie\b"):
        files, capped = jv_walk(base, recurse)
        by_size = {}
        for p, sz, _ in files:
            if sz > 0:
                by_size.setdefault(sz, []).append(p)
        groups, hashed, skipped = [], 0, 0
        try:
            for sz, ps in by_size.items():
                if len(ps) < 2:
                    continue
                if sz > 200 * 1024 * 1024 or hashed >= 3000:
                    skipped += len(ps)
                    continue
                by_hash = {}
                for p in ps:
                    try:
                        by_hash.setdefault(digests(p)[0], []).append(p)
                        hashed += 1
                    except OSError:
                        pass
                groups += [(sz, g) for g in by_hash.values() if len(g) > 1]
        except KeyboardInterrupt:
            jarvis_say("Stopped, sir. The list is partial.")
        if not groups:
            jarvis_say(f"No duplicate files in {scope_txt}, sir ({len(files):,} files compared).")
            return True
        waste = sum((len(g) - 1) * sz for sz, g in groups)
        jarvis_say(f"{len(groups)} group(s) of identical files in {scope_txt}, sir. Deleting copies would free {human(waste)} "
                   "(I never delete anything myself).")
        for sz, g in sorted(groups, key=lambda x: -x[0] * (len(x[1]) - 1))[:10]:
            out(f"  {human(sz)} x {len(g)}", YELLOW)
            for p in g[:6]:
                out(f"      {jv_rel(p, base)}")
        if skipped:
            out(f"  ({skipped} file(s) over 200 MB or beyond the hashing cap were not compared)", GRAY)
        out()
        return True

    # bigger / smaller than
    m = re.search(r"\b(bigger|larger|greater|over|above|more than|heavier than|piu di|più di|oltre|sopra|maggiore di|"
                  r"smaller|less than|under|below|lighter than|meno di|sotto|minore di)\s+(?:than\s+)?(\d+(?:[.,]\d+)?\s*(?:bytes?|kb|mb|gb|tb|b))\b", t)
    if m:
        limit = jv_size_of(m.group(2))
        bigger = m.group(1) in ("bigger", "larger", "greater", "over", "above", "more than", "heavier than", "piu di", "più di",
                                "oltre", "sopra", "maggiore di")
        files, capped = jv_walk(base, recurse)
        rows = sorted([r for r in files if (r[1] > limit if bigger else r[1] < limit)], key=lambda r: -r[1])
        jarvis_say(f"{len(rows):,} file(s) {'over' if bigger else 'under'} {human(limit)} in {scope_txt}, sir.")
        jv_rows(rows, base)
        CONTESTO["jlist"] = [r[0] for r in rows[:200]]
        return True

    # recently modified
    mt, vague = None, False
    if h(r"\bmodified\b", r"\bchanged\b", r"\bupdated\b", r"\bcreated\b", r"\bmodificat\w*\b", r"\bnew files\b", r"\brecent\w*\b"):
        now = time.time()
        lt = time.localtime()
        midnight = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
        mm = re.search(r"\b(?:last|past|ultim[ie])\s+(\d+)\s+(hours?|ore|days?|giorni|weeks?|settimane|months?|mesi|minutes?|minuti)\b", t)
        if mm:
            unit = mm.group(2)
            secs = 3600 if unit.startswith(("hour", "ore")) else 60 if unit.startswith("minut") else \
                604800 if unit.startswith(("week", "settim")) else 2592000 if unit.startswith(("month", "mes")) else 86400
            mt, label = now - int(mm.group(1)) * secs, f"in the last {mm.group(1)} {unit}"
        elif h(r"\btoday\b", r"\boggi\b"):
            mt, label = midnight, "today"
        elif h(r"\byesterday\b", r"\bieri\b"):
            mt, label = midnight - 86400, "since yesterday"
        elif h(r"\bthis week\b", r"\bquesta settimana\b"):
            mt, label = now - 7 * 86400, "in the last 7 days"
        elif h(r"\brecent\w*\b", r"\bnew files\b"):
            mt, label, vague = now - 7 * 86400, "in the last 7 days", True
    if mt is not None and (not vague or h(r"\bfiles?\b", r"\bwhat\b", r"\bwhich\b", r"\bshow\b", r"\blist\b", r"\bquali\b", r"\bcosa\b")):
        files, capped = jv_walk(base, recurse)
        rows = sorted([r for r in files if r[2] >= mt], key=lambda r: -r[2])
        jarvis_say(f"{len(rows):,} file(s) touched {label} in {scope_txt}, sir.")
        jv_rows(rows, base)
        CONTESTO["jlist"] = [r[0] for r in rows[:200]]
        return True

    # empty files / folders
    if h(r"\bempty\b", r"\bzero.?byte\b", r"\b0.?byte\b", r"\bvuot[ioe]\b"):
        if h(r"\bfolders?\b", r"\bdirector\w+\b", r"\bcartell\w+\b"):
            res = []
            for cur, ds, fs in os.walk(base, onerror=lambda e: None):
                ds[:] = [d for d in ds if not skip_dir(os.path.join(cur, d))]
                for d in ds:
                    try:
                        if not os.listdir(os.path.join(cur, d)):
                            res.append(os.path.join(cur, d))
                    except OSError:
                        pass
                if not recurse:
                    break
            jarvis_say(f"{len(res):,} empty folder(s) in {scope_txt}, sir.")
            for p in res[:25]:
                out(f"  {jv_rel(p, base)}")
            out()
        else:
            files, capped = jv_walk(base, recurse)
            rows = [r for r in files if r[1] == 0]
            jarvis_say(f"{len(rows):,} empty (0-byte) file(s) in {scope_txt}, sir.")
            jv_rows(rows, base)
            CONTESTO["jlist"] = [r[0] for r in rows[:200]]
        return True

    # breakdown by extension
    if h(r"\bby (?:extension|type)\b", r"\bfile types?\b", r"\bwhat kinds? of files\b", r"\bwhich extensions\b", r"\btipi di file\b",
         r"\bper estensione\b", r"\bbreakdown\b", r"\bextensions?\b"):
        files, capped = jv_walk(base, recurse)
        agg = {}
        for p, sz, _ in files:
            e = os.path.splitext(p)[1].lower() or "(none)"
            c, s = agg.get(e, (0, 0))
            agg[e] = (c + 1, s + sz)
        jarvis_say(f"{len(files):,} file(s) in {scope_txt}, sir, by type:")
        for e, (c, s) in sorted(agg.items(), key=lambda kv: -kv[1][0])[:15]:
            out(f"  {e.ljust(10)} {str(c).rjust(7)} file(s)  {human(s).rjust(12)}")
        if len(agg) > 15:
            out(f"  ... and {len(agg) - 15} more type(s)", GRAY)
        out()
        return True

    # rankings
    rk = re.search(r"\b(biggest|largest|heaviest|smallest|lightest|newest|latest|most recent|oldest|più grand\w*|piu grand\w*|"
                   r"più pesant\w*|più piccol\w*|più recent\w*|piu recent\w*|più vecchi\w*|piu vecchi\w*)\b", t) or \
        re.search(r"\b(last modified|recently modified|ultim\w+ modific\w+)\b", t)
    if rk and h(r"\bfiles?\b", r"\bfolders?\b", r"\bcartell\w+\b", r"\bdirector\w+\b", r"\bitems?\b"):
        w = rk.group(1)
        mn = re.search(r"\b(?:top\s+)?(\d{1,2})\b", t)
        n = int(mn.group(1)) if mn else 5
        if h(r"\bfolders?\b", r"\bcartell\w+\b", r"\bdirector\w+\b") and not h(r"\bfiles?\b"):
            try:
                subs = [os.path.join(base, d) for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))
                        and not skip_dir(os.path.join(base, d))]
            except OSError:
                subs = []
            sized = []
            try:
                for d in subs:
                    sized.append((d,) + count_folder(d)[:3])
            except KeyboardInterrupt:
                jarvis_say("Stopped, sir. The list is partial.")
            small = w in ("smallest", "lightest", "più piccol", "più piccolo")
            sized.sort(key=lambda r: r[3], reverse=small)
            if not sized:
                jarvis_say("There are no sub-folders here, sir.")
                return True
            jarvis_say(f"{'Smallest' if small else 'Biggest'} sub-folders of {where}, sir:")
            for d, nf, nd, sz in (sized if small else sized[:n])[:n]:
                out(f"  {human(sz).rjust(11)}  {nf:,} file(s)  {jv_rel(d, base)}")
            out()
            CONTESTO["jlist"] = [r[0] for r in sized[:n]]
            return True
        files, capped = jv_walk(base, recurse)
        if not files:
            jarvis_say(f"There are no files in {scope_txt}, sir.")
            return True
        if re.match(r"(biggest|largest|heaviest|più grand|piu grand|più pesant)", w):
            rows, what = sorted(files, key=lambda r: -r[1]), "Biggest"
        elif re.match(r"(smallest|lightest|più piccol)", w):
            rows, what = sorted(files, key=lambda r: r[1]), "Smallest"
        elif re.match(r"(oldest|più vecchi|piu vecchi)", w):
            rows, what = sorted(files, key=lambda r: r[2]), "Oldest"
        else:
            rows, what = sorted(files, key=lambda r: -r[2]), "Newest"
        top = rows[0]
        jarvis_say(f"{what}: {jv_rel(top[0], base)}, {human(top[1])}, {datetime.fromtimestamp(top[2]).strftime('%d/%m/%Y %H:%M')}"
                   f" (out of {len(files):,} file(s) in {scope_txt}).")
        if n > 1:
            jv_rows(rows[:n], base, n)
        CONTESTO["jlist"] = [r[0] for r in rows[:max(n, 5)]]
        return True

    # counts
    if h(r"\bhow many\b.*\b(?:files?|folders?|director\w+|dirs?|items?|elements?|subfolders?)\b", r"\bnumber of (?:files?|folders?|items?)\b",
         r"\bquant[ie]\s+(?:file|cartell\w+|element\w+|oggett\w+)\b"):
        if CONTESTO.get("file") and not explicit_dir and not h(r"\b(?:here|qui|folder|director\w+|cartell\w+|dir)\b"):
            return False                      # keep the old behaviour: a selected file gets its pluton report
        try:
            names = os.listdir(base)
        except OSError as e:
            jarvis_say(f"I can't read {where}, sir ({e.strerror}).")
            return True
        nf = sum(1 for n in names if os.path.isfile(os.path.join(base, n)))
        nd = sum(1 for n in names if os.path.isdir(os.path.join(base, n)))
        files, dirs, size, capped = count_folder(base)
        jarvis_say(f"{where.capitalize()} holds {nf:,} file(s) and {nd:,} folder(s) directly. Counting everything below: "
                   f"{files:,}{'+' if capped else ''} file(s) in {dirs:,} folder(s), {human(size)} in total.")
        return True

    # total size of a folder
    if h(r"\b(?:how big|how large|how much (?:space|disk)|total size|size of|weigh|weighs|quanto pesa|quanto spazio|dimensione|peso)\b") \
            and (explicit_dir or h(r"\b(?:folder|director\w+|cartella|here|qui)\b")):
        files, dirs, size, capped = count_folder(base)
        jarvis_say(f"{where.capitalize()} weighs {human(size)}{'+' if capped else ''}: {files:,} file(s) in {dirs:,} folder(s), sir.")
        return True

    if h(r"\bhidden\b", r"\bnascost\w+\b") and h(r"\bfiles?\b", r"\bfolders?\b", r"\bwhat\b", r"\bshow\b"):
        try:
            hid = [n for n in os.listdir(base) if nascosto(os.path.join(base, n), n)]
        except OSError:
            hid = []
        jarvis_say(f"{len(hid)} hidden item(s) in {where}, sir." + (":" if hid else ""))
        for n in sorted(hid, key=str.lower)[:30]:
            out(f"  {safe(n)}")
        out()
        return True
    return False


def jv_needs_file(t):
    """Questions that only make sense about one file, asked when no file is known."""
    return bool(re.search(r"\bhow many (?:lines?|words?|characters?|chars?|righe|parole|caratteri)\b|\b(?:first|last|top|head|tail|primi|ultim[ei])"
                          r"\s+\d*\s*(?:lines?|righe)\b|\bencoding\b|\bdimensions?\b|\bhow many pages\b|\bhex(?:dump)?\b|\bcolumns? of\b"
                          r"|\bwhich (?:keys|tables)\b|\bwhat game is\b", t))


def _jv_deep(orig, t, sel):
    if jv_selection(orig, t, sel) or jv_open_request(orig, t, sel) or jv_navigate(orig, t):
        return True
    if jv_examples(t) or jv_global(t):
        return True
    path, explicit = jv_target(orig, t, sel)
    if not explicit:
        missing = [k for k in jv_filename_tokens(orig) if not os.path.exists(os.path.expanduser(k))
                   and not (k.lower() == GM_FILE and re.match(r"(?:find|search|locate|where|trova|cerca|dov)", t))]
        if missing:
            jarvis_say(f"I can't find '{safe(missing[0])}', sir: not in this folder nor in the three levels below it.")
            close = difflib.get_close_matches(missing[0].lower(), [n.lower() for n in os.listdir(".")], n=3, cutoff=0.5)
            if close:
                jarvis_say("Did you mean: " + ", ".join(safe(n) for n in close) + "?")
            return True
    if path is None:
        if jv_needs_file(t):
            jarvis_say("Which file, sir? Say 'open <file>' first, or name it in the question.")
            show_file_choices()
            return True
        return jv_folder_q(orig, t, ".", False)
    if os.path.isfile(path):
        if jv_file_q(orig, t, path, explicit):
            return True
        if jv_folder_q(orig, t, ".", False):
            return True
        if explicit:                                        # a named file with a generic request
            if re.search(r"\b(?:describe|summar\w*|overview|riassum\w*|panoramica|everything about|tutto su)\b", t):
                extract_port([path])
                interact_port([path])
                return True
            if re.search(r"\b(?:battery|batteria|memory|memoria|ram|resources|consum\w*|usage)\b", t):
                pluton_key([path] + (["-Watch", "60"] if re.search(r"\b(?:watch|monitor|track|measure|misura)\b", t) else []))
                return True
            if re.search(r"\b(?:inside|content|contents|preview|look in|what'?s in|dentro|contenuto|show)\b", t):
                interact_port([path])
                return True
            if re.search(r"\b(?:info|inspect|detail|details|metadata|tell me about|about|analy\w*|extract|informazion\w*|dettagli)\b", t):
                extract_port([path])
                return True
        return False
    return jv_folder_q(orig, t, path, True)                 # an explicit folder


def jv_deep(orig, t, sel):
    """Entry point of the deep layer; never lets an unexpected error kill the shell."""
    try:
        return _jv_deep(orig, t, sel)
    except KeyboardInterrupt:
        out()
        jarvis_say("Stopped, sir.")
        return True
    except Exception as e:
        jarvis_say(f"I ran into trouble with that, sir: {safe(e)}")
        return True


# the word 'jarvis' on its own (not inside jarvis.py, jarvis_update, a path...)
JV_NAMED_RE = r"(?<![\w./\\-])jarvis(?![\w/\\-]|\.\w)"
JV_NOT_NAMED_CMDS = ("jarvis", "implement", "implement-jarvis", "maintenance", "help", "get-help", "man", "exit", "quit")


# >>>>> JARVIS-PART 11_brain_smalltalk.py >>>>>
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


# >>>>> JARVIS-PART 12_extract_key_local_ai.py >>>>>
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


# >>>>> JARVIS-PART 13_online_research.py >>>>>
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


# >>>>> JARVIS-PART 14_news.py >>>>>
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


# >>>>> JARVIS-PART 15_multi_intent_selfcheck.py >>>>>
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


# >>>>> JARVIS-PART 16_update_engine.py >>>>>
# ---------------- paths, log ----------------
def jv_upd_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis_update")


def jv_upd_sub(name):
    d = os.path.join(jv_upd_dir(), name)
    os.makedirs(d, exist_ok=True)
    return d


def jv_upd_clean(text, limit=300):
    """One safe line: no line breaks, escape codes or hidden characters (nothing can fake a log entry)."""
    t = JV_UPD_HIDDEN.sub(" ", str(text))
    t = "".join(c if c.isprintable() else " " for c in t)
    return re.sub(r"\s+", " ", t).strip()[:limit]


def jv_upd_log(msg):
    try:
        path = os.path.join(jv_upd_sub("."), "update.log")
        if os.path.isfile(path) and os.path.getsize(path) > 1_000_000:
            os.replace(path, path + ".1")          # one old generation is kept, the log never grows without limit
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {jv_upd_clean(msg, 600)}\n")
    except OSError:
        pass


def jv_upd_safe_name(name):
    base = re.sub(r"[^\w.\-]", "_", os.path.basename(name))[:60] or "update.py"
    return base if base.lower().endswith(".py") else base + ".py"


# ---------------- the data block ----------------
def jv_upd_data_block(src):
    """(error, data): the JV_DATA block of a Jarvis source, checked strictly."""
    import ast
    begin = [m for m in re.finditer(r"^# JV_DATA_BEGIN[ \t]*\r?$", src, re.M)]
    end = [m for m in re.finditer(r"^# JV_DATA_END[ \t]*\r?$", src, re.M)]
    if len(begin) != 1 or len(end) != 1 or begin[0].end() > end[0].start():
        return "the JV_DATA block is missing or not unique", None
    inner = src[begin[0].end():end[0].start()].strip()
    try:
        mod = ast.parse(inner)
        ok = (len(mod.body) == 1 and isinstance(mod.body[0], ast.Assign)
              and len(mod.body[0].targets) == 1 and isinstance(mod.body[0].targets[0], ast.Name)
              and mod.body[0].targets[0].id == "JV_DATA")
        if not ok:
            return "the JV_DATA block must be exactly one assignment", None
        data = ast.literal_eval(mod.body[0].value)
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        return "the JV_DATA block is not a plain literal", None
    if (not isinstance(data, dict) or set(data) != {"version", "game_dirs", "updated"}
            or not isinstance(data["version"], int) or isinstance(data["version"], bool)
            or not 1 <= data["version"] <= 1000000
            or not isinstance(data["updated"], str) or len(data["updated"]) > 40
            or not isinstance(data["game_dirs"], list) or len(data["game_dirs"]) > 100):
        return "the JV_DATA block has the wrong shape (version, game_dirs, updated)", None
    for d in data["game_dirs"]:
        if not isinstance(d, str) or not d or len(d) > 400 or "\n" in d or "\x00" in d:
            return "the JV_DATA block has an invalid game folder", None
    return None, data


# ---------------- security scan ----------------
def jv_upd_scan(tree):
    """Violations found outside the protected updater/launcher code. A safety net against mistakes
    and clumsy code, NOT a guarantee against deliberately hostile code. It follows aliases
    (import os as o / x = os.remove), catches dangerous functions even when only mentioned, and blocks the
    usual ways out of a checker (dunder tricks, dynamic getattr, sys.modules, writes through Path.open)."""
    import ast
    found = []
    seen = set()

    def dotted(n, alias):
        parts = []
        while isinstance(n, ast.Attribute):
            parts.append(n.attr)
            n = n.value
        if isinstance(n, ast.Name):
            parts.append(alias.get(n.id, n.id))
            return ".".join(reversed(parts))
        return None

    def flag(owner, node, key, text):
        if (owner, key) in JV_UPD_ALLOW:
            return
        tag = (owner, key, getattr(node, "lineno", 0))
        if tag not in seen:
            seen.add(tag)
            found.append(f"line {getattr(node, 'lineno', '?')}: {text} (in {owner})")

    alias = {}
    for node in ast.walk(tree):                              # pass 1, whole file: who is called what
        if isinstance(node, ast.Import):
            for a_ in node.names:
                if a_.asname:
                    alias[a_.asname] = a_.name
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            v = dotted(node.value, alias) if isinstance(node.value, (ast.Name, ast.Attribute)) else None
            if v and v.split(".")[0] in JV_UPD_ALIAS_ROOTS:
                alias[node.targets[0].id] = v
    for top in tree.body:
        owner = top.name if isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else "<module>"
        if owner.startswith(JV_UPD_PROTECTED):
            continue
        nodes = list(ast.walk(top))
        callfuncs = {id(n.func) for n in nodes if isinstance(n, ast.Call)}
        for node in nodes:                                   # pass 2: what is done
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.ImportFrom) and node.level:
                    flag(owner, node, "relative-import", "relative import")
                    continue
                mods = [a_.name for a_ in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                for m in mods:
                    root = m.split(".")[0]
                    if root in JV_UPD_NET:
                        flag(owner, node, root, f"network module '{root}'")
                    elif root in JV_UPD_DYNAMIC:
                        flag(owner, node, root, f"dynamic-code module '{root}'")
                    elif root in ("ctypes", "socket"):
                        flag(owner, node, root, f"import of '{root}'")
                    elif isinstance(node, ast.ImportFrom) and root in ("os", "shutil", "subprocess", "runpy", "sqlite3"):
                        flag(owner, node, root, f"'from {root} import ...'")
            elif isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name):
                    base = alias.get(node.value.id, node.value.id)
                    if base == "ctypes":
                        flag(owner, node, "ctypes", "use of ctypes")
                    elif base == "socket" and node.attr != "gethostname":
                        flag(owner, node, "socket", f"socket.{node.attr}")
                if node.attr in JV_UPD_BAD_DUNDERS:
                    flag(owner, node, node.attr, f"use of .{node.attr}")
                name = dotted(node, alias)
                if name in JV_UPD_BAD_SYS:
                    flag(owner, node, name, f"use of {name}")
                elif name in JV_UPD_BAD_CALLS and id(node) not in callfuncs:
                    flag(owner, node, name, f"{name} passed around without being called here")
            elif isinstance(node, ast.Subscript):
                if isinstance(node.ctx, (ast.Store, ast.Del)) and dotted(node.value, alias) == "os.environ":
                    flag(owner, node, "os.environ", "change of os.environ")
            elif isinstance(node, ast.Call):
                f = node.func
                name = dotted(f, alias)
                if isinstance(f, ast.Name) and f.id in JV_UPD_BAD_BUILTINS:
                    flag(owner, node, f.id, f"{f.id}()")
                if isinstance(f, ast.Name) and f.id in ("getattr", "setattr", "delattr"):
                    if node.args and isinstance(node.args[0], ast.Name) \
                            and alias.get(node.args[0].id, node.args[0].id).split(".")[0] in JV_UPD_MODULES:
                        flag(owner, node, "getattr", f"{f.id}() on module '{node.args[0].id}'")
                    if len(node.args) > 1:
                        an = node.args[1]
                        if not (isinstance(an, ast.Constant) and isinstance(an.value, str)):
                            flag(owner, node, "getattr-dynamic", f"{f.id}() with a computed attribute name")
                        elif an.value in JV_UPD_BAD_ATTRS or an.value in JV_UPD_BAD_DUNDERS:
                            flag(owner, node, "getattr-bad", f"{f.id}() reaching for '{an.value}'")
                for kw in node.keywords:
                    if kw.arg == "shell" and not (isinstance(kw.value, ast.Constant) and kw.value.value is False):
                        flag(owner, node, "shell", "shell=...")
                if name in JV_UPD_OPENERS:
                    mode = node.args[1] if len(node.args) > 1 else None
                    for kw in node.keywords:
                        if kw.arg == "mode":
                            mode = kw.value
                    if mode is not None:
                        if not (isinstance(mode, ast.Constant) and isinstance(mode.value, str)):
                            flag(owner, node, "open-mode", f"{name}() with a non-literal mode")
                        elif any(c in mode.value for c in "wax+"):
                            flag(owner, node, "open-write", f"{name}() opened for writing")
                elif isinstance(f, ast.Attribute) and f.attr == "open":          # Path.open('w'), anything.open(mode=...)
                    mode = None
                    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str) \
                            and re.fullmatch(r"[rwxabt+U]{1,4}", node.args[0].value):
                        mode = node.args[0]
                    for kw in node.keywords:
                        if kw.arg == "mode":
                            mode = kw.value
                    if mode is not None:
                        if not (isinstance(mode, ast.Constant) and isinstance(mode.value, str)):
                            flag(owner, node, "open-mode", ".open() with a non-literal mode")
                        elif any(c in mode.value for c in "wax+"):
                            flag(owner, node, "open-write", ".open() opened for writing")
                if name in JV_UPD_BAD_CALLS:
                    if name == "os.system" and node.args and isinstance(node.args[0], ast.Constant) \
                            and node.args[0].value == "":
                        pass
                    else:
                        flag(owner, node, name, f"{name}()")
                elif name and name.startswith(JV_UPD_BAD_PREFIX):
                    flag(owner, node, name, f"{name}()")
                if isinstance(f, ast.Attribute) and f.attr in JV_UPD_BAD_METHODS:
                    flag(owner, node, "." + f.attr, f".{f.attr}()")
            elif isinstance(node, ast.Name) and node.id in ("__builtins__", "__loader__", "__spec__"):
                flag(owner, node, node.id, f"use of {node.id}")
    return found


def jv_upd_protected(tree):
    """name -> syntax-tree dump of every protected function / class / constant."""
    import ast
    res = {}
    for top in tree.body:
        if isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and top.name.startswith(JV_UPD_PROTECTED):
            res[top.name] = ast.dump(top)
        elif isinstance(top, (ast.Assign, ast.AnnAssign)):
            tgts = top.targets if isinstance(top, ast.Assign) else [top.target]
            for t in tgts:
                if isinstance(t, ast.Name) and t.id.startswith(JV_UPD_PROTECTED_CONST):
                    res[t.id] = ast.dump(top)
    return res


def jv_upd_cmds(tree):
    """(every name+alias lowercased, canonical names) of the @cmdlet(...) commands of a source."""
    import ast
    names, canon = set(), []
    for top in ast.walk(tree):
        if isinstance(top, ast.FunctionDef):
            for d in top.decorator_list:
                if isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "cmdlet":
                    vals = [a.value for a in d.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
                    names.update(v.lower() for v in vals)
                    if vals:
                        canon.append(vals[0])
    return names, canon


# ---------------- running a candidate in a throw-away folder ----------------
def jv_upd_run(path, cwd, stdin_text, limit=20):
    import subprocess
    env = {k: v for k, v in os.environ.items() if k.upper() in JV_UPD_ENV_KEEP}      # no tokens, keys or passwords
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    t0 = time.perf_counter()
    try:
        # -I: isolated mode (ignores PYTHON* variables, the user's site folder and the script folder on the path)
        r = subprocess.run([sys.executable, "-I", "-B", "-X", "utf8", path], input=stdin_text, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=limit, cwd=cwd, env=env)
    except subprocess.TimeoutExpired:
        return None, "", f"did not finish in {limit} s", float(limit)
    except OSError as e:
        return None, "", str(e), 0.0
    return r.returncode, r.stdout, r.stderr, time.perf_counter() - t0


def jv_upd_box(title, color=None):
    """A plain ASCII panel header (looks the same in every Windows console)."""
    w = 62
    color = color or JV_SEC_G
    out("+" + "-" * (w - 2) + "+", color)
    out("| " + title[:w - 4].ljust(w - 4) + " |", color)
    out("+" + "-" * (w - 2) + "+", color)


def jv_upd_phase(i, ok, detail=""):
    name = JV_UPD_PHASES[i - 1]
    n = len(JV_UPD_PHASES)
    bar = "#" * i + "-" * (n - i)
    out(f"  {'[+]' if ok else '[!]'} [{bar}] {i}/{n} {name.ljust(15, '.')} {'PASS' if ok else 'BLOCKED'} {detail}".rstrip(),
        JV_SEC_G if ok else RED)
    return ok


def jv_upd_check(cand, want_sha, pin=None):
    """The 9 safety phases, in order. Returns (ok, phase name, reason). Installs nothing."""
    import ast
    import tempfile
    me = os.path.abspath(__file__)

    def bad(i, why):
        jv_upd_phase(i, False, why)
        return False, JV_UPD_PHASES[i - 1], why

    # 1 - valid source
    try:
        if not stat.S_ISREG(os.lstat(cand).st_mode):
            return bad(1, "not a plain file (a link, pipe or device)")
        with open(cand, "rb") as f:
            raw = f.read(JV_UPD_MAX_BYTES + 1)
    except OSError as e:
        return bad(1, f"cannot read it ({e.strerror})")
    if not raw or len(raw) > JV_UPD_MAX_BYTES:
        return bad(1, "empty or bigger than 4 MB")
    if b"\x00" in raw:
        return bad(1, "contains binary data")
    try:
        src = raw.decode("utf-8")
    except UnicodeDecodeError:
        return bad(1, "not valid UTF-8 text")
    hid = JV_UPD_HIDDEN.search(src[1:] if src.startswith("\ufeff") else src)
    if hid:
        return bad(1, f"hidden or direction-changing character U+{ord(hid.group()):04X} in the text")
    if "def main(" not in src or "__main__" not in src:
        return bad(1, "not a Jarvis program (no main)")
    jv_upd_phase(1, True, human(len(raw)))
    # 2 - checksum
    digest = hashlib.sha256(raw).hexdigest()
    if pin and digest != pin.lower():
        return bad(2, "the file changed after it was staged")
    if want_sha:
        if digest != want_sha.lower():
            return bad(2, f"sha256 is {digest[:16]}..., expected {want_sha.lower()[:16]}...")
        jv_upd_phase(2, True, "matches the one you gave")
    else:
        jv_upd_phase(2, True, f"none given, sha256 {digest[:16]}...")
    # 3 - syntax
    try:
        tree = ast.parse(src, "<update>")
        compile(tree, "<update>", "exec")
    except (SyntaxError, ValueError, RecursionError, MemoryError) as e:
        return bad(3, f"line {getattr(e, 'lineno', '?')}: {e}")
    jv_upd_phase(3, True)
    # 4 - data block
    err, data = jv_upd_data_block(src)
    if err:
        return bad(4, err)
    jv_upd_phase(4, True, f"data v{data['version']}, {len(data['game_dirs'])} game folder(s)")
    # 5 - security scan
    found = jv_upd_scan(tree)
    if found:
        return bad(5, f"{len(found)} violation(s), first: {found[0]}")
    jv_upd_phase(5, True, "0 violations")
    # 6 - the updater / launcher code is untouched
    try:
        with open(me, encoding="utf-8") as f:
            cur_src = f.read()
        cur_tree = ast.parse(cur_src)
    except (OSError, SyntaxError, UnicodeDecodeError):
        return bad(6, "cannot read the running Jarvis to compare")
    a, b = jv_upd_protected(cur_tree), jv_upd_protected(tree)
    if a != b:
        diff = sorted({k for k in set(a) | set(b) if a.get(k) != b.get(k)})
        return bad(6, "changed or missing: " + ", ".join(diff[:4]))
    jv_upd_phase(6, True, f"{len(a)} protected item(s) identical")
    # 7 - every command of today is still there
    cur_names, cur_canon = jv_upd_cmds(cur_tree)
    new_names, _ = jv_upd_cmds(tree)
    gone = sorted(cur_names - new_names)
    if gone:
        return bad(7, "missing: " + ", ".join(gone[:6]))
    jv_upd_phase(7, True, f"{len(cur_names)} names kept, {len(new_names - cur_names)} new")
    # 8 + 9 - start it for real in a disposable folder, and compare the speed
    with tempfile.TemporaryDirectory(prefix="jarvis_test_") as tmp:
        dirs = {}
        for tag, text in (("new", src), ("old", cur_src)):
            dirs[tag] = os.path.join(tmp, tag)
            os.makedirs(dirs[tag])
            with open(os.path.join(dirs[tag], "pwsh.py"), "w", encoding="utf-8", newline="") as f:
                f.write(text)
        script = {k: os.path.join(v, "pwsh.py") for k, v in dirs.items()}
        rc, so, se, t_new = jv_upd_run(script["new"], dirs["new"], "Get-Command\nexit\n")
        if rc != 0:
            return bad(8, f"exit code {rc}: {(se or so).strip().splitlines()[-1][:120] if (se or so).strip() else 'no output'}")
        if "Traceback" in so or "Traceback" in se:
            return bad(8, "it printed a Python error on start")
        if "Jarvis PowerShell" not in so:
            return bad(8, "it did not show the usual start screen")
        miss = [c for c in cur_canon if c not in so]
        if miss:
            return bad(8, "commands not listed by Get-Command: " + ", ".join(miss[:4]))
        jv_upd_phase(8, True, f"started and closed cleanly in {t_new:.2f} s")
        times_new, times_old = [t_new], []
        rc2, _, _, t2 = jv_upd_run(script["new"], dirs["new"], "exit\n")
        if rc2 == 0:
            times_new.append(t2)
        for _ in range(2):
            rc3, _, _, t3 = jv_upd_run(script["old"], dirs["old"], "exit\n")
            if rc3 == 0:
                times_old.append(t3)
        if times_old and min(times_new) > min(times_old) * 1.5 + 0.75:
            return bad(9, f"{min(times_new):.2f} s against {min(times_old):.2f} s of the current version")
        jv_upd_phase(9, True, f"{min(times_new):.2f} s (current: {min(times_old):.2f} s)" if times_old else "")
    return True, "", ""


# ---------------- sources ----------------
def jv_upd_fetch(url):
    """Download a source (https only, also after redirects; TLS 1.2 or newer; plain http only for this computer).
    Returns bytes or raises ValueError."""
    import ssl
    import urllib.error
    import urllib.parse
    import urllib.request
    p = urllib.parse.urlparse(url)
    here = ("localhost", "127.0.0.1", "::1")
    local = (p.hostname or "") in here
    if p.scheme != "https" and not (p.scheme == "http" and local):
        raise ValueError("only https:// links are accepted")

    class Strict(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            q = urllib.parse.urlparse(newurl)
            if q.scheme != "https" and not (q.scheme == "http" and local and (q.hostname or "") in here):
                raise urllib.error.HTTPError(newurl, code, "redirect to a non-https address refused", headers, fp)
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    ctx = ssl.create_default_context()
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    opener = urllib.request.build_opener(Strict, urllib.request.HTTPSHandler(context=ctx))
    req = urllib.request.Request(url, headers={"User-Agent": "JARVIS-updater"})
    try:
        with opener.open(req, timeout=15) as r:
            data = r.read(JV_UPD_MAX_BYTES + 1)
    except OSError as e:
        raise ValueError(f"download failed ({e})")
    if len(data) > JV_UPD_MAX_BYTES:
        raise ValueError("the download is bigger than 4 MB")
    return data


def jv_upd_stage(raw, name):
    """Put the candidate in jarvis_update/work/ (the checks always run on this private copy)."""
    base = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{jv_upd_safe_name(name)}"
    for n in range(100):
        path = os.path.join(jv_upd_sub("work"), base if n == 0 else f"{n}_{base}")
        try:
            with open(path, "xb") as f:          # exclusive: never writes through an existing file or link
                f.write(raw)
            return path
        except FileExistsError:
            continue
    raise OSError("cannot make a private copy of the update")


def jv_upd_build_maintenance(cur_src, cur_data):
    """A maintenance build: the current program with a fresh JV_DATA block. Returns (bytes, summary) or (None, why)."""
    dirs = []
    for p in find_named(game_locations(), GM_FILE, 6):
        d = os.path.dirname(os.path.abspath(p))
        if d not in dirs:
            dirs.append(d)
    for d in cur_data.get("game_dirs", []):
        if os.path.isdir(d) and d not in dirs:
            dirs.append(d)
    dirs = dirs[:100]
    if dirs == cur_data.get("game_dirs"):
        return None, "already up to date"
    data = {"version": int(cur_data.get("version", 0)) + 1, "game_dirs": dirs,
            "updated": datetime.now().strftime("%Y-%m-%d %H:%M")}
    begin = re.search(r"^# JV_DATA_BEGIN[ \t]*\r?$", cur_src, re.M)
    end = re.search(r"^# JV_DATA_END[ \t]*\r?$", cur_src, re.M)
    if not begin or not end:
        return None, "the running file has no data block"
    new = cur_src[:begin.end()] + "\nJV_DATA = " + repr(data) + "\n" + cur_src[end.start():]
    return new.encode("utf-8"), f"{len(dirs)} game folder(s) learned from this PC"


# ---------------- install / reject ----------------
def jv_upd_sha_of(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def jv_upd_install(cand, pin=None):
    """Backup the running file, put the candidate in its place, roll back on any trouble. Returns the backup path.
    With pin (the SHA-256 seen by the checks) it refuses a file that changed after the checks."""
    me = os.path.abspath(__file__)
    if pin and jv_upd_sha_of(cand) != pin.lower():
        raise OSError("the update changed after it was checked, nothing was installed")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = os.path.join(jv_upd_sub("backups"), f"{os.path.splitext(os.path.basename(me))[0]}_{stamp}.py")
    shutil.copy2(me, backup)
    if jv_upd_sha_of(backup) != jv_upd_sha_of(me):
        os.remove(backup)
        raise OSError("the backup is not identical to the original, nothing was changed")
    want = jv_upd_sha_of(cand)
    tmp = me + ".jvnew"
    try:
        with open(cand, "rb") as s_, open(tmp, "wb") as d_:
            shutil.copyfileobj(s_, d_)
            d_.flush()
            os.fsync(d_.fileno())              # on the disk before it replaces the running file
        if jv_upd_sha_of(tmp) != want:
            raise OSError("the new file was not copied correctly")
        os.replace(tmp, me)
        if jv_upd_sha_of(me) != want:
            raise OSError("the installed file does not match")
    except Exception:
        try:
            shutil.copyfile(backup, tmp)
            os.replace(tmp, me)
        except OSError:
            pass
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        raise
    return backup


def jv_upd_discard(*paths):
    n = 0
    for p in paths:
        if p and os.path.isfile(p):
            try:
                os.remove(p)
                n += 1
            except OSError:
                pass
    return n


def jv_upd_quarantine(work, incoming, why):
    dest = os.path.join(jv_upd_sub("rejected"), os.path.basename(work))
    shutil.move(work, dest)
    try:
        with open(dest + ".reason.txt", "w", encoding="utf-8") as f:
            f.write(why + "\n")
    except OSError:
        pass
    jv_upd_discard(incoming)
    return dest


def jv_upd_readline(deadline):
    """One typed line, or None when the time is up (or the input is closed)."""
    if os.name == "nt":
        import msvcrt
        buf = ""
        while time.time() < deadline:
            if msvcrt.kbhit():
                ch = msvcrt.getwch()
                if ch in ("\r", "\n"):
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    return buf
                if ch == "\x03":
                    raise KeyboardInterrupt
                if ch == "\x08":
                    if buf:
                        buf = buf[:-1]
                        sys.stdout.write("\b \b")
                elif ch >= " ":
                    buf += ch
                    sys.stdout.write(ch)
                sys.stdout.flush()
            else:
                time.sleep(0.05)
        return None
    import select
    left = deadline - time.time()
    if left <= 0:
        return None
    try:
        ready = select.select([sys.stdin], [], [], left)[0]
    except (OSError, ValueError):
        return None
    if not ready:
        return None
    line = sys.stdin.readline()
    return None if line == "" else line.rstrip("\r\n")


def jv_upd_restart(fresh_window):
    """Start Jarvis again from the file on disk. Does not return."""
    me = os.path.abspath(__file__)
    sys.stdout.write("\x1b[0m\x1b[2J\x1b[H")
    sys.stdout.flush()
    if os.name == "nt":
        import subprocess
        if fresh_window:
            subprocess.Popen([sys.executable, me], creationflags=0x10, cwd=os.path.dirname(me))   # CREATE_NEW_CONSOLE
            raise SystemExit(0)
        raise SystemExit(subprocess.call([sys.executable, me], cwd=os.getcwd()))
    if fresh_window:
        os.chdir(os.path.dirname(me))
    os.execv(sys.executable, [sys.executable, me])


def jv_upd_countdown(work, incoming, why):
    """Refused update: 'delete' within the time keeps the window and deletes it; silence closes this session."""
    out()
    jv_upd_box("SECURITY GATE // PATCH BLOCKED", RED)
    out(f"[!] UPDATE REFUSED: {why}", RED)
    out("Nothing was installed and Jarvis is untouched.", GRAY)
    out(f"Type  delete  within {JV_UPD_SECONDS} seconds to throw the update away and keep this window.", YELLOW)
    out("No answer: this window closes, the update goes to quarantine and a fresh, intact Jarvis opens.", YELLOW)
    deadline = time.time() + JV_UPD_SECONDS
    while True:
        line = jv_upd_readline(deadline)
        if line is None:
            break
        if line.strip().lower() == "delete":
            n = jv_upd_discard(work, incoming)
            jv_upd_log(f"REFUSED and DELETED by the user: {why}")
            out(f"Update deleted ({n} file(s)). This window stays open.", GREEN)
            out()
            return
        out(f"'{safe(line.strip())}' is not 'delete'. {max(0, int(deadline - time.time()))} s left.", YELLOW)
    try:
        dest = jv_upd_quarantine(work, incoming, why)
    except OSError:
        dest = "(could not move it)"
    jv_upd_log(f"REFUSED, no answer, quarantined at {dest}: {why}")
    out(f"No answer. Quarantined: {safe(dest)}", RED)
    out("Closing this session and opening a fresh Jarvis...", RED)
    jv_upd_restart(True)


def jv_upd_changes(old_src, new_src):
    """What really differs between two versions, computed from the two sources (nothing is guessed)."""
    import ast
    diff = [l for l in difflib.unified_diff(old_src.splitlines(), new_src.splitlines(), lineterm="", n=0)
            if l[:1] in "+-" and not l.startswith(("+++", "---"))]
    add = sum(1 for l in diff if l[0] == "+")
    rem = len(diff) - add
    if not diff:
        return ["No difference at all with the previous version."]
    lines = [f"{add} line(s) added, {rem} line(s) removed."]

    def top(src):
        tree = ast.parse(src)
        d, c = {}, {}
        for n in tree.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                d[n.name] = ast.dump(n)
            elif isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
                c[n.targets[0].id] = ast.dump(n)
        return tree, d, c

    def show(label, names):
        if names:
            more = f" and {len(names) - 8} more" if len(names) > 8 else ""
            lines.append(f"{label} ({len(names)}): {', '.join(names[:8])}{more}")
    try:
        ot, od, oc = top(old_src)
        nt, nd, nc = top(new_src)
    except (SyntaxError, ValueError):
        return lines
    show("Functions/classes added", sorted(set(nd) - set(od)))
    show("Functions/classes removed", sorted(set(od) - set(nd)))
    show("Functions/classes modified", sorted(k for k in od if k in nd and od[k] != nd[k]))
    oc.pop("JV_DATA", None)
    nc.pop("JV_DATA", None)
    show("Constants added or changed", sorted(k for k in nc if oc.get(k) != nc[k]))
    show("Constants removed", sorted(set(oc) - set(nc)))
    on, _ = jv_upd_cmds(ot)
    nn, _ = jv_upd_cmds(nt)
    show("Commands added", sorted(nn - on))
    show("Commands removed", sorted(on - nn))
    e1, o_data = jv_upd_data_block(old_src)
    e2, n_data = jv_upd_data_block(new_src)
    if not e1 and not e2 and o_data != n_data:
        gone = [d for d in o_data["game_dirs"] if d not in n_data["game_dirs"]]
        new = [d for d in n_data["game_dirs"] if d not in o_data["game_dirs"]]
        lines.append(f"Data block: version {o_data['version']} -> {n_data['version']}, "
                     f"{len(new)} game folder(s) added, {len(gone)} removed.")
        for d in new[:6]:
            lines.append("  + " + d)
        for d in gone[:6]:
            lines.append("  - " + d)
    return lines


def jv_upd_save_report(label, backup):
    """Right after an install: remember what changed, for the new window to tell."""
    me = os.path.abspath(__file__)
    try:
        with open(backup, encoding="utf-8") as f:
            old = f.read()
        with open(me, encoding="utf-8") as f:
            new = f.read()
        rep = {"time": datetime.now().strftime("%Y-%m-%d %H:%M"), "source": label, "backup": backup,
               "old_sha": jv_upd_sha_of(backup), "new_sha": jv_upd_sha_of(me), "changes": jv_upd_changes(old, new)}
        with open(os.path.join(jv_upd_sub("."), "last_update.json"), "w", encoding="utf-8") as f:
            json.dump(rep, f)
    except (OSError, ValueError, UnicodeDecodeError):
        pass


def jv_upd_show_report():
    """At start: tell what the last update changed, once, and only if this file is exactly the one installed."""
    path = os.path.join(jv_upd_dir(), "last_update.json")
    if not os.path.isfile(path):
        return
    try:
        with open(path, encoding="utf-8") as f:
            rep = json.load(f)
        same = rep["new_sha"] == jv_upd_sha_of(os.path.abspath(__file__))
        lines = [str(x) for x in rep["changes"]]
    except (OSError, ValueError, KeyError, TypeError):
        jv_upd_discard(path)
        return
    jv_upd_discard(path)
    if not same:
        return
    jarvis_say(f"Update installed on {safe(rep.get('time', '?'))}. This is what really changed, sir:")
    for ln in lines:
        out("  " + safe(ln)[:200], CYAN)
    out(f"  The previous version is saved in {safe(rep.get('backup', '?'))}", GRAY)


# >>>>> JARVIS-PART 17_implement_jarvis.py >>>>>
# ---------------- implement jarvis ----------------
@cmdlet("Implement", "Implement-Jarvis", group="Assistant", usage="""implement jarvis                      update myself: maintenance build with real data from this PC (or the file waiting in jarvis_update/incoming/)
implement jarvis <file.py>           install that file as the new Jarvis
implement jarvis <https://...> -Sha256 <hash>    download it (the hash is REQUIRED), then install
implement jarvis -Dry                run all the checks, install nothing
implement jarvis -Maintenance        ignore jarvis_update/incoming/ and build the maintenance update
The 9 checks: valid source, checksum, syntax, data block, security scan, updater code intact,
every command of today still present, start test in a throw-away folder, start speed.
All passed: the old file is copied to jarvis_update/backups/, the new one is installed (automatic
rollback on any trouble) and Jarvis restarts. One failed: nothing is installed, then type  delete
within 10 seconds to discard it and keep this window; no answer = this session closes, the update goes
to jarvis_update/rejected/ and a fresh Jarvis opens.
Downloads: https only (also after redirects), TLS 1.2+, and always with -Sha256. The start test runs isolated
(python -I) with a cleaned environment. A file that changes after the checks is refused at install time.
(Only install updates from sources you trust: the scan catches mistakes, not deliberately hostile code.)""")
def jv_upd_cmd(args):
    """Update Jarvis itself: 9 safety checks, backup, automatic rollback."""
    args = list(args)
    usage = "Usage: implement jarvis [<file.py> | <https://...> -Sha256 <hash>] [-Dry] [-Maintenance]"
    if not args or args[0].lower() != "jarvis":
        out(usage, YELLOW)
        out()
        return
    dry = force_m = False
    sha = src = None
    i = 1
    while i < len(args):
        a, al = args[i], args[i].lower()
        if al in ("-dry", "-dryrun", "-whatif"):
            dry = True
        elif al == "-maintenance":
            force_m = True
        elif al in ("-sha256", "-hash"):
            i += 1
            sha = args[i] if i < len(args) else ""
        elif al.startswith("-sha256="):
            sha = a.split("=", 1)[1]
        elif src is None and not a.startswith("-"):
            src = a
        else:
            out(f"Unknown or repeated option '{safe(a)}'.", RED)
            out(usage, YELLOW)
            out()
            return
        i += 1
    if sha is not None and not re.fullmatch(r"[0-9a-fA-F]{64}", sha):
        out("-Sha256 needs the 64 hexadecimal characters of the SHA-256 hash.", RED)
        out()
        return
    is_url = bool(src and re.match(r"https?://", src, re.I))
    if is_url and not sha:
        out("Refused: a download needs  -Sha256 <hash>.  Installing code you cannot verify is like running a stranger's file.", RED)
        out()
        return
    me = os.path.abspath(__file__)
    work, incoming = None, None
    try:
        try:
            with open(me, encoding="utf-8") as f:
                cur_src = f.read()
        except (OSError, UnicodeDecodeError) as e:
            out(f"I cannot read myself ({e}). Nothing was done.", RED)
            out()
            return
        label = ""
        try:
            if is_url:
                label = src
                work = jv_upd_stage(jv_upd_fetch(src), src.rsplit("/", 1)[-1] or "download.py")
            elif src:
                path = os.path.expanduser(src)
                if not os.path.isfile(path):
                    out(f"Cannot find the update file '{safe(src)}'. Nothing was done.", RED)
                    out()
                    return
                with open(path, "rb") as f:
                    raw = f.read(JV_UPD_MAX_BYTES + 1)
                label = os.path.abspath(path)
                if not label.lower().endswith(".py"):
                    out("An update must be a .py file. Nothing was done.", RED)
                    out()
                    return
                if os.path.dirname(label) == os.path.join(jv_upd_dir(), "incoming"):
                    incoming = label
                work = jv_upd_stage(raw, path)
            else:
                inc = os.path.join(jv_upd_dir(), "incoming")
                waiting = sorted((os.path.join(inc, n) for n in os.listdir(inc) if n.lower().endswith(".py")),
                                 key=os.path.getmtime) if (not force_m and os.path.isdir(inc)) else []
                if waiting:
                    incoming = waiting[0]
                    label = incoming + "  (waiting in jarvis_update/incoming/)"
                    with open(incoming, "rb") as f:
                        work = jv_upd_stage(f.read(JV_UPD_MAX_BYTES + 1), incoming)
                else:
                    err, cur_data = jv_upd_data_block(cur_src)
                    if err:
                        out(f"I cannot build the maintenance update: {err}.", RED)
                        out()
                        return
                    out("Collecting real data from this PC for a maintenance update...", GRAY)
                    raw, note = jv_upd_build_maintenance(cur_src, cur_data)
                    if raw is None:
                        jarvis_say(f"Nothing to update, sir: {note}.")
                        out()
                        return
                    label = f"maintenance build ({note})"
                    work = jv_upd_stage(raw, "maintenance.py")
        except (OSError, ValueError) as e:
            out(f"Cannot get the update: {e}. Nothing was done.", RED)
            out()
            return
        pin = jv_upd_sha_of(work)
        out()
        jv_upd_box("SECURITY GATE // PATCH VERIFICATION")
        out(f"[*] source : {safe(label)}", JV_SEC_D)
        out(f"[*] running the {len(JV_UPD_PHASES)} safety checks (a single failure blocks the patch)", JV_SEC_D)
        ok, phase, why = jv_upd_check(work, sha, pin)
        if not ok:
            if dry:
                out(f"Dry run: this update would be REFUSED at '{phase}'. Nothing was installed.", RED)
                out()
                return
            jv_upd_countdown(work, incoming, f"check '{phase}' failed: {why}")
            work = None
            return
        if dry:
            out(f"[+] PATCH VERIFIED {len(JV_UPD_PHASES)}/{len(JV_UPD_PHASES)} gates passed", JV_SEC_G)
            out(f"Dry run: all {len(JV_UPD_PHASES)} checks passed. Nothing was installed.", GREEN)
            out()
            return
        try:
            backup = jv_upd_install(work, pin)
        except OSError as e:
            jv_upd_log(f"INSTALL FAILED, rolled back: {e}")
            out(f"The installation failed and the old version is back in place: {e}", RED)
            out()
            return
        jv_upd_log(f"INSTALLED {label}; backup {backup}")
        jv_upd_save_report(label, backup)
        jv_upd_discard(work, incoming)
        work = None
        out()
        out(f"[+] PATCH VERIFIED {len(JV_UPD_PHASES)}/{len(JV_UPD_PHASES)} gates passed", JV_SEC_G)
        out("All checks passed. The new version is installed.", GREEN)
        out(f"Backup of the old version: {safe(backup)}", GRAY)
        out("Restarting Jarvis with the new version...", GRAY)
        jv_upd_restart(False)
    finally:
        if work:
            jv_upd_discard(work)


# >>>>> JARVIS-PART 18_maintenance.py >>>>>
# ---------------- maintenance (read-only health check) ----------------
def jv_upd_secline():
    """One compact line about the security state of this file, or None when it cannot be read."""
    import ast
    me = os.path.abspath(__file__)
    try:
        with open(me, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        viol = len(jv_upd_scan(tree))
        prot = len(jv_upd_protected(tree))
        try:
            nb = sum(1 for n in os.listdir(os.path.join(jv_upd_dir(), "backups")) if n.lower().endswith(".py"))
        except OSError:
            nb = 0
        return (f"[{'+' if not viol else '!'}] SECURITY  scan {viol} violation(s)  |  {prot} protected  |  "
                f"{len(JV_UPD_PHASES)} patch gates armed  |  {nb} backup(s)", not viol)
    except (OSError, SyntaxError, UnicodeDecodeError):
        return None


def jv_upd_health(args):
    """Read-only security status of Jarvis (integrity, security scan, backups, log)."""
    import ast
    me = os.path.abspath(__file__)
    out()
    jv_upd_box("SECURITY STATUS // INTEGRITY REPORT  (read-only)")

    def row(ok, key, text, color=None):
        out(f"  {'[+]' if ok else '[!]'} {key.ljust(13, '.')} {text}", color or (JV_SEC_G if ok else RED))
    try:
        with open(me, encoding="utf-8") as f:
            src = f.read()
        tree = ast.parse(src)
        row(True, "PROGRAM", f"{safe(me)}")
        row(True, "FINGERPRINT", f"sha256 {jv_upd_sha_of(me)[:32]}  ({human(len(src.encode('utf-8')))})")
    except (OSError, SyntaxError, UnicodeDecodeError) as e:
        row(False, "PROGRAM", f"cannot be checked ({e})")
        out()
        return
    err, data = jv_upd_data_block(src)
    if err:
        row(False, "DATA BLOCK", err)
    else:
        alive = sum(1 for d in data["game_dirs"] if os.path.isdir(d))
        row(True, "DATA BLOCK", f"version {data['version']}, last update '{data['updated'] or 'never'}', "
                                f"{alive}/{len(data['game_dirs'])} learned game folder(s) still there")
    found = jv_upd_scan(tree)
    row(not found, "CODE SCAN", "0 violations" if not found else f"{len(found)} violation(s), first: {found[0]}")
    prot = jv_upd_protected(tree)
    row(True, "PROTECTED", f"{len(prot)} updater/launcher item(s) locked: an update that changes them is refused")
    rules = (len(JV_UPD_NET) + len(JV_UPD_DYNAMIC) + len(JV_UPD_BAD_BUILTINS) + len(JV_UPD_BAD_CALLS)
             + len(JV_UPD_BAD_METHODS) + len(JV_UPD_BAD_SYS) + len(JV_UPD_BAD_DUNDERS))
    row(True, "GUARD", f"v{JV_UPD_GUARD}: {rules} scan rules, alias tracking, hidden-character and link/pipe refusal, pinned install")
    row(True, "ISOLATION", "start test: python -I, cleaned environment, 10 s limit; downloads: https only, TLS 1.2+")
    row(True, "PATCH GATES", " > ".join(JV_UPD_PHASES))
    base = jv_upd_dir()

    def count(sub, ext=".py"):
        try:
            return sorted(n for n in os.listdir(os.path.join(base, sub)) if n.lower().endswith(ext))
        except OSError:
            return []
    backups = count("backups")
    row(bool(backups), "BACKUPS", f"{len(backups)}" + (f", newest {safe(backups[-1])}" if backups else " (made before every install)"),
        JV_SEC_G if backups else JV_SEC_A)
    row(True, "QUARANTINE", f"{len(count('rejected'))} rejected update(s)", JV_SEC_D)
    row(True, "INCOMING", f"{len(count('incoming'))} update(s) waiting", JV_SEC_D)
    try:
        with open(os.path.join(base, "update.log"), encoding="utf-8", errors="replace") as f:
            last = f.read().splitlines()[-5:]
    except OSError:
        last = []
    row(True, "LOG", "(no events yet)" if not last else "last events:", JV_SEC_D)
    for ln in last:
        out("      " + safe(ln)[:150], JV_SEC_D)
    out()


@cmdlet("Get-SecurityStatus", "security", "secstat", group="Assistant", usage="""Get-SecurityStatus     security panel: file fingerprint, code scan, protected items, patch gates, backups, quarantine, log
(read-only; alias: security)""")
def jv_upd_security_cmd(args):
    """Security panel of Jarvis (fingerprint, code scan, patch gates, backups, log)."""
    jv_upd_health([])


def jv_upd_png(truncate=False):
    """A tiny valid PNG (2 x 3 pixels), optionally cut short to make a damaged one."""
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\x10\x20\x30" * 2 for _ in range(3))
    data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 3, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    return data[:-9] if truncate else data


def jv_upd_samples(tmp):
    """Throw-away sample files used by the self-test (they live in a temporary folder that is deleted after)."""
    def w(name, text):
        with open(os.path.join(tmp, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    text = "alpha beta\ngamma delta\nalpha again\nlast line\n"
    w("a.txt", text)
    w("dup.txt", text)
    w("e.txt", "")
    w("data.csv", "name,score\nx,1\ny,3\n")
    w("data.json", json.dumps({"alpha": 1, "beta": [1, 2, 3]}))
    with zipfile.ZipFile(os.path.join(tmp, "z.zip"), "w") as z:
        z.writestr("inside.txt", "hello")
    with open(os.path.join(tmp, "p.png"), "wb") as f:
        f.write(jv_upd_png())
    with open(os.path.join(tmp, "bad.png"), "wb") as f:
        f.write(jv_upd_png(True))
    con = sqlite3.connect(os.path.join(tmp, "db.sqlite"))
    con.execute("CREATE TABLE items (id INTEGER, name TEXT)")
    con.execute("INSERT INTO items VALUES (1, 'one')")
    con.commit()
    con.close()
    os.makedirs(os.path.join(tmp, "sub"))
    body = b"GEN8" + struct.pack("<I", 60) + bytes(60) + b"SPRT" + struct.pack("<I", 4) + struct.pack("<I", 0)
    with open(os.path.join(tmp, "sub", "data.win"), "wb") as f:
        f.write(b"FORM" + struct.pack("<I", len(body)) + body)


def jv_is_maintenance(t):
    """True for 'go in maintenance', 'maintenance mode', 'manutenzione', 'test all the commands'..."""
    toks = [x.strip(",.!?;:") for x in t.split()]
    names = ["maintenance", "manutenzione"]
    has_m = any("." not in x and "/" not in x and "\\" not in x and difflib.get_close_matches(x, names, n=1, cutoff=0.78)
                for x in toks)
    starters = ("go", "enter", "switch", "put", "start", "run", "begin", "vai", "entra", "passa", "metti", "mettiti",
                "avvia", "fai", "please", "now", "ora", "can", "could", "puoi")
    if has_m and (len(toks) <= 3 or (toks and toks[0] in starters)):
        return True
    return bool(re.search(r"\b(?:test|check|verify|testa|controlla|verifica|prova)\b.*\b(?:commands?|comandi)\b", t)
                and not re.search(r"\.\w{1,5}\b", t))


def jv_upd_selftest():
    """Run every command of Jarvis once on throw-away sample files and report what works.
    Nothing outside the temporary folder is touched; no game or file is opened. Returns (passed, total)."""
    import io
    import tempfile
    snap, old_cwd = dict(CONTESTO), os.getcwd()
    CONTESTO["jv_nolog"] = True          # the test sentences must not end up in the list of misunderstood phrases
    tmp = tempfile.mkdtemp(prefix="jarvis_selftest_")
    results = []
    tag = {"n": 0}

    def run(label, fn, need=(), expect="ok", bad=(), red=False, empty=False):
        buf, old = io.StringIO(), sys.stdout
        sys.stdout = buf
        problem, exited = None, False
        try:
            fn()
        except SystemExit:
            exited = True
        except KeyboardInterrupt:
            sys.stdout = old
            raise
        except Exception as e:
            problem = f"{type(e).__name__}: {e}"
        finally:
            sys.stdout = old
        text = buf.getvalue()
        plain = re.sub(r"\x1b\[[0-9;]*m", "", text)
        if problem is None:
            if expect == "exit":
                if not exited:
                    problem = "it did not close the shell"
            elif exited:
                problem = "it closed the shell by itself"
        if problem is None and expect != "exit":
            if "Traceback" in plain or "I ran into trouble" in plain:
                problem = "internal error: " + next((l.strip() for l in plain.splitlines()
                                                     if "Traceback" in l or "I ran into trouble" in l), "")[:90]
            elif expect == "err" and RED not in text:
                problem = "no error message was shown"
            elif expect == "ok" and RED in text and not red:
                problem = "it printed an error: " + next((re.sub(r"\x1b\[[0-9;]*m", "", l).strip()
                                                          for l in text.splitlines() if RED in l), "")[:90]
            elif not plain.strip() and not empty:
                problem = "no output"
            else:
                for s in need:
                    if s not in plain:
                        problem = f"output lacks '{s}'"
                        break
                for s in bad:
                    if s in plain and problem is None:
                        problem = f"output contains '{s}'"
        if problem and problem.startswith("output "):
            seen = " / ".join(l.strip() for l in plain.splitlines() if l.strip())      # what it really answered
            problem += f"  [it said: {safe(seen)[:200] or '(nothing)'}]  [folder: {safe(os.getcwd())}]"
        tag["n"] += 1
        results.append((label, problem))
        out(f"  {'[ OK ]' if problem is None else '[FAIL]'} {label}" + (f"  -> {problem}" if problem else ""),
            GREEN if problem is None else RED)

    def cmd(name, *a):
        def f():
            CONTESTO["riga"] = name + " " + " ".join(a)
            CMDLETS[name.lower()](list(a))
        return f

    def say(text):
        def f():
            if not jarvis_interpret(text):
                raise RuntimeError("Jarvis did not understand it")
        return f

    def section(title):
        out()
        out(title, YELLOW)

    try:
        jv_upd_samples(tmp)
        os.chdir(tmp)
        CONTESTO["file"] = None
        CONTESTO["jlast"] = None
        CONTESTO.pop("jlist", None)
        sub = os.path.join(tmp, "sub")

        section("Registry")
        def registry():
            for n, fn in NOMI.items():
                if CMDLETS.get(n.lower()) is not fn:
                    raise RuntimeError(f"{n} is not registered")
                for a in ALIASES[n]:
                    if CMDLETS.get(a.lower()) is not fn:
                        raise RuntimeError(f"alias {a} of {n} is broken")
            print(f"{len(NOMI)} commands, {len(CMDLETS)} names")
        run("every command and alias is registered", registry)

        section("Integrity of the program and of what I know")
        def dupes():
            import ast
            with open(os.path.abspath(__file__), encoding="utf-8") as f:
                tree = ast.parse(f.read())
            seen, dup = {}, []
            for top in tree.body:
                if isinstance(top, (ast.FunctionDef, ast.ClassDef)):
                    if top.name in seen:
                        dup.append(top.name)
                    seen[top.name] = True
            if dup:
                raise RuntimeError("defined twice (the second hides the first): " + ", ".join(sorted(set(dup))))
            print(f"{len(seen)} top-level names, no duplicates")
        run("no function is defined twice", dupes)
        def faqself():
            bad = []
            for k, qu, a in JV_FAQ:
                hit = jv_faq_find(qu)
                if not hit or hit[1][1] != qu:
                    bad.append(qu)
                if not a.strip() or len(a) < 40:
                    bad.append("short answer: " + qu)
            if bad:
                raise RuntimeError(f"{len(bad)} entries not found by their own question: {bad[:2]}")
            print(f"{len(JV_FAQ)} how-to answers, each found by its own question")
        run("every how-to answer is found by its own question", faqself)
        def kbsane():
            keys, dup = {}, []
            for ks, txt in JV_KB:
                if len(txt) < 15:
                    raise RuntimeError(f"too short: {ks}")
                for k in ks:
                    if k in keys and keys[k] != txt:
                        dup.append(k)
                    keys[k] = txt
            for pair in JV_COMPARE:
                if len(pair) != 2:
                    raise RuntimeError(f"bad comparison {set(pair)}")
            if dup:
                raise RuntimeError("same glossary word with two meanings: " + ", ".join(sorted(set(dup))[:8]))
            print(f"{len(JV_KB)} glossary entries, {len(JV_GAMES_KB)} games, {len(JV_COMPARE)} comparisons")
        run("glossary, games and comparisons are consistent", kbsane)
        run("the list of misunderstood phrases can be shown", say("jarvis what didnt you understand"), need=["JARVIS"])
        def misslog():
            jv_didnt_catch("this sentence is a test and must not be remembered")
        run("a misunderstood sentence gets a polite reply and is not logged during tests", misslog, need=["sir"])

        section("Standard commands")
        run("Get-Location", cmd("Get-Location"), need=[tmp])
        run("Get-ChildItem", cmd("Get-ChildItem"), need=["a.txt", "data.csv", "sub"])
        run("Get-ChildItem on a missing path (must show an error)", cmd("Get-ChildItem", "nope_missing"), expect="err")
        run("Set-Location into a folder", cmd("Set-Location", "sub"), empty=True)
        run("  ...and back", cmd("Set-Location", ".."), empty=True)
        run("Set-Location on a file selects it", cmd("Set-Location", "a.txt"), need=["Selected file"])
        run("Set-Location on a missing folder (must show an error)", cmd("Set-Location", "nope_missing"), expect="err")
        CONTESTO["file"] = None
        run("Write-Output", cmd("Write-Output", "hello", "world"), need=["hello world"])
        run("Write-Host", cmd("Write-Host", "hello"), need=["hello"])
        run("Get-Content", cmd("Get-Content", "a.txt"), need=["alpha beta", "last line"])
        run("Get-Content on a missing file (must show an error)", cmd("Get-Content", "nope_missing.txt"), expect="err")
        run("Clear-Host", cmd("Clear-Host"), empty=True)
        run("Get-Command lists everything", cmd("Get-Command"), need=list(NOMI))
        run("Get-Help (full list)", cmd("Get-Help"), need=["Available commands"])
        def helps():
            for n in list(NOMI):
                CMDLETS["get-help"]([n])
        run("Get-Help <command> for every command", helps, need=["SYNTAX"])
        run("Exit closes the shell", cmd("Exit"), expect="exit", empty=True)

        section("Port tools (on sample files)")
        samples = ["a.txt", "data.csv", "data.json", "z.zip", "p.png", "db.sqlite", "e.txt", "bad.png",
                   os.path.join("sub", "data.win")]
        for s in samples:
            run(f"extract.port {s}", cmd("extract.port", s), need=["Name", "Size"], bad=["Read error"])
        for s in samples:
            run(f"interact.port {s}", cmd("interact.port", s), need=["What you can DO"], bad=["Could not read"],
                red=(s == "bad.png"))
        CONTESTO["jv_export_dir"] = os.path.join(tmp, "exports")
        run("extract.key saves a report (in the temporary folder)", cmd("extract.key", "a.txt"), need=["Report saved"])
        def keyfile():
            d = os.path.join(tmp, "exports")
            got = [n for n in os.listdir(d)] if os.path.isdir(d) else []
            if len(got) != 1:
                raise RuntimeError(f"expected one report, found {got}")
            with open(os.path.join(d, got[0]), encoding="utf-8") as f:
                body = f.read()
            for need in ("JARVIS FILE REPORT", "SHA256", "VERIFY IT YOURSELF", "alpha beta"):
                if need not in body:
                    raise RuntimeError(f"the report lacks '{need}'")
            print("ok")
        run("the report file has everything in it", keyfile)
        run("extract.key on a missing file (must show an error)", cmd("extract.key", "nope_missing"), expect="err")
        CONTESTO.pop("jv_export_dir", None)
        run("extract.port on a missing file (must show an error)", cmd("extract.port", "nope_missing"), expect="err")
        run("denux.hunter finds the damaged PNG", cmd("denux.hunter", ".", "-Recurse"), need=["bad.png", "CORRUPT"], red=True)
        run("denux.hunter on one good file", cmd("denux.hunter", "a.txt"), need=["0 corrupt"])
        run("denux.hunter on one damaged file", cmd("denux.hunter", "bad.png"), need=["CORRUPT"], red=True)
        run("undersopic.key finds the sample data.win", cmd("undersopic.key", tmp), need=["Found 1 data.win"])
        run("pluton.key", cmd("pluton.key", "a.txt"), need=["Pluton report", "FILES", "MEMORY", "BATTERY"])
        run("pluton.key -Watch 1", cmd("pluton.key", "a.txt", "-Watch", "1"), need=["Pluton report"])

        section("Jarvis, plain language (read-only questions)")
        phrases = [
            ("status", []), ("what time is it", [":"]), ("free disk space", ["free"]), ("who are you", ["JARVIS"]),
            ("thank you", []), ("examples", ["ANY FILE"]), ("what os is this", []), ("uptime", []),
            ("how many files here", ["file(s)"]), ("biggest files", ["Biggest"]), ("find all png files", ["2 file(s)"]),
            ("duplicates", ["identical"]), ("modified today", ["file(s)"]), ("by extension", [".txt"]),
            ("empty files", ["empty"]), ("files bigger than 1 byte", ["file(s)"]),
            ("select a.txt", ["Selected"]), ("how many lines", ["4 line"]), ("first 2 lines", ["alpha beta"]),
            ("last 1 lines", ["last line"]), ("search for alpha", ["2 time"]), ("sha256", ["SHA256"]),
            ("is it corrupt", ["No damage"]), ("how big is it", ["weighs"]), ("when was it modified", ["modified"]),
            ("what type is it", ["Text file"]), ("hex dump", ["61 6C"]),
            ("select data.csv", ["Selected"]), ("which columns", ["name, score"]), ("average of score", ["2"]),
            ("select data.json", ["Selected"]), ("which keys", ["alpha"]),
            ("select z.zip", ["Selected"]), ("what is inside", ["inside.txt"]),
            ("select db.sqlite", ["Selected"]), ("which tables", ["items"]), ("how many rows in items", ["1 row"]),
            ("select p.png", ["Selected"]), ("dimensions", ["2 x 3"]),
            ("select bad.png", ["Selected"]), ("is it corrupt", ["damaged"]),
            ("select e.txt", ["Selected"]), ("is it corrupt", ["empty"]),
            ("select sub/data.win", ["Selected"]), ("what game is this", ["2 chunks"]), ("how many sprites", ["0 sprites"]),
            ("list the chunks", ["GEN8", "SPRT"]), ("go up", ["Now in"]), ("read a.txt", ["alpha beta"]),
            ("what is selected", []), ("deselect", []),
            ("jarvis thats sick", ["sir"]), ("jarvis help me", ["sir"]),
            ("jarvis why does my game crash", ["overheating"]), ("jarvis how do i fix a dll not found error", ["Redistributable"]),
            ("jarvis difference between ssd and hdd", ["moving parts"]), ("jarvis zip vs rar", ["WinRAR"]),
            ("jarvis how can i free disk space", ["Disk Cleanup"]), ("jarvis is it safe to delete temp files", ["Windows recreates"]), ("jarvis ur the best", ["sir"]), ("jarvis whats your name", ["JARVIS"]), ("jarvis lol", ["sir"]),
            ("what is a vpn", ["tunnel"]), ("i want to know what a dll is", ["library"]), ("cosa significa ssd", ["solid-state"]),
            ("tell me about cry of fear", ["horror"]), ("can you calculate 12*12", ["144"]), ("jarvis ssd", ["solid-state"]),
            ("tell me about a.txt", ["SHA256"]), ("what's inside a.txt", ["First 15 lines"]),
            ("jarvis tell me about a.txt", ["SHA256"]), ("jarvis what's inside a.txt", ["First 15 lines"]),
            ("jarvis free disk space", ["free"]), ("jarvis duplicates", ["identical"]), ("jarvis by extension", [".txt"]),
        ]
        for text, need in phrases:
            run(f"jarvis: {text}", say(text), need=need)

        section("Jarvis brain (small talk, knowledge, maths, dates, typos)")
        brain = [
            ("jarvis perfect", ["JARVIS"]), ("yo big jarvis", ["JARVIS"]), ("hey jarvis how are you", ["JARVIS"]),
            ("jarvis tell me a joke", ["JARVIS"]), ("jarvis thats awesome", ["JARVIS"]), ("good night jarvis", ["sir"]),
            ("jarvis what is 15% of 80", ["= 12"]), ("jarvis calculate 2+2*3", ["= 8"]), ("jarvis what is 7 times 8", ["= 56"]),
            ("what is 5 divided by 0", ["Division by zero"]), ("jarvis square root of 144", ["= 12"]),
            ("jarvis convert 5 km to miles", ["3.10"]), ("jarvis 100 f to c", ["37.7"]), ("jarvis 2 gb in mb", ["2,048"]),
            ("jarvis how many days until christmas", ["day(s) until"]), ("jarvis what day is 25/12/2026", ["Friday"]),
            ("jarvis days between 1/1/2026 and 1/3/2026", ["59 day"]),
            ("jarvis what is a dll", ["shared library"]), ("jarvis explain sha256", ["fingerprint"]),
            ("jarvis what is a .win file", ["GameMaker"]), ("jarvis what does dir do", ["Get-ChildItem"]),
            ("jarvis tell me about undertale", ["Toby Fox"]), ("jarvis tell me about cry of fear", ["Psykskallar"]),
            ("jarvis who made you", ["Python"]), ("jarvis are you an ai", ["rule-based"]),
            ("jarvis whats the weather", ["offline"]), ("jarvis blorp zzz qqq", None),
        ]
        for text, need in brain:
            if need is None:
                run("jarvis: an unknown request gets a helpful answer", lambda: jv_didnt_catch("jarvis blorp zzz qqq"),
                    need=["didn't catch"])
            else:
                run(f"jarvis: {text}", say(text), need=need)
        def typo():
            if jv_typofix("show the biggset files") != "show the biggest files":
                raise RuntimeError("typo not repaired")
            if jv_typofix("open undertale") != "open undertale":
                raise RuntimeError("a good sentence was changed")
            print("ok")
        run("typos of my own keywords are repaired", typo)
        run("jarvis: what time is it, then 'again'", lambda: (say("jarvis what time is it")(), say("jarvis again")()),
            need=["Repeating", ":"])

        section("Maintenance wording")
        def wording():
            for yes in ("go in maintenance", "go in maintance", "maintenance mode", "jarvis maintenance".replace("jarvis ", ""),
                        "vai in manutenzione", "test all the commands", "testa tutti i comandi", "enter maintenance mode"):
                if not jv_is_maintenance(yes):
                    raise RuntimeError(f"'{yes}' is not recognised")
            for no in ("open maintenance.txt", "find my games", "how many lines", "what is the status"):
                if jv_is_maintenance(no):
                    raise RuntimeError(f"'{no}' was taken for maintenance")
            print("ok")
        run("the phrases that start maintenance mode", wording)

        section("Online mode and research")
        def online_wording():
            for yes in ("be online", "go online", "online", "vai online", "sii online", "connettiti", "boot up"):
                if jv_online_kind(yes) != "on":
                    raise RuntimeError(f"'{yes}' does not bring me online")
            for yes in ("go offline", "be offline", "offline", "disconnettiti"):
                if jv_online_kind(yes) != "off":
                    raise RuntimeError(f"'{yes}' does not take me offline")
            for no in ("open online.txt", "find my games", "how many lines", "what is online banking"):
                if jv_online_kind(no):
                    raise RuntimeError(f"'{no}' was taken for the online switch")
            print("ok")
        run("the phrases that switch online and offline", online_wording)
        def online_flow():
            CONTESTO["jv_online"] = False
            if not jarvis_interpret("jarvis research ram"):
                raise RuntimeError("Jarvis did not understand it")
            if not jarvis_interpret("jarvis be online"):
                raise RuntimeError("Jarvis did not understand it")
            if not CONTESTO.get("jv_online"):
                raise RuntimeError("I did not come online")
        run("jarvis be online (research refused while offline, then the animation)", online_flow, need=["not online", "ONLINE"])
        run("jarvis cerca ram (research summary)", say("jarvis cerca ram"), need=["Research on", "In short"])
        run("jarvis research sha256 (works with a file selected too)", say("jarvis research sha256"), need=["Research on", "In short"])
        run("jarvis cerca a topic nobody taught me", say("jarvis cerca zzzqqqxx"), need=["found nothing"])
        def search_stays_a_file_question():
            CONTESTO["jv_online"] = True
            n = 0
            for phrase in ('jarvis search for "alpha"', "jarvis cerca alpha in notes.txt"):
                if jv_rs_parse(phrase.replace("jarvis ", "", 1), None) is not None:
                    raise RuntimeError(f"'{phrase}' was taken for a research")
                n += 1
            print("ok")
        run("quoted words and file names are not researched", search_stays_a_file_question)
        run("jarvis go offline", say("jarvis go offline"), need=["offline"])
        def news_wording():
            for yes, topic in (("news", ""), ("jarvis news".replace("jarvis ", ""), ""), ("ultime notizie", ""), ("le ultime news", ""),
                               ("news war", "war"), ("notizie sulla guerra", "guerra"), ("what's the news", ""),
                               ("show me the latest news about protests", "protests"), ("cosa succede nel mondo", "")):
                if jv_news_parse(yes) != topic:
                    raise RuntimeError(f"'{yes}' is not read as news about '{topic}'")
            for no in ("open news.txt", "search for news in it", "how many lines", 'search for "news"', "what is a dll"):
                if jv_news_parse(no) is not None:
                    raise RuntimeError(f"'{no}' was taken for a news request")
            print("ok")
        run("the phrases that ask for the news", news_wording)
        def news_pipeline():
            from datetime import timezone, timedelta
            now = datetime.now(timezone.utc)
            mk = lambda title, src, h, desc="Summary of the story. More detail follows here.": {
                "title": title, "link": "https://example.org/x", "desc": desc, "ts": now - timedelta(hours=h), "src": src, "img": None}
            items = [mk("Missile attack on city leaves dozens wounded", "BBC World", 2),
                     mk("Missile attack on city leaves dozens wounded overnight", "ANSA", 3),
                     mk("Thousands protest in the capital against the new law", "RaiNews", 5),
                     mk("Scientists find new exoplanet candidate", "Geopop", 7),
                     mk("Old story from last week", "ANSA", 300)]
            jv_news_show(items, "", {"BBC World", "ANSA", "RaiNews", "Geopop"}, {"BBC World", "ANSA", "RaiNews", "Geopop", "Il Post"},
                         with_images=False, now=now)
            jv_news_show(items, "war", {"ANSA"}, {"ANSA"}, with_images=False, now=now)
            jv_news_show([], "", set(), {"ANSA"}, with_images=False, now=now)
        run("news sorted into war / protests / everything else", news_pipeline, need=["WAR AND CONFLICTS", "PROTESTS", "SCIENCE AND TECH", "confirmed by 2 desks", "couldn't reach"], bad=["last week"])
        def news_refusals():
            for url, kind in (("http://www.ansa.it/sito/ansait_rss.xml", "feed"), ("https://example.com/feed", "feed"),
                              ("https://127.0.0.1/a.jpg", "image"), ("https://localhost/a.jpg", "image")):
                try:
                    jv_news_get(url, kind)
                except ValueError:
                    continue
                raise RuntimeError(f"{url} was not refused")
            try:
                jv_news_parse_feed(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><rss><channel/></rss>', "T")
            except ValueError:
                print("ok")
                return
            raise RuntimeError("a feed with XML entities was accepted")
        run("only my news sources, https, no numeric hosts, no XML entities", news_refusals)

        section("Game launcher (nothing is started)")
        def match():
            games = [{"name": "Cry of Fear", "alt": ""}, {"name": "Fear to Fathom", "alt": ""},
                     {"name": "DELTARUNE", "alt": "DELTARUNE"}]
            for phrase, want in (("cry of fear", "Cry of Fear"), ("the game cry of fear please", "Cry of Fear"),
                                 ("fear to fhatom", "Fear to Fathom"), ("deltarune", "DELTARUNE")):
                got, _ = jv_launch_match(phrase, games)
                if [g["name"] for g in got] != [want]:
                    raise RuntimeError(f"'{phrase}' gave {[g['name'] for g in got]}, expected {want}")
            if jv_launch_match("zzzzqq", games)[0]:
                raise RuntimeError("an unknown name matched a game")
            print("ok")
        run("matching a spoken name to a game (also with typos)", match)
        def listing():
            games = jv_launch_games(force=True)
            print(f"{len(games)} game(s) found on this PC: " + ", ".join(safe(g["name"]) for g in games[:12]))
        run("finding the games installed on this PC", listing)
        def blocked():
            win = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32", "notepad.exe") \
                if os.name == "nt" else "/etc/hosts"
            if jv_launch_blocked(win) is None:
                raise RuntimeError("a Windows/system file is not blocked")
            if jv_launch_blocked(os.path.join(tmp, "a.txt")) is not None:
                raise RuntimeError("a normal file is blocked")
            jv_launch_file(win)
        run("system files are refused, normal files allowed", blocked, need=["I won't open"])
        run("a program outside its game folder is refused", lambda: jv_launch_run(
            {"name": "test", "root": sub, "wins": [], "generic": True},
            ("launcher", os.path.join(tmp, "a.txt"), None)), need=["I won't start"])

        section("Voice and launcher (nothing is started, nothing is spoken)")
        def voice_quiet():
            if JV_VOICE["on"]:
                raise RuntimeError("the voice is on before anyone asked for it")
            jv_voice_say("this must stay silent")
            if JV_VOICE["q"] is not None and JV_VOICE["q"].unfinished_tasks:
                raise RuntimeError("a sentence was queued while the voice was off")
            got = jv_voice_clean("\x1b[36mOpen C:\\Games\\x\\y.exe now\x1b[0m")
            if got != "Open a file path now":
                raise RuntimeError(f"text for speech was not cleaned: {got!r}")
            print("ok")
        run("the voice starts silent; text is cleaned before it would be read aloud", voice_quiet)
        run("voice (shows its state)", cmd("Voice"), need=["OFF"])
        run("voice off while already silent", cmd("Voice", "off"), need=["already off"])
        run("'jarvis voice off' in plain words", say("jarvis voice off"), need=["already off"])
        def launch_plans():
            py = os.path.join(tmp, "t.py")
            with open(py, "w", encoding="utf-8") as f:
                f.write("print('hi')\n")
            p = jv_launch_plan(py, ["x"])
            if p["why"] or p["argv"][0] != sys.executable or p["argv"][-1] != "x" or not p["wait"]:
                raise RuntimeError(f"a .py script was planned wrongly: {p}")
            if jv_launch_plan(py, [], wait=False)["wait"]:
                raise RuntimeError("-Detach was ignored")
            doc = jv_launch_plan(os.path.join(tmp, "a.txt"), [])
            if doc["argv"] is not None or doc["why"]:
                raise RuntimeError("a text file should simply open with its usual program")
            if not jv_launch_plan(os.path.join(tmp, "a.txt"), ["x"])["why"]:
                raise RuntimeError("arguments for a document were accepted")
            if not jv_launch_plan(os.path.join(tmp, "nothing.py"), [])["why"]:
                raise RuntimeError("a missing file was accepted")
            print("ok")
        run("launch plans: .py gets this Python, documents open normally, bad requests are refused", launch_plans)
        def launch_blocked():
            win = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32", "notepad.exe") \
                if os.name == "nt" else "/etc/hosts"
            jv_launch_script(win, [])
        run("launch refuses system files", launch_blocked, need=["I won't launch"])
        run("launch without a file asks which one", cmd("Launch"), need=["Which file"])

        section("Browser mode (nothing is started: only checked)")
        def urlsafety():
            good = ["https://mail.google.com/", "https://www.canva.com/design?x=1"]
            bad = ["http://a.com", "https://localhost/", "https://127.0.0.1/", "https://10.0.0.5/", "https://a.com:8080/",
                   "https://user:pw@evil.com/", "javascript:alert(1)", "file:///C:/Windows/win.ini", "https://a.com/ x",
                   "https://x.local/", "chrome://settings", "data:text/html,hi", "https://a.com/\"onload=1"]
            for u in good:
                if not jv_launch_url_ok(u):
                    raise RuntimeError(f"a normal address was refused: {u}")
            for u in bad:
                if jv_launch_url_ok(u):
                    raise RuntimeError(f"an unsafe address was accepted: {u}")
            for phrase in ("javascript:alert(1)", "file:///C:/x", "chrome://settings", "data:text/html,hi", "https://u:p@evil.com"):
                if jv_launch_web_target(phrase)[0]:
                    raise RuntimeError(f"'{phrase}' would have been opened")
            print(f"{len(good)} normal and {len(bad)} unsafe addresses checked")
        run("only plain https pages are ever opened", urlsafety)
        def targets():
            want = {"email": "https://mail.google.com/", "my email": "https://mail.google.com/", "canva": "https://www.canva.com/",
                    "youtube lofi music": "https://www.youtube.com/results?search_query=lofi+music",
                    "search best pizza": "https://www.google.com/search?q=best+pizza", "example.com": "https://example.com",
                    "http://example.com": "https://example.com", "maps colosseo": "https://www.google.com/maps/search/colosseo"}
            for phrase, url in want.items():
                got = jv_launch_web_target(phrase)[0]
                if got != url:
                    raise RuntimeError(f"'{phrase}' gave {got}, expected {url}")
            print(f"{len(want)} phrases map to the right page")
        run("'email', 'canva', 'youtube <words>', 'search <words>' find the right page", targets)
        def profiles():
            d = os.path.join(tmp, "chrome")
            os.makedirs(d)
            sp = os.path.join(d, "Local State")
            with open(sp, "w", encoding="utf-8") as f:
                json.dump({"profile": {"info_cache": {"Default": {"name": "Anna", "user_name": "anna@example.com"},
                                                      "Profile 1": {"name": "Work", "user_name": "w@example.org"},
                                                      "../evil": {"name": "x"}}}}, f)
            ps = jv_launch_chrome_profiles(sp)
            if [p["dir"] for p in ps] != ["Default", "Profile 1"]:
                raise RuntimeError(f"profiles read wrongly: {ps}")
            for q, dirn in (("anna", "Default"), ("work", "Profile 1"), ("w@example.org", "Profile 1"), ("2", "Profile 1"), ("annna", "Default")):
                got = jv_launch_profile_match(q, ps)
                if [p["dir"] for p in got] != [dirn]:
                    raise RuntimeError(f"'{q}' matched {[p['dir'] for p in got]}, expected {dirn}")
            if jv_launch_profile_match("zzzz", ps):
                raise RuntimeError("an unknown name matched an account")
            print("2 accounts read, an unsafe folder name ignored, names/emails/numbers/typos matched")
        run("Chrome accounts are read and matched (from a sample file)", profiles)
        def convo():
            CONTESTO["jv_launch_dry"] = True
            try:
                CONTESTO["jv_online"] = False
                CONTESTO["jv_browser"] = None
                CONTESTO["jv_named"] = True
                if not jv_launch_browser("open chrome", "open chrome") or CONTESTO.get("jv_browser"):
                    raise RuntimeError("Chrome mode started while offline")
                CONTESTO["jv_online"] = True
                jv_launch_browser("open chrome", "open chrome")
                if not CONTESTO.get("jv_browser"):
                    raise RuntimeError("Chrome mode did not start")
                CONTESTO["jv_named"] = False
                for text in ("open email", "open canva", "search cats", "open chrome account"):
                    if not jv_launch_browser(text, text):
                        raise RuntimeError(f"'{text}' was not handled in Chrome mode")
                if jv_launch_browser("open a.txt", "open a.txt"):
                    raise RuntimeError("a file name was taken for a web page")
                jv_launch_browser("close chrome mode", "close chrome mode")
                if CONTESTO.get("jv_browser"):
                    raise RuntimeError("Chrome mode did not end")
                if jv_launch_browser("open email", "open email"):
                    raise RuntimeError("'open email' was taken without Chrome mode")
            finally:
                CONTESTO["jv_launch_dry"] = False
                CONTESTO["jv_browser"] = None
                CONTESTO["jv_online"] = False
                CONTESTO["jv_named"] = False
            print("ok")
        run("Chrome mode: needs online, then 'open email' / 'open canva', never takes file names, ends cleanly", convo)
        def chain_test():
            CONTESTO["jv_launch_dry"] = True
            try:
                CONTESTO.update(jv_online=True, jv_named=True, jv_browser=None)
                if jv_chain("open a.txt then read it", "open a.txt then read it"):
                    raise RuntimeError("a file sentence was taken for a browser chain")
                if jv_chain("open chrome", "open chrome"):
                    raise RuntimeError("a single step was taken for a chain")
                for text in ("open chrome then gmail and canva", "apri chrome poi youtube lofi", "open chrome, then search cats",
                             "open chrome then gmail on account zzzqqq"):
                    if not jv_chain(text, text):
                        raise RuntimeError(f"'{text}' was not handled")
                CONTESTO["jv_online"] = False
                if not jv_chain("open chrome then gmail", "open chrome then gmail"):
                    raise RuntimeError("the offline case was not answered")
            finally:
                CONTESTO.update(jv_launch_dry=False, jv_browser=None, jv_online=False, jv_named=False)
        run("several steps in one sentence: 'open chrome then gmail on account ...' (nothing is opened)", chain_test, need=["page(s) in one go", "online"])
        def layout_test():
            for text, want in (("open chrome full screen", ("open chrome", "full")), ("open chrome accanto", ("open chrome", "side")),
                               ("open chrome side by side", ("open chrome", "side")), ("gmail on account x a schermo intero", ("gmail on account x", "full")),
                               ("open chrome", ("open chrome", None))):
                got = jv_launch_layout_strip(text)
                if want[1] is None and got[1] is None:
                    continue
                if got != want:
                    raise RuntimeError(f"'{text}' gave {got}, expected {want}")
            CONTESTO["jv_launch_dry"] = True
            try:
                CONTESTO.update(jv_online=True, jv_named=True, jv_browser=None, jv_chrome_layout=None)
                if not jv_launch_browser("chrome full screen", "chrome full screen") or CONTESTO.get("jv_chrome_layout") != "full":
                    raise RuntimeError("'chrome full screen' did not set the layout")
                if not jv_launch_browser("chrome side by side", "chrome side by side") or CONTESTO.get("jv_chrome_layout") != "side":
                    raise RuntimeError("'chrome side by side' did not set the layout")
                jv_launch_browser("open chrome full screen", "open chrome full screen")
                if CONTESTO.get("jv_chrome_layout") != "full":
                    raise RuntimeError("'open chrome full screen' did not set the layout")
                jv_chain("open chrome side by side then gmail", "open chrome side by side then gmail")
                if CONTESTO.get("jv_chrome_layout") != "side":
                    raise RuntimeError("the chain did not take the layout")
                kind, rect = jv_launch_plan_rect("full")
                if kind != "full":
                    raise RuntimeError("full screen plan is wrong")
                print("ok")
            finally:
                CONTESTO.update(jv_launch_dry=False, jv_browser=None, jv_online=False, jv_named=False, jv_chrome_layout=None)
                CONTESTO.pop("jv_chrome_win", None)
        run("Chrome layout words: full screen / beside Jarvis (nothing is opened)", layout_test)
        def intro_test():
            for R in (4, 5, 11):
                ls = jv_logo_lines(R, 120, 0.7, 2)
                if len(ls) != 2 * R + 1 + 2:
                    raise RuntimeError(f"logo of radius {R} has {len(ls)} lines")
            if jv_launch_maximize_self() not in (True, False):
                raise RuntimeError("maximise returned something odd")
            jv_logo_show()                                    # not a terminal here: it must do nothing at all
            print("ok")
        run("start-up logo: sizes are right, nothing happens without a real terminal", intro_test, need=["ok"])

        section("Update system (checks only, nothing is installed)")
        run("Get-SecurityStatus panel", cmd("Get-SecurityStatus"), need=["SECURITY STATUS", "FINGERPRINT", "CODE SCAN", "GUARD", "ISOLATION"])
        cand = os.path.join(tmp, "jarvis_candidate.py")
        shutil.copyfile(os.path.abspath(__file__), cand)      # the running Jarvis as a candidate: all 9 checks must pass
        run("implement jarvis <copy of myself> -Dry (all 9 safety checks)", cmd("Implement", "jarvis", cand, "-Dry"),
            need=["SECURITY GATE", "9/9 gates passed"], bad=["would be REFUSED", "BLOCKED"], red=False)

        section("Security guard (the scanner must catch the classic tricks; nothing is executed or installed)")
        import ast as _ast

        def scan_blocks(code, want):
            def f():
                got = jv_upd_scan(_ast.parse(code))
                if not got:
                    raise RuntimeError("the scanner let it through")
                if want not in " ".join(got):
                    raise RuntimeError(f"flagged, but not as expected: {got[0]}")
                print(got[0])
            return f
        tricks = (
            ("import os as o ... o.remove()", "import os as o\ndef f(p):\n    o.remove(p)\n", "os.remove"),
            ("rm = shutil.rmtree ... rm()", "import shutil\nrm = shutil.rmtree\ndef f(p):\n    rm(p)\n", "shutil.rmtree"),
            ("map(os.remove, files)", "import os\ndef f(l):\n    list(map(os.remove, l))\n", "os.remove"),
            ("getattr(os, 'rem' + 'ove')", "import os\ndef f():\n    getattr(os, 'rem' + 'ove')('x')\n", "computed attribute"),
            ("getattr(x, 'system')", "def f(x):\n    getattr(x, 'system')('y')\n", "system"),
            ("__subclasses__ escape", "def f():\n    return ().__class__.__bases__[0].__subclasses__()\n", "__"),
            ("Path('a').open('w')", "import pathlib\ndef f():\n    pathlib.Path('a').open('w')\n", "opened for writing"),
            ("os.environ['A'] = ...", "import os\ndef f():\n    os.environ['A'] = '1'\n", "os.environ"),
            ("sys.modules['os']", "import sys\ndef f():\n    return sys.modules['os']\n", "sys.modules"),
            ("zip.extractall()", "def f(z):\n    z.extractall('.')\n", "extractall"),
            ("import subprocess as sp", "import subprocess as sp\ndef f():\n    sp.run(['x'])\n", "subprocess.run"),
            ("import socket as s ... s.socket()", "import socket as s\ndef f():\n    return s.socket()\n", "socket"),
            ("winreg write", "import winreg\ndef f():\n    winreg.SetValueEx(1, 'a', 0, 1, 'b')\n", "winreg"),
        )
        for label, code, want in tricks:
            run(f"scanner blocks: {label}", scan_blocks(code, want))

        def harmless():
            code = ("import os\nimport re\n"
                    "def f(p):\n    with open(p, 'rb') as h:\n"
                    "        return re.sub('a', 'b', h.read().decode()) + str(os.path.getsize(p)) + os.environ.get('X', '')\n"
                    "def g(o):\n    return getattr(o, 'st_birthtime', None)\n")
            got = jv_upd_scan(_ast.parse(code))
            if got:
                raise RuntimeError("false alarm: " + got[0])
            print("read-only code passes")
        run("scanner lets normal read-only code through", harmless)

        def candidate_with(text, name, **kw):
            path = os.path.join(tmp, name)
            with open(os.path.abspath(__file__), "rb") as s_, open(path, "wb") as d_:
                d_.write(s_.read() + text)
            return path
        hidden = candidate_with("\n# access \u202eevil\u202c\n".encode("utf-8"), "cand_hidden.py")
        run("a hidden direction-change character is refused (check 1)", lambda: jv_upd_check(hidden, None),
            need=["BLOCKED", "U+202E"], red=True)
        run("a file that changed after staging is refused (check 2)", lambda: jv_upd_check(cand, None, "0" * 64),
            need=["BLOCKED", "changed after"], red=True)
        link = os.path.join(tmp, "cand_link.py")

        def linked():
            try:
                os.symlink(cand, link)
            except (OSError, NotImplementedError, AttributeError):
                print("(this system does not allow links here: skipped)")
                return
            ok_, phase_, _why = jv_upd_check(link, None)
            if ok_ or phase_ != "valid source":
                raise RuntimeError("a link was accepted as an update")
        run("a link instead of a plain file is refused (check 1)", linked, need=[], red=True)
        run("log lines cannot be forged or carry escape codes", lambda: print(
            "clean" if jv_upd_clean("a\nb\x1b[31m c\u202e") == "a b [31m c" else (_ for _ in ()).throw(
                RuntimeError(repr(jv_upd_clean("a\nb\x1b[31m c\u202e"))))))

        exts = [n for n in NOMI if GROUPS.get(n) == "Extensions"]
        if exts:
            section("Extensions (from ext/): registered and documented; not executed, I do not know their arguments")
            for n in exts:
                run(f"help {n}", cmd("Get-Help", n), need=["SYNTAX"])
    except KeyboardInterrupt:
        out()
        out("Stopped by user: the results are partial.", YELLOW)
    finally:
        try:
            os.chdir(old_cwd)
        except OSError:
            pass
        CONTESTO.clear()
        CONTESTO.update(snap)
        shutil.rmtree(tmp, ignore_errors=True)
    failed = [r for r in results if r[1]]
    return len(results) - len(failed), len(results), failed


@cmdlet("Maintenance", group="Assistant", usage="""maintenance     maintenance mode: health check of Jarvis, then a test of EVERY command
(say it in plain words too: "jarvis go in maintenance", "jarvis test all the commands")
The tests run on sample files in a temporary folder that is deleted afterwards: nothing of yours is changed,
no game or file is opened, nothing is installed. To update, use  implement jarvis)""")
def jv_upd_maintenance_cmd(args):
    """Maintenance mode: health check of Jarvis and a test of every command."""
    out()
    out("=== MAINTENANCE MODE ===  (everything else is on hold; Ctrl+C stops it)", CYAN)
    jv_upd_health([])
    out("Testing every command on sample files in a temporary folder (deleted afterwards)...", GRAY)
    t0 = time.monotonic()
    ok, total, failed = jv_upd_selftest()
    out()
    secs = time.monotonic() - t0
    if failed:
        out(f"{ok}/{total} tests passed in {secs:.1f} s. {len(failed)} FAILED:", RED)
        for label, why in failed:
            out(f"  - {label}: {why}", RED)
    else:
        out(f"All {total} tests passed in {secs:.1f} s. Every command works, sir.", GREEN)
    out("Maintenance finished: nothing of yours was changed. Back to normal operation.", GRAY)
    out()


# ======================= GAME LAUNCHER (jarvis open <game>) =======================
# Only 'jarvis open <game>' starts anything: the game's own program, found inside the game's own folder.
# A plain 'open <game>' keeps showing the data.win read-only and never starts it.
def jv_launch_extra_dirs():
    """Game folders learned during updates (JV_DATA)."""
    try:
        return [d for d in JV_DATA.get("game_dirs", []) if isinstance(d, str) and os.path.isdir(d)]
    except Exception:
        return []


def jv_launch_norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def jv_launch_exes(folder):
    """The programs that can start a game in this folder (installers, crash reporters... skipped)."""
    res = []
    try:
        names = sorted(os.listdir(folder), key=str.lower)
    except OSError:
        return res
    for n in names:
        low, p = n.lower(), os.path.join(folder, n)
        if any(s in low for s in JV_LAUNCH_SKIP):
            continue
        if os.name == "nt":
            ok = low.endswith(".exe") and os.path.isfile(p)
        elif sys.platform == "darwin":
            ok = low.endswith(".app") and os.path.isdir(p)
        else:
            ok = os.path.isfile(p) and (low.endswith((".x86_64", ".x86", ".sh", ".appimage"))
                                        or ("." not in n and os.access(p, os.X_OK)))
        if ok:
            res.append(p)
    return res


def jv_launch_best(exes, names):
    """Of several programs, the one named like the game; otherwise the biggest."""
    if not exes:
        return None
    want = {jv_launch_norm(n) for n in names if n}
    for p in exes:
        if jv_launch_norm(os.path.splitext(os.path.basename(p))[0]) in want:
            return p
    try:
        return max(exes, key=os.path.getsize)
    except OSError:
        return exes[0]


JV_LAUNCH_NOTGAME = ("steamworks shared", "steam controller configs", "steam linux runtime", "proton", "steamvr",
                     "common redist", "directx", "vcredist")


def jv_launch_generic():
    """Games that are not GameMaker: every sub-folder of the game libraries that holds a program
    (searched in the folder itself, then one and two levels below). {key: game}."""
    res = {}
    for lib in game_locations() + jv_launch_extra_dirs():
        try:
            subs = sorted(os.listdir(lib), key=str.lower)
        except OSError:
            continue
        alts = {}                                         # Steam: install folder -> real game title
        if os.path.basename(lib.rstrip("\\/")).lower() == "common":
            sa = os.path.dirname(lib.rstrip("\\/"))
            try:
                for f in os.listdir(sa):
                    if f.startswith("appmanifest_") and f.endswith(".acf"):
                        with open(os.path.join(sa, f), encoding="utf-8", errors="replace") as fh:
                            txt = fh.read(20000)
                        d1 = re.search(r'"installdir"\s+"([^"]+)"', txt)
                        n1 = re.search(r'"name"\s+"([^"]+)"', txt)
                        if d1 and n1:
                            alts[d1.group(1).lower()] = n1.group(1)
            except OSError:
                pass
        for n in subs:
            root = os.path.join(lib, n)
            if not os.path.isdir(root) or skip_dir(root) or n.lower().startswith(JV_LAUNCH_NOTGAME):
                continue
            key = os.path.normcase(os.path.realpath(root))
            if key in res:
                continue
            exes, winexe = [], False
            alt = alts.get(n.lower(), "")
            base = root.rstrip(os.sep).count(os.sep)
            for cur, ds, _fs in os.walk(root, onerror=lambda e: None):
                depth = cur.rstrip(os.sep).count(os.sep) - base
                ds[:] = [] if depth >= 3 else sorted(d for d in ds if not skip_dir(os.path.join(cur, d)))
                exes = jv_launch_exes(cur)
                if exes:
                    break
            if exes:
                best = jv_launch_best(exes, [n, alt])
                res[key] = {"name": n, "alt": alt, "root": root, "wins": [], "dirs": [],
                            "parts": [("launcher", best, None)], "winexe": False, "generic": True}
            elif os.name != "nt":
                try:
                    winexe = any(f.lower().endswith(".exe") for f in os.listdir(root))
                except OSError:
                    pass
                if winexe:
                    res[key] = {"name": n, "alt": alt, "root": root, "wins": [], "dirs": [],
                                "parts": [], "winexe": True, "generic": True}
    return res


def jv_launch_games(force=False):
    """Installed games, one per game folder (chapter folders are grouped under their parent):
    {name, alt, root, wins, parts:[(label, exe, chapter)], winexe}."""
    cached = CONTESTO.get("jv_launch_cache")
    if cached and not force and time.time() - cached[0] < 30:
        return cached[1]
    roots = {}
    for w in jv_games():
        d = os.path.dirname(os.path.abspath(w))
        m = re.fullmatch(JV_LAUNCH_CHAPTER, os.path.basename(d))
        root = os.path.dirname(d) if m else d
        g = roots.setdefault(os.path.normcase(os.path.realpath(root)),
                             {"name": os.path.basename(root) or root, "alt": "", "root": root,
                              "wins": [], "dirs": [], "parts": [], "winexe": False})
        g["wins"].append(w)
        g["dirs"].append((d, int(m.group(1)) if m else None))
    for g in roots.values():
        try:
            g["alt"] = gm_read_info(g["wins"][0])["name"] or ""
        except Exception:
            g["alt"] = ""
        names = [g["name"], g["alt"]]
        launcher = jv_launch_best(jv_launch_exes(g["root"]), names)
        if launcher:
            g["parts"] = [("launcher", launcher, None)]
        else:
            for d, ch in sorted(g["dirs"], key=lambda x: (x[1] or 0, x[0].lower())):
                exe = jv_launch_best(jv_launch_exes(d), names)
                if exe:
                    g["parts"].append((os.path.basename(d), exe, ch))
        if not g["parts"] and os.name != "nt":
            try:
                g["winexe"] = any(n.lower().endswith(".exe") for n in os.listdir(g["root"]))
            except OSError:
                pass
    for key, g in jv_launch_generic().items():           # every other game (Cry of Fear, ...)
        if key not in roots:
            roots[key] = g
    games = sorted(roots.values(), key=lambda g: g["name"].lower())
    CONTESTO["jv_launch_cache"] = (time.time(), games)
    return games


def jv_launch_match(phrase, games):
    """(matching games, chapter number or None) for what the person said."""
    p = re.sub(r"\s+(?:please|pls|now|subito|ora|per favore)$", "", phrase.strip(), flags=re.I)
    p = re.sub(r"^(?:(?:the|il|lo|la|my|mio|il mio|game|gioco|il gioco|the game)\s+)+", "", p, flags=re.I).strip()
    tries = [(p, None)]
    m = re.match(r"(?i)^(.*?)[\s,]*(?:chapter|capitolo|cap\.?|ch\.?|#)?\s*(\d{1,2})$", p)
    if m and m.group(1).strip():
        tries.append((m.group(1).strip(), int(m.group(2))))
    for text, ch in tries:
        n = jv_launch_norm(text)
        if len(n) < 2:
            continue
        exact = [g for g in games if n in (jv_launch_norm(g["name"]), jv_launch_norm(g["alt"]))]
        if exact:
            return exact, ch
        part = [g for g in games if len(n) >= 3 and (n in jv_launch_norm(g["name"]) or n in jv_launch_norm(g["alt"]))]
        if part:
            return part, ch
        if len(n) >= 5:
            close = [g for g in games if difflib.get_close_matches(n, [jv_launch_norm(g["name"]),
                                                                        jv_launch_norm(g["alt"])], n=1, cutoff=0.85)]
            if close:
                return close, ch
    return [], None


def jv_launch_run(game, part):
    """Start ONE program of a known game folder. Everything is checked first."""
    label, exe, chapter = part
    name = safe(game["name"])
    real_root = os.path.normcase(os.path.realpath(game["root"]))
    real_exe = os.path.normcase(os.path.realpath(exe))
    if not (real_exe.startswith(real_root + os.sep) and os.path.exists(exe)
            and (game.get("generic") or any(os.path.isfile(w) for w in game["wins"]))):
        jarvis_say(f"I won't start that, sir: it is not inside the folder of a game I know ({name}).")
        return
    if os.name != "nt" and exe.lower().endswith(".exe"):
        jarvis_say(f"{name} is a Windows program, sir: this system cannot start it.")
        return
    import subprocess
    jarvis_say(f"Launching {name}{'' if label == 'launcher' else ' (' + safe(label) + ')'}, sir. "
               "I only start the game's own program; I don't touch its files.")
    out(f"  {safe(exe)}", GRAY)
    try:
        if sys.platform == "darwin" and exe.lower().endswith(".app"):
            proc = subprocess.Popen(["open", exe], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
        elif os.name == "nt":
            flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            proc = subprocess.Popen([exe], cwd=os.path.dirname(exe), stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    close_fds=True, creationflags=flags)
        else:
            proc = subprocess.Popen([exe], cwd=os.path.dirname(exe), stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    close_fds=True, start_new_session=True)
    except OSError as e:
        jarvis_say(f"It would not start, sir ({safe(e.strerror or e)}).")
        return
    time.sleep(1.2)
    rc = proc.poll()
    if rc not in (None, 0):
        jarvis_say(f"It closed right away with exit code {rc}, sir. Try starting it once from its own folder.")
    else:
        jarvis_say(f"{name} is starting, sir.")
    out()


def jv_launch_start(game, chapter):
    parts = game["parts"]
    if not parts:
        if game["winexe"]:
            jarvis_say(f"{safe(game['name'])} has only a Windows program, sir: this system cannot start it.")
        else:
            jarvis_say(f"I found the folder of {safe(game['name'])} but no program to start in it, sir.")
        out(f"  {safe(game['root'])}", GRAY)
        jarvis_say(f"'open {safe(game['name'])}' (without 'jarvis') still shows its data.win.")
        return
    if len(parts) > 1:
        if chapter is not None:
            hit = [p for p in parts if p[2] == chapter]
            if not hit:
                jarvis_say(f"{safe(game['name'])} has no chapter {chapter} here, sir.")
                return
            jv_launch_run(game, hit[0])
            return
        jarvis_say(f"{safe(game['name'])} has several chapters, sir. Which one?")
        for i, p in enumerate(parts, 1):
            out(f"  [{i}] {safe(p[0])}", CYAN)
        CONTESTO["jv_launch_pending"] = [(game, p) for p in parts]
        jarvis_say("Say 'jarvis open 1', 'jarvis open 2'... or 'jarvis open <game> chapter 2'.")
        return
    jv_launch_run(game, parts[0])


def jv_launch_blocked(path):
    """Why this file must not be opened (Windows internal / system files), or None when it is fine."""
    full = os.path.normcase(os.path.realpath(path))
    if os.name == "nt":
        roots = [os.environ.get("SystemRoot"), os.environ.get("windir")]
        for r in roots:
            if r:
                rr = os.path.normcase(os.path.realpath(r))
                if full == rr or full.startswith(rr + os.sep):
                    return "it is inside the Windows system folder"
        try:
            if os.stat(path).st_file_attributes & 0x4:        # FILE_ATTRIBUTE_SYSTEM
                return "it is marked as a Windows system file"
        except OSError:
            pass
        if os.path.splitext(full)[1] in (".sys", ".dll", ".drv", ".mui", ".cat", ".cpl", ".ocx"):
            return "it is an internal Windows component file"
    else:
        for d in PSEUDO_DIRS | {"/boot", "/etc"}:
            if full == d or full.startswith(d + os.sep):
                return "it is a system file"
    return None


def jv_launch_file(path):
    """'jarvis open <file>': open any file with its normal program, except Windows internal ones."""
    full = os.path.abspath(path)
    name = safe(os.path.basename(full))
    why = jv_launch_blocked(full)
    if why:
        jarvis_say(f"I won't open {name}, sir: {why}.")
        return
    import subprocess
    ack(f"Opening {name} with its usual program.")
    out(f"  {safe(full)}", GRAY)
    try:
        if os.name == "nt":
            os.startfile(full)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", full], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(["xdg-open", full], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError as e:
        jarvis_say(f"It would not open, sir ({safe(e.strerror or e)}). There may be no program set for this file type.")
        return
    CONTESTO["file"] = full
    CONTESTO["jlast"] = {"path": full, "sel": full}
    out()


JV_LAUNCH_NOSEARCH = r"(?:the\s+)?(?:scan|status|check|battery|memory|ram|search|find|update|test|everything|all|games?|corrupt)\b"


def jv_launch_search(phrase, limit=60):
    """Last resort for 'jarvis open <name>': look for a shortcut, a program or a game folder with that name
    on the whole PC (Windows folder excluded) and open it. True when it handled the request."""
    p = re.sub(r"\s+(?:please|pls|now|subito|ora|per favore)$", "", phrase.strip().strip("\"'`"), flags=re.I)
    p = re.sub(r"^(?:(?:the|il|lo|la|my|mio|il mio|game|gioco|il gioco|the game)\s+)+", "", p, flags=re.I).strip()
    n = jv_launch_norm(p)
    if len(n) < 3 or len(p.split()) > 6 or re.match(JV_LAUNCH_NOSEARCH, p, re.I) or re.search(r"[\\/:]", p):
        return False

    def close(stem):
        s = jv_launch_norm(stem)
        if not s:
            return False
        if s == n or (len(n) >= 6 and n in s):
            return True
        if len(n) >= 5 and abs(len(s) - len(n)) <= 4:
            sm = difflib.SequenceMatcher(None, s, n)
            return sm.real_quick_ratio() >= 0.85 and sm.ratio() >= 0.85
        return False

    home = os.path.expanduser("~")
    quick = []
    if os.name == "nt":
        for v in ("ProgramData", "APPDATA"):
            if os.environ.get(v):
                quick.append(os.path.join(os.environ[v], "Microsoft", "Windows", "Start Menu"))
        quick += [os.path.join(home, "Desktop"), os.path.join(home, "OneDrive", "Desktop"),
                  os.path.join(os.environ.get("PUBLIC", "C:\\Users\\Public"), "Desktop")]
    win = os.path.normcase(os.environ.get("SystemRoot") or os.environ.get("windir") or "\x00")
    jarvis_say(f"I don't know '{safe(p)}' yet, sir. Searching this PC for it (Ctrl+C stops me)...")
    t0, found, stopped = time.time(), [], False

    def scan(roots):
        nonlocal stopped
        for root in roots:
            if not os.path.isdir(root):
                continue
            for cur, ds, fs in os.walk(root, onerror=lambda e: None):
                if time.time() - t0 > limit:
                    stopped = True
                    return
                ds[:] = [d for d in ds if not skip_dir(os.path.join(cur, d))
                         and os.path.normcase(os.path.join(cur, d)) != win
                         and d.lower() not in ("$recycle.bin", "system volume information", "windowsapps")]
                for d in ds:
                    if close(d):
                        found.append((2, os.path.join(cur, d)))
                for f in fs:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in (".lnk", ".url", ".exe") and close(os.path.splitext(f)[0]) \
                            and not any(x in f.lower() for x in JV_LAUNCH_SKIP):
                        found.append((0 if ext != ".exe" else 1, os.path.join(cur, f)))
                if len(found) >= 12:
                    return

    try:
        scan(quick)
        if not found:
            scan(pc_roots())
    except KeyboardInterrupt:
        out()
        jarvis_say("Stopped, sir.")
        return True
    found = [x for x in found if jv_launch_blocked(x[1]) is None]
    found.sort(key=lambda x: (x[0], len(x[1])))
    for rank, path in found:
        if rank in (0, 1) and os.path.isfile(path):
            if rank == 1:
                jv_launch_run({"name": os.path.splitext(os.path.basename(path))[0], "root": os.path.dirname(path),
                               "wins": [], "generic": True}, ("launcher", path, None))
            else:
                jv_launch_file(path)
            return True
        if rank == 2 and os.path.isdir(path):
            exes, base = [], path.rstrip(os.sep).count(os.sep)
            for cur, ds, _fs in os.walk(path, onerror=lambda e: None):
                ds[:] = [] if cur.rstrip(os.sep).count(os.sep) - base >= 3 else sorted(
                    d for d in ds if not skip_dir(os.path.join(cur, d)))
                exes = jv_launch_exes(cur)
                if exes:
                    break
            best = jv_launch_best(exes, [os.path.basename(path), p])
            if best:
                jv_launch_run({"name": os.path.basename(path), "root": path, "wins": [], "generic": True},
                              ("launcher", best, None))
                return True
    jarvis_say(f"I searched the whole PC and found nothing called '{safe(p)}'{' (time limit reached)' if stopped else ''}, sir.")
    return True


# >>>>> JARVIS-PART 19_browser_mode.py >>>>>
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


# >>>>> JARVIS-PART 20_screen_watch.py >>>>>
# ---------------- SCREEN WATCH: "is someone watching my screen?" ----------------
# Every few seconds (Windows only) Jarvis READS four things: the session list (qwinsta), the open connections (netstat),
# the process list (tasklist) and the titles of the visible windows. Nothing on the PC is changed.
# When a Remote Desktop / VNC / remote-help / screen-sharing session shows up, Jarvis pauses at its next output (JV_RUN),
# a red WARNING window tells you who or what it is (names come from your list of known people: 'watch know'),
# an optional e-mail goes to YOU, and if you press F the viewer sees a SIMULATED intrusion screen (text and colours only).
# Safety nets: the pause always ends (window closed, window failed to open, or the time limit), see jv_watch_alert_run.
JV_WATCH = {"daemon": False, "on": True, "thread": None, "stop": threading.Event(), "seen": set(), "alert": False,
            "interval": 5, "last": []}
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


def jv_watch_save(cfg):
    """The only file this feature writes: its own tiny settings file. True when saved."""
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


def jv_watch_scan():
    """One look at the system -> list of {tag, what, remote, user, name} (empty = nobody watching)."""
    if os.name != "nt":
        return []
    items = []
    for sess, user, sid in jv_watch_parse_sessions(jv_watch_run(["qwinsta"])):
        items.append({"tag": "sess:" + sess, "what": f"Remote Desktop session {sess} (user {user})", "remote": "", "user": user})
    for port, ip in jv_watch_parse_netstat(jv_watch_run(["netstat", "-ano", "-p", "tcp"])):
        items.append({"tag": f"net:{ip}:{port}", "what": f"{JV_WATCH_PORTS[port]} connection on port {port}", "remote": ip, "user": ""})
    for proc, meaning in jv_watch_parse_tasks(jv_watch_run(["tasklist", "/fo", "csv", "/nh"])):
        items.append({"tag": "proc:" + proc, "what": meaning, "remote": "", "user": ""})
    for t in jv_watch_match_titles(jv_watch_windows()):
        items.append({"tag": "win:" + t.lower()[:80], "what": f"window: {t[:80]}", "remote": "", "user": ""})
    cfg = jv_watch_cfg()
    for it in items:
        it["name"] = jv_watch_who(it, cfg)
    return items


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
    jv_watch_beat("jarvis", st["interval"])
    while not st["stop"].wait(max(2, int(st["interval"]))):
        try:
            jv_watch_beat("jarvis", st["interval"])      # tells the background guard "Jarvis is open and watching": the guard stays quiet
            if not st["on"]:
                continue
            items = jv_watch_scan()
            st["last"] = items
            tags = {i["tag"] for i in items}
            new = tags - st["seen"]
            st["seen"] = tags                 # what ended is forgotten, so a later session alerts again
            if new and not st["alert"]:
                jv_watch_alert(items)
        except Exception:
            pass                              # the watcher never dies because of one bad reading


def jv_watch_start():
    st = JV_WATCH
    cfg = jv_watch_cfg()
    st["on"] = bool(cfg.get("on", True))
    try:
        st["interval"] = min(max(int(cfg.get("interval", 5)), 2), 300)
    except (TypeError, ValueError):
        st["interval"] = 5
    if os.name == "nt" and st["thread"] is None:
        st["thread"] = threading.Thread(target=jv_watch_loop, daemon=True)
        st["thread"].start()
        if not jv_watch_guard_installed() and int(cfg.get("hint_n") or 0) < 3:
            cfg["hint_n"] = int(cfg.get("hint_n") or 0) + 1
            jv_watch_save(cfg)
            out("  Screen watch only works while Jarvis is open. For always-on (also when closed):  watch guard on", GRAY)


def jv_watch_stop():
    JV_WATCH["stop"].set()
    JV_RUN.set()
    jv_watch_beat("jarvis", 0, closed=True)             # Jarvis is closing: the background guard takes over at once


# ---------------- the background guard: watches even when Jarvis is closed ----------------
# A second, tiny copy of the same watcher runs with NO console window (pythonw), started at every Windows login
# by one file in your Startup folder. It uses the very same read-only look and the same WARNING window.
# While Jarvis is open Jarvis does the alerting (and pauses itself), so you never get two windows: the guard stays quiet.
# It is yours to control:  watch guard on | off | start | stop.  Everything lives in jarvis_update/ and the Startup folder.
JV_GUARD_NAME = "JarvisScreenWatch.vbs"


def jv_watch_beat(name, interval, closed=False):
    """Heartbeat file jarvis_update/<name>.hb : 'unix-time interval'. closed=True writes an already-old time."""
    try:
        with open(os.path.join(jv_upd_sub("."), name + ".hb"), "w", encoding="utf-8") as f:
            f.write(f"{0 if closed else time.time():.0f} {int(interval)}")
    except OSError:
        pass


def jv_watch_beat_alive(name):
    """True when <name>.hb is fresh (written within about two of its own intervals)."""
    try:
        with open(os.path.join(jv_upd_dir(), name + ".hb"), encoding="utf-8") as f:
            t, iv = f.read().split()[:2]
        return time.time() - float(t) < 2 * max(int(iv), 2) + 10
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
    n = 0
    while max_loops is None or n < max_loops:
        n += 1
        try:
            cfg = jv_watch_cfg()
            try:
                st["interval"] = min(max(int(cfg.get("interval", 5)), 2), 300)
            except (TypeError, ValueError):
                st["interval"] = 5
            jv_watch_beat("guard", st["interval"])
            if os.path.isfile(stop):
                try:
                    os.remove(stop)
                except OSError:
                    pass
                break
            if bool(cfg.get("on", True)):
                items = jv_watch_scan()
                st["last"] = items
                tags = {i["tag"] for i in items}
                new = tags - st["seen"]
                st["seen"] = tags
                if new and not st["alert"] and not jv_watch_beat_alive("jarvis"):     # Jarvis open -> Jarvis alerts
                    jv_watch_alert(items)
        except Exception:
            pass                                         # the guard never dies because of one bad reading
        if max_loops is None:
            time.sleep(max(2, int(st["interval"])))
    jv_watch_beat("guard", 0, closed=True)
    jv_upd_log("screen watch guard stopped")


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
watch interval <seconds>       how often to look (2-300, default 5)
watch know                     list the people you know
watch know add <name> <ip-or-user>     e.g. watch know add Mario 192.168.1.20
watch know del <name>
watch mail to=<you@x.com> host=<smtp.x.com> [port=465] [user=<login>] [passenv=<ENV_VAR_WITH_PASSWORD>]
watch mail off | test
watch guard                    always-on guard: status (it watches even when Jarvis is closed)
watch guard on | off           start it with Windows (and now) / remove it
watch guard start | stop       run it now / stop it until the next Windows login
Read-only: it only reads the session list, open connections, process list and window titles.
On a sighting Jarvis pauses at its next output and a red WARNING window opens; ENTER resumes, F shows the
viewer a SIMULATED intrusion screen (text only). The pause always ends by itself after at most 15 minutes.""")
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
        jarvis_say(f"Screen watch is {'ON' if st['on'] else 'OFF'}, sir. I look every {st['interval']} s"
                   + ("." if os.name == "nt" else " (but only on Windows)."))
        out(f"  known people : {len(cfg.get('known') or {})}", GRAY)
        out(f"  e-mail alert : {'to ' + cfg['mail_to'] if cfg.get('mail_to') else 'not set up'}", GRAY)
        out(f"  seen now     : {len(st['last'])} item(s)", GRAY)
        out()
    elif word in ("on", "off"):
        st["on"] = word == "on"
        cfg["on"] = st["on"]
        st["seen"] = set()
        jarvis_say(f"Screen watch {'on' if st['on'] else 'off'}, sir." + ("" if jv_watch_save(cfg) else " (could not save the setting)"))
    elif word == "now":
        items = jv_watch_scan()
        st["last"] = items
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
    elif word == "interval" and rest and rest[0].isdigit():
        st["interval"] = min(max(int(rest[0]), 2), 300)
        cfg["interval"] = st["interval"]
        jv_watch_save(cfg)
        jarvis_say(f"I will look every {st['interval']} seconds, sir.")
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
# >>>>> JARVIS-PART 20_voice.py >>>>>
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


# >>>>> JARVIS-PART 21_parser_logo_main.py >>>>>
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
def jv_logo_lines(R, cols, angle, scan=-1):
    pad = [(" ", 0.0)] * max(0, (cols - (4 * R + 1)) // 2)
    lines = [jv_paint(pad + row, "cyan") for row in jv_globe_rows(R, angle, scan)]
    title = "J.A.R.V.I.S."
    lines.append("")
    lines.append(jv_paint([(c, 0.95) for c in " " * max(0, (cols - len(title)) // 2) + title], "cyan"))
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
    Rb = max(Rs, min((rows - 6) // 2, (cols - 6) // 4, 11))
    total = 2 * Rb + 1 + 2                                      # globe rows + blank + title
    pad0 = max(0, (rows - 1 - total) // 2)
    screen = pad0 + total
    state = {"first": True}

    def draw(R, pad, angle, scan=-1):
        lines = [""] * pad + jv_logo_lines(R, cols, angle, scan)
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
                draw(Rb, pad0, angle, scan=i % (2 * Rb + 1))
                angle += 0.07 + 0.2 * (1 - i / spin)
                time.sleep(0.05)
            steps = 22
            for i in range(1, steps + 1):                       # 2) it shrinks and rises to the top
                t = i / steps
                t = t * t * (3 - 2 * t)
                draw(round(Rb + (Rs - Rb) * t), round(pad0 * (1 - t)), angle)
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
