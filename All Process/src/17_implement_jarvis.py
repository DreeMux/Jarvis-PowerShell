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


