# ---------------- CLAUDE CODE BRIDGE (version 3.2.0) ----------------
# When a request is not one of Jarvis' own commands, it is handed to the Claude Code CLI in the background
# (hidden window, no separate terminal) and the answer is pasted here under the name JARVIS.
#
# Rules of this bridge:
#   * only the installed 'claude' command is used: no other model, no other provider, no API key of its own;
#   * the model is whatever Claude Code is configured to use (the same model you run Claude Code with).
#     Set JARVIS_CLAUDE_MODEL to pin a different one, e.g.  set JARVIS_CLAUDE_MODEL=sonnet
#   * tools are disabled (--tools ""): the answer is text only, so nothing on disk is read, changed or run;
#   * 'implement' and 'hack' never pass through here: they keep their own functions;
#   * Jarvis' own self-tests never start Claude Code (maintenance, hack yourself, update start test).
#
# Commands:   claude <question> | claude status | claude on | claude off | claude model <name>
# Plain 'jarvis <question>' that Jarvis cannot answer locally does the same automatically.

import shlex

JV_CLAUDE = {
    "auto": True,
    "bin": (os.environ.get("JARVIS_CLAUDE_BIN") or "claude").strip(),
    "extra": (os.environ.get("JARVIS_CLAUDE_ARGS") or "").strip(),
    "model": (os.environ.get("JARVIS_CLAUDE_MODEL") or "").strip(),
    "timeout": 180,
}
try:
    JV_CLAUDE["timeout"] = max(30, min(1800, int(os.environ.get("JARVIS_CLAUDE_TIMEOUT", "180"))))
except (TypeError, ValueError):
    pass

JV_CLAUDE_STYLE = ("You are JARVIS, the user's local assistant. Answer the request directly in plain text, "
                   "in the language of the request. Do not use a fixed template and do not mention Claude Code.")


def jv_claude_test_mode():
    """True while Jarvis is testing itself: never start an external model during a self-test."""
    if CONTESTO.get("jv_nolog") or CONTESTO.get("jv_launch_dry"):
        return True
    return type(sys.stdout).__name__ == "JvSink"


def jv_claude_exe():
    """The Claude Code command, or None. Only what is on PATH (or JARVIS_CLAUDE_BIN)."""
    b = JV_CLAUDE["bin"]
    if not b:
        return None
    if os.path.dirname(b):
        return b if os.path.isfile(b) else None
    return shutil.which(b) or shutil.which(b + ".exe") or shutil.which(b + ".cmd") or shutil.which(b + ".bat")


def jv_claude_available():
    """True when the bridge can actually be used right now (no process is started)."""
    return bool(JV_CLAUDE["auto"] and not jv_claude_test_mode() and jv_claude_exe())


def jv_claude_base_argv(exe):
    """The command line shared by every attempt: extra user flags first, then the model and the safe switches."""
    argv = [exe]
    if JV_CLAUDE["extra"]:
        try:
            argv += shlex.split(JV_CLAUDE["extra"])
        except ValueError:
            argv += JV_CLAUDE["extra"].split()
    if JV_CLAUDE["model"]:
        argv += ["--model", JV_CLAUDE["model"]]
    argv += ["--append-system-prompt", JV_CLAUDE_STYLE, "--tools", "", "--no-session-persistence"]
    return argv


def jv_claude_clean(text):
    """Paste the answer as it came, minus terminal control codes and with a sane upper bound."""
    s = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", str(text))
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", s)
    s = s.replace("\r\n", "\n").replace("\r", "\n").strip()
    return s[:40000]


def jv_claude_stream_text(so):
    """Read the JSON stream of 'claude --output-format stream-json' and return (text, tool names)."""
    deltas, blocks, tools, result = [], [], [], ""
    for line in so.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except (TypeError, ValueError):
            continue
        if not isinstance(ev, dict):
            continue
        typ = ev.get("type")
        if typ == "stream_event":
            e = ev.get("event") or {}
            if not isinstance(e, dict):
                continue
            if e.get("type") == "content_block_start":
                blk = e.get("content_block") or {}
                if isinstance(blk, dict) and blk.get("type") == "tool_use":
                    tools.append(str(blk.get("name") or "tool"))
            elif e.get("type") == "content_block_delta":
                d = e.get("delta") or {}
                if isinstance(d, dict) and d.get("type") == "text_delta":
                    deltas.append(str(d.get("text") or ""))
        elif typ == "assistant":
            msg = ev.get("message") or {}
            content = msg.get("content") if isinstance(msg, dict) else None
            for blk in content or []:
                if not isinstance(blk, dict):
                    continue
                if blk.get("type") == "text":
                    blocks.append(str(blk.get("text") or ""))
                elif blk.get("type") == "tool_use":
                    tools.append(str(blk.get("name") or "tool"))
        elif typ == "result":
            result = str(ev.get("result") or "")
    text = "".join(deltas) if deltas else "".join(blocks)
    if not text.strip() and result:
        text = result
    return jv_claude_clean(text), tools


