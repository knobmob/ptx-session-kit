// Version: 0.7.0 (beta) | Date: 2026-11-23
//! `0x5A` block tree parser, directory `0x0002` builder, and clean-room block serializer.

use crate::PtxError;
use crate::primitives::{u16_at, u32_at};
use crate::scramble::HEADER_LEN;

const MAX_DEPTH: usize = 64;
const MAX_BLOCKS: usize = 4_000_000;

/// Known content types (`tools/ptx_probe.py`) used to reject false `0x5A` matches inside opaque blobs.
pub const KNOWN_CTS: &[u16] = &[
    0x0000, 0x0002, 0x0003, 0x0F3C, 0x0F3D, 0x0F3E, 0x1000, 0x1001, 0x1003, 0x1004, 0x1006,
    0x1014, 0x1015, 0x1017, 0x1018, 0x1021, 0x1022, 0x1028, 0x1029, 0x102A, 0x102D, 0x1033,
    0x1038, 0x103A, 0x103D, 0x103E, 0x103F, 0x1040, 0x1041, 0x1042, 0x1045, 0x1048, 0x1049,
    0x104A, 0x104B, 0x104C, 0x104D, 0x104F, 0x1050, 0x1052, 0x1054, 0x1055, 0x1056, 0x1057,
    0x1058, 0x1059, 0x2000, 0x2004, 0x2005, 0x2006, 0x200A, 0x200B, 0x200C, 0x200D, 0x2010,
    0x2011, 0x2013, 0x2015, 0x2016, 0x2017, 0x2018, 0x2019, 0x201A, 0x201B, 0x201C, 0x201D,
    0x201E, 0x201F, 0x2020, 0x2021, 0x2023, 0x2024, 0x2025, 0x2026, 0x2027, 0x2028, 0x2029,
    0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2030, 0x2031, 0x2032, 0x2033, 0x2036, 0x2037,
    0x2038, 0x203A, 0x203B, 0x203C, 0x203D, 0x203E, 0x2047, 0x2049, 0x204A, 0x204B, 0x204D,
    0x2050, 0x2055, 0x2056, 0x2058, 0x205E, 0x205F, 0x2062, 0x2063, 0x2064, 0x2066, 0x2067,
    0x2068, 0x2069, 0x206A, 0x206B, 0x206C, 0x206D, 0x206E, 0x206F, 0x2070, 0x2071, 0x2072,
    0x2073, 0x2074, 0x2077, 0x2078, 0x207A, 0x207B, 0x207E, 0x2086, 0x208C, 0x208E, 0x208F,
    0x2096, 0x2097, 0x2098, 0x2099, 0x209F, 0x20A0, 0x20A1, 0x20A2, 0x2103, 0x2104, 0x2106,
    0x2107, 0x210B, 0x210C, 0x2203, 0x2301, 0x2302, 0x2305, 0x230A, 0x230B, 0x2423, 0x2424,
    0x2425, 0x2426, 0x2428, 0x242B, 0x242E, 0x242F, 0x2430, 0x2432, 0x2433, 0x2434, 0x2435,
    0x2437, 0x2501, 0x2502, 0x2504, 0x2505, 0x2506, 0x2507, 0x2508, 0x2509, 0x2510, 0x2511,
    0x2516, 0x2519, 0x251A, 0x251B, 0x251C, 0x2523, 0x2526, 0x252A, 0x252C, 0x2530, 0x2550,
    0x2551, 0x2552, 0x2553, 0x2554, 0x2556, 0x2557, 0x255F, 0x2567, 0x2580, 0x2581, 0x2582,
    0x2583, 0x2585, 0x2587, 0x2588, 0x2589, 0x258A, 0x258B, 0x258C, 0x258E, 0x258F, 0x2595,
    0x2597, 0x259B, 0x259C, 0x25C0, 0x2600, 0x2601, 0x2602, 0x2603, 0x2604, 0x260A, 0x260B,
    0x260C, 0x260D, 0x260E, 0x260F, 0x2611, 0x2613, 0x2614, 0x2615, 0x2616, 0x2617, 0x2619,
    0x261B, 0x261C, 0x261D, 0x261E, 0x2620, 0x2621, 0x2624, 0x2625, 0x2626, 0x2627, 0x2628,
    0x2629, 0x262A, 0x262B, 0x262C, 0x262E, 0x262F, 0x2630, 0x2632, 0x2633, 0x2634, 0x2636,
    0x2637, 0x263B, 0x2701, 0x270A, 0x270D, 0x2710, 0x2715, 0x2716, 0x2718, 0x2719, 0x271A,
    0x271B, 0x271C, 0x271F, 0x2721, 0x2A00, 0x4000, 0x4300, 0x4301, 0x4400, 0x4403, 0x4420,
    0x4421, 0x4422, 0x4501, 0x4530, 0x4701, 0x4702, 0x4807, 0x4808, 0x4809, 0x4820, 0x4823,
    0x4824, 0x4826, 0x4827, 0x4828, 0x4829, 0x4833, 0x4834, 0x483B, 0x483D, 0x4842, 0x4843,
    0x4845, 0x4846, 0x4847, 0x4848, 0x4849, 0x484D, 0x484E, 0x484F, 0x4850, 0x4852, 0x4856,
    0x485A, 0x485D, 0xFFFF,
];

