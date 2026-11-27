#!/usr/bin/env python3
# Version: 0.7.0 (beta) | Date: 2026-11-27
"""ptx_kitconfig -- shared reader of the kit configuration config.toml (kit root = folder above tools/).

What it gives
  Kit.find()                 config: --config / $PTX_CONFIG / <kit root>/config.toml / cwd
  kit.path("data")           [paths] value as an absolute path (relative values are relative to config.toml)
  kit.get(sec, key)          [section] key value
TOML is read with tomllib (Python 3.11+); older Python uses the built-in reader below.

Usage (from another tool next to this file)
    import importlib.util, os
    spec = importlib.util.spec_from_file_location("ptx_kitconfig", os.path.join(HERE, "ptx_kitconfig.py"))
    kc = importlib.util.module_from_spec(spec); spec.loader.exec_module(kc)
    kit = kc.Kit.find()                       # None when no config exists
    python3 tools/ptx_kitconfig.py            # self-check: prints config file, every path and whether it exists

Errors: 'ERROR: ...' + 'HINT: ...'.
"""
import glob, json, os, re, stat, sys

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
KIT_ROOT = os.path.dirname(HERE)


def _mini_toml(text):
    """Small TOML reader for the kit config (no inline tables, no multi-line strings). Returns a dict."""
    data, cur = {}, None
    cur = data
    for n, raw in enumerate(_join_arrays(text), 1):
        line = _strip_comment(raw).strip()
        if not line:
            continue
        m = re.match(r"^\[([A-Za-z0-9_.\-]+)\]$", line)
        if m:
            cur = data
            for part in m.group(1).split("."):
                cur = cur.setdefault(part, {})
            continue
        m = re.match(r"^([A-Za-z0-9_\-]+)\s*=\s*(.+)$", line)
        if not m:
            raise ValueError("line %d: cannot read '%s'" % (n, raw.strip()[:60]))
        cur[m.group(1)] = _value(m.group(2).strip(), n)
    return data


def _strip_comment(s):
    """Remove a '#' comment that is outside a string."""
    q = None
    for i, ch in enumerate(s):
        if q:
            if ch == q and s[i - 1] != "\\":
                q = None
        elif ch in "\"'":
            q = ch
        elif ch == "#":
            return s[:i]
    return s


def _value(v, n):
    """One TOML value: string, bool, int, float or array of those."""
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        return [_value(x.strip(), n) for x in re.findall(r'"[^"]*"|\'[^\']*\'|[^,]+', inner) if x.strip().strip(",")] if inner else []
    if v[0] == '"' and v[-1] == '"':
        return bytes(v[1:-1], "utf-8").decode("unicode_escape") if "\\" in v else v[1:-1]
    if v[0] == "'" and v[-1] == "'":
        return v[1:-1]
    if v in ("true", "false"):
        return v == "true"
    try:
        return float(v) if "." in v else int(v)
    except ValueError:
        raise ValueError("line %d: unknown value %s (strings need quotes)" % (n, v))


def _join_arrays(text):
    """Lines of a TOML text with multi-line arrays joined into one line (built-in reader; comments inside are removed)."""
    out, buf = [], None
    for raw in text.splitlines():
        if buf is not None:
            buf += " " + _strip_comment(raw).strip()
            if buf.rstrip().endswith("]"):
                out.append(buf); buf = None
            continue
        line = _strip_comment(raw).rstrip()
        if re.match(r"^\s*[A-Za-z0-9_\-]+\s*=\s*\[", line) and not line.endswith("]"):
            buf = line
            continue
        out.append(raw)
    if buf is not None:
        out.append(buf)
    return out


def load_toml(path):
    """Parse a TOML file: tomllib if available, else the built-in reader."""
    try:
        import tomllib
        with open(path, "rb") as f:
            return tomllib.load(f)
    except ImportError:
        return _mini_toml(open(path, encoding="utf-8").read())


