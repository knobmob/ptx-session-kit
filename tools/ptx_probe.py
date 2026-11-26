#!/usr/bin/env python3
# Version: 0.7.0 (beta) | Date: 2026-11-23
"""ptx_probe -- Read-only, stdlib-only probe for Pro Tools sessions (.ptx / .ptxt).

Descrambles containers, parses the 0x5A block tree (accepting child blocks when kind <= 64 and
content_type belongs to KNOWN_CTS or KNOWN_FAMILIES), and inspects blocks, strings, plug-ins,
regions, MIDI lists, field diffs, session stats, and structural sanity.

Container (xor types 1 and 5):
  - header 0x14 bytes; byte 0x12 = xor type, byte 0x13 = xor value; type 5 scrambles with one key byte per 4 KiB block
  - blocks  0x5A | type u16 | size u32 | content type u16 | data ... (little endian); 'size' starts at the content type;
    child blocks lie inside the data; the u32 at offset 0x1B (inside the first block) points to a top-level block

Commands ('#' = comment; <session> = a .ptx file; <where> = file or folder; folders searched recursively, backups skipped unless --all)
  python3 tools/ptx_probe.py census   <session>                  # block types: count, own bytes, coverage
  python3 tools/ptx_probe.py diff     <a.ptx> <b.ptx>            # block types that appear, vanish or change
  python3 tools/ptx_probe.py strings  <session>                  # readable text in session blocks
  python3 tools/ptx_probe.py dump     <session> <ctype hex>      # hex of the first block of that content type, e.g. 2000
  python3 tools/ptx_probe.py lpstrings <session> [min_len]      # length-prefixed strings with the path of their block (default 3)
  python3 tools/ptx_probe.py annotate <session> [max_blocks]     # block tree with labels, own bytes and strings (default 60)
  python3 tools/ptx_probe.py cover    <session>                  # own bytes by label status: known / partly / unknown
  python3 tools/ptx_probe.py plugins  <session>                  # plug-in state envelope of every insert slot (0x1038)
  python3 tools/ptx_probe.py regions  <session> [rate]           # region library 0x2628: name, flag, W1..W4 (+ seconds)
  python3 tools/ptx_probe.py notes    <session> [max_lists]      # MIDI note lists (MdNLB, 35-byte events; default 3)
  python3 tools/ptx_probe.py fields   <a.ptx> <b.ptx> [ctype hex]  # field finder: changed byte offsets inside blocks of equal size
  python3 tools/ptx_probe.py stats    <where> [--all]           # over many sessions: blocks, depth, coverage, types across files
  python3 tools/ptx_probe.py inventory <where> [--json out.json] [--all]   # one row per session: product, version, rate, counts
  python3 tools/ptx_probe.py check    <where> [--baseline <where>,<where>] [--json out.json] [--all]
                                                                  # structure: coverage, pointer, end, MIDI sanity, new types
Examples
  python3 tools/ptx_probe.py census test/CR_max3/CR_max3.ptx
  python3 tools/ptx_probe.py plugins test/CR_max3/CR_max3.ptx
  python3 tools/ptx_probe.py regions test/CR_max3/CR_max3.ptx 48000

Errors: 'ERROR: ...' + 'HINT: ...', exit code 2 (wrong arguments, unknown xor type, file too short, nothing found);
'check' ends with exit code 1 when a session has a structural problem. Nothing is ever written except the --json file.
"""
import collections
import glob
import json
import os
import re
import struct
import sys

sys.dont_write_bytecode = True

HEADER = 0x14


def fail(msg, hint):
    """Print ERROR + HINT and stop (exit code 2)."""
    sys.stderr.write("ERROR: %s\nHINT:  %s\n" % (msg, hint))
    sys.exit(2)


def gen_delta(value, mul, negative):
    """Search the step byte whose product with `mul` equals the xor value; type 5 uses the two's complement of it."""
    for i in range(256):
        if (i * mul) & 0xFF == value:
            return ((-i) & 0xFF) if negative else i
    fail("no xor delta for value %d" % value, "file is probably not a .ptx or is damaged")


def unscramble(raw):
    """Return the descrambled bytes (header unchanged). Supports xor types 1 and 5."""
    if len(raw) < HEADER + 9:
        fail("file too short", "give a saved .ptx session file")
    d = bytearray(raw)
    xtype, xval = d[0x12], d[0x13]
    if xtype not in (1, 5):
        fail("unknown xor type %d" % xtype, "only types 1 and 5 are known ")
    delta = gen_delta(xval, 53, False) if xtype == 1 else gen_delta(xval, 11, True)
    key = [(i * delta) & 0xFF for i in range(256)]
    for i in range(HEADER, len(d)):
        d[i] ^= key[(i & 0xFF) if xtype == 1 else ((i >> 12) & 0xFF)]
    return bytes(d)


