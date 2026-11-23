// Version: 0.7.0 (beta) | Date: 2026-11-23
//! Clean-room `.ptx` session builder mirroring `tools/ptx_edit.py`.

pub mod ids;
pub mod media;
pub mod plugins_data;
pub mod spec;
pub mod tracks;

use std::collections::BTreeMap;

use crate::error::PtxError;
use crate::primitives::{lp_bytes, OFFSET_FORM};
use crate::scramble::{scramble, DEFAULT_HEADER};
use crate::tree::{build_directory_0002, encode_block, parse_blocks};

use ids::IdGen;
use media::build_media_blocks;
use spec::{BuildEditState, PtxBuildSpec};
use tracks::{build_track_blocks, IoPathRef};

const ID_MARK: &[u8] = &[0x2a, 0x00, 0x00, 0x00];

fn build_1028(spec: &PtxBuildSpec) -> Result<Vec<u8>, PtxError> {
    let valid_sr = matches!(
        spec.sample_rate,
        44_100 | 48_000 | 88_200 | 96_000 | 176_400 | 192_000
    );
    let valid_bd = matches!(spec.bit_depth, 16 | 24 | 32);
    if !valid_sr || !valid_bd {
        return Err(PtxError::Unsupported(format!(
            "unsupported sample_rate={} / bit_depth={}",
            spec.sample_rate, spec.bit_depth
        )));
    }
    let fl = u8::from(spec.is_float || spec.bit_depth == 32);
    let stored_bd = if spec.bit_depth == 32 || spec.is_float {
        24
    } else {
        spec.bit_depth
    };
    let full_bd = u32::from(if spec.is_float { 32 } else { spec.bit_depth });
    let mut d = Vec::with_capacity(32);
    d.push(if spec.is_aiff { 4 } else { 3 });
    d.push(stored_bd);
    d.extend_from_slice(&spec.sample_rate.to_le_bytes());
    d.extend_from_slice(&[0u8; 5]);
    d.push(2);
    d.extend_from_slice(&0u32.to_le_bytes());
    d.extend_from_slice(&[0u8; 5]);
    d.extend_from_slice(&[2, 2, fl, fl]);
    d.extend_from_slice(&full_bd.to_le_bytes());
    d.extend_from_slice(&[0, 1]);
    Ok(encode_block(10, 0x1028, &d))
}

fn build_0003(creator_id: [u8; 8]) -> Vec<u8> {
    let mut d = Vec::new();
    d.push(6); // Pro Tools Intro
    d.extend_from_slice(&lp_bytes("Pro Tools Intro"));
    for v in [3u32, 26, 11, 0] {
        d.extend_from_slice(&v.to_le_bytes());
    }
    d.extend_from_slice(&lp_bytes("2026.11.0"));
    d.push(1);
    d.extend_from_slice(&lp_bytes("Release"));
    d.push(0);
    d.extend_from_slice(&lp_bytes("Pro Tools Session File"));
    d.extend_from_slice(&[6, 0]);
    d.extend_from_slice(&lp_bytes("MacOS"));
    d.extend_from_slice(&[0u8; 4]);
    d.extend_from_slice(&5u32.to_le_bytes());
    d.push(0);
    d.extend_from_slice(ID_MARK);
    d.extend_from_slice(&creator_id);
    encode_block(4, 0x0003, &d)
}

fn build_2603(spec: &PtxBuildSpec, ids: &mut IdGen) -> (Vec<u8>, BTreeMap<String, IoPathRef>) {
    let main_id = ids.next_id8();
    let sub0_id = ids.next_id8();
    let sub1_id = ids.next_id8();
    let mut map = BTreeMap::new();
    let mut paths_blocks = Vec::new();

    let path_tail = |st: u8| -> Vec<u8> {
        let mut t = vec![0xff, 0x00, st, 0, 0, 0, 0, 0, 0, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff, 0, 0, 0, 0, st];
        t.extend_from_slice(&[0u8; 6]);
        t.extend_from_slice(&[0xfe, 0xff]);
        t
    };

    // Main stereo output + 2 mono sub-paths
    let mut d_main = vec![0x02, 0x01];
    d_main.extend_from_slice(&lp_bytes(&spec.main_out_name));
    d_main.extend_from_slice(&2u32.to_le_bytes());
    d_main.extend_from_slice(&1u16.to_le_bytes());
    d_main.extend_from_slice(&2u16.to_le_bytes());
    d_main.extend_from_slice(&[0xff, 0xff, 0x01, 0x01, 0, 0, 0, 0]);
    d_main.extend_from_slice(ID_MARK);
    d_main.extend_from_slice(&main_id);
    d_main.extend_from_slice(&[0u8; 16]);
    d_main.extend_from_slice(&encode_block(1, 0x2601, &0u32.to_le_bytes()));
    d_main.extend_from_slice(&path_tail(1));
    paths_blocks.push(encode_block(14, 0x2602, &d_main));
    map.insert(
        spec.main_out_name.clone(),
        IoPathRef {
            path_num: 2,
            id: main_id,
            name: spec.main_out_name.clone(),
            stereo: true,
        },
    );

    let base_out = spec
        .main_out_name
        .rsplit_once(' ')
        .map_or(spec.main_out_name.as_str(), |(l, _)| l);
    for (i, sid) in [sub0_id, sub1_id].into_iter().enumerate() {
        let sub_name = format!("{base_out} {}", i + 1);
        let mut d_sub = vec![0x02, 0x00];
        d_sub.extend_from_slice(&lp_bytes(&sub_name));
        d_sub.extend_from_slice(&1u32.to_le_bytes());
        d_sub.extend_from_slice(&1u16.to_le_bytes());
        d_sub.extend_from_slice(&2u16.to_le_bytes());
        d_sub.extend_from_slice(&[0x01, 0x00, 0, 0, 0, 0]);
        d_sub.extend_from_slice(ID_MARK);
        d_sub.extend_from_slice(&sid);
        d_sub.extend_from_slice(&[0u8; 4]);
        d_sub.extend_from_slice(ID_MARK);
        d_sub.extend_from_slice(&main_id);
        d_sub.extend_from_slice(&encode_block(1, 0x2601, &0u32.to_le_bytes()));
        d_sub.extend_from_slice(&path_tail(0));
        paths_blocks.push(encode_block(14, 0x2602, &d_sub));
    }

    let mut ch_cursor = 4u16;
    for bus in &spec.busses {
        let bid = ids.next_id8();
        let st = u8::from(bus.stereo);
        let nch = if bus.stereo { 2u32 } else { 1u32 };
        let pidx = u16::try_from(paths_blocks.len() + 2).unwrap_or(2);
        let mut d_b = vec![0x02, st];
        d_b.extend_from_slice(&lp_bytes(&bus.name));
        d_b.extend_from_slice(&nch.to_le_bytes());
        d_b.extend_from_slice(&ch_cursor.to_le_bytes());
        if bus.stereo {
            d_b.extend_from_slice(&(ch_cursor + 1).to_le_bytes());
        }
        d_b.extend_from_slice(&[0xff, 0xff, 0x01, 0x00, 0, 0, 0, 0]);
        d_b.extend_from_slice(ID_MARK);
        d_b.extend_from_slice(&bid);
        d_b.extend_from_slice(&[0u8; 16]);
        d_b.extend_from_slice(&encode_block(1, 0x2601, &0u32.to_le_bytes()));
        d_b.extend_from_slice(&path_tail(st));
        paths_blocks.push(encode_block(14, 0x2602, &d_b));
        map.insert(
            bus.name.clone(),
            IoPathRef {
                path_num: pidx,
                id: bid,
                name: bus.name.clone(),
                stereo: bus.stereo,
            },
        );
        ch_cursor = ch_cursor.saturating_add(if bus.stereo { 2 } else { 1 });
    }

    let mut d2603 = u32::try_from(paths_blocks.len()).unwrap_or(0).to_le_bytes().to_vec();
    for pb in paths_blocks {
        d2603.extend_from_slice(&pb);
    }
    (encode_block(2, 0x2603, &d2603), map)
}

