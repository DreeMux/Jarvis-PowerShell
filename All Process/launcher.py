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
"""launcher.py - the Jarvis start screen (black background, terminal font, machine-style typing).

Autore: DreeMux

Lo lancia start.bat. Mostra il messaggio di benvenuto "scritto da una macchina" e un menu:
    Install Guard   ->  guardia sempre attiva (parte con Windows, anche a Jarvis chiuso)
    Delete Guard    ->  toglie la guardia
    Proceed         ->  allinea i moduli (build.py --auto) e apre Jarvis
    Exit            ->  esce

Comandi: frecce su/giu' + INVIO, oppure i tasti 1-4.  Un tasto qualsiasi durante la scrittura la salta.
"""
import os
import random
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PWSH = os.path.join(HERE, "pwsh.py")
BUILD = os.path.join(HERE, "build.py")
IS_WIN = os.name == "nt"

ESC = "\x1b"
BLACK_BG = ESC + "[40m"
GREEN = ESC + "[92m"        # bright green: the "machine" voice
DIM = ESC + "[32m"          # dark green: details
WHITE = ESC + "[97m"        # what YOU choose
RED = ESC + "[91m"
YELLOW = ESC + "[93m"
SEL = ESC + "[30;102m"      # black on bright green: the selected entry
RESET = ESC + "[0m"
CLEAR = ESC + "[2J" + ESC + "[H"
HIDE = ESC + "[?25l"
SHOW = ESC + "[?25h"
LEFT = ESC + "[D"
BLOCK = "█"

MENU = [
    ("Install Guard", "Always-on screen guard: it starts with Windows, even if Jarvis is closed."),
    ("Delete Guard", "Removes the guard: it will not start with Windows any more."),
    ("Proceed", "Opens Jarvis."),
    ("Exit", "Closes this window."),
]


# ---------------------------------------------------------------- terminal basics
def setup_terminal():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if IS_WIN:
        os.system("")                                  # classic trick that turns on ANSI codes
        try:
            import ctypes
            k = ctypes.windll.kernel32
            h = k.GetStdHandle(-11)
            mode = ctypes.c_uint32()
            if k.GetConsoleMode(h, ctypes.byref(mode)):
                k.SetConsoleMode(h, mode.value | 0x0004)   # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        except Exception:
            pass


def w(text):
    sys.stdout.write(text)
    sys.stdout.flush()


# ---------------------------------------------------------------- keyboard (no extra packages)
if IS_WIN:
    import msvcrt

    def raw_on():
        return None

    def raw_off(_state):
        pass

    def key_ready():
        return msvcrt.kbhit()

    def read_key():
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            return {"H": "up", "P": "down", "K": "left", "M": "right"}.get(msvcrt.getwch(), "")
        if ch == "\r":
            return "enter"
        if ch == "\x1b":
            return "esc"
        if ch == "\x03":
            raise KeyboardInterrupt
        return ch.lower()
else:
    import select
    import termios
    import tty

    def raw_on():
        try:
            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            tty.setcbreak(fd)
            return old
        except Exception:
            return None

    def raw_off(state):
        if state is not None:
            try:
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, state)
            except Exception:
                pass

    def key_ready():
        try:
            return bool(select.select([sys.stdin], [], [], 0)[0])
        except Exception:
            return False

    def read_key():
        fd = sys.stdin.fileno()
        b = os.read(fd, 1)
        if b == b"\x1b":
            if select.select([fd], [], [], 0.05)[0]:
                seq = os.read(fd, 2)
                return {b"[A": "up", b"[B": "down", b"[C": "right", b"[D": "left"}.get(seq, "")
            return "esc"
        if b in (b"\r", b"\n"):
            return "enter"
        if b == b"\x03":
            raise KeyboardInterrupt
        return b.decode("utf-8", "ignore").lower()


# ---------------------------------------------------------------- machine-style typing
_skip = [False]


def type_out(text, color=GREEN, delay=0.022, newline=True):
    """Prints text one character at a time, with a block cursor, like a machine answering you.
    Pressing any key skips the animation (the rest of the text appears at once)."""
    w(color)
    for ch in text:
        if not _skip[0] and key_ready():
            read_key()
            _skip[0] = True
            w(" " + LEFT)                              # erase the block cursor
        if _skip[0]:
            w(ch)
            continue
        w(ch + BLOCK + LEFT)
        pause = delay * random.uniform(0.5, 1.6)
        if ch in ",;:":
            pause += 0.12
        elif ch in ".!?":
            pause += 0.25
        time.sleep(pause)
    w(" " + LEFT if not _skip[0] else "")
    w(RESET + BLACK_BG + ("\n" if newline else ""))


def say(text, color=GREEN, delay=0.022):
    type_out(text, color, delay)


def say_fast(text, color=DIM):
    type_out(text, color, delay=0.004)


def pause(sec):
    if not _skip[0]:
        time.sleep(sec)


# ---------------------------------------------------------------- the menu
def menu_lines(idx):
    lines = [""]
    for i, (name, _hint) in enumerate(MENU):
        if i == idx:
            lines.append(f"  {SEL} ▶ {i + 1}. {name:<15}{RESET}{BLACK_BG}")
        else:
            lines.append(f"  {DIM}   {i + 1}. {name}{RESET}{BLACK_BG}")
    lines.append("")
    lines.append(f"  {DIM}{MENU[idx][1]}{RESET}{BLACK_BG}")
    lines.append(f"  {DIM}[up/down] move   [enter] select   [1-4] quick pick{RESET}{BLACK_BG}")
    return lines


