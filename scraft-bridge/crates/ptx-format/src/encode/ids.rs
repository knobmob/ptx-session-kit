// Version: 0.7.0 (beta) | Date: 2026-11-23
//! Deterministic `0x5A`-free ID generation for clean-room `.ptx` sessions.

/// Stateful deterministic ID generator guaranteeing no byte equals `0x5A` (`'Z'`),
/// preventing false block-header matches in tolerant scanners.
#[derive(Debug, Clone)]
pub struct IdGen {
    family: [u8; 4],
    counter: u32,
}

impl IdGen {
    /// Create a new ID generator with a safe non-`0x5A` 4-byte family prefix.
    #[must_use]
    pub fn new(family_seed: u32) -> Self {
        let mut f = family_seed.to_le_bytes();
        for b in &mut f {
            if *b == 0x5A || *b == 0x00 {
                *b = 0x5B;
            }
        }
        Self {
            family: f,
            counter: 0x0100,
        }
    }

    /// 4-byte session family prefix.
    #[must_use]
    pub const fn family(&self) -> [u8; 4] {
        self.family
    }

    /// Generate the next 8-byte object ID (`family + counter`), skipping any `0x5A` bytes.
    pub fn next_id8(&mut self) -> [u8; 8] {
        loop {
            self.counter = self.counter.wrapping_add(8);
            let lo = self.counter.to_le_bytes();
            if !lo.contains(&0x5A) {
                let mut out = [0u8; 8];
                out[..4].copy_from_slice(&self.family);
                out[4..8].copy_from_slice(&lo);
                return out;
            }
        }
    }

    /// Generate a track ID + companion playlist ID (`track_id_counter + 1`, no `0x5A`).
    pub fn next_track_pair(&mut self) -> ([u8; 8], [u8; 8]) {
        loop {
            self.counter = self.counter.wrapping_add(8);
            let lo1 = self.counter.to_le_bytes();
            let lo2 = self.counter.wrapping_add(1).to_le_bytes();
            if !lo1.contains(&0x5A) && !lo2.contains(&0x5A) {
                let mut t = [0u8; 8];
                let mut p = [0u8; 8];
                t[..4].copy_from_slice(&self.family);
                t[4..8].copy_from_slice(&lo1);
                p[..4].copy_from_slice(&self.family);
                p[4..8].copy_from_slice(&lo2);
                return (t, p);
            }
        }
    }

    /// Generate a deterministic 16-byte clip/GUID without `0x5A`.
    pub fn next_uuid16(&mut self) -> [u8; 16] {
        let a = self.next_id8();
        let b = self.next_id8();
        let mut out = [0u8; 16];
        out[..8].copy_from_slice(&a);
        out[8..16].copy_from_slice(&b);
        out
    }

    /// Fixed-count UUID list (e.g. 10 slot IDs on a channel strip set).
    pub fn next_uuids(&mut self, n: usize) -> Vec<[u8; 16]> {
        (0..n).map(|_| self.next_uuid16()).collect()
    }
}