KNOWN_CTS = frozenset((0x0000, 0x0002, 0x0003, 0x0F3C, 0x0F3D, 0x0F3E, 0x1000, 0x1001, 0x1003, 0x1004, 0x1006, 0x1014, 0x1015, 0x1017, 0x1018, 0x1021, 0x1022, 0x1028, 0x1029, 0x102A, 0x102D, 0x1033, 0x1038, 0x103A, 0x103D, 0x103E, 0x103F, 0x1040, 0x1041, 0x1042, 0x1045, 0x1048, 0x1049, 0x104A, 0x104B, 0x104C, 0x104D, 0x104F, 0x1050, 0x1052, 0x1054, 0x1055, 0x1056, 0x1057, 0x1058, 0x1059, 0x2000, 0x2004, 0x2005, 0x2006, 0x200A, 0x200B, 0x200C, 0x200D, 0x2010, 0x2011, 0x2013, 0x2015, 0x2016, 0x2017, 0x2018, 0x2019, 0x201A, 0x201B, 0x201C, 0x201D, 0x201E, 0x201F, 0x2020, 0x2021, 0x2023, 0x2024, 0x2025, 0x2026, 0x2027, 0x2028, 0x2029, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2030, 0x2031, 0x2032, 0x2033, 0x2036, 0x2037, 0x2038, 0x203A, 0x203B, 0x203C, 0x203D, 0x203E, 0x2047, 0x2049, 0x204A, 0x204B, 0x204D, 0x2050, 0x2055, 0x2056, 0x2058, 0x205E, 0x205F, 0x2062, 0x2063, 0x2064, 0x2066, 0x2067, 0x2068, 0x2069, 0x206A, 0x206B, 0x206C, 0x206D, 0x206E, 0x206F, 0x2070, 0x2071, 0x2072, 0x2073, 0x2074, 0x2077, 0x2078, 0x207A, 0x207B, 0x207E, 0x2086, 0x208C, 0x208E, 0x208F, 0x2096, 0x2097, 0x2098, 0x2099, 0x209F, 0x20A0, 0x20A1, 0x20A2, 0x2103, 0x2104, 0x2106, 0x2107, 0x210B, 0x210C, 0x2203, 0x2301, 0x2302, 0x2305, 0x230A, 0x230B, 0x2423, 0x2424, 0x2425, 0x2426, 0x2428, 0x242B, 0x242E, 0x242F, 0x2430, 0x2432, 0x2433, 0x2434, 0x2435, 0x2437, 0x2501, 0x2502, 0x2504, 0x2505, 0x2506, 0x2507, 0x2508, 0x2509, 0x2510, 0x2511, 0x2516, 0x2519, 0x251A, 0x251B, 0x251C, 0x2523, 0x2526, 0x252A, 0x252C, 0x2530, 0x2550, 0x2551, 0x2552, 0x2553, 0x2554, 0x2556, 0x2557, 0x255F, 0x2567, 0x2580, 0x2581, 0x2582, 0x2583, 0x2585, 0x2587, 0x2588, 0x2589, 0x258A, 0x258B, 0x258C, 0x258E, 0x258F, 0x2595, 0x2597, 0x259B, 0x259C, 0x25C0, 0x2600, 0x2601, 0x2602, 0x2603, 0x2604, 0x260A, 0x260B, 0x260C, 0x260D, 0x260E, 0x260F, 0x2611, 0x2613, 0x2614, 0x2615, 0x2616, 0x2617, 0x2619, 0x261B, 0x261C, 0x261D, 0x261E, 0x2620, 0x2621, 0x2624, 0x2625, 0x2626, 0x2627, 0x2628, 0x2629, 0x262A, 0x262B, 0x262C, 0x262E, 0x262F, 0x2630, 0x2632, 0x2633, 0x2634, 0x2636, 0x2637, 0x263B, 0x2701, 0x270A, 0x270D, 0x2710, 0x2715, 0x2716, 0x2718, 0x2719, 0x271A, 0x271B, 0x271C, 0x271F, 0x2721, 0x2A00, 0x4000, 0x4300, 0x4301, 0x4400, 0x4403, 0x4420, 0x4421, 0x4422, 0x4501, 0x4530, 0x4701, 0x4702, 0x4807, 0x4808, 0x4809, 0x4820, 0x4823, 0x4824, 0x4826, 0x4827, 0x4828, 0x4829, 0x4833, 0x4834, 0x483B, 0x483D, 0x4842, 0x4843, 0x4845, 0x4846, 0x4847, 0x4848, 0x4849, 0x484D, 0x484E, 0x484F, 0x4850, 0x4852, 0x4856, 0x485A, 0x485D, 0xFFFF))   # block types of the kit sessions (>= 2 times) + the types the decoder / writer name


KNOWN_FAMILIES = frozenset(c >> 8 for c in KNOWN_CTS)   # high byte of known block types (0x261F = VCA channel)
FLAT_CTS = frozenset((0x0002, 0x1028, 0x204D, 0x260A, 0x262F, 0x2637))   # leaf payloads with no nested 0x5A blocks (0x104F kept recursive for 0x242B loops)
RAW_PREFIX = {0x1054: 4}                                                  # leading u32 playlist count (90 = 0x5A would otherwise mimic a block header)


