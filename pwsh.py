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
"""pwsh.py - JARVIS: a Windows-PowerShell-style shell with a read-only file assistant.

Run:  python pwsh.py      (Windows: double-click START.bat)
Type  help  or just talk to it:  "find my games", "scan this PC for corrupt files".

All the file tools are READ-ONLY: they never write, move, execute or delete your files.
The ONLY thing JARVIS ever writes is its own program (pwsh.py) plus the folders
updates/ and backups/ next to it, and only through the self-update system:
    maintenance            health check + validation of pending updates (changes nothing)
    maintenance -Prepare   make updates/pwsh_next.py (a copy with the version bumped)
    implement jarvis       validate the newest update in updates/ and install it
    implement jarvis -DryRun | -Rollback | <file>
Optional: pip install psutil  (live memory/CPU of a running game in pluton.key).
Optional extensions: put .py files in a folder named ext/ next to this file.
"""

import ast
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
import shlex
import shutil
import sqlite3
import stat
import struct
import subprocess
import sys
import tempfile
import time
import zipfile
import zlib
from datetime import datetime

# ---------------- COLORI ORIGINALI (console Windows PowerShell) ----------------
def fg(r, g, b): return f"\x1b[38;2;{r};{g};{b}m"
def bg(r, g, b): return f"\x1b[48;2;{r};{g};{b}m"

BG      = bg(1, 36, 86)          # #012456 blu PowerShell
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
    jarvis_say('You can also just tell me what you need, sir: "find my games", "scan this PC", "select <file>".')
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
    jarvis_say(f"Hunter, game locator, file inspector and resource monitor are standing by (v{__version__}). "
               "Your files are only ever read. I write nothing but my own updates, on 'implement jarvis'.")
    jarvis_status("Current status")
    jarvis_say('Type "help" for commands, or just tell me what you need: '
               '"find my games", "scan this PC for corrupt files".')
    out()


