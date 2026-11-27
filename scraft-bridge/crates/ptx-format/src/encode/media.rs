// Version: 0.7.0 (beta) | Date: 2026-11-27
//! Clean-room builders for audio/MIDI media blocks: `0x0F3D`, `0x1004`, `0x2637`, `0x2630`, `0x262A`, `0x2000`, `0x2634`, `0x1054`, `0x1015`, `0x1058`.

use crate::encode::ids::IdGen;
use crate::encode::spec::{
    BuildAudioFile, BuildClipLoop, BuildFade, BuildFadeKind, BuildFadeSlope, BuildMidiClip,
    BuildTimebase, BuildTrackKind, PtxBuildSpec,
};
use crate::primitives::{lp_bytes, OFFSET_FORM};
use crate::tree::encode_block;

const ID_MARK: &[u8] = &[0x2a, 0x00, 0x00, 0x00];
const UMID_LABEL: &[u8] = &[0x06, 0x0a, 0x2b, 0x34, 0x01, 0x01, 0x01, 0x05, 0x01, 0x01, 0x0f, 0x10];

fn push_u40(dst: &mut Vec<u8>, val: u64) {
    dst.extend_from_slice(&val.to_le_bytes()[..5]);
}

fn min_varint_w(val: u64) -> u8 {
    if val < (1 << 8) {
        1
    } else if val < (1 << 16) {
        2
    } else if val < (1 << 24) {
        3
    } else if val < (1 << 32) {
        4
    } else if val < (1 << 40) {
        5
    } else {
        6
    }
}

fn nibble_width(val: u64) -> u8 {
    if val == 0 {
        0
    } else if val < (1 << 24) {
        3
    } else if val < (1 << 32) {
        4
    } else {
        5
    }
}

fn encode_242b(lp: &BuildClipLoop) -> Vec<u8> {
    let u = if lp.is_ticks { 0x40u8 } else { 0x00u8 };
    let mut d = Vec::with_capacity(57);
    d.push(lp.mode);
    d.extend_from_slice(&[0u8; 10]);
    d.extend_from_slice(&lp.bars.to_le_bytes());
    d.extend_from_slice(&lp.beats.to_le_bytes());
    d.extend_from_slice(&lp.ticks.to_le_bytes());
    d.extend_from_slice(&0u32.to_le_bytes());
    d.extend_from_slice(&lp.count.to_le_bytes());
    d.extend_from_slice(&lp.trim.to_le_bytes()[..7]);
    d.push(u);
    d.extend_from_slice(&lp.iter.to_le_bytes()[..7]);
    d.push(u);
    d.extend_from_slice(&[0u8; 10]);
    encode_block(2, 0x242b, &d)
}

/// Build an empty MIDI `MdChun` or populated MIDI `MdChun`.
#[must_use]
pub fn build_midi_chunk(
    clip: Option<&BuildMidiClip>,
    cid8: [u8; 8],
    plain: bool,
) -> Vec<u8> {
    let notes = clip.map_or(&[][..], |c| c.notes.as_slice());
    let base = if plain { 0u64 } else { OFFSET_FORM };
    let n = notes.len();

    let mut s1 = Vec::with_capacity(n * 35);
    let mut s2 = Vec::with_capacity(n * 11);
    for note in notes {
        push_u40(&mut s1, base + note.start_ticks);
        s1.extend_from_slice(&[0x00, 0x00, 0x40, note.key]);
        push_u40(&mut s1, note.length_ticks);
        s1.extend_from_slice(&[0x00, 0x00, 0x40, note.velocity, 64]);
        s1.extend_from_slice(&2.0f64.to_le_bytes());
        s1.extend_from_slice(&2.0f64.to_le_bytes());

        s2.push(note.key);
        push_u40(&mut s2, note.length_ticks);
        s2.extend_from_slice(&[0x00, 0x00, 0x40, note.velocity, 64]);
    }

    let mut nlb_body = Vec::new();
    nlb_body.extend_from_slice(&u32::try_from(n).unwrap_or(0).to_le_bytes());
    nlb_body.extend_from_slice(&s1);
    nlb_body.extend_from_slice(&u32::try_from(n).unwrap_or(0).to_le_bytes());
    nlb_body.extend_from_slice(&11u32.to_le_bytes());
    nlb_body.extend_from_slice(&s2);
    nlb_body.extend_from_slice(&u32::try_from(n).unwrap_or(0).to_le_bytes());
    nlb_body.extend_from_slice(&[0x03, 0x00, 0x12, 0x00, 0x00, 0x00]);
    nlb_body.extend(std::iter::repeat_n(0u8, 18 * n));

    let mut nlb = b"MdNLB\x03\x00".to_vec();
    nlb.extend_from_slice(&u32::try_from(nlb_body.len()).unwrap_or(0).to_le_bytes());
    nlb.extend_from_slice(&nlb_body);

    let ctrls = clip.map_or(&[][..], |c| c.controllers.as_slice());
    let mut sorted_ctrls: Vec<_> = ctrls.iter().collect();
    let order = |k: u8| match k {
        1 => 0u8,
        2 => 1,
        4 => 2,
        3 => 3,
        5 => 4,
        _ => 9,
    };
    sorted_ctrls.sort_by_key(|c| (order(c.kind), c.number));

    let mut sets = Vec::new();
    for c in &sorted_ctrls {
        let mut cd = u32::try_from(c.points.len()).unwrap_or(0).to_le_bytes().to_vec();
        for &(t, v) in &c.points {
            push_u40(&mut cd, base + t);
            cd.extend_from_slice(&[0x00, 0x00, 0x40]);
            cd.extend_from_slice(&v.to_le_bytes());
        }
        let mut ss = vec![c.kind, c.number, 0, 0, 0, 0, 0, 0xff, 0xff];
        ss.extend_from_slice(&[0u8; 16]);

        let mut cds_body = b"Mdss\x01\x00".to_vec();
        cds_body.extend_from_slice(&u32::try_from(ss.len()).unwrap_or(0).to_le_bytes());
        cds_body.extend_from_slice(&ss);
        cds_body.extend_from_slice(b"MdCD\x01\x00");
        cds_body.extend_from_slice(&u32::try_from(cd.len()).unwrap_or(0).to_le_bytes());
        cds_body.extend_from_slice(&cd);

        sets.extend_from_slice(b"MdCDS\x02\x00");
        sets.extend_from_slice(&u32::try_from(cds_body.len()).unwrap_or(0).to_le_bytes());
        sets.extend_from_slice(&cds_body);
    }

    let sysex = clip.map_or(&[][..], |c| c.sysex.as_slice());
    let mut tel = u32::try_from(sysex.len()).unwrap_or(0).to_le_bytes().to_vec();
    for (t, pay) in sysex {
        push_u40(&mut tel, base + *t);
        tel.extend_from_slice(&[0x00, 0x00, 0x40, 0x01, 0x00]);
        tel.extend_from_slice(&u32::try_from(pay.len() + 5).unwrap_or(5).to_le_bytes());
        tel.push(0x00);
        tel.extend_from_slice(&u32::try_from(pay.len()).unwrap_or(0).to_le_bytes());
        tel.extend_from_slice(pay);
    }

    let mut body = nlb;
    body.extend_from_slice(&u32::try_from(sorted_ctrls.len()).unwrap_or(0).to_le_bytes());
    body.extend_from_slice(&sets);
    body.extend_from_slice(b"MdES\x01\x00");
    body.extend_from_slice(&u32::try_from(11 + tel.len()).unwrap_or(15).to_le_bytes());
    body.extend_from_slice(b"MdTEL\x01\x00");
    body.extend_from_slice(&u32::try_from(tel.len()).unwrap_or(4).to_le_bytes());
    body.extend_from_slice(&tel);
    body.extend_from_slice(&0u32.to_le_bytes());
    body.extend_from_slice(ID_MARK);
    body.extend_from_slice(&cid8);
    body.push(0x01);

    let mut chunk = b"MdChun\x01\x00".to_vec();
    chunk.extend_from_slice(&u32::try_from(body.len()).unwrap_or(0).to_le_bytes());
    chunk.extend_from_slice(&body);
    chunk
}

