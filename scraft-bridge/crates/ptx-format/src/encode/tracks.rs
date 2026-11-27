// Version: 0.7.0 (beta) | Date: 2026-11-27
//! Clean-room track, mixer strip, send, insert, folder, and track-list builders
//! (`0x2519`, `0x2107`, `0x210C`, `0x2624`, `0x1018`).

use std::collections::BTreeMap;

use crate::encode::ids::IdGen;
use crate::encode::plugins_data::{
    build_1017, build_filled_insert, lookup_stock_plugin, FilledInsertArgs, InsertAutoLaneData,
};
use crate::encode::spec::{BuildTimebase, BuildTrack, BuildTrackKind, PtxBuildSpec};
use crate::primitives::{lp_bytes, OFFSET_FORM};
use crate::tree::encode_block;

const ID_MARK: &[u8] = &[0x2a, 0x00, 0x00, 0x00];

fn strip_mono_base() -> [i32; 69] {
    let mut t = [0i32; 69];
    t[2] = -1440;
    for idx in [5, 6, 7, 8, 9, 12, 13, 14, 15, 16] {
        t[idx] = 100;
    }
    for idx in [19, 20, 26, 27, 28, 29, 30, 33, 34, 35, 36, 37] {
        t[idx] = 6_553_600;
    }
    t[23] = -94_371_840;
    t[24] = 65_535;
    for idx in [42, 43, 54, 55] {
        t[idx] = 65_536;
    }
    t[64] = 16_842_752;
    t[67] = 3_276_800;
    t[68] = 3_276_800;
    t
}

fn strip_st_main_base() -> [i32; 69] {
    let mut t = strip_mono_base();
    t[3] = -100;
    t[4] = -100;
    t[10] = 100;
    t[11] = 100;
    t[24] = -6_488_065;
    t[25] = -6_488_065;
    t[26] = 6_619_135;
    t[31] = 6_553_600;
    t[32] = 6_553_600;
    t
}

fn strip_st_send_base() -> [i32; 69] {
    let mut t = strip_mono_base();
    t[3] = -100;
    t[4] = -100;
    t[10] = -100;
    t[11] = -100;
    t[24] = -6_488_065;
    t[25] = -6_488_065;
    t[26] = 6_619_135;
    t[31] = -6_553_600;
    t[32] = -6_488_065;
    t[33] = 6_619_135;
    t
}

fn encode_1029(t: &[i32; 69], post_fader: bool) -> Vec<u8> {
    let mut d = Vec::with_capacity(1 + 69 * 4 + 2);
    d.push(u8::from(post_fader));
    for v in t {
        d.extend_from_slice(&v.to_le_bytes());
    }
    d.extend_from_slice(&[0, 0]);
    encode_block(0x0e, 0x1029, &d)
}

fn encode_260a(tb: BuildTimebase, pts: &[(u64, i16)]) -> Vec<u8> {
    let is_tk = tb == BuildTimebase::Ticks;
    let pts = if pts.is_empty() { vec![(0, 0)] } else { pts.to_vec() };
    let mut body = Vec::new();
    body.extend_from_slice(&u16::from(is_tk).to_le_bytes());
    body.extend_from_slice(&u32::try_from(pts.len()).unwrap_or(1).to_le_bytes());
    body.extend_from_slice(&2u16.to_le_bytes());
    if is_tk {
        body.extend_from_slice(&(pts.len().saturating_sub(1) as u16).to_le_bytes());
        let first_t = OFFSET_FORM + pts[0].0;
        body.extend_from_slice(&first_t.to_le_bytes());
    } else {
        let segs = u32::try_from(pts.len().saturating_sub(1)).unwrap_or(u32::MAX);
        body.extend_from_slice(&segs.to_le_bytes());
        body.extend_from_slice(&0u16.to_le_bytes());
        let first_s = u32::try_from(pts[0].0).unwrap_or(u32::MAX);
        body.extend_from_slice(&first_s.to_le_bytes());
    }
    body.extend_from_slice(&pts[0].1.to_le_bytes());
    for &(p, v) in pts.iter().skip(1) {
        body.extend_from_slice(&(p.min(u64::from(u32::MAX)) as u32).to_le_bytes());
        body.extend_from_slice(&v.to_le_bytes());
    }
    let mut d = vec![0x01, 0x46, 0x01, 0x00];
    d.extend_from_slice(&u32::try_from(body.len()).unwrap_or(0).to_le_bytes());
    d.extend_from_slice(&body);
    d.extend_from_slice(&[0, 0]);
    encode_block(1, 0x260a, &d)
}

fn panner_260c(tb: BuildTimebase, first_pts: &[(u64, i16)]) -> Vec<u8> {
    let v0 = first_pts.first().map_or(0, |p| p.1);
    let mut d = Vec::new();
    for (idx, default_val) in [
        v0, v0, 100, 100, 100, 100, 100, 100, 0, 0, 1, 0, 0, 0,
    ]
    .into_iter()
    .enumerate()
    {
        d.push(0x01);
        if idx == 0 && !first_pts.is_empty() {
            d.extend_from_slice(&encode_260a(tb, first_pts));
        } else {
            d.extend_from_slice(&encode_260a(tb, &[(0, default_val)]));
        }
    }
    encode_block(2, 0x260c, &d)
}

fn blk_485a() -> Vec<u8> {
    encode_block(2, 0x485a, &[0, 0, 0, 0, 1])
}

fn view_2037() -> Vec<u8> {
    encode_block(1, 0x2037, &[])
}

fn view_203a(v: u8) -> Vec<u8> {
    let mut d = view_2037();
    d.extend_from_slice(&[v, v]);
    encode_block(2, 0x203a, &d)
}

fn view_2038() -> Vec<u8> {
    let mut d = view_2037();
    d.push(0);
    encode_block(1, 0x2038, &d)
}

fn view_203b() -> Vec<u8> {
    let mut d = view_2037();
    d.extend_from_slice(&1u32.to_le_bytes());
    encode_block(1, 0x203b, &d)
}