def jarvis_interpret(texto):
    """Map a plain-language request (English or Italian) to a read-only command.
    Returns True if it understood and handled the request."""
    orig = re.sub(r"^(?:(?:hey|ok|okay|hi|hello|ciao)[,\s]+)?jarvis\b[,:!\s]*", "",
                  texto.strip(), flags=re.I)
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
    if has("thank", "grazie"):
        jarvis_say("My pleasure, sir.")
        return True
    if has("who are you", "chi sei", "your name"):
        jarvis_say("I am JARVIS, your file assistant. I hunt corrupt files, locate the data.win of your "
                   "games and report on memory and battery. I never modify, move or delete anything.")
        return True
    if has("how are you", "come stai"):
        jarvis_say("Operating at full capacity, sir. Thank you for asking.")
        return True
    if has("maintenance", "manutenzione", "update yourself", "self-update", "self update",
           "aggiornati", "autoaggiorn", "check for updates", "controlla aggiornamenti"):
        ack("Running maintenance: health check and pending updates.")
        esegui("maintenance")
        return True
    if re.match(r"implement\s+jarvis\b", t):
        esegui(orig)
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

    m = re.match(r"(?:please\s+)?(?:select|choose|pick|use|seleziona|scegli|open|apri)\s+"
                 r"(?:the\s+|il\s+)?(?:file\s+)?[\"']?(.+?)[\"']?$", orig, re.I)
    if m:
        cand = m.group(1).strip()
        try:
            names = os.listdir(".")
        except OSError:
            names = []
        match = next((n for n in names if n.lower() == cand.lower()), None) or (cand if os.path.exists(cand) else None)
        if match is None:
            jarvis_say(f"I can't find '{safe(cand)}' in this folder, sir. Say 'list' to see what is here.")
        else:
            ack()
            esegui(f'cd "{match}"')
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
(You can also skip the word 'jarvis': just type the request.)""")
def jarvis_cmd(args):
    """Talk to JARVIS in plain language, e.g.  jarvis find my games"""
    if not jarvis_interpret(" ".join(args)):
        jarvis_say("I'm afraid I didn't catch that, sir. Try 'find my games', 'scan this PC', "
                   "'select <file>' or 'help'.")


# ======================= SELF-UPDATE (maintenance + implement jarvis) =======================
# The ONLY code allowed to touch the disk or start processes lives in the functions listed in
# WRITER_FUNCS / PROC_FUNCS below. Every candidate update is checked by the static rules
# (rule_violations) and run through a self-test BEFORE it can replace this file. These checks are
# guardrails against mistakes, not a sandbox: only install updates you trust.
__version__ = "1.1.0"

APP_PATH = os.path.abspath(__file__)
APP_DIR = os.path.dirname(APP_PATH)
UPD_DIR = os.path.join(APP_DIR, "updates")
BAK_DIR = os.path.join(APP_DIR, "backups")
MAX_UPDATE = 5 * 1024 * 1024
CONFIRM_SECONDS = 10
SELFTEST_TIMEOUT = 30

REQUIRED_FUNCS = {"main", "esegui", "cmdlet", "jarvis_interpret", "static_checks", "rule_violations",
                  "validate_update", "apply_update", "restore_backup", "jarvis_implement",
                  "reject_and_respawn", "selftest"}
REQUIRED_CMDLETS = {"extract.port", "interact.port", "denux.hunter", "undersopic.key", "pluton.key",
                    "Jarvis", "Implement", "Maintenance", "Get-Help", "Exit"}
BANNED_IMPORTS = {"socket", "urllib", "urllib2", "http", "ftplib", "smtplib", "telnetlib", "requests",
                  "xmlrpc", "ssl", "webbrowser", "pickle", "marshal", "importlib", "imp", "builtins"}
BANNED_CALLS = {"eval", "exec", "compile", "__import__"}
BANNED_PAIRS = {("os", "system"), ("os", "popen"), ("os", "startfile"), ("shutil", "rmtree")}
FS_MUTATORS = {("os", "remove"), ("os", "unlink"), ("os", "rmdir"), ("os", "removedirs"),
               ("os", "replace"), ("os", "rename"), ("os", "makedirs"), ("os", "mkdir"),
               ("os", "chmod"), ("os", "truncate"), ("shutil", "copy"), ("shutil", "copy2"),
               ("shutil", "copyfile"), ("shutil", "move"), ("shutil", "copytree")}
FS_ATTRS = {"unlink", "write_text", "write_bytes", "rmdir", "touch", "mkdir", "rename"}
PROC_OS = {"_exit", "execv", "execl", "execvp", "execlp", "spawnl", "spawnv"}
GUARDED_ROOTS = {"os", "shutil", "subprocess"}
WRITER_FUNCS = {"write_atomic", "apply_update", "restore_backup", "archive_candidate",
                "discard_candidate", "prepare_candidate", "selftest_candidate"}
PROC_FUNCS = {"battery_info", "selftest_candidate", "respawn_window", "restart_same_window"}


def file_sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def ver_tuple(s):
    return tuple(int(x) for x in s.split("."))


class _RuleVisitor(ast.NodeVisitor):
    """Collects every construct a JARVIS update is not allowed to contain."""

    def __init__(self):
        self.bad, self.stack = [], []

    def where(self):
        return self.stack[0] if self.stack else "<module>"

    def add(self, node, why):
        self.bad.append(f"line {getattr(node, 'lineno', '?')}: {why}")

    def visit_FunctionDef(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Import(self, node):
        for a in node.names:
            root = a.name.split(".")[0]
            if root in BANNED_IMPORTS:
                self.add(node, f"forbidden module '{root}'")
            if root in GUARDED_ROOTS and a.asname:
                self.add(node, f"aliased import of '{root}'")

    def visit_ImportFrom(self, node):
        root = (node.module or "").split(".")[0]
        if root in BANNED_IMPORTS:
            self.add(node, f"forbidden module '{root}'")
        elif root in GUARDED_ROOTS:
            self.add(node, f"'from {root} import ...' is not allowed (use {root}.name)")

    def visit_Call(self, node):
        f, where = node.func, self.where()
        if isinstance(f, ast.Name):
            if f.id in BANNED_CALLS:
                self.add(node, f"call to {f.id}()")
            elif f.id == "open":
                mode = node.args[1] if len(node.args) > 1 else next(
                    (k.value for k in node.keywords if k.arg == "mode"), None)
                if mode is not None and where not in WRITER_FUNCS:
                    if not (isinstance(mode, ast.Constant) and isinstance(mode.value, str)):
                        self.add(node, "open() with a non-literal mode outside the update machinery")
                    elif any(c in mode.value for c in "wax+"):
                        self.add(node, f"open() for writing in '{where}'")
        elif isinstance(f, ast.Attribute):
            base = f.value.id if isinstance(f.value, ast.Name) else None
            pair = (base, f.attr)
            if pair in BANNED_PAIRS:
                quiet = (pair == ("os", "system") and where == "main" and len(node.args) == 1
                         and isinstance(node.args[0], ast.Constant) and node.args[0].value == "")
                if not quiet:
                    self.add(node, f"forbidden call {base}.{f.attr}()")
            elif (pair in FS_MUTATORS or f.attr in FS_ATTRS) and where not in WRITER_FUNCS:
                self.add(node, f"file modification '{f.attr}' in '{where}' (read-only code)")
            elif (base == "subprocess" or (base == "os" and f.attr in PROC_OS)) and where not in PROC_FUNCS:
                self.add(node, f"process control '{base}.{f.attr}' in '{where}'")
        self.generic_visit(node)


def rule_violations(tree):
    v = _RuleVisitor()
    v.visit(tree)
    return v.bad


def _declared_version(tree):
    for n in tree.body:
        if (isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
                and n.targets[0].id == "__version__" and isinstance(n.value, ast.Constant)
                and isinstance(n.value.value, str) and re.fullmatch(r"\d+(\.\d+){1,3}", n.value.value)):
            return n.value.value
    return None


def static_checks(path, current_version=None):
    """Phases 1-5 (nothing is executed). Returns [(phase, ok, detail)]."""
    res = []
    try:
        size = os.path.getsize(path)
        if size == 0 or size > MAX_UPDATE:
            return [("File", False, f"size {human(size)} is not acceptable (max {human(MAX_UPDATE)})")]
        with open(path, "rb") as f:
            src = f.read().decode("utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return [("File", False, f"cannot read it as UTF-8 text ({safe(e)})")]
    res.append(("File", True, f"{human(size)}, UTF-8 text"))
    try:
        tree = ast.parse(src, filename=os.path.basename(path))
    except (SyntaxError, ValueError, RecursionError) as e:
        res.append(("Syntax", False, safe(e)))
        return res
    res.append(("Syntax", True, "valid Python"))

    ver = _declared_version(tree)
    if ver is None:
        res.append(("Version", False, 'must declare  __version__ = "X.Y.Z"'))
    elif current_version and ver_tuple(ver) <= ver_tuple(current_version):
        res.append(("Version", False, f"{ver} is not newer than the installed {current_version}"))
    else:
        res.append(("Version", True, ver + (f" (installed: {current_version})" if current_version else "")))

    funcs = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    cmds = set()
    for n in tree.body:
        if isinstance(n, ast.FunctionDef):
            for d in n.decorator_list:
                if (isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "cmdlet"
                        and d.args and isinstance(d.args[0], ast.Constant)):
                    cmds.add(d.args[0].value)
    guard = any(isinstance(n, ast.If) and isinstance(n.test, ast.Compare)
                and isinstance(n.test.left, ast.Name) and n.test.left.id == "__name__" for n in tree.body)
    missing = sorted(REQUIRED_FUNCS - funcs) + sorted("command " + c for c in REQUIRED_CMDLETS - cmds)
    if not guard:
        missing.append("the __main__ guard")
    res.append(("Structure", not missing,
                "all core functions, commands and safeguards are present" if not missing
                else "missing: " + ", ".join(missing)))

    bad = rule_violations(tree)
    res.append(("Safety rules", not bad,
                "no forbidden code" if not bad
                else f"{len(bad)} violation(s):\n" + "\n".join(bad[:8]) + ("\n..." if len(bad) > 8 else "")))
    return res


def selftest_candidate(path):
    """Phase 6: run the candidate's own --selftest in an isolated interpreter and a throw-away folder."""
    try:
        with tempfile.TemporaryDirectory(prefix="jarvis_selftest_") as tmp:
            dst = os.path.join(tmp, "pwsh.py")
            with open(path, "rb") as s, open(dst, "wb") as d:
                d.write(s.read())
            r = subprocess.run([sys.executable, "-I", dst, "--selftest"], cwd=tmp, stdin=subprocess.DEVNULL,
                               capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=SELFTEST_TIMEOUT)
    except subprocess.TimeoutExpired:
        return [("Self-test", False, f"timed out after {SELFTEST_TIMEOUT} s")]
    except OSError as e:
        return [("Self-test", False, f"could not run it ({safe(e)})")]
    ok = r.returncode == 0 and "SELFTEST-OK" in r.stdout
    if ok:
        return [("Self-test", True, "the new version starts and passes its own checks")]
    tail = (r.stderr.strip() or r.stdout.strip()).splitlines()[-4:]
    return [("Self-test", False, safe(" | ".join(tail)) or f"exit code {r.returncode}")]


