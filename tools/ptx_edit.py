#!/usr/bin/env python3
# Version: 0.7.0 (beta) | Date: 2026-11-23
"""ptx_edit -- Clean-room `.ptx` builder and editor.

Builds sessions from documented binary fields or modifies copies of saved sessions.
Never alters its input and never overwrites a file. Needs ptx_probe.py in the same folder.

Commands (usage: python3 tools/ptx_edit.py <command> <in.ptx> <out.ptx> [arguments])
  roundtrip <file...>                  check: descramble + rebuild from the block tree give the original bytes (no output file)
  copy                                 byte-identical rebuilt copy
  rename   OLD NEW [...]               replace texts of the SAME length (no size or offset changes)
  renamex  OLD NEW [...]               replace length-prefixed texts of ANY length (1..60 ASCII); sizes and stored offsets follow
  patch    CT OFF OLDHEX NEWHEX        same-length byte patch inside the data of block CT (hex); CT#n or CT:n = n-th block
  addmarker NAME QUARTERS              clone of the last marker (0x2077 in 0x2030) with a new name and position
  addnote  START KEY VELOCITY          one note appended to the first note list of the MIDI block 0x2000
  removetrack                          remove the last track
  newsession [name=..] [bpm=..] [rate=..]   session from a template .ptx with own name, tempo, sample rate
  setcomment TRACK TEXT                track comment ("" removes it)
  setnotes TRACK SPEC [name=..]        clip with notes/CC/PB/PC/CP/PP/SysEx: "q:key:len:vel;..." | "range:LO:HI[:len[:vel]]" | "chords:..." | @file
  addclip TRACK FILE.wav [at=samples] [name=..] [folder=..]   audio file + region + clip on an audio track (WAV not copied; supports 32f & .L/.R)
  newsong OUT [name=..] [bpm=..] [rate=..] <Track>=<kind>[,stereo][|<notes>] ...   clean-room session built from fields only
  buildspec OUT <spec.json>            clean-room session built in one call from a single declarative JSON parameter file
  rebuilddir                           rebuild directory block 0x0002 from the block tree; dircheck FILE... compares
  aucheck FILE...                      verify audio channel blocks match clean-room builder
  chcheck FILE...                      verify MIDI channel blocks match clean-room builder
  emptytrack TRACK                     clear clip on a MIDI / instrument track
  setfolder TRACK FOLDER [force=1]     put TRACK inside a basic / routing folder (0x210C)
  addbus NAME [stereo=1]               internal bus path from fields (mono default)
  addsend TRACK BUS [level=0] [pan=0] [pre=0] [mute=0] [active=1] [slot=a]   send from TRACK to BUS built from fields
  setoutput TRACK BUS                  main output of TRACK to BUS in 0x2603 (built from fields)
  setgroups @groups.json               track groups 0x202B > 0x202A built from fields (newsong option groups=@groups.json)
  addplugin TRACK SLOT PLUGIN [...]    stock plug-in insert (17 stock plug-ins: 0x1018 > 0x1017 + 0x2627 > 0x2616/0x2617) built from fields
  setcolor TRACK COLOUR [...]          track colour index in 0x2519 > 0x251A (-2 or none = default, 25..93 = palette)
  addplaylist TRACK NAME [...]         empty alternate playlist (0x1054 > 0x1052 + 0x1015 > 0x1014 + 0x261C index list)
  settimeline [tc_rate=..] [tc_start=..] [pull=..] [record_mode=..]   timeline / timecode / pull / record mode in 0x204D/0x204B/0x2023/0x2058
  setkeysig   TICKS:KEY [...]          key signature ruler 0x271B > 0x2433 > 0x2432 (e.g. 0:C 960000:Am 1920000:F#m)
  setcliploop TRACK POS [mode=1|2] [bars=B] [beats=b] [ticks=t] [count=N] [iter_ticks=L]   clip loop 0x242B on 0x104F
  addclipgroup TRACK NAME START END    group clips in [START, END] on TRACK (0x262C > 0x262B > 0x2628 + 0x2428 > 0x1054)
  setmarkers @markers.json             markers from fields ({"name", "start", "end", "unit": "ticks"|"samples", "kind", "comment"})
  newbase [rate=48000] [bits=24] [io=1]  empty clean-room session built from fields only
  dropblock CT[,CT..]                  remove top-level block(s) and rebuild directory
  addtrack4 [kind=midi|instrument|audio|aux|master|folder|rfolder] [stereo=1] [name=..]   clean-room track built from fields
  addtrack3 [kind=..] [stereo=1] [name=..]   alias of addtrack4
  setlane  TRACK LANE POS:VAL,... [...]       points of a mixer lane (volume | mute | pan | pan2 | send<N>.volume|mute|pan)
  setflag  TRACK FLAG VALUE [...]             solo | mode (0-4) | active | mute_static | bypass.<slot> | insert_active.<slot> | hidden
  setparam TRACK SLOT NAME VALUE [...]        plug-in parameter (d_ f64 / l_ i32) of a Complete Controls State chunk
  setclipgain K DB [...]                      clip-gain entry K of list 0x2637 to DB
  setdelay TRACK SAMPLES [...]                track user delay (i32 after the send-slot ids)
  diffblocks A.ptx B.ptx                      list top-level blocks that differ (CT:n per line)
  setclipmute TRACK bar:N|tN 0|1 [...]        clip mute (byte 0 of playlist entry 0x104F)
  addautolane TRACK SLOT NAME ID INDEX START [tb=0|1]   enable automation of a plug-in parameter (0x2614 > 0x260F > 0x260B)
  setpluglane TRACK SLOT ID POS:V,...         points of an automated plug-in parameter (normalised values)
  setinput TRACK PATH|-                       input of a track (aux: bus) = path number + input record of 0x261B
  setsendpath TRACK N PATH                    destination of an existing send (output block 0x260E of the send strip)
  renamebus OLD NEW                           rename a bus like the I/O setup (default name in 0x1021 kept)
  splitclip TRACK POS AT                      split the clip starting at POS at timeline position AT (two new regions)
  addfade TRACK POS LEN KIND SLOPE [center=1|pre=N]   fade / crossfade on clip starting at POS (0x2630 + playlist entry)
  setsyncpoint TRACK POS SAMPLES              set (or 0 = clear) sync point on clip starting at POS
  placeclip TRACK FROM TO                     place clip starting at FROM again at TO (same region and fade-in)
  setclipgainat TRACK POS DB                  clip gain of one clip with copy-on-write rule (new entry / new region)
  moveclip TRACK FROM TO                      move clip (+ its fades) from FROM to TO and sort 0x1050 chronologically
  deleteclip TRACK POS                        remove clip (+ its fades) from TRACK playlist(s) (keeps clip list)
  trimclip TRACK POS START END                in-place trim of fade-free clip at POS to [START, END)
  delmarker ID|NAME                           remove memory location 0x2077 (reset 0x251C[0][6]=0 if none remain)
  anonnames                                   fill empty nlen==0 playlist 0x1052 names from 0x1014 / track metadata
  dissolvegroup TRACK NAME|POS                dissolve clip group back into rebased member placements on TRACK
  setvisible TRACK 0|1                        show/hide track (updates 0x2519 display numbers + 0x2015 view flags)
  relinkcheck A.ptx [WAV_DIR...]              verify UMIDs, region bounds, and optional BWF bext/fmt/data on disk

Examples
  python3 tools/ptx_edit.py roundtrip test/CR_max/CR_max.ptx
  python3 tools/ptx_edit.py renamex session.ptx out.ptx "MIDI 1" Bass Test_New Drums_Clip
  python3 tools/ptx_edit.py addtrack4 session.ptx a.ptx ; python3 tools/ptx_edit.py addtrack4 a.ptx b.ptx name=Bass
  python3 tools/ptx_edit.py removetrack b.ptx back_to_a.ptx
  python3 tools/ptx_edit.py newsession template.ptx Song.ptx name=Song bpm=96 rate=48000
  python3 tools/ptx_edit.py newbase Song.ptx rate=48000 bits=24
  python3 tools/ptx_edit.py setcomment in.ptx out.ptx Aux_s "comment text"
  python3 tools/ptx_edit.py setnotes in.ptx out.ptx Bass "chords:C,Am,F,G7:4:96"
Errors: 'ERROR: <what>' + 'HINT: <what to do>', exit code 2 (text not found, unknown layout, output exists, ...). Every
command checks the result before writing (complete parse, structural offsets point to blocks).
"""
import importlib.util
import os
import re
import struct
import sys

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
import glob as _glob
_probe_path = os.path.join(HERE, "ptx_probe.py")
if not os.path.isfile(_probe_path):
    _probes = sorted(_glob.glob(os.path.join(HERE, "ptx_probe_v*.py")))
    if not _probes:
        sys.stderr.write("ERROR: ptx_probe.py not found next to this script\nHINT:  keep both files in <kit>/tools\n")
        sys.exit(2)
    _probe_path = _probes[-1]
_spec = importlib.util.spec_from_file_location("ptx_probe", _probe_path)
probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe)
HEADER = probe.HEADER


def _kit():
    """Kit configuration instance, or None when no kit config exists."""
    import glob
    mod = os.path.join(HERE, "ptx_kitconfig.py")
    if not os.path.isfile(mod):
        c = sorted(glob.glob(os.path.join(HERE, "ptx_kitconfig_v*.py")))
        if not c:
            return None
        mod = c[-1]
    sp = importlib.util.spec_from_file_location("ptx_kitconfig", mod)
    kc = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(kc)
    return kc.Kit.find(os.environ.get("PTX_CONFIG"))


def _cfg_val(section, key, default):
    """Read [section] key from kit TOML config, falling back to DEFAULT."""
    kit = _kit()
    return kit.get(section, key, default) if kit else default


def _originals():
    """Protected sessions path from kit config if configured, or None."""
    kit = _kit()
    return kit.originals() if kit else None


def rebuild(d, nodes, start, end):
    """Serialise the sibling blocks `nodes` that lie in d[start:end]; sizes are recomputed from the children, gaps are copied unchanged."""
    out, pos = bytearray(), start
    for n in nodes:
        out += d[pos:n["pos"]]                                   # bytes between blocks (none in the test files)
        payload = bytearray()
        inner_start, inner_end = n["pos"] + 9, n["pos"] + 7 + n["size"]
        payload += rebuild(d, n["kids"], inner_start, inner_end)  # data of this block with the children rebuilt
        # block = 0x5A | type u16 | size u32 | content type u16 | data ; size counts the content type + data
        out += b"\x5a" + struct.pack("<H", n["bt"]) + struct.pack("<I", 2 + len(payload)) + struct.pack("<H", n["ct"]) + payload
        pos = n["pos"] + 7 + n["size"]
    out += d[pos:end]
    return bytes(out)


def descramble_file(path):
    """(raw bytes, descrambled bytes, block tree) of a file."""
    try:
        raw = open(path, "rb").read()
    except OSError as e:
        probe.fail("cannot read %s (%s)" % (path, e), "check the path; cloud files must be downloaded locally")
    d = probe.unscramble(raw)
    return raw, d, probe.parse(d, HEADER, len(d))


def scramble(d):
    """Scrambling is the same XOR as descrambling (the key depends only on position and header)."""
    return probe.unscramble(d)


def check_roundtrip(path):
    """Two checks; returns True when both give the original bytes."""
    raw, d, tree = descramble_file(path)
    ok_xor = scramble(d) == raw
    rebuilt = d[:HEADER] + rebuild(d, tree, HEADER, len(d))
    ok_tree = rebuilt == d
    print("%-60s xor round trip %s, block-tree rebuild %s (%d blocks, %d bytes)" % (
        os.path.basename(path), "OK" if ok_xor else "DIFFERENT", "OK" if ok_tree else "DIFFERENT", sum(1 for _ in probe.walk(tree)), len(raw)))
    return ok_xor and ok_tree


def write_new(path, data):
    """Write a new file; never overwrite."""
    if os.path.exists(path):
        probe.fail("%s exists" % path, "choose a new output name; originals and earlier outputs are never overwritten")
    o = _originals()                                  # original sessions are never written
    if o:
        p, r = os.path.realpath(os.path.abspath(path)), os.path.realpath(o)
        if p == r or p.startswith(r + os.sep):
            probe.fail("%s is inside the original sessions (%s)" % (path, o), "write the output into data/sessions/automation/ instead")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    open(path, "wb").write(data)


def cmd_roundtrip(*paths):
    """Stage 1 check for any number of files; exit code 1 if one differs."""
    if not paths:
        probe.fail("no file given", "usage: roundtrip <file.ptx> [more files]")
    sys.exit(0 if all([check_roundtrip(p) for p in paths]) else 1)


def cmd_copy(src, dst):
    """Stage 1 file: the rebuilt copy (must be byte-identical to the source)."""
    raw, d, tree = descramble_file(src)
    out = scramble(d[:HEADER] + rebuild(d, tree, HEADER, len(d)))
    if out != raw:
        probe.fail("rebuilt copy differs from the source", "run roundtrip on the source and report the output")
    write_new(dst, out)
    print("wrote %s (%d bytes, identical to the source)" % (dst, len(out)))


def cmd_rename(src, dst, *pairs):
    """Stage 2: replace text by text of the same length (pairs: OLD NEW OLD NEW ...)."""
    if not pairs or len(pairs) % 2:
        probe.fail("need OLD NEW pairs", "usage: rename <in> <out> OLD NEW [OLD NEW ...]")
    raw, d, tree = descramble_file(src)
    census_before = probe.census(tree)
    d = bytearray(d)
    for old, new in zip(pairs[::2], pairs[1::2]):
        o, n = old.encode("ascii"), new.encode("ascii")
        if len(o) != len(n):
            probe.fail("'%s' and '%s' differ in length (%d / %d)" % (old, new, len(o), len(n)), "same-length texts only in v1.0 (a size change needs the size and index fields recomputed)")
        count = bytes(d).count(o)
        if count == 0:
            probe.fail("text '%s' not found" % old, "check spelling; run 'ptx_probe strings' on the file")
        d = bytearray(bytes(d).replace(o, n))
        print("replaced %d x '%s' -> '%s'" % (count, old, new))
    d = bytes(d)
    tree2 = probe.parse(d, HEADER, len(d))
    covered = sum(t["size"] + 7 for t in tree2)
    if covered != len(d) - HEADER or probe.census(tree2) != census_before:
        probe.fail("edited file does not parse like the original", "the replaced text was not only text; nothing written")
    write_new(dst, scramble(d))
    print("wrote %s (%d bytes, 100 %% of the blocks parsed, same block types)" % (dst, len(d)))


def cmd_renamex(src, dst, *pairs):
    """Rename length-prefixed texts to texts of any length (pairs: OLD NEW ...). Last occurrence first so earlier positions stay valid."""
    if not pairs or len(pairs) % 2:
        probe.fail("need OLD NEW pairs", "usage: renamex <in> <out> OLD NEW [OLD NEW ...]")
    raw, d, tree = descramble_file(src)
    out = bytearray(d)
    for old, new in zip(pairs[::2], pairs[1::2]):
        o, n = old.encode("ascii"), new.encode("ascii")
        if not (1 <= len(n) <= 60):
            probe.fail("new text '%s' has %d characters" % (new, len(n)), "use 1..60 ASCII characters")
        hits = [m.start() for m in re.finditer(re.escape(o), bytes(out)) if m.start() >= 4 and struct.unpack_from("<I", out, m.start() - 4)[0] == len(o)]
        total = bytes(out).count(o)
        if not hits:
            probe.fail("text '%s' not found with a length prefix (%d plain hits)" % (old, total), "check spelling; run ptx_probe strings; derived names have another length prefix")
        delta = len(n) - len(o)
        if delta and not os.environ.get("PTX_RENAMEX_LEGACY"):              # one splice over all hits
            tr = probe.parse(bytes(out), HEADER, len(out))
            out = bytearray(_splice2(bytes(out), tr, [{"p": i - 4, "ol": 4 + len(o), "nb": struct.pack("<I", len(n)) + n} for i in hits]))
            print("replaced %d x '%s' -> '%s' (%d plain hits, %d without prefix kept)" % (len(hits), old, new, total, total - len(hits)))
            continue
        for i in sorted(hits, reverse=True):
            tr = probe.parse(bytes(out), HEADER, len(out))
            chain = _path_to(tr, i)
            out[i - 4:i + len(o)] = struct.pack("<I", len(n)) + n
            for blk in chain:
                struct.pack_into("<I", out, blk["pos"] + 3, blk["size"] + delta)
            if delta:
                out = bytearray(_shift_offsets(out, tr, i, delta))
        print("replaced %d x '%s' -> '%s' (%d plain hits, %d without prefix kept)" % (len(hits), old, new, total, total - len(hits)))
    out = bytes(out)
    tree2 = probe.parse(out, HEADER, len(out))
    if sum(t_["size"] + 7 for t_ in tree2) != len(out) - HEADER:
        probe.fail("edited file does not parse completely", "nothing written")
    _check_sites(out, tree2)
    write_new(dst, scramble(out))
    print("wrote %s (%d bytes)" % (dst, len(out)))


def _path_to(nodes, pos, acc=()):
    """Chain of blocks (outermost first) whose range contains the byte position `pos`."""
    for n in nodes:
        if n["pos"] <= pos < n["pos"] + 7 + n["size"]:
            return _path_to(n["kids"], pos, acc + (n,))
    return acc




def _shift_offsets(out, tree, edit_pos, delta):
    """Absolute block offsets stored in the file must follow blocks that moved by `delta` (found by test GEN_S3: Pro Tools answered
    'magic ID does not match' when they were not updated). Three places: the u32 at file offset 27 (position of the last block 0x0002),
    the directory block 0x0002 (u32 after the byte patterns 01 04 00 01 00 and 01 08 00 02 00, the latter has two offsets) and the u32 10 bytes before the file end.
    Only values equal to the position of a block that lies behind the edit are changed. Returns bytes; fails if the result is not consistent."""
    old_pos = {n["pos"] for n in probe.walk(tree) if n["pos"] > edit_pos}
    old_pos_all = {n["pos"] for n in probe.walk(tree)}
    sites = [27, len(out) - 10]
    last = tree[-1]
    if last["ct"] != 0x0002:
        probe.fail("last top-level block is 0x%04x, expected the directory 0x0002" % last["ct"], "unknown layout; nothing written")
    d0, d1 = last["pos"] + delta + 9, last["pos"] + delta + 7 + last["size"]       # directory block in the new file
    # general record header  01 <4k> 00 <k> 00  followed by k offsets (k=1,2 known; k=3 found by the T17 -> T18 oracle: 3 offsets of the 0x251a track-name blocks)
    for pat, n_off in ((b"\x01" + struct.pack("<HH", 4 * k, k), k) for k in range(1, 513)):     # k up to 512 (was 8)
        i = bytes(out).find(pat, d0, d1)
        while i != -1:
            rec = [i + 5 + 4 * k for k in range(n_off)]
            if n_off <= 8 or all(struct.unpack_from("<I", out, x_)[0] in old_pos_all for x_ in rec):   # k > 8 only as a whole valid record
                sites += rec
            i = bytes(out).find(pat, i + 1, d1)
    # positions of parent blocks stored between the directory records: after `ff ff ff ff` come chains of  5 bytes + u16 type + u32 position;
    # a free scan for any u32 equal to a block position gave false hits (e.g. 65792 inside flag bytes), so only this structure is used
    all_old = {n["pos"] for n in probe.walk(tree)}
    extra, j0 = [], d0
    b_ = bytes(out)
    while True:
        j0 = b_.find(b"\xff\xff\xff\xff", j0, d1)
        if j0 < 0:
            break
        if b_[j0 - 1:j0] == b"\xff":
            j0 += 1
            continue
        j = j0 + 4
        while j + 11 <= d1 and struct.unpack_from("<I", b_, j + 7)[0] in all_old:
            extra.append(j + 7)
            j += 11
        j0 += 4
    extra = [i for i in extra if i not in sites]
    print("stored parent offsets inside the directory gaps: %d" % len(extra))
    sites += extra
    sites = sorted(set(sites))   # the trailer site (len-10) is ALSO found by the pattern 01 04 00 01 00 -> was shifted twice when v+delta happened to be another block position (name lengths 14/19/36)
    changed = 0
    for s_ in sites:
        v = struct.unpack_from("<I", out, s_)[0]
        if v in old_pos:
            struct.pack_into("<I", out, s_, v + delta)
            changed += 1
    if changed < 20:
        probe.fail("only %d offsets recognised; expected dozens" % changed, "unknown layout; nothing written")
    print("shifted %d stored block offsets by %+d" % (changed, delta))
    return bytes(out)


def cmd_addmarker(src, dst, name, quarters, *opts):
    """Stage 3: append a marker (clone of the last one). name: ASCII text, quarters: position in quarter notes from 1|1 (integer).
    a marker cloned from a SAMPLE-referenced marker (flag byte 6 of the position field = 0x00; 0x40 = ticks) needs
    samples=<N>; Pro Tools dropped markers whose position was written in the tick form there (T64 d01 F06, T65 j67)."""
    import os as _os
    raw, d, tree = descramble_file(src)
    census_before = probe.census(tree)
    lists = [n for n in probe.walk(tree) if n["ct"] == 0x2030 and n["kids"] and all(k["ct"] == 0x2077 for k in n["kids"])]
    if len(lists) != 1:
        probe.fail("marker list (ct 0x2030 with 0x2077 children) found %d times" % len(lists), "this command needs a session with markers, exactly one list")
    lst = lists[0]
    start, end = lst["pos"] + 9, lst["pos"] + 7 + lst["size"]
    count = struct.unpack_from("<I", d, start)[0]
    if count != len(lst["kids"]):
        probe.fail("count field %d differs from the %d marker blocks" % (count, len(lst["kids"])), "unknown layout; nothing written")
    last = lst["kids"][-1]
    x = bytearray(d[last["pos"] + 9:last["pos"] + 7 + last["size"]])            # data of the last marker block
    old_len = struct.unpack_from("<I", x, 6)[0]
    nb = name.encode("ascii")
    pos_old = 10 + old_len
    o_ = dict(a.split("=", 1) for a in opts if "=" in a)
    if x[pos_old + 6] & 0x40:                                                        # tick-referenced template
        position = 10 ** 12 + int(quarters) * 960000                              # unit 1/1000 tick, origin 10^12 at 1|1
    else:
        if "samples" not in o_:
            probe.fail("the template marker is sample based", "give samples=<position in samples>, e.g. addmarker in out M1 8 samples=192000")
        position = int(o_["samples"])
    pos5 = position.to_bytes(5, "little")
    if x[pos_old + 8:pos_old + 13] != x[pos_old:pos_old + 5]:
        probe.fail("the two position fields of the marker differ", "unknown layout; nothing written")
    new = bytearray(x[:6]) + struct.pack("<I", len(nb)) + nb + pos5 + x[pos_old + 5:pos_old + 8] + pos5 + x[pos_old + 13:]
    struct.pack_into("<H", new, 0, count + 1)                                       # marker number
    k = bytes(new).find(b"\x5a\x01\x00\x09")                                       # first 0x4826 child; the 16-byte id sits 12 bytes of ff before it
    if k < 30 or bytes(new[k - 12:k]) != b"\xff" * 12 or bytes(new[k - 30:k - 28]) != b"\xff\xff":
        probe.fail("id field of the marker not where expected", "unknown layout; nothing written")
    new[k - 28:k - 12] = __rnd(16)                                              # new random id so that no two markers share one
    block = b"\x5a" + struct.pack("<H", last["bt"]) + struct.pack("<I", 2 + len(new)) + struct.pack("<H", 0x2077) + bytes(new)
    old_payload = d[start:end]
    tail_pos = last["pos"] + 7 + last["size"]
    new_payload = struct.pack("<I", count + 1) + d[start + 4:tail_pos] + block + d[tail_pos:end]
    delta = len(new_payload) - len(old_payload)
    out = bytearray(d[:start] + new_payload + d[end:])
    for anc in _path_to(tree, lst["pos"]):                                          # grow the list block and all parents
        struct.pack_into("<I", out, anc["pos"] + 3, anc["size"] + delta)
    out = _shift_offsets(bytearray(out), tree, tail_pos, delta)
    tree2 = probe.parse(out, HEADER, len(out))
    covered = sum(t["size"] + 7 for t in tree2)
    if covered != len(out) - HEADER:
        probe.fail("edited file does not parse completely", "nothing written")
    write_new(dst, scramble(out))
    print("wrote %s (%d bytes, +%d); marker %d '%s' at %d quarter notes; 100 %% of the blocks parsed" % (dst, len(out), delta, count + 1, name, int(quarters)))


def cmd_patch(src, dst, ct_hex, *triples):
    """Stage 4: OFFSET OLDHEX NEWHEX ... inside the first top-level block of content type ct_hex (hex, e.g. 2000), or with
    ct_hex = 'CT#n' (or 'CT:n', usable in batch specs where '#' starts a comment) inside the n-th block of that type at any depth (v1.33). Same length only; OFFSET counts from the data start."""
    if not triples or len(triples) % 3:
        probe.fail("need OFFSET OLDHEX NEWHEX triples", "usage: patch <in> <out> <ct hex> OFFSET OLDHEX NEWHEX [...]")
    raw, d, tree = descramble_file(src)
    census_before = probe.census(tree)
    nth = None
    if "#" in ct_hex or ":" in ct_hex:                                 # v1.33: CT#n or CT:n = n-th block of the type at any depth
        ct_hex, nth = ct_hex.replace(":", "#").split("#", 1)
        try:
            nth = int(nth)
        except ValueError:
            probe.fail("bad block number in %s#%s" % (ct_hex, nth), "use CT#n with n = 1, 2, ... (depth-first order)")
    ct = int(ct_hex, 16)
    blocks = [n for n in (probe.walk(tree) if nth else tree) if n["ct"] == ct]
    if nth and not 1 <= nth <= len(blocks):
        probe.fail("block 0x%04x #%d not found (%d blocks of that type)" % (ct, nth, len(blocks)), "run 'ptx_probe census' to count the blocks")
    if not blocks:
        probe.fail("no top-level block of type 0x%04x" % ct, "run 'ptx_probe census' to list the types")
    blk = blocks[nth - 1] if nth else blocks[0]
    base, end = blk["pos"] + 9, blk["pos"] + 7 + blk["size"]
    d = bytearray(d)
    for off, old, new in zip(triples[::3], triples[1::3], triples[2::3]):
        o, n_, at = bytes.fromhex(old), bytes.fromhex(new), base + int(off)
        if len(o) != len(n_):
            probe.fail("old and new bytes differ in length at offset %s" % off, "same-length changes only")
        if at < base or at + len(o) > end:
            probe.fail("offset %s lies outside the block (data length %d)" % (off, end - base), "check the offset")
        if bytes(d[at:at + len(o)]) != o:
            probe.fail("bytes at offset %s are %s, not %s" % (off, bytes(d[at:at + len(o)]).hex(), old), "wrong offset or wrong source file; nothing written")
        d[at:at + len(o)] = n_
        print("offset %s: %s -> %s" % (off, old, new))
    d = bytes(d)
    tree2 = probe.parse(d, HEADER, len(d))
    if sum(t["size"] + 7 for t in tree2) != len(d) - HEADER or probe.census(tree2) != census_before:
        probe.fail("edited file does not parse like the original", "nothing written")
    write_new(dst, scramble(d))
    print("wrote %s (%d bytes, 100 %% of the blocks parsed, same block types)" % (dst, len(d)))


def cmd_addnote(src, dst, start_ticks, key, velocity):
    """Stage 5a: append one note (start in ticks of the 960 PPQ file, key 0-127, velocity 1-127) to list 1 of the first 0x2000 block of a T0-like session."""
    raw, d, tree = descramble_file(src)
    blocks = [n for n in tree if n["ct"] == 0x2000]
    if not blocks:
        probe.fail("no top-level block 0x2000", "the session needs an imported MIDI clip")
    blk = blocks[0]
    base, end = blk["pos"] + 9, blk["pos"] + 7 + blk["size"]
    x = d[base:end]
    # layout checked on T0: u32 1 | 'MdChun' ver len | 'MdNLB' ver len | u32 count | count x 35-byte records | second list with its own count
    if x[4:10] != b"MdChun" or x[16:21] != b"MdNLB":
        probe.fail("MdChun / MdNLB tags not at the expected place", "only sessions with exactly one MIDI clip (like T0 / T3 / T6) are supported")
    chun_len, nlb_len, count = struct.unpack_from("<I", x, 12)[0], struct.unpack_from("<I", x, 23)[0], struct.unpack_from("<I", x, 27)[0]
    list_end = 31 + 35 * count
    if struct.unpack_from("<I", x, list_end)[0] != count or 16 + chun_len > len(x) or 21 + nlb_len > len(x):
        probe.fail("list 1 does not end where a second list with the same count begins", "unknown layout; nothing written")
    rec = bytearray(x[list_end - 35:list_end])                                    # clone of the last record
    last_start = int.from_bytes(rec[0:5], "little")
    new_start = int(start_ticks) * 1000
    if new_start <= last_start:
        probe.fail("start %s ticks is not behind the last note (%d ticks)" % (start_ticks, last_start // 1000), "list 1 is ordered by time; choose a later start")
    if not (0 <= int(key) <= 127 and 1 <= int(velocity) <= 127):
        probe.fail("key 0-127 and velocity 1-127 expected", "check the arguments")
    rec[0:5] = new_start.to_bytes(5, "little")
    rec[8] = int(key)                                                              # key at anchor-1 (anchor = byte 9)
    rec[17] = int(velocity)                                                        # velocity at anchor+8
    nx = bytearray(x[:list_end]) + rec + x[list_end:]
    struct.pack_into("<I", nx, 12, chun_len + 35)
    struct.pack_into("<I", nx, 23, nlb_len + 35)
    struct.pack_into("<I", nx, 27, count + 1)
    out = bytearray(d[:base] + nx + d[end:])
    struct.pack_into("<I", out, blk["pos"] + 3, blk["size"] + 35)                  # only the top-level block: parsed 'children' of note data are chance matches
    out = _shift_offsets(out, tree, base + list_end, 35)
    tree2 = probe.parse(out, HEADER, len(out))
    if sum(t["size"] + 7 for t in tree2) != len(out) - HEADER:
        probe.fail("edited file does not parse completely", "nothing written")
    write_new(dst, scramble(out))
    print("wrote %s (%d bytes, +35); note %d: start %s ticks, key %s, velocity %s (list 1 only)" % (dst, len(out), count + 1, start_ticks, key, velocity))


# per-track block groups: path of block types from the top level -> number of blocks one track adds (found by comparing T0 with T7)
TRACK_GROUPS = [((0x1058, 0x1057), 1), ((0x2107, 0x210b), 1), ((0x2519, 0x251a), 2), ((0x2624, 0x2620), 1), ((0x2587, 0x2551, 0x258b, 0x258a, 0x2589), 1)]


# u32 counter inside the PARENT block of each group: (offset in the data of the parent, increase per new track); found by comparing T0 with T7 (test 6a v1: 'end of stream encountered' without them)
PARENT_COUNTS = {(0x1058, 0x1057): (0, 1), (0x2107, 0x210b): (9, 1), (0x2519, 0x251a): (14, 1), (0x2624, 0x2620): (0, 1), (0x2587, 0x2551, 0x258b, 0x258a, 0x2589): (None, 1)}   # None: the counter sits right before the first child of the target type


def _paths(tree):
    """dict: tuple of block types (outermost first) -> list of blocks in file order."""
    res = {}
    def rec(ns, path):
        for n in ns:
            p = path + (n["ct"],)
            res.setdefault(p, []).append(n)
            rec(n["kids"], p)
    rec(tree, ())
    return res




NEW_NAME = b"Notes_Full.dup1"      # name of the added track (set by addtrack option name=)






def _check_sites(out, tree):
    """Final check: every stored block offset that can be found by structure (file offset 27, trailer, directory patterns) must point to a block. A value that points nowhere means an offset was shifted by mistake (seen with some track-name lengths); nothing is written then."""
    pos = {n["pos"] for n in probe.walk(tree)}
    last = tree[-1]
    sites = [27, len(out) - 10]
    # general record header  01 <4k> 00 <k> 00  followed by k offsets (k=1,2 known; k=3 found by the T17 -> T18 oracle: 3 offsets of the 0x251a track-name blocks)
    for pat, n_off in ((b"\x01" + struct.pack("<HH", 4 * k, k), k) for k in range(1, 513)):     # k up to 512 (was 8)
        i = out.find(pat, last["pos"] + 9, last["pos"] + 7 + last["size"])
        while i != -1:
            rec = [i + 5 + 4 * k for k in range(n_off)]
            if n_off <= 8 or all(struct.unpack_from("<I", out, x_)[0] in pos for x_ in rec):     # k > 8 only as a whole valid record
                sites += rec
            i = out.find(pat, i + 1, last["pos"] + 7 + last["size"])
    bad = [s_ for s_ in sites if struct.unpack_from("<I", out, s_)[0] not in pos]
    if bad:
        probe.fail("%d stored offsets point to no block (first at file offset %d): an offset was shifted by mistake" % (len(bad), bad[0]),
                   "try another track name length (+/- 1 character); nothing written")






def _head_entry(out, new8, bump_counter):
    """Append the third entry to the track list in the head of 0x2519 (T13: type 01 00, u32 name length, name, 6 zero bytes, 2a 00 00 00, 8-byte track id, number 03, 00 00 = 42 bytes)."""
    out = bytearray(out)
    tr = probe.parse(bytes(out), HEADER, len(out))
    par = _paths(tr)[(0x2519,)][0]
    name = NEW_NAME
    ent = b"\x01\x00" + struct.pack("<I", len(name)) + name + b"\x00" * 6 + b"\x2a\x00\x00\x00" + new8 + b"\x03\x00\x00"
    at = par["kids"][0]["pos"]
    if bytes(out[at - 3:at]) != b"\x02\x00\x00":
        probe.fail("head of 0x2519 does not end with the entry number 02 00 00", "unknown layout; nothing written")
    out = bytearray(out[:at]) + ent + out[at:]
    struct.pack_into("<I", out, par["pos"] + 3, par["size"] + len(ent))
    out = bytearray(_shift_offsets(out, tr, at - 1, len(ent)))
    if bump_counter:
        v = struct.unpack_from("<I", out, par["pos"] + 9 + 14)[0]
        struct.pack_into("<I", out, par["pos"] + 9 + 14, v + 1)
    return bytes(out)






def _chain(tree, cts):
    """All blocks reached by descending through the child types `cts` from the top level (list of block dicts of the last type)."""
    cur = [t_ for t_ in tree if t_["ct"] == cts[0]]
    for ct in cts[1:]:
        cur = [k for n_ in cur for k in n_["kids"] if k["ct"] == ct]
    return cur







# one-pass splice engine + removetrack (J4)
def _sites_once(d, tree):
    """All stored block positions found by structure in the ORIGINAL file (detected once, no double listing): offset 27, trailer (len-10),
    directory records 01 <4k> 00 <k> 00 + k positions (k=1..8), chains after ff ff ff ff in the directory gaps. Only values that are block positions."""
    allp = {n["pos"] for n in probe.walk(tree)}
    last = tree[-1]
    d0, d1 = last["pos"] + 9, last["pos"] + 7 + last["size"]
    s = {27, len(d) - 10}
    for k in range(1, 513):                                    # k up to 512
        pat = b"\x01" + struct.pack("<HH", 4 * k, k)
        i = d.find(pat, d0, d1)
        while i != -1:
            rec = [i + 5 + 4 * j for j in range(k)]
            if k <= 8 or all(i_ + 4 <= len(d) and struct.unpack_from("<I", d, i_)[0] in allp for i_ in rec):   # k > 8 only as a whole valid record
                s.update(rec)
            i = d.find(pat, i + 1, d1)
    j0 = d0
    while True:
        j0 = d.find(b"\xff" * 4, j0, d1)
        if j0 < 0:
            break
        if d[j0 - 1:j0] == b"\xff":
            j0 += 1
            continue
        j = j0 + 4
        while j + 11 <= d1 and struct.unpack_from("<I", d, j + 7)[0] in allp:
            s.add(j + 7)
            j += 11
        j0 += 4
    return sorted(i for i in s if i + 4 <= len(d) and struct.unpack_from("<I", d, i)[0] in allp)


def _splice(d, tree, edits):
    """Apply byte edits (pos, old_len, new_bytes) to the ORIGINAL data d in one pass. Sizes of all enclosing blocks and every stored
    block position (_sites_once) follow. Sites inside a deleted range are dropped; a surviving site that points to a deleted block is an error."""
    d = bytes(d)
    edits = sorted(edits)
    for (p1, l1, _), (p2, _, _) in zip(edits, edits[1:]):
        if p1 + l1 > p2:
            probe.fail("overlapping edits at %d / %d" % (p1, p2), "internal error of the command; nothing written")
    inside = lambda x: any(p <= x < p + ol for p, ol, nb in edits)
    f = lambda x: x + sum(len(nb) - ol for p, ol, nb in edits if p + ol <= x)
    nodes = list(probe.walk(tree))
    gone = {n["pos"] for n in nodes if inside(n["pos"])}
    out, pos = bytearray(), 0
    for p, ol, nb in edits:
        out += d[pos:p] + nb
        pos = p + ol
    out += d[pos:]
    for n in nodes:
        if n["pos"] in gone:
            continue
        a, b = n["pos"] + 7, n["pos"] + 7 + n["size"]
        dd = sum(len(nb) - ol for p, ol, nb in edits if a <= p and p + ol <= b)
        if dd:
            struct.pack_into("<I", out, f(n["pos"]) + 3, n["size"] + dd)
    stale, used = [], 0
    for s_ in _sites_once(d, tree):
        if inside(s_):
            continue
        v = struct.unpack_from("<I", d, s_)[0]
        if v in gone:
            stale.append((s_, v))
            continue
        struct.pack_into("<I", out, f(s_), f(v))
        used += 1
    if stale:
        probe.fail("%d stored positions point to removed blocks: %s" % (len(stale), stale[:8]), "unknown directory record; nothing written")
    out = bytes(out)
    tree2 = probe.parse(out, HEADER, len(out))
    if sum(t_["size"] + 7 for t_ in tree2) != len(out) - HEADER:
        probe.fail("edited file does not parse completely", "nothing written")
    _check_sites(out, tree2)
    print("splice: %d edits, %d stored positions remapped, %d bytes -> %d bytes" % (len(edits), used, len(d), len(out)))
    return out


def cmd_removetrack(src, dst, groups="all"):
    """remove the LAST track of a session made like addtrack4: inverse of addtrack.
    Groups (default all): route, x2107, track, x258a, keys, markers, click, names, lists, cnt2, renum (directory records follow their group).
    Example: python3 ptx_edit.py removetrack GEN_S6a_Y1_default.ptx back_to_T0.ptx"""
    raw, d, tree = descramble_file(src)
    d = bytes(d)
    want = ["route", "x2107", "track", "x258a", "keys", "markers", "click", "names", "lists", "cnt2", "renum"] if groups == "all" else groups.split(",")
    t = _paths(tree)
    E = []
    u32 = lambda p: struct.unpack_from("<I", d, p)[0]
    def setu32(p, new, label):
        E.append((p, 4, struct.pack("<I", new)))
    def setbyte(p, old, new, label):
        if d[p] != old:
            probe.fail("%s: byte at %d is %d, expected %d" % (label, p, d[p], old), "unknown layout; skip group or nothing written")
        E.append((p, 1, bytes([new])))
    dele = lambda n: E.append((n["pos"], 7 + n["size"], b""))
    last = tree[-1]
    if last["ct"] != 0x0002:
        probe.fail("last block is 0x%04x, expected the directory 0x0002" % last["ct"], "unknown layout; nothing written")
    D0, D1 = last["pos"] + 9, last["pos"] + 7 + last["size"]
    ref = lambda p_: b"\x01\x04\x00\x01\x00" + struct.pack("<I", p_) + b"\x00" * 6
    def dir_list_drop(parent, child, label):
        """list in the directory: u32 count + records (15 bytes) of the parent and its children; drop the record of `child`."""
        i = d.find(ref(parent["pos"]), D0, D1)
        if i < 0:
            probe.fail("directory list of %s not found" % label, "unknown layout; nothing written")
        cnt = u32(i - 4)
        j = d.find(ref(child["pos"]), i, i + 15 * cnt)
        if j < 0 or (j - i) % 15:
            probe.fail("record of the removed %s not in its directory list" % label, "unknown layout; nothing written")
        setu32(i - 4, cnt - 1, label)
        E.append((j, 15, b""))
        return i
    trk = t.get((0x2624, 0x2620), [])
    if len(trk) < 2:
        probe.fail("found %d track blocks 0x2620, need at least 2" % len(trk), "use a session with at least two tracks")
    victim, keep = trk[-1], trk[-2]
    m = re.search(rb"\x2a\x00\x00\x00(.{8})\x00\x00\x00\x00\x2a\x00\x00\x00\1", d[victim["pos"]:victim["pos"] + 7 + victim["size"]], re.S)   # same pattern as addtrack: id, 4 zero bytes, id
    if not m:
        probe.fail("track id (2a 00 00 00 + 8 bytes, twice) not found in the last 0x2620", "unknown layout; nothing written")
    id8 = m.group(1)
    print("removing track id %s (0x2620 at %d)" % (id8.hex(), victim["pos"]))
    if "route" in want:
        par = t[(0x1058,)][0]
        r = t[(0x1058, 0x1057)][-1]
        dele(r)
        setu32(par["pos"] + 9, u32(par["pos"] + 9) - 1, "0x1058 count")
        dir_list_drop(par, r, "0x1058/0x1057")
    if "x2107" in want:
        par = t[(0x2107,)][0]
        dele(t[(0x2107, 0x210b)][-1])
        setu32(par["pos"] + 9 + 9, u32(par["pos"] + 9 + 9) - 1, "0x2107 count")
    if "track" in want:
        par = t[(0x2624,)][0]
        dele(victim)
        setu32(par["pos"] + 9, u32(par["pos"] + 9) - 1, "0x2624 count")
        dir_list_drop(par, victim, "0x2624/0x2620")
        clip = [n for n in probe.walk([keep]) if n["ct"] == 0x2010]
        vclip = [n for n in probe.walk([victim]) if n["ct"] == 0x2010]
        if clip and vclip and d[vclip[0]["pos"] + 47] == 1 and d[clip[0]["pos"] + 47] == 0 and d[clip[0]["pos"] + 227] == 0:
            setbyte(clip[0]["pos"] + 47, 0, 1, "clip last-flag")                  # T13: the 'last' flags move back to the remaining clip
            setbyte(clip[0]["pos"] + 227, 0, 1, "clip last-flag")
        setu32(last["pos"] + 9, u32(last["pos"] + 9) - 1, "directory counter")   # first directory counter: -1 per track
    if "x258a" in want:
        ent = _chain(tree, (0x2587, 0x2551, 0x258b, 0x258a, 0x2589))
        keys = [struct.unpack_from("<H", d, x_["pos"] + 9)[0] for x_ in ent]
        vi = keys.index(max(keys))
        setu32(ent[0]["pos"] - 4, u32(ent[0]["pos"] - 4) - 1, "0x2589 count")
        if "keys" in want and len(ent) == 3 and [x_["size"] for x_ in ent] == [266, 266, 276][:0] + [x_["size"] for x_ in ent] and keys == [0, 2, 1]:
            big, orig = ent[0], ent[2]                                            # addtrack/T13 order [key 0, key 2 (new), key 1] -> T0 order [key 1, key 0]
            ob = bytearray(d[orig["pos"]:orig["pos"] + 7 + orig["size"]])
            if ob[9 + 27] == 3:
                ob[9 + 27] = 4
            E.append((ent[0]["pos"], ent[2]["pos"] + 7 + ent[2]["size"] - ent[0]["pos"], bytes(ob) + d[big["pos"]:big["pos"] + 7 + big["size"]]))
        else:
            dele(ent[vi])
    if "markers" in want:
        for mk in t.get((0x2030, 0x2077), []):
            e_ = [k_ for k_ in mk["kids"] if k_["ct"] == 0x2506]
            hb, he = mk["pos"] + 9, mk["kids"][0]["pos"]
            K = len(trk) + 1                                                      # tracks incl. click before the removal
            i_ = d.find(b"\xff\xff\xff\xff" + struct.pack("<I", K), hb, he)
            if i_ < 0 or u32(i_ + 4 + 55 + K) != K or len(e_) < 2:
                probe.fail("per-track counters of marker at %d not where expected" % mk["pos"], "unknown layout; skip group markers")
            c1 = i_ + 4
            setbyte(c1, K, K - 1, "marker counter")
            E.append((c1 + 4 + K - 1, 1, b""))                                    # the per-track byte of the removed track
            setbyte(c1 + 55 + K, K, K - 1, "marker counter 2")
            dele(e_[-1])
    if "click" in want:
        par = t[(0x2519,)][0]
        ks = [k_ for k_ in par["kids"] if k_["ct"] == 0x251a]
        if len(ks) % 2 or len(ks) < 6:
            probe.fail("0x2519 has %d blocks 0x251a, expected 2 x N (N >= 3)" % len(ks), "unknown layout; nothing written")
        h = len(ks) // 2
        first, second = ks[:h], ks[h:]
        dele(first[-1]); dele(second[-1])
        setu32(par["pos"] + 9 + 14, u32(par["pos"] + 9 + 14) - 1, "0x2519 count")
        i0 = dir_list_drop(par, second[-1], "0x2519/0x251a")
        k = len(first)
        rec = b"\x01" + struct.pack("<HH", 4 * k, k) + b"".join(struct.pack("<I", x_["pos"]) for x_ in first)
        j = d.find(rec, D0, D1)
        if j < 0:
            probe.fail("directory record with the %d first-half 0x251a positions not found" % k, "unknown layout; nothing written")
        setbyte(j + 1, 4 * k, 4 * (k - 1), "k record"); setbyte(j + 3, k, k - 1, "k record")
        E.append((j + 5 + 4 * (k - 1), 4, b""))
        pre = b"\x19\x25\xff\xff\xff\xff\x01" + bytes([k]) + b"\x00\x00\x00"
        n_ = 0
        for tail in (b"\x1b\x25", b"\x1c\x25", b"\x16\x27"):
            q = d.find(pre + tail, i0, D1)
            while q >= 0:
                setbyte(q + 7, k, k - 1, "N record"); n_ += 1
                q = d.find(pre + tail, q + 1, D1)
        jr = d.find(ref(second[-1]["pos"]), i0 + 15 * u32(i0 - 4), D1)
        if jr < 0 or d[jr - 30:jr - 24] != b"\x02\x00\x00\x00\x19\x25" or d[jr - 30 + 11] != k:
            probe.fail("single directory record of the removed 0x251a block not as expected", "unknown layout; nothing written")
        E.append((jr - 30, 45, b""))
        print("click group: 2 blocks 0x251a, %d N records, k %d -> %d" % (n_, k, k - 1))
    if "names" in want:
        par = t[(0x2519,)][0]
        k0 = par["kids"][0]["pos"]
        ip = d.find(b"\x2a\x00\x00\x00" + id8, par["pos"] + 9, k0)
        s0 = None
        for L in range(1, 61):
            s_ = ip - 6 - L - 6
            if d[s_:s_ + 2] == b"\x01\x00" and u32(s_ + 2) == L:
                s0 = s_
                break
        if ip < 0 or s0 is None or ip + 12 + 3 != k0:
            probe.fail("track-list entry of the removed track not found in the head of 0x2519 (must be the last entry)", "unknown layout; skip group names")
        E.append((s0, k0 - s0, b""))
        ks_ = par["kids"]
        g_ = [i_ for i_ in range(len(ks_) - 1) if ks_[i_ + 1]["pos"] - (ks_[i_]["pos"] + 7 + ks_[i_]["size"]) == 4]
        if len(g_) != 1:
            probe.fail("found %d 4-byte gaps between the children of 0x2519" % len(g_), "unknown layout; skip group names")
        e_ = ks_[g_[0]]["pos"] + 7 + ks_[g_[0]]["size"]
        setu32(e_, u32(e_) - 1, "0x2519 trailing counter")
    if "lists" in want:
        for blk in [n for n in probe.walk(tree) if n["ct"] == 0x202a]:
            b0 = blk["pos"] + 9
            n0 = u32(b0 + 16)
            if n0 < 3:
                probe.fail("0x202a list at %d has count %d" % (blk["pos"], n0), "unknown layout; skip group lists")
            setu32(b0 + 16, n0 - 1, "0x202a count")
            E.append((b0 + 20 + 2 * (n0 - 1), 2, b""))                              # last u16 entry
    if "cnt2" in want:
        for cts in ((0x2016, 0x258b, 0x258a, 0x2581, 0x2056), (0x2587, 0x2551, 0x258b, 0x258a, 0x2581, 0x2056), (0x2056,)):
            h_ = _chain(tree, cts)[:1]
            if h_ and d[h_[0]["pos"] + 9 + 13] > 2:
                E.append((h_[0]["pos"] + 9 + 13, 1, bytes([d[h_[0]["pos"] + 9 + 13] - 1])))
        for b_ in ([x_ for x_ in probe.walk([keep]) if x_["ct"] == 0x2015] if len(trk) == 2 else []):     # back to 4 only when ONE track remains
            if d[b_["pos"] + 9 + 56] == 3:
                E.append((b_["pos"] + 9 + 56, 1, b"\x04"))
    if "renum" in want:
        b_ = _chain(tree, (0x2624, 0x261e, 0x261b))
        old_ = b"\x01\x01\x0a\x00" + struct.pack("<10I", *range(1, 11))
        i_ = d.find(old_, b_[0]["pos"], b_[0]["pos"] + 7 + b_[0]["size"]) if b_ and len(trk) == 2 else -1
        if i_ >= 0:
            E.append((i_ + 4, 40, struct.pack("<10I", *range(71, 81))))
    out = _splice(d, tree, E)
    write_new(dst, scramble(out))
    print("wrote %s (%d bytes)" % (dst, len(out)))



# splice engine with insertions + addtrack2 (J3, any number of tracks)
def _splice2(d, tree, edits):
    """Like _splice, but edits are dicts {p, ol, nb, enc}: nb = bytes or (length, fn) where fn(start) -> bytes (start(e) = output position of
    edit e, passed as a function; used for directory records that hold the position of a NEW block). enc = position of the innermost block an insertion belongs to
    (needed when it sits exactly at the end of a block); without enc an insertion belongs to the blocks with data start <= p < data end."""
    d = bytes(d)
    E = sorted(edits, key=lambda e: (e["p"], e["ol"]))
    ln = lambda e: e["nb"][0] if isinstance(e["nb"], tuple) else len(e["nb"])
    for a_, b_ in zip(E, E[1:]):
        if a_["p"] + a_["ol"] > b_["p"]:
            probe.fail("overlapping edits at %d / %d" % (a_["p"], b_["p"]), "internal error of the command; nothing written")
    acc, starts = 0, {}
    for e in E:
        starts[id(e)] = e["p"] + acc
        acc += ln(e) - e["ol"]
    start = lambda e: starts[id(e)]
    inside = lambda x: any(e["p"] <= x < e["p"] + e["ol"] for e in E)
    f = lambda x: x + sum(ln(e) - e["ol"] for e in E if e["p"] + e["ol"] <= x)
    nodes = list(probe.walk(tree))
    gone = {n["pos"] for n in nodes if inside(n["pos"])}
    enc_chain = {}
    for e in E:
        if e.get("enc") is not None:
            enc_chain[id(e)] = {n["pos"] for n in _path_to(tree, e["enc"])}
    out, pos = bytearray(), 0
    for e in E:
        nb = e["nb"][1](start) if isinstance(e["nb"], tuple) else e["nb"]
        if len(nb) != ln(e):
            probe.fail("lazy edit at %d gave %d bytes, %d announced" % (e["p"], len(nb), ln(e)), "internal error; nothing written")
        out += d[pos:e["p"]] + nb
        pos = e["p"] + e["ol"]
    out += d[pos:]
    for n in nodes:
        if n["pos"] in gone:
            continue
        a, b = n["pos"] + 7, n["pos"] + 7 + n["size"]
        dd = 0
        for e in E:
            dl = ln(e) - e["ol"]
            if not dl:
                continue
            if id(e) in enc_chain:
                dd += dl if n["pos"] in enc_chain[id(e)] else 0
            elif e["ol"] == 0:
                dd += dl if a <= e["p"] < b else 0
            elif a <= e["p"] and e["p"] + e["ol"] <= b:
                dd += dl
        if dd:
            struct.pack_into("<I", out, f(n["pos"]) + 3, n["size"] + dd)
    stale, used = [], 0
    for s_ in _sites_once(d, tree):
        if inside(s_):
            continue
        v = struct.unpack_from("<I", d, s_)[0]
        if v in gone:
            stale.append((s_, v))
            continue
        struct.pack_into("<I", out, f(s_), f(v))
        used += 1
    if stale:
        probe.fail("%d stored positions point to removed blocks: %s" % (len(stale), stale[:8]), "unknown directory record; nothing written")
    out = bytes(out)
    tree2 = probe.parse(out, HEADER, len(out))
    if sum(t_["size"] + 7 for t_ in tree2) != len(out) - HEADER:
        probe.fail("edited file does not parse completely", "nothing written")
    _check_sites(out, tree2)
    print("splice: %d edits, %d stored positions remapped, %d bytes -> %d bytes" % (len(E), used, len(d), len(out)))
    return out





# addtrack3 (instrument tracks)




def cmd_addtrack3(src, dst, *opts):
    """addtrack3 = addtrack4 (track from fields; the v1.55 - v1.70 clone / donor path and option clone=1 are removed, clean room).
    Example: python3 ptx_edit.py addtrack3 in.ptx out.ptx kind=instrument stereo=1 name=Keys"""
    if any(x.startswith("clone=") for x in opts):
        probe.fail("option clone= was removed in v1.73 (clean room: no donor blocks)", "leave it out: the track is built from fields")
    return cmd_addtrack4(src, dst, *opts)




# addtrack3 kind=audio | aux
def _demote_last(d, kids, E, keep_last=False):
    """clear the 'last track' marks of the channel blocks KIDS (all tracks but the new one). MIDI / instrument: clip block 0x2010 as in
    v1.55 (351-byte form flags 47 / 227, 371-byte form 47 / 51 / 247 + shrink to 351, byte 83 4 -> 3). Audio 0x261c: container 0x200b in its
    524-byte form, flags at 46 / 50 / 294. Aux 0x261e / master 0x261d: container 0x200d / 0x200c in its 361-byte form, flag 49, bytes 52 / 53
    00 01 -> 01 00, flag 257 (ground truth STAIR_05: Pro Tools clears exactly these; it also shrinks audio / aux containers, the master one not:
    the shrink is left out here). Blocks in other forms (never the last track of a save) are left alone."""
    put = lambda p, v: E.append({"p": p, "ol": 1, "nb": bytes([v]), "enc": None})
    for k in kids:
        if k["ct"] in (0x261e, 0x261d, 0x263b):                                # aux / routing folder / master (+ folder) in the built form: Pro Tools' demotion
            try:                                                               # in field terms (STAIR_05 S2 -> S3, STAIR_08 S0 -> S1): view flags f6 =
                blk_ = d[k["pos"]:k["pos"] + 7 + k["size"]]                    # 00 01 00 01 00 00, 'last' = 0 (one view cell less), g = 0
                if k["ct"] == 0x263b:
                    nmf_, tf_, vf_ = _folder_channel_fields(blk_)
                    fl_, same_ = {"v": vf_}, _folder_channel(nmf_, tf_, vf_) == blk_
                else:
                    fl_ = _aux_channel_fields(blk_)
                    same_ = _aux_channel(**fl_) == blk_
                if same_:
                    v15_ = [x_ for x_ in probe.walk([k]) if x_["ct"] == 0x2015][0]
                    c_ = sorted(v15_["kids"], key=lambda x_: x_["pos"])
                    q0_ = c_[0]["pos"] + 7 + c_[0]["size"]
                    E.append({"p": q0_, "ol": 6, "nb": b"\x00\x01\x00\x01\x00\x00", "enc": None})
                    ql_ = q0_ + 45 + len(fl_["v"]["comment"])
                    if d[ql_] == 1 and not keep_last:                          # keep_last = a basic folder was added (STAIR_10 S7)
                        put(ql_, 0)
                        E.append({"p": c_[1]["pos"], "ol": 7 + c_[1]["size"], "nb": b"", "enc": None})
                    ge_ = v15_["pos"] + 7 + v15_["size"] - 4
                    if d[ge_]:
                        put(ge_, 0)
                    continue
            except (struct.error, IndexError, UnicodeDecodeError, ValueError, KeyError):
                pass
        if k["ct"] == 0x261c:                                                  # audio block in the built form: demotion as Pro Tools does it, in field
            try:                                                               # terms (STAIR_08 S3 -> S4): view flags a / b / g = 0, 'last' = 0 (one 0x2038 less),
                blk_ = d[k["pos"]:k["pos"] + 7 + k["size"]]                    # the 28 bytes of 0x2104 = 0
                fl_ = _audio_channel_fields(blk_)
                if _audio_channel(**fl_) == blk_:
                    v15_ = [x_ for x_ in probe.walk([k]) if x_["ct"] == 0x2015][0]           # single-field edits (a whole-block replacement would
                    k38_ = [x_ for x_ in v15_["kids"] if x_["ct"] == 0x2038]                  # drop blocks the directory points to)
                    w04_ = [x_ for x_ in v15_["kids"] if x_["ct"] == 0x2104][0]
                    q0_ = k38_[0]["pos"] + 7 + k38_[0]["size"]
                    for off_ in (0, 4):
                        if d[q0_ + off_]:
                            put(q0_ + off_, 0)
                    E.append({"p": w04_["pos"] + 18, "ol": 28, "nb": b"\x00" * 28, "enc": None})
                    qe_ = w04_["pos"] + 7 + w04_["size"]
                    if d[qe_ + 23] == 1 and len(k38_) == 3 and not keep_last:
                        put(qe_ + 23, 0)
                        E.append({"p": k38_[1]["pos"], "ol": 7 + k38_[1]["size"], "nb": b"", "enc": None})
                    ge_ = v15_["pos"] + 7 + v15_["size"] - 4
                    if d[ge_]:
                        put(ge_, 0)
                    continue
            except (struct.error, IndexError, UnicodeDecodeError, ValueError):
                pass
        for c in k["kids"]:
            p = c["pos"]
            if c["ct"] == 0x2010:
                offs = (47, 227) if c["size"] == 351 else (47, 51, 247) if c["size"] == 371 else None
                if offs is None:
                    probe.fail("clip block 0x2010 of %d bytes (known: 351, 371)" % c["size"], "unknown layout; nothing written")
                for off in offs + (83,):
                    if d[p + off] == (4 if off == 83 else 1):
                        put(p + off, 3 if off == 83 else 0)
                if c["size"] == 371:
                    if d[p + 96:p + 116] != bytes.fromhex("5a02000d0000003a205a01000200000037200101") or d[p + 92] != 1:
                        probe.fail("371-byte clip block at %d: extra 0x203a child not where expected" % p, "unknown layout; nothing written")
                    put(p + 92, 0)
                    E.append({"p": p + 96, "ol": 20, "nb": b"", "enc": None})
            elif c["ct"] == 0x200b and c["size"] == 517:
                for off in (46, 50, 294):
                    if d[p + off] == 1:
                        put(p + off, 0)
            elif c["ct"] in (0x200d, 0x200c) and c["size"] == 354 and d[p + 49] == 1:
                put(p + 49, 0)
                if d[p + 52:p + 54] == b"\x00\x01":
                    put(p + 52, 1); put(p + 53, 0)
                if d[p + 257] == 1:
                    put(p + 257, 0)


def _own_pos(node, off):
    """position (in the coordinates of NODE's tree) of byte OFF of the block's OWN data (its data without the child blocks)."""
    p = node["pos"] + 9
    for k in sorted(node.get("kids", []), key=lambda k_: k_["pos"]):
        if off < k["pos"] - p:
            return p + off
        off -= k["pos"] - p
        p = k["pos"] + 7 + k["size"]
    return p + off




# newsession (J6, stage 6b)
def cmd_newsession(src, dst, *opts):
    """new session from a template session (e.g. a template session): options name=<session name> (renames the
    session/file name strings of the path blocks), bpm=<tempo> (every constant tempo record 0x2028, f64 at record offset 40),
    rate=<Hz> (EXPERIMENTAL: 0x1028 u32 at block +11 and the f64 tail of each 0x2028 block).
    Example: python3 ptx_edit.py newsession template.ptx Song.ptx name=Song bpm=96"""
    o = {}
    for x in opts:
        k, _, v = x.partition("=")
        if k not in ("name", "bpm", "rate") or not v:
            probe.fail("unknown option '%s'" % x, "use name=<text> bpm=<number> rate=<44100|48000|88200|96000>")
        o[k] = v
    raw, d, tree = descramble_file(src)
    out = bytearray(d)
    tempo = [n for n in probe.walk(tree) if n["ct"] == 0x2028]
    if "bpm" in o:
        bpm = float(o["bpm"])
        if not 20.0 <= bpm <= 999.0:
            probe.fail("bpm %s out of range" % o["bpm"], "use 20..999")
        n_ = 0
        for b_ in tempo:
            i = bytes(out).find(b"Const", b_["pos"], b_["pos"] + 7 + b_["size"])
            while i >= 0:
                struct.pack_into("<d", out, i + 40, bpm)
                n_ += 1
                i = bytes(out).find(b"Const", i + 1, b_["pos"] + 7 + b_["size"])
        if not n_:
            probe.fail("no tempo record (0x2028 'Const') found", "use a template saved by Pro Tools")
        print("tempo: %d records set to %.3f bpm" % (n_, bpm))
    if "rate" in o:
        rate = int(o["rate"])
        if rate not in (44100, 48000, 88200, 96000, 176400, 192000):
            probe.fail("rate %d not supported" % rate, "use 44100, 48000, 88200, 96000, 176400 or 192000")
        for b_ in [n for n in probe.walk(tree) if n["ct"] == 0x1028]:
            old = struct.unpack_from("<I", out, b_["pos"] + 11)[0]
            if old not in (44100, 48000, 88200, 96000, 176400, 192000):
                probe.fail("0x1028 rate field holds %d" % old, "unknown layout; nothing written")
            struct.pack_into("<I", out, b_["pos"] + 11, rate)
        for b_ in tempo:
            struct.pack_into("<d", out, b_["pos"] + 7 + b_["size"] - 8, float(rate))
        print("sample rate set to %d (experimental)" % rate)
    tmp = dst + ".tmp_newsession"
    write_new(tmp, scramble(bytes(out)))
    if "name" in o:
        nm = o["name"]
        if not (1 <= len(nm) <= 60 and nm.isascii() and nm.isprintable() and "/" not in nm and ":" not in nm):
            probe.fail("session name '%s' not allowed" % nm, "use 1..60 printable ASCII characters without / and :")
        stem = os.path.splitext(os.path.basename(src))[0]
        pairs = [stem + ".ptx", nm + ".ptx"]
        if bytes(out).count(struct.pack("<I", len(stem)) + stem.encode()):
            pairs += [stem, nm]
        cmd_renamex(tmp, dst, *pairs)
    else:
        write_new(dst, open(tmp, "rb").read())
    os.replace(tmp, tmp + ".done")        # deleting is not allowed in the connected folders: keep the temp file, renamed
    print("wrote %s" % dst)


# Read-only decoder helpers used to locate tracks, strips, lanes, and insert slots
def _decoder():
    """Load ptx_decode.py next to this file."""
    mod = os.path.join(HERE, "ptx_decode.py")
    if not os.path.isfile(mod):
        c = sorted(_glob.glob(os.path.join(HERE, "ptx_decode_v*.py")))
        if not c:
            probe.fail("ptx_decode.py not found next to this script", "keep the decoder in <kit>/tools")
        mod = c[-1]
    sp = importlib.util.spec_from_file_location("ptx_decode_for_edit", mod)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def _channel(dec, d, tree, name):
    """(index, channel block) of the track called `name` (displayed name); fails with the list of names."""
    names = [t["name"] for t in dec.tracks(d, tree, [])]
    top = dec.find(tree, 0x2624)
    if name not in names:
        probe.fail("track '%s' not found" % name, "tracks: %s" % names)
    if not top or len(top["kids"]) != len(names):
        probe.fail("channel blocks 0x2624 do not match the track list", "unknown layout; nothing written")
    i = names.index(name)
    return i, top["kids"][i]


def _strips_of(ch):
    """(main strip, [send strips]) of a channel block, as the decoder assigns them (first 0x260D with lanes and an output)."""
    def sub(n):
        for k in n["kids"]:
            yield k
            yield from sub(k)
    lanes = [x for x in sub(ch) if x["ct"] == 0x260D and any(k["ct"] == 0x260A for k in x["kids"])]
    if not lanes:
        probe.fail("track has no mixer strip", "MIDI tracks and folders have no lanes")
    main = next((x for x in lanes if any(k["ct"] == 0x260E for k in x["kids"])), lanes[0])
    return main, [x for x in lanes if x is not main]


def _lane_block(ch, lane):
    """0x260A block of a lane name: volume | mute | pan | pan2 | send<N>.volume | send<N>.mute | send<N>.pan (N from 1)."""
    main, sends = _strips_of(ch)
    st, kind = main, lane
    if lane.startswith("send"):
        n_, _, kind = lane[4:].partition(".")
        try:
            st = sends[int(n_) - 1]
        except (ValueError, IndexError):
            probe.fail("send '%s' not found (%d sends with lanes)" % (lane, len(sends)), "use send1.volume ... send%d.volume" % max(1, len(sends)))
    direct = [k for k in st["kids"] if k["ct"] == 0x260A]
    pcs = [k for k in st["kids"] if k["ct"] == 0x260C]                    # one 0x260C per panner (stereo: left, right input)
    pans = [p for p in (next((k for k in c["kids"] if k["ct"] == 0x260A), None) for c in pcs) if p is not None]
    pick = {"volume": direct[:1], "mute": direct[1:2], "pan": pans[:1], "pan2": pans[1:2]}.get(kind)
    if pick is None:
        probe.fail("unknown lane '%s'" % lane, "use volume, mute, pan, pan2 or send<N>.<volume|mute|pan>")
    if not pick:
        probe.fail("lane '%s' does not exist on this track" % lane, "pan2 exists on stereo tracks only; mute needs a second 0x260A")
    return pick[0]


def _points(text):
    """'pos:val,pos:val' -> [(pos, val)]; pos in the lane's time base (samples on sample tracks), val in lane units
    (volume dB x 10, -1440 = -inf; pan -100 .. +100; mute 0 / 1)."""
    pts = []
    for item in text.split(","):
        a, _, b = item.partition(":")
        try:
            pts.append((int(a), int(b)))
        except ValueError:
            probe.fail("bad point '%s'" % item, "write POS:VALUE pairs separated by commas, e.g. 0:0,192000:-200,384000:0")
    if not pts or any(p < 0 for p, _ in pts) or [p for p, _ in pts] != sorted(p for p, _ in pts):
        probe.fail("points must be non-negative and in time order: %s" % text, "sort the points by position")
    if any(not -32768 <= v <= 32767 for _, v in pts):
        probe.fail("value out of the int16 range in %s" % text, "volume -1440 .. 120, pan -100 .. 100, mute 0 / 1")
    return pts


def cmd_setlane(src, dst, *triples):
    """replace the points of automation lanes: TRACK LANE POINTS [...]. Lane 0x260A data = 01 46 01 00 | u32 L = 14 + 6 n |
    u16 time base | u32 n | u16 2 | u16 n - 1 | u64 first pos, i16 value | (n - 1) x (u32 pos, i16 value) | u16 0 (L and
    n - 1; u64 first position, tick lanes); the point list is spliced (sizes and stored offsets follow, as in addtrack2).
    Example: setlane in.ptx out.ptx B1 volume 0:0,192000:-200,384000:0 B2 pan 0:-100"""
    if not triples or len(triples) % 3:
        probe.fail("need TRACK LANE POINTS triples", "usage: setlane <in> <out> TRACK LANE POS:VAL,... [TRACK LANE POINTS ...]")
    dec = _decoder()
    raw, d, tree = descramble_file(src)
    edits, seen = [], set()
    for name, lane, text in zip(triples[::3], triples[1::3], triples[2::3]):
        _, ch = _channel(dec, d, tree, name)
        b = _lane_block(ch, lane)
        if b["pos"] in seen:
            probe.fail("lane %s %s given twice" % (name, lane), "one triple per lane")
        seen.add(b["pos"])
        s = b["pos"] + 9
        n_old = struct.unpack_from("<I", d, s + 10)[0]
        if d[s:s + 4] != b"\x01\x46\x01\x00" or struct.unpack_from("<I", d, s + 4)[0] != 14 + 6 * n_old or s + 22 + 6 * n_old > b["pos"] + 7 + b["size"]:
            probe.fail("lane %s %s: %d points do not fit the block" % (name, lane, n_old), "unknown lane layout; nothing written")
        pts = _points(text)
        tb = struct.unpack_from("<H", d, s + 8)[0]                                 # 0 samples, 1 ticks
        if pts[0][0] != 0:                                                         # also on sample lanes
            probe.fail("lane %s %s: the first point must be at 0 (it is the start value)" % (name, lane),
                       "write 0:<value> first; for a later step add POS:<same value>; tick lanes count 960000 ticks per quarter")
        if tb not in (0, 1) or any(p_ > 0xFFFFFFFF for p_, _ in pts[1:]):
            probe.fail("lane %s %s: time base %d or a position beyond 32 bit" % (name, lane, tb), "positions after the first one are u32")
        first = 10 ** 12 if tb == 1 else pts[0][0]
        new = struct.pack("<Qh", first, pts[0][1]) + b"".join(struct.pack("<Ih", p, v) for p, v in pts[1:])   # first u64
        edits.append({"p": s + 4, "ol": 4, "nb": struct.pack("<I", 14 + 6 * len(pts))})              # body length
        edits.append({"p": s + 10, "ol": 4, "nb": struct.pack("<I", len(pts))})
        edits.append({"p": s + 16, "ol": 2, "nb": struct.pack("<H", (len(pts) - 1) & 0xFFFF)})          # n - 1
        edits.append({"p": s + 18, "ol": 4 + 6 * n_old, "nb": new})                                    # from the u64 on
        print("%s %s: %d -> %d points %s" % (name, lane, n_old, len(pts), pts))
    out = _splice2(d, tree, edits)
    write_new(dst, scramble(out))
    print("wrote %s (%d bytes)" % (dst, len(out)))


def _flag_site(dec, d, tree, name, flag):
    """Byte position(s) of a one-byte flag: solo | mode | active | bypass.<slot> | insert_active.<slot> | mute_static.
    Returns [(position, label)]; positions as in ptx_decode ."""
    _, ch = _channel(dec, d, tree, name)
    sub = list(dec._subtree(ch))
    if flag in ("solo", "mode"):
        inf = next((x for x in sub if x["ct"] == 0x102D), None)
        if not inf:
            probe.fail("track info 0x102D not found", "unknown layout")
        return [(inf["pos"] + (161 if flag == "solo" else 162) + struct.unpack_from("<I", d, inf["pos"] + 18)[0], flag)]
    if flag == "active":
        main, _ = _strips_of(ch)
        o = next((k for k in main["kids"] if k["ct"] == 0x260E), None)
        if not o:
            probe.fail("no output block 0x260E", "track without output")
        sites = [(o["pos"] + 12, "active")]
        # Pro Tools keeps a track inactive only when the channel box agrees too:
        box = next((k for k in ch["kids"] if k["ct"] == 0x261B), ch)
        if box["kids"]:
            sites.append((box["kids"][0]["pos"] + 7 + box["kids"][0]["size"] + 3, "box flag"))   # 4 bytes after the track info: last = 1 / 0
        if ch["ct"] == 0x2621:                                                  # on 0x2621, 01 01 0a 00 stays 1;
            k2010 = next((k for k in box["kids"] if k["ct"] == 0x2010), None)   # instead the byte right before 0x2010 is 1 (active) / 0 (inactive)
            if k2010 and d[k2010["pos"] - 1] in (0, 1):
                sites.append((k2010["pos"] - 1, "inst active flag"))
        else:
            sts = [k for k in box["kids"] if k["ct"] == 0x260D]
            if sts:
                lo = max([k["pos"] + 7 + k["size"] for k in box["kids"] if k["ct"] == 0x485A and k["pos"] > sts[-1]["pos"]] + [sts[-1]["pos"] + 7 + sts[-1]["size"]])
                if d[lo] == 1 and d[lo + 1] in (0, 1):
                    sites.append((lo + 1, "slot record flag"))                 # 01 <active> u16 n ids delay
        return sites
    if flag == "mute_static":
        main, _ = _strips_of(ch)
        t = next((k for k in main["kids"] if k["ct"] == 0x1029), None)
        return [(t["pos"] + 9 + 5, "1029+5"), (t["pos"] + 9 + 91, "1029+91")] if t else probe.fail("no strip table 0x1029", "unknown layout")
    kind, _, slot = flag.partition(".")
    if kind in ("bypass", "insert_active") and slot:
        lst = next((x for x in sub if x["ct"] == 0x2627), None)
        k = dec.SLOTS.index(slot) if slot in dec.SLOTS else -1
        if not lst or not 0 <= k < len(lst["kids"]) or lst["kids"][k]["ct"] not in (0x2616, 0x2617):
            probe.fail("slot %s of %s is empty" % (slot, name), "slots a - j; see 'ptx_decode --only tracks' (inserts)")
        s = lst["kids"][k]
        s = s["kids"][0] if s["ct"] == 0x2617 and s["kids"] else s
        if kind == "bypass":
            inst = next((x for x in s["kids"] if x["ct"] == 0x2615), None)
            return [(inst["pos"] + 7 + inst["size"], "bypass.%s" % slot)]
        rec = next((x for x in dec._subtree(s) if x["ct"] == 0x2613), None)
        last = rec["kids"][-1]
        sites = [(last["pos"] + 7 + last["size"], "insert_active.%s" % slot)]
        first = rec["kids"][0]                                            # also the byte after the state chunk
        if first is not last:
            sites.insert(0, (first["pos"] + 7 + first["size"], "insert_active.%s (state)" % slot))
        return sites
    probe.fail("unknown flag '%s'" % flag, "use solo, mode, active, mute_static, bypass.<slot>, insert_active.<slot>")


def _set_hidden(dec, out, tree, name, hide):
    """hidden = display number 0 in the track list 0x2519 (entry: tag 2A000000 + 12) and in every 0x251a name
    block (same entry layout); the other visible tracks are renumbered 1, 2, ... in list order. In place (same length)."""
    d = bytes(out)
    tr = dec.tracks(d, tree, [])
    names = [t["name"] for t in tr]
    if name not in names:
        probe.fail("track '%s' not found" % name, "tracks: %s" % names)
    old = {t["name"]: t["number"] for t in tr}
    hid = {n for n, num in old.items() if num == 0}
    (hid.add if hide else hid.discard)(name)
    new, k = {}, 0
    for n in names:
        if n in hid:
            new[n] = 0
        else:
            k += 1
            new[n] = k
    lst = next((b for b in probe.walk(tree) if b["ct"] == 0x2519), None)
    s0, e0 = lst["pos"] + 9, lst["pos"] + 7 + lst["size"]
    for n in names:                                                       # list entries: name, 6 bytes, tag 2A000000, 8 id bytes, number
        enc = struct.pack("<I", len(n.encode("utf-8"))) + n.encode("utf-8")
        i = d.find(enc, s0, e0)
        tag = i + len(enc) + 6
        if i < 0 or d[tag:tag + 4] != b"\x2a\x00\x00\x00" or d[tag + 12] != old[n]:
            probe.fail("track list entry of '%s' not where expected" % n, "unknown layout; nothing written")
        out[tag + 12] = new[n]
    for b in probe.walk([lst]):                                          # name blocks: u16 kind, u32 len, name, 6 bytes, tag, 8 ids, number
        if b["ct"] != 0x251A:
            continue
        x0 = b["pos"] + 9
        ln = struct.unpack_from("<I", d, x0 + 2)[0]
        nm = d[x0 + 6:x0 + 6 + ln].decode("utf-8", "replace")
        tag = x0 + 6 + ln + 6
        if nm not in new or d[tag:tag + 4] != b"\x2a\x00\x00\x00" or d[tag + 12] != old[nm]:
            probe.fail("name block 0x251a of '%s' not as expected" % nm, "unknown layout; nothing written")
        out[tag + 12] = new[nm]
    _, ch = _channel(dec, d, tree, name)                                   # view flag of the track (T65 j70: 0x2624 alone
    n15 = 0                                                                #   fixed it; byte 1 after the first child of 0x2015)
    for b in dec._subtree(ch):
        if b["ct"] == 0x2015 and b["kids"]:
            at = b["kids"][0]["pos"] + 7 + b["kids"][0]["size"] + 1
            if d[at] not in (0, 1):
                probe.fail("view flag of '%s' holds %d" % (name, d[at]), "unknown layout; nothing written")
            out[at] = 0 if hide else 1
            n15 += 1
    print("%s hidden=%d; display numbers %s; view flags %d" % (name, hide, new, n15))


def cmd_setflag(src, dst, *triples):
    """one-byte flags, same length: TRACK FLAG VALUE [...]. VALUE 0 / 1 (mode: 0 off, 1 read, 2 touch, 3 latch, 4 write).
    mute_static sets the two mirror bytes of 0x1029 (+5, +91); the mute LANE is set with setlane (TRACK mute POS:1).
    Example: setflag in.ptx out.ptx Au_m_T solo 0 Au_m_T bypass.a 0"""
    if not triples or len(triples) % 3:
        probe.fail("need TRACK FLAG VALUE triples", "usage: setflag <in> <out> TRACK FLAG VALUE [...]")
    dec = _decoder()
    raw, d, tree = descramble_file(src)
    census = probe.census(tree)
    out = bytearray(d)
    for name, flag, val in zip(triples[::3], triples[1::3], triples[2::3]):
        v = int(val)
        if flag == "hidden":                                                    # display numbers (track list + name blocks)
            _set_hidden(dec, out, tree, name, v)
            continue
        if not 0 <= v <= (4 if flag == "mode" else 1):
            probe.fail("value %s for %s" % (val, flag), "0 / 1; mode 0 .. 4")
        for p, label in _flag_site(dec, d, tree, name, flag):
            if flag != "mode" and out[p] not in (0, 1):
                probe.fail("%s %s: byte at %d holds %d, not 0 / 1" % (name, label, p, out[p]), "unknown layout; nothing written")
            print("%s %s: %d -> %d" % (name, label, out[p], v))
            out[p] = v
        if flag == "active":                                                    # inverted inactive flag before 0x4856
            _, ch = _channel(dec, d, tree, name)
            box = next((k for k in ch["kids"] if k["ct"] == 0x261B), ch)
            k4856 = next((k for k in box["kids"] if k["ct"] == 0x4856), None)
            if k4856:
                inv_pos = (k4856["pos"] - 31) if ch["ct"] == 0x2621 else (k4856["pos"] - 25)
                if out[inv_pos] in (0, 1):
                    out[inv_pos] = 1 - v
        if flag == "active" and v == 0:                                         # voice masks 0x2104 of the track are cleared
            _, ch = _channel(dec, d, tree, name)
            for b_ in dec._subtree(ch):
                if b_["ct"] == 0x2104:                                          # own bytes only (gaps between children)
                    cur, gaps = b_["pos"] + 9, []
                    for k_ in b_["kids"]:
                        gaps.append((cur, k_["pos"]))
                        cur = k_["pos"] + 7 + k_["size"]
                    gaps.append((cur, b_["pos"] + 7 + b_["size"]))
                    n_ = 0
                    for a_, e_ in gaps:
                        if e_ > a_ and any(out[a_:e_]):
                            out[a_:e_] = bytes(e_ - a_)
                            n_ += e_ - a_
                    if n_:
                        print("%s voice mask 0x2104 at %d cleared (%d own bytes)" % (name, b_["pos"], n_))
    out = bytes(out)
    tree2 = probe.parse(out, HEADER, len(out))
    if probe.census(tree2) != census:
        probe.fail("edited file does not parse like the original", "nothing written")
    write_new(dst, scramble(out))
    print("wrote %s (%d bytes)" % (dst, len(out)))


def cmd_setparam(src, dst, *quads):
    """plug-in parameter of a "Complete Controls State" chunk, same length: TRACK SLOT NAME VALUE [...]
    (d_ = f64 BE, l_ = i32 BE; layout of ptx_decode name, NUL, pad to 4, value). Example: setparam in out Au_m_T a d_gain -6"""
    if not quads or len(quads) % 4:
        probe.fail("need TRACK SLOT NAME VALUE groups", "usage: setparam <in> <out> TRACK SLOT NAME VALUE [...]")
    dec = _decoder()
    raw, d, tree = descramble_file(src)
    census = probe.census(tree)
    out = bytearray(d)
    for name, slot, pname, val in zip(quads[::4], quads[1::4], quads[2::4], quads[3::4]):
        _, ch = _channel(dec, d, tree, name)
        lst = next((x for x in dec._subtree(ch) if x["ct"] == 0x2627), None)
        k = dec.SLOTS.index(slot) if slot in dec.SLOTS else -1
        if not lst or not 0 <= k < len(lst["kids"]) or lst["kids"][k]["ct"] not in (0x2616, 0x2617):
            probe.fail("slot %s of %s is empty" % (slot, name), "slots a - j")
        st = next((x for x in dec._subtree(lst["kids"][k]) if x["ct"] == 0x1038), None)
        a, b = st["pos"] + 9, st["pos"] + 7 + st["size"]
        s = d.find(b"Complete Controls State\x00", a, b)
        mm = dec._PNAME.search(d, s + 24, b) if s >= 0 else None
        hit = None
        while mm:
            nm = mm.group(1)
            j = mm.end() + (-(len(nm) + 1)) % 4
            w = 8 if nm[:1] == b"d" else 4
            if nm.decode() == pname:
                hit = (j, w)
                break
            mm = dec._PNAME.match(d, j + w, b)
        if not hit:
            probe.fail("parameter %s not found in slot %s of %s" % (pname, slot, name), "names: ptx_decode --only tracks (inserts.params)")
        j, w = hit
        old = struct.unpack_from(">d" if w == 8 else ">i", out, j)[0]
        struct.pack_into(">d" if w == 8 else ">i", out, j, float(val) if w == 8 else int(val))
        print("%s %s %s: %s -> %s" % (name, slot, pname, old, val))
    out = bytes(out)
    if probe.census(probe.parse(out, HEADER, len(out))) != census:
        probe.fail("edited file does not parse like the original", "nothing written")
    write_new(dst, scramble(out))
    print("wrote %s (%d bytes)" % (dst, len(out)))


def cmd_setclipgain(src, dst, *pairs):
    """clip-gain value of entry K (1 = first) of the list 0x2637, every point of that lane set to DB (f32), same length.
    Example: setclipgain in.ptx out.ptx 1 -12 2 0"""
    if not pairs or len(pairs) % 2:
        probe.fail("need K DB pairs", "usage: setclipgain <in> <out> K DB [K DB ...]")
    raw, d, tree = descramble_file(src)
    census = probe.census(tree)
    b = next((n for n in probe.walk(tree) if n["ct"] == 0x2637), None)
    if not b:
        probe.fail("no clip-gain list 0x2637", "the session has no clip gain; set one in Pro Tools first")
    x0, end, out = b["pos"] + 9, b["pos"] + 7 + b["size"], bytearray(d)
    ents, i = [], x0 + 4
    while i + 8 <= end and d[i:i + 4] == b"\x01\x46\x01\x00":
        ln = struct.unpack_from("<I", d, i + 4)[0]
        ents.append((i + 8, ln))
        i += 8 + ln
    for k, db in zip(pairs[::2], pairs[1::2]):
        k = int(k)
        if not 1 <= k <= len(ents):
            probe.fail("entry %d not found (%d entries)" % (k, len(ents)), "K = 1 .. %d" % len(ents))
        body, ln = ents[k - 1]
        n = struct.unpack_from("<I", d, body + 2)[0]
        for q in range(n):
            at = body + 18 + 8 * q
            print("entry %d point %d: %.3f -> %s dB" % (k, q, struct.unpack_from("<f", out, at)[0], db))
            struct.pack_into("<f", out, at, float(db))
    out = bytes(out)
    if probe.census(probe.parse(out, HEADER, len(out))) != census:
        probe.fail("edited file does not parse like the original", "nothing written")
    write_new(dst, scramble(out))
    print("wrote %s (%d bytes)" % (dst, len(out)))


def cmd_setdelay(src, dst, *pairs):
    """track user delay (samples, i32) of TRACK, same length: TRACK SAMPLES [...]. Record after the last strip of
    the channel: 01 xx, u16 n, n x u32 ids, i32 delay (ptx_decode  user_delay). Example: setdelay in.ptx out.ptx B1 4800"""
    if not pairs or len(pairs) % 2:
        probe.fail("need TRACK SAMPLES pairs", "usage: setdelay <in> <out> TRACK SAMPLES [...]")
    dec = _decoder()
    raw, d, tree = descramble_file(src)
    census = probe.census(tree)
    out = bytearray(d)
    for name, val in zip(pairs[::2], pairs[1::2]):
        _, ch = _channel(dec, d, tree, name)
        box = next((k for k in ch["kids"] if k["ct"] == 0x261B), ch)
        sts = [k for k in box["kids"] if k["ct"] == 0x260D]
        if not sts:
            probe.fail("track %s has no strip" % name, "audio, aux, instrument and master tracks have a delay")
        nxt = [k for k in box["kids"] if k["pos"] > sts[-1]["pos"] and k["ct"] != 0x485A]
        lo = max([dec.probe_end(k) for k in box["kids"] if k["ct"] == 0x485A and k["pos"] > sts[-1]["pos"]] + [dec.probe_end(sts[-1])])
        hi = nxt[0]["pos"] if nxt else dec.probe_end(box)
        if hi - lo < 8 or d[lo] != 1 or d[lo + 1] not in (0, 1):
            probe.fail("no delay record after the strips of %s" % name, "unknown layout; nothing written")
        n = struct.unpack_from("<H", d, lo + 2)[0]
        at = lo + 4 + 4 * n
        if n > 64 or at + 4 > hi:
            probe.fail("delay record of %s: %d ids" % (name, n), "unknown layout; nothing written")
        print("%s user delay: %d -> %d samples" % (name, struct.unpack_from("<i", out, at)[0], int(val)))
        struct.pack_into("<i", out, at, int(val))
    out = bytes(out)
    if probe.census(probe.parse(out, HEADER, len(out))) != census:
        probe.fail("edited file does not parse like the original", "nothing written")
    write_new(dst, scramble(out))
    print("wrote %s (%d bytes)" % (dst, len(out)))






def cmd_diffblocks(a_path, b_path):
    """list top-level blocks (type:n) whose bytes differ between two files (input for T65); prints one 'CT:n' per line."""
    _, a, ta = descramble_file(a_path)
    _, b, tb = descramble_file(b_path)
    from collections import defaultdict
    ga, gb = defaultdict(list), defaultdict(list)
    for n in ta:
        ga[n["ct"]].append(n)
    for n in tb:
        gb[n["ct"]].append(n)
    for ct in sorted(set(ga) | set(gb)):
        for i, (x_, y_) in enumerate(zip(ga[ct], gb[ct])):
            if bytes(a[x_["pos"]:x_["pos"] + 7 + x_["size"]]) != bytes(b[y_["pos"]:y_["pos"] + 7 + y_["size"]]):
                print("%04x:%d" % (ct, i + 1))
        if len(ga[ct]) != len(gb[ct]):
            print("# %04x count %d / %d" % (ct, len(ga[ct]), len(gb[ct])))



# ---------------------------------------------------------------- clean-room writers from the hand session MIX_07
def _playlist_block(d, tree, track):
    """the audio playlist 0x1052 named TRACK (u32 length + name) under 0x1054; fails with the playlist names."""
    names = []
    for top in probe.walk(tree):
        if top["ct"] != 0x1054:
            continue
        for pl in top["kids"]:
            if pl["ct"] != 0x1052:
                continue
            p = pl["pos"] + 9
            n = struct.unpack_from("<I", d, p)[0]
            if 0 < n < 256:
                nm = d[p + 4:p + 4 + n].decode("utf-8", "replace")
                names.append(nm)
                if nm == track:
                    return pl
    probe.fail("audio playlist '%s' not found" % track, "playlists: %s (the playlist carries the track name)" % names)



def _epos(d, o):
    """position of a playlist entry (own data at o): u40 at +7; own byte 14 = 0x40 -> ticks (10^12 offset removed), else samples."""
    v = int.from_bytes(d[o + 7:o + 12], "little")
    return v - 10 ** 12 if d[o + 14] == 0x40 else v


def _epos_bytes(b, o, v):
    """the 5 position bytes for value v in the time base of the entry at own offset o of b."""
    return (10 ** 12 + v if b[o + 14] == 0x40 else v).to_bytes(5, "little")


def _pos(dec, d, tree, text):
    """position text: 'sN' = samples (sample-based playlists), else bar:N / tN as _ticks."""
    return int(text[1:]) if text.startswith("s") else _ticks(dec, d, tree, text)

def _ticks(dec, d, tree, text):
    """position text -> ticks (960 000 per quarter): 'bar:N' (meter 4/4 only; an empty meter map counts as 4/4) or 'tN'."""
    if text.startswith("t"):
        return int(text[1:])
    if text.startswith("bar:"):
        mt = dec.meter(d, tree, [], 1) or dec.meter(d, tree, [])
        if any((m_.get("numerator"), m_.get("denominator")) != (4, 4) for m_ in mt):
            probe.fail("bar positions need a constant 4/4 meter (meter map: %s)" % mt, "give the position in ticks: tN")
        return int(round((float(text[4:]) - 1) * 4 * 960000))
    probe.fail("position '%s' not understood" % text, "use bar:N (4/4) or tN (ticks, 960000 per quarter)")


def cmd_setclipmute(src, dst, *triples):
    """clip mute = byte 0 of the playlist entry 0x104F of the clip (hand session MIX_07 s14: 0 -> 1, nothing else);
    a fade entry starting at the same tick (the clip's fade-in) gets the same byte, as Pro Tools writes it on save (T66 j74).
    TRACK POS 0|1 [...]; POS = bar:N or tN (start of the clip on the playlist named TRACK).
    Example: setclipmute in.ptx out.ptx Au_m_T bar:9 1"""
    if not triples or len(triples) % 3:
        probe.fail("need TRACK POS VALUE triples", "usage: setclipmute <in> <out> TRACK bar:N|tN 0|1 [...]")
    dec = _decoder()
    raw, d, tree = descramble_file(src)
    edits = []
    for track, pos, val in zip(triples[::3], triples[1::3], triples[2::3]):
        pl = _playlist_block(d, tree, track)
        t = _pos(dec, d, tree, pos)
        hit, fds = [], []
        for e in probe.walk(pl["kids"]):
            if e["ct"] != 0x104F:
                continue
            o = e["pos"] + 9
            if (_epos(d, o)) == t:
                (hit if d[o + 15] == 3 else fds if d[o + 15] == 1 else []).append(o)
        if len(hit) != 1:
            probe.fail("%s: %d clips start at tick %d" % (track, len(hit), t), "ptx_decode: audio_placements lists the clip starts")
        v = 1 if str(val) in ("1", "true", "on") else 0
        print("%s clip at tick %d: muted %d -> %d (+ %d fade entries at the same start)" % (track, t, d[hit[0]], v, len(fds)))
        for o in hit + fds:                     # the clip's fade-in entry too: Pro Tools mutes it on save
            edits.append({"p": o, "ol": 1, "nb": bytes([v])})
    out = _splice2(d, tree, edits)
    write_new(dst, scramble(out))
    print("wrote %s (%d bytes)" % (dst, len(out)))


def _slot_auto(dec, d, tree, track, slot):
    """(slot block, automation list 0x2614) of a filled insert slot (multi-mono: its first instance)."""
    _, ch = _channel(dec, d, tree, track)
    lst = next((x for x in dec._subtree(ch) if x["ct"] == 0x2627), None)
    k = dec.SLOTS.index(slot) if slot in dec.SLOTS else -1
    if not lst or not 0 <= k < len(lst["kids"]) or lst["kids"][k]["ct"] not in (0x2616, 0x2617):
        probe.fail("slot %s of %s is empty or missing" % (slot, track), "slots a - j with a plug-in (ptx_decode: inserts)")
    s = lst["kids"][k]
    if s["ct"] == 0x2617 and s["kids"]:
        s = s["kids"][0]
    auto = next((x for x in s["kids"] if x["ct"] == 0x2614), None)
    if not auto:
        probe.fail("slot %s of %s has no automation list 0x2614" % (slot, track), "unknown slot layout; nothing written")
    return ch, s, auto


def _plug_lane_meta(pid, name=""):
    """Return (4-byte 0x260F metadata, discrete_steps_or_None) matching Pro Tools AAX parameter types."""
    if pid == "MasterBypassID" or name == "Master Bypass":
        return b"\x01\x00\x01\x02", 2
    pl, nl = pid.lower(), name.lower()
    if pl in ("process order", "sc filter type", "filter 1 type", "filter 2 type", "hpfs", "lpfs",
              "effect type", "mod type", "meter num", "meter den"):
        return b"\x00\x00\x01\x04", 4
    if pl == "sc source":
        return b"\x00\x00\x01\x03", 3
    if (pl.startswith("in ") or pl in ("phse", "hife", "lofe", "hprg", "lfrg", "hfrg", "lprg", "hirg", "lorg",
            "invert left", "invert right", "tempo sync", "note dot left", "note dot right",
            "note triplet left", "note triplet right", "eq low type", "eq high type",
            "sc detector type avg/pk", "mtrg", "ones", "mbck", "etrg")
            or any(t in nl for t in ("in/out", "on/off", "pre/post", "enable", "12/24db", "phase invert"))):
        return b"\x00\x00\x01\x02", 2
    return b"\x00\x01\x01\x00", None


def _plug_lane(tb, pts, steps=None):
    """plug-in lane data (0x260B): 01 46 01 00 | u32 L = 14 + 8 n | u16 time base | u32 n | u16 4 | u16 n - 1 | u64 first
    position (10^12 on tick lanes) + i32 value | (n - 1) x (u32 position, i32 value) | u16 0;
    continuous: (normalised - 0.5) x 2^31; discrete: raw integer 0..steps-1."""
    if steps is not None:
        enc = (lambda v: 1 if float(v) >= 0.5 else 0) if steps <= 2 else (lambda v: int(round(max(0.0, min(1.0, float(v))) * (steps - 1))))
    else:
        enc = lambda v: max(-2 ** 31, min(2 ** 31 - 1, int(round((float(v) - 0.5) * 2 ** 31))))
    first = 10 ** 12 if tb == 1 else 0
    body = struct.pack("<HIHH", tb, len(pts), 4, (len(pts) - 1) & 0xFFFF) + struct.pack("<Qi", first, enc(pts[0][1]))
    body += b"".join(struct.pack("<Ii", int(p), enc(v)) for p, v in pts[1:])
    return b"\x01\x46\x01\x00" + struct.pack("<I", len(body)) + body + b"\x00\x00"


def _blk(kind, ct, data):
    """one block: 5a | u8 kind | 00 | u32 size (content type + data) | u16 content type | data."""
    return bytes([0x5A, kind, 0]) + struct.pack("<I", 2 + len(data)) + struct.pack("<H", ct) + data


def cmd_addautolane(src, dst, track, slot, name, pid, pindex, start, tb=None):
    """enable automation of a plug-in parameter: one entry 0x260F (kind 2) appended to the slot's list 0x2614 (u32 count
    + 1), holding flag 1, a one-point lane 0x260B (kind 1) with the normalised START value, then u32 length + NAME, u32 PINDEX,
    00 01 01 00, u32 0, u32 length + PID (hand session MIX_07 s10 / s21: Pro Tools appends in the order of enabling).
    PINDEX = the plug-in's own parameter number (EQ3 7-Band: Output Level 5, Low Band Gain 13; Sci-Fi Input Level 1).
    Time base: the track's volume lane (ticks on tick tracks) unless tb=0|1 is given.
    Example: addautolane in.ptx out.ptx Au_m_S a "Low Band Gain" gai2 13 0.5"""
    dec = _decoder()
    raw, d, tree = descramble_file(src)
    ch, s, auto = _slot_auto(dec, d, tree, track, slot)
    for f in auto["kids"]:
        if f["ct"] == 0x260F and dec.plugin_lane_names(d, f)[1] == pid:
            probe.fail("%s slot %s: parameter %s is already automated" % (track, slot, pid), "use setpluglane to change its points")
    if tb is None:
        main, _ = _strips_of(ch)
        vol = next((k for k in main["kids"] if k["ct"] == 0x260A), None)
        tbv = struct.unpack_from("<H", d, vol["pos"] + 9 + 8)[0] if vol else 0
    else:
        tbv = int(str(tb).split("=")[-1])
    meta4, steps = _plug_lane_meta(pid, name)
    lane = _blk(1, 0x260B, _plug_lane(tbv, [(0, start)], steps=steps))
    nb, ib = name.encode("latin-1"), pid.encode("latin-1")
    tail = struct.pack("<I", len(nb)) + nb + struct.pack("<I", int(pindex)) + meta4 + struct.pack("<I", 0) + struct.pack("<I", len(ib)) + ib
    entry = _blk(2, 0x260F, b"\x01" + lane + tail)
    cnt = struct.unpack_from("<I", d, auto["pos"] + 9)[0]
    if cnt != sum(1 for k in auto["kids"] if k["ct"] == 0x260F):
        probe.fail("0x2614 count %d does not match its entries" % cnt, "unknown layout; nothing written")
    end_a = auto["pos"] + 7 + auto["size"]
    edits = [{"p": auto["pos"] + 9, "ol": 4, "nb": struct.pack("<I", cnt + 1)},
             {"p": end_a, "ol": 0, "nb": entry, "enc": auto["pos"]}]
    print("%s slot %s: automation %d -> %d entries, + %s (%s, #%s), start %s, time base %d" % (track, slot, cnt, cnt + 1, name, pid, pindex, start, tbv))
    out = _splice2(d, tree, edits)
    write_new(dst, scramble(out))
    print("wrote %s (%d bytes)" % (dst, len(out)))


def cmd_setpluglane(src, dst, track, slot, pid, text):
    """points of an automated plug-in parameter (lane 0x260B under the 0x260F whose id is PID): POS:VALUE,... with
    normalised values 0..1; the first point must be at 0; positions in the lane's time base (ticks: 960 000 per quarter).
    Example: setpluglane in.ptx out.ptx Au_m_S a outp 0:0.769231,3840000:0.769231,11520000:0.6536"""
    dec = _decoder()
    raw, d, tree = descramble_file(src)
    ch, s, auto = _slot_auto(dec, d, tree, track, slot)
    f = next((f for f in auto["kids"] if f["ct"] == 0x260F and dec.plugin_lane_names(d, f)[1] == pid), None)
    lane = next((k for k in f["kids"] if k["ct"] == 0x260B), None) if f else None
    if not lane:
        probe.fail("%s slot %s: parameter %s is not automated" % (track, slot, pid), "addautolane first")
    s0 = lane["pos"] + 9
    if d[s0:s0 + 4] != b"\x01\x46\x01\x00":
        probe.fail("unknown plug-in lane layout", "nothing written")
    tb = struct.unpack_from("<H", d, s0 + 8)[0]
    pts = [(int(a), float(b)) for a, b in (x.split(":") for x in text.split(","))]
    if pts[0][0] != 0:
        probe.fail("the first point must be at 0", "write 0:<value> first")
    steps = dec._plugin_lane_steps(d, f) if hasattr(dec, "_plugin_lane_steps") else _plug_lane_meta(pid)[1]
    new = _plug_lane(tb, pts, steps=steps)
    old_len = 8 + struct.unpack_from("<I", d, s0 + 4)[0] + 2
    edits = [{"p": s0, "ol": old_len, "nb": new}]
    print("%s slot %s %s: %d points %s" % (track, slot, pid, len(pts), pts))
    out = _splice2(d, tree, edits)
    write_new(dst, scramble(out))
    print("wrote %s (%d bytes)" % (dst, len(out)))


def _io_path(d, tree, name):
    """(path number, 8-byte id, path type) of the I/O path NAME: position in the first I/O table 0x1022 > 0x1021 (MIX_07 s09 / s15:
    the aux input and the send store this number; FX1 = 6), the 8 bytes after the tag 2a 00 00 00 of its entry and its first
    byte (type: 0 hardware input, 1 / 2 output and bus entries; FX1 = 2)."""
    tab = next((n for n in probe.walk(tree) if n["ct"] == 0x1022), None)
    if not tab:                                                                # clean-room session (no I/O database yet): the path list 0x2603
        io, paths = _io_paths(bytes(d), tree)
        hit = [(i, p) for i, p in enumerate(paths) if p[1] == name and p[5]]
        if len(hit) != 1:
            probe.fail("path '%s' not found in the I/O setup 0x2603 (no I/O table 0x1022)" % name, "create the bus first: addbus")
        return hit[0][0] + 2, hit[0][1][5], 2
    names = []
    for i, k in enumerate(tab["kids"]):
        o = k["pos"] + 9
        n = struct.unpack_from("<I", d, o + 2)[0]
        nm = d[o + 6:o + 6 + n].decode("utf-8", "replace") if n < 128 else "?"
        names.append(nm)
        if nm == name:
            j = d.find(b"\x2a\x00\x00\x00", o + 6 + n, k["pos"] + 7 + k["size"])
            if j < 0:
                probe.fail("I/O entry %s has no id" % name, "unknown layout; nothing written")
            return i, bytes(d[j + 4:j + 12]), d[o]
    probe.fail("I/O path '%s' not found" % name, "paths: %s" % names)


def cmd_setinput(src, dst, track, path_name):
    """input of a track (aux: bus input) = u16 path number one byte after the track info 0x102D inside the box 0x261B
    (0xffff = none) plus the input record in the box's own data: u32 length + name, u32 0, u32 0x2a (0 when empty), 8-byte id of
    the path, 00, path type (first byte of its I/O entry; 0 when empty) (hand session MIX_07 s09; the name follows the bus
    name, s15). PATH_NAME = bus / input name, or '-' for none.
    Example: setinput in.ptx out.ptx Aux_m FX1"""
    dec = _decoder()
    raw, d, tree = descramble_file(src)
    _, ch = _channel(dec, d, tree, track)
    box = next((x for x in ch["kids"] if x["ct"] == 0x261B), None)
    if not box or not box["kids"] or box["kids"][0]["ct"] != 0x102D:
        probe.fail("track %s has no box 0x261B with track info" % track, "unknown layout; nothing written")
    pp = probe_end_(box["kids"][0]) + 1
    gaps, prev = [], box["pos"] + 9
    for k in box["kids"]:
        gaps.append((prev, k["pos"]))
        prev = k["pos"] + 7 + k["size"]
    gaps.append((prev, box["pos"] + 7 + box["size"]))
    rec = []
    for a, b in gaps:
        for m_ in re.finditer(re.escape(b"\x00\x00\x00\x00\x08\x00\x00\x00\x00"), d[a:b]):
            q = a + m_.end()
            n = struct.unpack_from("<I", d, q)[0] if q + 4 <= b else 999
            if n <= 64 and q + 4 + n + 16 <= b and d[q + 4 + n:q + 8 + n] == b"\x00\x00\x00\x00" and d[q + 8 + n:q + 12 + n] in (b"\x00\x00\x00\x00", b"\x2a\x00\x00\x00"):
                rec.append((q, n))
    if len(rec) != 1:
        probe.fail("%s: %d input records found" % (track, len(rec)), "unknown layout; nothing written")
    q, n = rec[0]
    if path_name == "-":
        num, new = 0xFFFF, struct.pack("<I", 0) + b"\x00" * 16
    else:
        num, pid, ptype = _io_path(d, tree, path_name)
        nb = path_name.encode("utf-8")
        new = struct.pack("<I", len(nb)) + nb + b"\x00\x00\x00\x00" + b"\x2a\x00\x00\x00" + pid
    old = struct.unpack_from("<H", d, pp)[0]
    edits = [{"p": pp, "ol": 2, "nb": struct.pack("<H", num)}, {"p": q, "ol": 4 + n + 16, "nb": new}]
    t_at = q + 4 + n + 16 + 1                                     # byte after the id + 1: path type (s09: 2 for the bus, 0 when empty)
    edits.append({"p": t_at, "ol": 1, "nb": bytes([0 if path_name == "-" else ptype])})
    print("%s input: path %s -> %s, name %r -> %r" % (track, old, num, d[q + 4:q + 4 + n].decode("latin-1"), path_name))
    out = _splice2(d, tree, edits)
    write_new(dst, scramble(out))
    print("wrote %s (%d bytes)" % (dst, len(out)))


def _path_entry(d, tree, name):
    """(u16 path number, 8-byte id, 16 bytes after the id (u32 0, tag, parent id), channel count) of the I/O path NAME:
    number from the I/O table 0x1022 > 0x1021, the rest from the path list 0x2603 > 0x2602 (entry: u8 2, u8 stereo, u32 + name,
    u32 channels, u16, u16, u16, ..., 2a 00 00 00 + id, u32 0, u32 tag 2a (0 on stereo paths) + parent id)."""
    num, pid, _ = _io_path(d, tree, name)
    lst = next((n for n in probe.walk(tree) if n["ct"] == 0x2603), None)
    for k in (lst["kids"] if lst else []):
        o = k["pos"] + 9
        n = struct.unpack_from("<I", d, o + 2)[0]
        if n < 128 and d[o + 6:o + 6 + n].decode("utf-8", "replace") == name:
            ch = struct.unpack_from("<I", d, o + 6 + n)[0]
            j = d.find(b"\x2a\x00\x00\x00" + pid, o, k["pos"] + 7 + k["size"])
            if j < 0:
                break
            return num, pid, bytes(d[j + 12:j + 28]), ch
    probe.fail("path '%s' not in the path list 0x2603" % name, "unknown layout; nothing written")


def cmd_setsendpath(src, dst, track, send, path_name):
    """destination of an existing send (send strip SEND = 1..10 in decoder order) = its output block 0x260E: u16 path
    number, 01, active, u32 0, 2a 00 00 00 + path id, the 16 bytes after the id in the path list (u32 0, tag, parent id), u32 +
    name, stem index (0 mono, 1 stereo), rest kept (hand session MIX_07 s08 / s15: send to FX1 = path 6, mono sub-path of Bus 1-2).
    Example: setsendpath in.ptx out.ptx Au_m_T 1 "Bus 2" """
    dec = _decoder()
    raw, d, tree = descramble_file(src)
    _, ch = _channel(dec, d, tree, track)
    main, sends = _strips_of(ch)
    k = int(send) - 1
    if not 0 <= k < len(sends):
        probe.fail("%s has %d sends" % (track, len(sends)), "send numbers start at 1 (ptx_decode: strips[].sends)")
    o = next((x for x in sends[k]["kids"] if x["ct"] == 0x260E), None)
    if not o:
        probe.fail("send %s of %s has no output block 0x260E" % (send, track), "unknown layout; nothing written")
    s0, e0 = o["pos"] + 9, o["pos"] + 7 + o["size"]
    if d[s0 + 8:s0 + 12] != b"\x2a\x00\x00\x00":
        probe.fail("send output block layout not recognised", "nothing written")
    n_old = struct.unpack_from("<I", d, s0 + 36)[0]
    if n_old > 128:
        probe.fail("send output name length %d" % n_old, "unknown layout; nothing written")
    num, pid, after, chn = _path_entry(d, tree, path_name)
    nb = path_name.encode("utf-8")
    new = struct.pack("<H", num) + bytes(d[s0 + 2:s0 + 4]) + b"\x00\x00\x00\x00" + b"\x2a\x00\x00\x00" + pid + after + struct.pack("<I", len(nb)) + nb + bytes([0 if chn == 1 else 1])
    old_len = 36 + 4 + n_old + 1
    print("%s send %s: path %d -> %d, %r -> %r (%d channel(s))" % (track, send, struct.unpack_from("<H", d, s0)[0], num,
          d[s0 + 40:s0 + 40 + n_old].decode("latin-1"), path_name, chn))
    out = _splice2(d, tree, [{"p": s0, "ol": old_len, "nb": new}])
    write_new(dst, scramble(out))
    print("wrote %s (%d bytes)" % (dst, len(out)))


def cmd_renamebus(src, dst, old, new):
    """rename an I/O path (bus) like the I/O setup does (hand session MIX_07 s15, Bus 1 -> FX1): every length-prefixed
    OLD becomes NEW (both I/O tables 0x1021, path list 0x2602, send outputs 0x260E, inputs 0x261B), EXCEPT the third text of an
    I/O table entry 0x1021 (Pro Tools keeps the default name there). One splice.
    Example: renamebus in.ptx out.ptx "Bus 1" FX1"""
    raw, d, tree = descramble_file(src)
    o, n = old.encode("utf-8"), new.encode("utf-8")
    if not 1 <= len(n) <= 60:
        probe.fail("new name has %d bytes" % len(n), "use 1..60 characters")
    hits = [m.start() for m in re.finditer(re.escape(o), d) if m.start() >= 4 and struct.unpack_from("<I", d, m.start() - 4)[0] == len(o)]
    keep = set()
    for e in probe.walk(tree):
        if e["ct"] != 0x1021:
            continue
        a, b = e["pos"] + 9, e["pos"] + 7 + e["size"]
        strs = probe.lp_strings(d, a, b, 1, 200)
        for k, (at, txt) in enumerate(strs):
            if k >= 2 and txt == old:
                keep.add(at + 4)
    use = [i for i in hits if i not in keep]
    if not use:
        probe.fail("bus '%s' not found" % old, "names are length-prefixed texts; ptx_decode lists sends / inputs")
    print("bus %r -> %r: %d texts renamed, %d default names kept (0x1021)" % (old, new, len(use), len(hits) - len(use)))
    out = _splice2(d, tree, [{"p": i - 4, "ol": 4 + len(o), "nb": struct.pack("<I", len(n)) + n} for i in use])
    write_new(dst, scramble(out))
    print("wrote %s (%d bytes)" % (dst, len(out)))


_REGION_MID = bytes.fromhex("0000000000000000803f0000803f0000000000000000ff")   # + clip id + 9 x 00 after each region
_REGION_META = bytes.fromhex("000001007f4d644368756e01004f0000004d644e4c4203001600000000000000000000000b00000000000000030012"
                             "000000000000004d64455301000f0000004d6454454c01000400000000000000000000002a000000")   # MIX_07 s18 / s19


def _minw(v):
    """smallest byte count that holds v (0 -> 0)."""
    n = 0
    while v >> (8 * n):
        n += 1
    return n


def _region_block(name, flag, vals, fileid, off, length, t0, tps, tail_flag, gidx, cid):
    """one audio region 0x2628 (kind 5) built from its fields (hand session MIX_07 s19):
    u32 + name | flag | 3 bytes: width nibbles of W1 .. W4 (high nibbles of bytes 1 - 3, low nibble of byte 3) | 08 (extension)
    | W1 .. W4 little endian in their widths | ff x 8 | fe ff 00 01 | 0x2636 (kind 1): file id (16) + lane 01 46 01 00, u32 38,
    00 01 02 00 00 00 08 00 01 00, u64 offset, u64 10^12 + start tick, u32 length, u64 10^12 + end tick | 00 00 ff ff 04 00 04 00,
    20 x 00, flag byte, u32 clip-gain index, 00 00 | 16-byte clip id. W = (offset, length, offset, time stamp + offset), or
    (0, length, time stamp, 0) for a region that starts at the file start."""
    nb = name.encode("utf-8")
    w = [_minw(v) for v in vals]
    head = struct.pack("<I", len(nb)) + nb + bytes([flag, w[0] << 4, w[1] << 4, (w[2] << 4) | w[3], 8])
    head += b"".join(v.to_bytes(k, "little") for v, k in zip(vals, w) if k)
    head += b"\xff" * 8 + b"\xfe\xff\x00\x01"
    lane = b"\x00\x01\x02\x00\x00\x00\x08\x00\x01\x00" + struct.pack("<QQIQ", off, 10 ** 12 + int(round(off * tps)), length, 10 ** 12 + int(round((off + length) * tps)))
    wave = _blk(1, 0x2636, fileid + b"\x01\x46\x01\x00" + struct.pack("<I", len(lane)) + lane)
    tail = b"\x00\x00\xff\xff\x04\x00\x04\x00" + b"\x00" * 20 + bytes([tail_flag]) + struct.pack("<I", gidx) + b"\x00\x00" + cid
    return _blk(5, 0x2628, head + wave + tail)


def cmd_splitclip(src, dst, track, pos, at):
    """split the clip that starts at POS on the playlist TRACK at the timeline position AT (bar:N or tN): two new
    regions (names <base>-NN with the next free numbers, new clip ids, the source's clip-gain index = shared gain, as Pro Tools does)
    appended to the region list 0x262A (wrapper 0x2629 = region + 0x4403 > 0x1000); the clip's playlist entry points to the first
    part, a new entry for the second part follows it (0x1052 count + 1). Hand session MIX_07 s19 (bar 41 split at bar 44).
    Example: splitclip in.ptx out.ptx Au_m_T bar:41 bar:44"""
    import uuid
    dec = _decoder()
    raw, d, tree = descramble_file(src)
    pl = _playlist_block(d, tree, track)
    t_pos, t_at = _pos(dec, d, tree, pos), _pos(dec, d, tree, at)
    ent = None
    for e in pl["kids"]:
        if e["ct"] != 0x1050 or not e["kids"] or e["kids"][0]["ct"] != 0x104F:
            continue
        o = e["kids"][0]["pos"] + 9
        if d[o + 15] == 3 and _epos(d, o) == t_pos:
            ent = e
    if not ent:
        probe.fail("%s: no clip starts at tick %d" % (track, t_pos), "ptx_decode: audio_placements")
    o = ent["kids"][0]["pos"] + 9
    ridx = struct.unpack_from("<H", d, o + 2)[0]
    lst = next((n for n in probe.walk(tree) if n["ct"] == 0x262A), None)
    wraps = [k for k in lst["kids"] if k["ct"] == 0x2629] if lst else []
    if ridx >= len(wraps) or struct.unpack_from("<I", d, lst["pos"] + 9)[0] != len(wraps):
        probe.fail("region list 0x262A does not match (index %d of %d)" % (ridx, len(wraps)), "unknown layout; nothing written")
    reg = next(k for k in wraps[ridx]["kids"] if k["ct"] == 0x2628)
    rp, re_ = reg["pos"] + 9, reg["pos"] + 7 + reg["size"]
    n = struct.unpack_from("<I", d, rp)[0]
    name = d[rp + 4:rp + 4 + n].decode("utf-8")
    q = rp + 4 + n
    flag, b1, b2, b3, ex = d[q:q + 5]
    w = [b1 >> 4, b2 >> 4, b3 >> 4, b3 & 15]
    sync_w = b2 & 15
    k = q + 5
    vals = [int.from_bytes(d[k:k + w[0]], "little") if w[0] else 0]
    k += w[0] + sync_w
    for x in w[1:]:
        vals.append(int.from_bytes(d[k:k + x], "little") if x else 0)
        k += x
    wave = next((c for c in reg["kids"] if c["ct"] == 0x2636), None)
    src_r = bytes(d[reg["pos"]:re_])
    strict = ex == 8 and d[k:k + 12] == b"\xff" * 8 + b"\xfe\xff\x00\x01" and wave is not None and src_r[1] == 5
    tail = d[wave["pos"] + 7 + wave["size"]:re_] if wave else d[k + (8 if ex == 8 else 0) + 4:re_]
    if wave:
        wv = d[wave["pos"] + 9:wave["pos"] + 7 + wave["size"]]
        fileid = wv[:16]
        off, st_t, length, en_t = struct.unpack_from("<QQIQ", wv, 16 + 8 + 10)
        tps = (en_t - st_t) / length
    else:                                                                   # record without waveform block (G2)
        fileid, off, length, tps = None, vals[0], vals[1], None
    if d[o + 14] == 0x40 and tps is None:                                  # ticks per sample from another region's waveform
        for w_ in wraps:                                                    # block (constant tempo only)
            for c_ in w_["kids"]:
                ww = next((g_ for g_ in c_["kids"] if g_["ct"] == 0x2636), None) if c_["ct"] == 0x2628 else None
                if ww and tps is None:
                    _o, st2, ln2, en2 = struct.unpack_from("<QQIQ", d, ww["pos"] + 9 + 16 + 8 + 10)
                    tps = (en2 - st2) / ln2 if ln2 else None
        tm = dec.tempo(d, tree, [], 1) or dec.tempo(d, tree, [])
        fm = dec.session_format(d, tree)
        if tps is None and len(tm) == 1 and fm.get("sample_rate"):           # constant tempo + sample rate of 0x1028
            tps = 960000.0 * tm[0]["bpm"] / 60.0 / fm["sample_rate"]
        if tps is None or len(tm) > 1:
            probe.fail("region %s has no waveform block, the playlist counts ticks and the tempo is not constant" % name,
                       "generality gap: ticks per sample unknown here")
    step = tps if d[o + 14] == 0x40 else 1.0                                # sample-based playlists count samples
    ts = vals[2] if vals[0] == 0 else vals[3] - vals[0]
    if strict:
        tail_flag, gidx = tail[28], struct.unpack_from("<I", tail, 29)[0]
        # check: the documented layout rebuilds the source region exactly
        if _region_block(name, flag, vals, fileid, off, length, 0, tps, tail_flag, gidx, tail[-16:]) != src_r:
            strict = False
    if not strict:                                                          # generic path (G2 / G4): fields edited in a copy
        gidx = None                                                         # of the source record; checked by rebuilding the source
        def rebuild(nm, v, po, pl_, cid):
            nb_ = nm.encode("utf-8")
            wd = [_minw(x) for x in v]
            body = struct.pack("<I", len(nb_)) + nb_ + bytes([flag, (b1 & 15) | (wd[0] << 4), (b2 & 15) | (wd[1] << 4), (wd[2] << 4) | wd[3], ex])
            body += b"".join(x.to_bytes(c_, "little") for x, c_ in zip(v, wd) if c_)
            mid_ = d[k:(wave["pos"] if wave else k + (8 if ex == 8 else 0) + 4)]
            wb = b""
            if wave:
                lane = bytearray(d[wave["pos"]:wave["pos"] + 7 + wave["size"]])
                struct.pack_into("<QQIQ", lane, 9 + 16 + 8 + 10, po, 10 ** 12 + int(round(po * tps)), pl_, 10 ** 12 + int(round((po + pl_) * tps)))
                wb = bytes(lane)
            tl = bytes(tail)
            if src_r[1] == 5 and cid is not None:
                tl = tl[:-16] + cid
            data = body + mid_ + wb + tl
            return bytes([0x5A, src_r[1], src_r[2]]) + struct.pack("<I", 2 + len(data)) + src_r[7:9] + data
        if rebuild(name, vals, off, length, src_r[-16:] if src_r[1] == 5 else None) != src_r:
            probe.fail("region %s does not match the documented layout (generic check failed too)" % name, "unknown region layout; nothing written")
        print("region %s: generic record path (kind %d, extension %s, waveform block %s)" % (name, src_r[1], ex == 8, bool(wave)))
    fe = _fadein_end(d, tree, pl, t_pos, step)
    if fe and t_at <= fe:
        probe.fail("cut at tick %d lies inside or at the end of the clip's fade-in (ends at tick %d)" % (t_at, fe),
                   "Pro Tools refuses this cut (Separate greyed out); cut after the fade-in")
    a = (t_at - t_pos) / step
    if abs(a - round(a)) < 0.5 and d[o + 14] == 0x40:                         # tick cut between two samples -> nearest sample
        a = float(round(a))
    if a != int(a) or not 0 < a < length:
        probe.fail("cut at tick %d is not inside the clip (%d samples) or not on a sample" % (t_at, length), "positions in ticks: 960000 per quarter")
    a = int(a)
    base = re.sub(r"-\d+$", "", name)
    used = [int(m_.group(1)) for k_ in wraps for c in k_["kids"] if c["ct"] == 0x2628
            for m_ in [re.match(re.escape(base) + rb"-(\d+)$".decode(), d[c["pos"] + 13:c["pos"] + 13 + struct.unpack_from("<I", d, c["pos"] + 9)[0]].decode("utf-8", "replace"))] if m_]
    nxt = max(used + [0]) + 1
    parts = [(off, a), (off + a, length - a)]
    # every wrapper ends with a metadata chunk (MdChun / MdNLB / MdES / MdTEL) and an 8-byte id: u32 session part +
    # u32 counter; new ids continue the highest counter of that session part in the file
    w0 = wraps[0]
    gap0 = d[w0["kids"][-1]["pos"] + 7 + w0["kids"][-1]["size"]:w0["pos"] + 7 + w0["size"]]
    if strict and (not gap0.startswith(_REGION_META) or len(gap0) != len(_REGION_META) + 17):
        probe.fail("region wrapper metadata differs from the documented constant", "unknown layout; nothing written")
    hi_ = gap0[len(_REGION_META):len(_REGION_META) + 4]
    src_w = d[wraps[ridx]["pos"]:wraps[ridx]["pos"] + 7 + wraps[ridx]["size"]]
    mid = d[re_:re_ + 48]
    if strict and mid != _REGION_MID + tail[-16:] + b"\x00" * 9:
        probe.fail("region wrapper: the 48 bytes after the region differ from the documented layout", "unknown layout; nothing written")
    if strict:
        ctr = max(struct.unpack_from("<I", d, m_.end())[0] for m_ in re.finditer(re.escape(b"\x2a\x00\x00\x00" + hi_), d))
    nid = lambda j: hi_ + struct.pack("<I", ctr + 1 + j)
    blocks = []
    if not strict:                                                          # generic wrapper: the source wrapper's bytes after
        sw = wraps[ridx]                                                    # the region, its clip id replaced, metadata counter bumped
        rest = bytes(d[re_:sw["pos"] + 7 + sw["size"]])
        old_cid = src_r[-16:] if src_r[1] == 5 else None
        m_ = re.search(re.escape(b"\x2a\x00\x00\x00") + b"(.{4})(.{4})\x01\x00{8}$", rest, re.S)
        ctr = None
        if m_:
            ctr = max(struct.unpack_from("<I", d, x_.end())[0] for x_ in re.finditer(re.escape(b"\x2a\x00\x00\x00" + m_.group(1)), d))
        for j, (po, pl_) in enumerate(parts):
            nm = "%s-%02d" % (base, nxt + j)
            v = [0, pl_, ts, 0] if po == 0 else [po, pl_, po, ts + po]
            cid = _rnd(16)
            rb_ = rebuild(nm, v, po, pl_, cid if old_cid else None)
            rs = rest.replace(old_cid, cid) if old_cid else rest
            if m_:
                rs = rs[:m_.start(2)] + struct.pack("<I", ctr + 1 + j) + rs[m_.end(2):]
            blocks.append(bytes([0x5A, d[sw["pos"] + 1], d[sw["pos"] + 2]]) + struct.pack("<I", 2 + len(rb_) + len(rs)) + d[sw["pos"] + 7:sw["pos"] + 9] + rb_ + rs)
            print("new region %s: offset %d, length %d (generic path)" % (nm, po, pl_))
    for j, (po, pl_) in enumerate(parts if strict else []):
        nm = "%s-%02d" % (base, nxt + j)
        v = [0, pl_, ts, 0] if po == 0 else [po, pl_, po, ts + po]
        cid = _rnd(16)
        reg_b = _region_block(nm, flag, v, fileid, po, pl_, 0, tps, tail_flag, gidx, cid)
        blocks.append(_blk(0x0B, 0x2629, reg_b + _REGION_MID + cid + b"\x00" * 9 + _blk(1, 0x4403, _blk(0, 0x1000, b"\x00" * 18) + b"\x00") + _REGION_META + nid(j) + b"\x01" + b"\x00" * 8))
        print("new region %s: offset %d, length %d (clip-gain entry %d shared)" % (nm, po, pl_, gidx))
    sample_4403 = next((c for c in wraps[0]["kids"] if c["ct"] == 0x4403), None)
    if strict and sample_4403 and d[sample_4403["pos"]:sample_4403["pos"] + 7 + sample_4403["size"]] != _blk(1, 0x4403, _blk(0, 0x1000, b"\x00" * 18) + b"\x00"):
        probe.fail("region wrapper 0x4403 differs from the documented constant", "unknown layout; nothing written")
    i_a, i_b = len(wraps), len(wraps) + 1
    ebytes = d[ent["pos"]:ent["pos"] + 7 + ent["size"]]
    eo = ent["kids"][0]["pos"] - ent["pos"] + 9
    ea = bytearray(ebytes)
    struct.pack_into("<H", ea, eo + 2, i_a)
    eb = bytearray(ebytes)
    struct.pack_into("<H", eb, eo + 2, i_b)
    eb[eo + 7:eo + 12] = _epos_bytes(eb, eo, t_at)
    pn = struct.unpack_from("<I", d, pl["pos"] + 9)[0]
    cnt_at = pl["pos"] + 9 + 4 + pn
    end_l = lst["pos"] + 7 + lst["size"]
    edits = [{"p": ent["pos"], "ol": len(ebytes), "nb": bytes(ea) + bytes(eb)},
             {"p": cnt_at, "ol": 4, "nb": struct.pack("<I", struct.unpack_from("<I", d, cnt_at)[0] + 1)},
             {"p": lst["pos"] + 9, "ol": 4, "nb": struct.pack("<I", len(wraps) + 2)},
             {"p": end_l, "ol": 0, "nb": b"".join(blocks), "enc": lst["pos"]}]
    print("%s: clip %s at tick %d split at tick %d (%d + %d samples)" % (track, name, t_pos, t_at, a, length - a))
    out = _splice2(d, tree, edits)
    write_new(dst, scramble(out))
    print("wrote %s (%d bytes)" % (dst, len(out)))


def cmd_addfade(src, dst, track, pos, length, kind, slope, *opts):
    """fade object + its playlist entry (sync-point aware, chronological splice).
    Options for crossfade: center=1 (50/50 pre/post cut, 34 B native 0x262F) or pre=<samples>.
    KIND = crossfade | fade_in | fade_out, SLOPE = equal_power | equal_gain."""
    types, slopes = {"crossfade": 1, "fade_in": 3, "fade_out": 2}, {"equal_power": 1, "equal_gain": 2}
    if kind not in types or slope not in slopes:
        probe.fail("kind %s / slope %s unknown" % (kind, slope), "kind crossfade | fade_in | fade_out, slope equal_power | equal_gain")
    o_map = dict(x.split("=", 1) for x in opts if "=" in x)
    if set(o_map) - {"center", "pre"} or len(o_map) != len(opts):
        probe.fail("unknown option in %s" % list(opts), "use [center=1|0] [pre=<samples>]")
    flen = int(length)
    if flen <= 0:
        probe.fail("fade length must be positive (got %d)" % flen, "pass fade length in samples")
    pre = 0
    if kind == "crossfade":
        if "pre" in o_map:
            pre = int(o_map["pre"])
            if not (0 <= pre < flen):
                probe.fail("crossfade pre=%d must satisfy 0 <= pre < length (%d)" % (pre, flen), "adjust pre=<samples>")
        elif str(o_map.get("center", "0")).strip().lower() in ("1", "true", "yes"):
            pre = flen // 2
    dec = _decoder()
    raw, d, tree = descramble_file(src)
    d = bytes(d)
    pls = _playlist_blocks(d, tree, track)
    t = _pos(dec, d, tree, pos)
    fl = next((n for n in probe.walk(tree) if n["ct"] == 0x2630), None)
    if not fl or struct.unpack_from("<I", d, fl["pos"] + 9)[0] != sum(1 for k in fl["kids"] if k["ct"] == 0x262F):
        probe.fail("fade list 0x2630 missing or its count does not match", "unknown layout; nothing written")
    n_f = sum(1 for k in fl["kids"] if k["ct"] == 0x262F)
    lst_ = next((n for n in probe.walk(tree) if n["ct"] == 0x262A), None)
    wraps_ = [k for k in lst_["kids"] if k["ct"] == 0x2629] if lst_ else []
    res_ = dec.decode(src)
    tempo_ = res_.get("tempo_used") or [{"ticks": 0, "bpm": 120.0}]
    rate_ = (res_.get("format") or {}).get("sample_rate") or 48000
    clips = []
    for pl in pls:
        clip, span = _find_clip_at(dec, d, tree, wraps_, pl, t, tempo_, rate_)
        if clip:
            clips.append((pl, clip, span))
    if not clips:
        probe.fail("%s: no clip starts at %d" % (track, t), "a fade is placed on a clip starting at POS (crossfade: clip after the cut)")
    if kind == "crossfade":                                                   # the clip before the cut must not fade in across it
        for pl, _clip, span in clips:
            c_start = span[2]
            prev = []
            for e in pl["kids"]:
                if e["ct"] == 0x1050 and e["kids"] and e["kids"][0]["ct"] == 0x104F:
                    eo = e["kids"][0]["pos"] + 9
                    if d[eo + 15] in (2, 3) and d[e["pos"] + 7 + e["size"] - 3] == 0:
                        sp_ = _clip_span_and_sync(dec, d, tree, wraps_, eo, tempo_, rate_)
                        if sp_[2] is not None and sp_[2] < c_start:
                            prev.append((sp_[2], sp_[1] if d[eo + 14] == 0x40 else 1.0))
            if prev:
                prev_start, w_tps = max(prev, key=lambda x: x[0])
                fe = _fadein_end(d, tree, pl, prev_start, w_tps)
                if fe and fe >= c_start:
                    probe.fail("the fade-in of the clip before the cut ends at %d, crossfade starts at %d" % (fe, c_start),
                               "Pro Tools drops a fade-in that reaches a crossfade on save (SONG_04 j81); cut later or shorten fade-in")
    if kind == "fade_out":
        w_ = 1 if flen < 256 else 2 if flen < 65536 else 3
        own = b"\x00" * 5 + bytes([(w_ << 4) | w_]) + b"\x00\x00" + flen.to_bytes(w_, "little") * 2 + bytes([2, slopes[slope]]) + b"\x00" * 13
    elif kind == "crossfade" and pre > 0:
        w1 = max(2, _minw(pre))
        w2 = max(2, _minw(flen))
        own = b"\x00" * 5 + bytes([(w1 << 4) | w2]) + b"\x00\x00" + pre.to_bytes(w1, "little") + flen.to_bytes(w2, "little") + bytes([1, slopes[slope]]) + b"\x00" * 20
    else:
        own = b"\x00\x00\x00\x00\x00\x30\x00\x00" + flen.to_bytes(3, "little") + bytes([types[kind], slopes[slope]]) + b"\x00" * 10
        if kind == "crossfade":
            own += b"\x00" * 10
    fades_b = []
    edits = []
    for ci, (pl, clip, span) in enumerate(clips):
        ln_, _wtps, c_start, _c_anchor, c_end, _soff = span
        eo = clip["kids"][0]["pos"] + 9
        is_tick = d[eo + 14] == 0x40
        if kind == "fade_out":
            if any(k["ct"] == 0x242B for k in clip["kids"]):
                probe.fail("clip at %d on '%s' has a clip loop (0x242B)" % (c_start, track),
                           "Pro Tools drops fade-out on looped clips during SaveSessionAs; place fade-out on an unlooped clip")
            if flen > ln_:
                probe.fail("fade-out of %d samples is longer than the clip (%d)" % (flen, ln_), "use a shorter fade")
            f_pos = c_end
        else:
            post_len = (flen - pre) if (kind == "crossfade" and pre > 0) else flen
            if post_len > ln_:
                probe.fail("%s length (%d) exceeds clip length (%d)" % (kind, post_len, ln_), "use a shorter fade")
            f_pos = c_start
        f_idx = n_f + ci
        fades_b.append(_blk(2, 0x262F, own))
        fade_1050 = _playlist_entry(f_idx, f_pos, ticks=1 if is_tick else 0, kind=(3 if kind == "fade_out" else 1), k2=b"\xfe\xff", tail=b"\x01\x01\x01")
        ents_raw = [d[k["pos"]:k["pos"] + 7 + k["size"]] for k in pl["kids"] if k["ct"] == 0x1050]
        ents_raw.append(bytes(fade_1050))
        edits.append(_splice_playlist_entries(d, pl, ents_raw))
    edits.insert(0, {"p": fl["pos"] + 9, "ol": 4, "nb": struct.pack("<I", n_f + len(clips))})
    edits.insert(1, {"p": fl["pos"] + 7 + fl["size"], "ol": 0, "nb": b"".join(fades_b), "enc": fl["pos"]})
    print("%s: %s %s, %d samples, at %d (fade %d)" % (track, kind, slope, flen, t, n_f))
    out = _splice2(d, tree, edits)
    write_new(dst, scramble(out))
    print("wrote %s (%d bytes)" % (dst, len(out)))


def _entries(d, pl):
    """playlist entries of 0x1052: [(0x1050 block, own position of its 0x104F, kind, index, tick)]."""
    out = []
    for e in pl["kids"]:
        if e["ct"] == 0x1050 and e["kids"] and e["kids"][0]["ct"] == 0x104F:
            o = e["kids"][0]["pos"] + 9
            out.append((e, o, d[o + 15], struct.unpack_from("<H", d, o + 2)[0], _epos(d, o)))
    return out


def _fadein_end(d, tree, pl, clip_tick, tps):
    """end position of fade-in/crossfade entries starting at CLIP_TICK (handles compact 0x20 and centered varint 0x262F)."""
    fl = next((n for n in probe.walk(tree) if n["ct"] == 0x2630), None)
    fades = [k for k in fl["kids"] if k["ct"] == 0x262F] if fl else []
    end = 0
    for e, o, kd, idx, tk in _entries(d, pl):
        if kd == 1 and tk == clip_tick and idx < len(fades):
            fb = fades[idx]
            f0 = fb["pos"] + 9
            fend = fb["pos"] + 7 + fb["size"]
            if f0 + 8 >= fend:
                continue
            b5 = d[f0 + 5]
            w1, w2 = b5 >> 4, b5 & 15
            ft_off = f0 + 8 + w1 + w2
            if ft_off >= fend:
                continue
            v1 = int.from_bytes(d[f0 + 8:f0 + 8 + w1], "little") if w1 else 0
            v2 = int.from_bytes(d[f0 + 8 + w1:f0 + 8 + w1 + w2], "little") if w2 else 0
            ftype = d[ft_off]
            if ftype == 3:
                end = max(end, clip_tick + int(round(v1 * tps)))
            elif ftype == 1:
                post = (v2 - v1) if w2 else v1
                end = max(end, clip_tick + int(round(post * tps)))
    return end


def cmd_placeclip(src, dst, track, from_pos, to_pos):
    """place the clip that starts at FROM again at TO on the same playlist (Copy / Paste of MIX_07 s18): the new entry
    uses the SAME region (no new region; a shared region shares its clip gain), a fade entry starting with the clip is placed
    with it (same fade object); entries stay in time order (0x1052 count + n).
    Example: placeclip in.ptx out.ptx Au_m_T bar:1 bar:41"""
    dec = _decoder()
    raw, d, tree = descramble_file(src)
    pl = _playlist_block(d, tree, track)
    tf, tt = _pos(dec, d, tree, from_pos), _pos(dec, d, tree, to_pos)
    ents = _entries(d, pl)
    src_e = [x for x in ents if x[4] == tf and x[2] in (1, 3)]
    if not any(x[2] == 3 for x in src_e):
        probe.fail("%s: no clip starts at tick %d" % (track, tf), "ptx_decode: audio_placements")
    if any(x[4] == tt for x in ents):
        probe.fail("%s: an entry already starts at tick %d" % (track, tt), "pick a free position (overlaps are not written)")
    nb = b""
    for e, o, kd, idx, tk in src_e:
        b_ = bytearray(d[e["pos"]:e["pos"] + 7 + e["size"]])
        eo = o - e["pos"]
        b_[eo + 7:eo + 12] = _epos_bytes(b_, eo, tt)
        nb += bytes(b_)
    after = next((x for x in ents if x[4] > tt), None)
    last = ents[-1][0] if ents else None                                     # 0x1052 keeps 2 own bytes after its entries
    at = after[0]["pos"] if after else (last["pos"] + 7 + last["size"] if last else pl["pos"] + 7 + pl["size"])
    pn = struct.unpack_from("<I", d, pl["pos"] + 9)[0]
    cnt_at = pl["pos"] + 9 + 4 + pn
    edits = [{"p": at, "ol": 0, "nb": nb, "enc": pl["pos"]},
             {"p": cnt_at, "ol": 4, "nb": struct.pack("<I", struct.unpack_from("<I", d, cnt_at)[0] + len(src_e))}]
    print("%s: %d entr%s from tick %d placed at tick %d" % (track, len(src_e), "y" if len(src_e) == 1 else "ies", tf, tt))
    out = _splice2(d, tree, edits)
    write_new(dst, scramble(out))
    print("wrote %s (%d bytes)" % (dst, len(out)))


def cmd_setclipgainat(src, dst, track, pos, db):
    """clip gain of ONE clip (the clip starting at POS on the playlist TRACK) with Pro Tools' copy-on-write rule
    (MIX_07 s12 / s13 / s18): the clip's region holds the index of its entry in 0x2637 (u32 22 bytes before the end of 0x2628).
    Entry used by this region only and region used by this clip only -> value changed in place. Entry shared with other regions ->
    a new one-point entry is appended (count + 1) and the region points to it. Region shared with other clips -> a new region
    (next free name, new clip id, the new entry) is appended to 0x262A and the clip entry points to it.
    Example: setclipgainat in.ptx out.ptx Au_m_T bar:1 -4"""
    import uuid
    dec = _decoder()
    raw, d, tree = descramble_file(src)
    pl = _playlist_block(d, tree, track)
    t = _pos(dec, d, tree, pos)
    ents = _entries(d, pl)
    me = next((x for x in ents if x[2] == 3 and x[4] == t), None)
    if not me:
        probe.fail("%s: no clip starts at tick %d" % (track, t), "ptx_decode: audio_placements")
    lst = next((n for n in probe.walk(tree) if n["ct"] == 0x262A), None)
    wraps = [k for k in lst["kids"] if k["ct"] == 0x2629]
    regs = [next(c for c in w_["kids"] if c["ct"] == 0x2628) for w_ in wraps]
    def gat(r):                                                             # tail found by search (record kinds 3 / 4 / 5)
        p = d.rfind(b"\x00\x00\xff\xff\x04\x00\x04\x00", r["pos"] + 9, r["pos"] + 7 + r["size"])
        if p < 0:
            probe.fail("region without the clip-gain tail", "this region version cannot take clip gain yet (generality gap G2)")
        return p + 29
    gidx = lambda r: struct.unpack_from("<I", d, gat(r))[0]
    ridx = me[3]
    r = regs[ridx]
    g = gidx(r)
    pool = next(n for n in probe.walk(tree) if n["ct"] == 0x2637)
    p0, pend = pool["pos"] + 9, pool["pos"] + 7 + pool["size"]
    starts, i = [], p0 + 4
    while i + 8 <= pend and d[i:i + 4] == b"\x01\x46\x01\x00":
        starts.append(i)
        i += 8 + struct.unpack_from("<I", d, i + 4)[0]
    if g == 0xFFFFFFFF:                                                    # region without clip gain yet (G3)
        g = None
    if struct.unpack_from("<I", d, p0)[0] != len(starts) or (g is not None and g >= len(starts)):
        probe.fail("clip-gain pool 0x2637 does not match (entry %d of %d)" % (g, len(starts)), "unknown layout; nothing written")
    clip_users = _region_use_counts(d, tree).get(ridx, 0)
    reg_users = sum(1 for rr in regs if gidx(rr) == g) if g is not None else 2      # none yet: always a new entry
    val = struct.pack("<f", float(db))
    edits = []
    if reg_users == 1 and clip_users == 1:
        s0 = starts[g]
        n = struct.unpack_from("<I", d, s0 + 10)[0]
        for k in range(n):
            edits.append({"p": s0 + 8 + 18 + 8 * k, "ol": 4, "nb": val})
        print("%s clip at tick %d: entry %d changed in place -> %s dB" % (track, t, g, db))
    else:
        newg = len(starts)
        entry = b"\x01\x46\x01\x00" + struct.pack("<I", 22) + struct.pack("<HIHHI", 0, 1, 4, 0, 0) + struct.pack("<I", 0) + val
        edits += [{"p": p0, "ol": 4, "nb": struct.pack("<I", newg + 1)}, {"p": pend, "ol": 0, "nb": entry, "enc": pool["pos"]}]
        if clip_users == 1:
            edits.append({"p": gat(r), "ol": 4, "nb": struct.pack("<I", newg)})
            print("%s clip at %d: entry %s shared by %d regions -> new entry %d (%s dB) for its region" % (track, t, "none" if g is None else g, reg_users, newg, db))
        else:
            rp = r["pos"] + 9
            n = struct.unpack_from("<I", d, rp)[0]
            name = d[rp + 4:rp + 4 + n].decode("utf-8")
            base = re.sub(r"-\d+$", "", name)
            used = []
            for rr in regs:
                nn = struct.unpack_from("<I", d, rr["pos"] + 9)[0]
                m_ = re.match(re.escape(base) + r"-(\d+)$", d[rr["pos"] + 13:rr["pos"] + 13 + nn].decode("utf-8", "replace"))
                if m_:
                    used.append(int(m_.group(1)))
            nm = "%s-%02d" % (base, max(used + [0]) + 1)
            w_ = wraps[ridx]
            wb = bytearray(d[w_["pos"]:w_["pos"] + 7 + w_["size"]])
            rb = bytes(d[r["pos"]:r["pos"] + 7 + r["size"]])
            k5 = rb[1] == 5                                                 # kinds 3 / 4 have no clip id at the end
            cid_old = rb[-16:] if k5 else None
            cid = _rnd(16)
            nb_ = name.encode("utf-8")
            gi = gat(r) - r["pos"]
            nm_b = nm.encode("utf-8")
            nrb = bytearray(rb[:9] + struct.pack("<I", len(nm_b)) + nm_b + rb[13 + len(nb_):])
            struct.pack_into("<I", nrb, 3, len(nrb) - 7)
            struct.pack_into("<I", nrb, gi + len(nm_b) - len(nb_), newg)
            if k5:
                nrb[-16:] = cid
            rest = bytes(wb[9 + len(rb):])
            if k5:
                rest = rest.replace(cid_old, cid)
            m2 = re.search(re.escape(b"\x2a\x00\x00\x00") + b"(.{4})(.{4})\x01\x00{8}$", rest, re.S)
            if m2:                                                          # metadata id: next counter of its session part
                ctr = max(struct.unpack_from("<I", d, x_.end())[0] for x_ in re.finditer(re.escape(b"\x2a\x00\x00\x00" + m2.group(1)), d))
                rest = rest[:m2.start(2)] + struct.pack("<I", ctr + 1) + rest[m2.end(2):]
            wrap = bytes([0x5A, wb[1], wb[2]]) + struct.pack("<I", 2 + len(nrb) + len(rest)) + bytes(wb[7:9]) + bytes(nrb) + rest
            ri_new = len(wraps)
            edits += [{"p": lst["pos"] + 9, "ol": 4, "nb": struct.pack("<I", ri_new + 1)},
                      {"p": lst["pos"] + 7 + lst["size"], "ol": 0, "nb": wrap, "enc": lst["pos"]},
                      {"p": me[1] + 2, "ol": 2, "nb": struct.pack("<H", ri_new)}]
            print("%s clip at %d: region %s shared by %d clips -> new region %s (index %d) with new entry %d (%s dB)" % (track, t, name, clip_users, nm, ri_new, newg, db))
    out = _splice2(d, tree, edits)
    write_new(dst, scramble(out))
    print("wrote %s (%d bytes)" % (dst, len(out)))





def _split_r_wav(wav):
    """if WAV ends with .L.wav / .L.WAV and the sibling .R.wav exists with identical format (1 ch), return its path, else None."""
    if not re.search(r"\.[Ll]\.(?:wav|WAV)$", wav):
        return None
    wr = re.sub(r"\.([Ll])(\.(?:wav|WAV))$", lambda m: "." + ("R" if m.group(1) == "L" else "r") + m.group(2), wav)
    if not os.path.isfile(wr):
        return None
    return wr if _wav_info(wr) == _wav_info(wav) and _wav_info(wav)[1] == 1 else None


# newsong (whole session from one call)
def cmd_newsong(dst, *args):
    """NEW session with tracks of all writer kinds and own notes, from one call; no template file.
    Arguments: options name=<session name> bpm=<20..999> rate=<Hz, experimental> and one argument per track, in track order:
        <TrackName>=<kind>[,stereo][,mono][,in:<Folder>][|<notes>]     kind: midi, instrument, audio, aux, master (stereo; ,mono = mono), folder,
        rfolder (stereo routing folder); in:<Folder> puts the track inside a folder listed BEFORE it (members directly behind their folder);
        notes (midi / instrument): see setnotes; v1.61 audio track: |<file.wav>[@<position in samples>][;<file.wav>...] = one clip per file
        (addclip rules: session rate, PCM 16 / 24 bit, mono file on mono track, stereo on stereo); the files are copied to 'Audio Files' beside OUT
    Method: the built-in base (click + one MIDI track), addtrack3 per further track, renamex, setnotes per notes spec, newsession.
    The base MIDI track is always track 2: it takes the FIRST listed track when that is a MIDI track, otherwise it stays as 'MIDI 1'.
    A MIDI / instrument track without notes has an empty playlist (v1.63; fill=1: the base test clip of 314 notes as in v1.58). Tracks above the Pro Tools Intro limits (8 audio, 8 MIDI,
    8 instrument, 3 aux beside the click, 1 master) are written, with a warning: Intro drops them on load.
    Example: python3 ptx_edit.py newsong Song.ptx bpm=96 "Bass=midi|range:36:47:0.5:100" "Keys=instrument,stereo|chords:C,Am,F,G7:4:96" Vox=audio Gtr=audio,stereo Rev=aux,stereo Mix=master"""
    import tempfile
    o, trk = {}, []
    kinds = ("midi", "instrument", "audio", "aux", "master", "folder", "rfolder")
    for x in args:
        k, _, v = x.partition("=")
        if k in ("name", "bpm", "rate", "fill", "bits", "base", "io", "tempo", "meter", "keysig", "markers", "groups") and v and v.split("|")[0].split(",")[0] not in kinds:
            o[k] = v
            continue
        spec, _, notes = v.partition("|")
        p = spec.split(",")
        if not k or p[0] not in kinds or [q for q in p[1:] if q not in ("stereo", "mono", "ticks") and not q.startswith("in:")]:
            probe.fail("argument '%s' not understood" % x, "use name=.. bpm=.. rate=.. or <TrackName>=<%s>[,stereo][,mono][,ticks][,in:<Folder>][|<notes>]" % "|".join(kinds))
        clips = []
        if notes and p[0] == "audio":                                          # audio track: <file.wav>[@<samples>][;<file.wav>[@<samples>]...]
            for c_ in notes.split(";"):
                f_, _, a_ = c_.rpartition("@") if "@" in c_ and c_.rpartition("@")[2].isdigit() else (c_, "", "0")
                ch_ = _wav_info(f_)[1]                                         # fails early with its own hint
                want_ch = 2 if "stereo" in p[1:] else 1
                if ch_ != want_ch and not (want_ch == 2 and ch_ == 1 and _split_r_wav(f_)):
                    probe.fail("track '%s': %s has %d channel(s)" % (k, f_, ch_), "mono file on a mono track, stereo (or .L.wav+.R.wav pair) on a stereo track (<Track>=audio,stereo)")
                clips.append((f_, int(a_)))
            if len({os.path.basename(f_) for f_, _ in clips}) != len(clips):
                probe.fail("track '%s': the same file name twice" % k, "one clip per file in newsong; further placements: addclip")
            notes = ""
        if notes and p[0] not in ("midi", "instrument"):
            probe.fail("track '%s': notes on a %s track" % (k, p[0]), "notes go on midi or instrument tracks; audio files on audio tracks")
        if not (1 <= len(k.encode("utf-8")) <= 60 and k.isprintable() and "," not in k and k not in ("Notes_Full", "Click 1")):
            probe.fail("track name '%s' not allowed" % k, "use 1..60 UTF-8 bytes of printable characters, no comma, not 'Notes_Full' / 'Click 1'")
        if notes:
            ns_, c_, x_ = _ctl_spec(notes)                                     # fails early with its own hint
            if ns_ or not (c_ or x_):
                _note_spec(ns_)
        trk.append({"name": k, "kind": p[0], "stereo": "stereo" in p[1:], "notes": notes, "mono": "mono" in p[1:],
                    "ticks": "ticks" in p[1:],
                    "into": next((q[3:] for q in p[1:] if q.startswith("in:")), None), "clips": clips})   # mono (master), in:<Folder>; ticks (audio)
    if not trk or len({t_["name"] for t_ in trk}) != len(trk):
        probe.fail("no tracks given, or duplicate track names", "give at least one <TrackName>=<kind>, every name once")
    if o.get("base") == "captured":                                            # the captured base path is removed (clean room)
        probe.fail("option base=captured was removed in v1.73 (clean room)", "leave it out: the session is built from fields (newbase + addtrack4)")
    return _newsong_clean(dst, o, trk)


def _map_options(o):
    """tempo=<ticks>:<bpm>;...  meter=<ticks>:<bar>:<num>/<den>;...  bpm=<bpm> -> (tempo events, meter events) or (None, None)."""
    try:
        tm = [(int(a), float(b)) for a, b in (x.split(":") for x in o["tempo"].split(";") if x)] if o.get("tempo") else None
        if not tm and o.get("bpm"):
            tm = [(0, float(o["bpm"]))]
        mm = [(int(a), int(b), int(c.split("/")[0]), int(c.split("/")[1])) for a, b, c in (x.split(":") for x in o["meter"].split(";") if x)] if o.get("meter") else None
        km = _parse_keysigs([x for x in o["keysig"].split(";") if x]) if o.get("keysig") else None
    except (ValueError, IndexError):
        probe.fail("tempo= / meter= / bpm= / keysig= not understood", "tempo=0:120;7680000:90  meter=0:1:4/4;7680000:3:3/4  keysig=0:C;960000:Am  bpm=96")
    if tm is not None and (not tm or tm[0][0] < 0 or [e[0] for e in tm] != sorted(e[0] for e in tm)):
        probe.fail("tempo map must start at tick >= 0 and be in time order", "e.g. tempo=0:120;7680000:90")
    for lst in [x for x in (mm, km) if x is not None]:
        if not lst or lst[0][0] != 0 or [e[0] for e in lst] != sorted(e[0] for e in lst):
            probe.fail("a map must start at tick 0 and be in time order", "first event 0:..., then rising ticks")
    if any(not 20 <= b <= 999 for _, b in tm or []) or any(n < 1 or d not in (1, 2, 4, 8, 16, 32, 64) for _, _, n, d in mm or []):
        probe.fail("tempo outside 20..999 bpm or meter denominator not a power of two", "e.g. 120.0 and 3/4, 7/8")
    return tm, mm, km


def _newsong_clean(dst, o, trk):
    """newsong in clean room: empty session from fields (_base_session), then per track addtrack4, folder membership (setfolder),
    notes (setnotes, empty playlist otherwise) and audio clips (addclip); every step in memory-free temp files. Options: rate=, bits=,
    io=0 (no output path; default io=1: 'Out 1-2'). bpm= / tempo= / meter= write the tempo and meter maps; name= is not written
    (Pro Tools uses the file name) - a warning says so."""
    import tempfile, shutil
    tmap, mmap, kmap = _map_options(o)                                         # tempo / meter; key sigs
    for k in ("name", "fill"):
        if k in o:
            print("WARNING: option %s= is not written by the clean-room base yet (Pro Tools default; base=captured = old path)" % k)
    lim = {
        "audio": int(_cfg_val("intro_limits", "audio_tracks", 8)),
        "midi": int(_cfg_val("intro_limits", "midi_tracks", 8)),
        "instrument": int(_cfg_val("intro_limits", "inst_tracks", 8)),
        "aux": int(_cfg_val("intro_limits", "aux_and_routing_folders", 4)),
        "master": int(_cfg_val("intro_limits", "master_tracks", 1)),
    }
    for kd, mx in lim.items():
        n_ = len([t_ for t_ in trk if t_["kind"] == kd or (kd == "aux" and t_["kind"] == "rfolder")])
        if n_ > mx:
            print("WARNING: %d %s tracks; Pro Tools Intro keeps %d and drops the rest on load" % (n_, kd, mx))
    tmp = tempfile.mkdtemp(prefix="ptx_newsong_")
    cnt = [0]
    def step():
        cnt[0] += 1
        return os.path.join(tmp, "s%03d.ptx" % cnt[0])
    cur = step()
    def_sr = int(_cfg_val("format", "default_sample_rate", 48000))
    def_bits = int(_cfg_val("format", "default_bit_depth", 24))
    write_new(cur, scramble(_base_session(int(o.get("rate", def_sr)), int(o.get("bits", def_bits)), io=o.get("io", "1") != "0", tempo=tmap, meter=mmap, keysig=kmap)))
    for t_ in trk:
        nxt = step()
        st = "1" if t_["stereo"] or (t_["kind"] in ("master", "rfolder") and not t_["mono"]) else "0"   # rfolder,mono = mono routing folder
        tb = ("timebase=ticks",) if t_.get("ticks") and t_["kind"] == "audio" else ()
        cmd_addtrack4(cur, nxt, "kind=" + t_["kind"], "name=" + t_["name"], "stereo=" + st, *tb)
        cur = nxt
    for t_ in trk:
        if t_["into"]:
            nxt = step()
            cmd_setfolder(cur, nxt, t_["name"], t_["into"], "force=1")
            cur = nxt
    for t_ in trk:
        if t_["notes"]:
            nxt = step()
            cmd_setnotes(cur, nxt, t_["name"], t_["notes"])
            cur = nxt
    media = []
    for t_ in trk:
        for f_, a_ in t_["clips"]:
            media.append(f_)
            wr_ = _split_r_wav(f_) if t_["stereo"] else None
            if wr_:
                media.append(wr_)
    if len({os.path.basename(f_) for f_ in media}) != len(media):
        probe.fail("the same audio file name on two tracks", "file names must differ ('Audio Files' is one folder); nothing written")
    af = os.path.join(os.path.dirname(os.path.abspath(dst)), "Audio Files")
    if media:                                                                  # files FIRST into 'Audio Files' (copy2 keeps the modification
        os.makedirs(af, exist_ok=True)                                         # time), clips are then made from the copies: the descriptor holds the
        for f_ in media:                                                       # file time and Pro Tools plays a stereo clip only when it matches (b41 - b56)
            to_ = os.path.join(af, os.path.basename(f_))
            if os.path.abspath(f_) != os.path.abspath(to_):
                if os.path.exists(to_) and open(to_, "rb").read() != open(f_, "rb").read():
                    probe.fail("%s exists with other content" % to_, "rename the file or use another session folder; nothing written")
                if not os.path.exists(to_):
                    shutil.copy2(f_, to_)
    for t_ in trk:
        for f_, a_ in t_["clips"]:
            nxt = step()
            cmd_addclip(cur, nxt, t_["name"], os.path.join(af, os.path.basename(f_)), "at=%d" % a_)
            cur = nxt
    if o.get("markers"):                                                       # markers after all tracks (one child per track)
        nxt = step()
        cmd_setmarkers(cur, nxt, o["markers"])
        cur = nxt
    if o.get("groups"):                                                        # groups after all tracks
        nxt = step()
        cmd_setgroups(cur, nxt, o["groups"])
        cur = nxt
    write_new(dst, open(cur, "rb").read())
    if media:
        print("audio files in %s: %s" % (af, ", ".join(os.path.basename(f_) for f_ in media)))
    print("wrote %s (clean room): %s" % (dst, ", ".join("%s (%s%s%s)" % (t_["name"], t_["kind"], " stereo" if t_["stereo"] else "", ", notes" if t_["notes"] else "") for t_ in trk)))


def cmd_buildspec(dst, spec_path):
    """Build a complete clean-room .ptx session in one call from a JSON parameter file."""
    import json, shutil, tempfile
    sp = spec_path[1:] if spec_path.startswith("@") else spec_path
    if not os.path.isfile(sp):
        probe.fail("spec file %s not found" % sp, "give path to a valid session JSON file (e.g. test/example_session.json)")
    spec_dir = os.path.dirname(os.path.abspath(sp))
    kit_root = os.path.dirname(HERE)
    spec = json.load(open(sp, encoding="utf-8"))
    if not isinstance(spec, dict):
        probe.fail("spec %s must be a JSON object" % sp, "see getting_started.md for the buildspec schema")

    def _resolve(rel_or_abs):
        q = os.path.expanduser(str(rel_or_abs))
        if os.path.isabs(q):
            return q
        c1 = os.path.normpath(os.path.join(spec_dir, q))
        if os.path.exists(c1):
            return c1
        return os.path.normpath(os.path.join(kit_root, q))

    def_sr = int(_cfg_val("format", "default_sample_rate", 48000))
    def_bits = int(_cfg_val("format", "default_bit_depth", 24))
    rate = int(spec.get("rate", def_sr))
    bits = int(spec.get("bits", def_bits))
    io = int(spec.get("io", 1)) != 0
    tmap = [(int(e["ticks"]), float(e["bpm"])) for e in spec["tempo"]] if spec.get("tempo") else ([(0, float(spec["bpm"]))] if "bpm" in spec else None)
    mmap = [(int(e["ticks"]), int(e["bar"]), int(e["num"]), int(e["den"])) for e in spec["meter"]] if spec.get("meter") else None
    kmap = _parse_keysigs(["%d:%s" % (int(e["ticks"]), e["key"]) for e in spec["keysig"]]) if spec.get("keysig") else None
    if tmap is not None and (not tmap or tmap[0][0] < 0 or [e[0] for e in tmap] != sorted(e[0] for e in tmap) or any(not 20 <= b <= 999 for _, b in tmap)):
        probe.fail("invalid 'tempo' map in spec", "start at tick >= 0, sorted ticks, bpm 20..999")
    if mmap is not None and (not mmap or mmap[0][0] != 0 or [e[0] for e in mmap] != sorted(e[0] for e in mmap) or any(n < 1 or d not in (1, 2, 4, 8, 16, 32, 64) for _, _, n, d in mmap)):
        probe.fail("invalid 'meter' map in spec", "start at tick 0, sorted ticks, denominator power of 2")
    tracks = spec.get("tracks", [])
    if not tracks:
        probe.fail("spec has no tracks", "add at least one entry in 'tracks'")
    for t in tracks:
        if ("colour" in t or "color" in t) and t.get("kind") != "audio":
            probe.fail("colour on non-audio track '%s' (%s)" % (t.get("name"), t.get("kind")), "cmd_setcolor currently supports 'audio' tracks only")

    tmp = tempfile.mkdtemp(prefix="ptx_spec_")
    try:
        cnt = [0]
        def step():
            cnt[0] += 1
            return os.path.join(tmp, "s%03d.ptx" % cnt[0])

        def run_step(fn, *a):
            nonlocal cur
            nxt = step()
            fn(cur, nxt, *a)
            cur = nxt

        cur = step()
        write_new(cur, scramble(_base_session(rate, bits, io=io, tempo=tmap, meter=mmap, keysig=kmap)))

        for b in spec.get("busses", []):
            run_step(cmd_addbus, b["name"], "stereo=%d" % (1 if b.get("stereo", True) else 0))

        for t in tracks:
            st = "1" if t.get("stereo") or (t.get("kind") in ("master", "rfolder") and not t.get("mono")) else "0"
            tb = ("timebase=ticks",) if t.get("ticks") and t.get("kind") == "audio" else ()
            run_step(cmd_addtrack4, "kind=" + t["kind"], "name=" + t["name"], "stereo=" + st, *tb)

        for t in tracks:
            fld = t.get("in") or t.get("folder")
            if fld:
                run_step(cmd_setfolder, t["name"], fld, "force=1")
        for fl in spec.get("folders", []):
            run_step(cmd_setfolder, fl["track"], fl["folder"], "force=1")

        for t in tracks:
            if t.get("input"):
                run_step(cmd_setinput, t["name"], t["input"])
            if t.get("output"):
                run_step(cmd_setoutput, t["name"], t["output"])
            if "colour" in t or "color" in t:
                col = t.get("colour", t.get("color"))
                run_step(cmd_setcolor, t["name"], str(col))
            if "comment" in t:
                run_step(cmd_setcomment, t["name"], str(t["comment"]))
            if "delay" in t and int(t["delay"]):
                run_step(cmd_setdelay, t["name"], str(int(t["delay"])))

        for n in spec.get("notes", []):
            nspec = str(n["spec"])
            if nspec.startswith("@"):
                nspec = "@" + _resolve(nspec[1:])
            run_step(cmd_setnotes, n["track"], nspec)

        clips = spec.get("clips", [])
        tr_stereo = {t["name"]: bool(t.get("stereo")) for t in tracks}
        af = os.path.join(os.path.dirname(os.path.abspath(dst)), "Audio Files")
        if clips:
            media_by_name = {}
            def _reg_media(p_w):
                ap = os.path.abspath(p_w)
                bn = os.path.basename(ap)
                if bn in media_by_name and media_by_name[bn] != ap:
                    probe.fail("two different audio files share basename '%s'" % bn, "Audio Files/ is a single flat folder; rename one source file")
                media_by_name[bn] = ap
            for c in clips:
                src_w = _resolve(c["wav"])
                _wav_info(src_w)
                _reg_media(src_w)
                if tr_stereo.get(c["track"]):
                    wr = _split_r_wav(src_w)
                    if wr:
                        _wav_info(wr)
                        _reg_media(wr)
            os.makedirs(af, exist_ok=True)
            for bn, src_w in media_by_name.items():
                dst_w = os.path.join(af, bn)
                if os.path.abspath(src_w) != os.path.abspath(dst_w):
                    if os.path.exists(dst_w) and open(dst_w, "rb").read() != open(src_w, "rb").read():
                        probe.fail("%s exists with different content" % dst_w, "remove or rename conflicting Audio Files/%s" % bn)
                    if not os.path.exists(dst_w):
                        shutil.copy2(src_w, dst_w)
            for c in clips:
                dst_w = os.path.join(af, os.path.basename(_resolve(c["wav"])))
                opts = ["at=%d" % int(c.get("at", 0))]
                for k in ("name", "start", "length", "sync"):
                    if k in c:
                        opts.append("%s=%s" % (k, c[k]))
                run_step(cmd_addclip, c["track"], dst_w, *opts)

        for fd in spec.get("fades", []):
            opts = []
            if fd.get("center"):
                opts.append("center=1")
            if "pre" in fd:
                opts.append("pre=%d" % int(fd["pre"]))
            pos_arg = "s%s" % fd["pos"] if str(fd["pos"]).isdigit() else str(fd["pos"])
            run_step(cmd_addfade, fd["track"], pos_arg, str(fd["len"]), fd["kind"], fd.get("slope", "equal_power"), *opts)

        for sd in spec.get("sends", []):
            opts = ["level=%s" % sd.get("level", 0.0), "pan=%s" % sd.get("pan", 0)]
            if sd.get("pre"):
                opts.append("pre=1")
            if sd.get("mute"):
                opts.append("mute=1")
            if "active" in sd:
                opts.append("active=%d" % (1 if sd["active"] else 0))
            if "slot" in sd:
                opts.append("slot=%s" % sd["slot"])
            run_step(cmd_addsend, sd["track"], sd["bus"], *opts)

        for pl in spec.get("plugins", []):
            opts = []
            if "bypass" in pl:
                opts.append("bypass=%d" % (1 if pl["bypass"] else 0))
            if "active" in pl:
                opts.append("active=%d" % (1 if pl["active"] else 0))
            if "multi" in pl:
                opts.append("multi=%d" % (1 if pl["multi"] else 0))
            if "delay" in pl:
                opts.append("delay=%d" % int(pl["delay"]))
            for pk, pv in (pl.get("params") or {}).items():
                opts.append("param.%s=%s" % (pk, pv))
            run_step(cmd_addplugin, pl["track"], pl["slot"], pl["plugin"], *opts)

        for ln in spec.get("lanes", []):
            run_step(cmd_setlane, ln["track"], ln["lane"], ln["points"])

        for pln in spec.get("plugin_lanes", []):
            tb_args = (str(int(pln["tb"])),) if "tb" in pln else ()
            run_step(cmd_addautolane, pln["track"], pln["slot"], pln["name"], str(pln["id"]), str(pln["index"]), str(pln.get("start", 0)), *tb_args)
            if pln.get("points"):
                run_step(cmd_setpluglane, pln["track"], pln["slot"], str(pln["id"]), pln["points"])

        tl = spec.get("timeline")
        if isinstance(tl, dict) and tl:
            opts = ["%s=%s" % (k, v) for k, v in tl.items() if k in ("tc_rate", "tc_start", "pull", "record_mode")]
            if opts:
                run_step(cmd_settimeline, *opts)

        if spec.get("markers"):
            mj = os.path.join(tmp, "markers.json")
            json.dump(spec["markers"], open(mj, "w", encoding="utf-8"))
            run_step(cmd_setmarkers, "@" + mj)

        if spec.get("groups"):
            gj = os.path.join(tmp, "groups.json")
            json.dump(spec["groups"], open(gj, "w", encoding="utf-8"))
            run_step(cmd_setgroups, "@" + gj)

        write_new(dst, open(cur, "rb").read())
        print("wrote %s (buildspec from %s): %d track(s), %d clip(s)" % (dst, sp, len(tracks), len(clips)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

# addclip (audio file + region + placement on an audio track)
def _wav_info(path):
    """(rate, channels, bits, frames) of a PCM WAV file (RIFF chunks 'fmt ' and 'data'; WAVE_FORMAT_EXTENSIBLE accepted)."""
    if not os.path.isfile(path):
        probe.fail("audio file %s not found" % path, "give the path of a .wav file")
    b = open(path, "rb").read()
    if b[:4] != b"RIFF" or b[8:12] != b"WAVE":
        probe.fail("%s is not a RIFF / WAVE file" % path, "only .wav (PCM 16 or 24 bit) is supported")
    p, fmt, dlen = 12, None, None
    while p + 8 <= len(b):
        cid, ln = b[p:p + 4], struct.unpack_from("<I", b, p + 4)[0]
        if cid == b"fmt ":
            fmt = struct.unpack_from("<HHIIHH", b, p + 8)
            if fmt[0] == 0xFFFE and ln >= 26:
                fmt = (struct.unpack_from("<H", b, p + 8 + 24)[0],) + fmt[1:]
        elif cid == b"data":
            dlen = min(ln, len(b) - p - 8)
        p += 8 + ln + (ln & 1)
    ok_ = fmt and ((fmt[0] == 1 and fmt[5] in (16, 24)) or (fmt[0] == 3 and fmt[5] == 32))    # 32-bit float (format 3)
    if not ok_ or dlen is None or fmt[1] not in (1, 2):
        probe.fail("%s: format %s not supported" % (path, fmt), "use PCM 16 / 24 bit or 32-bit float, mono or interleaved stereo")
    return fmt[2], fmt[1], fmt[5], dlen // fmt[4]


def _file_tree(data):
    """nodes of the file tree 0x103a (data = u32 count + nodes): [type, parent index, name, tail bytes]; type 1 folder (tail u32 0),
    2 file (tail 4 characters, 'EVAW'), 0 volume (parent ff ff ff ff, tail u32 volume id)."""
    n, p, out = struct.unpack_from("<I", data, 0)[0], 4, []
    for _ in range(n):
        ty, par, ln = data[p], struct.unpack_from("<I", data, p + 1)[0], struct.unpack_from("<I", data, p + 5)[0]
        if ty not in (0, 1, 2) or p + 9 + ln + 4 > len(data):
            probe.fail("file tree 0x103a: node type %d at %d" % (ty, p), "unknown layout; nothing written")
        out.append([ty, par, data[p + 9:p + 9 + ln], data[p + 9 + ln:p + 13 + ln]])
        p += 13 + ln
    if p != len(data):
        probe.fail("file tree 0x103a: %d bytes left over" % (len(data) - p), "unknown layout; nothing written")
    return out


def _file_tree_bytes(nodes):
    return struct.pack("<I", len(nodes)) + b"".join(bytes([t]) + struct.pack("<II", par, len(nm)) + nm + tl for t, par, nm, tl in nodes)


def cmd_addclip(src, dst, track, wav, *opts):
    """put the audio file WAV as one clip on the AUDIO track TRACK (mono file on a mono track, interleaved stereo file on a stereo track;
    sample rate = session rate; PCM 16 / 24 bit). Options: at=<position in samples, default 0>, name=<clip name, default file name without
    .wav>, folder=<absolute Mac folder of the session, default /Users/Shared>: only the stored search path; Pro Tools looks for the file
    in 'Audio Files' beside the session. THE WAV FILE IS NOT COPIED: put it into '<session folder>/Audio Files/' yourself.
    Writes: volume entry 0x0f3c (first file only, + directory reference), file tree 0x103a
    (folder 'Audio Files' / file node / volume / folder chain; a node stores the index of its parent), descriptor 0x1003 (file number,
    rate, channels, bits, frames, new file id, UMID), one region 0x2629 per channel (name, length, clip id, file index), one playlist entry
    0x1050 per channel (region index, position), 'has clips' flag of the track's two 0x251a blocks.
    Example: python3 ptx_edit.py addclip in.ptx out.ptx Vox "Audio Files/take1.wav" at=96000"""
    o = dict(x.split("=", 1) for x in opts if "=" in x)
    if set(o) - {"at", "name", "folder", "volume", "start", "length", "sync"} or len(o) != len(opts):
        probe.fail("unknown option in %s" % list(opts), "use at=<samples> name=<clip name> start=<offset in the file> length=<samples> sync=<samples> folder=<absolute Mac folder> volume=<Mac volume name>")
    rate, nch, bits, frames = _wav_info(wav)
    try:                                                                       # clip = a range of the file
        c_start = int(o.get("start", "0"))
        c_len = int(o.get("length", str(frames - c_start)))
        c_sync = int(o.get("sync", "0"))
    except ValueError:
        probe.fail("start= / length= / sync= must be numbers of samples", "e.g. start=48000 length=96000 sync=12000")
    if c_start < 0 or c_len < 1 or c_start + c_len > frames:
        probe.fail("range start %d + length %d outside the file (%d frames)" % (c_start, c_len, frames), "keep start + length <= the file length")
    if not 0 <= c_sync <= c_len:
        probe.fail("sync=%d outside clip length (%d samples)" % (c_sync, c_len), "keep 0 <= sync <= length")
    fname = os.path.basename(wav).encode("utf-8")
    cname = o.get("name", os.path.splitext(os.path.basename(wav))[0]).encode("utf-8")
    at_s = o.get("at", "0")
    at_ticks_flag = at_s.startswith("t")
    try:
        at = int(at_s[1:] if at_ticks_flag else at_s)
    except ValueError:
        probe.fail("at=%s is not a number" % at_s, "position in samples or t<ticks>, e.g. at=48000 or at=t1920000")
    if at < 0 or frames < 1 or frames >= 1 << 32 or not 1 <= len(cname) <= 60:
        probe.fail("position %d / %d frames / clip name length %d out of range" % (at, frames, len(cname)), "at >= 0, a non-empty file below 2^32 frames, name 1..60 bytes")
    raw, d, tree = descramble_file(src)
    d = bytes(d)
    dec = _decoder()
    t = _paths(tree)
    srate = dec.decode(src)["format"]["sample_rate"]
    if rate != srate:
        probe.fail("file rate %d, session rate %d" % (rate, srate), "convert the file to the session rate first (no sample-rate conversion here)")
    blk = lambda n: d[n["pos"]:n["pos"] + 7 + n["size"]]
    u32 = lambda p: struct.unpack_from("<I", d, p)[0]
    tn = struct.pack("<I", len(track.encode())) + track.encode()
    link = [n for n in t.get((0x1015, 0x1014), []) if blk(n)[9:9 + len(tn)] == tn]
    if len(link) != 1:
        probe.fail("audio track '%s' not found (0x1014 links: %d)" % (track, len(link)), "addclip needs an AUDIO track; names: ptx_decode")
    lb = blk(link[0])[9 + len(tn):]
    tch = struct.unpack_from("<I", lb, 1)[0]
    pls = list(struct.unpack_from("<%dH" % tch, lb, 5))
    wav_r = _split_r_wav(wav) if (tch == 2 and nch == 1) else None             # split-mono .L.wav + .R.wav stereo pair
    split_lr = wav_r is not None
    if tch != nch and not split_lr:
        probe.fail("file has %d channel(s), track '%s' has %d" % (nch, track, tch), "mono file on a mono track, stereo (or .L.wav+.R.wav pair) on a stereo track")
    if split_lr and "name" not in o:
        cname = re.sub(rb"\.[Ll]$", b"", cname)
    wavs = [wav, wav_r] if split_lr else [wav]
    p54, p4, p2a, pvol = t[(0x1054,)][0], t[(0x1004,)][0], t[(0x262a,)][0], t[(0x0f3d,)][0]
    lists = [k for k in p54["kids"] if k["ct"] == 0x1052]
    files = [k for k in p4["kids"] if k["ct"] == 0x1003]
    regs = [k for k in p2a["kids"] if k["ct"] == 0x2629]
    if u32(p4["pos"] + 9) != len(files) or u32(p2a["pos"] + 9) != len(regs) or p4["kids"][0]["ct"] != 0x103a or max(pls) >= len(lists):
        probe.fail("file list / region list counts do not match their blocks", "unknown layout; nothing written")
    E = []
    ed = lambda p, ol, nb, enc=None: E.append({"p": p, "ol": ol, "nb": nb, "enc": enc})
    rnd = lambda n: _rnd(n)
    # 1 volume (first file of the session)
    if u32(pvol["pos"] + 9) == 0:
        last = tree[-1]
        ref = lambda p_: b"\x01\x04\x00\x01\x00" + struct.pack("<I", p_) + b"\x00" * 6
        i = d.find(ref(pvol["pos"]), last["pos"] + 9)
        if i < 0 or u32(i - 4) != 1 or pvol["kids"]:
            probe.fail("volume list 0x0f3d: directory list not as expected", "unknown layout; nothing written")
        e_v = {"p": pvol["pos"] + 7 + pvol["size"], "ol": 0, "nb": _volume_entry(o.get("volume", str(_cfg_val("format", "default_volume", "Macintosh HD"))), rnd(4)), "enc": pvol["pos"]}   # built
        E.append(e_v)
        ed(pvol["pos"] + 9, 4, struct.pack("<I", 1))
        ed(i - 4, 4, struct.pack("<I", 2))
        ed(i + 15, 0, (15, lambda st, e=e_v: ref(st(e))), last["pos"])
    # 2 file tree & 3 descriptors
    ft = p4["kids"][0]
    nodes = _file_tree(d[ft["pos"] + 9:ft["pos"] + 7 + ft["size"]])
    fidxs, new_wavs = [], []
    if not nodes:
        vol = _volume_entry(o.get("volume", str(_cfg_val("format", "default_volume", "Macintosh HD"))), rnd(4))
        vl = struct.unpack_from("<I", vol, 9)[0]
        chain = [x for x in o.get("folder", str(_cfg_val("format", "default_folder", "/Users/Shared"))).split("/") if x]
        f_entries = [[2, 0, os.path.basename(w_).encode("utf-8"), b"EVAW"] for w_ in wavs]
        nc = len(f_entries)
        nodes = [[1, 1 + nc + len(chain), b"Audio Files", b"\x00" * 4]] + f_entries + [[0, 0xFFFFFFFF, vol[13:13 + vl], vol[13 + vl:17 + vl]]]
        nodes += [[1, 1 + nc + i_, x.encode("utf-8"), b"\x00" * 4] for i_, x in enumerate(chain)]
        fidxs = list(range(len(files), len(files) + nc))
        new_wavs = list(wavs)
    else:
        if nodes[0][0] != 1 or nodes[0][2] != b"Audio Files" or any(n_[0] == 2 and n_[1] != 0 for n_ in nodes):
            probe.fail("file tree 0x103a does not start with the folder 'Audio Files' holding all files", "unknown layout; nothing written")
        for w_ in wavs:
            fn_ = os.path.basename(w_).encode("utf-8")
            fnodes = [n_[2] for n_ in nodes if n_[0] == 2]
            if fn_ in fnodes:                                                  # file already in the session -> new clip of it
                fidxs.append(fnodes.index(fn_))
            else:
                k = 1 + len(fnodes)
                for n_ in nodes:
                    if n_[1] != 0xFFFFFFFF and n_[1] >= k:
                        n_[1] += 1
                nodes.insert(k, [2, 0, fn_, b"EVAW"])
                fidxs.append(len(files) + len(new_wavs))
                new_wavs.append(w_)
    if new_wavs:
        ed(ft["pos"] + 9, ft["size"] - 2, _file_tree_bytes(nodes))
        ds_all = b""
        for j_, w_ in enumerate(new_wavs):
            doff, _bext, ftime = _wav_layout(w_)
            if doff >= 1 << 16:
                probe.fail("sample data of %s starts at byte %d" % (w_, doff), "the descriptor holds a 16-bit offset: rewrite the file with a short header")
            ds_all += _file_descriptor(len(files) + 1 + j_, rate, nch, bits, frames, rnd(6) + b"\x80\x00", ftime, ftime, doff, rnd(16), rnd(8), flt=1 if bits == 32 else 0)
        ed(files[-1]["pos"] + 7 + files[-1]["size"] if files else ft["pos"] + 7 + ft["size"], 0, ds_all, p4["pos"])
        ed(p4["pos"] + 9, 4, struct.pack("<I", len(files) + len(new_wavs)))
    fidx = fidxs[0]
    # 4 regions, 5 playlist entries
    ids_ = [m_.group(1) for m_ in re.finditer(rb"\x2a\x00\x00\x00(.{8})\x01", d[p2a["pos"]:p2a["pos"] + 7 + p2a["size"]], re.S)]
    b20_ = next((n_ for n_ in tree if n_["ct"] == 0x2000), None)               # chunk ids: session part of the existing chunk ids, counter + 8
    if not ids_ and b20_:
        ids_ = [m_.group(1) for m_ in re.finditer(rb"\x2a\x00\x00\x00(.{8})\x01", d[b20_["pos"]:b20_["pos"] + 7 + b20_["size"]], re.S)]
    if not ids_:                                                               # no clip yet (clean-room session): session part of the track ids
        kids_ = [n_ for n_ in tree if n_["ct"] == 0x2624][0]["kids"] if [n_ for n_ in tree if n_["ct"] == 0x2624] else []
        sp_ = _new_track_id(d, kids_)[:4]
        ids_ = [x_ for x_ in _session_ids(d) if x_[:4] == sp_]
    else:
        sp_ = ids_[-1][:4]
    cids = [struct.unpack_from("<I", x_, 4)[0] for x_ in ids_ if x_[:4] == sp_]
    new_regs = b""
    dec_sess = dec.decode(src) if at_ticks_flag or any(d[lists[pls[c]]["pos"] + 7 + lists[pls[c]]["size"] - 2:lists[pls[c]]["pos"] + 7 + lists[pls[c]]["size"]] == b"\x02\x00" for c in range(tch)) else None
    for c in range(tch):                                                       # region built from fields; tch (split-mono .L/.R uses fidxs[c], channel=0)
        nid8 = sp_ + struct.pack("<I", (max(cids + [0]) + 8 * (c + 1)) & 0xFFFFFFFF)
        nm = cname + ((b".L", b".R")[c] if tch == 2 else b"")
        fi_c = fidxs[c] if split_lr else fidx
        ch_c = 0 if split_lr else c
        rg = _audio_region(nm.decode("utf-8"), c_len, rnd(16), fi_c, _midi_chunk([], nid8, plain=True), start=c_start, sync=c_sync, channel=ch_c)   # range; sync
        new_regs += bytes(rg)
        pl = lists[pls[c]]
        ents = [k_ for k_ in pl["kids"] if k_["ct"] == 0x1050]
        pn = struct.unpack_from("<I", d, pl["pos"] + 9)[0]
        cpos = pl["pos"] + 13 + pn
        if u32(cpos) != len(ents):
            probe.fail("playlist of '%s': count %d, entries %d" % (track, u32(cpos), len(ents)), "unknown layout; nothing written")
        pl_ticks = at_ticks_flag or d[pl["pos"] + 7 + pl["size"] - 2:pl["pos"] + 7 + pl["size"]] == b"\x02\x00"
        if at_ticks_flag:
            pos_val = int(round(dec.seconds_to_ticks(dec.ticks_to_seconds(at, dec_sess["tempo_used"]) + c_sync / srate, dec_sess["tempo_used"]))) if c_sync else at
        elif pl_ticks:
            pos_val = int(round(dec.seconds_to_ticks((at + c_sync) / srate, dec_sess["tempo_used"])))
        else:
            pos_val = at + c_sync
        en = _playlist_entry(len(regs) + c, pos_val, ticks=1 if pl_ticks else 0)
        after = [k_ for k_ in ents if k_["kids"] and k_["kids"][0]["ct"] == 0x104F and _epos(d, k_["kids"][0]["pos"] + 9) > pos_val]
        ed(after[0]["pos"] if after else (ents[-1]["pos"] + 7 + ents[-1]["size"] if ents else cpos + 4), 0, bytes(en), pl["pos"])
        ed(cpos, 4, struct.pack("<I", len(ents) + 1))
    ed(regs[-1]["pos"] + 7 + regs[-1]["size"] if regs else p2a["pos"] + 13, 0, new_regs, p2a["pos"])
    ed(p2a["pos"] + 9, 4, struct.pack("<I", len(regs) + tch))
    # 6 'has clips' flag of the track's two 0x251a blocks (5th byte from the end)
    hits = 0
    for x_ in t[(0x2519, 0x251a)]:
        b_ = blk(x_)
        if b_[9] == 0 and b_[11:11 + len(tn)] == tn:
            hits += 1
            if b_[-5] == 0:
                ed(x_["pos"] + len(b_) - 5, 1, b"\x01")
    if hits != 2:
        probe.fail("track-list blocks 0x251a of '%s': %d found, 2 expected" % (track, hits), "unknown layout; nothing written")
    out = _splice2(d, tree, E)
    write_new(dst, scramble(out))
    print("wrote %s: clip '%s' (%d frames, %d ch, %d bit) on '%s' at sample %d; file %d '%s' must be in 'Audio Files' beside the session"
          % (dst, cname.decode(), frames, nch, bits, track, at, fidx + 1, fname.decode()))




def cmd_setcomment(src, dst, track, text):
    """comment of TRACK = TEXT (UTF-8, up to 255 bytes; "" removes it). Field: 0x2015 of the channel block, after its first
    child block 8 bytes, then u32 length + text. One splice.
    Example: python3 ptx_edit.py setcomment in.ptx out.ptx Aux_s "ptx comment 37" """
    raw, d, tree = descramble_file(src)
    d = bytes(d)
    dec = _decoder()
    _, ch = _channel(dec, d, tree, track)
    b = next((n for n in probe.walk([ch]) if n["ct"] == 0x2015), None)
    new = text.encode("utf-8")
    if len(new) > 255:
        probe.fail("comment is %d bytes" % len(new), "use up to 255 bytes of UTF-8 text")
    if not b or d[b["pos"] + 9] != 0x5A:
        probe.fail("track '%s' has no 0x2015 block with the known layout" % track, "unknown layout; nothing written")
    c = b["pos"] + 9 + 7 + struct.unpack_from("<I", d, b["pos"] + 12)[0]
    old = struct.unpack_from("<I", d, c + 8)[0]
    if old > 4096 or c + 12 + old + 9 > b["pos"] + 7 + b["size"]:
        probe.fail("comment length field of '%s' holds %d" % (track, old), "unknown layout (older session version?); nothing written")
    out = _splice2(d, tree, [{"p": c + 8, "ol": 4 + old, "nb": struct.pack("<I", len(new)) + new, "enc": b["pos"]}])
    write_new(dst, scramble(out))
    print("wrote %s: comment of %s: '%s' -> '%s'" % (dst, track, d[c + 12:c + 12 + old].decode("utf-8", "replace"), text))


# MIDI channel block 0x2620 built field by field (clean room, stage 2)
# Fields: name, track id (three times), route index (three times), MPE mode bytes, MIDI volume / mute / pan (twice, and volume /
# pan again in the view block), mute lane header, view block 0x2010 > 0x200a > 0x2015 (flags a / b / g, heights h1 / h2, comment, view ratio,
# zoom z1 / z2, 'last track' mark and its extra 0x203a, track number). Built byte-identically for 317 of 318 MIDI channel blocks of Pro Tools
# saves (reference, handstep, runs of 2026-11-13); not: a MIDI track with mute automation points.
def _blk(kind, ct, *parts):
    data = b"".join(parts)
    return b"\x5a" + struct.pack("<HIH", kind, len(data) + 2, ct) + data
_ID_MARK = b"\x2a\x00\x00\x00"
def _view203a(v):                       # small view block: empty 0x2037 + two equal bytes
    return _blk(2, 0x203a, _blk(1, 0x2037), bytes([v, v]))
_MIDI_CH_DEFAULTS = dict(route=0, mpe=b"\x00\x00", vol=96, mute=0, pan=64, vol2=96, mute2=0, pan2=64, lane_on=1, extra=b"", ratio=0.0, a=0, b=1, h1=0x5c, c=2,
                     z1=500000, h2=0x61, mark=3, z2=500000, last=0, number=2, g=0, comment=b"")
def _midi_channel(name, tid, **kw):
    f = dict(_MIDI_CH_DEFAULTS); f.update(kw)
    nm = name.encode("utf-8")
    r = struct.pack("<II", f["route"], 1)
    info = _blk(3, 0x102d,
             _blk(9, 0x2619, struct.pack("<I", len(nm)) + nm + b"\x01\x00\x01\x00\x00\x00\x00" + _ID_MARK + tid + b"\x00" * 4 + _ID_MARK + tid + b"\x00" * 8 + struct.pack("<I", 1) + b"\x00" * 33,
               _blk(1, 0x4301, b"\x00" * 32), b"\x00" * 4 + _ID_MARK + tid + b"\x00\x00"),
             b"\x00\x01\x00\x00\x00\x01\x00")
    mix = struct.pack("<IIII", f["vol"], f["mute"], f["pan"], 0) + b"\x80\xff\x00\xc0\x00\x00" + struct.pack("<III", f["vol2"], f["mute2"], f["pan2"]) + b"\x00" * 33
    lane = struct.pack("<HIHH", f["lane_on"], 1, 2, 0) + (struct.pack("<Q", 10 ** 12) if f["lane_on"] else b"\x00" * 8) + b"\x00" * 4
    strip = _blk(1, 0x2611, _blk(7, 0x2036, mix), b"\x01", _blk(1, 0x260a, b"\x01\x46\x01\x00" + struct.pack("<I", len(lane) - 2) + lane))
    v15 = _blk(0x15, 0x2015, _view203a(1),
            bytes([f["a"], 1, 0, 0, f["b"], 0]) + struct.pack("<HI", f["h1"], len(f["comment"])) + f["comment"] + b"\x00" + struct.pack("<d", f["ratio"]) + b"\x00" + bytes([f["c"]]) + b"\xfe\xff\x01"
            + struct.pack("<I", f["z1"]) + b"\x00\x01" + struct.pack("<H", f["h2"]) + b"\x00\x00" + bytes([f["mark"]]) + b"\x00" + struct.pack("<I", f["z2"]) + b"\x00\x00\x00"
            + bytes([f["last"]]) + b"\x00\x00\x00",
            _view203a(1) if f["last"] else b"", b"\x00" * 4 + b"\x07" + b"\x00" * 7 + b"\x01", _blk(1, 0x2434, b"\x04\x00\x00\x00\x00\x00\x00\x3c\x00"), struct.pack("<I", f["number"]),
            _view203a(1), b"\x00\x01\x00\x00\x00",
            _blk(5, 0x2580, b"\x00", _view203a(3), b"\xff\xff\x00\x00\xff\xff\x00\x00\x00\x00\xff\xff\xff\xff", _view203a(3), b"\x00\xff\xff"),
            b"\x00" * 4 + struct.pack("<I", f["g"]))
    view = _blk(5, 0x2010,
             _blk(0x0a, 0x200a, v15, b"\x00\x00", _view203a(1), b"\x13\x00\x00\x09\x3d\x00\x17\x00\xff\xff\xff\xff", _view203a(1), b"\x02\x00\x00\x00", _view203a(1), _view203a(1)),
             struct.pack("<I", len(f["extra"])) + f["extra"] + b"\x01\x00" + bytes([f["vol"], f["pan"]]) + struct.pack("<dd", -1.0, -1.0) + b"\x00\xff\xff\xff\xff")
    return _blk(8, 0x2620, info, r + r[:5], strip, view, b"\x00" * 8, _blk(2, 0x206f, struct.pack("<I", 1)), b"\x01" + r + b"\x00" * 12 + f["mpe"])

def _midi_channel_fields(blk, parse=None):
    """named fields of a Pro Tools 0x2620 block (for the byte-compare test); parse = probe.parse"""
    t = (parse or probe.parse)(blk, 0, len(blk))[0]
    def find(n, ct, i=0):
        k = [x for x in n["kids"] if x["ct"] == ct]; return k[i]
    def own(n):
        x = bytearray(blk[n["pos"]:n["pos"] + 7 + n["size"]])
        for k in sorted(n.get("kids", []), key=lambda k: -k["pos"]): x[k["pos"] - n["pos"]:k["pos"] - n["pos"] + 7 + k["size"]] = b""
        return bytes(x[9:])
    o = own(t); i19 = own(find(find(t, 0x102d), 0x2619)); nl = struct.unpack_from("<I", i19, 0)[0]
    m = own(find(find(t, 0x2611), 0x2036)); la = own(find(find(t, 0x2611), 0x260a))
    v10 = find(t, 0x2010); o10 = own(v10); v15 = find(find(v10, 0x200a), 0x2015); o15 = own(v15)
    xl = struct.unpack_from("<I", o10, 0)[0]
    cl = struct.unpack_from("<I", o15, 8)[0]
    cm = o15[12:12 + cl]; o15 = o15[:12] + o15[12 + cl:]; o15 = o15[:8] + b"\x00" * 4 + o15[12:]
    return dict(name=i19[4:4 + nl].decode("utf-8"), tid=i19[4 + nl + 11:4 + nl + 19], route=struct.unpack_from("<I", o, 0)[0], mpe=o[42:44],
                vol=struct.unpack_from("<I", m, 0)[0], mute=struct.unpack_from("<I", m, 4)[0], pan=struct.unpack_from("<I", m, 8)[0],
                vol2=struct.unpack_from("<I", m, 22)[0], mute2=struct.unpack_from("<I", m, 26)[0], pan2=struct.unpack_from("<I", m, 30)[0],
                lane_on=struct.unpack_from("<H", la, 8)[0], extra=o10[4:4 + xl], a=o15[0], b=o15[4], h1=struct.unpack_from("<H", o15, 6)[0],
                ratio=struct.unpack_from("<d", o15, 13)[0], c=o15[22], z1=struct.unpack_from("<I", o15, 26)[0], h2=struct.unpack_from("<H", o15, 32)[0],
                mark=o15[36], z2=struct.unpack_from("<I", o15, 38)[0], last=o15[45], number=struct.unpack_from("<I", o15, 62)[0], g=struct.unpack_from("<I", o15, 75)[0], comment=cm)


def cmd_chcheck(*files):
    """are the MIDI channel blocks 0x2620 of each FILE equal to the blocks built from their named fields? One line per file.
    Example: python3 ptx_edit.py chcheck a.ptx b.ptx"""
    if not files:
        probe.fail("no file given", "usage: chcheck <file.ptx> [more files]")
    tot = ok = 0
    for f in files:
        raw, d, tree = descramble_file(f)
        d = bytes(d)
        n = k = 0
        for top in [t for t in tree if t["ct"] == 0x2624]:
            for ch in [c for c in top["kids"] if c["ct"] == 0x2620]:
                blk = d[ch["pos"]:ch["pos"] + 7 + ch["size"]]
                try:
                    fl = _midi_channel_fields(blk)
                    same = _midi_channel(fl.pop("name"), fl.pop("tid"), **fl) == blk
                except (struct.error, IndexError, UnicodeDecodeError):
                    same = False
                n += 1
                k += 1 if same else 0
        tot += n
        ok += k
        print("%s  %d of %d MIDI channel blocks  %s" % ("identical" if n == k else "DIFFERENT", k, n, f))
    print("%d of %d MIDI channel blocks equal the built ones" % (ok, tot))


# MIDI route 0x1057 and MIDI clip-library record built field by field
_ROUTE_2502 = b"\x01\x01\x00\x01"
_ROUTE_103D = bytes.fromhex("4500000000000000004c0d4100000000004cfd40050000000300000002000000000000000000000064000000000000006400000000000000010000")
_ROUTE_2502_END = bytes.fromhex("00006400640000000000000100a60e0000000000c00300000000000000000100640000e803000000000000000032aa05000000000100000001000000"
                                "000000000000000000006400000001007f000000003c0000")


def _midi_route(name, entries, playlist_id, t0=2):
    """MIDI route 0x1057 [4]: u32 length + name, u32 n, n placements 0x1056 [1] > 0x104f [10] (mute, u16 region index, u40 position,
    time-base byte 0x40 / 0, kind), the MIDI track settings 0x2502 [2] > 0x103d [4] (constant in all 384 routes of the kit's Pro Tools saves),
    time base (2 ticks, 1 samples), 4 x 00, id marker + playlist id. 380 / 384 rebuilt byte-identically. entries: [(region index, position,
    mute, kind, ticks)]"""
    nm = name.encode("utf-8")
    ents = b"".join(_blk(1, 0x1056, _blk(10, 0x104f, bytes([mu, 0]) + struct.pack("<H", ri) + b"\x00" * 3 + pos.to_bytes(5, "little") + b"\x00\x00"
                                            + bytes([0x40 if tk else 0, kd]) + b"\xfe\xff\x00\x00\x01\x00" + b"\xff" * 8 + b"\x00" * 5)) for ri, pos, mu, kd, tk in entries)
    return _blk(4, 0x1057, struct.pack("<I", len(nm)) + nm + struct.pack("<I", len(entries)), ents,
                _blk(2, 0x2502, _ROUTE_2502, _blk(4, 0x103d, _ROUTE_103D), _ROUTE_2502_END), bytes([t0]) + b"\x00" * 4 + _ID_MARK + playlist_id)


def _midi_clip_record(name, length, clip_id, chunk_index):
    """MIDI clip-library entry 0x2633 [1] > 0x2628 [5] of a clip that starts at 0: name, widths (start 0, unit nibble 1, length width), length,
    the region tail of 9.55 without clip gain, 16-byte clip id; then u32 index of the clip's chunk in 0x2000"""
    nm = name.encode("utf-8")
    wl = 3 if length < 1 << 24 else 4 if length < 1 << 32 else 5
    r28 = _blk(5, 0x2628, struct.pack("<I", len(nm)) + nm + bytes([0, 1, wl << 4, 0, 0]) + length.to_bytes(wl, "little") + b"\xfe\xff" + b"\x00" * 4
               + b"\xff\xff\x04\x00\x04\x00" + b"\x00" * 21 + b"\xff" * 4 + b"\x00\x00" + clip_id)
    return _blk(1, 0x2633, r28, struct.pack("<I", chunk_index))


# instrument channel block 0x2621 built field by field; 606 / 642 rebuilt
_MIDI_VIEW = ("aaa", "AA", "aaaa")
def _instr_channel(name, tid, stereo=0, route=1, runnum=None, out_id=None, out_name="", uuids=None, v=None, flags=None, tbl_main=None, tbl_send=None,
                  out_head=b"\x02\x00\x01\x01", out_tail=b"\x01\x01" + b"\xff" * 8 + b"\x00" + b"\xff" * 4 + b"\x00\x0c\x01\x00", mix=None, lane_on=1, extra=b"",
                  vol=0x60, pan=0x40, post=None, sends=10, tb=0, m80=b"\x01\x00", rk=None):
    """instrument 0x2621 [17]: the parts of a strip set inline (info, flags, inserts, main strip, sends), running numbers with the route index,
    the MIDI view block 0x2010, 0x206f, the MIDI strip 0x2611, input and slot ids, 0x4856"""
    st = 1 if stereo else 0
    vv = dict(_VIEW_DEFAULT, c=2, z1=12800000, z2=12800000, ratio=0.532258064516129, f0a=0); vv.update(v or {})
    ss = _strip_set(name, tid, st, flags=flags, runnum=runnum, out_id=out_id, out_name=out_name, out_head=out_head, out_tail=out_tail, sends=sends, uuids=uuids,
                   tbl_main=tbl_main, tbl_send=tbl_send, tb=tb)
    parts = _split_strip_set(ss)                                    # [info, flags, inserts, main, send list]
    rk = rk or (0, 0, 1, route, 1)                                 # (x0, x1, k, route 2, e): 'last track' values of a new track
    run = b"\x01\x01\x0a\x00" + struct.pack("<10I", *(runnum or range(1, 11))) + struct.pack("<IIIHIB", rk[0], rk[1], route, rk[2], rk[3], rk[4])
    view = _blk(5, 0x2010, _view0a(*_MIDI_VIEW, vv), struct.pack("<I", len(extra)) + extra + b"\x01\x00" + bytes([vol, pan]) + struct.pack("<dd", -1.0, -1.0) + b"\x00\xff\xff\xff\xff")
    m = mix or (96, 0, 64, 96, 0, 64)
    strip = _blk(1, 0x2611, _blk(7, 0x2036, struct.pack("<IIII", m[0], m[1], m[2], 0) + b"\x80\xff\x00\xc0" + m80 + struct.pack("<III", m[3], m[4], m[5]) + b"\x00" * 33), b"\x01",
              _blk(1, 0x260a, b"\x01\x46\x01\x00" + struct.pack("<I", 20) + struct.pack("<HIHH", lane_on, 1, 2, 0) + (struct.pack("<Q", 10 ** 12) if lane_on else b"\x00" * 8) + b"\x00" * 4))
    uu = uuids or [__import__('uuid').uuid4().bytes for _ in range(10)]
    tail = b"\x00" * 28 + b"\xff" * 4 + b"\x00\x00\xff\x7f" + struct.pack("<H", 10) + b"".join(uu) + (post if post is not None else bytes([0, st, 0, 0, 0, 1, 0, st]) + b"\x00" * 29)
    return _blk(0x11, 0x2621, *parts, run, view, b"\x00" * 8, _blk(2, 0x206f, struct.pack("<I", 1)), strip, tail, _blk(4, 0x4856, b"\x00" * 13 + b"\x01"), b"\x00\x00")
def _split_strip_set(ss):
    """own data of a built 0x261b without its tail and 0x4856: the inline parts of an instrument block"""
    body = ss[9:]
    i = body.find(b"\x01\x01\x0a\x00")
    return [body[:i]]


# basic folder channel block 0x263b built field by field; 28 / 31 rebuilt
def _folder_channel(name, tid, v):
    """basic folder 0x263b [5]: track info 0x2619 (flag 1), 01 00 00, view 0x4701 [2] > 0x200a; the view has no 0x2580 and bare 0x2037 cells"""
    nm = name.encode("utf-8")
    i19 = _blk(9, 0x2619, struct.pack("<I", len(nm)) + nm + b"\x01\x00\x01\x00\x00\x00\x00" + _ID_MARK + tid + b"\x00" * 4 + _ID_MARK + tid + b"\x00" * 8 + struct.pack("<I", 1) + b"\x00" * 33,
            _blk(1, 0x4301, b"\x00" * 32), b"\x00" * 4 + _ID_MARK + tid + b"\x00\x01")
    c8 = _CELL["8"]
    v15 = _blk(0x15, 0x2015, c8(),
            v["f6"] + struct.pack("<HI", v["h1"], len(v["comment"])) + v["comment"] + b"\x00" + struct.pack("<d", v["ratio"]) + b"\x00" + bytes([v["c"]])
            + b"\xfe\xff\x01" + struct.pack("<I", v["z1"]) + b"\x00\x01" + struct.pack("<H", v["h2"]) + b"\x00\x00" + bytes([v["mark"], 0]) + struct.pack("<I", v["z2"]) + b"\x00" * 3
            + bytes([v["last"]]) + b"\x00" * 3, c8() if v["last"] else b"", b"\x00" * 4 + b"\x07" + b"\x00" * 7 + b"\x01",
            _blk(1, 0x2434, b"\x04\x00\x00\x00\x00\x00\x00\x3c\x00"), struct.pack("<I", v["number"]), c8(), b"\x00" * 9 + bytes([v["g"]]) + b"\x00" * 3)
    e = _blk(1, 0x2037)
    va = _blk(0x0a, 0x200a, v15, b"\x00\x00", e, b"\x13\x00\xff\xff\xff\xff\x13\x00\xff\xff\xff\xff", e, b"\x00" * 4, e, e)
    return _blk(5, 0x263b, i19, b"\x01\x00\x00", _blk(2, 0x4701, va), b"\x00")


def _folder_channel_fields(b):
    """(name, track id, view fields) of a 0x263b block (test of the builder, demotion)"""
    t = probe.parse(b, 0, len(b))[0]
    i19 = _ax_own(b, _ax_find(t, 0x2619))
    nl = struct.unpack_from("<I", i19, 0)[0]
    v15 = _ax_find(_ax_find(_ax_find(t, 0x4701), 0x200a), 0x2015)
    o15 = _ax_own(b, v15)
    cl = struct.unpack_from("<I", o15, 8)[0]
    cm, o = o15[12:12 + cl], o15[:12] + o15[12 + cl:]
    v = dict(f6=o[0:6], h1=struct.unpack_from("<H", o, 6)[0], comment=cm, ratio=struct.unpack_from("<d", o, 13)[0], c=o[22], z1=struct.unpack_from("<I", o, 26)[0],
             h2=struct.unpack_from("<H", o, 32)[0], mark=o[36], z2=struct.unpack_from("<I", o, 38)[0], last=o[45], number=struct.unpack_from("<I", o, 62)[0], g=o[-4])
    return i19[4:4 + nl].decode("utf-8"), i19[4 + nl + 11:4 + nl + 19], v


# aux / routing folder / master channel blocks built field by field
# Generic parts: track info 0x102d, strip set 0x261b (inputs, 11 insert slots, main strip, send strips, running numbers, slot ids), view block
# 0x200a / 0x2015. Rebuilt byte-identically: aux 0x261e 904 / 1 107 (the others carry plug-ins - the click track - or automation), master
# 0x261d 210 / 244.
_CELL = {"a": lambda: _blk(2, 0x203a, _blk(1, 0x2037), b"\x01\x01"), "A": lambda: _blk(2, 0x203a, _blk(1, 0x2037), b"\x03\x03"),
        "b": lambda: _blk(1, 0x203b, _blk(1, 0x2037), b"\x01\x00\x00\x00"), "8": lambda: _blk(1, 0x2038, _blk(1, 0x2037), b"\x00")}
def _lane_tb(v=0, tb=0):                   # automation _lane_tb without points (time base 0 samples / 1 ticks)
    return _blk(1, 0x260a, b"\x01\x46\x01\x00" + struct.pack("<I", 20) + struct.pack("<HIHH", tb, 1, 2, 0) + struct.pack("<Q", 10 ** 12 if tb else 0) + struct.pack("<hH", v, 0))
def _panner_tb(first, tb=0):
    return _blk(2, 0x260c, b"".join(b"\x01" + _lane_tb(v, tb) for v in [first, first, 100, 100, 100, 100, 100, 100, 0, 0, 1, 0, 0, 0]))
def _track_info(name, tid, fl19=0):
    nm = name.encode("utf-8")
    return _blk(3, 0x102d, _blk(9, 0x2619, struct.pack("<I", len(nm)) + nm + b"\x01\x00\x01\x00\x00\x00\x00" + _ID_MARK + tid + b"\x00" * 4 + _ID_MARK + tid + b"\x00" * 8 + struct.pack("<I", 1) + b"\x00" * 33,
                          _blk(1, 0x4301, b"\x00" * 32), b"\x00" * 4 + _ID_MARK + tid + bytes([0, fl19])), b"\x00\x01\x00\x00\x00\x01\x00")
def _strip_set(name, tid, stereo=0, flags=None, runnum=None, out_id=None, out_name="", out_head=b"\x02\x00\x01\x01",
              out_tail=b"\x01\x01" + b"\xff" * 8 + b"\x00" + b"\xff" * 4 + b"\x00\x0c\x01\x00", sends=10, in_name="", in_id=None, uuids=None, t1=None, t6=None, main=None, tb=0, fl19=0, in_x=0, tbl_main=None, tbl_send=None, master=False):
    """0x261b [15]: track _track_info, input flags, 11 empty insert slots, main strip, SENDS send strips, running numbers, input, 10 slot ids"""
    on, inn = out_name.encode("utf-8"), in_name.encode("utf-8")
    inserts = _blk(1, 0x2627, struct.pack("<H", 11), *[_blk(1, 0x2625, _blk(1, 0x2626)) for _ in range(11)])
    p = -100 if stereo else 0
    tm = tbl_main if tbl_main is not None else (_STRIP_ST_MAIN if stereo else _STRIP_MONO)
    outb = _blk(9, 0x260e, out_head + b"\x00" * 4 + ((_ID_MARK + out_id) if out_id else b"\x00" * 12) + b"\x00" * 16 + struct.pack("<I", len(on)) + on + out_tail)
    if master:                                                   # master strip: one _lane_tb, two empty panners; no output block when unassigned
        main = _blk(6, 0x260d, _strip_table(tm), (b"\x01\x00" + outb) if out_name or out_id else b"\x00\x00", b"\x01", _lane_tb(0, tb), b"\x00\x00",
                 _blk(2, 0x260c, b"\x00" * 14), _blk(2, 0x260c, b"\x00" * 14), b"\x00" * 9, _BLK485A)
    if main is None:
        main = _blk(6, 0x260d, _strip_table(tm), b"\x01\x00",
                 _blk(9, 0x260e, out_head + b"\x00" * 4 + ((_ID_MARK + out_id) if out_id else b"\x00" * 12) + b"\x00" * 16 + struct.pack("<I", len(on)) + on + out_tail),
                 b"\x01", _lane_tb(0, tb), b"\x01", _lane_tb(0, tb), b"\x01", _lane_tb(-1440, tb), _panner_tb(p, tb), _panner_tb(100 if stereo else 0, tb), b"\x00" * 9, _BLK485A)
    send = _blk(6, 0x260d, _strip_table(tbl_send if tbl_send is not None else (_STRIP_ST_SEND if stereo else _STRIP_MONO)), b"\x00" * 5, _blk(2, 0x260c, b"\x00" * 14), _blk(2, 0x260c, b"\x00" * 14), b"\x00" * 9, _BLK485A)
    sl = struct.pack("<H", sends) + b"".join(struct.pack("<H", i) + send for i in range(sends))
    uu = uuids or [__import__('uuid').uuid4().bytes for _ in range(10)]
    src = b"\x00" + struct.pack("<I", len(inn)) + inn + b"\x00" * 4 + ((_ID_MARK + in_id) if in_id else b"\x00" * 12) + bytes([0, in_x]) + b"\x00" * 5
    tail = (b"\x01\x01\x0a\x00" + struct.pack("<10I", *(runnum or range(1, 11))) + b"\x00" * 4 + struct.pack("<I", 8) + src + b"\xff" * 4 + b"\x00\xff\x7f" + struct.pack("<H", 10)
            + b"".join(uu) + bytes([0, stereo if t1 is None else t1, 0, 0, 1, 0, stereo if t6 is None else t6, 0]) + b"\x00" * 20)
    return _blk(0x0f, 0x261b, _track_info(name, tid, fl19), flags if flags is not None else bytes([stereo]) + b"\xff\xff\x01", inserts, main, sl, tail, _blk(4, 0x4856, b"\x00" * 13 + b"\x01"))
def _view15(cells, cells80, v):
    """0x2015 [21]: the per-track view fields (cells: types of the 3 view cells, cells80: of the 2 cells in 0x2580)"""
    return _blk(0x15, 0x2015, _CELL[cells[0]](),
             (v["f6"] if "f6" in v else bytes([v["a"], 1, 0, v["s3"], v["b"], 0])) + struct.pack("<HI", v["h1"], len(v["comment"])) + v["comment"] + b"\x00" + struct.pack("<d", v["ratio"]) + b"\x00" + bytes([v["c"]])
             + b"\xfe\xff\x01" + struct.pack("<I", v["z1"]) + b"\x00\x01" + struct.pack("<H", v["h2"]) + b"\x00\x00" + bytes([v["mark"], 0]) + struct.pack("<I", v["z2"]) + b"\x00" * 3
             + bytes([v["last"]]) + b"\x00" * 3, _CELL[cells[1]]() if v["last"] else b"", b"\x00" * 4 + b"\x07" + b"\x00" * 7 + b"\x01",
             _blk(1, 0x2434, b"\x04\x00\x00\x00\x00\x00\x00\x3c\x00"), struct.pack("<I", v["number"]), _CELL[cells[2]](), b"\x00\x01\x00\x00\x00",
             _blk(5, 0x2580, b"\x00", _CELL[cells80[0]](), b"\xff\xff\x00\x00\xff\xff\x00\x00\x00\x00\xff\xff\xff\xff", _CELL[cells80[1]](), b"\x00\xff\xff"),
             b"\x00" * 4 + struct.pack("<I", v["g"]))
def _view0a(cells, cells80, cells0a, v):
    """0x200a [10]: 0x2015 + 4 view cells"""
    return _blk(0x0a, 0x200a, _view15(cells, cells80, v), struct.pack("<H", v["f0a"]), _CELL[cells0a[0]](), b"\x13\x00\x00\x09\x3d\x00\x17\x00\xff\xff\xff\xff",
             _CELL[cells0a[1]](), b"\x02\x00\x00\x00", _CELL[cells0a[2]](), _CELL[cells0a[3]]())
_AUX_VIEW = ("bbb", "bb", "b8b8")
_VIEW_DEFAULT = dict(s3=0, a=1, b=1, h1=0x5c, comment=b"", ratio=0.5, c=1, z1=4000000, h2=0x61, mark=4, z2=4000000, last=1, number=3, g=1, f0a=1)
def _aux_channel(name, tid, stereo=0, kind=1, ct=0x261e, vct=0x200d, view_cells=_AUX_VIEW, v=None, **kw):
    """aux 0x261e [1] (also click track, routing folder), master 0x261d: strip set + view block"""
    vv = dict(_VIEW_DEFAULT); vv.update(v or {})
    return _blk(kind, ct, _strip_set(name, tid, stereo, **kw), _blk(1, vct, _view0a(view_cells[0], view_cells[1], view_cells[2], vv)))

# field reader of the aux / master form (test of the builder, demotion of the 'last track' state)
def _ax_own(b,n):
    x=bytearray(b[n["pos"]:n["pos"]+7+n["size"]])
    for k in sorted(n.get("kids",[]),key=lambda k:-k["pos"]): x[k["pos"]-n["pos"]:k["pos"]-n["pos"]+7+k["size"]]=b""
    return bytes(x[9:])
def _ax_find(n,ct,i=0): return [x for x in n["kids"] if x["ct"]==ct][i]
def _ax_ctype(b,n): return {0x203a:"a" if _ax_own(b,n)==b"\x01\x01" else "A",0x203b:"b",0x2038:"8"}[n["ct"]]
def _ax_view_fields(b,va):
    v15=_ax_find(va,0x2015); o15=_ax_own(b,v15); cl=struct.unpack_from("<I",o15,8)[0]; cm=o15[12:12+cl]; o=o15[:12]+o15[12+cl:]
    cells=[_ax_ctype(b,k) for k in v15["kids"] if k["ct"] in (0x203a,0x203b,0x2038)]
    c80=[_ax_ctype(b,k) for k in _ax_find(v15,0x2580)["kids"]]
    c0a=[_ax_ctype(b,k) for k in va["kids"] if k["ct"] in (0x203a,0x203b,0x2038)]
    v=dict(f6=o[0:6],s3=o[3],a=o[0],b=o[4],h1=struct.unpack_from("<H",o,6)[0],comment=cm,ratio=struct.unpack_from("<d",o,13)[0],c=o[22],z1=struct.unpack_from("<I",o,26)[0],
           h2=struct.unpack_from("<H",o,32)[0],mark=o[36],z2=struct.unpack_from("<I",o,38)[0],last=o[45],number=struct.unpack_from("<I",o,62)[0],g=struct.unpack_from("<I",o,75)[0],
           f0a=struct.unpack_from("<H",_ax_own(b,va),0)[0])
    if not v["last"]: cells=[cells[0],"b",cells[1]]
    return (cells,c80,c0a),v
def _aux_channel_fields(b):
    t=probe.parse(b,0,len(b))[0]
    b61=_ax_find(t,0x261b); o61=_ax_own(b,b61)
    i19=_ax_own(b,_ax_find(_ax_find(b61,0x102d),0x2619)); nl=struct.unpack_from("<I",i19,0)[0]
    main=_ax_find(b61,0x260d)
    e_=[x for x in main["kids"] if x["ct"]==0x260e]
    oe=b[e_[0]["pos"]+9:e_[0]["pos"]+7+e_[0]["size"]] if e_ else b"\x00"*40+b"\x00"*4
    ol=struct.unpack_from("<I",oe,36)[0]
    def tab(n): x=_ax_own(b,_ax_find(n,0x1029)); return {i:v for i,v in enumerate(struct.unpack_from("<69i",x,1)) if v}
    sends=[x for x in b61["kids"] if x["ct"]==0x260d][1:]
    master=t["ct"]==0x261d
    q=o61.find(b"\x01\x01\x0a\x00"); run=struct.unpack_from("<10I",o61,q+4); q+=52
    il=struct.unpack_from("<I",o61,q+1)[0]; inn=o61[q+5:q+5+il]; q+=5+il+4
    in_id=o61[q+4:q+12] if o61[q:q+4]==_ID_MARK else None; in_x=o61[q+13]; q+=12+7+4+3+2
    uu=[o61[q+16*k:q+16*k+16] for k in range(10)]
    nsend=struct.unpack_from("<H",o61,4)[0]
    vb=[k for k in t["kids"] if k["ct"] in (0x200d,0x200c)][0]; va=_ax_find(vb,0x200a)
    cells,v=_ax_view_fields(b,va)
    st=1 if b"\x9c\xff\xff\xff" in _ax_own(b,_ax_find(main,0x1029)) else 0
    return dict(name=i19[4:4+nl].decode(),tid=i19[4+nl+11:4+nl+19],stereo=st,kind=struct.unpack_from("<H",b,1)[0],ct=t["ct"],vct=vb["ct"],view_cells=cells,v=v,
                flags=o61[:4],runnum=run,out_id=oe[12:20] if oe[8:12]==_ID_MARK else None,out_name=oe[40:40+ol].decode() if e_ else "",out_head=oe[:4],out_tail=oe[40+ol:],sends=nsend,
                tbl_main=tab(main),tbl_send=tab(sends[0]) if sends else None,master=master,in_name=inn.decode(),in_x=in_x,fl19=i19[-1],tb=struct.unpack_from("<H",_ax_own(b,_ax_find(main,0x260a)),8)[0],in_id=in_id,uuids=uu,t1=o61[q+161],t6=o61[q+166])

def _strip_master():
    """master strip table: the mono table with slot 64 = 0 (mono and stereo masters alike)"""
    t_ = dict(_STRIP_MONO)
    t_.pop(64)
    return t_


def _new_bus_channel(kind, name, tid, stereo, number, runnum, out_id, out_name):
    """channel block of a new aux, routing folder or master track (values of a track Pro Tools creates; STAIR_05 / STAIR_08)"""
    st = 1 if stereo else 0
    v = dict(_VIEW_DEFAULT, number=number, z2=1024000000)
    if kind == "aux":
        return _aux_channel(name, tid, st, v=v, runnum=runnum, out_id=out_id, out_name=out_name, t1=st, t6=st)
    if kind == "rfolder":
        v["f0a"] = 0
        return _aux_channel(name, tid, st, view_cells=("888", "bb", "8888"), v=v, runnum=runnum, out_id=out_id, out_name=out_name, t1=st, t6=st, fl19=1)
    if st:                                             # stereo master: assigned to the session's output
        return _aux_channel(name, tid, 0, ct=0x261d, vct=0x200c, v=v, runnum=runnum, out_id=out_id, out_name=out_name, flags=b"\x01\xff\xff\x01",
                            t1=1, t6=1, sends=0, master=True, tbl_main=_strip_master())
    return _aux_channel(name, tid, 0, ct=0x261d, vct=0x200c, v=v, runnum=runnum, out_id=None, out_name="", sends=0, master=True, tbl_main=_strip_master())


# track view entry 0x2589 and track-list entries built field by field
# View entry: forms midi (MIDI, instrument), audio (audio, routing folder), aux (aux, master), folder; 191 / 199 entries of Pro Tools saves rebuilt
# byte-identically. List entries: 0x251a 344 / 368, 0x210b 316 / 316. Values of a new track = Pro Tools' values for a new track.
def _view_cell(t):                         # small view cells: 0x203a = 01 01, 0x203b = u32 1, 0x2038 = 00, each with an empty 0x2037
    return {"a": _blk(2, 0x203a, _blk(1, 0x2037), b"\x01\x01"), "A": _blk(2, 0x203a, _blk(1, 0x2037), b"\x03\x03"),
            "b": _blk(1, 0x203b, _blk(1, 0x2037), b"\x01\x00\x00\x00"), "8": _blk(1, 0x2038, _blk(1, 0x2037), b"\x00")}[t]
_VIEW_FORMS = {"midi": ("aa", "AA", "aaaa"), "audio": ("88", "bb", "8888"), "aux": ("bb", "bb", "8bb8"), "folder": ("88", "", "8888")}
def _view_entry(form, idx, height=0x61, flag=1, mark=4, zoom=4000000, z2=4000000, ratio=0.5, lane=(0xffff, 0xffff), tail=b"\x00" * 6, dbl=None):
    head, mid, trail = _VIEW_FORMS[form]
    if dbl is None:
        dbl = -1.0 if form == "midi" else 0.0
    s0 = struct.pack("<HHH", idx, flag, height)
    s4 = bytes([0, mark, 0, 0]) + struct.pack("<I", zoom) + b"\x00\x00\x00\x17\x00"
    post = struct.pack("<d", -1.0) + b"\x00" * 4 + b"\xff" * 4
    s8 = struct.pack("<I", z2) + struct.pack("<d", ratio) + b"\x00" + struct.pack("<dd", dbl, dbl) + b"\x00"
    if form == "folder":
        return _blk(11, 0x2589, s0, _view_cell("8"), s4, _view_cell("8"), s8 + b"\x00" * 4 + post, _view_cell("8"), _view_cell("8"), _view_cell("8"), _view_cell("8"), tail + struct.pack("<H", height))
    s8 += b"\x01\x00\x00\x00"
    m = _blk(5, 0x2580, b"\x00", _view_cell(mid[0]), b"\xff\xff\x00\x00" + struct.pack("<H", lane[0]) + b"\x00" * 4 + b"\xff" * 4, _view_cell(mid[1]), b"\x00" + struct.pack("<H", lane[1]))
    return _blk(11, 0x2589, s0, _view_cell(head[0]), s4, _view_cell(head[1]), s8, m, post,
             *[_view_cell(c) for c in trail], tail + struct.pack("<H", height))

def _list_entry(kind, name, tid, number, stereo=0, f22=0, folder=0, clips=0, b7=0):
    """0x251a [10] (two per track, groups A and _blk of 0x2519)"""
    nm = name.encode("utf-8")
    return _blk(10, 0x251a, struct.pack("<HI", kind, len(nm)) + nm + bytes([stereo]) + b"\x00" * 5 + _ID_MARK + tid + struct.pack("<I", number) + bytes([f22]) + b"\x00" * 5
             + _ID_MARK + tid + bytes([stereo, 0]), _blk(1, 0x4420, b"\x00\x00"), bytes([folder, 0, stereo, 0, 1, 1, clips, b7, 0]) + b"\xfe\xff")
def _kind_entry(kind, name, tid):
    """0x210b [1] (one per track, in 0x2107)"""
    nm = name.encode("utf-8")
    return _blk(1, 0x210b, b"\x00\x00\x00" + bytes([kind]) + struct.pack("<I", len(nm)) + nm + b"\x00" * 4 + _ID_MARK + tid + b"\x00" * 16)
def _head_entry(kind, name, tid, number, stereo=0):
    """entry of the head list in the own data of 0x2519 (no block header)"""
    nm = name.encode("utf-8")
    return struct.pack("<HI", kind, len(nm)) + nm + bytes([stereo]) + b"\x00" * 5 + _ID_MARK + tid + bytes([number]) + b"\x00\x00"


_KIND_CODE = {"audio": 0, "midi": 1, "aux": 2, "rfolder": 2, "master": 5, "instrument": 7, "folder": 11}
_VIEW_FORM = {"audio": "audio", "rfolder": "audio", "midi": "midi", "instrument": "midi", "aux": "aux", "master": "aux", "folder": "folder"}




# audio clip blocks built field by field (clean room, stage 2)
# Rebuilt byte-identically from their fields: descriptor 0x1003 60 / 60 of the 2026 form, whole-file region 0x2629 314 / 327, playlist entry
# 0x1050 620 / 620 of the 49-byte form, volume 0x0f3c 3 / 3 (Pro Tools saves of the kit).
_UMID_LABEL = bytes.fromhex("060a2b340101010501010f10")          # SMPTE 330M basic UMID label (as in every descriptor)
def _file_descriptor(file_no, rate, ch, bits, frames, file_id, ft1, ft2, data_off, uid, umid_tail, ftype=3, f108=1, f119=0, f157=0, flt=0):
    st = 1 if ch == 2 else 0
    i2106 = (b"\x00" * 29 + struct.pack("<Q", ft1) + bytes([f108, 0]) + struct.pack("<H", data_off) + b"\x00" * 7 + bytes([f119]) + b"\x00" * 37 + bytes([f157])
             + b"\x00" * 5 + struct.pack("<Q", ft2) + bytes([flt]) + b"\x00\x00" + bytes([st]) + b"\x00" * 18 + uid,
             _blk(1, 0x4301, b"\x00" * 32),
             b"\x00" * 17 + bytes([st]) + _UMID_LABEL + b"\x13\x00\x00\x00" + file_id + umid_tail + b"\x00" * 7 + bytes([st]) + b"\x00" * 7)
    return _blk(9, 0x1003, struct.pack("<I", file_no), _blk(2, 0x1001, struct.pack("<IBBQQ", rate, ch, bits, frames, ftype) + _ID_MARK[:1] + file_id),
             _blk(2, 0x1033), _blk(0x26, 0x2106, *i2106), b"\x00" * 4)
def _audio_region(name, frames, clip_id, file_index, chunk, gain_index=0xffffffff, start=0, sync=0, mid=b"\x00" * 20, x=b"\x00\x00\x01\x00\x7f", channel=0):
    nm = name.encode("utf-8")
    wl = 3 if frames < 1 << 24 else 4 if frames < 1 << 32 else 5
    ws = 0 if not start else 3 if start < 1 << 24 else 4 if start < 1 << 32 else 5
    wsync = _minw(sync) if sync else 0
    vals = (start.to_bytes(ws, "little") if ws else b"") + (sync.to_bytes(wsync, "little") if wsync else b"") + frames.to_bytes(wl, "little")
    r28 = _blk(5, 0x2628, struct.pack("<I", len(nm)) + nm + bytes([0, ws << 4, (wl << 4) | wsync, 0, 0]) + vals + b"\xfe\xff" + b"\x00" * 4 + b"\xff\xff\x04\x00\x04\x00" + mid + b"\x00"
            + struct.pack("<I", gain_index) + b"\x00\x00" + clip_id)
    return _blk(11, 0x2629, r28, struct.pack("<IH", file_index, channel) + struct.pack("<ff", 1.0, 1.0) + b"\x00" * 8 + b"\xff" + clip_id + b"\x00" * 9,
             _blk(1, 0x4403, _blk(0, 0x1000, b"\x00" * 18), b"\x00"), x + chunk + struct.pack("<I", file_index) + b"\x00" * 4)
def _playlist_entry(region_index, position, mute=0, ticks=0, kind=3, k2=b"\xfe\xff", tail=b"\x00\x01\x01"):
    pos_val = OFF12 + position if ticks else position
    return _blk(3, 0x1050, _blk(10, 0x104f, bytes([mute, 0]) + struct.pack("<H", region_index) + b"\x00" * 3 + pos_val.to_bytes(5, "little") + b"\x00\x00"
                          + bytes([0x40 if ticks else 0, kind]) + k2 + b"\x00" * 4 + b"\xff" * 8 + b"\x00" * 5), tail)
def _volume_entry(name, vol_id):
    nm = name.encode("utf-8")
    return _blk(1, 0x0f3c, struct.pack("<I", len(nm)) + nm + vol_id + struct.pack("<I", 1) + b"/")


def _wav_layout(path):
    """(offset of the sample data, has 'bext', mtime as FILETIME) of a WAV file"""
    b = open(path, "rb").read()
    p, off, bext = 12, 0, False
    while p + 8 <= len(b):
        cid, ln = b[p:p + 4], struct.unpack_from("<I", b, p + 4)[0]
        bext = bext or cid == b"bext"
        if cid == b"data":
            off = p + 8
            break
        p += 8 + ln + (ln & 1)
    return off, bext, os.stat(path).st_mtime_ns // 100 + 116444736000000000           # exact (a float loses the last digits; b57)


# audio channel block 0x261c built field by field (clean room, stage 2)
# Form of a track as Pro Tools creates it: track info, 11 empty insert slots, main strip (value table 0x1029, output 0x260e,
# 3 lanes, 2 panners of 14 lanes), 10 unused send strips, running numbers, input, 10 random slot ids (UUID v4), view block 0x200b.
# Built byte-identically for all 200 audio channel blocks of Pro Tools saves that are in this form (of 410; the others carry inserts,
# sends, automation or an edited view and are not created by the writer).
def _lane0(v=0):                      # automation _lane0 without points: header, time base 0, 1 start value
    return _blk(1, 0x260a, b"\x01\x46\x01\x00" + struct.pack("<I", 20) + struct.pack("<HIHH", 0, 1, 2, 0) + b"\x00" * 8 + struct.pack("<hH", v, 0))
def _view2038(): return _blk(1, 0x2038, _blk(1, 0x2037), b"\x00")
def _view203b(): return _blk(1, 0x203b, _blk(1, 0x2037), struct.pack("<I", 1))
# strip value _strip_table 0x1029: 01, 69 x int32 (slot: value), 00 00.  Values as in every new strip of Pro Tools 2026 saves; -1440 = fader at -inf (dB x 10)
_STRIP_MONO = {2: -1440, 5: 100, 6: 100, 7: 100, 8: 100, 9: 100, 12: 100, 13: 100, 14: 100, 15: 100, 16: 100, 19: 6553600, 20: 6553600, 23: -94371840, 24: 65535,
          26: 6553600, 27: 6553600, 28: 6553600, 29: 6553600, 30: 6553600, 33: 6553600, 34: 6553600, 35: 6553600, 36: 6553600, 37: 6553600, 42: 65536, 43: 65536,
          54: 65536, 55: 65536, 64: 16842752, 67: 3276800, 68: 3276800}
_STRIP_ST_MAIN = dict(list(_STRIP_MONO.items()) + list({3: -100, 4: -100, 10: 100, 11: 100, 24: -6488065, 25: -6488065, 26: 6619135, 31: 6553600, 32: 6553600}.items()))
_STRIP_ST_SEND = dict(list(_STRIP_MONO.items()) + list({3: -100, 4: -100, 10: -100, 11: -100, 24: -6488065, 25: -6488065, 26: 6619135, 31: -6553600, 32: -6488065, 33: 6619135}.items()))
def _strip_table(t): return _blk(0x0e, 0x1029, b"\x01" + b"".join(struct.pack("<i", t.get(i, 0)) for i in range(69)) + b"\x00\x00")
def _panner(first):                    # panner 0x260c: 14 lanes
    return _blk(2, 0x260c, b"".join(b"\x01" + _lane0(v) for v in [first, first, 100, 100, 100, 100, 100, 100, 0, 0, 1, 0, 0, 0]))
_BLK485A = _blk(2, 0x485a, b"\x00\x00\x00\x00\x01")
def _audio_channel(name, tid, stereo=0, aidx=0, number=3, runnum=None, out_id=None, out_name="", out_head=b"\x02\x00\x01\x01", t1=None, t6=None, out_tail=b"\x01\x01" + b"\xff" * 8 + b"\x00" + b"\xff" * 4 + b"\x00\x0c\x01\x00",
                  in_path=0xffff, in_name="", in_id=None, uuids=None, path=(), stamp=b"\x00" * 4, v=None):
    nm, on, inn = name.encode("utf-8"), out_name.encode("utf-8"), in_name.encode("utf-8")
    f = dict(a=1, b=1, h1=0x5c, comment=b"", ratio=0.5, c1=1, w2104=bytes.fromhex("efffdfbfefffdfbf320000000000000000000000efffdfbf32000000"),
             mid=bytes.fromhex("01feff010004000000016100000004000000093d000000"), last=1, g=1)
    f.update(v or {})
    info = _blk(3, 0x102d,
             _blk(9, 0x2619, struct.pack("<I", len(nm)) + nm + b"\x01\x00\x01\x00\x00\x00\x00" + _ID_MARK + tid + b"\x00" * 4 + _ID_MARK + tid + b"\x00" * 8 + struct.pack("<I", 1) + b"\x00" * 33,
               _blk(1, 0x4301, b"\x00" * 32), b"\x00" * 4 + _ID_MARK + tid + b"\x00\x00"),
             b"\x00\x01\x00\x00\x00\x01\x00")
    inserts = _blk(1, 0x2627, struct.pack("<H", 11), *[_blk(1, 0x2625, _blk(1, 0x2626)) for _ in range(11)])
    p = -100 if stereo else 0
    main = _blk(6, 0x260d, _strip_table(_STRIP_ST_MAIN if stereo else _STRIP_MONO), b"\x01\x00",
             _blk(9, 0x260e, out_head + b"\x00" * 4 + ((_ID_MARK + out_id) if out_id else b"\x00" * 12) + b"\x00" * 16 + struct.pack("<I", len(on)) + on + out_tail),
             b"\x01", _lane0(0), b"\x01", _lane0(0), b"\x01", _lane0(-1440), _panner(p), _panner(100 if stereo else 0), b"\x00" * 9, _BLK485A)
    send = _blk(6, 0x260d, _strip_table(_STRIP_ST_SEND if stereo else _STRIP_MONO), b"\x00" * 5, _blk(2, 0x260c, b"\x00" * 14), _blk(2, 0x260c, b"\x00" * 14), b"\x00" * 9, _BLK485A)
    sends = struct.pack("<I", 10) + b"".join(send + (struct.pack("<H", i + 1) if i < 9 else b"") for i in range(10))
    uu = uuids or [__import__('uuid').uuid4().bytes for _ in range(10)]
    src = (b"\x00" + struct.pack("<I", len(inn)) + inn + b"\x00" * 4 + ((_ID_MARK + in_id) if in_id else b"\x00" * 12) + b"\x00" * 7)
    tail = (b"\x01\x01\x0a\x00" + struct.pack("<10I", *(runnum or range(1, 11))) + b"\x00" * 4 + struct.pack("<I", 8) + src + b"\xff" * 4 + b"\x00\xff\x7f" + struct.pack("<H", 10)
            + b"".join(uu) + bytes([0, stereo if t1 is None else t1, 0, 0, 1, 0, stereo if t6 is None else t6, 0]) + b"\x00" * 20)
    b61 = _blk(0x0f, 0x261b, info, bytes([stereo]) + struct.pack("<H", in_path) + b"\x01", inserts, main, sends, tail, _blk(4, 0x4856, b"\x00" * 13 + b"\x01"))
    v15 = _blk(0x15, 0x2015, _view2038(),
            bytes([f["a"], 1, 0, 0, f["b"], 0]) + struct.pack("<HI", f["h1"], len(f["comment"])) + f["comment"] + b"\x00" + struct.pack("<d", f["ratio"]) + bytes([f["c1"]]),
            _blk(2, 0x2104, _blk(1, 0x2103), f["w2104"]), f["mid"][:14] + f["mid"][14:15] + f["mid"][15:] + bytes([f["last"]]) + b"\x00" * 3,
            _view2038() if f["last"] else b"", b"\x00" * 4 + b"\x07" + b"\x00" * 7 + b"\x01", _blk(1, 0x2434, b"\x04\x00\x00\x00\x00\x00\x00\x3c\x00"), struct.pack("<I", number),
            _view2038(), b"\x00\x01\x00\x00\x00", _blk(5, 0x2580, b"\x00", _view203b(), b"\xff\xff\x00\x00\xff\xff\x00\x00\x00\x00\xff\xff\xff\xff", _view203b(), b"\x00\xff\xff"),
            b"\x00" * 4 + struct.pack("<I", f["g"]))
    plist = struct.pack("<II", 0, len(path)) + b"".join(struct.pack("<I", len(c.encode())) + c.encode() for c in path) + stamp + b"\x00" * 13
    view = _blk(0x0a, 0x200b, _blk(0x0a, 0x200a, v15, b"\x00\x00", _view2038(), b"\x13\x00\x00\x09\x3d\x00\x17\x00\xff\xff\xff\xff", _view2038(), b"\x02\x00\x00\x00", _view2038(), _view2038()), plist)
    end = b"\x00" * 17 + struct.pack("<I", aidx) + struct.pack("<I", 1) + b"\x00" * 11 + b"\x01"
    return _blk(6, 0x261c, b61, struct.pack("<I", aidx) + b"\x01\x00" + struct.pack("<H", aidx) + b"\x00\x00\xff\xff", view, end)

def _audio_channel_fields(blk, parse=None):
    """named fields of a Pro Tools 0x261c block (for the byte-compare test)"""
    t = (parse or probe.parse)(blk, 0, len(blk))[0]
    def find(n, ct, i=0): return [x for x in n["kids"] if x["ct"] == ct][i]
    def own(n):
        x = bytearray(blk[n["pos"]:n["pos"] + 7 + n["size"]])
        for k in sorted(n.get("kids", []), key=lambda k: -k["pos"]): x[k["pos"] - n["pos"]:k["pos"] - n["pos"] + 7 + k["size"]] = b""
        return bytes(x[9:])
    b61 = find(t, 0x261b); o61 = own(b61); o = own(t)
    i19 = own(find(find(b61, 0x102d), 0x2619)); nl = struct.unpack_from("<I", i19, 0)[0]
    oe = own(find(find(b61, 0x260d), 0x260e)); ol = struct.unpack_from("<I", oe, 36)[0]
    q = o61.find(b"\x01\x01\x0a\x00"); run = struct.unpack_from("<10I", o61, q + 4); q += 52
    il = struct.unpack_from("<I", o61, q + 1)[0]; inn = o61[q + 5:q + 5 + il]; q += 5 + il + 4
    in_id = o61[q + 4:q + 12] if o61[q:q + 4] == _ID_MARK else None; q += 12 + 7 + 4 + 3 + 2
    uu = [o61[q + 16 * k:q + 16 * k + 16] for k in range(10)]
    vb = find(t, 0x200b); pl = own(vb); n = struct.unpack_from("<I", pl, 4)[0]; r = 8; path = []
    for _ in range(n):
        ln = struct.unpack_from("<I", pl, r)[0]; path.append(pl[r + 4:r + 4 + ln].decode("utf-8")); r += 4 + ln
    v15 = find(find(vb, 0x200a), 0x2015); o15 = own(v15); cl = struct.unpack_from("<I", o15, 8)[0]; cm = o15[12:12 + cl]; o15 = o15[:12] + o15[12 + cl:]
    w = own(find(v15, 0x2104))
    return dict(name=i19[4:4 + nl].decode("utf-8"), tid=i19[4 + nl + 11:4 + nl + 19], stereo=o61[0], aidx=o[0], t1=o61[q + 161], t6=o61[q + 166], out_head=oe[:4], number=struct.unpack_from("<I", o15, 22 + 27 + 13)[0],
                runnum=run, out_id=oe[12:20] if oe[8:12] == _ID_MARK else None, out_name=oe[40:40 + ol].decode("utf-8"), out_tail=oe[40 + ol:], in_path=struct.unpack_from("<H", o61, 1)[0],
                in_name=inn.decode("utf-8"), in_id=in_id, uuids=uu, path=tuple(path), stamp=pl[r:r + 4],
                v=dict(a=o15[0], b=o15[4], h1=struct.unpack_from("<H", o15, 6)[0], comment=cm, ratio=struct.unpack_from("<d", o15, 13)[0], c1=o15[21], w2104=w,
                       mid=o15[22:45], last=o15[45], g=struct.unpack_from("<I", o15, 22 + 27 + 13 + 4 + 5 + 4)[0]))


def cmd_aucheck(*files):
    """audio channel blocks 0x261c of each FILE: equal to the block built from their named fields / other form (inserts, sends,
    automation: not built). One line per file. Example: python3 ptx_edit.py aucheck a.ptx"""
    if not files:
        probe.fail("no file given", "usage: aucheck <file.ptx> [more files]")
    tot = ok = oth = 0
    for f in files:
        raw, d, tree = descramble_file(f)
        d = bytes(d)
        n = k = x = 0
        for top in [t for t in tree if t["ct"] == 0x2624]:
            for ch in [c for c in top["kids"] if c["ct"] == 0x261C]:
                blk = d[ch["pos"]:ch["pos"] + 7 + ch["size"]]
                n += 1
                try:
                    same = _audio_channel(**_audio_channel_fields(blk)) == blk
                except (struct.error, IndexError, UnicodeDecodeError, ValueError):
                    x += 1
                    continue
                k += 1 if same else 0
        tot, ok, oth = tot + n, ok + k, oth + x
        print("%s  %d identical, %d other form, of %d audio channel blocks  %s" % ("ok       " if k + x == n else "DIFFERENT", k, x, n, f))
    print("%d of %d audio channel blocks equal the built ones, %d in another form, %d different" % (ok, tot, oth, tot - ok - oth))


# directory block 0x0002 built from the block tree (clean room, stage 1)
# Layout (all saves): u32 records; record = u32 path length, path elements (u16 block type, u32 position of the parent block or ff ff ff ff
# for a top-level block, u8 list flag, u32 1-based item index), u32 references, reference = 01, u16 4c, u16 c, c x u32 block position, 6 x 00.
# Records: one per top-level block type (a list block also references its items), a fixed set of nested blocks, and per list item its
# sub-blocks (0x251a / 0x251c entries, 0x2627 of a channel). Sorted by (type, index) along the path.
_DIR_LIST = {0x0f3d: 0x0f3c, 0x1015: 0x1014, 0x1054: 0x1052, 0x1055: None, 0x1058: 0x1057, 0x2424: 0x2423, 0x2426: 0x2425, 0x2519: 0x251a, 0x2624: "all",
        0x4829: None, 0x4828: None, 0x251b: 0x251c}
_DIR_FIXED = [(0x1015, 0x4829), (0x1054, 0x4828), (0x2016, 0x258b, 0x2501), (0x2016, 0x258b, 0x258a, 0x2581, 0x2056), (0x2016, 0x258b, 0x258a, 0x2581, 0x2066),
         (0x206a, 0x2074), (0x207b, 0x4530), (0x2428, 0x1054), (0x2428, 0x1054, 0x4828), (0x242e, 0x1058), (0x2430, 0x1055),
         (0x2587, 0x2551, 0x258b, 0x2501), (0x2587, 0x2551, 0x258b, 0x2553, 0x2583, 0x2581, 0x2056), (0x2587, 0x2551, 0x258b, 0x2553, 0x2583, 0x2581, 0x2066),
         (0x2587, 0x2551, 0x258b, 0x258a, 0x2581, 0x2056), (0x2587, 0x2551, 0x258b, 0x258a, 0x2581, 0x2066), (0x2597, 0x2588, 0x2056), (0x2597, 0x2588, 0x2066)]
_DIR_NONE = 0xffffffff
def _dir_ref(*pos):
    return b"\x01" + struct.pack("<HH", 4 * len(pos), len(pos)) + b"".join(struct.pack("<I", p) for p in pos) + b"\x00" * 6
def _dir_kid(n, ct, i=0):
    k = [x for x in n["kids"] if x["ct"] == ct]
    return k[i] if len(k) > i else None
def _dir_split251a(n):
    """0x2519: (group A, group B) of its 0x251a children; B = the contiguous run after the u32 count that follows group A"""
    a = [k for k in n["kids"] if k["ct"] == 0x251a]
    for i in range(1, len(a)):
        if a[i]["pos"] - (a[i - 1]["pos"] + 7 + a[i - 1]["size"]) == 4:
            return a[:i], a[i:]
    return [], a
def _dir_records(tree):
    """[(path [(ct, parent pos, flag, index)], [_dir_ref bytes])] in file order"""
    out = []
    tops = {}
    for n in tree[:-1]:
        if n["pos"] > 20:                                                    # the header pseudo-block at 20 has no record
            tops.setdefault(n["ct"], n)
    for ct, n in tops.items():
        fl = 1 if ct in _DIR_LIST else 0
        refs = [_dir_ref(n["pos"])]
        if ct == 0x2519:
            items = _dir_split251a(n)[1]
            refs += [_dir_ref(k["pos"]) for k in items]
        elif _DIR_LIST.get(ct) == "all":
            refs += [_dir_ref(k["pos"]) for k in n["kids"]]
        elif _DIR_LIST.get(ct):
            refs += [_dir_ref(k["pos"]) for k in n["kids"] if k["ct"] == _DIR_LIST[ct]]
        out.append(([(ct, _DIR_NONE, fl, 0)], refs))
    for path in _DIR_FIXED:
        n, el = tops.get(path[0]), [(path[0], _DIR_NONE, 1 if path[0] in _DIR_LIST else 0, 0)]
        for ct in path[1:]:
            if n is None:
                break
            c = _dir_kid(n, ct)
            el.append((ct, n["pos"], 1 if ct in _DIR_LIST else 0, 0))
            n = c
        if n is not None and len(el) == len(path):
            refs = [_dir_ref(n["pos"])]
            lct = _DIR_LIST.get(path[-1])
            if lct and lct != "all":
                refs += [_dir_ref(k["pos"]) for k in n["kids"] if k["ct"] == lct]
            out.append((el, refs))
    n = tops.get(0x1040)
    if n and _dir_kid(n, 0x1041):
        aa = [x for x in n["kids"] if x["ct"] == 0x1041]
        a = aa[-1]
        k2 = [x for y in aa for x in y["kids"] if x["ct"] == 0x1042]
        out.append(([(0x1040, _DIR_NONE, 0, 0), (0x1041, n["pos"], 0, 0), (0x1042, a["pos"], 0, 0)], [_dir_ref(*[x["pos"] for x in k2])]))
    n = tops.get(0x2519)
    if n:
        ga, gb = _dir_split251a(n)
        h = len(gb)
        out.append(([(0x2519, _DIR_NONE, 0, 0), (0x251a, n["pos"], 0, 0)], [_dir_ref(*[x["pos"] for x in ga])]))
        for i, k in enumerate(gb, 1):
            out.append(([(0x2519, _DIR_NONE, 1, i), (0x251a, n["pos"], 0, 0)], [_dir_ref(k["pos"])]))
        b = _dir_kid(n, 0x251b)
        if b:
            cs = [x for x in b["kids"] if x["ct"] == 0x251c]
            out.append(([(0x2519, _DIR_NONE, 1, h), (0x251b, n["pos"], 1, 0)], [_dir_ref(b["pos"])] + [_dir_ref(x["pos"]) for x in cs]))
            for j, x in enumerate(cs, 1):
                out.append(([(0x2519, _DIR_NONE, 1, h), (0x251b, n["pos"], 1, j), (0x251c, b["pos"], 0, 0)], [_dir_ref(x["pos"])]))
        c = _dir_kid(n, 0x2716)
        if c:
            out.append(([(0x2519, _DIR_NONE, 1, h), (0x2716, n["pos"], 0, 0)], [_dir_ref(c["pos"])]))
    n = tops.get(0x2624)
    if n:
        for i, k in enumerate(n["kids"], 1):
            if k["ct"] == 0x2621:
                t = _dir_kid(k, 0x2627)
                if t:
                    out.append(([(0x2624, _DIR_NONE, 1, i), (0x2621, n["pos"], 0, 0), (0x2627, k["pos"], 0, 0)], [_dir_ref(t["pos"])]))
            else:
                b = _dir_kid(k, 0x261b)
                t = _dir_kid(b, 0x2627) if b else None
                if t:
                    out.append(([(0x2624, _DIR_NONE, 1, i), (k["ct"], n["pos"], 0, 0), (0x261b, k["pos"], 0, 0), (0x2627, b["pos"], 0, 0)], [_dir_ref(t["pos"])]))
    return out
def _dir_build(tree, order=None):
    recs = _dir_records(tree)
    recs.sort(key=order or (lambda r: [(ct, ix) for ct, pos, fl, ix in r[0]]))
    body = struct.pack("<I", len(recs))
    for path, refs in recs:
        body += struct.pack("<I", len(path)) + b"".join(struct.pack("<HIBI", *e) for e in path) + struct.pack("<I", len(refs)) + b"".join(refs)
    return body


def cmd_dircheck(*files):
    """is the directory block 0x0002 of each FILE equal to the one built from its block tree? Prints one line per file.
    Example: python3 ptx_edit.py dircheck a.ptx b.ptx"""
    if not files:
        probe.fail("no file given", "usage: dircheck <file.ptx> [more files]")
    bad = 0
    for f in files:
        raw, d, tree = descramble_file(f)
        d = bytes(d)
        last = tree[-1]
        if last["ct"] != 0x0002:
            probe.fail("%s: last block is 0x%04x, not the directory 0x0002" % (f, last["ct"]), "unknown layout")
        same = _dir_build(tree) == d[last["pos"] + 9:last["pos"] + 7 + last["size"]]
        bad += 0 if same else 1
        print("%s  %s" % ("identical" if same else "DIFFERENT", f))
    print("%d of %d directories equal the built ones" % (len(files) - bad, len(files)))


def cmd_rebuilddir(src, dst):
    """write SRC with its directory block 0x0002 rebuilt from the block tree (no byte of the old directory is kept).
    Example: python3 ptx_edit.py rebuilddir in.ptx out.ptx"""
    raw, d, tree = descramble_file(src)
    d = bytes(d)
    last = tree[-1]
    if last["ct"] != 0x0002 or last["pos"] + 7 + last["size"] != len(d):
        probe.fail("the directory 0x0002 is not the last block of %s" % src, "unknown layout; nothing written")
    body = _dir_build(tree)
    out = d[:last["pos"] + 3] + struct.pack("<I", len(body) + 2) + d[last["pos"] + 7:last["pos"] + 9] + body
    write_new(dst, scramble(out))
    print("wrote %s: directory rebuilt (%d -> %d bytes, %s)" % (dst, last["size"] - 2, len(body), "identical" if body == d[last["pos"] + 9:] else "changed"))


# setfolder (track inside a basic / routing folder)
_FNODE = b"\x00" * 5 + b"\x2a\x00\x00\x00"


def _folder_map(d, tree):
    """(block 0x210c, [(folder id, [member ids])]) - the folder membership table. Layout (STAIR_08, 7 saves): u32 folders, per folder
    5 x 00 | 2a 00 00 00 | track id (8) | u32 members | per member 5 x 00 | 2a 00 00 00 | track id. Only folders WITH members are listed, in
    track order; a nested folder is a member of its parent (and gets an entry of its own once it has members: flat table)."""
    b = _paths(tree).get((0x210c,), [])
    if len(b) != 1:
        probe.fail("membership block 0x210c found %d times" % len(b), "unknown layout (older session version?); nothing written")
    b = b[0]
    p, end = b["pos"] + 9, b["pos"] + 7 + b["size"]
    def node(p):
        if d[p:p + 9] != _FNODE or p + 17 > end:
            probe.fail("membership block 0x210c: entry at %d not in the known layout" % p, "unknown layout; nothing written")
        return d[p + 9:p + 17], p + 17
    out = []
    n = struct.unpack_from("<I", d, p)[0]; p += 4
    for _ in range(n):
        fid, p = node(p)
        m = struct.unpack_from("<I", d, p)[0]; p += 4
        kids = []
        for _ in range(m):
            k, p = node(p)
            kids.append(k)
        out.append((fid, kids))
    if p != end:
        probe.fail("membership block 0x210c: %d bytes left over" % (end - p), "unknown layout; nothing written")
    return b, out


def cmd_emptytrack(src, dst, track):
    """empty the playlist of the MIDI / instrument TRACK (no clip on it). Fields (STAIR_08 S5, a MIDI track made by Pro Tools):
    route 0x1057 = u32 length + name, u32 clip entries, the entries 0x1056, then 0x2502; empty = count 0 and no 0x1056. The regions stay
    in the clip list. Example: python3 ptx_edit.py emptytrack in.ptx out.ptx Keys"""
    raw, d, tree = descramble_file(src)
    d = bytes(d)
    dec = _decoder()
    routes = dec.route_names(d, tree)
    if track not in routes:
        probe.fail("track '%s' has no MIDI route" % track, "MIDI / instrument tracks of this session: %s" % routes)
    rt = [k for k in dec.find(tree, 0x1058)["kids"] if k["ct"] == 0x1057][routes.index(track)]
    nl = struct.unpack_from("<I", d, rt["pos"] + 9)[0]
    cp = rt["pos"] + 13 + nl
    ent = [k for k in rt["kids"] if k["ct"] == 0x1056]
    if struct.unpack_from("<I", d, cp)[0] != len(ent) or (ent and ent[0]["pos"] != cp + 4):
        probe.fail("route of '%s': entry count %d, %d entry blocks" % (track, struct.unpack_from("<I", d, cp)[0], len(ent)), "unknown layout; nothing written")
    if not ent:
        probe.fail("track '%s' has no clip on its playlist" % track, "nothing to do")
    E = [{"p": cp, "ol": 4, "nb": struct.pack("<I", 0), "enc": None}] + [{"p": k["pos"], "ol": 7 + k["size"], "nb": b"", "enc": rt["pos"]} for k in ent]
    tn_ = struct.pack("<I", len(track.encode("utf-8"))) + track.encode("utf-8")       # 'has clips' flag of both 0x251a = 0 (STAIR_08 S5)
    for x_ in _paths(tree)[(0x2519, 0x251a)]:
        b_ = d[x_["pos"]:x_["pos"] + 7 + x_["size"]]
        if b_[11:11 + len(tn_)] == tn_ and b_[-5] == 1:
            E.append({"p": x_["pos"] + len(b_) - 5, "ol": 1, "nb": b"\x00", "enc": None})
    write_new(dst, scramble(_splice2(d, tree, E)))
    print("wrote %s: playlist of '%s' emptied (%d clip entr%s removed)" % (dst, track, len(ent), "y" if len(ent) == 1 else "ies"))


def cmd_setfolder(src, dst, track, folder, *opts):
    """put TRACK inside the folder track FOLDER (basic folder or routing folder; nested folders allowed). Field: the membership table
    0x210c (see _folder_map); the channel blocks and track lists hold nothing about it (STAIR_08: Pro Tools changes only 0x210c).
    Rule kept from Pro Tools saves: the members follow their folder in track order - TRACK must sit directly behind FOLDER and its present
    members (this writer does not reorder tracks). force=1 skips that check (test of what Pro Tools does with it).
    Example: python3 ptx_edit.py setfolder in.ptx out.ptx Vox Band"""
    o = dict(x.split("=", 1) for x in opts if "=" in x)
    if set(o) - {"force"} or len(o) != len(opts):
        probe.fail("unknown option in %s" % list(opts), "use force=1 or nothing")
    raw, d, tree = descramble_file(src)
    d = bytes(d)
    dec = _decoder()
    names = [t["name"] for t in dec.tracks(d, tree, [])]
    top = dec.find(tree, 0x2624)
    for n_ in (track, folder):
        if n_ not in names:
            probe.fail("track '%s' not found" % n_, "tracks: %s" % names)
    if not top or len(top["kids"]) != len(names) or track == folder:
        probe.fail("channel blocks do not match the track list, or TRACK = FOLDER", "give two different track names")
    ids = []
    for k in top["kids"]:
        m = re.search(rb"\x2a\x00\x00\x00(.{8})\x00\x00\x00\x00\x2a\x00\x00\x00\1", d[k["pos"]:k["pos"] + 7 + k["size"]], re.S)
        if not m:
            probe.fail("track id of channel block %d not found" % len(ids), "unknown layout; nothing written")
        ids.append(m.group(1))
    ti, fi = names.index(track), names.index(folder)
    fch = top["kids"][fi]
    kc = [x["ct"] for x in probe.walk([fch])]
    if not (fch["ct"] == 0x263B or (fch["ct"] == 0x261E and kc.count(0x2038) > kc.count(0x203B))):
        probe.fail("'%s' is not a folder track (channel block 0x%04x)" % (folder, fch["ct"]), "create it with addtrack3 kind=folder or kind=rfolder")
    blk, fmap = _folder_map(d, tree)
    if any(ids[ti] in kids for _, kids in fmap):
        probe.fail("'%s' is already inside a folder" % track, "this writer does not move members; nothing written")
    kids_of = dict(fmap)
    def desc(i_):
        out_ = []
        for k_ in kids_of.get(i_, []):
            out_ += [k_] + desc(k_)
        return out_
    if ids[fi] in desc(ids[ti]):
        probe.fail("'%s' is inside '%s'" % (folder, track), "a folder cannot go into its own member")
    inside = set(desc(ids[fi]))
    if o.get("force") != "1" and (ti <= fi or any(ids[j] not in inside for j in range(fi + 1, ti))):
        probe.fail("'%s' does not sit directly behind '%s' and its members (track order: %s)" % (track, folder, names),
                   "add the member right after its folder (newsong: list it behind the folder), or force=1 for a test")
    kids_of.setdefault(ids[fi], []).append(ids[ti])
    order = [i_ for i_ in ids if i_ in kids_of]                                # folders with members, in track order
    body = struct.pack("<I", len(order))
    for i_ in order:
        ks = sorted(kids_of[i_], key=ids.index)
        body += _FNODE + i_ + struct.pack("<I", len(ks)) + b"".join(_FNODE + k_ for k_ in ks)
    out = _splice2(d, tree, [{"p": blk["pos"] + 9, "ol": blk["size"] - 2, "nb": body, "enc": blk["pos"]}])
    write_new(dst, scramble(out))
    print("wrote %s: '%s' inside folder '%s' (%d member%s)" % (dst, track, folder, len(kids_of[ids[fi]]), "" if len(kids_of[ids[fi]]) == 1 else "s"))


Q_TICKS = 960000                                                                  # file ticks per quarter note (ticks of 960 PPQ x 1000)
CHORDS = {"": (0, 4, 7), "m": (0, 3, 7), "7": (0, 4, 7, 10), "maj7": (0, 4, 7, 11), "m7": (0, 3, 7, 10), "dim": (0, 3, 6), "aug": (0, 4, 8), "sus4": (0, 5, 7)}
ROOTS = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}


def _note_spec(spec):
    """notes from a text spec -> [(start ticks, key, length ticks, velocity)], times in quarter notes:
    'q:key:len:vel;q:key:len:vel;...'   explicit notes, e.g. '0:60:1:100;1:64:1:90'
    'range:LO:HI[:len[:vel]]'           one note per key LO..HI (chromatic), each `len` quarters (default 1, velocity 100)
    'chords:C,Am,F,G7[:len[:vel]]'      root-position chords from C4 = 60 (C, Cm, C7, Cmaj7, Cm7, Cdim, Caug, Csus4), `len` quarters each
    '@file'                             the same text read from a file (one spec per line, lines joined with ';')."""
    if spec.startswith("@"):
        if not os.path.isfile(spec[1:]):
            probe.fail("note file %s not found" % spec[1:], "give @<path to a text file>")
        spec = ";".join(l.strip() for l in open(spec[1:]) if l.strip() and not l.startswith("#"))
    out = []
    def num(v, what):
        try:
            return float(v)
        except ValueError:
            probe.fail("%s '%s' is not a number" % (what, v), "times and lengths in quarter notes, e.g. 1.5")
    if spec.startswith("range:"):
        p = spec.split(":")[1:]
        lo, hi = int(p[0]), int(p[1])
        ln, vel = num(p[2], "length") if len(p) > 2 else 1.0, int(p[3]) if len(p) > 3 else 100
        out = [(i * ln, k, ln, vel) for i, k in enumerate(range(lo, hi + 1))]
    elif spec.startswith("chords:"):
        p = spec.split(":")[1:]
        ln, vel = num(p[1], "length") if len(p) > 1 else 4.0, int(p[2]) if len(p) > 2 else 100
        for i, c in enumerate(p[0].split(",")):
            r = 2 if len(c) > 1 and c[1] in "#b" else 1
            if c[:r] not in ROOTS or c[r:] not in CHORDS:
                probe.fail("chord '%s' unknown" % c, "roots C .. B with # / b, kinds %s" % ",".join(k or "(major)" for k in CHORDS))
            out += [(i * ln, 60 + ROOTS[c[:r]] + iv, ln, vel) for iv in CHORDS[c[r:]]]
    else:
        for item in [x for x in spec.split(";") if x.strip()]:
            p = item.split(":")
            if len(p) != 4:
                probe.fail("note '%s' needs 4 fields" % item, "q:key:len:vel, e.g. 0:60:1:100")
            out.append((num(p[0], "start"), int(p[1]), num(p[2], "length"), int(p[3])))
    notes = []
    for q, k, ln, v in out:
        if not (0 <= k <= 127 and 1 <= v <= 127 and ln > 0 and q >= 0):
            probe.fail("note start %s key %s length %s velocity %s out of range" % (q, k, ln, v), "key 0..127, velocity 1..127, length > 0, start >= 0")
        notes.append((int(round(q * Q_TICKS)), k, int(round(ln * Q_TICKS)), v))
    if not notes:
        probe.fail("no notes in the spec", "see the forms in the help of setnotes")
    return sorted(notes)


def _ctl_spec(spec):
    """split a setnotes spec into (note spec, controller series, SysEx list). Extra items, separated by ';' like notes, times in
    quarter notes:  cc:<number 0..127>:<q>:<value 0..127>   pb:<q>:<value -8192..8191>   pc:<q>:<program 0..127>
    cp:<q>:<channel pressure 0..127>   pp:<key>:<q>:<poly pressure 0..127>   sx:<q>:<hex payload without f0 / f7>
    Returns note spec text, {(kind, number): [(ticks, value)]} with kind 1 pitch bend, 2 controller, 3 program, 4 channel pressure,
    5 poly pressure, and [(ticks, payload bytes)]."""
    if spec.startswith("@") or spec.startswith(("range:", "chords:")) and ";" not in spec:
        return spec, {}, []
    rest, ser, sx = [], {}, []
    def tk(v):
        try:
            q = float(v)
        except ValueError:
            probe.fail("time '%s' is not a number" % v, "times in quarter notes, e.g. cc:7:1.5:100")
        if q < 0:
            probe.fail("time %s is negative" % v, "times start at 0")
        return int(round(q * Q_TICKS))
    def iv(v, lo, hi, what):
        try:
            x = int(v)
        except ValueError:
            x = None
        if x is None or not lo <= x <= hi:
            probe.fail("%s '%s' out of range" % (what, v), "%s: %d .. %d" % (what, lo, hi))
        return x
    forms = {"cc": 4, "pb": 3, "pc": 3, "cp": 3, "pp": 4, "sx": 3}
    for item in [x.strip() for x in spec.split(";") if x.strip()]:
        p = item.split(":")
        if p[0] not in forms:
            rest.append(item)
            continue
        if len(p) != forms[p[0]]:
            probe.fail("item '%s' needs %d fields" % (item, forms[p[0]]), "cc:num:q:val  pb:q:val  pc:q:val  cp:q:val  pp:key:q:val  sx:q:hex")
        if p[0] == "cc":
            ser.setdefault((2, iv(p[1], 0, 127, "controller number")), []).append((tk(p[2]), iv(p[3], 0, 127, "controller value")))
        elif p[0] == "pb":
            ser.setdefault((1, 0), []).append((tk(p[1]), iv(p[2], -8192, 8191, "pitch bend")))
        elif p[0] == "pc":
            ser.setdefault((3, 0), []).append((tk(p[1]), iv(p[2], 0, 127, "program")))
        elif p[0] == "cp":
            ser.setdefault((4, 0), []).append((tk(p[1]), iv(p[2], 0, 127, "channel pressure")))
        elif p[0] == "pp":
            ser.setdefault((5, iv(p[1], 0, 127, "key")), []).append((tk(p[2]), iv(p[3], 0, 127, "poly pressure")))
        else:
            try:
                pay = bytes.fromhex(p[2])
            except ValueError:
                pay = b""
            if not pay or any(b_ > 127 for b_ in pay):
                probe.fail("SysEx payload '%s' is not hex data of 7-bit bytes" % p[2], "payload without f0 and f7, e.g. sx:0:7e7f0901")
            sx.append((tk(p[1]), pay))
    return ";".join(rest), {k: sorted(v) for k, v in ser.items()}, sorted(sx)


def _midi_chunk(notes, cid, plain=False, ctl=None, sysex=None):
    """one chunk of the MIDI data block 0x2000 for notes only (layout from T0 / T17 / T30 / MAX_midi, results/mining_20261112):
    'MdChun' 01 00 u32 L | 'MdNLB' 03 00 u32 22 + 64 n | u32 n | n x 35 (start u40 = 10^12 + ticks, 00 00 40, key, length u40,
    00 00 40, velocity, release velocity 64, f64 2.0, f64 2.0) | u32 n, u32 11, n x 11 (key, length u40, 00 00 40, velocity, 64) |
    u32 n, 03 00 12 00 00 00, 18 n zero bytes | u32 0 (no controller sets) | 'MdES' 01 00 u32 15 ('MdTEL' 01 00 u32 4, u32 0) | u32 0 |
    2a 00 00 00 + 8-byte chunk id | 01. Lists 2 / 3 are derived data; Pro Tools rebuilds them."""
    n = len(notes)                                                            # plain=True: start as plain ticks (imported lists), else 10^12 + ticks (drawn clips)
    s1 = b"".join(((0 if plain else 10 ** 12) + t).to_bytes(5, "little") + b"\x00\x00\x40" + bytes([k]) + ln.to_bytes(5, "little") + b"\x00\x00\x40" + bytes([v, 64])
                  + struct.pack("<dd", 2.0, 2.0) for t, k, ln, v in notes)
    s2 = b"".join(bytes([k]) + ln.to_bytes(5, "little") + b"\x00\x00\x40" + bytes([v, 64]) for t, k, ln, v in notes)
    nlb = struct.pack("<I", n) + s1 + struct.pack("<II", n, 11) + s2 + struct.pack("<I", n) + b"\x03\x00\x12\x00\x00\x00" + b"\x00" * (18 * n)
    nlb = b"MdNLB\x03\x00" + struct.pack("<I", len(nlb)) + nlb
    # controller sets and SysEx (layout / 9.49, rebuilt byte for byte against chunks in saved sessions):
    # u32 sets | per set 'MdCDS' 02 00 u32 L ('Mdss' 01 00 u32 25: kind, number, 5 x 00, ff ff, 16 x 00 | 'MdCD' 01 00 u32 4 + 12 n: u32 n,
    # n x (time u40, 00 00 40, i32 value)), sets in the order pitch bend, controllers by number, channel pressure, program, poly pressure | 'MdES' 01 00 u32 11 + T ('MdTEL' 01 00 u32 T: u32 m,
    # m x (time u40, 00 00 40, 01 00, u32 payload + 5, 00, u32 payload length, payload)) | u32 0 | 2a 00 00 00 + chunk id | 01
    base = 0 if plain else 10 ** 12
    sets = b""
    for (kind, num), pts in sorted((ctl or {}).items(), key=lambda x_: ({1: 0, 2: 1, 4: 2, 3: 3, 5: 4}.get(x_[0][0], 9), x_[0][1])):   # order of Pro Tools' own save (job h38): pitch bend, controllers, channel pressure, program, poly pressure
        cd = struct.pack("<I", len(pts)) + b"".join((base + t).to_bytes(5, "little") + b"\x00\x00\x40" + struct.pack("<i", v) for t, v in pts)
        ss = bytes([kind, num]) + b"\x00" * 5 + b"\xff\xff" + b"\x00" * 16
        body_ = b"Mdss\x01\x00" + struct.pack("<I", len(ss)) + ss + b"MdCD\x01\x00" + struct.pack("<I", len(cd)) + cd
        sets += b"MdCDS\x02\x00" + struct.pack("<I", len(body_)) + body_
    tel = struct.pack("<I", len(sysex or [])) + b"".join((base + t).to_bytes(5, "little") + b"\x00\x00\x40\x01\x00" + struct.pack("<I", len(pay) + 5) + b"\x00"
                                                        + struct.pack("<I", len(pay)) + pay for t, pay in (sysex or []))
    rest = (struct.pack("<I", len(ctl or {})) + sets + b"MdES\x01\x00" + struct.pack("<I", 11 + len(tel)) + b"MdTEL\x01\x00" + struct.pack("<I", len(tel)) + tel
            + b"\x00\x00\x00\x00" + b"\x2a\x00\x00\x00" + cid + b"\x01")
    body = nlb + rest
    assert len(nlb) == 33 + 64 * n
    return b"MdChun\x01\x00" + struct.pack("<I", len(body)) + body


def cmd_setnotes(src, dst, track, spec, *opts):
    """give MIDI / instrument TRACK its OWN clip with the notes of SPEC (see _note_spec: explicit, range, chords, @file).
    Adds one notes-only chunk to 0x2000 (u32 chunk count +1), one region (0x2633 wrapper > 0x2628 record cloned from the track's
    current region with a new name, length rounded up to whole bars of 4 quarters, new 16-byte clip id, u32 = index of the new chunk)
    to the library 0x2634 (u32 count +1), and points the track's first playlist entry 0x104F (u16 at data +2) to the new region.
    Other tracks keep their clips; the old region stays in the clip list (as Pro Tools keeps unused clips). One splice.
    Option name=<region name> (default <track>-01, next free number).
    Example: python3 ptx_edit.py setnotes in.ptx out.ptx Bass "chords:C,Am,F,G7:4:96" """
    import uuid
    raw, d, tree = descramble_file(src)
    d = bytes(d)
    dec = _decoder()
    o = dict(x.split("=", 1) for x in opts if "=" in x)
    nspec, ctl, sysex = _ctl_spec(spec)                                         # controllers and SysEx beside the notes
    notes = _note_spec(nspec) if nspec or not (ctl or sysex) else []
    routes = dec.route_names(d, tree)
    if track not in routes:
        probe.fail("track '%s' has no MIDI route" % track, "MIDI / instrument tracks of this session: %s" % routes)
    par = dec.find(tree, 0x1058)
    rt = [k for k in par["kids"] if k["ct"] == 0x1057][routes.index(track)]
    ent = next((n for n in probe.walk(rt["kids"]) if n["ct"] == 0x104F and n["size"] >= 16), None)
    lib, blk = dec.find(tree, 0x2634), next((t for t in tree if t["ct"] == 0x2000), None)
    if ent is None and lib and blk:                                              # empty playlist (new track of addtrack4 / emptytrack)
        return _setnotes_empty(d, tree, dst, track, rt, lib, blk, notes, ctl, sysex, o, dec)
    if not lib or not blk:
        probe.fail("no clip library 0x2634 or MIDI data block 0x2000", "use a session with at least one MIDI clip")
    wraps = [w for w in lib["kids"] if w["ct"] == 0x2633]
    cur = struct.unpack_from("<H", d, ent["pos"] + 11)[0]
    if cur >= len(wraps) or struct.unpack_from("<I", d, lib["pos"] + 9)[0] != len(wraps):
        probe.fail("region index %d / library count do not match %d wrappers" % (cur, len(wraps)), "unknown layout; nothing written")
    w = wraps[cur]
    rb = w["kids"][0] if w["kids"] and w["kids"][0]["ct"] == 0x2628 else None
    if rb is None:
        probe.fail("wrapper of region %d holds no 0x2628 record" % cur, "unknown layout; nothing written")
    rec = bytearray(d[rb["pos"] + 9:rb["pos"] + 7 + rb["size"]])
    ln = struct.unpack_from("<I", rec, 0)[0]
    names = [r["name"] for r in dec.regions(d, tree, [])]
    nm = o.get("name")
    if not nm:
        k = 1
        while "%s-%02d" % (track, k) in names:
            k += 1
        nm = "%s-%02d" % (track, k)
    if nm in names:
        probe.fail("region name '%s' exists" % nm, "choose another name=")
    q = 4 + ln
    flag, b1, b2, b3, ex = rec[q:q + 5]
    widths = [b1 >> 4, b2 >> 4, b3 >> 4, b3 & 15]
    vlen = sum(widths)
    if widths[0] != 0 or widths[2] or widths[3] or widths[1] not in (4, 5):
        probe.fail("source region widths %s (start must be 0, length 4 or 5 bytes)" % widths, "use a clip that starts at its source start (unedited clip)")
    bar = 4 * Q_TICKS
    last_ = max([t + l for t, k, l, v in notes] + [t for pts in ctl.values() for t, v in pts] + [t for t, pay in sysex] + [0])
    length = max(bar, -(-last_ // bar) * bar)
    if length >= 1 << 40:
        probe.fail("clip length %d ticks is too large" % length, "times and lengths are in QUARTER notes (not ticks), e.g. range:36:72:0.25:80")
    lw = 4 if length < 1 << 32 else 5
    vals = length.to_bytes(lw, "little")
    tail = bytes(rec[q + 5 + vlen:])
    if len(tail) < 16:
        probe.fail("region record too short for a clip id", "unknown layout; nothing written")
    tail = tail[:-16] + _rnd(16)                                       # new clip id (random, like a marker id: kept by Pro Tools)
    nn = nm.encode("utf-8")
    new_rec = struct.pack("<I", len(nn)) + nn + bytes([flag, b1, (lw << 4) | (b2 & 15), b3, ex]) + vals + tail
    child = d[rb["pos"]:rb["pos"] + 3] + struct.pack("<I", len(new_rec) + 2) + b"\x28\x26" + new_rec
    wdata = child + struct.pack("<I", 0)
    nchunk = struct.unpack_from("<I", d, blk["pos"] + 9)[0]
    wdata = wdata[:-4] + struct.pack("<I", nchunk)
    wrap = d[w["pos"]:w["pos"] + 3] + struct.pack("<I", len(wdata) + 2) + b"\x33\x26" + wdata
    wrap = _midi_clip_record(nm, length, _rnd(16), nchunk)          # built from fields (the clone above is kept only as the layout check)
    ids = {}                                                                     # new chunk id: session part of an existing chunk id, counter = max + 8
    for m in re.finditer(rb"\x2a\x00\x00\x00(.{4})(.{4})", d, re.S):
        ids.setdefault(m.group(1), set()).add(struct.unpack("<I", m.group(2))[0])
    x = d[blk["pos"] + 9:blk["pos"] + 7 + blk["size"]]
    j = x.rfind(b"\x2a\x00\x00\x00")
    sp_ = x[j + 4:j + 8] if j >= 0 else b"\x00\x00\x00\x00"
    cid = sp_ + struct.pack("<I", (max(ids.get(sp_, {0})) + 8) & 0xffffffff)
    chunk = _midi_chunk(notes, cid, plain=True, ctl=ctl, sysex=sysex)
    E = [{"p": blk["pos"] + 9, "ol": 4, "nb": struct.pack("<I", nchunk + 1)},
         {"p": blk["pos"] + 7 + blk["size"], "ol": 0, "nb": chunk, "enc": blk["pos"]},
         {"p": lib["pos"] + 9, "ol": 4, "nb": struct.pack("<I", len(wraps) + 1)},
         {"p": lib["pos"] + 7 + lib["size"], "ol": 0, "nb": wrap, "enc": lib["pos"]},
         {"p": ent["pos"] + 11, "ol": 2, "nb": struct.pack("<H", len(wraps))}]
    out = _splice2(d, tree, E)
    write_new(dst, scramble(out))
    print("wrote %s: %s plays its own clip '%s' (region %d, chunk %d): %d notes, %d bars" % (dst, track, nm, len(wraps), nchunk, len(notes), length // bar))


def _setnotes_empty(d, tree, dst, track, rt, lib, blk, notes, ctl, sysex, o, dec):
    """setnotes for a MIDI / instrument track WITHOUT a clip: chunk + clip-library record as in setnotes, the route 0x1057 rebuilt from
    fields with one placement (region = the new record, position 10^12 ticks = session start, kind 3, tick based: as in every Pro Tools MIDI
    route of the kit), 'has clips' = 1 in both 0x251a of the track"""
    import uuid
    wraps = [w for w in lib["kids"] if w["ct"] == 0x2633]
    if struct.unpack_from("<I", d, lib["pos"] + 9)[0] != len(wraps):
        probe.fail("clip library count does not match %d records" % len(wraps), "unknown layout; nothing written")
    names = [r["name"] for r in dec.regions(d, tree, [])]
    nm = o.get("name")
    if not nm:
        k = 1
        while "%s-%02d" % (track, k) in names:
            k += 1
        nm = "%s-%02d" % (track, k)
    if nm in names:
        probe.fail("region name '%s' exists" % nm, "choose another name=")
    bar = 4 * Q_TICKS
    last_ = max([t + l for t, k, l, v in notes] + [t for pts in ctl.values() for t, v in pts] + [t for t, pay in sysex] + [0])
    length = max(bar, -(-last_ // bar) * bar)
    if length >= 1 << 40:
        probe.fail("clip length %d ticks is too large" % length, "times and lengths are in QUARTER notes (not ticks), e.g. range:36:72:0.25:80")
    nchunk = struct.unpack_from("<I", d, blk["pos"] + 9)[0]
    wrap = _midi_clip_record(nm, length, _rnd(16), nchunk)
    ids = {}
    for m in re.finditer(rb"\x2a\x00\x00\x00(.{4})(.{4})", d, re.S):
        ids.setdefault(m.group(1), set()).add(struct.unpack("<I", m.group(2))[0])
    end_ = rt["pos"] + 7 + rt["size"]
    pid, t0 = d[end_ - 8:end_], d[end_ - 17]
    if d[end_ - 12:end_ - 8] != _ID_MARK or t0 not in (1, 2):
        probe.fail("tail of the route of '%s' not as expected (time base, id marker, playlist id)" % track, "unknown layout; nothing written")
    sp_ = pid[:4]                                                                # chunk id: session part of the track's playlist id, counter = max + 8
    cid = sp_ + struct.pack("<I", (max(ids.get(sp_, {0})) + 8) & 0xffffffff)
    chunk = _midi_chunk(notes, cid, plain=True, ctl=ctl, sysex=sysex)
    route = _midi_route(track, [(len(wraps), 10 ** 12, 0, 3, True)], pid, t0=t0)
    E = [{"p": blk["pos"] + 9, "ol": 4, "nb": struct.pack("<I", nchunk + 1)},
         {"p": blk["pos"] + 7 + blk["size"], "ol": 0, "nb": chunk, "enc": blk["pos"]},
         {"p": lib["pos"] + 9, "ol": 4, "nb": struct.pack("<I", len(wraps) + 1)},
         {"p": lib["pos"] + 7 + lib["size"], "ol": 0, "nb": wrap, "enc": lib["pos"]},
         {"p": rt["pos"] + 7, "ol": rt["size"], "nb": route[7:], "enc": None}]
    tn_ = struct.pack("<I", len(track.encode("utf-8"))) + track.encode("utf-8")
    hits = 0
    for x_ in _paths(tree)[(0x2519, 0x251a)]:
        b_ = d[x_["pos"]:x_["pos"] + 7 + x_["size"]]
        if b_[11:11 + len(tn_)] == tn_:
            hits += 1
            if b_[-5] == 0:
                E.append({"p": x_["pos"] + len(b_) - 5, "ol": 1, "nb": b"\x01", "enc": None})
    if hits != 2:
        probe.fail("list entries 0x251a of '%s' found %d times" % (track, hits), "unknown layout; nothing written")
    out = _splice2(d, tree, E)
    write_new(dst, scramble(out))
    print("wrote %s: %s plays its own clip '%s' (region %d, chunk %d, new playlist entry): %d notes, %d bars" % (dst, track, nm, len(wraps), nchunk, len(notes), length // bar))


def probe_end_(n):
    """end of a block (position after its data)."""
    return n["pos"] + 7 + n["size"]



# addtrack4 - track insertion from fields (clean room, stage 3)
# Every block a new track adds or changes is built or edited in field terms; nothing is cloned from another track, and the session may have
# no track at all (STAIR_09: Pro Tools adds the first MIDI track M1 to an empty session, then the audio track A1). Shared groups (9.59):
# 0x2624 channel block + count, 0x1058 > 0x1057 route (MIDI / instrument) + count, 0x2107 > 0x210b kind entry + count (data 9),
# 0x2519 head entry + count (data 14) + one 0x251a per half + the u32 between the halves, 0x258a > 0x2589 view entry + count,
# every marker 0x2077: u32 track count + one 00 per track + u32 count + one 0x2506 child, both 0x202a lists: u32 count (data 16) + u16 index,
# audio: one 0x1052 playlist per channel in 0x1054 and the link 0x1014 in 0x1015; first track of a session: 0x201f data 48 (05 00 00 00 ->
# ff ff ff ff), 0x206a data 5 (ff ff ff ff -> 00 00 00 00), last byte of 0x4849 (f9 -> 80) (meaning open); directory 0x0002 rebuilt (9.51).
_NEW_MIDI_VIEW = dict(ratio=0.532258064516129, z1=12800000, z2=3276800000)       # view values of a MIDI track as Pro Tools creates it (STAIR_09 S2)


def _session_ids(d):
    """all 8-byte ids behind an id marker '2a 00 00 00'"""
    out, i = [], d.find(_ID_MARK)
    while i >= 0:
        out.append(d[i + 4:i + 12])
        i = d.find(_ID_MARK, i + 1)
    return out


def _new_track_id(d, kids):
    """id of a new track: highest track id + 8 (second u32; v1.55 rule) - without tracks: the id of the session family (most frequent bytes 1..3)
    with the highest second u32, + 8 (STAIR_09: Pro Tools ids of one session share bytes 1..3 and grow in both halves)"""
    import collections
    ids = []
    for k in kids:
        m_ = re.search(rb"\x2a\x00\x00\x00(.{8})\x00\x00\x00\x00\x2a\x00\x00\x00\1", d[k["pos"]:k["pos"] + 7 + k["size"]], re.S)
        if m_:
            ids.append(m_.group(1))
    if not ids:
        allid = _session_ids(d)
        if not allid:
            probe.fail("no id in this session to derive a track id from", "unknown layout; nothing written")
        fam = collections.Counter(x[1:4] for x in allid).most_common(1)[0][0]
        ids = [x for x in allid if x[1:4] == fam]
    top = max(ids, key=lambda x: struct.unpack_from("<I", x, 4)[0])
    return top[:4] + struct.pack("<I", (struct.unpack_from("<I", top, 4)[0] + 8) & 0xffffffff)


def _main_output(d, tree):
    """(id, name) of the output path new tracks play to: the output of the session's tracks (0x260e), else the first multi-channel output path
    of the I/O setup 0x2603 > 0x2602 (02 01 | u32 length + name | ... | id marker + path id)"""
    oe_ = [d[x_["pos"] + 9:x_["pos"] + 7 + x_["size"]] for x_ in probe.walk(_paths(tree)[(0x2624,)][0]["kids"]) if x_["ct"] == 0x260e]
    oe_ = [x_ for x_ in oe_ if x_[:2] == b"\x02\x00" and x_[8:12] == _ID_MARK]
    if oe_:
        ol_ = struct.unpack_from("<I", oe_[-1], 36)[0]
        return oe_[-1][12:20], oe_[-1][40:40 + ol_].decode("utf-8")
    for n in _paths(tree).get((0x2603, 0x2602), []):
        x = d[n["pos"] + 9:n["pos"] + 7 + n["size"]]
        if x[:2] == b"\x02\x01":
            ln = struct.unpack_from("<I", x, 2)[0]
            q = x.find(_ID_MARK, 6 + ln)
            if q > 0:
                return x[q + 4:q + 12], x[6:6 + ln].decode("utf-8")
    # no I/O setup (session from newbase): Pro Tools assigns its own output path on the first save (h50); the track names one
    return _new_track_id(d, [])[:4] + struct.pack("<I", 1), "Out 1-2"


def _insert_track(d, tree, kind, name, stereo=None, timebase="samples"):
    """bytes of session D with one more track of KIND (midi, instrument, audio, aux, master, folder, rfolder) named NAME, built from
    fields; the directory is rebuilt from the block tree. Returns (new data, track id)."""
    P = _paths(tree)
    p24 = P[(0x2624,)][0]
    kids = p24["kids"]
    N = len(kids)
    nm = name.encode("utf-8")
    if not (1 <= len(nm) <= 60) or b"," in nm:
        probe.fail("track name '%s' not allowed" % name, "use 1..60 characters without comma")
    for k in kids:
        if (struct.pack("<I", len(nm)) + nm) in d[k["pos"]:k["pos"] + 60]:
            probe.fail("track name '%s' exists" % name, "choose another name")
    if kind == "rfolder" and stereo is None:                                   # mono routing folder (stereo=0); default stays stereo
        stereo = 1
    if kind == "folder" or stereo is None:
        stereo = 0
    tid = _new_track_id(d, kids)
    E = []
    after = lambda n: n["pos"] + 7 + n["size"]
    def ins(p, nb, enc):
        E.append({"p": p, "ol": 0, "nb": nb, "enc": enc["pos"]})
    def setu32(p, v):
        E.append({"p": p, "ol": 4, "nb": struct.pack("<I", v), "enc": None})
    def count(par, off, expect):
        v = struct.unpack_from("<I", d, par["pos"] + 9 + off)[0]
        if v != expect:
            probe.fail("count of 0x%04x (data %d) is %d, expected %d" % (par["ct"], off, v, expect), "unknown layout; nothing written")
        setu32(par["pos"] + 9 + off, v + 1)
    if N:                                                                      # a new basic folder clears the view flags, not the 'last' mark (STAIR_10 S7)
        _demote_last(d, kids, E, keep_last=kind == "folder")
    # running numbers and output path (audio-carrying kinds)
    lists_ = [struct.unpack("<10I", x_.group(1)) for k_ in kids for x_ in [re.search(rb"\x01\x01\x0a\x00(.{40})", d[k_["pos"]:k_["pos"] + 7 + k_["size"]], re.S)] if x_]
    top_ = max(max(x_) for x_ in lists_) if lists_ else 0
    run = range(top_ + 1, top_ + 11)
    rts = P.get((0x1058, 0x1057), [])
    r_idx = len(rts)
    if kind == "midi":
        blk = _midi_channel(name, tid, route=r_idx, number=N + 1, a=1, b=1, g=1, mark=4, last=1, **_NEW_MIDI_VIEW)
    elif kind == "instrument":
        oid, onm = _main_output(d, tree)
        blk = _instr_channel(name, tid, stereo, route=r_idx, runnum=run, out_id=oid, out_name=onm, v=dict(number=N + 1, z2=3276800000), tb=1)   # z2 as Pro Tools (STAIR_10 S3)
    elif kind == "audio":
        oid, onm = _main_output(d, tree)
        blk = _audio_channel(name, tid, stereo=stereo, aidx=len(P.get((0x1015, 0x1014), [])), number=N + 1, runnum=run, out_id=oid, out_name=onm)
    elif kind in ("aux", "master", "rfolder"):
        oid, onm = _main_output(d, tree)
        blk = _new_bus_channel(kind, name, tid, stereo, N + 1, run, oid, onm)
    else:
        blk = _folder_channel(name, tid, dict(f6=b"\x01\x01\x00\x00\x01\x00", h1=0x5c, comment=b"", ratio=0.5, c=0, z1=4000000, h2=0x61, mark=4, z2=1024000000, last=1, number=N + 1, g=1))   # z2: STAIR_10 S7
    ins(after(p24), blk, p24)
    count(p24, 0, N)
    # route (MIDI / instrument): empty placement list, playlist id = track id + 1
    if kind in ("midi", "instrument"):
        par = P[(0x1058,)][0]
        ins(after(par), _midi_route(name, [], tid[:4] + struct.pack("<I", struct.unpack_from("<I", tid, 4)[0] + 1)), par)
        count(par, 0, r_idx)
    kc, fo = _KIND_CODE[kind], 1 if kind in ("folder", "rfolder") else 0
    # kind entry 0x210b
    par = P[(0x2107,)][0]
    nk = len(P.get((0x2107, 0x210b), []))
    ins(after(par), _kind_entry(kc, name, tid), par)
    count(par, 9, nk)
    # 0x2519: head entry, one 0x251a per half, u32 between the halves, count at data 14
    par = P[(0x2519,)][0]
    h0 = par["pos"] + 9
    if struct.unpack_from("<I", d, h0 + 14)[0] != N:
        probe.fail("0x2519 track count is %d, expected %d" % (struct.unpack_from("<I", d, h0 + 14)[0], N), "unknown layout; nothing written")
    p = h0 + 18
    for _ in range(N):
        p += 2 + 4 + struct.unpack_from("<I", d, p + 2)[0] + 6 + 12 + 3
    ins(p, _head_entry(kc, name, tid, N + 1, stereo=stereo), par)
    ks = [k_ for k_ in par["kids"] if k_["ct"] == 0x251a]
    if len(ks) != 2 * N or (N and ks[0]["pos"] != p):
        probe.fail("0x2519 holds %d blocks 0x251a for %d tracks" % (len(ks), N), "unknown layout; nothing written")
    p1 = after(ks[N - 1]) if N else p
    if struct.unpack_from("<I", d, p1)[0] != N:
        probe.fail("u32 between the halves of 0x2519 is %d, expected %d" % (struct.unpack_from("<I", d, p1)[0], N), "unknown layout; nothing written")
    le = _list_entry(kc, name, tid, N + 1, stereo=stereo, folder=fo, clips=0)  # a new track has no clip (STAIR_09 S2: 'has clips' 0); setnotes sets it
    ins(p1, le, par)
    setu32(p1, N + 1)
    ins(after(ks[-1]) if N else p1 + 4, le, par)
    setu32(h0 + 14, N + 1)
    # view entry 0x2589 (key = track index), appended in 0x258a; count = u32 before the first entry (data 0 of 0x258a)
    vch = _chain(tree, (0x2587, 0x2551, 0x258b, 0x258a))
    par = vch[0] if vch else None                                              # no view blocks (newbase): Pro Tools writes them (h50)
    form = _VIEW_FORM[kind]
    ve = _view_entry(form, N, zoom=12800000 if form == "midi" else 4000000, ratio=0.532258064516129 if form == "midi" else 0.5)
    if par is not None:
        ent = [k_ for k_ in par["kids"] if k_["ct"] == 0x2589]
        k81 = [k_ for k_ in par["kids"] if k_["ct"] == 0x2581]
        if len(k81) != 1:
            probe.fail("0x258a holds %d blocks 0x2581" % len(k81), "unknown layout; nothing written")
        pc = after(k81[0])                                                         # u32 number of entries right behind 0x2581, then the entries
        if struct.unpack_from("<I", d, pc)[0] != len(ent):
            probe.fail("0x258a entry count is %d, expected %d" % (struct.unpack_from("<I", d, pc)[0], len(ent)), "unknown layout; nothing written")
        ins(pc + 4, ve, par)                                                       # newest entry first (Pro Tools order, STAIR_09 S3; T13)
        for e_ in ent:                                                             # mark of the other MIDI-form entries 4 -> 3 (own data byte 7; STAIR_09 S3,
            q_ = _own_pos(e_, 7)                                                   # STAIR_10: audio / aux / folder entries keep 4)
            if d[q_] == 4 and any(k_["ct"] == 0x203a for k_ in e_["kids"]):
                E.append({"p": q_, "ol": 1, "nb": b"\x03", "enc": None})
        setu32(pc, len(ent) + 1)
    # markers: u32 track count + one 00 per track, u32 count, one more 0x2506 child
    for mk in P.get((0x2030, 0x2077), []):
        hb, he = mk["pos"] + 9, (mk["kids"][0]["pos"] if mk["kids"] else after(mk))
        i_ = d.find(b"\xff\xff\xff\xff" + struct.pack("<I", N), hb, he)
        if i_ < 0 or struct.unpack_from("<I", d, i_ + 4 + 55 + N)[0] != N:
            probe.fail("per-track counters of the marker at %d not where expected" % mk["pos"], "unknown layout; nothing written")
        c1 = i_ + 4
        setu32(c1, N + 1)
        ins(c1 + 4 + N, b"\x00", mk)
        setu32(c1 + 55 + N, N + 1)
        e6 = [k_ for k_ in mk["kids"] if k_["ct"] == 0x2506]
        ins(after(e6[-1]) if e6 else c1 + 59 + N, _blk(3, 0x2506, b"\xff\xff\xff\xff" + b"\x00" * 4), mk)
    # 0x202a <ALL> lists: u32 count at data 16, u16 track index per track
    for b_ in [n for n in probe.walk(tree) if n["ct"] == 0x202a and d[n["pos"] + 9:n["pos"] + 18] == b"\x05\x00\x00\x00<ALL>"]:
        b0 = b_["pos"] + 9
        if struct.unpack_from("<I", d, b0 + 16)[0] != N:
            probe.fail("0x202a list at %d has count %d, expected %d" % (b_["pos"], struct.unpack_from("<I", d, b0 + 16)[0], N), "unknown layout; nothing written")
        setu32(b0 + 16, N + 1)
        ins(b0 + 20 + 2 * N, struct.pack("<H", N), b_)
    # audio: one empty playlist per channel (0x1054 > 0x1052) and the link 0x1014 (0x1015), before the trailing child of each parent
    if kind == "audio":
        nch = 2 if stereo else 1
        st = bytes([stereo])
        nn = struct.pack("<I", len(nm)) + nm
        p54, p15 = P[(0x1054,)][0], P[(0x1015,)][0]
        pl0 = len([k_ for k_ in p54["kids"] if k_["ct"] == 0x1052])
        tb_tail = b"\x00\x00\x00\x00" + (b"\x02\x00" if timebase == "ticks" else b"\x01\x00")
        for par, blocks in ((p54, [_blk(3, 0x1052, nn + tb_tail)] * nch),
                            (p15, [_blk(9, 0x1014, nn + st + struct.pack("<I", nch) + b"".join(struct.pack("<H", pl0 + c_) for c_ in range(nch)) + b"\x00\x00\x00\x00" + _ID_MARK
                                        + tid[:4] + struct.pack("<I", struct.unpack_from("<I", tid, 4)[0] + 1) + (b"\x01\x00\x01\x00\x00\x00\x00" if stereo else b"\x00" * 7)
                                        + b"".join(struct.pack("<I", pl0 + c_) for c_ in range(nch)) + st + b"\x00" * 5)])):
            tail_ = par["kids"][-1]
            if tail_["ct"] not in (0x4829, 0x4828):
                probe.fail("last child of 0x%04x is 0x%04x" % (par["ct"], tail_["ct"]), "unknown layout; nothing written")
            n_ = len(par["kids"]) - 1
            for b_ in blocks:
                ins(tail_["pos"], b_, par)
            count(par, 0, n_)
            if len(blocks) > 1:                                                # stereo: two playlists (STAIR_10 S8: count + 2)
                E[-1]["nb"] = struct.pack("<I", n_ + len(blocks))
    # first track of a session (STAIR_09 S1 -> S2; meaning open, observed values)
    if N == 0:
        for ct_, off, old, new in ((0x201f, 48, b"\x05\x00\x00\x00", b"\xff" * 4), (0x206a, 5, b"\xff" * 4, b"\x00" * 4)):   # offsets behind the leading child 0x2011
            b_ = [n for n in tree if n["ct"] == ct_]
            if b_ and b_[0]["kids"] and b_[0]["kids"][0]["ct"] == 0x2011:
                q_ = after(b_[0]["kids"][0]) + off
                if d[q_:q_ + 4] == old:
                    E.append({"p": q_, "ol": 4, "nb": new, "enc": None})
        b_ = _chain(tree, (0x4848, 0x4847, 0x4849))
        if b_ and d[after(b_[0]) - 1] != 0x80:                                 # f9 (STAIR_09) / e2 (STAIR_10) -> 80
            E.append({"p": after(b_[0]) - 1, "ol": 1, "nb": b"\x80", "enc": None})
    out = _splice2(d, tree, E)
    tr2 = probe.parse(out, HEADER, len(out))
    last = tr2[-1]
    if last["ct"] != 0x0002 or after(last) != len(out):
        probe.fail("the directory 0x0002 is not the last block", "unknown layout; nothing written")
    body = _dir_build(tr2)
    out = out[:last["pos"] + 3] + struct.pack("<I", len(body) + 2) + out[last["pos"] + 7:last["pos"] + 9] + body
    return out, tid


def cmd_dropblock(src, dst, cts, *opts):
    """experiment tool (clean-room stage 3): write SRC without its top-level block(s) CTS (hex types, comma separated, e.g. 1022,2033);
    the directory 0x0002 is rebuilt from the remaining tree, stored positions outside it are remapped. Pro Tools then shows whether the block
    is needed (survival job). The header block, 0x0002 and 0x0003 cannot be dropped.
    CTS = all-CT,CT.. drops every top-level block but the listed ones (and 0x0002, 0x0003, the header block).
    Example: python3 ptx_edit.py dropblock empty.ptx test.ptx 1022 ; python3 ptx_edit.py dropblock empty.ptx min.ptx all-2067"""
    raw, d, tree = descramble_file(src)
    d = bytes(d)
    try:
        if cts.startswith("all"):                                              # all[-CT,CT..] = every top-level block but the listed ones
            keep = {int(x, 16) for x in cts[4:].split(",") if x} | {0x0002, 0x0003}
            want = {n["ct"] for n in tree[1:]} - keep
        else:
            want = {int(x, 16) for x in cts.split(",") if x}
    except ValueError:
        probe.fail("block types '%s' are not hex numbers" % cts, "give hex types like 1022,2033 or all-1028,2026")
    if want & {0x0002, 0x0003} or not want:
        probe.fail("cannot drop %s" % sorted(hex(x) for x in want), "the directory 0x0002 and 0x0003 stay; give other types")
    hits = [n for n in tree[1:] if n["ct"] in want]
    if {n["ct"] for n in hits} != want:
        probe.fail("top-level block(s) %s not found" % sorted(hex(x) for x in want - {n["ct"] for n in hits}), "list them with: python3 tools/ptx_decode_v*.py FILE (newest)")
    last = tree[-1]
    if last["ct"] != 0x0002:
        probe.fail("the directory 0x0002 is not the last block", "unknown layout; nothing written")
    gone = {n["pos"] for n in hits}
    out = d[:HEADER] + b"".join(d[n["pos"]:n["pos"] + 7 + n["size"]] for n in tree if n["pos"] not in gone)   # top-level blocks: no parent sizes change
    tr2 = probe.parse(out, HEADER, len(out))
    l2 = tr2[-1]
    body = _dir_build(tr2)                                                     # all directory positions (incl. the trailer) from the new tree
    out = out[:l2["pos"] + 3] + struct.pack("<I", len(body) + 2) + out[l2["pos"] + 7:l2["pos"] + 9] + body
    out = out[:27] + struct.pack("<I", l2["pos"]) + out[31:]                     # file offset 27 = position of the directory (9.51)
    tr3 = probe.parse(out, HEADER, len(out))
    _check_sites(out, tr3)
    write_new(dst, scramble(out))
    print("wrote %s: dropped %s (%d bytes), directory rebuilt" % (dst, " ".join("0x%04x" % n["ct"] for n in hits), sum(7 + n["size"] for n in hits)))


def cmd_addtrack4(src, dst, *opts):
    """add one track built from fields (no clone, no donor; also into a session WITHOUT tracks). Options: kind=midi|instrument|audio|aux|
    master|folder|rfolder (default midi), stereo=1, name=<track name> (default Track <n>), timebase=samples|ticks (audio only).
    Example: python3 ptx_edit.py addtrack4 empty.ptx a.ptx kind=midi name=M1 ; python3 ptx_edit.py addtrack4 a.ptx b.ptx kind=audio name=A1"""
    o = dict(x.split("=", 1) for x in opts if "=" in x)
    kind = o.get("kind", "midi")
    tb = o.get("timebase", "samples")
    if kind not in ("midi", "instrument", "audio", "aux", "master", "folder", "rfolder") or tb not in ("samples", "ticks") or set(o) - {"kind", "stereo", "name", "timebase"}:
        probe.fail("unknown option or kind in %s" % list(opts), "use kind=midi|instrument|audio|aux|master|folder|rfolder stereo=1 name=<text> timebase=samples|ticks")
    raw, d, tree = descramble_file(src)
    d = bytes(d)
    n0 = len(_paths(tree)[(0x2624,)][0]["kids"])
    st_ = None if "stereo" not in o else (1 if o["stereo"] in ("1", "yes", "true") else 0)     # None = kind default (rfolder stereo)
    out, tid = _insert_track(d, tree, kind, o.get("name", "Track %d" % (n0 + 1)), st_, timebase=tb)
    write_new(dst, scramble(out))
    print("wrote %s: +1 %s track '%s' (track %d, id %s)" % (dst, kind, o.get("name", "Track %d" % (n0 + 1)), n0 + 1, tid.hex()))



# clean-room base session (stage 3 done differently)
# Jobs h48 - h50: Pro Tools opens a session that lacks top-level blocks and writes its own defaults for them on save (h48: 30 of 30 single
# blocks re-created, 26 byte-identical to the CreateSession session; h49: header block + 0x0003 + 0x1028 + 0x0002 is enough, without
# 0x1028 Pro Tools fails with an assertion; h50: with tracks, clips and notes only 0x1028 and the 12 containers tracks and clips use are
# needed - no I/O setup, no view blocks; Pro Tools assigns its own output on save). The base is therefore built from fields only:
# header, pointer block, track list 0x2519, format 0x1028, the empty containers (u32 count 0), version block 0x0003, directory.
_HEADER_MAGIC = b"\x03" + b"0010111100101011" + b"\x00"            # 20-byte file header: magic, then xor type 5 and the xor value (any)


def _block_1028(rate=48000, bits=24):
    """0x1028 [10] audio format: u8 file type (3 = WAV), u8 bit depth, u32 sample rate, 5 x 00, 02 = no I/O-settings file path (01 + path
    list in sessions that name one), u32 0, 5 x 00 (open), 02 02 (open), u8 float flag, u8 (open), u32 bit depth, 00 01 (open).
    32-bit float (14 saves): bit byte 24, flags 01 01, u32 32"""
    if rate not in (44100, 48000, 88200, 96000, 176400, 192000) or bits not in (16, 24, 32):
        probe.fail("rate %s / bits %s not supported" % (rate, bits), "use rate 44100 | 48000 | 88200 | 96000 | 176400 | 192000, bits 16 | 24 | 32 (32 = float)")
    fl = 1 if bits == 32 else 0
    return _blk(10, 0x1028, bytes([3, 24 if bits == 32 else bits]) + struct.pack("<I", rate) + b"\x00" * 5 + b"\x02" + struct.pack("<I", 0) + b"\x00" * 5
                + bytes([2, 2, fl, fl]) + struct.pack("<I", bits) + b"\x00\x01")


def _block_0003(creator_id, edition=6, product="Pro Tools Intro", version=(3, 26, 11, 0), os_name="MacOS", os_code=5):
    """0x0003 [4] version block: u8 edition (6 Intro, 1 Studio, 0 Ultimate; corpus), u32 length + product, 4 x u32 version (3, year - 2000,
    month, patch), u32 length + version string, 01, u32 + 'Release', 00, u32 + 'Pro Tools Session File', 06 00 (open), u32 + OS name,
    4 x 00, u32 os_code (open: 5 here, 0x0b - 0x16 in the corpus), 00, id marker + creator id (8 bytes; any id)"""
    s = lambda t: struct.pack("<I", len(t)) + t.encode("ascii")
    vs = "20%02d.%d.%d" % version[1:]
    return _blk(4, 0x0003, bytes([edition]) + s(product) + struct.pack("<4I", *version) + s(vs) + b"\x01" + s("Release") + b"\x00" + s("Pro Tools Session File")
                + b"\x06\x00" + s(os_name) + b"\x00" * 4 + struct.pack("<I", os_code) + b"\x00" + _ID_MARK + creator_id)


def _block_2519_empty():
    """0x2519 [9] track lists without tracks (STAIR_10 S0): 01 00, 12 x 00, u32 0 tracks, u32 0 (between the halves), 00 00, u32 24 (open),
    6 x 00; children 0x2716 (u32 0), 0x4422 (00 00), 0x4420 (00 00), 0x251b [1] = u32 5 + five 0x251c [2] (u32 i, 3 x 00, u32 i; open:
    five fixed entries), 0x483d (00 00)"""
    ent = b"".join(_blk(2, 0x251c, struct.pack("<I", i) + b"\x00" * 3 + struct.pack("<I", i)) for i in range(5))
    return _blk(9, 0x2519, b"\x01\x00" + b"\x00" * 12 + struct.pack("<II", 0, 0) + b"\x00\x00" + struct.pack("<I", 24) + b"\x00" * 6,
                _blk(1, 0x2716, b"\x00" * 4), _blk(1, 0x4422, b"\x00\x00"), _blk(1, 0x4420, b"\x00\x00"),
                _blk(1, 0x251b, struct.pack("<I", 5), ent), _blk(1, 0x483d, b"\x00\x00"))


def _block_2603(path_id, name="Out 1-2", sub_ids=None):
    """v1.72 I/O setup 0x2603 [2] with ONE stereo output path and its two mono sub-paths, no hardware link (0x2601
    count 0) - fields of STAIR_10 S0: u32 number of paths; path 0x2602 [14]: 02, u8 stereo, u32 length + name, u32 channels, u16 1, u16 2
    (open), stereo: ff ff 01 01 00 00 00 00 + id marker + path id + 16 x 00 / mono: 01 00 00 00 00 00 + id marker + own id + 4 x 00 + id
    marker + parent id; 0x2601 [1] u32 0; tail ff 00, u8 stereo, 6 x 00, 01 00, ff ff ff ff, 4 x 00, u8 stereo, 6 x 00, fe ff"""
    sub_ids = sub_ids or [path_id[:4] + struct.pack("<I", struct.unpack_from("<I", path_id, 4)[0] + 1 + i) for i in range(2)]
    s = lambda t: struct.pack("<I", len(t)) + t.encode("utf-8")
    tail = lambda st: b"\xff\x00" + bytes([st]) + b"\x00" * 6 + b"\x01\x00" + b"\xff" * 4 + b"\x00" * 4 + bytes([st]) + b"\x00" * 6 + b"\xfe\xff"
    p = [_blk(14, 0x2602, b"\x02\x01" + s(name) + struct.pack("<IHH", 2, 1, 2) + b"\xff\xff\x01\x01\x00\x00\x00\x00" + _ID_MARK + path_id + b"\x00" * 16,
              _blk(1, 0x2601, struct.pack("<I", 0)), tail(1))]
    base = name.rsplit(" ", 1)[0] if " " in name else name
    for i, sid in enumerate(sub_ids):
        p.append(_blk(14, 0x2602, b"\x02\x00" + s("%s %d" % (base, i + 1)) + struct.pack("<IHH", 1, 1, 2) + b"\x01\x00\x00\x00\x00\x00" + _ID_MARK + sid
                      + b"\x00" * 4 + _ID_MARK + path_id, _blk(1, 0x2601, struct.pack("<I", 0)), tail(0)))
    return _blk(2, 0x2603, struct.pack("<I", len(p)), *p)


OFF12 = 10 ** 12                                                               # tick / position offset of the stored forms


def _map_2619(name, ident):
    """0x2619 head of a tempo / meter map (constants as observed in every Pro Tools save, D1): name, three copies of the map id."""
    star = b"\x2a\x00\x00\x00" + ident
    return _blk(9, 0x2619, struct.pack("<I", len(name)) + name + b"\x00\x00" + struct.pack("<I", 1) + b"\x00" + star + b"\x00" * 4 + star
                + b"\x00" * 8 + b"\x01" + b"\x00" * 36 + _blk(1, 0x4301, b"\x00" * 32) + b"\x00" * 4 + star + b"\x00\x00")


def _tempo_payload(events, rate):
    """data of 0x2028: 'Tempo', u16 2, u32 4 + 61 n, u32 n, u32 0, n records of 61 bytes, 5 zero bytes, f64 sample rate.
    Record: 'Const' 01 00 u32 46 'TMS' 01 00 u32 20 u8 0 u32 first 5 zeros u64 10^12 + ticks u8 0 u8 first f64 bpm u32 960000 9 zeros."""
    recs = b""
    for k, (tk, bpm) in enumerate(events):
        f = 1 if k == 0 else 0
        recs += (b"Const\x01\x00" + struct.pack("<I", 46) + b"TMS\x01\x00" + struct.pack("<I", 20) + b"\x00" + struct.pack("<I", f) + b"\x00" * 5
                 + struct.pack("<Q", OFF12 + tk) + bytes([0, f]) + struct.pack("<d", bpm) + struct.pack("<I", 960000) + b"\x00" * 9)
    return b"Tempo\x02\x00" + struct.pack("<III", 4 + 61 * len(events), len(events), 0) + recs + b"\x00" * 5 + struct.pack("<d", float(rate))


def _meter_payload(events):
    """data of 0x2029: 'Meter', u16 2, u32 12 + 52 n, u32 n, n records of 36 bytes (u64 10^12 + ticks, u32 bar, u32 num, u32 den,
    constants u16 1 u16 3 u32 0 u32 2 u32 3), n entries of 16 bytes (u32 bar, u32 1, u64 0), u64 10^12."""
    recs = b"".join(struct.pack("<QIIIHHIII", OFF12 + tk, bar, num, den, 1, 3, 0, 2, 3) for tk, bar, num, den in events)
    tail = b"".join(struct.pack("<IIQ", bar, 1, 0) for _, bar, _, _ in events)
    return b"Meter\x02\x00" + struct.pack("<II", 12 + 52 * len(events), len(events)) + recs + tail + struct.pack("<Q", OFF12)


def _map_blocks(tempo, meter, rate, family):
    """the four top-level blocks 0x2718, 0x2028, 0x2719, 0x2029 (inner and top-level copy are equal, Pro Tools reads the second)."""
    t_, m_ = _tempo_payload(tempo, rate), _meter_payload(meter)
    tid, mid = family + struct.pack("<I", 0x7e000001), family + struct.pack("<I", 0x7e000003)
    return [_blk(2, 0x2718, _map_2619(b"Tempo", tid), _blk(3, 0x2028, t_), struct.pack("<d", 120.0) + b"\x01\x05\x00"), _blk(3, 0x2028, t_),
            _blk(1, 0x2719, _map_2619(b"Meter", mid), _blk(1, 0x2029, m_)), _blk(1, 0x2029, m_)]


_KEY_PARSE = {
    "cb": (True, -7), "gb": (True, -6), "db": (True, -5), "ab": (True, -4), "eb": (True, -3), "bb": (True, -2), "f": (True, -1),
    "c": (True, 0), "g": (True, 1), "d": (True, 2), "a": (True, 3), "e": (True, 4), "b": (True, 5), "f#": (True, 6), "c#": (True, 7),
    "abm": (False, -7), "ebm": (False, -6), "bbm": (False, -5), "fm": (False, -4), "cm": (False, -3), "gm": (False, -2), "dm": (False, -1),
    "am": (False, 0), "em": (False, 1), "bm": (False, 2), "f#m": (False, 3), "c#m": (False, 4), "g#m": (False, 5), "d#m": (False, 6), "a#m": (False, 7),
}


def _parse_keysigs(items):
    """parse ['0:C', '960000:Am', ...] -> [(ticks, major_bool, sharps_signed), ...]."""
    out = []
    for item in items:
        a, k = item.split(":", 1)
        kv = _KEY_PARSE.get(k.strip().lower())
        if kv is None:
            probe.fail("unknown key signature '%s'" % k, "use C, G, D, A, E, B, F#, C#, F, Bb, Eb, Ab, Db, Gb, Cb or minor Am..Abm")
        out.append((int(a), kv[0], kv[1]))
    return out


def _keysig_blocks(events, family):
    """top-level 0x271B > (0x2619 + 0x2433) + duplicate 0x2433 from fields."""
    k32 = b"".join(_blk(1, 0x2432, (OFF12 + tk).to_bytes(7, "little") + bytes([0, 1 if maj else 0, 1 if sf >= 0 else 0, abs(sf)]))
                   for tk, maj, sf in events)
    b33 = _blk(1, 0x2433, struct.pack("<I", len(events)) + k32)
    kid = family + struct.pack("<I", 0x7e000005)
    return [_blk(1, 0x271b, _map_2619(b"Key Signature", kid), b33), b33]


def _rnd(n):
    """random bytes without 0x5A: a 0x5A in random ids (track / clip / marker ids) can look like a block start to the
    tolerant block scanner (probe.parse) and made the writer refuse about 1 in 20 rebuilds (round trip C10, W12)."""
    while True:
        b = os.urandom(n)
        if 0x5A not in b:
            return b


_MK_VIEW = bytes.fromhex("f0bfffffffffffffffffffffffffffbfffffffffffffffbf00000000000000400000000000000040")   # no view properties (D1)
_MK_COLOUR = (23, bytes.fromhex("01003e004500ff"))       # marker colour index + its colour record: the pair seen most (187 of 927; D1)


def _mk_pos(v, ticks):
    """8-byte marker position: u40 (10^12 + ticks, or samples), 00 00, 0x40 when ticks."""
    return ((10 ** 12 + v) if ticks else v).to_bytes(5, "little") + b"\x00\x00" + (b"\x40" if ticks else b"\x00")


def _marker_2077(number, name, start, end, ticks, kind, ntracks, comment=b"", guid=None, colour=_MK_COLOUR):
    """memory location 0x2077 from fields. kind 1 = marker, 2 = selection; one 0x2506 child per track."""
    nm = name.encode("utf-8")
    g = guid or _rnd(16)
    head = struct.pack("<HBBH", number, 0x01 if ticks else 0x03, kind, 0) + struct.pack("<I", len(nm)) + nm
    body = (_mk_pos(start, ticks) + _mk_pos(end, ticks) + b"\x00" * 6 + _MK_VIEW + b"\xff" * 4 + struct.pack("<I", ntracks) + b"\x00" * ntracks
            + struct.pack("<IB", 1, 0) + struct.pack("<I", len(comment)) + comment + b"\x00" * 8 + b"\xff" * 4 + b"\x00" * 12 + b"\xff" * 4 + b"\x00" * 12
            + struct.pack("<HI", colour[0], ntracks) + b"".join(_blk(3, 0x2506, b"\xff" * 4 + b"\x00" * 4) for _ in range(ntracks))
            + b"\x00" * 4 + struct.pack("<I", len(comment)) + comment + b"\x00" * 13 + b"\xff\xff" + g + b"\xff" * 12
            + _blk(1, 0x4826, colour[1]) + _blk(1, 0x4826, b"\x00" * 7) + _blk(1, 0x4827, b"\x00" * 28) + struct.pack("<Q", 1))
    return _blk(0x12, 0x2077, head + body)


def _rebuild_top(d, tree, blocks):
    """file from the header + the given top-level block bytes (0x0002 last), directory rebuilt, offset 27 set (as dropblock)."""
    out = d[:HEADER] + b"".join(blocks)
    tr2 = probe.parse(out, HEADER, len(out))
    l2 = tr2[-1]
    body = _dir_build(tr2)
    out = out[:l2["pos"] + 3] + struct.pack("<I", len(body) + 2) + out[l2["pos"] + 7:l2["pos"] + 9] + body
    out = out[:27] + struct.pack("<I", l2["pos"]) + out[31:]
    _check_sites(out, probe.parse(out, HEADER, len(out)))
    return out


def cmd_setmarkers(src, dst, spec, *opts):
    """write memory locations built from fields into SRC, which must not have markers yet (block 0x2030 is created). SPEC =
    @file.json: list of {"name", "start", "end" (default start), "unit": "ticks" (960000 per quarter) | "samples", "kind": "marker" |
    "selection", "comment"}. Markers come in list order, numbers 1..n; one per-track child per existing track (add tracks first).
    Example: python3 ptx_edit.py setmarkers a.ptx b.ptx @markers.json"""
    import json
    if not spec.startswith("@") or not os.path.isfile(spec[1:]):
        probe.fail("markers spec '%s' is not @<existing json file>" % spec, 'write a JSON list like [{"name": "Verse", "start": 3840000, "unit": "ticks"}]')
    try:
        mks = json.load(open(spec[1:]))
        assert isinstance(mks, list) and all("name" in x and "start" in x for x in mks)
    except (ValueError, AssertionError):
        probe.fail("%s is not a JSON list of markers with name and start" % spec[1:], 'e.g. [{"name": "Intro", "start": 0, "unit": "samples"}]')
    raw, d, tree = descramble_file(src)
    d = bytes(d)
    if any(n["ct"] == 0x2030 for n in tree):
        probe.fail("the session already has memory locations (0x2030)", "setmarkers writes into a session without markers (newsong / newbase)")
    if tree[-1]["ct"] != 0x0002 or tree[-2]["ct"] != 0x0003:
        probe.fail("the session does not end with 0x0003, 0x0002", "unknown layout; nothing written")
    nt = len(next((n["kids"] for n in tree if n["ct"] == 0x2624), []))
    blks = []
    for k, x in enumerate(mks):
        unit, kind = x.get("unit", "ticks"), x.get("kind", "marker")
        if unit not in ("ticks", "samples") or kind not in ("marker", "selection") or not (1 <= len(x["name"].encode("utf-8")) <= 255):
            probe.fail("marker %d: unit / kind / name not valid" % (k + 1), "unit ticks|samples, kind marker|selection, name 1..255 bytes")
        st, en = int(x["start"]), int(x.get("end", x["start"]))
        if st < 0 or en < st:
            probe.fail("marker %d: start %d / end %d" % (k + 1, st, en), "start >= 0 and end >= start")
        blks.append(_marker_2077(k + 1, x["name"], st, en, unit == "ticks", 1 if kind == "marker" else 2, nt, x.get("comment", "").encode("utf-8")))
    c2030 = _blk(5, 0x2030, struct.pack("<I", len(blks)), *blks, b"\x00" * 8)      # u32 count, markers, 8 zero bytes
    fam = _new_track_id(d, next((n["kids"] for n in tree if n["ct"] == 0x2624), []))[:4] if nt else _rnd(4)
    w271a = _blk(3, 0x271a, _map_2619(b"Markers", fam + struct.pack("<I", 0x7e000005)), _blk(5, 0x2030, struct.pack("<I", 0), b"\x00" * 8),
                 *[_blk(1, 0x4833, b"\x00" * 5) for _ in range(5)])                       # 0x271A > 0x2619 'Markers' + empty 0x2030 + 5 x 0x4833 (D1)
    tops = [d[n["pos"]:n["pos"] + 7 + n["size"]] for n in tree]
    out = _rebuild_top(d, tree, tops[:-2] + [c2030] + tops[-2:])            # no 0x271A wrapper: Pro Tools refuses ours (bisect 3) and creates its own
    if any(x.get("kind", "marker") == "marker" for x in mks):                 # legacy marker ruler population flag (0x2519 > 0x251B > 0x251C[0][6])
        tr_out = probe.parse(out, HEADER, len(out))
        b1b = next((n for n in probe.walk(tr_out) if n["ct"] == 0x251B), None)
        if b1b and b1b["kids"] and b1b["kids"][0]["ct"] == 0x251C and b1b["kids"][0]["size"] >= 9:
            ba = bytearray(out)
            ba[b1b["kids"][0]["pos"] + 9 + 6] = 1
            out = bytes(ba)
    write_new(dst, scramble(out))
    print("wrote %s: %d memory locations (%d per-track children each)" % (dst, len(blks), nt))


def _io_paths(d, tree):
    """(0x2603 block, [(block, name, stereo, channels, first channel, id)]) of the I/O setup."""
    io = next((n for n in tree if n["ct"] == 0x2603), None)
    if io is None:
        probe.fail("the session has no I/O setup 0x2603", "build it with newbase / newsong io=1")
    out = []
    for k in [x for x in io["kids"] if x["ct"] == 0x2602]:
        p = k["pos"] + 9
        ln = struct.unpack_from("<I", d, p + 2)[0]
        q = p + 6 + ln
        nch, first, second = struct.unpack_from("<IHH", d, q)
        idp = d.find(_ID_MARK, q + 8, q + 24)
        out.append((k, d[p + 6:p + 6 + ln].decode("utf-8", "replace"), d[p + 1], nch, first, d[idp + 4:idp + 12] if idp >= 0 else None))
    return io, out


def cmd_addbus(src, dst, name, *opts):
    """append an internal bus path NAME to the I/O setup, built from fields: 0x2602 [14] = 02, u8 stereo, u32
    length + name, u32 channels, u16 first channel (running over all paths), stereo: u16 last channel, ff ff / mono: ff ff, then 01 00
    (01 01 = output), u32 0, id marker + new id, 16 zeros, 0x2601 u32 0, tail. Option stereo=1.
    Example: python3 ptx_edit.py addbus in.ptx out.ptx FX stereo=1"""
    o = dict(x.split("=", 1) for x in opts if "=" in x)
    if set(o) - {"stereo"} or len(o) != len(opts) or not (1 <= len(name.encode("utf-8")) <= 60):
        probe.fail("unknown option in %s or bus name length" % list(opts), "use stereo=1; name 1..60 bytes")
    st = 1 if o.get("stereo", "0") in ("1", "yes", "true") else 0
    raw, d, tree = descramble_file(src)
    d = bytes(d)
    io, paths = _io_paths(d, tree)
    if any(p[1] == name for p in paths):
        probe.fail("a path named '%s' exists" % name, "choose another bus name")
    if struct.unpack_from("<I", d, io["pos"] + 9)[0] != len(paths) or not paths:
        probe.fail("I/O setup count does not match its paths", "unknown layout; nothing written")
    first = max(p[4] + p[3] for p in paths)
    fam = next(p[5] for p in paths if p[5])[:4]
    pid = fam + struct.pack("<I", (max(struct.unpack_from("<I", p[5], 4)[0] for p in paths if p[5]) + 0x101) & 0xffffffff)
    nm = name.encode("utf-8")
    tail = b"\xff\x00" + bytes([st]) + b"\x00" * 6 + b"\x01\x00" + b"\xff" * 4 + b"\x00" * 4 + bytes([st]) + b"\x00" * 6 + b"\xfe\xff"
    blk = _blk(14, 0x2602, b"\x02" + bytes([st]) + struct.pack("<I", len(nm)) + nm + struct.pack("<IH", 2 if st else 1, first)
               + (struct.pack("<H", first + 1) if st else b"") + b"\xff\xff\x01\x00" + b"\x00" * 4 + _ID_MARK + pid + b"\x00" * 16,
               _blk(1, 0x2601, struct.pack("<I", 0)), tail)
    last = paths[-1][0]
    E = [{"p": last["pos"] + 7 + last["size"], "ol": 0, "nb": blk, "enc": io["pos"]},
         {"p": io["pos"] + 9, "ol": 4, "nb": struct.pack("<I", len(paths) + 1), "enc": None}]
    write_new(dst, scramble(_splice2(d, tree, E)))
    print("wrote %s: bus '%s' (%s), path number %d" % (dst, name, "stereo" if st else "mono", len(paths) + 2))


def _group_202a(name, gid, enabled, members, attr=None, ty=2):
    """one group record 0x202A [5] with its 0x258E [5] child, built from fields (byte-identical to 372 / 372
    0x202A blocks across all 139 reference sessions)."""
    nm = name.encode("utf-8")
    is_all = name == "<ALL>"
    gid = 0xFFFFFFFF if is_all else gid
    en = 0 if is_all else (1 if enabled else 0)
    attr = (0x00018010 if is_all else 1) if attr is None else attr
    e8e = (b"\x01\x01" + b"\x00" * 6 + b"\x01\x00" + b"\x00" * 52) if is_all else (b"\x00" * 4 + b"\x01\x00" + b"\x00" * 56)
    return _blk(5, 0x202a, struct.pack("<I", len(nm)) + nm + bytes([ty]) + struct.pack("<I", gid) + bytes([en, en])
                + struct.pack("<I%dH" % len(members), len(members), *members) + b"\xfe\xff" + struct.pack("<II", attr, 0) + b"\xff\xff",
                _blk(5, 0x258e, e8e))


def cmd_setgroups(src, dst, spec, *opts):
    """write track groups 0x202B > 0x202A built from fields into SRC (after all tracks are added). SPEC = @file.json:
    list of {"name", "type" (1 Edit, 2 Mix, 3 Mix/Edit; default 2), "id" (default 1..25 in order), "enabled" (default true),
    "members": [track names] or "member_indices": [track indices], "attributes" (optional)}. If '<ALL>' is not listed, it is
    prepended automatically for all tracks 0..N-1.
    Example: python3 ptx_edit.py setgroups a.ptx b.ptx @groups.json"""
    import json
    if not spec.startswith("@") or not os.path.isfile(spec[1:]):
        probe.fail("groups spec '%s' is not @<existing json file>" % spec, 'write a JSON list like [{"name": "G1", "members": ["Au_m_S", "Au_m_T"]}]')
    try:
        grps = json.load(open(spec[1:]))
        assert isinstance(grps, list) and all(isinstance(x, dict) and "name" in x for x in grps)
    except (ValueError, AssertionError):
        probe.fail("%s is not a JSON list of group dicts with 'name'" % spec[1:], 'e.g. [{"name": "G1", "members": ["Au_m_S", "Au_m_T"]}]')
    raw, d, tree = descramble_file(src)
    d = bytes(d)
    dec = _decoder()
    trks = dec.decode(src)["tracks"]
    t_names = [t["name"] for t in trks]
    nt = len(t_names)
    if not any(x["name"] == "<ALL>" for x in grps):
        grps = [{"name": "<ALL>", "type": 2, "id": 0xFFFFFFFF, "enabled": False, "member_indices": list(range(nt)), "attributes": 0x00018010}] + grps
    blks = []
    uid = 0
    for x in grps:
        nm = x["name"]
        if nm != "<ALL>":
            uid += 1
        gid = int(x.get("id", 0xFFFFFFFF if nm == "<ALL>" else uid))
        ty = int(x.get("type", 2))
        en = bool(x.get("enabled", nm != "<ALL>"))
        if "member_indices" in x:
            mems = [int(i) for i in x["member_indices"] if 0 <= int(i) < nt]
        else:
            mems = []
            for m in x.get("members", []):
                if m not in t_names:
                    probe.fail("group '%s': member track '%s' not found" % (nm, m), "tracks: %s" % t_names)
                mems.append(t_names.index(m))
        attr = int(x["attributes"]) if x.get("attributes") is not None else None
        blks.append(_group_202a(nm, gid, en, sorted(set(mems)), attr=attr, ty=ty))
    c202b = _blk(4, 0x202b, struct.pack("<I", len(blks)), *blks, struct.pack("<I", len(blks)), *blks, b"\x00\x00")
    tops = []
    ins_done = False
    for n in tree:
        if n["ct"] == 0x202B:
            continue
        b_ = d[n["pos"]:n["pos"] + 7 + n["size"]]
        tops.append(b_)
        if n["ct"] == 0x2624:
            tops.append(c202b)
            ins_done = True
    if not ins_done:
        tops = tops[:-2] + [c202b] + tops[-2:]
    out = _rebuild_top(d, tree, tops)
    write_new(dst, scramble(out))
    print("wrote %s: %d track group(s) (%s)" % (dst, len(blks), ", ".join(x["name"] for x in grps)))


def _bus_output_base(d, tree, paths):
    """Calibrate 0x260E output bus base = code - ordinal(0x2603) from any assigned strip (clean-room default: 2)."""
    names = [p[1] for p in paths]
    for blk in probe.walk(tree):
        if blk["ct"] != 0x260E or blk["size"] < 42:
            continue
        p = blk["pos"] + 9
        code = struct.unpack_from("<H", d, p)[0]
        if code == 0xFFFF or d[p + 8:p + 12] != _ID_MARK:
            continue
        bn_len = struct.unpack_from("<I", d, p + 36)[0]
        if 0 < bn_len <= 128 and p + 40 + bn_len <= blk["pos"] + 7 + blk["size"]:
            bn = d[p + 40:p + 40 + bn_len].decode("utf-8", "replace")
            if bn in names:
                return code - names.index(bn)
    return 2


def cmd_setoutput(src, dst, track, bus):
    """set the main output (first strip 0x260D > 0x260E) of TRACK to BUS in 0x2603, using calibrated base = code - ordinal."""
    dec = _decoder()
    raw, d, tree = descramble_file(src)
    d = bytes(d)
    io, paths = _io_paths(d, tree)
    hit = [(i, p) for i, p in enumerate(paths) if p[1] == bus]
    if len(hit) != 1 or hit[0][1][5] is None:
        probe.fail("bus path '%s' not found (or twice)" % bus, "create it first: addbus <in> <out> %s [stereo=1]" % bus)
    pidx, (pb, _, bst, _, _, pid) = hit[0]
    path_code = _bus_output_base(d, tree, paths) + pidx
    _, ch = _channel(dec, d, tree, track)
    main = next((x for x in probe.walk([ch]) if x["ct"] == 0x260D), None)
    o260e = next((c for c in (main["kids"] if main else []) if c["ct"] == 0x260E), None)
    if not o260e:
        probe.fail("track '%s' has no main output block 0x260E" % track, "setoutput needs an audio, aux, instrument, master or routing-folder track")
    act_b = d[o260e["pos"] + 11:o260e["pos"] + 13]
    bn = bus.encode("utf-8")
    body = (struct.pack("<H", path_code) + act_b + b"\x00" * 4 + _ID_MARK + pid + b"\x00" * 16 + struct.pack("<I", len(bn)) + bn
            + bytes([bst, bst]) + b"\xff" * 8 + b"\x00" + b"\xff" * 4 + b"\x00\x0c" + bytes([bst, 0]))
    E = [{"p": o260e["pos"] + 9, "ol": o260e["size"] - 2, "nb": body, "enc": None}]
    write_new(dst, scramble(_splice2(d, tree, E)))
    print("wrote %s: output of '%s' -> '%s' (%s, code %d)" % (dst, track, bus, "stereo" if bst else "mono", path_code))


def cmd_addsend(src, dst, track, bus, *opts):
    """send from TRACK to the bus path BUS in the first empty send slot (or slot=a..j), built from fields:
    strip 0x260D = table 0x1029 (slot 0 level dB x 10, 21 = level x 65536, 22 = 65535 + mute, 1 mute; mono track to stereo bus: 3 pan,
    24 = pan x 65536 + 65535, 25 = 65535; stereo track: 10, 11 = 100, 31 - 33 = 6553600), 01 00, output 0x260E (u16 path number, 01,
    active, u32 0, id, 16 zeros, name, stem, stem, ff x 8, 00, ff x 4, 00 0c, stem, 00; pre-fader = first data byte of 0x1029 is 00), 01 volume lane, 01 mute lane, 00, panner(s),
    9 zeros, 0x485A. Options: level=<dB, default 0> pan=<-100..100> pre=1 mute=1 active=0|1 slot=<a..j>.
    Example: python3 ptx_edit.py addsend in.ptx out.ptx Vox FX level=-7.3 pan=-37"""
    o = dict(x.split("=", 1) for x in opts if "=" in x)
    if set(o) - {"level", "pan", "pre", "mute", "slot", "active"} or len(o) != len(opts):
        probe.fail("unknown option in %s" % list(opts), "use level=<dB> pan=<-100..100> pre=1 mute=1 active=0|1 slot=a..j")
    try:
        lv = int(round(float(o.get("level", "0")) * 10)) if o.get("level", "0") not in ("-inf", "-Infinity") else -1440
        pan, pre, mute, act = int(o.get("pan", "0")), o.get("pre", "0") == "1", o.get("mute", "0") == "1", o.get("active", "1") != "0"
    except ValueError:
        probe.fail("level / pan are not numbers", "level in dB (e.g. -7.3), pan -100..100")
    if not -1440 <= lv <= 120 or not -100 <= pan <= 100:
        probe.fail("level %s dB or pan %s out of range" % (lv / 10.0, pan), "level -144..+12 dB, pan -100..100")
    dec = _decoder()
    raw, d, tree = descramble_file(src)
    d = bytes(d)
    io, paths = _io_paths(d, tree)
    hit = [(i, p) for i, p in enumerate(paths) if p[1] == bus]
    if len(hit) != 1 or hit[0][1][5] is None:
        probe.fail("bus path '%s' not found (or twice)" % bus, "create it first: addbus <in> <out> %s [stereo=1]" % bus)
    pidx, (pb, _, bst, _, _, pid) = hit[0]
    _, ch = _channel(dec, d, tree, track)
    strips = [x for x in probe.walk([ch]) if x["ct"] == 0x260D]
    if len(strips) != 11:
        probe.fail("track '%s' has %d strips, 11 expected (main + 10 sends)" % (track, len(strips)), "sends go on audio, aux, instrument tracks and routing folders")
    main, sends = strips[0], strips[1:]
    free = [k for k, x in enumerate(sends) if not any(c["ct"] == 0x260E for c in x["kids"])]
    k = "abcdefghij".index(o["slot"]) if o.get("slot") in list("abcdefghij") else (free[0] if free else -1)
    if k not in free:
        probe.fail("send slot %s of '%s' is not free" % (o.get("slot", "?"), track), "free slots: %s" % "".join("abcdefghij"[i] for i in free))
    tst = 1 if len([c for c in main["kids"] if c["ct"] == 0x260C and c["size"] > 100]) and struct.unpack_from("<i", d, main["kids"][0]["pos"] + 10 + 4 * 10)[0] != 0 and struct.unpack_from("<i", d, sends[k]["kids"][0]["pos"] + 10 + 4 * 3)[0] == -100 else 0
    l0 = next(c for c in main["kids"] if c["ct"] == 0x260A)
    tb = struct.unpack_from("<H", d, l0["pos"] + 17)[0]
    old = sends[k]
    tbl = list(struct.unpack_from("<69i", d, old["kids"][0]["pos"] + 10))
    tbl[0], tbl[21], tbl[22], tbl[1] = lv, lv * 65536, 65535 + int(mute), int(mute)
    if tst:
        tbl[10], tbl[11], tbl[31], tbl[32], tbl[33] = 100, 100, 6553600, 6553600, 6553600
    elif bst:
        tbl[3], tbl[24], tbl[25] = pan, pan * 65536 + 65535, 65535
    bn = bus.encode("utf-8")
    outb = _blk(9, 0x260e, struct.pack("<H", pidx + 2) + (b"\x01\x01" if act else b"\x00\x00") + b"\x00" * 4 + _ID_MARK + pid + b"\x00" * 16 + struct.pack("<I", len(bn)) + bn
                + bytes([bst, bst]) + b"\xff" * 8 + b"\x00" + b"\xff" * 4 + b"\x00\x0c" + bytes([bst, 0]))
    empty = _blk(2, 0x260c, b"\x00" * 14)
    p1 = _panner_tb(-100 if tst else pan, tb) if bst else empty
    p2 = _panner_tb(100, tb) if (bst and tst) else empty
    tblk = _strip_table(dict(enumerate(tbl)))
    if pre:                                                                    # first data byte of 0x1029: 01 post-fader, 00 pre-fader
        tblk = tblk[:9] + b"\x00" + tblk[10:]
    body = (tblk + b"\x01\x00" + outb + b"\x01" + _lane_tb(lv, tb) + b"\x01" + _lane_tb(int(mute), tb) + b"\x00" + p1 + p2 + b"\x00" * 9 + _BLK485A)
    E = [{"p": old["pos"] + 9, "ol": old["size"] - 2, "nb": body, "enc": None}]
    write_new(dst, scramble(_splice2(d, tree, E)))
    print("wrote %s: send %s of '%s' -> '%s' (%.1f dB%s%s)" % (dst, "abcdefghij"[k], track, bus, lv / 10.0, ", pre-fader" if pre else "", ", muted" if mute else ""))


# clean-room stock plug-in inserts, track colour & alternate playlists, timeline, clip loop

def _pack_elck(params, extra=b""):
    out = bytearray(b"\x01\x01\x01\x01")
    for k, v in params:
        kb = k.encode("latin-1") + b"\x00"
        kb += b"\x00" * ((-len(kb)) % 4)
        out += kb
        out += struct.pack(">d", float(v)) if k.startswith("d_") else struct.pack(">i", int(v))
    out += extra + b"\x00\x00\x00\x00"
    return bytes(out)


_CHST_PARAMS = (
    ("l_Process Order", 0), ("l_Phase Switch In/Out", 0), ("d_Input Trim", 0.0), ("d_Fader Volume", 0.0),
    ("l_Fader Volume Pre/Post", 0), ("l_Fader Volume On/Off", 1), ("l_EQ On/Off", 1), ("l_Filters On/Off", 1),
    ("l_Dynamics On/Off", 1), ("l_Dynamics Range", 0), ("l_Dynamics Reveal", 0), ("l_EQ Range", 0), ("l_EQ Reveal", 0),
    ("l_Meters Tab", 0), ("l_Order Tab", 0), ("l_Dynamics Tab", 1), ("l_EQ Tab", 0), ("l_Cmp In/Out", 1),
    ("d_Cmp Ratio", 1.0), ("d_Cmp Knee", 0.0), ("d_Cmp Attack Time", 0.0001), ("d_Cmp Release Time", 0.2),
    ("d_Cmp Gain Makeup", 0.0), ("d_Cmp Threshold", -24.0), ("d_Cmp Depth", -36.0), ("l_Exp In/Out", 1),
    ("d_Exp Ratio", 1.0), ("d_Exp Knee", 0.0), ("d_Exp Attack Time", 2e-05), ("d_Exp Release Time", 0.2),
    ("d_Exp Threshold", -58.0), ("d_Exp Depth", -36.0), ("d_Exp Hold Time", 0.001), ("d_Exp Hysteresis", 0.0),
    ("l_Sc Filter In/Out", 1), ("l_Sc Filter Type", 0), ("d_Sc Filter Frequency", 20.0), ("l_Sc Listen In/Out", 0),
    ("l_Sc Source", 0), ("l_Sc Detector Type Avg/Pk", 1), ("l_EQ Low In/Out", 1), ("l_EQ Low Type", 0),
    ("d_EQ Low Gain", 0.0), ("d_EQ Low Frequency", 41.2), ("d_EQ Low Q", 0.5), ("l_EQ Low Listen In/Out", 0),
    ("l_EQ Low-Mid In/Out", 1), ("d_EQ Low-Mid Gain", 0.0), ("d_EQ Low-Mid Frequency", 329.0), ("d_EQ Low-Mid Q", 0.5),
    ("l_EQ Low-Mid Listen In/Out", 0), ("l_EQ High-Mid In/Out", 1), ("d_EQ High-Mid Gain", 0.0),
    ("d_EQ High-Mid Frequency", 2630.0), ("d_EQ High-Mid Q", 0.5), ("l_EQ High-Mid Listen In/Out", 0),
    ("l_EQ High In/Out", 1), ("l_EQ High Type", 0), ("d_EQ High Gain", 0.0), ("d_EQ High Frequency", 10500.0),
    ("d_EQ High Q", 0.5), ("l_EQ High Listen In/Out", 0), ("l_Filter 1 In/Out", 0), ("l_Filter 1 Type", 0),
    ("d_Filter 1 Frequency", 20.6), ("d_Filter 1 Q", 0.5), ("l_Filter 1 Slope 12/24dB", 0), ("l_Filter 1 Listen In/Out", 0),
    ("l_Filter 2 In/Out", 0), ("l_Filter 2 Type", 1), ("d_Filter 2 Frequency", 21000.0), ("d_Filter 2 Q", 0.5),
    ("l_Filter 2 Slope 12/24dB", 0), ("l_Filter 2 Listen In/Out", 0),
)

_EQ3_7_PARAMS = (
    ("l_hak3", 0), ("l_hak1", 0), ("d_inpt", 0.0), ("d_outp", 0.0), ("l_Phse", 0), ("l_hprg", 1), ("l_in 1", 0),
    ("d_hpfq", 1.0), ("l_hpfs", 0), ("d_frq1", 20.0), ("l_in 2", 1), ("d_gai2", 0.0), ("d_frq2", 100.0), ("d_bnd2", 1.0),
    ("l_lfrg", 1), ("l_in 3", 1), ("d_gai3", 0.0), ("d_frq3", 200.0), ("d_bnd3", 1.0), ("l_in 4", 1), ("d_gai4", 0.0),
    ("d_frq4", 1000.0), ("d_bnd4", 1.0), ("l_in 5", 1), ("d_gai5", 0.0), ("d_frq5", 2000.0), ("d_bnd5", 1.0),
    ("l_in 6", 1), ("d_gai6", 0.0), ("d_frq6", 6000.0), ("d_bnd6", 1.0), ("l_hfrg", 1), ("l_lprg", 1), ("l_in 7", 0),
    ("d_lpfq", 1.0), ("l_lpfs", 0), ("d_frq7", 20000.0), ("l_hak2", 0),
)

_AUTOPAN_PARAMS = (
    ("d_outg", 0.0), ("d_angl", 0.0), ("d_posi", 100.0), ("d_sprd", 75.0), ("d_wdth", 100.0), ("d_offs", 50.0),
    ("l_mods", 0), ("l_dirn", 0), ("d_temp", 120.0), ("l_wave", 0), ("l_mtrg", 0), ("l_ones", 0), ("l_mbck", 0),
    ("l_etrg", 0), ("l_dura", 12), ("d_thrs", -20.0), ("d_attk", 10.0), ("d_rels", 20.0), ("l_ukey", 0),
    ("d_stem", 120.0), ("l_ftem", 0), ("l_vers", 0),
)

_DYN3_PARAMS = (
    ("d_sldG", 0.0), ("d_sld2", 3.0), ("d_sld1", 0.01), ("d_sld3", 0.08), ("d_sldD", 0.0), ("d_sldC", -24.0),
    ("l_Phse", 0), ("d_HiFF", 20000.0), ("l_HiRG", 1), ("l_HiFE", 0), ("d_LoFF", 20.0), ("l_LoRG", 1),
    ("l_LoFE", 0), ("l_sldE", 0),
)

_STOCK_PLUGINS = {
    "EQ3 1-Band": {"vid": "com.digidesign.aax.eq3.1band", "mfr": "Digi", "prod": "1be3", "mono": ("1emr", "1emr"), "stereo": ("1esr", "1esr"),
                   "fmt": "elck", "ver": -1, "lat": 0,
                   "params": (("l_hak1", 0), ("d_gain", 0.0), ("d_ctrf", 1000.0), ("d_bndw", 1.0), ("l_slop", 1), ("l_type", 3), ("d_trim", 0.0), ("l_Phse", 0))},
    "EQ3 7-Band": {"vid": "com.digidesign.aax.eq3.7band", "mfr": "Digi", "prod": "47e3", "mono": ("7emr", "7emr"), "stereo": ("7esr", "7esr"),
                   "fmt": "elck", "ver": -1, "lat": 0, "params": _EQ3_7_PARAMS},
    "Channel Strip": {"vid": "com.avid.aax.sdk.ChannelStrip", "mfr": "AVID", "prod": "ChSt", "mono": ("CMRT", "CMRT"), "stereo": ("CSRT", "CSRT"),
                      "fmt": "elck", "ver": -1, "lat": 0x64, "params": _CHST_PARAMS},
    "Dyn3 Compressor/Limiter": {"vid": "com.avid.aax.dyn3.Compressor", "mfr": "Digi", "prod": "dn3c", "mono": ("CMRT", "CMRT"), "stereo": ("CSRT", "CSRT"),
                                "fmt": "elck", "ver": -1, "lat": 0x64, "params": _DYN3_PARAMS},
    "AutoPan": {"vid": "com.avid.aax.tl.AutoPan", "mfr": "TrLn", "prod": "APan", "mono": ("rtms", "rtms"), "stereo": ("rtss", "rtss"),
                "fmt": "elck", "ver": -1, "lat": 0x64, "m2s": True, "params": _AUTOPAN_PARAMS},
    "Click II": {"vid": "com.avid.aax.sdk.megaclick", "mfr": "Digi", "prod": "clik", "mono": ("CkRT", "CkRT"), "stereo": ("CkRT", "CkRT"),
                 "fmt": "elck", "ver": -1, "lat": 0, "be_len": 40, "params": (("d_AcAt", 0.5), ("d_UnAt", 0.5)),
                 "extra": struct.pack(">Ii16s32sii", 224, 1, b"DigiclikCkRTAll ", b"\x00" * 32, 35, 36)
                          + b"Classic Click Acc".ljust(60, b"\x00") + struct.pack(">I", 17)
                          + b"Classic Click".ljust(60, b"\x00") + struct.pack(">I8i", 13, 2, -0x80000000, -0x80000000, 2, -0x80000000, -0x80000000, 0x7fffffff, 0x7fffffff)},
    "Trim": {"vid": "com.avid.aax.trim", "mfr": "Digi", "prod": "Trim", "mono": ("TR11", "TR11"), "stereo": ("TR11", "TR11"),
             "fmt": "All ", "ver": 2, "lat": 0, "values": (0x72bcaf28, -0x80000000, -0x80000000, -0x80000000, 0)},
    "D-Verb": {"vid": "com.avid.aax.dverb", "mfr": "Digi", "prod": "Rvrb", "mono": ("movh", "movh"), "stereo": ("stvh", "stvh"),
               "fmt": "All ", "ver": 1, "lat": 0,
               "values": (-0x80000000, 0x7fffffff, 0x20ffffff, 0x7fffffff, 0x60000000, 0, 0x40ab3680, 0x7fffffff, -0x80000000, 0, 0)},
    "Dither": {"vid": "com.avid.aax.dither", "mfr": "Digi", "prod": "Dthr", "mono": ("msrd", "msrd"), "stereo": ("ssrd", "ssrd"),
               "fmt": "All ", "ver": 1, "lat": 0, "values": (0, 0x7fffffff, 0x7fffffff, 0)},
    "POW-r Dither": {"vid": "com.avid.aax.powr", "mfr": "Digi", "prod": "POWr", "mono": ("mmpr", "mmpr"), "stereo": ("sspr", "sspr"),
                     "fmt": "All ", "ver": 1, "lat": 0, "values": (0x7fffffff, -0x80000000, 0)},
    "Time Adjuster": {"vid": "com.avid.aax.timeadjuster", "mfr": "Digi", "prod": "PIGD", "mono": ("11pl", "11pl"), "stereo": ("11pl", "11pl"),
                      "fmt": "All ", "ver": 3, "lat": 0, "values": (0, 0, 0, 0, 0, 0, 4, 4, 0)},
    "BF-76": {"vid": "com.avid.aax.bf76", "mfr": "BFD ", "prod": "1176", "mono": ("mm76", "mm76"), "stereo": ("mm76", "mm76"),
              "fmt": "All ", "ver": 10, "lat": 0x64, "values": (-558345749, 558345748, -730144512, 816043929, -0x80000000, 0x7fffffff, 0)},
    "Sci-Fi": {"vid": "com.avid.aax.scifi", "mfr": "Digi", "prod": "SciF", "mono": ("RMSF", "stmo"), "stereo": ("RMSF", "stmo"),
               "fmt": "All ", "ver": 1, "lat": 0, "values": (0x7fffffff, -0x80000000, -0x80000000, -0x80000000, -0x80000000, -0x80000000, -0x80000000, 0)},
    "Lo-Fi": {"vid": "com.avid.aax.lofi", "mfr": "Digi", "prod": "LoFi", "mono": ("RMLF", "ltmo"), "stereo": ("RMLF", "ltmo"),
              "fmt": "All ", "ver": 1, "lat": 0, "values": (0x7fffffff, 0x7fffffff, 0x7fffffff, -0x80000000, -0x80000000, 0, -0x80000000, -0x80000000, 0)},
    "SansAmp PSA-1": {"vid": "com.avid.aax.sansamp", "mfr": "BFD ", "prod": "PSA1", "mono": ("mmps", "mmps"), "stereo": ("mmps", "mmps"),
                      "fmt": "All ", "ver": 5, "lat": 0, "values": (0, -1073741824, 0, -42949673, 858993459, 85899345, 644245094, 515396075, 747324309, 0)},
    "Mod Delay III": {"vid": "com.avid.aax.moddelay3", "mfr": "Avid", "prod": "mdl3", "mono": ("xmm3", "xmm3"), "stereo": ("xss3", "xss3"),
                      "fmt": "MD_3", "ver": 8, "lat": 0, "be_len": 96,
                      "raw_fn": lambda c38="xmm3": (
                          struct.pack(">12i", 0x7fffffff, 0x7fffffff, -0x80000000, -0x80000000, 0x7fffffff, 0x7fffffff, -0x73333333, -0x73333333,
                                      0x7fffffff, 0x7fffffff, -0x80000000, -0x80000000)
                          + b"\x00" * 10
                          + struct.pack(">5i", -0x448676f3, -0x6739ce74, -0x6739ce74, -0x80000000, -0x80000000)
                          + b"\x00" * 11 + b"\x01\x00\x00" + struct.pack(">II", 57, 8)
                          + b"Avidmdl3" + c38.encode("latin-1") + b"ShHi" + b"\x00" * 37)},
    "Pitch II": {"vid": "com.avid.aax.pitch", "mfr": "Digi", "prod": "Pish", "mono": ("mmPi", "mmPi"), "stereo": ("ssPi", "ssPi"),
                 "fmt": "PiII", "ver": 1, "lat": 0,
                 "raw_fn": lambda c38="mmPi": struct.pack(">IIII3d", 1, 0x01000000, 0x01000000, 3, 1.0, 0.03, 0.5) + b"\x00" * 24
                                   + (struct.pack(">d8sQ20s", 100.0, b"\x00" * 8, 0x40d5887ffffffffd, b"\x00" * 20) * 2)},
}


def _build_1017(name, mfr, prod, code17, vid, is_stereo=False, m2s=False, lat=0, kind=3):
    nb = name.encode("utf-8")
    vb = vid.encode("utf-8")
    c_rev = mfr.encode("latin-1")[::-1] + prod.encode("latin-1")[::-1] + code17.encode("latin-1")[::-1]
    if m2s:
        mid = b"\x01\x00\x02\x01" + struct.pack("<H", lat) + b"\x00"
        tail = b"\x00\x01\x00\x01" + struct.pack("<II", 1, 2)
    elif is_stereo:
        mid = b"\x02\x01\x02\x01" + struct.pack("<H", lat) + b"\x00"
        tail = b"\x01\x01\x01\x01" + struct.pack("<II", 2, 2)
    else:
        mid = b"\x01\x00\x01\x00" + struct.pack("<H", lat) + b"\x00"
        tail = b"\x00\x00\x00\x00" + struct.pack("<II", 1, 1)
    return _blk(9, 0x1017, bytes([kind]) + struct.pack("<I", len(nb)) + nb + c_rev + mid + struct.pack("<I", len(vb)) + vb + tail)


def _build_2616(tidx, mfr, prod, code38, fmt, ver, body, active=True, bypass=False, multi_mono=False, sidx=0xFFFF, be_len=None):
    cname = b"Complete Controls State".ljust(32, b"\x00") if fmt == "elck" else b"\x00" * 32
    be_sz = 52 + (be_len if be_len is not None else len(body))
    b1038 = _blk(2, 0x1038, struct.pack("<II", 1, 52 + len(body)) + struct.pack(">Ii", be_sz, ver)
                 + mfr.encode("latin-1") + prod.encode("latin-1") + code38.encode("latin-1") + fmt.encode("latin-1") + cname + body)
    b260e = _blk(9, 0x260e, b"\xff\xff\x01\x01" + b"\x00" * 38 + b"\xff" * 8 + b"\x00" + b"\xff" * 4 + b"\x00\x0c\x00\x00")
    act = 1 if active else 0
    tail326 = (bytes([act]) + b"\x00" * 6 + struct.pack("<I", 15) + b"\x00" * 56 + struct.pack("<I", 15) + b"\x00" * 28
               + struct.pack("<I", 6) + b"\x00" * 10 + struct.pack("<I", 6) + b"\x00" * 10 + b"\x01\x00\x00"
               + b"\x01" * 64 + b"\x00" * 64 + b"\x10" + b"\x00" * 33 + b"\x10" + b"\x00" * 33)
    b2613 = _blk(10, 0x2613, struct.pack("<H", sidx & 0xFFFF), b1038, bytes([act, 0, 0xFF, 0xFF]), b260e, tail326)
    b2615 = _blk(1, 0x2615, _blk(1, 0x2626), struct.pack("<H", tidx), b2613)
    b2616 = _blk(1, 0x2616, b2615, bytes([1 if bypass else 0]), _blk(1, 0x2614, struct.pack("<I", 0)))
    return _blk(1, 0x2617, b2616, b"\x02") if multi_mono else b2616


def cmd_addplugin(src, dst, track, slot, plugin, *opts):
    """insert a stock plug-in built from documented fields into SLOT (a..j) of TRACK.
    Options: bypass=0|1 active=0|1 multi=0|1 state=default|empty delay=<samples> values=<i1,i2,...> param.<name>=<val>.
    Example: python3 ptx_edit.py addplugin in.ptx out.ptx Au_m_T a 'EQ3 1-Band' param.d_gain=3.7"""
    if plugin not in _STOCK_PLUGINS:
        probe.fail("unknown stock plug-in '%s'" % plugin, "supported: %s" % ", ".join(sorted(_STOCK_PLUGINS)))
    slot = slot.lower()
    if slot not in "abcdefghij" or len(slot) != 1:
        probe.fail("invalid slot '%s'" % slot, "use slot a..j")
    k_slot = "abcdefghij".index(slot)
    o = {}
    p_ovr = {}
    for x in opts:
        if "=" not in x:
            probe.fail("option '%s' has no '='" % x, "use bypass=0|1 active=0|1 multi=0|1 state=default|empty delay=N values=i1,i2,.. param.<k>=<v>")
        k, v = x.split("=", 1)
        if k.startswith("param."):
            p_ovr[k[6:]] = v
        else:
            o[k] = v
    if set(o) - {"bypass", "active", "multi", "state", "delay", "values"}:
        probe.fail("unknown option in %s" % list(o), "use bypass=0|1 active=0|1 multi=0|1 state=default|empty delay=N values=i1,i2,.. param.<k>=<v>")
    dec = _decoder()
    raw, d, tree = descramble_file(src)
    d = bytes(d)
    tidx_tr, ch = _channel(dec, d, tree, track)
    tinfo = dec.tracks(d, tree, [])[tidx_tr]
    tst = bool(tinfo.get("stereo"))
    multi = o.get("multi") == "1" if "multi" in o else False
    spec = _STOCK_PLUGINS[plugin]
    use_st = tst and not multi
    c17, c38 = spec["stereo" if use_st else "mono"]
    is_st_1017 = use_st and (c17 != spec["mono"][0] or plugin == "Dither")
    m2s = bool(spec.get("m2s") and not use_st)
    if o.get("state") == "empty":
        body = b""
    elif spec["fmt"] == "elck":
        plist = [(pk, float(p_ovr[pk]) if pk in p_ovr and pk.startswith("d_") else (int(p_ovr[pk]) if pk in p_ovr else pv))
                 for pk, pv in spec["params"]]
        body = _pack_elck(plist, spec.get("extra", b""))
    elif spec["fmt"] == "All ":
        vals = list(spec["values"])
        if "delay" in o and plugin == "Time Adjuster":
            dl = int(o["delay"])
            vals[6] = vals[7] = dl
        if "values" in o:
            vals = [int(v) for v in o["values"].split(",")]
        norm_i32 = lambda fv: max(-0x80000000, min(0x7fffffff, int(round((float(fv) - 0.5) * 2 ** 32))))
        bool_i32 = lambda bv, off=0: 0x7fffffff if str(bv).lower() in ("1", "true", "on", "yes") else off
        _TRIM_KNOTS = ((0.0, -144.0), (0.10, -53.10), (0.25, -23.40), (0.40, -14.60), (0.50, -10.40), (0.755, 0.0))
        def _trim_db_to_norm(db, rng_db):
            if db <= -144.0:
                return 0.0
            if db >= 0.0:
                return min(1.0, 0.755 + (db / max(rng_db, 1)) * (1.0 - 0.755))
            for (x0, y0), (x1, y1) in zip(_TRIM_KNOTS, _TRIM_KNOTS[1:]):
                if db <= y1:
                    return x0 + (db - y0) / (y1 - y0) * (x1 - x0)
            return 0.755
        _ALL_PARAM_MAP = {
            "Sci-Fi": {"input_level": (0, "norm"), "effect_type": (1, "norm"), "effect_frequency": (2, "norm"),
                       "effect_depth": (3, "norm"), "slot_4": (4, "norm"), "mod_depth": (5, "norm"),
                       "mod_rate_slew_thresh": (6, "norm"), "master_bypass": (7, "bypass")},
            "Trim": {"gain_norm": (0, "norm"), "gain_db": (0, "trim_db"), "phase_invert": (1, "bool"), "gain_range_db": (3, "range"), "master_bypass": (4, "bypass")},
            "Time Adjuster": {"delay_samples": (6, "delay"), "master_bypass": (8, "bypass")},
            "Lo-Fi": {"distortion": (6, "norm"), "master_bypass": (8, "bypass")},
        }
        pmap = _ALL_PARAM_MAP.get(plugin, {})
        # Apply gain_range_db before gain_db if both are provided
        ordered_ovr = sorted(p_ovr.items(), key=lambda kv: (kv[0] != "gain_range_db", kv[0]))
        for pk, pv in ordered_ovr:
            if pk not in pmap:
                continue
            idx, kind_p = pmap[pk]
            if kind_p == "norm":
                vals[idx] = norm_i32(pv)
            elif kind_p == "trim_db":
                rng_db = 12 if vals[3] > 0 else 6
                vals[idx] = norm_i32(_trim_db_to_norm(float(pv), rng_db))
            elif kind_p == "bool":
                vals[idx] = bool_i32(pv, -0x80000000)
            elif kind_p == "bypass":
                vals[idx] = bool_i32(pv, 0)
            elif kind_p == "range":
                vals[idx] = 0x7fffffff if int(pv) >= 12 else -0x80000000
            elif kind_p == "delay":
                vals[6] = vals[7] = int(pv)
        body = struct.pack(">%di" % len(vals), *vals)
    else:
        body = spec["raw_fn"](c38)
    entry17 = _build_1017(plugin, spec["mfr"], spec["prod"], c17, spec["vid"], is_stereo=is_st_1017, m2s=m2s, lat=spec["lat"])
    # Check if 0x1018 exists; if not, insert 0x1018 right after 0x262E (or before 0x2603 / 0x2000) and rebuild top
    ttab = next((n for n in tree if n["ct"] == 0x1018), None)
    if ttab is None:
        c1018 = _blk(1, 0x1018, struct.pack("<I", 1), entry17)
        tops = []
        ins_done = False
        for n in tree:
            b_ = d[n["pos"]:n["pos"] + 7 + n["size"]]
            tops.append(b_)
            if n["ct"] == 0x262E and not ins_done:
                tops.append(c1018)
                ins_done = True
        if not ins_done:
            tops = tops[:-2] + [c1018] + tops[-2:]
        d = _rebuild_top(d, tree, tops)
        tree = probe.parse(d, HEADER, len(d))
        ttab = next(n for n in tree if n["ct"] == 0x1018)
        _, ch = _channel(dec, d, tree, track)
    texist = [bytes(d[k["pos"]:k["pos"] + 7 + k["size"]]) for k in ttab["kids"]]
    E = []
    if entry17 in texist:
        tidx = texist.index(entry17)
    else:
        tidx = len(ttab["kids"])
        cnt = struct.unpack_from("<I", d, ttab["pos"] + 9)[0]
        end_t = ttab["pos"] + 7 + ttab["size"]
        E.append({"p": ttab["pos"] + 9, "ol": 4, "nb": struct.pack("<I", cnt + 1), "enc": None})
        E.append({"p": end_t, "ol": 0, "nb": entry17, "enc": ttab["pos"]})
    lst = next((x for x in dec._subtree(ch) if x["ct"] == 0x2627), None)
    if not lst or k_slot >= len(lst["kids"]):
        probe.fail("track '%s' has no insert slot %s" % (track, slot), "use audio, aux, instrument, master or routing-folder track")
    tgt = lst["kids"][k_slot]
    b2616 = _build_2616(tidx, spec["mfr"], spec["prod"], c38, spec["fmt"], spec["ver"], body,
                        active=o.get("active", "1") != "0", bypass=o.get("bypass", "0") == "1", multi_mono=multi, be_len=spec.get("be_len"))
    E.append({"p": tgt["pos"], "ol": 7 + tgt["size"], "nb": b2616, "enc": None})
    out = _splice2(d, tree, E)
    tr2 = probe.parse(out, HEADER, len(out))
    last = tr2[-1]
    if last["ct"] == 0x0002:
        out = out[:last["pos"]] + _blk(2, 0x0002, _dir_build(tr2))
    write_new(dst, scramble(out))
    print("wrote %s: slot %s of '%s' <- %s (%s, %d B state)" % (dst, slot, track, plugin, "multi-mono" if multi else ("stereo" if use_st else "mono"), len(body)))


def cmd_setcolor(src, dst, *pairs):
    """set the track colour index in 0x2519 > 0x251A (both group A and group B entries): TRACK COLOUR [...].
    COLOUR = -2 or 'none' (default colour), or stored colour index 25..93.
    Example: python3 ptx_edit.py setcolor in.ptx out.ptx Au_m_S 29 Au_m_T 44"""
    if not pairs or len(pairs) % 2:
        probe.fail("need TRACK COLOUR pairs", "usage: setcolor <in> <out> TRACK COLOUR [...]")
    raw, d, tree = descramble_file(src)
    census = probe.census(tree)
    out = bytearray(d)
    for name, cval in zip(pairs[::2], pairs[1::2]):
        col = -2 if cval.lower() in ("none", "default", "-2") else int(cval)
        hits = 0
        for n in probe.walk(tree):
            if n["ct"] != 0x251A or out[n["pos"] + 9] != 0:
                continue
            ln = struct.unpack_from("<I", out, n["pos"] + 11)[0]
            e = n["pos"] + 15 + ln
            if ln <= 255 and e + 64 <= n["pos"] + 7 + n["size"]:
                nm = out[n["pos"] + 15:e].decode("utf-8", "replace")
                if nm == name:
                    struct.pack_into("<h", out, e + 62, col)
                    hits += 1
        if not hits:
            probe.fail("track '%s' not found in 0x2519 > 0x251A" % name, "check track name with ptx_decode")
        print("%s colour -> %d (%d 0x251A blocks)" % (name, col, hits))
    out = bytes(out)
    if probe.census(probe.parse(out, HEADER, len(out))) != census:
        probe.fail("edited file does not parse like the original", "nothing written")
    write_new(dst, scramble(out))
    print("wrote %s (%d bytes)" % (dst, len(out)))


def cmd_addplaylist(src, dst, *pairs):
    """append empty alternate playlist(s) to Audio track(s): TRACK PLAYLIST_NAME [...].
    Appends 1 (mono) or 2 (stereo) empty 0x1052 playlists to 0x1054, a 0x1014 link to 0x1015, and the new 0x1014 index
    to the track's 0x261C channel block between 0x261B and 0x200B.
    Example: python3 ptx_edit.py addplaylist in.ptx out.ptx Au_m_S Au_m_S.01 Au_m_T Au_m_T.01"""
    if not pairs or len(pairs) % 2:
        probe.fail("need TRACK PLAYLIST_NAME pairs", "usage: addplaylist <in> <out> TRACK PLAYLIST_NAME [...]")
    dec = _decoder()
    raw, d, tree = descramble_file(src)
    d = bytes(d)
    for tname, plname in zip(pairs[::2], pairs[1::2]):
        tidx_tr, ch = _channel(dec, d, tree, tname)
        tinfo = dec.tracks(d, tree, [])[tidx_tr]
        if ch["ct"] != 0x261C:
            probe.fail("track '%s' is not an Audio track (0x261C)" % tname, "addplaylist supports Audio tracks")
        stereo = 1 if tinfo.get("stereo") else 0
        nch = 2 if stereo else 1
        st = bytes([stereo])
        nn = struct.pack("<I", len(plname.encode("utf-8"))) + plname.encode("utf-8")
        p54 = next((n for n in tree if n["ct"] == 0x1054), None)
        p15 = next((n for n in tree if n["ct"] == 0x1015), None)
        if not p54 or not p15:
            probe.fail("missing 0x1054 or 0x1015 in session", "unknown layout")
        b1b = next((x for x in ch["kids"] if x["ct"] == 0x261B), None)
        b0b = next((x for x in ch["kids"] if x["ct"] == 0x200B), None)
        p1b_end = b1b["pos"] + 7 + b1b["size"]
        mid = d[p1b_end:b0b["pos"]]
        aidx, npl = struct.unpack_from("<IH", mid, 0)
        pidxs = list(struct.unpack_from("<%dI" % npl, mid, 6))
        # Determine timebase (1 samples, 2 ticks) from the track's active 0x1052 playlist or track name suffix
        tb_code = 2 if tname.endswith("_T") else 1
        k14s = [k for k in p15["kids"] if k["ct"] == 0x1014]
        k52s = [k for k in p54["kids"] if k["ct"] == 0x1052]
        if aidx < len(k14s):
            p0 = k14s[aidx]["pos"] + 9
            ln0 = struct.unpack_from("<I", d, p0)[0]
            pl0_idx = struct.unpack_from("<H", d, p0 + 9 + ln0)[0]
            if pl0_idx < len(k52s) and not k52s[pl0_idx]["kids"]:
                q0 = k52s[pl0_idx]["pos"] + 9
                qln = struct.unpack_from("<I", d, q0)[0]
                if q0 + 4 + qln + 5 <= k52s[pl0_idx]["pos"] + 7 + k52s[pl0_idx]["size"]:
                    tb_code = d[q0 + 4 + qln + 4]
        pl0 = len(k52s)
        new_idx14 = len(k14s)
        pid = _rnd(8)
        b52s = [_blk(3, 0x1052, nn + b"\x00\x00\x00\x00" + struct.pack("<H", tb_code)) for _ in range(nch)]
        b14 = _blk(9, 0x1014, nn + st + struct.pack("<I", nch) + b"".join(struct.pack("<H", pl0 + c_) for c_ in range(nch))
                   + b"\x00\x00\x00\x00" + _ID_MARK + pid + (b"\x01\x00\x01\x00\x00\x00\x00" if stereo else b"\x00" * 7)
                   + b"".join(struct.pack("<I", pl0 + c_) for c_ in range(nch)) + st + b"\x00" * 5)
        tail54 = p54["kids"][-1]
        tail15 = p15["kids"][-1]
        E = [
            {"p": p54["pos"] + 9, "ol": 4, "nb": struct.pack("<I", pl0 + nch), "enc": None},
            {"p": tail54["pos"], "ol": 0, "nb": b"".join(b52s), "enc": p54["pos"]},
            {"p": p15["pos"] + 9, "ol": 4, "nb": struct.pack("<I", new_idx14 + 1), "enc": None},
            {"p": tail15["pos"], "ol": 0, "nb": b14, "enc": p15["pos"]},
            {"p": p1b_end, "ol": len(mid),
             "nb": struct.pack("<IH", aidx, npl + 1) + struct.pack("<%dI" % (npl + 1), *(pidxs + [new_idx14])) + b"\xff\xff",
             "enc": ch["pos"]},
        ]
        d = _splice2(d, tree, E)
        tree = probe.parse(d, HEADER, len(d))
    last = tree[-1]
    if last["ct"] == 0x0002:
        d = d[:last["pos"]] + _blk(2, 0x0002, _dir_build(tree))
    write_new(dst, scramble(d))
    print("wrote %s: added %d alternate playlist(s)" % (dst, len(pairs) // 2))


def cmd_settimeline(src, dst, *opts):
    """set session timecode rate, start timecode, pull factor, and/or record mode in 0x204D, 0x204B, 0x2023, 0x2058.
    Options: tc_rate=<24|25|29.97|29.97 Drop|30|...> tc_start=<HH:MM:SS:FF> pull=<None|+0.1%|-0.1%|...> record_mode=<Normal|Loop|Destructive|QuickPunch>.
    Example: python3 ptx_edit.py settimeline in.ptx out.ptx tc_rate=25 tc_start=01:00:00:00 pull=None"""
    dec = _decoder()
    o = dict(x.split("=", 1) for x in opts if "=" in x)
    if set(o) - {"tc_rate", "tc_start", "pull", "record_mode"} or len(o) != len(opts):
        probe.fail("unknown option in %s" % list(opts), "use tc_rate=.. tc_start=.. pull=.. record_mode=..")
    raw, d, tree = descramble_file(src)
    d = bytes(d)
    E = []
    if "tc_rate" in o or "tc_start" in o:
        rev_tc = {v.lower(): k for k, v in dec.TC_RATES.items()}
        tc_key = o.get("tc_rate", "25").lower()
        rc = rev_tc[tc_key] if tc_key in rev_tc else (int(o["tc_rate"]) if o.get("tc_rate", "").isdigit() else 2)
        tc_str = o.get("tc_start", "24:00:00;00" if rc in (5, 8, 12, 14, 19, 21) else "24:00:00:00").encode("ascii")
        rc_base = {15: 9, 16: 1, 10: 2, 17: 2, 11: 3, 18: 3, 12: 5, 19: 5, 13: 7, 20: 7, 14: 8, 21: 8}.get(rc, rc)
        sf = 0
        if "tc_start" in o:
            m_tc = re.match(r"^(\d+):(\d+):(\d+)[:;](\d+)", o["tc_start"])
            if m_tc:
                hh, mm, ss, ff = (int(x) for x in m_tc.groups())
                if hh == 24:
                    hh = 1
                fps = {1: 24, 2: 25, 3: 30, 5: 30, 7: 30, 8: 30, 9: 24}.get(rc_base, 25)
                sf = ((hh * 3600 + mm * 60 + ss) * fps) + ff
                if rc_base in (5, 8):
                    tot_min = hh * 60 + mm
                    sf -= 2 * (tot_min - tot_min // 10)
        sf2 = sf * 4 if rc_base in (5, 8) else sf
        b4d_body = (struct.pack("<I", rc_base) + b"\x00" * 5 + struct.pack("<I", sf) + b"\x00" * 4 + struct.pack("<II", 1, rc_base)
                    + struct.pack("<I", len(tc_str)) + tc_str + struct.pack("<III", rc, sf2, rc)
                    + struct.pack("<I", len(tc_str)) + tc_str)
        b4d = next((n for n in tree if n["ct"] == 0x204D), None)
        if b4d:
            E.append({"p": b4d["pos"] + 9, "ol": b4d["size"] - 2, "nb": b4d_body, "enc": None})
        else:
            c4d = _blk(5, 0x204d, b4d_body)
            tops = []
            ins_done = False
            for n in tree:
                if n["ct"] == 0x2637 and not ins_done:
                    tops.append(c4d)
                    ins_done = True
                tops.append(d[n["pos"]:n["pos"] + 7 + n["size"]])
            if not ins_done:
                tops = tops[:-2] + [c4d] + tops[-2:]
            d = _rebuild_top(d, tree, tops)
            tree = probe.parse(d, HEADER, len(d))
        b4b = next((n for n in tree if n["ct"] == 0x204B), None)
        if b4b and b4b["size"] >= 2 + 163:
            E.append({"p": b4b["pos"] + 9 + 162, "ol": 1, "nb": bytes([rc]), "enc": None})
    if "pull" in o:
        rev_p = {v.lower(): k for k, v in dec.PULL_CODES.items()}
        pf = int(o["pull"]) if o["pull"].isdigit() else rev_p.get(o["pull"].lower(), 12000)
        b23 = next((n for n in tree if n["ct"] == 0x2023), None)
        if b23 and b23["size"] >= 2 + 64:
            E.append({"p": b23["pos"] + 9 + 62, "ol": 2, "nb": struct.pack("<H", pf), "enc": None})
    if "record_mode" in o:
        rev_rm = {v.lower(): k for k, v in dec.RECORD_MODES.items()}
        rm = int(o["record_mode"]) if o["record_mode"].isdigit() else rev_rm.get(o["record_mode"].lower(), 0)
        b58 = next((n for n in tree if n["ct"] == 0x2058), None)
        if b58 and b58["size"] >= 2 + 65:
            E.append({"p": b58["pos"] + 9 + 48, "ol": 1, "nb": bytes([rm]), "enc": None})
            E.append({"p": b58["pos"] + 9 + 64, "ol": 1, "nb": bytes([rm]), "enc": None})
    if E:
        d = _splice2(d, tree, E)
        tr2 = probe.parse(d, HEADER, len(d))
        if tr2[-1]["ct"] == 0x0002:
            d = d[:tr2[-1]["pos"]] + _blk(2, 0x0002, _dir_build(tr2))
    write_new(dst, scramble(d))
    print("wrote %s: timeline updated (%s)" % (dst, ", ".join("%s=%s" % (k, v) for k, v in o.items())))


def cmd_setcliploop(src, dst, track, pos, *opts):
    """attach a 0x242B clip-loop block to the clip placement 0x104F starting at POS on TRACK (sync-point aware; refuses fade-out collision).
    Options: mode=1|2 (1 = loop length bars|beats|ticks, 2 = loop count) bars=0 beats=0 ticks=0 count=1 trim_ticks=0 iter_ticks=7680000
    [trim_samples=0] [iter_samples=N] [unit=ticks|samples].
    Example: python3 ptx_edit.py setcliploop in.ptx out.ptx Au_m_T t0 mode=2 bars=8 count=16 iter_ticks=1920000"""
    o = dict(x.split("=", 1) for x in opts if "=" in x)
    if set(o) - {"mode", "bars", "beats", "ticks", "count", "trim_ticks", "iter_ticks", "trim_samples", "iter_samples", "unit"} or len(o) != len(opts):
        probe.fail("unknown option in %s" % list(opts), "use mode=1|2 bars=B beats=b ticks=t count=N trim_ticks=T iter_ticks=L [unit=ticks|samples]")
    mode = int(o.get("mode", 2 if "count" in o and "bars" not in o else 1))
    bars, beats, ticks, cnt = int(o.get("bars", 0)), int(o.get("beats", 0)), int(o.get("ticks", 0)), int(o.get("count", 1))
    trim_v = int(o.get("trim_samples", o.get("trim_ticks", 0)))
    iter_v = int(o.get("iter_samples", o.get("iter_ticks", 7680000)))
    def _blk_242b(is_ticks):
        u = b"\x40" if is_ticks else b"\x00"
        return _blk(2, 0x242b, bytes([mode]) + b"\x00" * 10 + struct.pack("<5I", bars, beats, ticks, 0, cnt)
                    + trim_v.to_bytes(7, "little") + u + iter_v.to_bytes(7, "little") + u + b"\x00" * 10)
    raw, d, tree = descramble_file(src)
    d = bytes(d)
    dec = _decoder()
    target_pos = int(pos) if pos.isdigit() else _pos(dec, d, tree, pos)
    res_ = dec.decode(src)
    tempo_ = res_.get("tempo_used") or [{"ticks": 0, "bpm": 120.0}]
    rate_ = (res_.get("format") or {}).get("sample_rate") or 48000
    lst_ = next((n for n in probe.walk(tree) if n["ct"] == 0x262A), None)
    wraps_ = [k for k in lst_["kids"] if k["ct"] == 0x2629] if lst_ else []
    E = []
    for n in probe.walk(tree):
        if n["ct"] == 0x1052:
            p = n["pos"] + 9
            ln = struct.unpack_from("<I", d, p)[0]
            if ln > 256 or p + 4 + ln > n["pos"] + 7 + n["size"]:
                continue
            nm = d[p + 4:p + 4 + ln].decode("utf-8", "replace")
            if nm != track:
                continue
            clip_e, span = _find_clip_at(dec, d, tree, wraps_, n, target_pos, tempo_, rate_)
            if clip_e and span:
                e = clip_e["kids"][0]
                if any(k["ct"] == 0x242B for k in e["kids"]):
                    continue
                c_end = span[4]
                if c_end is not None and any(
                    k["ct"] == 0x1050 and k["kids"] and k["kids"][0]["ct"] == 0x104F
                    and d[k["kids"][0]["pos"] + 9 + 15] == 3 and d[k["pos"] + 7 + k["size"] - 3] == 1
                    and abs(_epos(d, k["kids"][0]["pos"] + 9) - c_end) <= 2
                    for k in n["kids"]
                ):
                    probe.fail("clip at %s on '%s' has a fade-out at %d" % (pos, track, c_end),
                               "Pro Tools drops fade-out on looped clips during SaveSessionAs; remove fade-out or loop an un-faded clip")
                is_tk = (o["unit"] == "ticks") if "unit" in o else (d[e["pos"] + 9 + 14] == 0x40)
                E.append({"p": e["pos"] + 9 + 19, "ol": 1, "nb": b"\x01" + _blk_242b(is_tk), "enc": e["pos"]})
    if not E:
        mtr = [t["name"] for t in dec.tracks(d, tree, []) if t["type"] in ("Midi", "Instrument")]
        p58 = next((n for n in tree if n["ct"] == 0x1058), None)
        if p58 and track in mtr:
            r57s = [k for k in p58["kids"] if k["ct"] == 0x1057]
            mi = mtr.index(track)
            if mi < len(r57s):
                for e in probe.walk(r57s[mi]["kids"]):
                    if e["ct"] == 0x104F and _epos(d, e["pos"] + 9) == target_pos and not any(k["ct"] == 0x242B for k in e["kids"]):
                        is_tk = (o["unit"] == "ticks") if "unit" in o else (d[e["pos"] + 9 + 14] == 0x40)
                        E.append({"p": e["pos"] + 9 + 19, "ol": 1, "nb": b"\x01" + _blk_242b(is_tk), "enc": e["pos"]})
    if not E:
        probe.fail("no unlooped clip placement at %s on '%s'" % (pos, track), "check track and position with ptx_decode")
    out = _splice2(d, tree, E)
    tr2 = probe.parse(out, HEADER, len(out))
    if tr2[-1]["ct"] == 0x0002:
        out = out[:tr2[-1]["pos"]] + _blk(2, 0x0002, _dir_build(tr2))
    write_new(dst, scramble(out))
    print("wrote %s: looped %d channel placement(s) on '%s' at %s (mode=%d, %d|%d|%d, count=%d)" % (dst, len(E), track, pos, mode, bars, beats, ticks, cnt))


def cmd_setkeysig(src, dst, *items):
    """set Key Signature ruler events (0x271B > 0x2619 + 0x2433, and top-level duplicate 0x2433).
    Arguments: TICKS:KEY [...] where KEY is C, G, D, A, E, B, F#, C#, F, Bb, Eb, Ab, Db, Gb, Cb or Am..Abm.
    Example: python3 ptx_edit.py setkeysig in.ptx out.ptx 0:C 960000:Am 1920000:F#m"""
    if not items:
        probe.fail("need TICKS:KEY event(s)", "usage: setkeysig <in> <out> 0:C [960000:Am ...]")
    events = _parse_keysigs(items)
    if events[0][0] != 0 or [e[0] for e in events] != sorted(e[0] for e in events):
        probe.fail("key signature map must start at tick 0 and be in time order", "first event 0:KEY, then rising ticks")
    raw, d, tree = descramble_file(src)
    d = bytes(d)
    ks_blks = _keysig_blocks(events, _rnd(4))
    b1b = next((n for n in tree if n["ct"] == 0x271B), None)
    tops = []
    inserted = False
    for n in tree:
        if n["ct"] in (0x271B, 0x2433):
            if not inserted:
                tops.extend(ks_blks)
                inserted = True
            continue
        if not b1b and not inserted and n["ct"] in (0x271C, 0x1054):
            tops.extend(ks_blks)
            inserted = True
        tops.append(d[n["pos"]:n["pos"] + 7 + n["size"]])
    if not inserted:
        tops = tops[:-2] + ks_blks + tops[-2:]
    out = _rebuild_top(d, tree, tops)
    write_new(dst, scramble(out))
    print("wrote %s: %d key signature event(s)" % (dst, len(events)))


def cmd_addclipgroup(src, dst, track, name, start_s, end_s):
    """create a clip group over [START, END] on Audio track TRACK.
    Wraps existing clip placement(s) in [START, END] into 0x2428 > 0x1054 > 0x1052, creates 0x262C > 0x262B > 0x2628,
    updates 0x2424 > 0x2423 and 0x2426 > 0x2425, and replaces the track placements with a grouped entry (0x104F byte 18 = 1).
    Example: python3 ptx_edit.py addclipgroup in.ptx out.ptx Au_m_S MyGroup.grp s0 s1248000"""
    dec = _decoder()
    raw, d, tree = descramble_file(src)
    d = bytes(d)
    res = dec.decode(src)
    tinfo = next((t for t in res["tracks"] if t["name"] == track and t["type"] == "Audio"), None)
    if not tinfo:
        probe.fail("audio track '%s' not found" % track, "check track name with ptx_decode")
    stereo = bool(tinfo.get("stereo"))
    nch = 2 if stereo else 1
    rate = (res.get("format") or {}).get("sample_rate") or 48000
    tempo = (res.get("tempo_used") or [{"ticks": 0, "bpm": 120.0}])
    bpm = float(tempo[0]["bpm"])
    tps = (bpm / 60.0) * 960000.0 / float(rate)

    def _to_samples(txt):
        if txt.startswith("s"):
            return int(txt[1:])
        return int(round(_pos(dec, d, tree, txt) / tps))

    def _to_ticks(txt):
        if txt.startswith("s"):
            return int(round(int(txt[1:]) * tps))
        return _pos(dec, d, tree, txt)

    # Find active 0x1052 channel playlist(s) for track (via 0x261C aidx -> 0x1015 > 0x1014 -> 0x1052)
    p54 = next((n for n in tree if n["ct"] == 0x1054), None)
    p15 = next((n for n in tree if n["ct"] == 0x1015), None)
    p2c = next((n for n in tree if n["ct"] == 0x262C), None)
    if not p54 or not p15 or not p2c:
        probe.fail("session lacks 0x1054 / 0x1015 / 0x262C", "cannot build clip group")
    tidx_tr, ch_blk = _channel(dec, d, tree, track)
    b1b = next((x for x in ch_blk["kids"] if x["ct"] == 0x261B), None)
    aidx = struct.unpack_from("<I", d, b1b["pos"] + 7 + b1b["size"])[0]
    k14s = [k for k in p15["kids"] if k["ct"] == 0x1014]
    p0 = k14s[aidx]["pos"] + 9
    ln0 = struct.unpack_from("<I", d, p0)[0]
    nch_pl = struct.unpack_from("<I", d, p0 + 5 + ln0)[0]
    pl_idxs = [struct.unpack_from("<H", d, p0 + 9 + ln0 + 2 * c)[0] for c in range(nch_pl)]
    k52s = [k for k in p54["kids"] if k["ct"] == 0x1052]
    if len(pl_idxs) != nch or any(i >= len(k52s) for i in pl_idxs):
        probe.fail("channel playlist indices out of range for '%s'" % track, "check 0x1014")

    pl0 = k52s[pl_idxs[0]]
    pl0_tb_byte = d[probe.end_of(pl0) - 2] if pl0["size"] >= 4 else 1
    is_tick_track = (pl0_tb_byte == 2) or (any(k["ct"] == 0x1050 and d[k["kids"][0]["pos"] + 9 + 14] == 0x40 for k in pl0["kids"]))
    g_start = _to_ticks(start_s) if is_tick_track else _to_samples(start_s)
    g_end = _to_ticks(end_s) if is_tick_track else _to_samples(end_s)
    if g_end <= g_start:
        probe.fail("END (%d) must be greater than START (%d)" % (g_end, g_start), "use start < end")
    g_len = g_end - g_start

    # Gather & rewrite entries in each track channel playlist
    lst_2a = next((n for n in probe.walk(tree) if n["ct"] == 0x262A), None)
    wraps_29 = [k for k in lst_2a["kids"] if k["ct"] == 0x2629] if lst_2a else []
    member_52s = []
    track_edits = []
    for ci, pli in enumerate(pl_idxs):
        pl = k52s[pli]
        pnl = struct.unpack_from("<I", d, pl["pos"] + 9)[0]
        cnt_pos = pl["pos"] + 13 + pnl
        ents_1050 = [k for k in pl["kids"] if k["ct"] == 0x1050]
        kept, grouped = [], []
        for e50 in ents_1050:
            e4f = e50["kids"][0]
            eo_ = e4f["pos"] + 9
            eb = bytearray(d[eo_:e4f["pos"] + 7 + e4f["size"]])
            is_tk = eb[14] == 0x40
            raw_pos = int.from_bytes(eb[7:12], "little")
            ev_native = (raw_pos - OFF12 if raw_pos >= OFF12 else raw_pos) if is_tk else raw_pos
            tr50 = d[e4f["pos"] + 7 + e4f["size"]:e50["pos"] + 7 + e50["size"]]
            in_grp = False
            if eb[15] in (2, 3) and tr50 and tr50[0] == 0 and (len(eb) <= 18 or eb[18] == 0):
                sp_ = _clip_span_and_sync(dec, d, tree, wraps_29, eo_, tempo, rate)
                c_st, c_en = sp_[2], sp_[4]
                if c_st is not None and c_en is not None:
                    in_grp = (g_start - 2 <= c_st and c_en <= g_end + 2) if is_tk else (g_start <= c_st and c_en <= g_end)
                else:
                    in_grp = (g_start <= ev_native < g_end)
            elif eb[15] == 1:
                in_grp = (g_start <= ev_native < g_end)
            elif eb[15] == 3 and tr50 and tr50[0] == 1:
                in_grp = (g_start < ev_native <= g_end)
            if in_grp:
                rel_u = max(0, ev_native - g_start)
                new_val = OFF12 + rel_u
                eb[7:12] = new_val.to_bytes(5, "little")
                eb[14] = 0x40 if is_tick_track else 0x00
                grouped.append(_blk(3, 0x1050, _blk(10, 0x104F, bytes(eb)), tr50))
            else:
                kept.append(d[e50["pos"]:e50["pos"] + 7 + e50["size"]])
        if not grouped:
            probe.fail("no clip placements on '%s' channel %d in [%d, %d)" % (track, ci, g_start, g_end), "check positions with ptx_decode")
        tb_val = 2 if is_tick_track else 1
        member_52s.append(_blk(3, 0x1052, struct.pack("<I", 1) + b"?" + struct.pack("<I", len(grouped)) + b"".join(grouped) + struct.pack("<H", tb_val)))
        track_edits.append((pl, cnt_pos, kept, grouped))

    old_2428 = next((n for n in tree if n["ct"] == 0x2428), None)
    old_mpls = [d[k["pos"]:k["pos"] + 7 + k["size"]] for k in old_2428["kids"][0]["kids"] if k["ct"] == 0x1052] if (old_2428 and old_2428["kids"]) else []
    mpl_base = len(old_mpls)

    old_262b = [d[k["pos"]:k["pos"] + 7 + k["size"]] for k in p2c["kids"] if k["ct"] == 0x262B]
    grp_reg_base = len(old_262b)
    grp_id = (max([struct.unpack_from("<I", x, len(x) - 9)[0] for x in old_262b], default=-1) + 1) if old_262b else 0

    new_262bs = []
    for ci in range(nch):
        ch_sfx = (".L" if ci == 0 else ".R") if stereo else ""
        rnm = (name + ch_sfx).encode("utf-8")
        if is_tick_track:
            vals = [OFF12, g_len, g_start, g_start]
            w = [_minw(v) for v in vals]
            head = (struct.pack("<I", len(rnm)) + rnm + bytes([0, (w[0] << 4) | 1, w[1] << 4, (w[2] << 4) | w[3], 8])
                    + b"".join(v.to_bytes(k, "little") for v, k in zip(vals, w) if k)
                    + b"\xff" * 8 + b"\xfe\xff\x00\x00\x00\x00\xff\xff\x04\x00\x04\x00\x01\x00\x00\x00")
            post26 = ((OFF12 + g_start).to_bytes(7, "little") + b"\x40" + b"\xff" * 4
                      + struct.pack("<IIII", 0, mpl_base + ci, 0, 1) + struct.pack("<Q", OFF12) + struct.pack("<dQ", bpm, 960000)
                      + OFF12.to_bytes(7, "little") + b"\x40" + (OFF12 + g_len).to_bytes(7, "little") + b"\x40"
                      + (OFF12 + g_start + g_len).to_bytes(7, "little") + b"\x40" + b"\xff" * 4 + b"\x00" * 9)
            r_tail = b"\x00" * 17 + b"\xff" * 4 + b"\x00\x00" + _rnd(16)
            r28 = _blk(4, 0x2628, head + _blk(9, 0x2523, _blk(2, 0x2526, b"\x00" * 12) + post26) + r_tail)
        else:
            vals = [OFF12, g_len, 0, 0]
            w = [_minw(v) for v in vals]
            head = (struct.pack("<I", len(rnm)) + rnm + bytes([0, w[0] << 4, w[1] << 4, 0, 8])
                    + b"".join(v.to_bytes(k, "little") for v, k in zip(vals, w) if k)
                    + b"\xff" * 8 + b"\xfe\xff\x00\x00\x00\x00\xff\xff\x04\x00\x04\x00\x01\x00\x00\x00")
            post26 = (b"\x00" * 8 + b"\xff" * 4 + struct.pack("<IIII", 0, mpl_base + ci, 0, 0)
                      + struct.pack("<QQI", OFF12, OFF12 + g_len, g_len) + b"\x00" * 4 + b"\xff" * 4 + b"\x00" * 9)
            r_tail = b"\x00" * 17 + b"\xff" * 4 + b"\x00\x00" + _rnd(16)
            r28 = _blk(5, 0x2628, head + _blk(9, 0x2523, _blk(2, 0x2526, b"\x00" * 12) + post26) + r_tail)
        new_262bs.append(_blk(1, 0x262b, r28 + struct.pack("<I", grp_id) + struct.pack(">HHB", ci, ci, 0)))

    body_262c = struct.pack("<I", grp_reg_base + nch) + b"".join(old_262b + new_262bs) + b"\x00" * 4

    # 0x2424 > 0x2423 (group name registry) and 0x2426 > 0x2425 (source session path)
    old_2424 = next((n for n in tree if n["ct"] == 0x2424), None)
    old_23s = [d[k["pos"]:k["pos"] + 7 + k["size"]] for k in old_2424["kids"] if k["ct"] == 0x2423] if old_2424 else []
    gn_b = name.encode("utf-8")
    new_23 = _blk(4, 0x2423, struct.pack("<II", grp_id, len(gn_b)) + gn_b + b"\x00" * 5)
    old_2426 = next((n for n in tree if n["ct"] == 0x2426), None)
    old_25s = [d[k["pos"]:k["pos"] + 7 + k["size"]] for k in old_2426["kids"] if k["ct"] == 0x2425] if old_2426 else []
    vol_name = str(_cfg_val("format", "default_volume", "Macintosh HD"))
    parts = [p.encode("utf-8") for p in [vol_name] + [x for x in os.path.abspath(dst).split("/") if x]]
    new_25 = _blk(2, 0x2425, struct.pack("<I", 1) + b"\x00" * 5 + struct.pack("<I", len(parts)) + b"".join(struct.pack("<I", len(p)) + p for p in parts) + _rnd(4) + b"\x00" * 6)

    # Splice edits in-place so existing block start offsets (0x1052, 0x262C, 0x2428, 0x1054, 0x4828, 0x2424, 0x2426) stay valid in 0x0002
    E = []
    for ci, (pl, cnt_pos, kept, _) in enumerate(track_edits):
        e_val = (OFF12 + g_start) if is_tick_track else g_start
        grp_entry = _blk(3, 0x1050, _blk(10, 0x104f,
                    b"\x00\x00" + struct.pack("<H", grp_reg_base + ci) + b"\x00" * 3
                    + e_val.to_bytes(5, "little") + b"\x00\x00"
                    + bytes([0x40 if is_tick_track else 0x00, 3]) + b"\xfe\xff\x01\x00\x00\x00" + b"\xff" * 8 + b"\x00" * 5), b"\x00\x01\x01")
        all_ents = kept + [grp_entry]
        all_ents.sort(key=_entry_sort_key)
        end_ents = probe.end_of(pl["kids"][-1]) if pl["kids"] else (cnt_pos + 4)
        E.append({"p": cnt_pos, "ol": end_ents - cnt_pos, "nb": struct.pack("<I", len(all_ents)) + b"".join(all_ents), "enc": pl["pos"]})
    if old_262b:
        p2c_ins = p2c["kids"][-1]["pos"] + 7 + p2c["kids"][-1]["size"]
        E.append({"p": p2c["pos"] + 9, "ol": 4, "nb": struct.pack("<I", grp_reg_base + nch), "enc": None})
        E.append({"p": p2c_ins, "ol": 0, "nb": b"".join(new_262bs), "enc": p2c["pos"]})
    else:
        body_262c = struct.pack("<I", grp_reg_base + nch) + b"".join(new_262bs) + b"\x00" * 4
        E.append({"p": p2c["pos"] + 9, "ol": p2c["size"] - 2, "nb": body_262c, "enc": None})
    tail_blocks = []
    ins_at = tree[-2]["pos"] if len(tree) >= 2 and tree[-2]["ct"] == 0x0003 else tree[-1]["pos"]
    if old_2428 and old_2428["kids"]:
        old_1054 = old_2428["kids"][0]
        b4828 = next((k for k in old_1054["kids"] if k["ct"] == 0x4828), None)
        ins_mpl = b4828["pos"] if b4828 else probe.end_of(old_1054)
        E.append({"p": old_1054["pos"] + 9, "ol": 4, "nb": struct.pack("<I", mpl_base + nch), "enc": None})
        E.append({"p": ins_mpl, "ol": 0, "nb": b"".join(member_52s), "enc": old_1054["pos"]})
    elif old_2428:
        body_2428 = _blk(2, 0x1054, struct.pack("<I", mpl_base + nch) + b"".join(old_mpls + member_52s), _blk(2, 0x4828, b"\x00" * 4))
        E.append({"p": old_2428["pos"] + 9, "ol": old_2428["size"] - 2, "nb": body_2428, "enc": None})
    else:
        body_2428 = _blk(2, 0x1054, struct.pack("<I", mpl_base + nch) + b"".join(old_mpls + member_52s), _blk(2, 0x4828, b"\x00" * 4))
        tail_blocks.append(_blk(1, 0x2428, body_2428))
    if old_2424:
        E.append({"p": old_2424["pos"] + 9, "ol": 4, "nb": struct.pack("<I", len(old_23s) + 1), "enc": None})
        E.append({"p": probe.end_of(old_2424), "ol": 0, "nb": new_23, "enc": old_2424["pos"]})
    else:
        tail_blocks.append(_blk(1, 0x2424, struct.pack("<I", 1) + new_23))
    if old_2426:
        E.append({"p": old_2426["pos"] + 9, "ol": 4, "nb": struct.pack("<I", len(old_25s) + 1), "enc": None})
        E.append({"p": probe.end_of(old_2426), "ol": 0, "nb": new_25, "enc": old_2426["pos"]})
    else:
        tail_blocks.append(_blk(1, 0x2426, struct.pack("<I", 1) + new_25))
    if tail_blocks:
        E.append({"p": ins_at, "ol": 0, "nb": b"".join(tail_blocks), "enc": None})
    out = _splice2(d, tree, E)
    tr2 = probe.parse(out, HEADER, len(out))
    if tr2[-1]["ct"] == 0x0002:
        out = out[:tr2[-1]["pos"]] + _blk(2, 0x0002, _dir_build(tr2))
    write_new(dst, scramble(out))
    print("wrote %s: clip group '%s' (%d channel(s), %s [%d, %d)) on '%s'" % (dst, name, nch, "ticks" if is_tick_track else "samples", g_start, g_end, track))


def _base_session(rate=48000, bits=24, creator_id=None, xor_value=0x5c, io=True, tempo=None, meter=None, keysig=None):
    """the complete empty session from fields (no Pro Tools bytes): header, pointer block (u32 position of the directory), 0x2519,
    0x1028, empty containers 0x0F3D volumes, 0x1004 file list (two empty 0x103a lists), 0x262A regions, 0x2000 MIDI data, 0x2634 MIDI clips,
    0x1054 playlists (+ 0x4828), 0x1015 audio links (+ 0x4829), 0x1058 routes, 0x210C folders, 0x2107 kinds (count at data 9), 0x2624 tracks,
    0x0003 version, 0x0002 directory (9.51). Returns descrambled bytes."""
    import uuid
    cid = creator_id or _rnd(16)[:8]
    u0 = struct.pack("<I", 0)
    blocks = [_block_2519_empty(), _block_1028(rate, bits), _blk(1, 0x0f3d, u0), _blk(3, 0x1004, u0, _blk(1, 0x103a, u0), u0, _blk(1, 0x103a, u0)),
              _blk(1, 0x2637, u0), _blk(1, 0x262c, u0 + u0), _blk(1, 0x2632, u0), _blk(1, 0x262a, u0), _blk(1, 0x2630, u0), _blk(1, 0x262e, u0)] + ([_block_2603(cid[:4] + struct.pack("<I", 0x100))] if io else []) + [_blk(1, 0x2000, u0), _blk(1, 0x2634, u0)] + \
             (_map_blocks(tempo or [(0, 120.0)], meter or [], rate, cid[:4]) if (tempo or meter) else []) + \
             (_keysig_blocks(keysig, cid[:4]) if keysig else []) + [_blk(2, 0x1054, u0, _blk(2, 0x4828, u0)), _blk(2, 0x1015, u0, _blk(2, 0x4829, u0)),
              _blk(1, 0x1058, u0), _blk(1, 0x210c, u0), _blk(5, 0x2107, b"\x00" * 8 + b"\x01" + u0), _blk(1, 0x2624, u0), _block_0003(cid)]
    body = b"".join(blocks)
    head = _HEADER_MAGIC + bytes([5, xor_value])
    dpos = len(head) + 11 + len(body)
    d = head + b"\x5a\x01\x00" + struct.pack("<I", 4) + struct.pack("<I", dpos) + body + _blk(2, 0x0002, b"")
    tree = probe.parse(d, HEADER, len(d))
    dirb = _dir_build(tree)
    return d[:dpos] + _blk(2, 0x0002, dirb)


def cmd_newbase(dst, *opts):
    """write an EMPTY session (no tracks) built from fields only (clean room). Options: rate=48000, bits=24 (16 | 24 |
    32 = float), io=1 (default: one stereo output path 'Out 1-2'; io=0: none - Pro Tools then refuses to bounce, no active output, b40).
    Pro Tools adds its view and window blocks and its I/O database on the first save. Tracks: addtrack4; notes: setnotes; audio: addclip.
    Example: python3 ptx_edit.py newbase empty.ptx rate=48000 bits=24 ; python3 ptx_edit.py addtrack4 empty.ptx a.ptx kind=audio name=Vox"""
    o = dict(x.split("=", 1) for x in opts if "=" in x)
    if set(o) - {"rate", "bits", "io"} or len(o) != len(opts):
        probe.fail("unknown option in %s" % list(opts), "use rate=<Hz> bits=16|24|32 io=1")
    try:
        rate, bits = int(o.get("rate", 48000)), int(o.get("bits", 24))
    except ValueError:
        probe.fail("rate / bits must be numbers", "e.g. rate=48000 bits=24")
    d = _base_session(rate, bits, io=o.get("io", "1") != "0")                   # io: one output path 'Out 1-2' (b39: tracks bounce; io=0 -> no output, b40)
    write_new(dst, scramble(d))
    print("wrote %s: empty session from fields (%d bytes, %d Hz, %d bit)" % (dst, len(d), rate, bits))


def _playlist_blocks(d, tree, track):
    """All audio channel playlists 0x1052 named TRACK under top-level 0x1054 (mono: 1, stereo: 2)."""
    top = next((n for n in tree if n["ct"] == 0x1054), None)
    if not top:
        probe.fail("session has no playlist container 0x1054", "cannot find track '%s'" % track)
    hits, names = [], []
    for pl in top["kids"]:
        if pl["ct"] != 0x1052:
            continue
        p = pl["pos"] + 9
        n = struct.unpack_from("<I", d, p)[0]
        if n < 256:
            nm = d[p + 4:p + 4 + n].decode("utf-8", "replace")
            names.append(nm)
            if nm == track:
                hits.append(pl)
    if not hits:
        probe.fail("audio playlist '%s' not found" % track, "playlists: %s" % names)
    return hits


def _entry_sort_key(raw_1050):
    """Chronological sort key (pos, rank) for a raw 0x1050 > 0x104F playlist entry block."""
    o = 18
    return (_epos(raw_1050, o), 0 if raw_1050[o + 15] == 1 else 1)


def _splice_playlist_entries(d, pl, entries_raw):
    """Build splice edit replacing all 0x1050 children of 0x1052 PL with chronologically sorted ENTRIES_RAW."""
    ordered = sorted(entries_raw, key=_entry_sort_key)
    pn = struct.unpack_from("<I", d, pl["pos"] + 9)[0]
    cnt_pos = pl["pos"] + 13 + pn
    end_ents = pl["kids"][-1]["pos"] + 7 + pl["kids"][-1]["size"] if pl["kids"] else cnt_pos + 4
    return {
        "p": cnt_pos,
        "ol": end_ents - cnt_pos,
        "nb": struct.pack("<I", len(ordered)) + b"".join(ordered),
        "enc": pl["pos"],
    }


def _clip_span_and_sync(dec, d, tree, wraps, o, tempo, srate):
    """Return (ln_samples, wave_tps, clip_start, anchor_pos, clip_end, sync_off) for a 0x104F clip entry at own offset O."""
    ridx = struct.unpack_from("<H", d, o + 2)[0]
    t_pos = _epos(d, o)
    if ridx >= len(wraps):
        return None, None, t_pos, t_pos, None, 0
    reg = next((k for k in wraps[ridx]["kids"] if k["ct"] == 0x2628), None)
    if not reg:
        return None, None, t_pos, t_pos, None, 0
    rp = reg["pos"] + 9
    n = struct.unpack_from("<I", d, rp)[0]
    q = rp + 4 + n
    b1, b2, b3 = d[q + 1], d[q + 2], d[q + 3]
    sync_w = b2 & 15
    ws = [b1 >> 4, b2 >> 4, b3 >> 4, b3 & 15]
    k = q + 5
    vals = [int.from_bytes(d[k:k + ws[0]], "little") if ws[0] else 0]
    k += ws[0]
    sync_off = int.from_bytes(d[k:k + sync_w], "little") if sync_w else 0
    k += sync_w
    for x in ws[1:]:
        vals.append(int.from_bytes(d[k:k + x], "little") if x else 0)
        k += x
    wave = next((c for c in reg["kids"] if c["ct"] == 0x2636), None)
    default_tps = 960000.0 * float((tempo or [{"bpm": 120.0}])[0]["bpm"]) / 60.0 / float(srate or 48000)
    if wave:
        wv = d[wave["pos"] + 9:wave["pos"] + 7 + wave["size"]]
        _, st_t, ln, en_t = struct.unpack_from("<QQIQ", wv, 16 + 8 + 10)
        wave_tps = (en_t - st_t) / ln if ln else default_tps
    else:
        ln, wave_tps = vals[1], default_tps
    is_tick = d[o + 14] == 0x40
    sr_f = float(srate or 48000)
    if not ln:
        return ln, wave_tps, t_pos, t_pos, None, sync_off
    if is_tick:
        if sync_off:
            anchor_sec = dec.ticks_to_seconds(t_pos, tempo)
            clip_start = int(round(dec.seconds_to_ticks(max(0.0, anchor_sec - sync_off / sr_f), tempo)))
        else:
            clip_start = t_pos
        end_pos = int(round(dec.seconds_to_ticks(dec.ticks_to_seconds(clip_start, tempo) + ln / sr_f, tempo)))
        return ln, wave_tps, clip_start, t_pos, end_pos, sync_off
    clip_start = t_pos - sync_off
    return ln, wave_tps, clip_start, t_pos, clip_start + ln, sync_off


def _find_clip_at(dec, d, tree, wraps, pl, target_pos, tempo, srate):
    """Find the ungrouped 0x1050 clip entry on PL matching TARGET_POS (by clip_start, fallback to synced anchor)."""
    fallback = None
    for e in pl["kids"]:
        if e["ct"] == 0x1050 and e["kids"] and e["kids"][0]["ct"] == 0x104F:
            e4f = e["kids"][0]
            o = e4f["pos"] + 9
            if d[o + 15] in (2, 3) and d[e["pos"] + 7 + e["size"] - 3] == 0 and (e4f["size"] < 21 or d[o + 18] == 0):
                sp = _clip_span_and_sync(dec, d, tree, wraps, o, tempo, srate)
                tol = 2 if d[o + 14] == 0x40 else 0
                if abs(sp[2] - target_pos) <= tol:
                    return e, sp
                if sp[5] and abs(sp[3] - target_pos) <= tol and fallback is None:
                    fallback = (e, sp)
    return fallback if fallback is not None else (None, None)


def _playlist_clip_end(dec, d, tree, wraps, o, ridx, t_pos, tempo, srate):
    """Return (clip_len_samples, wave_tps, end_pos_in_playlist_units) for a 0x104F clip entry at own offset O."""
    ln, wave_tps, _cs, _ca, end_pos, _so = _clip_span_and_sync(dec, d, tree, wraps, o, tempo, srate)
    return ln, wave_tps, end_pos


def _rebuild_region_inplace(d, reg, new_vals, new_off, new_len, tps, new_sync=None):
    """Rebuild an unshared 0x2628 region block with updated [start_off, length, origin, sync], optional sync_offset, and 0x2636 span."""
    src_r = bytes(d[reg["pos"]:reg["pos"] + 7 + reg["size"]])
    rp, re_ = reg["pos"] + 9, reg["pos"] + 7 + reg["size"]
    n = struct.unpack_from("<I", d, rp)[0]
    nb_ = d[rp + 4:rp + 4 + n]
    q = rp + 4 + n
    flag, b1, b2, b3, ex = d[q:q + 5]
    sync_w = b2 & 15
    old_w = [b1 >> 4, b2 >> 4, b3 >> 4, b3 & 15]
    k = q + 5
    old_vals = [int.from_bytes(d[k:k + old_w[0]], "little") if old_w[0] else 0]
    k += old_w[0]
    sync_raw = d[k:k + sync_w]
    old_sync = int.from_bytes(sync_raw, "little") if sync_w else 0
    k += sync_w
    for x in old_w[1:]:
        old_vals.append(int.from_bytes(d[k:k + x], "little") if x else 0)
        k += x
    wave = next((c for c in reg["kids"] if c["ct"] == 0x2636), None)
    mid_ = d[k:wave["pos"]] if wave else b""
    tail = d[wave["pos"] + 7 + wave["size"]:re_] if wave else d[k:re_]

    def _build(v, po, pl_, s_raw, s_w, widths=None, keep_wave=False):
        wd = widths if widths is not None else [_minw(x) for x in v]
        val_bytes = [x.to_bytes(c_, "little") if c_ else b"" for x, c_ in zip(v, wd)]
        body = (struct.pack("<I", len(nb_)) + nb_
                + bytes([flag, (b1 & 15) | (wd[0] << 4), s_w | (wd[1] << 4), (wd[2] << 4) | wd[3], ex])
                + val_bytes[0] + s_raw + b"".join(val_bytes[1:]))
        wb = b""
        if wave:
            lane = bytearray(d[wave["pos"]:wave["pos"] + 7 + wave["size"]])
            if not keep_wave:
                struct.pack_into("<QQIQ", lane, 9 + 16 + 8 + 10, po, 10 ** 12 + int(round(po * tps)), pl_, 10 ** 12 + int(round((po + pl_) * tps)))
            wb = bytes(lane)
        data = body + mid_ + wb + tail
        return bytes([0x5A, src_r[1], src_r[2]]) + struct.pack("<I", 2 + len(data)) + src_r[7:9] + data

    if _build(old_vals, old_vals[0], old_vals[1], sync_raw, sync_w, old_w, keep_wave=True) != src_r:
        probe.fail("region '%s' layout not round-trip reproducible" % nb_.decode("utf-8", "replace"), "cannot safely rewrite region in-place")
    if new_sync is None:
        out_sw, out_sraw = sync_w, sync_raw
    else:
        out_sw = _minw(new_sync) if new_sync > 0 else 0
        out_sraw = new_sync.to_bytes(out_sw, "little") if out_sw else b""
    keep_w = new_vals is None
    vals_out = old_vals if keep_w else new_vals
    return _build(vals_out, old_vals[0] if keep_w else new_off, old_vals[1] if keep_w else new_len, out_sraw, out_sw, widths=(old_w if keep_w else None), keep_wave=keep_w)


def _region_use_counts(d, tree):
    """Count non-fade ungrouped audio clip placements per region index across 0x1054 and 0x2428 member playlists."""
    counts = {}
    pls_all = []
    for n_ in tree:
        if n_["ct"] == 0x1054:
            pls_all.extend(k for k in n_["kids"] if k["ct"] == 0x1052)
        elif n_["ct"] == 0x2428 and n_["kids"] and n_["kids"][0]["ct"] == 0x1054:
            pls_all.extend(k for k in n_["kids"][0]["kids"] if k["ct"] == 0x1052)
    for pl_ in pls_all:
        for e, o, kd, ri, _tk in _entries(d, pl_):
            if kd in (2, 3) and d[e["pos"] + 7 + e["size"] - 3] == 0 and (e["kids"][0]["size"] < 21 or d[o + 18] == 0):
                counts[ri] = counts.get(ri, 0) + 1
    return counts


def cmd_setsyncpoint(src, dst, track, pos, offset_samples):
    """set (or 0 = clear) sync point OFFSET_SAMPLES on clip starting at POS on TRACK, updating 0x2628 and 0x104F anchor."""
    new_sync = int(offset_samples)
    if new_sync < 0:
        probe.fail("sync offset must be >= 0 (got %d)" % new_sync, "use offset_samples >= 0 (0 removes the sync point)")
    dec = _decoder()
    raw, d, tree = descramble_file(src)
    d = bytes(d)
    pls = _playlist_blocks(d, tree, track)
    t = _pos(dec, d, tree, pos)
    lst = next((n for n in probe.walk(tree) if n["ct"] == 0x262A), None)
    wraps = [k for k in lst["kids"] if k["ct"] == 0x2629] if lst else []
    res = dec.decode(src)
    tempo = res.get("tempo_used") or [{"ticks": 0, "bpm": 120.0}]
    srate = (res.get("format") or {}).get("sample_rate") or 48000
    ridx_uses = _region_use_counts(d, tree)
    edits, hit_count = [], 0
    for pl in pls:
        clip, span = _find_clip_at(dec, d, tree, wraps, pl, t, tempo, srate)
        if not clip or not span:
            continue
        ln, wave_tps, c_start, _c_anchor, _c_end, _old_sync = span
        if not ln or new_sync > ln:
            probe.fail("sync offset %d exceeds clip length %s" % (new_sync, ln), "keep 0 <= offset_samples <= clip length")
        o = clip["kids"][0]["pos"] + 9
        ridx = struct.unpack_from("<H", d, o + 2)[0]
        if ridx_uses.get(ridx, 0) != 1:
            probe.fail("region %d is shared (%d placements)" % (ridx, ridx_uses.get(ridx, 0)), "setsyncpoint requires an unshared region")
        reg = next(k for k in wraps[ridx]["kids"] if k["ct"] == 0x2628)
        new_reg_b = _rebuild_region_inplace(d, reg, None, 0, ln, wave_tps, new_sync=new_sync)
        edits.append({"p": reg["pos"], "ol": 7 + reg["size"], "nb": new_reg_b, "enc": wraps[ridx]["pos"]})
        is_tick = d[o + 14] == 0x40
        if is_tick:
            new_anchor = int(round(dec.seconds_to_ticks(dec.ticks_to_seconds(c_start, tempo) + new_sync / float(srate), tempo))) if new_sync else c_start
        else:
            new_anchor = c_start + new_sync
        new_ents = []
        for e in [k for k in pl["kids"] if k["ct"] == 0x1050 and k["kids"] and k["kids"][0]["ct"] == 0x104F]:
            eb = bytearray(d[e["pos"]:e["pos"] + 7 + e["size"]])
            if e is clip:
                eo = e["kids"][0]["pos"] - e["pos"] + 9
                eb[eo + 7:eo + 12] = _epos_bytes(eb, eo, new_anchor)
            new_ents.append(bytes(eb))
        edits.append(_splice_playlist_entries(d, pl, new_ents))
        hit_count += 1
    if not hit_count:
        probe.fail("%s: no clip starts at %d" % (track, t), "check positions with ptx_decode audio_placements")
    out = _splice2(d, tree, edits)
    write_new(dst, scramble(out))
    print("wrote %s: set sync point %d sample(s) on %d channel clip(s) at %d on '%s'" % (dst, new_sync, hit_count, t, track))


def cmd_moveclip(src, dst, track, from_pos, to_pos):
    """move clip at FROM_POS (+ its fade-in, sync anchor, and fade-out) to TO_POS and sort 0x1050 entries chronologically."""
    dec = _decoder()
    raw, d, tree = descramble_file(src)
    d = bytes(d)
    pls = _playlist_blocks(d, tree, track)
    tf, tt = _pos(dec, d, tree, from_pos), _pos(dec, d, tree, to_pos)
    if tf == tt:
        probe.fail("source and target positions are identical (%d)" % tf, "choose a different target position")
    lst = next((n for n in probe.walk(tree) if n["ct"] == 0x262A), None)
    wraps = [k for k in lst["kids"] if k["ct"] == 0x2629] if lst else []
    res = dec.decode(src)
    tempo = res.get("tempo_used") or [{"ticks": 0, "bpm": 120.0}]
    srate = (res.get("format") or {}).get("sample_rate") or 48000
    sr_f = float(srate)
    edits, moved_total = [], 0
    for pl in pls:
        ents = [k for k in pl["kids"] if k["ct"] == 0x1050 and k["kids"] and k["kids"][0]["ct"] == 0x104F]
        clip_e, span = _find_clip_at(dec, d, tree, wraps, pl, tf, tempo, srate)
        if not clip_e or not span:
            probe.fail("%s: no clip starts at %d" % (track, tf), "check positions with ptx_decode audio_placements")
        ln_, _wtps, c_start, c_anchor, c_end, sync_off = span
        tol = 2 if d[clip_e["kids"][0]["pos"] + 9 + 14] == 0x40 else 0
        new_ents, moved_here = [], 0
        for e in ents:
            eb = bytearray(d[e["pos"]:e["pos"] + 7 + e["size"]])
            eo = e["kids"][0]["pos"] - e["pos"] + 9
            ev = _epos(eb, eo)
            is_tk = eb[eo + 14] == 0x40
            is_clip = e is clip_e
            is_fade_in = (eb[eo + 15] == 1 and abs(ev - c_start) <= tol)
            is_fade_out = (eb[eo + 15] == 3 and eb[-3] == 1 and c_end is not None and abs(ev - c_end) <= 2)
            if is_clip:
                nv = (int(round(dec.seconds_to_ticks(dec.ticks_to_seconds(tt, tempo) + sync_off / sr_f, tempo))) if (is_tk and sync_off) else (tt + sync_off if not is_tk else tt))
            elif is_fade_in:
                nv = tt
            elif is_fade_out:
                nv = (int(round(dec.seconds_to_ticks(dec.ticks_to_seconds(tt, tempo) + ln_ / sr_f, tempo))) if is_tk else (tt + ln_))
            else:
                nv = None
            if nv is not None:
                if nv < 0:
                    probe.fail("target position moves entry below 0", "use a later position")
                eb[eo + 7:eo + 12] = _epos_bytes(eb, eo, nv)
                moved_here += 1
            new_ents.append(bytes(eb))
        moved_total += moved_here
        edits.append(_splice_playlist_entries(d, pl, new_ents))
    out = _splice2(d, tree, edits)
    write_new(dst, scramble(out))
    print("wrote %s: moved %d entry/entries on '%s' (%d -> %d)" % (dst, moved_total, track, tf, tt))


def cmd_deleteclip(src, dst, track, pos):
    """remove clip starting at POS (+ its fade-in, sync anchor, and fade-out) from TRACK playlist(s), keeping regions in clip list."""
    dec = _decoder()
    raw, d, tree = descramble_file(src)
    d = bytes(d)
    pls = _playlist_blocks(d, tree, track)
    t = _pos(dec, d, tree, pos)
    lst = next((n for n in probe.walk(tree) if n["ct"] == 0x262A), None)
    wraps = [k for k in lst["kids"] if k["ct"] == 0x2629] if lst else []
    res = dec.decode(src)
    tempo = res.get("tempo_used") or [{"ticks": 0, "bpm": 120.0}]
    srate = (res.get("format") or {}).get("sample_rate") or 48000
    edits, deleted_total, any_left = [], 0, False
    for pl in pls:
        ents = [k for k in pl["kids"] if k["ct"] == 0x1050 and k["kids"] and k["kids"][0]["ct"] == 0x104F]
        clip_e, span = _find_clip_at(dec, d, tree, wraps, pl, t, tempo, srate)
        if not clip_e or not span:
            probe.fail("%s: no clip starts at %d" % (track, t), "check positions with ptx_decode audio_placements")
        _, _, c_start, _c_anchor, c_end, _ = span
        tol = 2 if d[clip_e["kids"][0]["pos"] + 9 + 14] == 0x40 else 0
        kept, rem_here = [], 0
        for e in ents:
            o = e["kids"][0]["pos"] + 9
            ev = _epos(d, o)
            is_fade_in = (d[o + 15] == 1 and abs(ev - c_start) <= tol)
            is_fade_out = (d[o + 15] == 3 and d[e["pos"] + 7 + e["size"] - 3] == 1 and c_end is not None and abs(ev - c_end) <= 2)
            if e is clip_e or is_fade_in or is_fade_out:
                rem_here += 1
            else:
                kept.append(d[e["pos"]:e["pos"] + 7 + e["size"]])
        deleted_total += rem_here
        any_left = any_left or bool(kept)
        edits.append(_splice_playlist_entries(d, pl, kept))
    if not any_left:
        tn_ = struct.pack("<I", len(track.encode("utf-8"))) + track.encode("utf-8")
        for x_ in _paths(tree).get((0x2519, 0x251a), []):
            b_ = d[x_["pos"]:x_["pos"] + 7 + x_["size"]]
            if b_[11:11 + len(tn_)] == tn_ and b_[-5] == 1:
                edits.append({"p": x_["pos"] + len(b_) - 5, "ol": 1, "nb": b"\x00", "enc": None})
    out = _splice2(d, tree, edits)
    write_new(dst, scramble(out))
    print("wrote %s: deleted %d entry/entries at %d on '%s'" % (dst, deleted_total, t, track))


def cmd_trimclip(src, dst, track, pos, new_start_s, new_end_s):
    """trim an unshared fade-free clip at POS in-place to [NEW_START, NEW_END) preserving region IDs and updating sync_offset."""
    dec = _decoder()
    raw, d, tree = descramble_file(src)
    d = bytes(d)
    pls = _playlist_blocks(d, tree, track)
    t_old = _pos(dec, d, tree, pos)
    t_new0, t_new1 = _pos(dec, d, tree, new_start_s), _pos(dec, d, tree, new_end_s)
    if t_new1 <= t_new0 or t_new0 < t_old:
        probe.fail("invalid trim range [%d, %d) for clip at %d" % (t_new0, t_new1, t_old), "require start >= clip_start and end > start")
    lst = next((n for n in probe.walk(tree) if n["ct"] == 0x262A), None)
    wraps = [k for k in lst["kids"] if k["ct"] == 0x2629] if lst else []
    res = dec.decode(src)
    tempo = res.get("tempo_used") or [{"ticks": 0, "bpm": 120.0}]
    srate = (res.get("format") or {}).get("sample_rate") or 48000
    sr_f = float(srate)
    ridx_uses = _region_use_counts(d, tree)
    edits = []
    for pl in pls:
        ents = [k for k in pl["kids"] if k["ct"] == 0x1050 and k["kids"] and k["kids"][0]["ct"] == 0x104F]
        e, span = _find_clip_at(dec, d, tree, wraps, pl, t_old, tempo, srate)
        if not e or not span:
            probe.fail("%s: no clip starts at %d" % (track, t_old), "ptx_decode audio_placements")
        o = e["kids"][0]["pos"] + 9
        ridx = struct.unpack_from("<H", d, o + 2)[0]
        if ridx_uses.get(ridx, 0) != 1:
            probe.fail("region %d is shared (%d placements)" % (ridx, ridx_uses.get(ridx, 0)), "in-place trim requires an unshared region")
        ln, wave_tps, c_start, _c_anchor, c_end, sync_off = span
        if not ln or c_end is None or t_new1 > c_end + (2 if d[o + 14] == 0x40 else 0):
            probe.fail("trim end %d exceeds clip end %s" % (t_new1, c_end), "keep [start, end) inside clip bounds")
        tol = 2 if d[o + 14] == 0x40 else 0
        has_fade = any(
            (d[x["kids"][0]["pos"] + 9 + 15] == 1 and abs(_epos(d, x["kids"][0]["pos"] + 9) - c_start) <= tol)
            or (d[x["kids"][0]["pos"] + 9 + 15] == 3 and d[x["pos"] + 7 + x["size"] - 3] == 1 and abs(_epos(d, x["kids"][0]["pos"] + 9) - c_end) <= 2)
            for x in ents
        )
        if has_fade:
            probe.fail("clip at %d has fades" % t_old, "in-place trim requires a fade-free clip")
        is_tk = d[o + 14] == 0x40
        step = wave_tps if is_tk else 1.0
        d_left = int(round((t_new0 - c_start) / step))
        new_len = int(round((t_new1 - t_new0) / step))
        if new_len <= 0 or d_left < 0 or d_left + new_len > ln:
            probe.fail("computed sample span [%d, +%d) exceeds region length %d" % (d_left, new_len, ln), "adjust trim bounds")
        new_sync = min(max(0, sync_off - d_left), new_len) if sync_off else 0
        reg = next(k for k in wraps[ridx]["kids"] if k["ct"] == 0x2628)
        rp = reg["pos"] + 9
        qn = struct.unpack_from("<I", d, rp)[0]
        q = rp + 4 + qn
        b1, b2, b3 = d[q + 1], d[q + 2], d[q + 3]
        sync_w = b2 & 15
        ws_old = [b1 >> 4, b2 >> 4, b3 >> 4, b3 & 15]
        vals, kp = [], q + 5
        vals.append(int.from_bytes(d[kp:kp + ws_old[0]], "little") if ws_old[0] else 0)
        kp += ws_old[0] + sync_w
        for xw in ws_old[1:]:
            vals.append(int.from_bytes(d[kp:kp + xw], "little") if xw else 0)
            kp += xw
        new_off = vals[0] + d_left
        ts_origin = vals[2] if vals[0] == 0 else vals[3] - vals[0]
        new_vals = [0, new_len, ts_origin, 0] if new_off == 0 else [new_off, new_len, new_off, ts_origin + new_off]
        new_reg_b = _rebuild_region_inplace(d, reg, new_vals, new_off, new_len, wave_tps, new_sync=new_sync)
        edits.append({"p": reg["pos"], "ol": 7 + reg["size"], "nb": new_reg_b, "enc": wraps[ridx]["pos"]})
        if is_tk:
            new_anchor = int(round(dec.seconds_to_ticks(dec.ticks_to_seconds(t_new0, tempo) + new_sync / sr_f, tempo))) if new_sync else t_new0
        else:
            new_anchor = t_new0 + new_sync
        new_ents = []
        for x in ents:
            xb = bytearray(d[x["pos"]:x["pos"] + 7 + x["size"]])
            if x is e:
                xo = x["kids"][0]["pos"] - x["pos"] + 9
                xb[xo + 7:xo + 12] = _epos_bytes(xb, xo, new_anchor)
            new_ents.append(bytes(xb))
        edits.append(_splice_playlist_entries(d, pl, new_ents))
    out = _splice2(d, tree, edits)
    write_new(dst, scramble(out))
    print("wrote %s: trimmed '%s' clip %d -> [%d, %d)" % (dst, track, t_old, t_new0, t_new1))


def cmd_delmarker(src, dst, ident):
    """remove memory location(s) matching ID|NAME|'--all' from 0x2030 preserving the 8-byte trailer."""
    raw, d, tree = descramble_file(src)
    d = bytes(d)
    c2030 = next((n for n in tree if n["ct"] == 0x2030), None)
    if not c2030:
        probe.fail("session has no memory locations (0x2030)", "nothing to remove")
    mks = [k for k in c2030["kids"] if k["ct"] == 0x2077]
    if not mks:
        probe.fail("0x2030 already has 0 markers", "nothing to remove")
    by_num = None
    if ident != "--all" and ident.lstrip("#").isdigit():
        by_num = int(ident.lstrip("#"))
    victims, kept_kinds = [], []
    for k in mks:
        p = k["pos"] + 9
        num = struct.unpack_from("<H", d, p)[0]
        kd = d[p + 3]
        nm_len = struct.unpack_from("<I", d, p + 6)[0]
        nm = d[p + 10:p + 10 + nm_len].decode("utf-8", "replace") if p + 10 + nm_len <= k["pos"] + 7 + k["size"] else ""
        if ident == "--all" or (by_num is not None and num == by_num) or nm == ident:
            victims.append(k)
        else:
            kept_kinds.append(kd)
    if not victims:
        probe.fail("marker '%s' not found in 0x2030" % ident, "give marker number (e.g. 1) or exact marker name")
    edits = [{"p": c2030["pos"] + 9, "ol": 4, "nb": struct.pack("<I", len(mks) - len(victims)), "enc": None}]
    for v in victims:
        edits.append({"p": v["pos"], "ol": 7 + v["size"], "nb": b"", "enc": c2030["pos"]})
    out = _splice2(d, tree, edits)
    if not any(kd == 1 for kd in kept_kinds):
        tr_out = probe.parse(out, HEADER, len(out))
        b1b = next((n for n in probe.walk(tr_out) if n["ct"] == 0x251B), None)
        if b1b and b1b["kids"] and b1b["kids"][0]["ct"] == 0x251C and b1b["kids"][0]["size"] >= 9:
            ba = bytearray(out)
            ba[b1b["kids"][0]["pos"] + 9 + 6] = 0
            out = bytes(ba)
    write_new(dst, scramble(out))
    print("wrote %s: removed %d marker(s) from 0x2030 (%d left)" % (dst, len(victims), len(mks) - len(victims)))


def cmd_anonnames(src, dst):
    """fill anonymous (nlen == 0) 0x1052 playlist names using 0x261C -> 0x1014 -> 0x1052 and track names."""
    dec = _decoder()
    raw, d, tree = descramble_file(src)
    d = bytes(d)
    p54 = next((n for n in tree if n["ct"] == 0x1054), None)
    p15 = next((n for n in tree if n["ct"] == 0x1015), None)
    p24 = next((n for n in tree if n["ct"] == 0x2624), None)
    if not p54 or not p15 or not p24:
        probe.fail("session missing 0x1054 / 0x1015 / 0x2624", "cannot resolve anonymous playlists")
    trks = dec.tracks(d, tree, [])
    k14s = [k for k in p15["kids"] if k["ct"] == 0x1014]
    k52s = [k for k in p54["kids"] if k["ct"] == 0x1052]
    idx_to_name = {}
    for ch_i, ch in enumerate(p24["kids"]):
        if ch["ct"] != 0x261C:
            continue
        b1b = next((x for x in ch["kids"] if x["ct"] == 0x261B), None)
        if not b1b or b1b["pos"] + 7 + b1b["size"] + 4 > len(d):
            continue
        aidx = struct.unpack_from("<I", d, b1b["pos"] + 7 + b1b["size"])[0]
        if aidx >= len(k14s):
            continue
        p0 = k14s[aidx]["pos"] + 9
        ln0 = struct.unpack_from("<I", d, p0)[0]
        if ln0 > 256 or p0 + 9 + ln0 > k14s[aidx]["pos"] + 7 + k14s[aidx]["size"]:
            continue
        n14 = d[p0 + 4:p0 + 4 + ln0].decode("utf-8", "replace")
        tn = trks[ch_i]["name"] if ch_i < len(trks) and trks[ch_i]["name"] else n14
        nch_pl = struct.unpack_from("<I", d, p0 + 5 + ln0)[0]
        if tn and p0 + 9 + ln0 + 2 * nch_pl <= k14s[aidx]["pos"] + 7 + k14s[aidx]["size"]:
            for c in range(nch_pl):
                pli = struct.unpack_from("<H", d, p0 + 9 + ln0 + 2 * c)[0]
                if pli < len(k52s):
                    idx_to_name.setdefault(pli, tn)
    edits = []
    for pli, pl in enumerate(k52s):
        p = pl["pos"] + 9
        if struct.unpack_from("<I", d, p)[0] == 0 and pli in idx_to_name:
            nb = idx_to_name[pli].encode("utf-8")
            edits.append({"p": p, "ol": 4, "nb": struct.pack("<I", len(nb)) + nb, "enc": pl["pos"]})
    out = _splice2(d, tree, edits) if edits else d
    write_new(dst, scramble(out))
    print("wrote %s: filled %d anonymous 0x1052 playlist name(s)" % (dst, len(edits)))


def cmd_dissolvegroup(src, dst, track, group_spec):
    """dissolve clip group matching GROUP_SPEC (name or start position) on TRACK, rebasing 0x2428 members onto TRACK."""
    dec = _decoder()
    raw, d, tree = descramble_file(src)
    d = bytes(d)
    pls = _playlist_blocks(d, tree, track)
    p2c = next((n for n in tree if n["ct"] == 0x262C), None)
    p2428 = next((n for n in tree if n["ct"] == 0x2428), None)
    mpls = [k for k in p2428["kids"][0]["kids"] if k["ct"] == 0x1052] if (p2428 and p2428["kids"]) else []
    k2bs = [k for k in p2c["kids"] if k["ct"] == 0x262B] if p2c else []
    if not mpls or not k2bs:
        probe.fail("session has no clip groups (0x262C / 0x2428)", "nothing to dissolve")
    target_pos = _pos(dec, d, tree, group_spec) if group_spec.startswith(("s", "t", "bar:")) else None
    edits, dissolved = [], 0
    for pl in pls:
        is_tick_pl = d[probe.end_of(pl) - 2] == 2 if pl["size"] >= 4 else False
        ents = [k for k in pl["kids"] if k["ct"] == 0x1050 and k["kids"] and k["kids"][0]["ct"] == 0x104F]
        new_ents, hit_here = [], 0
        for e in ents:
            o = e["kids"][0]["pos"] + 9
            is_grp = d[o + 15] == 3 and (e["kids"][0]["size"] >= 21 and d[o + 18] == 1)
            ridx = struct.unpack_from("<H", d, o + 2)[0]
            ev_pos = _epos(d, o)
            gname = ""
            mpl_idx = None
            if is_grp and ridx < len(k2bs):
                reg = next((x for x in k2bs[ridx]["kids"] if x["ct"] == 0x2628), None)
                if reg:
                    gln = struct.unpack_from("<I", d, reg["pos"] + 9)[0]
                    gname = d[reg["pos"] + 13:reg["pos"] + 13 + gln].decode("utf-8", "replace")
                    b23 = next((x for x in reg["kids"] if x["ct"] == 0x2523), None)
                    if b23 and b23["kids"]:
                        post = d[probe.end_of(b23["kids"][-1]):probe.end_of(b23)]
                        if len(post) >= 20:
                            mpl_idx = struct.unpack_from("<I", post, 16)[0]
            base_gname = re.sub(r"\.(?:L|R)$", "", gname)
            matched = is_grp and mpl_idx is not None and mpl_idx < len(mpls) and (
                (target_pos is not None and ev_pos == target_pos)
                or (target_pos is None and group_spec in (gname, base_gname))
            )
            if matched:
                hit_here += 1
                mpl = mpls[mpl_idx]
                for me in [k for k in mpl["kids"] if k["ct"] == 0x1050 and k["kids"] and k["kids"][0]["ct"] == 0x104F]:
                    mb = bytearray(d[me["pos"]:me["pos"] + 7 + me["size"]])
                    mo = me["kids"][0]["pos"] - me["pos"] + 9
                    rel_raw = int.from_bytes(mb[mo + 7:mo + 12], "little")
                    rel = (rel_raw - OFF12) if (rel_raw >= OFF12) else rel_raw
                    abs_pos = ev_pos + rel
                    mb[mo + 14] = 0x40 if is_tick_pl else 0x00
                    mb[mo + 7:mo + 12] = _epos_bytes(mb, mo, abs_pos)
                    new_ents.append(bytes(mb))
            else:
                new_ents.append(d[e["pos"]:e["pos"] + 7 + e["size"]])
        if hit_here:
            dissolved += hit_here
            edits.append(_splice_playlist_entries(d, pl, new_ents))
    if not dissolved:
        probe.fail("no clip group matching '%s' on '%s'" % (group_spec, track), "check ptx_decode clip_groups")
    out = _splice2(d, tree, edits)
    write_new(dst, scramble(out))
    print("wrote %s: dissolved %d clip-group placement(s) matching '%s' on '%s'" % (dst, dissolved, group_spec, track))


def cmd_setvisible(src, dst, track, visible):
    """show (1/true/show) or hide (0/false/hide) TRACK via 0x2519 display numbers + 0x2015 view flags."""
    hide = 0 if str(visible).strip().lower() in ("1", "true", "on", "yes", "show") else 1
    cmd_setflag(src, dst, track, "hidden", str(hide))


def _scan_wav_metadata(path):
    """Read RIFF fmt, data sample count, and optional BWF bext metadata/UMID from a WAV file cleanly."""
    info = {"path": path, "channels": None, "sample_rate": None, "bits": None, "samples": None, "bext_umid": None}
    with open(path, "rb") as f:
        hdr = f.read(12)
        if len(hdr) < 12 or hdr[:4] not in (b"RIFF", b"RF64") or hdr[8:12] != b"WAVE":
            return None
        block_align = 0
        while True:
            chdr = f.read(8)
            if len(chdr) < 8:
                break
            cid, csz = chdr[:4], struct.unpack_from("<I", chdr, 4)[0]
            pos = f.tell()
            if cid == b"fmt " and csz >= 16:
                fmt = f.read(16)
                _, ch, sr, _, ba, bps = struct.unpack_from("<HHIIHH", fmt, 0)
                info["channels"], info["sample_rate"], info["bits"], block_align = ch, sr, bps, ba
            elif cid == b"data" and block_align:
                info["samples"] = csz // block_align
            elif cid == b"bext" and csz >= 602:
                bext = f.read(602)
                umid = bext[346 + 64:346 + 64 + 64]
                if any(umid[:32]):
                    info["bext_umid"] = umid[:32].hex()
            f.seek(pos + csz + (csz & 1))
    return info


def cmd_relinkcheck(src, *dirs):
    """read-only preflight verifying UMIDs, region bounds, and optional BWF bext/fmt/data on disk."""
    import json
    dec = _decoder()
    res = dec.decode(src)
    umids = res.get("umids") or {}
    regions = [r for r in (res.get("regions") or []) if r.get("list") is None]
    disk_wavs = {}
    for root_dir in dirs:
        for dirpath, _, fns in os.walk(root_dir):
            for fn in fns:
                if fn.lower().endswith((".wav", ".bwf")):
                    meta = _scan_wav_metadata(os.path.join(dirpath, fn))
                    if meta:
                        disk_wavs.setdefault(os.path.splitext(fn)[0], meta)
    issues = []
    sess_sr = (res.get("format") or {}).get("sample_rate")
    for stem, umid in sorted(umids.items()):
        if not umid:
            issues.append({"kind": "missing_umid", "stem": stem})
        if stem in disk_wavs:
            wm = disk_wavs[stem]
            if sess_sr and wm["sample_rate"] and wm["sample_rate"] != sess_sr:
                issues.append({"kind": "sample_rate_mismatch", "stem": stem, "session": sess_sr, "wav": wm["sample_rate"]})
            if wm["bext_umid"] and umid and wm["bext_umid"][:24] != umid[:24]:
                issues.append({"kind": "bext_umid_mismatch", "stem": stem, "session_umid": umid, "bext_umid": wm["bext_umid"]})
    for r in regions:
        stem = re.sub(r"(?:-\d+|\.(?:L|R))$", "", r.get("name", ""))
        wm = disk_wavs.get(stem)
        if wm and wm["samples"] is not None and (r.get("start", 0) + r.get("length", 0)) > wm["samples"]:
            issues.append({"kind": "region_oob", "region": r.get("name"), "end": r.get("start", 0) + r.get("length", 0), "wav_samples": wm["samples"]})
    report = {"file": src, "audio_files": len(umids), "umids": len([v for v in umids.values() if v]),
              "disk_wavs_matched": sum(1 for k in umids if k in disk_wavs), "regions_checked": len(regions), "issues": issues}
    print(json.dumps(report, indent=1))
    sys.exit(1 if issues else 0)


def main(argv):
    """Command line entry point; see the usage examples at the top of this file."""
    cmds = {"roundtrip": cmd_roundtrip, "copy": cmd_copy, "rename": cmd_rename, "addmarker": cmd_addmarker, "patch": cmd_patch, "addnote": cmd_addnote, "renamex": cmd_renamex, "removetrack": cmd_removetrack, "newsession": cmd_newsession, "newsong": cmd_newsong, "buildspec": cmd_buildspec, "addclip": cmd_addclip, "setcomment": cmd_setcomment, "setfolder": cmd_setfolder, "emptytrack": cmd_emptytrack, "rebuilddir": cmd_rebuilddir, "setnotes": cmd_setnotes, "addtrack3": cmd_addtrack3, "addtrack4": cmd_addtrack4, "dropblock": cmd_dropblock, "newbase": cmd_newbase, "setmarkers": cmd_setmarkers, "setgroups": cmd_setgroups, "addbus": cmd_addbus, "addsend": cmd_addsend, "setoutput": cmd_setoutput,
            "addplugin": cmd_addplugin, "setcolor": cmd_setcolor, "addplaylist": cmd_addplaylist, "settimeline": cmd_settimeline, "setkeysig": cmd_setkeysig, "setcliploop": cmd_setcliploop, "addclipgroup": cmd_addclipgroup,
            "setlane": cmd_setlane, "setflag": cmd_setflag, "setparam": cmd_setparam, "setclipgain": cmd_setclipgain, "setdelay": cmd_setdelay, 
            "setclipmute": cmd_setclipmute, "addautolane": cmd_addautolane, "setpluglane": cmd_setpluglane, "setinput": cmd_setinput, "setsendpath": cmd_setsendpath, "renamebus": cmd_renamebus, "splitclip": cmd_splitclip, "addfade": cmd_addfade, "setsyncpoint": cmd_setsyncpoint, "placeclip": cmd_placeclip, "setclipgainat": cmd_setclipgainat,
            "moveclip": cmd_moveclip, "deleteclip": cmd_deleteclip, "trimclip": cmd_trimclip, "delmarker": cmd_delmarker, "anonnames": cmd_anonnames, "dissolvegroup": cmd_dissolvegroup, "setvisible": cmd_setvisible}
    if len(argv) < 2 or (argv[1] not in cmds and argv[1] not in ("diffblocks", "dircheck", "chcheck", "aucheck", "relinkcheck")):
        probe.fail("unknown command", "usage: ptx_edit.py buildspec|newsong|newbase|roundtrip|copy|rename|addmarker|patch|addnote|renamex|removetrack|newsession|addclip|setcomment|setfolder|emptytrack|rebuilddir|setnotes|addtrack3|addtrack4|dropblock|setlane|setflag|setparam|setclipgain|setdelay|setclipmute|addautolane|setpluglane|setinput|setsendpath|renamebus|splitclip|addfade|setsyncpoint|placeclip|setclipgainat|moveclip|deleteclip|trimclip|delmarker|anonnames|dissolvegroup|setvisible|relinkcheck ... (see the top of this file)")
    if len(argv) > 1 and argv[1] == "relinkcheck":
        return cmd_relinkcheck(*argv[2:])
    if len(argv) > 1 and argv[1] == "aucheck":
        return cmd_aucheck(*argv[2:])
    if len(argv) > 1 and argv[1] == "chcheck":
        return cmd_chcheck(*argv[2:])
    if len(argv) > 1 and argv[1] == "dircheck":
        return cmd_dircheck(*argv[2:])
    if len(argv) > 1 and argv[1] == "diffblocks":
        return cmd_diffblocks(*argv[2:])
    cmds[argv[1]](*argv[2:])


if __name__ == "__main__":
    main(sys.argv)