fn is_known_child(bt: u16, ct: u16) -> bool {
    if bt > 64 {
        return false;
    }
    if KNOWN_CTS.contains(&ct) {
        return true;
    }
    matches!(
        ct >> 8,
        0x00 | 0x0F | 0x10 | 0x20 | 0x21 | 0x22 | 0x23 | 0x24 | 0x25 | 0x26 | 0x27 | 0x2A | 0x40
            | 0x43 | 0x44 | 0x45 | 0x47 | 0x48 | 0xFF
    )
}

/// One `0x5A` block in a `.ptx` tree.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Block {
    /// Block type (`u16` at `+1`).
    pub block_type: u16,
    /// Content type (`u16` at `+7`).
    pub content_type: u16,
    /// Byte offset of `0x5A` in the descrambled file.
    pub pos: usize,
    /// Payload size field (`u32` at `+3`: includes the 2-byte `content_type` plus data).
    pub size: usize,
    /// Nested child blocks.
    pub kids: Vec<Block>,
}

impl Block {
    /// First data byte after the 9-byte header.
    #[must_use]
    pub const fn data_start(&self) -> usize {
        self.pos.saturating_add(9)
    }

    /// One byte past the end of this block (`pos + 7 + size`).
    #[must_use]
    pub const fn end(&self) -> usize {
        self.pos.saturating_add(7).saturating_add(self.size)
    }

    /// Data slice (`d[pos + 9 .. end]`), clamped safely.
    #[must_use]
    pub fn data<'a>(&self, d: &'a [u8]) -> &'a [u8] {
        let s = self.data_start().min(d.len());
        let e = self.end().min(d.len());
        &d[s..e]
    }

    /// Total number of blocks in a forest.
    #[must_use]
    pub fn count(nodes: &[Block]) -> usize {
        nodes.iter().map(|n| 1 + Self::count(&n.kids)).sum()
    }

    /// First block matching `content_type` in depth-first file order.
    #[must_use]
    pub fn find(nodes: &[Block], ct: u16) -> Option<&Block> {
        nodes.iter().find_map(|n| {
            if n.content_type == ct {
                Some(n)
            } else {
                Self::find(&n.kids, ct)
            }
        })
    }

    /// Depth-first walk collecting all blocks in `nodes`.
    pub fn walk<'a>(nodes: &'a [Block], out: &mut Vec<&'a Block>) {
        for n in nodes {
            out.push(n);
            Self::walk(&n.kids, out);
        }
    }

    /// Return all blocks in `nodes` in depth-first file order.
    #[must_use]
    pub fn walk_all(nodes: &[Block]) -> Vec<&Block> {
        let mut out = Vec::new();
        Self::walk(nodes, &mut out);
        out
    }
}

const fn is_flat_ct(ct: u16) -> bool {
    matches!(ct, 0x0002 | 0x1028 | 0x204D | 0x260A | 0x262F | 0x2637)
}

const fn raw_prefix_len(ct: u16) -> usize {
    match ct {
        0x1054 => 4,
        _ => 0,
    }
}

fn parse_range(
    d: &[u8],
    mut pos: usize,
    end: usize,
    depth: usize,
    strict: bool,
    budget: &mut usize,
) -> Result<Vec<Block>, PtxError> {
    if depth > MAX_DEPTH {
        return Err(PtxError::Limit("block nesting deeper than 64"));
    }
    let mut out = Vec::new();
    while pos < end {
        if d.get(pos) != Some(&0x5A) || pos + 9 > end {
            pos += 1;
            continue;
        }
        let (Some(bt), Some(sz_u32), Some(ct)) =
            (u16_at(d, pos + 1), u32_at(d, pos + 3), u16_at(d, pos + 7))
        else {
            pos += 1;
            continue;
        };
        let Ok(size) = usize::try_from(sz_u32) else {
            pos += 1;
            continue;
        };
        let block_end = pos.saturating_add(7).saturating_add(size);
        if size < 2 || block_end > end || (strict && !is_known_child(bt, ct)) {
            pos += 1;
            continue;
        }
        *budget = budget
            .checked_sub(1)
            .ok_or(PtxError::Limit("more than 4 000 000 blocks"))?;
        let child_start = pos.saturating_add(9).saturating_add(raw_prefix_len(ct));
        let kids = if is_flat_ct(ct) || child_start > block_end {
            Vec::new()
        } else {
            parse_range(d, child_start, block_end, depth + 1, true, budget)?
        };
        out.push(Block {
            block_type: bt,
            content_type: ct,
            pos,
            size,
            kids,
        });
        pos = block_end;
    }
    Ok(out)
}