def validate_update(path, require_newer=True):
    """All six phases. The candidate is only EXECUTED (phase 6) if phases 1-5 passed."""
    phases = static_checks(path, __version__ if require_newer else None)
    if all(p[1] for p in phases):
        phases += selftest_candidate(path)
    return all(p[1] for p in phases), phases


def selftest():
    """Run by the update validator on a candidate:  python -I pwsh.py --selftest"""
    problems = []
    for n in REQUIRED_CMDLETS:
        if n.lower() not in CMDLETS:
            problems.append(f"command {n} is not registered")
    if tokenize('a "b c"') != ["a", "b c"]:
        problems.append("tokenize is broken")
    if parse(["-Force", "x"]) != ({"-force"}, ["x"]):
        problems.append("parse is broken")
    if _declared_version(ast.parse('__version__ = "1.0"')) != "1.0":
        problems.append("version reader is broken")
    # canaries: the rule checker must still catch bad code and accept clean code
    if not rule_violations(ast.parse("import socket\nos.remove('x')\neval('1')")):
        problems.append("rule checker no longer detects forbidden code")
    if rule_violations(ast.parse("x = 1\n")):
        problems.append("rule checker rejects harmless code")
    try:
        mine = static_checks(APP_PATH)
        problems += [f"{p[0]}: {p[2]}" for p in mine if not p[1]]
    except Exception as e:
        problems.append(f"static checks crashed: {e}")
    if problems:
        print("SELFTEST-FAIL: " + "; ".join(problems))
        return 1
    print("SELFTEST-OK")
    return 0