def parse(d, pos, end, strict=None):
    """Parse sibling blocks in d[pos:end]; every block: {bt, ct, pos, size, kids}. Children are searched after the content type."""
    out = []
    while pos < end:
        if d[pos] != 0x5A or pos + 9 > end:
            pos += 1
            continue
        bt, size, ct = struct.unpack_from("<HIH", d, pos + 1)
        if size < 2 or pos + 7 + size > end or (strict and (bt > 64 or (ct not in KNOWN_CTS and ct >> 8 not in KNOWN_FAMILIES))):
            pos += 1
            continue
        pref = RAW_PREFIX.get(ct, 0)
        kids = [] if ct in FLAT_CTS or pos + 9 + pref > pos + 7 + size else parse(d, pos + 9 + pref, pos + 7 + size, strict is not False)
        out.append({"bt": bt, "ct": ct, "pos": pos, "size": size, "kids": kids})
        pos += 7 + size
    return out


def walk(nodes):
    """Depth-first iterator over all blocks."""
    for n in nodes:
        yield n
        yield from walk(n["kids"])


def load(path):
    """Read + descramble + parse; returns (bytes, tree)."""
    try:
        raw = open(path, "rb").read()
    except OSError as e:
        fail("cannot read %s (%s)" % (path, e), "check the path; cloud files must be downloaded locally")
    d = unscramble(raw)
    return d, parse(d, HEADER, len(d))


def census(tree):
    """Per content type: (number of blocks, own bytes = size minus the bytes of the child blocks)."""
    n, own = collections.Counter(), collections.Counter()
    for x in walk(tree):
        n[x["ct"]] += 1
        own[x["ct"]] += x["size"] - sum(k["size"] + 7 for k in x["kids"])
    return n, own


def cmd_census(path):
    """Print per-ctype block counts and byte coverage for one session."""
    d, tree = load(path)
    covered = sum(t["size"] + 7 for t in tree)
    print("%s: %d bytes, top-level blocks %d, coverage %d of %d bytes" % (path, len(d), len(tree), covered, len(d) - HEADER))
    n, own = census(tree)
    for ct in sorted(n):
        print("  ct 0x%04x  blocks %4d  own bytes %7d" % (ct, n[ct], own[ct]))


def cmd_diff(a, b):
    """Block types that appear, vanish or change in number or own bytes between two sessions."""
    (_, ta), (_, tb) = load(a), load(b)
    na, oa = census(ta)
    nb, ob = census(tb)
    for ct in sorted(set(na) | set(nb)):
        if na[ct] != nb[ct] or oa[ct] != ob[ct]:
            tag = "new " if ct not in na else ("gone" if ct not in nb else "chg ")
            print("%s ct 0x%04x  blocks %d -> %d  own bytes %d -> %d" % (tag, ct, na[ct], nb[ct], oa[ct], ob[ct]))


def cmd_strings(path):
    """Readable text runs (>= 5 characters) of the descrambled session; scrambled areas give no output."""
    d, _ = load(path)
    seen = []
    for m in re.finditer(rb"[ -~]{5,}", d):
        s = m.group().decode()
        if s not in seen:
            seen.append(s)
    print("\n".join(seen))


def cmd_dump(path, ctype_hex):
    """Hex dump (first 256 bytes of data) of the first block with the given content type (hex, e.g. 2000)."""
    d, tree = load(path)
    want = int(ctype_hex, 16)
    for x in walk(tree):
        if x["ct"] == want:
            body = d[x["pos"] + 9:x["pos"] + 7 + x["size"]]
            print("ct 0x%04x at 0x%x, size %d" % (want, x["pos"], x["size"]))
            print(body[:256].hex(" "))
            return
    fail("content type 0x%04x not found" % want, "run 'census' to list the types of this file")




