#!/usr/bin/env python3
# Version: 0.7.0 (beta) | Date: 2026-11-27
"""ptx_decode -- Read-only decoder of verified `.ptx` / `.ptxt` binary fields.

Decodes tracks, playlists, markers, tempo maps, meter maps, key signatures, regions,
audio/MIDI placements, clip gains, fades, clip groups, clip loops, mixer strips
(volume/pan/mute/LFE/sends), inserts (`elck`, `All `, `MD_3`, `PiII`, automation lanes),
folders, groups, Elastic Audio, timeline, and settings into one JSON document.

Usage examples ('#' = comment)
  python3 tools/ptx_decode.py session.ptx                     # JSON: tracks, markers, tempo, meter, regions, placements, strips
  python3 tools/ptx_decode.py session.ptx --only tracks       # one part
  python3 tools/ptx_decode.py session.ptx --ticks 0,960000 --rate 48000   # convert tick positions with the session tempo map
  python3 tools/ptx_decode.py session.ptx --validate          # consistency checks (cross-reference, missing ids, zero durations)
JSON of the tracks: name, type (Audio, Midi, Aux, Master, Instrument, BasicFolder; kind 2 = aux / click / routing folder
is reported as Aux), format (Mono / Stereo for audio-carrying tracks), plus kind, list_name, id.
Tempo / meter: both maps are stored twice; the active map is in 'tempo_used', 'meter_used'.
Tracks also carry output (destination name) and stem_index (destination format index) from the strip;
"umids" maps each audio file stem to its stored basic UMID.
Positions: ticks = 960 000 per quarter note (stored as 10^12 + ticks or plain ticks), strips: samples and tenths of a dB.

Errors: parts that do not match the known layout are left out and named in "warnings" (never guessed); a file that is
not a session gives ERROR + HINT and exit code 2.
"""
import glob, re, importlib.util, json, os, struct, sys

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
_probe_path = os.path.join(HERE, "ptx_probe.py")
if not os.path.isfile(_probe_path):
    _p = sorted(glob.glob(os.path.join(HERE, "ptx_probe_v*.py")))
    if not _p:
        sys.exit("ERROR: ptx_probe.py not found next to this file\nHINT:  keep the kit tools together in <kit>/tools")
    _probe_path = _p[-1]
_spec = importlib.util.spec_from_file_location("ptx_probe", _probe_path)
probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe)

OFFSET_FORM = 10 ** 12
TPQ = 960000
KINDS = {0: "Audio", 1: "Midi", 2: "Aux", 5: "Master", 7: "Instrument", 9: "VCA", 11: "BasicFolder"}


def u32(d, at):
    """Little-endian u32."""
    return struct.unpack_from("<I", d, at)[0]


def plain(v):
    """10^12 + ticks or plain ticks -> ticks."""
    return v - OFFSET_FORM if v >= OFFSET_FORM else v


def le(d, at, n):
    """Little-endian unsigned integer of n bytes."""
    return int.from_bytes(d[at:at + n], "little")


def find(tree, ct):
    """First block of a content type (depth first)."""
    for n in probe.walk(tree):
        if n["ct"] == ct:
            return n
    return None


def tracks(d, tree, warn):
    """Track list head of the first 0x2519 + displayed names from the route blocks 0x1057 (MIDI / instrument).
    Data: +10 u32 n, n x u16 (unknown meaning), u32 count, then the entries (kind, name, format, id, number)."""
    b = find(tree, 0x2519)
    if not b:
        warn.append("no track list 0x2519")
        return []
    s, end = b["pos"] + 9, probe_end(b)
    pre = u32(d, s + 10)                                  # u32 n at +10, then n u16 values (n = 0 in the MIDI sessions, 1 / 3 in
    if pre > 4096:                                        # pre-track u16 index count guard
        warn.append("u16 list length %d at +10 > 4096" % pre)
        return []
    count, p, out = u32(d, s + 14 + 2 * pre), s + 18 + 2 * pre, []
    if count > 4096:
        warn.append("track count %d > 4096" % count)
        return []
    for i in range(count):
        kind, ln = struct.unpack_from("<HI", d, p)
        if ln > 1024 or p + 6 + ln + 6 + 15 > end + 3:
            warn.append("track entry %d beyond the block" % i)
            return out
        name_at = p + 6
        tag = name_at + ln + 6
        if d[tag:tag + 4] != b"\x2a\x00\x00\x00":
            warn.append("track entry %d: id tag 2A000000 not after the name" % i)
            return out
        name = d[name_at:name_at + ln].decode("utf-8", "replace")
        t = {"name": name, "list_name": name, "kind": kind, "type": KINDS.get(kind, "Other_%d" % kind),
             "stereo": d[name_at + ln] == 1, "id": "{00000000-2a000000-%s-%s}" % (d[tag + 4:tag + 8].hex(), d[tag + 8:tag + 12].hex()),
             "number": d[tag + 12]}                     # clip id in GUID form: {00000000-2a000000-<8 stored bytes>}
        if kind in (0, 2, 5, 7):                       # audio-carrying kinds: format byte 1 = stereo, 0 = mono
            t["format"] = "Stereo" if t["stereo"] else "Mono"
        out.append(t)
        p = tag + 4 + 8 + 3
    routes = route_names(d, tree)
    targets = [t for t in out if t["kind"] in (1, 7)]
    if len(routes) == len(targets):
        for t, n in zip(targets, routes):
            t["name"] = n
    elif targets:
        warn.append("%d route names for %d MIDI / instrument tracks: list names kept" % (len(routes), len(targets)))
    return out


def probe_end(b):
    """Offset after a block."""
    return b["pos"] + 7 + b["size"]


def route_names(d, tree):
    """Names of the route blocks 0x1057 (children of the first 0x1058)."""
    par = find(tree, 0x1058)
    out = []
    for k in (par["kids"] if par else []):
        if k["ct"] == 0x1057:
            s = k["pos"] + 9
            ln = u32(d, s)
            if ln <= 1024 and s + 4 + ln <= probe_end(k):
                out.append(d[s + 4:s + 4 + ln].decode("utf-8", "replace"))
    return out


def markers(d, tree, warn):
    """0x2077 children of the first 0x2030 that has such children."""
    lst = next((n for n in probe.walk(tree) if n["ct"] == 0x2030 and any(k["ct"] == 0x2077 for k in n["kids"])), None)
    out = []
    for m in (lst["kids"] if lst else []):
        if m["ct"] != 0x2077:
            continue
        s = m["pos"] + 9
        ln = u32(d, s + 6)
        if ln > 1024 or s + 15 + ln > probe_end(m):
            warn.append("marker at 0x%x does not match" % m["pos"])
            continue
        raw = le(d, s + 10 + ln, 5)
        mk = {"number": struct.unpack_from("<H", d, s)[0], "name": d[s + 10:s + 10 + ln].decode("utf-8", "replace"),
              "ticks": plain(raw)}
        # unit flag at position +7 (0x40 = ticks with the 10^12 offset; 0 = samples, no offset; X1 ESI run 2026-11-14)
        mk["flags"] = d[s + 2:s + 4].hex()                                      # +2 / +3
        mk["kind"] = {0: "none", 1: "marker", 2: "selection"}.get(d[s + 3] & 3, d[s + 3] & 3)   # T53 (0301 / 0302 / 5f00)
        mk["is_marker"] = mk["kind"] == "marker"                                # selection / none: not in the ESI marker list
        mk["unit"] = "ticks" if d[s + 10 + ln + 7] == 0x40 or raw >= OFFSET_FORM else "samples"
        if mk["unit"] == "samples":
            mk["samples"] = raw
        raw2 = le(d, s + 10 + ln + 8, 5)                                      # end position (selections)
        mk["end"] = plain(raw2) if mk["unit"] == "ticks" else raw2
        q = s + 10 + ln
        nt = u32(d, q + 66)
        if nt <= 64 and q + 70 + nt + 9 <= probe_end(m):                       # /28: comment (tag 1: +5/+9, tag 2: +6/+10)
            a = q + 70 + nt
            tag = u32(d, a)
            if tag == 1:
                cl = u32(d, a + 5)
                mk["comment"] = d[a + 9:a + 9 + cl].decode("utf-8", "replace") if cl < 4096 and a + 9 + cl <= probe_end(m) else ""
            elif tag == 2 and a + 10 <= probe_end(m):
                cl = u32(d, a + 6)
                mk["comment"] = d[a + 10:a + 10 + cl].decode("utf-8", "replace") if cl < 4096 and a + 10 + cl <= probe_end(m) else ""
            else:
                mk["comment"] = ""
        out.append(mk)
    return out


def _map_header(d, b, magic, count_len):
    """(first record, count) of a tempo / meter block or None."""
    s = b["pos"] + 9
    if d[s:s + len(magic)] != magic:
        return None
    return s + len(magic) + 6 + count_len, u32(d, s + len(magic) + 6)


def tempo_blocks(tree):
    """All 0x2028 blocks (the map is stored twice; the first is the one read)."""
    return [n for n in probe.walk(tree) if n["ct"] == 0x2028]


def tempo(d, tree, warn, which=0):
    """Constant-tempo events of the which-th 0x2028 block: [{ticks, bpm}]."""
    bl = tempo_blocks(tree)
    if len(bl) <= which:
        return []
    b = bl[which]
    h = _map_header(d, b, b"Tempo", 8)
    if not h or h[1] > 100000:
        warn.append("tempo block %d header" % which)
        return []
    p, out = h[0], []
    for _ in range(h[1]):
        if d[p:p + 5] != b"Const" or p + 61 > probe_end(b):
            warn.append("tempo record at 0x%x is not 'Const'" % p)
            break
        bpm = struct.unpack_from("<d", d, p + 40)[0]
        out.append({"ticks": plain(le(d, p + 30, 5)), "bpm": round(bpm, 6), "bpm_exact": bpm})   # exact f64 for writers
        p += 61
    return out


def meter(d, tree, warn, which=0):
    """Meter events of the which-th 0x2029 block (stored twice): [{ticks, bar, numerator, denominator}]."""
    bl = [n for n in probe.walk(tree) if n["ct"] == 0x2029]
    if len(bl) <= which:
        return []
    b = bl[which]
    h = _map_header(d, b, b"Meter", 4)
    if not h or h[1] > 100000:
        warn.append("meter block header")
        return []
    p, out = h[0], []
    for _ in range(h[1]):
        if p + 36 > probe_end(b):
            warn.append("meter record beyond the block")
            break
        out.append({"ticks": plain(struct.unpack_from("<Q", d, p)[0]), "bar": u32(d, p + 8), "numerator": u32(d, p + 12), "denominator": u32(d, p + 16)})
        p += 36
    return out


def _decode_2628_varints(d, q):
    """Parse 0x2628 nibble widths (W1, sync_offset via b2 & 0xF, W2, W3, W4); returns (flag, widths, v, sync_offset, end_o)."""
    flag, b1, b2, b3, ex = d[q:q + 5]
    widths = [b1 >> 4, b2 >> 4, b3 >> 4, b3 & 15]
    sync_w = b2 & 15
    if sync_w > 8 or max(widths) > 8:
        return flag, ex, widths, sync_w, [], None, q
    o = q + 5
    v = [le(d, o, widths[0]) if widths[0] else 0]
    o += widths[0]
    sync_offset = None
    if sync_w:
        sync_offset = le(d, o, sync_w)
        o += sync_w
    for w in widths[1:]:
        v.append(le(d, o, w) if w else 0)
        o += w
    return flag, ex, widths, sync_w, v, sync_offset, o