# ---- the only functions that write files or start processes ----
def write_atomic(path, data):
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def inside_updates(path):
    p = os.path.normcase(os.path.realpath(path))
    return p.startswith(os.path.normcase(os.path.realpath(UPD_DIR)) + os.sep)


def archive_candidate(path, sub):
    """Move a candidate from updates/ into updates/<sub>/ (kept, never deleted). Files elsewhere are left alone."""
    if not inside_updates(path):
        return None
    folder = os.path.join(UPD_DIR, sub)
    os.makedirs(folder, exist_ok=True)
    dst = os.path.join(folder, datetime.now().strftime("%Y%m%d_%H%M%S_") + os.path.basename(path))
    os.replace(path, dst)
    return dst


def discard_candidate(path):
    """Delete a rejected candidate - only if it lives in updates/ (your other files are never touched)."""
    if not inside_updates(path):
        return False
    os.remove(path)
    return True


def restore_backup(bak):
    with open(bak, "rb") as f:
        write_atomic(APP_PATH, f.read())


def apply_update(src, label="update"):
    """Back up the running version, install src, verify it, roll back on any problem. True on success."""
    with open(src, "rb") as f:
        new = f.read()
    os.makedirs(BAK_DIR, exist_ok=True)
    bak = os.path.join(BAK_DIR, f"pwsh_v{__version__}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.py")
    shutil.copy2(APP_PATH, bak)
    if file_sha(bak) != file_sha(APP_PATH):
        out("Backup verification failed: nothing was changed.", RED)
        return False
    try:
        write_atomic(APP_PATH, new)
        broken = [p for p in static_checks(APP_PATH) if not p[1]]
        if broken or file_sha(APP_PATH) != hashlib.sha256(new).hexdigest().upper():
            raise OSError("the installed file did not verify")
    except Exception as e:
        restore_backup(bak)
        out(f"Install failed ({safe(e)}): the previous version was restored from the backup.", RED)
        return False
    out(f"Backup of the old version: {safe(bak)}", GRAY)
    if label == "update":
        archive_candidate(src, "applied")
    return True


