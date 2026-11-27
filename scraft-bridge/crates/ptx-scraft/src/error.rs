// Version: 0.7.0 (beta) | Date: 2026-11-27
//! Error types for `.ptx` <-> `.scraft` conversion.

use thiserror::Error;

/// Errors raised while converting between `.ptx` and `.scraft`.
#[derive(Debug, Error)]
pub enum ConvertError {
    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),

    #[error("PTX format error: {0}")]
    Ptx(#[from] ptx_format::PtxError),

    #[error("SoundCraft session error: {0}")]
    Session(#[from] craft_scraft_format::SessionError),

    #[error("audio metadata error: {0}")]
    Audio(String),

    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),

    #[error("strict conversion refused lossy item: {0}")]
    Strict(String),

    #[error("missing audio file '{name}': {detail}")]
    MissingMedia { name: String, detail: String },
}