# helpers shared by the new commands
LABELS = {    # content type -> (label, status: V verified, P partly / hypothesis, ? unknown)
    0x0002: ("directory of stored positions (k records)", "V"), 0x0003: ("version/product", "V"),
    0x1000: ("path part / settings blob", "P"), 0x1004: ("audio file list", "V"), 0x1017: ("plug-in name + ID", "V"),
    0x1021: ("input path", "V"), 0x1022: ("input path tree", "V"), 0x1028: ("sample rate @+11", "V"),
    0x102a: ("path component", "V"), 0x1038: ("plug-in state of an insert slot", "P"),
    0x103a: ("audio file entry (name/path part)", "V"), 0x104f: ("playlist entry (+9 mute, +11 region, +16 position)", "V"),
    0x1050: ("playlist entries", "P"), 0x1052: ("playlist (track name)", "P"), 0x1057: ("displayed track name (MIDI / instrument)", "V"),
    0x2000: ("MIDI chunk (MdChun.. / MdNLB)", "V"), 0x200b: ("path component", "V"), 0x2028: ("tempo map (61-byte Const records)", "V"),
    0x2029: ("meter map (36-byte records)", "V"), 0x2030: ("marker list (0x2077 children)", "V"), 0x2033: ("channel format name", "V"),
    0x2037: ("plug-in param table row", "P"), 0x2038: ("plug-in param table row", "P"), 0x203b: ("plug-in param table row", "P"),
    0x2056: ("counter", "P"), 0x2058: ("transport / record modes", "V"), 0x2064: ("plug-in settings container", "P"),
    0x2067: ("session info + own path", "V"), 0x2077: ("named location/marker", "V"), 0x207a: ("audio device", "V"),
    0x2099: ("small state record", "?"), 0x210b: ("track name (view)", "P"), 0x2435: ("metadata field", "V"),
    0x2506: ("location position?", "?"), 0x2511: ("Snap1..48 slot name", "P"),
    0x2519: ("track list head (kind, name, format, id, duplicate number)", "V"), 0x251a: ("track record", "P"),
    0x2580: ("param/automation lane?", "?"), 0x2589: ("track-related list (order free)", "P"),
    0x2600: ("hw port mapping", "V"), 0x2601: ("path leg flags", "P"), 0x2602: ("output path (pair/mono)", "V"),
    0x2603: ("output path tree", "V"), 0x260a: ("value lane: count x (u32 samples, i16 value); fader dB x 10, pan", "V"),
    0x260c: ("strip state wrapper (first 0x260a = pan)", "P"), 0x260d: ("mixer strip section", "P"),
    0x260e: ("strip output assignment (name)", "V"), 0x2619: ("ruler name", "V"), 0x261b: ("input assignment (name)", "V"),
    0x2620: ("track block (bytes 185/193/703 = duplicate number)", "V"), 0x2628: ("region definition (W1..W4 nibble widths)", "V"),
    0x2629: ("region group/container", "P"), 0x262a: ("region list", "P"), 0x262b: ("clip group part", "P"),
    0x262c: ("clip group", "P"), 0x262f: ("fade part", "P"), 0x2630: ("fade object", "P"), 0x2715: ("metadata base64", "V"),
    0x4501: ("category/group name", "P"), 0x4702: ("category/group name", "P"), 0x4809: ("input path flag 'A'", "P"),
}
SESSION_EXT = (".ptx", ".ptxt")
MIDI_BASE, MIDI_TPQ = 10 ** 12, 960000          # MdNLB positions: 10^12 + ticks, 960000 ticks per quarter note


def label(ct):
    """(label, status) of a content type."""
    return LABELS.get(ct, ("-", "?"))


def tree_rows(tree, depth=0, parent=None):
    """Flat list of (block, depth, parent block) in file order."""
    rows = []
    for n in tree:
        rows.append((n, depth, parent))
        rows += tree_rows(n["kids"], depth + 1, n)
    return rows


def own_bytes(n):
    """Size of a block without its child blocks (header bytes of the children included in the children)."""
    return n["size"] - sum(k["size"] + 7 for k in n["kids"])


def end_of(n):
    """Offset after the block."""
    return n["pos"] + 7 + n["size"]


def _kit():
    """Kit configuration through ptx_kitconfig.py next to this file, or None."""
    import importlib.util
    here = os.path.dirname(os.path.abspath(__file__))
    mod = os.path.join(here, "ptx_kitconfig.py")
    if not os.path.isfile(mod):
        c = sorted(glob.glob(os.path.join(here, "ptx_kitconfig_v*.py")))
        if not c:
            return None
        mod = c[-1]
    sp = importlib.util.spec_from_file_location("ptx_kitconfig", mod)
    kc = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(kc)
    return kc.Kit.find(os.environ.get("PTX_CONFIG"))


def where(arg):
    """Resolve '@reference', '@generated', '@originals', '@runs' through the kit configuration; other args unchanged."""
    keys = {"@reference": "reference_sessions", "@generated": "generated_sessions", "@originals": "original_sessions", "@runs": "runs"}
    if arg in keys:
        kit = _kit()
        p = kit.path(keys[arg]) if kit else None
        if not p:
            fail("%s needs the kit configuration" % arg, "run inside ptx-session-kit/tools or give a folder path")
        return p
    return arg


def sessions(args, all_files=False):
    """Session files of the given files / folders (recursive); Pro Tools backups only with all_files."""
    out = []
    for a in args:
        a = where(a)
        if os.path.isfile(a):
            out.append(a)
            continue
        if not os.path.isdir(a):
            fail("%s not found" % a, "give a .ptx file, a folder or @reference / @generated / @originals / @runs")
        for dp, dn, fn in os.walk(a):
            dn.sort()
            for f in sorted(fn):
                if f.startswith("._") or not f.lower().endswith(SESSION_EXT):
                    continue
                p = os.path.join(dp, f)
                if not all_files and ("Session File Backups" in p or ".bak." in f):
                    continue
                out.append(p)
    if not out:
        fail("no session files found in %s" % ", ".join(args), "folders are searched for .ptx / .ptxt; backups need --all")
    return out


def try_load(path):
    """(bytes, tree, None) or (None, None, reason) - for commands that go over many files and must not stop."""
    try:
        raw = open(path, "rb").read()
        if len(raw) < HEADER + 9 or raw[0x12] not in (1, 5):
            return None, None, "not a session (header / xor type %s)" % (raw[0x12] if len(raw) > 0x12 else "?")
        d = unscramble(raw)
        return d, parse(d, HEADER, len(d)), None
    except SystemExit:
        return None, None, "unreadable (see ERROR above)"
    except OSError as e:
        if getattr(e, "errno", None) in (35, 11):          # EDEADLK / EAGAIN: cloud placeholder that is not downloaded
            return None, None, "cloud-only file: make it downloaded locally, then retry"
        return None, None, "cannot read (%s)" % e