def regions(d, tree, warn):
    """Region library 0x2628 (inside the first 0x2634 when present,  plus the audio clips 0x2629 > 0x2628 outside it):
    name, flag, W1..W4 (+ optional inline sample sync_offset when b2 & 0x0F > 0)."""
    lib = find(tree, 0x2634)
    src = list(probe.walk(lib["kids"])) if lib else list(probe.walk(tree))
    if lib:                                                   # audio clips 0x2629 > 0x2628 outside the MIDI library too
        inlib = {b["pos"] for b in src}
        src += [k for w in probe.walk(tree) if w["ct"] == 0x2629 for k in w["kids"] if k["ct"] == 0x2628 and k["pos"] not in inlib]
    out = []
    for b in src:
        if b["ct"] != 0x2628:
            continue
        p = b["pos"] + 9
        ln = u32(d, p)
        if ln > 1024:
            warn.append("region at 0x%x: name length %d" % (b["pos"], ln))
            continue
        q = p + 4 + ln
        flag, ex, widths, sync_w, v, sync_offset, _ = _decode_2628_varints(d, q)
        if not v:
            warn.append("region at 0x%x: width > 8" % b["pos"])
            continue
        ent = {"name": d[p + 4:p + 4 + ln].decode("utf-8", "replace"), "flag": flag, "extra": ex, "w": v,
               "start": plain(v[0]), "length": v[1],
               "time_stamp": v[2] - (1 << 64) if widths[2] == 8 and v[2] >= 1 << 63 else v[2]}   # signed
        if sync_offset is not None:
            ent["sync_offset"] = sync_offset
        out.append(ent)
    return out



def _region_blocks(tree):
    """the 0x2628 blocks in the order regions() reads them (for attaching per-region fields)."""
    lib = find(tree, 0x2634)
    src = list(probe.walk(lib["kids"])) if lib else list(probe.walk(tree))
    if lib:
        inlib = {b["pos"] for b in src}
        src += [k for w in probe.walk(tree) if w["ct"] == 0x2629 for k in w["kids"] if k["ct"] == 0x2628 and k["pos"] not in inlib]
    return [b for b in src if b["ct"] == 0x2628]


def _clip_loop(lb):
    """Decode 0x242B clip-loop child (57-59B): unit bytes +38/+46 (0x40=ticks, 0x00=samples)."""
    unit = "ticks" if lb[46] == 0x40 else "samples"
    trim_v, iter_v = le(lb, 31, 7), le(lb, 39, 7)
    out = {"mode": lb[0], "bars": u32(lb, 11), "beats": u32(lb, 15), "ticks": u32(lb, 19), "count": u32(lb, 27),
           "unit": unit, "trim_ticks": trim_v, "iter_ticks": iter_v, "raw": lb.hex()}
    if unit == "samples":
        out["trim_samples"], out["iter_samples"] = trim_v, iter_v
    return out


def placements(d, tree):
    """Playlist entries 0x104F per route block 0x1057 (MIDI / instrument tracks): from the block start +9 mute,
    u16 +11 region index, 5-byte position +16."""
    par = find(tree, 0x1058)
    out = []
    for r in (par["kids"] if par else []):
        if r["ct"] != 0x1057:
            continue
        lst = []
        for e in probe.walk(r["kids"]):
            if e["ct"] == 0x104F and e["size"] >= 16:
                s = e["pos"]                                   # offsets from the block start (Rust reader clips.rs)
                ent = {"region": struct.unpack_from("<H", d, s + 11)[0], "ticks": plain(le(d, s + 16, 5)), "muted": d[s + 9] == 1}
                lp = next((k for k in e["kids"] if k["ct"] == 0x242B), None)
                if lp and lp["size"] >= 2 + 47:
                    ent["loop"] = _clip_loop(d[lp["pos"] + 9:lp["pos"] + 7 + lp["size"]])
                lst.append(ent)
        out.append(lst)
    return out


def _lane(d, b):
    """Automation lane 0x260A (/28): 01 46 01 00 | u32 L | u16 time base | u32 n | u16 2 |
    tb=0 (samples): u32 (n - 1), u16 0, u32 first_pos; tb=1 (ticks): u16 (n - 1), u64 first_pos |
    i16 value | (n - 1) x (u32 position, i16 value) | u16 0. Returns [[position, value], ...]."""
    s = b["pos"] + 9
    n = u32(d, s + 10)
    if n > 1000000 or n < 1 or s + 28 + 6 * (n - 1) > probe_end(b):
        return None
    tb = struct.unpack_from("<H", d, s + 8)[0]
    pos0 = u32(d, s + 22) if tb == 0 and u32(d, s + 16) >= 65536 else struct.unpack_from("<Q", d, s + 18)[0]
    out = [[pos0, struct.unpack_from("<h", d, s + 26)[0]]]
    out += [[u32(d, s + 28 + 6 * i), struct.unpack_from("<h", d, s + 32 + 6 * i)[0]] for i in range(n - 1)]
    return out


def lane_time_base(d, b):
    """'samples' / 'ticks' of a lane 0x260A (u16 at data +8)."""
    v = struct.unpack_from("<H", d, b["pos"] + 9 + 8)[0]
    return {0: "samples", 1: "ticks"}.get(v, v)


def _out_dest(d, st):
    """Output of a strip: first 0x260E child; data '... u32 length | destination name | stem index of the destination | ...'
    ."""
    o = next((k for k in st["kids"] if k["ct"] == 0x260E), None)
    if not o:
        return None, None
    strs = probe.lp_strings(d, o["pos"] + 9, probe_end(o), 1, 200)
    if not strs:
        return "", None
    at, name = strs[-1]
    nb = at + 4 + len(name.encode("utf-8"))
    return name, (d[nb] if nb < probe_end(o) else None)


def _strip(d, st):
    """One 0x260D strip: output, stem index, volume lane, pan lane (tenths of a dB, -100..+100); mute lane (1 = muted),
    active flag and destination path number from 0x260E, post-fader flag (0x1029 byte 0; 1 post, 0 pre, meaningful for sends).
    only 0x260A lanes before the first 0x260C panner count as volume / mute / trim (Master 1 of tut0001 has a post-panner 0x260A)."""
    c0 = next((k["pos"] for k in st["kids"] if k["ct"] == 0x260C), probe_end(st))
    lanes = [k for k in st["kids"] if k["ct"] == 0x260A and k["pos"] < c0]
    o = next((k for k in st["kids"] if k["ct"] == 0x260E), None)
    t = next((k for k in st["kids"] if k["ct"] == 0x1029), None)
    extra = {"mute": (_lane(d, lanes[1]) or []) if len(lanes) > 1 else [],
             "active": (d[o["pos"] + 12] != 0) if o else None,                  # +3 (inactive track MIX_05 s13, inactive send MIX_02)
             "record_enable": False if (t and t["size"] >= 10) else None,        # 0x1029+5 (tm[1]) is mute_static, not record_enable
             "dest_path": u32(d, o["pos"] + 9) & 0xFFFF if o else None,
             "post_fader": bool(d[t["pos"] + 9]) if t else None}
    vol = lanes[0] if lanes else None
    pcs = [k for k in st["kids"] if k["ct"] == 0x260C]
    pc = pcs[0] if pcs else None
    pan = next((k for k in pc["kids"] if k["ct"] == 0x260A), None) if pc else None
    pc2 = pcs[1] if len(pcs) > 1 else None
    pan2 = next((k for k in pc2["kids"] if k["ct"] == 0x260A), None) if pc2 else None
    v = _lane(d, vol) if vol else None
    lfe = _lane(d, lanes[2]) if len(lanes) > 2 else None
    extra["lane_time_base"] = lane_time_base(d, vol) if vol else None
    dest, stem = _out_dest(d, st)
    return dict({"output": dest, "stem_index": stem, "volume": v or [], "pan": (_lane(d, pan) if pan else None) or [],
                 "pan2": (_lane(d, pan2) if pan2 else None) or [],
                 "volume_db": (None if not v else (float("-inf") if v[0][1] <= -1440 else v[0][1] / 10.0)),
                 "lfe": lfe or [],
                 "lfe_db": (None if not lfe else (float("-inf") if lfe[0][1] <= -1440 else lfe[0][1] / 10.0))}, **extra)


MODES = {0: "off", 1: "read", 2: "touch", 3: "latch", 4: "write"}
SLOTS = "abcdefghij"


def session_version(d, tree):
    """Pro Tools version string of the version block 0x0003 (e.g. '2026.11.0'), None when absent."""
    b3 = find(tree, 0x0003)
    if not b3:
        return None
    strs = [x.decode("latin-1") for x in re.findall(rb"[\x20-\x7e]{3,}", d[b3["pos"] + 9:probe_end(b3)])]
    return next((x for x in strs if re.match(r"^\d+(\.\d+)+$", x)), None)


def _ver_tuple(v):
    try:
        return tuple(int(x) for x in v.split("."))
    except (AttributeError, ValueError):
        return ()


def solo(d, ch):
    """solo of a channel: track info 0x102D, byte at +161 + name length (just before the automation mode)."""
    inf = next((x for x in _subtree(ch) if x["ct"] == 0x102D), None)
    if not inf:
        return None
    i = inf["pos"] + 161 + u32(d, inf["pos"] + 18)
    return d[i] == 1 if i < probe_end(inf) else None


def playlists(d, tree):
    """playlist records 0x1052 without children: name, time base (byte 4 after the name: 1 samples, 2 ticks)."""
    out = []
    for n in probe.walk(tree):
        if n["ct"] != 0x1052 or n["kids"]:
            continue
        x = d[n["pos"] + 9:probe_end(n)]
        if len(x) < 4:
            continue
        ln = u32(x, 0)
        if ln > 256 or 4 + ln + 5 > len(x):
            continue
        tb = x[4 + ln + 4]
        out.append({"name": x[4:4 + ln].decode("utf-8", "replace"), "time_base": {1: "samples", 2: "ticks"}.get(tb, tb)})
    return out


def automation_mode(d, ch):
    """automation mode of a channel block: track info 0x102D, u32 name length at +18, mode byte at +162 + length."""
    inf = next((x for x in _subtree(ch) if x["ct"] == 0x102D), None)
    if not inf:
        return None
    n = u32(d, inf["pos"] + 18)
    i = inf["pos"] + 162 + n
    return MODES.get(d[i], d[i]) if i < probe_end(inf) else None


_PNAME = re.compile(rb"([dl]_[A-Za-z0-9 /().+#-]{1,40})\x00")          # : spaces, / ( ) . + # - (Channel Strip)


def _params(b):
    """Named parameters of a "Complete Controls State" chunk: name\\0, pad to a multiple of 4 (name + NUL + pad), then
    d_ = f64 BE or l_ = i32 BE. read in sequence from the header on and stop at the first non-parameter (the old
    regex over the whole block with one fixed pad byte misread even-length names and matched bytes in other data)."""
    out = {}
    s = b.find(b"Complete Controls State\x00")
    mm = _PNAME.search(b, s + 24) if s >= 0 else None
    while mm:
        nm = mm.group(1)
        j = mm.end() + (-(len(nm) + 1)) % 4
        w = 8 if nm[:1] == b"d" else 4
        if j + w > len(b):
            break
        out[nm.decode()] = struct.unpack(">d", b[j:j + 8])[0] if w == 8 else struct.unpack(">i", b[j:j + 4])[0]
        mm = _PNAME.match(b, j + w)
    return out


def _plugin_lane_steps(d, f_blk):
    """Return discrete step count (>=2) from 0x260F entry metadata when is_continuous==0, else None."""
    tail_start = probe_end(f_blk["kids"][-1]) if f_blk["kids"] else f_blk["pos"] + 10
    end = probe_end(f_blk)
    if tail_start + 4 > end:
        return None
    nlen = u32(d, tail_start)
    mpos = tail_start + 4 + nlen + 4
    if mpos + 4 > end:
        return None
    meta = d[mpos:mpos + 4]
    return meta[3] if meta[1] == 0 and meta[3] >= 2 else None


