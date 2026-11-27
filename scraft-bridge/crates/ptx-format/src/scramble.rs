// Version: 0.7.0 (beta) | Date: 2026-11-27
//! Page XOR scrambler/descrambler for `.ptx` files after the 20-byte header (`0x00..0x14`).
//!
//! Byte `0x12` = XOR type (`1` or `5`), byte `0x13` = XOR seed byte.
//! Applying the XOR key table is its own inverse (`descramble` == `scramble`).

use crate::PtxError;

/// Fixed 20-byte `.ptx` file header length (kept unscrambled).
pub const HEADER_LEN: usize = 0x14;

/// Default clean-room 20-byte header for Pro Tools 10+ sessions (`type=5, xor=0`).
pub const DEFAULT_HEADER: [u8; HEADER_LEN] = [
    0x03, b'0', b'0', b'1', b'0', b'1', b'1', b'1', b'1', b'0', b'0', b'1', b'0', b'1', b'0', b'1',
    b'1', 0x00, 0x05, 0x00,
];

fn xor_delta(value: u8, mul: u8, negative: bool) -> Result<u8, PtxError> {
    let s = (0..=255u8)
        .find(|i| i.wrapping_mul(mul) == value)
        .ok_or(PtxError::NoXorDelta(value))?;
    Ok(if negative { s.wrapping_neg() } else { s })
}

fn apply_xor(raw: &[u8]) -> Result<Vec<u8>, PtxError> {
    if raw.len() < HEADER_LEN + 9 {
        return Err(PtxError::TooShort(raw.len()));
    }
    let (Some(&xtype), Some(&xval)) = (raw.get(0x12), raw.get(0x13)) else {
        return Err(PtxError::TooShort(raw.len()));
    };
    let delta = match xtype {
        1 => xor_delta(xval, 53, false)?,
        5 => xor_delta(xval, 11, true)?,
        t => return Err(PtxError::UnknownXorType(t)),
    };
    let key: [u8; 256] = core::array::from_fn(|j| (j as u8).wrapping_mul(delta));
    let mut out = raw.to_vec();
    for (i, b) in out.iter_mut().enumerate().skip(HEADER_LEN) {
        let idx = if xtype == 1 { i & 0xFF } else { (i >> 12) & 0xFF };
        *b ^= key[idx];
    }
    Ok(out)
}

/// Descramble a raw `.ptx` file buffer.
///
/// # Errors
/// Returns [`PtxError::TooShort`], [`PtxError::UnknownXorType`], or [`PtxError::NoXorDelta`].
pub fn descramble(raw: &[u8]) -> Result<Vec<u8>, PtxError> {
    apply_xor(raw)
}

/// Scramble a plain `.ptx` buffer using the XOR parameters in its 20-byte header.
///
/// # Errors
/// Returns [`PtxError::TooShort`], [`PtxError::UnknownXorType`], or [`PtxError::NoXorDelta`].
pub fn scramble(plain: &[u8]) -> Result<Vec<u8>, PtxError> {
    apply_xor(plain)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn with_header(xtype: u8, xval: u8) -> Vec<u8> {
        let mut out = vec![0u8; HEADER_LEN];
        out[0x12] = xtype;
        out[0x13] = xval;
        out
    }

    #[test]
    fn roundtrip_types_1_and_5() {
        for (t, v) in [(1u8, 53u8), (5, 0x00), (5, 0xf5), (5, 0x7f)] {
            let mut raw = with_header(t, v);
            raw.extend((0..9000u32).map(|i| (i % 251) as u8));
            let dec = descramble(&raw);
            assert!(dec.is_ok());
            if let Ok(plain) = dec {
                assert_eq!(&plain[..HEADER_LEN], &raw[..HEADER_LEN]);
                assert_eq!(scramble(&plain), Ok(raw));
            }
        }
    }

    #[test]
    fn rejects_short_or_unknown_type() {
        assert_eq!(descramble(&[0; 5]), Err(PtxError::TooShort(5)));
        let mut raw = with_header(7, 1);
        raw.extend([0; 16]);
        assert_eq!(descramble(&raw), Err(PtxError::UnknownXorType(7)));
    }
}