def write_json(path, obj):
    """Write a JSON result; refused inside the original sessions (kit write guard)."""
    kit = _kit()
    if kit:
        kit.guard(path, "write the result")
    try:
        with open(path, "w") as f:
            json.dump(obj, f, indent=1, default=str)
    except OSError as e:
        fail("cannot write %s (%s)" % (path, e), "choose a writable folder, e.g. ./")
    print("wrote %s" % path)


def u32(d, at):
    """Little-endian u32."""
    return struct.unpack_from("<I", d, at)[0]


def lp_strings(d, a, b, lo=2, hi=100):
    """Length-prefixed (u32) printable strings in d[a:b] -> [(offset, text)]."""
    out, k = [], a
    while k < b - 4:
        n = u32(d, k)
        if lo <= n <= hi and k + 4 + n <= b and all(32 <= c < 127 for c in d[k + 4:k + 4 + n]):
            out.append((k, d[k + 4:k + 4 + n].decode()))
            k += 4 + n
        else:
            k += 1
    return out


def midi_lists(d):
    """All MdNLB note lists: [(offset, count, size, events, error)] with events = dicts pos / note / len / vel (quarters)."""
    res = []
    for m in re.finditer(b"MdNLB", d):
        o = m.start()
        try:
            size, cnt = u32(d, o + 7), u32(d, o + 11)       # tag (5) + u16, then u32 size, u32 count
        except struct.error:
            res.append((o, 0, 0, [], "truncated list header"))
            continue
        p, ev, err = o + 15, [], None
        for i in range(cnt):
            e = d[p:p + 35]
            if len(e) < 35:
                err = "event %d runs past the end of the file (35-byte stride?)" % i
                break
            raw = int.from_bytes(e[0:5], "little")
            ev.append({"pos": (raw - MIDI_BASE if raw >= MIDI_BASE else raw) / MIDI_TPQ, "note": e[8],      # 10^12 + ticks or plain ticks
                       "len": int.from_bytes(e[9:14], "little") / MIDI_TPQ, "vel": e[17]})
            p += 35
        res.append((o, cnt, size, ev, err))
    return res


def session_rate(d, tree):
    """Sample rate from block 0x1028 (u32 at +11) or None."""
    for n in walk(tree):
        if n["ct"] == 0x1028 and n["size"] >= 11:
            return u32(d, n["pos"] + 11)
    return None


# ---------------------------------------------------------------- commands
def cmd_annotate(path, max_blocks="60"):
    """Block tree with labels, own bytes (hex, children excluded) and the first strings (from ptx_annot)."""
    raw = open(path, "rb").read()
    d, tree = load(path)
    xtype, xval = raw[0x12], raw[0x13]
    delta = gen_delta(xval, 53, False) if xtype == 1 else gen_delta(xval, 11, True)
    rows = tree_rows(tree)
    print("HEADER 0x00-0x13: magic=0x%02x marker=%r xor type=%d value=0x%02x -> delta=0x%02x; %d bytes, %d blocks"
          % (raw[0], raw[1:0x11].decode("latin1"), xtype, xval, delta, len(raw), len(rows)))
    print("offset     depth kind   size    ctype  st label                                      | own bytes (hex) / strings")
    for n, depth, _ in rows[:int(max_blocks)]:
        lab, st = label(n["ct"])
        a = n["pos"] + 9
        e = n["kids"][0]["pos"] if n["kids"] else end_of(n)
        own = d[a:e]
        sx = " ".join('"%s"@0x%x' % (t, k) for k, t in lp_strings(d, a, e)[:3])
        print("0x%08x %s%-2d 0x%04x %7d 0x%04x [%s] %-42s | %s%s %s" % (n["pos"], "  " * depth, depth, n["bt"], n["size"], n["ct"], st,
              lab[:42], own[:28].hex(" "), " ..." if len(own) > 28 else "", sx))
    if len(rows) > int(max_blocks):
        print("... %d more blocks (give a larger max_blocks)" % (len(rows) - int(max_blocks)))


def cmd_cover(path):
    """Own bytes per label status (V verified, P partly, ? unknown) and the 25 largest block types (from ptx_annot)."""
    raw = open(path, "rb").read()
    d, tree = load(path)
    by_st, by_ct, cnt = collections.Counter(), collections.Counter(), collections.Counter()
    for n in walk(tree):
        ob = own_bytes(n) + 7
        by_st[label(n["ct"])[1]] += ob
        by_ct[n["ct"]] += ob
        cnt[n["ct"]] += 1
    tot = sum(by_st.values()) + HEADER
    print("%s: %d bytes; header %d B; bytes by status of the owning block type:" % (os.path.basename(path), len(raw), HEADER))
    for st, name in (("V", "verified"), ("P", "partly / hypothesis"), ("?", "unknown")):
        print("  %-20s %9d B  %6.1f %%" % (name, by_st[st], 100.0 * by_st[st] / tot))
    print("\nTop 25 block types by own bytes:\nctype   count     bytes   share  st  label")
    for ct, b in by_ct.most_common(25):
        lab, st = label(ct)
        print("0x%04x %6d %9d %6.1f %%  [%s] %s" % (ct, cnt[ct], b, 100.0 * b / tot, st, lab))


