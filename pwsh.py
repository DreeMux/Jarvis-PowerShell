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

Run:  python pwsh.py      (Windows: double-click START.bat)
Type  help  or just talk to it:  "find my games", "scan this PC for corrupt files".

Everything here is READ-ONLY: nothing of yours is ever written, moved or deleted. Only two things you
ask for explicitly go further: "implement jarvis" (updates this very file, after 9 safety checks and
with a backup) and "jarvis open <game>" (starts the game's own program).
Optional: pip install psutil  (live memory/CPU of a running game in pluton.key).
Optional extensions: put .py files in a folder named ext/ next to this file.
"""

import codecs
import difflib
import errno
import gzip
import hashlib
import json
import mimetypes
import os
import pathlib
import random
import re
import runpy
import shutil
import sqlite3
import stat
import struct
import subprocess
import sys
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

BG      = bg(0, 0, 0)            # nero
TEXT    = fg(238, 237, 240)      # #EEEDF0 grigio chiaro
YELLOW  = fg(255, 255, 0)        # comandi digitati (PSReadLine)
RED     = fg(255, 0, 0)          # errori
GREEN   = fg(0, 255, 0)
CYAN    = fg(0, 255, 255)
GRAY    = fg(128, 128, 128)
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
    except OSError:
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
            with open(p, encoding="utf-8", errors="replace") as f:
                for riga in f:
                    out(safe(riga.rstrip("\r\n")))
        except OSError:
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
        with open(path, "rb") as f:
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
    with open(path, "rb") as f:
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
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            sha.update(chunk)
            md.update(chunk)
    return sha.hexdigest().upper(), md.hexdigest().upper()


def image_size(path, kind):
    try:
        with open(path, "rb") as f:
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


def resolve_existing(pos, cmd):
    p = pos[0]
    joined = " ".join(pos)
    if not os.path.exists(p) and os.path.exists(joined):
        p = joined
    if not os.path.exists(p):
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
            with open(path, "rb") as f:
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
        with open(path, "rb") as f:
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
        with open(path, "rb") as f:
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


# ----------------------------- denux.hunter -----------------------------
def check_zip(path):
    if not zipfile.is_zipfile(path):
        return "Not a valid ZIP container (bad or missing central directory)"
    with zipfile.ZipFile(path) as z:
        bad = z.testzip()
        if bad:
            return f"CRC/data error in entry '{safe(bad)}'"


def check_png(path):
    with open(path, "rb") as f:
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
    with open(path, "rb") as f:
        f.seek(max(0, size - n))
        return f.read()


def check_jpeg(path):
    with open(path, "rb") as f:
        if f.read(3) != b"\xff\xd8\xff":
            return "Invalid JPEG signature"
    if not tail_of(path, 64).rstrip(b"\x00").endswith(b"\xff\xd9"):
        return "Missing end-of-image marker (file likely truncated)"


def check_gif(path):
    with open(path, "rb") as f:
        if f.read(6) not in (b"GIF87a", b"GIF89a"):
            return "Invalid GIF signature"
    if not tail_of(path, 64).rstrip(b"\x00").endswith(b"\x3b"):
        return "Missing GIF trailer (file likely truncated)"


def check_pdf(path):
    with open(path, "rb") as f:
        if f.read(5) != b"%PDF-":
            return "Missing %PDF- header"
    if b"%%EOF" not in tail_of(path):
        return "Missing %%EOF marker (file likely truncated)"


def check_json(path):
    with open(path, "rb") as f:
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
    with open(path, "rb") as f:
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
            with open(path, "rb") as f:
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


# ----------------------------- undersopic.key -----------------------------
GM_FILE = "data.win"


def gm_read_info(path):
    """Read-only peek at a GameMaker data.win (a FORM container). Never modifies it."""
    info = {"ok": False, "notes": [], "chunks": [], "name": None, "gm": None, "bytecode": None}
    size = os.path.getsize(path)
    with open(path, "rb") as f:
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
            with open("/proc/meminfo") as f:
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
                    with open(f"{base}/{n}/capacity") as f:
                        pct = int(f.read().strip())
                    with open(f"{base}/{n}/status") as f:
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
        ("maintenance", "read-only health check: integrity, security scan, backups, quarantine, last log lines"),
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
               "Everything I do is read-only, except updating myself or starting a game when you ask.")
    jarvis_status("Current status")
    jarvis_say('Type "help" for commands, or just tell me what you need: '
               '"find my games", "scan this PC for corrupt files".')
    jv_upd_show_report()
    out()


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
        with open("/proc/uptime") as f:
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
    jarvis_say("Here is what I can answer, sir. All read-only, except the START A GAME and UPDATE rows:")
    rows = [
        ("OPEN", 'open data.win   |   open the 2nd one   |   open undertale   |   read notes.txt   |   go up'),
        ("START A GAME", 'jarvis open deltarune   |   jarvis open undertale   |   jarvis open deltarune chapter 2   (plain "open deltarune" never starts it)'),
        ("ANY FILE", 'how big is it   |   when was it modified   |   what type is it   |   is it corrupt   |   sha256   |   does the md5 match <hash>'),
        ("TEXT", 'how many lines/words   |   first 20 lines   |   last 5 lines   |   lines 10 to 20   |   search for "word"   |   hex dump'),
        ("CSV / JSON", 'which columns   |   average of <column>   |   first 5 rows   |   which keys   |   value of <key>'),
        ("ZIP / DB", 'what is inside   |   biggest entry   |   which tables   |   how many rows in <table>   |   columns of <table>'),
        ("IMAGE / PDF / EXE", 'dimensions   |   how many pages   |   is it 64-bit   |   when was it built   |   is it signed'),
        ("GAMES (data.win)", 'what game is this   |   how many sprites/rooms/sounds   |   list the chunks   |   biggest chunk   |   search for "text"'),
        ("FOLDER", 'how many files here   |   biggest files   |   newest / oldest   |   find all png files   |   duplicates   |   bigger than 100 MB   |   modified today   |   by extension'),
        ("PC", 'free disk space   |   what time is it   |   uptime   |   status   |   find my games   |   scan this PC for corrupt files'),
        ("UPDATE", 'implement jarvis   |   implement jarvis -Dry   |   implement jarvis <file.py>   |   maintenance'),
    ]
    w = max(len(a) for a, _ in rows)
    for a, b in rows:
        out(f"  {a.ljust(w)}  {b}", CYAN)
    out()
    return True


# ---------------- extra readers (all read-only) ----------------
def jv_gm_chunks(path):
    """[(chunk id, data start, data length)] of a GameMaker data file."""
    res = []
    size = os.path.getsize(path)
    with open(path, "rb") as f:
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
    with open(path, "rb") as f:
        f.seek(start)
        cnt = struct.unpack("<I", f.read(4))[0]
    return cnt if cnt * 4 + 4 <= ln else None


def jv_pe(path):
    with open(path, "rb") as f:
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
    with open(path, "rb") as f:
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
            with open(path, "rb") as f:
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
    with open(path, "rb") as f:
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
        with open(path, "rb") as f:
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
                with open(path, "rb") as f:
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


def jarvis_interpret(texto):
    """Map a plain-language request (English or Italian) to a read-only command.
    Returns True if it understood and handled the request."""
    # the word 'jarvis' counts anywhere in the sentence ('apri cry of fear jarvis', 'ehi jarvis apri ...')
    CONTESTO["jv_named"] = bool(re.search(JV_NAMED_RE, texto, re.I)) or bool(CONTESTO.get("jv_cmd"))
    orig = re.sub(r"^(?:(?:hey|ok|okay|hi|hello|ciao|ehi|ehy)[,\s]+)?jarvis\b[,:!\s]*", "",
                  texto.strip(), flags=re.I)
    orig = re.sub(JV_NAMED_RE, " ", orig, flags=re.I)
    orig = re.sub(r"\s{2,}", " ", orig).strip(" ,;:")
    orig = orig.strip().rstrip("?!. ").strip()
    t = orig.lower()
    sel = CONTESTO.get("file")

    def has(*stems):
        return any(re.search(r"\b" + re.escape(s), t) for s in stems)

    if t == "" or t in ("hello", "hi", "hey", "ciao", "salve", "buongiorno", "buonasera",
                        "good morning", "good afternoon", "good evening"):
        jarvis_say(f"{part_of_day()}, sir. At your service.")
        jarvis_status("Current status")
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
                   "starting a game when you say 'jarvis open <game>'.")
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


@cmdlet("Jarvis", group="Assistant", usage="""jarvis <request in plain English or Italian>
  jarvis find my games
  jarvis scan this PC for corrupt files
  jarvis select data.win        then:  jarvis tell me about it / what's inside / how much battery
  jarvis status
  jarvis open data.win          opens it read-only (also: open the 2nd one, open undertale, read notes.txt, go up)
  jarvis open deltarune         STARTS the installed game (jarvis open deltarune chapter 2 picks a chapter)
  open deltarune                without 'jarvis': only shows the data.win read-only, never starts the game
  implement jarvis              update myself (see: help implement)       maintenance   health check
  jarvis how many lines / first 20 lines / search for "word" / sha256 / is it corrupt
  jarvis what game is this / how many sprites / list the chunks      (for a GameMaker data.win)
  jarvis which columns / which tables / how many pages / is it 64-bit / what is inside
  jarvis biggest files / find all png files / duplicates / modified today / free disk space
  jarvis examples               shows everything I can answer
(You can also skip the word 'jarvis': just type the request.)""")
def jarvis_cmd(args):
    """Talk to JARVIS in plain language, e.g.  jarvis find my games"""
    CONTESTO["jv_cmd"] = True            # spoken to Jarvis by name: 'jarvis open <game>' may start a game
    try:
        handled = jarvis_interpret(" ".join(args))
    finally:
        CONTESTO["jv_cmd"] = False
    if not handled:
        jarvis_say("I'm afraid I didn't catch that, sir. Try 'find my games', 'scan this PC', "
                   "'open <file>', 'examples' or 'help'.")


# ======================= JARVIS SELF-UPDATE =======================
# The ONLY code that writes to disk, downloads or restarts lives in functions named jv_upd_*.
# Starting a game lives in jv_launch_*.  An update is REFUSED unless every jv_upd_* / jv_launch_*
# function and every JV_UPD_* / JV_LAUNCH_* constant stays identical (compared on the syntax tree).
JV_UPD_MAX_BYTES = 4 * 1024 * 1024
JV_UPD_SECONDS = 10
JV_UPD_PHASES = ("valid source", "checksum", "syntax", "data block", "security scan",
                 "updater intact", "commands kept", "start test", "start speed")
JV_UPD_PROTECTED = ("jv_upd_", "jv_launch_")
JV_UPD_PROTECTED_CONST = ("JV_UPD_", "JV_LAUNCH_")
JV_UPD_NET = ("urllib", "http", "ftplib", "smtplib", "telnetlib", "requests", "xmlrpc", "ssl", "poplib",
              "imaplib", "paramiko", "websocket", "websockets", "aiohttp", "httpx", "socketserver", "asyncio")
JV_UPD_DYNAMIC = ("importlib", "pickle", "marshal", "shelve", "pty", "multiprocessing", "webbrowser",
                  "code", "codeop", "builtins", "imp", "zipimport", "pkgutil")
JV_UPD_BAD_BUILTINS = ("eval", "exec", "compile", "__import__", "breakpoint")
JV_UPD_BAD_CALLS = (
    "os.remove", "os.unlink", "os.rmdir", "os.removedirs", "os.rename", "os.renames", "os.replace",
    "os.truncate", "os.chmod", "os.chown", "os.mkdir", "os.makedirs", "os.symlink", "os.link", "os.open",
    "os.popen", "os.startfile", "os.kill", "os.killpg", "os.fork", "os.forkpty", "os.putenv", "os.system",
    "shutil.rmtree", "shutil.move", "shutil.copy", "shutil.copy2", "shutil.copyfile", "shutil.copyfileobj",
    "shutil.copytree", "shutil.copymode", "shutil.copystat", "shutil.make_archive", "shutil.unpack_archive",
    "shutil.chown", "sqlite3.connect", "runpy.run_path", "runpy.run_module", "tempfile.mkstemp",
    "tempfile.mkdtemp", "tempfile.NamedTemporaryFile", "tempfile.TemporaryDirectory",
)
JV_UPD_BAD_PREFIX = ("subprocess.", "os.exec", "os.spawn", "os.posix_spawn")
JV_UPD_BAD_METHODS = ("write_text", "write_bytes", "unlink", "rmdir", "mkdir", "touch", "symlink_to",
                      "hardlink_to", "chmod", "rmtree", "removedirs", "makedirs")
JV_UPD_OPENERS = ("open", "io.open", "codecs.open", "gzip.open", "bz2.open", "lzma.open", "tarfile.open",
                  "zipfile.ZipFile", "ZipFile", "os.fdopen")
JV_UPD_MODULES = ("os", "shutil", "sys", "subprocess", "builtins")
# (function, thing) pairs that the existing, read-only code is allowed to do.
JV_UPD_ALLOW = (
    ("pc_roots", "ctypes"), ("system_memory", "ctypes"), ("battery_info", "ctypes"), ("jv_uptime", "ctypes"),
    ("battery_info", "subprocess.run"), ("jv_global", "socket"), ("sqlite_open_ro", "sqlite3.connect"),
    ("carica_estensioni", "runpy.run_path"), ("main", "os.system"),
)
JV_LAUNCH_SKIP = ("unins", "uninstall", "setup", "install", "redist", "vcredist", "dxsetup", "crash", "report",
                  "helper", "updater", "update", "dotnet", "directx", "vc_", "oalinst", "cleanup", "config")
JV_LAUNCH_CHAPTER = r"(?i)(?:chapter|capitolo|cap|ch)[ _.-]?(\d{1,2})(?:[ _-]?(?:windows|win|mac|macos|linux))?"


# ---------------- paths, log ----------------
def jv_upd_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis_update")


def jv_upd_sub(name):
    d = os.path.join(jv_upd_dir(), name)
    os.makedirs(d, exist_ok=True)
    return d


def jv_upd_log(msg):
    try:
        with open(os.path.join(jv_upd_sub("."), "update.log"), "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {msg}\n")
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
    and clumsy code, NOT a guarantee against deliberately hostile code."""
    import ast
    found = []
    seen = set()

    def dotted(n):
        parts = []
        while isinstance(n, ast.Attribute):
            parts.append(n.attr)
            n = n.value
        if isinstance(n, ast.Name):
            parts.append(n.id)
            return ".".join(reversed(parts))
        return None

    def flag(owner, node, key, text):
        if (owner, key) in JV_UPD_ALLOW:
            return
        tag = (owner, key, getattr(node, "lineno", 0))
        if tag not in seen:
            seen.add(tag)
            found.append(f"line {getattr(node, 'lineno', '?')}: {text} (in {owner})")

    for top in tree.body:
        owner = top.name if isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else "<module>"
        if owner.startswith(JV_UPD_PROTECTED):
            continue
        for node in ast.walk(top):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.ImportFrom) and node.level:
                    flag(owner, node, "relative-import", "relative import")
                    continue
                mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
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
            elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                if node.value.id == "ctypes":
                    flag(owner, node, "ctypes", "use of ctypes")
                elif node.value.id == "socket" and node.attr != "gethostname":
                    flag(owner, node, "socket", f"socket.{node.attr}")
            elif isinstance(node, ast.Call):
                f = node.func
                name = dotted(f)
                if isinstance(f, ast.Name) and f.id in JV_UPD_BAD_BUILTINS:
                    flag(owner, node, f.id, f"{f.id}()")
                if isinstance(f, ast.Name) and f.id in ("getattr", "setattr", "delattr") and node.args \
                        and isinstance(node.args[0], ast.Name) and node.args[0].id in JV_UPD_MODULES:
                    flag(owner, node, "getattr", f"{f.id}() on module '{node.args[0].id}'")
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
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    t0 = time.perf_counter()
    try:
        r = subprocess.run([sys.executable, path], input=stdin_text, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=limit, cwd=cwd, env=env)
    except subprocess.TimeoutExpired:
        return None, "", f"did not finish in {limit} s", float(limit)
    except OSError as e:
        return None, "", str(e), 0.0
    return r.returncode, r.stdout, r.stderr, time.perf_counter() - t0