fn file_descriptor(file_no: usize, af: &BuildAudioFile, ids: &mut IdGen) -> Vec<u8> {
    let st = u8::from(af.channels == 2);
    let uid = ids.next_uuid16();
    let fid = af.umid_file_id.unwrap_or_else(|| {
        let mut r = ids.next_id8();
        r[6] = 0x80;
        r[7] = 0x00;
        r
    });
    let umid_tail = ids.next_id8();

    let mut d1001 = Vec::new();
    d1001.extend_from_slice(&af.sample_rate.to_le_bytes());
    d1001.push(af.channels);
    d1001.push(af.bit_depth);
    d1001.extend_from_slice(&af.frames.to_le_bytes());
    d1001.extend_from_slice(&(if af.is_aiff { 4u64 } else { 3u64 }).to_le_bytes());
    d1001.push(0x2a);
    d1001.extend_from_slice(&fid);

    let mut p0 = vec![0u8; 29];
    p0.extend_from_slice(&af.filetime.to_le_bytes());
    p0.extend_from_slice(&[1, 0]);
    p0.extend_from_slice(&af.data_offset.to_le_bytes());
    p0.extend_from_slice(&[0u8; 51]);
    p0.extend_from_slice(&af.filetime.to_le_bytes());
    p0.push(u8::from(af.is_float));
    p0.extend_from_slice(&[0, 0, st]);
    p0.extend_from_slice(&[0u8; 18]);
    p0.extend_from_slice(&uid);

    let mut p2 = vec![0u8; 17];
    p2.push(st);
    p2.extend_from_slice(UMID_LABEL);
    p2.extend_from_slice(&[0x13, 0, 0, 0]);
    p2.extend_from_slice(&fid);
    p2.extend_from_slice(&umid_tail);
    p2.extend_from_slice(&[0u8; 7]);
    p2.push(st);
    p2.extend_from_slice(&[0u8; 7]);

    let mut i2106 = p0;
    i2106.extend_from_slice(&encode_block(1, 0x4301, &[0u8; 32]));
    i2106.extend_from_slice(&p2);

    let mut d1003 = Vec::new();
    d1003.extend_from_slice(&u32::try_from(file_no + 1).unwrap_or(1).to_le_bytes());
    d1003.extend_from_slice(&encode_block(2, 0x1001, &d1001));
    d1003.extend_from_slice(&encode_block(2, 0x1033, &[]));
    d1003.extend_from_slice(&encode_block(0x26, 0x2106, &i2106));
    d1003.extend_from_slice(&[0u8; 4]);
    encode_block(9, 0x1003, &d1003)
}

struct AudioRegionArgs<'a> {
    name: &'a str,
    frames: u64,
    start: u64,
    sync_offset: Option<u64>,
    file_index: usize,
    channel: u16,
    gain_index: u32,
}

fn audio_region_2629(args: &AudioRegionArgs<'_>, ids: &mut IdGen) -> Vec<u8> {
    let AudioRegionArgs {
        name,
        frames,
        start,
        sync_offset,
        file_index,
        channel,
        gain_index,
    } = *args;
    let clip_id = ids.next_uuid16();
    let cid8 = ids.next_id8();
    let chunk = build_midi_chunk(None, cid8, true);

    let ws = nibble_width(start);
    let wl = nibble_width(frames).max(1);
    let sync_v = sync_offset.filter(|&v| v > 0);
    let sync_w = sync_v.map_or(0, nibble_width);
    let mut r28_data = lp_bytes(name);
    r28_data.extend_from_slice(&[0, ws << 4, (wl << 4) | sync_w, 0, 0]);
    if ws > 0 {
        r28_data.extend_from_slice(&start.to_le_bytes()[..usize::from(ws)]);
    }
    if let Some(sv) = sync_v {
        r28_data.extend_from_slice(&sv.to_le_bytes()[..usize::from(sync_w)]);
    }
    r28_data.extend_from_slice(&frames.to_le_bytes()[..usize::from(wl)]);
    r28_data.extend_from_slice(&[0xfe, 0xff, 0, 0, 0, 0, 0xff, 0xff, 0x04, 0x00, 0x04, 0x00]);
    r28_data.extend_from_slice(&[0u8; 21]);
    r28_data.extend_from_slice(&gain_index.to_le_bytes());
    r28_data.extend_from_slice(&[0u8; 2]);
    r28_data.extend_from_slice(&clip_id);
    let r28 = encode_block(5, 0x2628, &r28_data);

    let mut d2629 = r28;
    d2629.extend_from_slice(&u32::try_from(file_index).unwrap_or(0).to_le_bytes());
    d2629.extend_from_slice(&channel.to_le_bytes());
    d2629.extend_from_slice(&1.0f32.to_le_bytes());
    d2629.extend_from_slice(&1.0f32.to_le_bytes());
    d2629.extend_from_slice(&[0u8; 8]);
    d2629.push(0xff);
    d2629.extend_from_slice(&clip_id);
    d2629.extend_from_slice(&[0u8; 9]);
    let b4403 = encode_block(1, 0x4403, &[&encode_block(0, 0x1000, &[0u8; 18])[..], &[0u8]].concat());
    d2629.extend_from_slice(&b4403);
    d2629.extend_from_slice(&[0x00, 0x00, 0x01, 0x00, 0x7f]);
    d2629.extend_from_slice(&chunk);
    d2629.extend_from_slice(&u32::try_from(file_index).unwrap_or(0).to_le_bytes());
    d2629.extend_from_slice(&[0u8; 4]);
    encode_block(11, 0x2629, &d2629)
}