fn view_cell(c: u8) -> Vec<u8> {
    match c {
        b'a' => view_203a(1),
        b'A' => view_203a(3),
        b'b' => view_203b(),
        _ => view_2038(),
    }
}

fn encode_2619(name: &str, tid: [u8; 8], is_rfolder: bool) -> Vec<u8> {
    let mut d = lp_bytes(name);
    d.extend_from_slice(&[0x01, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00]);
    d.extend_from_slice(ID_MARK);
    d.extend_from_slice(&tid);
    d.extend_from_slice(&[0u8; 4]);
    d.extend_from_slice(ID_MARK);
    d.extend_from_slice(&tid);
    d.extend_from_slice(&[0u8; 8]);
    d.extend_from_slice(&1u32.to_le_bytes());
    d.extend_from_slice(&[0u8; 33]);
    d.extend_from_slice(&encode_block(1, 0x4301, &[0u8; 32]));
    d.extend_from_slice(&[0u8; 4]);
    d.extend_from_slice(ID_MARK);
    d.extend_from_slice(&tid);
    d.push(0);
    d.push(u8::from(is_rfolder));
    encode_block(9, 0x2619, &d)
}

fn track_info_102d(name: &str, tid: [u8; 8], is_rfolder: bool, solo: bool, auto_mode: u8) -> Vec<u8> {
    let mut d = encode_2619(name, tid, is_rfolder);
    // `solo` and `auto_mode` sit immediately after `0x2619` inside `0x102D` (`+161 + name.len()` / `+162 + name.len()`).
    d.extend_from_slice(&[u8::from(solo), auto_mode, 0x00, 0x00, 0x00, 0x01, 0x00]);
    encode_block(3, 0x102d, &d)
}

struct ViewParams<'a> {
    cells: &'a [u8; 3],
    cells80: &'a [u8; 2],
    cells0a: &'a [u8; 4],
    comment: &'a str,
    ratio: f64,
    z1: u32,
    z2: u32,
    number: u32,
    is_audio_w2104: bool,
    c1_val: u8,
    a_val: u8,
    f0a: u16,
    g_val: u32,
    mark: u8,
}

fn view_15(vp: &ViewParams<'_>) -> Vec<u8> {
    let mut d = view_cell(vp.cells[0]);
    d.extend_from_slice(&[vp.a_val, 1, 0, 0, 1, 0]);
    d.extend_from_slice(&0x5cu16.to_le_bytes());
    d.extend_from_slice(&lp_bytes(vp.comment));
    d.push(0);
    d.extend_from_slice(&vp.ratio.to_le_bytes());
    if vp.is_audio_w2104 {
        d.push(vp.c1_val);
        let w2104: [u8; 28] = [
            0xef, 0xff, 0xdf, 0xbf, 0xef, 0xff, 0xdf, 0xbf, 0x32, 0x00, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xef, 0xff, 0xdf, 0xbf, 0x32, 0x00, 0x00, 0x00,
        ];
        let mut d2104 = encode_block(1, 0x2103, &[]);
        d2104.extend_from_slice(&w2104);
        d.extend_from_slice(&encode_block(2, 0x2104, &d2104));
        let mid: [u8; 23] = [
            0x01, 0xfe, 0xff, 0x01, 0x00, 0x04, 0x00, 0x00, 0x00, 0x01, 0x61, 0x00, 0x00, 0x00,
            0x04, 0x00, 0x00, 0x00, 0x09, 0x3d, 0x00, 0x00, 0x00,
        ];
        d.extend_from_slice(&mid);
    } else {
        d.push(0);
        d.push(vp.c1_val);
        d.extend_from_slice(&[0xfe, 0xff, 0x01]);
        d.extend_from_slice(&vp.z1.to_le_bytes());
        d.extend_from_slice(&[0x00, 0x01]);
        d.extend_from_slice(&0x61u16.to_le_bytes());
        d.extend_from_slice(&[0x00, 0x00, vp.mark, 0]);
        d.extend_from_slice(&vp.z2.to_le_bytes());
        d.extend_from_slice(&[0u8; 3]);
    }
    d.push(1); // last = 1
    d.extend_from_slice(&[0u8; 3]);
    d.extend_from_slice(&view_cell(vp.cells[1]));
    d.extend_from_slice(&[0, 0, 0, 0, 7, 0, 0, 0, 0, 0, 0, 0, 1]);
    d.extend_from_slice(&encode_block(1, 0x2434, &[4, 0, 0, 0, 0, 0, 0, 0x3c, 0]));
    d.extend_from_slice(&vp.number.to_le_bytes());
    d.extend_from_slice(&view_cell(vp.cells[2]));
    d.extend_from_slice(&[0, 1, 0, 0, 0]);
    let mut b80 = vec![0u8];
    b80.extend_from_slice(&view_cell(vp.cells80[0]));
    b80.extend_from_slice(&[0xff, 0xff, 0, 0, 0xff, 0xff, 0, 0, 0, 0, 0xff, 0xff, 0xff, 0xff]);
    b80.extend_from_slice(&view_cell(vp.cells80[1]));
    b80.extend_from_slice(&[0, 0xff, 0xff]);
    d.extend_from_slice(&encode_block(5, 0x2580, &b80));
    d.extend_from_slice(&[0u8; 4]);
    d.extend_from_slice(&vp.g_val.to_le_bytes());
    encode_block(0x15, 0x2015, &d)
}

fn view_0a(vp: &ViewParams<'_>) -> Vec<u8> {
    let mut d = view_15(vp);
    d.extend_from_slice(&vp.f0a.to_le_bytes());
    d.extend_from_slice(&view_cell(vp.cells0a[0]));
    d.extend_from_slice(&[0x13, 0x00, 0x00, 0x09, 0x3d, 0x00, 0x17, 0x00, 0xff, 0xff, 0xff, 0xff]);
    d.extend_from_slice(&view_cell(vp.cells0a[1]));
    d.extend_from_slice(&[2, 0, 0, 0]);
    d.extend_from_slice(&view_cell(vp.cells0a[2]));
    d.extend_from_slice(&view_cell(vp.cells0a[3]));
    encode_block(0x0a, 0x200a, &d)
}