class Kit:
    """The loaded kit configuration."""

    def __init__(self, path):
        self.file = os.path.abspath(path)
        self.base = os.path.dirname(self.file)
        try:
            self.cfg = load_toml(self.file)
        except Exception as e:
            sys.exit("ERROR: config %s unreadable (%s)\nHINT:  check the line named above (TOML: key = \"value\")" % (self.file, e))

    @classmethod
    def find(cls, explicit=None):
        """Config or None. Order: explicit, $PTX_CONFIG, <kit root>/config.toml, cwd."""
        if explicit:
            if not os.path.isfile(os.path.expanduser(explicit)):
                sys.exit("ERROR: config %s not found\nHINT:  fix the path or leave --config out" % explicit)
            return cls(os.path.expanduser(explicit))
        if os.environ.get("PTX_CONFIG") and os.path.isfile(os.environ["PTX_CONFIG"]):
            return cls(os.environ["PTX_CONFIG"])
        for base in (KIT_ROOT, os.getcwd()):
            for name in ("config.toml", "ptx_config.toml"):
                cfg_path = os.path.join(base, name)
                if os.path.isfile(cfg_path):
                    return cls(cfg_path)
            c = sorted(glob.glob(os.path.join(base, "ptx_config_v*.toml")))
            if c:
                return cls(c[-1])
        return None

    def get(self, section, key, default=None):
        """Raw value of [section] key (dotted sections allowed: 'tests.T00')."""
        cur = self.cfg
        for part in section.split("."):
            cur = cur.get(part, {}) if isinstance(cur, dict) else {}
        return cur.get(key, default) if isinstance(cur, dict) else default

    def abspath(self, v):
        """Config value -> absolute path (relative to the config file, '~' expanded)."""
        v = os.path.expanduser(str(v))
        return os.path.normpath(v if os.path.isabs(v) else os.path.join(self.base, v))

    def path(self, key, section="paths", default=None):
        """[section] key as an absolute path; default when missing or empty."""
        v = self.get(section, key)
        return self.abspath(v) if v else default

    def session(self, name):
        """Path of a reference / generated session listed in [reference_sessions.<name>]."""
        v = self.get("reference_sessions." + name, "path")
        return self.abspath(v) if v else None

    def tests(self):
        """{test id: table} of [tests.*]."""
        return dict(self.cfg.get("tests", {}))

    def test_enabled(self, tid):
        """True unless [tests.<tid>] enabled = false."""
        return bool(self.tests().get(tid, {}).get("enabled", True))

    def originals(self):
        """Absolute path of the original sessions (never written) or None."""
        return self.path("original_sessions")

    def guard(self, path, what="write"):
        """Exit with an error when path is inside the original sessions."""
        o = self.originals()
        if o and path:
            p = os.path.realpath(os.path.abspath(os.path.expanduser(path)))
            if p == os.path.realpath(o) or p.startswith(os.path.realpath(o) + os.sep):
                sys.exit("ERROR: refusing to %s %s: it is inside the original sessions (%s)\n"
                         "HINT:  original sessions are never changed; copy the file into data/sessions/ first" % (what, path, o))


def protect_originals(kit, force_ask=False):
    """Optional: make [paths] original_sessions read-only (chmod -R a-w). [originals] read_only = "ask" | "yes" | "no".
    'ask' asks once on the first interactive run; the answer is kept in [paths] setup_state (default queue/setup_state.json)."""
    o = kit.originals() if kit else None
    if not o or not os.path.isdir(o):
        return None
    mode = str(kit.get("originals", "read_only", "ask")).lower()
    state_file = kit.path("setup_state", default=os.path.join(kit.base, "queue", "setup_state.json"))
    try:
        state = json.load(open(state_file))
    except (OSError, ValueError):
        state = {}
    if mode == "no" or (mode == "ask" and not force_ask and "originals_read_only" in state):
        return state.get("originals_read_only")
    if mode == "ask":
        if not sys.stdin.isatty():
            return None                                        # runner / scripts: never ask, never change
        ans = input("[setup] Make the original sessions read-only (chmod -R a-w %s)? Pro Tools can still open them. [y/N] " % o).strip().lower()
        yes = ans in ("y", "yes", "j", "ja")
    else:
        yes = True
    if yes:
        n = 0
        for dp, dn, fn in os.walk(o):
            for x in dn + fn:
                q = os.path.join(dp, x)
                if not os.path.islink(q):
                    os.chmod(q, os.stat(q).st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)); n += 1
        os.chmod(o, os.stat(o).st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
        print("[setup] %d entries made read-only. Undo: chmod -R u+w \"%s\"" % (n, o))
    state["originals_read_only"] = bool(yes)
    try:
        os.makedirs(os.path.dirname(state_file), exist_ok=True)
        json.dump(state, open(state_file, "w"), indent=1)
    except OSError as e:
        print("HINT:  could not keep the answer in %s (%s); you will be asked again" % (state_file, e))
    return yes


def main():
    """Self-check: config file, every path and whether it exists; --protect-originals asks and applies."""
    kit = Kit.find(next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--config=")), None))
    if kit is None:
        print("ERROR: no config.toml in %s\nHINT:  keep this file in <kit>/tools" % KIT_ROOT, file=sys.stderr)
        return 2
    print("config: %s" % kit.file)
    if "--protect-originals" in sys.argv:
        protect_originals(kit, force_ask=True)
        return 0
    missing = 0
    for k, v in kit.cfg.get("paths", {}).items():
        p = kit.abspath(v) if v else ""
        ok = bool(p) and os.path.exists(p)
        late = not ok and k in ("setup_state", "runner_heartbeat", "suite_work")          # made at run time
        missing += not ok and not late
        print("  %-3s %-20s %s%s" % ("ok" if ok else "..", k, p, "   (made at run time)" if late else "") if ok or late else "  %-3s %-20s %s" % ("--", k, p))
    print("%d paths missing" % missing)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