def cmd_plugins(path):
    """Plug-in state envelope of every insert slot block 0x1038 (from ptx_plugin_hdr; report 5.5).
    Fields: u32 1, u32 length | big-endian u32 size, i32 version | 4 ID codes | chunk name (32 bytes)."""
    d, tree = load(path)
    n = 0
    for b in walk(tree):
        if b["ct"] != 0x1038:
            continue
        body = d[b["pos"] + 9:end_of(b)]
        if len(body) < 64:
            continue                                   # empty slot
        size, ver = struct.unpack_from(">Ii", body, 8)
        ids = [body[16 + 4 * i:20 + 4 * i].decode("latin1") for i in range(4)]
        name = body[32:64].split(b"\0")[0].decode("latin1", "replace")
        print("0x%08x len=%7d size=%8d ver=%6d ids=%s name=%r" % (b["pos"], len(body), size, ver, ids, name))
        n += 1
    print("%d slot blocks with a header (HINT: the size field does not mark the end of the state; use len)" % n)


def cmd_regions(path, rate=None):
    """Region library 0x2628: name, flag, extra byte, widths W1..W4 and the values .
    W1 = start inside the source (MIDI: 10^12 + ticks or plain ticks), W2 = length; audio values in samples."""
    d, tree = load(path)
    sr = int(rate) if rate else session_rate(d, tree)
    n = 0
    for b in walk(tree):
        if b["ct"] != 0x2628:
            continue
        p = b["pos"] + 9
        ln = u32(d, p)
        name = d[p + 4:p + 4 + ln].decode("utf-8", "replace")
        q = p + 4 + ln
        flag, b1, b2, b3, ex = d[q:q + 5]
        widths = [b1 >> 4, b2 >> 4, b3 >> 4, b3 & 15]
        sync_w = b2 & 15
        o = q + 5
        v0 = int.from_bytes(d[o:o + widths[0]], "little") if widths[0] else 0
        o += widths[0]
        sync_off = int.from_bytes(d[o:o + sync_w], "little") if sync_w else None
        o += sync_w
        vals = [v0]
        for w in widths[1:]:
            vals.append(int.from_bytes(d[o:o + w], "little") if w else 0)
            o += w
        plain = [v - MIDI_BASE if v >= MIDI_BASE else v for v in vals]
        secs = (" audio s=%s" % [round(v / sr, 3) for v in plain]) if sr else ""
        quarters = " midi q=%s" % [round(v / MIDI_TPQ, 3) for v in plain]
        sync_s = (" sync=%d" % sync_off) if sync_off is not None else ""
        print("%-28s flag=%d extra=0x%02x W=%s v=%s%s%s%s" % (name[:28], flag, ex, widths, vals, sync_s, secs, quarters))
        n += 1
    print("%d regions (both readings shown: audio = samples at %s Hz, MIDI = ticks / 960000 per quarter)" % (n, sr or "?"))


def cmd_notes(path, max_lists="3"):
    """MIDI note lists MdNLB (35-byte events: pos5 | 3 flags | note | len5 | 3 flags | velocity | rest) (from ptx_midi)."""
    d, _ = load(path)
    shown = 0
    for o, cnt, size, ev, err in midi_lists(d):
        if err:
            print("ERR @0x%x: %s" % (o, err))
            continue
        if not cnt:
            continue
        print("@0x%x count=%d size=%d" % (o, cnt, size))
        for e in ev[:8]:
            print("   pos=%.3f q  note=%d  len=%.3f q  vel=%d" % (e["pos"], e["note"], e["len"], e["vel"]))
        if cnt > 8:
            print("   ... %d more" % (cnt - 8))
        shown += 1
        if shown >= int(max_lists):
            break
    if not shown:
        print("no non-empty note list (MdNLB) in %s" % path)


def cmd_lpstrings(path, min_len="3"):
    """Length-prefixed (u32) strings with the content-type path of the innermost block that holds them (from ptx_strings)."""
    d, tree = load(path)
    rows = tree_rows(tree)
    def owner_path(o):
        best = None
        for n, depth, par in rows:
            if n["pos"] <= o < end_of(n):
                best = n
        chain, cur = [], best
        parents = {id(n): par for n, _, par in rows}
        while cur is not None:
            chain.append("%04x" % cur["ct"])
            cur = parents.get(id(cur))
        return "/".join(reversed(chain)) or "-"
    for k, t in lp_strings(d, HEADER, len(d), int(min_len), 200):
        print("0x%08x [%s] %r" % (k, owner_path(k), t))