/// Resolved bus / path lookup entry for output, input, and send builders.
#[derive(Debug, Clone)]
pub struct IoPathRef {
    pub path_num: u16,
    pub id: [u8; 8],
    pub name: String,
    pub stereo: bool,
}

fn build_out_260e(out_ref: Option<&IoPathRef>, active: bool, stem_override: Option<u8>) -> Vec<u8> {
    let act_b = u8::from(active);
    let mut d = Vec::new();
    match out_ref {
        Some(r) => {
            let st = stem_override.unwrap_or_else(|| u8::from(r.stereo));
            d.extend_from_slice(&r.path_num.to_le_bytes());
            d.extend_from_slice(&[act_b, act_b, 0, 0, 0, 0]);
            d.extend_from_slice(ID_MARK);
            d.extend_from_slice(&r.id);
            d.extend_from_slice(&[0u8; 16]);
            d.extend_from_slice(&lp_bytes(&r.name));
            d.extend_from_slice(&[st, st]);
            d.extend_from_slice(&[0xffu8; 8]);
            d.push(0);
            d.extend_from_slice(&[0xffu8; 4]);
            d.extend_from_slice(&[0x00, 0x0c, st, 0]);
        }
        None => {
            d.extend_from_slice(&[0xff, 0xff, act_b, act_b]);
            d.extend_from_slice(&[0u8; 38]);
            d.extend_from_slice(&[0xffu8; 8]);
            d.push(0);
            d.extend_from_slice(&[0xffu8; 4]);
            d.extend_from_slice(&[0x00, 0x0c, 0, 0]);
        }
    }
    encode_block(9, 0x260e, &d)
}

struct StripBuildArgs<'a> {
    tr: &'a BuildTrack,
    tid: [u8; 8],
    runnum: &'a [u32; 10],
    out_ref: Option<&'a IoPathRef>,
    in_ref: Option<&'a IoPathRef>,
    io_map: &'a BTreeMap<String, IoPathRef>,
    master: bool,
}

