// Version: 0.7.0 (beta) | Date: 2026-11-27
//! MIDI data block (`0x2000`: `MdChun`, `MdNLB`, `MdCDS`, `MdES` / `MdTEL`) decoding.

use serde::{Deserialize, Serialize};

use crate::primitives::{find_bytes, i32_at, le_u64, plain_ticks, u32_at};
use crate::tree::Block;

/// MIDI program-change decoded fields.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ProgramBank {
    pub ticks: u64,
    pub program: u32,
    pub bank_msb: u32,
    pub bank_lsb: u32,
}

/// MIDI controller / pitch-bend / pressure / program lane (`MdCDS`).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct MidiController {
    pub kind: serde_json::Value,
    pub number: u8,
    pub points: Vec<[i64; 2]>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub program_banks: Option<Vec<ProgramBank>>,
}

/// Per-note MPE curve inside an MPE `MdCDS` container.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct MpeCurve {
    pub kind: serde_json::Value,
    pub number: u8,
    pub mpe_channel: u8,
    pub key: u8,
    pub velocity: u8,
    pub note_start: u64,
    pub points: Vec<[i64; 2]>,
}

/// One `MdChun` chunk inside `0x2000`.
#[derive(Debug, Clone, PartialEq, Eq, Default, Serialize, Deserialize)]
pub struct MidiChunk {
    /// Notes as `[start_ticks, key, length_ticks, velocity]`.
    pub notes: Vec<[u64; 4]>,
    pub controllers: Vec<MidiController>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub mpe_curves: Vec<MpeCurve>,
    pub sysex: Vec<(u64, String)>,
}

fn ctrl_kind_value(code: u8) -> serde_json::Value {
    let s = match code {
        1 => "pitch_bend",
        2 => "controller",
        3 => "program",
        4 => "channel_pressure",
        5 => "poly_pressure",
        other => return serde_json::Value::from(other),
    };
    serde_json::Value::from(s)
}

fn decode_mdcd_points(body: &[u8], c_at: usize) -> Option<(Vec<[i64; 2]>, usize)> {
    let n = usize::try_from(u32_at(body, c_at + 10)?).ok()?;
    let end = c_at.checked_add(14)?.checked_add(12 * n)?;
    if end > body.len() {
        return None;
    }
    let mut pts = Vec::with_capacity(n);
    for r in 0..n {
        let off = c_at + 14 + 12 * r;
        let (raw_t, val) = (le_u64(body, off, 5)?, i32_at(body, off + 8)?);
        let t_plain = i64::try_from(plain_ticks(raw_t)).unwrap_or(i64::MAX);
        pts.push([t_plain, i64::from(val)]);
    }
    Some((pts, end))
}