fn map_2619(name: &[u8], ident: [u8; 8]) -> Vec<u8> {
    let mut d = u32::try_from(name.len()).unwrap_or(0).to_le_bytes().to_vec();
    d.extend_from_slice(name);
    d.extend_from_slice(&[0, 0]);
    d.extend_from_slice(&1u32.to_le_bytes());
    d.push(0);
    d.extend_from_slice(ID_MARK);
    d.extend_from_slice(&ident);
    d.extend_from_slice(&[0u8; 4]);
    d.extend_from_slice(ID_MARK);
    d.extend_from_slice(&ident);
    d.extend_from_slice(&[0u8; 8]);
    d.push(1);
    d.extend_from_slice(&[0u8; 36]);
    d.extend_from_slice(&encode_block(1, 0x4301, &[0u8; 32]));
    d.extend_from_slice(&[0u8; 4]);
    d.extend_from_slice(ID_MARK);
    d.extend_from_slice(&ident);
    d.extend_from_slice(&[0, 0]);
    encode_block(9, 0x2619, &d)
}

fn build_map_blocks(spec: &PtxBuildSpec, ids: &mut IdGen) -> Vec<u8> {
    let tempo_pts = if spec.tempo.is_empty() {
        vec![crate::encode::spec::BuildTempoPoint { ticks: 0, bpm: 120.0 }]
    } else {
        spec.tempo.clone()
    };
    let mut recs = Vec::new();
    for (k, pt) in tempo_pts.iter().enumerate() {
        let f = u8::from(k == 0);
        recs.extend_from_slice(b"Const\x01\x00");
        recs.extend_from_slice(&46u32.to_le_bytes());
        recs.extend_from_slice(b"TMS\x01\x00");
        recs.extend_from_slice(&20u32.to_le_bytes());
        recs.push(0);
        recs.extend_from_slice(&u32::from(f).to_le_bytes());
        recs.extend_from_slice(&[0u8; 5]);
        recs.extend_from_slice(&(OFFSET_FORM + pt.ticks).to_le_bytes());
        recs.push(0);
        recs.push(f);
        recs.extend_from_slice(&pt.bpm.to_le_bytes());
        recs.extend_from_slice(&crate::primitives::TPQ_U64.to_le_bytes()[..4]);
        recs.extend_from_slice(&[0u8; 9]);
    }
    let mut t_pay = b"Tempo\x02\x00".to_vec();
    t_pay.extend_from_slice(&u32::try_from(4 + 61 * tempo_pts.len()).unwrap_or(4).to_le_bytes());
    t_pay.extend_from_slice(&u32::try_from(tempo_pts.len()).unwrap_or(1).to_le_bytes());
    t_pay.extend_from_slice(&0u32.to_le_bytes());
    t_pay.extend_from_slice(&recs);
    t_pay.extend_from_slice(&[0u8; 5]);
    t_pay.extend_from_slice(&f64::from(spec.sample_rate).to_le_bytes());

    let meter_pts = if spec.meter.is_empty() {
        vec![crate::encode::spec::BuildMeterPoint {
            ticks: 0,
            bar: 1,
            numerator: 4,
            denominator: 4,
        }]
    } else {
        spec.meter.clone()
    };
    let mut mrecs = Vec::new();
    let mut mtail = Vec::new();
    for mp in &meter_pts {
        mrecs.extend_from_slice(&(OFFSET_FORM + mp.ticks).to_le_bytes());
        mrecs.extend_from_slice(&mp.bar.to_le_bytes());
        mrecs.extend_from_slice(&mp.numerator.to_le_bytes());
        mrecs.extend_from_slice(&mp.denominator.to_le_bytes());
        mrecs.extend_from_slice(&1u16.to_le_bytes());
        mrecs.extend_from_slice(&3u16.to_le_bytes());
        mrecs.extend_from_slice(&0u32.to_le_bytes());
        mrecs.extend_from_slice(&2u32.to_le_bytes());
        mrecs.extend_from_slice(&3u32.to_le_bytes());

        mtail.extend_from_slice(&mp.bar.to_le_bytes());
        mtail.extend_from_slice(&1u32.to_le_bytes());
        mtail.extend_from_slice(&0u64.to_le_bytes());
    }
    let mut m_pay = b"Meter\x02\x00".to_vec();
    m_pay.extend_from_slice(&u32::try_from(12 + 52 * meter_pts.len()).unwrap_or(12).to_le_bytes());
    m_pay.extend_from_slice(&u32::try_from(meter_pts.len()).unwrap_or(1).to_le_bytes());
    m_pay.extend_from_slice(&mrecs);
    m_pay.extend_from_slice(&mtail);
    m_pay.extend_from_slice(&OFFSET_FORM.to_le_bytes());

    let tid = ids.next_id8();
    let mid = ids.next_id8();
    let b2028 = encode_block(3, 0x2028, &t_pay);
    let b2029 = encode_block(1, 0x2029, &m_pay);

    let mut d2718 = map_2619(b"Tempo", tid);
    d2718.extend_from_slice(&b2028);
    d2718.extend_from_slice(&120.0f64.to_le_bytes());
    d2718.extend_from_slice(&[0x01, 0x05, 0x00]);
    let b2718 = encode_block(2, 0x2718, &d2718);

    let mut d2719 = map_2619(b"Meter", mid);
    d2719.extend_from_slice(&b2029);
    let b2719 = encode_block(1, 0x2719, &d2719);

    let mut out = b2718;
    out.extend_from_slice(&b2028);
    out.extend_from_slice(&b2719);
    out.extend_from_slice(&b2029);
    out
}