fn build_strip_set(
    args: &StripBuildArgs<'_>,
    plugin_table: &mut Vec<(String, bool, Vec<u8>)>,
    ids: &mut IdGen,
) -> Vec<u8> {
    let tr = args.tr;
    let tid = args.tid;
    let runnum = args.runnum;
    let out_ref = args.out_ref;
    let in_ref = args.in_ref;
    let io_map = args.io_map;
    let master = args.master;
    let st = u8::from(tr.stereo);
    let tb = tr.timebase;
    let is_rfolder = tr.kind == BuildTrackKind::RoutingFolder;
    let active = !tr.inactive;

    // 1) 11 insert slots (0x2627)
    let mut slot_blocks = Vec::with_capacity(11);
    for slot_i in 0..11 {
        if let Some(ins) = tr.inserts.iter().find(|x| x.slot_index == slot_i)
            && let Some(pspec) = lookup_stock_plugin(&ins.plugin_name)
        {
            let use_st = tr.stereo && !ins.multi_mono;
            let e17 = build_1017(&pspec, use_st);
            let ptab_idx = if let Some(pos) = plugin_table
                .iter()
                .position(|(nm, s_st, _)| nm == pspec.name && *s_st == use_st)
            {
                pos as u16
            } else {
                let pos = plugin_table.len() as u16;
                plugin_table.push((pspec.name.to_owned(), use_st, e17));
                pos
            };
            let auto_lanes: Vec<InsertAutoLaneData> = ins
                .automation
                .iter()
                .map(|a| InsertAutoLaneData {
                    param_name: a.param_name.clone(),
                    param_id: a.param_id.clone(),
                    param_index: a.param_index,
                    is_ticks: tb == BuildTimebase::Ticks,
                    points: a.points.clone(),
                })
                .collect();
            slot_blocks.push(build_filled_insert(&FilledInsertArgs {
                tidx: ptab_idx,
                spec: &pspec,
                use_stereo: use_st,
                ovr: &ins.params,
                active: ins.active,
                bypass: ins.bypass,
                multi_mono: ins.multi_mono,
                auto_lanes: &auto_lanes,
            }));
        } else {
            slot_blocks.push(encode_block(1, 0x2625, &encode_block(1, 0x2626, &[])));
        }
    }
    let mut d2627 = 11u16.to_le_bytes().to_vec();
    for sb in slot_blocks {
        d2627.extend_from_slice(&sb);
    }
    let inserts = encode_block(1, 0x2627, &d2627);

    // 2) Main strip (0x260D)
    let mut tm = if master {
        let mut m = strip_mono_base();
        m[64] = 0;
        m
    } else if tr.stereo {
        strip_st_main_base()
    } else {
        strip_mono_base()
    };
    let vol_pts = if tr.volume_lane.points.is_empty() {
        vec![(0u64, tr.volume_tenths_db)]
    } else {
        tr.volume_lane.points.clone()
    };
    let v0 = vol_pts[0].1;
    let m0 = tr.mute_lane.points.first().map_or(i16::from(tr.mute), |p| p.1);
    let mute_pts = if tr.mute_lane.points.is_empty() {
        vec![(0u64, m0)]
    } else {
        tr.mute_lane.points.clone()
    };
    tm[0] = i32::from(v0);
    tm[21] = i32::from(v0) * 65536;
    tm[1] = i32::from(m0 != 0);
    tm[22] = 65535 + i32::from(m0 != 0);

    let tbl_bytes = encode_1029(&tm, true);

    let main_strip = if master {
        let mut d = tbl_bytes;
        if let Some(oref) = out_ref {
            d.extend_from_slice(&[1, 0]);
            d.extend_from_slice(&build_out_260e(Some(oref), active, Some(st)));
        } else {
            d.extend_from_slice(&[0, 0]);
        }
        d.push(1);
        d.extend_from_slice(&encode_260a(tb, &vol_pts));
        d.extend_from_slice(&[0, 0]);
        d.extend_from_slice(&encode_block(2, 0x260c, &[0u8; 14]));
        d.extend_from_slice(&encode_block(2, 0x260c, &[0u8; 14]));
        d.extend_from_slice(&[0u8; 9]);
        d.extend_from_slice(&blk_485a());
        encode_block(6, 0x260d, &d)
    } else {
        let pan0: Vec<(u64, i16)> = tr
            .pan_lanes
            .first()
            .filter(|l| !l.points.is_empty())
            .map_or_else(
                || vec![(0, tr.pan.first().copied().unwrap_or(if tr.stereo { -100 } else { 0 }))],
                |l| l.points.clone(),
            );
        let pan1: Vec<(u64, i16)> = tr
            .pan_lanes
            .get(1)
            .filter(|l| !l.points.is_empty())
            .map_or_else(
                || vec![(0, tr.pan.get(1).copied().unwrap_or(if tr.stereo { 100 } else { 0 }))],
                |l| l.points.clone(),
            );
        let mut d = tbl_bytes;
        d.extend_from_slice(&[1, 0]);
        d.extend_from_slice(&build_out_260e(out_ref, active, None));
        d.push(1);
        d.extend_from_slice(&encode_260a(tb, &vol_pts));
        d.push(1);
        d.extend_from_slice(&encode_260a(tb, &mute_pts));
        d.push(1);
        d.extend_from_slice(&encode_260a(tb, &[(0, -1440)]));
        d.extend_from_slice(&panner_260c(tb, &pan0));
        d.extend_from_slice(&panner_260c(tb, &pan1));
        d.extend_from_slice(&[0u8; 9]);
        d.extend_from_slice(&blk_485a());
        encode_block(6, 0x260d, &d)
    };

    // 3) 10 Send strips
    let n_sends = if master { 0usize } else { 10usize };
    let mut sends_buf = if tr.kind == BuildTrackKind::Audio {
        u32::try_from(n_sends).unwrap_or(10).to_le_bytes().to_vec()
    } else {
        u16::try_from(n_sends).unwrap_or(0).to_le_bytes().to_vec()
    };
    for s_idx in 0..n_sends {
        if tr.kind != BuildTrackKind::Audio {
            sends_buf.extend_from_slice(&u16::try_from(s_idx).unwrap_or(0).to_le_bytes());
        }
        let s_strip = if let Some(s) = tr.sends.iter().find(|x| x.slot_index == s_idx)
            && let Some(bref) = io_map.get(&s.bus_name)
        {
            let mut stbl = if tr.stereo {
                strip_st_send_base()
            } else {
                strip_mono_base()
            };
            stbl[0] = i32::from(s.level_tenths_db);
            stbl[21] = i32::from(s.level_tenths_db) * 65536;
            stbl[1] = i32::from(s.mute);
            stbl[22] = 65535 + i32::from(s.mute);
            if tr.stereo {
                stbl[10] = 100;
                stbl[11] = 100;
                stbl[31] = 6_553_600;
                stbl[32] = 6_553_600;
                stbl[33] = 6_553_600;
            } else if bref.stereo {
                stbl[3] = i32::from(s.pan);
                stbl[24] = i32::from(s.pan) * 65536 + 65535;
                stbl[25] = 65535;
            }
            let empty_pan = encode_block(2, 0x260c, &[0u8; 14]);
            let send_pan_pts: Vec<(u64, i16)> = if s.pan_points.is_empty() {
                vec![(0, s.pan)]
            } else {
                s.pan_points.clone()
            };
            let send_vol_pts: Vec<(u64, i16)> = if s.volume_points.is_empty() {
                vec![(0, s.level_tenths_db)]
            } else {
                s.volume_points.clone()
            };
            let send_mute_pts: Vec<(u64, i16)> = if s.mute_points.is_empty() {
                vec![(0, i16::from(s.mute))]
            } else {
                s.mute_points.clone()
            };
            let p1 = if bref.stereo {
                panner_260c(tb, &send_pan_pts)
            } else {
                empty_pan.clone()
            };
            let p2 = if bref.stereo && tr.stereo {
                panner_260c(tb, &[(0, 100)])
            } else {
                empty_pan
            };
            let mut d = encode_1029(&stbl, !s.pre_fader);
            d.extend_from_slice(&[1, 0]);
            d.extend_from_slice(&build_out_260e(Some(bref), s.active, None));
            d.push(1);
            d.extend_from_slice(&encode_260a(tb, &send_vol_pts));
            d.push(1);
            d.extend_from_slice(&encode_260a(tb, &send_mute_pts));
            d.push(0);
            d.extend_from_slice(&p1);
            d.extend_from_slice(&p2);
            d.extend_from_slice(&[0u8; 9]);
            d.extend_from_slice(&blk_485a());
            encode_block(6, 0x260d, &d)
        } else {
            let stbl = if tr.stereo {
                strip_st_send_base()
            } else {
                strip_mono_base()
            };
            let mut d = encode_1029(&stbl, true);
            d.extend_from_slice(&[0u8; 5]);
            d.extend_from_slice(&encode_block(2, 0x260c, &[0u8; 14]));
            d.extend_from_slice(&encode_block(2, 0x260c, &[0u8; 14]));
            d.extend_from_slice(&[0u8; 9]);
            d.extend_from_slice(&blk_485a());
            encode_block(6, 0x260d, &d)
        };
        sends_buf.extend_from_slice(&s_strip);
        if tr.kind == BuildTrackKind::Audio && s_idx < 9 {
            sends_buf.extend_from_slice(&(u16::try_from(s_idx).unwrap_or(0) + 1).to_le_bytes());
        }
    }

    // 4) Running numbers, input, slot UUIDs, tail
    let in_path_num = in_ref.map_or(0xFFFFu16, |r| r.path_num);
    let uu = ids.next_uuids(10);
    let mut tail = Vec::new();
    tail.extend_from_slice(&[0x01, 0x01, 0x0a, 0x00]);
    for r in runnum {
        tail.extend_from_slice(&r.to_le_bytes());
    }
    tail.extend_from_slice(&tr.user_delay.to_le_bytes());
    tail.extend_from_slice(&8u32.to_le_bytes());
    tail.push(0);
    if let Some(ir) = in_ref {
        tail.extend_from_slice(&lp_bytes(&ir.name));
        tail.extend_from_slice(&0u32.to_le_bytes());
        tail.extend_from_slice(ID_MARK);
        tail.extend_from_slice(&ir.id);
        tail.extend_from_slice(&[0, 2]);
    } else {
        tail.extend_from_slice(&lp_bytes(""));
        tail.extend_from_slice(&0u32.to_le_bytes());
        tail.extend_from_slice(&[0u8; 12]);
        tail.extend_from_slice(&[0, 0]);
    }
    tail.extend_from_slice(&[0u8; 5]);
    tail.extend_from_slice(&[0xff, 0xff, 0xff, 0xff, 0x00, 0xff, 0x7f]);
    tail.extend_from_slice(&10u16.to_le_bytes());
    for u in uu {
        tail.extend_from_slice(&u);
    }
    let io_st = if master && tr.stereo { 1 } else { st };
    tail.extend_from_slice(&[0, io_st, 0, 0, 1, 0, io_st, 0]);
    tail.extend_from_slice(&[0u8; 20]);

    let info = track_info_102d(&tr.name, tid, is_rfolder, tr.solo, tr.automation_mode);
    let mut b261b = info;
    if master && tr.stereo {
        b261b.extend_from_slice(&[1, 0xff, 0xff, 1]);
    } else {
        b261b.push(st);
        b261b.extend_from_slice(&in_path_num.to_le_bytes());
        b261b.push(u8::from(active));
    }
    b261b.extend_from_slice(&inserts);
    b261b.extend_from_slice(&main_strip);
    b261b.extend_from_slice(&sends_buf);
    b261b.extend_from_slice(&tail);
    b261b.extend_from_slice(&encode_block(4, 0x4856, &[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1]));
    encode_block(0x0f, 0x261b, &b261b)
}