def prepare_candidate():
    """Create updates/pwsh_next.py = this program with the patch number raised. Returns (path, version)."""
    os.makedirs(UPD_DIR, exist_ok=True)
    dst = os.path.join(UPD_DIR, "pwsh_next.py")
    if os.path.exists(dst):
        return None
    with open(APP_PATH, "r", encoding="utf-8", newline="") as f:
        src = f.read()
    m = re.search(r'^__version__ = "(\d+)\.(\d+)\.(\d+)"', src, re.M)
    if not m:
        return None
    new = f"{m[1]}.{m[2]}.{int(m[3]) + 1}"
    with open(dst, "w", encoding="utf-8", newline="") as f:
        f.write(src[:m.start()] + f'__version__ = "{new}"' + src[m.end():])
    return dst, new


def restart_same_window():
    sys.stdout.write("\x1b[0m")
    sys.stdout.flush()
    if os.name == "nt":
        os._exit(subprocess.call([sys.executable, APP_PATH]))
    os.execv(sys.executable, [sys.executable, APP_PATH])


def respawn_window():
    """Open a brand-new window running JARVIS and close this one. No terminal found: restart in place."""
    cmd, here, spawned = [sys.executable, APP_PATH], os.getcwd(), False
    try:
        if os.name == "nt":
            subprocess.Popen(cmd, cwd=here, creationflags=0x00000010)      # CREATE_NEW_CONSOLE
            spawned = True
        elif sys.platform == "darwin":
            line = "cd " + shlex.quote(here) + " && " + " ".join(shlex.quote(c) for c in cmd)
            esc = line.replace("\\", "\\\\").replace('"', '\\"')
            subprocess.Popen(["osascript", "-e", f'tell application "Terminal" to do script "{esc}"'])
            spawned = True
        else:
            for term in (["x-terminal-emulator", "-e"], ["gnome-terminal", "--"], ["konsole", "-e"],
                         ["xfce4-terminal", "-e"], ["xterm", "-e"]):
                if shutil.which(term[0]):
                    subprocess.Popen(term + cmd, cwd=here)
                    spawned = True
                    break
    except OSError:
        spawned = False
    if spawned:
        sys.stdout.write("\x1b[0m")
        sys.stdout.flush()
        os._exit(0)
    restart_same_window()


# ---- the interactive parts ----
def ask_timeout(seconds):
    """Read one line, but give up after `seconds`. Returns the text, or None on timeout / end of input."""
    sys.stdout.write("> ")
    sys.stdout.flush()
    end = time.monotonic() + seconds
    if os.name == "nt":
        import msvcrt
        buf = ""
        while time.monotonic() < end:
            if msvcrt.kbhit():
                ch = msvcrt.getwche()
                if ch in ("\r", "\n"):
                    sys.stdout.write("\n")
                    return buf
                buf = buf[:-1] if ch == "\b" else buf + ch
            else:
                time.sleep(0.05)
        sys.stdout.write("\n")
        return None
    import select
    while True:
        left = end - time.monotonic()
        if left <= 0:
            sys.stdout.write("\n")
            return None
        ready, _, _ = select.select([sys.stdin], [], [], left)
        if ready:
            line = sys.stdin.readline()
            return line.rstrip("\r\n") if line else None


def show_phases(phases):
    for name, ok, detail in phases:
        lines = detail.split("\n")
        out(f"  [{' OK ' if ok else 'FAIL'}] {name.ljust(13)} {lines[0]}", GREEN if ok else RED)
        for extra in lines[1:]:
            out(" " * 22 + extra, RED)


