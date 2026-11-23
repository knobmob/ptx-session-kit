// Version: 0.7.0 (beta) | Date: 2026-11-23
//! Errors for the clean-room Pro Tools `.ptx` reader and writer.

/// Errors returned when parsing, validating, or building `.ptx` binary sessions.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum PtxError {
    /// I/O error reading or writing a session or media file.
    #[error("cannot access file: {0}")]
    Io(String),
    /// Shorter than the 20-byte header plus one block.
    #[error("file too short ({0} bytes): not a Pro Tools session")]
    TooShort(usize),
    /// XOR type byte (`0x12`) is not one of the known types `1` or `5`.
    #[error("unknown scrambling type {0} (known: 1, 5)")]
    UnknownXorType(u8),
    /// No step byte yields the stored XOR value (`0x13`).
    #[error("no scrambling step for value {0}: damaged or not a .ptx")]
    NoXorDelta(u8),
    /// Block tree or record count exceeds defensive limits.
    #[error("limit exceeded: {0}")]
    Limit(&'static str),
    /// A binary structure did not match its expected layout.
    #[error("unexpected layout at byte {offset}: {what}")]
    Layout {
        /// Description of the expected structure.
        what: &'static str,
        /// Byte offset in the descrambled payload.
        offset: usize,
    },
    /// Feature or parameter outside clean-room writer bounds.
    #[error("unsupported write operation: {0}")]
    Unsupported(String),
}