struct ChannelBuildArgs<'a> {
    tr: &'a BuildTrack,
    tid: [u8; 8],
    tidx: usize,
    aidx: u32,
    ridx: u32,
    runnum: &'a [u32; 10],
    out_ref: Option<&'a IoPathRef>,
    in_ref: Option<&'a IoPathRef>,
    io_map: &'a BTreeMap<String, IoPathRef>,
}

fn channel_block(
    args: &ChannelBuildArgs<'_>,
    plugin_table: &mut Vec<(String, bool, Vec<u8>)>,
    ids: &mut IdGen,
) -> Vec<u8> {
    let tr = args.tr;
    let tid = args.tid;
    let tidx = args.tidx;
    let aidx = args.aidx;
    let ridx = args.ridx;
    let runnum = args.runnum;
    let out_ref = args.out_ref;
    let in_ref = args.in_ref;
    let io_map = args.io_map;
    let number = u32::try_from(if tr.hidden { 0 } else { tidx + 1 }).unwrap_or(1);
    let st = u8::from(tr.stereo);

    match tr.kind {
        BuildTrackKind::Audio => {
            let b61 = build_strip_set(
                &StripBuildArgs {
                    tr,
                    tid,
                    runnum,
                    out_ref,
                    in_ref,
                    io_map,
                    master: false,
                },
                plugin_table,
                ids,
            );
            let va = view_0a(&ViewParams {
                cells: b"888",
                cells80: b"bb",
                cells0a: b"8888",
                comment: &tr.comment,
                ratio: 0.5,
                z1: 4_000_000,
                z2: 4_000_000,
                number,
                is_audio_w2104: true,
                c1_val: 1,
                a_val: 1,
                f0a: 1,
                g_val: 1,
                mark: 4,
            });
            let mut plist = 0u32.to_le_bytes().to_vec();
            plist.extend_from_slice(&0u32.to_le_bytes());
            plist.extend_from_slice(&[0u8; 4]);
            plist.extend_from_slice(&[0u8; 13]);
            let mut v0b_d = va;
            v0b_d.extend_from_slice(&plist);
            let view = encode_block(0x0a, 0x200b, &v0b_d);

            let mut mid = Vec::new();
            mid.extend_from_slice(&aidx.to_le_bytes());
            mid.extend_from_slice(&[0x01, 0x00]);
            mid.extend_from_slice(&(aidx as u16).to_le_bytes());
            mid.extend_from_slice(&[0x00, 0x00, 0xff, 0xff]);

            let mut end = vec![0u8; 17];
            end.extend_from_slice(&aidx.to_le_bytes());
            end.extend_from_slice(&1u32.to_le_bytes());
            end.extend_from_slice(&[0u8; 11]);
            end.push(0x01);

            let mut d = b61;
            d.extend_from_slice(&mid);
            d.extend_from_slice(&view);
            d.extend_from_slice(&end);
            encode_block(6, 0x261c, &d)
        }
        BuildTrackKind::Aux | BuildTrackKind::RoutingFolder | BuildTrackKind::Master => {
            let master = tr.kind == BuildTrackKind::Master;
            let ct = if master { 0x261d } else { 0x261e };
            let vct = if master { 0x200c } else { 0x200d };
            let cells = if tr.kind == BuildTrackKind::RoutingFolder {
                (b"888", b"bb", b"8888")
            } else {
                (b"bbb", b"bb", b"b8b8")
            };
            let f0a = u16::from(tr.kind != BuildTrackKind::RoutingFolder);
            let eff_out = if master && !tr.stereo && out_ref.is_some_and(|o| o.path_num == 2) {
                None
            } else {
                out_ref
            };
            let b61 = build_strip_set(
                &StripBuildArgs {
                    tr,
                    tid,
                    runnum,
                    out_ref: eff_out,
                    in_ref,
                    io_map,
                    master,
                },
                plugin_table,
                ids,
            );
            let va = view_0a(&ViewParams {
                cells: cells.0,
                cells80: cells.1,
                cells0a: cells.2,
                comment: &tr.comment,
                ratio: 0.5,
                z1: 4_000_000,
                z2: 1_024_000_000,
                number,
                is_audio_w2104: false,
                c1_val: 1,
                a_val: 1,
                f0a,
                g_val: 1,
                mark: 4,
            });
            let mut d = b61;
            d.extend_from_slice(&encode_block(1, vct, &va));
            encode_block(1, ct, &d)
        }
        BuildTrackKind::Midi => {
            let info = track_info_102d(&tr.name, tid, false, tr.solo, tr.automation_mode);
            let mut r = ridx.to_le_bytes().to_vec();
            r.extend_from_slice(&1u32.to_le_bytes());

            let mut mix = Vec::new();
            for v in [96u32, 0, 64, 0] {
                mix.extend_from_slice(&v.to_le_bytes());
            }
            mix.extend_from_slice(&[0x80, 0xff, 0x00, 0xc0, 0x00, 0x00]);
            for v in [96u32, 0, 64] {
                mix.extend_from_slice(&v.to_le_bytes());
            }
            mix.extend_from_slice(&[0u8; 33]);
            let lane_d = encode_260a(tr.timebase, &[(0, 0)]);
            let mut s_d = encode_block(7, 0x2036, &mix);
            s_d.push(0x01);
            s_d.extend_from_slice(&lane_d);
            let strip = encode_block(1, 0x2611, &s_d);

            let va = view_0a(&ViewParams {
                cells: b"aaa",
                cells80: b"AA",
                cells0a: b"aaaa",
                comment: &tr.comment,
                ratio: 0.532_258_064_516_129,
                z1: 12_800_000,
                z2: 3_276_800_000,
                number,
                is_audio_w2104: false,
                c1_val: 2,
                a_val: 1,
                f0a: 0,
                g_val: 1,
                mark: if tr.midi_clips.is_empty() { 4 } else { 3 },
            });
            let mut vd = va;
            vd.extend_from_slice(&0u32.to_le_bytes());
            vd.extend_from_slice(&[0x01, 0x00, 96, 64]);
            vd.extend_from_slice(&(-1.0f64).to_le_bytes());
            vd.extend_from_slice(&(-1.0f64).to_le_bytes());
            vd.extend_from_slice(&[0, 0xff, 0xff, 0xff, 0xff]);
            let view = encode_block(5, 0x2010, &vd);

            let mut d = info;
            d.extend_from_slice(&r);
            d.extend_from_slice(&r[..5]);
            d.extend_from_slice(&strip);
            d.extend_from_slice(&view);
            d.extend_from_slice(&[0u8; 8]);
            d.extend_from_slice(&encode_block(2, 0x206f, &1u32.to_le_bytes()));
            d.push(0x01);
            d.extend_from_slice(&r);
            d.extend_from_slice(&[0u8; 14]);
            encode_block(8, 0x2620, &d)
        }
        BuildTrackKind::Instrument => {
            let b61 = build_strip_set(
                &StripBuildArgs {
                    tr,
                    tid,
                    runnum,
                    out_ref,
                    in_ref,
                    io_map,
                    master: false,
                },
                plugin_table,
                ids,
            );
            // Strip off tail & 0x4856 to match inline 0x2621 format (`_split_strip_set`)
            let b61_body = &b61[9..];
            let split_at = b61_body
                .windows(4)
                .position(|w| w == [0x01, 0x01, 0x0a, 0x00])
                .unwrap_or(b61_body.len());
            let mut d = b61_body[..split_at].to_vec();
            d.extend_from_slice(&[0x01, 0x01, 0x0a, 0x00]);
            for rn in runnum {
                d.extend_from_slice(&rn.to_le_bytes());
            }
            d.extend_from_slice(&tr.user_delay.to_le_bytes());
            d.extend_from_slice(&0u32.to_le_bytes());
            d.extend_from_slice(&ridx.to_le_bytes());
            d.extend_from_slice(&1u16.to_le_bytes());
            d.extend_from_slice(&ridx.to_le_bytes());
            d.push(1);

            let va = view_0a(&ViewParams {
                cells: b"aaa",
                cells80: b"AA",
                cells0a: b"aaaa",
                comment: &tr.comment,
                ratio: 0.532_258_064_516_129,
                z1: 12_800_000,
                z2: 3_276_800_000,
                number,
                is_audio_w2104: false,
                c1_val: 2,
                a_val: 1,
                f0a: 0,
                g_val: 1,
                mark: if tr.midi_clips.is_empty() { 4 } else { 3 },
            });
            let mut vd = va;
            vd.extend_from_slice(&0u32.to_le_bytes());
            vd.extend_from_slice(&[0x01, 0x00, 96, 64]);
            vd.extend_from_slice(&(-1.0f64).to_le_bytes());
            vd.extend_from_slice(&(-1.0f64).to_le_bytes());
            vd.extend_from_slice(&[0, 0xff, 0xff, 0xff, 0xff]);
            d.extend_from_slice(&encode_block(5, 0x2010, &vd));
            d.extend_from_slice(&[0u8; 8]);
            d.extend_from_slice(&encode_block(2, 0x206f, &1u32.to_le_bytes()));

            let mut mix = Vec::new();
            for v in [96u32, 0, 64, 0] {
                mix.extend_from_slice(&v.to_le_bytes());
            }
            mix.extend_from_slice(&[0x80, 0xff, 0x00, 0xc0, 0x01, 0x00]);
            for v in [96u32, 0, 64] {
                mix.extend_from_slice(&v.to_le_bytes());
            }
            mix.extend_from_slice(&[0u8; 33]);
            let mut s_d = encode_block(7, 0x2036, &mix);
            s_d.push(0x01);
            s_d.extend_from_slice(&encode_260a(BuildTimebase::Ticks, &[(0, 0)]));
            d.extend_from_slice(&encode_block(1, 0x2611, &s_d));

            d.extend_from_slice(&[0u8; 28]);
            d.extend_from_slice(&[0xff, 0xff, 0xff, 0xff, 0x00, 0x00, 0xff, 0x7f]);
            d.extend_from_slice(&10u16.to_le_bytes());
            for u in ids.next_uuids(10) {
                d.extend_from_slice(&u);
            }
            d.extend_from_slice(&[0, st, 0, 0, 0, 1, 0, st]);
            d.extend_from_slice(&[0u8; 29]);
            d.extend_from_slice(&encode_block(4, 0x4856, &[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1]));
            d.extend_from_slice(&[0u8; 2]);
            encode_block(0x11, 0x2621, &d)
        }
        BuildTrackKind::BasicFolder => {
            let i19 = encode_2619(&tr.name, tid, true);
            let mut d15 = view_2038();
            d15.extend_from_slice(&[0x00, 0x01, 0x00, 0x01, 0x00, 0x00]);
            d15.extend_from_slice(&0x5cu16.to_le_bytes());
            d15.extend_from_slice(&lp_bytes(&tr.comment));
            d15.push(0);
            d15.extend_from_slice(&0.5f64.to_le_bytes());
            d15.extend_from_slice(&[0, 0, 0xfe, 0xff, 0x01]);
            d15.extend_from_slice(&4_000_000u32.to_le_bytes());
            d15.extend_from_slice(&[0, 1]);
            d15.extend_from_slice(&0x61u16.to_le_bytes());
            d15.extend_from_slice(&[0, 0, 4, 0]);
            d15.extend_from_slice(&1_024_000_000u32.to_le_bytes());
            d15.extend_from_slice(&[0u8; 11]);
            d15.extend_from_slice(&[7, 0, 0, 0, 0, 0, 0, 0, 1]);
            d15.extend_from_slice(&encode_block(1, 0x2434, &[4, 0, 0, 0, 0, 0, 0, 0x3c, 0]));
            d15.extend_from_slice(&number.to_le_bytes());
            d15.extend_from_slice(&view_2038());
            d15.extend_from_slice(&[0u8; 13]);
            let v15 = encode_block(0x15, 0x2015, &d15);

            let e = view_2037();
            let mut d0a = v15;
            d0a.extend_from_slice(&[0, 0]);
            d0a.extend_from_slice(&e);
            d0a.extend_from_slice(&[0x13, 0x00, 0xff, 0xff, 0xff, 0xff, 0x13, 0x00, 0xff, 0xff, 0xff, 0xff]);
            d0a.extend_from_slice(&e);
            d0a.extend_from_slice(&[0u8; 4]);
            d0a.extend_from_slice(&e);
            d0a.extend_from_slice(&e);
            let va = encode_block(0x0a, 0x200a, &d0a);

            let mut d = i19;
            d.extend_from_slice(&[0x01, 0x00, 0x00]);
            d.extend_from_slice(&encode_block(2, 0x4701, &va));
            d.push(0);
            encode_block(5, 0x263b, &d)
        }
    }
}