def pending_updates():
    try:
        names = [os.path.join(UPD_DIR, n) for n in os.listdir(UPD_DIR)
                 if n.lower().endswith(".py") and os.path.isfile(os.path.join(UPD_DIR, n))]
    except OSError:
        return []
    return sorted(names, key=os.path.getmtime, reverse=True)


def list_backups():
    try:
        names = [os.path.join(BAK_DIR, n) for n in os.listdir(BAK_DIR)
                 if n.startswith("pwsh_v") and n.endswith(".py")]
    except OSError:
        return []
    return sorted(names, key=os.path.getmtime, reverse=True)


def live_is_intact():
    return all(p[1] for p in static_checks(APP_PATH))


def reject_and_respawn(src, phases):
    """A candidate broke the safety phases: self-destruct this window, open a fresh intact one."""
    out()
    out("UPDATE REJECTED: it does not respect the safety phases. The installed version was NOT touched.", RED)
    show_phases(phases)
    out()
    jarvis_say("This window will now self-destruct and a fresh, intact JARVIS will open.")
    jarvis_say(f"Type  delete  within {CONFIRM_SECONDS} seconds to also delete the rejected update; "
               "otherwise it is kept in updates/rejected/.")
    answer = ask_timeout(CONFIRM_SECONDS)
    try:
        if answer is not None and answer.strip().lower() == "delete":
            if discard_candidate(src):
                jarvis_say("Rejected update deleted.")
            else:
                jarvis_say("That file is not inside updates/, so I left it untouched.")
        else:
            kept = archive_candidate(src, "rejected")
            jarvis_say("No 'delete' received: the rejected update is kept for inspection."
                       if kept else "No 'delete' received. The file is outside updates/, left untouched.")
    except OSError as e:
        out(f"Could not clean up the rejected update ({safe(e)}).", YELLOW)
    if not live_is_intact():
        baks = list_backups()
        if baks:
            restore_backup(baks[0])
            jarvis_say("The installed file looked damaged: restored from the latest backup.")
    jarvis_say("Goodbye, sir. Back in a moment.")
    respawn_window()


def jarvis_implement(src=None, dry=False, allow_older=False):
    """Validate an update and, if it passes every phase, install it (old version is backed up)."""
    if src is None:
        found = pending_updates()
        if not found:
            jarvis_say("There is no update in updates/, sir. Put the new pwsh.py there "
                       "(or run  maintenance -Prepare  for a ready-made candidate).")
            return
        src = found[0]
    if not os.path.isfile(src):
        jarvis_say(f"I can't find the update file '{safe(src)}', sir.")
        return
    ack(f"Validating {safe(os.path.basename(src))} before touching anything.")
    ok, phases = validate_update(src, require_newer=not allow_older)
    out()
    show_phases(phases)
    out()
    if not ok:
        if dry or allow_older:
            jarvis_say("That file does not pass the safety phases, sir. Nothing was changed.")
            return
        reject_and_respawn(src, phases)
        return
    if dry:
        jarvis_say("All phases passed. Dry run: nothing was installed.")
        return
    if os.path.normcase(os.path.realpath(src)) == os.path.normcase(APP_PATH) or file_sha(src) == file_sha(APP_PATH):
        jarvis_say("That is identical to the running version, sir. Nothing to do.")
        return
    jarvis_say("All phases passed. Installing, with a copy of the old version.")
    if apply_update(src, "rollback" if allow_older else "update"):
        jarvis_say("Update installed and verified. Restarting with the new version...")
        out()
        restart_same_window()