fn build_keysig_blocks(spec: &PtxBuildSpec, ids: &mut IdGen) -> Vec<u8> {
    if spec.key_signatures.is_empty() {
        return Vec::new();
    }
    let mut d33 = u32::try_from(spec.key_signatures.len()).unwrap_or(0).to_le_bytes().to_vec();
    for ks in &spec.key_signatures {
        let mut d32 = Vec::with_capacity(11);
        d32.extend_from_slice(&(OFFSET_FORM + ks.ticks).to_le_bytes()[..7]);
        d32.push(0);
        d32.push(u8::from(ks.major));
        d32.push(u8::from(ks.sharps >= 0));
        d32.push(ks.sharps.unsigned_abs());
        d33.extend_from_slice(&encode_block(1, 0x2432, &d32));
    }
    let b33 = encode_block(1, 0x2433, &d33);
    let kid = ids.next_id8();
    let mut d7b = map_2619(b"Key Signature", kid);
    d7b.extend_from_slice(&b33);
    let b7b = encode_block(1, 0x271b, &d7b);
    let mut out = b7b;
    out.extend_from_slice(&b33);
    out
}

fn mk_pos_bytes(v: u64, is_ticks: bool) -> [u8; 8] {
    let val = if is_ticks { OFFSET_FORM + v } else { v };
    let mut out = [0u8; 8];
    out[..5].copy_from_slice(&val.to_le_bytes()[..5]);
    out[7] = if is_ticks { 0x40 } else { 0x00 };
    out
}

fn build_204d_block(spec: &PtxBuildSpec) -> Vec<u8> {
    if spec.tc_rate_code.is_none() && spec.tc_start.is_none() {
        return Vec::new();
    }
    let rc = spec.tc_rate_code.unwrap_or(1);
    let rc_base = match rc {
        15 => 9,
        16 => 1,
        10 | 17 => 2,
        11 | 18 => 3,
        12 | 19 => 5,
        13 | 20 => 7,
        14 | 21 => 8,
        other => other,
    };
    let is_drop = matches!(rc, 5 | 8 | 12 | 14 | 19 | 21);
    let default_tc = if is_drop {
        "00:00:00;00".to_owned()
    } else {
        "00:00:00:00".to_owned()
    };
    let tc_str = spec.tc_start.as_deref().unwrap_or(&default_tc);
    let mut sf: u32 = 0;
    let parts: Vec<u32> = tc_str
        .replace(';', ":")
        .split(':')
        .filter_map(|p| p.parse::<u32>().ok())
        .collect();
    if parts.len() == 4 {
        let mut hh = parts[0];
        if hh == 24 {
            hh = 1;
        }
        let (mm, ss, ff) = (parts[1], parts[2], parts[3]);
        let fps: u32 = match rc_base {
            2 => 25,
            3 | 5 | 7 | 8 => 30,
            _ => 24,
        };
        let total = (hh * 3600 + mm * 60 + ss) * fps + ff;
        sf = if matches!(rc_base, 5 | 8) {
            let tot_min = hh * 60 + mm;
            total.saturating_sub(2 * (tot_min - tot_min / 10))
        } else {
            total
        };
    }
    let sf2 = if matches!(rc_base, 5 | 8) {
        sf.saturating_mul(4)
    } else {
        sf
    };
    let mut body = Vec::with_capacity(64);
    body.extend_from_slice(&u32::from(rc_base).to_le_bytes());
    body.extend_from_slice(&[0u8; 5]);
    body.extend_from_slice(&sf.to_le_bytes());
    body.extend_from_slice(&[0u8; 4]);
    body.extend_from_slice(&1u32.to_le_bytes());
    body.extend_from_slice(&u32::from(rc_base).to_le_bytes());
    body.extend_from_slice(&lp_bytes(tc_str));
    body.extend_from_slice(&u32::from(rc).to_le_bytes());
    body.extend_from_slice(&sf2.to_le_bytes());
    body.extend_from_slice(&u32::from(rc).to_le_bytes());
    body.extend_from_slice(&lp_bytes(tc_str));
    encode_block(5, 0x204d, &body)
}

fn build_markers_block(spec: &PtxBuildSpec, ids: &mut IdGen) -> Vec<u8> {
    if spec.markers.is_empty() {
        return Vec::new();
    }
    let nt = spec.tracks.len();
    let mk_view: [u8; 40] = [
        0xf0, 0xbf, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff,
        0xbf, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xbf, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x40, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x40,
    ];
    let mk_col: [u8; 7] = [0x01, 0x00, 0x3e, 0x00, 0x45, 0x00, 0xff];

    let mut d30 = u32::try_from(spec.markers.len()).unwrap_or(0).to_le_bytes().to_vec();
    for m in &spec.markers {
        let mut b = Vec::new();
        b.extend_from_slice(&m.number.to_le_bytes());
        b.push(if m.is_ticks { 0x01 } else { 0x03 });
        b.push(if m.is_selection { 2 } else { 1 });
        b.extend_from_slice(&0u16.to_le_bytes());
        b.extend_from_slice(&lp_bytes(&m.name));
        b.extend_from_slice(&mk_pos_bytes(m.start, m.is_ticks));
        b.extend_from_slice(&mk_pos_bytes(m.end, m.is_ticks));
        b.extend_from_slice(&[0u8; 6]);
        b.extend_from_slice(&mk_view);
        b.extend_from_slice(&[0xffu8; 4]);
        b.extend_from_slice(&u32::try_from(nt).unwrap_or(0).to_le_bytes());
        b.extend(std::iter::repeat_n(0u8, nt));
        b.extend_from_slice(&1u32.to_le_bytes());
        b.push(0);
        b.extend_from_slice(&lp_bytes(&m.comment));
        b.extend_from_slice(&[0u8; 8]);
        b.extend_from_slice(&[0xffu8; 4]);
        b.extend_from_slice(&[0u8; 12]);
        b.extend_from_slice(&[0xffu8; 4]);
        b.extend_from_slice(&[0u8; 12]);
        b.extend_from_slice(&23u16.to_le_bytes());
        b.extend_from_slice(&u32::try_from(nt).unwrap_or(0).to_le_bytes());
        for _ in 0..nt {
            b.extend_from_slice(&encode_block(3, 0x2506, &[0xff, 0xff, 0xff, 0xff, 0, 0, 0, 0]));
        }
        b.extend_from_slice(&[0u8; 4]);
        b.extend_from_slice(&lp_bytes(&m.comment));
        b.extend_from_slice(&[0u8; 13]);
        b.extend_from_slice(&[0xff, 0xff]);
        b.extend_from_slice(&ids.next_uuid16());
        b.extend_from_slice(&[0xffu8; 12]);
        b.extend_from_slice(&encode_block(1, 0x4826, &mk_col));
        b.extend_from_slice(&encode_block(1, 0x4826, &[0u8; 7]));
        b.extend_from_slice(&encode_block(1, 0x4827, &[0u8; 28]));
        b.extend_from_slice(&1u64.to_le_bytes());
        d30.extend_from_slice(&encode_block(0x12, 0x2077, &b));
    }
    d30.extend_from_slice(&[0u8; 8]);
    encode_block(5, 0x2030, &d30)
}