/// Parse all top-level blocks after the 20-byte header.
///
/// # Errors
/// Returns [`PtxError::Limit`] or [`PtxError::Layout`] if no valid blocks exist.
pub fn parse_blocks(data: &[u8]) -> Result<Vec<Block>, PtxError> {
    if data.len() < HEADER_LEN + 9 {
        return Err(PtxError::TooShort(data.len()));
    }
    let mut budget = MAX_BLOCKS;
    let tree = parse_range(data, HEADER_LEN, data.len(), 0, false, &mut budget)?;
    if tree.is_empty() {
        return Err(PtxError::Layout {
            what: "no block after the header",
            offset: HEADER_LEN,
        });
    }
    Ok(tree)
}

/// Serialize a clean-room `0x5A` block (`5A | u16 bt | u32 (2 + payload) | u16 ct | payload`).
#[must_use]
pub fn encode_block(bt: u16, ct: u16, payload: &[u8]) -> Vec<u8> {
    let size = u32::try_from(payload.len().saturating_add(2)).unwrap_or(u32::MAX);
    let mut out = Vec::with_capacity(9 + payload.len());
    out.push(0x5A);
    out.extend_from_slice(&bt.to_le_bytes());
    out.extend_from_slice(&size.to_le_bytes());
    out.extend_from_slice(&ct.to_le_bytes());
    out.extend_from_slice(payload);
    out
}