@cmdlet("Implement", group="Assistant", usage="""implement jarvis                  validate the newest file in updates/ and install it if every phase passes
implement jarvis <file>           same, for a specific file
implement jarvis -DryRun          only validate, install nothing
implement jarvis -Rollback        go back to the latest backup in backups/
Phases: file, syntax, version (must be newer), structure, safety rules, self-test.
If an update fails them, the window self-destructs and a fresh intact one opens
(type delete within 10 seconds to also delete the rejected file).
A copy of the old version is always kept in backups/.""")
def implement_cmd(args):
    """Install a JARVIS update after validating it (keeps a backup of the old version)"""
    flags, pos = parse(args)
    if not pos or pos[0].lower() != "jarvis":
        out("Usage: implement jarvis [file] [-DryRun | -Rollback]", YELLOW)
        out()
        return
    if "-rollback" in flags:
        baks = list_backups()
        if not baks:
            jarvis_say("There is no backup to roll back to, sir.")
            return
        jarvis_implement(baks[0], allow_older=True)
        return
    src = " ".join(pos[1:]) if len(pos) > 1 else None
    if src and not os.path.exists(src) and os.path.exists(os.path.join(UPD_DIR, src)):
        src = os.path.join(UPD_DIR, src)
    jarvis_implement(src, dry="-dryrun" in flags)


@cmdlet("Maintenance", "update-jarvis", group="Assistant", usage="""maintenance             health check of JARVIS itself, extensions, backups and pending updates
maintenance -Prepare    create updates/pwsh_next.py (this program, patch number +1) to edit and then install
(maintenance never installs anything: use  implement jarvis )""")
def maintenance_cmd(args):
    """JARVIS self-check: health, real system data, backups and pending updates"""
    flags, _ = parse(args)
    if "-prepare" in flags:
        made = prepare_candidate()
        if made:
            jarvis_say(f"Candidate created: {safe(made[0])}  (version {made[1]}). Edit it, then run  implement jarvis.")
        else:
            jarvis_say("I could not create updates/pwsh_next.py (it already exists, or the version line is missing).")
        return
    out()
    out(f"JARVIS v{__version__}", CYAN)
    out(f"  {safe(APP_PATH)}", GRAY)
    try:
        out(f"  SHA256 {file_sha(APP_PATH)}", GRAY)
    except OSError:
        pass
    out()
    out("HEALTH OF THE INSTALLED FILE", YELLOW)
    show_phases(static_checks(APP_PATH))
    out()
    ext = os.path.join(APP_DIR, "ext")
    if os.path.isdir(ext):
        out("EXTENSIONS (ext/)", YELLOW)
        for n in sorted(os.listdir(ext)):
            if n.endswith(".py") and not n.startswith("_"):
                try:
                    with open(os.path.join(ext, n), "rb") as f:
                        ast.parse(f.read())
                    out(f"  [ OK ] {safe(n)}", GREEN)
                except (OSError, SyntaxError, ValueError) as e:
                    out(f"  [FAIL] {safe(n)}: {safe(e)}", RED)
        out()
    out("SYSTEM (real data)", YELLOW)
    jarvis_status("Right now")
    try:
        du = shutil.disk_usage(APP_DIR)
        out(f"  Disk with JARVIS      : {human(du.free)} free of {human(du.total)}")
    except OSError:
        pass
    try:
        import psutil  # noqa: F401
        out("  psutil                : installed (live memory/CPU available)")
    except ImportError:
        out("  psutil                : not installed (pip install psutil for live memory/CPU)", GRAY)
    out(f"  Python                : {sys.version.split()[0]}")
    out()
    baks = list_backups()
    out("BACKUPS", YELLOW)
    out(f"  {len(baks)} backup(s)" + (f", latest: {safe(os.path.basename(baks[0]))}" if baks else ""))
    out()
    pend = pending_updates()
    out("PENDING UPDATES (updates/)", YELLOW)
    if not pend:
        out("  none")
    for p in pend:
        ok, phases = validate_update(p)
        out(f"  {safe(os.path.basename(p))}: " + ("READY - run  implement jarvis" if ok else "would be REJECTED"),
            GREEN if ok else RED)
        if not ok:
            show_phases([x for x in phases if not x[1]])
    out()


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
    if "--selftest" in sys.argv[1:]:
        raise SystemExit(selftest())
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    os.system("")  # abilita i codici ANSI sul terminale di Windows
    sys.stdout.write("\x1b]0;Windows PowerShell\x07" + BG + TEXT + "\x1b[2J\x1b[H")
    out("Windows PowerShell")
    out("Copyright (C) Microsoft Corporation. All rights reserved.")
    out()
    out("Install the latest PowerShell for new features and improvements! "
        "https://aka.ms/PSWindows")
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