/// Parse all `MdChun` chunks in `0x2000`.
pub fn parse_midi_lists(d: &[u8], tree: &[Block], warn: &mut Vec<String>) -> Vec<MidiChunk> {
    let Some(b) = tree.iter().find(|t| t.content_type == 0x2000) else {
        return Vec::new();
    };
    let Some(x) = d.get(b.data_start()..b.end().min(d.len())) else {
        return Vec::new();
    };
    let mut at = Vec::new();
    let mut scan = 0;
    while let Some(pos) = find_bytes(x, b"MdChun", scan) {
        at.push(pos);
        scan = pos + 1;
    }
    at.push(x.len());

    let mut out = Vec::with_capacity(at.len().saturating_sub(1));
    for k in 0..at.len().saturating_sub(1) {
        let seg = &x[at[k]..at[k + 1]];
        let mut ent = MidiChunk::default();

        if let Some(j) = find_bytes(seg, b"MdNLB", 0)
            && let Some(n) = u32_at(seg, j + 11).and_then(|v| usize::try_from(v).ok())
        {
            if j + 15 + 35 * n <= seg.len() {
                for r in 0..n {
                    let o = j + 15 + 35 * r;
                    let (Some(raw_start), Some(&key), Some(len_t), Some(&vel)) = (
                        le_u64(seg, o, 5),
                        seg.get(o + 8),
                        le_u64(seg, o + 9, 5),
                        seg.get(o + 17),
                    ) else {
                        break;
                    };
                    ent.notes
                        .push([plain_ticks(raw_start), u64::from(key), len_t, u64::from(vel)]);
                }
            } else {
                warn.push(format!("MIDI chunk {k}: note count {n} does not fit"));
            }
        }

        let mut j_opt = find_bytes(seg, b"MdCDS", 0);
        while let Some(j) = j_opt {
            let body_len = u32_at(seg, j + 7)
                .and_then(|v| usize::try_from(v).ok())
                .unwrap_or(0);
            let body_end = (j + 11 + body_len).min(seg.len());
            if let Some(body) = seg.get(j + 11..body_end)
                && let (Some(s_), Some(c_)) = (find_bytes(body, b"Mdss", 0), find_bytes(body, b"MdCD", 4))
                && s_ + 24 <= body.len()
                && let Some((pts, mut sub_pos)) = decode_mdcd_points(body, c_)
            {
                let m = &body[s_ + 10..];
                let kind_byte = m[0];
                let num_byte = m[1];
                let is_mpe_primary = m.get(7..9) != Some(&[0xFF, 0xFF]);
                let program_banks = if kind_byte == 3 && !pts.is_empty() {
                    Some(
                        pts.iter()
                            .map(|pt| {
                                let v = u32::from_le_bytes((pt[1] as i32).to_le_bytes());
                                let bank = (v >> 8) & 0x3FFF;
                                ProgramBank {
                                    ticks: u64::try_from(pt[0].max(0)).unwrap_or(0),
                                    program: v & 0xFF,
                                    bank_msb: (bank >> 7) & 0x7F,
                                    bank_lsb: bank & 0x7F,
                                }
                            })
                            .collect(),
                    )
                } else {
                    None
                };
                ent.controllers.push(MidiController {
                    kind: ctrl_kind_value(kind_byte),
                    number: num_byte,
                    points: pts,
                    program_banks,
                });

                if is_mpe_primary {
                    while let Some(s_sub) = find_bytes(body, b"Mdss", sub_pos) {
                        let Some(c_sub) = find_bytes(body, b"MdCD", s_sub + 4) else {
                            break;
                        };
                        let Some((sub_pts, next_pos)) = decode_mdcd_points(body, c_sub) else {
                            break;
                        };
                        if s_sub + 24 <= body.len() {
                            let sm = &body[s_sub + 10..];
                            if sm[5] == 4 && sm.get(7..9) != Some(&[0xFF, 0xFF]) {
                                let ns = le_u64(sm, 9, 5).map(plain_ticks).unwrap_or(0);
                                ent.mpe_curves.push(MpeCurve {
                                    kind: ctrl_kind_value(sm[0]),
                                    number: sm[1],
                                    mpe_channel: sm[6],
                                    key: sm[7],
                                    velocity: sm[8],
                                    note_start: ns,
                                    points: sub_pts,
                                });
                            }
                        }
                        sub_pos = next_pos;
                    }
                }
            }
            j_opt = find_bytes(seg, b"MdCDS", j + 1);
        }

        if let Some(tel_at) = find_bytes(seg, b"MdTEL", 0)
            && tel_at + 15 <= seg.len()
            && let Some(tlen) = u32_at(seg, tel_at + 7).and_then(|v| usize::try_from(v).ok())
            && let Some(m) = u32_at(seg, tel_at + 11).and_then(|v| usize::try_from(v).ok())
            && m > 0
        {
            let tend = (tel_at + 11 + tlen).min(seg.len());
            let mut p = tel_at + 15;
            for _ in 0..m {
                if p + 19 > tend {
                    break;
                }
                let Some(raw_t) = le_u64(seg, p, 5) else { break };
                let Some(pay_len) = u32_at(seg, p + 15).and_then(|v| usize::try_from(v).ok()) else {
                    break;
                };
                if p + 19 + pay_len > tend {
                    break;
                }
                let hex = seg[p + 19..p + 19 + pay_len]
                    .iter()
                    .map(|b| format!("{b:02x}"))
                    .collect::<String>();
                ent.sysex.push((plain_ticks(raw_t), hex));
                p += 19 + pay_len;
            }
        }

        out.push(ent);
    }
    out
}