def _plugin_lane(d, n, steps=None):
    """Plug-in automation lane 0x260B, laid out like 0x260A with i32 values (): 01 46 01 00 | u32 L | u16 time base |
    u32 n | u16 4 | u16 n - 1 | u64 first position (ticks + 10^12, or samples) | i32 | (n - 1) x (u32 offset from p0, i32);
    continuous uses value = (normalised - 0.5) x 2^31; discrete uses raw 0..steps-1."""
    s = n["pos"] + 9
    e = probe_end(n)
    if d[s:s + 4] != b"\x01\x46\x01\x00" or s + 30 > e:
        return []
    tb = struct.unpack_from("<H", d, s + 8)[0]
    cnt = u32(d, s + 10)
    if cnt < 1 or cnt > 1000000 or s + 30 + 8 * (cnt - 1) > e:
        return []
    p0 = struct.unpack_from("<Q", d, s + 18)[0]
    if tb == 1 and p0 >= 10 ** 12:
        p0 -= 10 ** 12
    def _dec(vi):
        if steps is not None:
            return (1.0 if vi != 0 else 0.0) if steps <= 2 else max(0.0, min(1.0, vi / (steps - 1)))
        return vi / 2 ** 31 + 0.5
    pts = [(p0, _dec(struct.unpack_from("<i", d, s + 26)[0]))]
    j = s + 30
    for _ in range(cnt - 1):
        pts.append((p0 + u32(d, j), _dec(struct.unpack_from("<i", d, j + 4)[0])))
        j += 8
    return [(p, round(v, 6)) for p, v in pts]


def user_delay(d, ch):
    """user delay offset (samples) of a channel: after the last strip 0x260D of the container (0x261B or the channel
    itself) come 01 01, u16 n (send slots), n x u32 ids, then i32 delay (default 0)."""
    box = next((k for k in ch["kids"] if k["ct"] == 0x261B), ch)
    strips_ = [k for k in box["kids"] if k["ct"] == 0x260D]
    if not strips_:
        return None
    nxt = [k for k in box["kids"] if k["pos"] > strips_[-1]["pos"] and k["ct"] != 0x485A]
    lo = max([probe_end(k) for k in box["kids"] if k["ct"] == 0x485A and k["pos"] > strips_[-1]["pos"]] + [probe_end(strips_[-1])])
    gap = d[lo:(nxt[0]["pos"] if nxt else probe_end(box))]
    i = 0 if len(gap) >= 4 and gap[0] == 1 and gap[1] in (0, 1) else gap.find(b"\x01\x01")   # record at gap start
    if i < 0 or i + 4 > len(gap):
        return None
    n = struct.unpack_from("<H", gap, i + 2)[0]
    j = i + 4 + 4 * n
    return struct.unpack_from("<i", gap, j)[0] if n <= 64 and j + 4 <= len(gap) else None


def mpe_mode(d, ch):
    """MPE mode of a MIDI / instrument track from its settings block 0x2010: block start +47 = 1 poly, +80 = 1 mono,
    both 0 = off (data +38 / +71; MIDI / Audio sessions)."""
    st = next((k for k in ch["kids"] if k["ct"] == 0x2010), None)
    if not st or probe_end(st) - st["pos"] < 80:
        return None
    return "poly" if d[st["pos"] + 47] == 1 else ("mono" if d[st["pos"] + 80] == 1 else "off")


def write_enables(d, tree):
    """Automation window write-enables: 0x204A, u32 count at +20 (7), then one byte per switch from +24; index 1 = pan
    (verified twice, MIX_03 and MIX_05); the order of the others follows the window (volume, pan, mute, send level, send pan,
    send mute, plug-in) = hypothesis."""
    b = find(tree, 0x204A)
    if not b:
        return None
    x = d[b["pos"] + 9:probe_end(b)]
    n = u32(x, 20) if len(x) >= 24 else 0
    return [x[24 + i] for i in range(min(n, 16))] if 0 < n <= 16 else None


def clip_gains(d, tree):
    """clip gain values in dB: 0x2637 = u32 count, then 30-byte one-point lanes (01 46 01 00 ...), f32 dB at +26
    (MIX_05: -4.465, -7.256). Which clip each value belongs to is not yet known."""
    b = find(tree, 0x2637)
    if not b:
        return []
    return [ln["points"][0][1] for ln in clip_gain_lanes(d, tree) if ln["points"]]   # first point of every lane


def clip_gain_lanes(d, tree):
    """entries of 0x2637 walked by length: 01 46 01 00, u32 L, body (L bytes): u16 0, u32 n points, u16 4, u16 0/4,
    u32 base (0 on one-point lanes; meaning open), then n x (u32 pos, f32 dB). One-point lanes have L = 22 (MIX_05),
    five-point lanes L = 54 (Low Roar demo)."""
    b = find(tree, 0x2637)
    if not b:
        return []
    x, i, out = d[b["pos"] + 9:probe_end(b)], 4, []
    while i + 8 <= len(x) and x[i:i + 4] == b"\x01\x46\x01\x00":
        ln = struct.unpack_from("<I", x, i + 4)[0]
        body = x[i + 8:i + 8 + ln]
        n = struct.unpack_from("<I", body, 2)[0] if len(body) >= 6 else 0
        pts = [(struct.unpack_from("<I", body, 14 + 8 * k)[0], round(struct.unpack_from("<f", body, 18 + 8 * k)[0], 3))
               for k in range(n) if 22 + 8 * k <= len(body)]
        out.append({"points": pts, "base": struct.unpack_from("<I", body, 10)[0] if len(body) >= 14 else None})
        i += 8 + ln
    return out


_TRIM_KNOTS = ((0.0, -144.0), (0.10, -53.10), (0.25, -23.40), (0.40, -14.60), (0.50, -10.40), (0.755, 0.0))


def _trim_norm_to_db(norm, rng_db):
    """Empirical Pro Tools Trim gain curve (14 live/MIX_01 points, <= 0.06 dB error)."""
    if norm <= 0.0:
        return -144.0
    if norm >= 0.755:
        return round(min(1.0, norm - 0.755) / (1.0 - 0.755) * rng_db, 2)
    for (x0, y0), (x1, y1) in zip(_TRIM_KNOTS, _TRIM_KNOTS[1:]):
        if norm <= x1:
            return round(y0 + (norm - x0) / (x1 - x0) * (y1 - y0), 2)
    return 0.0


def _be_norm(b, off):
    """Big-endian signed i32 normalized to [0..1] (0.5 at 0)."""
    return round(struct.unpack_from(">i", b, off)[0] / 2 ** 32 + 0.5, 6)


def _decode_md3(b):
    """Decode Mod Delay III 'MD_3' state chunk (217 B)."""
    keys = ("output_left", "output_right", "rate_left", "rate_right", "lpf_left", "lpf_right",
            "delay_left", "delay_right", "mix_left", "mix_right", "depth_left", "depth_right",
            "feedback_left", "feedback_right")
    p = {k: _be_norm(b, 64 + 4 * i) for i, k in enumerate(keys)}
    if len(b) >= 160:
        p["tempo_bpm"] = round(5.0 + _be_norm(b, 122) * 495.0, 2)
        p["meter_num"] = 1 + round(_be_norm(b, 126) * 31)
        p["meter_den"] = 1 + round(_be_norm(b, 130) * 31)
        p["note_left_norm"] = _be_norm(b, 134)
        p["note_right_norm"] = _be_norm(b, 138)
        p["invert_left"] = bool(b[142])
        p["invert_right"] = bool(b[143])
        p["groove_left"] = _be_norm(b, 148)
        p["groove_right"] = _be_norm(b, 152)
    return p


def _decode_piii(b):
    """Decode Pitch II 'PiII' state chunk (216 B)."""
    p = {"version": struct.unpack_from(">I", b, 64)[0], "mix_left": round(struct.unpack_from(">d", b, 128)[0], 4),
         "lpf_left": round(struct.unpack_from(">d", b, 144)[0], 2), "mix_right": round(struct.unpack_from(">d", b, 172)[0], 4),
         "lpf_right": round(struct.unpack_from(">d", b, 188)[0], 2)}
    return p


def inserts(d, ch):
    """insert slots of a channel block (0x2627: one child per slot a - j; 0x2616 filled, 0x2617 multi-mono wrapper,
    0x2625 empty). Per filled slot: ids (manufacturer, product, type), multi_mono, active, named parameters, automation lanes."""
    lst = next((x for x in _subtree(ch) if x["ct"] == 0x2627), None)
    out = []
    if not lst:
        return out
    for k, s in enumerate(lst["kids"]):
        if s["ct"] not in (0x2616, 0x2617):
            continue
        mm, slot = s["ct"] == 0x2617, s
        if mm and s["kids"]:
            slot = s["kids"][0]
        rec = next((x for x in _subtree(slot) if x["ct"] == 0x2613), None)
        st = next((x for x in _subtree(slot) if x["ct"] == 0x1038), None)
        auto = next((x for x in slot["kids"] if x["ct"] == 0x2614), None)
        e = {"slot": SLOTS[k] if k < len(SLOTS) else k, "multi_mono": mm, "ids": None, "name": "", "active": None, "params": {}, "automation": []}
        if rec and rec["kids"]:
            tail = probe_end(rec["kids"][-1])
            e["active"] = bool(d[tail]) if tail < probe_end(rec) else None
        inst = next((x for x in slot["kids"] if x["ct"] == 0x2615), None)          # bypass byte after 0x2615
        e["bypass"] = bool(d[probe_end(inst)]) if inst and probe_end(inst) < probe_end(slot) else None
        if st:
            b = d[st["pos"] + 9:probe_end(st)]
            mid = re.search(rb"[ -~]{16}", b[:64])
            if mid:
                ids = mid.group(0)
                e["ids"] = [ids[i:i + 4].decode("latin-1") for i in (0, 4, 8)]
                rest = b[mid.end():mid.end() + 40]
                nm = re.match(rb"([ -~]{3,40})", rest)
                e["name"] = nm.group(1).decode() if nm and b"Complete" in nm.group(1) else ""
            e["params"] = _params(b)
            if e["ids"] and e["ids"][1] == "PIGD" and len(b) >= 9:
                e["params"]["delay_samples"] = u32(b, len(b) - 9)          # Time Adjuster
        if inst:                                                               # table position (0x2626 in 0x2615)
            t26 = next((x for x in inst["kids"] if x["ct"] == 0x2626), None)
            e["table_index"] = struct.unpack_from("<H", d, probe_end(t26))[0] if t26 else None   # u16 right behind the empty 0x2626
        if rec and rec["size"] >= 4:
            e["settings_index"] = struct.unpack_from("<H", d, rec["pos"] + 9)[0]  # settings-file list entry
        if st:
            b = d[st["pos"] + 9:probe_end(st)]
            if len(b) >= 64:                                                   # 56-byte BE header after u32 1, u32 length
                e["state_format"] = b[28:32].decode("latin-1")
                if e["state_format"] == "All ":
                    e["values"] = [round(struct.unpack_from(">i", b, q)[0] / 2 ** 32 + 0.5, 6) for q in range(64, len(b) - 3, 4)]
                    e["values_i32"] = [struct.unpack_from(">i", b, q)[0] for q in range(64, len(b) - 3, 4)]
                    pid2, vs, vi = e["ids"][1] if e["ids"] else "", e["values"], e["values_i32"]
                    if pid2 == "SciF" and len(vs) >= 8:
                        for idx_s, kn in enumerate(("input_level", "effect_type", "effect_frequency", "effect_depth",
                                                    "slot_4", "mod_depth", "mod_rate_slew_thresh")):
                            e["params"][kn] = vs[idx_s]
                        e["params"]["master_bypass"] = vi[7] > 0
                    elif pid2 == "Trim" and len(vs) >= 5:
                        rng_db = 12 if vi[3] > 0 else 6
                        e["params"]["gain_norm"] = vs[0]
                        e["params"]["gain_db"] = _trim_norm_to_db(vs[0], rng_db)
                        e["params"]["phase_invert"] = vi[1] > 0
                        e["params"]["gain_range_db"] = rng_db
                        e["params"]["master_bypass"] = vi[4] > 0
                    elif pid2 == "PIGD" and len(vi) >= 9:
                        e["params"]["delay_samples_r"] = vi[7]
                        e["params"]["master_bypass"] = vi[8] > 0
                    elif pid2 == "LoFi" and len(vs) >= 9:
                        e["params"]["sample_rate_norm"] = vs[0]
                        e["params"]["sample_size_norm"] = vs[1]
                        e["params"]["anti_alias_norm"] = vs[2]
                        e["params"]["noise_norm"] = vs[3]
                        e["params"]["distortion"] = vs[6]
                        e["params"]["saturation"] = vs[7]
                        e["params"]["master_bypass"] = vi[8] > 0
                    elif pid2 == "1176" and len(vs) >= 7:
                        for idx_s, kn in enumerate(("input", "output", "attack", "release", "ratio", "meter_mode")):
                            e["params"][kn] = vs[idx_s]
                        e["params"]["master_bypass"] = vi[6] > 0
                    elif pid2 == "Rvrb" and len(vs) >= 11:
                        e["params"]["algorithm_norm"] = vs[0]
                        e["params"]["size_norm"] = vs[1]
                        e["params"]["decay_norm"] = vs[2]
                        e["params"]["mix"] = vs[3]
                        e["params"]["diffusion"] = vs[4]
                        e["params"]["pre_delay_norm"] = vs[8]
                        e["params"]["master_bypass"] = vi[10] > 0
                    elif pid2 == "PSA1" and len(vi) >= 10:
                        e["params"]["master_bypass"] = vi[9] > 0
                    elif pid2 == "Dthr" and len(vi) >= 4:
                        e["params"]["master_bypass"] = vi[3] > 0
                    elif pid2 == "POWr" and len(vi) >= 3:
                        e["params"]["master_bypass"] = vi[2] > 0
                elif e["state_format"] == "MD_3" and len(b) >= 120:
                    e["params"].update(_decode_md3(b))
                elif e["state_format"] == "PiII" and len(b) >= 196:
                    e["params"].update(_decode_piii(b))
        if auto:
            entries = [k for k in auto["kids"] if k["ct"] == 0x260F]
            e["automation"] = [
                _plugin_lane(d, b0b, _plugin_lane_steps(d, f))
                for f in entries
                for b0b in _subtree(f) if b0b["ct"] == 0x260B
            ]
            e["automation_params"] = [list(plugin_lane_names(d, x)) for x in entries]
        out.append(e)
    return out