def cmd_stats(*args):
    """Over many sessions: size, blocks, depth, top-level coverage, distinct types; then the 60 most frequent types with
    the number of files they occur in (from ptx_stats)."""
    pos, opt = _opts(args, {"--all": False})
    tot, per = collections.Counter(), {}
    for p in sessions(pos, opt.get("--all")):
        d, tree, err = try_load(p)
        if err:
            print("FAIL %s %s" % (p, err))
            continue
        rows = tree_rows(tree)
        c = collections.Counter(n["ct"] for n, _, _ in rows)
        per[p] = c
        tot.update(c)
        cov = sum(t["size"] + 7 for t in tree) / max(1, len(d) - HEADER)
        print("%-50s size=%9d blocks=%6d depth=%2d coverage=%.3f types=%d" % (os.path.basename(p)[:50], len(d), len(rows),
              max((x[1] for x in rows), default=0), cov, len(c)))
    print("\n%d sessions, %d distinct content types; top 60 (count, files, label):" % (len(per), len(tot)))
    for ct, n in tot.most_common(60):
        print("  0x%04x %8d  files=%4d  %s" % (ct, n, sum(1 for c in per.values() if ct in c), label(ct)[0]))


def cmd_fields(a, b, ctype_hex=None):
    """Field finder: blocks are paired by content type and order (depth first); for pairs of equal size the changed byte
    runs inside the data are listed (data offset, old hex, new hex); size changes are listed per type."""
    (da, ta), (db, tb) = load(a), load(b)
    want = int(ctype_hex, 16) if ctype_hex else None
    by = lambda t: collections.defaultdict(list, {})
    ga, gb = collections.defaultdict(list), collections.defaultdict(list)
    for n in walk(ta):
        ga[n["ct"]].append(n)
    for n in walk(tb):
        gb[n["ct"]].append(n)
    shown = 0
    for ct in sorted(set(ga) | set(gb)):
        if want is not None and ct != want:
            continue
        la, lb = ga[ct], gb[ct]
        if len(la) != len(lb):
            print("ct 0x%04x  count %d -> %d  (%s)" % (ct, len(la), len(lb), label(ct)[0]))
        for i, (x, y) in enumerate(zip(la, lb), 1):
            xa, ya = da[x["pos"] + 9:end_of(x)], db[y["pos"] + 9:end_of(y)]
            if xa == ya:
                continue
            if len(xa) != len(ya):
                print("ct 0x%04x #%d  size %d -> %d" % (ct, i, len(xa), len(ya)))
                continue
            runs, k = [], 0
            while k < len(xa):
                if xa[k] != ya[k]:
                    j = k
                    while j < len(xa) and (xa[j] != ya[j] or (j + 1 < len(xa) and xa[j + 1] != ya[j + 1])):
                        j += 1
                    runs.append((k, xa[k:j].hex(), ya[k:j].hex()))
                    k = j
                k += 1
            kids = ", ".join("+%d %s -> %s" % r for r in runs[:6]) + (" ... (%d runs)" % len(runs) if len(runs) > 6 else "")
            print("ct 0x%04x #%d  %s  | %s" % (ct, i, label(ct)[0][:30], kids))
            shown += 1
    print("%d changed blocks of equal size" % shown)


def _opts(args, flags):
    """Split args into positional args and {flag: value}; flags maps '--x' -> takes_value."""
    pos, opt, it = [], {}, iter(args)
    for a in it:
        if a in flags:
            opt[a] = next(it, None) if flags[a] else True
            if flags[a] and opt[a] is None:
                fail("%s needs a value" % a, "see the usage at the top of this file")
        else:
            pos.append(a)
    return pos, opt


def cmd_inventory(*args):
    """One row per session: size, product, version, platform, rate, strips, plug-ins, regions, playlist entries, notes,
    blocks (from ptx_inv). --json writes the rows; --all includes Pro Tools backups."""
    pos, opt = _opts(args, {"--json": True, "--all": False})
    if not pos:
        fail("no files", "usage: inventory <where> [--json out.json] [--all]")
    rows = []
    for p in sessions(pos, opt.get("--all")):
        d, tree, err = try_load(p)
        if err:
            rows.append({"file": p, "error": err})
            continue
        c = collections.Counter(n["ct"] for n in walk(tree))
        aux = sum(1 for n, _, par in tree_rows(tree) if n["ct"] == 0x261b and par is not None and par["ct"] == 0x261e)
        prod = ver = plat = None
        b3 = next((n for n in walk(tree) if n["ct"] == 3), None)
        if b3:
            strs = [s.decode("latin1") for s in re.findall(rb"[\x20-\x7e]{3,}", d[b3["pos"] + 9:end_of(b3)])]
            prod = strs[0] if strs else None
            ver = next((s for s in strs if re.match(r"^\d+(\.\d+)+$", s)), None)
            plat = "Windows" if "Windows" in strs else ("macOS" if any("Mac" in s or "OS X" in s or "macOS" in s for s in strs) else None)
        rows.append({"file": p, "size": len(d), "product": prod, "version": ver, "platform": plat, "rate": session_rate(d, tree),
                     "strips": c[0x261b] + c[0x2621], "aux": aux, "plugins": c[0x1017], "regions": c[0x2628], "playlist_entries": c[0x104f],
                     "notes": sum(x[1] for x in midi_lists(d) if not x[4]), "blocks": sum(c.values())})
    print("%-48s %9s %-14s %-10s %-8s %6s %5s %6s %6s %7s %6s %6s" % ("session", "bytes", "product", "version", "platform", "rate",
          "strip", "plugin", "region", "entries", "notes", "blocks"))
    for r in rows:
        if "error" in r:
            print("%-48s FAIL %s" % (os.path.basename(r["file"])[-48:], r["error"]))
        else:
            print("%-48s %9d %-14s %-10s %-8s %6s %5d %6d %6d %7d %6d %6d" % (os.path.basename(r["file"])[-48:], r["size"],
                  (r["product"] or "-")[:14], r["version"] or "-", r["platform"] or "-", r["rate"] or "-", r["strips"], r["plugins"],
                  r["regions"], r["playlist_entries"], r["notes"], r["blocks"]))
    print("%d sessions" % len(rows))
    if opt.get("--json"):
        write_json(opt["--json"], rows)