fn fade_block(fade: &BuildFade) -> Vec<u8> {
    let slope_b = match fade.slope {
        BuildFadeSlope::EqualPower => 1u8,
        BuildFadeSlope::EqualGain => 2u8,
    };
    match fade.kind {
        BuildFadeKind::FadeOut => {
            let w = if fade.length_samples < 256 {
                1u8
            } else if fade.length_samples < 65536 {
                2u8
            } else {
                3u8
            };
            let mut d = vec![0u8; 5];
            d.push((w << 4) | w);
            d.extend_from_slice(&[0, 0]);
            let lb = fade.length_samples.to_le_bytes();
            d.extend_from_slice(&lb[..usize::from(w)]);
            d.extend_from_slice(&lb[..usize::from(w)]);
            d.push(2);
            d.push(slope_b);
            d.extend_from_slice(&[0u8; 13]);
            encode_block(2, 0x262f, &d)
        }
        BuildFadeKind::FadeIn | BuildFadeKind::Crossfade => {
            if fade.kind == BuildFadeKind::Crossfade
                && let Some(pre) = fade.pre_roll_samples.filter(|&p| p > 0)
            {
                let w1 = nibble_width(pre).max(2);
                let w2 = nibble_width(fade.length_samples).max(2);
                let mut d = vec![0u8; 5];
                d.push((w1 << 4) | w2);
                d.extend_from_slice(&[0, 0]);
                d.extend_from_slice(&pre.to_le_bytes()[..usize::from(w1)]);
                d.extend_from_slice(&fade.length_samples.to_le_bytes()[..usize::from(w2)]);
                d.push(1);
                d.push(slope_b);
                d.extend_from_slice(&[0u8; 20]);
                return encode_block(2, 0x262f, &d);
            }
            let mut d = vec![0, 0, 0, 0, 0, 0x30, 0, 0];
            d.extend_from_slice(&fade.length_samples.to_le_bytes()[..3]);
            d.push(if fade.kind == BuildFadeKind::Crossfade { 1 } else { 3 });
            d.push(slope_b);
            d.extend_from_slice(&[0u8; 10]);
            if fade.kind == BuildFadeKind::Crossfade {
                d.extend_from_slice(&[0u8; 10]);
            }
            encode_block(2, 0x262f, &d)
        }
    }
}

struct PlaylistEntryArgs<'a> {
    region_index: u16,
    pos: u64,
    raw_pos_override: Option<u64>,
    is_ticks: bool,
    muted: bool,
    sub_kind: u8,
    link: i16,
    is_group: bool,
    trailer_is_fade: bool,
    clip_loop: Option<&'a BuildClipLoop>,
}

fn playlist_1050(args: PlaylistEntryArgs<'_>) -> Vec<u8> {
    let pos_val = args.raw_pos_override.unwrap_or({
        if args.is_ticks {
            OFFSET_FORM + args.pos
        } else {
            args.pos
        }
    });
    let mut o = Vec::with_capacity(35);
    o.push(u8::from(args.muted));
    o.push(0);
    o.extend_from_slice(&args.region_index.to_le_bytes());
    o.extend_from_slice(&[0u8; 3]);
    push_u40(&mut o, pos_val);
    o.extend_from_slice(&[0, 0]);
    o.push(if args.is_ticks { 0x40 } else { 0 });
    o.push(args.sub_kind);
    o.extend_from_slice(&args.link.to_le_bytes());
    o.push(u8::from(args.is_group));
    o.push(u8::from(args.clip_loop.is_some()));
    if let Some(lp) = args.clip_loop {
        o.extend_from_slice(&encode_242b(lp));
    }
    o.extend_from_slice(&[0, 0]);
    o.extend_from_slice(&[0xffu8; 8]);
    o.extend_from_slice(&[0u8; 5]);

    let mut d1050 = encode_block(10, 0x104f, &o);
    d1050.extend_from_slice(&[
        u8::from(args.trailer_is_fade),
        0x01,
        u8::from(!args.is_group),
    ]);
    if args.is_group {
        // Write `[0x00, 0x01, 0x01]` trailer on grouped entries matching `tools/ptx_edit.py`
        if let Some(last) = d1050.last_mut() {
            *last = 0x01;
        }
    }
    encode_block(3, 0x1050, &d1050)
}

fn build_midi_clip_2633(name: &str, length_ticks: u64, chunk_idx: u32, ids: &mut IdGen) -> Vec<u8> {
    let clip_id = ids.next_uuid16();
    let wl = nibble_width(length_ticks).max(1);
    let mut d28 = lp_bytes(name);
    d28.extend_from_slice(&[0, 1, wl << 4, 0, 0]);
    d28.extend_from_slice(&length_ticks.to_le_bytes()[..usize::from(wl)]);
    d28.extend_from_slice(&[0xfe, 0xff, 0, 0, 0, 0, 0xff, 0xff, 0x04, 0x00, 0x04, 0x00]);
    d28.extend_from_slice(&[0u8; 21]);
    d28.extend_from_slice(&[0xffu8; 4]);
    d28.extend_from_slice(&[0u8; 2]);
    d28.extend_from_slice(&clip_id);
    let r28 = encode_block(5, 0x2628, &d28);

    let mut d33 = r28;
    d33.extend_from_slice(&chunk_idx.to_le_bytes());
    encode_block(1, 0x2633, &d33)
}