fn head_entry(kind: u16, name: &str, tid: [u8; 8], number: u8, stereo: bool) -> Vec<u8> {
    let mut d = kind.to_le_bytes().to_vec();
    d.extend_from_slice(&lp_bytes(name));
    d.push(u8::from(stereo));
    d.extend_from_slice(&[0u8; 5]);
    d.extend_from_slice(ID_MARK);
    d.extend_from_slice(&tid);
    d.push(number);
    d.extend_from_slice(&[0, 0]);
    d
}

struct ListEntryArgs<'a> {
    kind: u16,
    name: &'a str,
    tid: [u8; 8],
    number: u32,
    stereo: bool,
    folder: bool,
    has_clips: bool,
    colour: i16,
}

fn list_entry(a: &ListEntryArgs<'_>) -> Vec<u8> {
    let st = u8::from(a.stereo);
    let mut d = a.kind.to_le_bytes().to_vec();
    d.extend_from_slice(&lp_bytes(a.name));
    d.push(st);
    d.extend_from_slice(&[0u8; 5]);
    d.extend_from_slice(ID_MARK);
    d.extend_from_slice(&a.tid);
    d.extend_from_slice(&a.number.to_le_bytes());
    d.push(0);
    d.extend_from_slice(&[0u8; 5]);
    d.extend_from_slice(ID_MARK);
    d.extend_from_slice(&a.tid);
    d.extend_from_slice(&[st, 0]);
    d.extend_from_slice(&encode_block(1, 0x4420, &[0, 0]));
    d.extend_from_slice(&[u8::from(a.folder), 0, st, 0, 1, 1, u8::from(a.has_clips), 0, 0]);
    d.extend_from_slice(&a.colour.to_le_bytes());
    encode_block(10, 0x251a, &d)
}