/// Directory `0x0002` payload builder matching `tools/ptx_edit.py`'s `_dir_build` layout.
#[must_use]
pub fn build_directory_0002(tree: &[Block]) -> Vec<u8> {
    const DIR_NONE: u32 = u32::MAX;
    const DIR_FIXED: &[&[u16]] = &[
        &[0x1015, 0x4829],
        &[0x1054, 0x4828],
        &[0x2016, 0x258b, 0x2501],
        &[0x2016, 0x258b, 0x258a, 0x2581, 0x2056],
        &[0x2016, 0x258b, 0x258a, 0x2581, 0x2066],
        &[0x206a, 0x2074],
        &[0x207b, 0x4530],
        &[0x2428, 0x1054],
        &[0x2428, 0x1054, 0x4828],
        &[0x242e, 0x1058],
        &[0x2430, 0x1055],
        &[0x2587, 0x2551, 0x258b, 0x2501],
        &[0x2587, 0x2551, 0x258b, 0x2553, 0x2583, 0x2581, 0x2056],
        &[0x2587, 0x2551, 0x258b, 0x2553, 0x2583, 0x2581, 0x2066],
        &[0x2587, 0x2551, 0x258b, 0x258a, 0x2581, 0x2056],
        &[0x2587, 0x2551, 0x258b, 0x258a, 0x2581, 0x2066],
        &[0x2597, 0x2588, 0x2056],
        &[0x2597, 0x2588, 0x2066],
    ];

    fn list_child_ct(ct: u16) -> Option<Option<u16>> {
        match ct {
            0x0f3d => Some(Some(0x0f3c)),
            0x1015 => Some(Some(0x1014)),
            0x1054 => Some(Some(0x1052)),
            0x1055 | 0x4828 | 0x4829 => Some(None),
            0x1058 => Some(Some(0x1057)),
            0x2424 => Some(Some(0x2423)),
            0x2426 => Some(Some(0x2425)),
            0x2519 => Some(Some(0x251a)),
            0x251b => Some(Some(0x251c)),
            0x2624 => Some(Some(u16::MAX)), // sentinel for "all"
            _ => None,
        }
    }

    fn dir_ref(positions: &[u32]) -> Vec<u8> {
        let len_bytes = u16::try_from(4 * positions.len()).unwrap_or(0);
        let cnt = u16::try_from(positions.len()).unwrap_or(0);
        let mut out = Vec::with_capacity(5 + 4 * positions.len() + 6);
        out.push(0x01);
        out.extend_from_slice(&len_bytes.to_le_bytes());
        out.extend_from_slice(&cnt.to_le_bytes());
        for &p in positions {
            out.extend_from_slice(&p.to_le_bytes());
        }
        out.extend_from_slice(&[0u8; 6]);
        out
    }

    fn dir_kid(n: &Block, ct: u16) -> Option<&Block> {
        n.kids.iter().find(|k| k.content_type == ct)
    }

    fn split_251a(n: &Block) -> (Vec<&Block>, Vec<&Block>) {
        let a: Vec<&Block> = n.kids.iter().filter(|k| k.content_type == 0x251a).collect();
        for i in 1..a.len() {
            let prev = a[i - 1];
            let prev_end = prev.pos + 7 + prev.size;
            if a[i].pos.saturating_sub(prev_end) == 4 {
                return (a[..i].to_vec(), a[i..].to_vec());
            }
        }
        (Vec::new(), a)
    }

    type PathElem = (u16, u32, u8, u32);
    type DirRec = (Vec<PathElem>, Vec<Vec<u8>>);
    let mut recs: Vec<DirRec> = Vec::new();
    let mut tops: Vec<(u16, &Block)> = Vec::new();
    let end_idx = tree.len().saturating_sub(1);
    for n in &tree[..end_idx] {
        if n.pos > HEADER_LEN && !tops.iter().any(|(ct, _)| *ct == n.content_type) {
            tops.push((n.content_type, n));
        }
    }
    let find_top = |ct: u16| tops.iter().find(|(t, _)| *t == ct).map(|(_, b)| *b);

    for &(ct, n) in &tops {
        let fl = u8::from(list_child_ct(ct).is_some());
        let mut refs = vec![dir_ref(&[u32::try_from(n.pos).unwrap_or(0)])];
        if ct == 0x2519 {
            let (_, items) = split_251a(n);
            for k in items {
                refs.push(dir_ref(&[u32::try_from(k.pos).unwrap_or(0)]));
            }
        } else if let Some(Some(lct)) = list_child_ct(ct) {
            for k in &n.kids {
                if lct == u16::MAX || k.content_type == lct {
                    refs.push(dir_ref(&[u32::try_from(k.pos).unwrap_or(0)]));
                }
            }
        }
        recs.push((vec![(ct, DIR_NONE, fl, 0)], refs));
    }

    for &path in DIR_FIXED {
        let Some(mut cur) = find_top(path[0]) else {
            continue;
        };
        let fl0 = u8::from(list_child_ct(path[0]).is_some());
        let mut el = vec![(path[0], DIR_NONE, fl0, 0)];
        let mut ok = true;
        for &ct in &path[1..] {
            let Some(c) = dir_kid(cur, ct) else {
                ok = false;
                break;
            };
            let fl = u8::from(list_child_ct(ct).is_some());
            el.push((ct, u32::try_from(cur.pos).unwrap_or(0), fl, 0));
            cur = c;
        }
        if ok && el.len() == path.len() {
            let mut refs = vec![dir_ref(&[u32::try_from(cur.pos).unwrap_or(0)])];
            if let Some(&last_ct) = path.last()
                && let Some(Some(lct)) = list_child_ct(last_ct)
                && lct != u16::MAX
            {
                for k in &cur.kids {
                    if k.content_type == lct {
                        refs.push(dir_ref(&[u32::try_from(k.pos).unwrap_or(0)]));
                    }
                }
            }
            recs.push((el, refs));
        }
    }

    if let Some(n) = find_top(0x1040) {
        let aa: Vec<&Block> = n.kids.iter().filter(|x| x.content_type == 0x1041).collect();
        if let Some(a) = aa.last() {
            let k2: Vec<u32> = aa
                .iter()
                .flat_map(|y| y.kids.iter().filter(|x| x.content_type == 0x1042))
                .map(|x| u32::try_from(x.pos).unwrap_or(0))
                .collect();
            recs.push((
                vec![
                    (0x1040, DIR_NONE, 0, 0),
                    (0x1041, u32::try_from(n.pos).unwrap_or(0), 0, 0),
                    (0x1042, u32::try_from(a.pos).unwrap_or(0), 0, 0),
                ],
                vec![dir_ref(&k2)],
            ));
        }
    }

    if let Some(n) = find_top(0x2519) {
        let npos = u32::try_from(n.pos).unwrap_or(0);
        let (ga, gb) = split_251a(n);
        let h = u32::try_from(gb.len()).unwrap_or(0);
        let ga_pos: Vec<u32> = ga.iter().map(|x| u32::try_from(x.pos).unwrap_or(0)).collect();
        recs.push((vec![(0x2519, DIR_NONE, 0, 0), (0x251a, npos, 0, 0)], vec![dir_ref(&ga_pos)]));
        for (idx, k) in gb.iter().enumerate() {
            let i = u32::try_from(idx + 1).unwrap_or(0);
            recs.push((
                vec![(0x2519, DIR_NONE, 1, i), (0x251a, npos, 0, 0)],
                vec![dir_ref(&[u32::try_from(k.pos).unwrap_or(0)])],
            ));
        }
        if let Some(b) = dir_kid(n, 0x251b) {
            let bpos = u32::try_from(b.pos).unwrap_or(0);
            let cs: Vec<&Block> = b.kids.iter().filter(|x| x.content_type == 0x251c).collect();
            let mut b_refs = vec![dir_ref(&[bpos])];
            for x in &cs {
                b_refs.push(dir_ref(&[u32::try_from(x.pos).unwrap_or(0)]));
            }
            recs.push((vec![(0x2519, DIR_NONE, 1, h), (0x251b, npos, 1, 0)], b_refs));
            for (jdx, x) in cs.iter().enumerate() {
                let j = u32::try_from(jdx + 1).unwrap_or(0);
                recs.push((
                    vec![(0x2519, DIR_NONE, 1, h), (0x251b, npos, 1, j), (0x251c, bpos, 0, 0)],
                    vec![dir_ref(&[u32::try_from(x.pos).unwrap_or(0)])],
                ));
            }
        }
        if let Some(c) = dir_kid(n, 0x2716) {
            recs.push((
                vec![(0x2519, DIR_NONE, 1, h), (0x2716, npos, 0, 0)],
                vec![dir_ref(&[u32::try_from(c.pos).unwrap_or(0)])],
            ));
        }
    }

    if let Some(n) = find_top(0x2624) {
        let npos = u32::try_from(n.pos).unwrap_or(0);
        for (idx, k) in n.kids.iter().enumerate() {
            let i = u32::try_from(idx + 1).unwrap_or(0);
            let kpos = u32::try_from(k.pos).unwrap_or(0);
            if k.content_type == 0x2621 {
                if let Some(t) = dir_kid(k, 0x2627) {
                    recs.push((
                        vec![(0x2624, DIR_NONE, 1, i), (0x2621, npos, 0, 0), (0x2627, kpos, 0, 0)],
                        vec![dir_ref(&[u32::try_from(t.pos).unwrap_or(0)])],
                    ));
                }
            } else if let Some(b) = dir_kid(k, 0x261b)
                && let Some(t) = dir_kid(b, 0x2627)
            {
                let bpos = u32::try_from(b.pos).unwrap_or(0);
                recs.push((
                    vec![
                        (0x2624, DIR_NONE, 1, i),
                        (k.content_type, npos, 0, 0),
                        (0x261b, kpos, 0, 0),
                        (0x2627, bpos, 0, 0),
                    ],
                    vec![dir_ref(&[u32::try_from(t.pos).unwrap_or(0)])],
                ));
            }
        }
    }

    recs.sort_by(|a, b| {
        a.0.iter()
            .map(|e| (e.0, e.3))
            .cmp(b.0.iter().map(|e| (e.0, e.3)))
    });

    let mut payload = Vec::new();
    payload.extend_from_slice(&u32::try_from(recs.len()).unwrap_or(0).to_le_bytes());
    for (path, refs) in &recs {
        payload.extend_from_slice(&u32::try_from(path.len()).unwrap_or(0).to_le_bytes());
        for &(ct, ppos, fl, ix) in path {
            payload.extend_from_slice(&ct.to_le_bytes());
            payload.extend_from_slice(&ppos.to_le_bytes());
            payload.push(fl);
            payload.extend_from_slice(&ix.to_le_bytes());
        }
        payload.extend_from_slice(&u32::try_from(refs.len()).unwrap_or(0).to_le_bytes());
        for r in refs {
            payload.extend_from_slice(r);
        }
    }
    payload
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::decode::clips::parse_fades;
    use crate::decode::mixer::parse_lane;
    use crate::decode::timeline::parse_markers;
    use crate::decode::decode_bytes;
    use crate::encode::encode_ptx;
    use crate::encode::spec::{BuildMarker, BuildTrack, BuildTrackKind, PtxBuildSpec};
    use crate::scramble::{descramble, HEADER_LEN};

    #[test]
    fn flat_cts_and_1054_count_90_ignore_false_5a_while_104f_keeps_242b() -> Result<(), PtxError> {
        let mut buf = vec![0u8; HEADER_LEN];
        // Build 0x104F containing a valid 0x242B child (strict=true child inside 0x104F)
        let child_242b = encode_block(2, 0x242b, &[0u8; 57]);
        let mut p104f = vec![0u8; 18];
        p104f.extend_from_slice(&child_242b);
        let blk_104f = encode_block(10, 0x104f, &p104f);

        // Build 0x1054 starting with playlist_count == 90 (0x5A 00 00 00) followed by valid 0x1052
        let mut p1054 = 90u32.to_le_bytes().to_vec();
        let blk_1052 = encode_block(3, 0x1052, &[1, 0, 0, 0, b'A', 0, 0, 0, 0]);
        p1054.extend_from_slice(&blk_1052);
        let blk_1054 = encode_block(2, 0x1054, &p1054);

        // Build flat 0x0002 containing a coincidental 0x5A block pattern
        let fake_kid = encode_block(2, 0x0000, &[0xAAu8; 16]);
        let mut p0002 = vec![0u8; 8];
        p0002.extend_from_slice(&fake_kid);
        let blk_0002 = encode_block(2, 0x0002, &p0002);

        buf.extend_from_slice(&blk_104f);
        buf.extend_from_slice(&blk_1054);
        buf.extend_from_slice(&blk_0002);
        let tree = parse_blocks(&buf)?;
        assert_eq!(tree.len(), 3);
        assert_eq!(tree[0].kids.len(), 1);
        assert_eq!(tree[0].kids[0].content_type, 0x242b);
        assert_eq!(tree[1].kids.len(), 1);
        assert_eq!(tree[1].kids[0].content_type, 0x1052);
        assert!(tree[2].kids.is_empty());
        Ok(())
    }

    #[test]
    fn parse_fades_maps_fade_out_and_crossfade() {
        let mut fo = vec![0, 0, 0, 0, 0, 0x22, 0, 0];
        fo.extend_from_slice(&480u16.to_le_bytes());
        fo.extend_from_slice(&480u16.to_le_bytes());
        fo.extend_from_slice(&[2, 1]);
        fo.extend_from_slice(&0.0f32.to_le_bytes());
        fo.extend_from_slice(&[0u8; 9]);

        let mut xf = vec![0, 0, 0, 0, 0, 0x22, 0, 0];
        xf.extend_from_slice(&120u16.to_le_bytes());
        xf.extend_from_slice(&240u16.to_le_bytes());
        xf.extend_from_slice(&[1, 2]);
        xf.extend_from_slice(&0.0f32.to_le_bytes());
        xf.extend_from_slice(&[0u8; 12]);

        let mut buf = vec![0u8; HEADER_LEN];
        buf.extend_from_slice(&encode_block(2, 0x262f, &fo));
        buf.extend_from_slice(&encode_block(2, 0x262f, &xf));
        if let Ok(tree) = parse_blocks(&buf) {
            let fades = parse_fades(&buf, &tree);
            assert_eq!(fades.len(), 2);
            assert_eq!(fades[0].fade_type, serde_json::Value::from("fade_out"));
            assert_eq!(fades[0].length, 480);
            assert_eq!(fades[0].length2, Some(480));
            assert_eq!(fades[1].fade_type, serde_json::Value::from("crossfade"));
            assert_eq!(fades[1].length, 120);
            assert_eq!(fades[1].length2, Some(240));
        }
    }

    #[test]
    fn parse_markers_handles_tag1_tag2_and_tag9() {
        let make_mk = |tag: u32, extra_pad: usize, comment: &[u8]| -> Vec<u8> {
            let mut p = Vec::new();
            p.extend_from_slice(&1u16.to_le_bytes());
            p.extend_from_slice(&[1, 1, 0, 0]);
            p.extend_from_slice(&1u32.to_le_bytes());
            p.push(b'M');
            p.extend_from_slice(&[0u8; 7]);
            p.push(0x40);
            p.extend_from_slice(&[0u8; 7]);
            p.push(0x40);
            p.extend_from_slice(&[0u8; 50]);
            p.extend_from_slice(&0u32.to_le_bytes()); // nt = 0
            p.extend_from_slice(&tag.to_le_bytes());
            p.extend(std::iter::repeat_n(0u8, extra_pad));
            p.extend_from_slice(&(u32::try_from(comment.len()).unwrap_or(0)).to_le_bytes());
            p.extend_from_slice(comment);
            encode_block(0x12, 0x2077, &p)
        };
        let mut p30 = 3u32.to_le_bytes().to_vec();
        p30.extend_from_slice(&make_mk(1, 1, b"legacy"));
        p30.extend_from_slice(&make_mk(2, 2, b"pt2026"));
        p30.extend_from_slice(&make_mk(9, 1, b"ignored"));
        let mut buf = vec![0u8; HEADER_LEN];
        buf.extend_from_slice(&encode_block(5, 0x2030, &p30));
        if let Ok(tree) = parse_blocks(&buf) {
            let mut warn = Vec::new();
            let mks = parse_markers(&buf, &tree, &mut warn);
            assert_eq!(mks.len(), 3);
            assert_eq!(mks[0].comment.as_deref(), Some("legacy"));
            assert_eq!(mks[1].comment.as_deref(), Some("pt2026"));
            assert_eq!(mks[2].comment.as_deref(), Some(""));
        }
    }

    #[test]
    fn sample_lane_gt_65536_segments_and_251c_marker_flag() -> Result<(), Box<dyn std::error::Error>> {
        // 1) Test 0x260A sample lane with segs == 70_000 (> u16::MAX)
        let n_pts = 70_001usize;
        let mut p = vec![0x01, 0x46, 0x01, 0x00];
        p.extend_from_slice(&((14 + 6 * n_pts) as u32).to_le_bytes());
        p.extend_from_slice(&0u16.to_le_bytes()); // tb = 0 (samples)
        p.extend_from_slice(&(n_pts as u32).to_le_bytes());
        p.extend_from_slice(&2u16.to_le_bytes());
        p.extend_from_slice(&((n_pts - 1) as u32).to_le_bytes()); // +16 u32 segs
        p.extend_from_slice(&0u16.to_le_bytes()); // +20 u16 0
        p.extend_from_slice(&123u32.to_le_bytes()); // +22 u32 pos0
        p.extend_from_slice(&(-50i16).to_le_bytes());
        for k in 1..n_pts {
            p.extend_from_slice(&(123u32 + k as u32).to_le_bytes());
            p.extend_from_slice(&0i16.to_le_bytes());
        }
        p.extend_from_slice(&0u16.to_le_bytes());
        let mut buf = vec![0u8; HEADER_LEN];
        buf.extend_from_slice(&encode_block(1, 0x260a, &p));
        let tree = parse_blocks(&buf)?;
        let decoded = parse_lane(&buf, &tree[0]);
        assert_eq!(decoded.as_ref().map(|v| (v.len(), v[0])), Some((n_pts, (123, -50))));

        // 2) Verify 0x251C[0][6] sets 1 for markers, 0 for colour-only
        let spec_mk = PtxBuildSpec {
            markers: vec![BuildMarker {
                number: 1,
                name: "M1".to_owned(),
                start: 0,
                end: 0,
                is_ticks: false,
                is_selection: false,
                comment: String::new(),
            }],
            ..PtxBuildSpec::default()
        };
        let b_mk = encode_ptx(&spec_mk)?;
        let d_mk = descramble(&b_mk)?;
        let t_mk = parse_blocks(&d_mk)?;
        let c0_mk = Block::find(&t_mk, 0x251b).and_then(|b| b.kids.first());
        assert_eq!(c0_mk.and_then(|c| c.data(&d_mk).get(6).copied()), Some(1));
        assert_eq!(decode_bytes("mk_flag.ptx", &b_mk)?.markers.len(), 1);

        let spec_col = PtxBuildSpec {
            tracks: vec![BuildTrack {
                name: "Audio 1".to_owned(),
                kind: BuildTrackKind::Audio,
                colour: Some(29),
                ..BuildTrack::default()
            }],
            ..PtxBuildSpec::default()
        };
        let d_col = descramble(&encode_ptx(&spec_col)?)?;
        let t_col = parse_blocks(&d_col)?;
        let c0_col = Block::find(&t_col, 0x251b).and_then(|b| b.kids.first());
        assert_eq!(c0_col.and_then(|c| c.data(&d_col).get(6).copied()), Some(0));
        Ok(())
    }

    #[test]
    fn parse_regions_reads_sync_offset_b2_low_nibble_lt_and_gt_65k() -> Result<(), Box<dyn std::error::Error>> {
        let mut r_lt = Vec::new();
        r_lt.extend_from_slice(&u32::try_from(9).unwrap_or(0).to_le_bytes());
        r_lt.extend_from_slice(b"SyncLT65k");
        // flag=0, b1=0x20 (W1=2B), b2=0x32 (W2=3B, sync=2B), b3=0x22 (W3=2B, W4=2B), ex=8
        r_lt.extend_from_slice(&[0x00, 0x20, 0x32, 0x22, 0x08]);
        r_lt.extend_from_slice(&5_000u16.to_le_bytes()); // W1
        r_lt.extend_from_slice(&10_000u16.to_le_bytes()); // sync_offset < 65k
        r_lt.extend_from_slice(&130_000u32.to_le_bytes()[..3]); // W2
        r_lt.extend_from_slice(&5_000u16.to_le_bytes()); // W3
        r_lt.extend_from_slice(&5_000u16.to_le_bytes()); // W4

        let mut r_gt = Vec::new();
        r_gt.extend_from_slice(&u32::try_from(9).unwrap_or(0).to_le_bytes());
        r_gt.extend_from_slice(b"SyncGT65k");
        // flag=0, b1=0x20, b2=0x33 (W2=3B, sync=3B), b3=0x22, ex=8
        r_gt.extend_from_slice(&[0x00, 0x20, 0x33, 0x22, 0x08]);
        r_gt.extend_from_slice(&5_000u16.to_le_bytes());
        r_gt.extend_from_slice(&80_000u32.to_le_bytes()[..3]); // sync_offset > 65k
        r_gt.extend_from_slice(&130_000u32.to_le_bytes()[..3]);
        r_gt.extend_from_slice(&5_000u16.to_le_bytes());
        r_gt.extend_from_slice(&5_000u16.to_le_bytes());

        let w0 = encode_block(0x0b, 0x2629, &encode_block(5, 0x2628, &r_lt));
        let w1 = encode_block(0x0b, 0x2629, &encode_block(5, 0x2628, &r_gt));
        let mut p2a = Vec::new();
        p2a.extend_from_slice(&2u32.to_le_bytes());
        p2a.extend_from_slice(&w0);
        p2a.extend_from_slice(&w1);
        let b2a = encode_block(1, 0x262a, &p2a);
        let mut d = vec![0u8; 20];
        d.extend_from_slice(&b2a);
        let t = parse_blocks(&d)?;
        let mut warn = Vec::new();
        let (regs, _) = crate::decode::clips::parse_regions(&d, &t, &mut warn);
        assert!(warn.is_empty(), "{warn:?}");
        assert_eq!(regs.len(), 2);
        assert_eq!(regs[0].sync_offset, Some(10_000));
        assert_eq!(regs[0].start, 5_000);
        assert_eq!(regs[0].length, 130_000);
        assert_eq!(regs[1].sync_offset, Some(80_000));
        assert_eq!(regs[1].length, 130_000);
        Ok(())
    }

    #[test]
    fn parse_tracks_handles_non_3_pre_prefix_and_mxf_sd2_stems() -> Result<(), Box<dyn std::error::Error>> {
        let mut p2519 = vec![0u8; 10];
        p2519.extend_from_slice(&1u32.to_le_bytes()); // pre = 1
        p2519.extend_from_slice(&17u16.to_le_bytes()); // value != 3 (e.g. PT 2026.4 0x0011)
        p2519.extend_from_slice(&1u32.to_le_bytes()); // 1 track
        p2519.extend_from_slice(&0u16.to_le_bytes()); // Audio
        p2519.extend_from_slice(&4u32.to_le_bytes());
        p2519.extend_from_slice(b"sine");
        p2519.extend_from_slice(&[0u8; 6]);
        p2519.extend_from_slice(&[0x2a, 0x00, 0x00, 0x00, 1, 2, 3, 4, 5, 6, 7, 8, 1, 0, 0]);
        let b2519 = encode_block(9, 0x2519, &p2519);

        let mut p103a = Vec::new();
        for s in ["Audio Files", "Fade Files", "sine.mxf", "drum.sd2"] {
            p103a.extend_from_slice(&u32::try_from(s.len()).unwrap_or(0).to_le_bytes());
            p103a.extend_from_slice(s.as_bytes());
            p103a.extend_from_slice(&[0u8; 8]);
        }
        let b103a = encode_block(1, 0x103A, &p103a);
        let mut p1004 = b103a;
        p1004.extend_from_slice(&encode_block(1, 0x1003, &[0x06, 0x0a, 0x2b, 0x34]));
        p1004.extend_from_slice(&encode_block(1, 0x1003, &[0x06, 0x0a, 0x2b, 0x34]));
        let b1004 = encode_block(1, 0x1004, &p1004);

        let mut d = vec![0u8; 20];
        d.extend_from_slice(&b2519);
        d.extend_from_slice(&b1004);
        let t = parse_blocks(&d)?;
        let mut warn = Vec::new();
        let tr = crate::decode::tracks::parse_tracks(&d, &t, &mut warn);
        assert!(warn.is_empty(), "{warn:?}");
        assert_eq!(tr.len(), 1);
        assert_eq!(tr[0].name, "sine");

        let stems = crate::decode::clips::parse_audio_file_stems(&d, &t);
        assert_eq!(stems, vec!["sine".to_owned(), "drum".to_owned()]);
        let exts = crate::decode::clips::parse_audio_file_exts(&d, &t);
        assert_eq!(exts.get("sine").map(String::as_str), Some("mxf"));
        assert_eq!(exts.get("drum").map(String::as_str), Some("sd2"));
        let umids = crate::decode::clips::parse_umids(&d, &t);
        assert!(umids.contains_key("sine"));
        assert!(umids.contains_key("drum"));
        Ok(())
    }
}
