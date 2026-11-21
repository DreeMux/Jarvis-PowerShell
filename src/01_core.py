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