fn midi_route_1057(
    name: &str,
    entries: &[(u16, u64, bool, bool, Option<&BuildClipLoop>)],
    playlist_id: [u8; 8],
    is_ticks_tb: bool,
) -> Vec<u8> {
    let mut d = lp_bytes(name);
    d.extend_from_slice(&u32::try_from(entries.len()).unwrap_or(0).to_le_bytes());
    for &(ri, pos, mu, tk, lp) in entries {
        let pos_val = if tk { OFFSET_FORM + pos } else { pos };
        let mut o = Vec::with_capacity(35);
        o.push(u8::from(mu));
        o.push(0);
        o.extend_from_slice(&ri.to_le_bytes());
        o.extend_from_slice(&[0u8; 3]);
        push_u40(&mut o, pos_val);
        o.extend_from_slice(&[0, 0]);
        o.push(if tk { 0x40 } else { 0 });
        o.push(3);
        o.extend_from_slice(&[0xfe, 0xff, 0, u8::from(lp.is_some())]);
        if let Some(l) = lp {
            o.extend_from_slice(&encode_242b(l));
        }
        o.extend_from_slice(&[1, 0]);
        o.extend_from_slice(&[0xffu8; 8]);
        o.extend_from_slice(&[0u8; 5]);
        d.extend_from_slice(&encode_block(1, 0x1056, &encode_block(10, 0x104f, &o)));
    }

    let r2502 = [0x01u8, 0x01, 0x00, 0x01];
    let exact_103d_59: [u8; 59] = [
        0x45, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x4c, 0x0d, 0x41, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x4c, 0xfd, 0x40, 0x05, 0x00, 0x00, 0x00, 0x03, 0x00, 0x00, 0x00, 0x02, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x64, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x64, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00,
    ];
    let exact_end: [u8; 84] = [
        0x00, 0x00, 0x64, 0x00, 0x64, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0xa6, 0x0e,
        0x00, 0x00, 0x00, 0x00, 0x00, 0xc0, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x01, 0x00, 0x64, 0x00, 0x00, 0xe8, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x32, 0xaa, 0x05, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x64, 0x00, 0x00, 0x00, 0x01,
        0x00, 0x7f, 0x00, 0x00, 0x00, 0x00, 0x3c, 0x00, 0x00,
    ];
    let mut b2502_body = r2502.to_vec();
    b2502_body.extend_from_slice(&encode_block(4, 0x103d, &exact_103d_59));
    b2502_body.extend_from_slice(&exact_end);

    d.extend_from_slice(&encode_block(2, 0x2502, &b2502_body));
    d.push(if is_ticks_tb { 2 } else { 1 });
    d.extend_from_slice(&[0u8; 4]);
    d.extend_from_slice(ID_MARK);
    d.extend_from_slice(&playlist_id);
    encode_block(4, 0x1057, &d)
}

struct ClipGroupRegionArgs<'a> {
    name: &'a str,
    is_ticks: bool,
    g_start: u64,
    g_len: u64,
    bpm: f64,
    mpl_idx: u32,
    grp_id: u32,
    ch_idx: u16,
}

fn build_clip_group_262b(a: &ClipGroupRegionArgs<'_>, ids: &mut IdGen) -> Vec<u8> {
    let clip_id = ids.next_uuid16();
    let (bt28, head, post26) = if a.is_ticks {
        let vals = [OFFSET_FORM, a.g_len, a.g_start, a.g_start];
        let w = [
            min_varint_w(vals[0]),
            min_varint_w(vals[1]),
            min_varint_w(vals[2]),
            min_varint_w(vals[3]),
        ];
        let mut h = lp_bytes(a.name);
        h.extend_from_slice(&[0, (w[0] << 4) | 1, w[1] << 4, (w[2] << 4) | w[3], 8]);
        for (v, k) in vals.into_iter().zip(w) {
            h.extend_from_slice(&v.to_le_bytes()[..usize::from(k)]);
        }
        h.extend_from_slice(&[0xffu8; 8]);
        h.extend_from_slice(&[0xfe, 0xff, 0, 0, 0, 0, 0xff, 0xff, 0x04, 0x00, 0x04, 0x00, 1, 0, 0, 0]);

        let mut p26 = Vec::new();
        p26.extend_from_slice(&(OFFSET_FORM + a.g_start).to_le_bytes()[..7]);
        p26.push(0x40);
        p26.extend_from_slice(&[0xffu8; 4]);
        for v in [0u32, a.mpl_idx, 0, 1] {
            p26.extend_from_slice(&v.to_le_bytes());
        }
        p26.extend_from_slice(&OFFSET_FORM.to_le_bytes());
        p26.extend_from_slice(&a.bpm.to_le_bytes());
        p26.extend_from_slice(&960_000u64.to_le_bytes());
        p26.extend_from_slice(&OFFSET_FORM.to_le_bytes()[..7]);
        p26.push(0x40);
        p26.extend_from_slice(&(OFFSET_FORM + a.g_len).to_le_bytes()[..7]);
        p26.push(0x40);
        p26.extend_from_slice(&(OFFSET_FORM + a.g_start + a.g_len).to_le_bytes()[..7]);
        p26.push(0x40);
        p26.extend_from_slice(&[0xffu8; 4]);
        p26.extend_from_slice(&[0u8; 9]);
        (4u16, h, p26)
    } else {
        let vals = [OFFSET_FORM, a.g_len];
        let w = [min_varint_w(vals[0]), min_varint_w(vals[1])];
        let mut h = lp_bytes(a.name);
        h.extend_from_slice(&[0, w[0] << 4, w[1] << 4, 0, 8]);
        for (v, k) in vals.into_iter().zip(w) {
            h.extend_from_slice(&v.to_le_bytes()[..usize::from(k)]);
        }
        h.extend_from_slice(&[0xffu8; 8]);
        h.extend_from_slice(&[0xfe, 0xff, 0, 0, 0, 0, 0xff, 0xff, 0x04, 0x00, 0x04, 0x00, 1, 0, 0, 0]);

        let mut p26 = vec![0u8; 8];
        p26.extend_from_slice(&[0xffu8; 4]);
        for v in [0u32, a.mpl_idx, 0, 0] {
            p26.extend_from_slice(&v.to_le_bytes());
        }
        p26.extend_from_slice(&OFFSET_FORM.to_le_bytes());
        p26.extend_from_slice(&(OFFSET_FORM + a.g_len).to_le_bytes());
        p26.extend_from_slice(&u32::try_from(a.g_len).unwrap_or(u32::MAX).to_le_bytes());
        p26.extend_from_slice(&[0u8; 4]);
        p26.extend_from_slice(&[0xffu8; 4]);
        p26.extend_from_slice(&[0u8; 9]);
        (5u16, h, p26)
    };
    let b2523 = encode_block(
        9,
        0x2523,
        &[&encode_block(2, 0x2526, &[0u8; 12])[..], &post26].concat(),
    );
    let mut r28_d = head;
    r28_d.extend_from_slice(&b2523);
    r28_d.extend_from_slice(&[0u8; 17]);
    r28_d.extend_from_slice(&[0xffu8; 4]);
    r28_d.extend_from_slice(&[0, 0]);
    r28_d.extend_from_slice(&clip_id);
    let r28 = encode_block(bt28, 0x2628, &r28_d);
    let mut d262b = r28;
    d262b.extend_from_slice(&a.grp_id.to_le_bytes());
    d262b.extend_from_slice(&a.ch_idx.to_be_bytes());
    d262b.extend_from_slice(&a.ch_idx.to_be_bytes());
    d262b.push(0);
    encode_block(1, 0x262b, &d262b)
}