def cmd_check(*args):
    """Structural check (from ptx_final + ptx_my): coverage of the top-level blocks, pointer at 0x1B, last block ends at
    the end of the file, MIDI note / velocity <= 127, content types not seen in the --baseline sessions. Exit 1 on problems."""
    pos, opt = _opts(args, {"--baseline": True, "--json": True, "--all": False})
    if not pos:
        fail("no files", "usage: check <where> [--baseline <where>,<where>] [--json out.json] [--all]")
    base = set()
    if opt.get("--baseline"):
        for p in sessions(opt["--baseline"].split(","), False):
            d, tree, err = try_load(p)
            if not err:
                base |= {n["ct"] for n in walk(tree)}
        print("baseline: %d content types" % len(base))
    rows, bad, new = [], 0, collections.defaultdict(list)
    for p in sessions(pos, opt.get("--all")):
        d, tree, err = try_load(p)
        if err:
            rows.append({"file": p, "error": err})
            bad += 1
            continue
        cov = sum(t["size"] + 7 for t in tree) / max(1, len(d) - HEADER)
        ptr = u32(d, 0x1B) if len(d) > 0x1F else None
        ptr_ok = ptr is not None and any(t["pos"] == ptr for t in tree)
        eof_ok = bool(tree) and end_of(tree[-1]) == len(d)
        lists = midi_lists(d)
        badnv = sum(1 for x in lists if x[4]) + sum(1 for x in lists for e in x[3] if e["note"] > 127 or e["vel"] > 127)
        cts = {n["ct"] for n in walk(tree)}
        for c in sorted(cts - base) if base else []:
            new[c].append(os.path.basename(p))
        ok = cov >= 0.999 and ptr_ok and eof_ok and not badnv
        bad += not ok
        rows.append({"file": p, "bytes": len(d), "blocks": sum(1 for _ in walk(tree)), "coverage": round(cov, 4), "pointer_ok": ptr_ok,
                     "end_ok": eof_ok, "note_lists": len(lists), "events": sum(len(x[3]) for x in lists), "bad_notes": badnv, "ok": ok})
    for r in rows:
        if "error" in r:
            print("FAIL %-60s %s" % (r["file"][-60:], r["error"]))
        else:
            print("%-4s %-60s %9d blk=%6d cov=%.4f ptr=%s end=%s notes=%d bad=%d" % ("ok" if r["ok"] else "BAD", r["file"][-60:], r["bytes"],
                  r["blocks"], r["coverage"], r["pointer_ok"], r["end_ok"], r["events"], r["bad_notes"]))
    if base:
        print("content types not in the baseline: %s" % ({"0x%04x" % c: (len(v), v[0]) for c, v in new.items()} or "none"))
    print("%d sessions, %d with problems" % (len(rows), bad))
    if opt.get("--json"):
        write_json(opt["--json"], {"rows": rows, "new_types": {"0x%04x" % c: v for c, v in new.items()}})
    return 1 if bad else 0


def main(argv):
    """Command line entry point; see the usage examples at the top of this file."""
    cmds = {"census": (cmd_census, 1, 1), "diff": (cmd_diff, 2, 2), "strings": (cmd_strings, 1, 1), "dump": (cmd_dump, 2, 2),
            "annotate": (cmd_annotate, 1, 2), "lpstrings": (cmd_lpstrings, 1, 2), "fields": (cmd_fields, 2, 3), "stats": (cmd_stats, 1, 99), "cover": (cmd_cover, 1, 1), "plugins": (cmd_plugins, 1, 1),
            "regions": (cmd_regions, 1, 2), "notes": (cmd_notes, 1, 2), "inventory": (cmd_inventory, 1, 99), "check": (cmd_check, 1, 99)}
    if len(argv) >= 2 and argv[1] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    if len(argv) < 2 or argv[1] not in cmds or not cmds[argv[1]][1] <= len(argv) - 2 <= cmds[argv[1]][2]:
        fail("wrong arguments", "usage: ptx_probe.py %s <session(s)> (see --help)" % "|".join(cmds))
    return cmds[argv[1]][0](*argv[2:]) or 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