def draw_menu(idx, first):
    lines = menu_lines(idx)
    if not first:
        w(ESC + f"[{len(lines)}A")
    w("".join(line + ESC + "[K\n" for line in lines))


def erase_menu():
    n = len(menu_lines(0))
    w(ESC + f"[{n}A" + ESC + "[J")


def choose():
    """Shows the menu and returns the index chosen (None = Esc)."""
    idx = 0
    draw_menu(idx, True)
    while True:
        k = read_key()
        if k == "up":
            idx = (idx - 1) % len(MENU)
        elif k == "down":
            idx = (idx + 1) % len(MENU)
        elif k in ("1", "2", "3", "4"):
            idx = int(k) - 1
            draw_menu(idx, False)
            return idx
        elif k == "enter":
            return idx
        elif k in ("esc", "q"):
            return None
        else:
            continue
        draw_menu(idx, False)


# ---------------------------------------------------------------- the work behind the choices
def run_with_dots(args, label):
    """Runs a helper script, prints 'label...' with moving dots, returns (exit code, output lines)."""
    type_out(label, newline=False)
    env = dict(os.environ, PYTHONUTF8="1")
    p = subprocess.Popen([sys.executable] + args, cwd=HERE, env=env, text=True, encoding="utf-8", errors="replace",
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = []
    import threading
    t = threading.Thread(target=lambda: out.append(p.communicate()[0] or ""), daemon=True)
    t.start()
    n = 0
    while t.is_alive():
        w(GREEN + "." + RESET + BLACK_BG)
        n += 1
        t.join(0.3)
    w("\n")
    lines = [ln for ln in (out[0] if out else "").replace("\r", "").split("\n") if ln.strip()]
    return p.returncode, lines


def sync_modules():
    """build.py --auto: the same check START.bat used to do. 0 = ok, 1 = error, 2 = warning."""
    rc, lines = run_with_dots([BUILD, "--auto"], "Checking Jarvis modules")
    for ln in lines:
        say_fast("  " + ln, RED if rc == 1 else (YELLOW if rc == 2 else DIM))
    return rc


def guard(remove):
    word = "Removing" if remove else "Installing"
    say(f"{word} the guard. One moment.")
    if sync_modules() == 1:
        say("I cannot do it: fix the error above, then try again.", RED)
        return
    rc, lines = run_with_dots([PWSH, "--guard-remove" if remove else "--guard-install"], f"{word} guard")
    for ln in lines:
        say("  " + ln, GREEN if rc == 0 else RED, delay=0.012)
    if rc == 0:
        say("Done.")
    else:
        say("Something went wrong. Details above.", RED)


def proceed():
    """Returns None to go back to the menu, or the exit code of Jarvis."""
    say("Great. Let me get Jarvis ready.")
    rc = sync_modules()
    if rc == 1:
        say("Jarvis will NOT start: fix the error above and try again.", RED)
        return None
    if rc == 2:
        say("There is a warning (see above). Starting anyway.", YELLOW)
        pause(1.5)
    say("Starting Jarvis...")
    pause(0.6)
    w(RESET + CLEAR + SHOW)
    env = dict(os.environ, PYTHONUTF8="1")
    while True:
        try:
            code = subprocess.call([sys.executable, PWSH], cwd=HERE, env=env)
            break
        except KeyboardInterrupt:
            continue
    if code:
        print(f"\n  Jarvis closed with an error (code {code}).")
        try:
            input("  Press ENTER to close. ")
        except (EOFError, KeyboardInterrupt):
            pass
    return code


# ---------------------------------------------------------------- main
def main():
    setup_terminal()
    if not sys.stdin.isatty() or not sys.stdout.isatty():      # no real console: skip the show, just open Jarvis
        return subprocess.call([sys.executable, PWSH], cwd=HERE)
    state = raw_on()
    try:
        w(BLACK_BG + CLEAR + HIDE)
        w("\n")
        for line in ("  J . A . R . V . I . S", "  " + "─" * 40):
            w(GREEN + line + RESET + BLACK_BG + "\n")
            time.sleep(0.12)
        w("\n")
        say("Hi everyone! thanks for using this software, what do you want to do?")
        while True:
            _skip[0] = False
            idx = choose()
            erase_menu()
            if idx is None or MENU[idx][0] == "Exit":
                w(WHITE + "  > " + (MENU[idx][0] if idx is not None else "Exit") + RESET + BLACK_BG + "\n")
                say("See you soon.")
                pause(0.7)
                return 0
            name = MENU[idx][0]
            w(WHITE + f"  > {name}" + RESET + BLACK_BG + "\n")
            _skip[0] = False
            if name == "Install Guard":
                guard(False)
            elif name == "Delete Guard":
                guard(True)
            elif name == "Proceed":
                code = proceed()
                if code is not None:
                    return code
            _skip[0] = False
            w("\n")
            say("Anything else? What do you want to do?")
    except KeyboardInterrupt:
        return 0
    finally:
        raw_off(state)
        w(RESET + SHOW)


if __name__ == "__main__":
    sys.exit(main())
