# Reference Review

Checked on 2026-09-10.

## eamonlush/nideriji-archive-studio

Strengths:

- Browser extension; reuses the logged-in web session.
- Host permissions are limited to `https://nideriji.cn/*` and `https://f.nideriji.cn/*`.
- Builds a ZIP with `archive.json`, `statistics.json`, reports, Markdown, TXT, HTML, profiles and images.
- Has image validation, unavailable-image classification, and ZIP-based incremental image reuse.

Limitations for our use:

- Browser-first workflow is good for manual backup, but awkward for scheduled sync and later SQLite/vector indexing.
- I did not find privacy-region decryption code in the extension, so encrypted private blocks must be sampled and verified.

## zanghuaren/nideriji-download

Strengths:

- Python script; easier to adapt into a scheduled local sync.
- Calls the same sync/detail/image APIs.
- Includes AES privacy-region decryption logic.

Limitations for our use:

- Directly prompts for account password or expects constants in source.
- Sets `session.verify = False`, which disables TLS certificate verification.
- Outputs rendered Markdown/HTML plus a coarse stats file, not a full structured archive suitable as a durable master record.

## Decision

DiaryVault follows a custom implementation:

- Keep a structured local `archive.json` as the master record.
- Use safe runtime credential handling.
- Keep TLS verification enabled by default.
- Add privacy-region decryption as an optional local feature.
- Treat Markdown as a derived view, not the only source of truth.