def jv_upd_phase(i, ok, detail=""):
    name = JV_UPD_PHASES[i - 1]
    out(f"  [{i}/{len(JV_UPD_PHASES)}] {name.ljust(15)} {'OK    ' if ok else 'FAILED'} {detail}".rstrip(),
        GREEN if ok else RED)
    return ok


def jv_upd_check(cand, want_sha):
    """The 9 safety phases, in order. Returns (ok, phase name, reason). Installs nothing."""
    import ast
    import tempfile
    me = os.path.abspath(__file__)

    def bad(i, why):
        jv_upd_phase(i, False, why)
        return False, JV_UPD_PHASES[i - 1], why

    # 1 - valid source
    try:
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
    if "def main(" not in src or "__main__" not in src:
        return bad(1, "not a Jarvis program (no main)")
    jv_upd_phase(1, True, human(len(raw)))
    # 2 - checksum
    digest = hashlib.sha256(raw).hexdigest()
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
    """Download a source (https only; plain http only for this computer). Returns bytes or raises ValueError."""
    import urllib.parse
    import urllib.request
    p = urllib.parse.urlparse(url)
    local = (p.hostname or "") in ("localhost", "127.0.0.1", "::1")
    if p.scheme != "https" and not (p.scheme == "http" and local):
        raise ValueError("only https:// links are accepted")
    req = urllib.request.Request(url, headers={"User-Agent": "JARVIS-updater"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = r.read(JV_UPD_MAX_BYTES + 1)
    except OSError as e:
        raise ValueError(f"download failed ({e})")
    if len(data) > JV_UPD_MAX_BYTES:
        raise ValueError("the download is bigger than 4 MB")
    return data


def jv_upd_stage(raw, name):
    """Put the candidate in jarvis_update/work/ (the checks always run on this private copy)."""
    path = os.path.join(jv_upd_sub("work"), f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{jv_upd_safe_name(name)}")
    with open(path, "wb") as f:
        f.write(raw)
    return path


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


def jv_upd_install(cand):
    """Backup the running file, put the candidate in its place, roll back on any trouble. Returns the backup path."""
    me = os.path.abspath(__file__)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = os.path.join(jv_upd_sub("backups"), f"{os.path.splitext(os.path.basename(me))[0]}_{stamp}.py")
    shutil.copy2(me, backup)
    if jv_upd_sha_of(backup) != jv_upd_sha_of(me):
        os.remove(backup)
        raise OSError("the backup is not identical to the original, nothing was changed")
    want = jv_upd_sha_of(cand)
    tmp = me + ".jvnew"
    try:
        shutil.copyfile(cand, tmp)
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
    out(f"UPDATE REFUSED: {why}", RED)
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
        out()
        out(f"Update source: {safe(label)}", CYAN)
        out(f"Running the {len(JV_UPD_PHASES)} safety checks...", GRAY)
        ok, phase, why = jv_upd_check(work, sha)
        if not ok:
            if dry:
                out(f"Dry run: this update would be REFUSED at '{phase}'. Nothing was installed.", RED)
                out()
                return
            jv_upd_countdown(work, incoming, f"check '{phase}' failed: {why}")
            work = None
            return
        if dry:
            out(f"Dry run: all {len(JV_UPD_PHASES)} checks passed. Nothing was installed.", GREEN)
            out()
            return
        try:
            backup = jv_upd_install(work)
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
        out("All checks passed. The new version is installed.", GREEN)
        out(f"Backup of the old version: {safe(backup)}", GRAY)
        out("Restarting Jarvis with the new version...", GRAY)
        jv_upd_restart(False)
    finally:
        if work:
            jv_upd_discard(work)


# ---------------- maintenance (read-only health check) ----------------
@cmdlet("Maintenance", group="Assistant", usage="""maintenance     read-only health check of Jarvis: integrity, security scan, backups, quarantine, last log lines
(it changes nothing; to update, use  implement jarvis)""")
def jv_upd_maintenance_cmd(args):
    """Read-only health check of Jarvis (integrity, security scan, backups, log)."""
    import ast
    me = os.path.abspath(__file__)
    out()
    out("JARVIS maintenance check (read-only)", YELLOW)
    try:
        with open(me, encoding="utf-8") as f:
            src = f.read()
        tree = ast.parse(src)
        out(f"  Program      : {safe(me)}  ({human(len(src.encode('utf-8')))}, sha256 {jv_upd_sha_of(me)[:16]}...)", GREEN)
    except (OSError, SyntaxError, UnicodeDecodeError) as e:
        out(f"  Program      : cannot be checked ({e})", RED)
        out()
        return
    err, data = jv_upd_data_block(src)
    if err:
        out(f"  Data block   : {err}", RED)
    else:
        alive = sum(1 for d in data["game_dirs"] if os.path.isdir(d))
        out(f"  Data block   : version {data['version']}, last update '{data['updated'] or 'never'}', "
            f"{alive}/{len(data['game_dirs'])} learned game folder(s) still there", GREEN)
    found = jv_upd_scan(tree)
    out(f"  Security scan: {'0 violations' if not found else str(len(found)) + ' violation(s), first: ' + found[0]}",
        GREEN if not found else RED)
    prot = jv_upd_protected(tree)
    out(f"  Protected    : {len(prot)} updater/launcher item(s)", GREEN)
    base = jv_upd_dir()

    def count(sub, ext=".py"):
        try:
            return sorted(n for n in os.listdir(os.path.join(base, sub)) if n.lower().endswith(ext))
        except OSError:
            return []
    backups = count("backups")
    out(f"  Backups      : {len(backups)}" + (f", newest {safe(backups[-1])}" if backups else ""),
        GREEN if backups else GRAY)
    out(f"  Quarantine   : {len(count('rejected'))} rejected update(s)", GRAY)
    out(f"  Incoming     : {len(count('incoming'))} update(s) waiting", GRAY)
    try:
        with open(os.path.join(base, "update.log"), encoding="utf-8", errors="replace") as f:
            last = f.read().splitlines()[-5:]
    except OSError:
        last = []
    out("  Last log     : " + ("(none yet)" if not last else ""), GRAY)
    for ln in last:
        out("    " + safe(ln)[:150], GRAY)
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


def prompt():
    base = f"PS {os.getcwd()}> "
    giallo = f"\x01{YELLOW}\x02" if HAS_READLINE else YELLOW
    testo = f"\x01{TEXT}\x02" if HAS_READLINE else TEXT
    return testo + base + giallo


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    os.system("")  # abilita i codici ANSI sul terminale di Windows
    sys.stdout.write("\x1b]0;Jarvis PowerShell\x07" + BG + TEXT + "\x1b[2J\x1b[H")
    out("Jarvis PowerShell")
    out("Copyright (C) Jarvis. All rights reserved.")
    out()
    carica_estensioni()
    jarvis_greeting()
    try:
        while True:
            try:
                riga = input(prompt())
            except EOFError:
                break
            except KeyboardInterrupt:
                out()
                continue
            sys.stdout.write(TEXT)
            esegui(riga)
    except SystemExit:
        pass
    sys.stdout.write("\x1b[0m\x1b[2J\x1b[H")


if __name__ == "__main__":
    main()