fn build_groups_block(spec: &PtxBuildSpec) -> Vec<u8> {
    if spec.groups.is_empty() {
        return Vec::new();
    }
    let nt = spec.tracks.len();
    let mut groups_to_write: Vec<(String, u8, u32, bool, Vec<u16>)> = Vec::new();
    let has_all = spec.groups.iter().any(|g| g.name == "<ALL>");
    if !has_all {
        groups_to_write.push((
            "<ALL>".to_owned(),
            2,
            u32::MAX,
            false,
            (0..u16::try_from(nt).unwrap_or(0)).collect(),
        ));
    }
    let mut uid = 0u32;
    for g in &spec.groups {
        let is_all = g.name == "<ALL>";
        let gid = if is_all {
            u32::MAX
        } else {
            uid += 1;
            uid
        };
        let mut mems: Vec<u16> = g
            .member_track_names
            .iter()
            .filter_map(|nm| {
                spec.tracks
                    .iter()
                    .position(|t| &t.name == nm)
                    .and_then(|i| u16::try_from(i).ok())
            })
            .collect();
        mems.sort_unstable();
        mems.dedup();
        groups_to_write.push((g.name.clone(), g.group_type, gid, g.enabled, mems));
    }

    let mut blks = Vec::new();
    for (nm, ty, gid, en, mems) in &groups_to_write {
        let is_all = nm == "<ALL>";
        let attr: u32 = if is_all { 0x0001_8010 } else { 1 };
        let e_b = u8::from(!is_all && *en);
        let mut d = lp_bytes(nm);
        d.push(*ty);
        d.extend_from_slice(&gid.to_le_bytes());
        d.extend_from_slice(&[e_b, e_b]);
        d.extend_from_slice(&u32::try_from(mems.len()).unwrap_or(0).to_le_bytes());
        for m in mems {
            d.extend_from_slice(&m.to_le_bytes());
        }
        d.extend_from_slice(&[0xfe, 0xff]);
        d.extend_from_slice(&attr.to_le_bytes());
        d.extend_from_slice(&0u32.to_le_bytes());
        d.extend_from_slice(&[0xff, 0xff]);
        let mut e8e = [0u8; 62];
        if is_all {
            e8e[0] = 1;
            e8e[1] = 1;
            e8e[8] = 1;
        } else {
            e8e[4] = 1;
        }
        d.extend_from_slice(&encode_block(5, 0x258e, &e8e));
        blks.push(encode_block(5, 0x202a, &d));
    }

    let cnt = u32::try_from(blks.len()).unwrap_or(0).to_le_bytes();
    let mut d2b = cnt.to_vec();
    for b in &blks {
        d2b.extend_from_slice(b);
    }
    d2b.extend_from_slice(&cnt);
    for b in &blks {
        d2b.extend_from_slice(b);
    }
    d2b.extend_from_slice(&[0, 0]);
    encode_block(4, 0x202b, &d2b)
}

fn build_2023_pull(pull_code: u16) -> Vec<u8> {
    let mut d = vec![0u8; 111];
    d[0..3].copy_from_slice(&[0x01, 0x50, 0x1e]);
    d[11] = 0x40;
    d[13..18].copy_from_slice(&[0x01, 0x03, 0x00, 0x01, 0x01]);
    d[26] = 0x40;
    d[34..36].copy_from_slice(&[0x40, 0x01]);
    d[44..50].copy_from_slice(&[0x01, 0x05, 0x00, 0x00, 0x01, 0x01]);
    d[53] = 0x01;
    d[55..57].copy_from_slice(&[0xa6, 0x0e]);
    d[62..64].copy_from_slice(&pull_code.to_le_bytes());
    d[71] = 0x01;
    d[87] = 0x04;
    d[104..107].copy_from_slice(&[1, 1, 1]);
    d[109] = 0x01;
    d.extend_from_slice(&encode_block(1, 0x2434, &[4, 0, 0, 0, 0, 0, 0, 0x3c, 0]));
    d.push(0x01);
    let mut d35 = Vec::with_capacity(75);
    d35.extend_from_slice(&lp_bytes("Title"));
    d35.extend_from_slice(&lp_bytes("Composer"));
    d35.extend_from_slice(&[0u8; 8]);
    d35.extend_from_slice(&1u32.to_le_bytes());
    d35.extend_from_slice(&6.0f32.to_le_bytes());
    for _ in 0..4 {
        d35.extend_from_slice(&15.0f32.to_le_bytes());
    }
    d35.extend_from_slice(&[1, 1, 1, 1]);
    d35.extend_from_slice(&5.5f32.to_le_bytes());
    d35.extend_from_slice(&9.25f32.to_le_bytes());
    d35.extend_from_slice(&[0u8; 8]);
    d35.extend_from_slice(&[1, 1]);
    d.extend_from_slice(&encode_block(4, 0x2435, &d35));
    d.extend_from_slice(&[0xfa, 0x00]);
    for _ in 0..3 {
        d.extend_from_slice(&encode_block(1, 0x2005, &[0u8; 8]));
    }
    d.extend_from_slice(&[0x00, 0x01, 0x01, 0x01]);
    encode_block(23, 0x2023, &d)
}

fn build_2024_edit_mode(edit_mode: u16) -> Vec<u8> {
    let mut f3e = 5u32.to_le_bytes().to_vec();
    for (idx, s) in [
        (0u8, "    0| 0| 060"),
        (1, "   0:00.001"),
        (2, "00:00:00:00.01"),
        (3, "     0+00.01"),
        (4, "          1"),
    ] {
        f3e.push(idx);
        f3e.extend_from_slice(&lp_bytes(s));
    }
    let mut d = u32::from(edit_mode).to_le_bytes().to_vec();
    d.extend_from_slice(&[1, 0]);
    d.extend_from_slice(&encode_block(1, 0x0f3e, &f3e));
    d.push(0);
    encode_block(6, 0x2024, &d)
}

fn build_2056_edit_tool(es: &BuildEditState) -> Vec<u8> {
    let mut d = vec![0u8; 41];
    d[0] = u8::from(es.smart_tool);
    d[9..13].copy_from_slice(&4u32.to_le_bytes());
    d[13..17].copy_from_slice(&u32::from(es.edit_tool).to_le_bytes());
    d[17..21].copy_from_slice(&u32::from(es.edit_mode).to_le_bytes());
    d[31..35].copy_from_slice(&2u32.to_le_bytes());
    d[35..39].copy_from_slice(&1u32.to_le_bytes());
    d[39..41].copy_from_slice(&0x0050u16.to_le_bytes());
    encode_block(6, 0x2056, &d)
}

