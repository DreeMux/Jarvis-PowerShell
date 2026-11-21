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