def _parse_2064(b):
    """Parse structured 0x2064 path locator: 0x5a 0x02 preset locator + optional 0x5a 0x01 session settings folder."""
    if len(b) < 13 or b[:2] != b"\x5a\x02":
        return None
    p = 9
    vl = u32(b, p); p += 4
    if p + vl + 4 > len(b):
        return None
    vol = b[p:p + vl].decode("utf-8", "replace"); p += vl
    fl = u32(b, p); p += 4
    if p + fl + 14 > len(b):
        return None
    fn = b[p:p + fl].decode("utf-8", "replace"); p += fl + 10
    depth = u32(b, p); p += 4
    parts = []
    for _ in range(min(depth, 64)):
        if p + 4 > len(b):
            return None
        pl = u32(b, p); p += 4
        if p + pl > len(b):
            return None
        parts.append(b[p:p + pl].decode("utf-8", "replace")); p += pl
    out = {"file": fn, "factory_default": fn.endswith("Fact.tfx"), "volume": vol, "folder": "/".join(parts[:-1]) if parts else ""}
    if p + 20 < len(b) and b[p + 5:p + 7] == b"\x5a\x01":
        q = p + 5 + 12
        if q + 4 <= len(b):
            d2 = u32(b, q); q += 4
            sparts = []
            for _ in range(min(d2, 64)):
                if q + 4 > len(b):
                    break
                pl = u32(b, q); q += 4
                if q + pl > len(b):
                    break
                sparts.append(b[q:q + pl].decode("utf-8", "replace")); q += pl
            if sparts:
                out["session_folder"] = "/".join(sparts)
    return out


def settings_files(d, tree):
    """settings-file list 0x2027 (u32 count) > 0x2064 per used settings file: volume, folder parts, file name. One entry per
    plug-in instance; '<codes>Fact.tfx' = the factory default of that plug-in, any other name = a loaded preset (MIX_07 s17
    'Add Fullness.tfx'). An insert points here with "settings_index" (u16 at the start of its 0x2613)."""
    t = find(tree, 0x2027)
    out = []
    for k in (x for x in (t["kids"] if t else []) if x["ct"] == 0x2064):
        b = d[k["pos"] + 9:probe_end(k)]
        parsed = _parse_2064(b)
        if parsed is not None:
            out.append(parsed)
        else:
            names = [m.group(0).decode("latin-1") for m in re.finditer(rb"[ -~]{3,}", b)]
            fn = next((n for n in names if n.lower().endswith(".tfx")), names[-1] if names else "")
            out.append({"file": fn, "factory_default": fn.endswith("Fact.tfx")})
    return out


def plugin_table(d, tree):
    """plug-in table 0x1018 (u32 count) > 0x1017: u8 kind (3 effect, 4 instrument), u32 length + display name, 12 bytes
    of AAX codes (each 4 reversed), 01 00 01 00, u32 0, u32 length + vendor id (com.<vendor>...; empty for some third-party
    entries), tail. Index = position in the table (the u16 of 0x2626 of a slot points here)."""
    t = find(tree, 0x1018)
    out = []
    if not t:
        return out
    for i, k in enumerate(x for x in t["kids"] if x["ct"] == 0x1017):
        b = d[k["pos"] + 9:probe_end(k)]
        try:
            ln = u32(b, 1)
            name = b[5:5 + ln].decode("utf-8", "replace")
            codes = b[5 + ln:17 + ln]
            q = b.find(b"com.", 17 + ln)
            vid = ""
            if q >= 4:
                vl = u32(b, q - 4)
                vid = b[q:q + vl].decode("latin-1") if 0 < vl < 200 else ""
            out.append({"index": i, "name": name, "vendor_id": vid, "kind": {3: "effect", 4: "instrument"}.get(b[0], b[0]),
                        "codes": [codes[j:j + 4][::-1].decode("latin-1") for j in (0, 4, 8)]})
        except (IndexError, struct.error):
            out.append({"index": i, "name": None, "vendor_id": "", "kind": None, "codes": []})
    return out


def _subtree(n):
    """All blocks below n (depth first, file order)."""
    for k in n["kids"]:
        yield k
        yield from _subtree(k)


CHANNEL_BLOCKS = {0x261C: "audio", 0x261E: "aux", 0x261D: "master", 0x2621: "instrument", 0x2620: "midi", 0x263B: "folder"}


def strips(d, tree):
    """mixer strips per channel block of 0x2624 (one block per track, track-list order). Strip = the first 0x260D with
    lanes and an output (0x260E), else the first with lanes; the other 0x260D with lanes of the block = "sends" (hypothesis).
    Without 0x2624 (older layouts): every 0x260D with lanes, as in ."""
    top = find(tree, 0x2624)
    if not top:
        return [dict(_strip(d, st), channel=None, track=None, sends=[]) for st in probe.walk(tree)
                if st["ct"] == 0x260D and any(k["ct"] == 0x260A for k in st["kids"])]
    out = []
    for i, ch in enumerate(top["kids"]):
        lanes = [x for x in _subtree(ch) if x["ct"] == 0x260D and any(k["ct"] == 0x260A for k in x["kids"])]
        if not lanes:
            continue
        main = next((x for x in lanes if any(k["ct"] == 0x260E for k in x["kids"])), lanes[0])
        out.append(dict(_strip(d, main), channel=CHANNEL_BLOCKS.get(ch["ct"], "%04X" % ch["ct"]), track=i,
                        sends=[_strip(d, x) for x in lanes if x is not main]))
    return out


AUDIO_EXT = (".wav", ".aif", ".aiff", ".bwf", ".mp3", ".m4a", ".flac", ".mxf", ".sd2")
UMID_LABEL = bytes.fromhex("060a2b34010101050101")


def umids(d, tree):
    """{file stem: basic UMID hex} of the audio files: file names in the order of the first 0x103A of 0x1004, one 0x1003 per
    file in the same order; the 32-byte UMID is found by its SMPTE label (block offset +252 / +268 in Pro Tools 2026 saves,
    +268 / +280 in the corpus). A file without a UMID gives "". Order mapping = hypothesis checked by T39 (V6)."""
    lst = find(tree, 0x1004)
    if not lst:
        return {}
    names_blk = next((k for k in lst["kids"] if k["ct"] == 0x103A), None)
    names = [t for _, t in probe.lp_strings(d, names_blk["pos"] + 9, probe_end(names_blk), 1, 400)] if names_blk else []
    names = [n for n in names if n.lower().endswith(AUDIO_EXT)]
    recs = [k for k in lst["kids"] if k["ct"] == 0x1003]
    out = {}
    for n, r in zip(names, recs):
        i = d.find(UMID_LABEL, r["pos"], probe_end(r))
        out[os.path.splitext(n)[0]] = d[i:i + 32].hex() if i >= 0 else ""
    return out


def ticks_to_seconds(ticks, tmap):
    """Ticks -> seconds through a constant-step tempo map [{ticks, bpm}] (sorted; the first event applies from 0).
    Raises ValueError for a tempo <= 0 (seen in generated acceptance sessions: Pro Tools keeps bpm 0 without complaint)."""
    if any(e["bpm"] <= 0 for e in tmap or []):
        raise ValueError("tempo map holds a tempo <= 0 bpm")
    if not tmap:
        tmap = [{"ticks": 0, "bpm": 120.0}]
    ev = sorted(tmap, key=lambda e: e["ticks"])
    secs, prev_t, prev_bpm = 0.0, 0, ev[0]["bpm"]
    for e in ev:
        if e["ticks"] >= ticks:
            break
        secs += (e["ticks"] - prev_t) / TPQ * 60.0 / prev_bpm
        prev_t, prev_bpm = e["ticks"], e["bpm"]
    return secs + (ticks - prev_t) / TPQ * 60.0 / prev_bpm


def seconds_to_ticks(secs, tmap):
    """Seconds -> ticks (inverse of ticks_to_seconds); ValueError for a tempo <= 0."""
    if any(e["bpm"] <= 0 for e in tmap or []):
        raise ValueError("tempo map holds a tempo <= 0 bpm")
    if not tmap:
        tmap = [{"ticks": 0, "bpm": 120.0}]
    ev = sorted(tmap, key=lambda e: e["ticks"])
    acc, prev_t, prev_bpm = 0.0, 0, ev[0]["bpm"]
    for e in ev:
        seg = (e["ticks"] - prev_t) / TPQ * 60.0 / prev_bpm
        if acc + seg >= secs:
            break
        acc += seg
        prev_t, prev_bpm = e["ticks"], e["bpm"]
    return prev_t + (secs - acc) * prev_bpm / 60.0 * TPQ



def _strings_lp(b):
    """length-prefixed strings (u32 LE length 1..64 + printable bytes) in b, in order, without overlap."""
    out, i = [], 0
    while i + 4 <= len(b):
        n = u32(b, i)
        s = b[i + 4:i + 4 + n]
        if 1 <= n <= 64 and len(s) == n and all(32 <= c < 127 for c in s):
            out.append(s.decode("latin-1"))
            i += 4 + n
        else:
            i += 1
    return out


def region_gain_links(d, tree):
    """{block position of an audio region 0x2628 (child of 0x2629): clip-gain entry index}. The u32 sits 22 bytes before
    the end of the record (just before the 16-byte clip id); MIX_07 s00 - s22: every audio region, consistent through reorderings.
    Generality run 2026-11-11: the tail 00 00 ff ff 04 00 04 00 + 20 x 00 + flag + u32 index is found by search, because older
    record versions (block kinds 3 / 4, no 16-byte clip id at the end) end differently; 0xffffffff = no clip gain (None). Verified across test sessions.md."""
    out = {}
    for w in probe.walk(tree):
        if w["ct"] != 0x2629:
            continue
        for k in w["kids"]:
            if k["ct"] == 0x2628:
                e = probe_end(k)
                p = d.rfind(b"\x00\x00\xff\xff\x04\x00\x04\x00", k["pos"] + 9, e)   # tail of every record version
                if p >= 0 and p + 33 <= e and d[p + 8:p + 28] == b"\x00" * 20:
                    v = u32(d, p + 29)
                    out[k["pos"]] = None if v == 0xFFFFFFFF else v                # 0xffffffff = no clip gain
    return out