def jv_claude_run(question):
    """Run Claude Code once, hidden, and return (answer, reason_if_any). No other model is ever used."""
    exe = jv_claude_exe()
    if not exe:
        return "", "the 'claude' command was not found on PATH"
    prompt = str(question).strip()
    if not prompt:
        return "", "the question is empty"
    base = jv_claude_base_argv(exe)
    attempts = (
        ["--output-format", "stream-json", "--verbose", "--include-partial-messages", "-p", prompt],
        ["--output-format", "text", "-p", prompt],
    )
    why = ""
    for n, tail in enumerate(attempts):
        kw = {"stdin": subprocess.DEVNULL, "stdout": subprocess.PIPE, "stderr": subprocess.PIPE,
              "text": True, "encoding": "utf-8", "errors": "replace"}
        if os.name == "nt":
            kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        try:
            proc = subprocess.Popen(base + tail, **kw)
        except OSError as e:
            return "", str(getattr(e, "strerror", "") or e)
        try:
            so, se = proc.communicate(timeout=JV_CLAUDE["timeout"])
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
                proc.communicate(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass
            return "", f"Claude Code did not answer within {JV_CLAUDE['timeout']} seconds"
        if proc.returncode == 0:
            if n == 0:
                text, tools = jv_claude_stream_text(so)
            else:
                text, tools = jv_claude_clean(so), []
            if text:
                return text, ""
            why = "Claude Code returned an empty answer"
            continue
        tail_lines = [x for x in (se or so or "").strip().splitlines() if x.strip()]
        why = tail_lines[-1][:300] if tail_lines else f"Claude Code exited with code {proc.returncode}"
    return "", why


def jv_claude_ask(question):
    """Hand one request to Claude Code and paste the answer as JARVIS. Returns False only when it did not run."""
    if jv_claude_test_mode():
        return False
    if not JV_CLAUDE["auto"]:
        jarvis_say("The Claude Code bridge is off, sir. Say 'claude on' to turn it back on.")
        out()
        return False
    exe = jv_claude_exe()
    if not exe:
        jarvis_say("I can't reach Claude Code, sir: the 'claude' command is not on PATH.")
        out()
        return True
    out("  consulting Claude Code (background)...", GRAY)
    answer, why = jv_claude_run(question)
    if not answer:
        jarvis_say(f"Claude Code did not answer, sir: {safe(str(why))}.")
        out()
        return True
    jarvis_say(answer)
    out()
    return True


def jv_claude_fallback(text):
    """Unknown request: send it to Claude Code. False means 'use the old local reply instead'."""
    if not JV_CLAUDE["auto"] or jv_claude_test_mode():
        return False
    q = re.sub(JV_NAMED_RE, " ", str(text), flags=re.I)
    q = re.sub(r"^\s*(?:(?:hey|ok|okay|hi|hello|ciao|ehi|ehy)[,\s]+)?", "", q, flags=re.I).strip(" ,;:")
    if not q:
        return False
    return jv_claude_ask(q)


def jv_claude_status():
    exe = jv_claude_exe()
    out(f"Claude Code bridge: {'ON' if JV_CLAUDE['auto'] else 'OFF'}", CYAN)
    out(f"  command : {safe(exe) if exe else 'not found on PATH'}", GRAY)
    out(f"  model   : {safe(JV_CLAUDE['model']) if JV_CLAUDE['model'] else 'Claude Code default (this model)'}", GRAY)
    out("  tools   : disabled (text answers only; nothing is read, changed or run)", GRAY)
    out("  routing : unknown requests go to Claude Code and are answered as JARVIS", GRAY)
    out("  usage   : claude <question>  |  claude on  |  claude off  |  claude status  |  claude model <name>", GRAY)
    out()


def jv_claude_set(auto):
    JV_CLAUDE["auto"] = bool(auto)
    jv_claude_status()


@cmdlet("Claude", "Ask-Claude", group="Assistant", usage="""claude <question>         ask Claude Code directly; the answer is pasted here as JARVIS
claude status             is the bridge on, which command and model it uses
claude on | off           auto-answer unknown questions through Claude Code (default: on)
claude model <name>       use a specific model for this session (set JARVIS_CLAUDE_MODEL to keep it)
Only the installed Claude Code CLI is used: no other model or provider, and tools are disabled.
'jarvis <question>' does the same automatically when the local rules cannot answer.
'implement' and 'hack' never go through the bridge.""")
def jv_claude_cmd(args):
    flags, pos = parse(args)
    word = (pos[0].lower() if pos else next(iter(sorted(flags)), "").lstrip("-").lower())
    if not args or word in ("", "status", "stato"):
        jv_claude_status()
        return
    if word in ("on", "enable", "enabled", "attiva", "start"):
        jv_claude_set(True)
        return
    if word in ("off", "disable", "disabled", "disattiva", "stop"):
        jv_claude_set(False)
        return
    if word in ("model", "modello"):
        name = pos[1].strip() if len(pos) > 1 else ""
        if name:
            JV_CLAUDE["model"] = name
            jarvis_say(f"Claude Code will use the model '{safe(name)}' for this session, sir.")
        else:
            jarvis_say("Which model, sir? Example:  claude model sonnet")
        out()
        return
    question = " ".join(pos).strip()
    if not question:
        jv_claude_status()
        return
    jv_claude_ask(question)
