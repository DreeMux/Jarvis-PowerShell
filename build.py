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
"""build.py - tiene allineati i moduli (src/*.py) e pwsh.py.

Autore: DreeMux

Perche' esiste: Jarvis si controlla, si testa e si aggiorna da solo lavorando su UN SOLO file
(pwsh.py). Per questo pwsh.py resta il file che gira davvero. Il codice invece lo modifichi comodamente
a pezzi in src/. Questo script fa la colla tra i due, in entrambe le direzioni:

    parti modificate in src/        ->  pwsh.py viene ricostruito
    pwsh.py modificato da Jarvis    ->  le parti in src/ vengono aggiornate (con backup)

START.bat lo lancia da solo ogni volta (--auto), quindi di solito non devi fare nulla.

Uso a mano (di norma non serve):
    python build.py            come --auto
    python build.py --check    dice solo se e' tutto allineato
    python build.py --build    forza  src/ -> pwsh.py   (backup del vecchio pwsh.py)
    python build.py --pull     forza  pwsh.py -> src/   (backup della vecchia src/)

Codici di uscita: 0 = ok, 1 = errore (non si avvia nulla), 2 = avviso (Jarvis parte lo stesso).
Nessuna modifica al comportamento: i marcatori '# >>>>> JARVIS-PART ... >>>>>' sono solo commenti.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")
OUT = os.path.join(HERE, "pwsh.py")
STAMP = os.path.join(HERE, ".build_stamp.json")
BACKUP = os.path.join(HERE, "backup")
KEEP_BACKUPS = 10

MARK = re.compile(rb"^# >>>>> JARVIS-PART (\S+) >>>>>[ \t]*\r?\n", re.M)


# ---------------------------------------------------------------- basics
def sha(b):
    return hashlib.sha256(b).hexdigest()


def read(path):
    with open(path, "rb") as f:
        return f.read()


def write(path, data):
    with open(path, "wb") as f:
        f.write(data)


def say(msg=""):
    print(msg, flush=True)


def part_names():
    if not os.path.isdir(SRC):
        return []
    return sorted(n for n in os.listdir(SRC) if n.endswith(".py") and not n.startswith("_"))


def read_parts():
    return [(n, read(os.path.join(SRC, n))) for n in part_names()]


def fix_nl(chunk):
    return chunk if (not chunk or chunk.endswith(b"\n")) else chunk + b"\n"


def build_bytes(parts):
    """parts -> the text of pwsh.py (the first part has no marker, so line 1 stays the shebang)."""
    out = []
    for i, (name, chunk) in enumerate(parts):
        chunk = fix_nl(chunk)
        if i:
            out.append(f"# >>>>> JARVIS-PART {name} >>>>>\n".encode("utf-8"))
        out.append(chunk)
    return b"".join(out)


def strip_markers(b):
    return MARK.sub(b"", b)


def load_stamp():
    try:
        with open(STAMP, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_stamp(final_out, parts):
    anchors = {}
    for n, c in parts:
        first = c.split(b"\n", 1)[0].rstrip(b"\r")
        anchors[n] = first.decode("utf-8", "replace")
    with open(STAMP, "w", encoding="utf-8") as f:
        json.dump({"sha": sha(final_out), "parts": [n for n, _ in parts], "anchors": anchors,
                   "synced": time.strftime("%Y-%m-%d %H:%M:%S")}, f, indent=1)


# ---------------------------------------------------------------- safety net
def locate(lineno, parts):
    """Line number in pwsh.py -> (part name, line inside that part)."""
    pos = 0
    for i, (name, chunk) in enumerate(parts):
        chunk = fix_nl(chunk)
        n = chunk.count(b"\n") + (1 if i else 0)
        if lineno <= pos + n:
            inner = lineno - pos - (1 if i else 0)
            return name, max(inner, 1)
        pos += n
    return "?", lineno


def syntax_ok(data, parts):
    try:
        compile(data, "pwsh.py", "exec", dont_inherit=True)
        return True
    except SyntaxError as e:
        where = ""
        if parts and e.lineno:
            name, inner = locate(e.lineno, parts)
            where = f"  ->  src/{name}, riga {inner}"
        say(f"ERRORE di sintassi: {e.msg} (pwsh.py riga {e.lineno}){where}")
        try:
            say("    " + data.split(b"\n")[e.lineno - 1].decode("utf-8", "replace").strip())
        except (IndexError, TypeError):
            pass
        return False


def backup_file(path, tag):
    if not os.path.isfile(path):
        return
    os.makedirs(BACKUP, exist_ok=True)
    dst = os.path.join(BACKUP, f"{tag}_{time.strftime('%Y%m%d_%H%M%S')}.py")
    shutil.copyfile(path, dst)
    prune(tag)


def backup_src():
    if not os.path.isdir(SRC):
        return
    os.makedirs(BACKUP, exist_ok=True)
    dst = os.path.join(BACKUP, f"src_{time.strftime('%Y%m%d_%H%M%S')}")
    shutil.copytree(SRC, dst)
    prune("src")


def prune(tag):
    try:
        items = sorted(n for n in os.listdir(BACKUP) if n.startswith(tag + "_"))
        for n in items[:-KEEP_BACKUPS]:
            p = os.path.join(BACKUP, n)
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    except OSError:
        pass


# ---------------------------------------------------------------- the two directions
def split_built(data, stamp):
    """pwsh.py -> [(name, chunk)]. Uses the part markers; if an update removed them,
    falls back on the first line of every part (saved in the stamp) as anchor."""
    names = stamp.get("parts") or part_names() or ["01_core.py"]
    ms = list(MARK.finditer(data))
    if ms:
        out = [(names[0], data[:ms[0].start()])]
        for i, m in enumerate(ms):
            end = ms[i + 1].start() if i + 1 < len(ms) else len(data)
            out.append((m.group(1).decode("utf-8", "replace"), data[m.end():end]))
        return out
    anchors = stamp.get("anchors") or {}
    cuts = [(0, names[0])]
    pos = 0
    for n in names[1:]:
        a = anchors.get(n, "").encode("utf-8")
        if not a:
            continue
        idx = data.find(b"\n" + a + b"\n", pos)
        if idx < 0:
            continue                      # section not found: it stays glued to the previous part
        cuts.append((idx + 1, n))
        pos = idx + 1
    out = []
    for i, (start, n) in enumerate(cuts):
        end = cuts[i + 1][0] if i + 1 < len(cuts) else len(data)
        out.append((n, data[start:end]))
    return out


def do_pull(data, stamp):
    """pwsh.py (changed by Jarvis) -> src/. Lossless, with a backup."""
    chunks = split_built(data, stamp)
    rebuilt = build_bytes(chunks)
    if strip_markers(rebuilt) != strip_markers(data):
        say("ERRORE: la divisione di pwsh.py in parti non e' fedele. Non tocco niente.")
        return False
    backup_src()
    os.makedirs(SRC, exist_ok=True)
    for n in part_names():
        os.remove(os.path.join(SRC, n))
    for n, c in chunks:
        write(os.path.join(SRC, n), fix_nl(c))
    final = rebuilt
    if rebuilt != data:                    # markers were missing: put them back (comments only)
        backup_file(OUT, "pwsh")
        write(OUT, rebuilt)
    save_stamp(final, chunks)
    say(f"OK: pwsh.py era stato cambiato (da Jarvis): aggiornate {len(chunks)} parti in src/ (backup in backup/).")
    return True


def do_build(parts, forced=False):
    built = build_bytes(parts)
    if not syntax_ok(built, parts):
        say("pwsh.py NON e' stato toccato.")
        return False
    if forced:
        backup_file(OUT, "pwsh")
    write(OUT, built)
    save_stamp(built, parts)
    say(f"OK: pwsh.py ricostruito da {len(parts)} parti.")
    return True


# ---------------------------------------------------------------- modes
def diagnose():
    """-> (state, cur, built, parts, stamp). state: missing | sync | src | out | conflict"""
    parts = read_parts()
    stamp = load_stamp()
    if not parts:
        return "nosrc", None, None, parts, stamp
    built = build_bytes(parts)
    cur = read(OUT) if os.path.isfile(OUT) else None
    if cur is None:
        return "missing", cur, built, parts, stamp
    cs, bs, last = sha(cur), sha(built), stamp.get("sha")
    if cs == bs:
        return "sync", cur, built, parts, stamp
    if last is None:
        return "conflict", cur, built, parts, stamp
    out_changed, src_changed = cs != last, bs != last
    if out_changed and src_changed:
        return "conflict", cur, built, parts, stamp
    return ("out" if out_changed else "src"), cur, built, parts, stamp


def auto():
    state, cur, built, parts, stamp = diagnose()
    if state == "nosrc":
        if cur is not None:
            say("Nessuna cartella src/: avvio pwsh.py cosi' com'e'.")
            return 2
        say("ERRORE: ne' src/ ne' pwsh.py trovati.")
        return 1
    if state == "sync":
        if stamp.get("sha") != sha(cur):
            save_stamp(cur, parts)
        return 0
    if state in ("missing", "src"):
        return 0 if do_build(parts) else 1
    if state == "out":
        return 0 if do_pull(cur, stamp) else 2
    say("ATTENZIONE: src/ e pwsh.py sono stati cambiati tutti e due (o manca il registro di sync).")
    say("Avvio pwsh.py cosi' com'e', senza toccare niente. Per scegliere:")
    say("    python build.py --build   tiene src/   (pwsh.py viene sostituito, backup in backup/)")
    say("    python build.py --pull    tiene pwsh.py (src/ viene sostituita, backup in backup/)")
    return 2


def check():
    state, cur, built, parts, stamp = diagnose()
    msg = {"sync": "Tutto allineato: src/ e pwsh.py coincidono.",
           "src": "src/ e' piu' nuova: pwsh.py va ricostruito (--build o avvio con START.bat).",
           "out": "pwsh.py e' piu' nuovo (l'ha cambiato Jarvis): src/ va aggiornata (--pull o START.bat).",
           "missing": "pwsh.py manca: verra' ricostruito.",
           "conflict": "Conflitto: cambiati tutti e due. Scegli --build o --pull.",
           "nosrc": "Manca src/."}[state]
    say(msg)
    return 0 if state == "sync" else 1


def main():
    ap = argparse.ArgumentParser(description="src/ <-> pwsh.py")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--auto", action="store_true", help="allinea nella direzione giusta (default)")
    g.add_argument("--check", action="store_true", help="dice solo se e' tutto allineato")
    g.add_argument("--build", action="store_true", help="forza src/ -> pwsh.py")
    g.add_argument("--pull", action="store_true", help="forza pwsh.py -> src/")
    a = ap.parse_args()
    if a.check:
        return check()
    if a.build:
        parts = read_parts()
        if not parts:
            say("ERRORE: src/ e' vuota o manca.")
            return 1
        return 0 if do_build(parts, forced=True) else 1
    if a.pull:
        if not os.path.isfile(OUT):
            say("ERRORE: pwsh.py non c'e'.")
            return 1
        return 0 if do_pull(read(OUT), load_stamp()) else 1
    return auto()


if __name__ == "__main__":
    sys.exit(main())
