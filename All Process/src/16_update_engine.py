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