def _group_inner(tree):
    """positions of all blocks inside clip groups 0x2428 (their 0x1054 playlists are not track playlists)."""
    return {n["pos"] for g in probe.walk(tree) if g["ct"] == 0x2428 for n in probe.walk(g["kids"])}


def _entry_kind(o, tr=None):
    """own byte 18 = 1 -> "group". else the first byte behind the 0x104F inside its 0x1050 parent (tr): 1 -> "fade",
    0 -> "clip" (the originals: fade-outs carry byte 15 = 3, clips byte 15 = 2 or 1; ESI X1 run 2026-11-14); without a parent the
    old rule of byte 15 (3 clip, 1 fade, other = the number)."""
    if o[18] == 1:
        return "group"
    if tr is not None:
        return "fade" if tr == 1 else "clip"
    return {3: "clip", 1: "fade"}.get(o[15], o[15])


def _trailers(d, kids):
    """{position of a 0x104F: first byte behind it inside its 0x1050 parent (1 = fade entry, 0 = clip entry)}."""
    out = {}
    for n in probe.walk(kids):
        if n["ct"] == 0x1050 and n["kids"] and n["kids"][0]["ct"] == 0x104F:
            k = n["kids"][0]
            q = k["pos"] + 7 + k["size"]
            if q < n["pos"] + 7 + n["size"]:
                out[k["pos"]] = d[q]
    return out


def audio_placements(d, tree, channels=False, groups=False):
    """playlists of audio tracks: 0x1054 > 0x1052 (u32 + playlist name) > 0x1050 > 0x104F. Per entry: kind ("clip" when
    own byte 15 = 3, "fade" when 1, else the number; kind 2 = a third kind, index always inside the region list, meaning open),
    index (u16 at own 2: region index or fade index), position u40 at own 7: "ticks" (10^12 offset removed) when own byte 14 =
    0x40, else "samples", muted (own byte 0), link (i16 at own 16; 25 or -2 seen, meaning open). Corpus 2026-11-11 (599 files,
    2 773 entries): kind 3 always inside the region list, kind 1 inside the fade list outside special containers."""
    out = {}
    inner = _group_inner(tree)
    for top in probe.walk(tree):
        if top["ct"] != 0x1054 or ((top["pos"] in inner) != groups):          # clip group content apart
            continue
        for pl in top["kids"]:
            if pl["ct"] != 0x1052:
                continue
            p = pl["pos"] + 9
            n = u32(d, p)
            if not 0 < n < 256:
                continue
            name = d[p + 4:p + 4 + n].decode("utf-8", "replace")
            lst = []
            trs = _trailers(d, pl["kids"])
            for e in probe.walk(pl["kids"]):
                if e["ct"] != 0x104F:
                    continue
                o = d[e["pos"] + 9:probe_end(e)]
                if len(o) < 18:
                    continue
                kd = _entry_kind(o, trs.get(e["pos"]))              # "group"; fade / clip from the 0x1050 byte
                ent = {"kind": kd, "sub": o[15], "index": struct.unpack_from("<H", o, 2)[0], "muted": o[0] == 1, "link": struct.unpack_from("<h", o, 16)[0]}
                lp = next((k for k in e["kids"] if k["ct"] == 0x242B), None)         # clip loop (trim_ticks, iter_ticks)
                if lp and lp["size"] >= 2 + 47:
                    ent["loop"] = _clip_loop(d[lp["pos"] + 9:lp["pos"] + 7 + lp["size"]])
                if o[14] == 0x40:                                   # tick position (10^12 offset), else samples (corpus: 0x40 / 0x00)
                    ent["ticks"] = plain(le(o, 7, 5))
                else:
                    sv = le(o, 7, 5)
                    ent["samples"] = plain(sv) if groups and sv >= 10 ** 12 else (sv - (1 << 40) if sv >= (1 << 39) else sv)
                lst.append(ent)
            if channels:                                            # one list per channel playlist (stereo = L, R)
                out.setdefault(name, []).append(lst)
            elif lst or name not in out:
                out[name] = lst
    return out


def fades(d, tree):
    """fade objects 0x262F in file order (index = the "fade" index of audio_placements). Own data: 5 bytes, a width
    byte (high nibble = width of value 1, low nibble = width of value 2), 2 bytes, the values from own 8 (value 1 = length
    in samples, or pre-roll on 34 B centered crossfades where length2 is total duration), then type (1 crossfade, 2 fade_out,
    3 fade_in; others raw), slope (1 equal_power, 2 equal_gain), curve (f32 LE), S-curve bytes at +4 / +7; size = byte len."""
    out = []
    for e in probe.walk(tree):
        if e["ct"] != 0x262F:
            continue
        o = d[e["pos"] + 9:probe_end(e)]
        if len(o) < 12:
            continue
        w1, w2 = o[5] >> 4, o[5] & 15
        p = 8 + w1 + w2
        if p + 10 > len(o):
            continue
        f = {"length": le(o, 8, w1) if w1 else 0, "type": {1: "crossfade", 2: "fade_out", 3: "fade_in"}.get(o[p], o[p]),
             "slope": {1: "equal_power", 2: "equal_gain"}.get(o[p + 1], o[p + 1]),
             "curve": round(struct.unpack_from("<f", o, p + 2)[0], 6), "s_curve": [o[p + 6], o[p + 9]], "size": len(o)}
        if w2:
            f["length2"] = le(o, 8 + w1, w2)
        out.append(f)
    return out


def audio_playlists(d, tree):
    """[[name, entries], ...] of every audio playlist in file order (entries as in audio_placements)."""
    out = []
    inner = _group_inner(tree)                                  # clip group content is not a track playlist
    for top in probe.walk(tree):
        if top["ct"] != 0x1054 or top["pos"] in inner:
            continue
        for pl in top["kids"]:
            if pl["ct"] != 0x1052:
                continue
            p = pl["pos"] + 9
            n = u32(d, p)
            if not 0 < n < 256:
                continue
            name = d[p + 4:p + 4 + n].decode("utf-8", "replace")
            lst = []
            trs = _trailers(d, pl["kids"])
            for e in probe.walk(pl["kids"]):
                if e["ct"] != 0x104F:
                    continue
                o = d[e["pos"] + 9:probe_end(e)]
                if len(o) < 18:
                    continue
                ent = {"kind": _entry_kind(o, trs.get(e["pos"])), "sub": o[15], "index": struct.unpack_from("<H", o, 2)[0], "muted": o[0] == 1,
                       "link": struct.unpack_from("<h", o, 16)[0]}
                if o[14] == 0x40:
                    ent["ticks"] = plain(le(o, 7, 5))
                else:
                    sv = le(o, 7, 5)
                    ent["samples"] = sv - (1 << 40) if sv >= (1 << 39) else sv
                lst.append(ent)
            if lst or name not in [x[0] for x in out]:
                out.append([name, lst])
    return out


def plugin_lane_names(d, n):
    """parameter name and id of a plug-in automation entry 0x260F (strings after its lane 0x260B): first = name,
    last = id (EQ3 "Output Level" / "outp"; Sci-Fi uses the name as id)."""
    tail = d[(probe_end(n["kids"][-1]) if n["kids"] else n["pos"] + 10):probe_end(n)]
    s = _strings_lp(tail)
    return (s[0], s[-1]) if s else (None, None)


def aux_input_path(d, ch):
    """input path of an aux / routing-folder channel 0x261E: u16 LE one byte after the end of the track info 0x102D
    inside the box 0x261B (0xffff = no input; MIX_07 s09: 6 = Bus 1). None when the layout does not match."""
    box = next((x for x in ch["kids"] if x["ct"] == 0x261B), None)
    if not box or not box["kids"] or box["kids"][0]["ct"] != 0x102D:
        return None
    e = probe_end(box["kids"][0])
    v = struct.unpack_from("<H", d, e + 1)[0]
    return None if v == 0xFFFF else v


def track_input(d, ch):
    """(input_name, input_type) of an audio / aux / routing-folder / instrument channel from the input record inside 0x261B
    (after the running numbers: 01 01 0a 00 + 40B runnum + 00000000 08000000 00 + u32 name_len + name + 00*4 + 12 bytes + 00 + input_type;
    type 2 = internal bus, 0 = hardware/none)."""
    box = next((x for x in ch["kids"] if x["ct"] == 0x261B), None)
    if not box or not box["kids"] or box["kids"][0]["ct"] != 0x102D:
        return None, None
    tail = d[probe_end(box["kids"][0]):probe_end(box)]
    i = tail.find(b"\x01\x01\x0a\x00")
    if i < 0 or i + 57 > len(tail):
        return None, None
    ln = u32(tail, i + 53)
    if ln > 256 or i + 57 + ln + 18 > len(tail):
        return None, None
    nm = tail[i + 57:i + 57 + ln].decode("utf-8", "replace") if ln else None
    return nm, tail[i + 57 + ln + 17]


def session_format(d, tree):
    """sample rate and bit depth from 0x1028 (offline byte map of empty sessions, T22 variants 16 / 24 / 32 float);
    own byte 0 = 3 ('WAV') or 4 ('AIFF'), u32 at own 2 = sample rate, own +24 = interleaved flag (1/0);
    the record ends with ... float flag (end - 8), bits (end - 6), ..."""
    n = find(tree, 0x1028)
    if not n:
        return {}
    a, e = n["pos"] + 9, probe_end(n)
    if e - a < 12 or d[a] not in (3, 4):
        return {}
    out = {"sample_rate": u32(d, a + 2), "bit_depth": d[e - 6], "float": d[e - 8] == 1,
           "file_format": "WAV" if d[a] == 3 else "AIFF"}
    if e - a >= 25:
        out["interleaved"] = bool(d[a + 24])
    return out


TC_RATES = {1: "24", 2: "25", 3: "29.97", 5: "29.97 Drop", 7: "30", 8: "30 Drop", 9: "23.976", 10: "50",
            11: "59.94", 12: "59.94 Drop", 13: "60", 14: "60 Drop", 15: "47.952", 16: "48", 17: "100",
            18: "119.88", 19: "119.88 Drop", 20: "120", 21: "120 Drop"}

TC_EXACT = {
    1: (24, 1, False),
    2: (25, 1, False),
    3: (30000, 1001, False),
    5: (30000, 1001, True),
    7: (30, 1, False),
    8: (30, 1, True),
    9: (24000, 1001, False),
    10: (50, 1, False),
    11: (60000, 1001, False),
    12: (60000, 1001, True),
    13: (60, 1, False),
    14: (60, 1, True),
    15: (48000, 1001, False),
    16: (48, 1, False),
    17: (100, 1, False),
    18: (120000, 1001, False),
    19: (120000, 1001, True),
    20: (120, 1, False),
    21: (120, 1, True),
}


def _round_half_up(num, den):
    return (2 * num + den) // (2 * den)