fn build_2058_transport(es: &BuildEditState) -> Vec<u8> {
    let mut d = vec![0u8; 289];
    d[0] = 1;
    d[1] = 1;
    d[3] = 1;
    d[4] = 1;
    d[6] = 1;
    d[12] = 60;
    d[14] = 0xee;
    d[15] = 0xff;
    d[20] = 2;
    d[25] = 1;
    d[26] = u8::from(es.loop_playback);
    d[28] = 1;
    d[29] = 1;
    d[30] = 1;
    d[32] = es.record_mode;
    d[33] = 1;
    d[35] = 1;
    d[36] = 10;
    d[38] = 5;
    d[48] = es.record_mode;
    d[58] = 32;
    d[59] = 3;
    d[62] = 1;
    d[64] = es.record_mode;
    encode_block(57, 0x2058, &d)
}

/// Encode a `PtxBuildSpec` clean-room into scrambled `.ptx` bytes.
///
/// # Errors
/// Returns `PtxError` on invalid audio parameters or container limits.
pub fn encode_ptx(spec: &PtxBuildSpec) -> Result<Vec<u8>, PtxError> {
    let mut ids = IdGen::new(0x1122_3344);
    let creator_id = ids.next_id8();
    let track_ids: Vec<([u8; 8], [u8; 8])> =
        (0..spec.tracks.len()).map(|_| ids.next_track_pair()).collect();

    let (blk_2603, io_map) = build_2603(spec, &mut ids);
    let built_media = build_media_blocks(spec, &track_ids, &mut ids);
    let built_tracks = build_track_blocks(
        spec,
        &track_ids,
        &built_media.track_has_clips,
        &io_map,
        &mut ids,
    );
    let blk_1028 = build_1028(spec)?;
    let maps = build_map_blocks(spec, &mut ids);
    let keysigs = build_keysig_blocks(spec, &mut ids);
    let b204d = build_204d_block(spec);
    let groups_blk = build_groups_block(spec);
    let markers_blk = build_markers_block(spec, &mut ids);
    let blk_0003 = build_0003(creator_id);

    let mut body = Vec::new();
    body.extend_from_slice(&built_tracks.blk_2519);
    body.extend_from_slice(&blk_1028);
    body.extend_from_slice(&built_media.blk_0f3d);
    body.extend_from_slice(&built_media.blk_1004);
    if let Some(es) = &spec.edit_state {
        body.extend_from_slice(&build_2058_transport(es));
        body.extend_from_slice(&build_2056_edit_tool(es));
        body.extend_from_slice(&build_2024_edit_mode(es.edit_mode));
    }
    body.extend_from_slice(&built_media.blk_2637);
    body.extend_from_slice(&built_media.blk_262c);
    body.extend_from_slice(&built_media.blk_2632);
    body.extend_from_slice(&built_media.blk_262a);
    body.extend_from_slice(&built_media.blk_2630);
    body.extend_from_slice(&built_media.blk_262e);
    if let Some(b1018) = &built_tracks.blk_1018 {
        body.extend_from_slice(b1018);
    }
    body.extend_from_slice(&blk_2603);
    body.extend_from_slice(&built_media.blk_2000);
    if let Some(pull) = spec.pull_code {
        body.extend_from_slice(&build_2023_pull(pull));
    }
    body.extend_from_slice(&b204d);
    body.extend_from_slice(&built_media.blk_2634);
    body.extend_from_slice(&maps);
    body.extend_from_slice(&keysigs);
    body.extend_from_slice(&built_media.blk_1054);
    body.extend_from_slice(&built_media.blk_1015);
    body.extend_from_slice(&built_media.blk_1058);
    body.extend_from_slice(&built_tracks.blk_210c);
    body.extend_from_slice(&built_tracks.blk_2107);
    body.extend_from_slice(&built_tracks.blk_2624);
    body.extend_from_slice(&groups_blk);
    if let Some(b) = &built_media.blk_2428 {
        body.extend_from_slice(b);
    }
    if let Some(b) = &built_media.blk_2424 {
        body.extend_from_slice(b);
    }
    if let Some(b) = &built_media.blk_2426 {
        body.extend_from_slice(b);
    }
    body.extend_from_slice(&markers_blk);
    body.extend_from_slice(&blk_0003);

    // Header (20B) + root index block (0x14..0x1F = 11B: `5a 01 00 04 00 00 00 <u32 dpos>`)
    let mut header = DEFAULT_HEADER;
    header[0x12] = 5;
    header[0x13] = spec.xor_seed;
    let dpos = header.len() + 11 + body.len();

    let mut plain = Vec::with_capacity(dpos + 16);
    plain.extend_from_slice(&header);
    plain.extend_from_slice(&[0x5a, 0x01, 0x00, 0x04, 0x00, 0x00, 0x00]);
    plain.extend_from_slice(&u32::try_from(dpos).unwrap_or(0).to_le_bytes());
    plain.extend_from_slice(&body);
    plain.extend_from_slice(&encode_block(2, 0x0002, &[]));

    let tree = parse_blocks(&plain)?;
    let dir_payload = build_directory_0002(&tree);
    plain.truncate(dpos);
    plain.extend_from_slice(&encode_block(2, 0x0002, &dir_payload));

    scramble(&plain)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::decode::decode_bytes;
    use crate::encode::spec::*;

    #[test]
    fn roundtrip_full_session_clean_room() -> Result<(), PtxError> {
        let mut params_eq1 = BTreeMap::new();
        params_eq1.insert("d_gain".to_owned(), BuildParamVal::Float(3.5));

        let mut params_trim = BTreeMap::new();
        params_trim.insert("gain_db".to_owned(), BuildParamVal::Float(-3.0));
        params_trim.insert("phase_invert".to_owned(), BuildParamVal::Bool(true));

        let mut spec = PtxBuildSpec {
            sample_rate: 48_000,
            bit_depth: 24,
            is_float: false,
            is_aiff: false,
            tempo: vec![
                BuildTempoPoint { ticks: 0, bpm: 120.0 },
                BuildTempoPoint { ticks: 3_840_000, bpm: 95.0 },
            ],
            meter: vec![
                BuildMeterPoint { ticks: 0, bar: 1, numerator: 4, denominator: 4 },
                BuildMeterPoint { ticks: 3_840_000, bar: 2, numerator: 3, denominator: 4 },
            ],
            key_signatures: vec![
                BuildKeySig { ticks: 0, major: true, sharps: 0 },
                BuildKeySig { ticks: 3_840_000, major: false, sharps: 0 },
            ],
            markers: vec![BuildMarker {
                number: 1,
                name: "Chorus".to_owned(),
                start: 3_840_000,
                end: 3_840_000,
                is_ticks: true,
                is_selection: false,
                comment: "Drop".to_owned(),
            }],
            busses: vec![BuildBus { name: "FX1".to_owned(), stereo: true }],
            audio_files: vec![BuildAudioFile {
                file_name: "tone.wav".to_owned(),
                sample_rate: 48_000,
                channels: 1,
                bit_depth: 24,
                is_float: false,
                is_aiff: false,
                frames: 48_000,
                data_offset: 44,
                filetime: 133_000_000_000_000_000,
                umid_file_id: None,
            }],
            groups: vec![BuildGroup {
                name: "VoxGrp".to_owned(),
                group_type: 2,
                enabled: true,
                member_track_names: vec!["Vox".to_owned()],
            }],
            tracks: vec![
                BuildTrack {
                    name: "FoldB".to_owned(),
                    kind: BuildTrackKind::BasicFolder,
                    ..BuildTrack::default()
                },
                BuildTrack {
                    name: "Vox".to_owned(),
                    kind: BuildTrackKind::Audio,
                    folder_name: Some("FoldB".to_owned()),
                    volume_tenths_db: -35,
                    solo: true,
                    comment: "Lead".to_owned(),
                    colour: Some(33),
                    inserts: vec![
                        BuildInsert {
                            slot_index: 0,
                            plugin_name: "EQ3 1-Band".to_owned(),
                            bypass: false,
                            active: true,
                            multi_mono: false,
                            params: params_eq1,
                            automation: vec![BuildInsertAutoLane {
                                param_name: "Gain".to_owned(),
                                param_id: "gain".to_owned(),
                                param_index: 1,
                                points: vec![(0, 0.5), (48_000, 0.75)],
                            }],
                        },
                        BuildInsert {
                            slot_index: 1,
                            plugin_name: "Trim".to_owned(),
                            bypass: true,
                            active: true,
                            multi_mono: false,
                            params: params_trim,
                            automation: Vec::new(),
                        },
                    ],
                    sends: vec![BuildSend {
                        slot_index: 0,
                        bus_name: "FX1".to_owned(),
                        level_tenths_db: -60,
                        pan: -25,
                        mute: false,
                        pre_fader: true,
                        active: true,
                        ..BuildSend::default()
                    }],
                    audio_clips: vec![BuildAudioClip {
                        name: "tone".to_owned(),
                        file_indices: vec![0],
                        file_offset: 0,
                        length_samples: 48_000,
                        start_pos: 24_000,
                        pos_in_ticks: false,
                        muted: false,
                        sync_offset: None,
                        clip_gain_points: vec![(0, -4.5)],
                        fade_in: Some(BuildFade {
                            kind: BuildFadeKind::FadeIn,
                            slope: BuildFadeSlope::EqualPower,
                            length_samples: 2400,
                            pre_roll_samples: None,
                        }),
                        fade_out: None,
                        clip_loop: Some(BuildClipLoop {
                            mode: 2,
                            bars: 0,
                            beats: 0,
                            ticks: 0,
                            count: 3,
                            trim: 0,
                            iter: 48_000,
                            is_ticks: false,
                        }),
                        group: None,
                    }],
                    ..BuildTrack::default()
                },
                BuildTrack {
                    name: "Keys".to_owned(),
                    kind: BuildTrackKind::Midi,
                    timebase: BuildTimebase::Ticks,
                    midi_clips: vec![BuildMidiClip {
                        name: "Keys-01".to_owned(),
                        start_pos: 0,
                        pos_in_ticks: true,
                        length_ticks: 3_840_000,
                        notes: vec![BuildMidiNote {
                            start_ticks: 0,
                            key: 60,
                            length_ticks: 960_000,
                            velocity: 100,
                        }],
                        controllers: vec![BuildMidiCtrl {
                            kind: 2,
                            number: 1,
                            points: vec![(0, 64), (960_000, 127)],
                        }],
                        sysex: vec![(0, vec![0x7e, 0x7f, 0x09, 0x01])],
                        muted: false,
                        clip_loop: None,
                    }],
                    ..BuildTrack::default()
                },
                BuildTrack {
                    name: "Verb".to_owned(),
                    kind: BuildTrackKind::Aux,
                    stereo: true,
                    input_bus: Some("FX1".to_owned()),
                    ..BuildTrack::default()
                },
                BuildTrack {
                    name: "Master".to_owned(),
                    kind: BuildTrackKind::Master,
                    stereo: true,
                    ..BuildTrack::default()
                },
            ],
            ..PtxBuildSpec::default()
        };
        let _ = &mut spec;

        let ptx_bytes = encode_ptx(&spec)?;
        let doc = decode_bytes("test.ptx", &ptx_bytes)?;

        assert_eq!(doc.tracks.len(), 5);
        assert_eq!(doc.tracks[1].name, "Vox");
        assert_eq!(doc.tracks[1].folder.as_deref(), Some("FoldB"));
        assert_eq!(doc.tracks[1].solo, Some(true));
        assert_eq!(doc.tracks[1].colour, Some(33));
        assert_eq!(doc.tracks[1].comment.as_deref(), Some("Lead"));
        assert_eq!(doc.tempo_used.len(), 2);
        assert_eq!(doc.meter_used.len(), 2);
        assert_eq!(doc.key_signatures.len(), 2);
        assert_eq!(doc.markers.len(), 1);
        assert_eq!(doc.markers[0].name, "Chorus");
        assert_eq!(doc.midi_lists.len(), 1);
        assert_eq!(doc.midi_lists[0].notes, vec![[0, 60, 960_000, 100]]);
        assert_eq!(doc.groups, vec!["<ALL>", "VoxGrp"]);
        assert_eq!(doc.fades.len(), 1);
        assert_eq!(doc.clip_gains.len(), 1);
        assert!((doc.clip_gains[0] - (-4.5)).abs() < 1e-3);
        assert!(doc.warnings.is_empty(), "warnings: {:?}", doc.warnings);
        Ok(())
    }

    #[test]
    fn encode_204d_timecode_and_rate_roundtrip() -> Result<(), Box<dyn std::error::Error>> {
        let spec = PtxBuildSpec {
            sample_rate: 48_000,
            bit_depth: 24,
            tc_rate_code: Some(9), // 23.976
            tc_start: Some("01:02:03:04".to_owned()),
            ..PtxBuildSpec::default()
        };
        let bytes = encode_ptx(&spec)?;
        let doc = decode_bytes("tc_test.ptx", &bytes)?;
        assert_eq!(doc.timeline.timecode_rate_code, Some(9));
        assert_eq!(doc.timeline.timecode_rate.as_deref(), Some("23.976"));
        assert_eq!(doc.timeline.session_start.as_deref(), Some("01:02:03:04"));
        Ok(())
    }

    #[test]
    fn encode_sorts_out_of_order_audio_clips_chronologically() -> Result<(), Box<dyn std::error::Error>> {
        let mut spec = PtxBuildSpec {
            sample_rate: 48_000,
            bit_depth: 24,
            audio_files: vec![BuildAudioFile {
                file_name: "take.wav".to_owned(),
                sample_rate: 48_000,
                channels: 1,
                bit_depth: 24,
                is_float: false,
                is_aiff: false,
                frames: 240_000,
                data_offset: 44,
                filetime: 133_000_000_000_000_000,
                umid_file_id: None,
            }],
            tracks: vec![BuildTrack {
                name: "Vox".to_owned(),
                kind: BuildTrackKind::Audio,
                timebase: BuildTimebase::Samples,
                audio_clips: vec![
                    BuildAudioClip {
                        name: "Late".to_owned(),
                        file_indices: vec![0],
                        file_offset: 0,
                        length_samples: 24_000,
                        start_pos: 96_000,
                        pos_in_ticks: false,
                        muted: false,
                        sync_offset: None,
                        clip_gain_points: vec![],
                        fade_in: Some(BuildFade {
                            kind: BuildFadeKind::FadeIn,
                            slope: BuildFadeSlope::EqualPower,
                            length_samples: 1_000,
                            pre_roll_samples: None,
                        }),
                        fade_out: Some(BuildFade {
                            kind: BuildFadeKind::FadeOut,
                            slope: BuildFadeSlope::EqualPower,
                            length_samples: 1_000,
                            pre_roll_samples: None,
                        }),
                        clip_loop: None,
                        group: None,
                    },
                    BuildAudioClip {
                        name: "Early".to_owned(),
                        file_indices: vec![0],
                        file_offset: 0,
                        length_samples: 24_000,
                        start_pos: 0,
                        pos_in_ticks: false,
                        muted: false,
                        sync_offset: None,
                        clip_gain_points: vec![],
                        fade_in: Some(BuildFade {
                            kind: BuildFadeKind::FadeIn,
                            slope: BuildFadeSlope::EqualPower,
                            length_samples: 1_000,
                            pre_roll_samples: None,
                        }),
                        fade_out: None,
                        clip_loop: None,
                        group: None,
                    },
                ],
                ..BuildTrack::default()
            }],
            ..PtxBuildSpec::default()
        };
        let _ = &mut spec;
        let bytes = encode_ptx(&spec)?;
        let doc = decode_bytes("sorted_clips.ptx", &bytes)?;
        let placements = doc
            .audio_placements
            .get("Vox")
            .ok_or("missing Vox placements")?;
        let positions: Vec<i64> = placements
            .iter()
            .filter_map(|p| p.get("samples").and_then(serde_json::Value::as_i64))
            .collect();
        assert_eq!(positions.len(), 5);
        assert!(
            positions.windows(2).all(|w| w[0] <= w[1]),
            "not chronological: {positions:?}"
        );
        assert_eq!(positions, vec![0, 0, 96_000, 96_000, 120_000]);
        Ok(())
    }

    #[test]
    fn encode_sync_offset_and_centered_crossfade_roundtrip() -> Result<(), Box<dyn std::error::Error>> {
        use spec::{
            BuildAudioClip, BuildAudioFile, BuildFade, BuildFadeKind, BuildFadeSlope,
            BuildTempoPoint,
        };
        let spec = PtxBuildSpec {
            sample_rate: 48_000,
            bit_depth: 24,
            tempo: vec![
                BuildTempoPoint {
                    ticks: 0,
                    bpm: 120.0,
                },
                BuildTempoPoint {
                    ticks: 1_920_000,
                    bpm: 140.0,
                },
            ],
            audio_files: vec![BuildAudioFile {
                file_name: "sig.wav".to_owned(),
                sample_rate: 48_000,
                channels: 2,
                bit_depth: 24,
                is_float: false,
                is_aiff: false,
                frames: 480_000,
                data_offset: 44,
                filetime: 0,
                umid_file_id: None,
            }],
            tracks: vec![
                BuildTrack {
                    name: "SampSync".to_owned(),
                    kind: BuildTrackKind::Audio,
                    stereo: false,
                    timebase: BuildTimebase::Samples,
                    audio_clips: vec![
                        BuildAudioClip {
                            name: "s_small".to_owned(),
                            file_indices: vec![0],
                            file_offset: 0,
                            length_samples: 48_000,
                            start_pos: 24_000,
                            pos_in_ticks: false,
                            muted: false,
                            sync_offset: Some(12_345),
                            clip_gain_points: vec![],
                            fade_in: Some(BuildFade {
                                kind: BuildFadeKind::FadeIn,
                                slope: BuildFadeSlope::EqualPower,
                                length_samples: 2_400,
                                pre_roll_samples: None,
                            }),
                            fade_out: Some(BuildFade {
                                kind: BuildFadeKind::FadeOut,
                                slope: BuildFadeSlope::EqualGain,
                                length_samples: 3_600,
                                pre_roll_samples: None,
                            }),
                            clip_loop: None,
                            group: None,
                        },
                        BuildAudioClip {
                            name: "s_xfade".to_owned(),
                            file_indices: vec![0],
                            file_offset: 0,
                            length_samples: 96_000,
                            start_pos: 120_000,
                            pos_in_ticks: false,
                            muted: false,
                            sync_offset: Some(72_000),
                            clip_gain_points: vec![],
                            fade_in: Some(BuildFade {
                                kind: BuildFadeKind::Crossfade,
                                slope: BuildFadeSlope::EqualPower,
                                length_samples: 9_600,
                                pre_roll_samples: Some(4_848),
                            }),
                            fade_out: None,
                            clip_loop: None,
                            group: None,
                        },
                    ],
                    ..BuildTrack::default()
                },
                BuildTrack {
                    name: "TickSync".to_owned(),
                    kind: BuildTrackKind::Audio,
                    stereo: true,
                    timebase: BuildTimebase::Ticks,
                    audio_clips: vec![BuildAudioClip {
                        name: "t_big".to_owned(),
                        file_indices: vec![0],
                        file_offset: 0,
                        length_samples: 144_000,
                        start_pos: 1_920_000,
                        pos_in_ticks: true,
                        muted: false,
                        sync_offset: Some(88_000),
                        clip_gain_points: vec![],
                        fade_in: Some(BuildFade {
                            kind: BuildFadeKind::FadeIn,
                            slope: BuildFadeSlope::EqualPower,
                            length_samples: 4_800,
                            pre_roll_samples: None,
                        }),
                        fade_out: Some(BuildFade {
                            kind: BuildFadeKind::FadeOut,
                            slope: BuildFadeSlope::EqualPower,
                            length_samples: 4_800,
                            pre_roll_samples: None,
                        }),
                        clip_loop: None,
                        group: None,
                    }],
                    ..BuildTrack::default()
                },
            ],
            ..PtxBuildSpec::default()
        };
        let bytes = encode_ptx(&spec)?;
        let doc = decode_bytes("sync_fade_stress.ptx", &bytes)?;

        // Check Sample track placements: fade_in at 24000, s_small at 24000+12345=36345 (clip_start_samples=24000),
        // fade_out at 72000, xfade at 120000, s_xfade at 120000+72000=192000 (clip_start_samples=120000).
        let sp = doc.audio_placements.get("SampSync").ok_or("missing SampSync")?;
        let s_smp: Vec<i64> = sp.iter().filter_map(|p| p.get("samples")?.as_i64()).collect();
        assert_eq!(s_smp, vec![24_000, 36_345, 72_000, 120_000, 192_000]);
        let s_small_pl = &sp[1];
        assert_eq!(s_small_pl.get("sync_offset").and_then(serde_json::Value::as_u64), Some(12_345));
        assert_eq!(s_small_pl.get("clip_start_samples").and_then(serde_json::Value::as_i64), Some(24_000));
        let s_xf_pl = &sp[4];
        assert_eq!(s_xf_pl.get("sync_offset").and_then(serde_json::Value::as_u64), Some(72_000));
        assert_eq!(s_xf_pl.get("clip_start_samples").and_then(serde_json::Value::as_i64), Some(120_000));

        // Centered crossfade in fades: fade_type="crossfade", pre_roll (length)=4848, total (length2)=9600
        let xf_blk = doc
            .fades
            .iter()
            .find(|f| f.fade_type.as_str() == Some("crossfade"))
            .ok_or("missing Crossfade")?;
        assert_eq!(xf_blk.length, 4_848);
        assert_eq!(xf_blk.length2, Some(9_600));

        // Tick track across 140 BPM tempo region: 1_920_000 ticks at 120 BPM = 1.0 s = 48_000 samples;
        // at 140 BPM, 88_000 samples = 88000/48000 * (140/60)*960000 = 4_106_667 ticks -> anchor=6_026_667 ticks;
        // 144_000 samples = 3.0 s -> 6_720_000 ticks -> fade_out at 8_640_000 ticks (4.0 s = 192_000 samples).
        let tp = doc.audio_placements.get("TickSync").ok_or("missing TickSync")?;
        let tc = doc.audio_channels.get("TickSync").ok_or("missing TickSync channels")?;
        let tpls: Vec<usize> = doc
            .audio_playlists
            .iter()
            .filter(|(n, _)| n == "TickSync")
            .map(|(_, p)| p.len())
            .collect();
        assert_eq!(tp.len(), 3);
        assert_eq!(tc.len(), 2);
        assert_eq!(tpls, vec![3, 3]);
        let t_clip = &tp[1];
        assert_eq!(t_clip.get("sync_offset").and_then(serde_json::Value::as_u64), Some(88_000));
        let cs = t_clip.get("clip_start_samples").and_then(serde_json::Value::as_i64).unwrap_or(-1);
        assert!((cs - 48_000).abs() <= 1, "expected clip_start_samples ~48000, got {cs}");
        let fo_tk = tp[2].get("ticks").and_then(serde_json::Value::as_u64).unwrap_or(0);
        assert_eq!(fo_tk, 8_640_000, "expected fade_out at 8_640_000 ticks, got {fo_tk}");
        Ok(())
    }

    #[test]
    fn encode_pull_edit_user_delay_and_clip_group_roundtrip() -> Result<(), Box<dyn std::error::Error>> {
        use spec::{BuildAudioClip, BuildAudioFile};
        let mut grp_names = BTreeMap::new();
        grp_names.insert(7u64, "Grp_Chorus".to_owned());
        let spec = PtxBuildSpec {
            sample_rate: 48_000,
            bit_depth: 24,
            pull_code: Some(12011), // +0.1%
            edit_state: Some(BuildEditState {
                edit_mode: 0, // Shuffle
                edit_tool: 8, // Pencil
                smart_tool: true,
                loop_playback: true,
                record_mode: 1, // Loop
            }),
            clip_group_names: grp_names,
            audio_files: vec![BuildAudioFile {
                file_name: "stem.wav".to_owned(),
                sample_rate: 48_000,
                channels: 1,
                bit_depth: 24,
                is_float: false,
                is_aiff: false,
                frames: 480_000,
                data_offset: 44,
                filetime: 0,
                umid_file_id: None,
            }],
            tracks: vec![BuildTrack {
                name: "Lead".to_owned(),
                kind: BuildTrackKind::Audio,
                user_delay: 137,
                audio_clips: vec![
                    BuildAudioClip {
                        name: "PartA".to_owned(),
                        file_indices: vec![0],
                        file_offset: 0,
                        length_samples: 48_000,
                        start_pos: 24_000,
                        pos_in_ticks: false,
                        muted: false,
                        sync_offset: None,
                        clip_gain_points: vec![],
                        fade_in: None,
                        fade_out: None,
                        clip_loop: None,
                        group: Some(7),
                    },
                    BuildAudioClip {
                        name: "PartB".to_owned(),
                        file_indices: vec![0],
                        file_offset: 48_000,
                        length_samples: 48_000,
                        start_pos: 72_000,
                        pos_in_ticks: false,
                        muted: false,
                        sync_offset: None,
                        clip_gain_points: vec![],
                        fade_in: None,
                        fade_out: None,
                        clip_loop: None,
                        group: Some(7),
                    },
                ],
                ..BuildTrack::default()
            }],
            ..PtxBuildSpec::default()
        };
        let bytes = encode_ptx(&spec)?;
        let doc = decode_bytes("tier1_features.ptx", &bytes)?;
        assert_eq!(doc.timeline.pull_code, Some(12011));
        assert_eq!(doc.timeline.pull.as_deref(), Some("+0.1%"));
        assert_eq!(doc.session_settings.edit_mode.as_deref(), Some("Shuffle"));
        assert_eq!(doc.session_settings.smart_tool, Some(true));
        assert_eq!(doc.session_settings.edit_tool_code, Some(8));
        assert_eq!(doc.session_settings.loop_playback, Some(true));
        assert_eq!(doc.session_settings.record_mode_code, Some(1));
        assert_eq!(doc.tracks[0].user_delay, Some(137));
        assert_eq!(doc.clip_group_regions.len(), 1);
        assert_eq!(doc.clip_group_regions[0].name, "Grp_Chorus");
        assert_eq!(doc.clip_group_regions[0].length, 96_000);
        assert_eq!(doc.clip_group_playlists.len(), 1);
        assert_eq!(doc.clip_group_playlists[0].len(), 2);
        Ok(())
    }
}