/// Output container blocks generated by `build_media_blocks`.
pub struct BuiltMedia {
    pub blk_0f3d: Vec<u8>,
    pub blk_1004: Vec<u8>,
    pub blk_2637: Vec<u8>,
    pub blk_262c: Vec<u8>,
    pub blk_2632: Vec<u8>,
    pub blk_262a: Vec<u8>,
    pub blk_2630: Vec<u8>,
    pub blk_262e: Vec<u8>,
    pub blk_2000: Vec<u8>,
    pub blk_2634: Vec<u8>,
    pub blk_1054: Vec<u8>,
    pub blk_1015: Vec<u8>,
    pub blk_1058: Vec<u8>,
    pub blk_2428: Option<Vec<u8>>,
    pub blk_2424: Option<Vec<u8>>,
    pub blk_2426: Option<Vec<u8>>,
    /// Per audio track: `channel_playlist_indices` (0-based in `0x1054`).
    pub audio_track_playlists: Vec<Vec<u16>>,
    /// Per track (indexed parallel to `spec.tracks`): whether the track has any placed clips.
    pub track_has_clips: Vec<bool>,
}

/// Build all media, audio/MIDI clip pool, playlist, fade, and route top-level blocks.
pub fn build_media_blocks(
    spec: &PtxBuildSpec,
    track_ids: &[([u8; 8], [u8; 8])],
    ids: &mut IdGen,
) -> BuiltMedia {
    // 1) Volume list 0x0F3D + Audio file tree 0x1004
    let vol_id: [u8; 4] = ids.next_id8()[..4].try_into().unwrap_or([0x11, 0x22, 0x33, 0x44]);
    let blk_0f3d = if spec.audio_files.is_empty() {
        encode_block(1, 0x0f3d, &0u32.to_le_bytes())
    } else {
        let mut vd = lp_bytes(&spec.volume_name);
        vd.extend_from_slice(&vol_id);
        vd.extend_from_slice(&1u32.to_le_bytes());
        vd.push(b'/');
        let mut d0f3d = 1u32.to_le_bytes().to_vec();
        d0f3d.extend_from_slice(&encode_block(1, 0x0f3c, &vd));
        encode_block(1, 0x0f3d, &d0f3d)
    };

    let mut d1004 = u32::try_from(spec.audio_files.len()).unwrap_or(0).to_le_bytes().to_vec();
    if spec.audio_files.is_empty() {
        d1004.extend_from_slice(&encode_block(1, 0x103a, &0u32.to_le_bytes()));
    } else {
        let nf = spec.audio_files.len();
        let chain_len = spec.audio_folder_chain.len();
        let mut nodes: Vec<(u8, u32, &[u8], [u8; 4])> = Vec::new();
        nodes.push((1, u32::try_from(1 + nf + chain_len).unwrap_or(1), b"Audio Files", [0u8; 4]));
        for af in &spec.audio_files {
            let tag = if af.is_aiff { *b"FFIA" } else { *b"EVAW" };
            nodes.push((2, 0, af.file_name.as_bytes(), tag));
        }
        nodes.push((0, u32::MAX, spec.volume_name.as_bytes(), vol_id));
        for (idx, part) in spec.audio_folder_chain.iter().enumerate() {
            nodes.push((1, u32::try_from(1 + nf + idx).unwrap_or(0), part.as_bytes(), [0u8; 4]));
        }
        let mut tbytes = u32::try_from(nodes.len()).unwrap_or(0).to_le_bytes().to_vec();
        for (ty, par, nm, tl) in nodes {
            tbytes.push(ty);
            tbytes.extend_from_slice(&par.to_le_bytes());
            tbytes.extend_from_slice(&u32::try_from(nm.len()).unwrap_or(0).to_le_bytes());
            tbytes.extend_from_slice(nm);
            tbytes.extend_from_slice(&tl);
        }
        d1004.extend_from_slice(&encode_block(1, 0x103a, &tbytes));
        for (i, af) in spec.audio_files.iter().enumerate() {
            d1004.extend_from_slice(&file_descriptor(i, af, ids));
        }
    }
    d1004.extend_from_slice(&0u32.to_le_bytes());
    d1004.extend_from_slice(&encode_block(1, 0x103a, &0u32.to_le_bytes()));
    let blk_1004 = encode_block(3, 0x1004, &d1004);

    // 2) Audio clip gain pool (0x2637), fades (0x2630), regions (0x262A), clip groups (0x262C/0x2428), audio playlists (0x1054 / 0x1015)
    let mut gain_lanes_bytes: Vec<Vec<u8>> = Vec::new();
    let mut fade_blocks: Vec<Vec<u8>> = Vec::new();
    let mut region_blocks: Vec<Vec<u8>> = Vec::new();
    let mut grp_262b_blocks: Vec<Vec<u8>> = Vec::new();
    let mut grp_member_1052: Vec<Vec<u8>> = Vec::new();
    let mut grp_2423_blocks: Vec<Vec<u8>> = Vec::new();
    let mut grp_2425_blocks: Vec<Vec<u8>> = Vec::new();
    let mut next_pt_grp_id: u32 = 0;
    let mut track_has_clips = vec![false; spec.tracks.len()];

    let mut p54_entries: Vec<Vec<u8>> = Vec::new();
    let mut p15_entries: Vec<Vec<u8>> = Vec::new();
    let mut audio_track_playlists: Vec<Vec<u16>> = Vec::new();

    let tempo_refs: Vec<(u64, f64)> = spec.tempo.iter().map(|t| (t.ticks, t.bpm)).collect();
    let sr_f = f64::from(spec.sample_rate.max(1));
    let default_bpm = tempo_refs.first().map_or(120.0, |t| t.1);

    for (tidx, tr) in spec.tracks.iter().enumerate() {
        if tr.kind != BuildTrackKind::Audio {
            continue;
        }
        let nch = if tr.stereo { 2usize } else { 1usize };
        let base_pl = u16::try_from(p54_entries.len()).unwrap_or(0);
        type ChannelEntry = (u64, u8, usize, Vec<u8>);
        let mut ch_pls = Vec::with_capacity(nch);
        let mut per_ch_entries: Vec<Vec<ChannelEntry>> = vec![Vec::new(); nch];
        let mut entry_seq = 0usize;

        // Partition clips into ungrouped singletons vs contiguous `group: Some(gid)` runs
        let mut clip_runs: Vec<(Option<u64>, &[crate::encode::spec::BuildAudioClip])> = Vec::new();
        let mut ci = 0usize;
        while ci < tr.audio_clips.len() {
            if let Some(gid) = tr.audio_clips[ci].group {
                let mut cj = ci + 1;
                while cj < tr.audio_clips.len() && tr.audio_clips[cj].group == Some(gid) {
                    cj += 1;
                }
                clip_runs.push((Some(gid), &tr.audio_clips[ci..cj]));
                ci = cj;
            } else {
                clip_runs.push((None, &tr.audio_clips[ci..=ci]));
                ci += 1;
            }
        }

        struct RunClipItem {
            ev_pos: u64,
            rank: u8,
            seq: usize,
            is_fade: bool,
            idx: u16,
            muted: bool,
            lp: Option<BuildClipLoop>,
        }

        for (grp_opt, run_clips) in clip_runs {
            let mut run_ch_items: Vec<Vec<RunClipItem>> = (0..nch).map(|_| Vec::new()).collect();
            let mut g_start = u64::MAX;
            let mut g_end = 0u64;
            let mut g_ticks = tr.timebase == BuildTimebase::Ticks;

            for clip in run_clips {
                track_has_clips[tidx] = true;
                g_ticks = clip.pos_in_ticks;
                let gain_idx = if clip.clip_gain_points.is_empty() {
                    u32::MAX
                } else {
                    let gi = u32::try_from(gain_lanes_bytes.len()).unwrap_or(u32::MAX);
                    let n = clip.clip_gain_points.len();
                    let mut gbody = Vec::new();
                    gbody.extend_from_slice(&0u16.to_le_bytes());
                    gbody.extend_from_slice(&u32::try_from(n).unwrap_or(1).to_le_bytes());
                    gbody.extend_from_slice(&4u16.to_le_bytes());
                    gbody.extend_from_slice(
                        &u16::try_from(n.saturating_sub(1))
                            .unwrap_or(u16::MAX)
                            .to_le_bytes(),
                    );
                    gbody.extend_from_slice(&0u32.to_le_bytes());
                    for &(pos, db) in &clip.clip_gain_points {
                        gbody.extend_from_slice(&pos.to_le_bytes());
                        gbody.extend_from_slice(&db.to_le_bytes());
                    }
                    let mut lane = vec![0x01, 0x46, 0x01, 0x00];
                    lane.extend_from_slice(&u32::try_from(gbody.len()).unwrap_or(0).to_le_bytes());
                    lane.extend_from_slice(&gbody);
                    gain_lanes_bytes.push(lane);
                    gi
                };

                let split_lr = tr.stereo && clip.file_indices.len() == 2;
                let fi0 = clip.file_indices.first().copied().unwrap_or(0);
                let sync_off = clip.sync_offset.unwrap_or(0);
                let (anchor_pos, end_pos) = if clip.pos_in_ticks {
                    let start_sec =
                        crate::primitives::ticks_to_seconds(clip.start_pos as f64, &tempo_refs);
                    let anchor = if sync_off > 0 {
                        crate::primitives::seconds_to_ticks(
                            start_sec + sync_off as f64 / sr_f,
                            &tempo_refs,
                        )
                        .round() as u64
                    } else {
                        clip.start_pos
                    };
                    let end = crate::primitives::seconds_to_ticks(
                        start_sec + clip.length_samples as f64 / sr_f,
                        &tempo_refs,
                    )
                    .round() as u64;
                    (anchor, end)
                } else {
                    (
                        clip.start_pos.saturating_add(sync_off),
                        clip.start_pos.saturating_add(clip.length_samples),
                    )
                };
                g_start = g_start.min(clip.start_pos);
                g_end = g_end.max(end_pos);

                for (c, item_vec) in run_ch_items.iter_mut().enumerate().take(nch) {
                    let reg_idx = u16::try_from(region_blocks.len()).unwrap_or(0);
                    let rname = if tr.stereo {
                        let base = clip
                            .name
                            .strip_suffix(".L")
                            .or_else(|| clip.name.strip_suffix(".R"))
                            .unwrap_or(&clip.name);
                        let ch_suffix = if c == 0 { ".L" } else { ".R" };
                        format!("{base}{ch_suffix}")
                    } else {
                        clip.name.clone()
                    };
                    let fi = if split_lr { clip.file_indices[c] } else { fi0 };
                    let ch_in_file = if split_lr { 0u16 } else { u16::try_from(c).unwrap_or(0) };
                    region_blocks.push(audio_region_2629(
                        &AudioRegionArgs {
                            name: &rname,
                            frames: clip.length_samples,
                            start: clip.file_offset,
                            sync_offset: clip.sync_offset,
                            file_index: fi,
                            channel: ch_in_file,
                            gain_index: gain_idx,
                        },
                        ids,
                    ));

                    if let Some(fi_fade) = &clip.fade_in {
                        let fidx = u16::try_from(fade_blocks.len()).unwrap_or(0);
                        fade_blocks.push(fade_block(fi_fade));
                        let seq = entry_seq;
                        entry_seq += 1;
                        item_vec.push(RunClipItem {
                            ev_pos: clip.start_pos,
                            rank: 0,
                            seq,
                            is_fade: true,
                            idx: fidx,
                            muted: false,
                            lp: None,
                        });
                    }
                    let seq = entry_seq;
                    entry_seq += 1;
                    item_vec.push(RunClipItem {
                        ev_pos: anchor_pos,
                        rank: 1,
                        seq,
                        is_fade: false,
                        idx: reg_idx,
                        muted: clip.muted,
                        lp: clip.clip_loop.clone(),
                    });
                    if let Some(fo_fade) = &clip.fade_out {
                        let fidx = u16::try_from(fade_blocks.len()).unwrap_or(0);
                        fade_blocks.push(fade_block(fo_fade));
                        let seq = entry_seq;
                        entry_seq += 1;
                        item_vec.push(RunClipItem {
                            ev_pos: end_pos,
                            rank: 2,
                            seq,
                            is_fade: true,
                            idx: fidx,
                            muted: false,
                            lp: None,
                        });
                    }
                }
            }

            if let Some(gid) = grp_opt {
                let pt_gid = next_pt_grp_id;
                next_pt_grp_id += 1;
                let base_name = spec
                    .clip_group_names
                    .get(&gid)
                    .cloned()
                    .unwrap_or_else(|| format!("Group_{gid}"));
                let g_len = g_end.saturating_sub(g_start).max(1);
                let tb_val: u16 = if g_ticks { 2 } else { 1 };
                let gn_b = base_name.as_bytes();
                let mut d23 = Vec::with_capacity(13 + gn_b.len());
                d23.extend_from_slice(&pt_gid.to_le_bytes());
                d23.extend_from_slice(&u32::try_from(gn_b.len()).unwrap_or(0).to_le_bytes());
                d23.extend_from_slice(gn_b);
                d23.extend_from_slice(&[0u8; 5]);
                grp_2423_blocks.push(encode_block(4, 0x2423, &d23));

                let mut d25 = 1u32.to_le_bytes().to_vec();
                d25.extend_from_slice(&[0u8; 5]);
                let parts = [spec.volume_name.as_str(), "ClipGroup"];
                d25.extend_from_slice(&u32::try_from(parts.len()).unwrap_or(0).to_le_bytes());
                for pt in parts {
                    d25.extend_from_slice(&lp_bytes(pt));
                }
                d25.extend_from_slice(&ids.next_id8()[..4]);
                d25.extend_from_slice(&[0u8; 6]);
                grp_2425_blocks.push(encode_block(2, 0x2425, &d25));

                for (c, mut items) in run_ch_items.into_iter().enumerate() {
                    items.sort_by_key(|x| (x.ev_pos, x.rank, x.seq));
                    let mpl_idx = u32::try_from(grp_member_1052.len()).unwrap_or(0);
                    let mut m52 = lp_bytes("?");
                    m52.extend_from_slice(&u32::try_from(items.len()).unwrap_or(0).to_le_bytes());
                    for it in items {
                        let sub_kind = if it.is_fade && it.rank == 0 { 1 } else { 3 };
                        let rel_pos = it.ev_pos.saturating_sub(g_start);
                        m52.extend_from_slice(&playlist_1050(PlaylistEntryArgs {
                            region_index: it.idx,
                            pos: rel_pos,
                            raw_pos_override: Some(OFFSET_FORM + rel_pos),
                            is_ticks: g_ticks,
                            muted: it.muted,
                            sub_kind,
                            link: -2,
                            is_group: false,
                            trailer_is_fade: it.is_fade,
                            clip_loop: it.lp.as_ref(),
                        }));
                    }
                    m52.extend_from_slice(&tb_val.to_le_bytes());
                    grp_member_1052.push(encode_block(3, 0x1052, &m52));

                    let grp_reg_idx = u16::try_from(grp_262b_blocks.len()).unwrap_or(0);
                    let ch_sfx = if tr.stereo { if c == 0 { ".L" } else { ".R" } } else { "" };
                    let rnm = if base_name.ends_with(ch_sfx) || ch_sfx.is_empty() {
                        base_name.clone()
                    } else {
                        format!("{base_name}{ch_sfx}")
                    };
                    grp_262b_blocks.push(build_clip_group_262b(
                        &ClipGroupRegionArgs {
                            name: &rnm,
                            is_ticks: g_ticks,
                            g_start,
                            g_len,
                            bpm: default_bpm,
                            mpl_idx,
                            grp_id: pt_gid,
                            ch_idx: u16::try_from(c).unwrap_or(0),
                        },
                        ids,
                    ));

                    let seq = entry_seq;
                    entry_seq += 1;
                    per_ch_entries[c].push((
                        g_start,
                        1,
                        seq,
                        playlist_1050(PlaylistEntryArgs {
                            region_index: grp_reg_idx,
                            pos: g_start,
                            raw_pos_override: None,
                            is_ticks: g_ticks,
                            muted: false,
                            sub_kind: 3,
                            link: -2,
                            is_group: true,
                            trailer_is_fade: false,
                            clip_loop: None,
                        }),
                    ));
                }
            } else {
                for (c, items) in run_ch_items.into_iter().enumerate() {
                    for it in items {
                        let sub_kind = if it.is_fade && it.rank == 0 { 1 } else { 3 };
                        per_ch_entries[c].push((
                            it.ev_pos,
                            it.rank,
                            it.seq,
                            playlist_1050(PlaylistEntryArgs {
                                region_index: it.idx,
                                pos: it.ev_pos,
                                raw_pos_override: None,
                                is_ticks: g_ticks,
                                muted: it.muted,
                                sub_kind,
                                link: -2,
                                is_group: false,
                                trailer_is_fade: it.is_fade,
                                clip_loop: it.lp.as_ref(),
                            }),
                        ));
                    }
                }
            }
        }

        let pl_tb_tail: [u8; 2] = if tr.timebase == BuildTimebase::Ticks {
            [2, 0]
        } else {
            [1, 0]
        };
        for (c, ch_ents) in per_ch_entries.iter_mut().enumerate().take(nch) {
            ch_ents.sort_by_key(|&(pos, rank, seq, _)| (pos, rank, seq));
            ch_pls.push(base_pl + u16::try_from(c).unwrap_or(0));
            let mut d1052 = lp_bytes(&tr.name);
            d1052.extend_from_slice(&u32::try_from(ch_ents.len()).unwrap_or(0).to_le_bytes());
            for (_, _, _, e) in ch_ents.iter() {
                d1052.extend_from_slice(e);
            }
            d1052.extend_from_slice(&pl_tb_tail);
            p54_entries.push(encode_block(3, 0x1052, &d1052));
        }

        let (_, pid) = track_ids[tidx];
        let mut d1014 = lp_bytes(&tr.name);
        d1014.push(u8::from(tr.stereo));
        d1014.extend_from_slice(&u32::try_from(nch).unwrap_or(1).to_le_bytes());
        for &pli in &ch_pls {
            d1014.extend_from_slice(&pli.to_le_bytes());
        }
        d1014.extend_from_slice(&0u32.to_le_bytes());
        d1014.extend_from_slice(ID_MARK);
        d1014.extend_from_slice(&pid);
        if tr.stereo {
            d1014.extend_from_slice(&[1, 0, 1, 0, 0, 0, 0]);
        } else {
            d1014.extend_from_slice(&[0u8; 7]);
        }
        for &pli in &ch_pls {
            d1014.extend_from_slice(&u32::from(pli).to_le_bytes());
        }
        d1014.push(u8::from(tr.stereo));
        d1014.extend_from_slice(&[0u8; 5]);
        p15_entries.push(encode_block(9, 0x1014, &d1014));
        audio_track_playlists.push(ch_pls);
    }

    let mut d2637 = u32::try_from(gain_lanes_bytes.len()).unwrap_or(0).to_le_bytes().to_vec();
    for gl in gain_lanes_bytes {
        d2637.extend_from_slice(&gl);
    }
    let blk_2637 = encode_block(1, 0x2637, &d2637);

    let blk_262c = if grp_262b_blocks.is_empty() {
        encode_block(1, 0x262c, &[0u8; 8])
    } else {
        let mut d2c = u32::try_from(grp_262b_blocks.len()).unwrap_or(0).to_le_bytes().to_vec();
        for gb in grp_262b_blocks {
            d2c.extend_from_slice(&gb);
        }
        d2c.extend_from_slice(&[0u8; 4]);
        encode_block(1, 0x262c, &d2c)
    };
    let (blk_2428, blk_2424, blk_2426) = if grp_member_1052.is_empty() {
        (None, None, None)
    } else {
        let mut m54 = u32::try_from(grp_member_1052.len()).unwrap_or(0).to_le_bytes().to_vec();
        for mp in grp_member_1052 {
            m54.extend_from_slice(&mp);
        }
        m54.extend_from_slice(&encode_block(2, 0x4828, &0u32.to_le_bytes()));
        let b2428 = encode_block(1, 0x2428, &encode_block(2, 0x1054, &m54));

        let mut d24 = u32::try_from(grp_2423_blocks.len()).unwrap_or(0).to_le_bytes().to_vec();
        for b23 in grp_2423_blocks {
            d24.extend_from_slice(&b23);
        }
        let b2424 = encode_block(1, 0x2424, &d24);

        let mut d26 = u32::try_from(grp_2425_blocks.len()).unwrap_or(0).to_le_bytes().to_vec();
        for b25 in grp_2425_blocks {
            d26.extend_from_slice(&b25);
        }
        let b2426 = encode_block(1, 0x2426, &d26);
        (Some(b2428), Some(b2424), Some(b2426))
    };
    let blk_2632 = encode_block(1, 0x2632, &0u32.to_le_bytes());

    let mut d262a = u32::try_from(region_blocks.len()).unwrap_or(0).to_le_bytes().to_vec();
    for rb in region_blocks {
        d262a.extend_from_slice(&rb);
    }
    let blk_262a = encode_block(1, 0x262a, &d262a);

    let mut d2630 = u32::try_from(fade_blocks.len()).unwrap_or(0).to_le_bytes().to_vec();
    for fb in fade_blocks {
        d2630.extend_from_slice(&fb);
    }
    let blk_2630 = encode_block(1, 0x2630, &d2630);
    let blk_262e = encode_block(1, 0x262e, &0u32.to_le_bytes());

    let mut d1054 = u32::try_from(p54_entries.len()).unwrap_or(0).to_le_bytes().to_vec();
    for p52 in p54_entries {
        d1054.extend_from_slice(&p52);
    }
    d1054.extend_from_slice(&encode_block(2, 0x4828, &0u32.to_le_bytes()));
    let blk_1054 = encode_block(2, 0x1054, &d1054);

    let mut d1015 = u32::try_from(p15_entries.len()).unwrap_or(0).to_le_bytes().to_vec();
    for p14 in p15_entries {
        d1015.extend_from_slice(&p14);
    }
    d1015.extend_from_slice(&encode_block(2, 0x4829, &0u32.to_le_bytes()));
    let blk_1015 = encode_block(2, 0x1015, &d1015);

    // 3) MIDI chunks (0x2000), MIDI clip library (0x2634), and MIDI routes (0x1058)
    let mut midi_chunks = Vec::new();
    let mut midi_2633s = Vec::new();
    let mut midi_1057s = Vec::new();

    for (tidx, tr) in spec.tracks.iter().enumerate() {
        if !matches!(tr.kind, BuildTrackKind::Midi | BuildTrackKind::Instrument) {
            continue;
        }
        let mut entries = Vec::new();
        for mclip in &tr.midi_clips {
            track_has_clips[tidx] = true;
            let cidx = u32::try_from(midi_chunks.len()).unwrap_or(0);
            let ridx = u16::try_from(midi_2633s.len()).unwrap_or(0);
            let cid8 = ids.next_id8();
            midi_chunks.push(build_midi_chunk(Some(mclip), cid8, true));
            midi_2633s.push(build_midi_clip_2633(&mclip.name, mclip.length_ticks, cidx, ids));
            entries.push((
                ridx,
                mclip.start_pos,
                mclip.muted,
                mclip.pos_in_ticks,
                mclip.clip_loop.as_ref(),
            ));
        }
        let (_, pid) = track_ids[tidx];
        midi_1057s.push(midi_route_1057(
            &tr.name,
            &entries,
            pid,
            tr.timebase == BuildTimebase::Ticks,
        ));
    }

    let mut d2000 = u32::try_from(midi_chunks.len()).unwrap_or(0).to_le_bytes().to_vec();
    for mc in midi_chunks {
        d2000.extend_from_slice(&mc);
    }
    let blk_2000 = encode_block(1, 0x2000, &d2000);

    let mut d2634 = u32::try_from(midi_2633s.len()).unwrap_or(0).to_le_bytes().to_vec();
    for r in midi_2633s {
        d2634.extend_from_slice(&r);
    }
    let blk_2634 = encode_block(1, 0x2634, &d2634);

    let mut d1058 = u32::try_from(midi_1057s.len()).unwrap_or(0).to_le_bytes().to_vec();
    for rt in midi_1057s {
        d1058.extend_from_slice(&rt);
    }
    let blk_1058 = encode_block(1, 0x1058, &d1058);

    BuiltMedia {
        blk_0f3d,
        blk_1004,
        blk_2637,
        blk_262c,
        blk_2632,
        blk_262a,
        blk_2630,
        blk_262e,
        blk_2000,
        blk_2634,
        blk_1054,
        blk_1015,
        blk_1058,
        blk_2428,
        blk_2424,
        blk_2426,
        audio_track_playlists,
        track_has_clips,
    }
}