def timecode_to_samples(tc_str, rate_code, sample_rate):
    """Exact rational SMPTE timecode -> integer samples across all 19 Pro Tools rate codes."""
    if sample_rate <= 0:
        raise ValueError("sample_rate must be > 0")
    spec = TC_EXACT.get(int(rate_code))
    if spec is None:
        raise ValueError("unsupported timecode rate code %r" % (rate_code,))
    fps_num, fps_den, is_drop = spec
    parts = tc_str.strip().replace(";", ":").split(":")
    if len(parts) != 4:
        raise ValueError("invalid timecode %r: expected HH:MM:SS:FF" % (tc_str,))
    hh, mm, ss, ff = (int(x) for x in parts)
    nominal = (fps_num + fps_den - 1) // fps_den
    drop = 2 * (nominal // 30) if is_drop else 0
    if hh < 0 or not (0 <= mm < 60) or not (0 <= ss < 60) or not (0 <= ff < nominal):
        raise ValueError("out-of-range timecode %r for nominal %d fps" % (tc_str, nominal))
    if is_drop and ss == 0 and (mm % 10) != 0 and ff < drop:
        raise ValueError("invalid drop-frame label %r (dropped frames 0..%d)" % (tc_str, drop - 1))
    total_min = 60 * hh + mm
    frames = (60 * total_min + ss) * nominal + ff - drop * (total_min - total_min // 10)
    return _round_half_up(frames * int(sample_rate) * fps_den, fps_num)


def samples_to_timecode(samples, rate_code, sample_rate):
    """Exact integer samples -> SMPTE timecode string (':' NDF, ';' DF, 3-digit FF for >=100 fps)."""
    if sample_rate <= 0 or samples < 0:
        raise ValueError("samples must be >= 0 and sample_rate > 0")
    spec = TC_EXACT.get(int(rate_code))
    if spec is None:
        raise ValueError("unsupported timecode rate code %r" % (rate_code,))
    fps_num, fps_den, is_drop = spec
    nominal = (fps_num + fps_den - 1) // fps_den
    drop = 2 * (nominal // 30) if is_drop else 0
    f = _round_half_up(int(samples) * fps_num, int(sample_rate) * fps_den)
    if is_drop and drop > 0:
        q10 = 600 * nominal - 9 * drop
        p1 = 60 * nominal - drop
        d10, r10 = divmod(f, q10)
        f += 9 * drop * d10 + (drop * ((r10 - drop) // p1) if r10 >= drop else 0)
    f, ff = divmod(f, nominal)
    f, ss = divmod(f, 60)
    hh, mm = divmod(f, 60)
    sep = ";" if is_drop else ":"
    width = 3 if nominal > 100 else 2
    return "%02d:%02d:%02d%s%0*d" % (hh, mm, ss, sep, width, ff)
PULL_CODES = {12000: "None", 12011: "+0.1%", 11988: "-0.1%", 12500: "+4.1667%", 12512: "+4.1667% +0.1%",
              12487: "+4.1667% -0.1%", 11520: "-4%", 11531: "-4% +0.1%", 11508: "-4% -0.1%"}
RECORD_MODES = {0: "Normal", 1: "Loop", 2: "Destructive", 3: "QuickPunch", 4: "TrackPunch", 5: "DestructivePunch"}


_KEY_MAJ = {-7: "Cb", -6: "Gb", -5: "Db", -4: "Ab", -3: "Eb", -2: "Bb", -1: "F", 0: "C", 1: "G", 2: "D", 3: "A", 4: "E", 5: "B", 6: "F#", 7: "C#"}
_KEY_MIN = {-7: "Abm", -6: "Ebm", -5: "Bbm", -4: "Fm", -3: "Cm", -2: "Gm", -1: "Dm", 0: "Am", 1: "Em", 2: "Bm", 3: "F#m", 4: "C#m", 5: "G#m", 6: "D#m", 7: "A#m"}


def key_signatures(d, tree):
    """key signature ruler 0x271B > 0x2433 > 0x2432 (11 bytes: u56 LE ticks + 10^12, +8 major 1/minor 0, +9 sharps 1/flats 0, +10 count)."""
    b33 = find(tree, 0x2433)
    if not b33:
        return []
    out = []
    for k in b33["kids"]:
        if k["ct"] != 0x2432 or k["size"] < 13:
            continue
        p = k["pos"] + 9
        t_raw = int.from_bytes(d[p:p + 7], "little")
        ticks = t_raw - 10 ** 12 if t_raw >= 10 ** 12 else t_raw
        maj, sh, cnt = bool(d[p + 8]), bool(d[p + 9]), d[p + 10]
        sf = cnt if sh else -cnt
        out.append({"ticks": ticks, "key": (_KEY_MAJ if maj else _KEY_MIN).get(sf, str(sf)), "major": maj, "sharps": sf})
    return out


def clip_group_regions(d, tree):
    """clip-group definitions 0x262C > 0x262B > 0x2628 (kind 4) + <IHHB trailer."""
    b2c = find(tree, 0x262C)
    if not b2c:
        return []
    out = []
    for k in b2c["kids"]:
        if k["ct"] != 0x262B or not k["kids"] or k["kids"][0]["ct"] != 0x2628:
            continue
        r = k["kids"][0]
        p0, re_ = r["pos"] + 9, probe_end(r)
        if p0 + 9 > re_:
            continue
        ln = u32(d, p0)
        p = p0 + 4 + ln
        if p + 5 > re_:
            continue
        nm = d[p0 + 4:p].decode("utf-8", "replace")
        _, _, _, _, vals, _, _ = _decode_2628_varints(d, p)
        if not vals:
            vals = [0, 0, 0, 0]
        b23 = next((x for x in r["kids"] if x["ct"] == 0x2523), None)
        post = d[probe_end(b23["kids"][-1]):probe_end(b23)] if b23 and b23["kids"] else b""
        is_ticks = bool(d[r["pos"] + 1] == 4 or (len(post) >= 28 and post[24] == 1))
        ent = {"name": nm, "unit": "ticks" if is_ticks else "samples",
               "length": vals[1], "origin": vals[2]}
        if is_ticks:
            ent["length_ticks"] = vals[1]
            ent["origin_ticks"] = vals[2]
        else:
            ent["length_samples"] = vals[1]
        if len(post) >= 20:
            ent["member_playlist_index"] = u32(post, 16)
        if len(post) >= 76:
            ent["tempo"] = round(struct.unpack_from("<d", post, 36)[0], 4)
        ktail = d[re_:probe_end(k)]
        if len(ktail) >= 6:
            ent["group_id"] = u32(ktail, 0)
            ent["channel"] = struct.unpack_from(">H", ktail, 4)[0]
        out.append(ent)
    return out


def timeline(d, tree):
    """session timecode rate, drop-frame flag, start timecode string, and audio pull factor
    from 0x204B, 0x204D, and 0x2023."""
    out = {}
    b4d = find(tree, 0x204D)
    if b4d and b4d["size"] >= 2 + 44:
        p, e = b4d["pos"] + 9, probe_end(b4d)
        ln1 = u32(d, p + 25)
        q = p + 29 + ln1 if 0 < ln1 <= 32 and p + 29 + ln1 + 16 <= e else p + 40
        rc = d[q] if q < e and d[q] in TC_RATES else d[p]
        out["timecode_rate_code"] = rc
        out["timecode_rate"] = TC_RATES.get(rc, str(rc))
        out["drop_frame"] = rc in (5, 8, 12, 14, 19, 21)
        if q + 16 <= e:
            ln2 = u32(d, q + 12)
            if 0 < ln2 <= 32 and q + 16 + ln2 <= e:
                tc = d[q + 16:q + 16 + ln2].decode("ascii", "replace")
                out["session_start"] = tc
                if ";" in tc:
                    out["drop_frame"] = True
    b4b = find(tree, 0x204B)
    if b4b and "timecode_rate" not in out and b4b["size"] >= 2 + 163:
        rc = d[b4b["pos"] + 9 + 162]
        out["timecode_rate_code"] = rc
        out["timecode_rate"] = TC_RATES.get(rc, str(rc))
        out["drop_frame"] = rc in (5, 8, 12, 14, 19, 21)
    b23 = find(tree, 0x2023)
    if b23 and b23["size"] >= 2 + 64:
        pf = struct.unpack_from("<H", d, b23["pos"] + 9 + 62)[0]
        out["pull_code"] = pf
        out["pull"] = PULL_CODES.get(pf, str(pf))
    return out


def _own_bytes(d, n):
    """Non-child own bytes of container block n (excluding 9-byte header)."""
    out, cur = [], n["pos"] + 9
    for k in n["kids"]:
        if k["pos"] > cur:
            out.append(d[cur:k["pos"]])
        cur = probe_end(k)
    end = probe_end(n)
    if end > cur:
        out.append(d[cur:end])
    return b"".join(out)


def session_settings(d, tree):
    """ (R12, T48/T52/T57/T66): 0x2058 (record_mode, loop_playback), 0x2024/0x2056 (edit_mode, smart_tool),
    0x201F (sub_counter), and 0x2016 (timeline_selection_ticks)."""
    b58 = find(tree, 0x2058)
    out = {}
    if b58 and b58["size"] >= 2 + 49:
        p = b58["pos"] + 9
        rc = d[p + 48] if d[p + 48] in RECORD_MODES and d[p + 48] != 0 else d[p + 32]
        if rc == 0 and find(tree, 0xD470) is not None:
            rc = 2
        out = {"record_mode_code": rc, "record_mode": RECORD_MODES.get(rc, rc), "loop_playback": bool(d[p + 26])}
    b24 = find(tree, 0x2024)
    if b24 and b24["size"] >= 4:
        em = struct.unpack_from("<H", d, b24["pos"] + 9)[0]
        out["edit_mode_code"] = em
        out["edit_mode"] = {0: "Shuffle", 3: "Grid"}.get(em, str(em))
    b56 = find(tree, 0x2056)
    if b56:
        o56 = _own_bytes(d, b56)
        if len(o56) >= 26:
            out["smart_tool"] = bool(o56[0])
            out["edit_tool_code"] = o56[13]
    b1f = find(tree, 0x201F)
    if b1f:
        o1f = _own_bytes(d, b1f)
        if len(o1f) >= 6:
            sc = o1f[4]
            out["sub_counter_code"] = sc
            out["sub_counter"] = {1: "BarsBeats", 4: "Samples"}.get(sc, str(sc))
    b16 = find(tree, 0x2016)
    if b16:
        o16 = _own_bytes(d, b16)
        if len(o16) >= 68 and o16[59] == 0x40 and o16[67] == 0x40:
            s0 = int.from_bytes(o16[52:59], "little")
            s1 = int.from_bytes(o16[60:67], "little")
            out["timeline_selection_ticks"] = [plain(s0), plain(s1)]
    return out


_ELASTIC_ALGOS = {"Polyphonic", "Rhythmic", "Monophonic", "Varispeed", "X-Form"}


def elastic_mode(d, ch):
    """Elastic Audio algorithm name in channel's 0x200B block, or None."""
    b0b = next((n for n in _subtree(ch) if n["ct"] == 0x200B), None)
    if not b0b:
        return None
    for _, s in reversed(probe.lp_strings(d, b0b["pos"] + 9, probe_end(b0b), 5, 20)):
        if s in _ELASTIC_ALGOS:
            return s
    return None


def elastic_params(d, ch):
    """Elastic Audio processor 'elckComplete Controls State' named params in 0x200B > 0x252C, or {}."""
    b0b = next((n for n in _subtree(ch) if n["ct"] == 0x200B), None)
    if not b0b:
        return {}
    out = {}
    for b in [n for n in _subtree(b0b) if n["ct"] == 0x252C]:
        s, e = b["pos"] + 9, probe_end(b)
        idx = d.find(b"elckComplete Controls State", s, e)
        if idx >= 0:
            out.update(_params(d[idx + 4:e]))
    return out


def track_timebase(d, ch):
    """timebase for MIDI / Instrument tracks from 0x2010 before fe ff 01."""
    b10 = next((n for n in _subtree(ch) if n["ct"] == 0x2010), None)
    if not b10:
        return None
    s, e = b10["pos"] + 9, probe_end(b10)
    idx = d.find(b"\xfe\xff\x01", s, e)
    if idx > s and d[idx - 1] in (1, 2):
        return "Ticks" if d[idx - 1] == 2 else "Samples"
    return None


def track_comment(d, ch):
    """(comment, height code) of a channel block: its 0x2015, after the first child block 8 bytes (the last two = u16 height
    code, hypothesis), then u32 length + text (e.g. 'ptx comment 37'). (None, None) when the layout does not fit."""
    b = next((n for n in _subtree(ch) if n["ct"] == 0x2015), None)
    if not b:
        return None, None
    s, e = b["pos"] + 9, probe_end(b)
    if d[s] != 0x5A:
        return None, None
    c = s + 7 + u32(d, s + 3)
    if c + 12 > e:
        return None, None
    ln = u32(d, c + 8)
    if ln > 4096 or c + 12 + ln + 9 > e:
        return None, None
    return d[c + 12:c + 12 + ln].decode("utf-8", "replace"), struct.unpack_from("<H", d, c + 6)[0]


def region_lists(d, tree):
    """per region of the MIDI library (0x2634 > 0x2633 wrapper): index of its chunk in 0x2000 = u32 at the end of the wrapper
. List in library order."""
    lib = find(tree, 0x2634)
    return [u32(d, probe_end(w) - 4) for w in (lib["kids"] if lib else []) if w["ct"] == 0x2633]


CTRL_KINDS = {1: "pitch_bend", 2: "controller", 3: "program", 4: "channel_pressure", 5: "poly_pressure"}


def midi_lists(d, tree, warn):
    """the chunks ('MdChun') of the MIDI data block 0x2000 in file order: notes of 'MdNLB' list 1 as [start, key, length,
    velocity] (35-byte records: start u40, 00 00 40, key, length u40, 00 00 40, velocity) and the controller sets 'MdCDS'
    (Mdss byte 0 kind, byte 1 number; MdCD u32 count + 12-byte records: time u40, 00 00 40, i32 value); "sysex"."""
    b = next((t for t in tree if t["ct"] == 0x2000), None)
    if not b:
        return []
    x = d[b["pos"] + 9:probe_end(b)]
    at, i = [], x.find(b"MdChun")
    while i >= 0:
        at.append(i); i = x.find(b"MdChun", i + 1)
    at.append(len(x))
    out = []
    for k in range(len(at) - 1):
        seg = x[at[k]:at[k + 1]]
        ent = {"notes": [], "controllers": []}
        j = seg.find(b"MdNLB")
        if j >= 0:
            n = u32(seg, j + 11)
            if j + 15 + 35 * n <= len(seg):
                for r in range(n):
                    o = j + 15 + 35 * r
                    ent["notes"].append([plain(le(seg, o, 5)), seg[o + 8], le(seg, o + 9, 5), seg[o + 17]])
            else:
                warn.append("MIDI chunk %d: note count %d does not fit" % (k, n))
        j = seg.find(b"MdCDS")
        while j >= 0:
            body = seg[j + 11:j + 11 + u32(seg, j + 7)]
            s_, c_ = body.find(b"Mdss"), body.find(b"MdCD", 4)
            if s_ >= 0 and c_ >= 0:
                m = body[s_ + 10:s_ + 12]
                n = u32(body, c_ + 10)
                if c_ + 14 + 12 * n <= len(body):
                    pts = [[plain(le(body, c_ + 14 + 12 * r, 5)), struct.unpack_from("<i", body, c_ + 22 + 12 * r)[0]] for r in range(n)]
                    cdict = {"kind": CTRL_KINDS.get(m[0], m[0]), "number": m[1], "points": pts}
                    if m[0] == 3 and pts:
                        cdict["program_banks"] = [{"ticks": pt[0], "program": pt[1] & 0xFF,
                                                   "bank_msb": ((pt[1] >> 8) & 0x3FFF) >> 7,
                                                   "bank_lsb": ((pt[1] >> 8) & 0x3FFF) & 0x7F} for pt in pts]
                    ent["controllers"].append(cdict)
                pos_sub = c_ + 14 + 12 * n
                if n == 0 and pos_sub + 4 <= len(body):
                    nsub = u32(body, pos_sub)
                    if 0 < nsub < 1024:
                        curves = []
                        sp = pos_sub + 4
                        for _ in range(nsub):
                            si = body.find(b"Mdss", sp)
                            ci = body.find(b"MdCD", si + 4) if si >= 0 else -1
                            if si < 0 or ci < 0 or ci + 14 > len(body):
                                break
                            sm = body[si + 10:si + 29]
                            cn = u32(body, ci + 10)
                            if ci + 14 + 12 * cn > len(body):
                                break
                            cpts = [[plain(le(body, ci + 14 + 12 * r, 5)), struct.unpack_from("<i", body, ci + 22 + 12 * r)[0]] for r in range(cn)]
                            curves.append({"kind": CTRL_KINDS.get(sm[0], sm[0]), "number": sm[1],
                                           "mpe_channel": sm[6], "key": sm[7], "velocity": sm[8],
                                           "note_start": plain(le(body, si + 19, 5)), "points": cpts})
                            sp = ci + 14 + 12 * cn
                        if curves:
                            ent.setdefault("mpe_curves", []).extend(curves)
            j = seg.find(b"MdCDS", j + 5)
        ent["sysex"] = []                                                      # SysEx list of 'MdTEL'
        j = seg.find(b"MdTEL")
        if j >= 0 and u32(seg, j + 7) > 4:
            body = seg[j + 11:j + 11 + u32(seg, j + 7)]
            n, o = u32(body, 0), 4
            for _ in range(n):
                if o + 20 > len(body) or body[o + 5:o + 8] != b"\x00\x00\x40":
                    warn.append("MIDI chunk %d: SysEx record %d does not match" % (k, len(ent["sysex"])))
                    break
                ln = u32(body, o + 15)
                ent["sysex"].append([plain(le(body, o, 5)), body[o + 19:o + 19 + ln].hex()])
                o += 19 + ln
        out.append(ent)
    return out


def track_colours(d, tree):
    """{track name: colour index or None (default)} from 0x251a (byte 9 = 0): u32 name length + name at +11, i16 at name end + 62."""
    out = {}
    for n in probe.walk(tree):
        if n["ct"] != 0x251A or d[n["pos"] + 9] != 0:
            continue
        ln = u32(d, n["pos"] + 11)
        e = n["pos"] + 15 + ln
        if ln > 255 or e + 64 > n["pos"] + 7 + n["size"]:
            continue
        nm = d[n["pos"] + 15:e].decode("utf-8", "replace")
        v = struct.unpack_from("<h", d, e + 62)[0]
        out.setdefault(nm, None if v == -2 else v)
    return out


def groups(d, tree):
    """group names (0x202B > 0x202A: u32 length + name at data +0), each once, file order (e.g. 'G1')."""
    out = []
    for p in probe.walk(tree):
        if p["ct"] != 0x202B:
            continue
        for g in p["kids"]:
            if g["ct"] == 0x202A:
                ln = u32(d, g["pos"] + 9)
                if 0 < ln <= 64 and g["pos"] + 13 + ln <= probe_end(g):
                    nm = d[g["pos"] + 13:g["pos"] + 13 + ln].decode("utf-8", "replace")
                    if nm not in out:
                        out.append(nm)
    return out


def group_details(d, tree, trks):
    """full group definitions from the first copy of 0x202B > 0x202A:
    name, type (1 Edit, 2 Mix, 3 Mix/Edit), id (u32, 0xffffffff for <ALL>), enabled (bool), member_indices (u16 track indices),
    members (track names), and attributes (u32 bitmask)."""
    b2b = find(tree, 0x202B)
    if not b2b or b2b["size"] < 6:
        return []
    cnt = u32(d, b2b["pos"] + 9)
    kids = [k for k in b2b["kids"] if k["ct"] == 0x202A][:cnt]
    out = []
    for k in kids:
        p, e = k["pos"] + 9, probe_end(k)
        if p + 4 > e:
            continue
        nl = u32(d, p)
        q = p + 4 + nl
        if nl > 256 or q + 11 > e:
            continue
        nm = d[p + 4:q].decode("utf-8", "replace")
        ty = d[q]
        gid = u32(d, q + 1)
        en = bool(d[q + 5])
        mc = u32(d, q + 7)
        if q + 11 + 2 * mc + 6 > e:
            continue
        mems = list(struct.unpack_from("<%dH" % mc, d, q + 11))
        attr = u32(d, q + 11 + 2 * mc + 2)
        out.append({"name": nm, "type": ty, "id": gid, "enabled": en, "member_indices": mems,
                    "members": [trks[m]["name"] for m in mems if m < len(trks)], "attributes": attr})
    return out


def folder_map(d, tree, trks):
    """{member_track_name: parent_folder_name} from 0x210C (u32 folder_count, per folder: 00*5 + 2a000000 + fid(8) +
    u32 member_count + member_count * (00*5 + 2a000000 + mid(8)))."""
    b = find(tree, 0x210C)
    if not b or b["size"] < 6:
        return {}
    by_id = {}
    for t in trks:
        tid = t.get("id", "")
        if len(tid) >= 36:
            try:
                by_id[bytes.fromhex(tid[19:27] + tid[28:36])] = t["name"]
            except ValueError:
                pass
    p, e = b["pos"] + 9, probe_end(b)
    fc = u32(d, p); p += 4
    out = {}
    for _ in range(min(fc, 1024)):
        if p + 21 > e or d[p + 5:p + 9] != b"\x2a\x00\x00\x00":
            break
        fnm = by_id.get(d[p + 9:p + 17])
        mc = u32(d, p + 17); p += 21
        for _ in range(min(mc, 1024)):
            if p + 17 > e or d[p + 5:p + 9] != b"\x2a\x00\x00\x00":
                break
            knm = by_id.get(d[p + 9:p + 17])
            if fnm and knm:
                out[knm] = fnm
            p += 17
    return out


def track_playlists(d, tree, trks):
    """per-track active and alternate playlists from 0x1015 > 0x1014 (audio tracks:  reads
    each 0x261C channel's exact u32 aidx + u16 npl + npl x u32 idx_in_1015 between 0x261B and 0x200B) and 0x1058 > 0x1057 (MIDI /
    instrument tracks)."""
    out = {}
    b15 = find(tree, 0x1015)
    atks = [t for t in trks if t["kind"] == 0]
    if b15:
        entries = []
        for k in b15["kids"]:
            if k["ct"] != 0x1014:
                continue
            p, e = k["pos"] + 9, probe_end(k)
            if p + 9 > e:
                continue
            ln = u32(d, p)
            if ln > 256 or p + 9 + ln > e:
                continue
            nm = d[p + 4:p + 4 + ln].decode("utf-8", "replace")
            ch_cnt = u32(d, p + 5 + ln)
            pls = [struct.unpack_from("<H", d, p + 9 + ln + 2 * c)[0] for c in range(min(ch_cnt, 16)) if p + 11 + ln + 2 * c <= e]
            entries.append((nm, pls))
        top = find(tree, 0x2624)
        ach = [ch for ch in (top["kids"] if top else []) if ch["ct"] == 0x261C]
        for idx, t in enumerate(atks):
            if idx >= len(entries):
                break
            nm, pls = entries[idx]
            alts = None
            if idx < len(ach):
                b1b = next((x for x in ach[idx]["kids"] if x["ct"] == 0x261B), None)
                b0b = next((x for x in ach[idx]["kids"] if x["ct"] == 0x200B), None)
                if b1b and b0b and probe_end(b1b) + 8 <= b0b["pos"]:
                    mid = d[probe_end(b1b):b0b["pos"]]
                    aidx, npl = struct.unpack_from("<IH", mid, 0)
                    if 6 + 4 * npl <= len(mid) and aidx < len(entries):
                        nm, pls = entries[aidx]
                        pidxs = struct.unpack_from("<%dI" % npl, mid, 6)
                        alts = [{"name": entries[j][0], "channel_playlists": entries[j][1]}
                                for j in pidxs if j != aidx and j < len(entries)]
            if alts is None:
                base = re.sub(r"\.\d+$", "", nm)
                alts = [{"name": anm, "channel_playlists": apls} for anm, apls in entries[len(atks):]
                        if anm != nm and re.sub(r"\.\d+$", "", anm) == base]
            out[t["name"]] = {"kind": "audio", "active": nm, "channel_playlists": pls, "alternates": alts}
    mtks = [t for t in trks if t["kind"] in (1, 7)]
    rnames = route_names(d, tree)
    for i, t in enumerate(mtks):
        act_nm = rnames[i] if i < len(rnames) else t["name"]
        base = re.sub(r"\.\d+$", "", act_nm)
        alts = [rnames[j] for j in range(len(mtks), len(rnames))
                if rnames[j] != act_nm and re.sub(r"\.\d+$", "", rnames[j]) == base]
        out[t["name"]] = {"kind": "midi", "active": act_nm, "active_index": i, "alternates": alts}
    return out


def decode(path):
    """Full decode of one session -> dict."""
    d, tree = probe.load(path)
    warn = []
    out = {"file": os.path.basename(path), "tracks": tracks(d, tree, warn), "markers": markers(d, tree, warn),
           "tempo": tempo(d, tree, warn), "tempo_copies": len(tempo_blocks(tree)), "meter": meter(d, tree, warn),
           "regions": regions(d, tree, warn), "placements": placements(d, tree), "strips": strips(d, tree), "umids": umids(d, tree)}
    out["version"] = session_version(d, tree)
    out["format"] = session_format(d, tree)
    out["timeline"] = timeline(d, tree)
    out["session_settings"] = session_settings(d, tree)
    fmap = folder_map(d, tree, out["tracks"])
    for t in out["tracks"]:
        t["folder"] = fmap.get(t["name"])
    top = find(tree, 0x2624)
    carry = [t for t in out["tracks"] if t["kind"] in (0, 2, 5, 7)]          # audio-carrying tracks have a strip (track order)
    if top and len(top["kids"]) == len(out["tracks"]) and all(st["track"] is not None for st in out["strips"]):
        for st in out["strips"]:                                               # channel block i = track i
            t = out["tracks"][st["track"]]
            t["output"], t["stem_index"] = st["output"], st["stem_index"]
            t["active"] = st["active"]                                          # track inactive = strip output +3
            if st.get("record_enable") is not None:
                t["record_enable"] = st["record_enable"]
        ptab = out["plugins"] = plugin_table(d, tree)
        sfiles = out["settings_files"] = settings_files(d, tree)
        for t, ch in zip(out["tracks"], top["kids"]):                          # mode and inserts per track
            if ch["ct"] == 0x261E:                                              # /routing folder = aux kind 2 + aux channel
                kc = [x["ct"] for x in _subtree(ch)]                            # block; it holds more 0x2038 than 0x203B (aux: 2 / 6) or is referenced by 0x210C
                if kc.count(0x2038) > kc.count(0x203B) or t["name"] in fmap.values():
                    t["type"] = "RoutingFolder"
            t["automation_mode"] = automation_mode(d, ch)
            t["user_delay"] = user_delay(d, ch)
            t["comment"], t["height_code"] = track_comment(d, ch)
            t["solo"] = solo(d, ch)
            t["hidden"] = t.get("number") == 0
            el_m = elastic_mode(d, ch)
            if el_m is not None:
                t["elastic_mode"] = el_m
                el_p = elastic_params(d, ch)
                if el_p:
                    t["elastic_params"] = el_p
            tb_m = track_timebase(d, ch)
            if tb_m is not None:
                t["timebase"] = tb_m
            if ch["ct"] in (0x2620, 0x2621) and _ver_tuple(out.get("version")) >= (2026, 11):
                t["mpe"] = mpe_mode(d, ch)                                      # only 2026.11+ layout
            ins = inserts(d, ch)
            if ins:
                for e_ in ins:                                                   # identity from the plug-in table
                    p_ = ptab[e_["table_index"]] if e_.get("table_index") is not None and e_["table_index"] < len(ptab) else None
                    e_["plugin"] = p_["name"] if p_ else None
                    e_["vendor_id"] = p_["vendor_id"] if p_ else ""
                    e_["stock"] = bool(p_ and p_["vendor_id"].startswith(("com.avid.", "com.digidesign.")))
                    sf_ = sfiles[e_["settings_index"]] if e_.get("settings_index") is not None and e_["settings_index"] < len(sfiles) else None
                    e_["settings_file"] = sf_["file"] if sf_ else None
                    e_["preset"] = sf_["file"][:-4] if sf_ and not sf_["factory_default"] else None
                t["inserts"] = ins
            if ch["ct"] == 0x261E:                                              # aux / routing folder input
                t["input_path"] = aux_input_path(d, ch)
            in_nm, in_ty = track_input(d, ch)                                   # input name & type (2 = bus)
            if in_nm is not None or in_ty is not None:
                t["input"], t["input_type"] = in_nm, in_ty
    elif top:
        warn.append("%d channel blocks for %d tracks: outputs not assigned" % (len(top["kids"]), len(out["tracks"])))
    elif len(carry) == len(out["strips"]):
        for t, st in zip(carry, out["strips"]):
            t["output"], t["stem_index"] = st["output"], st["stem_index"]
    elif out["strips"]:
        warn.append("%d strips for %d audio-carrying tracks: outputs not assigned" % (len(out["strips"]), len(carry)))
    out["write_enables"] = write_enables(d, tree)
    out["playlists"] = playlists(d, tree)
    out["clip_gains"] = clip_gains(d, tree)
    out["clip_gain_lanes"] = clip_gain_lanes(d, tree)
    links = region_gain_links(d, tree)                                          # clip-gain link per audio region
    pos = [b["pos"] for b in _region_blocks(tree)]
    for r, p in zip(out["regions"], pos):
        if p in links:
            r["clip_gain_index"] = links[p]
            r["clip_gain"] = out["clip_gains"][links[p]] if links[p] is not None and links[p] < len(out["clip_gains"]) else None
    out["audio_placements"] = audio_placements(d, tree)
    out["fades"] = fades(d, tree)
    out["audio_playlists"] = audio_playlists(d, tree)
    out["tempo_second"] = tempo(d, tree, [], 1)
    out["meter_second"] = meter(d, tree, [], 1)
    # Active copy used on load is the SECOND one; 'tempo' / 'meter' retain the first stored copy.
    out["tempo_used"] = out["tempo_second"] or out["tempo"]
    out["meter_used"] = out["meter_second"] or out["meter"]
    if out["tempo_second"] and out["tempo_second"] != out["tempo"]:
        warn.append("the two tempo copies differ")
    if out["meter_second"] and out["meter_second"] != out["meter"]:
        warn.append("the two meter copies differ")
    for r, li in zip(out["regions"], region_lists(d, tree)):                    # MIDI library regions precede audio regions in "regions"
        r["list"] = li
    aud = [r for r in out["regions"] if r.get("list") is None]
    out["audio_channels"] = audio_placements(d, tree, channels=True)
    out["clip_groups"] = audio_placements(d, tree, channels=True, groups=True)
    cgrs = out["clip_group_regions"] = clip_group_regions(d, tree)
    for lst_ in list(out["audio_placements"].values()) + [c for v in list(out["audio_channels"].values()) + list(out["clip_groups"].values()) for c in v]:
        for x in lst_:
            if x["kind"] == "clip" and x["index"] < len(aud):
                r_aud = aud[x["index"]]
                x["clip_name"], x["clip_length"] = r_aud["name"], r_aud["length"]
                if "sync_offset" in r_aud:
                    x["sync_offset"] = r_aud["sync_offset"]
                    if "samples" in x:
                        x["clip_start_samples"] = x["samples"] - r_aud["sync_offset"]
                    elif "ticks" in x and (out.get("format") or {}).get("sample_rate") and out.get("tempo_used"):
                        try:
                            sec = ticks_to_seconds(x["ticks"], out["tempo_used"])
                            x["clip_start_samples"] = round(sec * out["format"]["sample_rate"]) - r_aud["sync_offset"]
                        except ValueError:
                            pass
            elif x["kind"] == "group" and x["index"] < len(cgrs):
                g_ = cgrs[x["index"]]
                x["clip_name"], x["clip_length"] = g_["name"], g_["length"]
                if "group_id" in g_:
                    x["group_id"] = g_["group_id"]
                if "member_playlist_index" in g_:
                    x["member_playlist_index"] = g_["member_playlist_index"]
    cols = track_colours(d, tree)
    for t in out["tracks"]:
        t["colour"] = cols.get(t["name"])
    out["midi_lists"] = midi_lists(d, tree, warn)
    out["groups"] = groups(d, tree)
    out["group_details"] = group_details(d, tree, out["tracks"])
    out["track_playlists"] = track_playlists(d, tree, out["tracks"])
    out["key_signatures"] = key_signatures(d, tree)
    out["warnings"] = warn
    return out


def validate(runs_dir):
    """Offline V6 over earlier runs: every run session runs/<run>/sessions/<TEST>/<save>.ptx against the track list that
    Pro Tools reported for it (runs/<run>/results/observed/<save>.json): count, names, type, format, id. Returns rows."""
    rows = []
    for obs in sorted(glob.glob(os.path.join(runs_dir, "*", "results", "observed", "*.json"))):
        save = os.path.basename(obs)[:-5]
        run = os.path.dirname(os.path.dirname(os.path.dirname(obs)))
        cand = glob.glob(os.path.join(run, "sessions", "*", save + ".ptx"))
        if not cand or save.endswith("_media"):
            continue
        try:
            live = json.load(open(obs)).get("tracks", [])
            got = decode(cand[0])
        except (SystemExit, ValueError, OSError) as e:
            rows.append((os.path.basename(run), save, "ERROR", str(e)[:80]))
            continue
        dt = {t["name"]: t for t in got["tracks"]}
        bad = []
        if len(dt) != len(live):
            bad.append("count %d vs %d" % (len(got["tracks"]), len(live)))
        for t in live:
            g = dt.get(t["name"])
            if g is None:
                bad.append("missing %s" % t["name"])
                continue
            for k in ("type", "format", "id"):
                if k in g and t.get(k) is not None and g[k] != t[k]:
                    bad.append("%s.%s %s vs %s" % (t["name"], k, g[k], t[k]))
        rows.append((os.path.basename(run), save, "ok" if not bad else "DIFF", "; ".join(bad)[:200] or ("; ".join(got["warnings"])[:120])))
    return rows


def main(argv):
    """Command line entry point; see the usage examples at the top."""
    args = [a for a in argv[1:]]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if args else 2
    if args[0] == "--validate":
        runs = args[1] if len(args) > 1 else os.path.join(os.path.dirname(HERE), "queue", "runs")
        rows = validate(runs)
        for r in rows:
            if r[2] != "ok":
                print("%-18s %-44s %-5s %s" % r)
        n_ok = sum(1 for r in rows if r[2] == "ok")
        print("%d run sessions: %d ok, %d with differences" % (len(rows), n_ok, len(rows) - n_ok))
        return 0 if n_ok == len(rows) else 1
    opt = {}
    for k in ("--only", "--ticks", "--rate", "--tc-to-samples", "--samples-to-tc", "--tc-rate"):
        if k in args:
            i = args.index(k)
            if i + 1 >= len(args):
                probe.fail("%s needs a value" % k, "see --help")
            opt[k] = args[i + 1]
            del args[i:i + 2]
    if "--tc-to-samples" in opt or "--samples-to-tc" in opt:
        rate = int(opt.get("--rate", 0) or (decode(args[0])["format"]["sample_rate"] if args else 48000))
        tc_code = int(opt.get("--tc-rate", 0) or ((decode(args[0]).get("timeline") or {}).get("timecode_rate_code") if args else 2))
        if "--tc-to-samples" in opt:
            s = timecode_to_samples(opt["--tc-to-samples"], tc_code, rate)
            res = {"tc": opt["--tc-to-samples"], "tc_rate_code": tc_code, "tc_rate": TC_RATES.get(tc_code), "sample_rate": rate, "samples": s}
        else:
            s = int(opt["--samples-to-tc"])
            tc = samples_to_timecode(s, tc_code, rate)
            res = {"samples": s, "tc_rate_code": tc_code, "tc_rate": TC_RATES.get(tc_code), "sample_rate": rate, "tc": tc}
        print(json.dumps(res, indent=1, default=str))
        return 0
    res = decode(args[0])
    if "--ticks" in opt:
        rate = int(opt.get("--rate", 48000))
        res = {"rate": rate, "tempo": res["tempo_used"], "conversions": [{"ticks": int(t), "samples": round(ticks_to_seconds(int(t), res["tempo_used"]) * rate, 3)}
                                                                      for t in opt["--ticks"].split(",") if t.strip()]}
    elif "--only" in opt:
        res = {k: res.get(k) for k in opt["--only"].split(",")}
    print(json.dumps(res, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