fn kind_entry(kind: u16, name: &str, tid: [u8; 8]) -> Vec<u8> {
    let mut d = vec![0, 0, 0, kind as u8];
    d.extend_from_slice(&lp_bytes(name));
    d.extend_from_slice(&[0u8; 4]);
    d.extend_from_slice(ID_MARK);
    d.extend_from_slice(&tid);
    d.extend_from_slice(&[0u8; 16]);
    encode_block(1, 0x210b, &d)
}

/// Container outputs for track lists, folders, channels, and plug-in table.
pub struct BuiltTracks {
    pub blk_2519: Vec<u8>,
    pub blk_210c: Vec<u8>,
    pub blk_2107: Vec<u8>,
    pub blk_2624: Vec<u8>,
    pub blk_1018: Option<Vec<u8>>,
}

/// Build `0x2519`, `0x210C`, `0x2107`, `0x2624`, and optional `0x1018` plug-in table.
pub fn build_track_blocks(
    spec: &PtxBuildSpec,
    track_ids: &[([u8; 8], [u8; 8])],
    has_clips: &[bool],
    io_map: &BTreeMap<String, IoPathRef>,
    ids: &mut IdGen,
) -> BuiltTracks {
    let n = spec.tracks.len();
    let has_markers = spec.markers.iter().any(|m| !m.is_selection);

    // 1) 0x2519 track head & group A/B 0x251A entries
    let mut d2519 = vec![0x01, 0x00];
    d2519.extend_from_slice(&[0u8; 12]);
    d2519.extend_from_slice(&u32::try_from(n).unwrap_or(0).to_le_bytes());
    let mut list_a = Vec::new();
    let mut list_b = Vec::new();
    let mut vis_num = 0u32;
    for (i, tr) in spec.tracks.iter().enumerate() {
        let (tid, _) = track_ids[i];
        let kc = tr.kind.code();
        let num = if tr.hidden {
            0
        } else {
            vis_num += 1;
            vis_num
        };
        d2519.extend_from_slice(&head_entry(kc, &tr.name, tid, num as u8, tr.stereo));
        let le = list_entry(&ListEntryArgs {
            kind: kc,
            name: &tr.name,
            tid,
            number: num,
            stereo: tr.stereo,
            folder: tr.kind.is_folder(),
            has_clips: has_clips.get(i).copied().unwrap_or(false),
            colour: tr.colour.unwrap_or(-2),
        });
        list_a.extend_from_slice(&le);
        list_b.extend_from_slice(&le);
    }
    d2519.extend_from_slice(&list_a);
    d2519.extend_from_slice(&u32::try_from(n).unwrap_or(0).to_le_bytes());
    d2519.extend_from_slice(&list_b);
    d2519.extend_from_slice(&[0, 0]);
    d2519.extend_from_slice(&24u32.to_le_bytes());
    d2519.extend_from_slice(&[0u8; 6]);
    d2519.extend_from_slice(&encode_block(1, 0x2716, &[0u8; 4]));
    d2519.extend_from_slice(&encode_block(1, 0x4422, &[0, 0]));
    d2519.extend_from_slice(&encode_block(1, 0x4420, &[0, 0]));

    let mut ent_251c = Vec::new();
    for i in 0u32..5 {
        let mut d1c = i.to_le_bytes().to_vec();
        if i == 0 && has_markers {
            d1c.extend_from_slice(&[0, 0, 1]);
        } else {
            d1c.extend_from_slice(&[0, 0, 0]);
        }
        d1c.extend_from_slice(&i.to_le_bytes());
        ent_251c.extend_from_slice(&encode_block(2, 0x251c, &d1c));
    }
    let mut d251b = 5u32.to_le_bytes().to_vec();
    d251b.extend_from_slice(&ent_251c);
    d2519.extend_from_slice(&encode_block(1, 0x251b, &d251b));
    d2519.extend_from_slice(&encode_block(1, 0x483d, &[0, 0]));
    let blk_2519 = encode_block(9, 0x2519, &d2519);

    // 2) 0x2107 > 0x210B
    let mut d2107 = [0u8; 9].to_vec();
    d2107[8] = 1;
    d2107.extend_from_slice(&u32::try_from(n).unwrap_or(0).to_le_bytes());
    for (i, tr) in spec.tracks.iter().enumerate() {
        d2107.extend_from_slice(&kind_entry(tr.kind.code(), &tr.name, track_ids[i].0));
    }
    let blk_2107 = encode_block(5, 0x2107, &d2107);

    // 3) 0x210C folder membership
    let mut by_folder: BTreeMap<usize, Vec<[u8; 8]>> = BTreeMap::new();
    for (i, tr) in spec.tracks.iter().enumerate() {
        if let Some(fname) = &tr.folder_name
            && let Some(fidx) = spec.tracks.iter().position(|f| &f.name == fname && f.kind.is_folder())
        {
            by_folder.entry(fidx).or_default().push(track_ids[i].0);
        }
    }
    let mut d210c = u32::try_from(by_folder.len()).unwrap_or(0).to_le_bytes().to_vec();
    for (fidx, members) in by_folder {
        d210c.extend_from_slice(&[0u8; 5]);
        d210c.extend_from_slice(ID_MARK);
        d210c.extend_from_slice(&track_ids[fidx].0);
        d210c.extend_from_slice(&u32::try_from(members.len()).unwrap_or(0).to_le_bytes());
        for mid in members {
            d210c.extend_from_slice(&[0u8; 5]);
            d210c.extend_from_slice(ID_MARK);
            d210c.extend_from_slice(&mid);
        }
    }
    let blk_210c = encode_block(1, 0x210c, &d210c);

    // 4) 0x2624 channel blocks + plugin_table
    let main_out_ref = io_map
        .get(&spec.main_out_name)
        .or_else(|| io_map.values().next());
    let mut plugin_table: Vec<(String, bool, Vec<u8>)> = Vec::new();
    let mut aidx_ctr = 0u32;
    let mut ridx_ctr = 0u32;
    let mut next_run = 1u32;

    let mut d2624 = u32::try_from(n).unwrap_or(0).to_le_bytes().to_vec();
    for (i, tr) in spec.tracks.iter().enumerate() {
        let out_ref = match &tr.output_bus {
            Some(bn) => io_map.get(bn).or(main_out_ref),
            None => main_out_ref,
        };
        let in_ref = tr.input_bus.as_ref().and_then(|bn| io_map.get(bn));
        let mut runnum = [0u32; 10];
        if tr.kind.has_strip() {
            for slot in &mut runnum {
                *slot = next_run;
                next_run += 1;
            }
        }
        let ch_blk = channel_block(
            &ChannelBuildArgs {
                tr,
                tid: track_ids[i].0,
                tidx: i,
                aidx: aidx_ctr,
                ridx: ridx_ctr,
                runnum: &runnum,
                out_ref,
                in_ref,
                io_map,
            },
            &mut plugin_table,
            ids,
        );
        d2624.extend_from_slice(&ch_blk);
        if tr.kind == BuildTrackKind::Audio {
            aidx_ctr += 1;
        }
        if matches!(tr.kind, BuildTrackKind::Midi | BuildTrackKind::Instrument) {
            ridx_ctr += 1;
        }
    }
    let blk_2624 = encode_block(1, 0x2624, &d2624);

    let blk_1018 = if plugin_table.is_empty() {
        None
    } else {
        let mut d1018 = u32::try_from(plugin_table.len()).unwrap_or(0).to_le_bytes().to_vec();
        for (_, _, entry) in plugin_table {
            d1018.extend_from_slice(&entry);
        }
        Some(encode_block(1, 0x1018, &d1018))
    };

    BuiltTracks {
        blk_2519,
        blk_210c,
        blk_2107,
        blk_2624,
        blk_1018,
    }
}
